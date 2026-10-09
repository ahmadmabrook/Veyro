# M1-C-05 — Independent review: trusted dependency-vulnerability CI prerequisite

**Verdict: BLOCKED** (not `APPROVED_FOR_TRUSTED_BASE_ACTIVATION`).

## 1. Scope and snapshot

Exact-snapshot review of committed objects only. The dirty worktree was read
solely to establish what does and does not exist in git; no uncommitted file
was treated as part of the reviewed artifact.

| Item | Value |
| --- | --- |
| Reviewed commit | `2931933814018697c01b2965ffc79cd4fddf8dac` ("Add trusted dependency vulnerability gate candidate", Ahmad Mabrouk, Fri Oct 9 23:07:53 2026 +0300) |
| Files added by the commit | exactly the three under review (`git diff-tree -r`: 3 × `A`) |
| `.github/workflows/dependency-vulnerability-gate.yml` | blob `d812ded02030325b4c39d57fbd3690c52cb0ea86`, sha256 `4e10b219e5dcabf9b5c93ac3a29e3ad3f8374ace4b0ad70cd9f4d8c212ebbef7`, 188 lines |
| `tools/scan_dependency_advisories.py` | blob `05efe4c4b9183b86f45971657a490fcb80e70a9d`, sha256 `2a75b00985adee5fe03555045d53cb72dba39a22621af1f78af4e8a30d42bbe4`, 555 lines |
| `tools/tests/test_dependency_vulnerability_gate_workflow.py` | blob `534c2e2ff33897425a7244f36f74fa6ea209fa5f`, sha256 `5e92c18addf4494c3953d7ff0457f742a2c1ef0e3d254725667162cfc2e023b3`, 368 lines |
| Governing | GOV-01-R04 (`REQUIREMENTS.md` §GOV-01-R04, lines 234-320), SCN-MOD001-094 (`SCENARIOS.md` line 1946 ff.), `.claude/rules/infra/iac.md` control 1 |

Out of scope by instruction and not examined: R04 gate-2 F01-F14, C06 capabilities,
gate-3.

## 2. Attestation

- Reviewer: fresh independent reviewer session, no participation in authoring
  the reviewed commit; model **Opus 5** (`claude-opus-5`), Claude Code,
  non-interactive session, 2026-10-10.
- Host: darwin 27.0.0 (arm64), zsh; `git 2.54.0 (Apple Git-157)`;
  `python3 3.14.5` (Homebrew); `bash 3.2.57(1)` (macOS).
- **Caveat on every behavioral result below:** they were produced on this host,
  not on `ubuntu-24.04`. The runner's `bash` is 5.x and its `python3` is not
  3.14.5. The reviewed script uses only constructs valid in both bash versions
  (`[[ =~ ]]`, `${!var}`, `mktemp -d`), and the scanner is stdlib-only, so the
  results are expected to carry over — but they are **not runner-identical** and
  are not a CI result.
- No real Veyro scanner run, no network request to OSV, no mutation of the
  repository (probe artifacts live under `/tmp/veyro-rev-*`), no push, no CI
  activation, no branch-protection change, no scenario promotion. **No live
  proof of anything is claimed.**

## 3. Checks actually run

Static, against commit bytes (`git cat-file -p <sha>:<path>`):

- Read all 188 + 555 + 368 lines of the three files in full.
- Enumerated the snapshot trees: `.github/workflows/` at the snapshot contains
  **only** `dependency-vulnerability-gate.yml`; `tools/` contains no
  `validate_workflow_trust.py`; `tools/tests/` contains no
  `test_scan_dependency_advisories.py`.
- `git log --all -- tools/validate_workflow_trust.py` → **no commit on any
  branch has ever contained that file**; it exists only as an untracked
  worktree file.
- Read `backend/requirements-dev.lock.txt` at the snapshot (14 pins) and
  confirmed its shape matches `parse_lock`'s contract.
- Read `tools/generate_requirements_lock.py` at the snapshot: name handling is
  `name.replace("_", "-")` (line 60) — no case folding, no PEP 503 normalization.
