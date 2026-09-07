---
doc: CHUNK-20-ARCHIVE
status: ARCHIVED — full narrative for CURRENT_HANDOFF.md chunk 20, compressed to a summary line 2026-09-07 (chunk 22) per the retention rule
archived: 2026-09-07
---

# What happened chunk 20, 2026-09-06 — built PreToolUse Bash guard for BUG-013/022/023; FOUR independent review rounds, every one found new P0s; guard NOT certified, all three bugs remain OPEN

Per explicit instruction, continuing from chunk 19's architectural
conclusion (`permissions.deny` glob matching alone is insufficient;
build a project-scoped `PreToolUse` Bash security guard as a semantic
check, keeping deny patterns as defense-in-depth). Scope: implement and
qualify the guard; do not modify `.claude/settings.json`; do not begin
Phase 8; do not start MOD-001.

**Step 1 — hook mechanism verified before writing anything.** Cross-checked
two independent sources: strings extracted directly from the installed
Claude Code binary (`v2.1.167`) and the live docs at
`code.claude.com/docs/en/hooks.md`. Both agree exactly on the
`PreToolUse` schema (stdin JSON with `tool_input.command`; stdout JSON
with `hookSpecificOutput.permissionDecision`; exit-code semantics).
Conclusion: PreToolUse can technically enforce Bash execution here — not
BLOCKED. Full record:
`evidence/security/HOOK_CONTRACT_VERIFICATION_2026-09-06.md`.

**Steps 2-8 — guard built and tested.** `.claude/security/bash_guard.py`
normalizes the requested command (absolute-path resolution,
`env`/`command` unwrapping, git global-option skipping, `$()`/backtick
recursion, flag-character bundling) and denies destructive
filesystem/git operations and protected-path mutations, printing nothing
(deferring to the existing deny list) when it finds no violation.
`.claude/security/tests/test_bash_guard.py` — a real-subprocess,
real-PreToolUse-payload suite — was built and run before every review
round.

**Step 9 — four independent fresh-context `veyro-security-reviewer`
rounds, no round reusing any prior round's context.** Per this project's
standing discipline (never self-certify), and consistent with this
project's own history (Phase 5 took five rounds to reach APPROVED):

- **RR-1: BLOCKED, 5 P0 + 5 P1.** Command-segmentation layer: newline-
  separated commands silently merging into one, shell reserved
  words/grouping punctuation treated as an unrecognized command name
  instead of denied, interpreter/wrapper delegation (`bash -c`, `eval`,
  `xargs`, `sudo`, `timeout`, `env -S`) entirely unhandled, backslash
  line-continuation splitting one command into two, `cd`-then-relative-
  path defeating protected-path checks. All fixed same day; suite grew
  95→136.
- **RR-2: BLOCKED, 5 P0 + 6 P1.** Incomplete wrapper denylist; `$VAR`/
  `${VAR}` as a command name silently ALLOWING instead of denying (the
  sharpest finding — it bypassed the entire wrapper denylist in one
  token); `find -exec` checking a 5-name allowlist instead of recursing
  into the executed command; case-sensitive protected-path matching on
  this case-insensitive filesystem; `cd`'s own flag arguments poisoning
  the cwd tracker; interpreter stdin/heredoc-fed code uncaught; a narrow
  write-primitive command set; git `checkout`/`restore` not checking
  explicit path arguments; a persistent `git config alias.x '!shell'`
  form left open while the transient `-c` form was closed; the guard's
  own directory unprotected — plus a genuinely disruptive false-positive
  class (the reserved-word check matched shlex tokens, which have
  already had quotes stripped, so `grep -n 'if' file` and `echo done`
  were wrongly denied). Fixed via a structural change: reserved-word
  detection moved to raw, quote-aware, first-word-of-segment-only
  matching. Suite grew 136→171.
- **RR-3: BLOCKED, 4 P0 + 5 P1.** **This session's actual runtime shell
  is zsh 5.9, not bash** — the review's most consequential finding;
  zsh precommand modifiers (`noglob`/`nocorrect`) and reserved words
  (`repeat`/`coproc`) were unmodeled by construction, not by omission.
  Also: a leading redirection hiding the real command name (`>/dev/null
  rm -rf x` allowed); a greedy redirect-operator scan swallowing a
  trailing chain operator (`echo hi >&2|rm -rf x` allowed); more git
  config shell-execution keys (`diff.external` etc.); `git -C` not
  feeding the checkout/restore path check; a parallel-denylist drift on
  `time`. Fixed: exact-operator matching replacing the greedy scan,
  leading-redirection stripping, zsh additions, git config/`-C` fixes.
  Suite grew 171→194.
