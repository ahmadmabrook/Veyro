"""M1-C-07 B6 — focused deterministic check of the Linux CI Postgres route.

Deliberately NOT a pytest module. The CAP-011 independent determination
(2026-10-09) leaves CAP-011 `QUALIFIED — NOT APPROVED` on both verdicts and
states that no pytest run on any Veyro path is authorised, so this exercises
the route's decision logic directly under a plain interpreter instead.

What it proves:
  * the already-qualified CAP-008 Colima route is behaviourally unchanged
    when the Linux marker is unset (argv, host, isolated config, defaults);
  * every Linux-route control denies when its own precondition is violated,
    and denies before any container is created;
  * the positive Linux path reaches run -> port -> image proof -> teardown in
    that order, with the per-run credential never in argv or in an error.

What it does NOT prove, and cannot: that a real GitHub-hosted linux/amd64
engine satisfies these controls. The engine and CLI here are a scripted fake
installed at the module's pinned paths via its own constants — the same test
seam the committed fail-closed suite uses. No live Linux engine has been
observed. See the B6 evidence record for the residual requirements.

Run:  backend/.venv/bin/python -I \
        knowledge/03-Modules/MOD-001/evidence/implementation/tools/m1c07_b6_route_check.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# `-I` ignores PYTHONPATH, so resolve `backend/` from this file's own location
# rather than relying on the caller's environment.
BACKEND_ROOT = Path(__file__).resolve().parents[6] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from tests.harness import postgres
from tests.harness.postgres import (
    DockerRoute,
    disposable_postgres,
    trusted_docker,
)

SENTINEL_PASSWORD = "SENTINEL_NOT_A_REAL_PASSWORD_b6"
PINNED_DIGEST = postgres.IMAGE.partition("@")[2]

FAKE_DOCKER = """#!{python}
import json, os, sys
spec = json.load(open({spec!r}))
argv = sys.argv[1:]
with open({log!r}, "a") as log:
    log.write(json.dumps({{
        "argv": argv,
        "env": {{k: v for k, v in os.environ.items() if k.startswith("DOCKER_")}},
        "password_in_env": "POSTGRES_PASSWORD" in os.environ,
    }}) + "\\n")
while argv[:1] in (["--config"], ["--host"]):
    argv = argv[2:]
sub = argv[0] if argv else ""
if sub == "--version":
    print("Docker version 29.6.0, build fake")
elif sub == "info":
    if spec.get("info") is None:
        print("cannot connect to the docker daemon", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(spec["info"]))
elif sub == "run":
    print("fakecontainerid")
elif sub == "port":
    print(spec.get("port", "127.0.0.1:1"))
elif sub == "inspect":
    print("sha256:fakeconfigid")
elif sub == "image":
    print(json.dumps(spec.get("image", {{}})))
elif sub in ("rm", "logs"):
    pass
else:
    sys.exit(2)
