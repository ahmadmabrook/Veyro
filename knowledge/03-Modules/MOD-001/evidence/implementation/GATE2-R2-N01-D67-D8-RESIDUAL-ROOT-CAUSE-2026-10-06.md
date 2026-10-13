# Gate-2 R1-F01 / R2-N01 — residual position accounting and D8 root cause

Runner operation `43ac24da-a002-494a-97f4-fe0c5184ba9d`; deterministic analysis only. No guarded Claude dispatch, source/test change, review, scenario promotion, or live CTE state-3 wiring. The preceding four-signal shared-walker increment remains verified in `GATE2-R2-N01-D67-SHARED-LIST-WALK-FOUR-SIGNALS-2026-10-06.md`. R1-F01/R2-N01 P0 remain formally OPEN; round-2 review remains BLOCKED; U1/U2 B HOLD persists.

## Reproduced facts

Using `_f12b_run` on real SQL fixture files and reading `_f12b_counts` and `_f12b_ref_note` from each report:

| Subject | Result | D8 own / other / unattributed | `_table_position_results` | Current note |
|---|---|---:|---|---|
| `SELECT a FROM mem_roster, ONLY bil_invoices` | ERROR/2 `MODULE_DEPS_TABLE_UNATTRIBUTED` | 1 / 0 / 1 | `FROM mem_roster`, `FROM ONLY`; **billing target omitted** | “the counts are complete for this run” |
| `SELECT a FROM mem_roster, ONLY mem_events` | same ERROR/2 | 1 / 0 / 1 | same wrong `ONLY` target, even though actual second table is owned | same false completeness |
| `TRUNCATE mem_t, bil_invoices` | ERROR/2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` | 0 / 0 / 0 | empty | same false completeness |
| `TRUNCATE mem_t`; `COPY mem_t, bil_invoices TO STDOUT`; `GRANT SELECT ON mem_t, bil_invoices TO someone` | ERROR/2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` | 0 / 0 / 0 | empty | same false completeness |
| `SELECT a FROM mem_roster` | PASS/0 | 1 / 0 / 0 | one correct FROM target | “complete” currently, but the run-level code does not carry a proof of position-totality |

A two-file run with `a.sql: SELECT a FROM mem_roster` and `b.sql: TRUNCATE mem_t, bil_invoices` returns ERROR/2 with D8 own/other/unattributed **1/0/0** while calling those counts complete, despite the unaccounted positions in `b.sql`. The ERROR status refuses the tree; it does **not** make the attribution count a total. This is an executed counterexample to the current D8 sentence, not an inferred risk.

## Causal split and proof obligation

`_scan_sql_statement`'s `_table_position_results` stream is per-position for **recognised** signals, and it refuses an unresolved record. It cannot establish that an unrecognised table position does not exist: bare TRUNCATE/COPY/GRANT yield an empty stream and fall through to the statement I-1 backstop; ONLY yields a record for the keyword rather than the target. D6.7.2's necessary accounting condition is therefore not proved by a clean per-file scan, nor by nonzero extracted identifiers, nor by the absence of a dangling record. All six D3.2 counters total only **attributed extracted identifiers**. A report can call them complete only if **every SQL-ish subject in the run has a demonstrated complete table-position inventory and every inventory position reached a D3.2 terminal state**. The current run state carries no such proof. `_d8_table_ref_note` instead treats `_D8_SCOPE_COMPLETE` (per-file scan finished) as permission for the unqualified sentence “the counts are complete for this run” on PASS, FAIL, and ERROR alike. That conflates file traversal with position-totality and contradicts ADR-011 D6.7.5.

## Next single bounded code/test seam — not implemented here

Correct the **D8 table-reference attribution note only** to call the figures a **lower bound** on completed scans until an explicit D6.7.2 position-totality proof exists; keep `_D8_SCOPE_PARTIAL` as lower bound and `_D8_SCOPE_NOT_STARTED` as not-started zeros, preserving their distinct meanings. Do not claim a complete total merely because a subject happens to use the currently recognised syntax. Do not alter gate outcome codes, scan/attribution behavior, other D8 dimensions, or CTE state 3 in this increment.

Test the exact report text (and `asdict()`/JSON note) for PASS, FAIL, and ERROR, including the mixed two-file counterexample above. The M-E6 mutant that restores “the counts are complete for this run” for the completed-scan branch must be killed by a text assertion; an exit-code-only test cannot catch it. Positive controls must retain existing statuses and exact D3.2 numeric counters, and distinguish a genuinely completed **file scan** from a proved complete **table-reference inventory**. This is a truthful-disclosure increment, not R1-F01 closure.

Subsequent independent defects remain: `ONLY` target attribution, bare-verb/ON per-position signal and comma-list accounting, full N1–N10/P1–P5/M-E1–M-E7 corpus on both surfaces, DC-12 module docstring, then independent assurance. The reserved real-tree ownership manifest is not a prerequisite for fixture-scoped correction.
