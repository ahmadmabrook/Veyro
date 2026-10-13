"""GOV-01-R04 RLS-lint gate (TSD §24.1) against a real Postgres catalog — ADR-010.

ADR-010 acceptance cases on the approved CAP-008 Colima PostgreSQL 16 binding:
N1-N21 (negatives, each must FAIL with its stated code/token, never PASS) and
P1-P6 (positives). SCN-MOD001-004/005/067 cases from earlier rounds are kept.

Every breakage is applied by the superuser setup connection, judged, then
restored; `_broken` re-judges the canonical harness PASS and re-checks the
runtime role's DML and schema USAGE afterwards, so no case can leave the
shared fixture broken. Negatives that change role attributes, memberships or
grants only judge the catalog state; where a real cross-tenant leak exists it
is shown with ordinary row counts under the non-privileged runtime role.

`*-EVIDENCE` lines are structured JSON, printed for `pytest -rP` capture.
"""

from __future__ import annotations

import importlib.util
import json
import os
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
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
    read_posture,
)

_GATES_PATH = Path(__file__).resolve().parents[3] / "tools" / "validate_architecture_gates.py"


def _load_gates() -> ModuleType:
    # tools/ is outside the backend package; load the gate by path rather than
    # widening sys.path for the whole test session.
    spec = importlib.util.spec_from_file_location("validate_architecture_gates", _GATES_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gates = _load_gates()

TABLE = str(ACCESS_GRANT)
RT = RUNTIME_ROLE
_POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_RUNTIME_GRANT = f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {RT}"
_RESTORE_POLICY = (
    f"CREATE POLICY tenant_isolation ON {TABLE} USING ({_POLICY_EXPR}) WITH CHECK ({_POLICY_EXPR})"
)
_ALTER_POLICY_BACK = _RESTORE_POLICY.replace("CREATE", "ALTER", 1)

# Synthetic approval root (ADR-010 D3.4): a fixture ADR that names every manifest key used here.
AUTH_TABLES = ["harness_auth.identity", "harness_auth.session", "harness_auth.audit_event"]
_FIXTURE_KEYS = [*AUTH_TABLES, "harness.gate_platform", "harness.gate_mv", "harness.gate_lookup",
                 "harness.gate_sd()"]
APPROVAL_ROOT = Path(tempfile.mkdtemp(prefix="veyro-adr010-fixture-"))
(APPROVAL_ROOT / "knowledge" / "04-Decisions").mkdir(parents=True)
(APPROVAL_ROOT / "knowledge" / "04-Decisions" / "ADR-900-synthetic-rls-fixture.md").write_text(
    "---\nstatus: DECIDED (synthetic test fixture)\n---\n" + "\n".join(_FIXTURE_KEYS) + "\n"
)


def _manifest(relations: dict[str, str] | None = None,
              functions: tuple[str, ...] = ()) -> dict[str, Any]:
    rels = {name: "table" for name in AUTH_TABLES} | (relations or {})
    return {
        "version": 2,
        "platform_scope_relations": {
            name: {"kind": kind, "reason": "synthetic harness fixture", "approval": "ADR-900"}
            for name, kind in rels.items()
        },
        "reviewed_security_definer_functions": {
            key: {"reason": "synthetic reviewed fixture", "approval": "ADR-900"}
            for key in functions
        },
    }


def _evidence(tag: str, payload: Any) -> None:
    print(f"{tag}-EVIDENCE {json.dumps(payload, sort_keys=True, default=str)}")


def _gate(conn: Conn, **kw: Any) -> Any:
    args: dict[str, Any] = {"required_tables": [TABLE], "manifest": _manifest(),
                            "resolver_root": APPROVAL_ROOT}
    return gates.run_rls_gate(conn, RT, **{**args, **kw})


def _violations(report: Any) -> list[tuple[str, str, str]]:
    return [(v.code, v.subject, v.detail) for v in report.violations]


def _has(report: Any, code: str, fragment: str) -> bool:
    return any(c == code and fragment in d for c, _, d in _violations(report))


def _scalar(conn: Conn, query: str, params: tuple[Any, ...] = ()) -> Any:
    return one_row(conn.execute(query, params))[0]


@contextmanager
def _broken(admin: Conn, break_sql: list[str], restore_sql: list[str]) -> Iterator[None]:
    for stmt in break_sql:
        admin.execute(stmt)
    try:
        yield
    finally:
        for stmt in restore_sql:
            admin.execute(stmt)
    restored = _gate(admin)
    assert restored.status == gates.PASS, f"fixture not restored: {restored.render()}"
    assert read_posture(admin, ACCESS_GRANT).table_owner == OWNER_ROLE
    # Restoring flags is not enough: later tests need the runtime role's grants intact.
    assert _scalar(admin, "SELECT has_table_privilege(%s, %s, 'SELECT, INSERT, UPDATE, DELETE')",
                   (RT, TABLE)) is True, "runtime role lost its DML grant"
    assert _scalar(admin, "SELECT has_schema_privilege(%s, 'harness', 'USAGE')", (RT,)) is True


def _visible(runtime: Conn, relation: str, own: UUID, other: UUID,
             set_role: str | None = None) -> tuple[int, int]:
    """(own, other) tenant rows visible to the runtime role through `relation`."""
    with runtime.transaction():
        if set_role:
            runtime.execute(f"SET LOCAL ROLE {set_role}")
        runtime.execute("SELECT set_config('app.tenant_id', %s, true)", (str(own),))
        q = "SELECT count(*) FILTER (WHERE tenant_id = %s), count(*) FILTER (WHERE tenant_id = %s)"
        mine, theirs = one_row(runtime.execute(f"{q} FROM {relation}", (own, other)))
    return int(mine), int(theirs)


# --- positives -----------------------------------------------------------------------


def test_p1_canonical_harness_passes(admin: Conn, runtime: Conn) -> None:
    report = _gate(admin)
    _evidence("ADR010-P1", asdict(report))
    assert report.status == gates.PASS, report.render()
    assert report.exit_code == 0
    assert report.checked == [TABLE]
    # Same verdict through the non-privileged runtime connection: the gate needs no elevation.
    assert asdict(_gate(runtime)) == asdict(report)
    # D2: the gate's pinned search_path does not leak into the caller's session.
    assert _scalar(admin, "SHOW search_path") == '"$user", public'


def test_p2_dml_through_clean_group_role(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    group = "veyro_gate_dml_group"
    with _broken(
        admin,
        [f"CREATE ROLE {group} NOLOGIN", f"GRANT USAGE ON SCHEMA harness TO {group}",
         f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {group}",
         f"REVOKE ALL ON {TABLE} FROM {RT}", f"GRANT {group} TO {RT}"],
        [f"REVOKE {group} FROM {RT}", _RUNTIME_GRANT, f"REVOKE ALL ON {TABLE} FROM {group}",
         f"REVOKE USAGE ON SCHEMA harness FROM {group}", f"DROP ROLE {group}"],
    ):
        report = _gate(admin)
        seen = _visible(runtime, TABLE, a, b, set_role=group)
    _evidence("ADR010-P2", {"gate": asdict(report), "own_other_rows": seen})
    assert report.status == gates.PASS, report.render()
    assert seen == (2, 0)


def test_p3_security_invoker_view(admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]) -> None:
    a, b = tenants
    view = "harness.gate_inv"
    with _broken(
        admin,
        [f"CREATE VIEW {view} WITH (security_invoker = true) AS SELECT * FROM {TABLE}",
         f"GRANT SELECT ON {view} TO {RT}"],
        [f"DROP VIEW {view}"],
    ):
        report = _gate(admin)
        seen = _visible(runtime, view, a, b)
    _evidence("ADR010-P3", {"gate": asdict(report), "own_other_rows": seen})
    assert report.status == gates.PASS, report.render()
    assert seen == (2, 0)


def test_p4_p5_p6_manifest_platform_table_sequence_and_reviewed_definer(admin: Conn) -> None:
    with _broken(
        admin,
        ["CREATE TABLE harness.gate_platform (code text PRIMARY KEY)",
         f"GRANT SELECT, INSERT, UPDATE, DELETE ON harness.gate_platform TO {RT}",
         "CREATE SEQUENCE harness.gate_seq",
         f"GRANT USAGE, SELECT, UPDATE ON SEQUENCE harness.gate_seq TO {RT}",
         ("CREATE FUNCTION harness.gate_sd() RETURNS int LANGUAGE sql SECURITY DEFINER "
         "AS 'SELECT 1'")],
        ["DROP FUNCTION harness.gate_sd()", "DROP SEQUENCE harness.gate_seq",
         "DROP TABLE harness.gate_platform"],
    ):
        manifest = _manifest({"harness.gate_platform": "table"}, ("harness.gate_sd()",))
        report = _gate(admin, manifest=manifest)
        unreviewed = _gate(admin, manifest=_manifest({"harness.gate_platform": "table"}))
        unlisted = _gate(admin, manifest=_manifest(functions=("harness.gate_sd()",)))
    _evidence("ADR010-P4-P5-P6", asdict(report))
    assert report.status == gates.PASS, report.render()
    assert _has(unreviewed, "RLS_SECURITY_DEFINER_UNREVIEWED", "")  # N19, same fixture
    assert _has(unlisted, "RLS_TABLE_UNCLASSIFIED", "")


# --- SCN-004/005/067 behavioural cases (earlier rounds, retained) -----------------------


def test_scn067_gate_catches_rls_disabled_on_access_grant(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    clean = probe_cross_tenant(runtime, admin, ACCESS_GRANT, a, b, access_grant_row(90))
    assert clean.failures == [] and clean.visible_other_rows == 0
    with _broken(admin, [f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY"],
                 [f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"]):
        report = _gate(admin)
        runtime_view = _gate(runtime)
        leak = probe_cross_tenant(runtime, admin, ACCESS_GRANT, a, b, access_grant_row(91))
    _evidence("SCN-MOD001-067-GATE-NEGATIVE", asdict(report))
    _evidence("SCN-MOD001-067-RUNTIME-LEAK", {"failures": leak.failures, **asdict(leak)})
    assert report.status == gates.FAIL
    assert _violations(report) == [("RLS_NOT_ENFORCED", TABLE, "ENABLE ROW LEVEL SECURITY missing")]
    assert asdict(runtime_view) == asdict(report)
    assert leak.role == RT and leak.visible_other_rows == 3
    assert "CROSS_TENANT_READ:3" in leak.failures


TAUTOLOGIES = [
    ("permissive_true", "true", "true"),
    ("is_not_null", "tenant_id IS NOT NULL", "tenant_id IS NOT NULL"),
    ("self_equal", "tenant_id = tenant_id", "tenant_id = tenant_id"),
    ("or_true", f"{_POLICY_EXPR} OR true", f"{_POLICY_EXPR} OR true"),
    ("literal_check", _POLICY_EXPR, "'tenant_id' IS NOT NULL"),
]


@pytest.mark.parametrize(("name", "using", "check"), TAUTOLOGIES, ids=[t[0] for t in TAUTOLOGIES])
def test_tautological_policy_that_really_leaks(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID], name: str, using: str, check: str
) -> None:
    a, b = tenants
    with _broken(admin,
                 [f"ALTER POLICY tenant_isolation ON {TABLE} USING ({using}) WITH CHECK ({check})"],
                 [_ALTER_POLICY_BACK]):
        report = _gate(admin)
        leak = probe_cross_tenant(runtime, admin, ACCESS_GRANT, a, b, access_grant_row(89))
    _evidence(f"TAUTOLOGY[{name}]", {"gate": asdict(report), "leak": leak.failures})
    assert report.status == gates.FAIL
    assert {c for c, _, _ in _violations(report)} == {"RLS_NOT_ENFORCED"}
    assert leak.failures, f"{name}: predicate did not actually leak"



def test_tautological_using_with_canonical_check_is_a_read_leak(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]
) -> None:
    """USING alone broken, WITH CHECK canonical: only the USING rule can catch it."""
    a, b = tenants
    broken = (f"ALTER POLICY tenant_isolation ON {TABLE} USING (tenant_id IS NOT NULL) "
              f"WITH CHECK ({_POLICY_EXPR})")
    with _broken(admin, [broken], [_ALTER_POLICY_BACK]):
        report = _gate(admin)
        seen = _visible(runtime, TABLE, a, b)
    _evidence("TAUTOLOGY[using_only]", {"gate": asdict(report), "own_other_rows": seen})
    assert seen == (2, 3), "USING-only tautology must actually expose the other tenant"
    assert [d for _, _, d in _violations(report)] == [(
        "policy 'tenant_isolation' USING (tenant_id IS NOT NULL) is not the canonical "
        "tenant predicate")]


def test_n21_runtime_truncate_rejected_and_really_destructive(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    with _broken(admin, [f"GRANT TRUNCATE ON {TABLE} TO {RT}"],
                 [f"REVOKE TRUNCATE ON {TABLE} FROM {RT}"]):
        report = _gate(admin)
        with runtime.transaction():
            runtime.execute("SELECT set_config('app.tenant_id', %s, true)", (str(a),))
            runtime.execute(f"TRUNCATE {TABLE}")
        after = _scalar(admin, f"SELECT count(*) FROM {TABLE} WHERE tenant_id = %s", (b,))
    _evidence("ADR010-N21[truncate]", {"gate": asdict(report), "other_rows_after": after})
    assert _has(report, "RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}:TRUNCATE@{RT}")
    assert after == 0


# --- ADR-010 negatives as catalog breakages ----------------------------------------------
# (id, break SQL, restore SQL, [(code, detail fragment), ...])

G1, G2 = "veyro_gate_group_a", "veyro_gate_group_b"
_SCHEMA_BACK = [f"ALTER SCHEMA harness OWNER TO {OWNER_ROLE}",
                f"GRANT USAGE ON SCHEMA harness TO {RT}"]
_PREDEFINED = ["pg_execute_server_program", "pg_read_server_files", "pg_write_server_files",
               "pg_read_all_data", "pg_write_all_data"]
_RBF = "pg_catalog.pg_read_binary_file(text)"

BREAKAGES: list[tuple[str, list[str], list[str], list[tuple[str, str]]]] = [
    ("scn005_rls_not_forced", [f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY"],
     [f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"],
     [("RLS_NOT_ENFORCED", "FORCE ROW LEVEL SECURITY missing")]),
    ("scn005_policy_dropped", [f"DROP POLICY tenant_isolation ON {TABLE}"], [_RESTORE_POLICY],
     [("RLS_NOT_ENFORCED", "no RLS policy")]),
    ("scn005_tenant_id_nullable", [f"ALTER TABLE {TABLE} ALTER COLUMN tenant_id DROP NOT NULL"],
     [f"ALTER TABLE {TABLE} ALTER COLUMN tenant_id SET NOT NULL"],
     [("RLS_TENANT_ID_NULLABLE", "nullable")]),
    ("scn005_runtime_owns_table", [f"ALTER TABLE {TABLE} OWNER TO {RT}"],
     [f"ALTER TABLE {TABLE} OWNER TO {OWNER_ROLE}", _RUNTIME_GRANT],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"OWNS:table:{TABLE}")]),
    ("scn005_runtime_bypassrls", [f"ALTER ROLE {RT} BYPASSRLS"], [f"ALTER ROLE {RT} NOBYPASSRLS"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"ATTRIBUTE:BYPASSRLS@{RT}")]),
    ("scn005_runtime_member_of_owner", [f"GRANT {OWNER_ROLE} TO {RT}"],
     [f"REVOKE {OWNER_ROLE} FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"OWNS:table:{TABLE}")]),
    ("n1_replication", [f"ALTER ROLE {RT} REPLICATION"], [f"ALTER ROLE {RT} NOREPLICATION"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"ATTRIBUTE:REPLICATION@{RT}")]),
    ("n2_createrole", [f"ALTER ROLE {RT} CREATEROLE"], [f"ALTER ROLE {RT} NOCREATEROLE"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"ATTRIBUTE:CREATEROLE@{RT}")]),
    ("n2_createdb", [f"ALTER ROLE {RT} CREATEDB"], [f"ALTER ROLE {RT} NOCREATEDB"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"ATTRIBUTE:CREATEDB@{RT}")]),
    ("n3_group_bypassrls_set_only",
     [f"CREATE ROLE {G1} NOLOGIN BYPASSRLS", f"GRANT {G1} TO {RT} WITH INHERIT FALSE, SET TRUE"],
     [f"REVOKE {G1} FROM {RT}", f"DROP ROLE {G1}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"ATTRIBUTE:BYPASSRLS@{G1}")]),
    ("n3_group_replication_set_only",
     [f"CREATE ROLE {G1} NOLOGIN REPLICATION", f"GRANT {G1} TO {RT} WITH INHERIT FALSE, SET TRUE"],
     [f"REVOKE {G1} FROM {RT}", f"DROP ROLE {G1}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"ATTRIBUTE:REPLICATION@{G1}")]),
    *[(f"n4_{role}", [f"GRANT {role} TO {RT} WITH INHERIT FALSE, SET TRUE"],
       [f"REVOKE {role} FROM {RT}"],
       [("RLS_RUNTIME_ROLE_ELEVATED", f"PREDEFINED_ROLE:{role}")]) for role in _PREDEFINED],
    ("n5_runtime_owns_database", [f"ALTER DATABASE postgres OWNER TO {RT}"],
     ["ALTER DATABASE postgres OWNER TO postgres"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "PREDEFINED_ROLE:pg_database_owner"),
      ("RLS_RUNTIME_ROLE_ELEVATED", "OWNS:database:postgres")]),
    ("n6_system_function_execute_runtime", [f"GRANT EXECUTE ON FUNCTION {_RBF} TO {RT}"],
     [f"REVOKE EXECUTE ON FUNCTION {_RBF} FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"SYSTEM_ACL_MODIFIED:pg_read_binary_file(text):EXECUTE@{RT}")]),
    ("n6_system_function_execute_public", [f"GRANT EXECUTE ON FUNCTION {_RBF} TO PUBLIC"],
     [f"REVOKE EXECUTE ON FUNCTION {_RBF} FROM PUBLIC"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "SYSTEM_ACL_MODIFIED:pg_read_binary_file(text):EXECUTE@PUBLIC")]),
    ("n6_system_function_execute_group",
     [f"CREATE ROLE {G2} NOLOGIN", f"GRANT EXECUTE ON FUNCTION {_RBF} TO {G2}", f"GRANT {G2} TO {RT}"],
     [f"REVOKE {G2} FROM {RT}", f"REVOKE EXECUTE ON FUNCTION {_RBF} FROM {G2}", f"DROP ROLE {G2}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"SYSTEM_ACL_MODIFIED:pg_read_binary_file(text):EXECUTE@{G2}")]),
    ("n7_runtime_owns_schema", [f"ALTER SCHEMA harness OWNER TO {RT}"], _SCHEMA_BACK,
     [("RLS_RUNTIME_ROLE_ELEVATED", "OWNS:schema:harness")]),
    ("n7_group_owns_schema",
     [f"CREATE ROLE {G2} NOLOGIN", f"GRANT {G2} TO {RT}", f"ALTER SCHEMA harness OWNER TO {G2}"],
     [*_SCHEMA_BACK, f"REVOKE {G2} FROM {RT}", f"DROP ROLE {G2}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "OWNS:schema:harness")]),
    ("n8_create_on_schema", [f"GRANT CREATE ON SCHEMA harness TO {RT}"],
     [f"REVOKE CREATE ON SCHEMA harness FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:schema:harness:CREATE@{RT}")]),
    ("n8_create_on_database", [f"GRANT CREATE ON DATABASE postgres TO {RT}"],
     [f"REVOKE CREATE ON DATABASE postgres FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:database:postgres:CREATE@{RT}")]),
    ("n9_owns_unrelated_objects",
     ["CREATE SCHEMA gate_other", "CREATE SEQUENCE gate_other.s",
      f"ALTER SEQUENCE gate_other.s OWNER TO {RT}",
      "CREATE FUNCTION gate_other.f() RETURNS int LANGUAGE sql AS 'SELECT 1'",
      f"ALTER FUNCTION gate_other.f() OWNER TO {RT}", "CREATE TYPE gate_other.t AS (x int)",
      f"ALTER TYPE gate_other.t OWNER TO {RT}"],
     ["DROP SCHEMA gate_other CASCADE"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "OWNS:sequence:gate_other.s"),
      ("RLS_RUNTIME_ROLE_ELEVATED", "OWNS:function:gate_other.f()"),
      ("RLS_RUNTIME_ROLE_ELEVATED", "OWNS:composite_type:gate_other.t")]),
    ("n13_view_without_security_invoker",
     [f"CREATE VIEW harness.gate_v AS SELECT * FROM {TABLE}",
      f"GRANT SELECT ON harness.gate_v TO {RT}"],
     ["DROP VIEW harness.gate_v"],
     [("RLS_NOT_ENFORCED", "lacks security_invoker")]),
    ("n16_public_select", [f"GRANT SELECT ON {TABLE} TO PUBLIC"],
     [f"REVOKE SELECT ON {TABLE} FROM PUBLIC"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}:SELECT@PUBLIC")]),
    ("n17_tenant_id_text",
     ["CREATE TABLE harness.gate_text_tenant (tenant_id text NOT NULL)"],
     ["DROP TABLE harness.gate_text_tenant"],
     [("RLS_TENANT_ID_NOT_UUID", "not uuid")]),
    ("n18_role_tenant_default",
     [f"ALTER ROLE {RT} SET app.tenant_id = '00000000-0000-4000-8000-000000000001'"],
     [f"ALTER ROLE {RT} RESET app.tenant_id"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "TENANT_CONTEXT_DEFAULT:app.tenant_id=")]),
    ("n18_database_tenant_default",
     ["ALTER DATABASE postgres SET app.tenant_id = '00000000-0000-4000-8000-000000000001'"],
     ["ALTER DATABASE postgres RESET app.tenant_id"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "TENANT_CONTEXT_DEFAULT:app.tenant_id=")]),
    ("n19_unreviewed_security_definer",
     ["CREATE FUNCTION harness.gate_sd() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'"],
     ["DROP FUNCTION harness.gate_sd()"],
     [("RLS_SECURITY_DEFINER_UNREVIEWED", "")]),
    ("n20_lo_compat_privileges", ["SET lo_compat_privileges = on"],
     ["RESET lo_compat_privileges"],
     [("RLS_RUNTIME_ROLE_ELEVATED", "ATTRIBUTE:LO_COMPAT_PRIVILEGES@postgres")]),
    ("n21_public_truncate", [f"GRANT TRUNCATE ON {TABLE} TO PUBLIC"],
     [f"REVOKE TRUNCATE ON {TABLE} FROM PUBLIC"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}:TRUNCATE@PUBLIC")]),
    ("n21_trigger", [f"GRANT TRIGGER ON {TABLE} TO {RT}"], [f"REVOKE TRIGGER ON {TABLE} FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}:TRIGGER@{RT}")]),
    ("n21_references_table", [f"GRANT REFERENCES ON {TABLE} TO {RT}"],
     [f"REVOKE REFERENCES ON {TABLE} FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}:REFERENCES@{RT}")]),
    ("n21_references_column", [f"GRANT REFERENCES (tenant_id) ON {TABLE} TO {RT}"],
     [f"REVOKE REFERENCES (tenant_id) ON {TABLE} FROM {RT}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}.tenant_id:REFERENCES@{RT}")]),
    ("n21_truncate_via_set_role",
     [f"CREATE ROLE {G2} NOLOGIN", f"GRANT TRUNCATE ON {TABLE} TO {G2}", f"GRANT {G2} TO {RT}"],
     [f"REVOKE {G2} FROM {RT}", f"REVOKE ALL ON {TABLE} FROM {G2}", f"DROP ROLE {G2}"],
     [("RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:table:{TABLE}:TRUNCATE@{G2}")]),
]


@pytest.mark.parametrize(
    ("name", "break_sql", "restore_sql", "expected"), BREAKAGES, ids=[b[0] for b in BREAKAGES]
)
def test_adr010_negative_breakage(
    admin: Conn, runtime: Conn, name: str, break_sql: list[str], restore_sql: list[str],
    expected: list[tuple[str, str]],
) -> None:
    with _broken(admin, break_sql, restore_sql):
        report = _gate(admin)
    _evidence(f"ADR010-NEGATIVE[{name}]", asdict(report))
    assert report.status == gates.FAIL, report.render()
    for code, fragment in expected:
        assert _has(report, code, fragment), (code, fragment, report.render())


def test_n10_n11_operator_hijack_caught_by_pinned_deparse_and_dependency_closure(
    pg: DisposablePostgres, admin: Conn, runtime: Conn, runtime_password: str,
    tenants: tuple[UUID, UUID],
) -> None:
    """R2 P2-1. A policy written under `search_path = public, pg_catalog` binds a
    non-system `=`; under that ambient path its deparse reads canonical."""
    a, b = tenants
    hijack = [
        ("CREATE FUNCTION public.veyro_gate_true(uuid, uuid) RETURNS boolean "
        "LANGUAGE sql IMMUTABLE AS 'SELECT true'"),
        ("CREATE OPERATOR public.= (LEFTARG = uuid, RIGHTARG = uuid, "
        "FUNCTION = public.veyro_gate_true)"),
        "ALTER DATABASE postgres SET search_path = public, pg_catalog",
        "SET search_path = public, pg_catalog",
        (f"ALTER POLICY tenant_isolation ON {TABLE} USING ({_POLICY_EXPR}) "
        f"WITH CHECK ({_POLICY_EXPR})"),
        "RESET search_path",
    ]
    undo = [_ALTER_POLICY_BACK, "DROP OPERATOR public.= (uuid, uuid)",
            "DROP FUNCTION public.veyro_gate_true(uuid, uuid)",
            "ALTER DATABASE postgres RESET search_path"]
    with _broken(admin, hijack, undo):
        with psycopg.connect(pg.dsn(RT, runtime_password), autocommit=True) as fresh:
            ambient = _scalar(fresh, "SHOW search_path")
            report = _gate(fresh)  # inspector inherits the hostile database default
        seen = _visible(runtime, TABLE, a, b)
    _evidence("ADR010-N10", {"ambient": ambient, "gate": asdict(report), "own_other_rows": seen})
    assert ambient == "public, pg_catalog"
    assert seen[1] == 3, "hijacked predicate must actually leak for this negative to mean anything"
    assert _has(report, "RLS_NOT_ENFORCED", "is not the canonical tenant predicate")
    assert _has(report, "RLS_NOT_ENFORCED", "depends on")

    # N11: textually canonical policy whose NULLIF bound a shadowing =(text,text).
    shadow = [
        ("CREATE FUNCTION public.veyro_gate_texteq(text, text) RETURNS boolean "
        "LANGUAGE sql IMMUTABLE AS 'SELECT pg_catalog.texteq($1, $2)'"),
        ("CREATE OPERATOR public.= (LEFTARG = text, RIGHTARG = text, "
        "FUNCTION = public.veyro_gate_texteq)"),
        "SET search_path = public, pg_catalog",
        (f"ALTER POLICY tenant_isolation ON {TABLE} USING ({_POLICY_EXPR}) "
        f"WITH CHECK ({_POLICY_EXPR})"),
        "RESET search_path",
    ]
    with _broken(admin, shadow, [_ALTER_POLICY_BACK, "DROP OPERATOR public.= (text, text)",
                                 "DROP FUNCTION public.veyro_gate_texteq(text, text)"]):
        n11 = _gate(admin)
    _evidence("ADR010-N11", asdict(n11))
    assert _has(n11, "RLS_NOT_ENFORCED", "depends on")


def test_n12_n14_materialized_view(admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]) -> None:
    a, b = tenants
    with _broken(admin, [f"CREATE MATERIALIZED VIEW harness.gate_mv AS SELECT * FROM {TABLE}",
                         f"GRANT SELECT ON harness.gate_mv TO {RT}"],
                 ["DROP MATERIALIZED VIEW harness.gate_mv"]):
        report = _gate(admin)
        listed = _gate(admin, manifest=_manifest({"harness.gate_mv": "matview"}))
        seen = _visible(runtime, "harness.gate_mv", a, b)
    _evidence("ADR010-N12", {"gate": asdict(report), "own_other_rows": seen})
    assert seen[1] == 3, "materialized view must actually expose the other tenant"
    assert _has(report, "RLS_NOT_ENFORCED", "materialized view")
    # N14: a manifest matview entry cannot launder a relation that has tenant_id.
    assert _has(listed, "RLS_EXEMPTION_INVALID", "relation has tenant_id")
    assert _has(listed, "RLS_NOT_ENFORCED", "materialized view")


def test_n14_manifest_kind_mismatch(admin: Conn) -> None:
    with _broken(admin, ["CREATE TABLE harness.gate_lookup (code text PRIMARY KEY)"],
                 ["DROP TABLE harness.gate_lookup"]):
        report = _gate(admin, manifest=_manifest({"harness.gate_lookup": "matview"}))
    assert _has(report, "RLS_EXEMPTION_INVALID", "does not match relkind 'r'")


def test_n13_granted_foreign_table(admin: Conn) -> None:
    if not _scalar(admin, "SELECT count(*) FROM pg_available_extensions WHERE name = 'postgres_fdw'"):
        pytest.skip("postgres_fdw not shipped in the pinned image")
    with _broken(
        admin,
        ["CREATE EXTENSION postgres_fdw", "CREATE SERVER gate_srv FOREIGN DATA WRAPPER postgres_fdw",
         "CREATE FOREIGN TABLE harness.gate_ft (tenant_id uuid) SERVER gate_srv",
         f"GRANT SELECT ON harness.gate_ft TO {RT}"],
        ["DROP FOREIGN TABLE harness.gate_ft", "DROP SERVER gate_srv",
         "DROP EXTENSION postgres_fdw"],
    ):
        report = _gate(admin)
    _evidence("ADR010-N13[foreign]", asdict(report))
    assert _has(report, "RLS_NOT_ENFORCED", "foreign table")


def test_n15_granted_relation_outside_schema_scope(admin: Conn) -> None:
    report = _gate(admin, schemas=["harness"])
    _evidence("ADR010-N15", asdict(report))
    for name in AUTH_TABLES:
        assert _has(report, "RLS_RUNTIME_ROLE_ELEVATED", f"OUT_OF_SCOPE:{name}")


def test_n20_large_object_grant(admin: Conn) -> None:
    oid = int(_scalar(admin, "SELECT lo_create(0)"))
    try:
        admin.execute(f"GRANT SELECT ON LARGE OBJECT {oid} TO {RT}")
        report = _gate(admin)
    finally:
        admin.execute(f"SELECT lo_unlink({oid})")
    assert _has(report, "RLS_RUNTIME_ROLE_ELEVATED", f"PRIVILEGE:large_object:{oid}:SELECT@{RT}")



# --- ADR-010 Amendment A1: system-object definition and PG16 information_schema pin -----

INFO = "information_schema"


def test_a1_pin_equals_pristine_pg16_information_schema(admin: Conn) -> None:
    """The committed per-object pin is exactly what this pristine initdb grants PUBLIC."""
    rows = admin.execute(
        "SELECT c.relname::text, c.relkind::text FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a "
        "WHERE n.nspname = 'information_schema' AND c.oid < 16384 AND a.grantee = 0 "
        "AND a.privilege_type = 'SELECT'").fetchall()
    live = {name: {"r": "table", "v": "view"}[kind] for name, kind in rows}
    other_public = admin.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, "
        "aclexplode(c.relacl) a WHERE n.nspname = 'information_schema' AND a.grantee = 0 "
        "AND a.privilege_type <> 'SELECT'").fetchone()
    no_init = _scalar(admin, "SELECT count(*) FROM pg_init_privs ip JOIN pg_class c "
                             "ON c.oid = ip.objoid AND ip.classoid = 'pg_class'::regclass "
                             "WHERE c.relnamespace = 'information_schema'::regnamespace")
    _evidence("ADR010-A1-PIN", {"live": len(live), "pinned": len(gates.PINNED_INFORMATION_SCHEMA_SELECT[16])})
    assert live == gates.PINNED_INFORMATION_SCHEMA_SELECT[16]
    assert len(live) == 62 and other_public == (0,) and no_init == 0


def test_n27_n28_new_relation_in_information_schema(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, b = tenants
    for kind, ddl in (("view", f"CREATE VIEW {INFO}.zz_leak AS SELECT * FROM {TABLE}"),
                      ("table", f"CREATE TABLE {INFO}.zz_leak AS SELECT * FROM {TABLE}")):
        drop = f"DROP {kind.upper()} {INFO}.zz_leak"
        with _broken(admin, [ddl, f"GRANT SELECT ON {INFO}.zz_leak TO PUBLIC"], [drop]):
            report = _gate(admin)
            seen = _visible(runtime, f"{INFO}.zz_leak", a, b)
        _evidence(f"ADR010-N27-N28[{kind}]", {"gate": asdict(report), "own_other_rows": seen})
        assert seen == (2, 3), "the planted relation must actually expose the other tenant"
        assert _has(report, "RLS_RUNTIME_ROLE_ELEVATED",
                    f"NON_STOCK_SYSTEM_OBJECT:{kind}:{INFO}.zz_leak:SELECT@PUBLIC")
        _assert_token_exclusive(report, "NON_STOCK_SYSTEM_OBJECT:")


def test_n30_security_definer_function_in_system_schemas(
    admin: Conn, runtime: Conn, tenants: tuple[UUID, UUID]
) -> None:
    a, _ = tenants
    for schema, ident in (("pg_catalog", "zz_count()"), (INFO, f"{INFO}.zz_count()")):
        fn = f"{schema}.zz_count()"
        create = (f"CREATE FUNCTION {fn} RETURNS bigint LANGUAGE sql SECURITY DEFINER "
                  f"AS 'SELECT count(*) FROM {TABLE}'")
        with _broken(admin, [create], [f"DROP FUNCTION {fn}"]):
            report = _gate(admin)
            with runtime.transaction():
                runtime.execute("SELECT set_config('app.tenant_id', %s, true)", (str(a),))
                own = _scalar(runtime, f"SELECT count(*) FROM {TABLE}")
                via_definer = _scalar(runtime, f"SELECT {fn}")
        _evidence(f"ADR010-N30[{schema}]", {"gate": asdict(report), "own": own,
                                            "via_definer": via_definer})
        assert (own, via_definer) == (2, 5), "definer must actually count every tenant's rows"
        assert _has(report, "RLS_RUNTIME_ROLE_ELEVATED",
                    f"NON_STOCK_SYSTEM_OBJECT:function:{ident}:EXECUTE@PUBLIC")
        _assert_token_exclusive(report, "NON_STOCK_SYSTEM_OBJECT:")
        assert _has(report, "RLS_SECURITY_DEFINER_UNREVIEWED", "")


A1_BREAKAGES: list[tuple[str, list[str], list[str], tuple[str, str]]] = [
    ("n29_stock_user_mappings_public", [f"GRANT SELECT ON {INFO}._pg_user_mappings TO PUBLIC"],
     [f"REVOKE SELECT ON {INFO}._pg_user_mappings FROM PUBLIC"],
     ("RLS_RUNTIME_ROLE_ELEVATED", f"SYSTEM_ACL_MODIFIED:{INFO}._pg_user_mappings:SELECT@PUBLIC")),
    ("n29_stock_sql_parts_public", [f"GRANT SELECT ON {INFO}.sql_parts TO PUBLIC"],
     [f"REVOKE SELECT ON {INFO}.sql_parts FROM PUBLIC"],
     ("RLS_RUNTIME_ROLE_ELEVATED", f"SYSTEM_ACL_MODIFIED:{INFO}.sql_parts:SELECT@PUBLIC")),
    # N31a (ADR-010 A1.7): H2 is a NEW view, so non-stock: NON_STOCK_SYSTEM_OBJECT only.
    ("n31a_h2_new_view_granted_to_runtime",
     [f"CREATE VIEW {INFO}.zz_leak AS SELECT 1 AS x", f"GRANT SELECT ON {INFO}.zz_leak TO {RT}"],
     [f"DROP VIEW {INFO}.zz_leak"],
     ("RLS_RUNTIME_ROLE_ELEVATED", f"NON_STOCK_SYSTEM_OBJECT:view:{INFO}.zz_leak:SELECT@{RT}")),
    # N31b (A1.7): H4/H5/H6 are on stock objects: SYSTEM_ACL_MODIFIED only.
    ("n31b_h4_public_update_sql_features", [f"GRANT UPDATE ON {INFO}.sql_features TO PUBLIC"],
     [f"REVOKE UPDATE ON {INFO}.sql_features FROM PUBLIC"],
     ("RLS_RUNTIME_ROLE_ELEVATED", f"SYSTEM_ACL_MODIFIED:{INFO}.sql_features:UPDATE@PUBLIC")),
    ("n31b_h5_public_create_on_schema", [f"GRANT CREATE ON SCHEMA {INFO} TO PUBLIC"],
     [f"REVOKE CREATE ON SCHEMA {INFO} FROM PUBLIC"],
     ("RLS_RUNTIME_ROLE_ELEVATED", f"SYSTEM_ACL_MODIFIED:{INFO}:CREATE@PUBLIC")),
    ("n31b_h6_column_public_update", [f"GRANT UPDATE (feature_id) ON {INFO}.sql_features TO PUBLIC"],
     [f"REVOKE UPDATE (feature_id) ON {INFO}.sql_features FROM PUBLIC"],
     ("RLS_RUNTIME_ROLE_ELEVATED",
      f"SYSTEM_ACL_MODIFIED:{INFO}.sql_features.feature_id:UPDATE@PUBLIC")),
]


_A1_FAMILIES = ("NON_STOCK_SYSTEM_OBJECT:", "SYSTEM_ACL_MODIFIED:")


def _assert_token_exclusive(report: Any, expected_token: str) -> None:
    """ADR-010 A1.7: classification-based, exclusive tokens — a run whose expected token
    is one family must not emit the other family for any grant."""
    family = next(f for f in _A1_FAMILIES if expected_token.startswith(f))
    forbidden = next(f for f in _A1_FAMILIES if f != family)
    leaked = [d for _, _, d in _violations(report) if d.startswith(forbidden)]
    assert leaked == [], (expected_token, leaked)


@pytest.mark.parametrize(("name", "break_sql", "restore_sql", "expected"), A1_BREAKAGES,
                         ids=[b[0] for b in A1_BREAKAGES])
def test_a1_negative_breakage(
    admin: Conn, name: str, break_sql: list[str], restore_sql: list[str],
    expected: tuple[str, str],
) -> None:
    with _broken(admin, break_sql, restore_sql):
        report = _gate(admin)
    _evidence(f"ADR010-A1-NEGATIVE[{name}]", asdict(report))
    assert report.status == gates.FAIL, report.render()
    assert _has(report, *expected), report.render()
    _assert_token_exclusive(report, expected[1])


def test_p9_concurrent_temp_table_is_not_a_system_object(
    pg: DisposablePostgres, admin: Conn
) -> None:
    with psycopg.connect(pg.superuser_dsn, autocommit=True) as other:
        other.execute("CREATE TEMP TABLE zz_tmp (x int)")
        temp_ns = _scalar(other, "SELECT nspname FROM pg_namespace WHERE oid = pg_my_temp_schema()")
        report = _gate(admin)
    _evidence("ADR010-P9", {"temp_namespace": temp_ns, "gate": asdict(report)})
    assert str(temp_ns).startswith("pg_temp_")
    assert report.status == gates.PASS, report.render()


def test_p10_tightening_a_stock_public_grant_passes(admin: Conn) -> None:
    with _broken(admin, [f"REVOKE SELECT ON {INFO}.tables FROM PUBLIC"],
                 [f"GRANT SELECT ON {INFO}.tables TO PUBLIC"]):
        report = _gate(admin)
    _evidence("ADR010-P10", asdict(report))
    assert report.status == gates.PASS, report.render()

# --- inputs, scope and CLI -------------------------------------------------------------


def test_input_failures_never_pass(admin: Conn) -> None:
    typo = _gate(admin, schemas=["harnes"])
    no_role = gates.run_rls_gate(admin, "veyro_runtime_missing", manifest=_manifest(),
                                 resolver_root=APPROVAL_ROOT)
    gone = _gate(admin, required_tables=[TABLE, "harness.member_note"])
    bad_approval = _gate(admin, manifest={**_manifest(), "platform_scope_relations": {
        "harness_auth.identity": {"kind": "table", "reason": "r", "approval": "ADR-901"}}})
    _evidence("RLS-GATE-INPUT-FAILURES", [asdict(r) for r in (typo, no_role, gone, bad_approval)])
    assert (typo.status, typo.codes()) == (gates.ERROR, {"RLS_GATE_INPUT_INVALID"})
    assert no_role.status == gates.FAIL and "RLS_RUNTIME_ROLE_MISSING" in no_role.codes()
    assert _has(gone, "RLS_REQUIRED_TABLE_MISSING", "")
    assert bad_approval.status == gates.ERROR
    assert all(r.exit_code != 0 for r in (typo, no_role, gone, bad_approval))


def test_cli_end_to_end_uses_only_the_committed_manifest(
    pg: DisposablePostgres, admin: Conn, runtime_password: str
) -> None:
    # The committed manifest is the empty skeleton, so the CLI can only PASS once the
    # runtime role holds nothing on unclassified harness_auth tables.
    env = {**os.environ, gates.DSN_ENV: pg.dsn(RT, runtime_password)}
    argv = [sys.executable, str(_GATES_PATH), "--gate", "rls", "--runtime-role", RT,
            "--schema", "harness", "--require-table", TABLE, "--json"]

    def run(extra: list[str] | None = None,
            env_: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*argv, *(extra or [])], capture_output=True, text=True,
                              env=env_ or env, check=False)

    with_auth_grants = run()
    revoke = [f"REVOKE ALL ON {t} FROM {RT}" for t in AUTH_TABLES]
    regrant = [f"GRANT SELECT ON harness_auth.identity TO {RT}",
               f"GRANT INSERT ON harness_auth.session, harness_auth.audit_event TO {RT}"]
    with _broken(admin, revoke, regrant):
        ok = run()
    with _broken(admin, [*revoke, f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY"],
                 [f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY", *regrant]):
        bad = run()
    removed_flag = run(["--non-tenant-manifest", "/tmp/x.json"])
    wrong = run(env_={**env, gates.DSN_ENV: pg.dsn(RT, secrets.token_urlsafe(12))})
    _evidence("RLS-GATE-CLI", {k: [r.returncode, r.stdout] for k, r in {
        "with_auth_grants": with_auth_grants, "ok": ok, "bad": bad}.items()})
    assert with_auth_grants.returncode == 1
    assert "OUT_OF_SCOPE:harness_auth.identity" in with_auth_grants.stdout
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["violations"][0]["code"] == "RLS_NOT_ENFORCED"
    assert removed_flag.returncode == 2 and "unrecognized arguments" in removed_flag.stderr
    assert wrong.returncode == 2 and "OperationalError" in wrong.stdout
    for r in (with_auth_grants, ok, bad, wrong):
        assert runtime_password not in r.stdout + r.stderr
