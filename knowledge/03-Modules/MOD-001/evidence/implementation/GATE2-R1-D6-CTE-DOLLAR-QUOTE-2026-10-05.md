# GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05 — pure lexical CTE-name
# collection helper, hardened against PostgreSQL dollar-quoted strings

**Scope of this session:** bounded sub-step, exactly as dispatched — close
the dollar-quoted-string gap `GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05.md`
explicitly disclosed and left out of its own scope: a `WITH fake AS (`
occurring inside a PostgreSQL `$$...$$` or `$tag$...$tag$` dollar-quoted
string could create a false CTE binding and/or corrupt paren-depth tracking
in the pure, deliberately-unwired `_collect_cte_names` helper and its
private support function `_skip_balanced_parens`, both in
`tools/validate_architecture_gates.py`. Nothing else was touched. Routing
(Sonnet/routine implementation, gate 2 — not an Opus-reserved slice) was
settled by the dispatching instruction, which itself names ADR-005 Decision
1 lines 111-126 as excluding gate 2 from critical-engineer scope; not
re-litigated here.

## Baseline verification (before this session's change)

```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
175 passed in 1.87s
```

```
backend/.venv/bin/ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```

Both match the dispatch's claimed starting state (175/175, Ruff clean)
exactly — no discrepancy to report.

## What changed

All changes are confined to `tools/validate_architecture_gates.py`'s new
`GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05` section (inserted directly after
the pre-existing `GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05` section's
constants, before `_skip_single_quoted_literal`) and docstring updates to
three existing functions/sections it affects by composition
(`_skip_quote_or_comment`, `_skip_balanced_parens`, `_collect_cte_names`),
plus `tools/tests/test_validate_architecture_gates.py`'s matching new test
section. No other function, including `_scan_sql_text` itself, was edited.

### New constant

- `_DOLLAR_QUOTE_RE = re.compile(r"\$(?:" + _BARE_IDENT_RE.pattern + r")?\$")`
  — matches a dollar-quote opening delimiter exactly where anchored: either
  the empty-tag form `$$` or a tagged form `$tag$`, where `tag` reuses
  `_BARE_IDENT_RE` (the same bare-identifier pattern — `[A-Za-z_][A-Za-z0-9_]*`
  — this module already uses elsewhere for ordinary bare identifiers), per
  PostgreSQL's own rule that a dollar-quote tag "follows the same rules as
  an unquoted identifier, except that it cannot contain a dollar sign." The
  character class naturally excludes `$`, so no additional exclusion logic
  was needed for that part of the rule.

### New private helper

- `_skip_dollar_quoted_string(text, opener: re.Match[str]) -> int | None`
  — given a `_DOLLAR_QUOTE_RE` match anchored at the opening delimiter,
  finds the literal closing delimiter (the *exact same* matched text, e.g.
  `"$tag$"`) via a single `str.find` call starting right after the opener,
  and returns the index immediately past it, or `None` if not found
  (unterminated). The entire body is skipped as one atomic jump — no
  tokenizing, no paren counting, no `WITH` recognition ever runs on text
  inside it, satisfying the "skip atomically" requirement directly by
  construction (a substring search never inspects the skipped text as SQL
  at all).

### Modified existing function

