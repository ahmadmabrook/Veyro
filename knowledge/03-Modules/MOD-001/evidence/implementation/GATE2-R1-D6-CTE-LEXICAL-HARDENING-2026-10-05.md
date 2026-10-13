# GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05 — pure lexical CTE-name
# collection helper, hardened against quoted/commented decoy text

**Scope of this session:** bounded sub-step, exactly as dispatched — harden
the pure, deliberately-unwired helper `_collect_cte_names` (and its private
support function `_skip_balanced_parens`) in
`tools/validate_architecture_gates.py` so that `WITH fake AS (` text inside a
single-quoted SQL string literal or an SQL comment can never create a false
CTE binding and can never corrupt parenthesis-depth tracking. This closes the
limitation `GATE2-R1-D6-CTE-HELPER-2026-10-05.md` disclosed under "No
string-literal lexer." Nothing else. Routing (Sonnet/routine implementation,
gate 2 — not an Opus-reserved slice; re-verified below, not re-litigated)
was settled by the dispatching instruction.

## Routing re-verification (performed this session, not assumed)

`knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`,
Decision 1's "Slices in scope" list names exactly three critical slices: (1)
the tenant-isolation/RLS test harness, (2) the authentication
negative-credential fixture pattern, and (3) "Two of TSD §24.1's six
architecture gates specifically — the **RLS lint** gate and the **permission
lint** gate." The same section's "Explicitly NOT in scope" paragraph names
"the other four §24.1 gates" as routing normally. `IMPLEMENTATION.md` §4's
own six-gate table confirms gate 2 is the **module dependency/SQL lint**
(`CROSS_DOMAIN_SQL_IMPORT`/`REVERSE_EDGE_NOT_EVENT_DRIVEN`) — a different
gate from the RLS lint and permission lint gates ADR-005 reserves. Gate 2 is
therefore one of the "other four," confirmed routed to routine
Sonnet-tier implementation, not `veyro-critical-engineer`. No conflict found
in the governing docs; proceeded.

## Baseline verification (before this session's change)

```
source backend/.venv/bin/activate && python3 -m pytest tools/tests/test_validate_architecture_gates.py -q
159 passed in 1.92s
```

```
ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
All checks passed!
```

Both match the dispatch's claimed baseline (159/159, Ruff clean) exactly —
no discrepancy to report.

## What changed

All changes are confined to `tools/validate_architecture_gates.py`'s
GATE2-R1-D6-CTE-HELPER section (between the pre-existing `_CTE_WS_RE`
constant and `_is_dynamic_import_call`) and
`tools/tests/test_validate_architecture_gates.py`'s GATE2-R1-D6-CTE-HELPER
test section. No other function, including `_scan_sql_text` itself, was
edited.

### New private helpers (`tools/validate_architecture_gates.py`)

- `_skip_single_quoted_literal(text, pos) -> int | None` (line ~2234) —
  given `text[pos] == "'"`, returns the index immediately after the
  literal's closing `'`, or `None` if `text` ends first (unterminated).
  Recognises SQL's doubled-quote escape (`''`) and treats a backslash as
  escaping the next character unconditionally (see "Design decision:
  backslash handling" below).
- `_skip_line_comment(text, pos) -> int` (line ~2280) — given
  `text[pos:pos+2] == "--"`, returns the index immediately after the
  terminating `\n`, or `len(text)` if the comment runs to end of input
  (never `None`; a line comment always has a well-defined end).
- `_skip_block_comment(text, pos) -> int | None` (line ~2290) — given
  `text[pos:pos+2] == "/*"`, returns the index immediately after the
  matching `*/`, honouring PostgreSQL's nesting semantics (see "PostgreSQL
  nested-comment verification" below), or `None` if unterminated.
- `_skip_quote_or_comment(text, pos) -> int | None` (line ~2322) — the
  single dispatcher both call sites below use: if a single-quoted literal,
  line comment, or block comment starts exactly at `pos`, returns the index
  past it (or `None` if unterminated); otherwise returns `pos` unchanged.
  `"` (double-quoted identifiers) is deliberately NOT this function's
  concern — both call sites already check for it themselves, via the
  pre-existing `_lex_quoted_segment`, before ever reaching this dispatcher,
  so double-quoted identifiers are unaffected by this increment (same
  pre-existing behaviour, confirmed unchanged by direct reading).

