# R2-N01 / R1-F01 — D6.7.2 position-accounting gap (2026-10-06)

Operation `b7400bcb-ab85-43fa-bd79-19276c02e3e4`. Bounded deterministic analysis only; no scanner/test edit, review, or scenario verdict. R1-F01 and R2-N01 remain formally open; R2 remains BLOCKED. The named U1/U2 B HOLD continues to prohibit live CTE state-3 wiring.

## Reproduction on the current tree

The existing `_f12b_run` scaffold creates membership-owned `mem_roster` and billing-owned `bil_invoices`. Each case below was run in `query.sql` through the real gate report, and the six D8 counts were parsed from its emitted note. This is a real deterministic run, not a model-predicted result.

| Case | SQL | Exit / diagnostic | D8 own / other / unattributed | D8 complete claim |
| --- | --- | --- | --- | --- |
| N8 alias | `SELECT a FROM mem_roster m, bil_invoices b` | 0 PASS / none | 1 / 0 / 0 | yes |
| N9 AS alias | `SELECT a FROM mem_roster AS m, bil_invoices AS b` | 0 PASS / none | 1 / 0 / 0 | yes |
| N6 ONLY | `SELECT a FROM mem_roster, ONLY bil_invoices` | 2 ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED` | 1 / 0 / 1 | yes |
| P2 plain list | `SELECT a FROM mem_roster, bil_invoices` | 1 FAIL / `CROSS_DOMAIN_SQL_IMPORT` | 1 / 1 / 0 | yes |

N8/N9 are still false-clean: the second table position is lost behind the first identifier's alias. N6 is fail-closed but misattributes `ONLY` as an unattributed table name rather than reaching `bil_invoices`; that does not satisfy D6.7.2. The D8 `the counts are complete for this run` claim is false for the N8/N9 cases. P2 establishes that the simple comma-list path itself is live, not that alias-bearing continuations are covered.

## Structural cause and bounded next operation

`_extract_table_identifiers` and `_dangling_keywords` consume matching signal sources, which locally fixed N3 REFERENCES and N4 DELETE USING. But they return identifier lists / a boolean, not a record for every recognized table position. `_scan_sql_statement` still uses statement-level `if not idents:`; once one identifier is present, this guard cannot prove that every other recognized position was consumed and attributed. The alias-list reproducer shows the consequence. The current D8 count note describes extracted identifiers, yet claims complete accounting.

The next **one-operation** implementation should replace the aggregate seam with an explicit per-position result stream: each recognized table-position signal/continuation produces one record identifying its source/span and either a parsed identifier or an unresolved reason. The scanner must compare recognized positions against attributed terminal states position by position and emit `MODULE_DEPS_SOURCE_UNINSPECTABLE` naming any unresolved signal, even when another position is clean. Do not use an aggregate count-only test or another keyword-only patch. Scope the first bounded increment to FROM alias/AS-alias comma continuations and the core per-position accounting seam; prove N8/N9 fail with exactly one cross-domain finding, P2 remains FAIL/1, an own-table aliased positive remains PASS, and an unresolved second position after a clean first emits ERROR. Preserve N3/N4/P4 behavior. D6.7.3 other list forms, ONLY correct attribution, the full N1–N10/P1–P5/M-E1–M-E7 corpus, and D8 lower-bound-vs-complete wording remain explicit subsequent dependencies; do not claim closure from this increment.

No full review, scenario certification, CTE wiring, or original-finding closure is authorized by this analysis. The material strategy boundary requires runner-contract refresh before the next dispatch.
