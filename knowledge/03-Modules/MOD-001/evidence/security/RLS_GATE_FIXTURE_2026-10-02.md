---
doc: RLS_GATE_FIXTURE_2026-10-02
module: MOD-001
gate: TSD §24.1 gate 1 — RLS lint (`tools/validate_architecture_gates.py --gate rls`)
status: EXECUTED — R1 BLOCKED (P1-A); remediated; PENDING fresh R2 review
---

# RLS gate fixture record (IMPLEMENTATION.md §4 gate 1)

Engine: approved CAP-008 Colima binding (`colima`, 29.5.2, Ubuntu 24.04.4
LTS), pinned `postgres:16-alpine` digest, synthetic rows only. Fixture:
Slice-5 `harness.access_grant`, owned by `veyro_schema_owner`, runtime
`veyro_runtime` (NOSUPERUSER NOBYPASSRLS NOINHERIT, owns nothing).
Raw output: `R04-RLS-PERMISSION-GATES-RAW-2026-10-02.txt` §1.

| Fixture | Gate verdict | Scenario |
|---|---|---|
| Compliant `access_grant` | PASS, exit 0, checked `[harness.access_grant]` | SCN-004 |
| RLS disabled on `access_grant` | FAIL, `RLS_NOT_ENFORCED` (ENABLE missing); runtime probe leaks 3/3 of other tenant's rows | SCN-067 negative |
| Permissive `USING (true)` policy | FAIL, `RLS_NOT_ENFORCED` ×2; runtime probe leaks 3/3 | SCN-005 family |
| FORCE removed | FAIL, `RLS_NOT_ENFORCED` (FORCE missing) | SCN-005 |
| Policy dropped | FAIL, `RLS_NOT_ENFORCED` (no policy) | SCN-005 family |
| `tenant_id` nullable | FAIL, `RLS_TENANT_ID_NULLABLE` on `harness.access_grant.tenant_id` | SCN-005(ii) |
| Runtime owns table | FAIL, `RLS_RUNTIME_ROLE_ELEVATED` OWNS_TABLE | SCN-005(i) |
| Runtime BYPASSRLS | FAIL, `RLS_RUNTIME_ROLE_ELEVATED` BYPASSRLS | SCN-005(i) |
| Runtime member of owner | FAIL, `RLS_RUNTIME_ROLE_ELEVATED` MEMBER_OF_OWNER | SCN-005(i) |
| Runtime member of BYPASSRLS group | FAIL, `RLS_RUNTIME_ROLE_ELEVATED` MEMBER_OF_PRIVILEGED_ROLE | SCN-005(i) |
| Extra table without `tenant_id` | FAIL, `RLS_TABLE_UNCLASSIFIED`; PASS once declared non-tenant | gate hardening |
| Empty schema / misspelled schema / missing role / missing required table | INCONCLUSIVE / ERROR / FAIL / FAIL — all non-zero | gate hardening |

Every breakage was restored and the gate re-verified PASS with the
runtime DML grant intact. Gate verdicts were identical through the
superuser setup connection and the non-privileged runtime connection;
the CLI run used the runtime role's DSN via environment.

Not a real-repository PASS: no product database exists yet.
Disposition is the independent reviewer's call, not this record's.

## Update — R1 remediation (2026-10-02)

R1 reproduced a false PASS: with TRUNCATE granted to `veyro_runtime` the
gate passed while the runtime role emptied the other tenant's rows. The
table above is the pre-R1 run. Additional Colima fixtures now (raw:
`R04-R1-REMEDIATION-RAW-2026-10-02.txt` §1, re-run in
`R04-ADR009-IMPLEMENTATION-RAW-2026-10-02.txt` §2, 24/24):

| Fixture | Gate verdict | Harm shown |
|---|---|---|
| TRUNCATE granted to runtime | FAIL `RLS_RUNTIME_ROLE_ELEVATED TABLE_PRIVILEGE:TRUNCATE` | runtime TRUNCATE drops other tenant 3→0 |
| TRUNCATE on a NOLOGIN group the runtime role belongs to (NOINHERIT) | FAIL same | `SET LOCAL ROLE` group then TRUNCATE → 0 |
| TRUNCATE to PUBLIC; TRIGGER; REFERENCES table-level; REFERENCES (tenant_id) column-level | FAIL `TABLE_PRIVILEGE:<p>` | gate only |
| Policy `tenant_id IS NOT NULL`; `tenant_id = tenant_id`; canonical `OR true`; canonical USING with literal-only WITH CHECK | FAIL `RLS_NOT_ENFORCED` | each leaks via `probe_cross_tenant` |
| Unclassified table via CLI; same table exempted through committed-style manifest | FAIL / PASS | — |

The predicate check pins PostgreSQL 16's deparse of
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
That binds future tenant-context design and is open for `veyro-lead`
(`R04-DESIGN-OPTIONS-FOR-VEYRO-LEAD-2026-10-02.md` D4), as is the
manifest location (D3).
