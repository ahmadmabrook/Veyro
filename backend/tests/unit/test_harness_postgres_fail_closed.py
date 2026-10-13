"""The disposable-Postgres harness fails closed (errors, never mocks or skips),
keeps its credential out of docker's argv, and only ever reaches the approved
Colima engine through one trusted route (CAP-008 P1-1).

The real CLI/engine are replaced by a scripted fake installed at the trusted
path via the module's pinned constants — a test seam, not a runtime override:
the harness itself reads no variable that could repoint its CLI."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tests.harness import postgres
from tests.harness.postgres import APPROVED_ENGINE, DisposablePostgres, disposable_postgres

SENTINEL_PASSWORD = "SENTINEL_NOT_A_REAL_PASSWORD_x9"
DESKTOP_ENGINE = {
    "Name": "docker-desktop",
    "ServerVersion": "29.4.0",
    "OperatingSystem": "Docker Desktop",
}

FAKE_DOCKER = """#!{python}
import json, os, sys
spec = json.load(open({spec!r}))
argv = sys.argv[1:]
config = argv[1] if argv[:1] == ["--config"] else None
try:
    config_json = open(os.path.join(config, "config.json")).read() if config else None
except OSError:
    config_json = None
with open({log!r}, "a") as log:
    log.write(json.dumps({{
        "argv": argv,
        "env": {{k: v for k, v in os.environ.items() if k.startswith("DOCKER_")}},
        "password_in_env": "POSTGRES_PASSWORD" in os.environ,
        "config_json": config_json,
    }}) + "\\n")
while argv[:1] in (["--config"], ["--host"]):
    argv = argv[2:]
sub = argv[0] if argv else ""
if sub == "--version":
    print(spec.get("version", "Docker version 29.6.0, build fake"))
elif sub == "info":
    if spec.get("info") is None:
        print("failed to connect to the docker API at " + {host!r}, file=sys.stderr)
        sys.exit(1)
    print(json.dumps(spec["info"]))
elif sub == "run":
    if spec.get("run_ok"):
        print("fakecontainerid")
    else:
        print("argv: " + " ".join(argv), file=sys.stderr)
        sys.exit(1)
elif sub == "port":
    print(spec.get("port", "127.0.0.1:1"))
elif sub == "logs":
    print("fake server log")
elif sub == "rm":
    pass
elif sub == "inspect":
    print("sha256:fakeconfigid")
elif sub == "image":
    print(json.dumps(spec.get("image", {{}})))
else:
    sys.exit(2)
