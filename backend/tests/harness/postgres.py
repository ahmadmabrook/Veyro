"""Disposable, local-only Postgres for the GOV-01-R02 harnesses.

One throwaway container per pytest session: random container name, random
superuser password generated at runtime (nothing credential-shaped is ever
committed), published on 127.0.0.1 only, force-removed on exit. It only ever
holds synthetic fixture rows.

The superuser DSN is the elevated *setup* credential (role creation, fixture
DDL, ground-truth reads). It is never the connection under test — negative
isolation tests connect as the non-privileged runtime role from
`tenant_isolation`. No Docker means the harness errors out: it never falls back
to SQLite or a mock, because a mocked denial is exactly the false-clean
evidence this harness exists to prevent.

Engine binding (CAP-008, Colima). Every docker call goes through one
`DockerRoute`: the pinned Homebrew docker CLI (never whatever `docker` is
first on PATH, and never Docker.app's CLI), a fresh empty `--config` dir (so
no ambient context, `credsStore` or CLI plugin/hook is consulted), all
ambient `DOCKER_*` variables stripped, and an explicit `--host`. The host is
Colima's socket unless the caller sets `DOCKER_HOST` — which only negative
drills do, to point at an unreachable or foreign engine. Either way the
engine must identify as the approved Colima engine before anything runs; a
Docker Desktop or otherwise unapproved engine is an error, never a fallback.
Cleanup, port and log calls reuse the same route.

Second engine binding (M1-C-07 B6, Linux CI). A separate, explicitly
opted-in route reaches a Linux CI runner's own Docker engine, so the
integration layer can be a real blocking CI layer instead of a permanently
denying one. It is strictly additive: with its marker unset — every local
run — not one statement of it executes and the Colima route above behaves
exactly as before. See `_linux_ci_docker` for why its proofs are
*properties of the live target* rather than pinned version strings, and
`knowledge/03-Modules/MOD-001/evidence/implementation/M1-C-07-B6-LINUX-CI-POSTGRES-ROUTE-2026-10-09.md`
for what is still unqualified about it.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

# postgres:16-alpine, pinned by content digest so a moved tag can't change
# what runs. Bump deliberately (docker pull postgres:16-alpine; docker image
# inspect ... RepoDigests), never by editing the tag back in.
IMAGE = "postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
SUPERUSER = "postgres"

# The CAP-008 Colima binding, pinned the same way as IMAGE: any drift (a brew
# upgrade, a recreated VM, a different engine behind the socket) fails closed
# until it is deliberately re-qualified and these values bumped.
TRUSTED_DOCKER_CLI = Path("/opt/homebrew/bin/docker")
TRUSTED_DOCKER_CLI_REALPATH = Path("/opt/homebrew/Cellar/docker/29.6.0/bin/docker")
TRUSTED_DOCKER_CLI_VERSION = "29.6.0"
COLIMA_DOCKER_HOST = f"unix://{Path.home() / '.colima' / 'default' / 'docker.sock'}"
APPROVED_ENGINE = {
    "Name": "colima",
    "ServerVersion": "29.5.2",
    "OperatingSystem": "Ubuntu 24.04.4 LTS",
}
LOOPBACK = "127.0.0.1"

_HINT = "the GOV-01-R02 harness needs the approved local Colima Docker engine and never substitutes a mock"

# --- Linux CI route (M1-C-07 B6) -------------------------------------------
#
# The marker below selects *which* route to attempt. It never designates an
# engine as safe: a marker is a string any caller can set, so every control
# in this section is proven against the live target at runtime, after the
# marker is read. If any proof fails the route raises — it never falls back
# to Colima, to whatever engine happens to be ambient, or to a mock.
LINUX_CI_ROUTE_ENV_VAR = "VEYRO_HARNESS_LINUX_CI_POSTGRES"

LINUX_PLATFORM = ("Linux", "x86_64")
LINUX_DOCKER_CLI = Path("/usr/bin/docker")
# The CLI must resolve to a system location, not a user-writable one: on a CI
# runner the checkout and the job's own temp dirs are writable by the same
# user the job runs as, so a `docker` the job itself could have written is
# not a trusted CLI.
LINUX_DOCKER_CLI_ROOT = Path("/usr")
LINUX_DOCKER_SOCKET = Path("/var/run/docker.sock")
LINUX_DOCKER_HOST = f"unix://{LINUX_DOCKER_SOCKET}"

# Deliberately NO pinned CLI/engine version for this route, unlike the Colima
# binding above. Two reasons, both load-bearing:
#   1. Nothing has observed a GitHub-hosted runner's docker version, so any
#      value written here would be invented rather than measured — the exact
#      defect class M1-C-07 exists to close.
#   2. The Colima pins distinguish the approved VM engine from Docker Desktop
#      on a *shared developer machine*. A hosted runner is a single-tenant
#      disposable VM with one engine, and GitHub re-rolls that image
#      regularly, so a version pin would deny for reasons unrelated to
#      containment — the permanently-red outcome B6 itself warns about.
# What replaces them is `_verify_linux_engine`: the engine must prove it is
# *this host's own* Linux/amd64 engine, reached through a non-symlinked unix
# socket at a pinned system path.
#
# IMAGE needs no second pin either. It is an OCI image *index*, so the same
# digest-pinned reference resolves per-platform. Verified 2026-10-09 directly
# against the upstream registry manifest for this exact digest: the index
# carries a linux/amd64 child (sha256:1a66d744c1b459e13b05a8fca341da84cb6338
# 3e99ce262210efee5a319d4551) alongside the linux/arm64/v8 child the Colima
# VM resolves. `_verify_container_image` then proves the container actually
# running came from that pinned digest and resolved to linux/amd64, rather
# than trusting `docker run` to have honoured the digest.
LINUX_IMAGE_OS = "linux"
LINUX_IMAGE_ARCH = "amd64"

# libpq fills any connection parameter the caller leaves unset from these,
# and PGHOSTADDR/PGSERVICE/PGSERVICEFILE/PGOPTIONS can redirect or inject
# parameters even when host/port/user/password/dbname are all passed
# explicitly — so an ambient one of these is an ambient *database* target,
# exactly as an ambient DOCKER_* is an ambient *engine* target. Deliberately
# not a bare `PG*` prefix sweep: hosted runner images ship PostgreSQL
# *tooling* variables (PGROOT, PGDATA, PGBIN) that are not libpq connection
# parameters, and denying those would make this route unconditionally red for
# a reason unrelated to containment.
LIBPQ_CONNECTION_ENV_VARS = frozenset(
    {
        "PGAPPNAME",
        "PGCHANNELBINDING",
        "PGCLIENTENCODING",
        "PGCONNECT_TIMEOUT",
        "PGDATABASE",
        "PGGSSENCMODE",
        "PGHOST",
        "PGHOSTADDR",
        "PGKRBSRVNAME",
        "PGOPTIONS",
        "PGPASSFILE",
        "PGPASSWORD",
        "PGPORT",
        "PGREQUIRESSL",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSSLCERT",
        "PGSSLCRL",
        "PGSSLKEY",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGTARGETSESSIONATTRS",
        "PGUSER",
    }
)

_LINUX_HINT = (
    "the GOV-01-R02 harness needs this host's own linux/amd64 Docker engine, reached through "
    "the pinned socket, and never substitutes a mock"
)


@dataclass(frozen=True)
class DockerRoute:
    """The single trusted way this harness reaches a Docker engine."""

    cli: str
    host: str
    config_dir: str
    # Set only by the Linux CI route, which cannot pin an engine version and
    # so proves the running container's image instead. Defaulted off, so the
    # Colima route constructs and behaves exactly as it did before B6.
    verify_container_image: bool = False

    def __call__(
        self, *args: str, merge_stderr: bool = False, extra_env: dict[str, str] | None = None
    ) -> str:
        # Errors name the subcommand + docker's stderr only: never argv/env, which
        # is where a credential would be.
        env = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}
        env["DOCKER_CONFIG"] = self.config_dir
        env.update(extra_env or {})
        argv = [self.cli, "--config", self.config_dir, "--host", self.host, *args]
        try:
            res = subprocess.run(
                argv, capture_output=True, text=True, timeout=120, env=env, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(
                f"`docker {args[0]}` could not run ({type(exc).__name__}); {_HINT}"
            ) from None
        if res.returncode != 0:
            raise RuntimeError(
                f"`docker {args[0]}` exit {res.returncode}: {res.stderr.strip()}; {_HINT}"
            )
        return res.stdout + res.stderr if merge_stderr else res.stdout.strip()


@dataclass(frozen=True)
class DisposablePostgres:
    container: str
    host: str
    port: int
    superuser_password: str = field(repr=False)  # never rendered in tracebacks
    docker: DockerRoute = field(repr=False)

    def dsn(self, user: str, password: str) -> str:
        return make_conninfo(
            host=self.host, port=self.port, user=user, password=password, dbname="postgres"
        )

    @property
    def superuser_dsn(self) -> str:
        return self.dsn(SUPERUSER, self.superuser_password)

    def server_log(self) -> str:
        """The Postgres server's own log (stderr of the container)."""
        return self.docker("logs", self.container, merge_stderr=True)


