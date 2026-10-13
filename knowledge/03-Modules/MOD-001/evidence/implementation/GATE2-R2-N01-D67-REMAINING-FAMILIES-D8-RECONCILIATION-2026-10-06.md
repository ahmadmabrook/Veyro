# Gate-2 R1-F01 / R2-N01 — post-shared-list deterministic reconciliation

Runner operation `9cbfef2f-8e66-4b8d-9423-dc20a0cb35ed`. This operation performed fixture/accounting analysis only: **no guarded Claude dispatch, repository source/test edit, review, CTE state-3 wiring, or scenario promotion**. The preceding JOIN/USING increment and its 567/567 local tools-suite result remain preserved in `GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING-VERIFICATION-2026-10-06.md`. The source/test SHA-256 remained `0a551a6aeba9b02fa371880f985c3455b87ceaf4effcc1f6a3782626a0ca0ca2` / `d53bad4035996c130e26bdf4d0e4d0f6fa1342acf16504a192e94e4a41962b4e` before and after this analysis.

## Exact remaining behavior

Direct `_f12b_run` fixtures ran each SQL text as both `query.sql` and a Python string literal; both surfaces returned the same result. D8 figures below are read from the report's own `_f12b_counts`, shown as own / other / unattributed. Each report asserted **“the counts are complete for this run”** despite the absent or misattributed table position.

| SQL shape | Live result on each surface | D8 counts | Position-stream defect |
|---|---|---:|---|
| `INSERT INTO mem_t, bil_invoices SELECT 1` | false PASS/0 | 1 / 0 / 0 | only `INTO mem_t` emitted |
| `DROP TABLE mem_t, bil_invoices` | false PASS/0 | 1 / 0 / 0 | only `TABLE mem_t` emitted |
| `UPDATE mem_t, bil_invoices SET x = 1` | false PASS/0 | 1 / 0 / 0 | only `UPDATE mem_t` emitted |
| `CREATE TABLE mem_t (c int REFERENCES mem_a, bil_invoices)` | false PASS/0 | 2 / 0 / 0 | `TABLE mem_t` and first `REFERENCES mem_a` emitted; second omitted |
| `SELECT a FROM mem_roster, ONLY bil_invoices` | ERROR/2 `MODULE_DEPS_TABLE_UNATTRIBUTED` | 1 / 0 / 1 | FROM list emits `ONLY` as the identifier, not `bil_invoices` |
| `TRUNCATE mem_t, bil_invoices`; `COPY mem_t, bil_invoices TO STDOUT`; `GRANT SELECT ON mem_t, bil_invoices TO someone` | ERROR/2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` | 0 / 0 / 0 | bare-verb/ON forms have no position result; refusal is statement backstop rather than D6.7.2 per-position accounting |

`DROP TABLE mem_t, (SELECT 1)` is also false PASS/0 with own=1 and no unresolved second position. These are synthetic fixture-scoped counterexamples under ADR-011 D6.7.2–.5, not real-tree ownership assertions.

## Next smallest code/test seam, unimplemented

The existing `_table_list_positions` mechanism can be extended to `INTO`, `TABLE`, `UPDATE`, and `REFERENCES` through the single `_LIST_POSITION_SIGNALS` dispatch. A **runtime-only, in-memory** addition of those four signals changed each cross-domain negative above to FAIL/1 `CROSS_DOMAIN_SQL_IMPORT` (own/other 1/1 for the first three, 2/1 for REFERENCES). Representative positives stayed PASS/0: `CREATE TABLE mem_t (id int, x int)`, `UPDATE mem_t SET x=1, y=2`, `CREATE TABLE mem_t (c int REFERENCES mem_a)`, and `INSERT INTO mem_t (x,y) VALUES (1,2)`. This probe is feasibility evidence, **not** a completed code change or assurance. The next bounded implementation should add the four signals to the shared walker with `.py`/`.sql` negative and positive tests, an unresolved-second-element ERROR control, and a mutant dropping continuation. Do not replay already verified FROM/JOIN/USING work.

Subsequent distinct dependencies: correct `ONLY` target handling, bare TRUNCATE/COPY/GRANT position signals and list accounting, full N1–N10/P1–P5/M-E1–M-E7 corpus on both surfaces, D6.7.5's conditional completeness/lower-bound D8 wording including M-E6 text mutant, stale module docstring DC-12, then independent assurance. The D8 note currently selects “complete” from per-file scan scope, not established D6.7.2 position accounting, so even a PASS after partial extraction can falsely certify its own counts. R1-F01 and R2-N01 P0 remain formally OPEN; R2 remains BLOCKED. U1/U2 **B HOLD** remains binding.
