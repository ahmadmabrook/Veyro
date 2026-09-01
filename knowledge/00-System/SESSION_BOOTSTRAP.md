---
doc: SESSION_BOOTSTRAP
status: LIVE
---

# Session Bootstrap — Fail-Closed

Read this first, every session, before any action. This file must let a fresh Claude session (zero prior chat context) reconstruct legal next action from disk alone.

## 1. Governing baseline identities (verify before trusting anything else)

Re-hash the four artifacts and diff against `PROJECT_INDEX.md`. If any hash mismatches, STOP — report `BLOCKED: BASELINE_INTEGRITY_FAILURE` and do not proceed.

```bash
shasum -a 256 Gym_OS_Master_Product_Blueprint_v1_English.docx
shasum -a 256 Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx
shasum -a 256 Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx
```

Expected values: `knowledge/00-System/PROJECT_INDEX.md`.

## 2. Active module + current state

Read `knowledge/00-System/CURRENT_STATE.md`. It names the active module, its gate status, and whether WIP=1 is respected.

## 3. Open defects, decisions, approvals

- Defects: `knowledge/01-Modules/<active MOD>/evidence/bugs/`
- Decisions/ADRs: `knowledge/02-Decisions/`
- External gates / owner approvals: `knowledge/03-ExternalGates/`

## 4. Handoff

Read `knowledge/00-System/CURRENT_HANDOFF.md` for exactly what the previous session left unfinished and the next legally allowed action.

## 5. Fail-closed rule

If any of the above files are missing, unreadable, or contradict each other, do not guess or invent state. Report `BLOCKED: SESSION_RESTORE_FAILURE` with the specific missing/contradictory file and stop.