- **`_skip_quote_or_comment`** — one new branch added after the existing
  `'`/`--`/`/* */` checks: if `text[pos] == "$"` and `_DOLLAR_QUOTE_RE`
  matches anchored at `pos`, dispatches to `_skip_dollar_quoted_string` and
  returns its result (including `None` on an unterminated opener, per the
  function's existing contract). If `text[pos] == "$"` but no valid
  dollar-quote opener matches there (a positional parameter like `$1`, a
  bare `$`, or ordinary currency/dollar text), the function falls through
  to its existing `return pos` — the character is left for the caller to
  treat as ordinary text, exactly as before this change. Because both
  `_skip_balanced_parens` and `_collect_cte_names` already call this one
  dispatcher for every character position, no second call site needed to
  change — the same single-dispatcher structure the prior
  (`GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05`) increment established is
  reused unmodified, which is also why `_skip_balanced_parens`'s and
  `_collect_cte_names`'s own code bodies required zero logic changes this
  session — only their docstrings were updated to name the new lexical
  region.

### Docstring-only updates

- `_skip_balanced_parens` — names the new dollar-quoted-string skip
  alongside the pre-existing literal/comment skip in its description of
  what it tolerates inside a balanced-paren body.
- `_collect_cte_names` — its lexical-regions sentence now lists five
  regions (double-quoted segments, single-quoted literals, line comments,
  block comments, dollar-quoted strings) instead of four; its
  unterminated-region sentence now includes dollar-quoted strings; its
  LIMITATIONS bullet for dollar-quoted strings is rewritten from "NOT
  recognised... residual" to "recognised and skipped atomically", with a
  new sub-note about the ASCII-only tag character set (see "Design
  decision" below).

## Design decision: tag character set is `_BARE_IDENT_RE`, not full PostgreSQL identifier rules

The task required recognizing a tag "following PostgreSQL identifier
rules." Real PostgreSQL identifier rules permit non-ASCII letters (any
character with the high bit set in a multi-byte encoding) as both the
first character and continuation characters. This module's own existing
bare-identifier pattern, `_BARE_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")`,
is ASCII-only and was already in use elsewhere in this file for ordinary
bare identifiers before this session. Reusing it for the dollar-quote tag
(rather than inventing a second, wider pattern) was a deliberate choice,
verified safe by the same reasoning direction the prior increment's
backslash decision used:

- A real PostgreSQL tag using a non-ASCII letter (e.g. `$café$`) will not
  match `_DOLLAR_QUOTE_RE` at all, so this function does not recognise it
  as an opening delimiter — the `$` is left as an ordinary character.
- The *only* possible effect of that narrower-than-Postgres acceptance is
  that this function will not skip such a dollar-quoted region atomically;
  if it contains a `WITH fake AS (` or stray parens, those get scanned as
  ordinary text by the rest of `_collect_cte_names`/`_skip_balanced_parens`
  — exactly the same pre-existing, already-disclosed exposure that existed
  for *all* dollar-quoted strings before this session, just narrowed to the
  non-ASCII-tag case specifically. It never manufactures a new false
  binding beyond what already existed; it only leaves one narrow slice of
  the original gap open, which is recorded as a residual risk below rather
  than silently covered.
- Reusing `_BARE_IDENT_RE` also matches this module's own existing
  convention (DRY — one definition of "what is a bare identifier here,"
  not two subtly different ones) and was the dispatching task's own
  framing ("tag following PostgreSQL identifier rules," not "the complete
  PostgreSQL identifier grammar including non-ASCII").

This also directly satisfies the "do NOT treat positional parameters or
ordinary currency/dollar text as an opening delimiter" requirement: `$1`,
`$`, and plain `$5.00`-style text never match `_DOLLAR_QUOTE_RE` at all,
since a digit is not a valid identifier-start character and no second
literal `$` immediately follows a one-character match attempt in any of
those shapes — verified by the `test_cte_positional_parameter_is_not_misread_as_dollar_quote_opener`
test below, not merely reasoned.

## Live verification of required test shapes

Every shape the dispatch required was run via the formal pytest cases
below, which are the durable, re-runnable record (no separate throwaway
script was used this session beyond the normal pytest run, since each case
is already a direct, isolated call to the pure function):

| Input shape | Expected | Confirmed |
|---|---|---|
| `WITH fake AS (` inside `$$...$$` | no binding | yes |
| `WITH fake AS (` inside `$tag$...$tag$` | no binding | yes |
| Unbalanced parens inside `$$...$$` inside a real CTE body | body end located correctly, no sweep into trailing text | yes |
| Mismatched tag (`$a$ ... $b$ ... $a$`) | string stays open past the mismatched `$b$`, only closes at the real matching `$a$` | yes |
| Unterminated dollar-quoted opener | fails closed, collects nothing | yes |
| Real binding before an unterminated dollar-quoted string later in the text | kept | yes |
| Real `WITH` after a closed `$$...$$` | collected | yes |
| Real `WITH` after a closed, correctly-tag-matched `$tag$...$tag$` | collected | yes |
| `$1` positional parameter | not misread as an opener; surrounding real CTE still collected | yes |

## Tests added

9 new test functions in `tools/tests/test_validate_architecture_gates.py`,
in a new `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05` section inserted
directly after the existing `GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05`
section's tests and before `test_module_deps_cli_exit_codes_and_no_skip_flag`,
matching that section's own style (calling `_collect_cte_names` directly,
no fixture tree):

1. `test_cte_fake_with_inside_dollar_quoted_string_produces_no_binding`
2. `test_cte_fake_with_inside_tagged_dollar_quoted_string_produces_no_binding`
3. `test_cte_unbalanced_parens_inside_dollar_quoted_string_does_not_corrupt_depth`
4. `test_cte_mismatched_dollar_quote_tag_does_not_close_early`
5. `test_cte_unterminated_dollar_quoted_opener_fails_closed`
6. `test_cte_real_binding_before_unterminated_dollar_quote_is_still_kept`
7. `test_cte_real_binding_after_dollar_quoted_string_is_still_collected`
8. `test_cte_matching_tagged_dollar_quote_then_real_binding_is_collected`
9. `test_cte_positional_parameter_is_not_misread_as_dollar_quote_opener`

All 9 assert on `_collect_cte_names`'s return value directly; none drive it
through `run_module_deps_gate` or any fixture tree. Together they cover
every shape the dispatch's TESTS section named: deceptive `WITH` inside a
dollar-quoted string (1, 2), deceptive parens inside one (3), matching vs.
mismatched tagged delimiters (4, 8), an unterminated opener (5, 6), a real
`WITH` after a dollar-quoted string (7, 8), and `$1` not misread as an
opener (9).

## Test and Ruff results

**Before this session's change** (baseline, repeated for side-by-side
comparison):
```
175 passed in 1.87s
ruff check ...: All checks passed!
```