def _trusted_cli() -> str:
    # Exec the resolved file, not the symlink, so the checked binary is the run one.
    real = os.path.realpath(TRUSTED_DOCKER_CLI)
    if real != str(TRUSTED_DOCKER_CLI_REALPATH) or not (
        os.path.isfile(real) and os.access(real, os.X_OK)
    ):
        raise RuntimeError(
            f"trusted docker CLI {TRUSTED_DOCKER_CLI} resolves to {real!r}, expected executable "
            f"{TRUSTED_DOCKER_CLI_REALPATH}; refusing PATH or Docker Desktop's CLI; {_HINT}"
        )
    return real


@contextmanager
def trusted_docker() -> Iterator[DockerRoute]:
    """Yield a `DockerRoute` whose CLI and engine are both verified as the
    approved Colima binding; the isolated config dir lives as long as the route.

    With `LINUX_CI_ROUTE_ENV_VAR` set, delegates to the Linux CI route
    instead. Unset — every local run — this function is unchanged."""
    if linux_ci_route_requested():
        with _linux_ci_docker() as linux_route:
            yield linux_route
        return
    cli = _trusted_cli()
    host = os.environ.get("DOCKER_HOST") or COLIMA_DOCKER_HOST
    with tempfile.TemporaryDirectory(prefix="veyro-harness-docker-config-") as config_dir:
        Path(config_dir, "config.json").write_text("{}\n")
        route = DockerRoute(cli, host, config_dir)
        version = route("--version")
        if not version.startswith(f"Docker version {TRUSTED_DOCKER_CLI_VERSION},"):
            raise RuntimeError(
                f"docker CLI {cli} reports {version!r}, expected {TRUSTED_DOCKER_CLI_VERSION}; {_HINT}"
            )
        _verify_engine(route)
        yield route


