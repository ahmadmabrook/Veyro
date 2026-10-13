# M1-C-05 OSV CI candidate — trust-boundary correction (2026-10-09)

Closes the blocking defect recorded in
`M1-C-05-OSV-CI-CANDIDATE-TRUST-BOUNDARY-2026-10-09.md` §"Blocking defect".
Operation `ffb8b376-4f8a-4777-ac14-078e16bbfeb1`, ARCHITECTURE_CRITICAL /
`claude-opus-5`. Material checkpoint recorded (kind `code`, subgoal
`M1-C-05-OSV-TRUSTED-CODE-CORRECTION`).

## 1. What was wrong

The superseded candidate ran on `pull_request` and executed
`$head/tools/scan_dependency_advisories.py` — the pull request's own copy of
the gate's executable. A candidate could replace that file with one returning
zero and suppress its own vulnerability check. `permissions: {}` and a
tokenless fetch constrain what the job can *reach*; they do not constrain the
provenance of the bytes that decide the check *result*. The prior static test
asserted that exact unsafe command, so its green result could not establish
trusted enforcement.

## 2. Correction (changed paths)

| Path | State | sha256 |
|---|---|---|
| `.github/workflows/dependency-vulnerability-gate.yml` | rewritten, untracked | `4e10b219e5dcabf9b5c93ac3a29e3ad3f8374ace4b0ad70cd9f4d8c212ebbef7` |
| `tools/tests/test_dependency_vulnerability_gate_workflow.py` | rewritten, untracked | `5e92c18addf4494c3953d7ff0457f742a2c1ef0e3d254725667162cfc2e023b3` |

Unmodified, verified by hash: `tools/scan_dependency_advisories.py`
(`2a75b00985adee5fe03555045d53cb72dba39a22621af1f78af4e8a30d42bbe4`, still
**untracked**) and `backend/requirements-dev.lock.txt`
(`5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698`, tracked
and clean). No other file was touched; all unrelated uncommitted work is
preserved.

## 3. Trust model now enforced

The event mechanism chosen is `pull_request_target` restricted to
`branches: [main]` — the smallest GitHub Actions mechanism that satisfies the
requirement, because GitHub takes a `pull_request_target` workflow's
definition and `GITHUB_SHA` from the repository's default branch, never from
the pull request's branch. `pull_request` cannot provide this: under that
event the definition itself comes from the PR head. This reuses, rather than
invents, the pattern already reviewed in `scn020-trusted-event-contract.yml`
and `workflow-trust.yml`, so one review covers all three.

1. **Workflow definition** — default branch, GitHub-enforced for this event.
2. **Executable scanner** — `tools/scan_dependency_advisories.py` fetched by
   immutable SHA (`github.sha`) from the same trusted default-branch snapshot
   that supplied the definition, and executed as
   `python3 -I "$trusted/$scanner_rel"`. Isolated mode blocks `PYTHONPATH`,
   user site-packages, and script-directory import injection.
3. **PR contribution is inert data only** — the bytes of
   `backend/requirements-dev.lock.txt` at the PR head, screened as a regular
   blob (modes `100644`/`100755` only; symlink/gitlink/absent all DENY) and
   materialized under a scratch path never on `sys.path`. The candidate tree
   is never checked out.
4. **Candidate tamper check** — the PR head's copies of the workflow *and* the
   scanner must be byte-identical to the trusted default-branch bytes
   (`cmp` over inert blobs). A candidate that edits or deletes either fails the
   required check instead of silently landing a weakened gate; changing them
   intentionally therefore requires a separate reviewed default-branch commit,
   which is `.claude/rules/infra/iac.md` control 1 exactly.
5. **No PR-supplied executable code, workflow, action, test, shell fragment or
   secret can influence the result.** No `uses:` line (iac.md control 5: no
   action holds an APPROVED `CAP-<NNN>` row), no `secrets.` reference of any
   kind — not even `GITHUB_TOKEN` — and `permissions: {}`, which is tighter
   than the `contents: read` the two precedent workflows use and sufficient
   because every fetch is anonymous against the public repository. Untrusted
   values reach the shell only through `env:`, and only SHAs plus
   GitHub-supplied repository identity are consumed.
6. **Fail-closed nonzero preserved** — the scanner invocation is the final
   command of the final step under `set -euo pipefail`. Exit 1 (validated
   advisory) and exit 2 (clean not established) both fail the job with nothing
   between them that could reinterpret either as green. No
   `continue-on-error`, `if: always()`, `set +e`, or `|| true`.
7. **Stable status** — `name: dependency-vulnerability-gate` at both workflow
   and job level; no `paths`/`paths-ignore` filter (which would let a PR avoid
   triggering the required context) and no `workflow_dispatch`.

## 4. Deterministic verification (offline, no network, no real-tree scan)

`tools/tests/test_dependency_vulnerability_gate_workflow.py` is now three
layers. Layer 2 is the new one and is what proves the negative: it extracts
the step's own bash script from the workflow YAML (indentation parser — no
YAML dependency exists in this environment) and **executes it** against a
synthetic local `file://` git remote carrying a trusted default-branch commit
and a candidate head commit, with a deterministic stub standing in for the
scanner so no network is touched.

