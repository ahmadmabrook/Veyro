---
doc: SESSION_BOOTSTRAP
status: LIVE
---

# Session Bootstrap — Fail-Closed

Read this first, every session, before any action. This file must let a fresh Claude session (zero prior chat context) reconstruct legal next action from disk alone.

## 1. Governing baseline identities (verify before trusting anything else)

Re-hash **all four** artifacts (the 3 docx files, plus the design bundle
manifest) and diff against `PROJECT_INDEX.md`. Also confirm the four
identity strings (`VEYRO-MPB-1.0`, `Veyro TSD v1.4.1`,
`VEYRO-UX-V1-170-APPROVED`, `VEYRO-EIP-1.4.1-20260827`) are present in
`PROJECT_INDEX.md` — a hash match alone does not confirm the artifact's
declared identity/version. If any hash or identity mismatches, STOP —
report `BLOCKED: BASELINE_INTEGRITY_FAILURE` and do not proceed. (Corrected
2026-09-04, Phase 5 F5-013 — this section previously verified only 3 of 4
baselines, silently skipping the design bundle, which is exactly the
artifact BUG-001 was found in.)

```bash
shasum -a 256 Gym_OS_Master_Product_Blueprint_v1_English.docx
shasum -a 256 Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx
shasum -a 256 Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx
( cd veyro-product-experience-design && find . -type f ! -name '.DS_Store' -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 )
grep -E "VEYRO-MPB-1.0|Veyro TSD v1.4.1|VEYRO-UX-V1-170-APPROVED|VEYRO-EIP-1.4.1-20260827" knowledge/00-System/PROJECT_INDEX.md
```

Expected values: `knowledge/00-System/PROJECT_INDEX.md` (design bundle
manifest hash also recorded there and in
`knowledge/00-System/DESIGN_BUNDLE_MANIFEST.txt`).

## 2. Active module + current state

Read `knowledge/00-System/CURRENT_STATE.md`. It names the active module, its gate status, and whether WIP=1 is respected.

## 3. Open defects, decisions, approvals

- Defects: `knowledge/03-Modules/<active MOD>/evidence/bugs/`
- Decisions/ADRs: `knowledge/04-Decisions/`
- External gates: `knowledge/00-System/EXTERNAL_GATES.md` (+ detail records in `knowledge/00-System/external-gates-evidence/`)
- Owner approvals: `knowledge/00-System/OWNER_APPROVALS.md`

## 4. Handoff

Read `knowledge/00-System/CURRENT_HANDOFF.md` for exactly what the previous session left unfinished and the next legally allowed action.

## 5. Fail-closed rule

If any of the above files are missing, unreadable, or contradict each other, do not guess or invent state. Report `BLOCKED: SESSION_RESTORE_FAILURE` with the specific missing/contradictory file and stop.
