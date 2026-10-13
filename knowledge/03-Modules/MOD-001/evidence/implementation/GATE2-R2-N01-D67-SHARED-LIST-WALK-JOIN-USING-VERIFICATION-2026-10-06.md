# Gate-2 R1-F01 / R2-N01 — D6.7 shared list-position increment

Operation `8917098b-bdcf-4d58-9e4a-bdf61b63d422`; bounded subgoal `R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING`. Guarded implementation completed with exit 0. This is a local code/test increment, **not** formal finding closure or assurance.

## Change and independent verification

`tools/validate_architecture_gates.py` now routes FROM, JOIN, and table-valued USING through one `_table_list_positions` continuation walker. JOIN `USING (id)` remains a column list, not a table position. `tools/tests/test_validate_architecture_gates.py` adds focused negative, positive, unresolved-position, and shared-walker mutation controls. The guarded implementer reported that removing JOIN/USING from the shared signal set kills both new negative families and removing the shared continuation loop kills those plus existing FROM N1/N8/N9 controls; the implementer restored the code after each drill.

I independently reran `backend/.venv/bin/python -m pytest tools/tests/ -q`: **567 passed**. Ruff on the two files: **PASS**. `compileall` on both: **PASS**. Direct fixture execution through `_f12b_run` and report-derived `_f12b_counts` returned:

| Fixture | Result | D8 own / other / unattributed |
|---|---|---:|
| `FROM mem_roster JOIN mem_events, bil_invoices`, Python literal and SQL file | FAIL/1, one `CROSS_DOMAIN_SQL_IMPORT` each | 2 / 1 / 0 |
| `DELETE FROM mem_roster USING mem_events, bil_invoices`, Python literal and SQL file | FAIL/1, one `CROSS_DOMAIN_SQL_IMPORT` each | 2 / 1 / 0 |
| JOIN and DELETE USING with `(SELECT 1)` as second position | ERROR/2, `MODULE_DEPS_SOURCE_UNINSPECTABLE` each | — |
| JOIN and DELETE USING with `mem_dues` as second position | PASS/0 each | 3 / 0 / 0 |
| P4 `JOIN mem_events USING (id)` | PASS/0 | 2 / 0 / 0 |
| N8/N9 alias-list cross-domain controls | FAIL/1 each | 1 / 1 / 0 |

Source SHA-256 `0a551a6aeba9b02fa371880f985c3455b87ceaf4effcc1f6a3782626a0ca0ca2`; test SHA-256 `d53bad4035996c130e26bdf4d0e4d0f6fa1342acf16504a192e94e4a41962b4e` (guarded operation final hashes). The files remain untracked pre-existing WIP; no commit or unrelated source change was made in this increment.

## Remaining exact dependency

R1-F01 and R2-N01 P0 remain formally **OPEN**; round-2 review remains **BLOCKED**. D6.7.3 position-totality for INTO, TABLE, UPDATE, REFERENCES, ONLY and bare-verb/list families remains unverified or single-target; ONLY still misattributes its keyword. N2 unattributed-table and N10 quoted-uppercase behavior remain. The full N1–N10 / P1–P5 / M-E1–M-E7 corpus on both Python and SQL has not run. D6.7.5 is unchanged: `_d8_table_ref_note` can still assert “the counts are complete for this run” from scan scope without position-completeness proof, including the M-E6 text-mutant gap. The stale module docstring DC-12 also remains. Independent combined assurance has not evaluated this increment. U1/U2 B HOLD persists; live CTE state-3 wiring, scenario promotion, and a full review are not authorized at this boundary.
