---
doc: MOD-000_TESTSPRITE
status: LIVE
updated: 2026-09-05
---

# MOD-000 — TestSprite (index)

Appendix D field: "Plans/runs/results/artifacts/failure classifications."

CAP-002 (TestSprite CLI, v0.8.0) is APPROVED, **offline scope only**.
Positive/negative qualification and Phase 2 offline execution (scaffold,
lint, doctor, usage — 7 commands, 3 positive/2 negative/2 supporting) are
recorded at `knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase2/TEST_RUN_PHASE2_2026-09-01.md`.
Capability record: `knowledge/00-System/CAPABILITY_REGISTRY.md` (CAP-002 row).
Scope boundary rationale: `knowledge/05-QA/capability-evidence/CAP-002/SCOPE_NOTE.md`.

**Live cloud execution: never triggered.** Credit balance verified
unchanged (550 before, 550 after) across every phase that touched
TestSprite. `test run`/`test rerun`/`testlist run` are additionally denied
at the harness permission layer (`.claude/settings.json`), added and
live-verified during Phase 5 remediation.

No failures recorded — TestSprite has never produced a failure
classification on this project (all runs within offline scope succeeded
or correctly failed validation before billing).
