"""
Shared NET failure-drill prober (MOD-001, GOV-01-R03 / SCN-MOD001-030
foundation, M1-C-06).

Per `knowledge/03-Modules/MOD-001/evidence/implementation/
M1-C-06-TRUSTED-CI-ROUTING-DECISION-2026-10-09.md` sections 1, 2, 5 and 8:
a zero-authority drill of the CI environment's own failure classification.
It consumes no candidate input - its only inputs are the constants below
(or explicit CLI flags used by local tests) - and uses stdlib + `git`
only. It is a drill, not a gate: its conclusion is not a trust anchor.

Controls asserted (all must hold for exit 0):
  1. Positive control: a stdlib loopback listener on 127.0.0.1 accepts a
     connection quickly, proving the prober can observe success.
  2. Timeout negative control: RFC 5737 TEST-NET-1 (192.0.2.1) must
     classify as a genuine TIMEOUT - not "connected", not connection
     refused/reset, not unreachable, not another error. Any other class
     fails closed with that explicit class named.
  3. Bounded elapsed time: the timeout must elapse within
     [timeout * MIN_FRACTION, timeout + tolerance]; slower is a hang,
     much faster is not a real timeout.
  4. State control: SHA-256 of `git status --porcelain=v1 -uall` of the
     repository before and after must match.

`--invert` flips the target expectation to "connected" so a genuine
timeout turns the run RED. It exists only for a future disposable red
run proving no suppression; it never makes the normal mode pass.

Exit codes: 0 all controls hold; 1 a control failed; 2 usage/setup error.
Evidence is the inspected run output, not a claim of scenario PASS.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import socket
import subprocess
import sys
import time
from collections.abc import Callable

TARGET_HOST = "192.0.2.1"  # RFC 5737 TEST-NET-1; never routable.
TARGET_PORT = 81
TIMEOUT_SECONDS = 3.0
TOLERANCE_SECONDS = 2.0
MIN_FRACTION = 0.5
LOOPBACK_BOUND_SECONDS = 1.0

CONNECTED = "connected"
TIMEOUT = "timeout"
REFUSED = "refused"
UNREACHABLE = "unreachable"
OTHER = "other"

_REFUSED_ERRNOS = {errno.ECONNREFUSED, errno.ECONNRESET}
_UNREACHABLE_ERRNOS = {
    errno.ENETUNREACH,
    errno.EHOSTUNREACH,
    getattr(errno, "ENETDOWN", -1),
    getattr(errno, "EHOSTDOWN", -1),
}

Connector = Callable[[tuple, float], socket.socket]


def _default_connector(address: tuple, timeout: float) -> socket.socket:
    return socket.create_connection(address, timeout=timeout)


def probe(
    host: str,
    port: int,
    timeout: float,
    connector: Connector = _default_connector,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[str, float, str]:
    """Attempt one TCP connect; return (class, elapsed_seconds, detail)."""
    start = clock()
    try:
        sock = connector((host, port), timeout)
    except TimeoutError as exc:  # socket.timeout is an alias on 3.10+
        return TIMEOUT, clock() - start, f"{type(exc).__name__}: {exc}"
    except OSError as exc:
        elapsed = clock() - start
        detail = f"{type(exc).__name__} errno={exc.errno}: {exc}"
        if isinstance(exc, ConnectionRefusedError) or exc.errno in _REFUSED_ERRNOS:
            return REFUSED, elapsed, detail
        if exc.errno in _UNREACHABLE_ERRNOS:
            return UNREACHABLE, elapsed, detail
        return OTHER, elapsed, detail
    except Exception as exc:  # noqa: BLE001 - fail closed with explicit class
        return OTHER, clock() - start, f"{type(exc).__name__}: {exc}"
    elapsed = clock() - start
    sock.close()
    return CONNECTED, elapsed, "connection established"


def repo_state_hash(repo: str) -> str:
    """SHA-256 of `git status --porcelain=v1 -uall` for `repo`."""
    out = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain=v1", "-uall"],
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(out).hexdigest()


def loopback_positive_control(
    connector: Connector = _default_connector,
) -> tuple[bool, str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        cls, elapsed, detail = probe("127.0.0.1", port, LOOPBACK_BOUND_SECONDS, connector)
    finally:
        listener.close()
    ok = cls == CONNECTED and elapsed < LOOPBACK_BOUND_SECONDS
    return ok, f"class={cls} elapsed={elapsed:.3f}s detail={detail}"


def check_target(
    cls: str,
    elapsed: float,
    timeout: float,
    tolerance: float,
    invert: bool = False,
) -> list[str]:
    """Return failure messages for the unreachable-target observation."""
    failures: list[str] = []
    expected = CONNECTED if invert else TIMEOUT
    if cls != expected:
        failures.append(f"target class {cls!r} != expected {expected!r}")
    if not invert and cls == TIMEOUT:
        if elapsed > timeout + tolerance:
            failures.append(
                f"elapsed {elapsed:.3f}s exceeds bound {timeout + tolerance:.3f}s (hang)"
            )
        if elapsed < timeout * MIN_FRACTION:
            failures.append(
                f"elapsed {elapsed:.3f}s below {timeout * MIN_FRACTION:.3f}s "
                "(not a genuine timeout)"
            )
    return failures


def run_drill(
    repo: str,
    host: str = TARGET_HOST,
    port: int = TARGET_PORT,
    timeout: float = TIMEOUT_SECONDS,
    tolerance: float = TOLERANCE_SECONDS,
    invert: bool = False,
    connector: Connector = _default_connector,
    clock: Callable[[], float] = time.monotonic,
    emit: Callable[[str], None] = print,
) -> int:
    try:
        before = repo_state_hash(repo)
    except (subprocess.CalledProcessError, OSError) as exc:
        emit(f"SETUP-ERROR: cannot hash repository state: {exc}")
        return 2
    emit(f"repo-state-before sha256={before}")
    failures: list[str] = []

    ok, detail = loopback_positive_control(connector)
    emit(f"positive-control {'OK' if ok else 'FAIL'}: {detail}")
    if not ok:
        failures.append("loopback positive control failed")

    cls, elapsed, detail = probe(host, port, timeout, connector, clock)
    emit(
        f"target {host}:{port} class={cls} elapsed={elapsed:.3f}s "
        f"timeout={timeout}s tolerance={tolerance}s invert={invert} detail={detail}"
    )
    failures.extend(check_target(cls, elapsed, timeout, tolerance, invert))

    after = repo_state_hash(repo)
    emit(f"repo-state-after  sha256={after}")
    if before != after:
        failures.append("repository state changed during drill")

    if failures:
        for message in failures:
            emit(f"DRILL-FAIL: {message}")
        return 1
    emit("DRILL-OK: all controls held (inspected run is the evidence; not a gate)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="repository to hash (default .)")
    parser.add_argument("--host", default=TARGET_HOST)
    parser.add_argument("--port", type=int, default=TARGET_PORT)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE_SECONDS)
    parser.add_argument(
        "--invert",
        action="store_true",
        help="deliberately inverted assertion for a disposable red run",
    )
    args = parser.parse_args(argv)
    return run_drill(args.repo, args.host, args.port, args.timeout, args.tolerance, args.invert)


if __name__ == "__main__":
    sys.exit(main())
