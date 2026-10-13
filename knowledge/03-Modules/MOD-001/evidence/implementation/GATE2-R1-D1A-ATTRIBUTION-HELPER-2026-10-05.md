---
doc: GATE2-R1-D1A-ATTRIBUTION-HELPER
status: BOUNDED INCREMENT — a standalone, pure identifier-attribution helper
  only. NOT a review round, NOT a remediation round, NOT a certification
  step. D1a is still not complete after this increment (see LIMITATIONS).
date: 2026-10-05
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 2 — module dependency / cross-domain
  SQL lint)
scope: Exactly two files edited — `tools/validate_architecture_gates.py` and
  `tools/tests/test_validate_architecture_gates.py` — plus this evidence note.
  No other source, manifest, workflow, or knowledge file touched. No git
  commit/push performed.
---

# Gate-2 round-1 D1a — pure table-identifier attribution helper (increment "D1a")

## 1. Starting state

`GATE2-R1-D1A-MANIFEST-COMPLETION-2026-10-05.md` left
`tools/validate_architecture_gates.py` at **117 passed / 0 failed**, having
implemented ADR-011 D1/D2's manifest schema and three manifest-level D3
invariants (reserved `owned_schemas` values, `owned_schemas`/`default_schema`
disjointness, and the `external_table_references` D3.5 cross-check). That
report's own §5 explicitly disclosed that **D3's six-state identifier-
attribution table, as actually used during SQL scanning, remained entirely
unimplemented** — `_resolve_owner`/`_scan_sql_text` still implemented the
pre-ADR-011 "unowned ⇒ disclosed, not flagged" behaviour.

This increment implements exactly that six-state attribution logic as a new,
**standalone, pure function** — `attribute_table_identifier` — and adds
focused tests against it directly. Per this increment's explicit task
boundary, it does **not** wire that function into `_scan_sql_text` or
`_resolve_owner`, and does **not** touch the SQL lexer, `_root` scanning
behaviour, or coverage reconciliation. D1a is **not** complete after this
step; see §4.

Re-verified the starting state before touching anything:

```
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
117 passed in 1.74s
```

## 2. What was implemented

Added to `tools/validate_architecture_gates.py`, immediately after the
existing `_resolve_owner` function (which is untouched — neither read-edited
nor called by the new code):

- **`_split_identifier_segments(raw_identifier)`** — splits a possibly-quoted,
  dot-qualified identifier into raw parts via a single regex
  (`"[^"]*"|[^.]+`), treating a double-quoted run as one atomic segment so a
  dot inside quotes is never mistaken for a separator (the project's synthetic
  fixtures never need an embedded `""`-escaped quote, and this helper does not
  attempt to handle one — disclosed in its docstring).
- **`_normalize_identifier_segment(segment)`** — ADR-011 D3.1: a
  double-quoted segment preserves case exactly (quotes stripped); an unquoted
  segment is casefolded to lower case.
- **`_owner_by_prefix(table_part, modules)`** / **`_owner_by_schema(schema_part,
  modules)`** — two separate, single-purpose lookups (not a reuse of
  `_resolve_owner`, which only ever checks one dimension per identifier) so a
  conflict between the two dimensions can be detected rather than silently
  resolved by whichever check happens to run first.
- **`_is_declared_external(importer, modules, canonical)`** — true iff
  `canonical` is exactly one of the *importing* module's own declared
  `external_table_references` entries.
- **`AttributionOutcome`** (frozen dataclass: `state`, `owner: str | None`,
  `reason: str`) — the explicit structured outcome the task required instead
  of a bare bool. `state` is one of the five `ATTR_*` constants that already
  existed, unwired, in the file from a prior session's partial edit (D3.2's
  six terminal states collapse to five: states 1 and 2 both share
  `ATTR_OWNED`, with the caller — not this function — deciding own-vs-other by
  comparing `owner` to its own importer name, exactly as `_scan_sql_text`
  already does today with `_resolve_owner`'s return value).
- **`_attribute_bare_identifier(name, modules, importer, cte_names)`** — the
  shared resolution path for a genuinely bare (unqualified) identifier *and*
  for a 2-part identifier whose schema was stripped under D3.3 rule 2, so a
  bare name and a `default_schema`-qualified name resolve identically. Order:
  CTE-local → reserved `pg_`-prefixed system identifier → owned prefix →
  declared external → unattributed.
- **`attribute_table_identifier(raw_identifier, modules, importer,
  default_schema, cte_names=frozenset())`** — the public entry point. Pure:
  no I/O, no mutation of any argument, same five inputs always yield the same
  `AttributionOutcome` (locked by a dedicated test, §3). Dispatches on dotted
  part count (≥3 → unattributed/ERROR per D3.3 rule 1), normalises each
  segment per D3.1, then either delegates to the bare resolver (1-part, or
  2-part with schema == `default_schema`) or resolves the 2-part/non-default-
  schema case: reserved system schema or `pg_`-prefixed table part → system;
  otherwise compute both the schema-owner and the prefix-owner and ERROR on a
  conflict (D3.3 rule 4) before falling through to schema-governs → declared
  external → unattributed.