### Modified existing functions

- **`_skip_balanced_parens`** (line ~2344) — one new branch added: after the
  pre-existing `"` check, calls `_skip_quote_or_comment` and, if it returns
  a different index, jumps there instead of inspecting that character as a
  paren. Returns `None` (unbalanced body) if the dispatcher returns `None`
  (an unterminated literal/comment inside the body). No other line of this
  function changed.
- **`_collect_cte_names`** (line ~2441) — the identical one-branch addition
  in its own depth-tracking loop: calls `_skip_quote_or_comment` immediately
  after the pre-existing `"` check; a non-`None`, non-identity result jumps
  the scan position there; `None` `break`s the loop (mirroring the
  pre-existing unterminated-double-quote `break`, so everything collected up
  to that point is kept, nothing past it is inspected). Docstring extended
  to describe the new behaviour and to add three new, honestly-scoped
  LIMITATIONS bullets (dollar-quoting, `E'...'` escape semantics,
  Unicode-escape identifiers) plus one bullet clarifying double-quoted
  identifiers were already handled, unchanged. The single-quote-literal
  limitation bullet the prior report carried is removed, since it is now
  closed, not merely re-worded.

### Design decision: backslash handling inside single-quoted literals

`_skip_single_quoted_literal` treats a backslash as escaping the next
character for **every** single-quoted literal, not only ones with a leading
`E`/`e` (it does not look behind `pos` to check for one). This was a
deliberate choice, reasoned through and then verified live (see "Live
verification of the design decision" below) rather than assumed:

- A real PostgreSQL `E'...'`-escape string treats `\'` as an escaped literal
  quote. A scanner that only recognises the doubled-quote escape (`''`) and
  does not know about `\'` would read the quote immediately after the
  backslash as a genuine close — `E'foo\' WITH fake AS ('` would appear to
  close at that point, exposing `WITH fake AS ('` as ordinary SQL text one
  token later. That is exactly the false-binding direction this increment
  exists to prevent.
- For an ordinary (non-`E`) string, backslash is NOT special in real
  PostgreSQL; treating it as an escape there is not dialect-exact. But the
  *only* possible effect of that inexactness is to make this function
  consume MORE of `text` as "still inside the literal" than a real Postgres
  lexer would (it can delay closing, never advance it) — which can only
  cause a real binding later in the text to be missed, degrading to ADR-011
  D3.2 state 6 (`MODULE_DEPS_TABLE_UNATTRIBUTED`, ERROR) — the function's
  own already-documented safe direction. It can never manufacture a false
  binding by closing early, in either dialect.

This is the same "prefer fewer/no CTE names over a wrong one" principle the
original helper report already applied to unbalanced bodies; this session
applies it to one more lexical boundary.

## PostgreSQL nested-comment verification (performed, not assumed)

The task required verifying, not assuming, whether PostgreSQL nests
`/* ... */` block comments. Fetched the live PostgreSQL documentation
(`https://www.postgresql.org/docs/current/sql-syntax-lexical.html`,
"SQL Syntax" / lexical-structure chapter) this session and confirmed the
exact text: block comments of the form `/* ... /* nested */ ... */` "nest,
as specified in the SQL standard but unlike C, so that one can comment out
larger blocks of code that might contain existing block comments."
`_skip_block_comment` implements this with a depth counter (nested `/*`
increments, `*/` decrements, closes only at depth 0), not a first-`*/`-wins
scan. Also fetched the same page's String Constants section, confirming the
doubled-quote (`''`) escape and the `E'...'` backslash-escape convention
referenced in the "Design decision" section above.

## Live verification of the design decision and every required test shape

Before writing the formal pytest cases, every positive and adversarial shape
below was run interactively against the real function (not merely asserted
in prose) via a throwaway script, confirming each expected result exactly —
full transcript available on request, not reproduced verbatim here since the
pytest cases below are the durable, re-runnable record of the same checks:

| Input shape | Expected | Confirmed |
|---|---|---|
| Baseline multi-CTE (no quotes/comments) | `{a, b}` | yes |
| Real CTE after a single-quoted literal containing `WITH fake AS (` | `{real_cte}` only | yes |
| Real CTE after a doubled-quote-escaped literal containing the decoy | `{real_cte}` only | yes |
| CTE before an unclosed literal later in the text | kept (`{a}`) | yes |
| Unclosed literal with no real CTE anywhere | `{}` | yes |
| Real CTE after a `--` line-comment decoy | `{real_cte}` only | yes |
| Real CTE after a `/* */` block-comment decoy | `{real_cte}` only | yes |
| Unclosed block comment | `{}` | yes |
| Nested block comment (`/* outer /* decoy */ still open */`) | decoy hidden, real CTE after it collected | yes |
| Unbalanced parens inside a literal in a real CTE's own body | body end located correctly, no sweep into trailing text | yes |
| Unbalanced parens inside a comment in a real CTE's own body | same | yes |
| Backslash-escaped quote (`E'...\'...'`) decoy | does not close early; real CTE after it collected | yes |
| `RECURSIVE` (pre-existing disclosed gap) | still `{}` — unaffected by this increment | yes |
| Pre-existing depth-1 adversarial case (requirement 5 from the prior report) | still `{}` — unaffected | yes |

## Tests added

16 new test functions in `tools/tests/test_validate_architecture_gates.py`,
in a new `GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05` section inserted
directly after the existing 9 `_collect_cte_names` tests and before
`test_module_deps_cli_exit_codes_and_no_skip_flag`, matching that section's
own style (calling the pure function directly, no fixture tree):

**Positive (must still find/keep the real binding):**
1. `test_cte_recursive_still_not_recognised_lexical_hardening_is_orthogonal`
   — baseline guard: this increment must not accidentally start recognising
   `RECURSIVE`.
2. `test_cte_real_binding_after_single_quoted_text_is_still_collected` —
   real CTE after a single-quoted decoy literal.
3. `test_cte_real_binding_after_line_comment_is_still_collected` — real CTE
   after a `--` line-comment decoy.
4. `test_cte_real_binding_after_block_comment_is_still_collected` — real
   CTE after a `/* */` block-comment decoy.
5. `test_cte_doubled_quote_escape_inside_literal_does_not_close_early` —
   SQL's `''` escape inside the decoy must not expose the remaining decoy
   text as ordinary SQL; real CTE after it is the only binding.
6. `test_cte_nested_block_comment_per_postgresql_nesting_semantics` —
   PostgreSQL's real nesting behaviour, combined with a decoy inside the
   nested comment.

**Adversarial negative (must prove NO false binding):**
7. `test_cte_fake_with_inside_single_quoted_literal_produces_no_binding`
8. `test_cte_fake_with_inside_doubled_quote_escaped_literal_produces_no_binding`
9. `test_cte_fake_with_inside_unclosed_literal_produces_no_binding`
10. `test_cte_real_binding_before_unclosed_literal_is_still_kept` — fail-closed
    boundary: a real binding completed BEFORE the unclosed literal is kept;
    only scanning past the unclosed region stops.
11. `test_cte_fake_with_inside_line_comment_produces_no_binding`
12. `test_cte_fake_with_inside_block_comment_produces_no_binding`
13. `test_cte_fake_with_inside_unclosed_block_comment_produces_no_binding`
14. `test_cte_unbalanced_parens_inside_literal_in_real_cte_body_does_not_corrupt_depth`
    — depth corruption via literal, not false binding: an unbalanced paren
    inside a string literal INSIDE a real CTE's own body must not mislocate
    the body's real closing paren or sweep a trailing, unrelated table
    reference into the result.
15. `test_cte_unbalanced_parens_inside_comment_in_real_cte_body_does_not_corrupt_depth`
    — same hazard, via a comment instead of a literal.
16. `test_cte_backslash_escaped_quote_inside_literal_does_not_close_early` —
    the `E'...\'...'` false-binding risk the "Design decision" section
    above specifically closes.

All 16 assert on `_collect_cte_names`'s return value directly; none drive it
through `run_module_deps_gate` or any fixture tree.

## Test and Ruff results

**Before this session's change** (baseline, repeated for side-by-side
comparison):
```
159 passed in 1.92s
ruff check ...: All checks passed!
```

