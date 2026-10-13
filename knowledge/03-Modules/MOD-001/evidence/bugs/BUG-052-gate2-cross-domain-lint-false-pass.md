---
doc: BUG-052
module: MOD-001
status: OPEN
priority: P0
requirement: GOV-01-R04
scenarios: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
---

# BUG-052 — Gate-2 cross-domain dependency/SQL lint can falsely PASS

Found by the first fresh independent Opus code review on 2026-10-05. The gate-2 validator returns exit-0 PASS for a cross-domain raw table reference after `public.` qualification or case change (R1-F01/P0), violating TSD §24.1 and blocking SCN-MOD001-007. Seven P1s expose further scan/coverage and input-contract failures. Full reproduction, all 21 findings (P0=1/P1=7/P2=6/P3=7), severity rationale, snapshot hashes, and probe output: `knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1-2026-10-05.md`.

Status: **OPEN — BLOCKS gate-2 assurance and scenario promotion.** The four scenarios remain unpromoted; real-tree ownership of the six unclaimed scaffolds remains deferred per `GATE2-ARCHITECTURE-DECISION-2026-10-05.md`. No remediation or re-review has occurred. Historical SCN-070 five-review cap and DOM-002 interrupted round 5 are unrelated and unchanged.

Next: Opus root-cause/contract strategy for P0/P1, bounded implementation with decisive negative tests, then fresh independent code review within this unit's own convergence budget. Do not treat 90/90 unit tests or fixture evidence as PASS.
