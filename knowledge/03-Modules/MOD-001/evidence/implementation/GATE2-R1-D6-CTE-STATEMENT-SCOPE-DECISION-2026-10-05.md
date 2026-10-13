# GATE2-R1-D6-CTE-STATEMENT-SCOPE-DECISION-2026-10-05 — statement-scoped
# live wiring design for ADR-011 D3.2 state 3 (CTE-local attribution)

> ## ⚠️ PARTIALLY SUPERSEDED — 2026-10-05
>
> **Two of this record's stated invariants are wrong and one required
> disclosure sentence is false. Read
> [`GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md`](GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md)
> before implementing anything from this record.**
>
> - **§3 I-2's consequence clause** ("No identifier that is non-zero
>   under today's (empty-set) behaviour becomes clean") is **FALSE** —
>   falsified by execution, and contradicted by this record's own T3.
>   Superseded by I-2a/I-2b.
> - **§3 I-1's justification** ("holds independently of whether the
>   lexer's skip decisions are correct") is **withdrawn as stated** — it
>   covers only the lexer-over-skip direction, not the false-cut
>   direction this record's own §5 row 3 rejects an alternative over.
>   Superseded by I-1′/I-1″ plus the named, unproven **Lemma L**.
> - **§2.5's disclosure sentence** and **§4's decline-table "Why decline
>   is safe" column** ("a declined binding degrades to state 6 ERROR,
>   never to a clean state") are **FALSE** in 3 of 4 shapes. Replacement
>   text is in the correction's §2.1 — use that verbatim, not §2.5's.
> - **§7 residual 4's** "never a false clean" is no longer true once
>   state 3 is live. See the correction's §4.
>
> The **chosen design (§2), rejected alternatives (§5), tests T1–T8 (§6),
> and residuals 2/3/5/6 (§7) stand unchanged.** The correction adds **T9,
> T10 and mutation control M5** as required, and amends the expectation
> on **M2**. Disposition: live wiring is **not** BLOCKED.

**Record class:** SUBORDINATE qualified architecture/engineering decision
record. **Not an ADR**, not an amendment to one, and not a review. It
decides one bounded design question that `ADR-011` D3.2 state 3 leaves to
the implementer: *what text constitutes "the same statement"* when the
CTE-name collection helper is wired into the live scanner. ADR-011
governs; where this record and ADR-011 could be read as differing on
schema or semantics, **ADR-011 governs** (its own Follow-up says so).

**Decided by:** `veyro-lead` (architecture/critical-engineering-decision
role, fresh bounded dispatch; `claude-opus-5[1m]`, as reported by this
environment). Not the gate-2 implementer, not a reviewer.

**Model attestation:** NONE RUN BY THIS SESSION. `mr_verify.py` was not
run against this dispatch's own transcript — self-attestation is of
little value and the tool belongs to the orchestrating session. Stated
rather than omitted.

**Fixture-scoped; real-tree domain ownership DEFERRED** (`ADR-011` scope
limit, carried on the face of this record as that ADR requires).

**Module / gate / slot:** MOD-001, `GOV-01-R04`, TSD §24.1 gate 2,
decision slot **D6 — CTE state 3 live wiring**. Scenarios in play:
`SCN-MOD001-006`, `-007`, `-095`, `-096` — **none promoted, none
executed, none claimed PASS by this record.**

**No code was edited by this session.** Every behavioural claim below was
established by executing the *current, unmodified* `tools/validate_architecture_gates.py`
helpers from a throwaway `/tmp` prototype that imported them read-only;
the prototype was removed and no repository file was written other than
this record.

## 1. Context and the exact governing clauses

### 1.1 The governing text

`ADR-011` **D3.2** — "Every identifier in a table position resolves to
exactly one of six states. The sixth is an ERROR, not a note." State 3 is
the clause this record implements:

> | 3 | Bound locally in the same statement (a `WITH` CTE name, collected
> lexically at depth 0) | clean, counted |

