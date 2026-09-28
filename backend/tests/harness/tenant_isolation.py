"""Tenant-isolation (RLS) harness — GOV-01-R02, proving TSD §24.1's sentence:

    "runtime role cannot own/bypass. Negative isolation tests run with
     production-equivalent role."

Everything here exists to make that sentence impossible to satisfy vacuously:

* The runtime role is a real LOGIN role with NOSUPERUSER, NOBYPASSRLS, no role
  memberships, and owns nothing. Its posture is re-read *from the connection
  under test* on every probe, and any violation fails the probe — a harness
  that silently connected as a privileged role would report itself broken.
* Denial is a Postgres policy decision observed on the wire (rows filtered,
  rowcount 0, or SQLSTATE 42501 "row-level security policy"), never an
  application-layer exception.
* Every negative result is measured against ground truth read by a separate
  superuser/BYPASSRLS observer connection, so "0 rows" can never mean "there
  was nothing to see".

Distinct credentials (`.claude/rules/backend/database.md` rule 3): the
superuser `admin`/`observer` connection is setup + ground truth only; tables
are owned by OWNER_ROLE (NOLOGIN); probes run as RUNTIME_ROLE.

Plug-in point for later modules (MOD-004+): create your real tenant tables
through your own migrations, grant RUNTIME_ROLE, seed two tenants via the
observer, then call `probe_cross_tenant(...)` / `probe_same_tenant(...)` and
assert `.failures == []`.

Known ceiling: tenant context is a transaction-local GUC (`app.tenant_id`) set
by the app after server-side resolution (TEN-002). Postgres cannot tell who
set it, so SQL injection in the app could switch tenants. That trust boundary
is MOD-004's design, not something this harness can close.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

Conn = psycopg.Connection[TupleRow]

OWNER_ROLE = "veyro_schema_owner"
RUNTIME_ROLE = "veyro_runtime"
TENANT_SETTING = "app.tenant_id"
RLS_DENIAL_TEXT = "row-level security policy"
_TENANT_CTX = sql.SQL("NULLIF(current_setting('app.tenant_id', true), '')::uuid")


@dataclass(frozen=True)
class TenantTable:
    schema: str
    name: str

    @property
    def ident(self) -> sql.Identifier:
        return sql.Identifier(self.schema, self.name)

    def __str__(self) -> str:
        return f"{self.schema}.{self.name}"


def one_row(cur: psycopg.Cursor[TupleRow]) -> TupleRow:
    row = cur.fetchone()
    if row is None:
        raise AssertionError("expected exactly one row, got none")
    return row


# --- setup (superuser, one-time) ---------------------------------------------


def scram_verifier(conn: Conn, role: str, password: str) -> sql.Literal:
    """Client-side SCRAM-SHA-256 verifier (libpq PQencryptPasswordConn): the
    cleartext never reaches the server, so it can't land in a server log."""
    raw = conn.pgconn.encrypt_password(password.encode(), role.encode(), b"scram-sha-256")
    return sql.Literal(raw.decode())


def provision_roles(admin: Conn) -> str:
    """Create the schema-owner and runtime roles; return the runtime role's
    per-run random password. `admin` must be a superuser (role creation)."""
    password = secrets.token_urlsafe(24)
    admin.execute(
        sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(
            sql.Identifier(OWNER_ROLE)
        )
    )
    admin.execute(
        sql.SQL(
            "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB"
            " NOCREATEROLE NOREPLICATION NOINHERIT"
        ).format(sql.Identifier(RUNTIME_ROLE), scram_verifier(admin, RUNTIME_ROLE, password))
    )
    return password


@contextmanager
def as_schema_owner(admin: Conn) -> Iterator[Conn]:
    admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER_ROLE)))
    try:
        yield admin
    finally:
        admin.execute("RESET ROLE")


