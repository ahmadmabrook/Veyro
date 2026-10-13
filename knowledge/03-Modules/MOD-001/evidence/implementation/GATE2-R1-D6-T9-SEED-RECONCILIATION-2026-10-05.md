# GATE2-R1-D6 — T9 eighth-seed reconciliation (named `veyro-lead`, read-only, 2026-10-05)

Bounded architecture/evidence clarification. One question only: the honest
reproducible test obligation for the missing eighth adversarial seed named by
`GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md` §3.1. No code, no
test, no wiring, no review verdict, no owner action, no ADR-011 D3.2/D9 risk
judgment (see LIMITS).

## BOUNDED CONCLUSION

**Branch (a) AND branch (b), jointly — they are not alternatives here.** A
concrete, reproducible replacement seed for the "false-cut shape whose tail
re-lexes standalone" **is** constructible and verified against the actual
current helper (§2 below), **and** §3.1's historical "8 seeded adversarial
inputs" sentence must still be narrowed, because the replacement seed is not
and cannot be the lost original: the original was run against a *different,
subsequently-BLOCKED design*. The new seed discharges the forward test
obligation; it does not and must not discharge the historical claim (§3).

**T9 pure-stage adequacy: ADEQUATE-WITH-ONE-GAP.** The current test is sound,
non-vacuous and correct as far as it goes, but it is missing exactly one test
input — the seed in §2. That is the single named gap; nothing else is missing
at the pure (unwired) stage (§4).

## 1. What §3.1 actually claims, and against what

- `GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md:213-221` claims
  "**8 seeded adversarial inputs**, each targeting a specific skip decision"
  and then enumerates: backslash-before-quote under
  `standard_conforming_strings`, the doubled-quote form, an `E'...'` string, a
  `;` inside a block comment, inside a `$$` body, inside a `"c;ol"` quoted
  identifier, "and a false-cut shape whose tail re-lexes standalone". That is
  **seven** shape categories named for eight asserted inputs, and the seventh
  category is the only one given **no example text and no concrete lexical
  construct**.
- Same record, `:206-210`: the inputs were run by "a throwaway prototype
  [that] implemented §2.1/§2.2 verbatim over the current unmodified helpers."
- `GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md:115`: "The
  prototype is deleted; the exact seeds are not in the repository.
  **Unreproducible as recorded**." Same record `:123` flags its own T9 corpus
  as "a **reconstruction** of §3.1's eight adversarial seeds from their prose
  descriptions."
- **Decisive, and not previously recorded in this thread:** the §2.1/§2.2
  design the §3.1 prototype implemented was the **two-function**
  `_split_sql_statements` + reused-`_collect_cte_names` design, and that design
  was **BLOCKED and replaced**. Per
  `tools/validate_architecture_gates.py:2704-2718`, `_cte_scopes` exists
  precisely because the named `veyro-lead` blocked that two-function design
  (its Lemma L was false against the source), and `_cte_scopes` "collapses both
  branches into ONE lexical cursor, so there is only one walk and Lemma L
  becomes vacuous by construction." `_split_sql_statements` **does not exist**
  in `tools/validate_architecture_gates.py` — it appears only inside those two
  comment lines (`:2711`, `:2729`); it was never implemented.

Consequence: §3.1's "a false-cut shape whose tail **re-lexes standalone**"
describes a mechanism — a tail fragment handed to a *second* function and
walked from its own index 0 — that **structurally does not exist** in the
implemented one-pass design. `_cte_scopes`
(`tools/validate_architecture_gates.py:2725-2838`) never re-lexes a segment:
every binding is collected in the single pass (docstring `:2726-2731`), the
depth-0 `;` branch (`:2817-2825`) only closes a slice, resets `start` and
clears the per-segment accumulator, and leaves `depth` and the lexical cursor
trajectory untouched. So the eighth seed cannot be recovered *or* re-run as
recorded, even in principle, against today's helper.

## 2. (a) The concrete replacement seed, with exact assertions