- Read `.claude/rules/infra/iac.md` controls 1-5 and GOV-01-R04's acceptance
  criteria including bypass classes (f)-(i).

Deterministic offline execution:

- **Check A** — exported the snapshot with `git archive` and ran the committed
  test module from a clean tree: `ModuleNotFoundError: No module named
  'validate_workflow_trust'` at line 40, before any test runs.
- **Check B** — on an instrumented *copy* of the snapshot with only the missing
  import and the single test that uses it removed: 20 tests, all pass in 5.8 s,
  offline. The trust-boundary behavior the file claims does hold on these bytes.
- **Scanner probes** (own harness, injected fetcher, no network): verbatim query
  payload; unknown/non-normalized name + `{}` → exit 0; `"vulns": null` → 2;
  advisory-over-error precedence → 1 with the CVE cited; comment-only lock → 2;
  unpinned pin → 2; non-JSON body → 2; oversized body → 2; advisory without a
  CVE alias → 1. Every documented fail-closed path behaved as documented.
- **Workflow probes** (own harness, synthetic `file://` remote): gitlink
  (mode 160000) at the lock path → DENY; non-hex `TRUSTED_SHA` → DENY; trusted
  snapshot missing the scanner → DENY; clean candidate → green; **candidate
  adding a second, unscanned dependency source → green**.
- **Fetch-capability probe** — reran the script against a synthetic remote with
  `uploadpack.allowAnySHA1InWant=false` *and*
  `uploadpack.allowReachableSHA1InWant=false`, and again with the head commit
  unreachable from any ref: **green in every combination**.

## 4. What the artifact gets right

Recorded so the blockers below are not read as a rejection of the design. The
trust model is sound in its core: the definition and the executed bytes both
come from `github.sha` under `pull_request_target`; candidate code is never
executed, imported or installed; `python3 -I` genuinely removes the script
directory and user site from `sys.path`; the candidate contribution is screened
as a regular blob and materialized outside any import path; `permissions: {}`
with no `secrets.` reference and no `uses:` line is correct least privilege and
satisfies `iac.md` control 5 by having nothing to pin; the scanner's
`decide()` expresses ALLOW as a positive equality and every transport, status,
size, encoding, JSON and shape failure is a named non-clean outcome; the
scanner invocation is the final command of the final step under
`set -euo pipefail` with no masking construct anywhere. Check B and the
workflow probes confirm all of this behaviorally. The file's own "NOT claimed"
block is honest about having never run and about same-name check-run spoofing.

## 5. Blockers

### P0-1 — The commit's only verification artifact cannot run at all
`tools/tests/test_dependency_vulnerability_gate_workflow.py:40`
(`import validate_workflow_trust as trust`), used at line 165.

`tools/validate_workflow_trust.py` exists in **no commit on any branch** — only
as an untracked worktree file. From a clean checkout of
`2931933814018697c01b2965ffc79cd4fddf8dac` the module raises
`ModuleNotFoundError` at import, so **all 20 tests fail to collect** (Check A).
Nothing in this snapshot is verified by committed code. Compounding it, the
snapshot contains no workflow that runs `tools/tests/` at all, so landing this
on the trusted default branch plants a permanently-broken test that no CI stage
would surface. It also inverts `iac.md` control 1: the artifact asserting the
gate's reviewability depends on bytes that were never committed or reviewed.

**Exact minimum fix:** either commit `tools/validate_workflow_trust.py` (and its
own test) in the same reviewed default-branch commit as this gate, or delete
line 40 and lines 164-165 (`test_workflow_passes_standing_workflow_trust_lint`)
and the line 47-49 comment that depends on them. Re-run the suite from a clean
`git archive` export and confirm 19-20 tests collect and pass before activation.

### P1-1 — The documented trust argument rests on artifacts that are not in the repository
`.github/workflows/dependency-vulnerability-gate.yml:14-16, 47-49`.

