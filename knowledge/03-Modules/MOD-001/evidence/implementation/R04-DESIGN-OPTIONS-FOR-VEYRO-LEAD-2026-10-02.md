---
doc: R04-DESIGN-OPTIONS-FOR-VEYRO-LEAD
module: MOD-001
requirement: GOV-01-R04 critical slice (RLS lint + permission lint)
prepared_by: veyro-critical-engineer (Opus, claude-opus-5-5) — options only
date: 2026-10-02
status: D1/D2 DECIDED by ADR-009 (implemented); D3/D4 DECIDED by ADR-010 (implementation pending). Options below are historical.
---

# R04 gate design decisions that need `veyro-lead`

R1 security review (`evidence/security/R04-CRITICAL-SLICE-SECURITY-REVIEW-R1-2026-10-02.md`)
asked for a recorded `veyro-lead` decision on the permission-gate contract
before CI wiring. The implementing role prepares options; it does not
approve architecture: architecture calls route to `veyro-lead` (ADR-005
Decision 1; `veyro-lead` agent definition). Until decided, the tool keeps the most
restrictive behaviour listed as "current".

## D1 — Public / unauthenticated endpoints in the permission gate — DECIDED: ADR-009 D4 (authentication classes + two-key match + security consistency, no exemption); options below are historical

TSD §24.1: "API commands/queries declare action/resource/scope". TSD
§8.4 offers no "public" scope. Current: no exemption mechanism, so a
health check or login endpoint cannot pass.

| Option | Shape | For | Against |
|---|---|---|---|
| A (current) | none; every operation declares a registered triple | zero bypass surface | real public endpoints (health, login, OIDC callback) cannot pass; pressure to invent fake permissions |
| B | `x-veyro-public: {"reason": "...", "approval": "ADR-NNN"}` on the operation, mutually exclusive with `x-veyro-permission` | explicit, reviewable in the diff, same audit pattern as the RLS manifest | each public endpoint is a per-operation decision in the contract; spread out |
| C | committed `contracts/permissions/public-operations.json` listing operationIds with reason + approval | one reviewable list, easy to audit growth | operationId drift; a second file to keep in sync |
| D | dedicated platform permissions (e.g. `platform.health.read`, scope `tenant`) | no new mechanism | semantically false for unauthenticated calls; misleads audit evidence |

Implementer's view (non-binding): B or C; D misrepresents authorization.

## D2 — Contract format, locations and extension key — DECIDED: ADR-009 D1-D3 (3.1.x JSON, `contracts/permissions/registry.json`, `x-veyro-permission`); text below historical

Current (proposed by Slice 6, not baseline text): JSON-only OpenAPI
3.0.x/3.1.x under `contracts/openapi/`; registry
`contracts/permissions/registry.json`; operation key
`x-veyro-permission` with exactly `action`/`resource`/`scope`. YAML is an
ERROR (no YAML dependency qualified). 3.2 is an ERROR until its
`query`/`additionalOperations` are scanned. Options: confirm as is; allow
YAML (needs a qualified parser dependency, DC-19); adopt 3.2 (extend the
scan); rename paths/key.

## D3 — RLS non-tenant exemption manifest location — DECIDED by ADR-010 D3 (options below historical)

Current: `--non-tenant-manifest <path>` takes a committed JSON file
(`{"version": 1, "non_tenant_tables": {"schema.table": {"reason", "approval"}}}`,
approval must be `ADR-NNN`/`OWN-NNN`); the command-line
`--non-tenant-table` flag was removed so exemptions cannot live only in a
CI command line. No real manifest is committed (no real schema exists).
Decision needed: canonical path (e.g. `backend/migrations/non-tenant-tables.json`
or `contracts/rls/non-tenant-tables.json`) and whether approval references
must resolve to existing ADR/OWN records (a further check, not built).

## D4 — Canonical tenant predicate (constrains every future module) — DECIDED by ADR-010 D4 (options below historical)

To close the tautology finding the RLS gate now requires every permissive
policy reachable by the runtime role to be exactly Postgres's deparse of
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`
(USING and effective WITH CHECK). Consequences for MOD-004+: the GUC name
`app.tenant_id` and this predicate become the contract; extra narrowing
goes in RESTRICTIVE policies; a PostgreSQL major upgrade that changes the
deparse fails closed until the constant is re-pinned. This binds MOD-004's
tenant-context design (TEN-002), so it should be confirmed or replaced by
`veyro-lead` (alternatives: a configurable allowlist of approved
predicates; or drop the predicate check and rely on the behavioural
harness, which R1 showed leaves `tenant_id IS NOT NULL` passing).
