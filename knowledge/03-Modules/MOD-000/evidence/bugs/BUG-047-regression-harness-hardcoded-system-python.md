---
doc: BUG-047
status: CLOSED — 2026-10-01 independent Opus recovery assurance
---

# BUG-047 — regression harness ignored its invoking Python interpreter

**Module:** MOD-000. **Severity:** P2, false-FAIL of a permanent gate.
**Found:** 2026-10-01. **Status:** CLOSED — independent Opus recovery assurance 2026-10-01.

`backend/.venv/bin/python knowledge/05-QA/tools/run_regression.py` loaded the
harness with the project's Python environment, but each `CHECKS` command
hardcoded `python3`. On this host that resolves to `/usr/bin/python3` 3.9.6,
which cannot execute the existing `str | None` annotation in
`verify_baselines.py`. Real output was `AGGREGATE RESULT: FAIL (3/4 checks
passed, 1 N/A excluded)`; the other three checks passed. This was a harness
interpreter mismatch, not a governing-baseline failure.

All five child commands now use `sys.executable`, preserving the interpreter
that successfully started the harness. Added a test asserting every built-in
check has that interpreter. `backend/.venv/bin/python -m pytest -q
knowledge/05-QA/tools/test_run_regression.py` passed 10/10. Re-running the
real aggregate returned exit 0 and `PASS (4/4 checks passed, 1 N/A excluded)`;
record: `knowledge/05-QA/tools/regression-runs/RUN_20261001T071935Z.txt`.
The retired CAP-007 suite remains correctly N/A, not silently passed.

This local fix is included in the pending independent recovery-review scope.
It does not approve CAP-008, close BUG-038, or unlock R04.

## Final independent closure — 2026-10-01

Fresh independent `claude-opus-5-5` review session `veyro-recovery-opus-gate-20261001` returned **APPROVED**, P0=0/P1=0, after its initial BLOCKED verdict and the records-only remediation. Runtime model attested by `mr_verify.py`; 38/38 focused tests and validators passed in the review copy. This closes this recovery defect, not CAP-008 or BUG-038. Earlier pending/blocked statements above are historical and superseded by this final verdict.
