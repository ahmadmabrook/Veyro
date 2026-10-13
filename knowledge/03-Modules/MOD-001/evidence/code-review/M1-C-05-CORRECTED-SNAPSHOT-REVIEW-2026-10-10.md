# M1-C-05 — Independent re-review of the corrected trusted dependency-vulnerability CI prerequisite

**Verdict: BLOCKED** (not `APPROVED_FOR_TRUSTED_BASE_ACTIVATION`).
Open at this snapshot: **P0 = 0, P1 = 1, P2 = 2, P3 = 1.**

Prior review `M1-C-05-TRUSTED-DEPENDENCY-CI-REVIEW-2026-10-10.md` (BLOCKED,
commit `2931933`) raised P0-1, P1-1/2/3 and P2-1/2/3/4. **All eight are closed
or correctly dispositioned at this snapshot** — each verified independently
below, not accepted on the commit's own claim. The single remaining P1 is a new
defect introduced by the P2-2 correction itself, and it is cheap to fix.

## 1. Exact snapshot

Committed objects only. The worktree is dirty; it was read solely to establish
what does and does not exist in git, and (for finding **N1**) what MOD-001 has
in flight. No uncommitted file was treated as part of the reviewed artifact.

| Item | Value |
| --- | --- |
| Reviewed commit | `706be091cccfd5cc5f18cc3ec5e3c1f1a80103b4` — "Correct C05 trusted dependency gate candidate", Ahmad Mabrouk, Sat Oct 10 01:32:39 2026 +0300 |
| Parent | `dc5bdb8` ("Record C05 trusted CI review blocker"); the reviewed predecessor was `2931933` |
| Files changed | exactly 4, all `M` (`git diff-tree -r`): the three artifacts + `SCENARIOS.md` |
| `.github/workflows/dependency-vulnerability-gate.yml` | blob `1188016`, sha256 `90431d97c5a4f57c9cff698f35685c38c81a06918dcb4b2fd60a881a5768e547`, 17 094 B, 292 lines |
| `tools/scan_dependency_advisories.py` | blob `47eda54`, sha256 `55d002fa9ed21a0e2666af53ec1eed9b727bfb4b3423227111a168b8358c26cc`, 42 956 B, 1 029 lines |
| `tools/tests/test_dependency_vulnerability_gate_workflow.py` | blob `cce1552`, sha256 `0104a476e065ebcde69efa5f9104dd144dbd3aeea5089d46b992b155ad9f4287`, 37 666 B, 787 lines |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` | blob `3395177`, sha256 `69062c2ed94440909a7c5f7575b1a64c819d11eb345b094bf1e9e37ff8971655` |
| Governing | GOV-01-R04 (`REQUIREMENTS.md` §GOV-01-R04), SCN-MOD001-094 (`SCENARIOS.md` line 1743 ff.), `.claude/rules/infra/iac.md` control 1 |

Clean export under review: `git archive 706be09` → `/tmp/c05rev/export`
(verified byte-identical by the per-file sha256 above). Out of scope by
instruction and not examined: R04 gate-2, C06 capabilities, gate-3,
`c06-real-tree-scanner-candidate.yml`.

## 2. Runtime model proof

Not a self-report. `knowledge/05-QA/tools/mr_verify.py` run against this
session's own harness-written transcript
(`~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/9d279848-5b3e-43d8-abb4-b90b3caceba4.jsonl`):

```
{"verdict": "PASS",
 "reason": "96 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
 "models_observed": ["claude-opus-5"], "expected_tier": "opus"}   RC=0
