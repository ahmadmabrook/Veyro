---
doc: SLICE-6-gov01-r04-rls-permission-lint-gates
module: MOD-001
requirement: GOV-01-R04 (critical slice only — TSD §24.1 RLS lint + permission lint)
date: 2026-10-02
implemented_by: veyro-critical-engineer (Opus, claude-opus-5-5) — ADR-005 Decision 1, slice 3
mr_id: MR-MOD001-20261002-001
status: R1 BLOCKED (P1=2) -> remediated; R2 BLOCKED (P0=0/P1=2/P2=3/P3=3) -> ADR-010 D1-D5 implemented by the same critical-engineer session; PENDING fresh R3 security review and distinct fresh code review (no scenario promoted, no gate declared PASS by this session)
---

# Slice 6 — GOV-01-R04 critical slice: RLS-lint and permission-lint architecture gates

## Amendment A1 implementation (2026-10-02) — supersedes gap 1 and the D1.5 rows of the ADR-010 section below

A fresh `veyro-lead` probed this session's disclosed D1.5 gap and decided
ADR-010 **Amendment A1** (raw probe:
`evidence/security/ADR010-A1-INFORMATION-SCHEMA-PROBE-RAW-2026-10-02.txt`).
**My provisional `PINNED_INFORMATION_SCHEMA_PUBLIC` predicate was rejected**:
it was class-level, not per-object, and did not check that the object was
stock. It produced measured false PASSes. H1/H3 (a new view/table in
`information_schema` with PUBLIC SELECT) leaked 3 cross-tenant rows, and
H10 (PUBLIC SELECT on stock `_pg_user_mappings`) also passed. The earlier
statement in this record that "anything else on information_schema is still
SYSTEM_ACL_MODIFIED" was **incorrect** and is withdrawn. A1 also found a
gap in ADR-010's own D1 definition: new SECURITY DEFINER functions in
`pg_catalog`/`information_schema` passed (H7/H8).

Implemented, same retained session, ADR-010 in-scope files only:

- **A1.2 system object** = non-temp `pg_*`/`information_schema` namespace
  AND oid < 16384, OR a `pg_init_privs` row. Any other object in those
  namespaces with a G privilege is `RLS_RUNTIME_ROLE_ELEVATED
  NON_STOCK_SYSTEM_OBJECT:<class>:<id>:<priv>@<grantee>`, with no
  allow-table and no manifest escape. Temp namespaces
  (`^pg_(toast_)?temp_[0-9]+$`) are never system. The SECURITY DEFINER
  query uses the same definition.
- **A1.3 D1.5a exact pin** `PINNED_INFORMATION_SCHEMA_SELECT[16]`: 62
  relation names, each with its class (59 views + 3 tables), plus schema
  USAGE. It applies only to system objects with no `pg_init_privs` row,
  PUBLIC grantee, relation-level SELECT, and the matching class. The
  constant was generated from A1.3's own list, and a Colima test asserts
  it equals the live pristine PG16 catalog (62/62, no other PUBLIC
  privilege, 0 init-privs rows).

