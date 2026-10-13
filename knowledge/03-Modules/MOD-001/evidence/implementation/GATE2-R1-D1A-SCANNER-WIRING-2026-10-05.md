---
doc: GATE2-R1-D1A-SCANNER-WIRING
status: BOUNDED INCREMENT — wires the existing `attribute_table_identifier`
  pure helper into the live `_scan_sql_text` path. NOT a review round, NOT a
  remediation round, NOT a certification step. D1a is still not complete after
  this increment (see LIMITATIONS). No scenario PASS claimed; P0 (R1-F01) is
  NOT claimed closed.
date: 2026-10-05
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 2 — module dependency / cross-domain
  SQL lint)
scope: Exactly two files edited — `tools/validate_architecture_gates.py` and
  `tools/tests/test_validate_architecture_gates.py` — plus this evidence note.
  No other source, manifest, workflow, or knowledge file touched. No git
  commit/push performed.
---

# Gate-2 round-1 D1a — scanner wiring (increment "D1a scanner wiring")

## 1. Starting state

`GATE2-R1-D1A-ATTRIBUTION-HELPER-2026-10-05.md` left
`tools/validate_architecture_gates.py` at **137 passed / 0 failed**, having
built `attribute_table_identifier` as a standalone, pure function implementing
ADR-011 D3's six-state identifier-attribution table, with 20 focused unit
tests calling it directly against hand-built `ModuleEntry` objects. That
report's own §4 explicitly disclosed that the helper was **NOT** wired into
`_scan_sql_text`/`_resolve_owner` — the live scan still implemented the
pre-ADR-011 "unowned ⇒ disclosed note, not flagged" behaviour.

This increment wires `attribute_table_identifier` into the live
`_scan_sql_text` path actually called from `run_module_deps_gate`, threads
`default_schema` from the manifest through to that call, and adds focused
fixture tests driving the gate end-to-end (via `run_module_deps_gate`, not
only direct calls to the pure helper) to lock in the wiring itself.

Re-verified the starting state before touching anything:

```
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
137 passed in 1.83s
```

## 2. What was wired, and where

### 2.1 `default_schema` now flows from the manifest to the attribution call

Before this increment, `parse_module_manifest` parsed and validated
`default_schema` (for the three manifest-level D3 invariants the prior
increment already enforced) and then **discarded** it — the function returned
only `dict[str, ModuleEntry]`. `run_module_deps_gate` had no way to obtain the
value at all.

- `parse_module_manifest` (`tools/validate_architecture_gates.py:1467`) now
  returns `tuple[dict[str, ModuleEntry], str]` — `(modules, default_schema)`.
- `load_module_manifest` (`:1651`) propagates the same tuple from
  `parse_module_manifest(_load_json(path), modules_root)` (`:1656`).
- `run_module_deps_gate` (`:2108`) now does
  `modules, default_schema = load_module_manifest(manifest_path, modules_root)`
  (`:2112`) and passes `default_schema` into every `_scan_sql_text` call
  (`:2137`, `:2168`).

This is an **additive return-shape change**, not a new concept: every call
site in the module and its test file was updated to unpack the tuple (11
non-production call sites in the test file, all `out = parse_module_manifest(...)`
→ `out, _default_schema = parse_module_manifest(...)`; two call sites with no
captured return value are unaffected). `main()`'s CLI dispatch
(`run_module_deps_gate(args.modules_dir, args.module_manifest)`, `:2252`) is
untouched — `run_module_deps_gate`'s own signature did not change.

### 2.2 `_scan_sql_text` now calls `attribute_table_identifier`, not `_resolve_owner`

`_scan_sql_text` (`tools/validate_architecture_gates.py:1992` pre-increment,
now rewritten in place) gained a `default_schema: str` parameter and a new
`unattributed: list[Violation]` output parameter (passed by reference, the
same calling convention `violations`/`uninspectable` already use). Its body
no longer calls `_resolve_owner`; it calls
`attribute_table_identifier(ident, modules, importer, default_schema)` for
every identifier `_TABLE_IDENT_RE` extracts, and dispatches on
`outcome.state`:

```python
for ident in (m.group(1) for m in _TABLE_IDENT_RE.finditer(text)):
    outcome = attribute_table_identifier(ident, modules, importer, default_schema)
    if outcome.state == ATTR_OWNED:
        if outcome.owner != importer:
            violations.append(Violation(
                "CROSS_DOMAIN_SQL_IMPORT", f"{importer} -> {outcome.owner}",
                f"{loc}: table {ident!r} owned by {outcome.owner!r}",
            ))
    elif outcome.state == ATTR_UNATTRIBUTED:
        unattributed.append(Violation(
            "MODULE_DEPS_TABLE_UNATTRIBUTED", loc,
            f"table {ident!r}: {outcome.reason}",
        ))
    # ATTR_CTE / ATTR_SYSTEM / ATTR_EXTERNAL (states 3/4/5): clean, no action.
```

`_resolve_owner` — the old, one-dimensional (prefix-OR-schema, never both)
owner lookup — had no remaining caller anywhere in the file or its tests
(confirmed by grep across both files and a repo-wide grep before deletion) and
was **removed**, not merely left unreferenced, so there are not two competing
owner-resolution mechanisms live in the file. `_unowned_note` and
`_UNOWNED_NOTE_LIMIT` (the "unowned ⇒ note" disclosure helper) were removed for
the same reason — "unowned" is no longer a note-worthy-but-benign category
once D3.2 state 6 is wired in as ERROR.

`run_module_deps_gate`'s final status logic (`:2174`) was extended from
`if uninspectable:` to `if uninspectable or unattributed:`, returning
`uninspectable + unattributed` as the combined violations list, status
`ERROR`. The two codes (`MODULE_DEPS_SOURCE_UNINSPECTABLE`,
`MODULE_DEPS_TABLE_UNATTRIBUTED`) are reported together but remain **distinct
codes** on each `Violation`, consistent with ADR-011 D7.1's "disjoint, and the
discriminator is stated" requirement. **Not implemented by this increment:**
D7.2's broader requirement that any already-collected FAIL `violations` also
be carried alongside an ERROR return — that discard behaviour predates this
increment and is unchanged; fixing it is out of this wiring-only scope and is
named explicitly in LIMITATIONS below, not silently left unstated.

### 2.3 The six terminal outcomes and how each is reached

| # | ADR-011 D3.2 state | Outcome | Reached via |
|---|---|---|---|
| 1 | Owned by the importing module | clean, no action | `attribute_table_identifier` → `ATTR_OWNED` with `outcome.owner == importer` |
| 2 | Owned by another module | `CROSS_DOMAIN_SQL_IMPORT` | `ATTR_OWNED` with `outcome.owner != importer` |
| 3 | CTE-defined name | clean, no action | `ATTR_CTE` — reachable from `attribute_table_identifier`'s own unit tests (prior increment) via a non-empty `cte_names`; **not yet reachable from this live path**, since `_scan_sql_text` always calls with the default empty `cte_names=frozenset()` — collecting real `WITH ...` names lexically is D6 (SQL lexer) work, explicitly out of this increment's scope. Disclosed, not silently claimed closed. |
| 4 | System/catalog table | clean, no action | `ATTR_SYSTEM` — `pg_catalog`/`pg_temp`/`information_schema` schema match, or a `pg_`-prefixed bare name/table part |
| 5 | Known external table | clean, no action | `ATTR_EXTERNAL` — exact match against the *importing* module's own declared `external_table_references` |
| 6 | Unattributed identifier | `MODULE_DEPS_TABLE_UNATTRIBUTED`, ERROR | `ATTR_UNATTRIBUTED` — the catch-all; appended to `unattributed`, never silently dropped |

