---
doc: BASH_GUARD_V2_FINAL_VERIFICATION
status: LIVE — owner-authorized final independent verification of the Round 3 P1 remediation; APPROVED FOR OWNER ACTIVATION, conditional on a settings.json write-protection caveat; BUG-013/022/023 moved to REMEDIATED — PENDING LIVE ACTIVATION VERIFICATION
updated: 2026-09-08
---

# v2 Bash Guard — Final Independent Verification (owner-authorized)

## Authorization and scope (binding, verbatim intent from the owner)

After the narrowly-scoped Sonnet remediation of Round 3's 3 P1 findings
(`BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md`), the owner
authorized **one final independent verification pass** — explicitly:
not a reopening of the old review loop, not permission for Round 4+
iterative review, not permission to begin Phase 8, not permission to
start MOD-001, not permission to activate the guard, and not permission
to modify `.claude/settings.json`.

Scope, exactly as specified: (A) independently re-verify the `grep -f`
fix against every relevant spelling; (B) independently re-verify the
trusted-script integrity mechanism, including symlink/aliasing tricks
and fail-open exception paths, and give a reasoned opinion on whether
`.claude/security/**` remaining writable is certification-blocking for
activation; (C) independently evaluate whether CAP-007 now has
sufficient evidence for `APPROVED`, without auto-approving; (D) rerun
the full 194-test suite and build fresh adversarial fixtures across the
full historical threat surface; (E) separate implementation defects from
expected pre-activation gaps, and give a definite per-item answer on
what the eventual activation patch must protect.

## Reviewer and method

`veyro-security-reviewer` (Opus, fresh context, available directly —
the fourth independent Opus review in this line, distinct from all
three Round 1-3 reviewers and from the Sonnet remediation session).
Tools: Read/Grep/Glob/Bash only — no Write/Edit, so no file could be
modified even if attempted. Independently re-inspected
`.claude/security/bash_guard.py` and its test suite from scratch,
re-ran the existing 194-test suite, and built roughly 250 of its own
fresh adversarial fixtures (fed as real PreToolUse JSON on stdin, the
guard's printed decision read from stdout — the same non-destructive
method the existing suite uses). No destructive command was run against
the real repository; symlink/tamper/exception-path probes for the
trusted-script mechanism were confined to a throwaway temp tree with
`REPO_ROOT` pointed at it, not the real repository.

## Result

**P0 = 0, P1 = 0, P2 = 6, Editorial = 9**

**Verdict: APPROVED FOR OWNER ACTIVATION**

The reviewer was explicit that this approval is conditional and
load-bearing on the activation patch containing a specific protection
(below) — approving the code artifact at commit 43de121, not
pre-approving whatever the eventual `.claude/settings.json` patch turns
out to contain.

## A. `grep -f` handling — CLOSED

27 spellings tested, all deny correctly: `-f`, `-f<path>` (attached
short-flag form, verified as valid real grep/ugrep syntax), `--file`,
`--file=<path>`, `-rf`, `-nf`, `-if`, `-hf`, `-rif`, `-rnf`, `-fr`,
`-fn`, `-rfF`, `-Ff`, `-f -r`, `-r -f`, combined with `-e`/`--regexp`,
relative and absolute path targets. Two independent mechanisms cover
the class: the literal-`f`-in-bundle check, and the generic flag-shape
charset rejecting any spelling containing `=` or `/`. No false
positives: `-F`, `-Fn`, `-rF`, `--fixed-strings`, `-i`, `-c`, `-rl`, and
a plain `grep -rn TODO knowledge` all still allow correctly.

One related gap surfaced in a *different* flag (`--exclude-from`), not
`-f` itself — recorded as P2-1 below, not part of the remediated class.

## B. Trusted-script integrity — CLOSED, activation caveat attached

All 7 pinned SHA-256 hashes in `_ALLOWED_PYTHON_SCRIPTS` were
independently recomputed and confirmed to match the current files
byte-for-byte. The integrity check is genuinely on the execution path
(`_python_readonly` requires both allowlist membership AND a passing
`_script_integrity_ok` call, not either alone).

