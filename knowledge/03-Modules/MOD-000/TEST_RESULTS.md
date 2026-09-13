---
doc: MOD-000_TEST_RESULTS
status: LIVE
updated: 2026-09-13 (Phase 9 row added, fourth Gatekeeper pass Editorial finding — this index had no Phase 9 row and never had a Phase 2 row; both real gaps, same "stale index" species this file's own 2026-09-12 update note already names)
---

# MOD-000 — Test Results (index)

Appendix D field: "Deterministic automated/integration/E2E results and run references."

| Phase | What | Result | Evidence |
|---|---|---|---|
| Phase 1 | 19 deterministic/automated scenarios | **13 PASS, 5 BLOCKED (artifact-pending), 1 PARTIAL-SCOPE (046), 1 NOT_APPLICABLE (090), 0 FAIL** — corrected 2026-09-05 (final Phase 5 re-review NF-1): this row still published the pre-F5-022 count after the catalog's own Phase 1 Final Matrix was fixed 2026-09-04; F5-022 in `CR-MOD000-001.md` was marked FIXED when only the catalog itself had actually been corrected, not this index | `evidence/scenario-execution/phase1/TEST_RUN_PHASE1_2026-09-01.md`; authoritative matrix: `SCENARIO_CATALOG.md` §"Phase 1 Final Matrix" |
| Phase 2 | 7 TestSprite commands, strictly offline scope | PASS, 0 spend, credit balance unchanged (550 before/after) | `evidence/scenario-execution/phase2/TEST_RUN_PHASE2_2026-09-01.md` |
| Phase 3 | 26 negative/fail-closed drills | 21 PASS, 5 BLOCKED (precondition/mechanism-absent), 0 FAIL | `evidence/scenario-execution/phase3/TEST_RUN_PHASE3_2026-09-04.md` |
| Phase 4 | Execution reconciliation of Phases 1-3 | PASS | `evidence/scenario-execution/phase4/PHASE4_RECONCILIATION_2026-09-04.md` |
| Catalog validator | Structural integrity of the 95-scenario catalog | PASS, 0 errors | `scenario-catalog/evidence/VALIDATOR_PHASE5_REWRITTEN_2026-09-04.txt` (latest) |
| Evidence-integrity checker | Broken-reference/bug-linkage/staleness scan | PASS | `evidence/scenario-execution/phase3/raw/` (latest run) |
| Phase 5 | Independent code/config review, 5 rounds | APPROVED, 0 P0/P1 | `evidence/code-review/CR-MOD000-001.md` |
| Phase 6 | Real manual QA, 7 required scenarios | PASS, 0 P0/P1 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE6_2026-09-05.md` |
| Phase 7 | Security/performance/resilience assurance, Bash guard live activation | PASS (2026-09-08, after owner activation + 14/14 live-test matrix) | `evidence/security/BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md` |
| Phase 8 | Cumulative regression across all 95 scenarios and Phases 1-7, closeout-corrected | PASS (2026-09-12) — all 95 scenarios resolve to exactly one canonical disposition (76 PASS/14 BLOCKED/3 OWNER_ASSISTED/2 NOT_APPLICABLE/0 FAIL); BUG-024 (P1, closed) and BUG-025 (P2, open, non-blocking) found; Notion Scenario DB fully reconciled (95/95 verified, 46 corrected) | `evidence/scenario-execution/phase8/PHASE8_CANONICAL_95_MATRIX_2026-09-12.md` |
| Bash guard automated suite (current) | 194 fixture tests across all bypass classes | PASS, 194/194 (re-confirmed Phase 8/9) | `.claude/security/tests/test_bash_guard.py` |
| Phase 9 | Fresh-session restoration proof — durable-sources-only state reconstruction, independent Gatekeeper review | **PASS (2026-09-13).** BUG-026 found and fixed. Nine independent fresh-context Gatekeeper rounds ran; the ninth returned APPROVED, P0=0/P1=0, independently reconfirming every restoration claim. Phase 10 legally unlocked. | `evidence/scenario-execution/phase9/PHASE9_FRESH_SESSION_RESTORATION_PROOF_2026-09-12.md` |

0 P0, 0 FAIL across all deterministic runs to date. Full per-scenario
detail lives in the referenced files, not duplicated here. **This index
was found stale during Phase 8's own regression pass** — it had not
been updated since Phase 4 (2026-09-05) despite Phases 5-8 all
completing since, an instance of exactly the "stale Phase status"
propagation gap Phase 8 exists to catch; corrected here, not silently
left.
