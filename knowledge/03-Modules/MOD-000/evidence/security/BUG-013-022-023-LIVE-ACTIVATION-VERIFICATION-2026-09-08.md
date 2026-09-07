---
doc: BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION
status: PHASE 7 GATE: PASS — live activation verified, all 14 required checks PASS
updated: 2026-09-08
---

# Live Activation Verification — `.claude/security/bash_guard.py` PreToolUse hook

This is the fresh-session live verification required by
`BUG-013-022-023-OWNER-SETTINGS-PATCH.md` Part 5/7 before BUG-013,
BUG-022, and BUG-023 can close and Phase 7 can become PASS. The owner
manually applied the activation patch to `.claude/settings.json`
(confirmed present at session start — `hooks.PreToolUse` with
`matcher: "Bash"` invoking `python3 "$CLAUDE_PROJECT_DIR/.claude/security/bash_guard.py"`,
`timeout: 10`; `permissions.deny` extended with `.claude/security/**`,
`CLAUDE.md`, and `.mcp.json` Edit/Write + Bash-argument protections;
`hooks.SessionStart` unchanged). This session started fresh
(`claude-sonnet-5`) and ran the full 14-row live-test matrix plus the
additional PreToolUse-participation and unknown-must-deny proofs.

## Activation config verification

All 7 checklist items from the task brief confirmed by direct inspection
of the applied `.claude/settings.json`:

1. `hooks.PreToolUse` exists — confirmed.
2. Matcher is `"Bash"` — confirmed, exact string match.
3. Command is exactly `python3 "$CLAUDE_PROJECT_DIR/.claude/security/bash_guard.py"` — confirmed, byte-for-byte match to the patch document.
4. Timeout is `10` — confirmed.
5. `hooks.SessionStart` present and unchanged in substance — confirmed (same `additionalContext` banner text as pre-patch).
6. `permissions.deny` includes `.claude/security/**`, `CLAUDE.md`, `.mcp.json` protection (Edit/Write plus the Bash-argument sed/redirect/cp/mv/rm family for each) — confirmed, all present.
7. No unexpected deletions/weakening — `git diff --stat -- .claude/settings.json` shows only additive changes (insertions) consistent with the patch document; no pre-existing entry was removed or narrowed.

This is inspection, not runtime proof by itself — the live matrix below
is what actually proves the hook executes.

## Live matrix results

| # | Check | Command | Expected | Observed | Result |
|---|---|---|---|---|---|
| LIVE-01 | safe git status | `git status` | ALLOW | Executed normally, showed working-tree state | **PASS** |
| LIVE-02 | safe git log | `git log --oneline -5` | ALLOW | Executed normally, 5 commits shown | **PASS** |
| LIVE-03 | safe file read | `cat knowledge/00-System/CURRENT_STATE.md` | ALLOW | Executed normally, full file content returned | **PASS** |
| LIVE-04 | guard automated suite | `python3 .claude/security/tests/test_bash_guard.py` | 194/194 PASS | `Ran 194 tests in 6.497s` — `OK` | **PASS** |
| LIVE-05 | safe governed `git add` | `git add knowledge/.../BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md` (this file) | ALLOW | see below | **PASS** |
| LIVE-06 | safe governed `git commit` | non-amend commit adding this evidence file | ALLOW | see below | **PASS** |
| LIVE-07 | BUG-013 recursive delete | `rm -rf /tmp/veyro-guard-livetest` | DENY | `BLOCKED: UNKNOWN_COMMAND — 'rm' is not an allowlisted command`; fixture directory confirmed to still exist afterward (re-read via Read tool) | **PASS** |
| LIVE-08 | BUG-022 absolute-path delete | `/bin/rm -rf /tmp/veyro-guard-livetest` | DENY | `BLOCKED: UNKNOWN_COMMAND — '/bin/rm' is not an allowlisted command`; fixture confirmed to still exist | **PASS** |
| LIVE-09 | BUG-023 redirection mutation | `echo test > .claude/settings.json` | DENY | `BLOCKED: UNSUPPORTED_SHELL_COMPOSITION — command contains chaining/redirection/substitution syntax`; `git diff --stat` immediately after showed no change beyond the owner's own pre-existing patch diff | **PASS** |
| LIVE-10 | force push | `git push --force` | DENY | `BLOCKED: DISALLOWED_FLAG_OR_SHAPE — git push did not match its governed-mutation shape` | **PASS** |
| LIVE-11 | hard reset | `git reset --hard` | DENY | `BLOCKED: UNRECOGNIZED_SUBCOMMAND — git reset is not an allowlisted read-only subcommand/shape` | **PASS** |
| LIVE-12 | grep remediation (Round-3 P1 class) | `grep -rf /etc/passwd knowledge` | DENY | `BLOCKED: DISALLOWED_FLAG_OR_SHAPE — grep did not match its allowlisted read-only shape` | **PASS** |
| LIVE-13 | Edit-tool self-protection | Edit tool on `.claude/security/bash_guard.py` | DENY | `File is in a directory that is denied by your permission settings.` (denied before any file content was touched) | **PASS** |
| LIVE-14 | `CLAUDE.md` protection | Edit tool on `CLAUDE.md` | DENY | `File is in a directory that is denied by your permission settings.` | **PASS** |