`ADR-011` **D3.2 state 6** — "Anything else" ⇒ **ERROR**
`MODULE_DEPS_TABLE_UNATTRIBUTED`. This is the state every identifier
falls into when a CTE binding is *declined*, and it is why declining is
always safe: declining can only move an identifier from a clean state to
a non-zero one, never the reverse.

`ADR-011` **D7.1** — `MODULE_DEPS_SOURCE_UNINSPECTABLE` applies iff
reduction to statements/tokens "failed or was impossible"; `MODULE_DEPS_TABLE_UNATTRIBUTED`
applies iff lexing succeeded and produced at least one identifier
resolving to none of states 1–5. The two are disjoint and the
discriminator is whether an identifier was actually extracted.

`ADR-011` **D8** — every run including PASS must carry a coverage note
naming what is *not* examined, including the lexer's dialect limitation.

`ADR-011` **Follow-up / mutation controls** — "state 3's CTE collection
widened to accept any bare identifier as locally bound" must be killed by
a named test; "a surviving mutant is a **blocker for the dispatch**, not a
note."

**TSD §24.1 gate 2**, as quoted first-hand from the governing docx by
`ADR-011`'s Context section (this session did **not** independently
re-extract the docx; it relies on ADR-011's own verified quotation, which
that ADR records as checked against the docx and not only against
`TSD_MIRROR.md`):

> "Module dependency/SQL lint: application modules may reference only
> their owned table prefix/schema and approved read-model/application
> interfaces; cross-domain raw SQL/ORM imports fail CI."

The load-bearing property is the one ADR-011 already drew from it: §24.1
is written as an **allow-list**, so the gate may never let an
unrecognised identifier reach PASS. State 3 is one of only five clean
states, so state 3 must be *narrow*. An over-wide state 3 is a silent
allow-list extension — precisely the "unowned ⇒ benign note" failure
class (`R1-F01`) that ADR-011 D9 forbids in any form.

### 1.2 The live defect this decision exists to close

`GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05.md` records the pure helper
`_collect_cte_names` at 193/193 tests, hardened against single-quoted
literals, line comments, nested block comments, double-quoted
identifiers, and ASCII/empty/Unicode-tagged dollar-quoted strings — and
**still UNWIRED**. Its own residual risk #4 names the open question
precisely: "the exact 'same statement' scope the live scanner should pass
to `_collect_cte_names` remains an open design question."

The naive wiring — pass the whole file or the whole Python string literal
to `_collect_cte_names` and hand the result to every identifier — is
**unsound**, and this session reproduced that by direct execution against
the current code:

```
_collect_cte_names(
  "WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;"
  " SELECT * FROM bil_scratch")
-> frozenset({'bil_scratch'})

_extract_table_identifiers(same text)
-> ['bil_scratch', 'bil_scratch']
```

Both occurrences would receive the same CTE set. The second one is a
reference to a *real table* in a *different statement* — owned by another
module under any manifest where `bil_` is an owned prefix — and it would
be marked state 3 "clean, counted". That is a false clean on a
cross-domain reference: the exact outcome §24.1 says must fail CI. The
extractor compounds it by yielding **bare names with no offsets**, so
today there is no information in the call chain with which to tell the
two apart.

## 2. The chosen design

**Chosen method: (i) lexical per-statement segmentation plus
per-statement extraction and attribution, with a one-expression
per-segment trust predicate as the soundness net.** No offsets, no new
lexer, no parser.

### 2.1 New pure helper — `_split_sql_statements`

Place immediately after `_skip_balanced_parens` in
`tools/validate_architecture_gates.py`.

```
_split_sql_statements(text: str) -> list[str] | None
```

It walks `text` character-by-character using **exactly the same
three-branch composition `_collect_cte_names` and `_skip_balanced_parens`
already use** — no second lexer is introduced:

