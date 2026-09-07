---
doc: BASH_GUARD_V2_ROUND3_REVIEW
status: LIVE — final owner-authorized review round for the v2 architecture; BLOCKED (P1=3); no further round authorized
updated: 2026-09-07
---

# v2 Bash Guard — Round 3 Independent Security Review (final authorized round)

## Authorization

After v2 (allow-by-construction, fail-closed) passed two independent
review rounds — both explicitly judging the *architecture* sound while
finding local implementation gaps (see
`BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`) — the owner authorized
**exactly one additional review round** as the final verification round
for the current architecture, with these binding constraints stated
verbatim by the owner:

> This authorization does NOT permit: open-ended further review rounds;
> architectural redesign; starting Phase 8; starting MOD-001; activating
> the guard; modifying `.claude/settings.json`; creating the owner
> activation patch unless Round 3 passes with P0=0 and P1=0.

The owner's gate rule (also verbatim, binding) governs everything below:
if Round 3 returns P0=0 AND P1=0, remediate P2/Editorial only if safe,
rerun tests, create (not apply) the owner settings-activation patch,
update evidence/Notion, commit/push, and report activation-ready. If
Round 3 returns **any** P0 or P1: stop, do not patch, do not request
Round 4, do not activate, record the fixed verbatim string below, and
keep BUG-013/022/023 OPEN, Phase 7 BLOCKED, Phase 8 LOCKED.

## Reviewer and method

`veyro-security-reviewer` (Opus, fresh context — this custom agent type
was available directly this session; no substitution was needed, unlike
Rounds 1 and 2 which used a briefed `general-purpose`@Opus stand-in).
Independently re-inspected `.claude/security/bash_guard.py` and
`.claude/security/tests/test_bash_guard.py` from scratch; re-tested
every Round 1/Round 2 P0/P1 and its claimed remediation; re-ran all
historical BUG-013/022/023 bypass classes; ran 500,000 fresh adversarial
cases against `classify()` (structured dangerous-command permutations,
random control-character/metacharacter strings, and quoting/whitespace
mutations of the allowed shapes) plus targeted probes of oversized
inputs and exotic Unicode/control-character injections; confirmed a
required real-command usability list still allows; and verified two
grep/glob findings against real (non-destructive) shell semantics before
reporting them. No files were modified, no destructive command was run
against the repository — every proof is a guard decision read from
PreToolUse JSON on stdin, plus two read-only `grep`/glob checks.

## Result

**P0 = 0, P1 = 3, P2 = 5, Editorial = 7**

**Architectural verdict: BLOCKED**

The reviewer was explicit that this verdict is not a repeat of v1's
pattern (every round finding something structurally new about the
design itself). The allow-by-construction architecture held under all
500,000 adversarial cases — `classify()` never returned without an
explicit allow/deny verdict and never raised an unhandled exception; the
Stage-1 composition ban and Stage-2 `shlex` tokenization behaved exactly
as designed; every historical BUG-013/022/023 bypass fixture denied
correctly. But the owner's bar for this round was P0=0/P1=0, and one of
the three P1s is a Round-2 finding recorded as fixed that is not
actually fixed for every input spelling — precisely the failure mode
this final round existed to catch.

### P1-1 — `grep -f` pattern-file path check defeated by every spelling except the one tested

`_grep_readonly` in `bash_guard.py` gates the pattern-file check on
`if "-f" in flags:` — exact token equality. Bundled short-flag forms
(`-rf`, `-nf`, `-if`, `-hf`, `-Ff`, `-rif`) contain the letter `f` but
are not the literal token `-f`, so they fall through to the generic
branch, which path-checks only `positionals[1:]` on the assumption that
`positionals[0]` is search text — under `-f` semantics it is actually a
**path**. `--file <path>` is separately unrecognized as the `-f` case at
all and its value lands unchecked. Confirmed allowed:
`grep -rf /etc/passwd .`, `grep -nf ~/.ssh/id_rsa knowledge`,
`grep -if ~/.aws/credentials knowledge`, `grep --file /etc/passwd
knowledge`, `grep -rf ../../../etc/shadow .`. This is an explicit ALLOW
(bypasses the permission system entirely) for an unbounded read of any
file on the machine, confirmed against real `grep` semantics
non-destructively. `BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`'s claim
that "`grep -f`'s argument is now path-checked" is true only for the one
literal spelling Round 2's fixture tested
(`test_grep_dash_f_absolute_path`) — the class is open, and this also
falsifies the stronger claim that path arguments now run through
exactly one shared check everywhere.