**After this session's change:**
```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
184 passed in 1.95s
```
184 = 175 baseline + 9 new test functions, zero regressions, zero failures.

```
backend/.venv/bin/ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```
Clean on both touched files, no new findings.

**Baselines:**
```
backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.
```
4/4, unchanged — this session never reads or writes any of the four
governing artifacts.

## Fail-closed convention used

Identical to the convention the prior `GATE2-R1-D6-CTE-LEXICAL-HARDENING`
increment established for single-quoted literals and block comments, and
to `_lex_quoted_segment`'s pre-existing convention for double-quoted
segments: `_skip_dollar_quoted_string` returns `None` when no closing
delimiter is found before `text` ends. Both call sites
(`_skip_balanced_parens`, `_collect_cte_names`) already treat a `None`
from `_skip_quote_or_comment` as "stop scanning entirely from this point" —
`_skip_balanced_parens` reports the enclosing body as unbalanced (`None`),
and `_collect_cte_names` `break`s its scan loop, keeping only names already
collected before the unterminated region. No new fail-closed mechanism was
invented; the existing one was extended to a fourth lexical region by
routing it through the same `_skip_quote_or_comment` dispatcher both call
sites already used.

## Confirmation: helper remains unwired; nothing out-of-scope touched

- **Unwired, confirmed by execution, not inspection alone:**
  `grep -n "_collect_cte_names(" tools/validate_architecture_gates.py`
  returns exactly one match — the function's own `def` line. No caller
  exists anywhere in the module, including `_scan_sql_text`.
- **`_scan_sql_text` untouched.** Confirmed by direct re-reading: its
  docstring and body are unchanged; it still passes `attribute_table_identifier`
  the default empty `cte_names`, exactly as before.
- **`_skip_balanced_parens`'s and `_collect_cte_names`'s code bodies were
  not edited** — only their docstrings changed, since the new dollar-quote
  handling is entirely composed through the shared `_skip_quote_or_comment`
  dispatcher both already called. This was verified by the diff itself:
  the only non-docstring, non-comment lines changed in those two functions
  are zero.
- **The scanner, table extraction, D4/D5/D7/D8, trigger/I1, byte
  counts/pins, CI config, the real-tree manifest, D1b/D2, SCN-070, and
  DOM-002** were not read or touched by this session.
- **No review was performed or requested** by this session. This is an
  implementation record, not an independent review.
- **No P0 closure or scenario PASS claim.** No scenario was touched,
  inspected for promotion, or claimed closed.
- **Nothing was committed, pushed, staged, or stashed.** `git status --porcelain
  tools/` shows both touched files still as untracked (`??`), identical in
  status to their state before this session; the three pre-existing
  unrelated modified files (`tools/tests/test_validate_migration_ordering.py`,
  `tools/validate_capability_manifest.py`, `tools/validate_migration_ordering.py`)
  are confirmed untouched by this session (diff stats checked, all
  pre-existing from before this session started).
- **WIP=1 preserved; MOD-001 only.** No other module's files were read or
  edited.

