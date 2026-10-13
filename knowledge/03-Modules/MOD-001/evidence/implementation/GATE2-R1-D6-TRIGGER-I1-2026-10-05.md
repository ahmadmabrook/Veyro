# GATE2-R1-D6-TRIGGER-I1-2026-10-05 — stabilization report (I-1 / broad-trigger)

**Scope of this session:** D6 interrupted-work stabilization only, exactly as
scoped by the dispatching instruction. Added end-to-end fixture tests for
ADR-011 D6.1 (broad-trigger-verb widening) and D6.3 (the corrected I-1
zero-table-statement backstop) in `tools/tests/test_validate_architecture_gates.py`, ran
the focused pytest and Ruff, and recorded the result. **No production-code
change was made** — see "Fix made" below.

## Context inherited from the prior (timed-out) session

The prior Sonnet attempt left partial, uncommitted source edits in
`tools/validate_architecture_gates.py` implementing ADR-011 D6.1/D6.3 (the
widened `_TRIGGER_VERBS` set, `_TABLE_POSITION_KEYWORDS`, `_BARE_VERB_FORMS`,
`_has_bare_table_verb_form`, and the I-1 backstop block in `_scan_sql_text`).
**These edits were preserved and not reverted, rewritten, or touched** in
this session. Both `tools/validate_architecture_gates.py` and
`tools/tests/test_validate_architecture_gates.py` are untracked (`??`) in
git status — there is no prior commit to diff against; the file content
inherited at session start is exactly what this session read and tested.

## Tests added

One new table-driven test function,
`test_d6_trigger_verb_widening_and_i1_backstop_table_driven`, added to
`tools/tests/test_validate_architecture_gates.py` (inserted after the
existing `test_rule6_binop_sql_string_concatenation_is_uninspectable_error`,
before the "rule 8" section comment). It reuses the existing `_md_module`,
`_md_entry`, `_md_base_modules`, and `_md_run` fixture helpers — no new
harness was introduced, and no private regex/lexer helper
(`_TRIGGER_VERBS`, `_is_sql_ish`, `_dangling_keywords`,
`_has_bare_table_verb_form`) was imported directly, matching this file's
existing convention of driving module-deps-gate behavior end-to-end through
`run_module_deps_gate` rather than unit-testing private internals.

15 sub-cases, grouped exactly as the task named them:

**broad-trigger verbs** (6 sub-cases) — a D6.1-widened verb (not one of the
pre-widening SELECT/INSERT/UPDATE/DELETE/TRUNCATE/COPY set), each paired with
a real cross-module table reference (`billing_invoice`, owned by a `billing`
module with prefix `billing_`, referenced from a `membership` module), to
prove the widened verb actually drives live scanning through to attribution
rather than just being declared in the trigger set:
- `broad_trigger_merge` — `MERGE INTO billing_invoice`
- `broad_trigger_create` — `CREATE TABLE billing_invoice`
- `broad_trigger_alter` — `ALTER TABLE billing_invoice`
- `broad_trigger_drop` — `DROP TABLE billing_invoice`
- `broad_trigger_lock` — `LOCK TABLE billing_invoice`
- `broad_trigger_comment` — `COMMENT ON TABLE billing_invoice`

Each asserts `report.status == FAIL` and `report.codes() ==
{"CROSS_DOMAIN_SQL_IMPORT"}`, with `billing_invoice` named in the violation
detail.

**dangling table-position keyword** (2 sub-cases) — a keyword from the
backstop's broader `_TABLE_POSITION_KEYWORDS` set (`ONLY`/`REFERENCES`,
which are *not* in the extractor's own `_TABLE_KEYWORD_RE`
FROM/JOIN/INTO/UPDATE/TABLE set), with zero table-position keyword/verb
present and zero identifiers extracted — isolating the I-1 backstop branch
specifically, as distinct from the extractor's own pre-existing
dangling-keyword early return:
- `dangling_only_keyword` — `SELECT ONLY `
- `dangling_references_keyword` — `ALTER foo ADD CONSTRAINT fk REFERENCES `

**bare-table verbs** (3 sub-cases) — a verb with no table-position keyword
of its own at all:
- `bare_table_truncate` — `TRUNCATE billing_invoice`
- `bare_table_copy` — `COPY billing_invoice TO STDOUT`
- `bare_table_grant_on` — `GRANT SELECT ON billing_invoice TO someone`