Lines 14-16 claim the shape is "identical to the already-reviewed pattern in
`scn020-trusted-event-contract.yml` and `workflow-trust.yml` — deliberately the
same shape, so one review covers all three", and lines 47-49 claim the absence
of `secrets.` makes the file "ALLOW under the standing `workflow-trust-lint`
hazard predicate". At the snapshot, `.github/workflows/` contains this file and
nothing else, and no `workflow-trust-lint` exists in any commit. There is no
precedent review to inherit and no standing lint to be ALLOW under; a reader of
the trusted branch is told a control exists that does not.

**Exact minimum fix:** in the same reviewed commit, either land
`workflow-trust.yml`, `scn020-trusted-event-contract.yml` and the lint they
refer to, or rewrite lines 14-16 and 47-49 to state the properties as
self-contained and unreviewed-elsewhere, deleting every reference to a
precedent review and to a standing lint.

### P1-2 — Undisclosed hard dependency on anonymous fetch; fork-PR fetch viability is unproven and unprovable by the committed fixture
`.github/workflows/dependency-vulnerability-gate.yml:106, 138, 150`.

With `permissions: {}` the job holds no `GITHUB_TOKEN` scope, so both fetches
against `${{ github.server_url }}/${{ github.repository }}.git` are anonymous.
That requires the repository (`origin` =
`https://github.com/ahmadmabrook/Veyro.git`) to be **public**. If it is private,
every run denies at line 138 and the required check can never go green — a
permanent merge deadlock on `main`. Separately, both fetches request a bare
40-hex SHA; for a fork PR the head commit lives in the fork and is reachable in
the base repository only via `refs/pull/N/head`, and whether GitHub's
upload-pack honours that want is not established here. The committed fixture
cannot establish it: my probe shows the script goes **green against the
synthetic `file://` remote even with `allowAnySHA1InWant=false` and
`allowReachableSHA1InWant=false`, and even when the head commit is unreachable
from any ref**. The fixture's `uploadpack.allow*` settings
(`test_...workflow.py:202-203`) are therefore decorative — the local green is
no evidence about GitHub.com. Neither dependency appears in the file's
"NOT claimed" block (lines 68-82).

**Exact minimum fix:** add both to lines 68-82 as named undisclosed
dependencies — tokenless fetch requires a public repository, and fetch-by-SHA
of a fork PR head is unverified — and make a single observed green dry-run on a
throwaway fork PR a precondition of adding `dependency-vulnerability-gate` to
`main`'s required checks. Do not add the check first.

### P1-3 — The gate is self-blocking: once required, neither the workflow nor the scanner can be updated through the protected PR path
`.github/workflows/dependency-vulnerability-gate.yml:171-175`; proven by
`test_candidate_workflow_edit_cannot_produce_green` and
`test_candidate_scanner_edit_cannot_produce_green`.

The tamper check compares the candidate's copies of both files against the base
tip at trigger time. A legitimate PR that improves the scanner or the gate
therefore fails its own required check. Lines 37-39 resolve this with "a
separate reviewed default-branch commit" — but under branch protection that is
the direct/force-push path, which GOV-01-R04's acceptance criterion (h)
(`REQUIREMENTS.md:304-305`) requires the gate to resist, so the stated update
procedure routes through a bypass class R04 forbids. Second-order: because the
comparison is against the base tip, any future gate update red-lights every
open un-rebased PR until each rebases.

**Exact minimum fix:** record the update procedure explicitly in lines 68-82 and
in SCN-MOD001-094's detail block as an owner-executed sequence — temporarily
remove `dependency-vulnerability-gate` from `main`'s required checks, land the
reviewed change by PR, re-add the check — and name the "all open PRs must
rebase after a gate update" consequence. This is a documentation + procedure
fix; do not weaken the byte comparison.

### P2-1 — False clean: no PEP 503 normalization, and "OSV knows nothing about this name" is recorded as CLEAN
`tools/scan_dependency_advisories.py:368-370` (query payload), `285-286`
(absent `vulns` → CLEAN), `92` (`NAME_RE` permits uppercase); upstream cause
`tools/generate_requirements_lock.py:60` (`replace("_", "-")`, no `.lower()`).

