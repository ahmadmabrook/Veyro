---
doc: GATE2-R1-D1A-QUOTED-LEXER
status: BOUNDED STABILIZATION STEP — NOT a review round, NOT a remediation
  round, NOT a certification step, NOT a scenario PASS. D1a/GOV-01-R04 is
  NOT complete after this step.
date: 2026-10-05
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 2 — module dependency / cross-domain
  SQL lint)
scope: One test file edited — `tools/tests/test_validate_architecture_gates.py`
  (one obsolete test rewritten/renamed, four new end-to-end fixture tests
  added). `tools/validate_architecture_gates.py` was inspected only, not changed
  by this stabilization. No other source, manifest, or workflow file touched.
  No git commit/push performed.
---

# Gate-2 round-1 D1a — quoted-identifier lexer (D6) stabilization

## 1. Scope executed

This session continued a prior Sonnet attempt at MOD-001 GOV-01-R04 D6 (the
quoted-identifier lexer) that timed out after 1200s without producing a
verdict. Per the task's explicit bound, the following and only the
following was done:

1. Inspected the already-landed partial lexer edits in
   `tools/validate_architecture_gates.py`
   (`_lex_quoted_segment`, `_lex_identifier_segment`, `_lex_dotted_identifier`,
   `_identifier_after_keyword`, `_extract_table_identifiers`,
   `_dangling_keywords`, `_split_identifier_segments`,
   `_normalize_identifier_segment`, and `attribute_table_identifier`'s
   3+-part-is-ERROR check) against ADR-011 D3.1 (normalisation/case
   semantics), D3.2 (six-state resolution), D3.3 (resolution precedence,
   including the 3+-part rule and the schema/prefix conflict rule), and D6
   (SQL trigger, zero-table-statement backstop, and the quoted-identifier
   lexer requirement specifically) — **sections D3.1, D3.2, D3.3, and D6
   only**, as the task bounded.
2. Updated the obsolete test
   `test_wiring_quoted_identifier_disclosed_regex_gap_but_attribution_is_correct`,
   which asserted the OLD pre-lexer regex-gap behavior (a live scan of a
   double-quoted identifier reaching `MODULE_DEPS_SOURCE_UNINSPECTABLE`
   before extraction). Renamed to
   `test_wiring_quoted_identifier_extracted_and_attributed_correctly` and
   rewritten to assert the CURRENT, governed behavior (the live scan now
   reaches a clean `PASS`), with a comment explaining what the test
   previously encoded and why it changed. The two direct
   `attribute_table_identifier` calls in the test (case-preserved
   uppercase → unattributed; lowercase quoted → owned by `membership`) were
   left unchanged — they were already correct before this increment.
3. Added four small end-to-end fixture tests, following the existing
   `_md_run`/`_md_module`/`_md_entry`/`_md_base_modules` conventions in the
   same file exactly, with no new harness invented:
   - `test_wiring_quoted_cross_domain_reference_is_cross_domain_import` —
     unquoted schema + quoted (lowercase) table segment, resolving into
     another module's owned prefix → `CROSS_DOMAIN_SQL_IMPORT`.
   - `test_wiring_quoted_unknown_identifier_is_unattributed_error` — a
     quoted, exact-case identifier no module owns →
     `MODULE_DEPS_TABLE_UNATTRIBUTED` (ERROR).
   - `test_wiring_three_part_qualified_name_is_unattributed_error` — a
     3-part dotted name (`some_db.public.bil_invoices`) →
     `MODULE_DEPS_TABLE_UNATTRIBUTED` (ERROR), proving the lexer captures
     the identifier in full rather than silently truncating to two parts.
   - `test_wiring_mixed_quoted_schema_unquoted_table_is_cross_domain_import` —
     the reverse mix (quoted schema segment matching `default_schema`,
     unquoted table segment) → `CROSS_DOMAIN_SQL_IMPORT`, proving
     default-schema stripping still applies when the schema segment itself
     arrives quoted.
4. Ran the focused pytest selection, Ruff, and mypy (exact commands and
   results in §3 below).

**No lexer source code was changed by this session.** Inspection against
ADR-011 D3.1–D3.3 and D6 did not surface a concrete bug in the
quote-extraction code path — see §4.

## 2. Files changed

| File | Change |
|---|---|
| `tools/validate_architecture_gates.py` | **No change.** Inspected only (see §4 — no concrete bug found). |
| `tools/tests/test_validate_architecture_gates.py` | One test renamed and rewritten (`test_wiring_quoted_identifier_disclosed_regex_gap_but_attribution_is_correct` → `test_wiring_quoted_identifier_extracted_and_attributed_correctly`); four new end-to-end fixture tests added (listed in §1 item 3). |