def _verify_engine(route: DockerRoute) -> None:
    raw = route("info", "--format", "{{json .}}")
    try:
        info = json.loads(raw)
    except ValueError:
        raise RuntimeError(f"`docker info` at {route.host} was not JSON; {_HINT}") from None
    if not isinstance(info, dict) or info.get("ServerErrors"):
        raise RuntimeError(f"`docker info` at {route.host} reported no usable engine; {_HINT}")
    observed = {key: info.get(key) for key in APPROVED_ENGINE}
    if observed != APPROVED_ENGINE:
        raise RuntimeError(
            f"engine at {route.host} is not the approved Colima binding: observed {observed}, "
            f"expected {APPROVED_ENGINE}; {_HINT}"
        )


def linux_ci_route_requested(env: Mapping[str, str] | None = None) -> bool:
    """Whether the Linux CI route was explicitly opted into. Requesting it is
    not the same as being allowed it — `_linux_ci_docker` proves the target."""
    return bool((env if env is not None else os.environ).get(LINUX_CI_ROUTE_ENV_VAR))


def linux_env_denials(env: Mapping[str, str]) -> list[str]:
    """Ambient variables that could repoint the Docker engine or the database
    out from under the controls before any of them could observe it.

    Refused, not stripped, for the same reason the scoped pytest runner
    refuses ambient `PYTEST_*`: silently normalising an override hides that
    something tried to set one, and on this route the thing being overridden
    is which engine and which database the harness talks to."""
    denials = []
    if docker_vars := sorted(k for k in env if k.startswith("DOCKER_")):
        denials.append(f"ambient Docker engine variables {docker_vars}")
    if pg_vars := sorted(LIBPQ_CONNECTION_ENV_VARS & set(env)):
        denials.append(f"ambient libpq connection variables {pg_vars}")
    return denials


