---
doc: GATE2-R2-N01-D67-POST-INCREMENT-CONVERGENCE-ANALYSIS-2026-10-06
module: MOD-001
requirement: GOV-01-R04
finding: R1-F01 / R2-N01 / BUG-053
status: ANALYSIS_ONLY; R2_BLOCKED
---

# R2-N01 convergence after the first D6.7 increment

The sole runner reconciled the guarded `SOFT_NO_PROGRESS` operation `616a3879-8f9c-423a-93c8-d847cb37f30a` before this analysis. Its source/test changes are durable and independently verified by the runner (471/471 architecture-gate tests, Ruff and compile PASS; hashes in `GATE2-R2-N01-D6.7-FROM-LIST-FIRST-SUBCASE-2026-10-06.md`). The soft stop is **not** a failed test or a final Claude verdict, and the exact `FROM`-list implementation subgoal is consumed, not replayable.

Against the current fixture helper `_f12b_run` with a `.py` literal, the runner measured:

| Qualified-lead corpus row | Current result | D6.7 disposition |
|---|---|---|
| N1 `FROM mem_roster, bil_invoices` | FAIL/1 `CROSS_DOMAIN_SQL_IMPORT`, own=1/other=1 | First bounded subcase locally fixed, not assured |
| N2 `FROM mem_roster, nobody_owns_this` | ERROR/2 `MODULE_DEPS_TABLE_UNATTRIBUTED`, own=1/unattributed=1 | Correct control |
| N3 `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` | **PASS/0**, own=1/other=0 | P0 false clean remains |
| N4 `DELETE FROM mem_roster USING bil_invoices` | **PASS/0**, own=1/other=0 | P0 false clean remains |
| N5 three-element `FROM` list with two `bil_` tables | FAIL/1, own=1/other=2 | First bounded subcase locally fixed, not assured |
| N6 `FROM mem_roster, ONLY bil_invoices` | ERROR/2 `MODULE_DEPS_TABLE_UNATTRIBUTED`, own=1/unattributed=1 | Nonzero but not yet correctly position-accounted; exact-code corpus pending |
| P2 same-module comma list | PASS/0, own=2 | Non-vacuity control retained |
| P4 `JOIN mem_y USING (id)` column list | PASS/0, own=2 | Necessary non-table-position control retained |

These are current **fixture-scoped** observations; real-tree domain ownership remains DEFERRED. They are not scenario execution or an assurance verdict. Source/test hashes remained `febab8d3b6f382f28861f0ae637b66020fc96ef4abf5e9b73cbf3d0b15586209` and `404cfff43119470b6ff9ce584262f7dbfc515155849683eec62c3ad783ab850d` after this read-only analysis.

## Classification and changed strategy

R2-N01 is a **RECURRING_DEFECT** of R1-F01's cross-domain false-PASS invariant, at a distinct partial-extraction mechanism. The qualified lead already classified R2-N02 as its governing-contract root cause and amended ADR-011 D6.7. The one completed `FROM`-list patch narrows two corpus failures but does not reduce the original formal blocker set: 14 original findings remain OPEN; R2 remains BLOCKED P0=1/P1=1/P2=2/P3=2. The active unit retains **2 completed independent review rounds and 1 completed remediation cycle**; a soft-stopped partial increment does not mint a review verdict or reset either count. The R04 stagnation counter is **2 completed no-reduction operations**, not 3: the soft-stopped operation is separately preserved as material partial work.

The next strategy is **shared table-position signal accounting**, not another keyword-only or `FROM`-specific extraction patch. Preserve each recognized position independently through extraction and D3.2 attribution, with an unmatched signal becoming `MODULE_DEPS_SOURCE_UNINSPECTABLE` even when another identifier extracted cleanly. This is the D6.7.2 mechanism that the former statement-level `if not idents:` backstop lacks. The first bounded implementation subgoal should establish that seam for N3 `REFERENCES` through both `.py` and `.sql` paths, prove an own-table first identifier cannot suppress it, and keep P4 `JOIN ... USING (id)` PASS as a non-vacuity guard. Add a targeted mutant that drops or marks the N3 signal accounted without attribution; it must be killed. Do **not** satisfy N3 merely by widening `_TABLE_KEYWORD_RE`; ADR-011 rejects vocabulary expansion as the whole fix. N4 `DELETE ... USING` and its P4 discrimination, remaining N rows, D8 truthfulness, and the M-E1…M-E7 corpus remain separately pending. No third-party parser, trigger narrowing, real-tree ownership binding, or live CTE state-3 wiring is authorized.

This materially changes the implementation mechanism from a narrow comma-continuation walker to position-signal/attribution accounting. One guarded Sonnet implementation increment may be dispatched only after this analysis is checkpointed and the required contract refresh is acknowledged. No full review or scenario promotion is legal while the P0 and other code/test blockers remain.
