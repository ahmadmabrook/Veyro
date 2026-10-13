---
doc: ADR-010
status: DECIDED (2026-10-02) — conforming to the governing baseline; no owner approval required (see "Conformance and owner-reserved determination")
date: 2026-10-02
decided_by: veyro-lead (fresh Opus architecture-decision session, claude-opus-5-5; not the Slice-6 implementer, not the R1/R2 reviewer; approves no gate, scenario or code)
model_attestation: mr_verify.py PASS on complete transcript 21d8bbd9-2370-4576-a6e9-eb63f1b6293d.jsonl, tier opus, agent veyro-lead; 40 turns, 100% claude-opus-5-5 (orchestrator independent run)
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 1 RLS lint and gate 4 permission lint; ADR-005 Decision 1 slice 3)
amends: ADR-009 (D2 registry, D4.3 native `security` consistency) — see D5; ADR-009 is otherwise unchanged
requested_by: knowledge/03-Modules/MOD-001/evidence/security/R04-CRITICAL-SLICE-SECURITY-REVIEW-R2-2026-10-02.md (P1-1, P1-2, P2-1, P2-2, P3); knowledge/03-Modules/MOD-001/evidence/implementation/R04-DESIGN-OPTIONS-FOR-VEYRO-LEAD-2026-10-02.md (D3, D4)
baseline_check: verify_baselines.py PASS 4/4 and independent raw shasum 4/4 match PROJECT_INDEX.md; 4 identity strings present (this session, before decision)
amended: 2026-10-02 Amendment A1 (D1 system-object definition + D1.5a PG16 information_schema exact pin; append-only, see end of file; separate fresh veyro-lead session; original text above unchanged); 2026-10-03 Amendment A2 (R3 dispositions: pg_init_privs no longer confers system status + extension-capture token, unconditional SECURITY DEFINER review, stock-trusted-language/aggregate-component rule, rewrite-rule ban, function proconfig tenant context, token-bounded approvals; append-only; fresh veyro-lead session; mr_verify PASS 20 turns 100% claude-opus-5-5; D1–D5, A1, A1.7 unchanged)
---

# ADR-010: RLS gate — allow-by-construction runtime-role envelope, committed RLS manifest with resolving approvals, canonical tenant predicate under a pinned catalog view, and ADR-009 strictness amendments

## Context

R2 (fresh, attested Opus) returned BLOCKED P0=0/P1=2/P2=3/P3=3 against the
post-R1 RLS gate. Every blocking finding has one shape: **the gate enumerates
known-bad powers, and the reviewer found a power it did not enumerate.**

- P1-1: `veyro_runtime` with `REPLICATION` (real `pg_basebackup` copied
  tenant B's heap); membership in `pg_execute_server_program`; a direct
  `GRANT EXECUTE` on `pg_read_binary_file(text)`. All PASSed.
- P1-2: `ALTER SCHEMA harness OWNER TO veyro_runtime` PASSed; the runtime
  role then dropped `harness.access_grant`.
- P2-1: `pg_get_expr` deparsed under the inspector's ambient
  `search_path`; a `public.=` operator made a tautological policy match the
  canonical string.
- P2-2: the `relkind IN ('r','p')` scan missed a granted materialized view
  exposing 3 cross-tenant rows.

R1 found the same shape (TRUNCATE). Two rounds of "add the newly found
privilege to the deny list" is the pattern this project already resolved
once for the Bash guard (MOD-000 chunk 21: v1 deny-list superseded by v2
allow-by-construction). This ADR applies the same remedy here.

### Baseline constraints (verified this session in `TSD_MIRROR.md` / `EIP_MIRROR.md`)

- TSD §24.1 gate 1: "every tenant table tenant_id NOT NULL + policy +
  ENABLE/FORCE RLS; runtime role cannot own/bypass. Negative isolation
  tests run with production-equivalent role."
- TSD §7.3 role model: runtime roles are "LOGIN, NOSUPERUSER, NOCREATEDB,
  NOCREATEROLE and NOBYPASSRLS; they do not own tenant tables." Table rule:
  "tenant_id UUID NOT NULL, ENABLE … FORCE ROW LEVEL SECURITY. No tenant
  table is granted to PUBLIC." Policy rule: compare tenant_id to a
  transaction-local value "(for example
  current_setting('app.tenant_id', true)::uuid)"; "Missing/invalid context
  fails closed". Pooling rule: `SET LOCAL app.tenant_id`. CI lint "rejects
  SECURITY DEFINER functions unless explicitly reviewed."
- TSD ADR-002 (Accepted): runtime roles "non-owner, NOBYPASSRLS and never
  superuser"; "CI blocks non-compliant migrations."
- TSD TEN-001: platform-global records are "explicitly marked
  platform_scope"; §7.3 table: "explicit platform_scope tables".
- TSD critical controls: "Default deny and least privilege are mandatory."
- EIP RLS gate detail: non-owner NOBYPASSRLS runtime roles; transaction-local
  `SET LOCAL app.tenant_id`; fail-closed missing/invalid context; explicit
  review of SECURITY DEFINER functions.

Everything below is an implementation contract inside those constraints.
The baseline fixes *what* must hold; it does not fix how the gate proves
it. That is a veyro-lead call (ADR-005 Decision 1; ADR-009 precedent).

### Not re-adjudicated

R1 dispositions, ADR-009 D1/D3, and D4.1/D4.2/D4.4 stand. The R1
remediation (TRUNCATE/TRIGGER/REFERENCES/MAINTAIN, canonical predicate
exact-match, committed manifest, strict parsers) is retained and absorbed
into the envelope below, not replaced.

---

## Decision

### D1 — Runtime-role posture: allow-by-construction envelope (decides R2 P1-1, P1-2)

The gate stops asking "does the runtime role hold one of these bad powers?"
and asks "**is everything the runtime role can exercise inside this
explicit envelope?**" Anything not listed is a violation. Missing catalog
read access, or any query error, is ERROR, never an empty result.

**Definitions.**

- *Runtime closure* `R` = the `--runtime-role` plus every role `m` with
  `pg_has_role(runtime, m, 'MEMBER')`. MEMBER is used, not USAGE, because
  NOINHERIT and PG16 `INHERIT FALSE` grants still allow `SET ROLE`.
- *Grantee set* `G` = `R ∪ {PUBLIC}` (ACL grantee oid 0).
- *System object* = any object in a `pg_*` schema or `information_schema`,
  plus any object with a `pg_init_privs` row.
- *Scope*: the envelope is evaluated over the **whole connected database**
  and cluster-shared role/database catalogs, irrespective of `--schema`.
  `--schema` only limits which relations are classified as tenant or
  platform tables (D1.6 closes the gap that opens).

**D1.1 Role attributes.** For every role in `R`: `rolsuper`,
`rolbypassrls`, `rolreplication`, `rolcreaterole`, `rolcreatedb` are all
false. The first four are named by TSD §7.3/ADR-002. `REPLICATION` is
included as a direct "bypass" under §24.1, which R2 demonstrated with a
real physical copy.

**D1.2 No predefined roles.** `R` contains no role with oid < 16384
(`FirstNormalObjectId`) and no role named `pg_*`. This covers every
predefined role, including file-access, read/write-all-data, monitor and
signal roles, without enumerating them. It also covers `pg_database_owner`,
so implicit membership through database ownership is caught. A future
runtime need for any predefined role requires a superseding ADR, and in
practice a separate non-runtime role.

**D1.3 Owns nothing.** No role in `R` owns any object in the connected
database or any shared object it depends on. The primary check is
`pg_shdepend` rows with `deptype = 'o'`, `refobjid ∈ R`, and
`dbid ∈ {current database, 0}`. This is the generic owner record behind
`DROP OWNED`, and it covers schemas, relations of every kind, functions,
types, sequences, large objects, publications and the database itself.
Explicit belt-and-braces checks on `pg_database.datdba`,
`pg_namespace.nspowner` and `pg_class.relowner` must agree with it. They
are named because P1-2 was schema ownership. This subsumes the existing
`OWNS_TABLE` and `MEMBER_OF_OWNER` checks.

**D1.4 Privilege allow-table for non-system objects.** Enumerate every
ACL-bearing catalog. Use `aclexplode(coalesce(<acl>, acldefault(<type>,
<owner>)))` so implicit defaults are included, and include column ACLs from
`pg_attribute.attacl`. Every entry whose grantee is in `G` must match a row
of this table. Any privilege not allowed in its row is a violation:

