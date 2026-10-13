# R1-F01 / R2-N01 — bounded N4 DELETE USING verification

Runner operation `e84f0e22-5c1b-4bc9-8e5f-3c6c301a52e7`: one guarded Sonnet implementation dispatch, `ACTIVE_OPERATION.json` COMPLETED exit 0, code/test material checkpoints recorded, no live child at collection. Prior N3 operation was already reconciled and was not replayed. This is local code/test evidence only, not independent assurance, F01 closure, or scenario PASS.

## What changed

`tools/validate_architecture_gates.py` adds `USING` to ADR-011 D6.7.4's vocabulary floor and a context-sensitive `_using_table_position_matches` signal that excludes a `USING` immediately followed by `(`. It refactors the earlier REFERENCES signal and this USING signal into one `_SINGLE_IDENTIFIER_SIGNAL_SOURCES` tuple used by both `_extract_table_identifiers` and `_dangling_keywords`. `tools/tests/test_validate_architecture_gates.py` adds N4 `.py`/`.sql` negatives, a direct P4 helper control and a dropped-USING-signal mutant pin. The guarded child demonstrated in-process that dropping the USING source restores the old `['mem_t']` extraction and `dangling=False`; the test pins against that mutation. No CTE state-3 wiring or resolution-order change.

**Scope limit:** this shared tuple prevents the two consumers from drifting for its two registered signal classes, but `_scan_sql_statement` still has the statement-level `if not idents:` guard; the full ADR-011 D6.7.2 per-position signal-to-attribution comparison is **not implemented**. Do not describe this bounded N4 fix as completing D6.7 or as eliminating the whole R2-N01 class.

## Independent deterministic verification

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q`: **480 passed**.
- `backend/.venv/bin/python -m ruff check` on both changed files: **PASS**.
- `backend/.venv/bin/python -m py_compile` on both changed files: **PASS**.
- Direct synthetic fixture: N4 `DELETE FROM mem_t USING bil_invoices ...` in `.py` and `.sql` now **FAIL/1** `CROSS_DOMAIN_SQL_IMPORT`, own=1/other=1; previously PASS/0, own=1/other=0. Dangling `DELETE FROM mem_t USING` now **ERROR/2** `MODULE_DEPS_SOURCE_UNINSPECTABLE` in both forms.
- Regression controls: N3 `REFERENCES bil_invoices` remains **FAIL/1**, own=1/other=1, both forms. P4 `JOIN mem_y USING (id)` remains **PASS/0**, own=2/other=0, both forms.

SHA-256: source `a6e1884a3b081391a4c0a6d28c17192aec0959fa0f912627d2423546985928ec`; tests `f856bc57adfda137a3a53aca6cf995562bebdd2cd2fb9b5bc4ddf020438c5b8c`. Both files remain untracked WIP; no commit/push.

## Remaining exact dependency and next boundary

R1-F01 is formally OPEN, R2-N01 P0 and R2 overall BLOCKED. ADR-011 D6.7.2 still requires actual per-position accounting independent of statement-level `if not idents:`; ONLY and other list/alias/subquery positions, the full ten-negative/five-positive/seven-mutant corpus, D8 lower-bound/completeness truthfulness and the stale module-docstring assertion remain. The N4 child explicitly disclosed these. Three prior completed operations plus this one did not reduce the original-finding blocker set, so the R04 stagnation gate must be reconciled before any further implementation dispatch. Preserve U1/U2 **B HOLD**; live CTE state-3 wiring remains forbidden. No review or scenario promotion is warranted.
