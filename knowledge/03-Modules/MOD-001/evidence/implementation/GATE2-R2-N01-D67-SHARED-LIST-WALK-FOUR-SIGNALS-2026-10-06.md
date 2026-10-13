# Gate-2 R1-F01 / R2-N01 — shared list walk extended to INTO / TABLE / UPDATE / REFERENCES

Runner operation `dc76446a-8662-4cd1-a159-88659d56c7c2`, subgoal
`R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-FOUR-SIGNALS`. Routine implementation tier
(`veyro-implementer` / Sonnet routing per ADR-005; no Opus-reserved architectural
judgment was required, since ADR-011 D6.7.3 already decided the mechanism and the
preceding reconciliation already identified the seam). **No independent review, no
assurance claim, no scenario promotion, no CTE state-3 wiring, no CTE resolution-order
change, no real-tree ownership work, no commit, no push.** All pre-existing uncommitted
WIP preserved; `HEAD` unchanged at `e481b81`.

Predecessor increment: `GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING-VERIFICATION-2026-10-06.md`.
Input analysis: `GATE2-R2-N01-D67-REMAINING-FAMILIES-D8-RECONCILIATION-2026-10-06.md`.
Governing clause: ADR-011 addendum D6.7.1 / D6.7.2 / D6.7.3.

## 1. Baseline independently re-reproduced before any edit

The four families named by the reconciliation record were re-run against the unmodified
source on **both** surfaces (`.py` string literal and real `.sql` fixture file) via the
test module's own `_f12b_run` scaffold. All eight runs reproduced the recorded false
PASS, with the D8 counts read out of the report's own disclosure note (own / other /
unattributed):

| Statement | Result, both surfaces | D8 counts |
|---|---|---:|
| `INSERT INTO mem_t, bil_invoices SELECT 1` | PASS / 0 | 1 / 0 / 0 |
| `DROP TABLE mem_t, bil_invoices` | PASS / 0 | 1 / 0 / 0 |
| `UPDATE mem_t, bil_invoices SET x = 1` | PASS / 0 | 1 / 0 / 0 |
| `CREATE TABLE mem_t (c int REFERENCES mem_a, bil_invoices)` | PASS / 0 | 2 / 0 / 0 |

The unresolved-second-element variants (second element a parenthesised subquery) were
**also** false PASS / 0 before this increment, in all four families and on both surfaces.

## 2. Change made

One seam, in `tools/validate_architecture_gates.py`:

```
_LIST_POSITION_SIGNALS = frozenset({
    "FROM", "JOIN", "USING", "INTO", "TABLE", "UPDATE", "REFERENCES",
})
```

`INTO`, `TABLE`, `UPDATE` and `REFERENCES` were each **already** a recognised
table-position signal, so the *first* element of each one's list was always a position —
which is precisely why the D6.3 statement backstop was already disarmed and the element
beside it was silently absent from the stream. Only the comma continuation was out of
reach. No per-keyword walker was added, and none can be: `_positions_for_signal`
consults this frozenset in exactly one place, and the shared `_table_list_positions`
walk is written against the signal match alone.

Also updated, same file, no behavioural effect: the `_table_list_positions` and
`_table_position_results` docstrings, which documented the previous three-signal scope
as current behaviour (DC-12 accuracy for the text this increment itself made stale), and
a new comment block recording the reproduced defect and why `ONLY` / bare-verb forms are
deliberately still absent.

## 3. Tests added

Four focused tests in `tools/tests/test_validate_architecture_gates.py`, each asserting
through both the `.py`-literal and `.sql`-file surfaces:

- `test_gate2_d6_7_four_signal_comma_lists_cross_domain_both_surfaces` — each of the
  four negatives is now **FAIL / 1 `CROSS_DOMAIN_SQL_IMPORT`**, subject
  `membership -> billing`, detail naming `'bil_invoices'`, with `other == 1` (the
  previously-absent billing position now counted) **and** the per-row `own` count
  preserved (1, 1, 1, 2) so a blanket refusal cannot satisfy it.
