---
doc: BUG-042
status: CLOSED
---

# BUG-042 — Session-restore documentation staleness (CAP-007/BUG-035/next-action)

**Module:** MOD-000 (durable-state documentation)
**Severity:** P2 (session-restore-misleading, non-blocking, no false-clean
risk — every affected file's underlying evidence-of-record was already
correct; only descriptive/summary text had drifted)
**Status:** CLOSED (2026-09-30), same session as filing.

## Summary

Session-restore reconciliation (2026-09-30) found three durable-state
files carrying text that contradicted already-recorded decisions/evidence:

1. `knowledge/00-System/PROJECT_INDEX.md`'s MOD-001 Active-Module line
   still said implementation was gated on `BUG-035` (BLOCKED) with
   "slices 1-2 complete," though `BUG-035` was CLOSED 2026-09-25 (Round
   5, `RULE-001`..`009` APPROVED/ACTIVE) and 5 slices were complete as
   of 2026-09-29.
2. `knowledge/00-System/SESSION_BOOTSTRAP.md` described CAP-007's Bash
   `PreToolUse` guard as "live"/"active since 2026-09-08," though CAP-007
   was retired 2026-09-28 per `OWN-006`/`ADR-007` (commit `058ed27`) —
   independently confirmed this session by direct inspection:
   `.claude/security/bash_guard.py` is now an inert 843-byte stub, and
   `.claude/settings.json` has no `PreToolUse` hook (`Bash(*)` allow,
   empty deny, `bypassPermissions`).
3. `knowledge/00-System/CURRENT_HANDOFF.md` chunk 64's "Next legally
   allowed action" paragraph read as live to a session reading it
   without chunk 65 above it (chunk 65 is newer and already executed
   option (a), and separately closed `BUG-037`, which that paragraph
   still named open); and the file's literal last lines (a pre-Phase-8,
   pre-MOD-001-activation "MOD-001 remains locked. WIP=1, MOD-000 only."
   snapshot) sat at the physical end of the file with no terminal
   marker.

## Fix

All three fixed with inline corrections that preserve the original
historical text (not deleted or rewritten), each citing an
already-existing decision or evidence file — no new owner approval
fabricated, no governing baseline artifact touched, no governance
policy/model routing/tool permission changed. A related, previously
undocumented fact was also recorded: system `python3` (3.9.6 on this
host) fails `verify_baselines.py` outright (`TypeError` on the script's
`str | None` PEP 604 syntax, which needs Python 3.10+); `SESSION_BOOTSTRAP.md`
now points to `backend/.venv/bin/python` instead.

A fourth stale statement (`.claude/settings.json`'s `SessionStart` hook
still naming "MOD-000 control plane... WIP=1, MOD-000 only") was found
and a fix drafted; the first attempt returned a `toolDenialKind:
"permission-rule"` error, a mechanical/rule-based denial, not confirmed
evidence of a human reviewing and refusing that specific prompt (the
original wording here overclaimed "the user declined"). A later
same-day recovery continuation retried the identical edit and it
succeeded — `.claude/settings.json` now carries the corrected text.
Item CLOSED, not left open.

Full detail, validator re-run results, and the exact before/after text
for every fix: `knowledge/03-Modules/MOD-000/evidence/session-restore/SESSION_RESTORE_RECONCILIATION_2026-09-30.md`.

## Verification

`backend/.venv/bin/python knowledge/00-System/verify_baselines.py` — PASS
(4/4). `validate_capabilities.py` — PASS (7/7 APPROVED).
`tools/validate_repo_skeleton.py`, `tools/validate_baseline_binding.py`,
`tools/validate_capability_manifest.py` (MOD-000 + MOD-001 manifests),
`tools/validate_migration_ordering.py` — all PASS. `git rev-parse HEAD`
== `origin/main` (`e516bed`) confirmed unchanged before and after (all
fixes are uncommitted working-tree edits, per explicit instruction not
to commit this package).
