---
doc: CHUNK-27-ARCHIVE
status: ARCHIVED (2026-09-13, Phase 10 readiness, eleventh retention-rule application)
source: knowledge/00-System/CURRENT_HANDOFF.md, "What happened chunk 27" section
---

## What happened chunk 27, 2026-09-12 — Phase 8 closeout correction: all 95 scenarios resolved to exactly one canonical disposition (76 PASS/14 BLOCKED/3 OWNER_ASSISTED/2 NOT_APPLICABLE/0 FAIL); full Notion Scenario DB reconciled; BUG-025 found

Continuation of the owner's follow-up: the chunk-26 Phase 8 report used
non-canonical final categories (NOT EXECUTED, "documented limitation",
"formerly-partial", "partial-scope") instead of resolving every scenario
to exactly one of PASS/BLOCKED/OWNER_ASSISTED/NOT_APPLICABLE/FAIL, and
had folded OWNER_ASSISTED into BLOCKED. This chunk corrects both.

**All 14 previously-"NOT EXECUTED" scenarios individually re-examined,
not blanket-reclassified.** 11 resolved to **PASS** with fresh, real
evidence gathered this chunk: SCN-006/008 (real scratch bootstrap-
absence/contradiction drills — genuine missing-file and genuine-
contradiction fixtures, correct fail-closed reports produced, not
simulated); SCN-036 (the `next_review_due` overdue-check mechanism now
exists and was verified correct by direct code inspection);
SCN-064 (two real, live write attempts against both frozen-baseline path
types this chunk, both denied); SCN-068 (a real 5-pattern credential
scan, 0 hits); SCN-075 (a synthetic capability-gap drill, correctly
identified as unregistered); SCN-083 (a real audit of all 7
capabilities' declared scope against actual usage history); SCN-092 (a
synthetic gap walked through the exact 5-stage priority order,
corroborated by 6 real prior instances of this project's own tool-
building history). 3 IDs resolved to **BLOCKED** via 3 rejected self-
checks (SCN-013, SCN-060, SCN-065/066): each was attempted on Sonnet
using either the wrong drill shape or real-history analysis instead of
the specific scratch-copy construction the scenario names, and each was
explicitly rejected as a null test rather than accepted — these
scenarios name Opus/`veyro-lead`/`veyro-security-reviewer` specifically
because they are judgment calls, and self-administering a drill while
already knowing the "correct" answer repeats the exact failure mode this
project already identified and corrected for once (SCN-031's own
history, and the same reasoning a fresh `veyro-security-reviewer`
applied this same chunk when declining to self-re-run SCN-031).

**SCN-059 (PARTIAL-SCOPE) resolved to PASS** — the specific 22-pattern
`.claude/settings.json` deny list it names is no longer the primary
enforcement layer (superseded by the live Bash guard since Phase 7); 2
more of its historically-untested patterns were also closed live this
chunk (a `Write()` design-bundle attempt via the SCN-064 drill; both
`testsprite test rerun`/`testlist run`, denied as `UNKNOWN_COMMAND`).

**SCN-020 (the "documented non-blocking limitation") resolved to
BLOCKED** — a canonical status assigned for the first time to an
already-honestly-tracked gap, re-confirmed still true, not silently
resolved.

**SCN-041/043/044 reinstated as OWNER_ASSISTED, no longer folded into
BLOCKED**, per the owner's explicit instruction that the two statuses
carry different governance meaning: SCN-041 (Android AVD/system-image
provisioning — this project's own established "owner-approval-scale"
framing), SCN-043 (Accessibility — capturing real VoiceOver
announcements and driving its own gestures requires a human, not a
tooling gap), SCN-044 (Edge/device-bridge — every real option is a paid
service, and spend decisions are owner-reserved per DC-16).

**One new real defect found: BUG-025 (P2, OPEN, non-blocking).** While
determining SCN-084's true disposition, direct inspection of
`validate_capabilities.py` confirmed it never checks whether a
capability's `version`/`content_hash` has drifted since its
`approved_date` — only that the fields are non-blank. Confirmed by code-
path analysis, not a live exploited failure (no capability has ever
actually changed version in this project's history). SCN-084 itself:
BLOCKED. **[Superseded 2026-09-13, Phase 10 readiness: BUG-025 FIXED via
`capability_drift_check.py`; SCN-084 now PASS. See
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-025-*.md`.]**

**Full Notion Scenario database reconciliation.** Notion's 3-state
`Status` field cannot represent the 5-way canonical model exactly —
explicit mapping documented (`PASS → Done`; `BLOCKED`/`OWNER_ASSISTED`/
`NOT_APPLICABLE` → `Not started`, Git/`knowledge/` remains the sole
source of which of the three actually applies to a given `Not started`
row). All 95 rows verified live via SQL against the canonical matrix: 46
were divergent and corrected (13 wrongly `Done`→`Not started`, 33
wrongly `Not started`→`Done`); 49 already matched and were left
untouched, not blindly rewritten. Post-update verification, all live:
95 total rows, 95 distinct names (0 duplicates, 0 missing), 76 `Done` /
19 `Not started` — exact match to the canonical 76/19 split. **[Superseded
2026-09-13, Phase 10 readiness: re-reconciled to 82 Done / 13 Not
started after 6 scenarios closed PASS. See
`knowledge/00-System/NOTION_CONTROL_PLANE.md`.]**

**Final canonical totals: 76 PASS + 14 BLOCKED + 3 OWNER_ASSISTED + 2
NOT_APPLICABLE + 0 FAIL = 95.** All permanent regression suites re-
confirmed PASS (194/194 Bash guard tests, all 4 validators, all 4
baseline hashes unchanged). 0 remaining P0, 0 remaining P1 (BUG-024
closed last chunk; BUG-025 is P2). Full record:
`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase8/PHASE8_CANONICAL_95_MATRIX_2026-09-12.md`.
**[Totals superseded 2026-09-13, Phase 10 readiness: 82 PASS + 8 BLOCKED
+ 3 OWNER_ASSISTED + 2 NOT_APPLICABLE + 0 FAIL = 95 — see that file's own
"Phase 10 update" section.]**

**PHASE 8 GATE: PASS. PHASE 9 IS LEGALLY UNLOCKED** — not started this
chunk, per explicit instruction.
