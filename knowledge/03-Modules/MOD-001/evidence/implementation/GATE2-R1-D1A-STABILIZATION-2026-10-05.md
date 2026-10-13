---
doc: GATE2-R1-D1A-STABILIZATION
status: INTERRUPTED STABILIZATION STEP — NOT a review round, NOT a remediation
  round, NOT a certification step. D1a is not complete after this step.
date: 2026-10-05
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 2 — module dependency / cross-domain
  SQL lint)
scope: Exactly two files edited — `tools/validate_architecture_gates.py` and
  `tools/tests/test_validate_architecture_gates.py`. No other source, manifest,
  workflow, or knowledge file touched. No git commit/push performed.
---

# Gate-2 round-1 D1a stabilization — checkpoint

## 1. Starting state (as handed off by the prior, timed-out attempt)

A prior D1a attempt timed out after 1200s mid-edit, leaving the two files above
in a partially-edited state:

- ADR-011 constants and `ModuleEntry.external_table_references` had already
  been added (`_PREFIX_FLOOR_RE`, `_RESERVED_MANIFEST_VALUES`,
  `_RESERVED_SCHEMA_NAMES`, `_EXTERNAL_REF_RE`, `_MODULE_ENTRY_OPTIONAL`
  including `"external_table_references"`, `_RESERVED_MODULE_NAMES`,
  `ROOT_IMPORTER`, and a `_TRIGGER_VERBS`/`_TABLE_POSITION_KEYWORDS`/
  `_BARE_VERB_FORMS`/`ATTR_*` block — the last four are ADR-011 D6 SQL-lexer
  scaffolding, confirmed unused anywhere in the file and left untouched by
  this session; see §4).
- `_SQL_DML_RE` had been **removed** before its consumer `_is_sql_ish` was
  updated to stop referencing it.
- Focused pytest: **69 passed / 21 failed**, first failure a `NameError` at
  approximately line 1627 (`_SQL_DML_RE` undefined inside `_is_sql_ish`).
- `python -m py_compile tools/validate_architecture_gates.py`: **PASS**
  (the name error is a runtime `NameError`, not a syntax error, so compilation
  alone did not catch it).
- No D1a report had been written, no verdict issued.

This session independently re-ran both checks before touching anything and
confirmed the handoff's numbers exactly: **69 passed / 21 failed**, first
failure `NameError: name '_SQL_DML_RE' is not defined` at
`tools/validate_architecture_gates.py:1627`, `py_compile` PASS.

**One correction to the handoff's own framing, stated rather than silently
absorbed:** grepping the file before editing showed the gap was wider than
"`_SQL_DML_RE` was removed" — `_SQL_CLAUSE_RE`, `_TABLE_KEYWORD_RE`, and
`_TABLE_IDENT_RE` (all three consumed by `_is_sql_ish`/`_dangling_keywords`/
`_scan_sql_text`) had **no definition anywhere in the file either**. Both
files are entirely untracked (new, never committed — confirmed via
`git status`/`git diff HEAD`, which showed no diff because there is no prior
committed version to diff against), so there was no git history to recover
the missing definitions from; they were restored from the 90 pre-existing
tests' own specification of the required behavior (see §2).

## 2. Step 1 — repair the undefined SQL trigger

Restored a minimal, non-redesigned SQL-ish classifier immediately above
`_is_sql_ish`/`_dangling_keywords` in `tools/validate_architecture_gates.py`:

- `_SQL_DML_RE` — `\b(?:SELECT|INSERT|UPDATE|DELETE)\b` (case-insensitive).
- `_TABLE_KEYWORD_RE` — `\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\b` (case-insensitive;
  this is also `_SQL_CLAUSE_RE`, the same keyword set reused rather than a
  second, independently-evolving one, since every existing test only ever
  requires `FROM`/`UPDATE` to be present alongside a DML verb).
- `_TABLE_IDENT_RE` — the same keyword set followed by whitespace and a
  bare-or-schema-qualified identifier, captured in group 1, anchored so
  `.match(text, kw.start())` in `_dangling_keywords` can test "does an
  identifier immediately follow *this* keyword occurrence" rather than merely
  "does one exist somewhere in the string".

This is deliberately the old, simple, pre-lexer trigger — not the ADR-011 D6
broad-verb-trigger SQL lexer (`_TRIGGER_VERBS`/`_TABLE_POSITION_KEYWORDS`/
`_BARE_VERB_FORMS`/`ATTR_*`), which stays unwired and out of scope for this
step exactly as instructed.

**Verification (executed):**

```
$ python -m py_compile tools/validate_architecture_gates.py && echo PY_COMPILE_OK
PY_COMPILE_OK
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
90 passed in 1.67s
```

**Step 1 result: 90 passed / 0 failed — green baseline restored exactly.**

## 3. Step 2 — ADR-011 D1/D2 manifest-schema checks only

