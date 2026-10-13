---
doc: M1-C-07 CAP-011 exact-runner synthetic drill
status: SYNTHETIC_ONLY_NOT_APPROVED
date: 2026-10-09
bounded-operation: M1-C-07
runner-operation: 3e9f0b56-47e5-4694-a3e8-a68b390c4a2c
---

# Scoped pytest runner: actual subprocess path on disposable fixtures

The unmodified `tools/run_scoped_pytest.py` candidate (SHA-256 `df0c857e208e8a74550d1a0331dd783c152970d85e749a5b970f5fc56713d85d`) was copied into a fresh temporary repository-shaped tree. That tree contained only synthetic `backend/pyproject.toml`, `backend/tests/unit/test_synthetic.py`, and `tools/tests/test_validate_idempotency_contract.py`; its `HOME` and `TMPDIR` were temporary. The interpreter was the locally installed backend venv with pytest 9.1.1 and iniconfig 2.3.0. The copied wrapper was invoked from the temporary tree, so no Veyro test, config, conftest or source was passed to pytest. The temporary tree was removed after the drill.

| Case | Expected | Observed |
|---|---|---|
| Exact idempotency file positive | One test passes | rc 0, `1 passed` |
| Exact idempotency file deliberate failure | Gate fails | rc 1, `1 failed` |
| Exact idempotency file symlink to outside temp tree | Refuse before pytest | rc 2, symlink denial |
| Backend unit synthetic positive | One test passes | rc 0, `1 passed` |

This exercises the wrapper's real version-probe and pytest subprocess path on synthetic content, beyond the prior pure argv/refusal tests. It is a qualification input, **not** CAP-011 approval, Veyro test evidence, CI evidence or scenario PASS. The exact idempotency target remains outside CAP-011's drafted `backend/tests` scope, and the Linux lock still pins iniconfig 2.3.1 rather than the 2.3.0 used here. Those scope/artifact differences require reconciliation and independent qualified determination before any real-tree or CI reliance.