- `test_gate2_d6_7_four_signal_unresolved_second_element_errors_naming_signal` — a clean
  first element followed by an unresolvable one is **ERROR / 2
  `MODULE_DEPS_SOURCE_UNINSPECTABLE`** naming the originating signal
  (`INTO` / `TABLE` / `UPDATE` / `REFERENCES` "signal at offset …"), verified present in
  the violation detail rather than only in the exit code.
- `test_gate2_d6_7_four_signal_ordinary_comma_forms_stay_clean` — the non-vacuity
  discriminators stay **PASS / 0**, zero violations, `other == 0`, `unattributed == 0`:
  `CREATE TABLE mem_t (id int, x int)` (column list), `UPDATE mem_t SET x = 1, y = 2`
  (SET assignment list), `CREATE TABLE mem_t (c int REFERENCES mem_a)` (single
  REFERENCES target), `INSERT INTO mem_t (x, y) VALUES (1, 2)` (INSERT column list).
- `test_gate2_d6_7_four_signal_shared_walk_mutation_control` — white-box pins: the exact
  frozenset membership, exactly one `_table_list_positions` call site in
  `_positions_for_signal`, the per-family identifier stream and signal attribution,
  `_dangling_keywords is False` on the negatives (so the refusal is not reached by the
  statement-level route), three-element lists per family (so a widen-by-one mutant is
  caught), and the unresolved-element records.

One pre-existing assertion was relaxed deliberately: the JOIN/USING mutation control's
`_LIST_POSITION_SIGNALS == {"FROM", "JOIN", "USING"}` became a subset check
(`{"FROM", "JOIN", "USING"} <= _LIST_POSITION_SIGNALS`), with exact membership now owned
by the new four-signal control. That block's stale "still pending: INTO/TABLE/
REFERENCES" comment was corrected to point at the new block.

## 4. Mutants — actually executed, not asserted

Both drills were run in throwaway full-structure copies under `/tmp`, never against the
real tree (`git status --porcelain tools/` confirmed the two target files untouched by
the drills afterwards; both copies removed). A **control copy** was run first, because
the copies carry 26 pre-existing failures from tests that read repository-root files —
so mutant effect is reported as the set difference against that control, not as a raw
count.

- **Dropped-signal mutant** (frozenset reverted to `{"FROM", "JOIN", "USING"}`):
  killed. Exactly three mutant-only failures, all three the new behavioural tests
  (cross-domain, unresolved-element, mutation control). The positives test correctly
  still passes — the mutant removes refusals rather than adding them.
- **Shared-continuation mutant** (the `while` continuation loop deleted from
  `_table_list_positions`): killed, with **22** mutant-only failures spanning *every*
  family — N1/N8/N9 `FROM`, the JOIN/USING block, and all four new signals. One edit,
  every family, which is the structural property four hand-copied per-keyword walks
  would not have.

Both mutants reverted (copies discarded) and the suite re-run green.

## 5. Verification executed this session

| Check | Result |
|---|---|
| Focused `-k d6_7` | **32 passed** |
| Full `tools/tests/` suite | **571 passed** (567 before + 4 new) |
| Direct-run path (`python tools/tests/test_validate_architecture_gates.py`) | **PASS — all 498 tests passed** |
| `ruff check` (both changed files) | **All checks passed** |
| `py_compile` (both changed files) | OK |
| `verify_baselines.py` | **PASS, 4/4 governing baselines unchanged** |
| `git rev-parse HEAD` | `e481b81`, unchanged |

Post-change SHA-256: `tools/validate_architecture_gates.py`
`6c18ab982fb7124ac93bef498537dd54628898ae77ea7c29aa6d1b38104f9f6e`;
`tools/tests/test_validate_architecture_gates.py`
`1e60b75abe4cc4d66d17d399544a43ad2addf1a5a2a6e6c70a8a2e9718fa60c0`.

## 6. Disclosed as NOT done — remaining dependencies

1. **`ONLY` accounting is unchanged and still wrong.**
   `SELECT a FROM mem_roster, ONLY bil_invoices` was re-run after this change: still
   **ERROR / 2 `MODULE_DEPS_TABLE_UNATTRIBUTED`**, D8 counts 1 / 0 / 1. It refuses, but
   for the wrong reason — the FROM-list walk emits `ONLY` itself as the element
   identifier, so the billing table is never extracted and never attributed. No list
   walk fixes this; `ONLY` needs its own signal-source/target handling first, which is
   why it is deliberately absent from `_LIST_POSITION_SIGNALS`. Not a membership
   question yet.
