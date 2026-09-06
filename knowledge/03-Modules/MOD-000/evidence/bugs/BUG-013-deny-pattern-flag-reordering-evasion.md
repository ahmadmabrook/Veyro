---
doc: BUG-013
status: NARROWED (2026-09-06, RR-3) — git-injection half CLOSED by owner's manual edit; rm-recursive half remains OPEN, requires a further human edit
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-16, SEC-17); residual scope widened by an independent Phase 7 re-review (RR-2); git half confirmed CLOSED and rm half confirmed still OPEN by a third independent re-review (RR-3) after the owner's manual settings.json edit
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

## RR-3 (2026-09-06): owner's manual edit verified — git half CLOSED, rm half still OPEN, plus corrected prior claim

The owner hand-edited `.claude/settings.json` (a human edit — this
session's own SEC-06 self-protection correctly blocks agent-side edits to
this file) to add the wildcard-between-`git`-and-subcommand pattern family
(`Bash(git * <subcommand>*<flag>*)`) across all 15 destructive git
subcommands named above. A verification session then live-tested it
directly, and a third, distinct fresh-context `veyro-security-reviewer`
independently re-tested with its own fresh fixtures (not reusing the
verification session's).

**Confirmed CLOSED, both independently:** every git global-flag-injection
variant tried — `-c core.pager=cat`, `--no-pager`, `-C <path>`, `-c
advice.detachedHead=false`, stacked `-c` flags, `GIT_PAGER=cat git ...`,
`command git ...`, `env git ...` — against all 15 covered subcommands
(`reset --hard`, `push --force`, `branch -D`, `clean -fd`, `restore
--staged .`, `filter-branch`, `filter-repo`, `reflog expire`, `update-ref
-d`, `commit --amend`, `stash clear`/`drop`, `worktree remove --force`,
`gc --prune=now`) — **16+ variants, all DENIED.** The re-reviewer
additionally confirmed its fixture repo was byte-for-byte unchanged
afterward (real refusals, not silent no-ops). `git status`/`log`/`diff`/
`show` remain fully usable; the edit is purely additive with zero
deletions; no previously-closed control regressed (`*production*`,
`*--prod*`, baseline `cp`/`mv`/`tee`/`dd`/`truncate`/`sed -i` denies, and
`.claude/settings.json`'s own `cp`/`sed -i` self-protection all re-tested
and still hold).

**Confirmed still OPEN, both independently:** the owner's edit made no
`rm`-related change at all (`git diff` on the file shows only the git
wildcard family added). Bare lowercase `rm -r <path>` (no `-f`) executes a
real recursive delete with **no denial and no permission prompt at all**
— confirmed live against disposable scratch fixtures by both sessions.
The independent re-review went further and also proved `rm -rv`, `rm -vr`,
`rm -Rv`, `rm -v -r`, and `find ... -delete` all execute uncaught —
**broader than the four-pattern fix this file previously prescribed**,
which itself only covered `-r`/`-r*`/`* -r *`/`* -r` and would still miss
`-vr` (flag order reversed) and `-Rv` (uppercase `-R` inside a combined
cluster, which the existing `Bash(rm -R *)` pattern requires a trailing
space to catch and cannot see once `-R` is bundled with another short
flag). **Corrected minimum fix**, per the independent re-review: either a
blanket `Bash(rm *)` / `Bash(rm)` deny (these agent roles have no
legitimate need for `rm` at all) plus `Bash(find * -delete*)` and
`Bash(find * -exec rm*)`, or, if enumeration is still preferred, the
complete set `Bash(rm -r*)`, `Bash(rm -R*)`, `Bash(rm -*r*)`, `Bash(rm
-*R*)`, `Bash(rm * -r*)`, `Bash(rm * -R*)`, `Bash(rm * -*r*)`, `Bash(rm *
-*R*)` (accepting that the `-*r*`/`-*R*` forms will also over-deny some
benign non-recursive `rm` calls whose operand contains the letter after a
flag — fail-closed, consistent with this project's SEC-17 stance).

**Correction to this file's own prior claim:** the "Remediation applied"
section above states baseline/self-protection redirection coverage
(`cp`/`mv`/`tee`/`dd`/`truncate`/`sed -i`/"redirection") was added. The
`cp`/`mv`/`tee`(-onto-baseline-docx)/`dd`/`truncate`/`sed -i` parts are
real and hold. **The redirection (`>`/`>>`) part, and `tee` onto
`.claude/settings.json`/`.claude/rules/**` specifically, do not work** —
see the new `BUG-023` for the proof and full correction. This file is
being corrected here, per this project's preserve-history convention,
rather than silently rewritten.

**Two new, distinct P1s were also found by the same RR-3 re-review** while
verifying this bug — filed separately since they are different bypass
classes, not sub-findings of the flag-reordering issue this bug was
originally scoped to: `BUG-022` (absolute-path/wrapper invocation
defeats the entire deny list, including the git family this bug just
closed) and `BUG-023` (non-functional redirection denies, see above).

## Remediation attempt (2026-09-06): PreToolUse guard built, NOT yet certified

Rather than a further `.claude/settings.json` pattern for the `rm`
family alone, a `.claude/security/bash_guard.py` PreToolUse hook was
built per the architectural conclusion in `BUG-022` to close this and
the two sibling bugs together with a semantic check instead of another
enumerable glob. It correctly denies the full recursive-delete family
this bug named (`-r`/`-R`/`-rf`/`-fr`/reordered/verbose combos, `find
-delete`) and has been through four independent fresh-context review
rounds hardening it further — but has not yet reached a state with zero
known P0/P1 findings; see
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`
for the full four-round record. **This bug's `rm`-recursive half remains
OPEN** pending a clean independent review of the guard.

## Certification impact

**Blocks Phase 7 PASS.** The git-injection half of this bug is genuinely
CLOSED. The `rm`-recursive half remains OPEN and, combined with the two
new sibling bugs `BUG-022`/`BUG-023`, still blocks Phase 7 (P1=3 total
across the three bugs). All other sub-findings (SEC-03/04/16) are fixed
and live-verified; SEC-05 is corrected (see above, RR-3); SEC-17 is a
deliberate non-fix.

## Affected

`.claude/settings.json`, `knowledge/03-Modules/MOD-000/evidence/
scenario-execution/phase3/TEST_RUN_PHASE3_2026-09-04.md` (its claim that
force-push/hard-reset are harness-denied is corrected to note the
argument-ordering caveat that existed before this fix, now resolved for
the git-injection form specifically), `knowledge/03-Modules/MOD-000/
evidence/security/PHASE7_SECURITY_REVIEW_2026-09-06.md` (SEC-05/SEC-06
disposition corrected re: redirection, see `BUG-023`).
