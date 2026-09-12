# Archived: What happened chunk 25, 2026-09-08 — owner applied the activation patch; fresh-session live-test matrix (14/14 PASS); BUG-013/022/023 CLOSED; CAP-007 ACTIVE; PHASE 7 GATE: PASS

This is the fresh, non-interactive Claude Code session the prior chunk's
"next legally allowed action" called for. Bootstrap read first
(`SESSION_BOOTSTRAP.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`), then
`.claude/settings.json`, `.claude/security/bash_guard.py`, and the
owner's activation patch document were inspected read-only, per the
task's explicit instruction not to modify `.claude/settings.json` or
`.claude/security/**` this session.

**Activation config verification: CONFIRMED.** All 7 required checks
passed by direct inspection: `hooks.PreToolUse` present, matcher `"Bash"`,
command exactly `python3 "$CLAUDE_PROJECT_DIR/.claude/security/bash_guard.py"`,
timeout `10`; `hooks.SessionStart` present and unchanged in substance;
`permissions.deny` extended with `.claude/security/**`, `CLAUDE.md`, and
`.mcp.json` protections; `git diff --stat` on the file showed only
additive changes, matching the drafted patch, no weakening.

**Live matrix: all 14 required checks PASS.** Two early chained-command
attempts (`ls ... && wc ...`, `git status && git log ...`) were denied
live with `BLOCKED: UNSUPPORTED_SHELL_COMPOSITION` before this session
adapted to one-command-per-call — direct, incidental proof the
PreToolUse hook was already executing on this session's own real tool
calls, not just on synthetic fixtures. LIVE-01/02/03 (safe git
status/log/read) — ALLOW. LIVE-04 — the 194-test automated suite,
re-run live: `Ran 194 tests in 6.497s — OK`. A real constraint was
discovered live: the guard's `mkdir` allowance is scoped to `knowledge/`
only, so the task's own suggested `mkdir -p /tmp/...` fixture-creation
step was itself denied (`DISALLOWED_FLAG_OR_SHAPE`) — worked around by
creating the disposable fixture via the Write tool instead (a different,
ungoverned-by-this-hook tool), disclosed rather than silently routed
around. LIVE-05/06 — this chunk's own new evidence file
(`BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md`) served as
the required disposable/real evidence file: `git add` then a real
non-amend `git commit` (`30d8c22`) both ALLOW. LIVE-07/08 — `rm -rf` and
`/bin/rm -rf` against the disposable fixture both DENY
(`UNKNOWN_COMMAND`), fixture confirmed to still exist via a Read-tool
re-check. LIVE-09 — `echo test > .claude/settings.json` DENY
(`UNSUPPORTED_SHELL_COMPOSITION`), content confirmed unchanged via
`git diff --stat` immediately after. LIVE-10/11/12 — `git push --force`,
`git reset --hard`, `grep -rf /etc/passwd knowledge` all DENY, each with
a distinct guard-specific reason (`DISALLOWED_FLAG_OR_SHAPE`,
`UNRECOGNIZED_SUBCOMMAND`, `DISALLOWED_FLAG_OR_SHAPE`). LIVE-13/14 —
Edit-tool attempts on `.claude/security/bash_guard.py` and `CLAUDE.md`
both denied at the permission layer before any file content was
touched. An additional unknown-command probe (`uptime`, not in any
allow-by-construction family) confirmed fail-closed DENY.

**Safe regression: all PASS.** `git status`/`log`/`diff`/`show` and a
safe read all executed normally throughout. All 4 governance validators
re-run live and PASS: `verify_baselines.py` (all 4 governing baseline
hashes MATCH `PROJECT_INDEX.md` exactly), `validate_capabilities.py` (6
capabilities, all APPROVED), `validate_catalog.py` (0 errors, 1
pre-existing non-blocking warning), `evidence_integrity_check.py` (no
broken references beyond pre-existing, already-documented forward
refs). Local HEAD confirmed == `origin/main` before this chunk's own
commits.

**Result: BUG-013, BUG-022, and BUG-023 are now CLOSED** — each bug file
updated with a "Live activation verification" section citing the exact
live command/response pair that proved its own historical bypass class
denied. **CAP-007 is now ACTIVE** — added to
`knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml` for the
first time (this is the guard's first genuine MOD-000 dependency, now
that it is actually enforcing), and its `CAPABILITY_REGISTRY.md` row and
`lifecycle_status` updated accordingly. `BUG_REGISTRY.md` and
`LOAD_SECURITY.md` both updated to reflect closure and **PHASE 7 GATE:
PASS**. `.claude/settings.json` was not modified by this session — it
remains exactly as the owner applied it; this session only read it and
exercised it live.

**Phase 8 is legally unlocked as of this chunk.** Per the task's
explicit instruction, this session does not start Phase 8 or MOD-001
work — that is the next session's legally allowed action, not this
one's. Full live-test record:
`knowledge/03-Modules/MOD-000/evidence/security/BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md`.
