# GATE2-R1-D6-CTE-HELPER-2026-10-05 — pure lexical CTE-name collection helper

**Scope of this session:** bounded sub-step D6, exactly as dispatched — add
ONE pure lexical CTE-name collection helper, `_collect_cte_names`, to
`tools/validate_architecture_gates.py`, plus its direct unit tests. Nothing
else. Routing (Sonnet/routine implementation, gate 2 — not an Opus-reserved
slice per ADR-005 lines 111-126) was settled by the dispatching instruction
and not re-litigated here.

## Baseline verification (before this session's change)

```
source backend/.venv/bin/activate && python3 -m pytest tools/tests/test_validate_architecture_gates.py -q
150 passed in 1.80s
```

```
ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```

Both match the dispatch's claimed baseline (150/150, Ruff clean) exactly —
no discrepancy to report.

## What was implemented

Added to `tools/validate_architecture_gates.py`, immediately after
`_scan_sql_text` (which already disclosed, unchanged, that "`cte_names` is
always the empty default here ... this state is reachable from
`attribute_table_identifier`'s own unit tests but not yet from this live
scanning path"):

- `_collect_cte_names(text: str) -> frozenset[str]` — the one pure function
  this step was scoped to add. It implements exactly ADR-011 D3.2 state 3's
  text: **"Bound locally in the same statement (a `WITH` CTE name, collected
  lexically at depth 0)."**
- Three small private supporting helpers it needs, matching the existing
  codebase convention (`attribute_table_identifier` itself is similarly
  supported by `_attribute_bare_identifier`/`_owner_by_prefix`/
  `_owner_by_schema`/`_is_declared_external`, all added together under one
  prior increment):
  - `_skip_balanced_parens(text, pos) -> int | None` — skips one parenthesised
    span (respecting nested parens and double-quoted segments via the
    existing `_lex_quoted_segment`), or `None` if unbalanced.
  - `_parse_one_cte_binding(text, pos) -> tuple[str, int] | None` — lexes one
    `name AS (` binding at an exact position, or `None` if that shape does
    not confirm.
  - `_parse_cte_binding_list(text, pos) -> tuple[frozenset[str], int]` —
    parses a comma-separated list of such bindings for as long as each one
    confirms.
  - Three small new regexes scoped to this helper only: `_CTE_WITH_RE`,
    `_CTE_AS_RE`, `_CTE_WS_RE`.

**Reuse, not reinvention:** identifier lexing reuses the existing
`_lex_identifier_segment`/`_lex_quoted_segment` (the D1a quoted lexer), and
case/quote normalisation reuses the existing `_normalize_identifier_segment`
verbatim — no second normalisation rule was invented, per the task's
explicit instruction.

**Algorithm, in one paragraph:** a single left-to-right scan over `text`
tracks parenthesis depth, skipping double-quoted segments (via
`_lex_quoted_segment`) so a quote or paren character inside a quoted
identifier never corrupts depth. A `\bWITH\b` match is only ever inspected as
a binding-list opener when depth is exactly 0 at that position — a `WITH`
nested inside any parenthesised subquery or CTE body is at depth ≥ 1 and is
never inspected at all. When a depth-0 `WITH` is found, `_parse_cte_binding_list`
confirms and consumes a comma-separated run of `name AS (...)` bindings,
collecting each confirmed name and skipping its body via
`_skip_balanced_parens`; it stops the moment a binding fails to confirm,
keeping everything already collected up to that point.

**Fails closed on ambiguity, by construction:** if the token immediately
after `WITH` is not a lexable identifier, or no `AS` follows it, or no `(`
follows that, `_parse_one_cte_binding` returns `None` and nothing is bound
for that position — scanning simply resumes past the `WITH` keyword as
ordinary text. An unbalanced body (`_skip_balanced_parens` returns `None`)
has the same effect. No code path in this helper guesses a binding; every
collected name was independently, lexically confirmed as `name AS (`.

## Tests added

Nine new test functions in `tools/tests/test_validate_architecture_gates.py`,
inserted in a new section directly above `test_module_deps_cli_exit_codes_and_no_skip_flag`
(after the pre-existing `attribute_table_identifier` pure-function test
section, matching that section's own style of calling the pure function
directly rather than through a fixture tree):

1. `test_cte_multiple_bindings_in_one_with_list_are_both_collected` —
   **requirement 1.** `WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a, b"`
   → `{"a", "b"}`.
2. `test_cte_nested_subquery_identifiers_inside_the_body_are_not_collected` —
   **requirement 2.** `WITH recent_orders AS (SELECT * FROM orders ...) ...`
   → only `{"recent_orders"}`; asserts `"orders" not in` the result.