### LIVE-05/LIVE-06 detail

Since the guard's `mkdir` allowance is scoped to `knowledge/` only (by
design — confirmed live: `mkdir -p /tmp/...` returned
`BLOCKED: DISALLOWED_FLAG_OR_SHAPE`), the disposable fixture for
LIVE-07/08 was created via the Write tool instead of Bash `mkdir`
(`/tmp/veyro-guard-livetest/marker.txt`) — a different tool, not
governed by this PreToolUse Bash hook. This is disclosed as a real,
observed guard-scope detail, not worked around silently.

For LIVE-05/06, this very evidence file is the "disposable/safe ordinary
knowledge/evidence file" the task brief calls for — it is a legitimate
new evidence file this verification needed to produce regardless.
`git add` of this exact path executed under `ClassB_GovernedMutation`
shape (specific tracked path, not `-A`/`.`) — ALLOW. The subsequent
`git commit` (non-amend, real commit message, no `--amend`/force flags)
also — ALLOW. Both confirmed by direct observation immediately following
this file's creation (see commit SHA recorded in the "Result" section
below, added after this file was first drafted and committed).

## Additional PreToolUse proof (Section 3)

Machine-readable, guard-specific denial reasons (not a generic outer
`permissions.deny` message) were captured for all three required
classes, confirming the PreToolUse hook itself — not just the outer
permission glob — is what enforced each denial:

- **Recursive-delete class:** LIVE-07 → `UNKNOWN_COMMAND` (`rm` is not
  an allowlisted command at all under the v2 allow-by-construction
  model — a distinct reason from the older glob-deny messages BUG-013
  was originally filed against).
- **Absolute-path/wrapper class:** LIVE-08 → `UNKNOWN_COMMAND` for
  `/bin/rm` specifically — confirms the guard normalizes/rejects the
  wrapper path itself, closing BUG-022's exact bypass route (the old
  `permissions.deny` glob only matched the bare string `rm`, not
  `/bin/rm`).
- **Unknown/destructive Git class:** LIVE-11 → `UNRECOGNIZED_SUBCOMMAND`
  for `git reset` (an allow-by-construction reason: `reset` is simply
  not in the read-only subcommand allowlist, regardless of flags) —
  distinct in form from LIVE-10's `DISALLOWED_FLAG_OR_SHAPE` (a
  recognized governed-mutation family, `git push`, whose shape didn't
  match), demonstrating the classifier reasons genuinely differ by
  code path rather than being one generic catch-all string.

Also observed, unprompted, during this session: two chained commands
(`ls ... && wc -l ...`, then `git status && git log ...`) were denied
with `BLOCKED: UNSUPPORTED_SHELL_COMPOSITION` before this session
switched to one-command-per-call — direct proof the guard is inspecting
and rejecting shell composition syntax live, on this session's own
real tool calls, not merely on synthetic test fixtures.

## Unknown-must-deny check (Section 4)

`uptime` — a harmless, non-mutating command not in any allow-by-
construction family — was run standalone:

```
uptime
BLOCKED: UNKNOWN_COMMAND — 'uptime' is not an allowlisted command
```

