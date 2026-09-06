---
doc: BASH_GUARD_DEVELOPMENT
status: IN PROGRESS — NOT certified clean after 4 independent review rounds; BUG-013/022/023 remain OPEN
date: 2026-09-06
---

# `.claude/security/bash_guard.py` — development record (BUG-013/022/023 remediation attempt)

## Why this exists

`BUG-013`, `BUG-022`, `BUG-023` collectively established that
`.claude/settings.json`'s `permissions.deny` glob-pattern matching is not
a sufficient sole technical enforcement layer for protected Bash
operations (global-flag injection, absolute-path invocation, and
non-functional redirection patterns all defeated it in turn). The
recorded architectural conclusion was to add a project-scoped
`PreToolUse` Bash security guard that parses/normalizes the requested
command and fails closed semantically, keeping the existing deny
patterns as defense-in-depth alongside it.

## Step 1 — hook contract verification

Before writing anything, the `PreToolUse` hook mechanism was verified
against two independent sources: strings extracted directly from the
installed Claude Code binary (`v2.1.167`,
`@anthropic-ai/claude-code`), and the live docs at
`https://code.claude.com/docs/en/hooks.md`. Both agree exactly on the
schema. Full record:
`knowledge/03-Modules/MOD-000/evidence/security/HOOK_CONTRACT_VERIFICATION_2026-09-06.md`.
Conclusion: PreToolUse can technically enforce Bash execution in this
installed version. Not BLOCKED.

## Steps 2-8 — guard built, tested

`.claude/security/bash_guard.py` was written: reads the PreToolUse JSON
payload, normalizes the command (absolute-path resolution, `env`/
`command` unwrapping, git global-option skipping, `$()`/backtick
recursion, flag-character bundling), and denies destructive
filesystem/git operations and protected-path mutations while deferring
(printing nothing) on anything it doesn't recognize as a violation — so
the existing `.claude/settings.json` deny list keeps working underneath
it. `.claude/security/tests/test_bash_guard.py` — a real-subprocess,
real-PreToolUse-JSON-payload test suite — was built alongside it and run
directly before every review round.

## Steps 9 — four independent review rounds, each finding new P0s

Per this project's standing discipline (never self-certify; independent
fresh-context confirmation required), a fresh-context Opus
`veyro-security-reviewer` reviewed the guard **four times**, each with no
memory of prior rounds. Every round found genuine P0-severity bypasses
that the previous round's fixes had not closed:

| Round | Verdict | P0 | P1 | Key findings |
|---|---|---|---|---|
| RR-1 | BLOCKED | 5 | 5 | Command-segmentation layer: newline-separated commands merging, reserved-word/grouping punctuation unrecognized instead of denied, interpreter/wrapper delegation (`bash -c`, `eval`, `xargs`, `sudo`, `timeout`, `env -S`) entirely unhandled, backslash line-continuation splitting commands, `cd`-then-relative-path defeating protected-path checks |
| RR-2 | BLOCKED | 5 | 6 | Incomplete wrapper denylist, `$VAR`/`${VAR}` command name silently ALLOWING (not denying), `find -exec` checking a 5-name list instead of recursing, case-sensitive protected-path matching, `cd` flags poisoning the cwd tracker, interpreter stdin/heredoc code uncaught, narrow write-primitive set, git checkout/restore path args, persistent `git config alias.x '!shell'`, guard's own directory unprotected — plus a disruptive false-positive (reserved-word check matched quote-*stripped* tokens, denying `grep -n 'if' file`) |
| RR-3 | BLOCKED | 4 | 5 | **This session's actual runtime shell is zsh 5.9, not bash** — zsh precommand modifiers (`noglob`/`nocorrect`) and reserved words (`repeat`/`coproc`) were unmodeled by construction; leading redirection hiding the command name (`>/dev/null rm -rf x`); a greedy redirect-run swallowing a trailing chain operator (`echo hi >&2\|rm -rf x`); more git config shell-execution keys (`diff.external` etc.); `git -C` not feeding the checkout/restore path check; parallel-denylist drift on `time` |
| RR-4 | BLOCKED | 3 | 3 | zsh clobber/append redirection spellings (`>!`, `>>!`, `>>&`, `&>!`, `&>\|`) unmodeled; command-*name* matching was case-sensitive (`RM -rf x` bypassed everything) though path matching had already been made case-insensitive for the same filesystem reason; `builtin` precommand modifier (sibling of `command`) neither unwrapped nor denied; more git config keys (`core.fsmonitor`, `difftool.*.cmd`, `--config-env=`); protected-path set omitted `CLAUDE.md`/`.mcp.json`/core governance docs |

Every round's findings that could be concretely, mechanically fixed
without an architectural rewrite were fixed and tested same-session
(test suite grew 95 → 136 → 171 → 194 → 200 across the four rounds, all
passing at every checkpoint). The full revision history and exact fixes
are recorded in `.claude/security/bash_guard.py`'s own module docstring
(search for "RR-1"/"RR-2"/"RR-3"/"RR-4"), which is the authoritative
detail record — this file is the durable summary.

## Incident during RR-4 (disclosed, verified resolved)