Fresh probing against a throwaway temp tree (never the real repo)
confirmed correct fail-closed behavior for: a genuine matching file
(ALLOW, as expected); an appended-payload tamper; a single-byte/newline
tamper; a missing file; a wholly replaced file; a symlink at the pinned
path pointing to different content (DENY — `read_bytes()` and the
would-be `python3` execution follow the same link, so what's hashed is
what would execute); a symlink to identical content (ALLOW, correctly —
not a bypass since content matches); a directory at the pinned path
(`IsADirectoryError` → DENY); a permission-denied file (`PermissionError`
→ DENY); a dangling symlink (→ DENY). Exceptions from
`_script_integrity_ok` that aren't plain `OSError` still propagate to
`main()`'s blanket `except Exception`, which emits an explicit DENY —
no silent fail-open on exception was found.

**Certification-blocking-weakness determination (the owner specifically
asked for this, not a dismissal):** the reviewer's answer is **yes, for
activation** — the pinned hashes live inside the same file
(`bash_guard.py`) that has no write protection today. An agent that can
Edit that file can change a trusted script's pin and the script's
content in the same edit, or simply rewrite `classify()` to allow
everything, making the hash-pinning remediation ineffective against the
exact escalation path it was built to close, *unless* write protection
lands with it. `.claude/security/**` is the one part of the project's
own governance tree (`.claude/settings.json`, `.claude/rules/**`,
`.claude/agents/**` are already protected) that is not.