"""


def _write_fake(path: Path, tmp_path: Path, spec: dict[str, Any], log: Path) -> Path:
    spec_file = tmp_path / f"spec-{path.parent.name}.json"
    spec_file.write_text(json.dumps(spec))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        FAKE_DOCKER.format(
            python=sys.executable, spec=str(spec_file), log=str(log), host="unix:///nowhere"
        )
    )
    path.chmod(0o755)
    return path


def _trust(monkeypatch: pytest.MonkeyPatch, cli: Path) -> None:
    monkeypatch.setattr(postgres, "TRUSTED_DOCKER_CLI", cli)
    monkeypatch.setattr(postgres, "TRUSTED_DOCKER_CLI_REALPATH", Path(os.path.realpath(cli)))


def _calls(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _subcommands(log: Path) -> list[str]:
    return [c["argv"][4] for c in _calls(log)]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in [k for k in os.environ if k.startswith("DOCKER_")]:
        monkeypatch.delenv(key)
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _n: SENTINEL_PASSWORD)
    # Any `docker` reached via PATH would log here; the harness must never use one.
    path_dir = tmp_path / "pathbin"
    _write_fake(
        path_dir / "docker",
        tmp_path,
        {"info": APPROVED_ENGINE, "run_ok": True},
        tmp_path / "path-docker.log",
    )
    monkeypatch.setenv("PATH", f"{path_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return tmp_path / "path-docker.log"


def _trusted_fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **spec: Any) -> Path:
    log = tmp_path / "trusted.log"
    cli = _write_fake(tmp_path / "trusted" / "docker", tmp_path, spec, log)
    _trust(monkeypatch, cli)
    return log


# --- CLI identity: no PATH, no Docker Desktop CLI -----------------------------------------


def test_missing_trusted_cli_is_an_error_not_a_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    _trust(monkeypatch, tmp_path / "absent" / "docker")
    with pytest.raises(RuntimeError, match="never substitutes a mock"), disposable_postgres():
        pass
    assert _calls(clean_env) == []  # a working `docker` on PATH was NOT used instead


def test_docker_on_path_is_never_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE)
    with pytest.raises(RuntimeError), disposable_postgres():
        pass
    assert _subcommands(log)[:2] == ["--version", "info"]
    assert _calls(clean_env) == []


def test_desktop_cli_symlinked_at_trusted_path_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    desktop_log = tmp_path / "desktop.log"
    desktop_cli = _write_fake(
        tmp_path / "Applications/Docker.app/Contents/Resources/bin/docker",
        tmp_path,
        {"info": APPROVED_ENGINE, "run_ok": True},
        desktop_log,
    )
    trusted = tmp_path / "homebrew/bin/docker"
    trusted.parent.mkdir(parents=True)
    trusted.symlink_to(desktop_cli)
    monkeypatch.setattr(postgres, "TRUSTED_DOCKER_CLI", trusted)
    monkeypatch.setattr(
        postgres,
        "TRUSTED_DOCKER_CLI_REALPATH",
        tmp_path / "homebrew/Cellar/docker/29.6.0/bin/docker",
    )
    with (
        pytest.raises(RuntimeError, match="refusing PATH or Docker Desktop's CLI"),
        disposable_postgres(),
    ):
        pass
    assert _calls(desktop_log) == []
    assert _calls(clean_env) == []


def test_cli_version_drift_is_rejected_before_engine_contact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(
        monkeypatch,
        tmp_path,
        info=APPROVED_ENGINE,
        run_ok=True,
        version="Docker version 28.0.1, build desktop",
    )
    with pytest.raises(RuntimeError, match="expected 29.6.0"), disposable_postgres():
        pass
    assert _subcommands(log) == ["--version"]


# --- Routing: isolated config, explicit Colima host, ambient context ignored --------------


def test_ambient_desktop_context_config_and_creds_are_not_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    ambient = tmp_path / "ambient-docker-config"
    ambient.mkdir()
    ambient_json = '{"credsStore": "desktop", "currentContext": "desktop-linux"}'
    (ambient / "config.json").write_text(ambient_json)
    monkeypatch.setenv("DOCKER_CONFIG", str(ambient))
    monkeypatch.setenv("DOCKER_CONTEXT", "desktop-linux")
    monkeypatch.setenv("DOCKER_TLS_VERIFY", "1")
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE)

    with pytest.raises(RuntimeError), disposable_postgres():
        pass

    calls = _calls(log)
    assert [c["argv"][4] for c in calls] == ["--version", "info", "run"]
    isolated = calls[0]["argv"][1]
    for call in calls:
        assert call["argv"][:4] == ["--config", isolated, "--host", postgres.COLIMA_DOCKER_HOST]
        assert call["env"] == {"DOCKER_CONFIG": isolated}  # DOCKER_CONTEXT/TLS stripped
        assert json.loads(call["config_json"]) == {}  # no credsStore, no currentContext
    assert isolated != str(ambient)
    assert postgres.COLIMA_DOCKER_HOST.endswith("/.colima/default/docker.sock")
    assert (ambient / "config.json").read_text() == ambient_json
    assert not Path(isolated).exists()  # isolated config is removed afterwards


# --- Engine identity: wrong engine and unreachable engine fail before `run` ---------------


def test_desktop_engine_on_default_route_is_rejected_before_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(monkeypatch, tmp_path, info=DESKTOP_ENGINE, run_ok=True)
    with (
        pytest.raises(RuntimeError, match="not the approved Colima binding") as caught,
        disposable_postgres(),
    ):
        pass
    assert "docker-desktop" in str(caught.value)
    assert "run" not in _subcommands(log)


def test_caller_docker_host_cannot_bypass_engine_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    foreign = "unix:///tmp/veyro-foreign-engine.sock"
    monkeypatch.setenv("DOCKER_HOST", foreign)
    log = _trusted_fake(monkeypatch, tmp_path, info=DESKTOP_ENGINE, run_ok=True)
    with (
        pytest.raises(RuntimeError, match="not the approved Colima binding"),
        disposable_postgres(),
    ):
        pass
    calls = _calls(log)
    assert all(c["argv"][2:4] == ["--host", foreign] for c in calls)
    assert all("DOCKER_HOST" not in c["env"] for c in calls)
    assert "run" not in _subcommands(log)


@pytest.mark.parametrize(
    "field_name, value",
    [("ServerVersion", "29.5.3"), ("OperatingSystem", "Docker Desktop"), ("Name", "lima-default")],
)
def test_engine_identity_drift_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path, field_name: str, value: str
) -> None:
    log = _trusted_fake(
        monkeypatch, tmp_path, info={**APPROVED_ENGINE, field_name: value}, run_ok=True
    )
    with (
        pytest.raises(RuntimeError, match="not the approved Colima binding"),
        disposable_postgres(),
    ):
        pass
    assert "run" not in _subcommands(log)


def test_engine_reporting_server_errors_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(
        monkeypatch, tmp_path, info={**APPROVED_ENGINE, "ServerErrors": ["boom"]}, run_ok=True
    )
    with pytest.raises(RuntimeError, match="no usable engine"), disposable_postgres():
        pass
    assert "run" not in _subcommands(log)


def test_unreachable_engine_fails_closed_before_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/veyro-no-daemon.sock")
    log = _trusted_fake(monkeypatch, tmp_path, info=None, run_ok=True)
    with (
        pytest.raises(RuntimeError, match="`docker info` exit 1.*never substitutes a mock"),
        disposable_postgres(),
    ):
        pass
    assert _subcommands(log) == ["--version", "info"]


# --- Credential handling, loopback, and one route for run/port/logs/cleanup ---------------


def test_superuser_password_never_in_docker_argv_or_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE)
    with pytest.raises(RuntimeError) as caught, disposable_postgres():
        pass
    msg = str(caught.value)
    assert "argv: run -d --rm" in msg  # the fake really received the call
    assert "-e POSTGRES_PASSWORD -p 127.0.0.1::5432" in msg  # name only, value via env
    assert "POSTGRES_PASSWORD=" not in msg
    assert SENTINEL_PASSWORD not in msg
    calls = _calls(log)
    assert all(SENTINEL_PASSWORD not in " ".join(c["argv"]) for c in calls)
    assert [c["password_in_env"] for c in calls] == [False, False, True]  # run only


def test_port_and_cleanup_use_the_same_trusted_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    # Nothing listens on 127.0.0.1:1, so readiness fails fast and cleanup must run.
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE, run_ok=True)
    with pytest.raises(Exception), disposable_postgres(ready_timeout_s=0):  # noqa: B017
        pass
    calls = _calls(log)
    assert [c["argv"][4] for c in calls] == ["--version", "info", "run", "port", "rm"]
    assert len({tuple(c["argv"][:4]) for c in calls}) == 1
    run_argv = calls[2]["argv"]
    assert calls[-1]["argv"][5:] == ["-f", "-v", run_argv[run_argv.index("--name") + 1]]  # same one
    assert SENTINEL_PASSWORD not in json.dumps(calls)


def test_error_path_teardown_removes_the_anonymous_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """BUG-051 (round 16, R16-1; corrected round 16 segment 3, R16-3): the
    image declares `VOLUME /var/lib/postgresql/data`, so every container
    gets an anonymous volume. The container is still running when this
    `finally`-block teardown call executes — it never exits on its own, so
    `--rm` never fires here; this `rm` call is what removes the container
    on **every** invocation, success or failure alike, not only on an error
    path. Before the fix it ran plain `docker rm -f`, which removed the
    container but left that anonymous volume behind: **one leak per
    fixture-using pytest session, unconditionally** — not one per
    failed/erroring session — with no ceiling on a fixed-size disk (round 16
    traced 473 orphaned volumes filling the Colima VM's 20GB disk to 100%,
    blocking every live Postgres-backed test). This pins the teardown's
    exact argv so a future edit that drops `-v` — restoring the leak — fails
    here, without needing a live Docker engine or a real volume count."""
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE, run_ok=True)
    with pytest.raises(Exception), disposable_postgres(ready_timeout_s=0):  # noqa: B017
        pass
    rm_call = _calls(log)[-1]
    assert rm_call["argv"][4] == "rm"
    assert "-v" in rm_call["argv"][5:], (
        f"teardown {rm_call['argv'][4:]!r} omits -v; the container's anonymous "
        "Postgres data volume would leak on every fixture-using session, not just a failed one"
    )


def test_non_loopback_publish_is_rejected_and_cleaned_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(
        monkeypatch, tmp_path, info=APPROVED_ENGINE, run_ok=True, port="0.0.0.0:5999"
    )
    with pytest.raises(RuntimeError, match="not 127.0.0.1"), disposable_postgres():
        pass
    assert _subcommands(log)[-1] == "rm"


def test_server_log_uses_the_same_trusted_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE)
    with postgres.trusted_docker() as docker:
        pg = DisposablePostgres("c", "127.0.0.1", 1, SENTINEL_PASSWORD, docker)
        assert pg.server_log().startswith("fake server log")
        assert SENTINEL_PASSWORD not in repr(pg)
    calls = _calls(log)
    assert [c["argv"][4] for c in calls] == ["--version", "info", "logs"]
    assert calls[-1]["argv"][:4] == ["--config", docker.config_dir, "--host", docker.host]


# --- Linux CI route (M1-C-07 B6) ----------------------------------------------------------
#
# The route exists so `backend-integration` can be a real blocking CI layer instead of a
# permanently denying one. It is not yet a qualified capability (the engine is outside
# CAP-008's Colima/arm64 scope), so these tests pin its *controls*, which is what makes a
# later qualification drill meaningful. Everything here runs against the same scripted fake
# as the Colima tests above: no live Docker, no live Linux engine.

GOOD_LINUX_ENGINE = {"OSType": "linux", "Architecture": "x86_64", "Name": "runner-host"}
GOOD_LINUX_IMAGE = {
    "Os": "linux",
    "Architecture": "amd64",
    "RepoDigests": [f"docker.io/library/postgres@{postgres.IMAGE.partition('@')[2]}"],
}


_SEAM_SOCKETS: list[tuple[socket.socket, Path]] = []


@pytest.fixture(autouse=True)
def _close_seam_sockets() -> Any:
    yield
    while _SEAM_SOCKETS:
        server, sock_dir = _SEAM_SOCKETS.pop()
        server.close()
        shutil.rmtree(sock_dir, ignore_errors=True)


def _linux_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spec: dict[str, Any], **overrides: Any
) -> Path:
    """Install the fake CLI and a real unix socket at the module's pinned Linux paths, and
    make the platform/hostname checks expect this host, so every *other* control can be
    exercised off a Linux runner. A test seam via the module's own constants — the route
    itself reads nothing that could repoint its CLI, socket or engine expectations."""
    log = tmp_path / "linux.log"
    cli = _write_fake(tmp_path / "usr" / "bin" / "docker", tmp_path, spec, log)
    # AF_UNIX paths are capped (~104 bytes on macOS), which pytest's tmp_path exceeds, so
    # the socket lives in its own short disposable directory, removed by the autouse fixture.
    sock_dir = Path(tempfile.mkdtemp(prefix="vq", dir="/tmp"))
    sock = sock_dir / "d.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _SEAM_SOCKETS.append((server, sock_dir))
    server.bind(str(sock))
    monkeypatch.setattr(postgres, "LINUX_PLATFORM", (os.uname().sysname, os.uname().machine))
    monkeypatch.setattr(postgres, "LINUX_DOCKER_CLI", cli)
    monkeypatch.setattr(postgres, "LINUX_DOCKER_CLI_ROOT", tmp_path / "usr")
    monkeypatch.setattr(postgres, "LINUX_DOCKER_SOCKET", sock)
    monkeypatch.setattr(postgres, "LINUX_DOCKER_HOST", f"unix://{sock}")
    monkeypatch.setenv(postgres.LINUX_CI_ROUTE_ENV_VAR, "1")
    for key, value in overrides.items():
        monkeypatch.setattr(postgres, key, value)
    return log


def _linux_engine(**overrides: Any) -> dict[str, Any]:
    return {**GOOD_LINUX_ENGINE, "Architecture": os.uname().machine,
            "Name": os.uname().nodename, **overrides}


def test_marker_unset_leaves_the_colima_route_exactly_as_it_was(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """The Linux route is strictly additive: with its marker unset — every local run — the
    CAP-008 route's probe order, host and isolated config are unchanged, and nothing on the
    Linux path executes. This is the regression guard for "preserve the qualified route"."""
    monkeypatch.delenv(postgres.LINUX_CI_ROUTE_ENV_VAR, raising=False)
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE)
    assert not postgres.linux_ci_route_requested()
    with postgres.trusted_docker() as route:
        assert route.host == postgres.COLIMA_DOCKER_HOST
        assert route.verify_container_image is False  # no image probe on the Colima route
    assert _subcommands(log) == ["--version", "info"]
    assert _calls(clean_env) == []


def test_the_marker_alone_never_designates_a_safe_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """Requesting the route is not being granted it. On a non-Linux host the platform proof
    denies, and the denial is an error — never a silent fall back to the Colima route."""
    monkeypatch.setenv(postgres.LINUX_CI_ROUTE_ENV_VAR, "1")
    log = _trusted_fake(monkeypatch, tmp_path, info=APPROVED_ENGINE, run_ok=True)
    with (
        pytest.raises(RuntimeError, match="not a substitute for the local Colima route"),
        postgres.trusted_docker(),
    ):
        pass
    assert _calls(log) == []
    assert _calls(clean_env) == []


@pytest.mark.parametrize(
    "variable, value",
    [
        ("DOCKER_HOST", "tcp://10.0.0.1:2375"),
        ("DOCKER_CONTEXT", "foreign"),
        ("PGHOSTADDR", "10.0.0.9"),
        ("PGSERVICE", "elsewhere"),
        ("PGPASSFILE", "/tmp/elsewhere"),
    ],
)
def test_ambient_engine_or_database_target_is_refused_not_stripped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path, variable: str, value: str
) -> None:
    """An ambient DOCKER_* is an ambient engine and an ambient libpq connection variable is
    an ambient database — both are refused before any docker call, because silently
    stripping an override hides that something tried to set one."""
    log = _linux_seam(monkeypatch, tmp_path, {"info": _linux_engine(), "image": GOOD_LINUX_IMAGE})
    monkeypatch.setenv(variable, value)
    with (
        pytest.raises(RuntimeError, match="refuses to run with ambient"),
        postgres.trusted_docker(),
    ):
        pass
    assert _calls(log) == []


def test_runner_postgres_tooling_variables_are_not_connection_targets() -> None:
    """The deliberate non-over-match: hosted runner images ship PGROOT/PGDATA/PGBIN, which
    are not libpq connection parameters. A bare `PG*` prefix sweep would deny them and make
    this layer unconditionally red for a reason unrelated to containment."""
    tooling = {"PGROOT": "/usr/lib/postgresql/16", "PGDATA": "/var/lib/pg", "PGBIN": "/usr/bin"}
    assert postgres.linux_env_denials(tooling) == []
    assert postgres.linux_env_denials({**tooling, "PGHOST": "elsewhere"}) != []


def test_cli_outside_the_pinned_system_root_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """A CI job's checkout and temp dirs are writable by the user the job runs as, so a
    `docker` the job itself could have written is not a trusted CLI."""
    spec = {"info": _linux_engine(), "image": GOOD_LINUX_IMAGE}
    _linux_seam(monkeypatch, tmp_path, spec)
    writable_log = tmp_path / "writable.log"
    writable = _write_fake(tmp_path / "writable" / "docker", tmp_path, spec, writable_log)
    monkeypatch.setattr(postgres, "LINUX_DOCKER_CLI", writable)
    with (
        pytest.raises(RuntimeError, match="the job itself could have written"),
        postgres.trusted_docker(),
    ):
        pass
    assert _calls(writable_log) == []  # the untrusted CLI never ran


def test_symlinked_docker_socket_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """A symlink at the pinned socket path could forward to a user-writable or remote
    socket, which would make the engine's own identity claim meaningless."""
    log = _linux_seam(monkeypatch, tmp_path, {"info": _linux_engine(), "image": GOOD_LINUX_IMAGE})
    link = postgres.LINUX_DOCKER_SOCKET.parent / "docker.sock.link"
    link.symlink_to(postgres.LINUX_DOCKER_SOCKET)
    monkeypatch.setattr(postgres, "LINUX_DOCKER_SOCKET", link)
    with (
        pytest.raises(RuntimeError, match="refusing a forwarded socket"),
        postgres.trusted_docker(),
    ):
        pass
    assert _calls(log) == []


