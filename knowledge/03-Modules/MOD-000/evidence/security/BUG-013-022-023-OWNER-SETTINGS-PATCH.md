---
doc: BUG-013-022-023-OWNER-SETTINGS-PATCH
status: APPLIED AND LIVE-VERIFIED (2026-09-08) — the owner applied this patch and a fresh session ran the full 14-row live-test matrix, all PASS; BUG-013/022/023 are now CLOSED. This file is retained as the historical record of the drafted patch, not a currently-pending action.
updated: 2026-09-13 (Phase 9 restoration proof, fourth Gatekeeper pass P2-1 — this status line had gone stale since 2026-09-08, still saying the patch was drafted/not-applied and the bugs were open, after the owner applied it and a live-test matrix closed all three the same day)
---

# Owner Activation Patch — `.claude/security/bash_guard.py` PreToolUse hook

**This file is instructions for the owner to apply manually. No session
has modified, staged, or committed `.claude/settings.json` in producing
this document — that file remains exactly as the owner last edited it.**

## Why this patch exists

`.claude/settings.json`'s `permissions.deny` glob matching proved
bypassable (BUG-013 recursive delete, BUG-022 absolute-path/wrapper
bypass, BUG-023 ineffective redirection controls). `.claude/security/bash_guard.py`
(v2, allow-by-construction) closes all three classes for the Bash
surface, and has been through four independent fresh-context Opus
reviews — the fourth and final one (2026-09-08) returned **P0=0, P1=0,
verdict APPROVED FOR OWNER ACTIVATION**, conditional on this patch
including the write-protection item in Part 2 below. Full review chain:
`BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md` (rounds 1-2),
`BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md` (round 3, BLOCKED),
`BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md` (remediation),
`BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md` (final approval, this
patch's direct source).

## Part 1 — the PreToolUse hook registration

Add a `PreToolUse` array to the existing `"hooks"` object. **Exact JSON
to merge** (this is additive — it does not touch the existing
`SessionStart` array):

```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/security/bash_guard.py\"",
        "timeout": 10
      }
    ]
  }
]
```

- **Matcher**: `"Bash"` — exact tool-name match, verified against this
  installed Claude Code version's own hook contract
  (`HOOK_CONTRACT_VERIFICATION_2026-09-06.md`). No `if` pre-filter is
  used; the guard performs its own complete analysis on every Bash call.
- **Command**: invokes the guard via `$CLAUDE_PROJECT_DIR`, Claude
  Code's own project-root environment variable, so the hook resolves
  correctly regardless of the invoking session's working directory. The
  guard itself independently re-derives its own `REPO_ROOT` from
  `Path(__file__).resolve().parents[2]` for the trusted-script hash
  checks, so this is belt-and-suspenders, not the guard's only path
  resolution.
- **Timeout**: `10` seconds — added per the final reviewer's explicit
  instruction (a P2 finding showed the guard can hang indefinitely on a
  FIFO at a pinned trusted-script path; an explicit timeout bounds that
  to a fail-*open* window of exactly 10 seconds rather than an
  unbounded one — see the Known Residuals section below for why this is
  accepted, not eliminated, this pass).

## Part 2 — required protection additions to `permissions.deny`

The final reviewer determined `.claude/security/**` remaining writable
is **certification-blocking for activation** (not a code defect, but an
activation precondition): the guard's own implementation and its
pinned-hash trusted-script map live in that directory, unprotected by
the existing deny list, so an agent that can Edit `bash_guard.py` can
neutralize the whole control in one edit. Add these entries to the
existing `permissions.deny` array (they do not replace anything —
append alongside the existing `.claude/settings.json`/`.claude/rules/**`/
`.claude/agents/**` entries, which are already correct and unchanged):

```json
"Edit(.claude/security/**)",
"Write(.claude/security/**)",
"Bash(sed -i*.claude/security*)",
"Bash(*>*.claude/security*)",
"Bash(cp*.claude/security*)",
"Bash(mv*.claude/security*)",
"Bash(rm*.claude/security*)",

"Edit(CLAUDE.md)",
"Write(CLAUDE.md)",
"Bash(sed -i*CLAUDE.md*)",
"Bash(*>*CLAUDE.md*)",
"Bash(rm*CLAUDE.md*)",

"Edit(.mcp.json)",
"Write(.mcp.json)",
"Bash(sed -i*.mcp.json*)",
"Bash(*>*.mcp.json*)",
"Bash(rm*.mcp.json*)"
```

Reasoning for each, per the final reviewer's explicit per-item
determination:
- **`.claude/security/**`** — required. The single most important
  addition in this patch.
- **`CLAUDE.md`** — required. Confirmed currently absent from the deny
  list entirely (the guard covers it only as a Bash-argument path
  fragment, not for direct Edit/Write).
- **`.mcp.json`** — pre-emptive. The file does not exist yet; adding
  the deny now costs nothing and closes the window at creation time.
- **The 7 trusted `knowledge/` scripts** — deliberately **not** added
  here. Once `bash_guard.py` itself is protected, tampering with those
  scripts can only produce a hash-mismatch deny (no privilege gain);
  protecting them directly would obstruct normal evidence-tree editing
  work.
- **`CAPABILITY_POLICY.md`/`DEVELOPMENT_CONSTITUTION.md`/`PROJECT_INDEX.md`**
  — deliberately **not** added. Living governance documents that
  sessions must be able to update; `verify_baselines.py` plus Git
  history already provide tamper evidence without a hard deny.

## Part 3 — exact merge location

Both changes are additive to the existing `.claude/settings.json`
structure. The resulting file's shape (illustrative — apply the two
diffs above to the real file, do not paste this whole block over it):

