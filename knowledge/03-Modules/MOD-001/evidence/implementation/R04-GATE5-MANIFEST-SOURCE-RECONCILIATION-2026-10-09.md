# R04 gate-5 manifest source reconciliation — 2026-10-09

Operation `23f0d8a8-687a-46ab-972d-86b29e4a7276`; sole runner, read-only source audit. Contract refresh acknowledged at the pinned hash. Governing baselines rechecked 4/4 MATCH. MOD-001 remains HIGH tier; lean checker projects 74 completed operations against initial 14, with the prior scope review current through 67 and `scopeReviewRequired=false`. No new review, scenario promotion, product code, test, or remote mutation.

## Exact source and obligation

- `IMPLEMENTATION.md` §10 binds import to the frozen eight-field `veyro-registry-data.js` rows and Appendix B ownership, with unknown/ambiguous owner failing closed. The source has IDs and domain/surface hints, **not routes, BFF queries or API-operation mappings**.
- The generated `contracts/ui/screen-registry.json` has 170 unique V1 UI IDs (Admin 85, Front Desk/POS 16, Coach 19, Member 35, Console 15); 8 V1 `SYS-*` rows are backend-only. This is an ID input, not the Appendix F manifest.
- EIP Appendix F requires `screen-contracts.yaml` rows with route, owning module/wave/domain, read/query/command, permissions, realtime and masking/offline/error-state contracts, and exact 170 equality with the frontend V1 route registry. TSD Appendix F additionally calls for validation against OpenAPI and AsyncAPI.
- Repository source inventory found only `contracts/ui/screen-registry.json` under `contracts/ui`. There is **no** `contracts/ui/screen-contracts.yaml`, frontend route registry, or OpenAPI/AsyncAPI file. `admin-web`, `frontdesk-web`, `mobile`, and `web` contain no route source files in the bounded inventory. The design registry search returned no route/read-model fields. Prototype links are not approved route contracts and cannot be inferred into manifest rows.

## Disposition

**MANDATORY_NOW:** preserve the canonical import and fail-closed gate, then implement a bounded explicit source-input contract and generator/lint that refuses missing or ambiguous route/owner/API mapping rather than emitting 170 fabricated completed rows. A subsequent governed technical mapping/route source must supply real data before full manifest, 170-way route equality, and CI proof can pass. The exact route paths and API bindings remain unresolved engineering inputs, not permission to infer a PASS or an owner stop for the whole mission. Scope estimate: one bounded source-input/generator correction before re-assessing missing mapping data; record added operation only if a new dispatch is selected. **DEFERRED:** none newly created. **OPTIONAL:** no confidence review, generic route scaffolding or aesthetic cleanup on the critical path.

The shared SCN-012/013/110 synthetic mechanics remain executed but unpromoted; SCN-118 not executed. Gate-5 review/remediation stays 0/0; the consumed gate-3 review is not reused. Historical R1-F14 and all original R04 gate-2 findings remain formally 14/14 CLOSED; MOD-001 mandatory exit remains 0/8, PR #3 approval/assurance held, SCN-070 cap and U1/U2 B HOLD unchanged.