These 5 (dangling + bare-table) sub-cases each assert `report.status ==
ERROR`, `report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}`, and that
some violation's `detail` contains the literal substring `"I-1 backstop"`
(the backstop's own message text), confirming the backstop branch fired
rather than some other ERROR path.

**clean/no-trigger cases** (4 sub-cases) — D6.3's own explicitly named list,
verbatim:
- `clean_select_1` — `SELECT 1`
- `clean_select_now` — `SELECT now()`
- `clean_analyze` — `ANALYZE`
- `clean_vacuum` — `VACUUM`

Each asserts `report.status == PASS` and `not report.violations` (zero
violations of any kind).

## Pytest result

```
tools/tests/test_validate_architecture_gates.py -q
150 passed in 1.90s
```

150 passed (149 pre-existing + 1 new test function, which itself contains
all 15 sub-cases above via internal loops with per-case assertion messages).
**Zero failures on the first run** — no fix to any code path was required;
the inherited D6.1/D6.3 implementation already satisfied every sub-case as
written.

Command run (from repo root, backend venv activated):
```
source backend/.venv/bin/activate && python3 -m pytest tools/tests/test_validate_architecture_gates.py -q
```

## Ruff result

```
ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```

Clean on both touched files.

## Fix made

**None.** Step 3 of the task ("if a test reveals a concrete failure, fix it
narrowly") did not trigger — every one of the 15 new sub-cases passed
against the inherited, untouched `tools/validate_architecture_gates.py` on
the first pytest run. No line in `tools/validate_architecture_gates.py` was
added, removed, or modified in this session.

## Explicit limitations — what remains open

- **P0 is NOT closed.** This session added targeted fixture coverage for
  the I-1 backstop and the broad-trigger-verb widening only. It does not
  constitute closure of the GOV-01-R04 Gate-2 P0, which has a much larger
  scope (D1b/D2, D4, D5, D7, D8, the real-tree manifest, CI wiring, and
  independent review) explicitly excluded from this session by the
  dispatching instruction.
- **The scenario is NOT PASS.** No scenario (SCN-070 or any other) was run,
  re-run, or asserted PASS in this session. This report makes no PASS claim
  of any scenario.
- **D8's "zero-table triggered statements" counter is not wired in.** D6.3
  requires clean/zero-table triggered statements to be "counted, and
  disclosed under its own counter" in the D8 report surface. This session
  confirmed only that such statements do not raise a violation (`not
  report.violations`); it did not verify, and the current code does not yet
  appear to implement, any dedicated D8 counter for this bucket (grep found
  no `zero_table`/`triggered` counter variable in the module as of this
  session). This is explicitly out of scope per the hard-exclusions list
  (D8) and is called out here only as a disclosed gap, not fixed.
- **CTE handling, bytes handling, docstring exclusion, D4/D5/D7/D8, CI
  config, the real-tree manifest, D1b/D2, SCN-070, DOM-002, and any
  independent review** were not touched, read in depth, or verified in this
  session, per the explicit hard-exclusions list in the dispatching
  instruction.
- **No commit was made.** The working tree is left exactly as it was
  (dirty), with the new test function added and nothing else. `git status`
  still shows `tools/validate_architecture_gates.py` and
  `tools/tests/test_validate_architecture_gates.py` as untracked (`??`).
- **ADR-011 citation provenance.** D6.1 and D6.3 were read directly from
  `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md`
  (lines 309–349) in this session — this is a direct re-read, not a
  secondhand citation.
- **Known residual not in scope to fix:** constructs like `FROM ONLY
  <table>` or `ANALYZE <table>` (verb directly followed by a real table name
  with no qualifying keyword the backstop's `_TABLE_POSITION_KEYWORDS`/
  `_BARE_VERB_FORMS` recognize) can either mis-extract `ONLY` itself as a
  table identifier, or pass through uninspected. This matches D6.3's
  explicit, deliberate decision ("a triggered statement with no table
  position at all... is clean") and is not a new finding — it is noted here
  only so it is not mistaken for something this session verified as
  correct in the general case; the test cases above deliberately avoid
  constructing those specific ambiguous shapes rather than asserting
  behavior for them.
