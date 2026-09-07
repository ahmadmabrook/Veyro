# Archived: What happened chunk 23, 2026-09-07 — narrowly-scoped remediation of Round 3's 3 P1 findings (explicitly NOT a Round 4 review); BUG-013/022/023 remain OPEN

Per explicit owner authorization: fix exactly the three Round 3 P1
findings, add regression tests, rerun the suite and affected validators,
verify baselines and git integrity, update evidence — nothing more.
Binding: not a Round 4 review; no Phase 8; no MOD-001; no guard
activation; no `.claude/settings.json` edit; no owner activation patch;
no requesting or running another independent security review this turn.

**1. `grep -f` handling — fixed.** Round 3's P1-1 was that the Round-2
fix only matched the exact token `-f`, leaving every bundled short-flag
spelling (`-rf`, `-nf`, `-if`, `-hf`) and both long forms (`--file`,
`--file=...`) able to leak an unbounded file read. A new
`_requests_grep_pattern_file(flags)` helper in `bash_guard.py` matches
any short flag containing a literal lowercase `f` after the dash, plus
the exact long forms — denying the whole `-f` pattern-file mode outright
in every spelling rather than trying to path-check it (per the owner's
explicit instruction not to broaden grep's recognized shapes). Uppercase
`-F` (grep's real, unrelated fixed-strings flag) is untouched, preserving
the case-sensitive-exact-shape convention the rest of the file uses. 10
new regression tests (`RR3_GrepDashFAllSpellings`): every bad spelling
denies, `-F` and a plain `grep -rn` still allow.

**2. Trusted-script allowlist integrity — fixed, with one disclosed
residual.** Round 3's P1-2 was that `_ALLOWED_PYTHON_SCRIPTS` trusted a
path string alone — no content check — so any edit to one of the seven
allowlisted scripts stayed silently, permanently trusted.
`_ALLOWED_PYTHON_SCRIPTS` is now a `{path: sha256_hex}` map; a new
`_script_integrity_ok()` reads the real file (resolved from
`bash_guard.py`'s own location via `REPO_ROOT`, not process cwd) and
denies on any hash mismatch, missing file, or unlisted path — no
fallback that trusts the path alone. Update governance documented
inline: a script edit and its hash update must land in the same commit.
**Residual, explicitly not closed:** this is tamper *detection*, not
write *prevention* — `.claude/settings.json`'s Edit/Write deny coverage
still does not extend to `.claude/security/**`, and this pass did not
touch `.claude/settings.json` per instruction; a future owner-authorized
settings change is still needed to fully close this half. 5 new isolated
unit tests (`RR3_TrustedScriptIntegrity`, using `tempfile` fixtures — no
real repository file read, written, or mutated) plus 5 new end-to-end
positive tests confirming all 7 real pinned hashes are correct against
the actual current repository files.

**3. `CAPABILITY_POLICY` registration — fixed, honestly scoped.**
Round 3's P1-3 was that the guard — a project-authored executable hook
with filesystem scope — had never been registered under this project's
capability-governance process. Registered as **CAP-007** in
`CAPABILITY_REGISTRY.md` with the full 15-field schema already used by
CAP-001 through CAP-006 — no parallel mechanism invented.
`review_status` recorded as **`QUALIFIED — NOT APPROVED`**, not
force-labeled `APPROVED`: `CAPABILITY_POLICY.md`'s own model-routing rule
bars a capability from becoming `APPROVED` "solely from a Sonnet
implementation run," and this turn's explicit instruction was not to
request an Opus review — recording `APPROVED` here would have violated
the exact policy this registration exists to demonstrate compliance
with. Deliberately **not** added to
`knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml` this
pass, since `validate_capabilities.py` requires every manifest-
referenced capability's registry row to contain "approved" and MOD-000
does not depend on this unactivated guard for any real gate yet — adding
it now would either fail the validator or falsely claim a live
dependency; deferred until the guard is both `APPROVED` and activated.
The registry's `lifecycle_status` field (`ACTIVE`/`DEPRECATED`/
`REVOKED`) has no value for "reviewed, not yet approved, not yet
activated" — flagged as a schema gap (in the spirit of this project's
existing BUG-010/F5-027 pattern) rather than force-fit.

**Verification: 194/194 tests passing** (174 pre-existing + 20 new).
`verify_baselines.py` — PASS, all 4 hashes unchanged.
`validate_capabilities.py` — PASS, 6 capability/capabilities (CAP-007
correctly not manifest-bound, so invisible to this check by design).
`validate_catalog.py` — PASS, 0 errors. `evidence_integrity_check.py` —
PASS (one new expected-forward-reference entry added for the still-
unauthored owner settings patch file, matching the project's existing
`APPROVAL.md`-style forward-reference pattern). Local HEAD verified
against `origin/main` after commit (see this chunk's commit SHA below).

**`BUG-013`, `BUG-022`, and `BUG-023` all remain OPEN.** This chunk is
remediation, not certification — no independent Opus evaluation of these
three fixes has occurred, and none was authorized this turn.
`.claude/settings.json` was not staged or modified — it remains the
owner's own untouched pending edit. **Phase 7 gate remains BLOCKED.
Phase 8 is NOT legally unlocked.** Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md`.
