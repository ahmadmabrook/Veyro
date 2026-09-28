"""GOV-01-R02 tenant-isolation harness against a real Postgres, as the real
non-privileged runtime role.

SCN-MOD001-067  cross-tenant access to `access_grant` denied by RLS, plus the
                deliberately-broken companions proving the harness can tell a
                correctly-isolated table from a broken one.
SCN-MOD001-028  same-tenant (correctly-scoped) request permitted.

`*-EVIDENCE` lines are structured JSON, printed for `pytest -rP` capture.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

import psycopg
import pytest

from tests.harness.postgres import DisposablePostgres
from tests.harness.tenant_isolation import (
    ACCESS_GRANT,
    OWNER_ROLE,
    RUNTIME_ROLE,
    Conn,
    access_grant_row,
    one_row,
    probe_cross_tenant,
    probe_same_tenant,
    read_posture,
    visible_without_tenant_context,
)

RLS_LOG_LINE = 'new row violates row-level security policy for table "access_grant"'
_POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _evidence(tag: str, payload: Any) -> None:
    print(f"{tag}-EVIDENCE {json.dumps(payload, sort_keys=True, default=str)}")


def test_runtime_role_is_production_equivalent(runtime: Conn) -> None:
    posture = read_posture(runtime, ACCESS_GRANT)
    _evidence("RUNTIME-POSTURE", asdict(posture))
    assert posture.role == RUNTIME_ROLE
    assert posture.table_owner == OWNER_ROLE
    assert posture.violations == []


def test_scn067_access_grant_cross_tenant_access_denied(
    runtime: Conn, admin: Conn, pg: DisposablePostgres, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    log_before = pg.server_log().count(RLS_LOG_LINE)
    probe = probe_cross_tenant(runtime, admin, ACCESS_GRANT, a, b, access_grant_row(99))
    log = pg.server_log()
    _evidence("SCN-MOD001-067", asdict(probe))
    _evidence("SCN-MOD001-067-SERVER-LOG", [ln for ln in log.splitlines() if RLS_LOG_LINE in ln])

    assert probe.failures == []
    assert (probe.role, probe.other_rows_before, probe.visible_other_rows) == (RUNTIME_ROLE, 3, 0)
    # Postgres itself (not the harness) logged both write denials, naming the table.
    assert log.count(RLS_LOG_LINE) >= log_before + 2


def test_scn028_same_tenant_request_permitted(
    runtime: Conn, admin: Conn, tenants: tuple[UUID, UUID]
) -> None:
    _, b = tenants
    probe = probe_same_tenant(runtime, admin, ACCESS_GRANT, b, access_grant_row(98))
    _evidence("SCN-MOD001-028", asdict(probe))
    assert probe.failures == []
    assert (probe.rows_ground_truth, probe.visible_rows) == (3, 3)


def test_missing_tenant_context_sees_no_rows(
    runtime: Conn, admin: Conn, tenants: tuple[UUID, UUID]
) -> None:
    assert one_row(admin.execute("SELECT count(*) FROM harness.access_grant"))[0] == 5
    assert visible_without_tenant_context(runtime, ACCESS_GRANT) == 0


# (id, break, restore, posture codes the harness must raise, behavioural leak expected)
BREAKAGES = [
    (
        "rls_disabled",
        "ALTER TABLE harness.access_grant DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE harness.access_grant ENABLE ROW LEVEL SECURITY",
        {"RLS_NOT_ENABLED"},
        True,
    ),
    (
        "permissive_policy",  # posture looks fine; only the behavioural probe can catch it
        "ALTER POLICY tenant_isolation ON harness.access_grant USING (true) WITH CHECK (true)",
        (
            f"ALTER POLICY tenant_isolation ON harness.access_grant"
            f" USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
        ),
        set(),
        True,
    ),
    (
        "rls_not_forced",
        "ALTER TABLE harness.access_grant NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE harness.access_grant FORCE ROW LEVEL SECURITY",
        {"RLS_NOT_FORCED"},
        False,
    ),
    (
        "tenant_id_nullable",
        "ALTER TABLE harness.access_grant ALTER COLUMN tenant_id DROP NOT NULL",
        "ALTER TABLE harness.access_grant ALTER COLUMN tenant_id SET NOT NULL",
        {"TENANT_ID_NULLABLE_OR_MISSING"},
        False,
    ),
    (
        "runtime_owns_table",
        f"ALTER TABLE harness.access_grant OWNER TO {RUNTIME_ROLE}",
        f"ALTER TABLE harness.access_grant OWNER TO {OWNER_ROLE}",
        {"RUNTIME_ROLE_OWNS_TABLE"},
        False,
    ),
]


@pytest.mark.parametrize(
    ("name", "break_sql", "restore_sql", "codes", "leaks"), BREAKAGES, ids=[b[0] for b in BREAKAGES]
)
def test_scn067_negative_harness_detects_broken_fixture(
    runtime: Conn,
    admin: Conn,
    tenants: tuple[UUID, UUID],
    name: str,
    break_sql: str,
    restore_sql: str,
    codes: set[str],
    leaks: bool,
) -> None:
    a, b = tenants
    admin.execute(break_sql)
    try:
        probe = probe_cross_tenant(runtime, admin, ACCESS_GRANT, a, b, access_grant_row(97))
    finally:
        admin.execute(restore_sql)
    _evidence(f"SCN-MOD001-067-NEGATIVE[{name}]", {"failures": probe.failures, **asdict(probe)})

    assert probe.failures, f"harness PASSED a deliberately broken fixture ({name})"
    assert codes <= set(probe.posture_violations)
    behavioural = [f for f in probe.failures if not f.startswith("POSTURE:")]
    assert bool(behavioural) is leaks
    assert read_posture(runtime, ACCESS_GRANT).violations == [], "fixture not restored"


def test_harness_rejects_bypassrls_connection(
    elevated_login: Conn, admin: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    probe = probe_cross_tenant(elevated_login, admin, ACCESS_GRANT, a, b, access_grant_row(96))
    _evidence("HARNESS-SELF-CHECK[bypassrls]", {"failures": probe.failures, **asdict(probe)})
    assert "RUNTIME_ROLE_BYPASSRLS" in probe.posture_violations
    assert probe.visible_other_rows == 3  # the leak a bypass-role harness would hide


def test_harness_rejects_superuser_connection(
    pg: DisposablePostgres, admin: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    with psycopg.connect(pg.superuser_dsn, autocommit=True) as su:
        probe = probe_cross_tenant(su, admin, ACCESS_GRANT, a, b, access_grant_row(95))
    _evidence("HARNESS-SELF-CHECK[superuser]", {"failures": probe.failures, **asdict(probe)})
    assert "RUNTIME_ROLE_SUPERUSER" in probe.posture_violations
    assert probe.visible_other_rows == 3


def test_harness_refuses_rls_filtered_observer(runtime: Conn, tenants: tuple[UUID, UUID]) -> None:
    a, b = tenants
    with pytest.raises(AssertionError, match="observer connection must be superuser"):
        probe_cross_tenant(runtime, runtime, ACCESS_GRANT, a, b, access_grant_row(94))