No identifier can fall through `_scan_sql_text`'s loop without reaching one
of `ATTR_OWNED`, `ATTR_CTE`, `ATTR_SYSTEM`, `ATTR_EXTERNAL`, or
`ATTR_UNATTRIBUTED` — `attribute_table_identifier` itself is total over its
five-state `AttributionOutcome` return type (verified by the prior
increment's own purity/totality tests, unchanged by this increment).

### 2.4 Stale comments corrected

Several comments and docstrings across both files still said the helper was
"deliberately NOT wired into `_scan_sql_text`/`_resolve_owner`" (true when the
prior increment wrote them, false now). These were corrected in place —
`attribute_table_identifier`'s own docstring, `AttributionOutcome`'s
docstring, the module-level comment block introducing the D3 section, and two
comments in the test file — rather than left stale. `run_module_deps_gate`'s
own report `notes` also carried a literal, now-false line, **"input contract
not yet fixed by an ADR, unlike gates 1 (RLS) and 4 (permission)"** — ADR-011
fixed gate 2's input contract days before this increment, so that line was
corrected to name ADR-011 and explicitly list D4/D5/D6 as the parts still
unimplemented, rather than leave a known-false claim inside a report this very
increment is making more decisive.

## 3. Tests added

8 new focused tests added to `tools/tests/test_validate_architecture_gates.py`,
all driving the gate **end-to-end** through `run_module_deps_gate`/`_md_run`
(not direct `attribute_table_identifier` calls — that pure-function coverage
already exists from the prior increment) to lock in the wiring itself:

| Test | Covers |
|---|---|
| `test_wiring_schema_qualified_other_module_table_is_cross_domain_import` | `public.bil_invoices` → `CROSS_DOMAIN_SQL_IMPORT` |
| `test_wiring_case_variation_resolves_identically_to_lower_case` | `Public.BIL_Invoices` (mixed/upper case) resolves identically to the lower-case form above |
| `test_wiring_known_external_table_is_clean_and_feasible` | A declared `external_table_references` entry → PASS, no violation |
| `test_wiring_own_module_table_is_clean_and_feasible` | A bare own-prefix table → PASS, no violation |
| `test_wiring_unknown_identifier_is_unattributed_error_live` | An identifier no module owns → `MODULE_DEPS_TABLE_UNATTRIBUTED`, ERROR |
| `test_wiring_no_regression_previously_clean_input_stays_clean` | Re-runs `test_scn006`'s own-schema-and-approved-interface fixture; still PASS after the `_scan_sql_text` rewrite |
| `test_wiring_default_schema_from_manifest_reaches_attribution_call` | A custom `default_schema: "sm"` manifest value strips an `sm.`-qualified identifier to bare resolution (PASS); the same qualifier against the *implicit* `"public"` default does **not** strip and is `MODULE_DEPS_TABLE_UNATTRIBUTED` instead — proves the thread is real, not merely present in the function signature |
| `test_wiring_quoted_identifier_disclosed_regex_gap_but_attribution_is_correct` | See §4 — documents, by live execution, that a quoted identifier in real SQL text is **not** extracted by the current regex (reaches `MODULE_DEPS_SOURCE_UNINSPECTABLE` before `attribute_table_identifier` is ever called), while confirming via a direct call with the manifest-derived `modules`/`default_schema` that attribution itself is correct once an identifier is extracted |

One pre-existing test,
`test_unowned_table_reference_is_disclosed_not_flagged`, asserted the
pre-ADR-011 behaviour this increment inverts (unowned ⇒ benign note, not
ERROR). It was **renamed and rewritten**, not deleted, to
`test_unowned_table_reference_is_now_an_unattributed_error_not_a_benign_note`,
asserting the new `MODULE_DEPS_TABLE_UNATTRIBUTED`/ERROR outcome — the rename
keeps the gate's pre-ADR-011 behaviour visible in version-control history
rather than silently erasing it.

**Verification (executed):**

```
$ python3 -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
  (no output — compiled clean)
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
145 passed in 1.75s
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k "wiring"
8 passed, 137 deselected in 0.04s
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k "not wiring and not test_attr"
117 passed, 28 deselected in 1.69s
$ backend/.venv/bin/python tools/tests/test_validate_architecture_gates.py   # the file's own
                                                                              # standalone, non-pytest runner
PASS — all 145 tests passed.
$ backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
All checks passed!
$ backend/.venv/bin/python -m mypy tools/validate_architecture_gates.py
Success: no issues found in 1 source file
```

(The first `ruff check` run surfaced 2 `ISC004` findings — two multi-line
`notes` list entries added by this increment were unparenthesized implicit
string concatenations. Both were wrapped in parentheses and the check re-run
clean; recorded here rather than silently fixed-and-omitted from the record.)

**Result: 145 passed / 0 failed (117 pre-existing manifest-check tests +
20 pre-existing attribution-helper unit tests, both unchanged, + 8 new
live-wiring tests), both collection paths (pytest and the file's own manual
runner) agree, Ruff and mypy clean, zero regressions.** The pre-existing 137
were independently re-confirmed unchanged by running them in isolation
(`-k "not wiring and not test_attr"` plus the already-passing `test_attr*`
set implicitly covered by the full 145-count run), not merely inferred from
the combined total.

## 4. The quoted-identifier gap — confirmed by execution, not assumed

Before writing the fixture test, the live regex's behaviour against a quoted
identifier was checked directly:

```python
_TABLE_IDENT_RE = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\b\s+"
    r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)",
    re.IGNORECASE,
)
_TABLE_IDENT_RE.match('SELECT id FROM "BIL_INVOICES"\n', 10)  # -> None
```

The identifier character class (`[A-Za-z_][A-Za-z0-9_]*`) does not include
`"`, so `FROM "BIL_INVOICES"` never matches at all. `_dangling_keywords`
therefore reports the `FROM` keyword as dangling, and `_scan_sql_text` returns
`MODULE_DEPS_SOURCE_UNINSPECTABLE` **before** `attribute_table_identifier` is
ever reached. `test_wiring_quoted_identifier_disclosed_regex_gap_but_attribution_is_correct`
confirms this live (the `report.codes() == {"MODULE_DEPS_SOURCE_UNINSPECTABLE"}`
assertion), and separately confirms, via a direct call to
`attribute_table_identifier` using the real `modules`/`default_schema` this
increment's own `load_module_manifest` wiring produces, that quoted-identifier
attribution itself is correct (case preserved, matches/doesn't-match
correctly) once an identifier is actually extracted.

This is a **regex-extraction** gap (ADR-011 D6, SQL lexer rework), not an
**attribution-logic** gap, and widening `_TABLE_IDENT_RE`/`_TABLE_KEYWORD_RE`
to admit quoted identifiers would be exactly the SQL-lexer rework this
increment's task boundary forbids touching. Disclosed here rather than
quietly worked around.

## 5. LIMITATIONS — explicit, per the task's "no false completion" instruction

- **P0 (R1-F01) is NOT claimed closed.** The SQL lexer's case-sensitivity/
  schema-stripping defect lived in `_resolve_owner`/`_TABLE_IDENT_RE`.
  `_resolve_owner` is now removed and replaced by `attribute_table_identifier`
  for the case/schema-stripping semantics (D3.1/D3.3 rule 2), which this
  increment's own tests confirm behave correctly for the cases exercised. But
  `_TABLE_IDENT_RE` itself — the **extraction** regex, as opposed to the
  **attribution** logic — is unchanged, untouched, and still cannot capture a
  quoted identifier at all (§4). Closing R1-F01 fully requires D6 (the SQL
  lexer rework); this increment narrows but does not close it, and that
  distinction is the reason this section exists.
- **No scenario is claimed PASS.** SCN-MOD001-006/-007/-095/-096 remain NOT
  EXECUTED and unpromoted; nothing in `SCENARIOS.md` was touched or claimed.
- **CTE-local attribution (state 3) is unreachable from this live path.**
  `_scan_sql_text` always calls `attribute_table_identifier` with the default
  empty `cte_names`. Collecting real `WITH ... AS (...)` names lexically at
  depth 0 is D6 (SQL lexer) work and is not implemented here. The dispatch
  branch for `ATTR_CTE` exists and is correct (proven by the prior increment's
  unit tests), but no live fixture can currently produce it.
- **D4's `_root` scanning behaviour, D5 (coverage reconciliation), and the
  rest of D6 (the SQL lexer rework generally)** remain entirely unimplemented,
  exactly as the three prior D1a reports already disclosed and unchanged by
  this increment.
- **No I-1 check** (the zero-table-statement backstop) was implemented or
  touched.
- **ADR-011 D7.2's "violations and uninspectable findings reported
  partitioned, never collapsed" is not fully implemented.** When `uninspectable`
  or `unattributed` is non-empty, `run_module_deps_gate` still returns only
  that combined list and discards any `violations` (FAIL-tier
  `CROSS_DOMAIN_SQL_IMPORT`/`REVERSE_EDGE_NOT_EVENT_DRIVEN`) already collected
  in the same run — this predates this increment and this increment's own
  addition of `unattributed` inherits the same discard behaviour rather than
  fixing it, since restructuring that return path is report-surface (D7/D8)
  work beyond "scanner wiring only." Flagged explicitly rather than silently
  carried forward.
- **D8's full report-surface counters (by-state table-reference counts, a
  declared-external-references-by-name list on every PASS, etc.) are not
  implemented.** This increment adds one disclosure line
  ("0 unattributed table identifier reference(s)...") on the clean path and
  relies on the `Violation` list on the ERROR path; it does not build the
  richer per-state counters D8 describes.