3. `test_cte_quoted_name_preserves_case_per_existing_normalisation_rule` —
   **requirement 3.** `WITH "Recent_Orders" AS (SELECT 1) ...` → `{"Recent_Orders"}`
   (case preserved, quotes stripped, via the existing D3.1 rule).
4. `test_cte_unrelated_with_clause_produces_no_binding` — **requirement 4.**
   `CREATE TABLE foo (id int) WITH (fillfactor = 70)` (a storage-parameter
   `WITH`, not a CTE list — no `name AS (` shape at all) → `frozenset()`.
5. `test_cte_adversarial_nested_with_at_depth_one_is_not_a_false_depth_zero_binding`
   — **requirement 5.** `SELECT * FROM (WITH inner_cte AS (SELECT 1) SELECT * FROM inner_cte) AS sub`
   — a naive, depth-blind scanner would textually match `WITH inner_cte AS (`
   and bind `inner_cte`; because it is actually nested one level inside the
   outer `FROM (...)` subquery, the correct result is `frozenset()`. This is
   the adversarial false-binding case the task required.
6. `test_cte_no_with_keyword_at_all_collects_nothing` — plain SQL with no
   `WITH` token at all.
7. `test_cte_empty_text_collects_nothing` — the empty string.
8. `test_cte_unbalanced_body_paren_fails_closed_to_no_binding` — `WITH a AS
   (SELECT * FROM billing_invoice` (no closing paren) → `frozenset()`,
   confirming the unbalanced-body fail-closed path.
9. `test_cte_is_pure_and_does_not_mutate_or_depend_on_call_order` — same input
   called twice yields equal results, and the input string is unchanged
   afterward (strings are immutable in Python, so this is a sanity check on
   the call contract, not a mutation risk the function could actually have —
   disclosed as such, not oversold as a meaningful mutation test).

All nine assert on `_collect_cte_names`'s return value directly; none drive
it through `run_module_deps_gate` or any fixture tree, since the helper is
not wired into that path.

## Test and Ruff results

**Before this session's change** (baseline, repeated from above for
side-by-side comparison):
```
150 passed in 1.80s
ruff check ...: All checks passed!
```

**After this session's change:**
```
source backend/.venv/bin/activate && python3 -m pytest tools/tests/test_validate_architecture_gates.py -q
159 passed in 1.92s
```
159 = 150 baseline + 9 new test functions, zero regressions, zero failures.

```
ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```
Clean on both touched files, no new findings.

## Hard exclusions honoured

- `_collect_cte_names` is **not** called from `_scan_sql_text`, `attribute_table_identifier`,
  or any other caller. Confirmed by `grep -n "_collect_cte_names\|_parse_cte_binding_list\|
  _parse_one_cte_binding\|_skip_balanced_parens\|_CTE_WITH_RE\|_CTE_AS_RE\|_CTE_WS_RE"
  tools/validate_architecture_gates.py` — every match is inside the new
  helper's own definitions/docstrings, none in `_scan_sql_text` or any other
  pre-existing function. The helper lands unused this step, by design.
- `_scan_sql_text` itself, the D6 trigger/I-1 work
  (`GATE2-R1-D6-TRIGGER-I1-2026-10-05.md` and the code it covers), byte
  counts/pins, existing docstrings, and D4/D5/D7/D8 were not touched. The new
  code was inserted as a new block between `_scan_sql_text`'s closing line
  and `_is_dynamic_import_call`'s definition — no existing line was edited,
  moved, or removed.
- No CI config, real-tree manifest, D1b/D2, SCN-MOD001-070, DOM-002, or
  review artifact was read or touched.
- Nothing was committed, pushed, staged, stashed, or reset.
  `git status --porcelain tools/` still shows both touched files as
  untracked (`??`), exactly as before this session (no prior commit exists
  for either to diff against), and the pre-existing unrelated modified files
  (`tools/tests/test_validate_migration_ordering.py`,
  `tools/validate_capability_manifest.py`, `tools/validate_migration_ordering.py`)
  are untouched by this session.
- No P0/scenario was closed or marked PASS, nothing was promoted, no
  `REVIEW_IN_FLIGHT.md` claim was written or cleared, no self-review or
  self-approval occurred.

## Limitations — stated honestly and specifically

- **Not wired in.** `_collect_cte_names` is never called from
  `_scan_sql_text` or `attribute_table_identifier`'s live call site. The live
  scanning path's behavior is completely unchanged by this session —
  `cte_names` still always defaults to the empty frozenset in the live path,
  exactly as before. Wiring this in (replacing the empty default with a real
  `_collect_cte_names(text)` call per statement/file, and deciding the exact
  scope of "the same statement" the live scanner should pass) is explicitly
  separate, future work, not attempted here.
