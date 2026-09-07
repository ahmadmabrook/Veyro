---
doc: CHUNK-21-ARCHIVE
status: ARCHIVED — full narrative for CURRENT_HANDOFF.md chunk 21, compressed to a summary line 2026-09-07 (chunk 23) per the retention rule
archived: 2026-09-07
---

# What happened chunk 21, 2026-09-06 — v1 Bash guard superseded (4 failed review rounds); v2 allow-by-construction redesign built and reviewed under an explicit 2-round cap; BUG-013/022/023 remain OPEN

Per explicit instruction: chunk 20's pattern — four independent review
rounds of `bash_guard.py`, every single one finding a new P0-severity
bypass — was treated as an architectural finding, not a queue of more
patches. Explicit scope this chunk: redesign the Bash enforcement model
into a simpler fail-closed architecture that does not attempt to
implement a general Bash/zsh parser; do not continue patching individual
syntax bypasses; do not activate any guard; do not modify
`.claude/settings.json`; do not begin Phase 8; do not start MOD-001; a
hard cap of two review rounds for this redesign pass, with an explicit
instruction to STOP after two rounds if P0/P1 remain rather than keep
iterating.

**v1 superseded, not deleted.** `.claude/security/bash_guard.py` (the
deny-by-enumeration guard from chunk 20) and its test suite were moved
to `.claude/security/superseded_v1/` with a README explaining why —
preserved as durable evidence of what was tried and why it failed, per
this project's durability discipline.

**New architecture: allow-by-construction, fail closed on ambiguity.**
Rather than trying to recognize dangerous shell constructs (v1's
approach, which kept meeting new ones), v2 does the opposite: (1) any
shell composition/substitution marker anywhere in the raw command
(`;`, `&&`, `||`, `|`, `&`, backtick, `$(`, `<(`, `>(`, `<<`, `>`, `<`,
newline) is an unconditional, non-quote-aware deny — no exceptions; (2)
what's left is tokenized with `shlex`, parse failure denies; (3) the
exact tokenized argv must match one of a small explicit allowlist of
command families (Class A safe read-only: git status/log/diff/show/
rev-parse/ls-files/branch-list/remote-read/fetch-scoped/worktree-list/
stash-list, plus find/shasum/ls/cat/head/tail/wc/pwd/stat/grep with
restricted flags, plus `python3` limited to ~7 allowlisted project
validator scripts; Class B narrowly governed mutation: `git add
<specific safe paths>`, `git commit -m <msg>` or `-F <file>`, `git push`
with zero flags, `git checkout -b <branch>`, `mkdir -p` under
`knowledge/` only) — anything else, including every syntactic form v1
tried and failed to defend against by recognition, is an explicit deny.
Unlike v1 (silent when it didn't recognize a specific known-bad
pattern), v2 renders an explicit ALLOW or DENY on every single Bash call
once activated — UNKNOWN MUST DENY, with no third "defer" outcome
anywhere in the file. `veyro-security-reviewer` was not spawnable
directly this session (custom agent type unavailable); both v2 review
rounds used `general-purpose` at Opus tier, explicitly briefed to read
and adopt that role's own charter file
(`.claude/agents/veyro-security-reviewer.md`) as its operating
instructions before reviewing — disclosed here as a deviation from the
normal agent-invocation path, not concealed.

**Round 1** confirmed the architecture itself sound (traced every
family-dispatch exit path, confirmed `classify()` always raises a
verdict) and found **2 P0 + 4 P1 + 5 P2 + 6 Editorial**, all local
implementation gaps: `git push`/`fetch` refspec syntax (`:branch`
delete, `+branch` force) expressed as positionals bypassing the
flag-based exclusion; `git add` protected-path check defeated by
pathspec magic (`:/`), bare directory-level add (`git add .claude`),
traversal, and git's own glob expansion; the project's mandated
multi-line/attribution-trailer commit format being structurally
impossible under an `-m`-only design; routine read-only shapes wrongly
denied (`--porcelain`, `--format=`, `diff <ref> -- <path>`, no
`checkout -b`); arbitrary URLs accepted by a "read-only" fetch/remote
family; plus a `main()` path where a malformed JSON payload could raise
uncaught and fail OPEN. **All fixed same session** via one shared
mechanism — a strict literal-relative-path charset
(`_is_safe_relative_path`) gating mutation-family path arguments, and a
strict ref/remote charset (`_is_safe_ref_or_remote`, excluding `:`/`+`
entirely) gating ref-consuming families — plus a new `git commit -F
<file>` form so the attribution trailer never has to pass through the
Bash command string as literal text. Test suite: 111 → 145.

**Round 2** (the maximum permitted for this redesign pass) independently
re-verified round 1's fixes (8 of 10 fully closed, 2 partially) and
found **1 P0 + 2 P1 + 4 P2 + 5 Editorial** new findings — all traced to
one root cause: the strict-charset mechanism had been wired into
mutation and ref-consuming families, but the plain read-only file
families (`cat`/`head`/`tail`/`wc`/`stat`/`grep`/`find`/`ls`/`shasum`)
were still on a much weaker check that never rejected `$HOME`-style
expansion, `..` traversal, or bare glob characters — most sharply,
`find . *`, where a real shell's glob expansion of a maliciously-named
file (creatable via the ungoverned Write tool) could inject a
destructive predicate the guard never sees as text, reaching the exact
BUG-013 class through an ALLOW verdict. Also: `git push /tmp/exfil.git`/
`git push ~/exfil.git` (the round-1 ref/remote charset's "closes
arbitrary remotes" claim held for URLs but not plain filesystem paths).
**Reviewer's explicit architectural determination — the load-bearing
judgment call this task required before proceeding further:** *"a small
number of local bugs in an otherwise-sound design... both are bounded,
enumerable, single-mechanism fixes of the same shape that already
succeeded."* Re-confirmed independently with 120,000 fresh fuzz cases:
zero fail-open paths, all v1-era regression fixtures still deny
correctly. **Fixed same session** by making `_is_safe_relative_path` the
single shared gate for every path-shaped argument in every family
(mutation and read-only alike), and rewriting `find`'s walker to
distinguish a value-taking flag's value (which may legitimately contain
wildcards) from a bare positional (which must be a safe literal path).
Test suite: 145 → 174.

**The 2-round cap has now been reached.** Per explicit instruction, no
third review was dispatched — even though the round-2 fixes reuse a
mechanism both reviewers independently confirmed works everywhere it has
been wired in. Those fixes are **unverified by independent review** and
are not represented as certified. To be precise about what the cap does
and does not mean: the second reviewer's own explicit determination was
that the remaining findings are local implementation gaps, not evidence
the allow-by-construction approach is unworkable under the current
Claude Code Bash/PreToolUse model — both facts are recorded because they
point to different next steps, and per the explicit cap the choice of
which belongs to the owner now, not to another automatic iteration.

**`BUG-013`, `BUG-022`, and `BUG-023` all remain OPEN.** No
`.claude/settings.json` edit was made. The owner-facing settings-
integration patch file was not authored — activation requires a review
round that returns P0=0/P1=0, which this pass did not reach. **Phase 7
gate remains BLOCKED. Phase 8 is NOT legally unlocked.** Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`.

(The owner subsequently authorized a final Round 3 review in chunk 22,
and a narrowly-scoped remediation of Round 3's findings in chunk 23.)
