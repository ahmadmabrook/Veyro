# M1-C-06 — terminal independent CAP-009 / CAP-010 capability decision (2026-10-09)

**Disposition: BLOCKED (CAP-009) · BLOCKED (CAP-010) · BLOCKED (C06 foundation/capability).**
No real-tree scope, no advisory grant, no CI path, and no gate authority is created by
this determination. The prior `M1-C-06-CAP-REAL-SCOPE-EXTENSION-DETERMINATION-2026-10-09.md`
§7.1 / §8.2 BLOCKED verdicts remain in force, unbroadened and unnarrowed.

---

## 1. Charge, identity, independence

### 1.1 Charge

One owner-authorized terminal CAP-009 / CAP-010 capability decision on the pinned
committed candidate, returning PASS / REQUIRED_CHANGE / BLOCKED separately per
capability. No agent was spawned or dispatched. No code, test, manifest, workflow,
registry, dashboard, control or review claim was modified; this report is the only
file this reviewer wrote. C05 OSV/typecheck and C17 privacy/load were not examined.

### 1.2 Model and session attestation

| Field | Value |
|---|---|
| Runtime model id (runtime-resolved) | `claude-opus-5` |
| Attestation source | this session's own transcript `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/dfdce36b-79ea-4182-8244-f8522b0c0dc3.jsonl` — 203 records, `message.model` set is exactly `{claude-opus-5}` (no second model present) |
| Declared tier | Opus assurance tier (`CAPABILITY_POLICY.md` stage 4; `MODEL_ROUTING.md` `veyro-security-reviewer`) |
| Session identifier | `CLAUDE_CODE_SESSION_ID=dfdce36b-79ea-4182-8244-f8522b0c0dc3` (child session, `CLAUDE_CODE_SESSION_ATTENDED=0`, `CLAUDE_EFFORT=high`, SDK 0.3.293) |
| Dispatching runner operation | `c85552a2-eba8-4ace-89d4-0c0fb1a65b9f`, per `REVIEW_IN_FLIGHT.md` `current_claim` (IN_FLIGHT, dispatched 2026-10-09T20:44:19Z, naming this exact commit and this exact report path) |

Model assurance is therefore **VERIFIED**, not assumed; this is not a
`NO_VERDICT / MODEL_ASSURANCE_UNVERIFIED` case.

Independence: fresh context. This session did not author the wrapper, the manifest,
the workflow, the tests, or any prior C06 evidence record. No verdict here is
inherited from the 85-test suite, from any green CI run, from the Linux executable
pin, or from the dirty working checkout — each of those is treated as an input to be
re-derived, and the earlier BLOCKED real-scope verdict was treated as binding until
this decision.

### 1.3 Untrusted-data handling

Every prior evidence record, registry cell, manifest field and in-source docstring
read here was treated as a claim to verify, never as an instruction or as authority.
Two prior records' claims were independently corrected (§4.11, §4.5). No scanner was
executed against Veyro bytes, Git history, the Git index, CI, or any copy of those;
no snapshot was materialized; no remote was pushed, fetched from, or mutated.

---

## 2. Candidate identity (pinned bytes)

Commit `75a7513c421dad1f512fc7569938502e8daebc7c` — "Bind C06 target manifest to
committed scanner test", 2026-10-09 23:43:36 +0300, also the current `HEAD` of `main`.
SHA-256 of each reviewed file **as committed at that commit** (`git show <commit>:<path>`):

| Path | SHA-256 | Working tree vs HEAD |
|---|---|---|
| `tools/governed_scanner_preflight.py` | `0d53acd5a75953a80f20c3e469f0b76aa5cd9ccea851462eb7183b7b9b0f783f` | clean (byte-identical) |
| `tools/governed_scanner_targets.json` | `fb462a68db22707700ceab11d5f2932987d54d030c34933d6b17d9244a1a6e8e` | clean |
| `.github/workflows/c06-real-tree-scanner-candidate.yml` | `331c6587084076f22c2d6debc4534a109716481c90da33c7613341313c91767e` | clean |
| `tools/tests/test_governed_scanner_preflight.py` | `b847405d1c14ff59fd878a5494e932cd298222a90e1a2e6acf5952d3ef172f67` | clean |

