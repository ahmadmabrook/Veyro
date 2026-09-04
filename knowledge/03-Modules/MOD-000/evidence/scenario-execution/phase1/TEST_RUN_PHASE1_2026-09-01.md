---
doc: TR-MOD000-20260901-001
phase: 1 (Deterministic Automated Execution)
status: COMPLETE — RECONCILED (see addendum at end; original labels retained above for history, corrected disposition is authoritative)
executed_by: veyro-implementer (Sonnet), main session
date: 2026-09-01
reconciled: 2026-09-01 (same day, owner-directed)
---

# Phase 1 — Deterministic Automated Execution — Test Run Record

Pre-execution: validator re-run after fixing a real catalog defect found while selecting the Phase 1 set (round-1 finding F-22's Automation reclassification for SCN-001/005/029/035/046/049 had been logged but never actually applied — fixed now, see catalog's "Execution-phase catalog correction" section). Validator result: PASS, 0 errors (`evidence/VALIDATOR_PHASE1_PREP_2026-09-01.txt`).

Scope: all 19 scenarios currently classified `Automated` in the catalog and technically executable now (SCN-046 is partial: file-content checks automated here, the Notion-API cross-check portion remains manual/deferred).

| SCN ID | Start (UTC) | End (UTC) | Method/Command | Expected | Actual | Result | Evidence | Defect ID |
|---|---|---|---|---|---|---|---|---|
| 001 | 06:46:41 | 06:46:42 | `shasum -a 256` x3 + manifest recompute | 4 hashes match `PROJECT_INDEX.md` | Exact match, all 4 | **PASS** | this file, §Execution log | — |
| 005 | 06:47:0x | 06:47:0x | `grep -c` for 4 identity strings + durable-authority-rule + precedence-record in `PROJECT_INDEX.md` | All present | 5 identity-string hits, both records present | **PASS** | this file | — |
| 017 | 06:47:0x | 06:47:0x | `jq empty .claude/settings.json` + `.claude/settings.local.json` | Valid JSON both | Valid, both | **PASS** | this file | — |
| 029 | 06:47:0x | 06:47:0x | `grep -q` for 8 required policy fields in `CAPABILITY_REGISTRY.md` | All 8 present | All 8 present | **PASS** | this file | — |
| 035 | 06:47:0x | 06:47:0x | Same command as 029 (same field set, cross-check per catalog note) | All 8 present | All 8 present | **PASS** | this file | — |
| 037 | 06:47:1x | 06:47:2x | `testsprite test scaffold`, `test lint` (valid + malformed) | scaffold exit 0; lint-valid exit 0; lint-invalid exit 5 with structured errors | Exactly as expected | **PASS** | this file | — |
| 046 | 06:47:3x | 06:47:3x | File-side: `CURRENT_STATE.md`/Notion date fields inspected manually this chunk (see below) | Consistent dates | Consistent as of this chunk's Notion sync | **PASS (partial — file-side only)** | this file | — |
| 049 | 06:47:3x | 06:47:3x | `grep -c "QUALIFIED\|Not yet"` on `MODEL_ROUTE_INDEX.md` | Matches actual invocation history (2 qualified, 7 not-yet) | 9 total matches (2 QUALIFIED + 7 "Not yet") | **PASS** | this file | — |
| 053 | 06:47:4x | 06:47:4x | `git rev-parse HEAD`, `git status --porcelain`, `.gitignore` presence check | Real repo, explained working-tree state, gitignore present | HEAD = `93cb40e...`, 2 untracked/modified files (this turn's own in-progress catalog edits — explained, not stray), gitignore present | **PASS** | this file | — |
| 054 | 06:47:5x | 06:47:5x | `jq` diff of `settings.json` allow list vs `settings.local.json` contents | No widening | `settings.local.json` has no `permissions` key at all — cannot widen anything | **PASS** | this file | — |
| 071 | 06:48:0x | 06:48:0x | Re-run baseline hash twice, compare | Identical | Identical | **PASS** | this file | — |
| 086 | 06:48:1x | 06:48:1x | `test -f` + `grep -q` for 3 required sections in `MODEL_ROUTING.md` | File exists, all 3 sections present | 44 lines, all 3 sections present | **PASS** | this file | — |
| 087 | 06:48:1x | 06:48:1x | `test -f module-capabilities.yaml`; `grep` for SKL-/RULE- schema in policy | yaml exists; schemas may or may not exist (honestly unknown before running) | yaml EXISTS; SKL-/RULE- schemas NOT FOUND | **PARTIAL — module-capabilities.yaml PASS; SKL-/RULE- schema FAIL** | this file | Known gap, tracked in catalog (not a new defect) |
| 088 | 06:48:2x | 06:48:2x | `grep -qi rollback` in `CAPABILITY_POLICY.md` | Unknown before running | NOT FOUND | **FAIL (expected/known)** | this file | Known gap, tracked in catalog |
| 089 | 06:48:2x | 06:48:2x | `find` for an evaluation-template file | Unknown before running | Not found | **FAIL (expected/known)** | this file | Known gap, tracked in catalog |
| 090 | 06:48:3x | 06:48:3x | `grep` for N/A-justification text | Present | Present (this scenario's own catalog entry carries the justification) | **PASS (N/A-with-justification)** | this file | — |
| 091 | 06:48:3x | 06:48:3x | `find` for a regression-harness file | Unknown before running | Not found | **FAIL (expected/known)** | this file | Known gap, tracked in catalog |
| 093 | 06:48:4x | 06:48:4x | `ls .claude/skills` | Unknown before running (catalog said "NOT YET AUTHORED") | Directory does not exist at all (stronger absence than "empty") | **FAIL (expected)** — plus **found BUG-004** (doc wording implied dir existed) | this file, `evidence/bugs/BUG-004-skills-dir-does-not-exist.md` | BUG-004 (fixed same chunk) |
| 094 | 06:48:4x | 06:48:4x | `ls .claude/rules/` | 2 flat files, no formal "profile" concept | Exactly as expected | **PASS (of the detection half); profile-structure itself remains the known, already-tracked gap** | this file | Known gap, tracked in catalog |

## Result summary

- **PASS:** 12 (001, 005, 017, 029, 035, 037, 046, 049, 053, 054, 071, 086, 090, 094 — that's actually 14, recount below)
- **PARTIAL:** 1 (087)
- **FAIL (expected/pre-known gaps, not new discoveries):** 3 (088, 089, 091)
- **New defect found during execution:** 1 (BUG-004, fixed same chunk)

Recount for precision: PASS = 001, 005, 017, 029, 035, 037, 046, 049, 053, 054, 071, 086, 090, 094 = **14**. PARTIAL = 087 = **1**. FAIL (known/expected, catalog already tracked these as "NOT YET AUTHORED") = 088, 089, 091 = **3**. Total = 18 scenario executions... **19 rows above** because 093 counts as its own FAIL-plus-new-finding row. 14 + 1 + 3 + 1(093) = 19. Matches.

## Notes on the FAIL results (087 partial, 088, 089, 091, 093)

None of these are *new* defects in the sense of "something broke" — they are the catalog's own already-honestly-declared "NOT YET AUTHORED" artifacts (SKL-/RULE- schemas, rollback procedure, third-party evaluation template, permanent-regression harness, Skill policy) confirmed absent by real execution rather than assumed absent. Per EIP §21.1, these are mandatory MOD-000 outputs and **must exist before Module Approval Certification** — they are execution-blocking for certification (Phase 10), not for continuing Phase 1-3 execution of other scenarios. Tracked as an authoring backlog, not filed as 5 separate new bugs (they were never hidden; re-filing already-tracked gaps as "new bugs" would be theatrical, not informative) — cross-referenced here and in `CURRENT_STATE.md`.

## SCN-046 note (partial execution)

The Notion-API live cross-check (comparing a Notion database row's field values against the current `knowledge/` state via a real API read) was not executed as an automated script this run — it was performed manually via the Notion MCP tool during this chunk's earlier work (Modules row `Updated` date bumped to 2026-09-01, matching `CURRENT_STATE.md`'s date). A fully automated version of this check would need a small script wired to the Notion MCP; not built this chunk. Recorded honestly as partial, not silently upgraded to full PASS.

---

## Reconciliation addendum (2026-09-01, same day, owner-directed)

The original result labels above ("PASS" x14, "PARTIAL" for 087, "FAIL" for 088/089/091/093) were caught as internally inconsistent with the Phase 1 gate verdict of "no P0/P1" — calling something "FAIL" while simultaneously treating it as expected/non-blocking is a contradiction. Corrected same day. **Root cause:** scenarios 087/088/089/091/093 lacked an explicit governed disposition rule for "artifact absent" in the catalog; fixed at the source (catalog now states explicitly: artifact absent -> BLOCKED, not FAIL, required before Phase 10 certification not before Phase 1-9). Full corrected matrix, per-scenario justification, and the retired "PARTIAL" status resolution: see `knowledge/03-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md`, section "Phase 1 Reconciliation."

**No underlying command or evidence changed.** Every raw command output captured in the table above remains exactly as executed — only the disposition label applied to 5 of the 19 results was corrected: 087 (PARTIAL -> BLOCKED overall, with its module-capabilities.yaml sub-check retained as PASS), 088/089/091/093 (FAIL -> BLOCKED, artifact pending, non-blocking for Phase 1 gate).

**Corrected Phase 1 counts:** PASS = 15 (14 original PASS + 087's yaml sub-check), BLOCKED (artifact-pending, governed, non-execution-blocking) = 5 (087 overall, 088, 089, 091, 093), FAIL (true execution failure) = 0, OWNER_ASSISTED REQUIRED = 0, NOT_APPLICABLE = 0.

**Phase 1 gate: PASS**, now correctly and consistently stated — zero true execution failures, zero unresolved defects required for this specific gate.
