"""
Unit tests for tools/net_failure_drill.py (MOD-001, GOV-01-R03 / SCN-030
NET failure-drill foundation). No external network: the unreachable target
is simulated through an injected connector; loopback is real.
"""

from __future__ import annotations

import errno
import socket
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import net_failure_drill as nfd


def _raiser(exc: BaseException):
    def connector(address, timeout):
        raise exc

    return connector


def _routing_connector(target_connector):
    """Real connect for loopback, injected behaviour for everything else."""

    def connector(address, timeout):
        if address[0] == "127.0.0.1":
            return socket.create_connection(address, timeout=timeout)
        return target_connector(address, timeout)

    return connector


@pytest.fixture()
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.txt").write_text("x")
    return str(tmp_path)


def test_loopback_positive_control_connects():
    ok, detail = nfd.loopback_positive_control()
    assert ok, detail


def test_probe_classifies_real_loopback_refusal():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cls, _, _ = nfd.probe("127.0.0.1", port, 1.0)
    assert cls == nfd.REFUSED


def test_probe_classifies_timeout():
    cls, _, _ = nfd.probe("192.0.2.1", 81, 1.0, _raiser(TimeoutError("t")))
    assert cls == nfd.TIMEOUT


@pytest.mark.parametrize(
    "exc,expected",
    [
        (ConnectionRefusedError(errno.ECONNREFUSED, "refused"), nfd.REFUSED),
        (OSError(errno.ECONNRESET, "reset"), nfd.REFUSED),
        (OSError(errno.ENETUNREACH, "net"), nfd.UNREACHABLE),
        (OSError(errno.EHOSTUNREACH, "host"), nfd.UNREACHABLE),
        (OSError(errno.EPERM, "perm"), nfd.OTHER),
        (RuntimeError("boom"), nfd.OTHER),
    ],
)
def test_probe_non_timeout_classes(exc, expected):
    cls, _, _ = nfd.probe("192.0.2.1", 81, 1.0, _raiser(exc))
    assert cls == expected


def _fake_clock(*values: float):
    it = iter(values)
    return lambda: next(it)


def test_run_drill_passes_on_genuine_timeout(repo):
    conn = _routing_connector(_raiser(TimeoutError("timed out")))
    out: list[str] = []
    rc = nfd.run_drill(repo, connector=conn, clock=_fake_clock(0.0, 3.05), emit=out.append)
    assert rc == 0, out


def test_run_drill_fails_on_instant_timeout(repo):
    conn = _routing_connector(_raiser(TimeoutError("timed out")))
    out: list[str] = []
    rc = nfd.run_drill(repo, connector=conn, clock=_fake_clock(0.0, 0.01), emit=out.append)
    assert rc == 1
    assert any("not a genuine timeout" in m for m in out)


def test_check_target_accepts_timeout_within_bounds():
    assert nfd.check_target(nfd.TIMEOUT, 3.1, 3.0, 2.0) == []


def test_check_target_rejects_hang_and_instant_timeout():
    assert any("hang" in m for m in nfd.check_target(nfd.TIMEOUT, 9.0, 3.0, 2.0))
    assert any("genuine" in m for m in nfd.check_target(nfd.TIMEOUT, 0.01, 3.0, 2.0))


@pytest.mark.parametrize("cls", [nfd.REFUSED, nfd.UNREACHABLE, nfd.OTHER, nfd.CONNECTED])
def test_check_target_fails_closed_on_non_timeout_class(cls):
    failures = nfd.check_target(cls, 3.0, 3.0, 2.0)
    assert failures and cls in failures[0]


def test_run_drill_fails_closed_on_refusal_naming_class(repo):
    conn = _routing_connector(_raiser(ConnectionRefusedError(errno.ECONNREFUSED, "r")))
    out: list[str] = []
    assert nfd.run_drill(repo, connector=conn, emit=out.append) == 1
    assert any("'refused'" in m for m in out if m.startswith("DRILL-FAIL"))


def test_inverted_mode_turns_genuine_timeout_red(repo):
    conn = _routing_connector(_raiser(TimeoutError("timed out")))
    out: list[str] = []
    rc = nfd.run_drill(
        repo,
        invert=True,
        connector=conn,
        clock=_fake_clock(0.0, 3.05),
        emit=out.append,
    )
    assert rc == 1
    assert any("expected 'connected'" in m for m in out)


def test_invert_flag_does_not_change_normal_mode_expectation():
    assert nfd.check_target(nfd.TIMEOUT, 3.0, 3.0, 2.0, invert=False) == []
    assert nfd.check_target(nfd.TIMEOUT, 3.0, 3.0, 2.0, invert=True) != []


def test_state_change_during_drill_is_detected(repo):
    def mutating(address, timeout):
        Path(repo, "new.txt").write_text("changed")
        raise TimeoutError("t")

    out: list[str] = []
    rc = nfd.run_drill(repo, connector=_routing_connector(mutating), emit=out.append)
    assert rc == 1
    assert any("repository state changed" in m for m in out)


def test_non_repo_is_setup_error(tmp_path):
    out: list[str] = []
    assert nfd.run_drill(str(tmp_path), emit=out.append) == 2
