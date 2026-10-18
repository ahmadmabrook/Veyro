---
description: MOD-004 CON-04 privileged console (Internal SaaS Console) rule
paths:
  - "frontend/console/con-04-tenant-provisioning/**"
# Non-operative provisional placeholder (CON-04 only; matches no existing repository path). It is not an implementation path, route contract, approval or claim that a UI exists. Replacing or widening it requires separate review.
---

# MOD-004 CON-04 — privileged console rule

This rule itself grants no approval. It authorizes no code, UI, operation or dependency, and it does not declare MOD-004 Ready, Scenario Review passed or any capability ACTIVE. Implementation requires independently evidenced Module Ready, a qualified ACTIVE manifest, Scenario Review and the applicable owner approvals. No CON-04 implementation path exists yet; the single `paths` glob (`frontend/console/con-04-tenant-provisioning/**`) is a non-operative provisional placeholder, not an implementation path, route contract, approval or claim that a UI exists. Replacing or widening it requires separate review; do not add any other path, broad or inferred, without it.

## Authority
- Governing: `knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md` (D6, D11, D12, D14) and `knowledge/03-Modules/MOD-004/MOD-004.md` (Screens). If this file disagrees with them, they win.
- **Mapping:** CON-04 (Tenant provisioning, Internal SaaS Console) is assigned to MOD-004 UI by D14 because its primary mutation is `ProvisionTenant` (Appendix F ¶8740). Per ADR-0002 D14 and MOD-004 status, this ownership mapping is an unreviewed engineering decision outside the accepted ADR scope. It is not a passed mapping gate: no bound Opus review or exact-SHA CI is claimed for it (ADR-0002 checklist item 8 lists its independent review as not claimed). It supplies no CON-04 route or screen contract (`owning_module` and all contract fields in `contracts/ui/screen-contracts.yaml` stay null), and it does not resolve the owner decisions below (region choice, OWNER-Q2). No full D14 mapping review is recorded for any row.
- **Accepted:** D6 function-only platform_scope boundary and the closed D6.3 allowlist (`provision_tenant`, `resolve_placement`), within ADR-0002's own review and CI.
- **Proposed / OPEN:** D6.7 transport and caller authentication/authorization, D6.8 support/break-glass, D6.4 access log (OWNER-Q1 pending; default none), CON-04 route, permission and masking contracts, OWNER-Q2 (Scenario Review timing).

## Rules
1. **Privileged-console review.** Any change to CON-04 or a MOD-004 privileged-console surface requires an independent review (not the writer) against the admin/privileged-console Rule family. The MOD-004 capability-manifest row must select the Internal SaaS Console profile and bind that Rule family and its privileged-console-review checks (EIP Appendix H ¶11758, MOD-029 card ¶2853; an [INFERENCE] for MOD-004, ADR-0002 D11/D14). Until a qualified ACTIVE manifest row with that binding is independently evidenced in `contracts/engineering/module-capabilities.yaml`, the binding is unmet.
2. **Owner approvals.** Owner-reserved matters stay with the owner (DC-16): region choice, spend, paid activation, real member data, production promotion and material business or product changes. CON-04 is additionally blocked on the owner-reserved region choice. Do not infer approval from this file, from ADR text or from an assessment.
3. **Prerequisites before any CON-04 UI or live operation:** (a) MOD-007/008 authentication and authorization, which depend on MOD-004 (circularity not waived); (b) MOD-008 immutable audit and approvals (the interim access log is not audit); (c) caller-to-tenant binding and an auth/transport design reviewed for the D6.7 contract; (d) Module Ready, qualified ACTIVE manifest, Scenario Review (blocked by Appendix F ¶8741 and missing `REQUIREMENTS.md` unless OWNER-Q2 is answered Yes) and the EIP §18 ¶1167 determination.
4. **No cross-tenant access without a function.** The console reaches control-plane data only through D6.3 allowlisted functions or tenant-context transactions. A cross-tenant read or any new privileged action needs an ADR change; never a table grant, a role membership or a policy bypass. CON-01/03 (MOD-029) and CON-02 (MOD-031) are not MOD-004 UI.
5. **No support or break-glass, no destructive operations.** Do not add impersonation, break-glass, archive, delete, relocation-source-deletion or similar paths. They need MOD-008 audit or an `OWNER-*`/governance decision (D6.8, interim-log statement).
6. **No live operations or real data before the gates.** Until the prerequisites above are met and recorded, use only synthetic fixtures in a local environment. No managed cloud, production or customer target, and no real tenant or member data.
7. **Report faithfully.** Do not claim Module Ready, capability ACTIVE, Scenario Review or TestSprite PASS, or acceptance without independent evidence. Null contract fields are not PASS.

## Verification evidence required
The future privileged-console review (rule 1) must cite the concrete CON-04 file paths and their exact changed hashes, and the separately reviewed D14 mapping and CON-04 route contract. This is an obligation only: no CON-04 paths, hashes, reviewed D14 mapping or route contract exist today, and nothing here implies they do.

## Scope limit
Applies only to MOD-004 CON-04 and its privileged-console surface. It does not govern ADM-SET-01/02/06, other modules, global policy, governance, workflow, runner, catalog, registry or owner-record paths. Tenant isolation mechanics are in `mod004-rls.md`.
