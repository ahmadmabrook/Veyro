# R04 gate-5 canonical UX input selection — 2026-10-09

Operation: `cab3c627-eb12-4a7e-bc91-81c72ea99478`. Read-only contract/source reconciliation; no product edit, reviewer dispatch, scenario promotion, or module credit. The sole runner lease and active gate-5 distinct unit remain unchanged.

## Observed contract and source

- MOD-001 `IMPLEMENTATION.md` §10 imports the canonical UX export with fields `id,module,name,phase,status,roles,ar,note`; EIP Appendix F requires a generated `contracts/ui/screen-contracts.yaml` and count/route/contract lint before UI-bearing module Ready. TSD §24.1 requires the manifest to materialize from the canonical design export and validate against OpenAPI/AsyncAPI and the frontend route registry.
- `veyro-product-experience-design/project/veyro-registry-data.js` contains 186 rows; 178 are marked V1. Eight `SYS-*` V1 rows are backend-only/no-UI. The 170 V1 UI rows divide ADM 85, FD/POS 16, CCH 19, MBR 35, CON 15, matching the EIP screen total. Excluding SYS is a surface classification, not a silent count waiver.
- The current gate-5 input parser rejects the real `ADM-CC-01` ID shape with `screen registry 'screens' must be a list of Screen IDs`. Existing synthetic `SCR-001` controls do not exercise canonical import. The live tree has no generated screen manifest or frontend route registry, so the current default CLI remains fail-closed/INCONCLUSIVE, not a real-contract PASS.

## MANDATORY_NOW bounded follow-up

One bounded canonical registry input adapter: parse the approved export; select V1 UI rows by governed surface classification; preserve and validate actual canonical IDs (including `ADM-CC-01`), reject duplicate/malformed IDs, and prove the 170 count and five-surface split with deterministic positive and negative controls. Do not fabricate routes, owner-domain resolution, read models, API references, or a full `screen-contracts.yaml`. Those remain separate mandatory generator/route/contract/CI obligations before R04 certification. SCN-118 ownership edge cases remain unexecuted.

Four scope questions: requirement = EIP Appendix F / TSD §24.1 / MOD-001 Implementation §10; observed failure = current parser rejects a real canonical ID and no generated registry exists; certification dependency = real-source import/count gate before screen-contract lint can be relied upon; legal deferral = no for R04 certification, but route/API mapping and assurance are later distinct mandatory steps. Estimate one bounded implementation/verification operation; overall MOD-001 mandatory remainder remains unknown. Optional broad refactoring is excluded.

Gate-5 current review/remediation 0/0; shared SCN-012/013/110 mechanical outputs 3/3 observed but unpromoted pending qualified assurance. Gate-3 historical review authority consumed and P2-4 upstream PR #3 remains approval/assurance-held. Gate-2 originals F01–F14 are formally 14/14 CLOSED, SCN-070 five-review cap unchanged, MOD-001 exit 0/8. This selection changes no counters or review entitlement. Contract refresh was acknowledged before selection. The source/manifest boundary requires a new refresh before implementation dispatch.