Focused result, replayed: **88 passed, 31 subtests passed** across
`test_scan_dependency_advisories.py`,
`test_dependency_vulnerability_gate_workflow.py` and
`test_validate_workflow_trust.py` (21 of them in the gate module itself).
Ruff clean on the test module; `py_compile` clean. The standing
`workflow-trust-lint` validator ALLOWs all 11 workflow files, exit 0.

Positive: a clean candidate lock goes green *and* captured stdout proves the
trusted snapshot's scanner was the code that ran. Negative, each nonzero with
the candidate's own code proven never to have executed: candidate scanner
edited to always-return-zero; candidate scanner deleted; candidate workflow
edited; candidate workflow deleted; advisory exit 1; unestablished-clean exit
2; candidate lock absent; candidate lock a symlink; non-hex `HEAD_SHA`.

Four disposable mutants were injected and all four were killed, then the
workflow was restored byte-identically:

| Mutant | Killed by |
|---|---|
| tamper-check block deleted | 5 tests (4 behavioral) |
| execute `$cand/` scanner (the original defect) | 4 tests (3 behavioral) |
| subtle `\|\| exit 0` mask, not in the string blocklist | 4 tests (2 behavioral) |
| trigger reverted to `pull_request` | 1 static test |

## 5. Not claimed — and the remaining exact dependency

No live CI run, no required status, no known-published-CVE denial run, no
patched clean companion run, no SCN-MOD001-094 PASS, no independent assurance,
no C06 CAP-009/010 review consumption. Nothing was pushed.

**Live activation is BLOCKED on exactly one dependency: a reviewed commit on
the trusted default branch `main` carrying both
`.github/workflows/dependency-vulnerability-gate.yml` and
`tools/scan_dependency_advisories.py`.** Both are still untracked in the
working tree, so the scanner is *not* on the trusted base today and the
workflow's step 1 assertion ("trusted snapshot has no regular
tools/scan_dependency_advisories.py") would DENY if run now. That is the
correct fail-closed behavior, not a defect. Installed anywhere other than the
default branch the file is inert and the required context would never report.

Two residuals carried forward unchanged, neither introduced here:

- **Same-name check-run spoofing is not solved.** Identical to
  `scn020-trusted-event-contract.yml`'s open C2 / probe N5: nothing in this
  YAML proves a candidate head cannot publish its own check run named
  `dependency-vulnerability-gate` and satisfy the required context. Live
  negative proof after installation is required; do not record this gate as
  trusted until it is run.
- **The scanner has no independent security review.** It is project source
  riding the planned shared material-code review, which has not happened.

Making the check blocking additionally needs a separate owner action on
github.com adding `dependency-vulnerability-gate` to `main`'s required status
checks.

## 6. Remediation of the 2026-10-10 independent review (BLOCKED) — local, unreviewed

Corrects statements above that the review found false: §3 "reuses ... the
pattern already reviewed in `scn020-trusted-event-contract.yml` and
`workflow-trust.yml`" and §4's reference to the standing `workflow-trust-lint`
and `test_validate_workflow_trust.py` — none of those is committed with the
gate, so no precedent review or standing lint is inherited. The 88-test figure
is superseded by the clean-export result below.

Changed paths (uncommitted edits on top of `2931933`): the workflow,
`tools/scan_dependency_advisories.py`, the focused gate test, `SCENARIOS.md`
(SCN-094 status paragraph), this record.

| Review item | Disposition |
|---|---|
| P0-1 | Deleted the uncommitted `validate_workflow_trust` import and its test. Clean `git archive 2931933` + these three files: 26 tests pass, offline. |
| P1-1 | Precedent/standing-lint claims rewritten as self-contained. |
| P1-2 | Public-repo and fork-PR-fetch dependencies disclosed as UNVERIFIED; green fork dry-run named a precondition of making the check required. |
| P1-3 | Owner-executed update procedure and rebase consequence documented; byte comparison unchanged. |
| P2-1 | Scanner sends PEP 503-normalized name to OSV (reports keep the lock spelling); focused test. OSV was observed to also accept `Jinja2`, but the fix does not rely on that. `generate_requirements_lock.py:60` `.lower()` NOT changed (out of scope). |
| P2-2 | Step 3a denies any other dependency manifest in the candidate tree; allowlist is only the scanned lock plus `backend/requirements-dev.txt` and `backend/pyproject.toml`. No other governed gate was found covering it. Residual: lock/intent consistency is not verified by this gate. Mutant (block removed) killed by 7 tests. |
| P2-3 | Tests assert the CVE ID is emitted and add a Jinja2 2.10 / CVE-2019-10906 fixture (ids observed via OSV 2026-10-10) plus the 2.10.1 clean companion. |
| P2-4 | Interpretation recorded as pending qualified adjudication; trigger unchanged. |
| P3 | Untouched. |

Not claimed: no review PASS, no CI run, no SCN-MOD001-094 PASS. Lint: Ruff on
the two Python files reports the same 4 findings as on `2931933` (EXE001,
2x RUF100, ISC004), none introduced here.