2. **Bare-verb forms are unchanged and still refused only by the statement backstop.**
   `TRUNCATE mem_t, bil_invoices` re-run after this change: **ERROR / 2
   `MODULE_DEPS_SOURCE_UNINSPECTABLE`**, D8 counts 0 / 0 / 0. `COPY ... TO STDOUT` and
   `GRANT SELECT ON ...` are the same shape. These produce **no position result at
   all**, so the refusal is the statement-level backstop rather than D6.7.2 per-position
   accounting. Distinct increment.
3. **D6.7.5 is not addressed — the D8 note still asserts false completeness.** The
   disclosure note still carries the unconditional sentence "the counts are complete for
   this run", and it is still selected from per-file scan scope rather than from
   established D6.7.2 position accounting. Verified unchanged this session on a PASS, on
   the `ONLY` ERROR, and on the `TRUNCATE` ERROR. A PASS after partial extraction can
   therefore still falsely certify its own counts. Out of scope by instruction; the one
   remaining false-in-the-reassuring-direction claim on this surface.
4. **Full corpus not run.** The N1–N10 / P1–P5 / M-E1–M-E7 corpus on both surfaces,
   including the M-E6 text mutant, is not executed by this increment. Only the four
   families, their four positives, their four unresolved controls and two mutants are.
5. **DC-12 module-docstring correction still owed.** `tools/validate_architecture_gates.py`
   still states, as current behaviour, that "An identifier no module owns is **not
   flagged** — only counted and disclosed in a note" — the terminal state ADR-011 D9
   forbids and the addendum's follow-up requires corrected before any D6.7 remediation
   record may claim this work finished. **This record makes no such claim.** Note the
   addendum cites this text at lines 249–257; the sentence now sits at lines 262–264,
   the docstring having grown since. Additionally, the same docstring's "across a FROM
   list's comma-separated elements" phrasing now understates the walk's actual reach
   (it predates the JOIN/USING increment as well) — an accuracy nit in the safe
   direction, left for the DC-12 pass rather than touched piecemeal here.
6. **No independent assurance.** This is implementation-tier work, self-verified only.
   DC-06/DC-14 fresh-context independent review has not been dispatched, no
   `REVIEW_IN_FLIGHT.md` claim was written, and nothing here is a PASS, an approval, or
   a convergence claim.

## 7. Status unchanged by this increment

`R1-F01` and `R2-N01` **P0 remain formally OPEN**; gate-2 round 2 remains **BLOCKED**.
`SCN-MOD001-006` / `-007` / `-095` / `-096` remain **NOT EXECUTED** and unpromoted.
The U1/U2 named-judgment **B HOLD** remains binding and untouched (no CTE state-3
wiring, no resolution-order change). Real-tree domain/prefix binding remains
`BLOCKED: OWNER_APPROVAL_REQUIRED` and is not a dependency of this increment. WIP=1
preserved; MOD-002 remains locked.

## 8. Runner collection and independent local check

After the guarded child exited 0 and `ACTIVE_OPERATION.json` recorded COMPLETED, the sole runner independently reran `backend/.venv/bin/python -m pytest tools/tests/ -q` (**571 passed**), Ruff on both changed files (**PASS**), and `compileall` on both (**PASS**). Runner-owned direct `_f12b_run` execution then confirmed each of the four cross-domain negatives is FAIL/1 `CROSS_DOMAIN_SQL_IMPORT` on both `.py` and `.sql` (D8 own/other/unattributed respectively 1/1/0, 1/1/0, 1/1/0, 2/1/0); each of four unresolved-second-position variants is ERROR/2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` on both; and each of the four listed positive controls is PASS/0 on both. These checks do not discharge the dependencies in §6.

The child created this evidence record after dispatch, so `operation_budget.py checkpoint --kind evidence` rejected it as an undeclared tracked path. Its **code and test** checkpoints succeeded. The evidence-file checkpoint failure is disclosed, not counted as material budget progress; the runner independently inspected this record and verified the results above before citing it for R1-F01's blocked status.