### P1-2 — `_ALLOWED_PYTHON_SCRIPTS` trusts seven mutable paths with no content pinning, and `.claude/security/**` has no write protection

`_python_readonly` matches `tokens[0]` against a set of path strings
with no hash/signature/immutability check. Separately,
`.claude/settings.json`'s deny list protects `.claude/settings.json`,
`.claude/rules/**`, and `.claude/agents/**` from Edit/Write, but the
string `security` appears nowhere in it — `.claude/security/bash_guard.py`
and its own test file are freely writable, and so are all six allowlisted
`knowledge/` validator scripts. A single Edit to any of the seven —
including routine housekeeping edits agents make to those scripts as a
matter of course — converts `python3 <that path>` into an explicit ALLOW
for arbitrary Python execution, re-opening BUG-013/022/023 wholesale
through a path the guard itself blesses. This directly conflicts with
`CAPABILITY_POLICY.md`'s requirement that filesystem-resident
capabilities carry a `content_hash`. (No script currently performs any
write — the finding is about the trust mechanism, not present
behavior.)

### P1-3 — the guard is not a registered capability under `CAPABILITY_POLICY.md`

`bash_guard.py` appears nowhere in `CAPABILITY_REGISTRY.md` (which ends
at CAP-006). It is a project-authored executable hook with filesystem
scope, about to become the sole authority over every Bash call — exactly
the profile the policy's stage 4 requires an independent Opus
capability-security review for, and stage 7 requires a full registry row
for (provenance, version, `content_hash`, scope, `review_status`,
`qualified_by`, `approved_by`, `next_review_due`, `rollback_target`)
*before* any module may depend on it. The policy's fail-closed rule:
not `APPROVED` in the registry means not usable. The reviewer flagged
this as a gap rather than treating its own review as satisfying it —
this Round 3 review is one input toward that record, not the record
itself, and the reviewer explicitly declined to self-approve prior work
in this line.

### P2 (5) and Editorial (7) findings

Recorded in full in the Round 3 agent transcript; summarized:
`find`'s value-taking flag values (e.g. `-newer <path>`) are exempt from
path checking (out-of-repo mtime/existence oracle); the unquoted-glob
divergence Round 2 fixed for bare positionals is still reachable through
those same value-flag values; `_is_safe_ref_or_remote` accepts relative
filesystem paths as git push/fetch remotes (`git push .claude/x.git
main`); allowlisted Python scripts' own arguments are unrestricted,
letting `mr_verify.py <arbitrary-path>` read outside the repo; and
`mkdir -p knowledge/.git` / `mkdir -p knowledge/-delete` are both
allowed. Editorial: `tool_name` mismatches and malformed stdin fail
silently rather than denying (harness-dependent, not model-controllable,
but should be documented); misleading deny-reason codes for read-only
families; trailing-slash paths (`ls knowledge/`) wrongly denied; `git
add -- <path>` wrongly denied; bare `shasum -a` / bare `find` allow and
read stdin/cwd; `git add knowledge` (whole top-level directory) allowed
despite the project's own stated single-file convention; and a
documented-but-unasserted `\r`-as-whitespace divergence between `shlex`
and the real shell.

### BUG-013 / BUG-022 / BUG-023 status confirmed under the current guard

- **BUG-013 (recursive delete):** closed for the Bash surface across 30
  variants tested (`rm -r/-R/-rf/-fr`/reordered/verbose, `rmdir`,
  `unlink`, `shred`, `srm`, `trash`, `find -delete`/`-exec`/`-execdir`/
  `-ok`/`-fls`/`-fprintf`, `git rm -r[f]`, quoting evasions). Residual:
  the value-flag-glob P2 above is a theoretical route back to a
  `-delete`-shaped argument.