```

Fresh independent reviewer; no participation in authoring any reviewed commit
and no participation in the prior review. Host: Darwin 27.0.0 (arm64), zsh,
`git 2.54.0 (Apple Git-157)`, `python3 3.14.5`, `bash 3.2.57(1)`.

**Caveat on every behavioral result below:** produced on this host, not on
`ubuntu-24.04`. The runner's `bash` is 5.x and its `python3` is not 3.14.5. The
script uses only constructs valid in both bash versions and the scanner is
stdlib-only, so results are expected to carry over, but they are **not
runner-identical and are not a CI result.**

**Live-network disclosure.** Unlike the prior review, this one did reach the
network. Probe P-I (a no-mutation baseline) ran past step 5 and issued real
`https://api.osv.dev/v1/query` requests; I then deliberately repeated live
queries to test the known-CVE blocking path (§4.3). These are read-only GET/POST
lookups against a free public advisory API: no authentication, no repository or
remote state touched, no push, no CI activation, no branch-protection change, no
scenario promotion. **No CI result and no SCN-MOD001-094 PASS is claimed.**

## 3. Checks actually run

Static, against commit bytes: read all 292 + 1 029 + 787 lines in full; read
GOV-01-R04's acceptance criteria including bypass classes (f)–(i), SCN-MOD001-094
in full, and `iac.md` controls 1–5; enumerated the snapshot trees.

Committed suite, from the clean export, isolated interpreter:
`python3 -I -m unittest discover -s tools/tests -p 'test_dependency_vulnerability_gate_workflow.py'`
→ **`Ran 45 tests … OK`, 16.1 s.** The 45/45 claim is credited and independently
reproduced. `tools/validate_workflow_trust.py` is still in **no** commit on any
branch, but the test module no longer imports it — the prior P0-1 import failure
is gone.