def test_pinned_path_that_is_not_a_socket_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _linux_seam(monkeypatch, tmp_path, {"info": _linux_engine(), "image": GOOD_LINUX_IMAGE})
    plain = postgres.LINUX_DOCKER_SOCKET.parent / "not-a-socket"
    plain.write_text("")
    monkeypatch.setattr(postgres, "LINUX_DOCKER_SOCKET", plain)
    with pytest.raises(RuntimeError, match="is not a socket"), postgres.trusted_docker():
        pass
    assert _calls(log) == []


@pytest.mark.parametrize(
    "field_name, value, expected",
    [
        ("Name", "some-other-host", "not this host's own"),
        ("OSType", "windows", "not this host's own"),
        ("Architecture", "riscv64", "not this host's own"),
        ("ServerErrors", ["boom"], "no usable engine"),
    ],
)
def test_engine_that_is_not_this_hosts_own_linux_engine_is_rejected_before_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    clean_env: Path,
    field_name: str,
    value: Any,
    expected: str,
) -> None:
    """The locality proof that stands in for the version pins the Colima route uses: this
    route cannot pin an unobserved hosted-runner docker version, so the engine must instead
    identify as this host's own linux engine."""
    log = _linux_seam(
        monkeypatch,
        tmp_path,
        {"info": _linux_engine(**{field_name: value}), "image": GOOD_LINUX_IMAGE},
    )
    with pytest.raises(RuntimeError, match=expected), postgres.trusted_docker():
        pass
    assert "run" not in _subcommands(log)