This is a **newly constructed replacement seed authored on 2026-10-05 against
the current `_cte_scopes`/`_collect_cte_names`. It is NOT a recovered original
and must never be recorded as one.** It is chosen to exercise the *consequence*
§3.1's seventh category was aimed at, and the exact mechanism §5 row 3 of the
correction rejects ("split on every raw `;`" — "the tail fragment re-lexes
standalone with a depth-0 `WITH fake AS (` and yields a **false** binding").

Exact seed string (Python source form):

```python
# Newly constructed replacement for correction section 3.1's unreconstructable
# eighth seed ("a false-cut shape whose tail re-lexes standalone"). NOT the
# historical seed; see GATE2-R1-D6-T9-SEED-RECONCILIATION-2026-10-05.md.
false_cut_tail = "SELECT 'a ; WITH fake AS (SELECT 1) SELECT * FROM bil_t' FROM t"
```

Exact expected assertions (all five verified by direct execution of the current
helpers today — see §2.1 for the observation method):

```python
tail = false_cut_tail.split(";", 1)[1]
scopes = _cte_scopes(false_cut_tail)

# 1. No false cut: the only `;` in the text is inside a single-quoted literal,
#    so the one-pass cursor must emit exactly ONE segment spanning the whole text.
assert len(scopes) == 1, scopes
assert scopes[0][0] == false_cut_tail

# 2. Trust predicate fires: the `;` survives in the sliced segment text (it was
#    skipped atomically inside the literal, never consumed as a cut), so the
#    segment's bindings are declined.
assert scopes[0][1] == frozenset(), scopes

# 3. No `fake` binding in any scope, in either direction.
assert all("fake" not in names for _seg, names in scopes), scopes
assert _collect_cte_names(false_cut_tail) == frozenset()

# 4. NON-VACUITY / danger proof: the tail genuinely IS dangerous when re-lexed
#    standalone -- it yields the false binding. This is what makes the seed a
#    false-cut-tail seed rather than decoration, and it is the assertion that
#    would fail if a future edit regressed to a re-lexing (two-function) design.
assert _collect_cte_names(tail) == frozenset({"fake"})

# 5. T9's own subset property still holds on this input.
assert scopes[0][1] <= _collect_cte_names(false_cut_tail)
```

### 2.1 Observed behaviour (method, and why no file was touched)

Observed by loading `tools/validate_architecture_gates.py` in a throwaway
in-memory `importlib` module and calling the two helpers; **no file was
created, edited or deleted**, and `tools/validate_architecture_gates.py`'s
SHA-256 is still
`3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d` — byte-for-
byte the value
`GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md:89` records as
the "nothing was wired" check. Observed values:

- `_cte_scopes(false_cut_tail)` → `[(<whole seed text>, frozenset())]` (len 1).
- `_collect_cte_names(false_cut_tail)` → `frozenset()`.
- `_collect_cte_names(tail)` → `frozenset({'fake'})`.
- Incidentally, `_cte_scopes(tail)` → `[(tail, frozenset())]`, via the
  **whole-text decline** path, not the trust predicate: the tail carries an
  unterminated single-quoted literal (`bil_t'`), so `_skip_quote_or_comment`
  returns `None` and `_cte_scopes` declines everything
  (`tools/validate_architecture_gates.py:2802-2804`), whereas
  `_collect_cte_names` `break`s and **keeps** what it already collected
  (`:2680-2682`). This asymmetry is in the safe direction for `_cte_scopes` and
  is why assertion 4 is stated on `_collect_cte_names(tail)`, not on
  `_cte_scopes(tail)`.

### 2.2 Why this seed is not a duplicate of anything already in T9's corpus

- It is **not** `t5_input`
  (`tools/tests/test_validate_architecture_gates.py:3557`): there the
  literal-internal `;` is followed by a **real** top-level `;` and a **real**
  CTE `c`. Here the literal-internal `;` is the text's **only** `;`, and the
  name behind it is **`fake`** — a false binding, not a real one.
- It is **not** the existing five reconstructed §3.1 shapes
  (`:3568-3581`): each of those asserts only *where the `;` hides*. None of
  them asserts the **tail-re-lex consequence** (`_collect_cte_names(tail) ==
  {"fake"}`), which is the proposition the seventh category names and the one
  that would detect a regression back to the BLOCKED two-function design.

## 3. (b) and (c) — historical claim vs new corpus, kept separate

These are two different claims and the record must keep them apart.

**HISTORICAL (about seeds that existed, 2026-10-05 prototype).** §3.1's "8
seeded adversarial inputs ... 0 falsifications" is: (i) an arithmetic mismatch
on its face (eight inputs, seven named categories, one category with no
construct given); (ii) unreproducible — prototype deleted, seeds not in the
repository
(`GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md:115`); and
(iii) **run against a design that no longer exists** (§1 above). It must be
**narrowed and marked unreconstructable**, not quietly satisfied by a new
corpus. Proposed wording for whoever amends the record (proposed text, not an
applied edit — I did not and will not edit the correction):

> **§3.1 seed-count correction (2026-10-05).** This paragraph's "8 seeded
> adversarial inputs" is unreconstructable as recorded and is narrowed to:
> *seven* adversarial shape categories were named, of which six are
> reconstructable from this paragraph's own text and one — "a false-cut shape
> whose tail re-lexes standalone" — was recorded with no example text and no
> concrete lexical construct. The eighth input is unaccounted for. The
> prototype that ran them is deleted and the exact seed strings are not in the
> repository, so neither the count nor the "0 falsifications" result is
> independently reproducible. The prototype also implemented the §2.1/§2.2
> **two-function** `_split_sql_statements` + `_collect_cte_names` design, which
> was subsequently BLOCKED and replaced by the one-pass `_cte_scopes`
> (`tools/validate_architecture_gates.py:2704-2718`); the result therefore does
> not transfer to the implemented design even if the seeds were recovered. The
> negative result stands only as what it is: one session's bounded, now
> unrepeatable search over a superseded design.

**NEW (about the corpus the current test can legitimately assert going
forward).** The standing T9 corpus asserts a *different and narrower* thing: for
each of its inputs, `N(s) <= _collect_cte_names(T)` against **today's**
`_cte_scopes`, re-verified on every test run. The §2 seed joins it as an
explicitly-labelled **newly constructed replacement**. No forward corpus
result may be cited as evidence for the historical "8 seeds / 0
falsifications" claim, and the in-test comment must say so — this is the
laundering risk, and labelling at the seed definition (as in §2's code comment)
is the control.

## 4. (d) Adequacy of the current T9 pure-stage test

`test_cte_scopes_segment_bindings_are_a_subset_of_whole_text_bindings`
(`tools/tests/test_validate_architecture_gates.py:3527-3598`): **ADEQUATE for
the pure (unwired) stage, with exactly one missing input.**

What it already does right, and I am not asking to change:
- Asserts the correct proposition (`names <= whole_text_names`, `:3588`) over
  T1/T5/T7/T8 plus five reconstructed §3.1 shapes.
- Carries the §5-mandated non-vacuity control, both halves
  (`saw_nonempty_segment_binding`, `saw_whole_text_strictly_larger`,
  `:3596-3597`).
- **Discloses its own gap in-test rather than inventing a seed**
  (`:3542-3550`: "inventing one would not be a transcription of the source.
  This gap is reported, not silently filled"). That was the correct call at
  authoring time and is why this reconciliation is cheap.

**The exact single missing test:** the §2 `false_cut_tail` seed, added to
`corpus` with its five assertions. Assertions 1-3 and 5 fit the existing loop;
**assertion 4 (`_collect_cte_names(tail) == frozenset({"fake"})`) must be
written explicitly outside the subset loop** — it is a danger-proof /
regression-detector, not a subset assertion, and folding it into the loop would
lose it. Nothing else is missing at this stage.

## 5. (e) Smallest next legal step

**Add the one §2 seed (plus its assertion 4 and its "newly constructed
replacement, not a recovered original" comment) to the existing T9 test, and
nothing else.** Specifically: one edit to
`tools/tests/test_validate_architecture_gates.py` inside
`test_cte_scopes_segment_bindings_are_a_subset_of_whole_text_bindings`; replace
the `:3542-3550` "not reconstructed" comment block with a pointer to this
record; re-run the focused test set + Ruff; and confirm
`tools/validate_architecture_gates.py`'s SHA-256 is still
`3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d`
(nothing wired). No production-source change, no signature change, no new error
code, no new dependency, no ADR amendment.

Deliberately **not** bundled into that step, and ordered after it:
1. The §3 narrowing of §3.1's historical sentence (a correction-record
   amendment, separate write, separate author).
2. The seeded property/fuzz corpus increment
   (`GATE2-R1-D6-PREWIRE-TEST-SEQUENCING-LEAD-DECISION-2026-10-05.md:72`,
   stdlib `random` only).
3. The fresh ADR-011 D3.2/D9 risk adjudication, which still gates wiring.

## LIMITS

- **Not read:** the correction record outside §3 and §5 (its §1, §2, §2.1,
  §2.5, §4, §6 and §7 were not read this session; §1-§3.2 and §5-§7 headings
  only were listed to locate §3.1 and T9); the D6 statement-scope decision
  record itself; `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md`
  (cited only second-hand, via the source comment at
  `tools/validate_architecture_gates.py:2704-2718`); ADR-011 itself; the TSD;
  `SCN-070`/`DOM-002` material; the bug registry; the open round-1 code review.
- **Second-hand citation:** the claim that the two-function design was BLOCKED
  rests on the source file's own comment, not on an independent read of the
  qualification record. A future session relying on §1's decisive point should
  verify it against that record directly.
- **Deferred, explicitly:** the **ADR-011 D3.2/D9 final risk judgment**. Not
  rendered, not pre-empted, not partially hinted at here. Nothing in this
  record licenses wiring.
- **No live-behaviour claim is made.** `_cte_scopes` and `_collect_cte_names`
  remain **unwired** — `_scan_sql_text` still calls
  `attribute_table_identifier` with its default empty `cte_names`
  (`tools/validate_architecture_gates.py:2209-2214`, `:2720-2724`), so ADR-011
  D3.2 state 3 is unreachable from the live scanning path. Every observation in
  §2.1 is a direct call to a pure helper in isolation; none of it says anything
  about gate behaviour on real SQL.
- **No verdict rendered** on the correction's T10 or M5 (the Lemma L structural
  guard and its mutation control). I note only, without adjudicating, that
  T10's premise — two functions whose dispatches could disagree — may no longer
  match the one-pass source; that is a separate question for a separate
  bounded step.
- **No proof claimed** for the subset property. §1's trajectory-identity
  argument for why the one-pass design makes a standalone-tail divergence
  structurally unreachable is an argument, not a proof, and correction §6.1's
  "Lemma L is unproven" residual is carried forward unchanged.
- **Scope discipline:** no implementation, no test edit, no owner action
  requested or taken, no commit. This record is the only file created,
  modified, or deleted by this session.

## Orchestrator verification addendum (2026-10-05)

The guarded inspection `50f116e2-c59e-489e-b553-084eb6cd9097` completed exit 0 with one verified evidence checkpoint. The foreground named `veyro-lead` Task was agent `a5cc80896234a5b43`; the orchestrator independently ran `mr_verify.py opus veyro-lead` on `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/d527cc94-16eb-4b60-baa9-b8a124cc57f6/subagents/agent-a5cc80896234a5b43.jsonl`: **PASS 39/39 `claude-opus-5`**. It independently executed the five proposed seed assertions against the current pure helpers: all passed. Source/test SHA-256 remained `3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d` / `cff4215e7072711877a8972779fb6e0956977f2eea2d9d8d3bbbd593bba6f32e`.

**Precision qualification:** assertion 4 (`_collect_cte_names(tail) == {"fake"}`) proves the standalone tail is hazardous. It does **not by itself** detect a future change to `_cte_scopes`, because it does not call that helper. The regression detection is the **combined** test: if a future splitter falsely cuts/re-lexes the seed, assertions 1–3 and/or 5 on the resulting scopes must be discriminating. Preserve assertion 4 as the danger/non-vacuity control, but do not cite it alone as a regression detector. This qualification does not change the lead's chosen seed or authorize wiring.
