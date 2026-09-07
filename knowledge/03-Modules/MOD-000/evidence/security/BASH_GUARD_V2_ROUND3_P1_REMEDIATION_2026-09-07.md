---
doc: BASH_GUARD_V2_ROUND3_P1_REMEDIATION
status: LIVE — narrowly-scoped Sonnet remediation of Round 3's 3 P1 findings; NOT an independent review; BUG-013/022/023 remain OPEN
updated: 2026-09-07
---

# v2 Bash Guard — Round 3 P1 remediation (narrowly-scoped, not a Round 4 review)

## Authorization and scope (binding, verbatim intent from the owner)

After Round 3 (`BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md`) returned
P0=0/P1=3, verdict BLOCKED, the owner authorized a **narrowly-scoped
remediation pass for the three Round 3 P1 findings only** — explicitly
**not** a Round 4 security review. Binding constraints: do not begin
Phase 8; do not start MOD-001; do not activate the guard; do not modify
`.claude/settings.json`; do not create the owner activation patch; do
not request or run another independent security review this turn. Fix
exactly the three named P1s, add regression tests, rerun the suite and
affected validators, verify baselines and git integrity, update durable
evidence, and report a fixed list of results — no more, no less.

**This document records remediation, not certification.** No Opus
reviewer has evaluated these fixes. BUG-013, BUG-022, and BUG-023 remain
OPEN; nothing in this pass is represented as closing them.

## 1. `grep -f` handling — fixed

**Prior gap (Round 3 P1-1):** `_grep_readonly` gated the pattern-file
check on `"-f" in flags` — exact token equality. Bundled short-flag
forms (`-rf`, `-nf`, `-if`, `-hf`, `-Ff`, `-rif`) and the long forms
(`--file`, `--file=...`) all fell through to the plain-pattern branch,
which treats `positionals[0]` as search text rather than the path it
actually is under `-f` semantics — an unbounded file read via an
explicit ALLOW.

