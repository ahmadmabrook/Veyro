> **ORCHESTRATOR QUALIFICATION HOLD — 2026-10-05.** This report was written by a top-level Claude ACP turn, not an observed `veyro-lead` named subagent: transcript `4db03185-076b-4cd5-b948-122f7a42ea5f.jsonl` has `isSidechain=false`, no `agentId`, and no Task delegation. Independent `mr_verify.py` confirms **33/33 claude-opus-5 turns**, which attests the model tier only, not the governed named role. The report's "Decided by veyro-lead" attribution is therefore **unverified**. Its correction and "live wiring may proceed" disposition remain provisional; do not wire CTE state 3 until a bounded named `veyro-lead` qualification resolves the role/proof gap, including the report's expressly unproven Lemma L. No review or scenario verdict is inferred.

> **RESIDUAL-CLAIM SUPERSESSION QUALIFICATION — 2026-10-05.** Sections §3.2, §4, §5, and §6 below still read as live, current obligations resting on this record's own two-function Lemma L / T9/T10 design, which two subsequent bounded named-`veyro-lead` dispatches found superseded: `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md` ("LEAD-QUALIFICATION", verdict BLOCKED) and `GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md` ("SEQUENCING"). This notice reconciles the sections below against those two records only. It supplies no new architecture judgment, resolves no open question either record left open, and changes no review verdict, scenario verdict, promotion status, or hold status.
>
> | Section | Reconciliation |
> |---|---|
> | **§3.2** — Lemma L / I-1′ / I-1″, "promoted to a required test with a structural guard (T9/T10)" | LEAD-QUALIFICATION §2(a) Finding 2 (decisive): Lemma L's stated mechanism — that `_collect_cte_names` "walks the same text with the same three-branch dispatch in the same order" as the designed splitter — is false against the source in both directions. `_collect_cte_names` (`tools/validate_architecture_gates.py:2667-2704`, per LEAD-QUALIFICATION) has the three lexical-region branches plus `(`/`)` depth bookkeeping plus a fourth, depth-0 `WITH` branch that jumps the cursor via `_parse_cte_binding_list`/`_skip_balanced_parens` (`:2546-2583`, per LEAD-QUALIFICATION); the designed splitter (§2.1 below) has no `WITH` branch and adds a `;`-at-depth-0 cut branch `_collect_cte_names` lacks (LEAD-QUALIFICATION §2(a) Finding 2). Separately, `_split_sql_statements` does not exist anywhere in the source (SEQUENCING §(f), "Verified first-hand") — the two-function §2.1/§2.2 design was BLOCKED and replaced by the one-pass `_cte_scopes`; the §3.1 notice above cites that function at `tools/validate_architecture_gates.py:2704-2718`, SEQUENCING §(f) cites `:2725-2855` — each range attributed only to the record that states it, neither re-derived here. Under the one-pass design, Lemma L's segmentation half is "vacuous by construction... there is no two-function agreement property left to prove" (LEAD-QUALIFICATION §2(b) option 1; SEQUENCING §(f) "Not done, and not proven"). |
> | **§4** — consequential-corrections table rows resting on I-2a/Lemma L | The same Finding-2 falsification applies to every row whose cited support is I-2a/Lemma L. T9 itself is not swept up in that falsification: SEQUENCING §(a) T9 row records that T9 is "*more* necessary under the one-pass design, not less" because `_cte_scopes` has `WITH`-jump / `;`-cut / depth interactions `_collect_cte_names` does not — it is Lemma L's segmentation claim that goes vacuous, not T9's comparator property. |
> | **§5** — "The one condition for proceeding", T9/T10/M5, "Live wiring may proceed" | **Not in force.** LEAD-QUALIFICATION §2 returns verdict **BLOCKED** and states: "The hold is not lifted." Its §2(b) closing note records that this record's own `veyro-lead` role attribution "remains unverified" and that this record's "live wiring may proceed" disposition "stays provisional and is not inherited here." T10 and M5 are **obsolete by construction** and must not be carried forward as outstanding obligations by any future session — SEQUENCING's T10 note under §(a) ("obsolete by construction... the lead qualification §2(b)(1) anticipated exactly this ('T10/M5 become unnecessary rather than under-scoped')") and LEAD-QUALIFICATION §2(b)(1) itself. |
> | **§6** (item 1, "§6.1") — "Lemma L is unproven... fuzz-supported (300k+8, zero falsifications)... test-guarded by T9/T10" | The 300k+8 figure is **historical only** and supplies no support for today's one-pass design — see the existing §3.1 notice above (narrowed count, unreproducible, non-transferable to the one-pass design); not restated here. "Test-guarded by T9/T10" no longer describes the current state: T10 is obsolete by construction (§5 row above). T9 remains live and current — *more* necessary, per SEQUENCING §(a), under the one-pass design than under the superseded two-function one — with the newly constructed replacement false-cut seed and resulting **217/217** focused PASS recorded exactly as the existing §3.1 notice above already states them (`GATE2-R1-D6-T9-SEED-RECONCILIATION-2026-10-05.md` §2; `GATE2-R1-D6-T9-REPLACEMENT-SEED-VERIFICATION-2026-10-05.md`, both as named in §3.1). Separately, SEQUENCING §(a)/(e) dispose the named test function `test_segment_bindings_are_a_subset_of_whole_text_bindings` itself as "LANDABLE-GREEN-NOW — absent from the repo." That observation and the §3.1 notice's "standing pure T9 corpus"/217-PASS language are sequential rather than in tension: the function was absent from the repo as of that sequencing decision, and has subsequently landed and is current — `tools/tests/test_validate_architecture_gates.py:3527` defines `test_cte_scopes_segment_bindings_are_a_subset_of_whole_text_bindings`, carrying the replacement false-cut seed and 217/217 focused-PASS record exactly as §3.1 above states them. Nothing further is claimed here: the historical eight-seed prototype corpus is not reproduced, and no review verdict, scenario verdict, or PASS is inferred. |
>
> Nothing above is a new finding; every sentence traces to LEAD-QUALIFICATION or SEQUENCING as cited, and neither record's open questions (LEAD-QUALIFICATION §2(b)'s smallest-next-subgoal list; SEQUENCING's own step 3 ADR-011 D3.2/D9 adjudication) are answered here.

# GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05 — superseding
# correction to the D6 statement-scope decision's invariants I-1 and I-2

**Record class:** SUBORDINATE qualified architecture/engineering decision
record — a **correction that supersedes** `GATE2-R1-D6-CTE-STATEMENT-SCOPE-DECISION-2026-10-05.md`
§3's invariants I-1 and I-2 and §2.5's required disclosure sentence.
**Not an ADR**, not an amendment to one, not a review, not a scenario
result. `ADR-011` governs; where this record and ADR-011 could be read as
differing, **ADR-011 governs**.

**What is superseded, precisely:** the decision record's **I-1**
justification clause ("holds independently of whether the lexer's skip
decisions are correct"), its **I-2** consequence clause ("No identifier
that is non-zero under today's (empty-set) behaviour becomes clean"), and
its **§2.5** disclosure sentence ("a declined binding degrades to state 6
ERROR, never to a clean state"). **Everything else in that record — the
chosen design in §2, the rejected alternatives in §5, the test catalogue
in §6, and the residual risks in §7 — stands unchanged** and is not
re-opened here. The design itself is not withdrawn; two of its stated
proofs were wrong and one disclosure sentence was false.

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
established by executing the *current, unmodified* helpers of
`tools/validate_architecture_gates.py` from a throwaway `/tmp/d6probe`
prototype that imported them read-only and implemented §2.1/§2.2 locally;
the prototype was removed. The only repository files written by this
session are this record and the pointer banner added to the superseded
record.

**Disposition: (A) — revised, checkable safety conditions.** Live wiring
is **not** marked BLOCKED. The design survives; its proof obligations
change, and one of them is now a *named proposition requiring a test*
rather than an asserted invariant. See §5 for the one condition that must
hold for the implementing session to proceed.

---

## 1. Finding C-1 (DECISIVE) — I-2's consequence clause is false

The decision record's I-2 ends:

> Consequence: this design can only move an identifier **out of** state 3
> and into states 1/2/6 — never into state 3 from outside. **No
> identifier that is non-zero under today's (empty-set) behaviour becomes
> clean.**

The final sentence is **false**, and it is falsified by the record's own
intended effect. `attribute_table_identifier` is **already wired** into
the live `_scan_sql_text` path (by `GATE2-R1-D1A-SCANNER-WIRING-2026-10-05`;
see the function's own docstring at `tools/validate_architecture_gates.py:2073`)
and today receives its default fifth argument, `cte_names=frozenset()`.
"Today's behaviour" is therefore *the empty set at every call site*, not
the naive whole-text wiring.

Executed this session against the unmodified helper, with manifest
`membership ⇒ MEM-01/membership_`, `billing ⇒ BIL-02/bil_`, importer
`membership`, `default_schema = public`:

```
attribute_table_identifier("bil_scratch", mods, "membership", "public", frozenset())
  -> state='owned'  owner='billing'      # non-zero: CROSS_DOMAIN_SQL_IMPORT, FAIL
attribute_table_identifier("bil_scratch", mods, "membership", "public",
                           frozenset({"bil_scratch"}))
  -> state='cte'    owner=None           # ATTR_CTE, clean, counted
```

A **genuine, same-statement, legitimately-collected** CTE binding moves
`bil_scratch` from non-zero (FAIL) to clean. That is not a defect — it is
the entire purpose of wiring state 3, and the decision record's own **T3**
demands exactly this flip ("If this test does not currently FAIL before
the wiring lands and PASS after, the wiring is not actually live"). I-2's
consequence clause therefore contradicts the record's own required test.

**This matters beyond pedantry.** I-2 is the proposition §4 leans on to
justify declining rather than ERRORing ("Since declining is *already*
strictly fail-closed by **I-2**, ERRORing buys no soundness") and the
proposition §7 leans on to call the residuals non-blocking. A reviewer who
accepted I-2 as written would have accepted a false premise in support of
two downstream decisions that are, as it happens, still correct — but
correct for a reason I-2 does not supply.

### 1.1 Corrected statement

I-2 is replaced by two separate propositions with distinct comparators.

> **I-2a (monotone relative to the naive whole-text wiring — the valid
> comparator).** For every text `T` and every segment `s ∈ _cte_scopes(T)`,
> `N(s) ⊆ _collect_cte_names(T)`. Equivalently: the binding set handed to
> `attribute_table_identifier` for any identifier is a subset of what the
> rejected naive whole-text wiring (§5 row 2) would have handed it. This
> design is therefore never *more* permissive than the naive wiring it
> replaces, for any input.

I-2a is the claim the decision record *should* have made, and it is the
only sense in which "declining is monotone fail-closed" is true. It is
**not** vacuous: §3 below shows it is not self-evident either, and it is
promoted here to a required test (**T9**).

> **I-2b (bounded widening relative to today's live behaviour — stated,
> not denied).** Relative to today's live behaviour (`cte_names` empty at
> every call site), this design **does** move identifiers into state 3,
> and that is its purpose. The widening is bounded to exactly: an
> identifier whose normalised bare name is a member of `N(s)` for the
> segment it was extracted from, where `N(s)` is non-empty only for a
> segment containing no `;` at all. No other identifier changes state.

**Do not claim that declining always yields state 6.** I-2b replaces that
claim; §2 below shows it is false in three of four shapes.

## 2. Finding C-2 — §2.5's disclosure sentence is false

§2.5 instructs the implementer to add a coverage note ending:

> a declined binding degrades to state 6 ERROR, never to a clean state.

Both halves are wrong. Declining a binding does not "degrade" an
identifier to anything — it merely removes the state-3 branch, after
which the identifier resolves through the *unchanged* precedence chain of
`_attribute_bare_identifier` (CTE → `pg_` → owned prefix → declared
external → unattributed). Where it lands depends entirely on the name.
Executed this session, importer `membership`, same manifest:

| declined CTE name | resolves to | is it state 6? | is it clean for the importer? |
|---|---|---|---|
| `bil_scratch` (another module's prefix) | `owned` / `billing` | **no** | no — FAIL, not ERROR |
| `membership_scratch` (importer's own prefix) | `owned` / `membership` | **no** | **yes — clean, no violation** |
| `pg_scratch` (reserved system prefix) | `system` | **no** | **yes — clean** |
| `scratch_cte` (nothing owns it) | `unattributed` | yes | no — state 6 ERROR |

So a declined binding reaches state 6 in **one** of four shapes, and is
**clean anyway** in two of them. The record's own §7 residual 1 already
half-knew this (it documents the `CROSS_DOMAIN_SQL_IMPORT` row) but §2.5,
which is the text that would actually have been written into the shipped
coverage note under `ADR-011` **D8**, states the opposite without
qualification. A coverage note is a self-evidencing artefact; shipping a
false one is worse than shipping none.

### 2.1 Corrected disclosure sentence (use this text verbatim)

> CTE-local attribution (ADR-011 D3.2 state 3) is **statement-scoped**:
> bindings are collected per lexically-segmented statement, and are
> **declined** for any statement containing a semicolon that is not its
> own terminator, and for any text that cannot be lexically segmented at
> all. A declined binding does not create a state of its own — the
> identifier resolves through the unchanged D3.2 precedence chain and may
> land in any of states 1, 2, 4, 5 or 6. Declining therefore never makes
> an identifier *cleaner* than it would be with no CTE support at all,
> which is the fail-closed property; it does not guarantee an ERROR.

## 3. Finding C-3 — I-1's independence-from-the-lexer justification does
## not hold, though its conclusion survives for a different reason

I-1 asserts, and rests its status as "an invariant rather than a hope"
on:

> **I-1 therefore holds independently of whether the lexer's skip
> decisions are correct.**

The supplied mechanism covers exactly one failure direction. Spelled out:

- **Direction 1 — the lexer OVER-skips (merges).** A region swallows a
  real terminator, so statements `A` and `B` land in one segment `s`. The
  real `;` is a character of `s`, so `";" in s` and `N(s) = frozenset()`.
  **Covered by the trust predicate, correctly.** This is the only
  direction the record's mechanism addresses.
- **Direction 2 — the lexer UNDER-skips (false-cuts).** A `;` that is
  really inside a quoted literal, a comment, a dollar-quoted body or a
  double-quoted identifier is judged to be at depth 0, so a cut is made
  *inside* a real statement and the offending `;` is **excluded from both
  neighbours** (§2.1 is explicit about this). The tail fragment can
  therefore be `;`-free, hence **trusted**, and is then handed to
  `_collect_cte_names` **out of context** — the fragment no longer knows
  it is inside a literal. A fake depth-0 `WITH` written inside that
  literal becomes a live binding. **The trust predicate provides no
  protection whatsoever in this direction**, because the very character
  that would have tripped it was consumed as the cut.

This is not a hypothetical class the record was unaware of: §5 row 3
rejects "split on every raw `;`" as "actively unsafe" on *precisely* this
mechanism ("the tail fragment re-lexes standalone with a depth-0
`WITH fake AS (` and yields a **false** binding"). The only thing
separating the chosen design from the design it rejects on those grounds
is **the accuracy of the lexer's skip decisions** — which is exactly what
I-1 claims to be independent of. I-1, as justified, is self-contradictory
with §5.

### 3.1 What this session found when it looked for a live falsification

> **§3.1 seed-count correction (2026-10-05, applied).** This paragraph's
> "8 seeded adversarial inputs" is unreconstructable as recorded and is
> narrowed to: *seven* adversarial shape categories were named, of which
> six are reconstructable from this paragraph's own text and one — "a
> false-cut shape whose tail re-lexes standalone" — was recorded with no
> example text and no concrete lexical construct. The eighth input is
> unaccounted for. The prototype that ran them is deleted and the exact
> seed strings are not in the repository
> (`GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md:115`),
> so neither the count nor the "0 falsifications" result is independently
> reproducible. The prototype also implemented the §2.1/§2.2
> **two-function** `_split_sql_statements` + `_collect_cte_names` design,
> which was subsequently BLOCKED and replaced by the one-pass
> `_cte_scopes` (`tools/validate_architecture_gates.py:2704-2718`); the
> result therefore does not transfer to the implemented one-pass design
> even if the seeds were recovered. The negative result stands only as
> what it is: one session's bounded, now unrepeatable search over a
> superseded design. The same non-transfer applies to this paragraph's
> separately stated 300,000-random-input result, produced by the same
> deleted prototype over the same superseded two-function design; that
> claim is otherwise left exactly as recorded and was **not** re-run.
>
> **Not retroactively satisfied.** A **newly constructed** replacement
> false-cut seed was authored on 2026-10-05 against the current one-pass
> `_cte_scopes`/`_collect_cte_names` and added to the standing pure T9
> corpus (`GATE2-R1-D6-T9-SEED-RECONCILIATION-2026-10-05.md` §2;
> `GATE2-R1-D6-T9-REPLACEMENT-SEED-VERIFICATION-2026-10-05.md`), where
> `tools/tests/test_validate_architecture_gates.py` runs **217/217 PASS**.
> That is a forward, pure-stage result about today's design only. It is
> **not** the lost historical seed and does not discharge, reproduce, or
> retroactively satisfy this paragraph's "8 seeds / 0 falsifications"
> claim.

**HISTORICAL — as recorded by the now-deleted prototype, narrowed by the
notice above; not independently reproducible and not transferable to the
implemented one-pass `_cte_scopes`.** A throwaway prototype implemented
§2.1/§2.2 verbatim over the then-current unmodified helpers and searched
for any `T` with
`N(s) ⊄ _collect_cte_names(T)` (a direct falsification of I-2a, and the
observable signature of a direction-2 escape):

- **8 seeded adversarial inputs** *(as recorded; seven shape categories
  are actually named below — see the narrowing notice above)*, each
  targeting a specific skip
  decision — backslash-before-quote under `standard_conforming_strings`
  (`'a\'; WITH fake AS (SELECT 1) ...`), the doubled-quote form, an
  `E'...'` string, a `;` inside a block comment, inside a `$$` body,
  inside a `"c;ol"` quoted identifier, and a false-cut shape whose tail
  re-lexes standalone: **0 falsifications.**
- **300,000 randomly generated inputs** over a 22-token adversarial
  alphabet (`WITH`, `;`, `'`, `\`, `''`, `--`, `\n`, `/*`, `*/`, `$$`,
  `$t$`, `"`, `(`, `)`, `E'`, `U&'`, identifiers, …), seeded `20261005`:
  **0 falsifications.**

So I-1's *conclusion* survived every attack this session mounted. But it
survives for a reason the record never states, and that reason is
materially different from the one it does state:

> **Lemma L (the actual mechanism, and the real load-bearing
> proposition).** `_split_sql_statements` emits a cut at index `i` only
> when its own left-to-right dispatch believes `i` is at top level,
> outside every lexical region, at depth 0. `_collect_cte_names` walks
> the same text with **the same three-branch dispatch in the same order**
> (`_lex_quoted_segment` → `_skip_quote_or_comment` → ordinary
> character). Therefore at any cut index both functions are in the same
> lexical state, and the standalone re-lexing of a tail fragment from its
> own index 0 follows the identical dispatch path as the whole-text scan
> does from that index. Any binding a trusted fragment yields is
> consequently a binding `_collect_cte_names(T)` **also** yields — the
> naive whole-text wiring is fooled by exactly the same false cut, to
> exactly the same extent.

Lemma L is why I-2a holds, and it is also why direction-2 escapes cannot
make this design *worse than the alternative it replaces*. Note what L
does **not** say: it does not say a false binding is impossible. It says
a false binding is **not introduced by segmentation**. If the lexer can
be fooled, both wirings are fooled identically — segmentation neither
adds nor removes that exposure.

### 3.2 Corrected statement

See the 2026-10-05 residual-claim supersession qualification at the top of this record — the claims below about the two-function Lemma L, T10/M5, and the 300k+8 fuzz result are historical and partly superseded.

> **I-1′ (no cross-statement suppression — conditional, not
> unconditional).** For any two distinct real statements `A` and `B` in
> `T` that the lexer separates correctly, no name bound by a `WITH`
> clause in `A` is ever applied to an identifier extracted from `B`.
> Where the lexer **over**-skips and merges `A` and `B`, the merged
> segment necessarily contains the real `;`, the trust predicate fires,
> and `N(s) = frozenset()` — so the conclusion holds in that direction
> *unconditionally and independently of lexer accuracy*, exactly as the
> original I-1 argued. Where the lexer **under**-skips and false-cuts
> inside a single real statement, the resulting fragments are all parts
> of that one statement, so no binding crosses a real statement boundary;
> but the trust predicate contributes nothing there, and the resulting
> fragment-local bindings are sound only to the extent of **Lemma L**.

> **I-1″ (the safety property that actually matters, stated separately
> because I-1 is too narrow to carry it).** A false binding arising from
> a direction-2 false cut applies only to identifiers within the
> false-cut fragment, and `_collect_cte_names(T)` yields that same
> binding, so this design is never more permissive than the naive
> whole-text wiring (= **I-2a**, = **Lemma L**). It is **not** claimed
> that such a binding is impossible, nor that the gate cannot be fooled
> by a sufficiently adversarial literal — only that segmentation is not
> the thing that fools it.

**Lemma L is supported by argument and by 300k+8 unfalsified executions.
It is NOT proven.** It is a statement about the agreement of two
hand-written lexer walks, and it would be broken by any future edit that
changes one function's dispatch order, branch set, or depth bookkeeping
without changing the other's. It is therefore promoted to a **required
test with a structural guard** (T9/T10 below), not left as prose.

## 4. Consequential corrections to the decision record's own text

| Location | Status after this correction |
|---|---|
| §3 **I-1** | SUPERSEDED by **I-1′** + **I-1″** (§3.2). The clause "holds independently of whether the lexer's skip decisions are correct" is withdrawn as stated; it is true only of the over-skip direction. |
| §3 **I-2** | SUPERSEDED by **I-2a** + **I-2b** (§1.1). The consequence clause is withdrawn as false. |
| §2.5 disclosure | SUPERSEDED by §2.1 of this record (verbatim replacement text). |
| §4, "Why declining rather than ERRORing" | Conclusion **stands**; its cited support changes from "I-2" to "**I-2a**". The argument is unaffected — declining never makes an identifier cleaner than no-CTE-support-at-all, which is what that paragraph needs. |
| §4 decline table, "Why decline is safe" column | The phrase "A real table reference is never clean; a genuine CTE reference becomes a loud state-6 ERROR" is **wrong in the same way as §2.5** and is superseded by §2.1's text. A declined name matching the importer's own prefix is clean and silent. |
| §7 residual 1 | **Stands, and is strengthened**: it correctly identified the `CROSS_DOMAIN_SQL_IMPORT`-not-ERROR route. §2 of this record shows two further routes (self-owned prefix, `pg_` prefix) that are clean and silent, which residual 1 does not name. |
| §7 residual 4 | **Materially weakened by the wiring, and this is a new disclosure.** It states that extraction from inside literals/comments "errs in the loud direction (a false FAIL/ERROR, never a false clean)". Once state 3 is live, a binding collected from a segment can clean an identifier that `_extract_table_identifiers` pulled out of a comment or literal in that same segment. The sentence "never a false clean" is **no longer true** after this increment. This is a precision change, not a soundness regression relative to the naive wiring (Lemma L), but it must be re-worded rather than carried forward unchanged. |
| §2 design, §5 alternatives, §6 tests T1–T8, §7 residuals 2/3/5/6, §8 | Unchanged, not re-opened. |

## 5. The one condition for proceeding, and the added required tests

See the 2026-10-05 residual-claim supersession qualification at the top of this record — the claims below about the two-function Lemma L, T10/M5, and the 300k+8 fuzz result are historical and partly superseded.

**Live wiring may proceed** under disposition (A), with these additions
to §6's catalogue. They are narrowly scoped: two tests and one structural
guard, no redesign, no signature change, no new error code.

**T9 — `test_segment_bindings_are_a_subset_of_whole_text_bindings`**
(pure; the **I-2a / Lemma L** lock, and the single most important test
added by this correction). For a corpus comprising every input already
named in §6's T1/T5/T7/T8 **plus** the eight adversarial seeds recorded
in §3.1 of this record, assert for every input `T` and every
`(s, N(s)) ∈ _cte_scopes(T)` that `N(s) <= _collect_cte_names(T)`. This
is the proposition that replaces I-2's withdrawn consequence clause as
the design's actual soundness claim, so it must be a standing test, not a
one-off probe. **Non-vacuity control, same test:** assert the corpus
contains at least one input for which some `N(s)` is non-empty and at
least one for which the whole-text set is strictly larger — otherwise the
subset assertion passes trivially.

**T10 — `test_statement_splitter_and_cte_collector_share_one_dispatch`**
(structural; the **Lemma L** guard). Lemma L is an agreement property
between two functions, and nothing in the code enforces it. Assert
structurally — by AST inspection of `_split_sql_statements` and
`_collect_cte_names`, in the style this repository already uses for
`tests/contract/_execution_suppression_guard.py` — that both call
`_lex_quoted_segment` and `_skip_quote_or_comment`, in that order, and
that neither contains a lexical-region branch the other lacks. A future
edit that adds a skip branch to one function alone is the exact mutation
that breaks Lemma L silently, and it is invisible to every behavioural
test in §6.

**M5 (added mutation control)** — in a throwaway full-structure copy,
add one lexical-region branch to `_split_sql_statements` that
`_collect_cte_names` does not have (e.g. treat `#` as a line-comment
start in the splitter only). **T10 must fail.** If T10 survives this
mutant, T10 is not actually locking Lemma L and the implementing session
must stop and report rather than proceed. Run in a throwaway copy, never
in the repository, and confirm `git status --porcelain tools/` is clean
afterwards.

**Amendment to §6's M2** — the decision record's M2 ("delete the
`";" in seg` trust predicate") is expected to fail T5 and T8's `fake`
assertion. Per §3.1, the current helpers resisted every direction-2 probe
this session ran, so **if M2 survives green, that is a signal the trust
predicate is not load-bearing on the chosen corpus, not a licence to drop
it.** The implementing session must record M2's actual observed outcome
rather than its expected one.

**Explicitly NOT required:** no change to the chosen design, no offset-
aware attribution, no union-cut/trust-flag alternative, no ADR amendment.
§7 residual 6's instruction stands: if a reviewer concludes the trust
predicate narrows D3.2 state 3 too far, that is a finding against ADR-011
for `veyro-lead` to amend, not something to widen in implementation.

## 6. Unresolved propositions carried forward

See the 2026-10-05 residual-claim supersession qualification at the top of this record — the claims below about the two-function Lemma L, T10/M5, and the 300k+8 fuzz result are historical and partly superseded.

1. **Lemma L is unproven.** It is argued, fuzz-supported (300k+8, zero
   falsifications), and now test-guarded by T9/T10 — but it is not a
   proof, and this record does not claim one. A property-based test over
   the combined literal + comment + dollar-quote + segmentation surface
   (the fuzz item already named in the decision record's §7 residual 3)
   is the honest next step, and it is **more** material now than when
   that residual was written, because Lemma L is load-bearing where the
   withdrawn I-1 clause used to be.
2. **This record did not re-derive the decision record's §7 residuals
   2, 3, 5 or 6**, nor re-extract TSD §24.1 from the governing docx. §7
   residual 5's second-hand-citation caveat is carried forward unchanged.
3. **No direction-2 false cut was demonstrated against the current
   helpers.** Absence of a found counterexample over one session's
   bounded search is not absence of one; §3.1's negative result is
   recorded as what it is.

## 7. Explicitly not done by this session

- No code, test, CI, capability-manifest, `SCN-070`, or `DOM-002` edit.
  The only repository writes are this record and the pointer banner at
  the top of the superseded record.
- No independent review verdict, no review-round increment, no
  `REVIEW_IN_FLIGHT.md` claim.
- No scenario PASS, no P0 closure, no promotion of
  `SCN-MOD001-006/-007/-095/-096`.
- No `git` add/commit/push, no branch change.
- No edit to `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`,
  or `ADR-011`.
- No owner-reserved action: no spend, no real member data, no production
  deploy, no material product/pricing/business/scope change.