- **BUG-022 (absolute-path/wrapper/case):** closed for the Bash surface
  across the full historical fixture set plus new probes (`/bin/rm`,
  `/usr/bin/git`, `env`, `command`, `builtin`, `nice`, `sudo`, `doas`,
  `su -c`, `xargs`, `timeout`, `nohup`, `setsid`, `stdbuf`, `eval`,
  `exec`, `source`, every shell `-c` form, every inline interpreter
  invocation, case variants, `git -c`/`-C`). Inline interpreter
  invocation is confirmed genuinely unreachable, not merely unlisted.
  Residual: P1-2 is a wrapper-class re-entry via a different mechanism
  (rewriting a *trusted* script rather than wrapping an *untrusted* one).
- **BUG-023 (redirection/alternate write):** closed for the Bash surface
  — every redirection spelling dies at Stage 1 on the raw string before
  any parsing, and every v1-era write primitive (`tee`, `sed -i`, `mv`,
  `cp`, `dd`, `rsync`, `scp`, `curl -o`, `wget -O`, etc.) is simply an
  unknown command. **Scope caveat carried forward explicitly:** this
  closure is Bash-surface-only. Write/Edit/NotebookEdit/MCP tools never
  reach this hook and remain governed solely by `.claude/settings.json`'s
  globs — which, per P1-2, do not cover `.claude/security/**`.

### Usability and fail-closed confirmation

All required real MOD-000 commands (reading `knowledge/` files, the
full `git status/diff/log/show/add/commit -m|-F/push/checkout -b` set,
`mkdir -p knowledge/…`, all six validator scripts, the guard's own test
suite) still allow — the 174-test suite passes clean. The 500,000-case
adversarial run found zero fail-open cases and zero unhandled
exceptions; every unintended allow traced back to P1-1 or one of the
five P2s, not to a structural gap in the classify-or-deny invariant
itself.

## Gate-rule application (binding, per owner instruction)

Round 3 returned P1 = 3 (> 0). Per the owner's exact gate rule, this
session:

- **Does not** patch these findings and request a Round 4.
- **Does not** continue the review loop.
- **Does not** activate the guard.
- **Does not** modify `.claude/settings.json`.
- **Does not** create the owner settings-activation patch file.

Recorded per instruction, verbatim:

> CURRENT PRETOOLUSE BASH CONTROL NOT CERTIFIABLE UNDER THE APPROVED REVIEW BUDGET

**BUG-013: OPEN. BUG-022: OPEN. BUG-023: OPEN. Phase 7: BLOCKED. Phase 8: LOCKED.**

## What would move this to APPROVED FOR ACTIVATION (reviewer's own assessment, not an instruction to act on it this session)

Fix `_grep_readonly` to path-check `positionals[0]` whenever any flag
token contains `f` or is `--file`/`--file=…` (or drop `-f` support
entirely, in keeping with the architecture's own preference for fewer
recognized shapes over more parsing). Pin `_ALLOWED_PYTHON_SCRIPTS` to
SHA-256 content hashes and extend `.claude/settings.json`'s
Edit/Write deny coverage to `.claude/security/**`. Register the guard in
`CAPABILITY_REGISTRY.md` with the full supply-chain field set, approved
by a review that is not the session that wrote the guard. The five P2s
are one- or two-line fixes of the same shape and worth folding in, but
are not what blocks this round's verdict. None of this is authorized to
be acted on under the current review budget — it is recorded for the
owner's decision on next steps.

## Relationship to prior rounds

Unlike v1 (four rounds, each finding something structurally new about
the *design*, treated as an architectural failure), both v2 rounds 1-2
and this Round 3 found local, bounded implementation gaps in a design
all three reviewers independently judged sound. Round 3's P1-1 is
notable as a partial-fix miss (a Round 2 remediation that was correct
for its tested fixture but not for the general case) — a caution about
declaring a class "closed" from a single fixture, not evidence against
the architecture itself.