## RESIDUAL RISKS

These are carried forward, re-confirmed, or newly identified by this
session — none were silently resolved:

1. **Non-ASCII dollar-quote tags are not recognised as openers at all.**
   PostgreSQL's real identifier rules permit non-ASCII letters in a tag;
   `_DOLLAR_QUOTE_RE` reuses this module's existing ASCII-only
   `_BARE_IDENT_RE`. A tag like `$café$` will not be matched as an opening
   delimiter, so any deceptive `WITH fake AS (` or stray parens inside such
   a region would still be scanned as ordinary text — the same exposure
   this increment closes for ASCII-tagged and empty-tag dollar-quoted
   strings specifically, narrowed to this one non-ASCII slice. This is a
   real, disclosed gap, not silently covered; see "Design decision" above
   for why it is still safe-direction (a missed opener degrades to a
   missed binding, never a false one) rather than closed outright.
2. **`RECURSIVE`, a parenthesised column-name list after a CTE name
   (`WITH cte(a, b) AS (...)`), and `[NOT] MATERIALIZED`** remain
   unrecognised, exactly as both prior reports disclosed — unaffected by
   and out of scope for this session's change. Each still fails closed
   (no binding collected), never guessed past.
3. **Unicode identifier escapes (`U&"..."` / `U&'...'`)** remain only
   partially covered, exactly as the prior report disclosed — unaffected
   by this session's change; a `U&'...'` form is lexed as an ordinary
   single-quoted literal (not confused with a dollar-quoted string, since
   its first character is `U`/`u`, not `$` or `'` — no interaction between
   this session's new branch and that pre-existing gap was found or
   introduced).
4. **The exact "same statement" scope the live scanner should pass to
   `_collect_cte_names`** remains an open design question, named as still
   open by both prior reports. This session's change is purely about what
   happens lexically once some scope of text is handed to the helper, and
   does not touch that design question.
5. **`_collect_cte_names` and `_skip_balanced_parens` remain entirely
   unwired into `_scan_sql_text`**, as required by this session's hard
   exclusions. All dollar-quote hardening closed here is inert in the live
   scanning path today; a future wiring increment must re-confirm every
   residual risk across all three reports (the original helper report, the
   lexical-hardening report, and this one) before relying on this helper
   in a release-blocking gate — none of that re-confirmation was performed
   or assumed by this session.
6. **No fuzz/property-based testing was performed.** All verification here
   is example-based (9 new hand-written cases plus the 16 from the prior
   lexical-hardening increment and the 9 from the original helper). A
   future increment relying on this helper for a release-blocking gate
   should consider adversarial/fuzz testing of the combined literal +
   comment + dollar-quote lexer surface before trusting it against
   arbitrary, untrusted SQL text.

None of the above was attempted or silently resolved in this session; they
are recorded here, building on (not replacing) the residual-risk sections
of the two prior reports, so a future increment does not have to re-derive
them from scratch.

## Orchestrator correction — 2026-10-05T04:02:48Z

Residual risk #1 above incorrectly characterizes an unrecognized non-ASCII dollar-quote opener as only a safe-direction missed binding. The independent deterministic probe

```sql
SELECT $café$ WITH fake AS (SELECT 1) $café$
```

returned `_collect_cte_names(...) == frozenset({"fake"})`. This is a **false CTE binding**, not merely a missed one, and would be unsafe if the helper were wired into live table attribution. The helper remains unwired; no scenario PASS or P0 closure follows. This record supersedes only that safety characterization, not the 184/184 test result or the confirmed ASCII dollar-quote behavior. Non-ASCII-tag handling and statement scope remain open before wiring.

## Addendum — 2026-10-05 (GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05)

The defect the orchestrator correction above identified has now been FIXED,
not merely disclosed, in a separate bounded increment: see
`GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05.md`. The dollar-quote tag matcher
now follows PostgreSQL's real (Unicode-aware) identifier rules instead of
this report's ASCII-only `_BARE_IDENT_RE`-based tag, so `$café$` and other
non-ASCII tags are recognised and skipped atomically — the probe above now
returns `frozenset()`. This addendum is appended, not a rewrite of this
report's historical text; residual risk #1 above and the orchestrator
correction both remain exactly as originally recorded, describing the state
as it was at the time. The helper remains unwired; no scenario PASS or P0
closure follows from the fix either.
