# GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05 — Unicode-aware dollar-quote
# tag recognition for the pure CTE-name collection helper

**Scope of this session:** bounded sub-step, exactly as dispatched — fix a
real defect in `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05`'s own residual
risk #1, which mischaracterized an unrecognized non-ASCII dollar-quote tag
as "safe-direction only." A direct adversarial probe disproved that
characterization (reproduced below). Routing (Sonnet/routine implementation,
gate 2 — not an Opus-reserved slice) was settled by the dispatching
instruction, which names ADR-005 Decision 1 lines 111-126 as excluding gate
2 from critical-engineer scope; not re-litigated here.

## The defect

`GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05.md`'s residual risk #1 stated that
a dollar-quote tag using a non-ASCII letter would go unrecognized as an
opener, and characterized this as safe: "a missed opener degrades to a
missed binding, never a false one." That reasoning is wrong. An unrecognized
opener does not degrade to a *missed binding* — it degrades to the entire
dollar-quoted region being scanned as **ordinary top-level text**, because
no lexical region is entered at all. If that region happens to contain a
genuine-looking `WITH fake AS (...)` construct at parenthesis depth 0, it is
read and collected as a real binding.

**Reproducing probe (confirmed by direct execution before any change this
session):**

```python
_collect_cte_names("SELECT $café$ WITH fake AS (SELECT 1) $café$")
# -> frozenset({'fake'})   (pre-fix)
```

This is a **false CTE binding** — ADR-011 D3.2 state 3 exists precisely to
mark an identifier as "locally bound, clean, counted," and a false positive
here means a real table named `fake` would be silently treated as a CTE and
excluded from cross-domain attribution if this helper were ever wired into
the live scanner (`_scan_sql_text`). It remains unwired today (confirmed
below), so nothing in the live gate is currently affected — but the
helper's own safety claim was false, and this record corrects it by fixing
the underlying mechanism, not by re-wording the disclosure.

## Lexical rule applied

Per the official PostgreSQL lexical-structure documentation
(https://www.postgresql.org/docs/current/sql-syntax-lexical.html):

- An unquoted identifier's first character is "a letter (including letters
  with diacritical marks and non-Latin letters) or an underscore"; later
  characters may additionally be digits.
- "The tag, if any, of a dollar-quoted string follows the same rules as an
  unquoted identifier, except that it cannot contain a dollar sign."
- The closing delimiter must have exactly the same tag as the opening
  delimiter — matching is case-sensitive and exact.
- `$` followed by a digit is a positional parameter (e.g. `$1`), not a
  dollar-quote opener — a digit can never start an identifier, so this falls
  out of the identifier rule directly rather than needing a special case.
- An empty tag (`$$...$$`) is valid.

The prior increment's tag matcher (`_DOLLAR_QUOTE_RE`) reused this module's
own `_BARE_IDENT_RE`, which is `[A-Za-z_][A-Za-z0-9_]*` — **ASCII-only**,
narrower than the real rule above. This session replaces that matcher with
one that follows the real rule, approximated via Python's Unicode-aware
`str.isalpha()` ("letter") and `str.isalnum()` ("letter or digit") — both
of which recognize letters with diacritical marks and non-Latin letters,
unlike the ASCII character class.

## What changed

All changes are confined to `tools/validate_architecture_gates.py`'s
existing `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05` section (extended with a
new `GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05` sub-increment, inline, not a
new section — the dispatch is a correction of that section's own defect,
not an independent addition) and `tools/tests/test_validate_architecture_gates.py`'s
matching new test section. No other function, including `_scan_sql_text`,
`_skip_balanced_parens`'s or `_collect_cte_names`'s code bodies (only their
docstrings), was edited.

### Removed

- `_DOLLAR_QUOTE_RE` (the ASCII-only regex constant). No other caller
  existed anywhere in the module or its tests (confirmed by grep before
  removal), so removing it is not a breaking change to anything else.

### Added