Read ADR-011 (`knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md`)
D1, D2, and D3.4, and the qualified-lead corrections b3, b5, and e2 in
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-QUALIFIED-LEAD-DECISION-2026-10-05.md`.
Implemented exactly the four items named by this step's task, inside
`parse_module_manifest` only — no change to `_resolve_owner`, `_scan_sql_text`,
or any other identifier-attribution (D3/I-2) or scanning (D4/D5/I-3) code path:

1. **Module-name regex validation, plus reserved names `_root` and `_shared`
   (b5/c4).** The module key is now validated against `_MODULE_NAME_IDENT_RE`
   (`^[a-z_][a-z0-9_]*$`), and the reserved-name guard was widened from the
   prior single `if name == SHARED_PACKAGE` check to
   `if name in _RESERVED_MODULE_NAMES` (`{"_shared", "_root"}` — the constant
   already existed, unwired, from the prior session's partial edit).
2. **Prefix floor value and reserved prefix values (b3, D3.4).** Each
   `owned_table_prefixes` entry now fullmatches `_PREFIX_FLOOR_RE`
   (`^[a-z][a-z0-9_]+_$` — `+`, not `*`) instead of the generic
   `_MODULE_NAME_IDENT_RE`, and is additionally rejected if it is a member of
   `_RESERVED_MANIFEST_VALUES` (`pg_`, `pg_catalog`, `pg_temp`,
   `information_schema`) — checked *after* the floor, matching the ADR's own
   framing that `pg_` satisfies the floor and must still be caught.
3. **Optional fields with their defaults.** `default_schema` (top-level,
   default `"public"`) is now accepted by widening the top-level key check
   from an exact-set equality (`set(raw) != {"version", "modules"}`) to
   `_TOP_LEVEL_ALLOWED`/`_TOP_LEVEL_REQUIRED`, and schema-validated as a
   lowercase identifier. `external_table_references` (per-module, default
   `[]`) is now actually read from the manifest (previously the key was
   merely *tolerated* by the unsupported-key check but its value was never
   parsed or stored — `ModuleEntry.external_table_references` always came out
   `()` regardless of manifest content), validated against `_EXTERNAL_REF_RE`
   (concrete 1- or 2-part identifier, no wildcard), and threaded into the
   `ModuleEntry` constructor call.
4. **Duplicate/overlap detection preserved exactly as currently specified.**
   The nested-same-module-accepted / cross-module-overlap-rejected loop at
   the bottom of `parse_module_manifest`, and the per-module duplicate-prefix
   and duplicate-domain/duplicate-schema checks, are byte-identical to the
   pre-stabilization version — only the *input* to the prefix duplicate check
   changed shape (floor-validated first now), never the duplicate/overlap
   logic itself.

Added 16 new focused tests to `tools/tests/test_validate_architecture_gates.py`,
calling `parse_module_manifest` directly (no file-tree gate run needed for pure
schema validation — matches the house style of calling the pure function
directly where the existing RLS-gate tests already do this), covering a
positive and negative case for each of the four items above:
`test_d2_module_name_invalid_identifier_is_error`,
`test_d2_module_name_valid_identifier_passes`,
`test_d4_module_named_shared_or_root_is_reserved_error`,
`test_d2_prefix_floor_rejects_single_char_before_underscore`,
`test_d2_prefix_floor_accepts_two_chars_before_underscore`,
`test_d34_reserved_prefix_value_pg_is_rejected`,
`test_d2_external_table_references_defaults_to_empty_tuple`,
`test_d2_external_table_references_valid_entries_are_stored`,
`test_d2_external_table_references_wildcard_entry_is_error`,
`test_d2_default_schema_omitted_defaults_without_error`,
`test_d2_default_schema_valid_identifier_passes`,
`test_d2_default_schema_invalid_identifier_is_error`,
`test_d1_unknown_top_level_key_still_rejected_alongside_default_schema`,
`test_d2_duplicate_overlap_detection_unchanged_same_module_nested_accepted`,
`test_d2_duplicate_overlap_detection_unchanged_cross_module_overlap_rejected`,
`test_d2_duplicate_prefix_entry_within_module_still_rejected`.

**Verification (executed):**

```
$ python -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
  (no output — compiled clean)
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
106 passed in 1.75s
$ backend/.venv/bin/python tools/tests/test_validate_architecture_gates.py   # the file's own
                                                                              # standalone, non-pytest runner