| A1 case | Proof (approved Colima PG16 unless "unit") |
|---|---|
| N27 H1 new view, PUBLIC SELECT | FAIL `NON_STOCK_SYSTEM_OBJECT:view:information_schema.zz_leak:SELECT@PUBLIC`; runtime reads (own 2, other 3) |
| N28 H3 new table, PUBLIC SELECT | FAIL `NON_STOCK_SYSTEM_OBJECT:table:…`; runtime reads (2, 3) |
| N29 H10 `_pg_user_mappings`; `sql_parts` | FAIL `SYSTEM_ACL_MODIFIED:…:SELECT@PUBLIC` |
| N30 H8 `pg_catalog.zz_count()` and H7 `information_schema.zz_count()` SECURITY DEFINER | FAIL `NON_STOCK_SYSTEM_OBJECT:function:…:EXECUTE@PUBLIC` + `RLS_SECURITY_DEFINER_UNREVIEWED`; runtime counts 5 via definer vs 2 directly |
| N31b (A1.7) H4 PUBLIC UPDATE `sql_features`, H5 PUBLIC CREATE on schema, H6 column PUBLIC UPDATE | FAIL `SYSTEM_ACL_MODIFIED` only (no `NON_STOCK_SYSTEM_OBJECT` emitted, asserted) |
| N31a (A1.7) H2 new view `information_schema.zz_leak` granted to runtime | FAIL `NON_STOCK_SYSTEM_OBJECT:view:information_schema.zz_leak:SELECT@veyro_runtime` only (no `SYSTEM_ACL_MODIFIED` emitted, asserted) |
| N32 pin-set mutants | unit cases (unpinned stock names, class mismatch, non-PUBLIC, other privilege, column ACL, init-privs row, unknown name, schema CREATE, a future major's predicate pinned without its info-schema set) + mutants A01-A05 all killed |
| P9 concurrent superuser session holding a temp table | PASS (temp row types judged as ordinary objects) |
| P10 revoke stock PUBLIC SELECT on `information_schema.tables` | PASS |
| P1 clean harness | PASS, zero information_schema violations |

Results (raw: `evidence/security/R04-ADR010-A1-IMPLEMENTATION-RAW-2026-10-02.txt`):

| Check | Result |
|---|---|
| Gate unit tests | 52/52 |
| Colima PG16 RLS integration tests | 68/68 |
| Full backend suite | 119/119 |
| Other tool tests | 9/9, 6/6, 3/3 |
| Mutation kill-check (78 mutants, A01-A12 for A1) | 78/78 killed on the first run, real tool SHA-256 unchanged (`34aa8461…`) |
| Ruff / mypy strict | clean / clean |
| Validators (baselines 4/4, capabilities, both manifests, skeleton, baseline binding, migration ordering, drift 8/8) | all PASS |
| Real repository | both gates ERROR exit 2 (fail closed) |

**N31 token question — resolved by `veyro-lead` in ADR-010 A1.7.** This
session had flagged that A1.5 N31 listed `SYSTEM_ACL_MODIFIED` for H2,
although A1.2 makes the new H2 view non-stock. A1.7 decided that tokens are
classification-based and exclusive. N31 is split into:

- **N31a:** H2 → `NON_STOCK_SYSTEM_OBJECT` only.
- **N31b:** H4/H5/H6 on stock objects → `SYSTEM_ACL_MODIFIED` only.

**A1.7 completion (same session).**

- **Exclusivity.** Every A1 breakage now also asserts that the other token
  family is absent: N29, N31a and N31b, plus N27/N28/N30 for
  non-stock.
- **H2 fixture.** It was renamed `zz_h2` → `zz_leak` to match A1.7's
  stated token.
- **Proof the assertions are not vacuous.** Mutant A13 makes a non-stock
  grant also emit `SYSTEM_ACL_MODIFIED`. Only the new integration
  assertions kill it.
- **Results** (raw: `evidence/security/R04-ADR010-A17-EXCLUSIVITY-RAW-2026-10-02.txt`):

  | Check | Result |
  |---|---|
  | Focused A1/A1.7 integration | 9/9 |
  | Full Colima RLS integration | 68/68 |
  | Gate unit tests | 52/52 |
  | Full backend suite | 119/119 |
  | Kill-check | 79/79, real tool unchanged (`34aa8461…`) |
  | Ruff / mypy | clean / clean |

- **Gate tool.** Unchanged by A1.7.

**Remaining gaps after A1:** items 2-6 of the list below still stand.
Gap 1 is closed by A1, pending R3 verification. R3 must verify A1
literally, including N27-N30.

## Current state (2026-10-02, ADR-010 implementation after R2) — superseded in part by the A1 section above

R2 (`evidence/security/R04-CRITICAL-SLICE-SECURITY-REVIEW-R2-2026-10-02.md`)
returned BLOCKED, P0=0/P1=2/P2=3/P3=3. `veyro-lead` then decided
`knowledge/04-Decisions/ADR-010-rls-gate-runtime-envelope-manifest-predicate.md`.
This same retained critical-engineer session (direct implementation, no
Sonnet leg) implemented ADR-010 across its in-scope files only. It was
interrupted once by the provider limit
(`R04-ADR010-PROVIDER-LIMIT-CHECKPOINT-2026-10-02.md`) and resumed. **This is
implementation evidence, not a review result: R2 stays BLOCKED until a fresh
R3 says otherwise, and SCN-004/005/010/011/067 stay unpromoted.**

| R2 finding | ADR-010 rule | Implementation | Proof (Colima PG16 unless "unit") |
|---|---|---|---|
| P1-1 REPLICATION / predefined roles / system-function EXECUTE PASSed | D1.1, D1.2, D1.5 | allow-by-construction envelope over runtime closure R (MEMBER incl. SET-only) and G=R+PUBLIC: attribute, predefined-role, and system-ACL-vs-initial checks | N1, N2, N3 (INHERIT FALSE, SET TRUE), N4 ×5 roles, N5, N6 ×3 grantees; gate verdict only, no file/program/backup path exercised |
| P1-2 schema ownership PASSed | D1.3 | `pg_shdepend` owner rows (current db + shared) plus datdba/nspowner/relowner | N7 (direct and via group), N9 sequence/function/type |
| P2-1 `pg_get_expr` under ambient search_path | D2, D4.3 | `SET search_path = pg_catalog, pg_temp` first, read back, one RR READ ONLY tx, `RESET` after; deparse pinned per major (PG16 only, else ERROR) plus policy dependency closure | N10 (hostile db default path, operator hijack, real 3-row leak), N11 (shadowed `=(text,text)` inside NULLIF), N23 (unit) |
| P2-2 materialized views / foreign tables unscanned | D4.4 | kinds r,p,v,m,f,S scanned; granted view needs `security_invoker`; granted matview must be manifest matview w/o tenant_id; granted foreign table always FAIL | N12 (real 3-row leak), N13 view + postgres_fdw foreign table, N14 |
| P2-3 state/handoff ordering | — | out of ADR-010 file scope (orchestrator) | — |
| P3 `security: null`, `{}` scheme | D5.2 | explicit `security` always validated (null → ERROR); every defined Security Scheme Object validated | N25 (unit, 15 single-fault cases each asserting its own reason) |
| P3 mutation script edited the real tool | D5.3 | temp mirror only; real tool SHA-256 asserted in `finally`, `atexit`, SIGINT/SIGTERM | N26 runs below |
| ADR-009 D2 approval recommendation | D5.1 | registry v2; non-`authenticated` entries need `approval` resolving to one live ADR/OWN naming the permission; inventory shows approval | N24 (unit) |

Other ADR-010 items: D1.4 default-deny allow-table (N8 CREATE on schema/db,
N16 PUBLIC SELECT, N20 large object + `lo_compat_privileges`, N21
TRUNCATE/TRIGGER/REFERENCES direct/PUBLIC/SET ROLE; MAINTAIN is PG17+, so
unit-only); D1.6 OUT_OF_SCOPE (N15); D1.7 tenant-context defaults (N18 role
and database); D3 fixed `backend/migrations/rls-manifest.json` v2 (empty
skeleton committed-to-worktree), `--non-tenant-manifest` removed, resolving
approvals (N22 unit, incl. CLI flag rejection); D4.1 uuid tenant_id (N17);
SECURITY DEFINER review (N19, P6). Positives P1-P6 on Colima (P1 also via the
non-privileged runtime inspector and with the caller's search_path restored),
P7/P8 unit.

Results (raw: `evidence/security/R04-ADR010-IMPLEMENTATION-RAW-2026-10-02.txt`):

| Check | Result |
|---|---|
| Gate unit (`tools/tests/test_validate_architecture_gates.py`) | 50/50 (direct runner and pytest) |
| RLS integration, approved Colima PG16 (`backend/tests/integration/test_architecture_gate_rls.py`) | 57/57, none skipped (74 breakage-parametrised result lines incl. evidence) |
| Full backend suite | 108/108 |
| Other tool tests | 9/9, 6/6, 3/3 |
| Mutation kill-check (66 mutants: R01-R37 RLS incl. every D1.1-D1.7, D2.1, D3.4, D4.3 both proofs, D4.4; P01-P29 permission incl. D5.1-D5.2) | final run 66/66 killed, real tool SHA-256 unchanged (`e01eedc1...`). First run of the new script: 64/66 — R08 (USING rule masked by WITH CHECK in every fixture) and R27 (N23 read-back case erred for an incidental reason) exposed two vacuous tests; both tests were fixed (single-clause predicate fixtures incl. a Colima USING-only read leak; reason-specific N23 assertions) before the final run |
| Ruff (gate + tests + backend) / mypy strict (backend 21 files, gate tool) | clean / clean. EXE001 resolved by making the two shebang scripts executable |
| Real repository | permission gate ERROR (no `contracts/`), RLS gate ERROR (no DSN): fail closed, no real-repo PASS claimed |

Contract defects found and fixed in this resume (not just expectations):
explicit `security: null` on `credential_exchange`/`provider_signature`
was treated as absent and PASSed (now ERROR); the N24 fixture cited an
approval absent from its synthetic root; N25 scheme negatives were
vacuous (root `session` became undefined, so they erred for the wrong
reason) and now assert their own reasons.

**Remaining gaps, disclosed for R3 / veyro-lead:**

1. **[Superseded by ADR-010 Amendment A1; see the A1 section above.]**
   PG16 has no `pg_init_privs` rows for `information_schema`. The
   interpretation first implemented here (`PINNED_INFORMATION_SCHEMA_PUBLIC`,
   class-level) was rejected by A1 because of measured false PASSes. Its
   claim that "anything else there stays `SYSTEM_ACL_MODIFIED`" was
   incorrect. It is replaced by the exact per-object pin and the A1.2
   system-object definition.
2. MAINTAIN (N21) is unit-only: the privilege does not exist on PG16.
   `lo_compat_privileges` is proven via the inspector session and via
   `pg_db_role_setting` in unit, not via `ALTER DATABASE` on Colima.
3. Synthetic permission-registry fixtures cite ADR-009 as approval because
   it names exactly those three illustrative permissions; real entries need
   their own ADR/OWN.
4. A manifest SECURITY DEFINER entry naming a non-existent function is not
   flagged (ADR-010 did not require it).
5. ADR-010's own residuals stand (one database; TEN-002/pooling;
   ALTER DEFAULT PRIVILEGES; system-ACL tightening false-FAIL), plus
   ADR-009's contract/route-parity residual. BUG-048 remains P2 OPEN.
6. No CI wiring; neither gate has a real-repo PASS.

**Next:** a fresh `veyro-security-reviewer` R3 (mr_verify-attested) per
ADR-010 "After implementation" — including a new privilege path outside the
D1.4 table — and a distinct fresh `veyro-code-reviewer`. Only those can move
SCN-004/005/010/011/067; SCN-067 stays BLOCKED.

---

*Earlier "Current state" sections (R1/ADR-009) follow as history.*

## Current state (2026-10-02, after R1 remediation and ADR-009) — supersedes the pre-R1 sections below

History, kept rather than rewritten: the first submission (13/36/64/12
results below) went to a fresh `veyro-security-reviewer`, which returned
**R1 BLOCKED, P0=0, P1=2, P2=5**
(`evidence/security/R04-CRITICAL-SLICE-SECURITY-REVIEW-R1-2026-10-02.md`).
Both P1s were real false PASSes in this session's code. `veyro-lead` then
recorded `knowledge/04-Decisions/ADR-009-permission-lint-input-contract.md`.
This same critical-engineer session (direct implementation, no Sonnet leg)
remediated R1 and implemented ADR-009 D1-D4. **Nothing below is a review
result; R1 stays BLOCKED until a fresh R2 says otherwise.**

| R1 finding | Change (`tools/validate_architecture_gates.py`) | Real negative fixture |
|---|---|---|
| P1-A runtime TRUNCATE passed | `RLS_RUNTIME_ROLE_ELEVATED TABLE_PRIVILEGE:<p>` for TRUNCATE/TRIGGER/REFERENCES (column-level via `has_any_column_privilege`; MAINTAIN on PG17+), evaluated over the runtime role, PUBLIC and every role it can `SET ROLE` to | Colima: direct TRUNCATE grant → gate FAIL, then `veyro_runtime` really truncates (other tenant 3→0); group grant reached via `SET LOCAL ROLE` → FAIL + truncate; PUBLIC TRUNCATE, TRIGGER, table and column REFERENCES → FAIL |
| P1-B 3.2 `query`/`additionalOperations`, uppercase `POST` unscanned | Superseded by ADR-009 D1: 3.1.x only; closed path-item key set; `webhooks`, `components.pathItems`, `components.callbacks`, operation `callbacks`, `$ref` path items, symlinks → ERROR | unit: each case ERROR, never PASS beside a valid GET |
| P2 tautological policies (`tenant_id IS NOT NULL`, `tenant_id = tenant_id`) passed | Every permissive policy reachable by the runtime role must equal PG16's deparse of the canonical predicate (USING and effective WITH CHECK). **Correction:** the earlier claim that `pg_depend` excluded a string literal *per clause* was false (`pg_depend` is per policy); that check is removed | Colima: 4 predicates (IS NOT NULL, self-equality, `OR true`, literal-only WITH CHECK) each → FAIL and each shown to leak through `probe_cross_tenant` |
| P2 unhashable scopes / deep JSON / duplicate keys | type checks before hashing; strict loader (`object_pairs_hook`, RecursionError) → structured ERROR | unit |
| P2 `--non-tenant-table` CLI exemptions unaudited | flag removed; `--non-tenant-manifest` committed JSON, each entry `reason` + `ADR-NNN`/`OWN-NNN` approval | unit + Colima CLI (unclassified FAIL; PASS only via manifest) |
| P2 permission contract needs `veyro-lead` | implemented ADR-009 D1-D4 literally (below) | see next table |
| P3 boolean `version`, `$` vs `fullmatch` | `type(...) is int`; `fullmatch` everywhere | unit |

ADR-009 D1-D4 as implemented (permission gate):

| ADR-009 rule | Implementation | Fixtures |
|---|---|---|
| D1.1 recursive `.json` only, `.gitkeep` ignored, symlinks ERROR | `_contract_files` | symlinked file, dir, openapi dir, registry → ERROR |
| D1.2 `openapi` = 3.1.x | `_OPENAPI_VERSION_RE` fullmatch | 3.0.3, 3.2.0, 3.1, 3.10.0, 4.0.0, `3.1.0\n`, number, null → ERROR; 3.1.0/3.1.1 PASS |
| D1.3 blind spots refused | `webhooks` (even `{}`), `components.pathItems/callbacks`, op `callbacks`, `$ref`, unknown/uppercase keys, non-`/` paths | ERROR each |
| D1.4 strict JSON | duplicate keys, deep nesting | ERROR |
| D1.5 one owner per op | `(method, template with {} params)` and `operationId` unique across all docs | `/members/{id}/profile` vs `/members/{memberId}/profile` in two files; dup operationId cross-file and in-file → ERROR |
| D2 registry | `authentication` required (closed enum, no default); non-`authenticated` needs non-blank string `justification`; exact key sets; bool version refused | 15 invalid shapes → ERROR |
| D3 `x-veyro-permission` | unchanged rules, single registered scope | existing suite |
| D4.1 `x-veyro-authentication` | missing / non-enum / case variants → violation | unit |
| D4.2 two-key match | op class must equal registry class | 3 mismatch directions → violation |
| D4.3 native `security` | authenticated: non-empty, no `{}`, defined schemes; anonymous: explicit `[]`; credential_exchange/provider_signature: explicit; undefined schemes (op → violation, root → ERROR) | root `{}`, mixed `{}`, op `[]`, no security, undefined scheme; anonymous inheriting / non-empty / `[{}]` / empty root; both non-session classes inheriting root |
| D4.4 visible inventory | `GateReport.inventory` + per-class counts, text and JSON, every run | 4-class positive PASS asserts exact inventory; CLI text shows 3 lines, JSON 3 rows |
| D5 no exemption | no skip/allowlist/exempt option exists | `--help` contains none of exempt/skip/allowlist/public/ignore (weak signal; reviewer should read the code) |

Latest real results (raw: `evidence/security/R04-ADR009-IMPLEMENTATION-RAW-2026-10-02.txt`;
R1-remediation-only run: `evidence/security/R04-R1-REMEDIATION-RAW-2026-10-02.txt`):
gate unit **57/57**; RLS integration on approved Colima **24/24**; full
backend **75/75**; other tool tests 9/9, 6/6, 3/3; mutation kill-check
**37/37** (M13-M21 target R1, M22-M37 target ADR-009); Ruff clean
(tools files keep the repo-wide EXE001 shebang/mode pattern); mypy strict
clean; baselines 4/4; capabilities 7/7; manifests MOD-000 7/7 and
MOD-001 9/9; skeleton, baseline binding, migration ordering, drift 8/8
PASS. Real repository: permission gate → ERROR exit 2 (no `contracts/`),
correct fail-closed; still no real-repo PASS for either gate.

Open design items for `veyro-lead` (not self-authorized; see
`R04-DESIGN-OPTIONS-FOR-VEYRO-LEAD-2026-10-02.md`): ADR-009 explicitly
leaves RLS out of its scope, so the RLS exemption-manifest location (D3)
and the canonical-tenant-predicate contract that binds MOD-004's tenant
context (D4) remain undecided. The tool currently enforces the most
restrictive reading of each.

Model attestation correction: the "102 turns" figure below was captured
mid-session; the complete transcript was later independently re-attested
at 128 turns and then 175 turns, 100% `claude-opus-5-5` (orchestrator,
`R04-PROVIDER-LIMIT-CHECKPOINT-2026-10-02.md`). This resumed session's
own attestation is for the orchestrator to record; self-attestation is
not claimed here.

---

*Pre-R1 record (historical, as first submitted):*

## Scope, exactly

In scope (ADR-005 Decision 1, slice 3): TSD §24.1 gate 1 (RLS lint) and
gate 4 (permission lint), each with valid and deliberate-negative fixtures.

Out of scope and not touched: the other four §24.1 gates plus the ADR-005
surface-profile gate and toolchain mode (the tool refuses them with exit 2,
`GATE_NOT_IMPLEMENTED`, never PASS); pipeline-wide CI wiring
(`.github/workflows/`, branch protection); `contracts/` creation; every
other GOV-01-R04 routine item (SAST, secret/dependency scanning, signing).

Source text (`TSD_MIRROR.md` lines 11599-11601, 11614-11615, §8.4 lines
1850-1860): "every tenant table tenant_id NOT NULL + policy + ENABLE/FORCE
RLS; runtime role cannot own/bypass. Negative isolation tests run with
production-equivalent role." / "API commands/queries declare
action/resource/scope; unregistered permission names fail build." /
permission name `<domain>.<resource>.<action>`, scope grammar
tenant|organization|brand|region|location|department|assigned_clients|self|explicit_resource.

## Routing and execution mode (EIP §4.1)

**Implemented directly by `veyro-critical-engineer` (Opus); no supervised
Sonnet leg.** Every line of both gates is load-bearing for the
anti-false-clean property (what counts as a tenant table, what counts as
elevation, what an empty scan means), so there was no routine remainder
to hand off. Runtime attestation of this implementing session:
`mr_verify.py <session fcb53847-f348-432d-b8e6-485f9dc8fe6a.jsonl> opus
veyro-critical-engineer` → PASS, 102 turns, 100% `claude-opus-5-5` (mid-session count; see correction above — complete transcript 128, later 175 turns).
This attests the implementer's tier only; it is not a review.

## What was built

| File | Purpose |
|---|---|
| `tools/validate_architecture_gates.py` | The plan's named tool (`IMPLEMENTATION.md` §1/§4). `--gate rls` and `--gate permission`; every other planned gate name exits 2. Outcomes PASS 0 / FAIL 1 / INCONCLUSIVE 2 / ERROR 2. |
| `tools/tests/test_validate_architecture_gates.py` | 36 unit tests: permission gate over real temp files; RLS verdict function over hand-built catalogs (every code reachable without a DB); CLI exit codes. |
| `backend/tests/integration/test_architecture_gate_rls.py` | 13 integration tests against the approved CAP-008 Colima Postgres, reusing the Slice-5 `access_grant` fixture and roles unchanged. |
| `evidence/implementation/r04_gate_mutation_killcheck.py` | 12-mutation kill-check (preserved copy of the script actually run). |
| `evidence/implementation/bug048_acl_restore_probe.py` | Reproduction for BUG-048 (pre-existing, found this slice). |

No dependency added (stdlib + already-qualified psycopg 3.3.6). No
`pyproject.toml`, harness, rule, agent, or settings file changed.

## Design decisions a reviewer should check

**RLS gate reads the live catalog, not migration text.** Only the catalog
says what actually exists. It classifies every ordinary/partitioned table
(partitions included) in scope: has `tenant_id` → fully checked; declared
`--non-tenant-table` → exempt; anything else → `RLS_TABLE_UNCLASSIFIED`.
So a tenant table that forgot its `tenant_id` column cannot pass as "not a
tenant table", and an exemption on a table that has `tenant_id` or does
not exist is itself a violation.

**Elevation is judged on the named runtime role, broadly.** Superuser,
BYPASSRLS, owning the table, or membership (direct or transitive, via
`pg_has_role(..., 'MEMBER')`) in the owner or in any superuser/BYPASSRLS
role → `RLS_RUNTIME_ROLE_ELEVATED`, citing role/table. Membership is
included because a member can `SET ROLE` to the owner even when
`NOINHERIT`.

**Policy check is structural, two-sided.** At least one policy must exist;
every permissive policy that can reach the runtime role (PUBLIC or a role
it is a member of) must reference `tenant_id` in USING (for
SELECT/UPDATE/DELETE/ALL) and in the effective WITH CHECK (for
INSERT/UPDATE/ALL), confirmed both by `pg_depend` (a real column
dependency, so `'tenant_id'::text` doesn't count) and by the deparsed
expression. **[Superseded and corrected after R1: `pg_depend` is
per-policy, not per-clause, so this claim was false, and tautologies
passed. Replaced by the canonical-predicate check above.]** Restrictive and unreachable policies are ignored since they
cannot widen access.

**Empty scans never pass.** Zero tenant tables in scope → INCONCLUSIVE,
`RLS_GATE_VACUOUS`; zero API operations → INCONCLUSIVE,
`PERMISSION_GATE_VACUOUS`. A named schema that doesn't exist → ERROR, not
a smaller scan. `--require-table` lets a caller pin tables that must be
present.

**The inspector needs no privilege, and gets none.** All catalog reads are
PUBLIC-readable; the integration suite runs the gate through the
non-privileged `veyro_runtime` connection and the CLI as `veyro_runtime`,
with identical verdicts. The DSN comes from `VEYRO_RLS_GATE_DSN`, never
argv; DB errors report the exception class only.

**[Superseded by ADR-009 — see the current-state table above.]**
**Permission gate input contract (new, proposed here — reviewer should
confirm).** JSON only (stdlib, no YAML dependency): OpenAPI 3.x documents
under `contracts/openapi/` (any non-`.json` file is an ERROR, not
skipped), and a registry `contracts/permissions/registry.json`
(`{"version": 1, "permissions": {"<domain>.<resource>.<action>": {"scopes":
[...]}}}`). Each operation of all eight HTTP methods must carry
`x-veyro-permission: {action, resource, scope}` with exactly those keys;
the name is `resource + "." + action`. A path-level declaration does not
cover operations; `$ref` path items are an ERROR. **There is no exemption
mechanism**, so a future public endpoint such as a health check will need
a recorded decision (`veyro-lead`) before it can pass. The registry path
and the `x-veyro-permission` key are this slice's design, not baseline text.

## Results (raw: `evidence/security/R04-RLS-PERMISSION-GATES-RAW-2026-10-02.txt`)

| Check | Result |
|---|---|
| Integration, approved Colima engine (`colima 29.5.2 Ubuntu 24.04.4 LTS`) | 13/13 passed |
| Unit (`tools/tests/test_validate_architecture_gates.py`) | 36/36 passed (also under system Python 3.14.5) |
| Full backend suite | 64/64 passed |
| Other tool tests | 9/9, 6/6, 3/3 passed |
| Mutation kill-check (12 deliberate gate weakenings) | 12/12 killed; restored file sha256 verified |
| Ruff (backend config; tools with `--line-length 100`) | clean; tools files carry the same pre-existing EXE001 shebang/mode pattern as every other `tools/*.py` |
| mypy `--strict` (backend 21 files; gate tool) | clean |
| Governance: baselines 4/4, capabilities 7/7, manifests MOD-000 7/7 + MOD-001 9/9, skeleton, baseline binding, migration ordering, drift 8/8, evidence integrity (336 files), aggregate regression 4/4 (1 N/A), `git diff --check` | all PASS |

### The SCN-MOD001-067 negative clause, executed

With RLS deliberately disabled on `harness.access_grant`, the gate returns
FAIL, exit 1, exactly one violation:
`RLS_NOT_ENFORCED harness.access_grant — ENABLE ROW LEVEL SECURITY missing`
(identical through the runtime connection). The same breakage is then
shown to be a real hole: as `veyro_runtime` (no superuser, no BYPASSRLS,
not owner), tenant A reads all 3 of tenant B's grants
(`CROSS_TENANT_READ:3`). Before the break and after restore, the gate is
PASS and the probe is clean. The permissive-`USING (true)` policy case
leaks the same way and is also caught (`RLS_NOT_ENFORCED` ×2).

### Other deliberate negatives (each exactly one named violation, then restored and re-verified PASS with runtime grants intact)

FORCE missing; policy dropped; `tenant_id` nullable
(`RLS_TENANT_ID_NULLABLE`); runtime owns table, runtime BYPASSRLS, runtime
member of owner, runtime member of a BYPASSRLS group
(`RLS_RUNTIME_ROLE_ELEVATED` with the specific reason); unclassified
table; whole-catalog scan naming the three `harness_auth` tables as
unclassified; empty schema (INCONCLUSIVE); misspelled schema (ERROR);
missing runtime role; missing required table; CLI with wrong password
(exit 2, no credential in output). Permission: missing declaration,
unregistered name, each missing field, extra key, out-of-grammar scope,
scope not registered for the permission, malformed resource, non-string
values, path-level-only declaration, all 8 methods, empty contract,
YAML/broken/Swagger-2/`$ref` inputs, 7 invalid-registry shapes.

### Real-repository invocation

`--gate permission` on this repository → ERROR exit 2 (`contracts/`
does not exist yet). That is the correct fail-closed result, not a PASS:
there are no real API operations to judge. The RLS gate has no real
database to point at yet either. **Neither gate has a real-repo PASS, and
none is claimed.** Both are proven only against synthetic fixtures.

## Defect found: BUG-048 (pre-existing, not fixed here)

The first full-suite run failed 7 Slice-5 harness tests with "permission
denied for table access_grant". Root cause, reproduced in isolation
(`bug048_acl_restore_probe.py`): `ALTER TABLE ... OWNER TO veyro_runtime`
followed by `OWNER TO veyro_schema_owner` rewrites the ACL and drops
`veyro_runtime=arwd`. My new test had that defect in its own restore
(fixed: re-grant, plus a post-restore `has_table_privilege` assertion in
every breakage). The existing Slice-5 test
`test_scn067_negative_harness_detects_broken_fixture[runtime_owns_table]`
has the identical restore and is masked only by test ordering. Filed as
`evidence/bugs/BUG-048-harness-owner-restore-drops-runtime-grant.md`,
P2, OPEN; it fails toward false failures, not false-clean evidence.

## Known limits (disclosed, not hidden)

1. ~~Structural policy check: `USING (tenant_id = x OR true)` passes the
   gate~~ — closed after R1 by the canonical-predicate check (fixtured on
   Colima). New limit instead: the predicate is pinned to PG16's deparse
   and to `app.tenant_id`; pending `veyro-lead` (options note D4).
2. Views, functions, SECURITY DEFINER paths and column grants over tenant
   tables are not inspected.
3. Permission gate proves declaration, not enforcement (IAM-002's
   runtime half), and not that the contract matches served routes.
4. No CI wiring, so nothing yet makes either gate blocking. That is
   pipeline work outside this slice.
5. The gate's identification of "tenant table" keys on a column literally
   named `tenant_id`, which is the TSD's own wording.

## Scenario disposition (not self-promoted)

SCN-MOD001-004, -005, -010, -011 and SCN-067's gate-negative half were
executed for the first time. **All stay at their current status pending
independent fresh-context `veyro-security-reviewer` (Opus) review.**
SCN-067 remains BLOCKED until that review.

## Next independent review needed (current)

Two fresh, distinct sessions, neither this implementer nor the R1 reviewer
reusing its own context: (1) `veyro-security-reviewer` R2 — re-test both R1
P1s and the P2/P3 items, verify ADR-009 D1-D4 literally (try to PASS a
non-`authenticated` op without a matching justified registry entry; try to
scan an operation out of existence via 3.2 fields, `$ref`, `pathItems`,
callbacks, case variants, duplicate documents, symlinks; confirm the
inventory on PASS; confirm no exemption path), re-run the 37-mutation
kill-check, and judge ADR-009 gaps; (2) independent `veyro-code-reviewer`.
Only those reviews can move SCN-004/005/010/011/067.

*Original request (historical):* Fresh-context `veyro-security-reviewer` (Opus, no participation in this
slice), with `mr_verify.py` attestation, covering: (a) both gates'
fail-closed logic and the 4 design decisions above; (b) reproduction of
the SCN-067 gate-negative and leak proof on the approved Colima binding;
(c) the 12-mutation kill-check; (d) the proposed permission input
contract; (e) BUG-048 triage. Only that review can move SCN-004/005/010/
011/067.
