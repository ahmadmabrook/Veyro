---
scope: path
paths:
  - "backend/**"
---
<!-- Target path once applied: .claude/rules/backend/database.md -->

# Rule: Backend PostgreSQL Tenant Isolation (RLS) and Migration Safety (`backend/**` binding)

Authored 2026-09-19 (MOD-001, `ADR-005` Decision 2 binding pre-implementation
condition — see `architecture.md` for the shared authority citation, not
restated here). Grounded directly in TSD §1.2/§2.2
(`TSD_MIRROR.md` lines 562-567, 620-634: `TEN-001`/`TEN-002` — every
persisted tenant-owned object belongs to exactly one `tenant_id`; tenant
context is resolved server-side, clients cannot select it on a trusted
write path), TSD §24.1's RLS lint (`TSD_MIRROR.md` lines 11599-11601:
"every tenant table tenant_id NOT NULL + policy + ENABLE/FORCE RLS;
runtime role cannot own/bypass. Negative isolation tests run with
production-equivalent role"), and TSD §24.2's Database Migration Policy
in full (`TSD_MIRROR.md` lines 11655-11669) — read directly this session
from the owner-produced mirrors. Per this project's own convention
(`REQUIREMENTS.md` §0), the governing `.docx` wins over this
mirror-sourced text on any conflict.

**Scope note (`ADR-005` Decision 1):** the tenant-isolation/RLS test
harness itself — its critical-slice logic, fixture schema, roles and
grants (`REQUIREMENTS.md` GOV-01-R02) — is owned by the registered
`veyro-critical-engineer` role, not this rule or its authoring agent.
This rule states the schema/role constraint all backend code and
migrations must satisfy so that harness can prove something real; it
does not itself build or modify the harness's own test logic.

## Required controls for `backend/**` (schema, models, migrations)

1. **Every tenant-owned table has `tenant_id NOT NULL`.** No tenant
   table may leave `tenant_id` nullable — TSD §24.1's RLS lint denies
   this as `RLS_TENANT_ID_NULLABLE`, citing the column.

2. **Every tenant-owned table has RLS enabled and forced.** Every such
   table carries `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL
   SECURITY`, plus at least one RLS policy that scopes visible/writable
   rows to the resolved tenant context. A table missing
   `FORCE ROW LEVEL SECURITY` fails as `RLS_NOT_ENFORCED`.

3. **The runtime role never owns or bypasses RLS.** The database role
   backend request-handling code connects as is never the owning role
   of a tenant table and never carries the `BYPASSRLS` attribute — TSD
   §24.1, verbatim: "runtime role cannot own/bypass." A migration role
   with elevated DDL privileges is a distinct credential from the
   runtime request-handling role, never reused for it. Violating this
   fails as `RLS_RUNTIME_ROLE_ELEVATED`, citing the role/table pair.

4. **Tenant context is resolved server-side, never client-supplied.**
   No backend code path accepts a client-supplied `tenant_id` on a
   trusted write path; tenant context comes only from authenticated
   identity resolved server-side (`TEN-002`).

5. **Negative isolation tests run under the production-equivalent
   role.** Any test asserting RLS denial (the harness `ADR-005` scopes
   to `veyro-critical-engineer`) runs as the same non-privileged runtime
   role backend code actually connects as in production — never a
   superuser or `BYPASSRLS`-capable role, which would make the test
   meaningless regardless of who authors it.

## Required controls for migrations (TSD §24.2)

6. **Expand → migrate/backfill → switch → contract ordering.** A
   destructive (contract-phase) schema change is never deployed in the
   same release that stops reading the old shape; it follows an
   already-deployed expand step, a backfill, and a read/write switch
   first.

7. **Every migration records the 4 TSD §24.2 fields.** A migration's
   own record (docstring, commit message, or migration-record template
   per `REQUIREMENTS.md` GOV-01-R06) states: owner, expected lock/write
   impact, rollback/forward-fix strategy, and a data-validation query.
   A migration missing any one of these 4 fields does not merge.

8. **Large backfills are online, resumable, and throttled.** A backfill
   touching a non-trivial row count runs as a resumable job with
   progress tracking and throttling — never as a single deployment
   transaction (TSD §24.2, verbatim).

9. **Rolling-deploy compatibility is tested against the previous
   supported version.** Schema and application deployment ordering is
   verified compatible with at least the immediately prior deployed
   version, so a rolling deploy never runs new application code against
   an unmigrated schema or vice versa.

## Fail-closed rule

A tenant table without `tenant_id NOT NULL` plus an enforced RLS policy
plus `FORCE ROW LEVEL SECURITY`, a runtime role that owns or bypasses
RLS, or a migration missing one of the 4 required TSD §24.2 record
fields or attempting a destructive change out of expand-contract order,
does not merge. The RLS lint and migration-safety check (TSD §24.1/§24.2)
are both CI-blocking, proven by a deliberate-violation fixture per
`IMPLEMENTATION.md` §4.
