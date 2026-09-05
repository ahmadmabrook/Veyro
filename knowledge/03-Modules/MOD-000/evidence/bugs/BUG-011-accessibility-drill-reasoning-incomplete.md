---
doc: BUG-011
status: FIXED (2026-09-05) — documentation-accuracy correction, verdict unaffected
found_date: 2026-09-05
found_by: Phase 6 real fresh-context Opus veyro-manual-qa run (FINDING-P6-01)
severity: P2
---

# BUG-011: Phase 5 accessibility evidence file's reasoning was incomplete, not just its label

## What is wrong

`knowledge/03-Modules/MOD-000/evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md`
§5 (2026-09-04) concluded VoiceOver "never ran" on the iOS Simulator and that
a preference write alone does not start it. The first half is correct; the
second is materially incomplete — that run never attempted starting the
service via `launchctl`/`kickstart`, only a raw preference write.

## Why this matters

The 2026-09-04 record implied the screen reader *cannot* be started at all
in this environment. A later Phase 6 run found it genuinely can be —
`xcrun simctl spawn <udid> launchctl start com.apple.VoiceOverTouch` starts
a real process with a moving focus cursor and real speech audio (captured
directly from the simulator's own log). A future session reading only the
2026-09-04 record would carry forward a wrong capability boundary and might
not even attempt the real activation path next time.

## What is NOT wrong

**The BLOCKED — OWNER_ASSISTED REQUIRED verdict itself was correct and
remains correct.** Starting the process is not the same as being able to
capture what it announces or drive its own gesture-based navigation — both
of those genuinely remain unavailable from this harness (no announcement
text is exposed anywhere; an injected swipe is delivered as a raw touch,
not VoiceOver's "next item" gesture). This is not a false-BLOCKED finding;
it is a correct-verdict-wrong-reasoning finding.

## Remediation applied (2026-09-05)

`CAPABILITY_DRILL_PHASE5_RERUN.md` §5 corrected — original text preserved,
a dated correction appended explaining the real activation path and the
two genuine remaining gaps (no announcement capture, no gesture-driven
navigation), pointing to the full account in
`evidence/manual-qa/CAPABILITY_DRILL_PHASE6_2026-09-05.md`.

## Affected

`CAPABILITY_DRILL_PHASE5_RERUN.md`, SCN-MOD000-043. Does not block MOD-000
certification — accessibility remains a correctly-carried-forward BLOCKED
item either way; this bug is about evidentiary accuracy, not disposition.
