"""Independent review probe for BUG-048 (read-only wrt the repo; throwaway container)."""
from __future__ import annotations
import sys
sys.path.insert(0, "/Users/ahmadmabrouk/Desktop/Veyro/backend")

from tests.harness.postgres import disposable_postgres
from tests.harness.tenant_isolation import (
    ACCESS_GRANT, ACCESS_GRANT_COLUMNS, OWNER_ROLE, RUNTIME_ROLE,
    create_tenant_table, provision_roles, one_row, read_posture,
)
import psycopg

RT, OWN = RUNTIME_ROLE, OWNER_ROLE
TBL = "harness.access_grant"
_RUNTIME_GRANT = f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TBL} TO {RT}"
_RUNTIME_DML = "SELECT, INSERT, UPDATE, DELETE"

def acl(c):
    return one_row(c.execute("SELECT relacl::text FROM pg_class WHERE oid = %s::regclass", (TBL,)))[0]

def sacl(c):
    return one_row(c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='harness'"))[0]

def htp(c, privs=_RUNTIME_DML, role=RT):
    return one_row(c.execute("SELECT has_table_privilege(%s, 'harness.access_grant', %s)", (role, privs)))[0]

def flags(c):
    return one_row(c.execute(
        "SELECT pg_get_userbyid(c.relowner)::text, c.relrowsecurity, c.relforcerowsecurity,"
        " (SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid),"
        " (SELECT a.attnotnull FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attname='tenant_id' AND NOT a.attisdropped),"
        " (SELECT p.polqual::text IS NOT NULL FROM pg_policy p WHERE p.polrelid=c.oid LIMIT 1)"
        " FROM pg_class c WHERE c.oid=%s::regclass", (TBL,)))

def P(label, *vals):
    print(f"[{label}] " + " | ".join(str(v) for v in vals), flush=True)

with disposable_postgres() as pg:
    with psycopg.connect(pg.superuser_dsn, autocommit=True) as a:
        provision_roles(a)
        create_tenant_table(a, ACCESS_GRANT, ACCESS_GRANT_COLUMNS)
        baseline_acl = acl(a); baseline_sacl = sacl(a); baseline_flags = flags(a)
        P("0-BASELINE-relacl", baseline_acl)
        P("0-BASELINE-nspacl", baseline_sacl)
        P("0-BASELINE-flags", baseline_flags)
        P("0-BASELINE-htp(list)", htp(a))
        P("0-ROLE-attrs", one_row(a.execute(
            "SELECT rolinherit, rolsuper, rolbypassrls, (SELECT count(*) FROM pg_auth_members m JOIN pg_roles r2 ON r2.oid=m.member WHERE r2.rolname=%s) FROM pg_roles WHERE rolname=%s", (RT, RT))))

        # --- Q2a: comma-list semantics, measured ---
        a.execute(f"REVOKE INSERT, UPDATE, DELETE ON {TBL} FROM {RT}")
        P("Q2a-only-SELECT-relacl", acl(a))
        P("Q2a-only-SELECT-htp(list)", htp(a))
        P("Q2a-only-SELECT-htp(INSERT)", htp(a, "INSERT"))
        P("Q2a-only-SELECT-htp(SELECT)", htp(a, "SELECT"))
        a.execute(f"REVOKE ALL ON {TBL} FROM {RT}")
        P("Q2a-none-relacl", acl(a))
        P("Q2a-none-htp(list)", htp(a))
        a.execute(_RUNTIME_GRANT)
        P("Q2a-regranted-relacl", acl(a), "identical_to_baseline=", acl(a) == baseline_acl)

        # --- Q2b: PUBLIC-grant path with the runtime ACL entry genuinely absent ---
        a.execute(f"REVOKE ALL ON {TBL} FROM {RT}")
        a.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TBL} TO PUBLIC")
        P("Q2b-PUBLIC-relacl", acl(a))
        P("Q2b-PUBLIC-htp(list)-with-runtime-entry-absent", htp(a))
        a.execute(f"REVOKE ALL ON {TBL} FROM PUBLIC")
        a.execute(_RUNTIME_GRANT)
        P("Q2b-restored", acl(a) == baseline_acl)

        # --- Q1: owner round-trip WITHOUT the re-grant (mutant M1 = pre-fix shape) ---
        a.execute(f"ALTER TABLE {TBL} OWNER TO {RT}")
        P("Q1-M1-owned-by-runtime-relacl", acl(a))
        a.execute(f"ALTER TABLE {TBL} OWNER TO {OWN}")
        P("Q1-M1-after-roundtrip-relacl", acl(a))
        P("Q1-M1-after-roundtrip-htp(list)", htp(a))
        P("Q1-M1-ASSERTION-WOULD-PASS", htp(a) is True)
        P("Q1-M1-nspacl-unchanged", sacl(a) == baseline_sacl, sacl(a))
        P("Q1-M1-flags-unchanged", flags(a) == baseline_flags, flags(a))
        P("Q1-M1-posture-violations-empty", read_posture(a, ACCESS_GRANT).violations)

        # --- Q1: the fix's restore order (OWNER TO first, then GRANT) ---
        a.execute(_RUNTIME_GRANT)
        P("Q1-FIX-relacl", acl(a))
        P("Q1-FIX-byte-identical-to-baseline", acl(a) == baseline_acl)
        P("Q1-FIX-htp(list)", htp(a))

        # --- Q1: reverse order (GRANT issued while veyro_runtime still owns the table) ---
        a.execute(f"ALTER TABLE {TBL} OWNER TO {RT}")
        a.execute(_RUNTIME_GRANT)
        P("Q1-REV-grant-while-runtime-owns-relacl", acl(a))
        a.execute(f"ALTER TABLE {TBL} OWNER TO {OWN}")
        P("Q1-REV-after-owner-back-relacl", acl(a))
        P("Q1-REV-htp(list)", htp(a))
        P("Q1-REV-byte-identical-to-baseline", acl(a) == baseline_acl)
        a.execute(_RUNTIME_GRANT)
        P("Q1-REV-repaired", acl(a) == baseline_acl)

        # --- Q2d: mutant M2 = partial re-grant (SELECT only) after the owner round-trip ---
        a.execute(f"ALTER TABLE {TBL} OWNER TO {RT}")
        a.execute(f"ALTER TABLE {TBL} OWNER TO {OWN}")
        a.execute(f"GRANT SELECT ON {TBL} TO {RT}")
        P("Q2d-M2-partial-relacl", acl(a))
        P("Q2d-M2-htp(list)", htp(a))
        P("Q2d-M2-ASSERTION-WOULD-PASS", htp(a) is True)
        P("Q2d-M2-byte-identical-to-baseline", acl(a) == baseline_acl)
        P("Q2d-M2-posture-violations", read_posture(a, ACCESS_GRANT).violations)
        # does real runtime DML actually work in M2 state?
        a.execute(_RUNTIME_GRANT)

        # --- Q1: do the other four Slice-5 breakages mutate the ACL? ---
        others = [
            ("rls_disabled", [f"ALTER TABLE {TBL} DISABLE ROW LEVEL SECURITY"], [f"ALTER TABLE {TBL} ENABLE ROW LEVEL SECURITY"]),
            ("permissive_policy", [f"ALTER POLICY tenant_isolation ON {TBL} USING (true) WITH CHECK (true)"],
             [f"ALTER POLICY tenant_isolation ON {TBL} USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
              f" WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"]),
            ("rls_not_forced", [f"ALTER TABLE {TBL} NO FORCE ROW LEVEL SECURITY"], [f"ALTER TABLE {TBL} FORCE ROW LEVEL SECURITY"]),
            ("tenant_id_nullable", [f"ALTER TABLE {TBL} ALTER COLUMN tenant_id DROP NOT NULL"], [f"ALTER TABLE {TBL} ALTER COLUMN tenant_id SET NOT NULL"]),
        ]
        for name, brk, res in others:
            for s in brk: a.execute(s)
            mid_acl, mid_sacl = acl(a), sacl(a)
            for s in res: a.execute(s)
            P(f"Q1-OTHER[{name}]", "acl_changed_while_broken=", mid_acl != baseline_acl,
              "acl_after_restore_identical=", acl(a) == baseline_acl,
              "nspacl_identical=", sacl(a) == baseline_sacl,
              "flags_identical=", flags(a) == baseline_flags)
        P("FINAL-relacl", acl(a), "identical=", acl(a) == baseline_acl)
        P("FINAL-flags-identical", flags(a) == baseline_flags)