- **Quoted identifiers in live SQL text are not reachable by this increment's
  wiring** — confirmed by execution in §4, not merely asserted. The
  `attribute_table_identifier` quote-handling this increment wires in is
  correct and tested directly; it is unreachable from a real `.sql`/
  string-literal scan until D6 widens `_TABLE_IDENT_RE`.
- **No root `ruff.toml`, no CI wiring, no real ownership manifest, no domain
  mappings.** None authored, implied, or made authorable by this increment.
- **No independent review.** This is implementation work product only. A
  fresh independent review is the explicit next action before any
  promotion/certification claim.
- **No git commit, push, or any git write operation.** `git status` confirms
  the two in-scope tool files remain untracked (both were already untracked
  before this session, per the prior three D1a reports — there is no
  committed baseline for either); no other file in the working tree was
  touched by this session. `git rev-parse HEAD` unchanged at `e481b81`.

## 6. Final counts (for the orchestrator's report)

| Check | Result |
|---|---|
| Starting state (post-attribution-helper) | 137 passed / 0 failed |
| Post-scanner-wiring (final) | **145 passed / 0 failed** (117 manifest + 20 attribution-helper, both unchanged + 8 new live-wiring) |
| Pre-existing 137, re-run isolated | 117 passed (`not wiring and not test_attr`) + 20 `test_attr*` (unchanged, implicitly re-confirmed by the full-suite 145 count) |
| New 8, run isolated | 8 passed, 137 deselected |
| `ruff check` (both files) | All checks passed (after fixing 2 ISC004 findings this increment introduced and then corrected) |
| `mypy` (`validate_architecture_gates.py`) | Success: no issues found |
| Files touched | `tools/validate_architecture_gates.py`, `tools/tests/test_validate_architecture_gates.py`, plus this evidence note |
| Git commit/push | None performed; HEAD unchanged at `e481b81` |
| D1a overall status | **Still not complete** — D4 (`_root` scanning), D5 (coverage), D6 (SQL lexer: quoted-identifier extraction, CTE collection, I-1 backstop) remain unimplemented; R1-F01/P0 narrowed but NOT closed; D7.2/D8 report-surface requirements only partially implemented; no scenario PASS claimed; no independent review performed |