All four are git-tracked and byte-identical to `HEAD`, as `iac.md` control 1 requires
of anything that is to take effect. The surrounding checkout is dirty (797
modified/untracked entries), which is itself a refusal input (§4.6).

Governing sources read: `knowledge/00-System/CAPABILITY_POLICY.md`,
`CAPABILITY_REGISTRY.md` (committed and working-tree states, compared),
`.claude/rules/infra/iac.md`, `.claude/rules/infra/secrets.md`,
`.claude/rules/infra/release.md`, `.claude/rules/global/owner-reserved-restrictions.md`,
`.claude/rules/global/knowledge-vault-durability.md`,
`M1-C-06-CAP-REAL-SCOPE-EXTENSION-DETERMINATION-2026-10-09.md` (§6, §7, §8, §10, §11, §12),
`M1-C-06-COMMITTED-CANDIDATE-LINUX-DIGEST-2026-10-09.md`,
`M1-C-06-LINUX-EXECUTABLE-PIN-2026-10-09.md`.

---

## 3. Decisive finding, stated first

**At commit `75a7513`, `knowledge/00-System/CAPABILITY_REGISTRY.md` contains no
CAP-009 row and no CAP-010 row at all.**

Observable evidence, re-derived against the committed blob rather than the working
tree: the committed registry holds 16 lines matching `^| CAP-0`, and the distinct ids
in them are exactly `CAP-001 … CAP-008`. The string `CAP-009` does not occur anywhere
in the committed file. The committed `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`
(245 lines) contains **no** `CAP-0NN` identifier at all, against 423 lines in the
working tree. `git diff --stat HEAD -- knowledge/00-System/CAPABILITY_REGISTRY.md`
reports 46 insertions / 18 deletions still uncommitted.

The `APPROVED (BOUNDED) 2026-10-09` CAP-009 / CAP-010 rows that
`knowledge/00-System/validate_capabilities.py` reports as present (run read-only this
session: 3 errors, all CAP-012) exist **only as uncommitted working-tree bytes**.

Consequences, each independently sufficient:

1. `CAPABILITY_POLICY.md` stage 7 requires a registry entry "**before** any module may
   depend on it", and its fail-closed rule makes any capability without an `APPROVED`
   row "**not usable** on this project". A row that is not committed is not in the
   authoritative record at all.
2. `knowledge-vault-durability.md`: the durable authority is the Git-tracked vault.
   Uncommitted bytes are not a record.
3. The prior determination §10.3 bound this explicitly and in advance: "Until that is
   done, **no** CAP-009/CAP-010 scope is operative, narrow or broad, and no subsequent
   extension round has a coherent row to extend." That dependency is still unmet at
   this commit. There is no committed row to extend, so a scope extension is not
   grantable in this round regardless of candidate quality.

Mechanical corroboration from the candidate's own predicate: in a clean checkout of
`75a7513` — which is precisely what the candidate workflow's fetch step constructs —
`_registry_row("CAP-009")` returns the empty string and the emitted blocker is
"CAP-009 has no row in CAPABILITY_REGISTRY.md". The candidate fail-closes correctly;
the prerequisite for any grant is absent.

---

## 4. Criterion-by-criterion evidence

### 4.1 Both named gitleaks hashes enforced before executable use — **SATISFIED**

The workflow downloads `gitleaks_8.30.1_linux_x64.tar.gz`, pipes
`551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` through
`sha256sum -c -`, and only then runs `tar -xzf … gitleaks` — verify-before-extract,
in that order, with `set -euo pipefail` so a mismatch aborts the job. The extracted
ELF is then checked against
`88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509` via a second
`sha256sum -c -`, and that check precedes `gitleaks version` and every other
invocation. Both literals match the charge values and both are corroborated by
`M1-C-06-COMMITTED-CANDIDATE-LINUX-DIGEST-2026-10-09.md` (archive member listing
`LICENSE`, `README.md`, `gitleaks`; extracted ELF 64-bit x86-64, statically linked).