def _verify_linux_platform() -> None:
    uname = os.uname()
    observed = (uname.sysname, uname.machine)
    if observed != LINUX_PLATFORM:
        raise RuntimeError(
            f"the Linux CI Postgres route was requested on {observed}, which is not "
            f"{LINUX_PLATFORM}; it is not a substitute for the local Colima route; {_LINUX_HINT}"
        )


def _linux_cli() -> str:
    # Exec the resolved file, not the symlink, so the checked binary is the run one.
    real = os.path.realpath(LINUX_DOCKER_CLI)
    if not (os.path.isfile(real) and os.access(real, os.X_OK)):
        raise RuntimeError(
            f"docker CLI {LINUX_DOCKER_CLI} resolves to {real!r}, which is not an executable "
            f"regular file; refusing any CLI found via PATH; {_LINUX_HINT}"
        )
    if LINUX_DOCKER_CLI_ROOT not in Path(real).parents:
        raise RuntimeError(
            f"docker CLI {LINUX_DOCKER_CLI} resolves to {real!r}, outside "
            f"{LINUX_DOCKER_CLI_ROOT}; refusing a CLI the job itself could have written; "
            f"{_LINUX_HINT}"
        )
    return real


def _verify_linux_socket() -> None:
    """The engine must be reached through a real unix socket at the pinned
    system path. A symlink there could forward to a user-writable or remote
    socket, which would make the engine's own identity claim meaningless."""
    if LINUX_DOCKER_SOCKET.is_symlink():
        raise RuntimeError(
            f"pinned Docker socket {LINUX_DOCKER_SOCKET} is a symlink to "
            f"{os.path.realpath(LINUX_DOCKER_SOCKET)!r}; refusing a forwarded socket; "
            f"{_LINUX_HINT}"
        )
    try:
        mode = LINUX_DOCKER_SOCKET.stat().st_mode
    except OSError as exc:
        raise RuntimeError(
            f"pinned Docker socket {LINUX_DOCKER_SOCKET} is not usable "
            f"({type(exc).__name__}); {_LINUX_HINT}"
        ) from None
    if not stat.S_ISSOCK(mode):
        raise RuntimeError(f"pinned path {LINUX_DOCKER_SOCKET} is not a socket; {_LINUX_HINT}")


