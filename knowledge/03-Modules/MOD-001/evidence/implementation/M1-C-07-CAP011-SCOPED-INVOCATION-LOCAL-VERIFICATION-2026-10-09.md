---
doc: M1-C-07 CAP-011 scoped invocation local verification
status: CANDIDATE_ONLY_CAPABILITY_NOT_APPROVED
date: 2026-10-09
bounded-operation: M1-C-07
runner-operation: e44c73c5-1603-4fb5-aea0-960324bdf822
---

# GOV-01-R01/R02: scoped pytest invocation candidate

A guarded `ARCHITECTURE_CRITICAL` Opus implementation call completed exit 0. It added `tools/run_scoped_pytest.py`, its synthetic stdlib `unittest` checks, and routed the two direct pytest steps in `.github/workflows/test-pyramid.yml` through the fixed-suite runner. The wrapper names four backend test layers and one exact idempotency test file, validates canonical paths and symlink/ambient-override refusals, fixes config/root/confcutdir arguments, and maps pytest rc 4/5 to denial. The workflow's hash-enforced install, skip/empty-result denials, tokenless fetch, CAP-008 Linux integration HOLD and regression failure are unchanged. No registry approval, CI push/run or scenario status change occurred.

Independent local checks used Python stdlib only: **21/21** synthetic wrapper tests passed; both new Python files compiled; Ruby parsed six workflow jobs; `bash -n` passed all **16** run blocks; exactly two CI steps call the wrapper and zero directly invoke `-m pytest`. No pytest process was started against Veyro tests, config, imports or source. The wrapper's real `run()` subprocess path remains unexecuted and unapproved.

**Exact dependencies before CAP-011 or C07 proof:** CAP-011 is still `QUALIFIED`, not `APPROVED`; its drafted scope names `backend/tests`, while the candidate's idempotency target is `tools/tests/test_validate_idempotency_contract.py`, requiring an independently justified exact-scope extension. The registry describes iniconfig **2.3.0** but the Linux hash lock installs **2.3.1**; reconcile the selected artifact and its qualification before a grant. The wrapper/workflow are uncommitted. A fresh independent qualified capability decision is required before any Veyro pytest or live CI reliance. CAP-008 Linux Postgres remains unqualified, and CAP-012/typecheck-CI belongs to C05. SCN-016/036/061/071 remain unpromoted; prior SCN-009/132/133 PASS is reused unchanged.
