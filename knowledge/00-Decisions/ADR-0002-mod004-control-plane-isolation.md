# ADR-0002 — MOD-004 control-plane tenant isolation: PostgreSQL roles, RLS, context, placement

- ID: ADR-0002
- Status: PROPOSED
- Decision-Key: mod004-control-plane-isolation
- Covers: backend/app/tenancy/, backend/migrations/, backend/tests/integration/tenancy/, infra/db/

**This ADR is PROPOSED. It is not accepted, has no `Review` header and records no owner approval.** It is an engineering design proposal for MOD-004 only. It authorizes no write, no code, no migration, no dependency, no cloud spend and no owner-reserved action, and it cannot self-authorize anything. The existing standing authority for the controlled decisions path is ADR-0001 (ACCEPTED, key `governance-foundation-change-control`), which covers `knowledge/00-Decisions/`. Creating this file relies on ADR-0001 plus the OWNER direct-main process (exact-diff independent review and exact-SHA push CI), not on this ADR. `knowledge/03-Modules/MOD-004/MOD-004.md` is not an ADR-0001-controlled path; only this ADR-0002 path is. Covers lists only the future engineering paths this design would govern (the integration-test path is narrowed to a tenancy-only subpath); it deliberately lists no governance, workflow, runner, catalog, registry, frozen-baseline or `OWNER-*` path. A CI PostgreSQL service would be a future controlled `.github/workflows/` change under ADR-0001 and the owner direct-main process; this ADR does not authorize it. The current validator does not control the engineering paths, so this ADR is a project engineering gate, not a validator-enforced one. No module is Ready, nothing is implemented, and no product PASS or acceptance is claimed.

## Context
EIP §21.5 (¶1934-1969) gives MOD-004 the PLT-01 scope with "No special waiver. All Development Constitution gates apply" (¶1954), risk class Foundation/Control (¶1956). Appendix B (¶5093-5148) assigns the complete Critical requirements PLT-01-R01..R07 to MOD-004, each "Full requirement implemented and completed in the listed module". No MOD-003-style foundation-only acceptance applies. The module card requires isolation release-gate evidence across PostgreSQL/RLS, cache keys, search/read models, object-storage paths, events/jobs/queues, telemetry/log correlation and AI/retrieval context (¶1946), manual QA as the actual runtime DB role (¶1950), load evidence (¶1952) and an expanded security suite (¶1958).

TSD §7.3 (¶741-772), §7.5 (¶775-783), §10.1 (¶1194-1245) and INV-PLT-01 (¶10550-10558) define the engineering contract. The repository has no PostgreSQL, driver, migration tool or CI database service today. Pinned sources: EIP SHA-256 `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f`; TSD SHA-256 `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33`; evidence bundle `mod004-pinned-source-evidence-20261017` and supplement `mod004-ready-scenarios-source-supplement-20261017` (supplement SHA-256 `85fe2c7eae9fe6e948dadb4c671cabb5b2ab5ac17560f5287d359e8514bc7388`; EIP §8 Ready ¶746-773, §9.1 ¶880-883); read-only, not an owner decision or waiver. Every citation in the overlapping ¶741-783 range carries an explicit EIP or TSD prefix (EIP ¶749-750 is the Ready rule; EIP ¶754 is the capability manifest rule; EIP ¶766 is the load/security N/A rule; TSD ¶766 is quarantine of messages without tenant context; TSD ¶776 is tenant placement). Outside that range, ¶ numbers 1194-1245 and 10550-10558 are TSD and 1934-1969 and 5084-5148 are EIP.

**Capability manifest (EIP ¶754).** EIP ¶754 requires a reviewed capability manifest and supply-chain evidence for psycopg, PostgreSQL and any other third-party capability before activation. None exists. The driver and database choices in D4.3 are proposals only and cannot be activated until that manifest and evidence are reviewed. EIP ¶881-882 (§9.1) require explicit QA disposition and test mapping for every scenario and a minimum of 24 Required scenarios (and at least the number of Critical requirements/slices) for a concurrency/security-critical module; the D9 list is a set of obligations, not an executable scenario catalog, so that rule is OPEN and Scenario Review is not passed.