The RR-4 reviewer accidentally executed part of a heredoc test payload
as real commands against this repository (a literal `EOF` line inside
the test payload terminated the reviewer's own outer heredoc early,
and the remaining lines ran for real: `mv .claude /tmp/junk`, an
overwrite of `CLAUDE.md`, and an overwrite of
`knowledge/00-System/CAPABILITY_POLICY.md`). The reviewer self-detected
this, restored `.claude/` via `mv` back from `/tmp/junk`, and restored
`CLAUDE.md`/`CAPABILITY_POLICY.md` via `git checkout --` (both were
clean at session start, so this was lossless). **The orchestrating
session independently re-verified this restoration before continuing**,
not trusting the reviewer's own account: `git status --short` confirmed
byte-identical to before the review started (`M .claude/settings.json`,
`?? .claude/security/`, `?? .../HOOK_CONTRACT_VERIFICATION_2026-09-06.md`),
`git diff --stat HEAD` on both `CLAUDE.md` and `CAPABILITY_POLICY.md`
returned empty (zero diff against the committed version), `.claude/security/`
was confirmed intact with both the guard and its test file present, and
the 194-test suite (RR-3's count, before RR-4's own fixes) was re-run
clean. No data was lost. This incident is itself independent, real-world
evidence for two of the guard's own disclosed gaps: heredoc handling
(P0, see below) and the ancestor-directory protection gap (P1, see
below) — the reviewer's accidental `mv .claude /tmp/junk` is exactly the
BUG-023-class operation that gap describes.

## Current honest status — NOT certified, BUG-013/022/023 remain OPEN

After four independent review rounds and concrete fixes for every round's
mechanically-fixable findings, the guard is **substantially more robust**
than the `.claude/settings.json` deny-pattern approach it supplements —
but it has **not** reached a state with zero known P0/P1 findings, and
every round so far has found at least one new P0. Per this project's
standing discipline (never declare a security gate PASS while a known
P0/P1 remains, and — the pattern this specific effort has now
demonstrated four times — do not assume the absence of a further round's
findings just because no more have been found yet), **this guard does
NOT close BUG-013, BUG-022, or BUG-023**. All three remain OPEN.

**Known open gaps, disclosed in the guard's own docstring, not fixed:**
- **P0 (zsh clobber/append redirections):** `>!`, `>>!`, `>>&`, `&>!`,
  `&>|` are not in the guard's redirect-operator vocabulary — both hide
  a leading command name and fail to protect a redirection target.
- **P0 (heredoc live-expansion):** a heredoc body under an unquoted
  delimiter is a live shell-expansion context; `$()`/backticks inside it
  execute in the real shell before this guard ever sees them, because
  the body is discarded before substitution-extraction runs.
- **P1 (ancestor-directory operations):** protected-path matching is
  per-listed-path, not per-subtree — `mv .claude /tmp/x`, `tar -czf x.tgz
  .claude`, `chmod -R 000 .claude` all escape every protected-path check.
- **P1 (`python -m <module> "<code>"`):** inline code passed as a plain
  argument to a module runner is not caught by the stdin-feeding
  heuristic that blanket-denies `-c`/`-e`.
- **P1 (git config key coverage):** `core.fsmonitor`, `difftool.*.cmd`,
  `mergetool.*.cmd`, `gpg.program`, and `--config-env=key=ENVVAR` all
  execute a value as a shell command and are not yet covered.
- **P1 (protected-path set gaps):** `CLAUDE.md`, `.mcp.json`, and the
  core governance documents (`DEVELOPMENT_CONSTITUTION.md`,
  `CAPABILITY_POLICY.md`) are not in the protected-path set despite
  having comparable or greater behavioral authority than what IS
  protected.

**Structural observation, stated plainly rather than glossed over:**
every round has found a fresh instance of the same shape of gap — a
name, operator spelling, or config key this guard's enumeration-based
approach didn't yet know about. This is the exact "enumeration of bad
names is inherently incomplete" critique RR-2 raised about the original
`.claude/settings.json` glob approach, now demonstrated against the
guard meant to replace it. A future session should weigh whether further
enumeration rounds are the right next step, or whether the guard needs
an architectural change (e.g. an allowlist-of-known-safe-command-shapes
design, which RR-2 proposed and this session judged too large a change
to make safely without a broader redesign of what this repo's routine
workflow actually needs to remain usable).

## What was explicitly NOT done this chunk

Per explicit instruction, `.claude/settings.json` was not modified. Since
the guard has not passed an independent review clean, the
owner-facing settings-patch file (that would normally be produced once a
guard "passes review," per this task's own step ordering) was
**deliberately not created** this chunk — creating it would imply a
readiness this guard has not earned. The next session's job, if it picks
this up, is either another review-and-fix round or the architectural
decision above; only once a round returns P0=0/P1=0 should the
settings-patch file be authored and BUG-013/022/023 be considered for
closure.

## Affected / cross-referenced

`.claude/security/bash_guard.py`, `.claude/security/tests/test_bash_guard.py`,
`knowledge/03-Modules/MOD-000/evidence/security/HOOK_CONTRACT_VERIFICATION_2026-09-06.md`,
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-013-*.md`,
`BUG-022-*.md`, `BUG-023-*.md`, `BUG_REGISTRY.md`,
`PHASE7_SECURITY_REVIEW_2026-09-06.md`, `CURRENT_STATE.md`,
`CURRENT_HANDOFF.md`.
