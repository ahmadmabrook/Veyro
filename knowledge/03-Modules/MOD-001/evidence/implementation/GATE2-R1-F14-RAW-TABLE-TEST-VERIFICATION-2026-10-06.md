# R1-F14 SCN007 raw-table test-only verification

- UTC: 2026-10-05T21:58:55.246562+00:00
- Runner operation: `e84eaf2f-4473-4707-9d8a-cbab88b93177`; guarded status `COMPLETED`, exit 0.
- Scope: one dedicated synthetic raw-table negative and same-shape own-table positive test in `tools/tests/test_validate_architecture_gates.py`. No scanner source, review, scenario status, or CTE state-3 wiring change.
- Negative: `membership/repo.sql` contains `SELECT id FROM bil_invoices`; observed FAIL/exit 1 with exactly `CROSS_DOMAIN_SQL_IMPORT`, subject `membership -> billing`, detail naming `bil_invoices` and billing ownership.
- Positive: same fixture uses `SELECT id FROM mem_roster`; observed PASS/exit 0 and no violations.
- Worker dedicated test: 1 passed, 449 deselected. Worker focused file: 450 passed; Ruff and compile passed. An initial system-Python invocation lacked pytest and an overly strict line-number assertion failed; the worker corrected the assertion and reran successfully under `backend/.venv/bin/python`.
- Independent local verification on final bytes: `backend/.venv/bin/python -m pytest tools/tests -q -p no:cacheprovider` **523 passed**; Ruff checked source and test **PASS**; `py_compile` source and test **PASS**.
- Source SHA-256: `fc6404c613fb5f475fe7e7dd05f1efc5654833503f9294ef692694461cbed08d` (unchanged from F13). Final test SHA-256: `6f2c304e45594ab5e194aedf399a1aefc36649b78234e3f7c723f5608784184d`. The final assertion correction followed the first material checkpoint; this hash is the independently verified final file, not the checkpoint hash.
- Finding remains formally OPEN. Exact next dependency: capture actual CLI text and JSON raw-table denial and own-table positive evidence, including the specified evasion corpus, then independent assurance. This test-only increment is not a scenario verdict.