- **Deliberately declined ambiguous shapes** (each fails closed to "no name
  collected for that binding," not to a guess):
  - `RECURSIVE` — `WITH RECURSIVE cte AS (...)` is not recognised. The
    `RECURSIVE` token is lexed as a candidate CTE name by
    `_parse_one_cte_binding`, then fails to find `AS` immediately after it
    (the real name follows instead), so the *entire* binding list for that
    `WITH` fails to confirm even its first entry — a recursive CTE's name(s)
    are not collected at all by this helper as written. This is a real,
    non-trivial gap: any genuinely recursive CTE in the codebase would
    currently degrade (if this helper were wired in) to the identifier never
    reaching `ATTR_CTE`, which is the disclosed safe direction (state 6
    ERROR) but is a gap worth a future increment closing explicitly, not
    silently.
  - A parenthesised column-name list after the CTE name (`WITH cte(a, b) AS
    (...)`) is not recognised — `_parse_one_cte_binding` expects `AS`
    immediately (modulo whitespace) after the name; a `(` there instead
    fails the binding closed.
  - `[NOT] MATERIALIZED` between `AS` and the opening `(` is not recognised
    — `_parse_one_cte_binding` requires `(` immediately (modulo whitespace)
    after `AS`; `MATERIALIZED` or `NOT MATERIALIZED` there instead fails the
    binding closed.
  - None of these three shapes were covered by a dedicated test in this
    session — they are documented as known gaps in the function's own
    docstring and here, not asserted against, since the task's five required
    test cases do not call for them and adding untested claims about their
    exact behavior would overclaim. A reader should treat "RECURSIVE /
    column-list / MATERIALIZED CTEs are not collected" as a disclosed,
    verified-by-code-reading gap, not a behavior pinned down by a passing
    test.
- **No string-literal lexer.** A single-quoted SQL string literal containing
  a `(`, a `)`, or the literal text `WITH` is not distinguished from real
  syntax by this helper, because no part of `tools/validate_architecture_gates.py`
  has a single-quote string-literal lexer anywhere, not only in this new
  code. This is an inherited, pre-existing lexical-approximation limitation
  (the same one `_is_sql_ish`/`_extract_table_identifiers` already carry),
  not a new gap this helper introduces — but it does mean a pathological
  string literal could in principle corrupt this helper's depth tracking or
  trigger a spurious `WITH` inspection. No test in this session exercises
  that shape.
- **Depth-underflow clamping is a judgment call, not a proven-safe one.**
  `_collect_cte_names` clamps depth at a floor of 0 (`depth = max(0, depth -
  1)`) rather than letting it go negative on an excess closing paren. This
  is a reasonable conservative choice for malformed/unbalanced text, but its
  exact interaction with a later genuinely-nested `WITH` in the same
  pathologically unbalanced text was not tested — no test in this session
  constructs that specific shape.
- **`_parse_one_cte_binding`'s `None` return on a dangling match is not
  separately unit-tested in isolation** — it is only exercised indirectly
  through `_collect_cte_names`'s own tests (requirement 4's "unrelated
  WITH" case, and the unbalanced-body case). No test calls
  `_parse_one_cte_binding` or `_parse_cte_binding_list` directly; they are
  private, and the task scoped testing to the one public helper,
  `_collect_cte_names`.
- **No mutation-testing pass was run** against this new code in this
  session (the task did not ask for one at this sub-step, unlike some
  sibling increments' remediation sessions that did run mutants). The nine
  tests above were individually traced by hand against the algorithm during
  development, and all pass, but no live mutant-kill drill was performed to
  independently confirm test sensitivity the way some other MOD-001 evidence
  records do.

## What was deliberately not done

- No wiring into `_scan_sql_text` (hard exclusion, honoured).
- No change to `attribute_table_identifier`'s live call site or its
  default-empty `cte_names` behavior.
- No attempt to make `_collect_cte_names` handle every SQL dialect
  construct involving the word `WITH` (e.g. `WITH TIES`, `WITH DATA`/`WITH
  NO DATA`, `WITH GRANT OPTION`, `WITH ORDINALITY`) individually — these are
  not specifically tested, though by construction (no `AS` follows the
  relevant token in any of them, in the realistic case) they are expected to
  fall into the same "unrelated WITH, no binding" path as the tested
  `CREATE TABLE ... WITH (fillfactor = 70)` case. This expectation was not
  independently verified by a test for each named construct.
- No commit, push, or git state change.
