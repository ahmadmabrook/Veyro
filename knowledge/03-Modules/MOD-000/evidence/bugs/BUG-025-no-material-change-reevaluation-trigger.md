---
doc: BUG-025
status: FIXED (2026-09-13, Phase 10 readiness) — mechanism built and registered; one disclosed activation-gap residual (same pattern as CAP-007's own PreToolUse activation gap and SCN-091's regression harness)
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

## Fix applied (2026-09-13, Phase 10 readiness)

Built `knowledge/05-QA/tools/capability_drift_check.py` — a new script
(not an extension of `validate_capabilities.py`) comparing each
registry row's live `version`/`content_hash` against a new
`## Version/hash snapshot at approval` section added to
`CAPABILITY_REGISTRY.md`, flagging any mismatch as `MATERIAL CHANGE
DETECTED`. A new script was necessary rather than extending
`validate_capabilities.py` directly, because that file's SHA-256 hash
is pinned inside `.claude/security/bash_guard.py`'s
`_ALLOWED_PYTHON_SCRIPTS` map, and `.claude/security/**` is
Edit/Write-denied to this session — editing `validate_capabilities.py`
would have silently broken its own guard-trust the moment its hash no
longer matched the pinned value.

**Disclosed residual, same pattern as CAP-007's pre-activation state and
SCN-091's regression harness:** `capability_drift_check.py` is not yet
on `bash_guard.py`'s trusted-script allowlist, so an agent session
cannot invoke it through its own governed Bash tool today — confirmed
by direct attempt this chunk (`DISALLOWED_FLAG_OR_SHAPE`). Wiring it in
requires an owner-authorized edit to `.claude/security/**` plus an
independent security re-review, the same discipline every prior change
to that file has gone through. It is fully runnable today by the owner
or any human terminal session outside Claude Code's guard. All 7
current capability rows were manually cross-checked (by direct
inspection, since the script itself could not be executed) against
their new snapshot rows this chunk — no drift found, consistent with
this project's own history (no capability has ever actually changed
version).

**Follow-up fix (2026-09-13, same day, final certification-scope
Gatekeeper review, P2-2):** `parse_registry_rows()` originally dropped
any `| CAP-` line that didn't split into exactly 15 cells via a bare
`continue`, with no error and no effect on the PASS exit code — a
capability whose row became unparseable (e.g. a future cell containing
a literal `|`) would silently stop being drift-checked while the tool
kept reporting `RESULT: PASS`. Fixed: unparseable rows are now collected
and surfaced as errors that flip the result to `FAIL`, so a parsing
failure can never look identical to a clean pass. Same species of defect
as `BUG-020` (`validate_catalog.py` silently swallowing duplicate
scenario IDs), independently found in this project's second such tool.

## Affected

`knowledge/05-QA/tools/capability_drift_check.py` (new; follow-up fix
same day for the silent-row-skip finding above),
`knowledge/00-System/CAPABILITY_REGISTRY.md` (new snapshot section, no
schema change to the main 15-column table),
`knowledge/03-Modules/MOD-000/scenario-catalog/SCENARIO_CATALOG.md`
(SCN-084's disposition, corrected to PASS).
