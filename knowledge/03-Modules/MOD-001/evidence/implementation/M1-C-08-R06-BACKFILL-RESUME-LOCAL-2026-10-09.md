# M1-C-08 R06 synthetic backfill resume — local evidence

Scope: TSD §24.2 / GOV-01-R06 source-independent, disposable PostgreSQL proof. This is a partial C08 increment, not R06 certification or scenario promotion.

`test_migrate_backfill_resumes_after_interruption_and_reaches_throttle_hook` interrupts the synthetic 12-row backfill at the configured throttle hook after the first four-row transaction. It observes exactly that first batch committed, resumes the same migration, observes eight remaining rows processed, and checks all 12 final IDs and mapped values without loss or duplication. The hook receives `0.25` seconds; elapsed-rate limiting, concurrent writers, and N-1 rolling-deploy compatibility are not proven.

Independent orchestrator replay on 2026-10-09: `backend/.venv/bin/python -m pytest backend/tests/integration/test_migration_safety_harness.py -q` → **37 passed**; `backend/.venv/bin/python -m ruff check backend/tests/integration/test_migration_safety_harness.py` → **all checks passed**. The worker changed only the existing integration-test file; the orchestrator corrected two now-stale disclosure paragraphs in the existing harness module. No CI run, independent assurance, R05 release proof, or R06 scenario PASS is claimed.