### Mapping to ADR-011 D3.1–D3.5 (as implemented)

| ADR-011 state / rule | Outcome | Implemented as |
|---|---|---|
| State 1/2 — owned by importing/another module | `ATTR_OWNED`, `owner` set | Caller compares `owner` to its own importer name |
| State 3 — CTE-local (bare only) | `ATTR_CTE` | `cte_names` membership check, bare resolution only |
| State 4 — reserved system identifier | `ATTR_SYSTEM` | `pg_catalog`/`pg_temp`/`information_schema` schema match, or any `pg_`-prefixed bare name/table part |
| State 5 — declared `external_table_references` | `ATTR_EXTERNAL` | Exact match against the *importing* module's own declared entries only (see LIMITATIONS §4 on scoping) |
| State 6 — anything else | `ATTR_UNATTRIBUTED` | The catch-all terminal ERROR state |
| D3.1 normalisation | — | `_normalize_identifier_segment` |
| D3.3 rule 1 (≥3 parts) | `ATTR_UNATTRIBUTED` | Checked before normalisation/dispatch |
| D3.3 rule 2 (default-schema stripping) | delegates to bare resolver | `schema_part == default_schema` branch |
| D3.3 rule 3 (`owned_schemas` disjoint from `default_schema`) | N/A here | Already enforced at manifest-parse time (prior increment); not re-checked by this pure function, which trusts its `modules` argument |
| D3.3 rule 4 (schema/prefix conflict) | `ATTR_UNATTRIBUTED` | Explicit conflict check before the schema-governs branch |