1. `text[i] == '"'` → `_lex_quoted_segment(text, i)`. `None` ⇒ return
   `None` (unterminated double-quoted identifier).
2. Otherwise `_skip_quote_or_comment(text, i)`. `None` ⇒ return `None`
   (unterminated single-quoted literal, unterminated block comment, or
   unterminated dollar-quoted string). A returned index `!= i` ⇒ jump to
   it and continue (the region is skipped atomically; nothing inside it
   is ever inspected).
3. Otherwise: `(` increments a depth counter; `)` decrements it with
   `max(0, depth - 1)`; and **`;` at `depth == 0`** closes the current
   segment at `text[start:i]` (the `;` itself is *excluded* from both
   segments) and starts the next at `i + 1`.

After the loop, append the final `text[start:]`. A single-statement text
therefore returns a one-element list, and `len(result) - 1` is exactly
the number of cuts made.

`;` at `depth > 0` is deliberately **not** a cut: a semicolon inside
parentheses is not a statement terminator in SQL. Such a semicolon is
then a non-terminator semicolon inside a segment, which the trust
predicate below handles.

### 2.2 New pure helper — `_cte_scopes`

Place immediately after `_collect_cte_names`.

```
_cte_scopes(text: str) -> list[tuple[str, frozenset[str]]]
```

```
segments = _split_sql_statements(text)
if segments is None:
    return [(text, frozenset())]                       # decline, whole text
return [(seg, frozenset() if ";" in seg else _collect_cte_names(seg))
        for seg in segments]
```

**The trust predicate is `";" not in seg`, and that is the whole
mechanism.** It is correct *because of* how segmentation works: every cut
consumes exactly one `;` and excludes it from both neighbours, so a
segment can only contain a `;` that the lexer judged to be inside a
quoted string, a comment, a dollar-quoted body, a double-quoted
identifier, or inside parentheses. Any such segment is one where the
lexer's skip decisions are load-bearing for *where the statement
boundary is* — so its bindings are declined.

### 2.3 The change to `_scan_sql_text`

Everything above the attribution loop is **unchanged, deliberately**:
`_is_sql_ish(text)`, `_dangling_keywords(text)`,
`idents = _extract_table_identifiers(text)`, and the whole D6.3 I-1
zero-table backstop block all keep operating on the **whole** text, so
`GATE2-R1-D6-TRIGGER-I1-2026-10-05`'s behaviour is provably untouched by
this increment. Only the final loop changes:

```
    for ident in idents:                                   # REMOVE
        outcome = attribute_table_identifier(ident, modules, importer,
                                             default_schema)
```
becomes
```
    for segment, cte_names in _cte_scopes(text):
        for ident in _extract_table_identifiers(segment):
            outcome = attribute_table_identifier(ident, modules, importer,
                                                 default_schema, cte_names)
```

The violation/unattributed append branches inside the loop are copied
verbatim; nothing about their wording, codes, or `loc` values changes.
`attribute_table_identifier`'s signature already carries
`cte_names: frozenset[str] = frozenset()` as its fifth parameter — **no
signature change is needed anywhere**, and `_extract_table_identifiers`
keeps returning bare names.

### 2.4 Both required input shapes are covered by the same code

`run_module_deps_gate` calls `_scan_sql_text` from exactly two places
(verified this session):

- **(a) a `.sql` file** — `kind == "sql"`, whole file text, one call per
  file (line ~2789). A multi-statement `.sql` file is segmented by
  `_cte_scopes` and each statement gets its own binding set.
- **(b) a Python string literal** — every `ast.Constant` `str` node, one
  call per literal, `loc = f"{relpath}:{node.lineno}"` (line ~2820).
  Docstring positions are excluded upstream per D6.4. A literal holding
  several statements is segmented identically.

No per-shape branching is added. The segmentation unit is "the text
handed to `_scan_sql_text`", and a Python literal is simply a text with
its own independent statement list — a CTE in one literal can never
reach another literal, because the two are never in the same string.