- **RR-4: BLOCKED, 3 P0 + 3 P1, plus a disclosed incident.** zsh
  clobber/append redirection spellings (`>!`, `>>!`, `>>&`, `&>!`,
  `&>|`) still unmodeled; command-*name* matching was case-sensitive
  (`RM -rf x` bypassed everything) even though path matching had
  already been made case-insensitive for the identical filesystem
  reason; `builtin` (the `command` builtin's sibling) neither unwrapped
  nor denied; more git config keys (`core.fsmonitor`,
  `difftool.*.cmd`, `--config-env=`); the protected-path set omitted
  `CLAUDE.md`/`.mcp.json`/core governance docs. Case-insensitive command
  matching and `builtin` were fixed same day; the remaining items were
  left explicitly open (see below). Suite grew 194→200.

**Incident, disclosed in full:** during RR-4, the reviewer fed a
heredoc-based test payload whose body contained a literal `EOF` line,
which terminated the reviewer's own outer heredoc early — the shell
executed the remaining payload lines for real: `mv .claude /tmp/junk`,
an overwrite of `CLAUDE.md`, an overwrite of
`knowledge/00-System/CAPABILITY_POLICY.md`. The reviewer self-detected
this and restored `.claude/` via `mv` back from `/tmp/junk` and the two
files via `git checkout --` (both were clean at session start, so this
was lossless). **This session independently re-verified the restoration
before continuing, not trusting the reviewer's own account:** `git
status --short` confirmed byte-identical to before the review started;
`git diff --stat HEAD` on both affected files returned empty; `.claude/
security/` was confirmed intact with both the guard and its test file
present; the 194-test suite was re-run clean. No data was lost. This
incident is itself real-world evidence for two of the guard's own
disclosed gaps (heredoc handling; ancestor-directory protection — the
accidental `mv .claude /tmp/junk` is exactly that gap's shape).

**Current honest status: the guard is NOT certified.** Every one of four
independent review rounds found at least one new P0. All mechanically-
fixable findings were fixed and tested (final count: 200/200 passing).
**Disclosed, unfixed gaps remain** — recorded in the guard's own module
docstring and in `evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`:
zsh clobber/append redirection operators; heredoc live-expansion under an
unquoted delimiter (a `$()`/backtick inside such a body executes in the
real shell before this guard ever sees it); ancestor-directory operations
(`mv .claude /tmp/x`, `tar -czf x.tgz .claude` escape every protected-path
check, since matching is per-listed-path not per-subtree); `python -m
<module> "<code>"` inline code; several more git config shell-execution
keys; a still-incomplete protected-path set. **Per this project's
standing discipline (never declare a security gate PASS while a known
P0/P1 remains, and — the pattern this effort demonstrated four times
running — do not assume a further round would find nothing just because
none has been dispatched), BUG-013, BUG-022, and BUG-023 all remain
OPEN.** No `.claude/settings.json` edit was made. The owner-facing
settings-integration patch file (`BUG-013-022-023-OWNER-SETTINGS-PATCH.md`)
was deliberately NOT authored this chunk — producing it would imply a
readiness this guard has not earned; it should only be written once a
review round returns P0=0/P1=0. **Phase 7 gate remains BLOCKED. Phase 8
is NOT legally unlocked.**

**Next legally allowed action, if a future session picks this up:**
either (1) a fifth independent review round plus fixes for whatever it
finds, repeating until clean, or (2) the architectural decision RR-2
raised and this session did not act on — whether to invert the guard's
design from enumerating dangerous shapes to allowlisting known-safe
command shapes, which would close this whole class of recurring gap but
requires deriving a safe-command allowlist broad enough not to cripple
this repo's routine engineering workflow. Full four-round detail:
`evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`.

(This decision was in fact taken in chunk 21: v1 was superseded and a v2
allow-by-construction redesign was built and reviewed under an explicit
2-round cap, later followed by an owner-authorized final Round 3 in
chunk 22.)