**After this session's change:**
```
source backend/.venv/bin/activate && python3 -m pytest tools/tests/test_validate_architecture_gates.py -q
175 passed in 1.87s
```
175 = 159 baseline + 16 new test functions, zero regressions, zero failures.

```
ruff check tools/tests/test_validate_architecture_gates.py tools/validate_architecture_gates.py
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

## Full lexical-shape table (handled / fail-closed / residual)

| Shape | Status | Reasoning |
|---|---|---|
| Single-quoted literal, ordinary (`'...'`) | **Handled** | `_skip_single_quoted_literal`, new this session. |
| Single-quoted literal, doubled-quote escape (`'it''s'`) | **Handled** | Same function, explicit `''`-lookahead branch. |
| Single-quoted literal, unclosed to EOF | **Fail-closed** | Returns `None`; both call sites stop scanning entirely from that point (`_collect_cte_names` keeps everything already collected; `_skip_balanced_parens` reports the enclosing body as unbalanced) — never guessed closed, never a false binding. |
| Paren characters inside a single-quoted literal | **Handled** | Consumed as one atomic jump by `_skip_quote_or_comment`; never reaches the `(`/`)` depth-counting branches at all, in both the outer scan and `_skip_balanced_parens`. |
| `--` line comment | **Handled** | `_skip_line_comment`, new this session; always well-defined (ends at `\n` or EOF). |
| `/* */` block comment, non-nested | **Handled** | `_skip_block_comment`, new this session. |
| `/* */` block comment, nested (PostgreSQL semantics) | **Handled** | Verified against the live PostgreSQL docs this session (see above); depth-counted, not first-`*/`-wins. |
| `/* */` block comment, unclosed to EOF | **Fail-closed** | Returns `None`; same stop-scanning behaviour as an unclosed literal. |
| Paren characters inside a comment | **Handled** | Same atomic-jump mechanism as the literal case. |
| `E'...'` escape strings — the specific `\'` premature-close risk | **Handled** | Closed by the universal backslash-skip in `_skip_single_quoted_literal` (see "Design decision" above), verified live. |
| `E'...'` escape strings — decoded escape *meaning* (`\n`, `\xNN`, `\uNNNN`, octal) | **Residual, by design, and safe** | This function's output never depends on a literal's decoded value, only on where it ends; the universal backslash-skip only needs to know "skip exactly one character after a backslash," never what that character means, to stay correct for this purpose. |
| Dollar-quoted strings (`$$...$$`, `$tag$...$tag$`) | **Residual** | Not recognised as a lexical region at all — explicitly out of this increment's required-hardening scope per the dispatching task (listed only in the "honestly document" list, not the "required hardening" list). Deceptive text inside one is treated as ordinary SQL text; this is a real, disclosed gap a future increment must close before this helper could safely be wired in. |
| Unicode-escape identifiers (`U&"..."`, `U&'...'`) | **Residual, partially benign** | A `U&"..."` form is lexed as an ordinary double-quoted segment by the pre-existing `_lex_quoted_segment` (unchanged); a `U&'...'` form is lexed as an ordinary single-quoted literal by this session's new function. Both close correctly at the real terminating quote in the common case, but neither path recognises or validates a trailing `UESCAPE` clause, and the `U&` prefix itself is not specially distinguished from a bare `&` operator or similar text immediately before the quote. |
| Double-quoted identifiers (`"..."`, including escaped embedded `"`) | **Handled — pre-existing, unchanged** | `_lex_quoted_segment`, already present before this increment; both call sites check for `"` before ever reaching the new dispatcher, so this session did not touch this path. |
| `RECURSIVE`, post-name column list, `[NOT] MATERIALIZED` | **Fail-closed — pre-existing, unchanged, out of this increment's scope** | Disclosed in the prior report; untouched by this session; the three new interactive-verification cases above confirm `RECURSIVE` is unaffected. |

