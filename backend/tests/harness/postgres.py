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
"""

from __future__ import annotations

import os
import secrets
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg
from psycopg.conninfo import make_conninfo

# postgres:16-alpine, pinned by content digest so a moved tag can't change
# what runs. Bump deliberately (docker pull postgres:16-alpine; docker image
# inspect ... RepoDigests), never by editing the tag back in.
IMAGE = "postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
SUPERUSER = "postgres"


@dataclass(frozen=True)
class DisposablePostgres:
    container: str
    host: str
    port: int
    superuser_password: str = field(repr=False)  # never rendered in tracebacks

    def dsn(self, user: str, password: str) -> str:
        return make_conninfo(
            host=self.host, port=self.port, user=user, password=password, dbname="postgres"
        )

    @property
    def superuser_dsn(self) -> str:
        return self.dsn(SUPERUSER, self.superuser_password)

    def server_log(self) -> str:
        """The Postgres server's own log (stderr of the container)."""
        return _docker("logs", self.container, merge_stderr=True)


def _docker(*args: str, merge_stderr: bool = False, env: dict[str, str] | None = None) -> str:
    # Errors name the subcommand + docker's stderr only: never argv/env, which
    # is where a credential would be.
    hint = "the GOV-01-R02 harness needs a local Docker engine and never substitutes a mock"
    try:
        res = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=120, env=env, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"`docker {args[0]}` could not run ({type(exc).__name__}); {hint}") from None
    if res.returncode != 0:
        raise RuntimeError(f"`docker {args[0]}` exit {res.returncode}: {res.stderr.strip()}; {hint}")
    return res.stdout + res.stderr if merge_stderr else res.stdout.strip()


@contextmanager
def disposable_postgres(ready_timeout_s: float = 60.0) -> Iterator[DisposablePostgres]:
    name = f"veyro-mod001-harness-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    # `-e NAME` (no value) makes docker read it from our env: keeps it out of argv/`ps`.
    _docker(
        "run", "-d", "--rm", "--name", name,
        "-e", "POSTGRES_PASSWORD",
        "-p", "127.0.0.1::5432",
        IMAGE,
        env={**os.environ, "POSTGRES_PASSWORD": password},
    )
    try:
        host, _, port = _docker("port", name, "5432/tcp").splitlines()[0].rpartition(":")
        pg = DisposablePostgres(name, host, int(port), password)
        _wait_ready(pg, ready_timeout_s)
        yield pg
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


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