**Determination on required activation-patch protections:**
`.claude/security/**` — **required**. The 7 trusted `knowledge/` scripts
themselves — **not required as a separate protection**, since once
`bash_guard.py` is write-protected, tampering with those 6 scripts can
only produce a hash mismatch (fail-closed deny), not a privilege gain;
protecting them directly would obstruct normal evidence-tree work. The
7th (the guard's own test file) is already inside
`.claude/security/**`.

## C. CAP-007 capability governance — sufficient for APPROVED

Every one of the registry's 15 required columns was independently
checked against the actual current text of `CAPABILITY_REGISTRY.md` and
`CAPABILITY_POLICY.md` (both read directly, not assumed): provenance,
version/identity, `content_hash` (independently recomputed and
confirmed exact match), scope (including the honest "not currently
active" statement), review status, qualified/approved by-and-date,
last-reviewed/next-review dates, rollback target, and evidence paths.
`validate_capabilities.py` was confirmed to still pass with CAP-007
correctly excluded (not yet a manifest dependency).

**Determination: sufficient independent evidence exists for `APPROVED`.**
The sole blocker the prior entry recorded — no Opus review of the
remediation — is exactly what this pass supplies, in fresh context, by
a session that authored none of the guard, the remediation, or the
registry entry. `CAPABILITY_POLICY.md`'s stage 4 (independent
evaluation) and stage 5 (positive/negative testing, recorded) are both
satisfied. Two minor accuracy corrections were identified and applied
to the registry row: `qualified_by` had misattributed test-running to
the Opus reviewers rather than the Sonnet session that actually ran the
tests (policy defines the field as who ran the tests); and the
`evidence` path uses a different directory convention than most other
capability rows (`knowledge/03-Modules/MOD-000/evidence/security/`
rather than `knowledge/05-QA/capability-evidence/CAP-007/`) — flagged
as a documented deviation, not silently moved, since the files
themselves are real and correctly linked.

**`lifecycle_status` remains deliberately unset** (the registry's
3-value enum still has no value for "approved, not yet activated" — a
pre-existing documented gap, unchanged) — to be set `ACTIVE` in the same
future commit that installs the PreToolUse hook, per the reviewer's own
instruction.

## D. Regression — baseline confirmed, ~250 fresh adversarial cases

`python3 .claude/security/tests/test_bash_guard.py` → 194 tests, all
passing, confirmed independently. The reviewer's own ~250 fresh
fixtures (none previously in any test file) covered every category the
owner named — unknown commands/shapes (44 cases), shell composition
including markers embedded inside an otherwise-allowed command's own
arguments (19 cases), wrapper/absolute-path/interpreter forms (26
cases), destructive git operations (54 cases, including several forms
not previously fixture-tested: `--force-with-lease`, `--mirror`,
`switch`, `restore`, `filter-branch`, `submodule add`, `gc --prune`),
recursive filesystem deletion (22 cases), protected-artifact mutation
(18 cases) — with **zero mismatches** against the expected DENY in
every one of those categories. All 38 safe read-only operations and all
8 governed-mutation pathways (including all 7 allowlisted scripts and a
`./`-prefixed path-normalization case) still correctly ALLOW.

**BUG-013 (recursive delete), BUG-022 (absolute-path/wrapper), and
BUG-023 (redirection/alternate-write) were independently re-confirmed
closed under the current, remediated code, for the Bash surface, on
fixtures the reviewer built itself** — not merely by re-running the
existing suite. The two caveats already on record are unchanged and
re-confirmed, not newly discovered: the closure is Bash-surface-only
(Write/Edit/NotebookEdit/MCP tools never reach this hook), and it
remains *potential* rather than *actual* enforcement until the guard is
actually installed as a live hook.

### P2 findings (6, one line each — accepted-known residuals, not fixed this pass)

1. `grep --exclude-from <arbitrary-absolute-path> ...` allows; the
   flag's argument lands in an unchecked positional slot and the real
   binary opens it, giving an existence/permission oracle for arbitrary
   paths — same class as the remediated `-f` finding, a different flag.
2. `_generic_readonly_flags_ok` (shared by grep/cat/ls/stat) accepts any
   flag matching a bare shape regex rather than an explicit per-command
   allowlist, contradicting the module's own stated design principle;
   root cause of finding 1 above.
3. `_script_integrity_ok`'s `read_bytes()` has no timeout/size cap — a
   FIFO at a pinned path would hang the guard indefinitely with no
   verdict (a harness-timeout fail-open under the hook contract).
   Currently unreachable from the guarded surface (special-file creation
   is itself denied), which is why this is P2 not P1.
4. The guard assumes cwd == `REPO_ROOT` and never consults the payload's
   actual `cwd`; `cat .ssh/id_rsa` reads relative to the wrong root in
   some invocation contexts, and there is a structural TOCTOU between
   the hash-check path and the actual execution path for the same
   reason.
5. Bare `$` is not a Stage 1 composition marker, so unquoted variable/
   glob expansion in two argument slots (`grep $FOO`, `find . -name $FOO`)
   is not blocked at the string level the way other composition is.
6. All 5 of Round 3's own P2s (unrestricted script arguments, `find
   -newer` value-flag path gap, git push/fetch accepting relative
   filesystem paths as remotes, two `mkdir -p` edge cases) were
   independently re-confirmed still reproducible — expected, since the
   remediation pass was explicitly P1-only.

### Editorial findings (9, one line each)

Misleading `UNRECOGNIZED_SUBCOMMAND` reason for a flag-shape rejection
on `git log`; a `-5`/`-n 5` usability asymmetry on `git log`; trailing-
slash and `--`-positional false-denies on `ls`/`cat`/`git add`; the
CAP-007 evidence-path convention deviation (see Part C); the CAP-007
`qualified_by` misattribution (see Part C, now corrected); the
registry's `lifecycle_status` field being absent from the table schema
entirely (pre-existing, affects every row, not just CAP-007); this
review re-running the test suite and authoring fresh fixtures, which
`CAPABILITY_POLICY.md`'s prose says an assurance reviewer should not do
— recorded as a knowing, owner-authorized deviation for this specific
verification task, not an oversight; `REPO_ROOT`'s symlink-following
resolution (a symlinked guard file would silently relocate its own
integrity root); and the silent-exit-on-non-Bash-payload behavior being
documented only in a code comment, not in the activation record.

## E. Owner-activation boundary — expected gaps vs. defects

**Expected pre-activation gaps, confirmed correct, not defects:** no
`PreToolUse` entry exists in `.claude/settings.json` (confirmed zero
occurrences); CAP-007 is not present in `module-capabilities.yaml`;
BUG-013/022/023 remain open as defects pending live activation.

**Per-item determination on what the eventual activation patch must
protect via `.claude/settings.json`'s Edit/Write deny list:**

| Item | Add protection? | Reasoning |
|---|---|---|
| `.claude/security/**` | **YES — required** | The single most important addition; without it the guard's own code and pinned hashes are editable by the agent it constrains. |
| `.claude/settings.json` | Already present | No change needed. |
| `.claude/rules/**` | Already present | No change needed. |
| `.claude/agents/**` | Already present | No change needed. |
| 3 governing docx baselines + design bundle | Already present | No change needed. |
| `CLAUDE.md` | **YES — currently missing** | Not present anywhere in the deny list; the guard covers it only for Bash-family path arguments, not for direct Edit/Write. |
| `.mcp.json` | **YES — pre-emptive** | File doesn't exist yet; adding the deny now costs nothing and closes the window at creation time. |
| The 7 trusted `knowledge/` scripts | **NO** | Once `bash_guard.py` itself is write-protected, tampering with these can only produce a hash-mismatch deny, not a privilege gain; a hard write-deny would obstruct normal evidence-tree work. |
| `CAPABILITY_POLICY.md`/`DEVELOPMENT_CONSTITUTION.md`/`PROJECT_INDEX.md` | **NO** | Living governance documents sessions must be able to update as part of normal work; `verify_baselines.py` plus Git history already provide tamper evidence without a hard deny. |

**Two additional activation-patch requirements identified**, beyond the
deny list: an explicit `timeout` on the PreToolUse hook entry (P2-3
shows the guard can hang; the harness's own timeout-then-proceed
behavior is the actual fail-open boundary in that case), and setting
CAP-007's `lifecycle_status: ACTIVE` in the same commit that installs
the hook.

## Section 5 actions taken this pass (only because P0=0 AND P1=0)

1. **CAP-007 approved** in `CAPABILITY_REGISTRY.md` per the reviewer's
   exact specified fields (review_status, approved_by, approved_date,
   next_review_due, last_reviewed_at), with the two accuracy corrections
   noted in Part C applied. Not added to `module-capabilities.yaml` —
   the reviewer's own determination was that policy does not require
   this until the guard is actually activated, and inventing that
   binding now would exceed what was authorized.
2. **Owner activation patch drafted, not applied**: see
   `knowledge/03-Modules/MOD-000/evidence/security/BUG-013-022-023-OWNER-SETTINGS-PATCH.md`.
   `.claude/settings.json` itself was not modified, staged, or read for
   editing purposes beyond the read-only inspection needed to draft an
   accurate patch.
3. **`BUG-013`, `BUG-022`, and `BUG-023` moved to `REMEDIATED — PENDING
   LIVE ACTIVATION VERIFICATION`** — explicitly not closed. Per the
   owner's exact instruction, closure requires: the owner manually
   applies the settings patch; a fresh Claude Code session starts; the
   PreToolUse hook is proven to actually execute; live destructive
   fixtures are proven denied; safe operations are proven unaffected —
   all deferred to a future session with the owner present.
4. **Durable evidence and Notion mirror updated** — see the commit this
   evidence file ships with for the full file list.

## What this pass does NOT do

- Does not activate the guard or modify `.claude/settings.json`.
- Does not close BUG-013, BUG-022, or BUG-023 — moved to a distinct
  "remediated, pending live verification" state, not CLOSED.
- Does not fix the 6 P2 or 9 Editorial findings — recorded as
  accepted-known residuals for a future, separately-authorized pass.
- Does not add CAP-007 to `module-capabilities.yaml` — deferred to
  actual activation.
- Does not begin Phase 8 or start MOD-001.