def create_tenant_table(admin: Conn, table: TenantTable, columns: sql.Composable) -> None:
    """Fixture tenant table exactly as TSD §24.1 requires: owned by OWNER_ROLE,
    `tenant_id uuid NOT NULL`, ENABLE + FORCE RLS, one tenant policy, DML
    granted to RUNTIME_ROLE. A missing tenant context matches no row."""
    schema, t, rt = sql.Identifier(table.schema), table.ident, sql.Identifier(RUNTIME_ROLE)
    admin.execute(
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
            schema, sql.Identifier(OWNER_ROLE)
        )
    )
    with as_schema_owner(admin):
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, rt))
        admin.execute(sql.SQL("CREATE TABLE {} (tenant_id uuid NOT NULL, {})").format(t, columns))
        admin.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(t))
        admin.execute(sql.SQL("ALTER TABLE {} FORCE ROW LEVEL SECURITY").format(t))
        admin.execute(
            sql.SQL(
                "CREATE POLICY tenant_isolation ON {} USING (tenant_id = {ctx})"
                " WITH CHECK (tenant_id = {ctx})"
            ).format(t, ctx=_TENANT_CTX)
        )
        admin.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}").format(t, rt))


def seed(observer: Conn, table: TenantTable, tenant: UUID, rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        observer.execute(_insert_sql(table, row), [tenant, *row.values()])


# --- the connection-under-test's own posture ---------------------------------

_POSTURE_SQL = """
SELECT current_user::text, session_user::text, r.rolsuper, r.rolbypassrls,
       (SELECT count(*) FROM pg_auth_members m WHERE m.member = r.oid),
       pg_get_userbyid(c.relowner)::text, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid),
       (SELECT a.attnotnull FROM pg_attribute a
         WHERE a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped)
FROM pg_roles r, pg_class c
WHERE r.rolname = current_user AND c.oid = %s::regclass
"""


@dataclass(frozen=True)
class Posture:
    table: str
    role: str
    session_role: str
    superuser: bool
    bypassrls: bool
    role_memberships: int
    table_owner: str
    rls_enabled: bool
    rls_forced: bool
    policies: int
    tenant_id_not_null: bool | None

    @property
    def violations(self) -> list[str]:
        checks = {
            "ROLE_SWITCHED": self.role != self.session_role,
            "RUNTIME_ROLE_SUPERUSER": self.superuser,
            "RUNTIME_ROLE_BYPASSRLS": self.bypassrls,
            "RUNTIME_ROLE_HAS_MEMBERSHIPS": self.role_memberships > 0,
            "RUNTIME_ROLE_OWNS_TABLE": self.table_owner == self.role,
            "RLS_NOT_ENABLED": not self.rls_enabled,
            "RLS_NOT_FORCED": not self.rls_forced,
            "NO_RLS_POLICY": self.policies < 1,
            "TENANT_ID_NULLABLE_OR_MISSING": self.tenant_id_not_null is not True,
        }
        return [code for code, failed in checks.items() if failed]


def read_posture(conn: Conn, table: TenantTable) -> Posture:
    return Posture(str(table), *one_row(conn.execute(_POSTURE_SQL, (str(table),))))


# --- probes --------------------------------------------------------------------


@contextmanager
def tenant_transaction(conn: Conn, tenant: UUID | None) -> Iterator[Conn]:
    """One transaction with tenant context set the way the app sets it after
    server-side resolution: transaction-local, never session-wide."""
    with conn.transaction():
        if tenant is not None:
            conn.execute("SELECT set_config(%s, %s, true)", (TENANT_SETTING, str(tenant)))
        yield conn


def _insert_sql(table: TenantTable, row: Mapping[str, Any]) -> sql.Composed:
    cols = [sql.Identifier("tenant_id"), *(sql.Identifier(c) for c in row)]
    return sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        table.ident, sql.SQL(", ").join(cols), sql.SQL(", ").join([sql.Placeholder()] * len(cols))
    )


def _require_observer(observer: Conn) -> None:
    # Ground truth read through RLS would be vacuous, so the observer must see everything.
    sees_all = one_row(
        observer.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
    )[0]
    if not sees_all:
        raise AssertionError("observer connection must be superuser/BYPASSRLS for ground truth")


