# M1-C-08 R06 failed-contract atomicity — local synthetic proof (2026-10-09)

Bounded runner: `365515ef-2560-4dd7-93d2-c1d489c3918f`. The previous Opus dispatch exited at provider model confirmation before worker action. A changed-strategy Sonnet implementation call made this narrow correction.

`contract_after_old_shape_retirement` now drops the N-1 compatibility trigger and contracts the legacy column inside a single psycopg transaction. A disposable PostgreSQL regression creates a dependent view, observes contract failure (`2BP01`), confirms the trigger and legacy column survive, confirms an N-version write/read still succeeds, then removes the view and successfully contracts. Temporarily removing the transaction wrapper made the new test fail at the missing trigger; the wrapper was restored.

Independent replay: `backend/.venv/bin/python -m pytest backend/tests/integration/test_migration_safety_harness.py -q` — **43 passed**. `backend/.venv/bin/ruff check` and `backend/.venv/bin/mypy` on the two files — **PASS**. `ruff format --check` flags pre-existing formatting in the untracked harness files; no broad formatting was undertaken.

File SHA-256:
- `backend/tests/harness/migration_safety.py`: `3976d89703c04518e607dd0bbeb29187ac0c77424c129b570b0319e107d2546a`
- `backend/tests/integration/test_migration_safety_harness.py`: `ba65229b143fb21d123bb224b7d6e60169f5f30c38c854a18e1254174361b18e`

Boundary: source-independent synthetic R06 local proof only. C08 remains PARTIAL/HELD on C05 release/CI input and real prior deployed-version evidence. No real CI, deployment/canary, independent review, or scenario PASS is inferred. C06 may resume its separate terminal prerequisite under WIP=1.