### 4.2 Wrapper matches the workflow pins — **SATISFIED (gitleaks)**

`GITLEAKS_ELIGIBLE_ARCHIVE_SHA256` contains `551f6fc8…2470eb`;
`GITLEAKS_ELIGIBLE_BINARY_SHA256` contains `88f91962…c32e5509` alongside the darwin
arm64 `ba52fb1b…bbc0e84f`; the Homebrew digest `052d1882…c771422` is named
*ineligible* with a specific reason rather than falling through to the generic
unknown-digest branch. `verify_artifact_digest` re-hashes the executable on **every**
invocation (correct: the gitleaks release is `immutable: false`), refuses a symlink or
non-regular file, and `assert_pinned_version` requires stdout exactly `8.30.1` — the
same assertion the workflow makes. No `PATH` lookup exists anywhere; `--binary` is
mandatory and its absence is an explicit refusal.

### 4.3 Ruff artifact identity — **DEFECT (fail-closed, path non-functional)**

The workflow verifies the wheel digest `a21713e6…bc728` before extraction, which is
sound: the extracted member is deterministic from a digest-verified ZIP. But the
contained Linux executable is only **printed** (`sha256sum "$RUNNER_TEMP/bin/ruff"`),
never checked, and `RUFF_ELIGIBLE_BINARY_SHA256` contains the macOS arm64 digest
`8b799e53…509e57` *only*. Therefore the authorised CAP-010 branch, if it were ever
reachable, hands the Linux executable to `verify_artifact_digest`, which refuses it;
`invoke` returns `EXIT_REFUSED` (2); the workflow's `[[ "$rc" -eq 0 || "$rc" -eq 1 ]]`
guard then DENYs. Safe, but the CAP-010 CI path cannot complete, and the Linux Ruff
executable identity is still unrecorded anywhere. This is the exact asymmetry
`M1-C-06-COMMITTED-CANDIDATE-LINUX-DIGEST-2026-10-09.md` flagged as its "exact
remaining entry condition" — closed for gitleaks by the later pin commit, still open
for Ruff.

### 4.4 Scope: real-tree target, Git-free, no index or history — **SATISFIED (design)**

`gitleaks_argv` is the module's only gitleaks argv builder and hardcodes `dir`, so no
`gitleaks git`, `--staged` or `--baseline-path` invocation is constructible anywhere
in the module. `materialize_tracked_snapshot` copies exactly the enumerated committed
blobs into `<work>/committed-snapshot` — outside the repository by construction,
since `_resolve_work_dir` refuses any work directory inside it — re-deriving each
file's Git blob OID from the bytes actually copied and refusing on any mismatch, on
any `.git`/`.`/`..`/empty path component, on any symlink or non-regular source, on a
pre-existing destination, and on any post-copy set inequality or surviving
symlink/`.git` entry. `_discard_snapshot` removes the copy on every exit path
(`except BaseException`, plus a `finally` around the scan), independently re-checks
existence rather than trusting `rmtree(ignore_errors=True)`, and converts an
unremovable residue into a refusal — `retained_after_run` is only written after
cleanup was attempted and observed. `run_gitleaks_governed` additionally refuses any
target containing `.git` as a backstop for a caller who skips materialization.
`_VEYRO_DERIVED_TARGETS` is populated *before* the first byte is written and is
consulted append-only, so a partially-written snapshot outside the repository is
already governed as a Veyro target by `_require_scan_allowed`. Scope honesty here is
correct and unusually careful: a copy of reviewed Veyro bytes is treated as a Veyro
scan, not reclassified as approved synthetic scope.

### 4.5 Commit binding — **PARTIAL (two gaps, neither exploitable)**