def _verify_linux_engine(route: DockerRoute) -> None:
    """Prove the engine behind the pinned socket is this host's own Linux/amd64
    engine — the locality control that stands in for the version pins the
    Colima route uses (see the constants block for why there are none here).

    Disclosed limit: `Name` is the engine's own claim about itself, so this is
    not a cryptographic identity proof. It is meaningful only in combination
    with `_verify_linux_socket` — a remote or forwarded engine reached through
    a non-symlinked socket at a root-owned system path would still have to
    report this host's hostname to pass, and anyone able to arrange that
    already controls the runner."""
    raw = route("info", "--format", "{{json .}}")
    try:
        info = json.loads(raw)
    except ValueError:
        raise RuntimeError(f"`docker info` at {route.host} was not JSON; {_LINUX_HINT}") from None
    if not isinstance(info, dict) or info.get("ServerErrors"):
        raise RuntimeError(
            f"`docker info` at {route.host} reported no usable engine; {_LINUX_HINT}"
        )
    expected = {
        "OSType": LINUX_IMAGE_OS,
        "Architecture": LINUX_PLATFORM[1],
        "Name": os.uname().nodename,
    }
    observed = {key: info.get(key) for key in expected}
    if observed != expected:
        raise RuntimeError(
            f"engine at {route.host} is not this host's own linux/amd64 engine: observed "
            f"{observed}, expected {expected}; {_LINUX_HINT}"
        )


def _verify_container_image(docker: DockerRoute, name: str) -> None:
    """Prove the container that is actually running came from the
    digest-pinned IMAGE and resolved to that index's linux/amd64 child,
    instead of trusting `docker run` to have honoured the digest."""
    image_id = docker("inspect", "--type", "container", "--format", "{{.Image}}", name)
    raw = docker("image", "inspect", "--format", "{{json .}}", image_id)
    try:
        spec = json.loads(raw)
    except ValueError:
        raise RuntimeError(f"`docker image inspect` was not JSON; {_LINUX_HINT}") from None
    if isinstance(spec, list):  # some CLI versions wrap a single image in a list
        spec = spec[0] if spec else {}
    observed = (spec.get("Os"), spec.get("Architecture"))
    if observed != (LINUX_IMAGE_OS, LINUX_IMAGE_ARCH):
        raise RuntimeError(
            f"container {name} runs a {observed} image, expected "
            f"{(LINUX_IMAGE_OS, LINUX_IMAGE_ARCH)}; {_LINUX_HINT}"
        )
    # Compare the digest itself, not the whole reference: an engine may
    # normalise `postgres@sha256:...` to `docker.io/library/postgres@sha256:...`.
    pinned = IMAGE.partition("@")[2]
    digests = spec.get("RepoDigests") or []
    if not any(entry.partition("@")[2] == pinned for entry in digests):
        raise RuntimeError(
            f"container {name}'s image does not carry the pinned digest {pinned}; observed "
            f"{digests}; {_LINUX_HINT}"
        )


@contextmanager
def _linux_ci_docker() -> Iterator[DockerRoute]:
    """Yield a `DockerRoute` to a Linux CI runner's own Docker engine, having
    proven the target rather than trusted the marker that selected it.

    Every control is a property measured on the live target: the host really
    is linux/x86_64; no ambient variable can repoint the engine or the
    database; the CLI resolves to an executable system file; the socket is a
    real, non-symlinked socket at the pinned path; and the engine identifies
    as this host's own linux/amd64 engine. Containment of the container
    itself — loopback-only publish, random per-run credential, pinned image
    digest, `rm -f -v` teardown, synthetic rows only — is the shared path in
    `disposable_postgres`, unchanged."""
    _verify_linux_platform()
    if denials := linux_env_denials(os.environ):
        raise RuntimeError(
            f"the Linux CI Postgres route refuses to run with {'; '.join(denials)}; {_LINUX_HINT}"
        )
    cli = _linux_cli()
    _verify_linux_socket()
    with tempfile.TemporaryDirectory(prefix="veyro-harness-docker-config-") as config_dir:
        Path(config_dir, "config.json").write_text("{}\n")
        route = DockerRoute(cli, LINUX_DOCKER_HOST, config_dir, verify_container_image=True)
        _verify_linux_engine(route)
        yield route