## Confirmation: helper remains unwired; nothing out-of-scope touched

- **Unwired, confirmed by execution, not inspection alone:**
  `grep -n "_collect_cte_names(" tools/validate_architecture_gates.py`
  returns exactly one match — the function's own `def` line. No caller
  exists anywhere in the module, including `_scan_sql_text`, whose function
  body was re-read in full this session and is byte-identical to before
  (confirmed by direct comparison against the text quoted in the prior
  helper report).
- **`_scan_sql_text` untouched.** Confirmed by direct re-reading: its
  docstring and body are unchanged; it still passes `attribute_table_identifier`
  the default empty `cte_names`, exactly as before.
- **D6 trigger/I-1 work, byte counts/pins, D4/D5/D7/D8, D1b/D2, CI config,
  the real-tree manifest, SCN-MOD001-070, and DOM-002** were not read or
  touched by this session.
- **No P0 or scenario was marked PASS.** Scenarios 006/007/095/096 were not
  touched, inspected for promotion, or claimed closed — they remain context
  only, as instructed.
- **No review was performed or requested** by this session. This is an
  implementation record, not an independent review.
- **Nothing was committed, pushed, staged, or stashed.** `git status --porcelain
  tools/` shows both touched files still as untracked (`??`), identical to
  their state before this session (no prior commit exists for either to
  diff against); the pre-existing unrelated modified files
  (`tools/tests/test_validate_migration_ordering.py`,
  `tools/validate_capability_manifest.py`,
  `tools/validate_migration_ordering.py`) are confirmed untouched by this
  session (git status identical to the session's starting snapshot for
  those three files).