Two independent Opus assessments (both OUTCOME: APPROVED as assessments only) informed this ADR: `mod004-foundation-architecture-evidence-retry-20261017-1` and `mod004-source-grounded-architecture-opus-20261017-1`. They are assessment evidence and do not weaken any source requirement. They differ: the first says code and migrations cannot start until the module is Ready; the second says a bounded PostgreSQL-isolation first slice can start once the spec and an ADR exist.

**Gate position.** Common ground: the documents and ADR gate comes before any code. Whether code may start before the module is Ready is **OPEN**. It is not decided here and this ADR does not choose the stricter or the looser reading. It is to be resolved by citing the EIP §8 Ready rule (EIP ¶749-750, with unlock rule EIP ¶773), the capability manifest (EIP ¶754) and EIP §9.1 (¶880-883), and checking the module's screens and scope. Nothing in this ADR asserts implementation is authorized.

### Review history (informational; this is not a `Review` header)
- `mod004-spec-adr0002-opus-review-20261017` (bound Opus review of the two-file write `mod004-spec-adr0002-sonnet-20261017`): OUTCOME CHANGES_REQUESTED. Preserved.
- `mod004-documents-adr-opus-review-20261017` (read-only Opus review): OUTCOME CHANGES_REQUESTED. Preserved.
- `mod004-spec-adr0002-remediation-opus-review-20261017` (bound Opus review of the first remediation `mod004-spec-adr0002-remediation-sonnet-20261017`): OUTCOME CHANGES_REQUESTED. Preserved.
- This second and final bounded remediation responds to all three. It is not a re-review, grants no retroactive approval and approves nothing. A new independent bound Opus review and exact-SHA CI remain required before any acceptance change.

## Decision
Marking: **[SRC]** means mandated by the cited source paragraph. **[INFERENCE]** means an engineering reading extending a source paragraph; flagged so review can challenge it. **[PROPOSAL]** means a concrete engineering choice proposed here with rationale; it is not an owner business-policy decision and can change at independent review.

### D1. Roles and ownership (TSD ¶743, ¶1208, ¶1240)
1. [SRC] DDL and migrations run as a non-runtime owner role. Runtime roles do not own tenant tables (TSD ¶743).
2. [SRC] TSD ¶743 states the flags for `veyro_app` and worker roles: LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS. [INFERENCE] Extending these flags to the control-plane runtime and worker roles is an engineering inference; TSD ¶743 names the product-plane roles, and ¶1208/¶1969 require only a runtime role "separate from product plane". Control-plane roles are separate from the product-plane `veyro_app` role.
3. [PROPOSAL] Names: migration owner `veyro_cp_migrator` (non-superuser, not used at runtime); runtime `veyro_cp_app`; worker `veyro_cp_worker`; platform-scope owner `veyro_cp_platform` (NOLOGIN, NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE; see D6). Rationale: the sources do not name control-plane roles.
4. [SRC] The control plane is a separate database from the product plane: "Control-plane PostgreSQL database; module-prefixed tables; separate runtime role from product plane" (¶1208; ¶1969). [PROPOSAL] Local container for tests, no managed cloud, and product-plane roles hold no grants there.