| Object class | Allowed for `G` | Conditions |
|---|---|---|
| Connected database | CONNECT, TEMPORARY | CREATE forbidden |
| Schema | USAGE | CREATE forbidden on every schema |
| Tenant table / partition (D4.1) | SELECT, INSERT, UPDATE, DELETE (table or column level) | Grantee ≠ PUBLIC (TSD §7.3) |
| Platform-scope table (D3 manifest, kind `table`) | SELECT, INSERT, UPDATE, DELETE | Grantee ≠ PUBLIC |
| View | SELECT, INSERT, UPDATE, DELETE | `security_invoker=true` in `reloptions`; grantee ≠ PUBLIC (D4.4) |
| Materialized view | SELECT | Only if listed in the manifest as kind `matview` and it has no `tenant_id` column (D4.4) |
| Foreign table | none | No manifest escape (D4.4) |
| Sequence | USAGE, SELECT, UPDATE | Grantee ≠ PUBLIC |
| Function / procedure | EXECUTE | Not `prosecdef`, unless listed in the manifest's reviewed SECURITY DEFINER section (TSD §7.3) |
| Type / domain | USAGE | — |
| Language | USAGE | — (Postgres refuses USAGE grants on untrusted languages) |
| Large object | none | `lo_compat_privileges` must be `off` |
| FDW, foreign server, tablespace, parameter (`pg_parameter_acl`) | none | — |
| Any other ACL-bearing class | none | Default deny |

TRUNCATE, TRIGGER, REFERENCES and MAINTAIN are therefore forbidden
everywhere by construction. The R1 remediation becomes a special case.

**D1.5 System ACLs unmodified.** For every system object, the privileges
granted to `G` must be a subset of the object's initial ACL. The initial
ACL is `pg_init_privs.initprivs` where a row exists, and
`acldefault(<type>, <owner>)` otherwise. Any extra entry is a violation,
whether granted to the runtime role, a member role, or PUBLIC. This catches
`GRANT EXECUTE ON FUNCTION pg_read_binary_file(text)`, and every sibling of
it, without listing functions. Ordinary PUBLIC-default system functions,
such as `lower`, are unaffected. A deliberate tightening, such as revoking
a PUBLIC default, can produce a false FAIL. That is a fail-closed outcome
and is accepted.

**D1.6 No out-of-scope reach.** Every non-system relation on which `G`
holds any privilege must be inside the scanned schemas. With no `--schema`,
all non-system schemas are scanned. Otherwise the result is a violation.
`--schema` can no longer hide a granted relation.

**D1.7 Tenant context cannot be defaulted.** No `pg_db_role_setting` entry
that applies to `G` may set any `app.*` parameter. Such an entry has
`setrole ∈ R ∪ {0}` and `setdatabase ∈ {current database, 0}`. The
inspecting session's `current_setting('app.tenant_id', true)`, read before
the gate sets anything, must be NULL or empty. This is TSD §7.3 "missing
context fails closed": a persisted default tenant would turn "no `SET
LOCAL`" into a silent read of one tenant.

**What remains legitimate** (positive cases must prove it):

- LOGIN;
- CONNECT/TEMP on its database;
- USAGE on application schemas;
- DML on tenant tables, filtered by RLS;
- DML on approved platform tables;
- DML through `security_invoker` views;
- sequence use;
- EXECUTE on non-definer application functions and default system
  functions;
- membership in non-predefined NOLOGIN group roles, all of whose attributes
  and grants are themselves judged by D1.1-D1.7 through `R`.

The harness's `provision_roles()` runtime role (NOSUPERUSER, NOBYPASSRLS,
NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOINHERIT) is already inside the
envelope.

**Violation codes.** All D1 breaches are `RLS_RUNTIME_ROLE_ELEVATED`,
subject `<runtime>/<object identity>`, with a machine-stable detail token:

- `ATTRIBUTE:<ATTR>@<role>`
- `PREDEFINED_ROLE:<role>`
- `OWNS:<class>:<identity>`
- `PRIVILEGE:<class>:<identity>:<priv>@<grantee>`
- `SYSTEM_ACL_MODIFIED:<identity>:<priv>@<grantee>`
- `OUT_OF_SCOPE:<identity>`
- `TENANT_CONTEXT_DEFAULT:<source>`

Unreviewed SECURITY DEFINER functions are `RLS_SECURITY_DEFINER_UNREVIEWED`.
The existing code names in `IMPLEMENTATION.md` §4 are kept.

### D2 — Inspector session discipline (decides R2 P2-1, mechanism)

1. The first statement on the gate connection is
   `SET search_path = pg_catalog, pg_temp`. The gate then reads back
   `current_setting('search_path')`. If it is not exactly that value, the
   result is ERROR `RLS_GATE_INPUT_INVALID`. Nothing, including the server
   version query, runs before the pin.
2. All collection runs in one `BEGIN ISOLATION LEVEL REPEATABLE READ READ
   ONLY` transaction. That gives one consistent catalog snapshot, and the
   gate never writes.
3. All gate SQL schema-qualifies catalog objects (`pg_catalog.pg_class`,
   and so on) as defence in depth.
4. Any catalog that is unreadable to the inspector is ERROR, never treated
   as empty.

### D3 — Canonical RLS manifest (decides open D3)

1. **Path (fixed): `backend/migrations/rls-manifest.json`.**
   - TSD §7.3 calls this the "CI migration lint", so the manifest belongs
     with the migrations. A platform table's classification must land in
     the same diff as the migration that creates it.
   - No client consumes it, so it is not a `contracts/` artifact.
   - It does not collide with the Slice-4 validator, which reads only
     `backend/migrations/records/*.yaml`.
2. **The CLI has no manifest-path flag.** `--non-tenant-manifest` is
   removed. The gate always reads the fixed path relative to the
   repository root.
   - A missing file is ERROR.
   - A symlink is ERROR.
   - Parsing uses ADR-009's strict JSON loader, so duplicate keys and
     over-deep nesting are ERROR.
   - Tests may inject a parsed manifest and a resolver root only through
     the Python API. No CI command line can substitute a manifest.
3. **Schema, version 2.** Version 1 is refused, so an in-flight v1 fixture
   cannot be silently reinterpreted:
   ```json
   {
     "version": 2,
     "platform_scope_relations": {
       "<schema>.<relation>": {"kind": "table" | "matview", "reason": "<non-empty>", "approval": "ADR-NNN" | "OWN-NNN"}
     },
     "reviewed_security_definer_functions": {
       "<regprocedure text under the D2 search_path>": {"reason": "<non-empty>", "approval": "ADR-NNN" | "OWN-NNN"}
     }
   }
   ```
   Key sets are exact. Relation names fully match the existing `_TABLE_RE`.
   A function key must equal `p.oid::regprocedure::text` as rendered under
   the pinned `search_path`, so it is schema-qualified.
4. **Approval references must resolve. Unresolved is ERROR
   `RLS_GATE_INPUT_INVALID`.** The resolver reads only the repository:
   - `ADR-NNN`: exactly one file matches
     `knowledge/04-Decisions/ADR-NNN-*.md`. Its front-matter `status:`
     begins with `DECIDED` or `ACCEPTED`, and the file contains the entry's
     exact key string.
   - `OWN-NNN`: exactly one table row in
     `knowledge/00-System/OWNER_APPROVALS.md` begins `| OWN-NNN |`, and
     that row contains the entry's exact key string.

   This stops citing an unrelated or superseded record.
5. **Entry semantics.** Existing rules stay: an entry naming a missing
   relation, or a relation that has `tenant_id`, is
   `RLS_EXEMPTION_INVALID`. New: an entry whose `kind` does not match the
   actual `relkind` is also `RLS_EXEMPTION_INVALID`.
6. **Who approves.** Marking a relation `platform_scope` (TSD TEN-001) is
   an architecture classification, so an ADR suffices. It needs an OWN
   record only if the owning module's ADR determines that DC-16 applies.
   MOD-001 commits only the empty skeleton:
   `{"version": 2, "platform_scope_relations": {}, "reviewed_security_definer_functions": {}}`.
   Real entries belong to the modules that create the relations.

### D4 — Canonical tenant predicate contract and relation kinds (decides open D4, R2 P2-1, P2-2)

1. **Tenant table.** A tenant table is a relation of kind `r` or `p` with a
   `tenant_id` column. That column must be `uuid` (new violation
   `RLS_TENANT_ID_NOT_UUID`, per TSD §7.3 "tenant_id UUID") and NOT NULL.
   ENABLE, FORCE, the policy checks and the no-PUBLIC rule all apply to
   every partition and every parent.