Both files remain untracked (`??`) in `git status`, consistent with the
prior session's partial work never having been committed; nothing was
reverted, stashed, or checked out.

## 3. Exact commands run and exact results

```
cd /Users/ahmadmabrouk/Desktop/Veyro
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -vv
```
Result: **149 passed** (the pre-existing 144 passing + the 1 previously
failing test, now passing under its new name/assertions, + 4 new tests =
149; 0 failed).

```
backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
```
Result: **All checks passed!**

```
backend/.venv/bin/python -m mypy tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
```
Result: **Success: no issues found in 2 source files** (project's
`mypy.ini` has `strict = true` set globally, confirmed by inspection, so no
separate `--strict` flag was needed).

## 4. Was a concrete lexer bug found?

**No.** The task's step 4 ("if — and only if — a concrete lexer bug
surfaces, fix it") was not triggered. Inspection of
`_lex_quoted_segment`, `_lex_identifier_segment`, `_lex_dotted_identifier`,
`_identifier_after_keyword`, `_extract_table_identifiers`,
`_split_identifier_segments`, and `_normalize_identifier_segment` against
ADR-011 D3.1 (case preservation for quoted segments, casefolding for
unquoted), D3.3 rule 1 (3+ parts → unattributed/ERROR, enforced in
`attribute_table_identifier` via `len(segments) >= 3`), and D6's
quoted-identifier requirement found the implementation consistent with the
governing text on every point checked: escaped embedded quotes (`""`)
correctly keep a quoted segment open rather than closing it early; an
unterminated quote fails closed (returns `None` from
`_lex_quoted_segment`, which `_lex_dotted_identifier` and
`_split_identifier_segments` both treat as a non-match/remainder rather
than a silent partial capture); and the 3+-part check and the live-scan
wiring in `_scan_sql_text` both exercise the lexer correctly, confirmed by
the new end-to-end tests in §1 item 3 actually passing against the
unmodified source. The one prior test failure was traced entirely to test
obsolescence (the test asserting old, superseded behavior), not to a
defect in the lexer itself — consistent with the task's own stated
independently-verified starting state.

This is a bounded, non-adversarial code-reading inspection by the
implementing session, not an independent review. It does not substitute
for a fresh-context independent review of this lexer, which has not been
dispatched or performed.

## 5. Limitations — explicitly NOT addressed by this session

The following are named here precisely because the task excluded them;
none of them was touched, investigated, or implicitly resolved by this
work:

- **CTE handling** (ADR-011 D3.2 state 3 lexical collection of `WITH ...`
  names) — not implemented. `_scan_sql_text` still passes `cte_names` as
  the empty default to every live call; this state is reachable only from
  `attribute_table_identifier`'s own direct unit tests, not from a live
  scan.
- **The I-1 zero-table-statement backstop** (ADR-011 D6.3) — not
  implemented in this session.
- **The remainder of D6** (D6.1 broadened trigger-verb set beyond what is
  already wired, D6.2 bytes-literal decoding, D6.4 docstring-position
  exclusion mechanics, D6.5/D6.6) beyond the quoted-identifier lexer itself
  — not inspected or touched beyond what was necessary to read D6's
  quoted-identifier requirement.
- **D4** (`_root`/`_shared` reserved-importer scanning) — not touched.
- **D5** (coverage reconciliation / totality) — not touched.
- **D7, D8** (error taxonomy completeness beyond what D3/D6 already
  exercise; report-surface self-evidencing requirements) — not
  independently re-verified beyond what the existing/new tests already
  cover incidentally.
- **CI changes** — none made.
- **The real module tree / real manifest** — not touched; all tests use
  the existing synthetic `_md_*` tempdir fixtures only.
- **SCN-070** (migration-ordering lint, a distinct surface) — not touched,
  not investigated.
- **DOM-002** (concurrency/versioning harness, a distinct surface) — not
  touched, not investigated, not resumed.
- **Any independent review** (security, scenario-catalog, code, or
  gatekeeper) — none dispatched, none claimed, no `REVIEW_IN_FLIGHT.md`
  entry written or touched.
- **Any git commit, push, or branch operation** — none performed. All
  changes remain in the working tree, both files still untracked.
- **Owner-reserved items** — no paid services, no real member data, no
  production deploy, no architecture/scope change; none of these arose
  during this bounded step.

## 6. Explicit non-claims

- This work does **not** close MOD-001's P0 in full.
- This work does **not** constitute a scenario PASS for
  `GOV-01-R04`/TSD §24.1 gate 2, or for any `SCN-MOD001-*` identifier.
- This work does **not** certify, approve, or promote anything. The next
  legally allowed action is a fresh-context independent review of the
  quoted-identifier lexer and its tests (and, separately, continued
  implementation of the excluded D4/D5/D6-remainder items), not a
  self-certification by this session.