PASS — all 106 tests passed.
$ backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
All checks passed!
$ backend/.venv/bin/python -m mypy tools/validate_architecture_gates.py
Success: no issues found in 1 source file
```

**Step 2 result: 106 passed / 0 failed (90 pre-existing + 16 new), both
collection paths (pytest and the file's own manual runner) agree, ruff and
mypy clean.**

**One observed interaction, disclosed rather than silently left implicit:**
the pre-existing `test_rule7_prefix_that_is_a_prefix_of_another_is_error`
uses `owned_table_prefixes: ["mem"]` (no trailing underscore) for one module
in an overlap scenario. Under the now-restored prefix floor, `"mem"` is
rejected by the *floor* check before the overlap-detection loop ever runs.
The test still passes — it only asserts `ERROR` status and
`MODULE_DEPS_GATE_INPUT_INVALID`, not which specific check fired — but it no
longer exercises the overlap-detection code path it was originally written
to exercise. This is a side effect of restoring b3's correction, not a new
defect introduced here, and it is squarely the e4 "C-1 rows inherited from
round 1's fixture must be re-expressed under the corrected floor" item the
qualified-lead decision already named. Editing that pre-existing test was out
of this step's two-file scope (`tools/tests/test_validate_architecture_gates.py`
*is* one of the two in-scope files, but re-expressing an inherited round-1
corpus row is e4's job, not this stabilization step's four-item list) — left
untouched and flagged here instead of silently fixed or silently ignored.

## 4. Deferred to a later bounded D1a (or D1b) step — explicit, not guessed

Each item below was identified as in-scope-adjacent but was **not**
implemented, because it is not one of the four named items and/or its
semantics are genuinely ambiguous against the bounded task:

- **`owned_schemas` reserved-value check** (D2's table row: "reserved values
  ERROR (D3.4)" for `owned_schemas`, mirroring the prefix check). The
  `_RESERVED_SCHEMA_NAMES` constant already exists, unwired, from the prior
  session. Not implemented because the task's four-item list names only
  "prefix floor value and reserved prefix values", not schema reserved
  values — treated as a distinct, not-yet-authorized item rather than
  assumed-included.
- **`default_schema` disjoint from any module's `owned_schemas`** (D2's table
  row for `default_schema`, itself cross-referenced to D3.3). `default_schema`
  is now accepted, defaulted, and format-validated, but this disjointness
  check is not implemented — D3.3 is identifier-*resolution* precedence
  (I-2), and the task explicitly excludes I-2. Whether the disjointness
  constraint itself is "D2 schema" or "D3 attribution" is genuinely
  ambiguous from the table's own cross-reference; left unimplemented rather
  than guessed in either direction.
- **`external_table_references` D3.5 cross-check** ("an entry that resolves
  to any module's `owned_table_prefixes` or `owned_schemas` is ERROR"). Only
  the shape-level check (concrete identifier, no wildcard) was implemented.
  The ownership cross-check requires the same attribution machinery D3/I-2
  owns and is explicitly out of scope.
- **Everything in D3 (six-state identifier attribution), D4's `_root`
  scanning behavior beyond the manifest-level name reservation, D5 (coverage
  reconciliation), and D6 (the SQL lexer rework)** — all untouched, per the
  task's explicit "do not start" instruction. The D6 scaffolding constants
  added by the prior session (`_TRIGGER_VERBS`, `_TABLE_POSITION_KEYWORDS`,
  `_BARE_VERB_FORMS`, `ATTR_OWNED`/`ATTR_CTE`/`ATTR_SYSTEM`/`ATTR_EXTERNAL`/
  `ATTR_UNATTRIBUTED`) remain exactly as found: defined, present, and
  unreferenced anywhere else in the file. Confirmed by grep before and after
  this session's edits — this session added no reference to them and removed
  none of them.

## 5. What was NOT done (explicit, per the task's "no false completion" instruction)

- **D1a is not complete.** Only D1/D2 manifest-schema checks were implemented;
  D3 (identifier-attribution semantics), D4/D5 (reserved-importer scanning
  behavior and coverage reconciliation beyond manifest-level name
  reservation), and D6 (the SQL lexer) remain entirely unimplemented against
  this gate's actual scan/attribution logic. `_resolve_owner` and
  `_scan_sql_text` still implement the pre-ADR-011 "unowned ⇒ disclosed, not
  flagged" behavior, not D3.2's six-state table.
- **No SQL lexer rework.** `_is_sql_ish`/`_dangling_keywords`/`_TABLE_IDENT_RE`
  remain the simple pre-lexer regex trigger restored in Step 1, not ADR-011
  D6's broad-verb lexer.
- **No I-1 or I-2 checks.**
- **No CI changes of any kind.**
- **No real ownership manifest.** No `contracts/modules/ownership.json` was
  authored, implied, or made authorable — ADR-011's own scope limit ("binds
  NO real scaffold and NO domain logic") is unaffected by this step.
- **No domain bindings.**
- **No scenario PASS claim.** Nothing in `SCENARIOS.md`, `SCN-070`, or
  `DOM-002` was touched or claimed.
- **No git commit, push, or any git write operation.** `git status` confirms
  only the two in-scope files are untracked/modified; no other file in the
  working tree was touched by this session.

## 6. Final counts (for the orchestrator's report)

| Check | Result |
|---|---|
| Starting state | 69 passed / 21 failed, first `NameError` ~line 1627, `py_compile` PASS |
| Post-Step-1 | **90 passed / 0 failed** |
| Post-Step-2 (final) | **106 passed / 0 failed** (90 pre-existing + 16 new) |
| `ruff check` (both files) | All checks passed |
| `mypy` (`validate_architecture_gates.py`) | Success: no issues found |
| Files touched | `tools/validate_architecture_gates.py`, `tools/tests/test_validate_architecture_gates.py`, plus this checkpoint |
| Git commit/push | None performed |
