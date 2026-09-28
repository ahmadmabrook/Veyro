"""Integration fixtures for the GOV-01-R02 harnesses (one disposable Postgres per session).

Credential separation (`.claude/rules/backend/database.md` rule 3):
  `admin`   — container superuser: role creation, fixture DDL, ground-truth reads.
  `runtime` — RUNTIME_ROLE: every probe/authentication under test runs here.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from tests.harness.authn import provision_auth_schema
from tests.harness.postgres import DisposablePostgres, disposable_postgres
from tests.harness.tenant_isolation import (
    ACCESS_GRANT,
    ACCESS_GRANT_COLUMNS,
    RUNTIME_ROLE,
    Conn,
    access_grant_row,
    create_tenant_table,
    provision_roles,
    scram_verifier,
    seed,
)


@pytest.fixture(scope="session")
def pg() -> Iterator[DisposablePostgres]:
    with disposable_postgres() as instance:
        yield instance


@pytest.fixture(scope="session")
def admin(pg: DisposablePostgres) -> Iterator[Conn]:
    with psycopg.connect(pg.superuser_dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def runtime_password(admin: Conn) -> str:
    password = provision_roles(admin)
    create_tenant_table(admin, ACCESS_GRANT, ACCESS_GRANT_COLUMNS)
    provision_auth_schema(admin)
    return password


@pytest.fixture(scope="session")
def runtime(pg: DisposablePostgres, runtime_password: str) -> Iterator[Conn]:
    with psycopg.connect(pg.dsn(RUNTIME_ROLE, runtime_password), autocommit=True) as conn:
        yield conn


@pytest.fixture
def tenants(admin: Conn, runtime_password: str) -> tuple[UUID, UUID]:
    """Fresh (A, B) tenant pair with 2 and 3 seeded `access_grant` rows."""
    a, b = uuid4(), uuid4()
    admin.execute("TRUNCATE harness.access_grant")
    seed(admin, ACCESS_GRANT, a, [access_grant_row(i) for i in range(2)])
    seed(admin, ACCESS_GRANT, b, [access_grant_row(i) for i in range(10, 13)])
    return a, b


@pytest.fixture
def elevated_login(pg: DisposablePostgres, admin: Conn) -> Iterator[Conn]:
    """A deliberately *wrong* runtime connection (BYPASSRLS) — used only to
    prove the harness rejects it, never to produce isolation evidence."""
    name, password = f"veyro_bypass_probe_{secrets.token_hex(3)}", secrets.token_urlsafe(24)
    role = sql.Identifier(name)
    admin.execute(
        sql.SQL("CREATE ROLE {} LOGIN BYPASSRLS PASSWORD {}").format(
            role, scram_verifier(admin, name, password)
        )
    )
    admin.execute(sql.SQL("GRANT USAGE ON SCHEMA harness TO {}").format(role))
    admin.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON harness.access_grant TO {}").format(role)
    )
    with psycopg.connect(pg.dsn(name, password), autocommit=True) as conn:
        yield conn