`authorisation_blockers` requires `SELF_REL`, `MANIFEST_REL` and the manifest-named
`candidate_workflow` each to be git-tracked (`git ls-files --error-unmatch`) **and**
byte-identical to `HEAD` (`git diff --quiet HEAD`). Verified satisfied for all three
at this commit.

Gap (a): the two *grant-bearing* inputs — the CAP registry row and the manifest-named
authorising determination — are read from the working tree with **no** tracked-or-
identical-to-HEAD check of their own. In the `invoke` path this is transitively
covered, because `assert_clean_committed_checkout` refuses on any modified or
untracked entry. But `preflight` deliberately excludes the clean-checkout result from
`refusals`, so the published `authorised_for_real_tree_scan` field can read `true` on
a dirty tree whose grant token exists only in uncommitted bytes — and the candidate
workflow branches on exactly that field. The subsequent `scan` call still fail-closes
(exit 2 → DENY), so there is no execution path through the gap; what is defective is
the honesty of the published authorisation field. Smallest fix: fold the
clean-checkout result into the blocker set that `authorised_for_real_tree_scan` is
computed from, and add a `_git_blob_matches_head` check on `REGISTRY_PATH` and on the
named determination.

Gap (b): the manifest records `head_commit = 9f3a075671a50cf505b8b54bbb5332f6f9fa74d0`
— the parent, not the containing commit `75a7513`. Substantively harmless, and the
verifier deliberately binds the digests rather than that field; I independently
confirmed the tracked path set and both digests are identical across `9f3a075` and
`75a7513`, so the binding holds. The field nonetheless misstates the commit it
describes. (The prior digest record anticipated this reading and stated the same
rationale; I verified it rather than inheriting it.)

### 4.6 Target manifest, drift and non-vacuity — **SATISFIED**

Independently recomputed from the committed tree at `75a7513` with the wrapper's own
digest construction (`sha256("\n".join(sorted paths) + "\n")`), without invoking the
wrapper to produce the numbers: **465** tracked paths, `d4166f7f797ad8c339d755060bbb561d1f9424d8d82e4fd99364fc2c075b4632`;
**45** `.py` targets, `6061395c1e0d90e06815cfb30e494484dd96c0606adf4a1d72091d598e9710aa`
— exactly the four manifest values. `verify_against_manifest` refuses on drift in
either direction (missing *or* extra), on count mismatch, and on either digest
mismatch. A read-only `preflight` run for both scanners (which executes no scanner —
only `git ls-files`, `git rev-parse`, `git status`) produced **zero refusals**,
confirming no live drift.

gitleaks allowlist non-vacuity: 4 of 465 paths are declared out of coverage, all
`.docx`, enumerated in the manifest with the observed-vs-untested distinction stated
honestly in both the manifest note and the `ALLOWLIST_EXCLUDED_*` comment. 461 paths
remain examined, so `assert_scannable`'s allowlist-vacuity refusal correctly does not
fire and a "0 findings" result would not be produced by exclusion. This closes C09-X
item 3 via its second (declare-out-of-coverage) branch.

Ruff non-vacuity is count-based, not "≥1": `--show-files` must list exactly
`manifest["python_target_count"]` (45) files or the run refuses — which is what closes
the partial-gitignore residual the prior determination §5.3 left open for directory
targets. `assert_clean_committed_checkout` plus the deliberately gitignore-blind
`_on_disk_files` walk prevents a `dir` walk over any unenumerated byte; the local tree
currently fails that check with 797 entries, correctly.

### 4.7 Suppression — **SATISFIED**

gitleaks: `--ignore-gitleaks-allow` set, `-i` pointed at a freshly created directory
that is then asserted empty, `--redact=100`, `--exit-code 42` (so leak is never
conflated with error), and `--baseline-path` constructible nowhere in the module. A
target-root `.gitleaksignore` is refused outright rather than assumed defeatable by
flag; no `.gitleaksignore` and no `gitleaks.toml` is tracked anywhere in the tree
(verified against the committed name list). Ruff: `--ignore-noqa` in the governed
shape, `--no-fix`, `--no-cache`; `--fix`, `--unsafe-fixes` and `--add-noqa` appear
nowhere. Exit classification keeps `invalid-syntax` apart from `S` findings, so an
unanalysable target cannot read as `S`-clean.

