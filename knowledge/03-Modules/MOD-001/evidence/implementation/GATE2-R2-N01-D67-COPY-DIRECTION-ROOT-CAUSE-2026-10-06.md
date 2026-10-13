# R1-F01 / R2-N01 — D6.7 COPY directional root cause

Runner operation `4cd575df-2715-4ef3-813e-f671934829c0`. Deterministic diagnosis only. No scanner/test edit, Claude dispatch, review, scenario verdict, D8 change, or CTE state-3 wiring. U1/U2 B HOLD persists and R1-F01/R2-N01 remains formally OPEN.

Fresh isolated membership (`mem_`) fixtures ran the identical SQL as a `.sql` file and Python string literal; `_table_position_results` and live report status/codes/counts matched on both surfaces:

| SQL | Position records now | Live result now | Diagnosis |
| --- | --- | --- | --- |
| `COPY mem_roster TO STDOUT` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE`, own=0 | Bare table target omitted; an own target should be attributable. |
| `COPY bil_invoices TO STDOUT` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE`, other=0 | Cross-domain target omitted; it should earn `CROSS_DOMAIN_SQL_IMPORT`. |
| `COPY mem_roster FROM STDIN` | `FROM → STDIN` | ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED`, own=0 | Directional `FROM` is not a table-position signal; the real COPY target is absent. |
| `COPY bil_invoices FROM STDIN` | `FROM → STDIN` | ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED`, other=0 | Same false directional attribution masks the cross-domain target. |
| `COPY (SELECT * FROM mem_roster) TO STDOUT` | `FROM → mem_roster` | PASS, own=1 | Inner query `FROM` is a real table position and must remain. |
| `COPY (SELECT * FROM bil_invoices) TO STDOUT` | `FROM → bil_invoices` | FAIL / `CROSS_DOMAIN_SQL_IMPORT`, other=1 | Query-form cross-domain denial must remain. |
| `COPY (SELECT 1) TO STDOUT` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE` | D6.3 query-form versus bare-table-form classification needs an explicit decision; a blanket `COPY` backstop assumes a table position. |
| `SELECT * FROM bil_invoices` | `FROM → bil_invoices` | FAIL / `CROSS_DOMAIN_SQL_IMPORT` | Ordinary `FROM` must remain a signal. |
| `COPY` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE` | Dangling COPY must continue to fail closed. |

## Shared seam and decision boundary

`_TABLE_KEYWORD_RE` currently supplies every context-free `FROM`; `_TABLE_POSITION_SIGNAL_SOURCES` feeds the shared `_positions_for_signal` / `_table_list_positions` stream, and `_has_bare_table_verb_form` treats every `COPY` as a bare-table form. A safe implementation cannot simply add `COPY` to the keyword/list sets: that does not account for the directional `FROM STDIN` false position and may read `(` in query form as an unresolved table target. It also cannot globally suppress `FROM`: that loses ordinary SELECT and the real inner `FROM` of `COPY (SELECT ...)`.

The smallest structural implementation would distinguish a COPY **table-target form** from its query form at the COPY target offset, emit the table target via the existing shared signal/list seam, and classify only the **top-level directional** `FROM`/`TO` after that target as non-table tokens while leaving inner-query FROM signals intact. A bare `COPY`/malformed target remains unresolved and ERROR. Exact controls must include both surfaces and position cardinality/identifiers for the rows above, own-target PASS, cross-domain FAIL, dangling ERROR, ordinary FROM FAIL, inner-query FROM PASS/FAIL, and mutations for omitted COPY source, context-free COPY source, global FROM suppression, and direction-token misclassification.

This crosses an ADR-011 D6.7.1 boundary: excluding the currently extracted `FROM → STDIN` is an extractor narrowing, which D6.7.1 says requires its **own recorded decision**, even though that record is a false table position. D6.3's wording names a *bare-table* COPY form, but does not explicitly classify `COPY (SELECT 1) TO STDOUT`; its current I-1 ERROR is not evidence of a true table position. A qualified, bounded interpretation of both cases is required before code dispatch. No parser, D8 completeness, scenario PASS or review verdict is inferred from this probe.