The lock name is sent to OSV verbatim. Probe: a lock containing
`Jinja2==2.10.0` produces the payload
`{"package": {"name": "Jinja2", "ecosystem": "PyPI"}, "version": "2.10.0"}` and,
on a 200 with body `{}`, **exit 0 — ALLOW**. OSV's PyPI corpus is keyed on
normalized names, and the API returns the same empty body for "no advisories"
and "no such package", so the scanner cannot distinguish them. Whether OSV
itself normalizes the query name is upstream behavior I did not test (no
network by instruction), so I state this as a dependency rather than a
confirmed miss — but relying on an unverified upstream normalization is exactly
what §"Fail-closed contract" (lines 38-44) says must not happen: "Silence, an
empty response body... is never a pass." The fix is unconditionally correct
either way.

**Exact minimum fix:** normalize before querying — at
`scan_dependency_advisories.py:368`, send
`re.sub(r"[-_.]+", "-", entry.name).lower()` as `package.name` (keeping
`entry.name` for reporting), and add a test asserting the payload name for a
`Zope.Interface`-style pin. Separately, `generate_requirements_lock.py:60`
should `.lower()` as well so the lock itself is normalized.

### P2-2 — Coverage: exactly one lock path is scanned and nothing forbids a second dependency source
`.github/workflows/dependency-vulnerability-gate.yml:117, 178-180`.

`lock_rel` is the single constant `backend/requirements-dev.lock.txt`. Probe Q4:
a candidate that leaves that lock clean and adds `backend/requirements.txt`
pinning `Jinja2==2.10.0` plus a `backend/package.json` pinning
`lodash 4.17.4` **passes the gate green**. GOV-01-R04 names the
dependency-vulnerability stage without restricting it to one ecosystem, and
`REQUIREMENTS.md:606` asks for "a real dependency-vulnerability scanner proven
to block on a known-CVE fixture" — a gate that scans one of several possible
manifests does not block the obvious route around it. The PyPI-only limit is
disclosed in the scanner docstring (lines 60-65); the *single-manifest* limit is
disclosed nowhere.

**Exact minimum fix:** add it to lines 68-82 as a named residual, and add a deny
in the run block before step 5 for any other dependency-manifest path appearing
in the candidate tree (`git ls-tree -r --name-only "$HEAD_SHA"` matched against
`requirements*.txt`, `pyproject.toml`, `package.json`, `*.lock` outside
`$lock_rel`) — or record an owner-accepted decision that mobile/npm ecosystems
are a separate, later gate.

### P2-3 — No committed test exercises SCN-MOD001-094's stated acceptance
`tools/tests/test_dependency_vulnerability_gate_workflow.py:356-364`.

SCN-MOD001-094 (`SCENARIOS.md` line 1946 ff.) requires "a synthetic dependency
pin with a known-published CVE... Expected: the scanner flags it and the CI
stage fails, **citing the CVE ID**", plus a patched companion. The committed
test uses a fabricated advisory (`GHSA-aaaa-bbbb-cccc` / `CVE-1900-0001`) and
asserts only `== 1`; nothing asserts the CVE ID reaches the output, and no
known-published CVE appears anywhere. The scanner does cite correctly (my probe
confirms `CVE-2019-1234` is emitted), so this is a test-adequacy gap, not a
defect — and the file is right not to claim SCN-094 PASS.

**Exact minimum fix:** in `ExitContractTests`, assert the emitted text contains
the CVE ID (capture the redirected stdout at line 353 and `assertIn` it), and
add one offline case whose injected payload carries a real historical CVE for a
real pinned old version, so the committed suite matches the scenario's wording.
The live known-published-CVE run remains §7 residual evidence.

### P2-4 — The gate adopts `pull_request_target`, which R04 criterion (i) says it must resist "outright"
`.github/workflows/dependency-vulnerability-gate.yml:87`;
`REQUIREMENTS.md:304-306`.

R04's corrected acceptance criterion requires the gate to resist
"(i) `pull_request_target` running base-branch workflow code with secrets"
outright. This gate neutralizes the hazard rather than avoiding the event —
no secrets exist and candidate bytes are never executed, which I consider
substantively correct and which lines 14-22 argue well. But a literal reading
of (i) is in tension with the gate's own trigger, and nothing in `knowledge/`
records the reconciliation.