2. **GUC and predicate (binding on MOD-004 TEN-002 and every later
   module).**
   - The tenant-context GUC is `app.tenant_id`, the name the TSD §7.3 and
     EIP text use.
   - The canonical source predicate is
     `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
     This is TSD §7.3's example, hardened so that an empty or reset GUC
     yields NULL and therefore no rows. The bare `''::uuid` would raise an
     error instead.
   - Every permissive policy reachable by `G` must use this predicate.
     "Reachable" means `polroles` contains 0 or any member of `R`. USING is
     checked for commands `*`, `r`, `w` and `d`. The effective WITH CHECK
     (falling back to USING when absent) is checked for `*`, `a` and `w`.
   - Additional narrowing goes in RESTRICTIVE policies, which the
     predicate rule does not judge. D1.4 and D3 govern any functions they
     call.
3. **Two independent proofs, both required:**
   - **Deparse match:** `pg_get_expr` output, taken under the D2-pinned
     `search_path`, equals the constant pinned for the server's major
     version. Only PG16 is pinned (CAP-008 binding), using today's
     `CANONICAL_TENANT_PREDICATE`. An unpinned major is ERROR
     `RLS_GATE_INPUT_INVALID`, never FAIL and never PASS. Pinning a new
     major needs raw evidence that the constant is that server's own
     deparse of the identical source predicate, plus independent security
     review. It does not need a new ADR.
   - **Dependency closure:** every `pg_depend` row with
     `classid = 'pg_policy'::regclass` and `objid = <policy oid>` must
     reference only the policy's own relation. Any other referenced object
     is `RLS_NOT_ENFORCED`. That includes a non-system operator, function,
     type, collation or relation. All components of the canonical
     predicate are pinned system objects, so they record no dependency.
     This closes hijacks invisible in deparse, such as a shadowed `=`
     inside `NULLIF`.
4. **Relation kinds scanned: `r`, `p`, `v`, `m`, `f`, `S`.**

   | Kind | Rule |
   |---|---|
   | `r`/`p` | Classified as tenant (D4.1) or manifest `table`; otherwise `RLS_TABLE_UNCLASSIFIED` |
   | `v` view | If `G` holds any privilege: `security_invoker=true` is required, so RLS evaluates as the runtime role. Otherwise `RLS_NOT_ENFORCED`. Views cannot be manifest entries. |
   | `m` materialized view | Materialized views cannot carry RLS. If `G` holds any privilege: it must be a manifest `matview` without `tenant_id`; otherwise `RLS_NOT_ENFORCED` |
   | `f` foreign table | If `G` holds any privilege: always `RLS_NOT_ENFORCED`. No manifest escape. Admitting foreign tables needs a superseding ADR. |
   | `S` sequence | Allow-table only (D1.4) |

   Ungranted views, materialized views and foreign tables are not
   violations. With the D1 envelope, unreachable relations are not an
   isolation risk to the runtime role. Who owns them, and the owner's
   powers, are the migration role's concern.

### D5 — ADR-009 amendments (decides item 4; R2 D2 recommendation and P3s)

**D5.1 Approval references are required for non-`authenticated` registry
entries.** This amends ADR-009 D2:

- A registry entry whose `authentication` is not `authenticated` has
  exactly the keys `{scopes, authentication, justification, approval}`.
- `approval` is `ADR-NNN` or `OWN-NNN`. It is resolved by the D3.4
  resolver, and the resolved record must contain the exact permission name.
- `authenticated` entries stay exactly `{scopes, authentication}`, and an
  `approval` key there is ERROR.
- The registry `version` becomes 2. Version 1 is refused. No real registry
  has been committed, so only fixtures change.
- The non-`authenticated` inventory gains an `approval` field in both text
  and JSON output.
- Governance rule, not a gate rule: an ADR that authorises an `anonymous`
  operation which returns tenant or member data is a product decision under
  DC-16, so it must cite or be accompanied by an OWN record. The gate checks
  resolution, not semantics.

**D5.2 Native OpenAPI `security` strictness is mandated.** This amends
ADR-009 D4.3. Each case below is ERROR `PERMISSION_GATE_INPUT_INVALID`:

- A `security` value, at root or operation level, that is not a JSON array
  of objects. This includes `null`.
- A requirement object whose values are not arrays of strings.
- A requirement naming a scheme absent from `components.securitySchemes`.
- For `credential_exchange` and `provider_signature`, a missing `security`
  key. "Explicit" means present with an array value, possibly `[]`; `null`
  is never explicit.
- Any entry in `components.securitySchemes` that is not a valid Security
  Scheme Object. That covers `$ref`, `{}`, and a `type` outside `apiKey`,
  `http`, `mutualTLS`, `oauth2` or `openIdConnect`. It also covers a scheme
  missing its type's required fields:
  - `apiKey`: `name` and `in` ∈ {query, header, cookie};
  - `http`: a non-empty `scheme`;
  - `oauth2`: a non-empty `flows` object;
  - `openIdConnect`: a non-empty `openIdConnectUrl`.

  Every defined scheme is validated, not only the ones referenced.

**D5.3 Mutation kill-check hygiene (P3).** `r04_gate_mutation_killcheck.py`
mutates a temporary copy only. It must assert that the real
`tools/validate_architecture_gates.py` has the same SHA-256 before and after
the run, and the assert must hold even if the run fails or is interrupted.
A run that cannot prove this is invalid evidence.

---

## Acceptance criteria

Catalog-dependent cases run as integration tests against the approved
CAP-008 Colima PostgreSQL 16 binding. Pure-verdict cases run as unit tests.
Each negative must produce the stated outcome and violation code or token,
and must not produce PASS. Where R2 demonstrated a real leak, the fixture
asserts that leak behaviourally as well, so the negative is proven
meaningful.

### Negative (must FAIL unless ERROR is stated)

| # | Fixture | Expected |
|---|---|---|
| N1 | Runtime `REPLICATION` | `ATTRIBUTE:REPLICATION@veyro_runtime` |
| N2 | Runtime `CREATEROLE`; separately `CREATEDB` | `ATTRIBUTE:` token for each |
| N3 | NOLOGIN group role with `BYPASSRLS` (and separately `REPLICATION`) granted to runtime with `INHERIT FALSE, SET TRUE` | `ATTRIBUTE:…@<group>` |
| N4 | Runtime member of `pg_execute_server_program` with SET only (R2 case); parametrise over `pg_read_server_files`, `pg_write_server_files`, `pg_read_all_data`, `pg_write_all_data` | `PREDEFINED_ROLE:` token per role |
| N5 | Runtime owns the connected database | `PREDEFINED_ROLE:pg_database_owner` and `OWNS:database:…` |
| N6 | `GRANT EXECUTE ON FUNCTION pg_read_binary_file(text)` to runtime (R2 case); again to PUBLIC; again to a group role runtime belongs to | `SYSTEM_ACL_MODIFIED:` token in each case |
| N7 | `ALTER SCHEMA harness OWNER TO veyro_runtime` (R2 case); again to a group role runtime belongs to | `OWNS:schema:harness` |
| N8 | `GRANT CREATE ON SCHEMA harness`; separately `GRANT CREATE ON DATABASE` | `PRIVILEGE:…:CREATE@…` |
| N9 | Runtime owns an unrelated sequence, function or type in another schema | `OWNS:` via `pg_shdepend` |
| N10 | R2 P2-1 reproduction: `public.=` operator, `ALTER DATABASE … SET search_path = public, pg_catalog`, tautological policy. Behavioural: runtime reads cross-tenant rows | `RLS_NOT_ENFORCED` from deparse mismatch and dependency closure |
| N11 | Policy textually canonical, created while a non-system `=(text,text)` shadowed the system operator | `RLS_NOT_ENFORCED` from dependency closure |
| N12 | R2 P2-2 reproduction: materialized view over `access_grant` granted SELECT to runtime. Behavioural: 3 cross-tenant rows | `RLS_NOT_ENFORCED` |
| N13 | View over `access_grant` without `security_invoker`, granted; separately a granted foreign table | `RLS_NOT_ENFORCED` |
| N14 | Manifest lists a materialized view that has `tenant_id`; manifest `kind` mismatches `relkind` | `RLS_EXEMPTION_INVALID` |
| N15 | Granted table in a schema excluded by `--schema` | `OUT_OF_SCOPE:` |
| N16 | `GRANT SELECT ON harness.access_grant TO PUBLIC` | `PRIVILEGE:…@PUBLIC` |
| N17 | Tenant table with `tenant_id text NOT NULL` | `RLS_TENANT_ID_NOT_UUID` |
| N18 | `ALTER ROLE veyro_runtime SET app.tenant_id = '<uuid>'`; separately `ALTER DATABASE … SET app.tenant_id` | `TENANT_CONTEXT_DEFAULT:` |
| N19 | SECURITY DEFINER function in an application schema, executable by runtime through the PUBLIC default, not in the manifest | `RLS_SECURITY_DEFINER_UNREVIEWED` |
| N20 | `GRANT SELECT ON LARGE OBJECT` to runtime; separately `lo_compat_privileges = on` | `PRIVILEGE:large_object…`; ATTRIBUTE/GUC token |
| N21 | TRUNCATE, TRIGGER, REFERENCES and MAINTAIN regressions from R1 (direct, PUBLIC, via SET ROLE) | Still FAIL (envelope) |
| N22 | Manifest problems: missing file; symlink; `version: 1`; duplicate key; `ADR-999`; an ADR that exists but does not contain the key; an ADR whose status is not DECIDED/ACCEPTED; an OWN row lacking the key; `--non-tenant-manifest` passed on the CLI | **ERROR** (`argparse` rejection for the removed flag) |
| N23 | Unpinned server major injected into the verdict (`170000`, `180000`); search_path read-back mismatch from an injected connection; an unreadable catalog | **ERROR** |
| N24 | Permission gate: non-`authenticated` entry without `approval`; with an unresolvable `approval`; with an `approval` record lacking the permission name; `approval` on an `authenticated` entry; registry `version: 1` | **ERROR** |
| N25 | Permission gate: `security: null` on `credential_exchange`/`provider_signature` (R2 P3); `authenticated` referencing a scheme defined as `{}` (R2 P3); scheme `$ref`; unknown `type`; `apiKey` missing `in`; requirement value not an array | **ERROR** |
| N26 | Mutation kill-check: at least one mutant per D1.1-D1.7, D2.1, D3.4, D4.3 (both proofs), D4.4 and D5.1-D5.2 rule is killed | All killed; the real tool's SHA-256 is unchanged |

### Positive (must PASS)

| # | Fixture | Expected |
|---|---|---|
| P1 | The canonical harness. Runtime as provisioned by `provision_roles()`, `access_grant` as created by `create_tenant_table()`, scan covering every schema where runtime holds grants, and a resolving empty-or-fixture manifest | PASS. The tenant table is listed in `checked`. |
| P2 | DML granted only to a clean NOLOGIN group role, which is granted to runtime (inheritance proof) | PASS. Behavioural: runtime still sees only its own tenant. |
| P3 | `security_invoker=true` view over `access_grant` granted to runtime | PASS. Behavioural: own-tenant rows only. |
| P4 | Manifest-listed platform table (no `tenant_id`) with DML grant, approval resolving to a fixture ADR in an injected resolver root | PASS |
| P5 | Sequence USAGE/SELECT/UPDATE granted | PASS |
| P6 | SECURITY DEFINER function listed in the manifest with a resolving approval | PASS. Proves the escape is explicit and visible. |
| P7 | Permission gate: one operation per class, each non-`authenticated` one with a resolving approval and well-formed schemes | PASS. Inventory lists the three non-`authenticated` operations with their `approval`. |
| P8 | Existing ADR-009 positive and negative permission fixtures, updated to registry v2 | Unchanged verdicts |

**Known consequence to handle, not paper over:** the authn harness grants
the runtime role access to `harness_auth.*`. Under D1.6, any RLS gate run
that narrows `--schema` to `harness` in a database that also has
`harness_auth` will FAIL `OUT_OF_SCOPE`. Integration fixtures must either
include and classify `harness_auth`, or run in a database without it.
Weakening D1.6 is not an option.

## Exact implementation scope

**In scope.** The retained `veyro-critical-engineer` implementation
session, ADR-005 Decision 1, may change only these files:

- `tools/validate_architecture_gates.py`:
  - RLS collection and verdict per D1, D2 and D4;
  - manifest v2 parser and approval resolver per D3;
  - permission registry v2 and `security` strictness per D5.1 and D5.2;
  - remove `--non-tenant-manifest`;
  - rewrite the module docstring, including the "Static limits" paragraph,
    which D4.4 now partly supersedes.
- `tools/tests/test_validate_architecture_gates.py`: unit cases N22-N25,
  P7 and P8, and pure-verdict versions of the others.
- `backend/tests/integration/test_architecture_gate_rls.py`: N1-N21 and
  P1-P6 on CAP-008 Colima PG16.
- `backend/migrations/rls-manifest.json`: new, the empty v2 skeleton (D3.6).
- `knowledge/03-Modules/MOD-001/evidence/implementation/r04_gate_mutation_killcheck.py`:
  N26 and D5.3.
- The Slice-6 evidence record, plus one new raw evidence file for this
  remediation.

**Out of scope:**

- `backend/tests/harness/*`. The role provisioning already conforms.
  BUG-048 is separate.
- CI wiring.
- The other §24.1 gates.
- `contracts/` contents.
- Scenario status, `STATUS.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`
  (the orchestrator handles R2 P2-3 separately).
- Any change to a governing baseline.

**After implementation:**

1. A **fresh** `veyro-security-reviewer` R3, mr_verify-attested, verifies
   D1-D5 literally. It must specifically attempt a new privilege path
   outside the D1.4 table, to test the "default deny" claim rather than
   only the listed cases. It reports any ADR-010 gap as a finding against
   this ADR.
2. A **distinct** fresh `veyro-code-reviewer` reviews the code.
3. Neither this ADR nor veyro-lead approves the gate, promotes SCN-004,
   SCN-005, SCN-010, SCN-011 or SCN-067, or closes BUG-048.

## Alternatives considered

| Alternative | Verdict |
|---|---|
| Extend the deny list: add REPLICATION, the four file/exec roles, `pg_read_binary_file`, `nspowner` | Rejected. It is the third round of the same pattern, and the reviewer already named related unprobed paths. The MOD-000 Bash guard history shows where this goes. |
| Allow-list the runtime role's grants against a committed expected-grants file | Rejected. It is a second source of truth to keep in sync with migrations, and it still needs D1.1-D1.5 for powers that are not grants. |
| D3 manifest under `contracts/rls/` | Rejected. It is not a consumer contract, and TSD calls this the migration lint. |
| Keep the CLI manifest flag and restrict it to tracked files | Rejected. It is complexity with no benefit over a fixed path. |
| Format-only approval regex (status quo) | Rejected. `ADR-001` would "approve" anything. |
| D4: configurable allowlist of approved predicates | Rejected. Each entry is a new tautology review, and it moves an isolation decision into config. |
| D4: drop the predicate check and rely on the behavioural harness | Rejected. R1 showed `tenant_id IS NOT NULL` passes behavioural probes that do not test that shape. |
| D4: semantic expression analysis instead of exact deparse | Rejected. It is a large parser surface in a false-PASS-sensitive gate. Exact deparse plus dependency closure is small and complete for one canonical form. |
| Disclose materialized views and foreign tables as a limitation (R2's alternative) | Rejected. Under the envelope, fixing them costs one allow-table row each. |

## Conformance and owner-reserved determination

Conforms to Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1:

- Every rule tightens enforcement of TSD §7.3, §24.1, TSD ADR-002, TEN-001
  and the EIP RLS gate detail.
- The GUC name and predicate shape are the TSD's own, hardened only so that
  an empty context fails closed.
- No TSD grammar, API style, product feature, module scope or routing
  changes. ADR-005 and ADR-009 D1/D3 are unchanged.
- No spend, no real data, no Production action.

**No owner approval is required, and no owner-stop condition exists
today.**

**These future proposals are owner-reserved stops** under DC-16 /
`owner-reserved-restrictions.md`. Each would weaken the TSD ADR-002
"Accepted" control or a product boundary:

1. Any runtime role holding superuser, BYPASSRLS, REPLICATION, ownership,
   or a predefined role.
2. Removing FORCE RLS.
3. An `anonymous` operation returning tenant or member data (D5.1).
4. Storing tenant data outside the shared-PostgreSQL RLS model, for
   example foreign tables or a cross-database layout.

These are **superseding-ADR matters only, not owner matters**: pinning a
new PostgreSQL major's deparse, and admitting a materialized view or a
SECURITY DEFINER function through the manifest with a resolving ADR.

## Residual risk, disclosed

- The gate inspects one database. Other databases in the cluster,
  `pg_hba`, OS-level access, and a superuser-controlled server are outside
  SQL-catalog proof.
- Runtime correctness of `SET LOCAL` use, pooled-connection tenant
  switching, and TEN-002 resolution remains the behavioural harness's and
  MOD-004's job.
- `ALTER DEFAULT PRIVILEGES` entries are not judged as such. Their effect
  is caught when the object they grant on exists, and CI runs the gate
  after migrations.
- D1.5 can false-FAIL on a deliberate tightening of a system ACL. That is
  fail-closed and accepted.

---

## Amendment A1 (2026-10-02): system-object definition and the PG16 `information_schema` initial ACL

**Decided by:** a separate fresh `veyro-lead` architecture-decision session
(Opus, `claude-opus-5-5`). It did not author the original ADR-010, the
Slice-6 implementation, or R1/R2. It approves no gate, code or scenario.
Model attestation of this session's transcript is for the orchestrator to
run with `mr_verify.py`. This session did not self-attest.

**Status:** DECIDED. It conforms to the governing baseline, and no owner
approval is required. The original D1-D5 text above is unchanged.
Everything in A1 tightens the gate; nothing in it relaxes one.

**Raw evidence:**
`knowledge/03-Modules/MOD-001/evidence/security/ADR010-A1-INFORMATION-SCHEMA-PROBE-RAW-2026-10-02.txt`.
Probe conditions:

- Target: approved CAP-008 Colima binding, `postgres:16-alpine` at the
  pinned digest, `server_version_num` 160015.
- Fixture: the project harness (`disposable_postgres`, `provision_roles`,
  `create_tenant_table`).
- Tool under test: unmodified `tools/validate_architecture_gates.py`,
  sha256 `e01eedc1…`, the same file the Slice-6 record describes.
- Baselines: `verify_baselines.py` PASS 4/4 in the same session.

### A1.0 What was asked

The Slice-6 implementation reported a problem with D1.5. Read literally,
D1.5 flags every clean PostgreSQL 16 database, because stock
`information_schema` PUBLIC grants have no `pg_init_privs` rows. The
implementation therefore added `PINNED_INFORMATION_SCHEMA_PUBLIC`. That
constant treats a PUBLIC grant inside `information_schema` as initial if
the class/privilege pair is `(schema, USAGE)`, `(table, SELECT)` or
`(view, SELECT)`. The implementation recorded it as an ADR gap for
veyro-lead.

### A1.1 Catalog facts, measured (not assumed)

**F1. The literal-D1.5 false FAIL is real.**

- A pristine PG16 database has **0** `pg_init_privs` rows for any
  `information_schema` namespace, relation, function or type.
- Rows exist for other objects: `pg_class` 156, `pg_namespace` 2,
  `pg_proc` 62.
- initdb loads `information_schema` after it records initial privileges.
- With the pin disabled, the clean P1 harness FAILs with **63**
  `SYSTEM_ACL_MODIFIED` violations: schema USAGE@PUBLIC plus SELECT@PUBLIC
  on 62 relations.

This is a defect in D1.5's text. D1.5 names `pg_init_privs` or
`acldefault` as the source of the initial ACL, and for this schema the
catalog records neither. The implementation was right to treat it as an
ADR gap and not paper over it.

**F2. Stock `information_schema` on PG16 has this exact shape.**

- **Schema.** `nspacl = {postgres=UC/postgres,=U/postgres}`.
- **Relations.** There are 69 relations: 4 tables (`r`) and 65 views
  (`v`).
- **PUBLIC SELECT.** Exactly **62** relations carry PUBLIC SELECT (list in
  A1.3).
- **Relations without PUBLIC SELECT.** 7 stock relations have none:
  - `sql_parts` (r);
  - `transforms` (v);
  - `_pg_foreign_tables` (v);
  - `_pg_foreign_table_columns` (v);
  - `_pg_foreign_data_wrappers` (v);
  - `_pg_foreign_servers` (v);
  - `_pg_user_mappings` (v).
- **Other ACL entries.** There is no other PUBLIC privilege, no other
  grantee and no column ACL.
- **OIDs.** Every `information_schema` object and every `pg_catalog`
  object has oid < 16384 (`FirstNormalObjectId`). The maximum observed is
  13660 and 13665 respectively. On stock, 0 objects in system namespaces
  have oid ≥ 16384.

**F3. The implemented class-level pin silently admits modified system
ACLs.** These are false PASS results, measured with the gate.

| Case | Pin on | Literal D1.5 | Behavioural |
|---|---|---|---|
| H1: superuser `CREATE VIEW information_schema.zz_leak AS SELECT * FROM harness.access_grant; GRANT SELECT … TO PUBLIC` | **PASS** | FAIL (`zz_leak:SELECT@PUBLIC`) | runtime reads **3 cross-tenant rows** (the view runs as its superuser owner) |
| H3: same with `CREATE TABLE information_schema.zz_t AS …` | **PASS** | (FAIL, same mechanism) | **3 cross-tenant rows** |
| H10: `GRANT SELECT ON information_schema._pg_user_mappings TO PUBLIC` (stock object, stock ACL has no PUBLIC) | **PASS** | FAIL (`_pg_user_mappings:SELECT@PUBLIC`) | exposes user-mapping options, which can hold FDW credentials |

The pin introduced H1, H3 and H10. The predicate keys on the pair
(namespace, class, privilege, grantee). It does not key on *which object*
the grant is on, and it does not check that the object is stock.

**F4. A separate gap exists in ADR-010's own D1 definition.** It exists
with or without the pin.

- **The case (H8).** Run `CREATE FUNCTION pg_catalog.zz_count() …
  SECURITY DEFINER` over `harness.access_grant`. PASSes both with the pin
  and under literal D1.5.
- **Real leak.** The runtime counts **4 rows across both tenants**, but
  can directly see only 1.
- **Same result in `information_schema`.** H7, the same function created
  there, also PASSes.
- **Cause.** D1 defines a system object by namespace. Any object in
  `pg_*` or `information_schema` is therefore "system". Its initial ACL
  falls back to `acldefault`, which includes PUBLIC EXECUTE for functions
  (and PUBLIC USAGE for types). The SECURITY DEFINER rule also excludes
  system namespaces by name.
- **No relation variant in `pg_catalog`.** PostgreSQL itself refuses
  `CREATE VIEW pg_catalog.…` with "System catalog modifications are
  currently disallowed". Functions are not refused.

**F5. Controls that already hold.** These still FAIL correctly and must
keep doing so:

- H2: a new `information_schema` view granted to the runtime role
  directly;
- H4: PUBLIC UPDATE on `sql_features`;
- H5: PUBLIC CREATE on the schema;
- H6: column-level PUBLIC UPDATE.

Tightening (H9, revoking a stock PUBLIC SELECT) PASSes, which is correct.

**F6. False-FAIL check for A1.2.**

- Clean harness: the A1.2 rule has **0** hits. That includes 2 toast
  relations with oid ≥ 16384, whose ACLs are owner-only.
- Concurrent session: a temp table created by a concurrent superuser
  session yields 2 hits. Both are PUBLIC USAGE on the temp table's row
  types in `pg_temp_N`. A1.2 therefore excludes temp namespaces from the
  system definition.

### A1.2 Decision: correct the D1 "System object" definition (replaces the D1 bullet; D1.5 now applies only to this set)

- **System object.** An object is a system object if either condition
  holds:
  - it is in `pg_catalog`, `information_schema`, `pg_toast` or another
    `pg_*` namespace, other than a temp namespace matching
    `^pg_(toast_)?temp_[0-9]+$`, **and** its oid is below 16384
    (`FIRST_NORMAL_OBJECT_ID`);
  - or it has a `pg_init_privs` row.
- **Non-stock object.** Any other object in one of those non-temp system
  namespaces is a *non-stock object in a system schema*. If `G` holds any
  privilege on it, from any source including `acldefault`, the gate
  reports `RLS_RUNTIME_ROLE_ELEVATED`. The detail token is
  `NON_STOCK_SYSTEM_OBJECT:<class>:<identity>:<priv>@<grantee>`.
- **No allow-table, no manifest escape.** Application objects do not
  belong in system schemas. A future extension that needs this, for
  example a `CREATE EXTENSION … SCHEMA pg_catalog` whose objects have
  default ACLs, needs a superseding ADR.
- **Temp namespaces are never system.** Objects in them are judged as
  ordinary objects by D1.4, D1.6 and the SECURITY DEFINER rule:
  - row-type USAGE is allowed;
  - a temp relation granted to `G` is `OUT_OF_SCOPE`, because system
    schemas are never scanned;
  - a reachable temp SECURITY DEFINER function is
    `RLS_SECURITY_DEFINER_UNREVIEWED`.
- **One definition everywhere.** The SECURITY DEFINER query must use this
  same definition, not a bare namespace-name test. H7 and H8 are caught
  by the token above in any case.

### A1.3 Decision: D1.5a, the PG16 `information_schema` initial ACL is an exact, per-object pin

For a system object in `information_schema` with no `pg_init_privs` row,
the initial ACL for D1.5 is:

- **Owner `acldefault`**, plus for PG major 16 only exactly the following
  PUBLIC grants:
  - `USAGE` on the namespace `information_schema` itself;
  - `SELECT` on each of these 62 relations, matched by `relname` **and**
    expected `relkind`, with the object also a system object under A1.2
    (oid < 16384). The relations are all views except the 3 marked (r):

    `administrable_role_authorizations`, `applicable_roles`, `attributes`,
    `character_sets`, `check_constraint_routine_usage`,
    `check_constraints`, `collation_character_set_applicability`,
    `collations`, `column_column_usage`, `column_domain_usage`,
    `column_options`, `column_privileges`, `column_udt_usage`, `columns`,
    `constraint_column_usage`, `constraint_table_usage`,
    `data_type_privileges`, `domain_constraints`, `domain_udt_usage`,
    `domains`, `element_types`, `enabled_roles`,
    `foreign_data_wrapper_options`, `foreign_data_wrappers`,
    `foreign_server_options`, `foreign_servers`, `foreign_table_options`,
    `foreign_tables`, `information_schema_catalog_name`,
    `key_column_usage`, `parameters`, `referential_constraints`,
    `role_column_grants`, `role_routine_grants`, `role_table_grants`,
    `role_udt_grants`, `role_usage_grants`, `routine_column_usage`,
    `routine_privileges`, `routine_routine_usage`,
    `routine_sequence_usage`, `routine_table_usage`, `routines`,
    `schemata`, `sequences`, `sql_features` (r),
    `sql_implementation_info` (r), `sql_sizing` (r), `table_constraints`,
    `table_privileges`, `tables`, `triggered_update_columns`, `triggers`,
    `udt_privileges`, `usage_privileges`, `user_defined_types`,
    `user_mapping_options`, `user_mappings`, `view_column_usage`,
    `view_routine_usage`, `view_table_usage`, `views`.

**Anything else on `information_schema` remains `SYSTEM_ACL_MODIFIED`.**
That includes:

- any PUBLIC grant on the 7 stock relations that have none (F2);
- any non-PUBLIC grant to `G`;
- any column ACL;
- any privilege other than the one pinned.

Functions and types in `information_schema` keep the D1.5 `acldefault`
fallback. They are stock (oid < 16384), and F2 shows their ACLs are
default.

**Pinning rules.**

- **Unpinned major.** No pin applies. The D4.3 predicate pin already makes
  such a server ERROR.
- **Adding a major's set.** This follows the D4.3 rule: raw evidence that
  the set equals a pristine initdb of that major, plus independent
  security review. It does not need a new ADR.
- **Where the pin lives.** It is a committed constant in the gate, keyed
  by major. It is not read from the target database, because nothing in
  the target's catalog can distinguish a stock grant from an added one
  (F3, H10). `template0` is not a trusted reference either: it is
  unconnectable by default and outside the one-database scope.

### A1.4 Disposition of the implemented interpretation

- **Intent: conforms.** A pin is the right mechanism, and the
  implementation correctly disclosed the gap rather than deciding it.
- **Predicate as implemented: rejected.** It is class-level, not
  per-object, and it does not check that the object is stock. It produces
  measured false PASS results (H1, H3, H10), two of them with real
  cross-tenant leaks. The Slice-6 record's statement "anything else there
  stays `SYSTEM_ACL_MODIFIED`" is incorrect, as H1, H3 and H10 show.

**Rejected alternatives:**

- **oid < 16384 plus a class-level shape, without names.** H10 still
  PASSes, because `_pg_user_mappings` is stock.
- **Exempt `information_schema` wholesale.** This opens H1, H3 and H10.
- **Read the initial ACL from `template0`.** This is outside scope, and
  the template is mutable by a superuser.
- **Literal D1.5 with no pin.** Every clean database FAILs, so the gate is
  unusable.

### A1.5 Acceptance additions (append to ADR-010's acceptance tables; Colima PG16 integration unless stated)

| # | Fixture | Expected |
|---|---|---|
| N27 | H1 view in `information_schema` over `access_grant`, PUBLIC SELECT; behavioural 3-row leak asserted | FAIL `NON_STOCK_SYSTEM_OBJECT:` |
| N28 | H3 table in `information_schema`, PUBLIC SELECT; behavioural leak asserted | FAIL `NON_STOCK_SYSTEM_OBJECT:` |
| N29 | H10 `GRANT SELECT ON information_schema._pg_user_mappings TO PUBLIC`; also `sql_parts` | FAIL `SYSTEM_ACL_MODIFIED:` |
| N30 | H8 SECURITY DEFINER function in `pg_catalog` (default PUBLIC EXECUTE); behavioural all-tenant count asserted; H7 same in `information_schema` | FAIL `NON_STOCK_SYSTEM_OBJECT:` |
| N31 | Regression H2, H4, H5, H6 | Still FAIL `SYSTEM_ACL_MODIFIED:` |
| N32 | Unit: pin-set mutants (class-level pin, missing oid check, pin applied to an unpinned major, a relname dropped/added) | Each killed by a unit or integration case |
| P9 | Clean P1 with a concurrent session holding a temp table | PASS |
| P10 | H9 tightening (revoke a stock PUBLIC SELECT) | PASS |

P1 must still PASS on the clean harness with zero `information_schema`
violations.

### A1.6 Scope, routing and owner determination

- **Implementer.** The retained `veyro-critical-engineer` session (ADR-005
  Decision 1) does the work, within ADR-010's existing in-scope files
  only:
  - the gate tool, covering the definition, D1.5a, the SECURITY DEFINER
    query, the docstring "Disclosed limits" paragraph and the comment at
    the pin;
  - its unit tests;
  - the RLS integration test;
  - the kill-check;
  - the Slice-6 record, correcting gap 1 to cite A1.
- **Out of scope.** No harness, CI, baseline or scenario change.
- **After implementation.** R3 security and the distinct code review are
  still required. R3 must verify A1 literally, including N27-N30.
- **Owner determination.** **No owner-reserved change is involved.**
  - It tightens TSD §7.3/§24.1 and TSD ADR-002 enforcement only.
  - It involves no spend, no real data and no Production action.
  - It changes no product, pricing or scope.
  - It changes no governing baseline.

### A1.7 Clarification (2026-10-02, same day, veyro-lead): token for H2, N31 and the "Anything else" sentence

Raised by the retained implementer after implementing A1. This clarification
is append-only; the A1 text above is unchanged and is to be read as
corrected by this section. Where they conflict, A1.7 governs.

1. **Token precedence is classification-based and exclusive.** A1.2
   classifies each object in a non-temp system namespace as either a system
   object or a non-stock object. `SYSTEM_ACL_MODIFIED` (D1.5/D1.5a) applies
   only to system objects. `NON_STOCK_SYSTEM_OBJECT` applies only to
   non-stock objects. A single grant never produces both tokens.
2. **H2 is non-stock.** Its view is created after initdb (oid ≥ 16384, no
   `pg_init_privs` row). Its expected result is FAIL
   `NON_STOCK_SYSTEM_OBJECT:view:information_schema.zz_leak:SELECT@veyro_runtime`
   (format per A1.2), not `SYSTEM_ACL_MODIFIED`. The F5 listing of H2 is a
   record of what the pre-A1 tool emitted, not a binding expectation.
3. **N31 is replaced by:**

   | # | Fixture | Expected |
   |---|---|---|
   | N31a | H2: new `information_schema` view granted SELECT to the runtime role directly | FAIL `NON_STOCK_SYSTEM_OBJECT:` only |
   | N31b | Regression H4, H5, H6 (all on stock objects) | Still FAIL `SYSTEM_ACL_MODIFIED:` only |

4. **The A1.3 sentence "Anything else on `information_schema` remains
   `SYSTEM_ACL_MODIFIED`" is scoped to system objects.** It reads: anything
   else granted to `G` on a *system object* in `information_schema` remains
   `SYSTEM_ACL_MODIFIED`. Its four bullets keep that scope. Any grant to `G`
   on a non-stock object in `information_schema` is
   `NON_STOCK_SYSTEM_OBJECT` per A1.2, whatever the grantee or privilege.
5. **No other change.** N27-N30, N32, P9, P10, the 62-relation pin and the
   A1.6 routing stand. R3 verifies A1 as corrected by A1.7, including N31a
   and N31b.

---

## Amendment A2 (2026-10-03): system classification without `pg_init_privs`, unconditional SECURITY DEFINER review, trusted-language functions, rewrite rules, function-level tenant context

**Decided by:** a fresh `veyro-lead` architecture-decision session (Opus,
`claude-opus-5-5`). It is not the implementer, not R1/R2/R3, and not the A1
author. It approves no gate, code or scenario. Model attestation is for the
orchestrator to run with `mr_verify.py`; this session did not self-attest.
Judgments are code/design reading only — nothing was executed.

**Status:** DECIDED. Conforms to the governing baseline; no owner approval
required (A2.9). D1–D5, A1 and A1.7 text above is unchanged; A2 supersedes
only the bullets it names. Everything in A2 tightens the gate.

### A2.0 What was asked

`knowledge/03-Modules/MOD-001/evidence/security/R04-CRITICAL-SLICE-SECURITY-REVIEW-R3-2026-10-03.md`
(BLOCKED, incomplete after a classifier stop, findings provisional and not
executed) reported P1-1, P1-2, P1-3, P2 ×4 and P3 ×2 against gate sha256
`34aa8461…629e91b`. This session verified each cited line range in that
file; all match.

**Threat model, made explicit.** The gate must not PASS any end state that
a migration can reach through supported DDL/DCL. That covers mistaken
migrations and deliberate ones alike, and includes `CREATE EXTENSION`,
`ALTER EXTENSION … ADD`, `CREATE RULE` and triggers.

The following stay outside SQL-catalog proof, as the existing residual
"a superuser-controlled server" already says:

- direct catalog writes (`allow_system_table_mods`);
- custom extension scripts on the server filesystem;
- server configuration.

### A2.1 Dispositions

| R3 | Class | Sev | Disposition |
|---|---|---|---|
| P1-1 | A | P1 | A2.2 |
| P1-2 | A | P1 | A2.3 |
| P1-3 | A | P1 | A2.4 |
| P2-a | A | P1 (raised: same impact as P1-2) | A2.5 |
| P2-b | B | P2 | A2.8 (D1.7 already forbids it) |
| P2-c | A | P2 | A2.6 |
| P2-d | B | P2 | A2.8 (D1.6 already forbids it) |
| P3-a | A | P3 | A2.7 |
| P3-b | D | P3 | Deferred to the contract-validation scope (OpenAPI structural validation of `contracts/`). Safe because flow contents do not affect any operation's authentication class, permission or scope. D5.2 is met as written. |

### A2.2 System classification (decides P1-1; supersedes A1.2 bullet 1, second condition)

1. **System object.** An object is a system object only if:
   - it is in a non-temp system namespace (the A1.2 namespace rule); **and**
   - its oid < 16384.

   A `pg_init_privs` row never confers system status. Namespace-less
   classes are never system and are judged by the D1.4 allow-table. Those
   classes are: database, language, large object, FDW, foreign server,
   tablespace and parameter. The same definition is used in the ACL scan,
   the SECURITY DEFINER rule (A2.3), A2.4 and A2.6; drop the
   `pg_init_privs` `EXISTS` clause from the definer query.
2. **D1.5 initial ACL is unchanged for system objects.** It is the
   `pg_init_privs` row, else `acldefault`, plus the A1.3 pin, which still
   applies only when no `pg_init_privs` row exists.
3. **Extension-captured system object.** A system object is
   extension-captured if it has a `pg_catalog.pg_depend` row with all of:
   - `classid` = its catalog;
   - `objid` = its oid;
   - `objsubid = 0`;
   - `deptype = 'e'`;
   - `refclassid = 'pg_catalog.pg_extension'::regclass`;
   - `refobjid >= 16384`.

   Column grants use the relation's membership. Every privilege `G` holds
   on such an object is `RLS_RUNTIME_ROLE_ELEVATED`, subject
   `<runtime>/<identity>`, token
   `SYSTEM_OBJECT_EXTENSION_MEMBER:<class>:<identity>:<priv>@<grantee>`.
   D1.5 is not evaluated for that grant.
4. **Extension members get no exemption.** Members that are not system
   objects are judged like any other object: D1.4, D1.6, D4.4,
   `NON_STOCK_SYSTEM_OBJECT`, A2.3, A2.4 and A2.6. Any extension that
   needs an exception requires a superseding ADR (see A1.2, A2.4).
5. **A1.7 exclusivity, extended.** One grant yields at most one of these
   tokens: `NON_STOCK_SYSTEM_OBJECT`, `SYSTEM_OBJECT_EXTENSION_MEMBER`,
   `SYSTEM_ACL_MODIFIED`, `PRIVILEGE`.

### A2.3 SECURITY DEFINER review is unconditional (decides P1-2; supersedes the "executable"/"reachable" scope in D1.4's function row, N19's wording and A1.2's "reachable temp" bullet)

TSD §7.3: "The lint also rejects SECURITY DEFINER functions unless
explicitly reviewed."

Every `pg_proc` row with `prosecdef` that is not a system object (A2.2)
must be a key in `reviewed_security_definer_functions`. Otherwise the
result is `RLS_SECURITY_DEFINER_UNREVIEWED`, subject
`<runtime>/<regprocedure>`. This holds in any namespace (including temp,
non-stock system and extension members) and regardless of any ACL,
executability, `--schema` or trigger attachment.

Reason: triggers and event triggers invoke definer functions without a
caller EXECUTE check. The runtime fires event triggers itself through
`CREATE TEMP TABLE`.

### A2.4 Function code must be stock-trusted (decides P1-3; supersedes D1.4's function row and the "EXECUTE on non-definer application functions" positive bullet)

1. **Language rule.** This applies to every non-system `pg_proc` row with
   `prokind <> 'a'`, regardless of grants, schema, `--schema`, extension
   membership or manifest. Its `prolang` must reference a `pg_language`
   row with `lanpltrusted = true` **and** oid < 16384. On PG16 that means
   `sql` and `plpgsql`. Otherwise the result is
   `RLS_RUNTIME_ROLE_ELEVATED`, subject `<runtime>/<regprocedure>`, token
   `UNTRUSTED_LANGUAGE_FUNCTION:<regprocedure>:<lanname>`.
2. **Aggregates** (`prokind = 'a'`, whose own `prolang` is `internal`).
   Check every non-zero component of a non-system aggregate in
   `pg_catalog.pg_aggregate`: `aggtransfn`, `aggfinalfn`, `aggcombinefn`,
   `aggserialfn`, `aggdeserialfn`, `aggmtransfn`, `aggminvtransfn` and
   `aggmfinalfn`. `G` must hold EXECUTE on each one in
   `aclexplode(coalesce(proacl, acldefault('f', proowner)))`, because the
   executor checks the aggregate owner's privilege, not the caller's.
   Otherwise the result is `RLS_RUNTIME_ROLE_ELEVATED`, token
   `AGGREGATE_COMPONENT:<aggregate regprocedure>:<component regprocedure>`.
   The components are themselves judged by rule 1.
3. **Why this construction.**
   - Owner-based rules cannot separate safe from unsafe code, because
     migrations run as a superuser/owner role.
   - EXECUTE-based rules miss server-invoked slots that skip the caller
     check: triggers, aggregate components, type I/O, operator
     estimators, opclass support and conversions.
   - A language rule on existence covers all of these slots for
     non-system code.
4. **No extension escape in A2.** Admitting an extension needs a
   superseding ADR in the module that first installs it. This includes
   TSD's V1 `pg_trgm` search. That ADR must define a pinned
   reviewed-extension mechanism with these properties:
   - name and version pinned per PG major;
   - C members accepted only with `probin` equal to that extension's own
     library;
   - every other rule still applies.

   Until then, any C/internal/untrusted-PL member FAILs. That is
   fail-closed and accepted.

### A2.5 Rewrite rules (decides P2-a)

Every `pg_catalog.pg_rewrite` row with `rulename <> '_RETURN'` and
oid >= 16384, on any relation in any namespace, regardless of grants, is
`RLS_RUNTIME_ROLE_ELEVATED`. Subject `<runtime>/<schema>.<relation>`,
token `REWRITE_RULE:<schema>.<relation>:<rulename>`.

Reason: rule actions run with, and evaluate RLS as, the relation owner.
Stock rules (for example the rules on `pg_settings`) have oid < 16384 and
are excluded. Views stay judged by D4.4 through `_RETURN`.

### A2.6 Function-level tenant context (decides P2-c; extends D1.7)

For every non-system `pg_proc` row, regardless of grants: any `proconfig`
entry whose name (the text before the first `=`), lower-cased, starts
with `app.` is `TENANT_CONTEXT_DEFAULT`. The source is
`<entry>@function=<regprocedure>`.

D1.7 parameter-name matching is case-insensitive for every source (see
A2.8).

### A2.7 Approval resolution is token-bounded (decides P3-a; clarifies D3.4 and D5.1)

"Contains the entry's exact key string" means an occurrence of the key
that meets both conditions:

- the preceding character is absent, or not in `[A-Za-z0-9_.-]`;
- the following character is absent, or not in `[A-Za-z0-9_.-]`.

This applies to both the ADR file text and the single OWN row. Resolution
still proves only that the record mentions the key, not intent. Diff
review of the manifest/registry remains the control for intent.

### A2.8 Implementation-only items (B): ADR already requires; code must conform

| R3 | Required by | Fix | Executed negative fixture |
|---|---|---|---|
| P2-b | D1.7 "any `app.*` parameter" (GUC names are case-insensitive) | Compare the lower-cased parameter name, as is already done for `lo_compat_privileges` | N42 |
| P2-d | D1.6 | Judge scope on the grant's separate `schema` field (`AclGrant.schema`). Key `granted` and the D4.4 membership test on `(schema, relname)`, not on a split identity string. Token text is unchanged: `OUT_OF_SCOPE:<schema>.<relation>`. | N43 |

### A2.9 Acceptance additions

Integration rows run on CAP-008 Colima PG16; unit rows are marked. The
existing numbering ends at N32 / P10. A negative must not PASS. The
listed token must be present, and other tokens are allowed unless stated.

| # | Fixture | Expected |
|---|---|---|
| N33 | `CREATE EXTENSION tcn`; `harness.zz_forged` view over `access_grant` (no `security_invoker`), SELECT to runtime; `ALTER EXTENSION tcn ADD VIEW`. Pre-assert that a `pg_init_privs` row now exists. Behavioural: cross-tenant rows via the view | FAIL `RLS_NOT_ENFORCED` on `harness.zz_forged` |
| N34 | As N33, but with a `LANGUAGE sql SECURITY DEFINER` function in `harness`, added to the extension | FAIL `RLS_SECURITY_DEFINER_UNREVIEWED` |
| N35 | As N33, in `information_schema`, PUBLIC SELECT | FAIL `NON_STOCK_SYSTEM_OBJECT:view:information_schema.zz_forged:SELECT@PUBLIC` only (A2.2.5) |
| N36 | `GRANT EXECUTE ON FUNCTION pg_read_binary_file(text)` to runtime, then `ALTER EXTENSION tcn ADD FUNCTION pg_read_binary_file(text)` | FAIL `SYSTEM_OBJECT_EXTENSION_MEMBER:function:pg_read_binary_file(text):EXECUTE@veyro_runtime` only. If PG16 refuses the ADD, commit the raw refusal and replace with a unit verdict case |
| N37 | `plpgsql SECURITY DEFINER` trigger function in `harness`, `REVOKE EXECUTE … FROM PUBLIC`, `AFTER INSERT` trigger on `access_grant`. Behavioural: runtime insert produces a cross-tenant effect. Separately, a definer event-trigger function | FAIL `RLS_SECURITY_DEFINER_UNREVIEWED` (each) |
| N38 | `harness.zz_rf(text) LANGUAGE internal` with `prosrc` read from `pg_read_binary_file(text)`. Behavioural: runtime reads a data-directory-relative file. Variants: `LANGUAGE c`; `plperlu` if available | FAIL `UNTRUSTED_LANGUAGE_FUNCTION:harness.zz_rf(text):internal` (respective `lanname` per variant) |
| N39 | `CREATE AGGREGATE harness.zz_agg(text) (SFUNC = textcat, STYPE = text, INITCOND = '', FINALFUNC = pg_read_binary_file)`. Behavioural: runtime reads a file | FAIL `AGGREGATE_COMPONENT:harness.zz_agg(text):pg_read_binary_file(text)` |
| N40 | `CREATE RULE zz_r AS ON INSERT TO harness.access_grant DO ALSO INSERT …` copying other-tenant rows. Behavioural: more own-tenant rows. Separately, a `DO INSTEAD` rule on a `security_invoker` view | FAIL `REWRITE_RULE:harness.access_grant:zz_r` (and the view equivalent) |
| N41 | `harness.zz_ctx() LANGUAGE sql SET app.tenant_id = '<B>'` counting `access_grant`. Behavioural: under context A it returns B's count. Variant: `SET "APP.TENANT_ID"` | FAIL `TENANT_CONTEXT_DEFAULT:` source `…@function=harness.zz_ctx()` |
| N42 | `ALTER ROLE veyro_runtime SET "APP.TENANT_ID" = '<uuid>'`. Behavioural: a new runtime session reads it via `current_setting('app.tenant_id', true)` | FAIL `TENANT_CONTEXT_DEFAULT:` |
| N43 | Schema `"harness.x"` containing a view over `access_grant` without `security_invoker`, granted to runtime. Gate with `--schema harness`; then unnarrowed | FAIL `OUT_OF_SCOPE:harness.x.<view>`; unnarrowed run FAIL `RLS_NOT_ENFORCED` |
| N44 | Unit: an ADR mentioning only `members.profile.reader` cited for `members.profile.read`; the same for an OWN row; a manifest key cited by a record mentioning only `<key>_v2` | ERROR |
| N45 | Kill-check: one killed mutant per A2.2.1, A2.2.3, A2.3, A2.4.1, A2.4.2, A2.5, A2.6, A2.7, A2.8 | All killed; real tool SHA-256 unchanged |
| P11 | Clean P1 harness (stock `pg_settings` rules, stock languages, `plpgsql` handlers) | PASS, with zero A2 tokens |
| P12 | Non-definer `sql` and `plpgsql` functions with PUBLIC EXECUTE in `harness`, plus an aggregate whose components are PUBLIC-executable | PASS |
| P13 | Manifest-reviewed definer function with PUBLIC EXECUTE revoked (resolving approval) | PASS |

N19, N30, N31a/b, P1–P10 stand. The implementation must also update the
module docstring at "Executable non-system SECURITY DEFINER" (L77–79) and
the System-objects paragraph.

### A2.10 Scope, routing and owner determination

- **Implementer.** The retained `veyro-critical-engineer` session, within
  ADR-010's existing in-scope files only.
- **Out of scope.** No harness, CI, baseline, scenario, `STATUS`, `STATE`
  or `HANDOFF` change.
- **After implementation.** A fresh R4 `veyro-security-reviewer` must
  execute N33–N43 adversarially and attempt at least one path outside
  A2. Then a distinct fresh code review.
- **Owner.** No owner-reserved change is involved:
  - it tightens TSD §7.3, §24.1 and TSD ADR-002 enforcement only;
  - there is no spend, no real data and no Production action;
  - no product, pricing or scope change;
  - no baseline change.
- **Superseding-ADR matters (not owner matters).** Admitting any
  extension, including `pg_trgm`.

### A2.11 Residual risk, disclosed

- **Direct catalog writes and server-side extension scripts.** These stay
  outside SQL-catalog proof. A source-level migration lint forbidding
  `allow_system_table_mods`, `ALTER EXTENSION … ADD` and unreviewed
  `CREATE EXTENSION` would be defence in depth. It is recommended for the
  migration-tooling scope and is not decided here.
- **Function bodies that call `set_config('app.tenant_id', …)`.** These
  are not statically decidable. They grant the runtime nothing beyond its
  own ability to set the GUC. Correctness rests with MOD-004, the
  behavioural harness and code review.
- **Stock functions bound into server-invoked slots** (type I/O, opclass
  support, operator estimators, conversions, range support) are
  constrained by PostgreSQL signature rules. This is not proven; R4 should
  probe it.
- **Foreign-key RI checks bypass RLS by design** (an existence side
  channel). Out of R04.
- **A2.4 FAILs every C-extension install until a superseding ADR admits
  it.** Fail-closed and accepted.

### A2.12 Orchestrator record (scribe note, not part of the lead's decision text)

- The fresh parent session `7c774fbc-d164-497d-887e-42060f7a302d` appended A2.0–A2.11 verbatim from the lead's returned text. That session reused no implementation or R3 context. The lead itself had read-only tools and wrote no files.
- Model route, orchestrator-run: `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-lead` returned **PASS, 20 turns, 100% `claude-opus-5-5`**, exit 0.
  - Transcript: `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/7c774fbc-d164-497d-887e-42060f7a302d/subagents/agent-ab5b62eb296d4578e.jsonl`
  - Transcript sha256: `d700d112f8a7f290d677102c013bd23131849efe6c39657f34a04985d0f31b35`
  - `meta.json`: `agentType: veyro-lead`, foreground, non-interactive.
- One cross-reference is mislabelled in the decision text. Where A2's Status line and A2.10 refer to "A2.9" for the owner determination, they mean A2.10. A2.9 is the acceptance table. The scribe did not alter the decision text.
- Pre-decision checks, in this parent:
  - `verify_baselines.py` PASS 4/4.
  - Gate sha256 `34aa8461…629e91b`, which is R3's reviewed file.
  - `git diff` sha256 `827cbaa1…c7aec7a1`, unchanged from R3 and unchanged after the lead ran.
  - Highest existing acceptance ids N32 / P10, confirmed by grep.