**Fix:** `.claude/security/bash_guard.py`'s `_grep_readonly` now calls a
new `_requests_grep_pattern_file(flags)` helper before doing anything
else. It matches: the exact tokens `-f`/`--file`; any token starting
with `--file=`; and any short-flag token (starts with `-`, is not a
recognized long flag) containing a literal lowercase `f` anywhere after
the leading dash — which covers every bundled short-flag spelling
without needing to enumerate them individually. Matching is on lowercase
`f` specifically, preserving this guard's existing case-sensitive-exact-
shape convention and correctly leaving grep's real, unrelated `-F`
(fixed-strings) flag untouched. Per the owner's explicit instruction
("do not broaden grep into arbitrary shell behavior... unknown/
unsupported forms must fail closed"), the fix does **not** add pattern-
file support with proper path-checking for every spelling — it drops
`-f`/`--file` pattern-file mode entirely, in every spelling, fail-closed
by construction rather than by an enumerated denylist. A legitimate
`grep <pattern> <path>` invocation with none of these flags is
unaffected.

**Regression tests added** (`RR3_GrepDashFAllSpellings`, 10 tests):
`-rf`, `-nf`, `-if`, `-hf`, `-rif` (bundled forms), `--file`,
`--file=...` (long forms), a relative (not just absolute) path target
under `-rf` to confirm the denial isn't merely an absolute-path check, a
positive control confirming uppercase `-F` (fixed-strings, unrelated
flag) still allows, and a positive control confirming a plain
`grep -rn TODO knowledge` with no `-f` anywhere still allows.

## 2. Trusted-script allowlist integrity — fixed, with one disclosed residual

**Prior gap (Round 3 P1-2):** `_ALLOWED_PYTHON_SCRIPTS` was a set of
seven path strings. A path appearing in the set was the *entire* trust
decision — the guard never read the file's actual content, so any edit
to one of the seven allowlisted scripts (a routine change or a
compromise) was silently and permanently re-trusted. Separately,
`.claude/settings.json`'s Edit/Write deny coverage does not extend to
`.claude/security/**` at all.

**Fix implemented this pass — deterministic content-hash pinning:**
`_ALLOWED_PYTHON_SCRIPTS` is now a `{relative_path: sha256_hex}` map
instead of a bare set. A new `_script_integrity_ok(relpath)` function
reads `REPO_ROOT / relpath` (where `REPO_ROOT` is derived from
`bash_guard.py`'s own file location — `Path(__file__).resolve().parents[2]`
— not the process cwd or the hook payload's `cwd` field, since neither
is guaranteed stable across every invocation context) and compares its
SHA-256 digest to the pinned value. `_python_readonly` now requires
**both** the path to be in the map **and** `_script_integrity_ok` to
return `True` before allowing. Every failure mode — unknown path,
missing file, unreadable file, hash mismatch — returns `False`, with no
fallback that trusts the path string alone. All 7 real hashes were
computed via `sha256sum`/`hashlib.sha256` against the actual current
repository files (values recorded in `bash_guard.py` itself and in
`CAPABILITY_REGISTRY.md`'s CAP-007 row).

**Governance for updates (the deterministic mechanism the owner's
instruction required to be documented):** a change to any one of the
seven scripts and the update to its hash entry in
`_ALLOWED_PYTHON_SCRIPTS` MUST land in the same reviewed commit —
`sha256sum <path>` gives the exact value to paste. A script edited
without a corresponding hash update simply stops being executable
through this guard (fails closed); a hash entry changed with no real
script change is a self-evident, reviewable one-line diff. This mirrors
the file's existing "adding a new script is a reviewable, one-line
change" design principle rather than inventing a new mechanism.

**Disclosed residual, not silently closed:** this is content-**tamper
detection**, not **write prevention**. Nothing in this fix stops an
Edit/Write tool call from modifying one of the seven files in the first
place — `.claude/settings.json` was not touched this pass, per explicit
owner instruction. The practical effect is still real and closes the
specific bypass Round 3 found: a tampered file can no longer be
*executed* through this guard once its hash stops matching, so "trusted
because the path matched" is no longer true. But the underlying write
itself remains possible today. **This residual requires a future
owner-authorized `.claude/settings.json` change** (extending Edit/Write
deny coverage to `.claude/security/**`) to fully close — tracked here
explicitly, not represented as done.

**Regression tests added** (`RR3_TrustedScriptIntegrity`, 5 tests, plus
5 new end-to-end positive tests in `ClassA_ReadOnly` for the 5
previously-untested allowlisted scripts): unit-level tests import
`bash_guard` directly and exercise `_script_integrity_ok` against
temporary fixture files in an isolated `tempfile.TemporaryDirectory()`
(no real repository file is read, written, or mutated by any test) —
matching-hash passes, tampered-content fails closed, missing-file fails
closed, unlisted-path fails closed, and one end-to-end test that drives
the real `classify()` entry point (not just the helper) with a
deliberately wrong pinned hash to confirm the DENY actually propagates
through `_python_readonly`/`classify()`.

## 3. `CAPABILITY_POLICY` registration — fixed, honestly scoped

**Prior gap (Round 3 P1-3):** `bash_guard.py` — a project-authored
executable hook with filesystem scope, about to become the sole
authority over every Bash call — was never registered in
`CAPABILITY_REGISTRY.md`, despite `CAPABILITY_POLICY.md` requiring
exactly this profile of capability to have a full registry row before
any module may depend on it.

**Fix:** registered as **CAP-007** in `CAPABILITY_REGISTRY.md` with the
full required field set (provenance, version/identity, content_hash,
scope, review_status, qualified_by/date, approved_by/date,
last_reviewed_at, next_review_due, rollback_target, evidence). No
parallel governance mechanism was invented — this uses the exact same
table, the exact same 15 required columns, and the exact same
`validate_capabilities.py` machinery every other capability in this
project goes through.

**Honest status recorded, not overclaimed:** `review_status` is
**`QUALIFIED — NOT APPROVED`**, not `APPROVED`. Three independent Opus
reviews have evaluated this guard (v2 Round 1, Round 2, and the final
Round 3), and all three judged the underlying architecture sound — but
`CAPABILITY_POLICY.md`'s own model-routing rule states plainly: "No
capability may become `APPROVED` solely from a Sonnet implementation
run." This remediation pass is exactly that — a Sonnet session fixing
named findings — and the owner's explicit instruction for this turn was
**not** to request or run another independent review. Recording
`APPROVED` here would violate the policy this registration is supposed
to demonstrate compliance with. An Opus review of this remediation
(itself requiring fresh owner authorization, since the Round 3 review
budget is exhausted) is the actual precondition for `APPROVED`.

**Required module binding recorded, without inventing a false
dependency:** CAP-007 binds to MOD-000 (project-scoped control-plane
tooling). It was deliberately **not** added to
`knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml` this
pass — `validate_capabilities.py` requires every manifest-referenced
capability's registry row to contain "approved" in `review_status`
(case-insensitive substring match), and MOD-000 does not currently
depend on this guard for any real gate (it remains unactivated in
`.claude/settings.json`). Adding a manifest row now would either falsely
claim an active dependency that doesn't exist, or fail the validator —
both worse than the current honest state. The manifest row is deferred
to whenever the guard is both `APPROVED` and actually activated.

**A schema gap surfaced and disclosed, not force-fit:** the registry's
`lifecycle_status` field is a 3-value enum (`ACTIVE`/`DEPRECATED`/
`REVOKED`) with no value that honestly describes "reviewed, not yet
approved, not yet activated." CAP-007 is recorded with a note explaining
this gap explicitly (in the same spirit as this project's existing
BUG-010/F5-027 "flag the gap, don't paper over it" pattern) rather than
being force-labeled `ACTIVE` (false — it isn't running) or omitted
silently.

**Validator confirmed unaffected:** `validate_capabilities.py` was
re-run after this registration and still returns `PASS — 6
capability/capabilities, all registered and APPROVED` — CAP-007 is
correctly invisible to that check because it is not (yet) referenced in
`module-capabilities.yaml`, exactly as intended. The registry row itself
was independently confirmed to parse to the correct 15-cell shape the
validator's own row parser expects.

## Verification performed this pass

- **Full test suite:** 174 pre-existing tests + 20 new tests = **194
  tests, all passing** (`python3 .claude/security/tests/test_bash_guard.py`).
  The 20 new tests: 10 for `grep -f` spellings
  (`RR3_GrepDashFAllSpellings`), 5 for trusted-script integrity
  (`RR3_TrustedScriptIntegrity`), 5 new end-to-end positive tests for the
  5 previously-untested allowlisted scripts (added to `ClassA_ReadOnly`,
  serving as a live regression check that all 7 pinned hashes are
  correct against the real, current repository files).
- **Validators re-run:** `verify_baselines.py` — PASS, all 4 governing
  baseline hashes unchanged. `validate_capabilities.py` — PASS, 6
  capability/capabilities (CAP-007 correctly not yet manifest-bound).
  `validate_catalog.py` — PASS, 0 errors. `evidence_integrity_check.py`
  — PASS, no broken references beyond expected forward refs.
- **Baseline hashes:** independently re-verified unchanged (all 4 exact
  matches against `PROJECT_INDEX.md`).
- **Git integrity:** local HEAD and `origin/main` verified identical
  after this pass's commit (see the chunk record in `CURRENT_HANDOFF.md`
  for the exact SHA). `.claude/settings.json` was not staged or
  committed — it remains the owner's own untouched pending edit.

## What this pass does NOT do

- Does not certify the guard, activate it, or create the owner
  activation patch.
- Does not close BUG-013, BUG-022, or BUG-023 — all three remain OPEN.
- Does not run or request an independent security review (Round 4 or
  otherwise) — that decision remains the owner's, requiring fresh
  authorization, per the exhausted Round 3 review budget.
- Does not fully close Round 3 P1-2's write-protection half (the
  `.claude/settings.json` Edit/Write deny extension to
  `.claude/security/**`) — disclosed above as a tracked residual.
- Does not mark CAP-007 `APPROVED` — disclosed above as requiring a
  future Opus review this session was explicitly not authorized to run.