```json
{
  "permissions": {
    "allow": [ /* unchanged */ ],
    "deny": [
      /* ... all existing entries, unchanged ... */,
      "Edit(.claude/security/**)",
      "Write(.claude/security/**)",
      "Bash(sed -i*.claude/security*)",
      "Bash(*>*.claude/security*)",
      "Bash(cp*.claude/security*)",
      "Bash(mv*.claude/security*)",
      "Bash(rm*.claude/security*)",
      "Edit(CLAUDE.md)",
      "Write(CLAUDE.md)",
      "Bash(sed -i*CLAUDE.md*)",
      "Bash(*>*CLAUDE.md*)",
      "Bash(rm*CLAUDE.md*)",
      "Edit(.mcp.json)",
      "Write(.mcp.json)",
      "Bash(sed -i*.mcp.json*)",
      "Bash(*>*.mcp.json*)",
      "Bash(rm*.mcp.json*)"
    ],
    "defaultMode": "default"
  },
  "hooks": {
    "SessionStart": [ /* EXACTLY as it exists today — see below, do not alter */ ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/security/bash_guard.py\"", "timeout": 10 }
        ]
      }
    ]
  }
}
```

## Part 4 — preservation of the existing `SessionStart` hook

The current `SessionStart` array (the one that prints the MOD-000
control-plane `additionalContext` banner) **must be preserved byte-for-
byte** — this patch only adds a sibling `PreToolUse` key inside the same
`"hooks"` object, it does not touch `SessionStart` in any way. After
applying, confirm `hooks.SessionStart` in the file is unchanged from
before (a diff of the applied file against the pre-patch version should
show only additions, zero deletions, inside `permissions.deny` and one
new `PreToolUse` key — nothing removed anywhere).

## Part 5 — activation and restart requirements

1. Apply Parts 1 and 2 to `.claude/settings.json` (owner action; no
   session may do this).
2. Validate the resulting file is syntactically valid JSON before
   saving (a malformed `.claude/settings.json` could disable hook
   enforcement entirely, silently).
3. **A fresh Claude Code session is required** — hooks are loaded at
   session start; an already-running session will not pick up a
   mid-session settings change.
4. In that fresh session, run the live-test matrix in Part 7 below
   *before* relying on the guard for any real work.

## Part 6 — rollback procedure

If the guard needs to be disabled after activation (a false positive
blocking legitimate work, an unforeseen issue, or an owner decision to
revert):

