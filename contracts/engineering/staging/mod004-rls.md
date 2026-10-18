---
description: MOD-004 S1 control-plane tenant isolation (RLS, context, platform_scope) rule
paths:
  - "backend/app/tenancy/**"
  - "backend/migrations/**"
  - "backend/tests/integration/tenancy/**"
  - "infra/db/**"
---

# MOD-004 S1 — tenant isolation (RLS) rule

This rule itself grants no approval. It authorizes no code, migration, dependency, environment pull or spend, and it does not declare MOD-004 Ready or any capability ACTIVE. Implementation under it requires independently evidenced Module Ready, a qualified ACTIVE capability manifest, Scenario Review and the applicable owner approvals.

## Authority
- Governing: `knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md` (ADR-0002) and `knowledge/03-Modules/MOD-004/MOD-004.md`. If this file disagrees with them, they win.
- **Accepted (narrow scope, D1-D6):** roles and ownership, tenant-table RLS, platform_scope function boundary, provisioning, transaction-local context and pooling, migration lint. Acceptance is limited to that scope and rests on ADR-0002's own exact-diff review and exact-SHA CI; this file does not add to it.
- **Proposed / OPEN, do not treat as decided:** D4.3 driver, database and version (psycopg, psycopg_pool, PostgreSQL 17); D6.4 access-log seam (default: none in S1); D6.7 transport and caller authn/authz (placement contract is test-harness only); D6.8 support/break-glass; D7-D10 functionality; D15 items outside the owner-approved core.
- **Gates required before S1 implementation (ADR-0002 D11, D12):** independently evidenced Module Ready; a qualified ACTIVE capability manifest in `contracts/engineering/module-capabilities.yaml` (no such qualified ACTIVE entry is established by this file); Scenario Review; the EIP §18 ¶1167 interpretation; and any applicable owner approvals. Without them, S1 code and migrations are not authorized.

## Rules
1. **Explicit tenant context.** Every request or worker command opens an explicit transaction and sets `app.tenant_id`, `app.actor_id`, `app.correlation_id` transaction-locally (`SET LOCAL`, or `set_config(name, value, true)`) through the single approved tenancy primitive (D4.1-D4.2). Refuse autocommit and non-UUID values.
2. **No session-level context.** Do not use `SET app.*`, `SET SESSION`, `ALTER ROLE/DATABASE ... SET app.*` or `set_config(..., false)`. PostgreSQL does not reject these; the ban rests on lint, the primitive and reuse tests. Pool reset is defence in depth only, and `pg_db_role_setting` must hold no `app.*` entry (D4.2, D5).
3. **Fail closed.** Every tenant table has `tenant_id UUID NOT NULL`, `ENABLE` and `FORCE ROW LEVEL SECURITY`, no PUBLIC grant, and a policy with `USING` and `WITH CHECK` on `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` (D2, D3). Missing or invalid context may error or return zero rows, never unrestricted rows. No `OR true`, role-membership bypass or unrestricted-returning function in a tenant policy.
4. **Non-owner runtime roles.** Runtime and worker roles (`veyro_cp_app`, `veyro_cp_worker`) are LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS, own no tenant table, and are members of no role (no `SET ROLE` path). DDL runs as a separate non-runtime owner (D1, D6.5). Role names are ADR proposals; do not rename without an ADR change.
5. **Least privilege.** No TRUNCATE or REFERENCES grant to runtime roles; no PUBLIC privilege on schemas, tables, sequences or functions; views are `security_invoker = true` or banned; history and outbox are insert/select only (D2.4, D5, D6.2).
6. **platform_scope is function-only (D6).** Platform tables sit in `plt01_platform` with no RLS and no policy, no runtime-role grant and no USAGE for runtime roles. Runtime access is only through the closed D6.3 allowlist (`provision_tenant`, `resolve_placement`); adding a function, including any cross-tenant list or read, needs an ADR change and review ID. SECURITY DEFINER functions need an allowlist entry, pinned `search_path`, no dynamic SQL and no PUBLIC EXECUTE.
7. **No cross-tenant leakage.** Cache keys, search and read models, object-storage paths, events/jobs/queues, telemetry and AI/retrieval context must carry tenant scope and must not combine data across tenants (MOD-004 release-gate layers; TSD §7.3). Only the PostgreSQL layer is mapped in S1; the other layers are OPEN, so do not build or claim them from this rule.
8. **No invention.** Do not invent product behavior or owner policy: regions, keys, retention, hierarchy cardinalities, plan tiers, spend and real-member-data handling are owner-reserved. Placement stays `UNASSIGNED` in S1. Unsupported commands, events or tables are source gaps to raise, not to fill (D8.3).
9. **Synthetic data, local only.** Tests use generated UUIDs and synthetic tenants in a local container, run as the actual runtime role with no application tenant filter (D9). No real data, managed cloud or production target.
10. **Tests are obligations, not evidence.** Do not report a PASS, Ready, ACTIVE or acceptance status that no independent review or CI has produced.

## Verification evidence required
Before any claim that this rule is qualified for implementation, record both of these tests, run as the actual runtime role against a local synthetic database. They are obligations, not existing PASS; none is recorded today.
- A role-privilege test proving the runtime role is not a table owner and has no BYPASSRLS or role-membership escape (rule 4).
- A transaction-pool reuse test proving `app.*` context does not leak between transactions on a reused pooled connection (rules 1-2).

## Scope limit
Applies only to MOD-004 S1 paths above. It does not govern other modules, global policy, governance, workflow, runner, catalog, registry or owner-record paths.