### D2. Tables and RLS (TSD ¶744, ¶753, ¶1236, ¶1239)
Tenant-owned tables have mandatory FORCE RLS, runtime roles are NOBYPASSRLS, and runtime roles hold no direct cross-tenant grants. These apply to tenant tables only; whether platform_scope tables use RLS is OPEN (D6).
1. [SRC] Every tenant-owned table has `tenant_id UUID NOT NULL`, `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`, and no grant to PUBLIC. Tenant tables keep FORCE RLS without exception.
2. [PROPOSAL] Module-prefixed tables `plt01_*` for Organization, LegalEntity, Brand, Region, Location, Department, CostCenter, TenantConfiguration, lifecycle history, outbox. Tenant registry and placement are platform_scope (D6).
3. [SRC] Tenant-leading indexes for primary list/detail paths; external/provider identifiers unique per tenant/provider; aggregate version supports optimistic concurrency (¶1239). [PROPOSAL] Composite unique `(tenant_id, id)`, composite foreign keys `(tenant_id, parent_id)` so a row cannot reference another tenant's parent, and `version bigint NOT NULL` checked by `WHERE version = :expected`.
4. [PROPOSAL] Lifecycle history tables are append-only (no UPDATE/DELETE/TRUNCATE grant to runtime roles), supporting R07 history without rewrite.