1. Remove the `PreToolUse` key added in Part 1 from `.claude/settings.json`
   (leave `SessionStart` and everything in `permissions` untouched,
   unless also reverting Part 2's deny additions).
2. Start a fresh Claude Code session — the removal, like the addition,
   only takes effect at session start.
3. `permissions.deny`'s existing glob patterns (pre-dating this guard)
   remain in effect regardless — rollback returns to the pre-activation
   state (deny-glob-only enforcement, the state BUG-013/022/023 were
   originally filed against), not to zero enforcement.
4. No code deletion is required for rollback — `bash_guard.py` and its
   test suite can remain in the repository inert; only the hook
   registration in `.claude/settings.json` need be removed.
5. If Part 2's protection additions are also rolled back, be aware this
   re-opens the "trusted-script pin lives in an editable file" gap this
   whole patch exists to close — rolling back Part 2 without also
   disabling the guard (Part 1) is not a safe intermediate state.

## Part 7 — exact fresh-session live-test matrix

Run every one of these in the fresh post-activation session, in order,
and confirm the actual observed result matches "expected" before
treating the guard as live-verified:

| # | Command | Expected |
|---|---|---|
| 1 | `git status` | ALLOW (executes normally) |
| 2 | `git log --oneline -5` | ALLOW |
| 3 | `cat knowledge/00-System/CLAUDE.md` (or any real repo file) | ALLOW |
| 4 | `python3 .claude/security/tests/test_bash_guard.py` | ALLOW (and reports 194/194 passing) |
| 5 | `git add knowledge/00-System/CLAUDE.md` (a real, specific, already-tracked file) | ALLOW |
| 6 | `git commit -m "test: live activation check"` (only if step 5's add is meant to be real — otherwise use a disposable scratch file instead of a real tracked one) | ALLOW |
| 7 | `rm -rf /tmp/veyro-guard-livetest` (create a disposable dir first, e.g. `mkdir -p /tmp/veyro-guard-livetest`, outside the repo) | **DENY** — confirms BUG-013's class is live-blocked |
| 8 | `/bin/rm -rf /tmp/veyro-guard-livetest` | **DENY** — confirms BUG-022's class (absolute-path bypass) is live-blocked |
| 9 | `echo test > .claude/settings.json` | **DENY** — confirms BUG-023's class (redirection) AND Part 2's new `.claude/security`/self-protection are live-blocked (this exact target also independently proves the pre-existing `.claude/settings.json` self-protection still works) |
| 10 | `git push --force` | **DENY** |
| 11 | `git reset --hard` | **DENY** |
| 12 | `grep -rf /etc/passwd knowledge` | **DENY** — confirms Round 3 P1-1's fix is live |
| 13 | Edit tool: attempt to edit `.claude/security/bash_guard.py` | **DENY** — confirms Part 2's new write-protection is live (this is an Edit-tool test, not a Bash command — the guard itself doesn't cover Edit/Write, `.claude/settings.json`'s own deny list does) |
| 14 | Edit tool: attempt to edit `CLAUDE.md` | **DENY** — confirms the new `CLAUDE.md` protection is live |

If any DENY-expected row instead allows, or any ALLOW-expected row is
incorrectly blocked, **do not consider the guard live-verified** — stop,
record the exact discrepancy, and treat it as a new, real finding
requiring its own fresh-context review before proceeding further.

## Known residuals at activation time (accepted, not silently hidden)

Per `BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`: 6 P2 findings
remain open (an unrestricted-argument gap in a different grep flag
family, a FIFO-hang risk this patch's `timeout: 10` bounds but does not
eliminate, a cwd-vs-REPO_ROOT path-resolution divergence, unquoted-`$`/
glob-expansion gaps in two argument slots, and the 5 pre-existing Round
3 P2s). None were judged activation-blocking. They should be tracked
for a future, separately-authorized remediation pass — not silently
dropped because activation proceeded.

## What activation does NOT do

Applying this patch and passing the live-test matrix makes the
enforcement **live**, but per the owner's explicit instruction,
**BUG-013, BUG-022, and BUG-023 close only after** all of: the owner
applies this patch; a fresh session starts; the PreToolUse hook is
proven to execute (matrix rows 1-6 above); live destructive fixtures
are proven denied (rows 7-12); and Part 2's write-protections are
proven live (rows 13-14). Closing the three bugs, updating
`CURRENT_STATE.md`/`CURRENT_HANDOFF.md`/`BUG_REGISTRY.md`/
`LOAD_SECURITY.md` to reflect Phase 7 PASS, and unlocking Phase 8 are
all separate, later actions — not part of applying this patch.