#  Round-3 DOM-002 code-review finding R3-1: a nested-subprocess caller (e.g.
# `test_concurrency_harness_order_independence.py`) needs to identify *this
# exact* container by provenance, not by a prefix sweep that could also
# match an unrelated concurrent session's container. If the caller sets this
# env var, its value becomes the container's random suffix instead of a
# freshly generated one, so the caller can predict the exact name in advance
# and never needs to guess which container among several it created. Unset
# (every other caller, today and historically) is byte-identical to the
# prior unconditional `secrets.token_hex(4)` behavior.
#
# Round-4 review R4-2: an env var is inherited by the whole process tree,
# but a real session can call `disposable_postgres()` more than once with
# overlapping lifetimes (e.g. a module-scoped `pg` fixture shadowing the
# session-scoped one for just that module) — a *fixed* token would then
# collide on the second `docker run`, demonstrated live. `disposable_postgres`
# therefore `pop`s the var rather than merely reading it: only the *first*
# container created in a given process honours a caller-supplied token: any
# later one in the same process always falls back to a fresh random token,
# which removes the in-process collision class entirely rather than just
# documenting it.
CONTAINER_TOKEN_ENV_VAR = "VEYRO_HARNESS_CONTAINER_TOKEN"
CONTAINER_NAME_PREFIX = "veyro-mod001-harness-"


def container_name(token: str) -> str:
    """The one place this naming scheme is spelled out — callers that need
    to predict or match a container name (e.g. the order-independence
    regression tests) import this instead of keeping their own copy (round-4
    review R4-5: a second, hand-duplicated copy of this literal had already
    drifted from enforcement, though not yet from the actual value)."""
    return f"{CONTAINER_NAME_PREFIX}{token}"


@contextmanager
def disposable_postgres(ready_timeout_s: float = 60.0) -> Iterator[DisposablePostgres]:
    token = os.environ.pop(CONTAINER_TOKEN_ENV_VAR, "") or secrets.token_hex(4)
    name = container_name(token)
    password = secrets.token_urlsafe(24)
    with trusted_docker() as docker:
        # `-e NAME` (no value) makes docker read it from our env: keeps it out of argv/`ps`.
        docker(
            "run", "-d", "--rm", "--name", name,
            "-e", "POSTGRES_PASSWORD",
            "-p", f"{LOOPBACK}::5432",
            IMAGE,
            extra_env={"POSTGRES_PASSWORD": password},
        )
        try:
            host, _, port = docker("port", name, "5432/tcp").splitlines()[0].rpartition(":")
            if host != LOOPBACK:
                raise RuntimeError(f"container published on {host!r}, not {LOOPBACK}; {_HINT}")
            if docker.verify_container_image:
                # Linux CI route only (it pins no engine version, so it proves
                # the image instead). Before readiness, so an unverified
                # server is never connected to. Teardown below still runs.
                _verify_container_image(docker, name)
            pg = DisposablePostgres(name, host, int(port), password, docker)
            _wait_ready(pg, ready_timeout_s)
            yield pg
        finally:
            try:
                # BUG-051 (round 16, R16-1; corrected round 16 segment 3,
                # R16-3): the image declares `VOLUME /var/lib/postgresql/data`,
                # so every container gets an anonymous volume. This container
                # is still running when this `finally` block executes — it
                # never exits on its own, so `--rm` (which only reaps a
                # container that exits by itself) never fires here. This `rm`
                # call, not `--rm`, is what actually removes the container on
                # every single invocation, success or failure alike. Before
                # this fix it ran plain `rm -f`, which removed the container
                # but left its anonymous volume behind — one ~40MB leak per
                # fixture-using session, unconditionally, with no ceiling, on
                # a fixed-size VM disk. `-v` removes the anonymous volume
                # along with the container here too.
                docker("rm", "-f", "-v", name)
            except RuntimeError:
                pass  # best effort: masking the original error would be worse, but
                # a failed cleanup here leaks both the still-running container and
                # its anonymous volume — this is not reaped by `--rm` either, since
                # (per the comment above) this container never exits on its own


def _wait_ready(pg: DisposablePostgres, timeout_s: float) -> None:
    # The image's init phase runs a socket-only temp server, so the first
    # successful TCP login is the real, final server.
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with psycopg.connect(pg.superuser_dsn, connect_timeout=2):
                return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)