### 4.8 Redaction — **SATISFIED in code, with one unresolved disclosure criterion**

`redact_gitleaks_findings` fail-closes unless every finding's `Secret` is exactly
`REDACTED`, and forwards only `RuleID`, `File`, `StartLine`, `Fingerprint` — dropping
`Match` and `Line`. `redact_ruff_findings` drops Ruff's `message`, which for
`S105`/`S106` quotes the credential-shaped value itself; this is the correct reading of
`secrets.md` control 1. `veyro_relative_findings` refuses any finding path it cannot
place inside the snapshot, so no finding can name a vanished temp path.

Unresolved: in the authorised branch, `invoke`'s full JSON report — rule ids plus
repository-relative paths plus line numbers across 461 paths — is printed to stdout,
i.e. into the Actions log. The fetch step is a tokenless anonymous HTTPS fetch of
`${{ github.server_url }}/${{ github.repository }}.git`, which succeeds only for an
anonymously-readable repository; in that case the log is public, and a public map of
candidate-secret locations in the Veyro tree is a disclosure this candidate does not
address. I did not query the remote to establish visibility, so this is recorded as an
open criterion for any CI grant, not as an established leak.

### 4.9 Trust boundaries and CI — **UNRESOLVED**

In the candidate's favour, and verified by reading the committed YAML: zero `uses:`
references (so `iac.md` control 5's action-capability bar is satisfied by having no
actions at all), zero `secrets.` references, `permissions: contents: read` only,
`timeout-minutes: 10`, `VEYRO_SCAN_MODE: advisory` with no gate path anywhere in the
file, a ref assertion plus a 40-hex SHA assertion plus a post-checkout
`rev-parse HEAD == $PUSH_SHA` assertion, and a trigger branch
(`ci/c06-real-tree-candidate-NOT-CREATED`) that does not exist, so the job cannot
execute even by accident. `python3 -I` is used for every inline interpreter call.

Open regardless: the hosted runner (`ubuntu-24.04`) and its supplied toolchain
(`curl`, `tar`, `sha256sum`, `git`, `python3`) are an **unregistered and unpinned**
execution environment — the committed registry's highest row is CAP-008, so no
`CAP-<NNN>` row exists for the CI runner surface, and the prior determination §12
recorded the same residual. Two network egresses (github.com, files.pythonhosted.org)
occur on every run. And `release.md` control 3 makes any CI capacity that carries a
cost — a paid Actions tier included — conditional on an `OWN-<NNN>` entry recorded in
`OWNER_APPROVALS.md` *before* activation; no such entry was established here, and
activation (pushing the branch into existence) is the step that would engage it.

### 4.10 Non-self-authorisation — **SATISFIED**

There is no `--force`, no `--allow-real-tree`, no environment override, no marker
file, and no `--repo-root`/`--registry` CLI flag. `_require_scan_allowed` is the single
choke point and calls `authorisation_blockers(scanner)` with module defaults only, so
the parameterised `repo_root`/`registry_path` are reachable only from in-process test
monkeypatching, never from the command line. `emit-targets` prints and can never write
the manifest, so the tool cannot re-bind its own target set. `_VEYRO_DERIVED_TARGETS`
is consulted in one direction only: it can add a refusal, never remove one. In
`invoke`, authorisation is evaluated before anything is computed about the binary or
the work directory, so a bad flag cannot convert a blocked run into a different
outcome. I found no path by which this candidate can authorise itself.

### 4.11 Live blocker state (read-only, no scanner executed)

`preflight --scanner gitleaks|ruff --mode advisory` against the working tree:
`authorised_for_real_tree_scan = false` for both; zero refusals; two blockers each —
the missing registry grant token and the null `authorising_determination`; gate mode
independently refused for both on the null `advisory_run_evidence`;
`clean_committed_checkout = false` (797 entries).

