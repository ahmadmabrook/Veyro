---
doc: MOD-000_TEST_RESULTS
status: LIVE
updated: 2026-09-05
---

# MOD-000 — Test Results (index)

Appendix D field: "Deterministic automated/integration/E2E results and run references."

| Phase | What | Result | Evidence |
|---|---|---|---|
| Phase 1 | 19 deterministic/automated scenarios | 15 PASS, 5 BLOCKED (artifact-pending), 0 FAIL | `evidence/scenario-execution/phase1/TEST_RUN_PHASE1_2026-09-01.md` |
| Phase 3 | 26 negative/fail-closed drills | 21 PASS, 5 BLOCKED (precondition/mechanism-absent), 0 FAIL | `evidence/scenario-execution/phase3/TEST_RUN_PHASE3_2026-09-04.md` |
| Phase 4 | Execution reconciliation of Phases 1-3 | PASS | `evidence/scenario-execution/phase4/PHASE4_RECONCILIATION_2026-09-04.md` |
| Catalog validator | Structural integrity of the 95-scenario catalog | PASS, 0 errors | `scenario-catalog/evidence/VALIDATOR_PHASE5_REWRITTEN_2026-09-04.txt` (latest) |
| Evidence-integrity checker | Broken-reference/bug-linkage/staleness scan | PASS | `evidence/scenario-execution/phase3/raw/` (latest run) |

0 P0, 0 FAIL across all deterministic runs to date. Full per-scenario
detail lives in the referenced files, not duplicated here.
