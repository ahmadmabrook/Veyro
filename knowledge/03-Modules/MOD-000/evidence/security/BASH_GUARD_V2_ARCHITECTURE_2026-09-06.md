---
doc: BASH_GUARD_V2_ARCHITECTURE
status: IN PROGRESS — 2-round review cap for this redesign pass reached; NOT certified; BUG-013/022/023 remain OPEN
date: 2026-09-06
---

# `.claude/security/bash_guard.py` v2 — allow-by-construction redesign

## Why a redesign, not a fifth patch round

The v1 guard (deny-by-enumeration — see
`.claude/security/superseded_v1/README.md` and
`BASH_GUARD_DEVELOPMENT_2026-09-06.md`) went through four independent
fresh-context security reviews. Every round found new P0-severity
bypasses (5+5, 5+6, 4+5, 3+3 across P0/P1). The owner's explicit
instruction treated that pattern as an architectural finding: v1 tried
to *understand* arbitrary Bash/zsh syntax well enough to prove a request
safe, and kept meeting one more syntactic shape it hadn't modeled. That
is an unbounded search space — patching it further was explicitly ruled
out ("do not continue patching individual Bash syntax bypasses
one-by-one").

## The v2 architecture

**Allow-by-construction, fail closed on ambiguity.** Full design
rationale lives in `.claude/security/bash_guard.py`'s own module
docstring — this file is the durable summary and review record, not a
duplicate of the design doc.

In brief: (1) any shell composition/substitution marker anywhere in the
raw command is an unconditional deny, no quote-awareness, no exceptions;
(2) the remainder is tokenized with `shlex`, parse failure denies; (3)
the exact tokenized argv must match one of a small set of explicit
command-family validators (Class A safe read-only, Class B narrowly
governed mutation) or it is denied. There is no third "defer" outcome —
unlike v1, v2 renders an explicit ALLOW or DENY on every single Bash
call once activated.

**Old v1 preserved as evidence, not deleted**, per durability discipline
— `.claude/security/superseded_v1/bash_guard_v1.py` and its test suite,
with a README explaining why it was abandoned.

**`veyro-security-reviewer` was not spawnable this session** (the custom
agent type was unavailable) — both review rounds used `general-purpose`
at Opus tier, explicitly briefed to read and adopt
`.claude/agents/veyro-security-reviewer.md` as its operating charter
(ground-truth documents, review scope, no self-approval) before
reviewing. This is disclosed here as a deviation from the project's
normal agent-invocation path, not concealed.

## Review round 1

Reviewer confirmed the architecture itself is **sound**: traced every
family-dispatch exit path and confirmed `classify()` always raises a
verdict (later re-confirmed by a second reviewer with 120,000 fuzz
cases, zero fail-open results). Found **2 P0 + 4 P1 + 5 P2 + 6
Editorial**, all local implementation gaps in specific family
validators, not evidence against the architecture:

- **P0**: `git push`/`git fetch` refspec syntax (`:branch` delete,
  `+branch` force) expressed as *positional* arguments, bypassing the
  flag-based force/delete exclusion entirely.
- **P1**: `git add` protected-path check defeated by pathspec magic
  (`:/`), bare directory-level add (`git add .claude`), path
  normalization tricks (`//`, `..`), and git's own unquoted-argument
  globbing (`.claude/*`).
- **P1**: the project's mandated commit format (multi-line body with a
  `Co-Authored-By:` trailer, containing `<`/`>`/newline) was structurally
  impossible under the original `-m`-only commit family, given Stage 1's
  blanket character ban.
- **P1**: routine read-only shapes wrongly denied (`--porcelain`,
  `--format=`, `diff <ref> -- <path>`, no `checkout -b` family at all).
- **P1**: `git fetch`/`git remote show` accepted arbitrary URLs with no
  constraint — an exfiltration/transport-helper risk in a family
  labeled read-only.
- P2s: `mkdir -p` `..` traversal escape; a shlex/shell tokenization
  divergence on `$'...'`/`${...}`; unbounded reads outside the repo
  (`~/.ssh/id_rsa` etc.) via `cat`/`grep`/`find`/`head`/`tail`/`stat`; a
  `main()` path where a non-dict JSON payload could raise uncaught and
  fail OPEN; dead code and a duplicate allowlist entry.

**All fixed same session**, primarily via one shared mechanism: a strict
literal-relative-path charset (`_is_safe_relative_path`, letters/digits/
`._-` plus `/` as separator only) gating `git add`/`git commit -F`/
`mkdir -p`, and a strict ref/remote charset (`_is_safe_ref_or_remote`,
excluding `:`/`+` entirely) gating `git push`/`fetch`/`remote show`/
`log`/`diff`/`show`/`rev-parse`. `git commit -F <file>` added
specifically so the attribution trailer never has to pass through the
Bash command string as literal text. `main()` restructured so a
malformed-but-valid-JSON payload always gets an explicit decision or a
silent (genuinely-not-Bash) no-op, never an uncaught exception. Test
suite: 111 → 145.

## Review round 2 (final permitted round for this pass)

A second, distinct fresh-context reviewer verified every round-1 fix
individually (8 of 10 fully closed; 2 only partially closed) and found
**1 P0 + 2 P1 + 4 P2 + 5 Editorial NEW findings**, all sharing one root
cause: **the strict charset mechanism was wired into the mutation
families and some ref-consuming families, but the plain read-only file
families (`cat`/`head`/`tail`/`wc`/`stat`/`grep`/`find`/`ls`/`shasum`)
were still gated by a much weaker two-character prefix check
(`_not_absolute_or_home`) that never rejected `$HOME`-style expansion,
`..` traversal, or bare glob characters**:

- **P0**: `cat $HOME/.ssh/id_rsa`, `cat $'/etc/passwd'`, and — the
  sharper escalation — `find . *` (a bare positional `*` that a real
  shell glob-expands *before* `find` ever sees it; a file named
  `-delete` created via the ungoverned Write tool would let this reach
  actual recursive deletion, the exact BUG-013 class, entirely through
  an ALLOW verdict).
- **P1**: `..`-traversal reads (`cat ../../.ssh/id_rsa`, and the same
  shape for `head`/`tail`/`wc`/`stat`/`grep`/`find`/`ls`) — the weaker
  check never rejected `..` at all.
- **P1**: `git push /tmp/exfil.git` / `git push ~/exfil.git` — the
  round-1 ref/remote charset's docstring claimed it closed "arbitrary
  remote" risk because a URL needs `://`, which is true for URLs but
  git also accepts a plain filesystem path as a remote, writing a full
  repository copy to it.
- P2s: `ls`/`shasum` had no path restriction at all; `grep -f`'s
  argument (a pattern *file*, i.e. a path) was exempted from path
  checking meant for the search pattern; the safe-path charset
  technically matched content-free tokens (`--`, `-`); a duplicate
  allowlist entry.

**Reviewer's explicit architectural determination** (the load-bearing
judgment call this task required before proceeding further): *"(a) — a
small number of local bugs in an otherwise-sound design... The failures
are confined to one identifiable omission... Both are bounded,
enumerable, single-mechanism fixes of the same shape that already
succeeded."* Confirmed once more, independently, with 120,000 fresh
fuzz cases: zero fail-open paths in `classify()`, all v1 regression
fixtures still deny correctly.

**Fixed same session** (mechanical, reusing the already-proven
mechanism per the reviewer's own recommendation): `_is_safe_relative_path`
is now the single shared gate for every path-shaped argument in every
family — `cat`/`head`/`tail`/`wc`/`stat`/`ls`/`shasum`/`grep`/`find`
included, not just mutation families — closing the `$`/traversal/glob
divergence uniformly instead of family-by-family. `find`'s walker was
rewritten to distinguish a value-taking flag's value (e.g. `-name`'s
pattern, which may legitimately contain `*`) from a bare positional
(which must be a safe literal path), closing the `find . *` escalation
without breaking `find . -name '*.py'`. `_is_safe_ref_or_remote` now
explicitly rejects a leading `/` or `~`, closing the filesystem-path
half of the remote-exfiltration vector the round-1 fix's URL-only
reasoning had missed. `grep -f`'s argument is now path-checked. The
charset's content-free-token rejection was corrected so it still rejects
bare `-`/`--` without also rejecting the legitimately-safe bare `.`
(find's cwd shorthand) — an intermediate version of this fix briefly
broke that case and was caught by this session's own test run before
being recorded here. Duplicate allowlist entry removed. Test suite:
145 → 174.

## The 2-round cap — reached, not exceeded

This redesign pass was explicitly capped at two independent review
rounds, precisely to prevent repeating v1's unbounded patch loop. That
cap has now been reached. **Per explicit instruction, no third review
was dispatched this session**, even though the round-2 fixes above were
applied (they reuse a mechanism both reviewers independently confirmed
works everywhere it has been wired in, and leaving known, well-
understood bugs unfixed would serve no one) — but those fixes are
**unverified by independent review** and must not be represented as
certified.

**Reported plainly, per instruction**: this control cannot yet be
certified this pass. To be precise about what that does and does not
mean — the second reviewer's own explicit determination was that the
remaining findings are local implementation gaps in an otherwise-sound
architecture, not evidence the allow-by-construction approach itself is
unworkable under the current Claude Code Bash/PreToolUse model. Both
facts are recorded here because they point to different next steps: a
third round (if the owner grants one) would very plausibly reach
P0=0/P1=0 given the pattern across two rounds, but per the explicit cap
that decision belongs to the owner now, not to another automatic
iteration.

**BUG-013, BUG-022, and BUG-023 all remain OPEN.** No
`.claude/settings.json` edit was made. The owner-facing settings-
integration patch file was not authored — activation requires a review
round that returns P0=0/P1=0, which this pass did not reach.

## Trusted surface (per the task's "minimize trusted code" requirement)

| Metric | v1 (superseded) | v2 (current) |
|---|---|---|
| Total lines | 1292 | 700 |
| Non-blank/non-comment-only lines | 1030 | 476 |
| Functions/classes | — (state-machine heavy) | 31 |
| Allowed read-only command families (Class A) | n/a (deny-only design) | 22 (11 git subcommand shapes + find/shasum/ls/cat/head/tail/wc/pwd/stat/grep/python3) |
| Governed mutation pathways (Class B) | n/a | 5 (git add / git commit -m / git commit -F / git push / git checkout -b / mkdir -p) |
| Unknown-command default | silent no-op (defer to `.claude/settings.json`) | explicit DENY |

## Affected / cross-referenced

`.claude/security/bash_guard.py`, `.claude/security/tests/test_bash_guard.py`,
`.claude/security/superseded_v1/**`, `knowledge/03-Modules/MOD-000/
evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md` (v1 history),
`HOOK_CONTRACT_VERIFICATION_2026-09-06.md`, `BUG_REGISTRY.md`,
`BUG-013-*.md`, `BUG-022-*.md`, `BUG-023-*.md`, `CURRENT_STATE.md`,
`CURRENT_HANDOFF.md`, `LOAD_SECURITY.md`.