Independent behavioral probes (my own harness — extracted the single `run: |`
block to `/tmp/c05rev/probe/step.sh` and executed it against synthetic
throwaway `file://` git remotes under `/tmp/c05rev/work`; the real committed
scanner, not the committed fixture's stub):

| Probe | Mutation at the candidate head | Result |
| --- | --- | --- |
| P-A | scanner replaced with an always-green stub | DENY exit 1 — "candidate changed `tools/scan_dependency_advisories.py`" |
| P-B | one line appended to the gate definition | DENY exit 1 — "candidate changed …`.yml`" |
| P-C | gate definition deleted | DENY exit 1 — "head … has no …`.yml`" |
| P-D | clean lock + `backend/requirements.txt` (`Jinja2==2.10.0`) + `mobile/package.json` | **DENY exit 1** — step 3a |
| P-D2 | `mobile/androidApp/build.gradle.kts` only | **DENY exit 1** — step 3a |
| P-D3 | `backend/requirements-typecheck-…lock.txt` only | **DENY exit 1** — step 3a |
| P-E | `requests==2.31.0` added to `requirements-dev.txt`, absent from lock | DENY exit 2 — `UNLOCKED_DECLARATION` |
| P-E2 | `pytest` declared at a version the lock does not pin | DENY exit 2 — `DECLARATION_VERSION_MISMATCH` |
| P-F | gitlink (mode 160000) at the lock path | DENY exit 1 — "refused head tree entry mode 160000" |
| P-G | `backend/pyproject.toml` → symlink to `/etc/passwd` | DENY exit 1 — "refused … mode 120000" |
| P-I | no mutation, both intent files removed | reached step 5; live OSV: 14/14 CLEAN, ALLOW exit 0 |

**P-D is the prior review's own probe Q4, which previously went green. It now
denies.** P-F additionally required correcting my first attempt, whose `git add
-A` dropped the gitlink from the index; the mis-set probe still failed closed,
and the re-run exercised the intended branch.

Scanner-level probes, offline, against the real committed scanner: `tool.poetry.dependencies`
→ `UNSUPPORTED_DECLARATION_SITE` DENY; `tool.setuptools.dynamic.dependencies` →
DENY; `project.dynamic = ["dependencies"]` → `DYNAMIC_DEPENDENCIES` DENY;
environment marker, direct URL (`name @ https://…`) and range (`>=`) → each
`UNSUPPORTED_DECLARATION` DENY. Every documented fail-closed path behaved as
documented.

Self-consistency of the committed trio:
`python3 -I tools/scan_dependency_advisories.py --check-declarations
backend/requirements-dev.lock.txt --declares backend/requirements-dev.txt
--declares backend/pyproject.toml` → **ALLOW**, 14 pinned, 8 declarations, every
one matched. Step 3a's own loop replayed over the snapshot's 466 tree entries →
**0 would-deny** (1.5 s, so no `timeout-minutes: 10` concern).

Fetch-capability probe: a `file://` fetch of a bare 40-hex SHA succeeds with
`uploadpack.allowAnySHA1InWant=false` *and*
`uploadpack.allowReachableSHA1InWant=false`, and for a commit unreachable from
any ref. **Confirmed: the local fixture carries zero evidence about GitHub.com
fork-PR fetch** — git's local transport bypasses upload-pack want validation.
The workflow now says exactly this.

## 4. Disposition of the prior findings

Each verified independently, not accepted on assertion.

**P0-1 — CLOSED.** The `validate_workflow_trust` import and the single test
depending on it are gone; 45/45 collect and pass from a clean `git archive`
export. The second half of P0-1 — that no CI stage runs `tools/tests/` at all —
is still true and is re-raised below as **N3**, at P2 rather than P0, because the
suite now runs and passes and the tamper check bounds drift to the reviewed path.

**P1-1 — CLOSED.** The "already-reviewed pattern" / "one review covers all
three" / `workflow-trust-lint` claims are all deleted; lines 14–16 now state the
trust model as self-contained and explicitly disclaim inheriting any prior review
or standing lint, and `test_comments_claim_no_uncommitted_precedent` enforces
their absence against the committed text. One dangling comparative reference
survives — see **N4** (P3).

**P1-2 — CLOSED as a disclosure finding.** Both dependencies are now named in
the NOT-claimed block as `UNVERIFIED DEPENDENCY, anonymous fetch` (repository
must be public) and `UNVERIFIED DEPENDENCY, fork-PR fetch`, the latter stating
that the `file://` fixture cannot establish it — which my own probe confirms —
and making one observed green fork-PR dry-run a **precondition** of adding the
required check. The underlying viability remains an open live residual, correctly
gated rather than assumed.

**P1-3 — CLOSED.** The owner-executed update procedure (remove the required
check → land by reviewed PR → re-add) is recorded in the workflow (lines
124–131) and in SCN-MOD001-094, together with the "every open PR must rebase
after a gate update" consequence. The byte comparison is explicitly marked
not-to-be-weakened and is unchanged. This is the correct fix: the procedure is
an owner-controlled toggle of branch protection, not the direct/force-push path
criterion (h) forbids.

**P2-1 — CLOSED.** `normalize_name()` (PEP 503) is added and is used both in the
OSV query payload and as the lock-lookup key; `test_query_name_is_pep503_normalized`
asserts the emitted payload name for `Zope.Interface`, `Typing_Extensions` and
`ZOPE--interface`. `check_declarations` additionally denies when two lock pins
normalize to the same name, which also resolves prior P3-5. The upstream
suggestion to `.lower()` in `generate_requirements_lock.py:60` is not taken; that
is harmless now that the scanner normalizes, so it is not re-raised.

**P2-2 — CLOSED, and verified by the exact prior probe.** Step 3a denies any
other recognised dependency-manifest basename anywhere in the candidate tree;
step 4a runs the trusted scanner's `--check-declarations` over the candidate's
two allowlisted intent files. Probes P-D/P-D2/P-D3/P-E/P-E2 all deny. The
residuals of the new check (exact-string version comparison, four TOML sites
only, extras checked against the base pin, one-directional by design, and
"a dependency in a file that is neither allowlisted nor a recognised manifest
basename remains outside this gate") are disclosed in the workflow and enforced
by `test_coverage_disclosure_matches_the_implemented_consistency_check`. The fix
is sound — but it is what introduces **N1**.

**P2-3 — CLOSED in form; a new defect in its fixture is raised as N2.**
`ExitContractTests` now asserts the CVE ID reaches the output and adds a
real-historical-CVE case. The scanner genuinely cites correctly.

**P2-4 — ADJUDICATED. Criterion (i) is SATISFIED.** SCN-MOD001-094 and the
workflow both record this as "pending qualified adjudication"; I am asked to
decide it, so it is decided here and no longer pending.

R04's text is conjunctive and names a specific documented hazard: *"(i)
`pull_request_target` running base-branch workflow code **with secrets**."* This
gate does not instantiate it. `permissions: {}` grants the job no `GITHUB_TOKEN`
scope; there is no `secrets.` reference of any kind, not even `GITHUB_TOKEN`;
there is no `uses:`, so no `actions/checkout` credential persistence; and no
candidate byte is ever executed, imported or installed — probes P-A/P-B/P-C
confirm the executed bytes come from `github.sha` and that a candidate edit
fails the check rather than weakening it.

The stronger point is that the event is the **mechanism of compliance, not a
violation of it**. R04's governing criterion is that "no gate is bypassable at
the CI-workflow-configuration layer." Under `pull_request`, a workflow's
definition comes from the PR head, so a candidate could rewrite the gate it is
subject to — precisely the defect the superseded revision had.
`pull_request_target` is the smallest mechanism that puts the definition and the
executed scanner on the trusted default branch. Reading (i) as a ban on the
event would therefore force the gate back into a configuration R04's own primary
criterion forbids. "Resists (i) outright" is satisfied by holding no secrets and
executing no candidate code, not by avoiding the event name.

Two premises are GitHub-documented behaviours I cannot prove offline and which
this adjudication depends on: that a `pull_request_target` workflow's definition
and `github.sha` are taken from the base branch, and that `permissions: {}`
yields a zero-scope token. Both are correctly stated in the file; the fork-PR
dry-run (§6.3) is their live proof.

**Required-check / status spoofing — NOT closed, correctly disclosed, and an
activation precondition.** Branch protection matches a required check by name
string. A fork PR cannot write a check run to the base repository (its token is
scoped to the fork), but a *same-repository* PR branch from someone with push
access can add a `pull_request` workflow declaring `permissions: {checks: write}`
and publish a check run named `dependency-vulnerability-gate`, if the
repository's default workflow permissions are read-and-write. Pinning the
required check to a source app does not help, because a spoof via Actions shares
the "GitHub Actions" app identity. Nothing in this YAML can prevent that, and
the file says so (lines 87–90). Mitigations are owner-side: set default workflow
permissions to read-only, and/or require the workflow via a ruleset rather than
a named status check. This blocks *making the check required*; it does not block
the commit landing on the trusted base.

## 5. Findings open at this snapshot

### N1 — P1 · Step 3a denies on MOD-001's own in-flight tree, so activation as a required check deadlocks the module's next PR
`.github/workflows/dependency-vulnerability-gate.yml:229-245` (step 3a),
disclosure block lines 104-120.

Step 3a is the correct fix for P2-2, but it denies the mere *existence* of any
recognised dependency-manifest basename outside the three allowlisted paths —
not merely an unscanned Python lock. The snapshot tree is clean (0 would-deny
across 466 entries), so this is invisible at HEAD. MOD-001's **current
uncommitted work already contains three such files**:

- `mobile/androidApp/build.gradle.kts`
- `mobile/shared/build.gradle.kts`
- `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt`

Probes P-D2 and P-D3 confirm each denies on its own. The moment
`dependency-vulnerability-gate` becomes a required check on `main`, the next PR
carrying MOD-001's in-flight mobile surface or its C06 typecheck lock fails the
required check permanently, with no path to green except the P1-3 procedure —
i.e. temporarily removing the gate to land work the gate was never meant to
reject. This is the same permanent-merge-deadlock class the prior review rated
P1 for the private-repository case, so it takes the same severity. It fails
**closed** (red), so it is an availability/operability defect, not a security
hole.

It is also undisclosed. Lines 104-120 disclose that only one lock is *scanned*,
that coverage is PyPI-only, and that "other ecosystems need their own later
gate" — a reader reasonably concludes an unscanned npm/Gradle manifest is
out-of-scope-but-tolerated. Nothing states that its presence is a hard DENY,
and nothing warns that the repository must bring every other manifest under a
gate before this one can be made required.

**Exact minimum fix** (either, not both): (a) add to the NOT-claimed block a
named residual stating that step 3a denies the *existence* of any recognised
manifest basename outside the allowlist, that the repository must therefore
carry no other manifest while this check is required, and that MOD-001's
mobile/typecheck manifests are known pending cases — then make "no unallowlisted
manifest exists in `main`" an explicit precondition alongside the fork dry-run;
or (b) extend step 3a's allowlist to the manifests MOD-001 will legitimately
carry and record, per path, which later gate covers each. Do not relax step 3a
into a warning.

### N2 — P2 · A committed test records a false OSV observation, and its patched companion is not actually clean
`tools/tests/test_dependency_vulnerability_gate_workflow.py:519-528`.

`test_known_published_cve_fixture_denies_and_patched_companion_allows` comments
that the ids were *"observed via OSV 2026-10-10 (jinja2 2.10 lists them; 2.10.1
does not)"*, and asserts `Jinja2==2.10.1` → exit 0. The test passes only because
it injects a `{}` payload. Live OSV on 2026-10-10 contradicts the comment:

- `Jinja2==2.10` → exit 1, 12 advisories, cites `CVE-2019-10906` (correct).
- `Jinja2==2.10.1` → **exit 1, 10 advisories** (`CVE-2025-27516`,
  `CVE-2024-22195`, `CVE-2024-34064`, `CVE-2024-56326`, `CVE-2020-28493`).
- `Jinja2==2.11.3` → exit 1 (8); `3.1.4` → exit 1 (6); **`3.1.6` → exit 0, ALLOW.**

Two consequences. The committed bytes carry a factual claim about observed
external data that is wrong, in a project whose entire review chain turns on not
asserting unverified observations. And SCN-MOD001-094's required companion half —
"the same lockfile with the dependency pinned to a patched version passes
cleanly" — will **fail** if the live run uses the version this test pre-selects.
The scanner itself is correct throughout; this is a fixture-selection and
attestation defect.

**Exact minimum fix:** change the companion pin to `Jinja2==3.1.6` (verified
ALLOW live on 2026-10-10), and either delete the "observed via OSV" parenthetical
or restate it as what it is — ids used in an injected payload, with the live
observation recorded separately and dated. Keep the injected-payload form; the
test must stay offline.

### N3 — P2 · The gate's 45-test verification artifact is never executed by CI
No committed workflow runs `tools/tests/` (`grep` over
`.github/workflows/` at the snapshot: no `tools/tests`, `unittest` or `pytest`
reference; the only other committed workflow is
`c06-real-tree-scanner-candidate.yml`, on `push`).

The suite passes today — I reproduced 45/45 from a clean export — so this is no
longer the prior P0-1. But landing this on the trusted default branch plants a
verification artifact that no CI stage would surface if it broke. The tamper
check bounds the blast radius (neither the workflow nor the scanner can change
without a reviewed default-branch commit), which is why this is P2 and not
higher. It is a MOD-001-wide gap (GOV-01-R04's "test" stage / GOV-01-R01), not
specific to C-05.

**Exact minimum fix:** record it as a named residual in the workflow's
NOT-claimed block and in SCN-MOD001-094, pointing at the test-stage work item
that will run `tools/tests/`. No change to this gate is required.

### N4 — P3 · Dangling reference to two workflows that are in no commit
`.github/workflows/dependency-vulnerability-gate.yml:44-45` — "`permissions: {}`
— tighter than the `contents: read` the two precedent workflows use".

`.github/workflows/` at the snapshot holds only this file and
`c06-real-tree-scanner-candidate.yml`; `workflow-trust.yml` and
`scn020-trusted-event-contract.yml` exist in no commit on any branch. P1-1's
substance is fixed — no review is inherited and no lint is claimed — so what
remains is a comparative aside pointing at files a reader of the trusted branch
cannot find. **Fix:** delete "the two precedent workflows use" and state the
property directly, or name the files as not-yet-committed.

### P3 — carried forward, unchanged and non-blocking
No `concurrency:` group, so rapid `synchronize` events queue redundant runs. No
`MAX_LOCK_ENTRIES` bound (a very large lock exceeds `timeout-minutes: 10` and
red-lights the gate — fail-closed, but a cheap always-red DoS of the gate). No
retry on transient OSV failure, so as a required check an OSV outage blocks all
merges (deliberate; the operational consequence deserves a residual line).
`github.sha` is the base tip at trigger time, so without "require branches to be
up to date before merging" a green can have been computed by an older trusted
scanner. `run_scan` still accepts `bool` as a timeout
(`isinstance(timeout, float | int)`), unreachable from the workflow.

## 6. Activation checklist — residual evidence that does not yet exist

1. Fix **N1** (and ideally N2–N4) in a new reviewed default-branch commit.
2. Any CI run of this workflow whatsoever — it has never executed.
3. A live known-published-CVE denial run with the CVE ID in the job log, **and**
   its patched-companion clean run. §4.3's live scanner results are evidence the
   blocking path works end-to-end against the real OSV API; they are **not** a CI
   run and **not** an SCN-MOD001-094 PASS. Use a companion pin that is actually
   clean (N2).
4. A fork-PR dry-run proving both anonymous `git fetch <40-hex>` calls succeed on
   GitHub.com, plus confirmation that the repository is public.
5. Negative proof that a candidate head cannot publish its own check run named
   `dependency-vulnerability-gate` (§4, spoofing), with the owner-side mitigation
   recorded — default workflow permissions read-only and/or a workflow-requiring
   ruleset.
6. Confirmation that `main` carries no unallowlisted dependency manifest at the
   moment the check is made required (N1).
7. The owner action adding `dependency-vulnerability-gate` to `main`'s required
   status checks, plus the disclosed-residual record for bypass class (f) —
   admin override / "include administrators" — which R04 requires to be recorded
   as a deliberate residual and which appears in neither the workflow nor
   SCN-MOD001-094.
8. An independent security review of `tools/scan_dependency_advisories.py` as
   project source. The file states it has none. This review covers its
   fail-closed contract and its use by this workflow; it is **not** the shared
   material-code review the scanner's docstring defers to.

## 7. Verdict

**BLOCKED.** The correction is substantial and honest work: every one of the
prior review's eight findings is genuinely closed or correctly dispositioned,
and I confirmed each independently rather than on assertion — including
re-running the prior review's own fail-open probe Q4, which now denies. The
trust boundary itself is sound and behaved as documented under all eleven of my
workflow probes and all six scanner probes. Criterion (i) is adjudicated
**SATISFIED** and is no longer pending: `pull_request_target` here is the
mechanism that makes the gate unbypassable, holds no secrets, and executes no
candidate byte.

What blocks activation is **N1**, a new P1 introduced by the P2-2 fix: step 3a
denies the existence of any unallowlisted dependency manifest, MOD-001's own
in-flight tree already contains three, and that consequence is disclosed
nowhere. Making this check required today would deadlock the module's next PR
and force the very remove-the-gate manoeuvre P1-3 reserves for reviewed gate
updates. N2 additionally embeds a demonstrably false "observed via OSV" claim in
committed bytes and pre-selects a patched companion that will fail SCN-094's
companion half live.

All four open findings are documentation, disclosure or fixture changes; none
requires weakening the byte comparison or the fail-closed contract. The correct
next step is one more reviewed default-branch commit, then re-review — not
activation of this snapshot.

No integrated C13 claim, no scenario PASS, and no CI or remote activation was
performed by this review.