Correction to prior evidence, recorded because it changes what the blocker set means:
both `M1-C-06-LINUX-EXECUTABLE-PIN-2026-10-09.md` and
`M1-C-06-COMMITTED-CANDIDATE-LINUX-DIGEST-2026-10-09.md` describe the first blocker as
a *missing grant token in the row*. That is what the predicate reports **against the
dirty working tree**, where the rows exist uncommitted. Against the committed bytes —
the only authoritative state, and the state a CI checkout would materialize — the
blocker is stronger: there is no row (§3). Neither prior record is dishonest; both
read the working tree. The distinction is decisive for this decision.

### 4.12 Tests — read, not executed

53 test functions parametrize to the claimed 85 cases. I read them for synthetic
discipline and did **not** run them, both because the charge forbids executing either
scanner against real Veyro bytes and because no grant may be inferred from a passing
suite. Two shapes are worth recording: the test that points `run_gitleaks_governed` at
`REPO_ROOT / "tools"` monkeypatches both argv builders to raise, and asserts
`RealScanBlocked` — sound, because `_require_scan_allowed` is the first statement in
that function, before `verify_artifact_digest` and before any subprocess, so no
scanner can start; and the authorised-branch coverage is obtained by monkeypatching
`gsp.REPO_ROOT` / `MANIFEST_PATH` / `REGISTRY_PATH` onto a disposable synthetic
repository. That is the correct way to demonstrate the predicate's non-vacuity, and it
also means the authorised real-tree path has never executed against any real target —
consistent with the no-real-scan state this report records.

### 4.13 Minor, non-blocking

`RUFF_CONFIGS = ("ruff.toml", "backend/pyproject.toml")` (line 145) is dead: it is
referenced nowhere and reads like the governed config set while constraining nothing.
Given §4.14, its presence is actively misleading and it should be deleted or bound.

### 4.14 CAP-010's governed `--config` file is not committed — **MANDATORY DEFECT**

`_verify_governed_ruff_config` requires `ruff.toml` to be a regular file, to hash to
`RUFF_CONFIG_SHA256 = 81c6492e759cb6a3a622e29d7996de6fb8f590190110b36ad993bf2b534c9743`,
and to pass `_git_blob_matches_head("ruff.toml")`. Observable evidence:

- `git ls-files --error-unmatch -- ruff.toml` → rc 1, "did not match any file(s) known
  to git". `ruff.toml` is **not tracked** at `75a7513` (nor at `HEAD`); `git ls-tree -r`
  over the commit confirms its absence, and no `ruff*.toml` is tracked anywhere.
- The file exists on disk, untracked, 87 bytes, `sha256 = 81c6492e…c9743` — i.e. the
  pinned digest pins **uncommitted, unreviewable bytes**.

Failure scenario: in CI the checkout of `75a7513` contains no `ruff.toml` at all, so
`config.is_file()` is false and `invoke` refuses at exit 2; locally
`_git_blob_matches_head` fails and refuses identically. Either way the CAP-010
real-tree path cannot execute. Beyond the non-functionality, three governance
consequences: the scope-defining config was never committed, so `iac.md` control 1 is
unmet for it; CAP-010's already-in-force scope text (prior determination §8.3)
explicitly requires `--config <committed repo config>`, so this is a failure against a
standing condition rather than a new one; and because `ruff.toml` is untracked it is
itself one of the 797 entries that make `assert_clean_committed_checkout` refuse.

Smallest concrete mandatory fix: commit `ruff.toml` and re-emit the manifest (the
target set becomes 466 tracked / 45 Python with new digests, and both manifest digests
and `python_target_count` must be re-bound), **or** repoint the governed `S` shape at
an already-committed config (`backend/pyproject.toml` is tracked) and re-pin
`RUFF_CONFIG_REL` / `RUFF_CONFIG_SHA256` accordingly. Either way `RUFF_CONFIGS` (§4.13)
should be reconciled in the same change.

---

## 5. Verdicts

### 5.1 CAP-009 (gitleaks 8.30.1) — **BLOCKED**

