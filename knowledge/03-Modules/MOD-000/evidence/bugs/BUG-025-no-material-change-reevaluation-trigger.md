---
doc: BUG-025
status: OPEN — real gap, non-blocking for Phase 8/9, required before Phase 10 certification
found_date: 2026-09-12
found_by: Phase 8 closeout reconciliation (this session), while determining SCN-MOD000-084's real disposition
severity: P2
---

# BUG-025: `validate_capabilities.py` never checks whether a capability's version has drifted since its approval — no material-change re-evaluation trigger exists

## What is wrong

`SCN-MOD000-084` ("Material capability change triggers mandatory
re-evaluation") requires: if an approved capability's version changes
materially, the session must not silently continue trusting the old
qualification — re-review must be triggered before further reliance.

Direct inspection of `knowledge/00-System/validate_capabilities.py`
confirms no such check exists:

- The script's per-capability field checks (read directly this chunk,
  lines 164-188) verify that `review_status` contains "approved",
  that `approved_by` is populated (unless exempted), that
  `next_review_due` is a parseable date not in the past (unless
  exempted — the mechanism `BUG`-fixing SCN-036 confirmed real), and
  that `provenance`/`version`/`content_hash` are **non-blank**.
- **Nothing compares the current `version` (or `content_hash`) value
  against the value recorded at `approved_date`/`last_reviewed_at`
  time.** `approved_date` and `last_reviewed_at` appear only in the
  schema's required-field-name list (line 76) — they are recorded, but
  never read back for a drift comparison anywhere in the script.

Concretely: if `CAPABILITY_REGISTRY.md`'s CAP-002 row had its `version`
cell edited from `0.8.0` to `0.9.0` today, with `review_status`,
`approved_by`, and `next_review_due` all left unchanged,
`validate_capabilities.py` would still report `PASS` — the version
field is non-blank, which is the only check that touches it. No
`BLOCKED`/re-review-required signal would fire.

## Why this was not caught earlier

This is a gap in a supply-chain governance tool, not a security-hook
gap — it fell outside the scope of every Bash-guard review round
(Phase 7's four-plus-Round-3 rounds all concerned the Bash surface, not
capability-lifecycle tooling) and outside Phase 5's code review rounds
(which audited evidence completeness and catalog consistency, not this
specific cross-field drift check). It surfaced now because Phase 8's
reconciliation required determining SCN-084's real, current disposition
rather than leaving it as an unexamined "not yet executed" line.

## Real-world exposure, honestly scoped

**No live exploitation has occurred.** TestSprite CLI (CAP-002) has
stayed at version 0.8.0 throughout this project's history — no
capability has ever actually undergone a material version change, so
this gap has never been silently relied upon in practice. This is a
defense-in-depth gap, not an active control failure.

## Certification impact

**P2 — non-blocking for Phase 8/9.** SCN-084 itself is Major severity,
not Blocker, and DC-19's capability supply-chain governance requirement
is about the framework existing and being correct, which this finding
shows is currently incomplete for exactly one dimension (version-drift
detection) while the rest (approval accountability, review-cadence
staleness via `next_review_due`, non-blank supply-chain fields) is
proven real and correct. Required to be fixed before Phase 10
certification (DC-19 compliance), not before Phase 8/9.

## Recommended fix (not built this chunk — reconciliation scope, not remediation scope)

Extend `validate_capabilities.py` with a check comparing each row's
current `version`/`content_hash` against a recorded
`version_at_approval`/`hash_at_approval` field (new columns would be
needed), flagging drift as requiring re-review before the row can
satisfy a manifest dependency. Not implemented this chunk — this is a
reconciliation pass identifying a real gap, not a remediation pass
building new capability-governance tooling, which would be a separately
scoped and separately authorized change.

## Affected

`knowledge/00-System/validate_capabilities.py`,
`knowledge/00-System/CAPABILITY_REGISTRY.md` (schema would need new
columns for a real fix), `knowledge/03-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md`
(SCN-084's own disposition).