def _ground_truth(observer: Conn, table: TenantTable, tenant: UUID) -> tuple[int, str]:
    n, fp = one_row(
        observer.execute(
            sql.SQL(
                "SELECT count(*), md5(coalesce(string_agg(r::text, ',' ORDER BY r::text), ''))"
                " FROM {} AS r WHERE r.tenant_id = %s"
            ).format(table.ident),
            (tenant,),
        )
    )
    return int(n), str(fp)


def _attempt_write(conn: Conn, tenant: UUID, stmt: sql.Composed, params: Sequence[Any]) -> str:
    try:
        with tenant_transaction(conn, tenant):
            return f"ALLOWED rowcount={conn.execute(stmt, params).rowcount}"
    except psycopg.errors.InsufficientPrivilege as exc:
        msg = exc.diag.message_primary or str(exc)
        return ("DENIED_BY_RLS: " if RLS_DENIAL_TEXT in msg else "DENIED_OTHER: ") + msg


@dataclass(frozen=True)
class CrossTenantProbe:
    table: str
    role: str
    own_tenant: str
    other_tenant: str
    posture_violations: list[str]
    own_rows_before: int
    other_rows_before: int
    other_fingerprint_before: str
    visible_other_rows: int
    updated_other_rows: int
    insert_as_other: str
    reassign_own_to_other: str
    deleted_other_rows: int
    other_rows_after: int
    other_fingerprint_after: str

    @property
    def failures(self) -> list[str]:
        f = [f"POSTURE:{v}" for v in self.posture_violations]
        if self.own_rows_before < 1 or self.other_rows_before < 1:
            f.append("VACUOUS: both tenants need seeded ground-truth rows")
        if self.visible_other_rows:
            f.append(f"CROSS_TENANT_READ:{self.visible_other_rows}")
        if self.updated_other_rows:
            f.append(f"CROSS_TENANT_UPDATE:{self.updated_other_rows}")
        if not self.insert_as_other.startswith("DENIED_BY_RLS"):
            f.append(f"CROSS_TENANT_INSERT:{self.insert_as_other}")
        if not self.reassign_own_to_other.startswith("DENIED_BY_RLS"):
            f.append(f"CROSS_TENANT_REASSIGN:{self.reassign_own_to_other}")
        if self.deleted_other_rows:
            f.append(f"CROSS_TENANT_DELETE:{self.deleted_other_rows}")
        before = (self.other_rows_before, self.other_fingerprint_before)
        if (self.other_rows_after, self.other_fingerprint_after) != before:
            f.append("OTHER_TENANT_ROWS_CHANGED")
        return f


def probe_cross_tenant(
    runtime: Conn,
    observer: Conn,
    table: TenantTable,
    own: UUID,
    other: UUID,
    new_row: Mapping[str, Any],
) -> CrossTenantProbe:
    """Attack `other`'s rows from inside `own`'s tenant context via read,
    update, insert, reassignment and delete — each committed, like a real
    attacker's — and measure the result against observer ground truth."""
    _require_observer(observer)
    posture = read_posture(runtime, table)
    t = table.ident
    own_before, _ = _ground_truth(observer, table, own)
    other_before, fp_before = _ground_truth(observer, table, other)

    with tenant_transaction(runtime, own):
        count_q = sql.SQL("SELECT count(*) FROM {} WHERE tenant_id = %s").format(t)
        visible = int(one_row(runtime.execute(count_q, (other,)))[0])
    with tenant_transaction(runtime, own):
        update_q = sql.SQL("UPDATE {} SET tenant_id = tenant_id WHERE tenant_id = %s").format(t)
        updated = runtime.execute(update_q, (other,)).rowcount
    insert = _attempt_write(runtime, own, _insert_sql(table, new_row), [other, *new_row.values()])
    reassign = _attempt_write(
        runtime, own, sql.SQL("UPDATE {} SET tenant_id = %s WHERE tenant_id = %s").format(t),
        [other, own],
    )
    with tenant_transaction(runtime, own):
        delete_q = sql.SQL("DELETE FROM {} WHERE tenant_id = %s").format(t)
        deleted = runtime.execute(delete_q, (other,)).rowcount

    other_after, fp_after = _ground_truth(observer, table, other)
    return CrossTenantProbe(
        table=str(table), role=posture.role, own_tenant=str(own), other_tenant=str(other),
        posture_violations=posture.violations,
        own_rows_before=own_before, other_rows_before=other_before,
        other_fingerprint_before=fp_before,
        visible_other_rows=visible, updated_other_rows=updated, insert_as_other=insert,
        reassign_own_to_other=reassign, deleted_other_rows=deleted,
        other_rows_after=other_after, other_fingerprint_after=fp_after,
    )