No grant token is issued. This report deliberately never writes CAP-009's full grant
token (the `GRANT-REAL-TREE-DIR-SCAN` prefix joined by `: ` to the capability id), so
`authorisation_blockers` cannot clear even if a later manifest edit named this file as
its `authorising_determination`. CAP-009's scope is **unchanged**: the
synthetic-fixture `dir` scope recorded in the prior determination §7.3, which is
itself non-operative while §3 stands. Real-tree, Git index, Git history, CI and any
gate or required-status role remain NOT approved and permanently excluded as listed in
§7.3.

Exact unavoidable prerequisite: **commit the CAP-009 row into
`knowledge/00-System/CAPABILITY_REGISTRY.md`, together with the corresponding
`MOD-001/evidence/module-capabilities.yaml` entry, recording the already-granted
`APPROVED (BOUNDED)` synthetic-only scope with a named `approved_by` and a parseable
`next_review_due`** — the prior determination §10.3 dependency, still undone. Existing
owner: the dispatching MOD-001 orchestration session, sole runner operation
`c85552a2-eba8-4ace-89d4-0c0fb1a65b9f` (`REVIEW_IN_FLIGHT.md` `current_claim`). This is
a control-plane *recording* action, not a material scope change, so it is not
owner-reserved; no `OWN-<NNN>` entry is needed for the commit itself.

Assessed against C09-X's five properties, so a later round need not redo this: item 1
(committed reviewed wrapper carrying the fail-closed pre-checks as code) **satisfied**;
item 2 (explicit enumerated Veyro target set) **satisfied** and independently
re-derived (§4.6); item 3 (allowlist non-vacuity) **satisfied** via the
declare-out-of-coverage branch; item 4 (evidence for the mode the gate uses)
**satisfied in the negative** — `dir` is the only constructible mode and `git`/`--staged`
are excluded by construction, so no history/index drill is owed; item 5 (install-time
digest verification every run, failing closed, Homebrew excluded by hash)
**satisfied** (§4.1, §4.2). The candidate is, on the evidence, the strongest C09-X
submission to date. It is blocked on a prerequisite outside its own four files, plus
the §4.5(a) authorisation-field defect and the §4.8 / §4.9 open CI criteria, which must
be resolved before any CI path — not merely any gate — is grantable.

### 5.2 CAP-010 (Ruff 0.16.9 `S`) — **BLOCKED**

No grant token is issued, and CAP-010's full grant token is likewise never written
here, for the same reason as §5.1.
CAP-010's scope is **unchanged**: the synthetic bounded scope plus the local read-only
non-gate lint/format extension recorded in the prior determination §8.3, itself
non-operative while §3 stands. Real-tree `--select S` over any Veyro path, all CI
execution, `--fix`, `--unsafe-fixes`, in-place `ruff format`, `--add-noqa`, and any
gate or required-status role remain NOT approved and permanently excluded.

Three prerequisites, each independently blocking:

1. The §5.1 registry/manifest commit (same prerequisite, same owner).
2. **§4.14 — the governed `--config` file `ruff.toml` is not committed.** This is a
   mandatory defect *in the candidate itself*, with the smallest concrete fix stated in
   §4.14. Were prerequisite 1 satisfied, this alone would be a REQUIRED_CHANGE.
3. **§4.3 — the Linux Ruff contained-executable identity is neither recorded nor
   enforced.** `RUFF_ELIGIBLE_BINARY_SHA256` holds the macOS digest only, so the
   authorised CI branch refuses the executable the workflow builds. Fix: observe the
   digest of the `ruff-0.16.9.data/scripts/ruff` member extracted from the
   digest-verified wheel `a21713e6…bc728`, add it to the eligible set, and add a
   `sha256sum -c -` check in the workflow before the first `--version` call — mirroring
   what the gitleaks pin commit already did.

