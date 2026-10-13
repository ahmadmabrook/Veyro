---
doc: M1-C-07 R01/R02 CI candidate local verification
status: CANDIDATE_PARTIAL_CI_NOT_RUN
date: 2026-10-09
runner_operation: b4c71294-ecfe-4b70-b277-120e576b7a54
bounded_operation: M1-C-07
---

# Mandatory shared test-harness CI increment

One guarded Sonnet implementation call completed exit 0. It added only `.github/workflows/test-pyramid.yml` and `contracts/idempotency/synthetic-widget-create.json`. The workflow has current unit/component/contract/integration matrix jobs, an idempotency lint/test job, a blocking regression job, and E2E/Android/iOS applicability jobs. Exploratory testing remains manual. The synthetic declaration has no credential, provider call, or customer/member data. This is a candidate `pull_request` workflow, not trusted required-status enforcement.

Runner-local independent checks: Ruby YAML parse found **6 jobs**; `bash -n` accepted all **16** embedded run blocks. The committed-form synthetic declaration passed `tools/validate_idempotency_contract.py`, and its focused test suite passed **33/33**. Backend unit/component/contract suites passed **60/60**; the integration suite passed **144/144** on the approved local Colima route. These are local executions, not GitHub CI results.

The recorded SCN-061 regression command (`knowledge/05-QA/tools/run_regression.py`) ran once and **failed 4/6** scored checks: `validate_capabilities.py` denies CAP-011/012 because both remain QUALIFIED, not APPROVED; `evidence_integrity_check.py` reports three broken abbreviated references and two stale committed-state checks. Its timestamped output is `knowledge/05-QA/tools/regression-runs/RUN_20261009T170418Z.txt`. The retired CAP-007 Bash-guard suite was N/A, not counted as PASS. This does not satisfy SCN-061's full MOD-001 accumulated-suite criterion.

The candidate cannot currently produce full green R01/R02 CI proof: the integration fixture is bound to local Homebrew/Colima and denies GitHub Ubuntu Docker; the Linux lock lacks Ruff for the static/lint layer; and the blocking regression job is already red locally. Do not disable those denials or infer a CI result. No remote run, trusted default-branch activation, independent assurance, or new scenario PASS occurred. SCN-016/036/061/071 remain unpromoted; earlier SCN-009/132/133 PASS is reused unchanged.