def test_linux_route_does_not_probe_a_pinned_cli_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """Pinning a CLI version nobody has observed would be an invented pin, and GitHub
    re-rolls its runner images regularly — the permanently-red outcome B6 warns about."""
    log = _linux_seam(monkeypatch, tmp_path, {"info": _linux_engine(), "image": GOOD_LINUX_IMAGE})
    with postgres.trusted_docker() as route:
        assert route.verify_container_image is True
    assert _subcommands(log) == ["info"]


@pytest.mark.parametrize(
    "image, expected",
    [
        ({**GOOD_LINUX_IMAGE, "Architecture": "arm64"}, r"expected \('linux', 'amd64'\)"),
        (
            {**GOOD_LINUX_IMAGE, "RepoDigests": ["postgres@sha256:" + "0" * 64]},
            "does not carry the pinned digest",
        ),
        ({**GOOD_LINUX_IMAGE, "RepoDigests": []}, "does not carry the pinned digest"),
    ],
)
def test_running_container_must_prove_the_pinned_amd64_image(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    clean_env: Path,
    image: dict[str, Any],
    expected: str,
) -> None:
    """Since this route pins no engine version, it proves the image instead: the container
    actually running must come from the digest-pinned IMAGE, resolved to that OCI index's
    linux/amd64 child, rather than trusting `docker run` to have honoured the digest. The
    container is torn down and never connected to."""
    log = _linux_seam(
        monkeypatch, tmp_path, {"info": _linux_engine(), "image": image, "run_ok": True}
    )
    with pytest.raises(RuntimeError, match=expected), disposable_postgres(ready_timeout_s=0):
        pass
    assert _subcommands(log) == ["info", "run", "port", "inspect", "image", "rm"]
    assert _calls(log)[-1]["argv"][5:7] == ["-f", "-v"]  # container and volume both removed