### 2.5 Required disclosure (ADR-011 D8)

Add one sentence to `run_module_deps_gate`'s coverage note, in the same
increment, so a PASS stays self-evidencing: CTE-local attribution
(D3.2 state 3) is **statement-scoped** — bindings are collected
per lexically-segmented statement, and are **declined** for any statement
containing a semicolon that is not its own terminator, and for any text
that cannot be lexically segmented at all; a declined binding degrades to
state 6 ERROR, never to a clean state.

## 3. Invariants (checkable propositions)

Let `T` be the text passed to `_scan_sql_text`, `S = _cte_scopes(T)`, and
for a segment `s` let `N(s)` be its bound set.

- **I-1 (the hard invariant — no cross-statement suppression).** For any
  two distinct real statements `A` and `B` in `T`, no name bound by a
  `WITH` clause in `A` is ever applied to an identifier extracted from
  `B`. *Mechanism:* names applied to identifiers in `s` come only from
  `N(s)`; if the lexer ever merged `A` and `B` into one `s`, the real `;`
  between them is inside `s`, so `";" in s` and `N(s) = frozenset()`.
  **I-1 therefore holds independently of whether the lexer's skip
  decisions are correct**, which is what makes it an invariant rather
  than a hope.
- **I-2 (declining is monotone fail-closed).** `N(s) ⊆
  _collect_cte_names(s)` for every `s`, and for every identifier the set
  handed to `attribute_table_identifier` is a subset of what the naive
  whole-text wiring would hand it. Consequence: this design can only move
  an identifier **out of** state 3 and into states 1/2/6 — never into
  state 3 from outside. No identifier that is non-zero under today's
  (empty-set) behaviour becomes clean.
- **I-3 (segmentation totality).** When `_split_sql_statements` returns a
  list, `";".join(segments) == text` and `len(segments) - 1` equals the
  number of depth-0 cuts. Every character of `T` lies in exactly one
  segment or is a cut semicolon. No text is dropped from scanning.
- **I-4 (trust predicate soundness).** A segment is trusted iff it
  contains no `;` at all. Equivalently: a trusted segment's boundaries
  were established without any lexical-region judgement about a
  semicolon.
- **I-5 (extraction equivalence).** For every `T`, the multiset
  `⋃_s _extract_table_identifiers(s)` equals
  `_extract_table_identifiers(T)`. **Verified by execution** over this
  record's whole 10-input corpus (HOLDS, no divergence). It can only fail
  where a cut lands strictly between a table-position keyword and its
  identifier, in which case neither form yields an identifier. This is
  the proposition that makes "keep the I-1 backstop on whole text, attribute
  per segment" safe rather than merely convenient, so it is a **required
  test**, not an assumption.
- **I-6 (purity).** `_split_sql_statements` and `_cte_scopes` perform no
  I/O, no mutation of any argument, and are deterministic — same input,
  same output, matching every other helper in this section.

## 4. Fail-closed behaviour: what ERRORs, what declines, and why

**Nothing in this design introduces a new error code or a new ERROR
condition.** That is a deliberate choice, and it is the reason no ADR
amendment is required.

**Conditions that DECLINE the binding (return `frozenset()`), by design:**

| Condition | Scope of the decline | Why decline is safe |
|---|---|---|
| Segment contains a non-terminator `;` (inside a literal, a line/block comment, a dollar-quoted body, a double-quoted identifier, or inside parens) | that segment only | The identifier falls to state 1/2/6. A real table reference is never clean; a genuine CTE reference becomes a loud state-6 ERROR |
| `_split_sql_statements` returns `None` (unterminated literal / block comment / dollar-quoted string / double-quoted identifier) | the whole text, as one scope | Same: zero bindings suppress nothing |
| `_collect_cte_names` itself fails closed on a trusted segment (`WITH RECURSIVE`, `WITH cte(a, b) AS`, `[NOT] MATERIALIZED`, unbalanced body) | that binding only | Pre-existing, already-disclosed helper behaviour, unchanged by this increment |