**One explicit interpretation decision, disclosed per the task's own
instruction** ("if ADR-011's exact wording of the six differs from the gloss
above, follow ADR-011 and say so"): ADR-011's D7 error taxonomy gives neither
D3.3 rule 1 (≥3 parts) nor rule 4 (schema/prefix conflict) a distinct outcome
code of its own — D3.2 state 6 is described as "anything else ⇒ ERROR", and
both conditions are indeed "anything else" relative to states 1–5. This
helper therefore represents both as `ATTR_UNATTRIBUTED`, distinguished only by
the `reason` string, rather than inventing an undocumented seventh state. This
is this implementer's reading of an ADR passage that does not spell out the
mapping explicitly; a future round-2 reviewer should treat it as a finding
against this increment (not against ADR-011) if that reading is wrong.

## 3. Tests added

20 new focused tests added to `tools/tests/test_validate_architecture_gates.py`,
table-driven where a single assertion shape repeats over several inputs,
calling `attribute_table_identifier` directly with hand-built `ModuleEntry`
objects (no manifest JSON, no file-tree gate run — matching this file's own
house style for pure-function tests):

| Test | Covers |
|---|---|
| `test_attr_bil_invoices_unquoted_variants_attribute_identically_p0` | P0: `public.bil_invoices` + 5 case/qualification variants, all unquoted, all → same owner |
| `test_attr_quoted_identifier_preserves_case_and_is_unattributed` | Quoted case preservation, bare |
| `test_attr_quoted_identifier_under_default_schema_still_preserves_case` | Quoted case preservation, schema-qualified + stripped |
| `test_attr_quoted_lowercase_identifier_matches_like_unquoted` | Quoting alone is not disqualifying |
| `test_attr_three_or_more_dotted_parts_is_unattributed_error` | 3-part and 4-part rejection |
| `test_attr_schema_owner_and_prefix_owner_conflict_is_unattributed_error` | Schema/prefix conflict |
| `test_attr_schema_owner_alone_resolves_clean_when_no_conflicting_prefix` | Conflict-test control (no false positive) |
| `test_attr_cte_local_name_is_attributed_as_cte` | CTE-local |
| `test_attr_cte_local_name_takes_precedence_over_owned_prefix` | CTE precedence over ownership |
| `test_attr_reserved_system_schema_pg_catalog_is_system` | Reserved schema |
| `test_attr_reserved_system_schema_information_schema_is_system` | Reserved schema (second value) |
| `test_attr_bare_pg_prefixed_identifier_is_system` | Reserved `pg_` prefix, bare |
| `test_attr_table_part_pg_prefix_under_nonreserved_schema_is_still_system` | Reserved `pg_` prefix, qualified |
| `test_attr_declared_external_reference_bare_is_clean` | Declared external, bare |
| `test_attr_declared_external_reference_schema_qualified_is_clean` | Declared external, qualified |
| `test_attr_external_reference_is_scoped_to_the_declaring_module_only` | External-ref scoping decision (disclosed) |
| `test_attr_unknown_identifier_is_unattributed_error` | Unknown/unattributed |
| `test_attr_cross_module_bare_identifier_is_owned_by_the_other_module` | ATTR_OWNED collapses states 1/2; caller decides own-vs-other |
| `test_attr_is_pure_deterministic_and_does_not_mutate_inputs` | Purity/determinism, no mutation |
| `test_attr_outcome_is_a_structured_dataclass_not_a_bare_bool` | Structured-outcome requirement |

**Verification (executed):**

```
$ python3 -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
  (no output — compiled clean)
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
137 passed in 1.83s
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k "not test_attr"
117 passed, 20 deselected in 1.73s
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k "test_attr"
20 passed, 117 deselected in 0.03s
$ backend/.venv/bin/python tools/tests/test_validate_architecture_gates.py   # the file's own
                                                                              # standalone, non-pytest runner
PASS — all 137 tests passed.
$ backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
All checks passed!
$ backend/.venv/bin/python -m mypy tools/validate_architecture_gates.py
Success: no issues found in 1 source file
```

**Result: 137 passed / 0 failed (117 pre-existing manifest-check tests,
unchanged, + 20 new attribution-helper tests), both collection paths (pytest
and the file's own manual runner) agree, Ruff and mypy clean, zero
regressions.** The pre-existing 117 manifest checks were independently
re-confirmed to still pass, unchanged, by running them in isolation
(`-k "not test_attr"`), not merely inferred from the combined total.

## 4. LIMITATIONS — explicit, per the task's "no false completion" instruction

- **The helper is NOT wired into `_scan_sql_text`.** `_scan_sql_text` and
  `_resolve_owner` are byte-for-byte untouched by this increment (confirmed by
  diffing this session's edits against the pre-increment file — the only
  changes to the file are the new, additive block inserted after
  `_resolve_owner` and before `_UNOWNED_NOTE_LIMIT`). `_scan_sql_text` still
  implements the pre-ADR-011 "unowned ⇒ disclosed, not flagged" behaviour via
  `_resolve_owner`, not the six-state table. The gate's actual scanning
  behaviour against real or fixture source is **unchanged** by this
  increment.
- **R1-F01 is NOT closed.** This increment is not claimed as a fix to
  round-1's P0 finding (the SQL lexer's case-sensitivity/schema-stripping
  defect), because the defect lives in `_resolve_owner`/`_TABLE_IDENT_RE`,
  neither of which this increment touches. The new pure function
  demonstrates the *corrected* semantics exist and are tested in isolation;
  it does not yet correct the gate's live behaviour.
- **No scenario is claimed PASS.** SCN-MOD001-006/-007/-095/-096 remain NOT
  EXECUTED and unpromoted; nothing in `SCENARIOS.md` was touched or claimed.
- **D4's `_root` scanning behaviour, D5 (coverage reconciliation), and D6
  (the SQL lexer rework)** remain entirely unimplemented, exactly as the two
  prior D1a reports already disclosed and unchanged by this increment.
- **No I-1 check** (the zero-table-statement backstop) was implemented or
  touched.
- **External-reference scoping is this implementer's reading, not an
  ADR-011-spelled-out rule.** ADR-011 D3.5 says a declared
  `external_table_references` entry is "clean, counted, disclosed by name"
  but does not explicitly say whether that disclosure is visible only to the
  declaring module or to every importer. This helper scopes state 5 strictly
  to the declaring module (an identifier declared external by module A is
  `ATTR_UNATTRIBUTED`, not `ATTR_EXTERNAL`, when the importer argument is
  module B) — the reading that keeps state 5 from becoming a second,
  wider-than-intended bypass. Disclosed as an interpretation, not asserted as
  ADR-011's own explicit text.
- **The ≥3-part-identifier and schema/prefix-conflict conditions are both
  represented as `ATTR_UNATTRIBUTED`**, per the interpretation disclosed in
  §2 above — not given distinct states, since ADR-011's D7 taxonomy does not
  name distinct codes for them.
- **No root `ruff.toml`, no CI wiring, no real ownership manifest, no domain
  mappings.** None authored, implied, or made authorable.
- **No independent review.** This is implementation work product only. A
  fresh independent review is the explicit next action before any
  promotion/certification claim — and per this increment's own hard
  constraints, that review is for a future round covering the *wired-in*
  behaviour, not this isolated helper alone.
- **No git commit, push, or any git write operation.** `git status` confirms
  only the two in-scope tool files are untracked (both were already untracked
  before this session, per the prior two D1a reports — there is no committed
  baseline for either); no other file in the working tree was touched by this
  session.

## 5. Final counts (for the orchestrator's report)

| Check | Result |
|---|---|
| Starting state (post-manifest-completion) | 117 passed / 0 failed |
| Post-attribution-helper (final) | **137 passed / 0 failed** (117 pre-existing + 20 new) |
| Pre-existing 117, re-run isolated | 117 passed, 20 deselected — unchanged |
| New 20, run isolated | 20 passed, 117 deselected |
| `ruff check` (both files) | All checks passed |
| `mypy` (`validate_architecture_gates.py`) | Success: no issues found |
| Files touched | `tools/validate_architecture_gates.py`, `tools/tests/test_validate_architecture_gates.py`, plus this evidence note |
| Git commit/push | None performed |
| D1a overall status | **Still not complete** — not wired into `_scan_sql_text`/`_resolve_owner`; D4 (`_root` scanning), D5 (coverage), D6 (SQL lexer), I-1 remain unimplemented; R1-F01 not closed; no scenario PASS claimed |