def test_linux_positive_path_is_loopback_only_with_a_credential_never_in_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    """The image proof passes, so the run proceeds to readiness and fails there (nothing
    listens on the fake port) — which is what lets this assert the containment shape:
    loopback-only ephemeral publish, the digest-pinned image, the per-run credential passed
    by name only, and `rm -f -v` teardown. Credential separation (admin superuser for DDL,
    the non-privileged runtime role for every probe) is the integration conftest's, unchanged
    by this route."""
    log = _linux_seam(
        monkeypatch,
        tmp_path,
        {"info": _linux_engine(), "image": GOOD_LINUX_IMAGE, "run_ok": True},
    )
    with (
        pytest.raises(Exception),  # noqa: B017 - readiness, not a containment denial
        disposable_postgres(ready_timeout_s=0),
    ):
        pass
    assert _subcommands(log) == ["info", "run", "port", "inspect", "image", "rm"]
    run_argv = next(c["argv"] for c in _calls(log) if c["argv"][4] == "run")
    assert run_argv[run_argv.index("-p") + 1] == f"{postgres.LOOPBACK}::5432"
    assert postgres.IMAGE in run_argv
    assert run_argv[run_argv.index("-e") + 1] == "POSTGRES_PASSWORD"
    assert all(SENTINEL_PASSWORD not in json.dumps(c) for c in _calls(log))
    assert [c["password_in_env"] for c in _calls(log)] == [
        c["argv"][4] == "run" for c in _calls(log)
    ]


def test_linux_non_loopback_publish_is_rejected_and_cleaned_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean_env: Path
) -> None:
    log = _linux_seam(
        monkeypatch,
        tmp_path,
        {
            "info": _linux_engine(),
            "image": GOOD_LINUX_IMAGE,
            "run_ok": True,
            "port": "0.0.0.0:5999",
        },
    )
    with pytest.raises(RuntimeError, match="not 127.0.0.1"), disposable_postgres():
        pass
    # Denied before the image was even inspected, and torn down.
    assert _subcommands(log) == ["info", "run", "port", "rm"]