- **`_match_dollar_quote_opener(text: str, pos: int) -> int | None`** — new
  pure helper replacing the regex match. `text[pos]` must be `"$"`. Checks
  for the empty-tag form (`$$`) first; otherwise requires the next character
  to satisfy `str.isalpha() or == "_"` (tag start), then consumes
  `str.isalnum() or == "_"` characters (tag continuation, Unicode-aware),
  then requires an immediate closing `$`. Returns the index just past the
  full opening delimiter, or `None` if no valid opener starts at `pos` at
  all (positional parameter, bare `$`, ordinary currency/dollar text, or any
  shape that doesn't close with a second `$`).

### Modified

- **`_skip_dollar_quoted_string`** — signature changed from
  `(text, opener: re.Match[str])` to `(text, pos: int, opener_end: int)`,
  since there is no longer a `re.Match` object to carry the delimiter text
  and its end index. The delimiter is now sliced directly as
  `text[pos:opener_end]`; the closing-delimiter search (`text.find`) and the
  `None`-on-unterminated contract are byte-for-byte unchanged from the prior
  increment — only how the delimiter text and search start position are
  obtained changed, not the skip/fail-closed logic itself.
- **`_skip_quote_or_comment`** — its one dollar-quote branch now calls
  `_match_dollar_quote_opener(text, pos)` instead of `_DOLLAR_QUOTE_RE.match(text, pos)`,
  and passes `(text, pos, opener_end)` to `_skip_dollar_quoted_string`
  instead of a `re.Match`. `_skip_balanced_parens` and `_collect_cte_names`
  both still call this one dispatcher for every character position, so
  neither required any code change — composition through the shared
  dispatcher, exactly as the prior two increments relied on.

### Docstring-only updates

- The `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05` module-level comment block
  gained a `GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05` sub-section stating
  the defect, the reproducing probe, and the PostgreSQL doc citation for the
  real identifier rule.
- `_collect_cte_names`'s LIMITATIONS bullet for dollar-quoted strings is
  rewritten: removed the false "narrower-than-Postgres acceptance ... safe
  direction" claim; states the tag now follows PostgreSQL's real
  (Unicode-aware) identifier rules, names the corrected defect and probe
  inline, and keeps the positional-parameter and exact/case-sensitive
  matching statements (unchanged, still true).

## Live verification of required test shapes

| Input shape | Expected | Confirmed |
|---|---|---|
| `WITH fake AS (` inside `$café$...$café$` (the reproducing probe) | no binding | yes |
| `WITH fake AS (` inside a CJK-tagged `$标签$...$标签$` region | no binding | yes |
| Decoy unbalanced parens inside a non-ASCII-tagged region, inside a real CTE body | body end located correctly, trailing table not swept in | yes |
| Malformed/unclosed non-ASCII-tagged region (opener matches, never closes) | fails closed, collects nothing | yes |
| Mismatched non-ASCII tag (`$café$ ... $cafe$ ... $café$`) | string stays open past the mismatched tag, only closes at the real match | yes |
| Mismatched tag via case difference only (`$Tag$ ... $tag$ ... $Tag$`) | string stays open past the case-mismatched tag | yes |
| `$1` positional parameter, after the Unicode-aware rewrite | still not misread as an opener | yes |
| Pre-existing ASCII-tagged and empty-tag (`$$`) shapes | unchanged behavior | yes |
| Real `WITH` after a correctly-closed non-ASCII-tagged region | collected | yes |

## Tests added

9 new test functions in `tools/tests/test_validate_architecture_gates.py`,
in a new `GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05` section inserted
directly after the existing `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05`
section's tests and before `test_module_deps_cli_exit_codes_and_no_skip_flag`:

1. `test_cte_fake_with_inside_non_ascii_tagged_dollar_quoted_string_produces_no_binding`
   — the exact reproducing probe (`$café$`).
2. `test_cte_fake_with_inside_cjk_tagged_dollar_quoted_string_produces_no_binding`
   — second non-Latin tag shape (CJK), confirming the fix is Unicode-general.
3. `test_cte_decoy_parens_inside_non_ascii_tagged_dollar_quoted_string_do_not_corrupt_depth`
   — decoy parentheses inside a non-ASCII-tagged region.
4. `test_cte_malformed_non_ascii_dollar_quote_region_fails_closed` — malformed/
   unclosed region (opener recognized, body never closes).
5. `test_cte_mismatched_non_ascii_dollar_quote_tag_does_not_close_early` —
   mismatched opening vs. closing tag (`$café$` vs `$cafe$`).
6. `test_cte_case_difference_dollar_quote_tag_mismatch_does_not_close_early` —
   mismatched tag via case difference only (`$Tag$` vs `$tag$`).
7. `test_cte_positional_parameter_still_not_misread_after_unicode_fix` —
   `$1` regression under the new Unicode-aware matcher.
8. `test_cte_ascii_and_empty_tag_dollar_quotes_still_work_after_unicode_fix`
   — ASCII-tag and empty-tag (`$$`) regression.
9. `test_cte_real_binding_after_non_ascii_tagged_dollar_quoted_string_is_still_collected`
   — a real CTE after a correctly closed non-ASCII-tagged region.

All 9 assert on `_collect_cte_names`'s return value directly, matching the
existing section's style; none drive it through `run_module_deps_gate` or
any fixture tree.

## Test and Ruff results

**Baseline, independently re-verified before this session's change**
(matches the dispatch's claimed starting state exactly — no discrepancy):
```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
184 passed in 1.84s

backend/.venv/bin/ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!

backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.
```

**Probe, run against the unmodified baseline code (confirms the defect is
real, not hypothetical):**
```
_collect_cte_names("SELECT $café$ WITH fake AS (SELECT 1) $café$")
-> frozenset({'fake'})
```

**After this session's change:**
```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
193 passed in 1.94s
```
193 = 184 baseline + 9 new test functions, zero regressions, zero failures.

```
backend/.venv/bin/ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```

**Probe re-run against the fixed code:**
```
_collect_cte_names("SELECT $café$ WITH fake AS (SELECT 1) $café$")
-> frozenset()
```
`'fake'` is confirmed absent.

**Baselines, re-run after the change:**
```
backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.
```
4/4, unchanged — this session never reads or writes any of the four
governing artifacts.

## Fail-closed convention used

Unchanged from the prior two increments: `_skip_dollar_quoted_string`
returns `None` when no closing delimiter is found before `text` ends. Both
call sites (`_skip_balanced_parens`, `_collect_cte_names`) already treat a
`None` from `_skip_quote_or_comment` as "stop scanning entirely from this
point." This session's change only widens *which* openers are recognized
(via `_match_dollar_quote_opener`'s Unicode-aware tag rule) — it does not
alter, weaken, or add a new fail-closed path. A malformed, unclosed, or
mismatched-tag region still fails closed exactly as before: no name is
collected from inside or after an unresolvable region, and nothing falls
back to parsing the region's contents as ordinary SQL.

## Confirmation: helper remains unwired; nothing out-of-scope touched

- **Unwired, confirmed by execution, not inspection alone:**
  `grep -n "_collect_cte_names(" tools/validate_architecture_gates.py`
  returns exactly one match — the function's own `def` line (plus two
  docstring/comment mentions of the probe string, which are not calls). No
  caller exists anywhere in the module, including `_scan_sql_text`.
- **`_scan_sql_text` untouched.** Not read or edited by this session.
- **`_skip_balanced_parens`'s and `_collect_cte_names`'s code bodies were
  not edited** — only their docstrings changed, since the Unicode-aware
  dollar-quote handling is entirely composed through the shared
  `_skip_quote_or_comment` dispatcher both already called.
- **D4/D5/D7/D8, trigger/I1, bytes/docstrings handling, CI config, the
  real-tree manifest, D1b/D2, SCN-070, and DOM-002** were not read or
  touched by this session.
- **No review was performed or requested** by this session. This is an
  implementation record, not an independent review.
- **No P0 closure or scenario PASS claim.** No scenario was touched,
  inspected for promotion, or claimed closed.
- **Nothing was committed, pushed, staged, or stashed.** Both touched files
  remain untracked (`??`), identical in status to their state before this
  session. The three pre-existing unrelated modified files
  (`tools/tests/test_validate_migration_ordering.py`,
  `tools/validate_capability_manifest.py`,
  `tools/validate_migration_ordering.py`) were confirmed untouched by this
  session via `git status --porcelain tools/`.
- **WIP=1 preserved; MOD-001 only.** No other module's files were read or
  edited.

## Correction of the prior report's false characterization

`GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05.md`'s residual risk #1 stated:

> This is a real, disclosed gap, not silently covered; see "Design
> decision" above for why it is still safe-direction (a missed opener
> degrades to a missed binding, never a false one) rather than closed
> outright.

This is **incorrect** and is corrected here (and via an appended addendum
in that report itself, not a rewrite of its historical text — see its
"Addendum — 2026-10-05" section). The correct characterization: a missed
dollar-quote opener does not degrade to a missed *binding* — the helper
never "misses" a binding by skipping too much. It degrades to the entire
would-be-quoted region being scanned as **ordinary top-level text**, which
can produce a **false** binding if that text happens to contain a
syntactically valid `WITH ... AS (...)` construct at depth 0, exactly as
the reproducing probe demonstrates. That report's own orchestrator
correction (dated 2026-10-05T04:02:48Z) had already identified this via the
same probe; this report's contribution is the **fix**, not merely a second
restatement of the finding.

## RESIDUAL RISKS

Carried forward from the two prior reports, re-confirmed where re-tested,
and updated where this session's fix changes their status:

1. **CLOSED by this session:** non-ASCII dollar-quote tags are now
   recognized as openers (Unicode-aware, per `_match_dollar_quote_opener`).
   The prior report's residual #1 is superseded by this fix; see the
   correction section above and that report's own addendum.
2. **`RECURSIVE`, a parenthesised column-name list after a CTE name
   (`WITH cte(a, b) AS (...)`), and `[NOT] MATERIALIZED`** remain
   unrecognised, exactly as all prior reports disclosed — unaffected by and
   out of scope for this session's change. Each still fails closed (no
   binding collected), never guessed past.
