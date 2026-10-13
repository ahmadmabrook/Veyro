# R2-N01 / R1-F01 — post-position-core stagnation reconciliation

Runner operation `21c074d5-251e-4adf-9e6f-ba0c0f932db7`. Deterministic analysis only; no scanner/test change, Claude dispatch, review or scenario verdict. The preceding position-result-core operation `b29ea7ad-25fd-4068-a74c-bbe16da49323` is COMPLETED exit 0 and independently verified; do not replay it. R1-F01 and R2-N01 remain formally OPEN; R2 BLOCKED. U1/U2 B HOLD forbids live CTE state-3 wiring.

## Exact current behavior

The existing `_f12b_run` membership/billing fixture was rerun after the prior operation. Counts below are parsed from the emitted D8 attribution note, not recomputed from the SQL. The entire N1–N10 qualified negative set was nonzero: N1/N3/N4/N5/N7/N8/N9 fail with cross-domain findings, N2 errors with unattributed table, N6 errors by misattributing `ONLY` as a table, and N10 errors because quoted uppercase `"BIL_INVOICES"` remains case-sensitive/unattributed. These are **outcomes**, not a claim that D6.7.3 or D8 is complete. P2 own-table list and P4 JOIN USING column-list remain PASS.

| Probe | Exit / diagnostic | D8 own / other / unattributed | Recorded positions | Complete-count claim |
| --- | --- | --- | --- | --- |
| `SELECT a FROM mem_roster JOIN mem_events, bil_invoices ON 1=1` | 0 PASS / none — false clean | 2 / 0 / 0 | FROM `mem_roster`; JOIN `mem_events`; **billing target absent** | yes — false |
| `DELETE FROM mem_roster USING mem_events, bil_invoices WHERE 1=1` | 0 PASS / none — false clean | 2 / 0 / 0 | FROM `mem_roster`; USING `mem_events`; **billing target absent** | yes — false |
| `SELECT a FROM mem_roster, ONLY bil_invoices` | 2 ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED` | 1 / 0 / 1 | FROM `mem_roster`; FROM `ONLY` — wrong target | yes — false |
| `SELECT a FROM ONLY bil_invoices` | 2 ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED` | 0 / 0 / 1 | FROM `ONLY` — wrong target | yes — false |
| `SELECT a FROM mem_roster, mem_events` | 0 PASS | 2 / 0 / 0 | both own targets | yes |
| `SELECT a FROM mem_roster JOIN mem_events USING (id)` | 0 PASS | 2 / 0 / 0 | JOIN USING column-list correctly excluded | yes |

The new `_TablePositionResult` either/or invariant prevents a **recognized** position from being neither attributed nor refused. It cannot account for a position that the signal/list walker never emits. `_from_list_positions` handles FROM aliases only; `_single_identifier_position` still handles JOIN/USING one target each. `_d8_table_ref_note` selects `the counts are complete for this run` solely from per-file scan scope, without a D6.7.2 position-completeness proof. Hence the same root defect survives in two valid list families despite green focused tests. Keyword-specific additions would repeat the treadmill ADR-011 rejected.

## Materially changed bounded strategy

Replace the FROM-only continuation mechanism with **one shared, depth-aware table-list position walker** used by both existing `FROM` and the independently recognized `JOIN` and table-position `USING` signal sources. One signal plus its same-depth comma continuations must emit one `_TablePositionResult` per element, including unresolved elements; preserve the JOIN `USING (id)` column-list exclusion. The next **single** guarded code/test increment is bounded to JOIN and DELETE USING comma lists through this shared walker. Required proof: each false-clean SQL above as `.py` and `.sql` becomes FAIL/1 `CROSS_DOMAIN_SQL_IMPORT` with D8 own=2/other=1; an unresolved second position after a clean first becomes ERROR naming its originating signal; own-table JOIN and USING lists PASS, P4 remains PASS, and N1/N8/N9 remain unchanged. A mutation removing the shared continuation must be killed for both list families. Focused tests, Ruff, compile, then independent local rerun. This is a new shared grammar seam, not another per-keyword extraction patch and not a claim that all D6.7.3 forms are done.

Subsequent distinct dependencies: INTO/TABLE/REFERENCES/ONLY and bare-verb list positions and correct `ONLY` target attribution; full N1–N10/P1–P5/M-E1–M-E7 suite on `.py` and `.sql`; D6.7.5 lower-bound-vs-complete note correction and M-E6 text mutant; stale module docstring at `tools/validate_architecture_gates.py:249-257`; independent assurance. The real-tree manifest remains owner-reserved and is not a prerequisite for these fixture-scoped tests. No full review or scenario promotion while these code/test blockers remain.

This strategy selection is a material boundary: refresh the runner contract next turn before implementation dispatch.