**Conditions that ERROR:** exactly the ones ADR-011 already defines, via
the already-wired paths. A declined CTE identifier that no module owns
reaches **D3.2 state 6 ⇒ `MODULE_DEPS_TABLE_UNATTRIBUTED`, ERROR, exit
2**. A dangling keyword or an unextractable table position still reaches
`MODULE_DEPS_SOURCE_UNINSPECTABLE` through the untouched whole-text
checks. D7.1's disjointness is preserved because this increment never
changes *whether* an identifier was extracted — only which set it is
attributed against.

**Why declining rather than ERRORing on unlexable text.** Promoting a
segmentation failure to `MODULE_DEPS_SOURCE_UNINSPECTABLE` was considered
and rejected: `_scan_sql_text` reaches every `ast.Constant` string in the
tree, and any ordinary English string containing a trigger verb and an
apostrophe ("don't SELECT from the table") would then become a hard
ERROR. That is the false-ERROR-on-prose class ADR-011 D6.4 explicitly
refuses to create ("a false `CROSS_DOMAIN_SQL_IMPORT` on English prose is
worse than the residual"), and D6.3 refuses for the same reason. Since
declining is *already* strictly fail-closed by **I-2**, ERRORing buys no
soundness and costs real precision. The invariant the task sets — "must
NEVER silently treat a raw table reference as clean" — is satisfied by
**I-2**, not by an added ERROR: a declined binding cannot clean anything,
because state 3 is the *only* thing a CTE name does.

## 5. Rejected alternatives

| Alternative | Reason rejected |
|---|---|
| **(ii) Span/offset-aware attribution** — change `_extract_table_identifiers` to yield `(name, offset)`, record each CTE binding's span, attribute by containment | Rejected. It changes the extractor's signature and therefore every call site and its existing tests, for no additional soundness: the invariant becomes a *computed* property over offset arithmetic (off-by-one, nested-span, and overlapping-binding judgement calls) instead of the *structural* property I-1 gives for free. ADR-011's own seam note keeps `_extract_table_refs(text)` text-in/refs-out precisely so a future parser swap touches one function; widening it to offsets closes that seam |
| **Pass the whole file/string to `_collect_cte_names` and use the result globally** (today's naive wiring) | Rejected — this is the defect. Reproduced live in §1.2: a CTE in statement A silently cleans a same-named real table in statement B |
| **Split on every raw `;`, no lexing** | Rejected, and it is actively unsafe. A cut inside a single-quoted literal drops the opening quote, so the tail fragment re-lexes standalone with a depth-0 `WITH fake AS (` and yields a **false** binding — re-opening exactly the class `GATE2-R1-D6-CTE-DOLLAR-QUOTE` and `-UNICODE-DOLLAR` closed |
| **Global reconciliation: compare `text.count(";")` against the cut count and decline for the entire text on mismatch** | Rejected as needlessly blunt. It is equally sound, but one `;` inside one comment or one plpgsql body would decline bindings in *every* statement of the file. Verified live: under this rule the chained-CTE statement in `"SELECT ... 'a;b'; WITH c AS (...) SELECT * FROM c"` loses its legitimate binding, whereas the per-segment predicate keeps it. Same guarantee, strictly worse precision, and one more piece of bookkeeping |
| **Union of raw and lexical cut points, with segments marked trusted/untrusted by which cut produced them** | Rejected. It is sound and marginally more precise than the chosen rule in some shapes, but requires maintaining two cut lists plus a per-boundary provenance flag — three times the state for a precision gain no current fixture needs. Recorded here as the named follow-up if a real fixture ever demands it |
| **Adopt a third-party SQL parser (`sqlglot`/`pglast`/`sqlparse`) to segment statements** | Rejected — `ADR-011` D9 forbids it in this contract; it is a `CAPABILITY_POLICY.md` capability (CAP-009 candidate) with a registry row, and `BUG-038` is this project's own precedent for the cost of skipping that lifecycle |
| **Write a general SQL parser in-tree** | Out of bounds by the dispatch and by D9's reasoning. The chosen design adds ~25 lines reusing the existing dispatcher |
| **Leave the helper unwired and disclose the gap** | Rejected. D3.2 state 3 is a named clean state in a binding contract; leaving it permanently unreachable means every legitimate CTE reference in fixture SQL is a state-6 ERROR, which is the pressure-to-weaken-the-gate dynamic D6.3 was corrected to avoid |

## 6. REQUIRED tests (synthetic fixtures only — no real member data)

All inputs below are synthetic SQL strings written for this purpose.
Pure-helper tests assert on `_cte_scopes` directly, matching the existing
`_collect_cte_names` test style; live tests drive
`run_module_deps_gate` through the existing `_md_run` / `_md_module` /
`_md_entry` / `_md_base_modules` fixture harness. Place all of them in a
new `GATE2-R1-D6-CTE-STATEMENT-SCOPE-2026-10-05` section. Every one of
the eight must pass, and tests 3 and 6's controls are what make the
others non-vacuous.

**T1 — `test_cte_binding_is_not_visible_to_a_later_statement`** (pure).
Input `"WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;"
" SELECT * FROM bil_scratch"`. Assert `len(scopes) == 2`,
`scopes[0][1] == frozenset({"bil_scratch"})`, and
`scopes[1][1] == frozenset()`. Second input
`"WITH a AS (SELECT 1), b AS (SELECT * FROM a) SELECT * FROM b;"
" SELECT * FROM a"` (chained CTEs): assert `scopes[0][1] ==
frozenset({"a", "b"})` and `scopes[1][1] == frozenset()`. Third input
`"WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r; SELECT * FROM r"`:
assert **both** scopes are empty — `RECURSIVE` fails closed rather than
binding. This is the I-1 lock.

**T2 — `test_live_same_named_table_in_second_statement_is_not_suppressed`**
(live, input shape (a)). `membership` module with
`reports.sql` = `"WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;\n"
"SELECT * FROM bil_scratch;\n"`; manifest `membership` ⇒ `MEM-01`/`membership_`,
`billing` ⇒ `BIL-02`/`bil_` (plus a `billing/interface.py` stub, as the
sibling wiring tests do). Assert `report.status == FAIL` and that some
`CROSS_DOMAIN_SQL_IMPORT` violation's detail names `bil_scratch` and
`billing`.

**T3 — `test_live_single_statement_cte_reference_is_clean_control`**
(live, non-vacuity control for T2 and the first live proof that state 3
is reachable at all). Identical fixture with the second statement
removed: `reports.sql` = `"WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;\n"`.
Assert `report.status == PASS` and `not report.violations`. **If this
test does not currently FAIL before the wiring lands and PASS after, the
wiring is not actually live** — it must be run in both directions and the
result recorded.

**T4 — `test_live_python_string_literal_cte_scope_is_statement_scoped`**
(live, input shape (b)). `membership/queries.py` containing a
module-level assignment — **not** a docstring, which D6.4 excludes:
`QUERY = "WITH bil_scratch AS (SELECT 1) SELECT * FROM bil_scratch;"
" SELECT * FROM bil_scratch"` (plus one trivial statement so the module
is substantive). Same manifest as T2. Assert `report.status == FAIL`,
a `CROSS_DOMAIN_SQL_IMPORT` naming `bil_scratch`, and that its `loc`
carries the `queries.py:<lineno>` form.

**T5 — `test_semicolon_inside_quoted_string_declines_only_its_own_statement`**
(pure). Input `"SELECT * FROM t WHERE x = 'a;b'; WITH c AS (SELECT 1)"
" SELECT * FROM c"`. Assert `len(scopes) == 2`; `";" in scopes[0][0]`
and `scopes[0][1] == frozenset()` (the hidden semicolon did **not** cut,
and that statement's bindings are declined); and
`scopes[1][1] == frozenset({"c"})` (the decline is statement-local, not
global). Assert additionally that neither scope's text equals the whole
input — i.e. the real `;` was the only cut.

**T6 — `test_semicolon_inside_line_comment_declines_binding_fail_closed`**
(live + its control, input shape (a)). `reports.sql` =
`"-- cleanup; later\nWITH scratch_cte AS (SELECT 1) SELECT * FROM scratch_cte;\n"`
with `_md_base_modules()` (nobody owns `scratch_cte`). Assert
`report.status == ERROR`, `report.codes() == {"MODULE_DEPS_TABLE_UNATTRIBUTED"}`,
and that a violation detail names `scratch_cte` — the declined binding
degrades to a loud state-6 ERROR, never to clean. **Control, same test:**
the identical file with the semicolon removed from the comment
(`"-- cleanup later\n..."`) must return `PASS` with no violations. The
pair is what proves the decline is caused by the hidden semicolon and not
by something incidental.

**T7 — `test_dollar_quoted_body_semicolon_is_not_a_statement_cut`**
(pure). Input `"CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1;"
" END $$ LANGUAGE plpgsql; SELECT * FROM bil_x"`. Assert
`len(scopes) == 2` — proving the `;` inside the `$$ ... $$` body produced
**no** cut while the real `;` after `plpgsql` did; assert
`"bil_x" in scopes[1][0]` and `"CREATE FUNCTION" in scopes[0][0]`; assert
`scopes[0][1] == frozenset()` (that segment carries a non-terminator
semicolon, so it is untrusted). Add a `$tag$`-tagged variant of the same
shape to confirm the tagged form behaves identically.

**T8 — `test_extraction_equivalence_and_unlexable_decline`** (pure, the
I-5 and unlexable-decline lock). For each of the T1/T5/T7 inputs plus
`"SELECT * FROM t WHERE x = 'unterminated"` and
`"SELECT 'a\\'; WITH fake AS (SELECT 1) SELECT * FROM bil_t'"`, assert
`Counter(chain of _extract_table_identifiers(seg) for each scope) ==
Counter(_extract_table_identifiers(whole_text))` (I-5). Additionally
assert that the unterminated-literal input yields exactly one scope with
an empty binding set, and that the backslash-escape input yields **no**
`fake` binding in any scope — that second case is the adversarial
over-skip shape, and it is the direct demonstration that I-1 does not
depend on the lexer's skip decisions being right.

**Required mutation controls** (per `ADR-011`'s Follow-up — a surviving
mutant is a blocker for the dispatch, not a note). Run each in a
throwaway full-structure copy, never in the repository, and confirm the
repository files are byte-identical afterwards via `git status --porcelain tools/`:

- **M1:** make `_cte_scopes` return `[(text, _collect_cte_names(text))]`
  (the naive whole-text wiring). **T1 and T2 must fail.**
- **M2:** delete the `";" in seg` trust predicate (always trust).
  **T5 and T8's `fake` assertion must fail.**
- **M3:** make `_split_sql_statements` cut on every `;` regardless of
  lexical region. **T5 and T7 must fail.**
- **M4:** make `_split_sql_statements` never cut (always one segment).
  **T1 must fail.**

## 7. Residual risk and blockers

1. **A declined CTE binding can surface as `CROSS_DOMAIN_SQL_IMPORT`
   (FAIL) rather than `MODULE_DEPS_TABLE_UNATTRIBUTED` (ERROR)** when the
   CTE name happens to match another module's `owned_table_prefixes` —
   which is exactly the shape T2 and T3 use. Both outcomes are non-zero
   and loud, so the fail-closed property holds, but the FAIL names an
   owner for an identifier that was never that owner's table. ADR-011
   rejected treating state 6 as FAIL on the grounds that a FAIL "would
   have to name an owner it does not know"; this residual is the same
   concern arriving by a different route. Disclosed, not closed — closing
   it would require distinguishing "declined CTE" from "foreign table",
   which is offset-aware attribution (the rejected alternative (ii)).
2. **Precision cost, by construction.** Any statement containing a
   semicolon inside a comment, a string literal, a dollar-quoted body, a
   double-quoted identifier, or parentheses loses its CTE bindings. For
   fixture SQL this is the already-recorded ADR-011 consequence
   "existing fixtures may need re-expression"; for a plpgsql function body
   it is common, though T7 shows the cost stays inside the offending
   statement. The named, bounded follow-up is the union-cut/trust-flag
   alternative in §5 — **not** to be built speculatively.
3. **Every residual risk of the three prior D6 CTE records is carried
   forward unchanged and must be re-confirmed by the implementing
   session, not assumed:** `RECURSIVE` / column-list / `MATERIALIZED`
   non-recognition, `U&"..."`/`U&'...'`/`UESCAPE` partial coverage, the
   `str.isalpha()`/`str.isalnum()` approximation of PostgreSQL's
   encoding-dependent identifier rules, and the absence of any
   fuzz/property-based testing on the combined literal + comment +
   dollar-quote + segmentation surface. This decision widens the blast
   radius of that lexer from an unwired helper to a release-blocking
   gate path, so the fuzz item in particular is now more material than
   it was.
4. **`_extract_table_identifiers` still extracts from inside string
   literals and comments** (it is a pure regex over raw text; `FROM bil_x`
   inside a `--` comment is extracted and attributed). That is
   **pre-existing** behaviour, out of this slot's scope, and it errs in
   the loud direction (a false FAIL/ERROR, never a false clean). Named
   here so it is never mistaken for something this increment introduced
   or fixed.
5. **TSD §24.1 is cited at second hand.** This session relied on
   ADR-011's own first-hand docx quotation rather than re-extracting the
   governing docx itself. A reviewer who wants the citation
   independently verified should re-extract §24.1 from
   `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` directly.
6. **No ADR amendment is required, and this record does not make one.**
   D3.2 state 3's clause is implemented literally — "bound locally in the
   same statement" — and this design is what *defines* "the same
   statement" lexically, which D3.2 leaves to the implementer. Where the
   trust predicate declines, state 3 is reached in **fewer** cases than a
   maximally generous reading of the clause would allow; ADR-011 already
   establishes that under-approximating state 3 is in-contract and merely
   disclosed, both through the helper's existing `RECURSIVE`/column-list
   limitations and through its Consequences section ("additional
   fail-closed paths, not new defects"). Nothing here widens a clean
   state, adds an outcome code, changes the manifest schema, alters D7's
   taxonomy, or touches D9's prohibitions. **If a reviewer concludes the
   trust predicate narrows D3.2 state 3 so far as to make the clause
   effectively unreachable in practice, that is a finding against
   ADR-011 for `veyro-lead` to amend — raise it as such rather than
   widening the predicate in implementation.**

**Unresolved blocker: NONE.** Real-tree domain ownership remains
`BLOCKED: OWNER_APPROVAL_REQUIRED` and is untouched; it is not a
dependency of this design, which operates entirely on fixture trees.

## 8. Explicitly not done by this session

- No code, test, CI, capability-manifest, `SCN-070`, or `DOM-002` edit.
  No file was written other than this record.
- No independent review verdict, no review-round increment, no
  `REVIEW_IN_FLIGHT.md` claim.
- No scenario PASS, no P0 closure, no promotion of
  `SCN-MOD001-006/-007/-095/-096`.
- No `git` add/commit/push, no branch change.
- No edit to `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`,
  or `ADR-011`.
- No owner-reserved action: no spend, no real member data, no production
  deploy, no material product/pricing/business/scope change.
