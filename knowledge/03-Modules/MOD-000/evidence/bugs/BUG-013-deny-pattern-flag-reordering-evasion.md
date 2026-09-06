---
doc: BUG-013
status: MOSTLY FIXED (2026-09-06) — residual scope WIDER than first recorded, still OPEN, requires human edit
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-16, SEC-17); residual scope widened by an independent Phase 7 re-review (RR-2)
severity: P1 (primary), P2 (sub-findings)
---

# BUG-013: `.claude/settings.json` deny patterns evaded by flag reordering, spelling variants, and missing coverage

## What is wrong (as found)

A fresh-context `veyro-security-reviewer` proved live, against real
(harmless-target) commands, that the deny list's destructive-command
patterns matched only one argument ordering/spelling each:

- **SEC-02 (P1):** `git push nosuchremote main --force` (flag after
  args) and `git -c core.pager=cat reset nosuchref --hard` (global flag
  injected before the subcommand) both **executed**, reaching git and
  failing only on the invalid remote/ref — `Bash(git push --force*)` and
  `Bash(git reset --hard*)` only matched a literal prefix.
- **SEC-03 (P2):** `rm -fr`, `rm -r -f`, and (on a GNU coreutils `rm`)
  `rm --recursive --force` all bypass `Bash(rm -rf *)`.
- **SEC-04 (P2):** `git branch -D`, `git checkout .`, and other
  destructive/history-rewriting git commands (`clean -f`, `restore .`,
  `filter-branch`, `reflog expire`, `commit --amend`, `stash clear`,
  `worktree remove`, `gc --prune=now`) had no deny coverage at all.
- **SEC-05 (P2):** the 4 governing baselines were protected against
  `rm`/`Edit`/`Write` but not `cp`/`mv`/`tee`/`dd`/`truncate`/`sed -i`/
  shell-redirection onto a baseline filename.
- **SEC-06 (P2):** `.claude/settings.json` and `.claude/rules/**`
  themselves had no deny coverage — nothing prevented a session from
  editing away its own governance config (the Phase 3 adversarial drill
  showed the *behavioral* layer holds, but there was no *technical*
  layer).
- **SEC-16 (Editorial):** the TestSprite billed-command deny patterns
  were anchored on the bare command name (`testsprite test run*`), not
  tested against an `npx`/absolute-path invocation of the same binary
  (not live-tested, to avoid risking real spend — by inspection only).
- **SEC-17 (Editorial):** `Bash(*production*)` is intentionally broad
  (blocks benign reads containing the word) — the reviewer suggested
  narrowing it; this project deliberately keeps it broad (see
  Remediation below).

## Remediation applied (2026-09-06)

`.claude/settings.json`'s deny list was substantially rewritten:
enumerated `rm` flag-order/spelling variants (`-fr`, `-Rf`, `-fR`, `-R`,
`-r -f`, `-f -r`, `--recursive`, `--force`, both prefix and
anywhere-in-command forms); added the full destructive/history-rewrite
git command set (branch -D, checkout ., clean -f/-d, restore ., 
filter-branch, filter-repo, reflog expire, update-ref -d, commit --amend,
stash clear/drop, worktree remove, gc --prune); added `cp`/`mv`/`tee`/
`dd`/`truncate`/`sed -i`/redirection coverage for all 4 baseline
filenames and the design-bundle directory; added self-protection
(`Edit`/`Write`/`sed -i`/redirection/`cp`/`mv`/`rm` denies against
`.claude/settings.json`, `.claude/rules/**`, `.claude/agents/**`);
broadened the TestSprite billed-command patterns to match anywhere in
the command, not just as a prefix.

**Live-verified fixed (un-injected argument form only — see Residual gap
below for the important caveat an independent re-review found):**
`git push nosuchremote main --force` now DENIED; `rm -fr`/`rm -r -f` on
scratch targets now DENIED; `git branch -D`/`git checkout .`/
`cp <src> .../Gym_OS_Master_Product_Blueprint...` now DENIED. **Each of
these same commands, with a `-c <anything>` global flag injected right
after `git`, still executes** — the qualifier "un-injected argument form
only" is load-bearing, not a formality.

**SEC-17 explicitly not narrowed, by design:** the reviewer's own
assessment was "fails in the safe direction... will block legitimate
read-only work." This project's standing discipline favors fail-closed
over convenience — a benign blocked read can be rephrased; a real
production-action gap cannot be un-caused. Not a defect; a deliberate
trade-off, recorded here rather than silently accepted.

## Residual gap — genuinely OPEN, cannot be self-remediated further, WIDER than first recorded

**The self-protection fix (SEC-06) took effect immediately upon being
written**, and correctly blocked this same session's own next attempt to
edit `.claude/settings.json` further — including more real fixes that
were still needed. The original record of this bug scoped the residual
to `git -c core.pager=cat reset <ref> --hard` alone. **An independent
Phase 7 re-review (RR-2) proved the bypass is broader**: a single
injected `-c` global flag between `git` and the subcommand defeats
**every** `Bash(git <subcommand>...)` deny pattern in the file, not just
`reset --hard`. Confirmed live by the re-reviewer against harmless
targets:

- `git -c core.pager=cat reset nosuchref --hard` → **EXECUTED** (as
  originally recorded)
- `git -c core.pager=cat push nosuchremote main --force` → **EXECUTED**
  (the force-push deny this bug's first version called "live-verified
  fixed" is only true for the un-injected argument form)
- `git -c core.pager=cat branch -D nosuchbranch` → **EXECUTED**

The correct fix needs the wildcard-between-`git`-and-subcommand pattern
form (`Bash(git *<subcommand>*<flag>*)`) applied to **every** git deny
pattern in the family (push --force, reset --hard, branch -D,
checkout ., clean -f/-d, restore ., filter-branch, reflog expire,
update-ref -d, commit --amend, stash clear/drop, worktree remove, gc
--prune), not only the one this session happened to test first.

**A second, distinct residual gap was also found by the same re-review:**
`rm -r <path>` (lowercase `-r`, no `-f`) is **not denied** — the deny
list enumerates `rm -R *` (uppercase) but never bare lowercase `rm -r *`
standalone (only in combination with `-f`). The re-reviewer confirmed
this executes a real recursive delete (against its own scratch files,
not real project state) on this host's `rm`, which evidently does not
block on a non-interactive stdin the way an interactive terminal would.
This needs its own additional deny entries: `Bash(rm -r *)`,
`Bash(rm -r*)`, `Bash(rm * -r *)`, `Bash(rm * -r)`.

**This is the self-protection control working as designed, not
malfunctioning** — SEC-06's own remediation explicitly asked that
changes to this file "require the same owner-approval path as a baseline
change." That now means a human, not this agent, must apply both fix
families above. Until that happens, `git -c <flag> <destructive-subcommand>`
against any covered git pattern, and bare `rm -r <path>`, remain real,
live, unresolved bypasses.

## Certification impact

**Blocks Phase 7 PASS** until the residual gap above is closed (requires
a human edit to `.claude/settings.json`, then live re-verification, then
a fresh-context re-review). All other sub-findings (SEC-03/04/05/16) are
fixed and live-verified; SEC-17 is a deliberate non-fix.

## Affected

`.claude/settings.json`, `knowledge/03-Modules/MOD-000/evidence/
scenario-execution/phase3/TEST_RUN_PHASE3_2026-09-04.md` (its claim that
force-push/hard-reset are harness-denied is corrected to note the
argument-ordering caveat that existed before this fix, and the residual
`-c`-flag-injection caveat that remains).