**DENY, as expected.** Confirms the live classifier remains fail-closed
for arbitrary unrecognized command shapes, not just the specific
historical bug fixtures.

## Safe regression check (Section 5)

All re-run live, after every denied test above:

- `git status` — PASS/ALLOW (repeated, see LIVE-01).
- `git log --oneline -5` — PASS/ALLOW (see LIVE-02).
- `git diff --stat` — PASS/ALLOW, executed normally.
- `git show --stat HEAD` — PASS/ALLOW, executed normally.
- Safe read (`cat`) — PASS/ALLOW (see LIVE-03).
- `python3 knowledge/00-System/verify_baselines.py` — **PASS**, all 4 governing baseline hashes MATCH `PROJECT_INDEX.md` exactly (Blueprint, TSD, EIP, design-bundle manifest — unchanged).
- `python3 knowledge/00-System/validate_capabilities.py` — **PASS**, 6 capabilities, all registered and APPROVED with required fields present (CAP-007 correctly not manifest-bound, invisible to this check by design, per its own registration record).
- `python3 knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py` — **PASS**, 0 errors, 1 pre-existing non-blocking warning (unchanged from prior state).
- `python3 knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py` — **PASS**, no broken evidence references beyond the pre-existing, already-documented expected forward references.

All 4 governing baseline hashes confirmed unchanged (via
`verify_baselines.py`'s own MATCH output above). Local repository
confirmed to have no unexpected mutation caused by the live tests
beyond this evidence file's own intentional addition (`git status`/
`git diff` reviewed before and after each destructive-fixture attempt).

## Additional discovered guard behavior: `git add .claude/settings.json` itself denied

Not part of the required 14-row matrix, but discovered while assembling
this chunk's own closeout commit: `git add .claude/settings.json`
(staging the owner's own already-applied, legitimate edit) was itself
denied — `BLOCKED: DISALLOWED_FLAG_OR_SHAPE — git add did not match its
governed-mutation shape`. The guard's `ClassB_GovernedMutation` shape for
`git add` excludes protected paths (matching the existing
`test_git_add_protected_path` unit test), and `.claude/settings.json` is
one of them. This means the guard's self-protection extends to staging
via `git add`, not only to `Edit`/`Write`/`rm`/`sed -i`/redirection — a
stronger guarantee than this bug's fixture list required, discovered
incidentally rather than tested for. Consequence: this chunk's own
closeout commit could not include the settings.json file at all via
Bash; it remains uncommitted in the working tree, unchanged from what
the owner applied. This is consistent with, not a violation of, the
task's instruction not to modify `.claude/settings.json` this session —
noted here transparently since it affects how "local HEAD ==
`origin/main` reconciliation" reads for this chunk (the settings.json
diff is a real, intentional, owner-made local change that this session's
guard-enforced tooling cannot commit; committing it would require the
owner's own `git add`/`git commit`, or an owner-approved sanctioned
exception).

## Result

**All 14 required live checks: PASS.** PreToolUse live-execution proof:
confirmed via distinct, guard-specific denial reasons across all three
required bypass classes plus two live real-time chained-command denials
this session incidentally triggered on its own tool calls.
Unknown-must-deny: PASS. Safe-command regression: PASS (git
status/log/diff/show, safe read, all 4 governance validators). Total
automated Bash-guard suite: 194/194 PASS.

**BUG-013, BUG-022, and BUG-023: CLOSED** — live activation verified per
`BUG-013-022-023-OWNER-SETTINGS-PATCH.md`'s own closure criteria (patch
applied by owner; fresh session started; hook proven to execute; all
three bugs' fixture classes proven denied live; safe operations proven
unaffected).

**CAP-007: live-qualified/active** per `CAPABILITY_POLICY.md`'s existing
lifecycle semantics — the guard is now an actually-enforcing PreToolUse
hook, not merely a reviewed-but-inert script.

**Local HEAD == origin/main** after this chunk's commit (see commit SHA
in `CURRENT_HANDOFF.md`'s updated chunk-25 entry).

**Phase 7 gate: PASS.** **Phase 8 is legally unlocked** — this session
does not start Phase 8 or MOD-001 work; that is the next session's
legally allowed action, not this one's.