@dataclass(frozen=True)
class SameTenantProbe:
    table: str
    role: str
    tenant: str
    posture_violations: list[str]
    rows_ground_truth: int
    visible_rows: int
    updated_rows: int
    insert_own: str

    @property
    def failures(self) -> list[str]:
        f = [f"POSTURE:{v}" for v in self.posture_violations]
        if self.rows_ground_truth < 1:
            f.append("VACUOUS: tenant needs seeded ground-truth rows")
        if self.visible_rows != self.rows_ground_truth:
            f.append(f"SAME_TENANT_READ:{self.visible_rows}!={self.rows_ground_truth}")
        if self.updated_rows != self.rows_ground_truth:
            f.append(f"SAME_TENANT_UPDATE:{self.updated_rows}!={self.rows_ground_truth}")
        if not self.insert_own.startswith("ALLOWED rowcount=1"):
            f.append(f"SAME_TENANT_INSERT:{self.insert_own}")
        return f


def probe_same_tenant(
    runtime: Conn, observer: Conn, table: TenantTable, tenant: UUID, new_row: Mapping[str, Any]
) -> SameTenantProbe:
    """Positive control: a correctly-scoped request reaches exactly its own
    tenant's rows. Proves the negative probe's zeros come from the policy, not
    from missing grants or a table that hides everything."""
    _require_observer(observer)
    posture = read_posture(runtime, table)
    t = table.ident
    truth, _ = _ground_truth(observer, table, tenant)
    with tenant_transaction(runtime, tenant):
        visible = int(one_row(runtime.execute(sql.SQL("SELECT count(*) FROM {}").format(t)))[0])
    with tenant_transaction(runtime, tenant):
        update_q = sql.SQL("UPDATE {} SET tenant_id = tenant_id WHERE tenant_id = %s").format(t)
        updated = runtime.execute(update_q, (tenant,)).rowcount
    insert = _attempt_write(runtime, tenant, _insert_sql(table, new_row), [tenant, *new_row.values()])
    return SameTenantProbe(
        table=str(table), role=posture.role, tenant=str(tenant),
        posture_violations=posture.violations, rows_ground_truth=truth,
        visible_rows=visible, updated_rows=updated, insert_own=insert,
    )


def visible_without_tenant_context(runtime: Conn, table: TenantTable) -> int:
    """Fail-closed check: no tenant context must mean no rows, not all rows."""
    with tenant_transaction(runtime, None):
        count_q = sql.SQL("SELECT count(*) FROM {}").format(table.ident)
        return int(one_row(runtime.execute(count_q))[0])


# --- MOD-001's canonical fixture: `access_grant` (SCN-MOD001-067) ------------
# Synthetic, life-safety-shaped stand-in for a future MOD-021/022 physical
# access-grant table. No access-control logic lives here.

ACCESS_GRANT = TenantTable("harness", "access_grant")
ACCESS_GRANT_COLUMNS = sql.SQL(
    "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    " subject_ref text NOT NULL,"
    " zone text NOT NULL,"
    " valid_until timestamptz NOT NULL DEFAULT now() + interval '30 days'"
)


def access_grant_row(n: int) -> dict[str, str]:
    return {"subject_ref": f"synthetic-member-{n:04d}", "zone": f"synthetic-zone-{n % 3}"}
