---
doc: BUG-005
status: FIXED (backfilled 2026-09-04 — the fix itself was made 2026-09-01; this durable record was missing, only a Notion Bugs row existed for it, which is a durability-rule violation now corrected)
found_date: 2026-09-01
fixed_date: 2026-09-01
found_by: Owner-directed correction pass, 2026-09-01
severity: Major
---

# BUG-005: Manual QA drill overclaimed Accessibility + Edge/device as PASS

## What was wrong

The MOD-000 manual-QA capability drill originally marked two surfaces PASS
on insufficient evidence:

- **Accessibility (VoiceOver/TalkBack):** marked PASS from an
  accessibility-tree *read*, which is not real screen-reader execution.
- **Edge/device-bridge:** marked PASS from browser viewport-resize
  emulation, which is not a real Edge simulator or device/vendor sandbox.

## Fix

Both corrected to BLOCKED on the same day (2026-09-01):
- Accessibility -> **BLOCKED — OWNER_ASSISTED REQUIRED**
- Edge/device -> **BLOCKED — NOT YET QUALIFIED**

See `knowledge/03-Modules/MOD-000/evidence/manual-qa/CAPABILITY_DRILL.md`
for the corrected drill record.

## Durability-rule note (why this file exists as of 2026-09-04)

This fix was made and mirrored to Notion (Bugs database, page
"Manual QA drill overclaimed Accessibility + Edge/device as PASS",
Status: Done) on 2026-09-01, but — unlike BUG-001 through BUG-004 — no
corresponding durable `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-*.md`
file was ever created for it. That meant this bug's record existed only in
Notion, which is a real violation of `.claude/rules/knowledge-vault-durability.md`
("Notion may be updated for the same change, but only as a mirror — never
as the first or only place a fact is recorded"). Found during Phase 4
(execution reconciliation) on 2026-09-04, while checking Notion Bugs
against local `evidence/bugs/`. No further remediation of the underlying
QA drill was needed — the fix itself was already correct and already
durably described inside `CAPABILITY_DRILL.md`; only this dedicated bug
record was missing. Backfilled now so the durable record is the true
first-class one and Notion is a proper mirror of it, not a parallel source.

No rerun needed — the corrected disposition (BLOCKED for both surfaces)
remains the current, unchanged manual-QA state as of this writing; both
surfaces are still tracked open (BLOCKED, non-blocking for Phases 1-9,
required to be either resolved or explicitly carried forward before
Phase 10 certification).