### D3. Policies fail closed (TSD ¶745)
[SRC] Policies compare `tenant_id` to a transaction-local value and fail closed on missing/invalid context. [PROPOSAL] One policy per tenant table `TO veyro_cp_app, veyro_cp_worker` with both `USING` and `WITH CHECK`:
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`

Fail-closed contract: missing or empty context yields zero rows (the comparison is NULL). Invalid context may raise a cast error **or** yield zero rows, depending on whether and when the planner evaluates the expression (for example an empty table may never evaluate it). The ADR does not promise that an invalid UUID always raises. The invariant is: **missing or invalid context may error or return zero rows, and never returns unrestricted rows.** Tests assert "error or zero rows", never a specific error. No tenant-table policy uses `OR true`, a role-membership bypass or a function that can return unrestricted access.

**Trust statement.** The RLS policy trusts the integrity of the `app.tenant_id` setting. The database does not authenticate who set it. Therefore the context-setting primitive (D4) and deny-by-default grants (no PUBLIC, no TRUNCATE/REFERENCES, no owner membership, no unreviewed SECURITY DEFINER, D5) are part of the trusted boundary, not merely application hygiene.

### D4. Transaction-local context and pooling (TSD ¶746, ¶1950)
1. [SRC] Every request or worker command opens an explicit transaction, sets `app.tenant_id`, `app.actor_id` and `app.correlation_id` transaction-locally (`SET LOCAL`), then runs all tenant SQL. Session-level SET is forbidden with pooled connections (TSD ¶746).
2. **PostgreSQL does not prohibit a runtime role from running `SET app.tenant_id = ...`**: a custom GUC with a dotted name is user-settable by any role. This ADR does not claim the database rejects session-level SET. The ban is enforced by (a) a source scan and lint rejecting session-level `SET app.`, `SET SESSION`, `ALTER ROLE/DATABASE ... SET app.` and `set_config(..., false)`, with no exception; (b) the single approved tenancy primitive being the only code path that sets the context, and refusing autocommit and non-UUID values; (c) pool reset on check-in (`RESET ALL`/`DISCARD ALL`) as defence in depth, never the primary control. Reset restores role- and database-level defaults, not an empty state, so a default configured through `ALTER ROLE/DATABASE ... SET app.*` would be re-applied by the reset; the D5 catalog checks therefore require `pg_db_role_setting` to hold no `app.*` entry for any role or database; and (d) reuse tests proving that a deliberately leaked session-level value does not authorize the next transaction (D9). [PROPOSAL] The primitive sets context with `set_config(name, value, true)` (the parameterized form of `SET LOCAL`).
3. [PROPOSAL] Driver and pool: psycopg 3 with psycopg_pool; PostgreSQL 17 (pinned by image digest at implementation review); hash-locked requirements. Alternatives (asyncpg, SQLAlchemy-only) are open at review. EIP ¶754 requires a reviewed capability manifest and supply-chain evidence for psycopg, PostgreSQL and any third-party capability before activation; this proposal is not that manifest.

### D5. Migration lint and review (TSD ¶747)
[SRC] A migration fails if a new tenant table lacks `tenant_id`, FORCE RLS, a policy, expected tenant-leading indexes or runtime-role negative tests, and the lint rejects SECURITY DEFINER functions unless explicitly reviewed. [PROPOSAL] Plain ordered SQL migrations applied by `veyro_cp_migrator`; a Python lint over the SQL plus live catalog assertions; a mutation corpus with one failing migration per rule. The lint and catalog assertions must also fail on:
- any TRUNCATE or REFERENCES grant to runtime roles (TRUNCATE ignores RLS);
- default privileges (`pg_default_acl`) and PUBLIC privileges on schemas, tables, sequences and functions (including the default PUBLIC EXECUTE on new functions);
- views that are not `security_invoker = true`, or any view over a tenant table unless on an explicit reviewed allowlist (banned by default);
- `pg_auth_members` showing a runtime role (`veyro_cp_app`, `veyro_cp_worker`) as a member, directly, transitively through inheritance or through a SET path, of `veyro_cp_migrator`, `veyro_cp_platform`, a table owner or any role that owns tenant or platform_scope objects (so `SET ROLE` to any of them cannot succeed);
- `pg_db_role_setting` containing any `app.*` default (for example `app.tenant_id`, `app.actor_id`, `app.correlation_id`) for any role or database, because `RESET ALL`/`DISCARD ALL` restores such defaults and would re-apply them on the next pooled checkout;
- role flags (`pg_roles`), `pg_class.relforcerowsecurity`, ownership, and `pg_proc.prosecdef`.

SECURITY DEFINER exceptions require explicit review and an allowlist entry naming the function, owner role, pinned `search_path`, EXECUTE grantees and a review ID. An unlisted SECURITY DEFINER function fails lint.

### D6. platform_scope isolation (TSD ¶753, ¶783, ¶1243) — OPEN, not acceptable until closed
[SRC] TSD ¶753 lists "explicit platform_scope tables" as a distinct item from tenant-owned tables. Cross-tenant reporting is prohibited in product-plane data paths (TSD ¶783). Support/break-glass access creates delegated actor evidence (¶1243).

**OPEN decisions in D6 (this section is a proposal, not an approved design):**
- **OPEN-D6-a:** whether platform_scope tables use RLS at all (ENABLE/FORCE RLS), or rely only on schema/grant isolation plus the function boundary.
- **OPEN-D6-b:** if they do use RLS, what policy the platform function owner `veyro_cp_platform` receives. Because `veyro_cp_platform` is NOBYPASSRLS, a table with FORCE RLS and no policy for it returns no rows, and any policy that lets it see all rows is a cross-tenant access path that needs explicit review. No permissive policy (for example `USING (true)`) is proposed or implied here, and none is to be added without a recorded decision.
Until both are closed, the platform_scope structure below is not verified, and nothing in this ADR should be read as choosing a permissive policy.

[PROPOSAL, safe candidate design] Tenant-table RLS is not weakened: tenant-owned tables keep mandatory FORCE RLS, runtime roles are NOBYPASSRLS, and no runtime role has a direct cross-tenant grant. platform_scope tables (tenant registry, placement, interim platform access log) are not tenant tables:
1. They live in a separate schema (`plt01_platform`), owned by `veyro_cp_migrator`, and are allowlisted in lint as platform_scope. The tenant-table policy (D3) is not attached to them and no `OR true` policy is introduced anywhere; the RLS treatment of these tables is OPEN-D6-a/b above.
2. Deny by default: no direct grant on those tables or schema to `veyro_cp_app`, `veyro_cp_worker`, PUBLIC or product-plane roles. Privileges on them are held only by `veyro_cp_platform` (NOLOGIN, audited platform role).
3. Runtime roles get EXECUTE only on a narrow set of reviewed, allowlisted SECURITY DEFINER command/query functions owned by `veyro_cp_platform`, with pinned `SET search_path = pg_catalog, plt01_platform`, schema-qualified references, `REVOKE EXECUTE ... FROM PUBLIC`, and typed parameters (no dynamic SQL). Each function writes its access-log row in the same transaction as its effect, so the effect cannot commit without the evidence. These functions are the SECURITY DEFINER exceptions of D5 and need review IDs.
4. Product-plane exposure of placement (TSD ¶776) is only through the stable control-plane command/query interface, never table or schema grants in the control-plane database (D1.4). The transport and consumer contract for that interface are **OPEN**.
5. Support/break-glass actors: delegated actor evidence (¶1243) is recorded in the access log; their authorization and approvals depend on MOD-007/008 and are OPEN.

**Provisioning role.** `ProvisionTenant` writes the registry (platform_scope) and tenant tables. Proposed split, with no role holding both grant sets: in one transaction `veyro_cp_app` calls the allowlisted provisioning function (which inserts the registry row and access-log row as `veyro_cp_platform` and returns the new `tenant_id`), then sets tenant context through the primitive and inserts the tenant rows under RLS. Which scoped role performs provisioning, and whether this split is acceptable, is an **engineering choice that remains OPEN before code**.

**Interim access log is not audit.** The platform access log is an engineering record. It is not a substitute for the MOD-008 immutable audit and approvals required by ¶1231 and INV-PLT-01. Building it inside MOD-004 is a seam whose permissibility depends on the unresolved cross-module sequencing decision (governance or `OWNER-*`; none exists). It is therefore OPEN and does not satisfy any audit requirement.

D6 stays OPEN: the least-privilege design above is a candidate, not an enforceable design verified against source, and the items marked OPEN (including OPEN-D6-a and OPEN-D6-b) must close at review before this ADR can be accepted. While D6 or Ready is open, this ADR is not accepted and no S1 code may start on its authority.

### D7. Placement and relocation epoch (TSD ¶776-782, ¶1240)
[SRC] Placement is a control-plane record (source cluster, target cluster, region, encryption-key assignment, relocation state); `relocation_epoch` is included in requests and events and commands with an old epoch are rejected after route switch; the staged workflow and reconciliation of row counts, control totals, outbox high-water marks, object references and projections apply before source deletion; domain code never assumes shared or dedicated. [PROPOSAL] This ADR specifies only the record structure and the epoch-rejection rule; key assignment holds a reference, never key material. Region and key values are owner-reserved. There is no encryption-key assignment command in ¶1237, and durable workflow orchestration (¶1216) has no complete owner or design: both OPEN.

### D8. Command/query contracts, outbox, invariants, runbook (TSD ¶1214-1216, ¶1237-1245, ¶10557-10558)
1. [SRC] Domain command/query interface, no direct table access. Commands ProvisionTenant, ActivateTenant, SuspendTenant, ChangeOrgHierarchy, AssignRegion, RelocateTenant, ArchiveTenant each declare permission, idempotency, expected aggregate version and transaction boundary.
2. [SRC] Transactional outbox for state changes with idempotent consumers; events tenant.provisioned, tenant.activated, tenant.suspended, organization.updated, location.opened, brand.created. [PROPOSAL] `plt01_outbox` is tenant-scoped, written in the command transaction, envelope carries tenant_id, actor_id, correlation_id, aggregate version and relocation_epoch. The relay and bus belong to MOD-010 (which depends on MOD-004); sequencing is unresolved.
3. Source gaps are recorded, not filled: R01 and R04 name deletion, cloning and templates but ¶1237 has no delete/clone/template commands; ¶1206 has no archived/deleted/relocated events; published `brand.created` and `location.opened` have no matching commands; there is no maintenance command for LegalEntity, Department, CostCenter or TenantConfiguration; ¶1238 read models cover four of nine entities. A later ADR must decide these before code.
4. [SRC] Invariant/property tests for each state transition, API/event contract tests, tenant-isolation negative tests, INV-PLT-01 evidence, and runbook RB-PLT-01 (stuck commands, reconciliation, dependency outage, repair without history rewrite). Destructive lifecycle actions require approvals, retention checks and an immutable audit record (¶1231).
5. Other §10.1 obligations with no design and no implementation (all OPEN): required outcomes ¶1233-1234; stale read models carry freshness and "cannot authorize a consequence-bearing mutation beyond budget" (¶1242); Tier-1 control path 99.95%+ and p95 <100 ms (¶1244); AI tool policy before execution (TSD ¶771).

### D9. Required isolation tests (TSD ¶748, ¶1950, ¶1958)
Synthetic fixtures only (generated UUIDs, "Synthetic Tenant A/B/C"; no real customer or member data). Obligations, not evidence:
- actual-runtime-role queries with no application filter for SELECT/UPDATE/DELETE return no cross-tenant rows; INSERT with a foreign tenant_id is rejected;
- missing/empty/invalid context never returns unrestricted rows (error or zero rows accepted; no specific error asserted);
- `DISABLE RLS` and `SET ROLE` to the owner fail for the runtime role;
- session-level SET of `app.tenant_id` is **not** expected to be rejected by PostgreSQL. Tests prove instead that the source scan/lint flags it, the primitive refuses it, and a deliberately leaked session-level value in a pooled connection does not authorize the next transaction (pool reset and reuse tests, including the same backend PID across tenants and mid-transaction exceptions);
- a property test that per-context views are disjoint and union to the full set;
- catalog assertions from D5: role flags, FORCE RLS, ownership, no TRUNCATE/REFERENCES runtime grants, default/schema/function PUBLIC privileges, security-invoker or banned views, `pg_auth_members` (runtime roles cannot SET ROLE to the owner, migrator or `veyro_cp_platform`, directly or via inheritance/SET paths), `pg_db_role_setting` (no `app.*` defaults), and the SECURITY DEFINER allowlist;
- negative tests for those catalog defects, each expected to make the catalog check fail: (1) grant `veyro_cp_platform` to `veyro_cp_app`; (2) grant it indirectly through an intermediate role with INHERIT; (3) grant it with a SET option; (4) the same three for `veyro_cp_migrator` and a table-owner role; (5) `ALTER ROLE veyro_cp_app SET app.tenant_id = '<uuid>'`; (6) `ALTER DATABASE ... SET app.tenant_id = '<uuid>'` and a role-in-database setting; plus a reuse test showing that if (5) or (6) were present, `RESET ALL`/`DISCARD ALL` would restore the value, which is why the catalog check, not the reset, is the control;
- platform_scope: runtime roles have no direct grant; only allowlisted functions are executable; each function writes its access-log row in the same transaction (rolled back together on failure). Tests for the platform_scope RLS treatment cannot be written until OPEN-D6-a/b are decided.
These are obligations only. They are not an executable scenario catalog with QA disposition and test mapping (EIP ¶881) and do not meet the EIP ¶882 minimum; that remains OPEN.
The 1,000 concurrent mixed-tenant read, noisy-neighbor and RLS-overhead tests are separate release evidence, not covered here.

### D10. First slice status
A first PostgreSQL-isolation slice (roles, one platform_scope registry, two proposed tenant tables, tenancy primitive, lint, D9 tests) is **NOT STARTED**, at the documents/ADR gate. The two tenant tables are proposed, not delivered, and are not yet named; names and columns are decided at review. No code exists and none is authorized. Later R01-R07 capabilities (lifecycle and deletion guard, full hierarchy and multi-brand, templates and inheritance, placement/region/key policy, cache/search/object-storage/event/telemetry/AI primitives, APIs, screens, load, runbook, DR) and every module-card gate remain required.

## Rationale
Choosing roles, policy shape and context handling now, in a reviewed ADR, prevents isolation primitives from being invented in code, and keeps engineering choices separate from owner authority. Real PostgreSQL in a local container exercises RLS semantics that mocks cannot. Stating plainly that RLS trusts the context-setting primitive keeps the trusted boundary explicit.

## Alternatives considered
- Shared control/product database with schema separation: rejected as the default, weaker than ¶1208 separation and harder to assert.
- Session-level tenant variable: forbidden by TSD ¶746.
- Application-filter-only isolation: rejected, does not satisfy TSD ¶748.
- Relying on BYPASSRLS or owner connections in workers: forbidden by TSD ¶743.
- Putting platform_scope tables under a permissive tenant-table policy: rejected; it would weaken tenant-table RLS.
- Building MOD-003-style foundation-only acceptance: not available, ¶1954.

## Unresolved owner-reserved choices (not decided here)
1. Regions, data-residency policy, KMS/encryption keys and any cloud or managed-PostgreSQL spend (DC-16, ¶1964; R05).
2. Lifecycle retention periods, legal/billing/retention gate criteria, deletion approvals and who approves destructive actions (R01, R07, ¶1231).
3. Business hierarchy cardinalities, brand separation extent (pricing, catalogs, domains), template and default contents, plan tiers and dedicated-placement eligibility (R02, R04, R06, TSD ¶780-781).
4. Cross-module sequencing: permissions and approvals/audit (MOD-007/008), outbox and bus (MOD-010), key management (MOD-009), billing gate (MOD-015), configuration overlap (MOD-005). Building seams inside MOD-004 (including the D6 interim access log) or re-slicing needs a governance or `OWNER-*` decision; none exists.
5. Real member data, production promotion and paid activation stay reserved to the owner.

## Source-grounded risks (no assignment, no waiver)
Per the module catalog as read in review: MOD-005/007/008/009/010/015 depend on MOD-004 while MOD-004 evidence needs them (circularity); MOD-011 depends on MOD-010; search and AI platforms are MOD-059/MOD-058 (V1.5), so ¶1946 search/AI evidence cannot come from real Foundation-wave platforms; MOD-029, MOD-016, MOD-066, MOD-070, MOD-071 and MOD-073 overlap R01/R05/R06/R07 or the Console screens. These are recorded as risks and are decided by neither this ADR nor MOD-004.md.

## Consequences
- Roles, GUC names, driver, versions and tool choices are proposals; changing them needs ADR review, not an owner record.
- Nothing here is evidence of PASS. Tests listed are obligations.
- Acceptance of this ADR needs a new independent bound Opus document review recorded as a `Review` header in a separate change, plus exact-SHA CI, and D6 closed. It is not approved by this file.

## Invariant
INV-PLT-01 (¶10557): no cross-tenant query, cache, file, event or search result is permitted; destructive lifecycle actions require approvals, retention checks and an immutable audit record.

## Next-gate checklist
1. [ ] Governance `check` and `check-change` on the changed paths.
2. [ ] New independent bound Opus document review of MOD-004.md and this ADR.
3. [ ] Exact-SHA push CI success for the commit carrying them.
4. [ ] Separate ADR approval change (Review header) after independent review; D6 closed first.
5. [ ] Cite the EIP §8 Ready rule (EIP ¶749-750, ¶773), the capability manifest (EIP ¶754) and EIP §9.1 (¶880-883), check the module's screens and scope, and resolve whether code may start before Ready. Do not assume implementation is authorized.
6. [ ] Later ADR for delete/clone/template commands, missing events, entity maintenance commands, key assignment and workflow orchestration (D8.3, D7).
7. [ ] Owner decisions or `OWNER-*` records for the unresolved list, including MOD-008 audit sequencing for D6.
8. [ ] Screen ownership resolved from the pinned UX registry and MOD-001 timing decision (EIP ¶1960) before Ready.
9. [ ] Decide the provisioning-role split and the product-plane placement interface (D6).
10. [ ] Only if item 5 permits: a bounded implementation slice with Opus exact-diff code review; a CI PostgreSQL service is a separate controlled `.github/workflows/` change; module gates follow.