3. **Unicode identifier escapes (`U&"..."` / `U&'...'`)** remain only
   partially covered, exactly as prior reports disclosed — unaffected by
   this session's change.
4. **The exact "same statement" scope the live scanner should pass to
   `_collect_cte_names`** remains an open design question, named as still
   open by all prior reports. This session's change is purely about which
   dollar-quote openers are recognized lexically, and does not touch that
   design question.
5. **`_collect_cte_names` and `_skip_balanced_parens` remain entirely
   unwired into `_scan_sql_text`**, as required by this session's hard
   exclusions. All dollar-quote hardening closed here (both the ASCII/empty-
   tag increment and this Unicode increment) is inert in the live scanning
   path today; a future wiring increment must re-confirm every residual risk
   across all three reports before relying on this helper in a
   release-blocking gate — none of that re-confirmation was performed or
   assumed by this session.
6. **No fuzz/property-based testing was performed.** All verification here
   is example-based (9 new hand-written cases this session, plus 9 from the
   ASCII/empty-tag increment and 9 from the original helper report, 27
   dollar-quote-focused cases total). A future increment relying on this
   helper for a release-blocking gate should consider adversarial/fuzz
   testing of the combined literal + comment + dollar-quote lexer surface.
7. **`str.isalpha()`/`str.isalnum()` are an approximation of PostgreSQL's
   real identifier character rules, not a byte-exact reimplementation of
   PostgreSQL's own identifier grammar.** Python's Unicode letter/digit
   categories and PostgreSQL's server-encoding-dependent identifier rules
   are not guaranteed to agree on every exotic code point (e.g. certain
   Unicode categories PostgreSQL may or may not accept depending on
   encoding/locale). This is a new, narrower residual than #1 above (which
   is now closed for the common case), disclosed rather than silently
   assumed to be a perfect match. In the fail direction this matters: a
   code point Python accepts as a tag character but PostgreSQL would not
   can only cause this helper to recognize a non-existent-in-real-Postgres
   opener, over-skipping text that a real Postgres parser would not treat as
   a dollar-quoted region — the same safe direction (over-skip degrades to a
   missed binding later in the text, never a false one) the original
   ASCII-only implementation relied on for the inverse case. No evidence of
   a concrete disagreeing code point was found or tested; this is a
   disclosed theoretical gap, not a demonstrated one.

None of the above was attempted or silently resolved beyond what is stated.
They build on, not replace, the residual-risk sections of the three prior
reports.

## Deliberately left out of scope

- No wiring of `_collect_cte_names` into `_scan_sql_text`.
- No change to the live scanner or table-extraction logic.
- No touch to D4/D5/D7/D8, trigger/I1, bytes/docstrings handling, CI config,
  the real-tree manifest, D1b/D2, SCN-070, or DOM-002.
- No review, commit, or push.
- No P0 closure, no scenario PASS claim.