"""

GOOD_IMAGE = {
    "Os": "linux",
    "Architecture": "amd64",
    "RepoDigests": [f"docker.io/library/postgres@{PINNED_DIGEST}"],
}

failures: list[str] = []
checks = 0
_seam_count = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  PASS  {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def write_fake(path: Path, tmp: Path, spec: dict[str, Any], log: Path) -> Path:
    spec_file = tmp / f"spec-{path.parent.name}-{path.name}.json"
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.write_text(json.dumps(spec))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE_DOCKER.format(python=sys.executable, spec=str(spec_file), log=str(log)))
    path.chmod(0o755)
    return path


def calls(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def subcommands(log: Path) -> list[str]:
    return [c["argv"][4] for c in calls(log)]


def denial(fn: Any) -> str:
    """Run `fn`, returning the RuntimeError message, or '' if none was raised."""
    try:
        fn()
    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - a non-RuntimeError is explicitly NOT a denial
        return f"<{type(exc).__name__}: {exc}>"
    return ""


@contextmanager
def linux_seam(tmp: Path, *, spec: dict[str, Any] | None = None, env: dict[str, str] | None = None):
    """Install the fake CLI + a real unix socket at the module's pinned Linux
    paths, and make the platform check expect this host, so the *other*
    controls can be exercised on a developer machine. Restores everything."""
    saved = {
        k: getattr(postgres, k)
        for k in ("LINUX_PLATFORM", "LINUX_DOCKER_CLI", "LINUX_DOCKER_CLI_ROOT",
                  "LINUX_DOCKER_SOCKET", "LINUX_DOCKER_HOST")
    }
    saved_env = dict(os.environ)
    # One fresh directory per seam: the CLI log and the unix socket must not be
    # shared between cases, or a later case would read an earlier one's calls.
    global _seam_count
    _seam_count += 1
    tmp = tmp / f"seam{_seam_count}"
    tmp.mkdir(parents=True)
    log = tmp / "linux.log"
    cli = write_fake(tmp / "usr" / "bin" / "docker", tmp, spec or {}, log)
    sock_path = tmp / "run" / "docker.sock"
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    try:
        postgres.LINUX_PLATFORM = (os.uname().sysname, os.uname().machine)
        postgres.LINUX_DOCKER_CLI = cli
        postgres.LINUX_DOCKER_CLI_ROOT = tmp / "usr"
        postgres.LINUX_DOCKER_SOCKET = sock_path
        postgres.LINUX_DOCKER_HOST = f"unix://{sock_path}"
        for key in [k for k in os.environ if k.startswith(("DOCKER_", "PG"))]:
            del os.environ[key]
        os.environ[postgres.LINUX_CI_ROUTE_ENV_VAR] = "1"
        os.environ.update(env or {})
        yield log
    finally:
        srv.close()
        for key, value in saved.items():
            setattr(postgres, key, value)
        os.environ.clear()
        os.environ.update(saved_env)


def engine_info(**overrides: Any) -> dict[str, Any]:
    info = {
        "OSType": "linux",
        "Architecture": os.uname().machine,
        "Name": os.uname().nodename,
    }
    info.update(overrides)
    return info


# --------------------------------------------------------------------------
# 1. The qualified Colima route is unchanged when the marker is unset.
# --------------------------------------------------------------------------
def check_colima_route_unchanged(tmp: Path) -> None:
    print("\n1. CAP-008 Colima route unchanged (marker unset)")
    saved = (postgres.TRUSTED_DOCKER_CLI, postgres.TRUSTED_DOCKER_CLI_REALPATH)
    saved_env = dict(os.environ)
    log = tmp / "colima.log"
    cli = write_fake(tmp / "trusted" / "docker", tmp, {"info": postgres.APPROVED_ENGINE}, log)
    try:
        for key in [k for k in os.environ if k.startswith("DOCKER_")]:
            del os.environ[key]
        os.environ.pop(postgres.LINUX_CI_ROUTE_ENV_VAR, None)
        postgres.TRUSTED_DOCKER_CLI = cli
        postgres.TRUSTED_DOCKER_CLI_REALPATH = Path(os.path.realpath(cli))

        check("marker unset is not a Linux-route request", not postgres.linux_ci_route_requested())
        with trusted_docker() as route:
            observed = calls(log)
            check("route is the Colima socket, not the Linux one",
                  route.host == postgres.COLIMA_DOCKER_HOST, route.host)
            check("verify_container_image defaults off on the Colima route",
                  route.verify_container_image is False)
            check("probe order is --version then info (pre-B6 shape)",
                  [c["argv"][4] for c in observed] == ["--version", "info"],
                  str([c["argv"][4] for c in observed]))
            check("every call carries --config <isolated> --host <colima>",
                  all(c["argv"][:4] == ["--config", route.config_dir, "--host", route.host]
                      for c in observed))
            check("ambient DOCKER_* stripped from the child env",
                  all(c["env"] == {"DOCKER_CONFIG": route.config_dir} for c in observed))
        check("3-positional DockerRoute still constructs with the old signature",
              DockerRoute("c", "h", "d").verify_container_image is False)
    finally:
        postgres.TRUSTED_DOCKER_CLI, postgres.TRUSTED_DOCKER_CLI_REALPATH = saved
        os.environ.clear()
        os.environ.update(saved_env)


# --------------------------------------------------------------------------
# 2. The marker alone never designates a safe engine.
# --------------------------------------------------------------------------
def check_marker_is_not_authority(tmp: Path) -> None:
    print("\n2. Marker alone grants nothing (real platform check, unpatched)")
    saved_env = dict(os.environ)
    try:
        os.environ[postgres.LINUX_CI_ROUTE_ENV_VAR] = "1"
        msg = denial(lambda: trusted_docker().__enter__())
        check("requested on this non-Linux host -> denied",
              "is not" in msg and "Linux CI Postgres route" in msg, msg[:160])
        check("denial does not fall back to the Colima route",
              "Colima" not in msg or "not a substitute" in msg, msg[:160])
    finally:
        os.environ.clear()
        os.environ.update(saved_env)


# --------------------------------------------------------------------------
# 3. Ambient engine / database targets are refused, not stripped.
# --------------------------------------------------------------------------
def check_ambient_targets(tmp: Path) -> None:
    print("\n3. Ambient DOCKER_*/libpq targets refused")
    spec = {"info": engine_info(), "image": GOOD_IMAGE}
    for label, env, expect in [
        ("DOCKER_HOST", {"DOCKER_HOST": "tcp://10.0.0.1:2375"}, "ambient Docker engine"),
        ("DOCKER_CONTEXT", {"DOCKER_CONTEXT": "foreign"}, "ambient Docker engine"),
        ("PGHOSTADDR", {"PGHOSTADDR": "10.0.0.9"}, "ambient libpq connection"),
        ("PGSERVICE", {"PGSERVICE": "elsewhere"}, "ambient libpq connection"),
        ("PGPASSWORD", {"PGPASSWORD": "x"}, "ambient libpq connection"),
    ]:
        with linux_seam(tmp, spec=spec, env=env) as log:
            msg = denial(lambda: trusted_docker().__enter__())
            check(f"ambient {label} -> denied", expect in msg, msg[:160])
            check(f"ambient {label} -> no docker call at all", calls(log) == [])

    # The non-over-match half: runner-image PostgreSQL *tooling* variables are
    # not libpq connection parameters and must not deny.
    tooling = {"PGROOT": "/usr/lib/postgresql/16", "PGDATA": "/var/lib/postgresql", "PGBIN": "/x"}
    check("PGROOT/PGDATA/PGBIN are not treated as connection targets",
          postgres.linux_env_denials(tooling) == [], str(postgres.linux_env_denials(tooling)))
    check("a bare PG-prefix sweep would have denied them (so this is deliberate)",
          [k for k in tooling if k.startswith("PG")] != [])


# --------------------------------------------------------------------------
# 4. CLI, socket and engine proofs each deny before any container exists.
# --------------------------------------------------------------------------
def check_target_proofs(tmp: Path) -> None:
    print("\n4. CLI / socket / engine proofs deny before `run`")
    spec = {"info": engine_info(), "image": GOOD_IMAGE}

    with linux_seam(tmp, spec=spec) as log:
        postgres.LINUX_DOCKER_CLI = tmp / "usr" / "bin" / "absent-docker"
        msg = denial(lambda: trusted_docker().__enter__())
        check("missing CLI -> denied", "not an executable regular file" in msg, msg[:160])
        check("missing CLI -> no docker call", calls(log) == [])

    with linux_seam(tmp, spec=spec) as log:
        outside = write_fake(tmp / "writable" / "docker", tmp, spec, tmp / "outside.log")
        postgres.LINUX_DOCKER_CLI = outside
        msg = denial(lambda: trusted_docker().__enter__())
        check("CLI outside the pinned system root -> denied",
              "the job itself could have written" in msg, msg[:160])
        check("CLI outside the pinned root -> that CLI never ran",
              calls(tmp / "outside.log") == [])

    with linux_seam(tmp, spec=spec) as log:
        link = postgres.LINUX_DOCKER_SOCKET.parent / "docker.sock.link"
        link.symlink_to(postgres.LINUX_DOCKER_SOCKET)
        postgres.LINUX_DOCKER_SOCKET = link
        msg = denial(lambda: trusted_docker().__enter__())
        check("symlinked socket -> denied", "refusing a forwarded socket" in msg, msg[:160])
        check("symlinked socket -> no docker call", calls(log) == [])

    with linux_seam(tmp, spec=spec) as log:
        plain = postgres.LINUX_DOCKER_SOCKET.parent / "not-a-socket"
        plain.write_text("")
        postgres.LINUX_DOCKER_SOCKET = plain
        msg = denial(lambda: trusted_docker().__enter__())
        check("pinned path that is not a socket -> denied", "is not a socket" in msg, msg[:160])
        check("not-a-socket -> no docker call", calls(log) == [])

    with linux_seam(tmp, spec=spec) as log:
        postgres.LINUX_DOCKER_SOCKET = postgres.LINUX_DOCKER_SOCKET.parent / "vanished.sock"
        msg = denial(lambda: trusted_docker().__enter__())
        check("absent socket -> denied", "is not usable" in msg, msg[:160])

    for label, info, expect in [
        ("foreign hostname", engine_info(Name="some-other-host"), "not this host's own"),
        ("non-linux OSType", engine_info(OSType="windows"), "not this host's own"),
        ("wrong architecture", engine_info(Architecture="riscv64"), "not this host's own"),
        ("ServerErrors present", engine_info(ServerErrors=["boom"]), "no usable engine"),
        ("unreachable engine", None, "docker info"),
    ]:
        with linux_seam(tmp, spec={"info": info, "image": GOOD_IMAGE}) as log:
            msg = denial(lambda: trusted_docker().__enter__())
            check(f"engine {label} -> denied", expect in msg, msg[:160])
            check(f"engine {label} -> never reached `run`", "run" not in subcommands(log),
                  str(subcommands(log)))


# --------------------------------------------------------------------------
# 5. Container containment: image proof, loopback, credential, teardown.
# --------------------------------------------------------------------------
def check_container_containment(tmp: Path) -> None:
    print("\n5. Container containment on the Linux route")
    import secrets as secrets_mod

    saved_token = secrets_mod.token_urlsafe
    secrets_mod.token_urlsafe = lambda _n: SENTINEL_PASSWORD  # type: ignore[assignment]
    try:
        # Positive: image proof passes, then readiness fails against the fake
        # port (nothing listens on 127.0.0.1:1) and teardown runs.
        with linux_seam(tmp, spec={"info": engine_info(), "image": GOOD_IMAGE}) as log:
            msg = denial(lambda: disposable_postgres(ready_timeout_s=0).__enter__())
            seq = subcommands(log)
            check("positive path order: info, run, port, inspect, image, rm",
                  seq == ["info", "run", "port", "inspect", "image", "rm"], str(seq))
            check("no --version probe on the Linux route (no invented version pin)",
                  "--version" not in seq)
            check("image proof passed, so the failure is readiness, not a denial",
                  "OperationalError" in msg or msg.startswith("<"), msg[:160])
            run_argv = next(c["argv"] for c in calls(log) if c["argv"][4] == "run")
            check("published on loopback with an ephemeral port",
                  "-p" in run_argv and run_argv[run_argv.index("-p") + 1] == "127.0.0.1::5432",
                  str(run_argv))
            check("image is the digest-pinned reference",
                  postgres.IMAGE in run_argv, str(run_argv))
            check("credential passed by name only, never as an argv value",
                  run_argv[run_argv.index("-e") + 1] == "POSTGRES_PASSWORD"
                  and all(SENTINEL_PASSWORD not in " ".join(c["argv"]) for c in calls(log)))
            check("credential is in the child env for `run` only",
                  [c["password_in_env"] for c in calls(log)] == [
                      c["argv"][4] == "run" for c in calls(log)])
            rm_argv = calls(log)[-1]["argv"]
            check("teardown removes container AND anonymous volume (-f -v)",
                  rm_argv[4:7] == ["rm", "-f", "-v"], str(rm_argv[4:]))
            check("teardown names this exact container",
                  rm_argv[7] == run_argv[run_argv.index("--name") + 1])
            check("credential never appears in the surfaced error",
                  SENTINEL_PASSWORD not in msg)

        # Negative: the running container's image is the wrong platform.
        wrong_arch = {**GOOD_IMAGE, "Architecture": "arm64"}
        with linux_seam(tmp, spec={"info": engine_info(), "image": wrong_arch}) as log:
            msg = denial(lambda: disposable_postgres(ready_timeout_s=0).__enter__())
            check("container image of the wrong platform -> denied",
                  "expected ('linux', 'amd64')" in msg, msg[:160])
            check("wrong-platform image -> never connected to, and torn down",
                  subcommands(log) == ["info", "run", "port", "inspect", "image", "rm"],
                  str(subcommands(log)))

        # Negative: the image does not carry the pinned digest.
        wrong_digest = {**GOOD_IMAGE, "RepoDigests": ["postgres@sha256:" + "0" * 64]}
        with linux_seam(tmp, spec={"info": engine_info(), "image": wrong_digest}) as log:
            msg = denial(lambda: disposable_postgres(ready_timeout_s=0).__enter__())
            check("image without the pinned digest -> denied",
                  "does not carry the pinned digest" in msg, msg[:160])
            check("unpinned image -> torn down, never connected to",
                  subcommands(log)[-1] == "rm", str(subcommands(log)))

        # Negative: a non-loopback publish is refused on this route too.
        with linux_seam(
            tmp, spec={"info": engine_info(), "image": GOOD_IMAGE, "port": "0.0.0.0:5999"}
        ) as log:
            msg = denial(lambda: disposable_postgres(ready_timeout_s=0).__enter__())
            check("non-loopback publish -> denied", "not 127.0.0.1" in msg, msg[:160])
            check("non-loopback publish -> image never inspected, container torn down",
                  subcommands(log) == ["info", "run", "port", "rm"], str(subcommands(log)))
    finally:
        secrets_mod.token_urlsafe = saved_token  # type: ignore[assignment]


def main() -> int:
    print("M1-C-07 B6 Linux CI Postgres route — focused deterministic check")
    print(f"host={os.uname().sysname}/{os.uname().machine}  python={sys.version.split()[0]}")
    print(f"pinned image digest={PINNED_DIGEST}")
    with tempfile.TemporaryDirectory(prefix="m1c07-b6-") as raw:
        for name, fn in [
            ("colima", check_colima_route_unchanged),
            ("marker", check_marker_is_not_authority),
            ("ambient", check_ambient_targets),
            ("proofs", check_target_proofs),
            ("containment", check_container_containment),
        ]:
            sub = Path(raw) / name
            sub.mkdir(parents=True)
            fn(sub)
    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("FAILURES:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("ALL PASS — scripted-fake coverage only; no live Linux engine observed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