C10-X's five properties: item 1 (enumerated target set, explicit file list)
**satisfied** — 45 explicit `.py` paths, not a directory target; item 2 (count-based
non-vacuity, exact expected `.py` count) **satisfied**; item 3 (committed reviewed
wrapper **and** workflow) **satisfied for the wrapper and workflow, failed for the
governed config** per §4.14; item 4 (`S` capability limits carried in the registry row
— pattern-based not taint analysis, version-dependent rule set, `S`-clean ≠ absence of
injection defects) **cannot be satisfied: there is no committed row to carry them**;
item 5 (advisory-before-gate sequencing) **satisfied** — `gate_mode_refusals` refuses
`gate` independently of authorisation while `advisory_run_evidence` is null, and the
workflow pins `VEYRO_SCAN_MODE=advisory` with no gate path.

### 5.3 C06 foundation / capability — **BLOCKED**

The C06 scanner foundation is blocked on §3 for both capabilities. No advisory
real-tree scope and no governed CI path is granted to either; gate mode, Git history,
Git index, and unreviewed target bytes are not authorised by any part of this
determination and were never candidates for it.

---

## 6. No real scan, no scenario PASS, nothing else established

No scanner was executed against any Veyro file, the Git index, Git history, CI, or any
copy of those bytes, by this reviewer or by the candidate. No snapshot was
materialized. The candidate workflow has never run: its trigger branch does not exist
in any remote and no push occurred. `authorised_for_real_tree_scan` is `false` for both
scanners.

Accordingly: no advisory run exists, no `ADVISORY-RUN-RECORDED` evidence is created,
and gate mode stays refused on its own independent ground. SCN-MOD001-029, 094, 134,
135, 136 and all 13 M1-C-06 scenarios remain **NOT EXECUTED**. No GOV-01-R03 or
GOV-01-R04 acceptance criterion is closed; no CI gate, required status, branch
protection, or trust anchor is created or implied; `c06-synthetic-scanner-qualification.yml`
and `c06-real-tree-scanner-candidate.yml` are neither approved as gates nor usable as
trust anchors. CAP-011 and CAP-012 were not adjudicated and no verdict about them may
be inferred here — note only that the committed registry lacks their rows too, and that
the working-tree validator's 3 remaining errors are all CAP-012. C05 OSV/typecheck and
C17 privacy/load were out of charge and were not examined. MOD-001 exit is unchanged.
MOD-002 remains locked.

No owner-reserved restriction was engaged by this review: no spend, no real member
data, no Production action, no material product/pricing/business/architecture/scope
change. Two forward-looking owner-reserved exposures are recorded rather than engaged:
`release.md` control 3 (Actions capacity cost on activation, §4.9) and the §4.8
public-log disclosure question. The only credential-shaped value encountered anywhere
in this evidence set is the explicitly-labelled `EXAMPLE_NOT_A_REAL_KEY` placeholder
named in prior records; no credential was read, written, or copied.

This reviewer modified no file other than this report, did not touch the
`REVIEW_IN_FLIGHT.md` claim, and spawned no agent. One terminal decision, two separate
verdicts, as charged.

---

## 7. Residual risks (recorded, not accepted as cured)

Both tools' provenance chains terminate at GitHub/PyPI with no verified cryptographic
signature, so platform-level compromise is undetected by checksum agreement; the
gitleaks release is mutable, which is why per-run re-verification is load-bearing
rather than ceremonial. The CI runner image and toolchain are unpinned and
unregistered (§4.9). The declared gitleaks out-of-coverage set is a lower bound from a
non-exhaustive synthetic probe, honestly labelled as such in the source. The governed
`S` shape passes `--ignore-noqa`, so the tree's `S` state remains unknown and a first
authorised advisory run should be expected to produce a large previously-unseen
finding set — a sequencing fact, not a security objection. An advisory run over 461
paths would, if the Actions log is publicly readable, publish the locations of
candidate secrets even with values redacted (§4.8).

Not accepted, and therefore withheld rather than disclosed: everything in §5.

---

*Terminal decision: BLOCKED / BLOCKED. Recording of this result is the orchestrator's
action, not this reviewer's.*