- **WIP=1 preserved; MOD-001 only.** No other module's files were read or
  edited.

## Residual risk a future wiring increment must address

Before `_collect_cte_names` is ever wired into `_scan_sql_text` (explicitly
not attempted here or previously), a future increment must at minimum:

1. Close or explicitly accept the dollar-quoted-string gap above — a
   dollar-quoted function body is common PostgreSQL usage (`CREATE FUNCTION
   ... AS $$ ... $$`) and is exactly the kind of text that could contain
   arbitrary, deceptive `WITH fake AS (` content completely unseen by this
   helper today.
2. Decide and test the `RECURSIVE` / column-list / `MATERIALIZED` gaps
   (pre-existing, re-confirmed unaffected this session) — these are real
   PostgreSQL CTE forms a live codebase could use, and each currently
   degrades to a missed, safe-direction binding, not a crash.
3. Decide the exact "same statement" scope the live scanner should pass to
   `_collect_cte_names` (named as still-open in the original helper report)
   — this hardening increment does not resolve that design question, only
   the lexical-safety question of what happens once that scope of text is
   handed to the helper.
4. Confirm, with a live drill rather than reasoning alone (as this session
   did for the backslash/nesting decisions), that the `Unicode-escape
   identifiers` residual above cannot be combined with another gap to
   produce a false binding before relying on it in a release-blocking gate.

None of the above was attempted in this session; they are recorded here so a
future increment does not have to re-derive them from scratch.
