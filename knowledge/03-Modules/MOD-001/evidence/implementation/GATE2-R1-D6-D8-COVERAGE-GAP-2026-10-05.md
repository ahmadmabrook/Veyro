# Gate-2 R1 D6 — ADR-011 D8 state-3 coverage gap (2026-10-05)

**Status:** evidence-only disclosure, not live CTE wiring, an independent review, or a scenario verdict. This records the narrow D8 consequence of the named lead's pre-wire **B HOLD**. The round-1 gate-2 code review remains BLOCKED and R1-F01 formally OPEN; SCN-MOD001-006/007/095/096 remain NOT EXECUTED.

## Observed live coverage

`tools/validate_architecture_gates.py` `_scan_sql_text` calls `attribute_table_identifier(ident, modules, importer, default_schema)` without a `cte_names` argument. The latter's default is `frozenset()`. The pure `_cte_scopes` helper and its U1 lexical tests are not wired into this call path. Thus ADR-011 D3.2 state 3 (`ATTR_CTE`) is **unreachable in the live gate-2 scan**. Passing pure-helper tests does not change that fact or establish a live positive proof.

An otherwise-unattributed genuine depth-0 `WITH` CTE table-position name follows the unchanged attribution chain to state 6, `MODULE_DEPS_TABLE_UNATTRIBUTED` (ERROR), rather than becoming clean-and-counted as state 3. Depending on its name and declarations, an identifier can instead resolve to another existing state; the gap does **not** mean every CTE-looking name necessarily ERRORs. Keeping state 3 unreachable can cause a loud false fail for a genuine CTE but cannot introduce a state-3 false clean relative to the current no-CTE baseline. This does not cure other existing scanner findings or constitute assurance that the whole gate has no false PASS.

The correction record `GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md` §2.1 prescribes this disclosure sentence for a *future wired statement-scoped design* (verbatim, not a claim that the design is live):

> CTE-local attribution (ADR-011 D3.2 state 3) is **statement-scoped**:
> bindings are collected per lexically-segmented statement, and are
> **declined** for any statement containing a semicolon that is not its
> own terminator, and for any text that cannot be lexically segmented at
> all. A declined binding does not create a state of its own — the
> identifier resolves through the unchanged D3.2 precedence chain and may
> land in any of states 1, 2, 4, 5 or 6. Declining therefore never makes
> an identifier *cleaner* than it would be with no CTE support at all,
> which is the fail-closed property; it does not guarantee an ERROR.

## Evidence and next dependency

- Named lead/Opus B HOLD: `GATE2-R1-D6-D3D9-PREWIRE-LEAD-JUDGMENT-2026-10-05.md` §§1–4. Its U1 named lexical classes were subsequently exercised in still-unwired tests; `GATE2-R1-D6-U1-LEXICAL-UNDER-SKIP-TESTS-VERIFICATION-2026-10-05.md` records 24/24 focused, 224/224 whole-file and Ruff PASS. A finite corpus does not prove absolute absence of a false binding.
- U2 source/probe: `GATE2-R1-D6-U2-PRECEDENCE-INSPECTION-2026-10-05.md` records CTE-before-owned prefix precedence in the helper: a future false `bil_invoices` CTE binding could mask a cross-domain ownership denial. The live call currently supplies no bindings.
- Before any live state-3 wiring, a **fresh narrow named `veyro-lead`/Opus U1/U2 redecision** must weigh the now-recorded evidence and explicitly authorize a bounded next step. This note supplies no such authorization. Round-2 combined independent code review remains dependent on all blocking implementation and test items, and no scenario can be promoted from this note.