**Exact minimum fix:** one recorded sentence — in SCN-MOD001-094's detail block
or an ADR — stating that criterion (i) targets secret exposure to untrusted
code, that this gate satisfies it by `permissions: {}` + no `secrets.` + never
executing candidate bytes, and that the event itself is therefore permitted for
this gate.

## 6. P3 — non-blocking

1. Three deny branches I verified by probe are untested in the committed suite:
   gitlink (mode 160000) at the lock path, non-hex `TRUSTED_SHA` (only
   `HEAD_SHA` is covered, line 337), and trusted-snapshot-missing-scanner
   (workflow lines 142-145). Each is one fixture call.
2. No `concurrency:` group — rapid `synchronize` events queue redundant runs.
3. No bound on the candidate lock's size or entry count. A 10 000-pin lock
   exceeds `timeout-minutes: 10` at 14 sequential queries × up to 10 s; the
   result is a red (fail-closed) check, but it is a cheap always-red DoS of the
   gate. A `MAX_LOCK_ENTRIES` guard returning exit 2 would make it explicit.
4. No retry on transient OSV failure (deliberate, lines 60-65). As a *required*
   check this means any OSV blip hard-blocks all merges. Fail-closed is the
   right default; the operational consequence deserves a line in the residuals.
5. Duplicate detection (`scan_dependency_advisories.py:231`) is case-sensitive,
   so `Foo==1.0` and `foo==2.0` coexist as two pins. Both are queried, so it is
   not a miss — it resolves with the P2-1 normalization fix.
6. `github.sha` under `pull_request_target` is the base tip *at trigger time*,
   so without "require branches to be up to date before merging" a green result
   can have been computed by an older trusted scanner than `main`'s current one.
7. `scan_dependency_advisories.py:474` accepts `bool` as a timeout
   (`isinstance(timeout, float | int)`); unreachable from the workflow, which
   passes no `--timeout`.

## 7. Residual evidence that must still be produced live (none of it exists)

Correctly disclaimed by the file itself at lines 68-82, restated here as the
activation checklist:

1. Any CI run of this workflow whatsoever — the file has never executed.
2. A known-published-CVE denial run, with the CVE ID visible in the job log,
   and its patched-companion clean run (SCN-MOD001-094's own two halves).
3. A fork-PR dry-run proving the two anonymous `git fetch <40-hex>` calls
   succeed on GitHub.com, and confirmation that the repository is public
   (P1-2).
4. Negative proof that a candidate head cannot publish its own check run named
   `dependency-vulnerability-gate` — the same-name spoofing residual shared
   with `scn020-trusted-event-contract.yml` probe N5 (file lines 77-81).
5. The owner action adding `dependency-vulnerability-gate` to `main`'s required
   status checks, plus the disclosed-residual record for bypass class (f)
   (admin override / "include administrators"), per
   `REQUIREMENTS.md:300-310`.
6. An independent security review of `tools/scan_dependency_advisories.py` as
   project source — the file states it has none (lines 82, and the scanner's own
   lines 16-19). This review covers its fail-closed contract and its use by this
   workflow; it is not the shared material-code review the scanner's docstring
   defers to.

## 8. Verdict

**BLOCKED.** The trust boundary itself is well built and behaves as documented
under every probe I ran — P0-1 is not a design defect but it is disqualifying
for a trusted-base activation decision, because the snapshot's sole verification
artifact cannot be imported from a clean checkout of the snapshot, so no
committed evidence of the gate's properties exists. P1-1 through P1-3 each have
to be resolved before the file lands on the trusted default branch: the file
documents controls that are not in the repository, depends undisclosed on an
anonymous fetch and an unproven fork-PR fetch, and cannot be updated through
the protected path it is meant to guard. P2-1 through P2-4 are small, concrete
and cheap. Re-review after the fixes above; the correct next step is a new
reviewed default-branch commit, not activation of this one.
