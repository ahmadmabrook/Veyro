---
doc: MOD-000_TEST_RESULTS
status: LIVE
updated: 2026-09-05
---

# MOD-000 — Test Results (index)

Appendix D field: "Deterministic automated/integration/E2E results and run references."

| Phase | What | Result | Evidence |
|---|---|---|---|
| Phase 1 | 19 deterministic/automated scenarios | **13 PASS, 5 BLOCKED (artifact-pending), 1 PARTIAL-SCOPE (046), 1 NOT_APPLICABLE (090), 0 FAIL** — corrected 2026-09-05 (final Phase 5 re-review NF-1): this row still published the pre-F5-022 count after the catalog's own Phase 1 Final Matrix was fixed 2026-09-04; F5-022 in `CR-MOD000-001.md` was marked FIXED when only the catalog itself had actually been corrected, not this index | `evidence/scenario-execution/phase1/TEST_RUN_PHASE1_2026-09-01.md`; authoritative matrix: `SCENARIO_CATALOG.md` §"Phase 1 Final Matrix" |
| Phase 3 | 26 negative/fail-closed drills | 21 PASS, 5 BLOCKED (precondition/mechanism-absent), 0 FAIL | `evidence/scenario-execution/phase3/TEST_RUN_PHASE3_2026-09-04.md` |
| Phase 4 | Execution reconciliation of Phases 1-3 | PASS | `evidence/scenario-execution/phase4/PHASE4_RECONCILIATION_2026-09-04.md` |
| Catalog validator | Structural integrity of the 95-scenario catalog | PASS, 0 errors | `scenario-catalog/evidence/VALIDATOR_PHASE5_REWRITTEN_2026-09-04.txt` (latest) |
| Evidence-integrity checker | Broken-reference/bug-linkage/staleness scan | PASS | `evidence/scenario-execution/phase3/raw/` (latest run) |

0 P0, 0 FAIL across all deterministic runs to date. Full per-scenario
detail lives in the referenced files, not duplicated here.
