# Gate-2 R1 D6 — U1/U2 qualified redecision (named `veyro-lead`, Opus, 2026-10-05)

## 0. Provenance

- **Operation-id:** `ebcb6b4c-fe27-417e-93b6-2e82ba538b77`
- **Operation name:** `D6-U1-U2-QUALIFIED-REDECISION`
- **Subgoal:** `D6-U1-U2-QUALIFIED-REDECISION`
- **Date:** 2026-10-05
- **Role/model:** named `veyro-lead` (Opus) — architecture/critical-decision tier. This is
  **not** an independent code review, security review, gate-2 round verdict, scenario
  verdict, or module certification, and it advances no review counter.
- **Unit:** MOD-001 / GOV-01-R04 gate 2 (module-deps lint), fixture-scoped.
- **Question decided (exactly one):** do the U1 finite named-class lexical controls and the
  now-resolved U2 CTE-before-owned false-binding risk justify a narrowly bounded **live
  state-3 wiring increment** under ADR-011 D9, or must the prior **B HOLD** continue?

**Artifacts actually inspected (paths):**

Governance preamble
- `knowledge/00-System/SESSION_BOOTSTRAP.md`
- `knowledge/00-System/CURRENT_STATE.md` (current `current_as_of` entry only; file is ~464 lines
  and was not read end to end)
- `knowledge/00-System/CURRENT_HANDOFF.md` (current watchdog checkpoint + `current_as_of` head only)

Bounded evidence scope
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-U1-LEXICAL-UNDER-SKIP-TESTS-VERIFICATION-2026-10-05.md` (U1 lexical test report)
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-U2-PRECEDENCE-INSPECTION-2026-10-05.md` (U2 precedence inspection)
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-D8-COVERAGE-GAP-2026-10-05.md` (D8 coverage-gap disclosure)
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-D3D9-PREWIRE-LEAD-JUDGMENT-2026-10-05.md` (prior B HOLD judgment)
- `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md` — D3 (D3.1–D3.5, incl.
  D3.2's six states), D8, D9, plus the "Alternatives considered"/"Conformance determination" rows
  bearing on D9

Corroborating current source/test excerpts (read-only, not re-derived, not executed)
- `tools/validate_architecture_gates.py` lines ~2023–2130 (`AttributionOutcome`,
  `_attribute_bare_identifier`, `attribute_table_identifier`) and ~2185–2205 (the live
  `_scan_sql_text` attribution loop / call site)
- `tools/tests/test_validate_architecture_gates.py` — the six U1 named-class tests
  (lines ~3687–3830), `test_attr_cte_local_name_takes_precedence_over_owned_prefix`
  (lines ~2640–2645), and the seeded property-corpus test (lines ~4079+)
- SHA-256 recomputed this session: source `3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d`
  (unchanged from the verdict-B checkpoint and from the U1/U2 records);
  test `1e81b0b2681b4b47c5917597a3b4eccdc8e4b907b4c826580dac632a601a37eb`
  (matches the U1 record's post-increment value)

---

## 1. Verdict

**(B) — HOLD continues. The prior B HOLD remains governing; no live state-3 wiring increment
is permitted, narrowly bounded or otherwise.**

No owner approval is required for **this** verdict (B withholds a change rather than making
one). Real-tree domain ownership binding — committing `contracts/modules/ownership.json` with
real domain/prefix bindings — remains separately **`BLOCKED: OWNER_APPROVAL_REQUIRED`** per
ADR-011 D9 and the prior B HOLD's scope paragraph; this redecision neither touches nor advances it.

---

## 2. Rationale

### 2.1 The prior hold named two constraints as jointly necessary for (A). U2 resolved one of
them affirmatively **false**, not merely unverified.

`GATE2-R1-D6-D3D9-PREWIRE-LEAD-JUDGMENT-2026-10-05.md` §2.5 is explicit: "(A) requires bounding
the residual by constraint. The two constraints that would actually bound it — verified
fail-closed behaviour on the U1 classes, and a pinned state-1/2-before-state-3 precedence — are
not established facts I may condition on." §2.4(U2) pre-committed to the consequence of each
branch: if states 1/2 are consulted before state 3, the residual "collapses to … bounded and
arguably disclosable"; if **state 3 is consulted before state 2**, "a falsely-bound
`bil_invoices` masks a **real cross-domain import**: exactly the R1-F01 class, **unacceptable at
any probability**."

The U2 inspection resolved it in the second direction, and I corroborated that directly in the
current source rather than taking the report's word for it. `_attribute_bare_identifier`
(`tools/validate_architecture_gates.py` ~2039–2059) opens with:

```python
    if name in cte_names:
        return AttributionOutcome(ATTR_CTE, None, ...)
    if name.startswith("pg_"):
        ...
    owner = _owner_by_prefix(name, modules)
```

State 3 is therefore the **first** resolution consulted for a bare identifier, and
`attribute_table_identifier` routes a 2-part name whose schema equals `default_schema` into the
same function under D3.3 rule 2 — so default-schema-qualified names inherit the same ordering.
A supplied CTE binding pre-empts the owned-prefix check, which is the sole producer of state 2
`CROSS_DOMAIN_SQL_IMPORT` for bare names. This is *demonstrated* in source, and independently
locked by an existing test the U2 record cites,
`test_attr_cte_local_name_takes_precedence_over_owned_prefix`, whose own comment states the
intent plainly ("CTE-local binding (ADR-011 D3.2 state 3) is checked first and wins").

The condition the prior lead set for (A) is thus not an open question awaiting work. It has been
answered against wiring. A verdict of (A) now would require me to overrule a pre-committed
"unacceptable at any probability" on the strength of evidence that *confirmed* the bad branch.

### 2.2 U1's closure is real but is the wrong kind of fact to offset U2.

U1 was genuinely executed as the prior hold's §4 item 1 specified. All six named classes have
repository-resident, still-unwired tests — nested PostgreSQL block comment, tagged dollar-quote
with an inner mismatched tag, `E'…\'…'`, `U&'…'`, `U&"…"`, and a doubled quote inside a
double-quoted identifier — each placing a decoy `WITH bil_invoices AS (...)` inside the inert
region and a genuine `real_cte` outside it, asserting no `bil_invoices` binding in any returned
scope **plus** a positive control proving the negative assertion is non-vacuous. I read these
tests and they assert what the U1 report says they assert.

**A passing finite named-class lexical test establishes only that the enumerated classes behaved
as specified on the inputs actually exercised. It is not a soundness proof over PostgreSQL's
unenumerated lexical input space.** The U1 report says so in its own words; so does the D8
disclosure; so did the prior hold about the 512-case corpus. I adopt that caveat without
weakening it anywhere in this rationale.

That matters structurally, because the class the prior hold identified as governing (§2.1) was
not "these six classes" — it was **shared-lexer under-skip inside a single real statement**, of
which the six are an enumerated subset the lead chose as the cheapest confirmatory probes. Six
named classes passing removes six specific suspicions. It does not bound the residual, and the
prior hold's §2.2 asymmetry argument is untouched by any artifact in this packet: every control
in the current design (the per-segment `;` predicate, the whole-text decline on an unterminated
region) can only **remove** the state-3 branch, never add one, so **no existing control points
at the only route to a false clean, which is an extra binding**. A falsely-bound name is simply
present in the accumulator; nothing inspects it for corroboration. No control answering that was
added by the U1 increment — the production source SHA-256 is byte-identical to the verdict-B
checkpoint, which I recomputed. Only the test file advanced.

So the two movements since the hold run in opposite directions and are not commensurable: U1
shrank a set of *known unknowns* in the low-consequence direction; U2 converted the *magnitude*
of the residual from unknown to maximal. Netting them out as "progress, therefore permit a small
step" would be exactly the inference from finite testing to absolute safety the hold refused.

### 2.3 Against ADR-011 D3.2 / D8 / D9, wiring now is a silent allow-list widening.

Under **D3.2**, states 1, 3, 4 and 5 are all "clean, counted"; state 2 FAILs and state 6 ERRORs.
Today the live call site passes no `cte_names` — I confirmed `_scan_sql_text`'s loop calls
`attribute_table_identifier(ident, modules, importer, default_schema)` with four arguments
against a `cte_names: frozenset[str] = frozenset()` default — so state 3 is unreachable and
every CTE-looking identifier falls through the unchanged chain. That baseline's divergence is
**false-fail only** (a legitimate depth-0 `WITH` name reaching state 6
`MODULE_DEPS_TABLE_UNATTRIBUTED`): loud, safe, and already disclosed.

Wiring converts some of those into clean-and-counted. Given §2.1's confirmed precedence, the
conversion set is not confined to names that would otherwise have ERRORed at state 6 — it
includes names that would otherwise have **FAILed at state 2**. That is a reachable, unbounded
transition from FAIL to clean on the gate's own headline invariant. **D9** rejects "any skip
flag, exempt list, path-pattern allowlist, or per-module/per-file suppression" and rejects
"'Unowned ⇒ benign note', in any form" — the point of "in any form" is that the prohibited thing
is the *effect*, not the spelling. An over-wide state 3 that can swallow a real
`CROSS_DOMAIN_SQL_IMPORT` is a suppression path the manifest never declares and the report never
names. It is the R1-F01 class re-entering through the attribution helper.

**D8** cuts the same way rather than mitigating. D8 requires a PASS to be self-evidencing and to
disclose table references by D3.2 state and a coverage note naming what is not examined. A
disclosure can honestly describe a **false-fail** divergence, because the reader is not being
told something is clean that is not. It cannot discharge a **false-clean** one: counting a
masked cross-domain reference in the "CTE" column and listing "the lexer's SQL dialect
limitation" in the coverage note would produce a report that is formally D8-compliant and
substantively misleading. D8 is a constraint on the strength of any conclusion drawn here, not a
footnote that converts an unbounded residual into an acceptable one.

### 2.4 Why not (A), including in a "narrowly bounded" form.

I considered the narrowest wirings available and reject each:

- **Wire state 3 only for identifiers no module owns.** This is semantically attractive — it is
  precisely the bounded residual §2.4(U2) called "arguably disclosable" — but it is *not* the
  current code. Achieving it requires moving the `cte_names` check **after** `_owner_by_prefix`,
  i.e. a precedence change. The prior verdict states in terms: "No reordering is authorised by
  this verdict." Reordering is also not a free implementation detail (see §3.4) and is out of
  this dispatch's single question.
- **Wire state 3 behind a narrowed trust predicate.** §2.2's objection is structural, not a
  matter of predicate strength: the predicates in the design subtract bindings, and the hazard is
  an added one. There is no predicate in the packet that inspects a collected name for
  corroboration.
- **Wire state 3 on a restricted fixture subset / behind a flag.** A per-path or per-module
  restriction on where the gate's attribution semantics apply is the shape D9 names first and
  forbids outright.

A constraint an agent cannot verify at wiring time is not a constraint — the prior hold's §2.5
formulation, which I affirm. Nothing in U1, U2 or D8 supplies a verifiable one.

### 2.5 Why not (C).

ADR-011 needs no amendment for **B** to hold, and the prior hold's §2.6 reasoning survives
unchanged: D3.2 state 3 already prescribes a *lexical* recognizer ("collected lexically at depth
0") and D9 already declines a third-party SQL parser in this contract, so "lexical, with a
residual" is the ADR's own chosen point on the curve. The current unreachable-state-3 baseline is
a conservative under-approximation of state 3 whose only divergence is false-fails, which D8 can
honestly record — and the D8 disclosure has now been authored. The decision is fully decidable on
the inspected evidence without resolving any governing ambiguity, and the decidable answer is the
fail-closed one. Escalating a question that is already answered conservatively would be
ceremony, not caution.

There *is* one genuine governing silence, recorded in §3.4 below: ADR-011 does not pin state 3's
position in the precedence order. That silence is load-bearing only for a **future** proposal to
reorder, which is not what was asked here and which I am explicitly not authorizing. It is logged
as a dependency of any future (A), not escalated as the disposition of this one.

---

## 3. Evidence limits

### 3.1 What the inspected artifacts do establish (demonstrated)

- **D (demonstrated, source-corroborated):** state 3 is consulted **first** in
  `_attribute_bare_identifier`, ahead of the reserved `pg_` check, the owned-prefix check,
  declared-external, and unattributed — for bare identifiers and for default-schema-stripped
  2-part identifiers. Read directly in current source this session.
- **D (demonstrated, source-corroborated):** the live `_scan_sql_text` call site supplies no
  `cte_names`; the parameter defaults to `frozenset()`. ADR-011 D3.2 state 3 is therefore
  **unreachable in the live gate-2 scan today**.
- **D (demonstrated, as reported):** a direct pure-function probe (U2 record) measured
  `bil_invoices` under importer `membership` with `billing` owning `bil_` resolving to
  `state=owned, owner=billing` with an empty CTE set, and to `state=cte, owner=None` with
  `cte_names={'bil_invoices'}`. I did not re-execute this probe; the source ordering I read
  independently predicts exactly that result.
- **D (demonstrated, as reported):** the six U1 named-class tests exist in the repository, assert
  no decoy binding plus a non-vacuity positive control, and were reported passing —
  24/24 focused `cte_scopes`, 224/224 whole test file, Ruff PASS, `git diff --check` clean, under
  a guarded operation whose Sonnet agent transcript carried an independent `mr_verify.py`
  PASS 57/57 `claude-sonnet-5`. I read the test bodies and confirmed their assertion shape.
- **D (demonstrated, recomputed this session):** production source SHA-256 unchanged from the
  verdict-B checkpoint; test SHA-256 advanced to the U1 record's stated value. The U1 increment
  added tests only — **no new production control**.

### 3.2 What they do **not** establish (inferred / untested / out of reach)

- **The finite-test caveat, stated plainly and not softened anywhere above:** the U1 result
  establishes only that the six enumerated classes behaved as specified on the inputs exercised.
  It is **not** a soundness proof over PostgreSQL's unenumerated lexical space, and no claim in
  this record should be read as implying completeness. The same holds for the 512-case seeded
  property corpus, whose own asserted non-vacuity floors (57 non-empty-binding segments, 190
  multi-scope cases) are a floor, not coverage.
- **Absence of a false binding is untested, not shown.** No artifact demonstrates that
  `_cte_scopes` never emits an extra binding; the U2 record is careful to label its own finding "a
  conditional risk demonstration, not evidence that `_cte_scopes` currently produces such a false
  binding." I adopt that distinction. The U2 risk is therefore **live as a precedence/parse-order
  concern** — demonstrably *not* mechanically foreclosed, since the ordering that enables masking
  is the ordering actually in the source.
- **The D8 coverage gap bounds this conclusion.** D8's own disclosure record states that state 3
  is unreachable live and that "passing pure-helper tests does not change that fact or establish a
  live positive proof," and that the gap "does not cure other existing scanner findings or
  constitute assurance that the whole gate has no false PASS." Accordingly this verdict asserts
  nothing about the gate's overall soundness; it decides one wiring question. The statement-scoped
  disclosure paragraph quoted verbatim in the D8 record is explicitly prescribed for a *future
  wired* design and is **not** a description of anything live.
- **Not re-executed by me.** I did not run pytest, Ruff, mypy, the gate, or any probe — the
  operation is report-only and executing the suite would write cache artifacts. All pass/fail
  counts above are *as reported* by the U1/U2 records plus their cited `mr_verify.py`
  attestations, which I accept as stated without re-attestation. My independent contribution is
  the source/test reading and the SHA-256 recomputation.
- **Not read by me:** EIP/TSD §24.1 source text, `_cte_scopes`' implementation body and the
  shared lexer helpers (`_skip_quote_or_comment`, `_lex_quoted_segment`,
  `_skip_block_comment`, `_skip_dollar_quoted_string`), the round-1 independent review report
  itself, and ADR-011 D1/D2/D4/D5/D6/D7 beyond the excerpts cited. The bounded scope forbade an
  open-ended survey. In particular I did **not** verify the lexer helpers' nesting/tag-matching
  logic against PostgreSQL semantics — the U1 tests' *comments* assert that logic; I treated those
  as the tests' rationale, not as verified facts.
- **Nothing could not be located.** Every named artifact in the bounded scope was found at the
  paths listed in §0. There is no missing-artifact gap to report.

### 3.3 Standing blockers, unchanged by this redecision

Round-1 combined independent gate-2 code review remains **BLOCKED, P0=1 / P1=7 / P2=6 / P3=7**,
with R1-F01 formally OPEN. `SCN-MOD001-006`, `-007`, `-095`, `-096` remain **NOT EXECUTED** and
unpromoted. No review counter advanced. No scenario may be promoted from this note. MOD-001 is
uncertified; WIP=1 holds and MOD-002 stays locked.

### 3.4 One governing silence, logged not escalated

ADR-011 **D3.3** is headed "Resolution precedence is pinned," but its four rules pin part-count
handling, default-schema stripping, `owned_schemas`/`default_schema` disjointness, and the
schema-vs-prefix conflict rule. **D3.4** pins only "reserved identifiers, checked **before
ownership resolution**." Neither D3.3 nor D3.4 nor D3.2's state table pins state 3's position
relative to states 1/2 — or relative to state 4, which the current code also pre-empts
(`if name in cte_names` precedes `if name.startswith("pg_")`; both are clean states, so this
particular ordering has no false-clean consequence and is noted as an observation, not a finding).
The CTE-first ordering is therefore an **implementation choice in a region the ADR leaves
unspecified**, not a contract requirement. Consequence: a future proposal to make state 3
last-resort is not a mere refactor — it would set contract semantics ADR-011 has not set, and
needs its own recorded decision before any code moves. Not decided here.

---

## 4. Smallest next legal action

**Given verdict B, the single smallest legal next action is: close the CTE/state-3 lane at
B HOLD plus the already-authored D8 disclosure, and return the gate-2 effort to the oldest
highest-severity still-open round-1 finding (the P0, R1-F01 class) under the existing BLOCKED
round-1 review.**

Concretely, that means the orchestrator's next bounded operation targets a round-1 blocking
finding, routed per `ADR-005` / the Development Constitution — **not** a further CTE increment.
The prior hold's §4 list is now fully discharged: U1 tests authored (done), U2 precedence
recorded read-only (done), D8 coverage-gap disclosure authored (done). There is no remaining
pre-wire item in that lane, and B means there is no post-wire item either. Continuing to spend
increments on an enhancement lane whose current state is *maximally fail-closed* while a P0 and
seven P1s sit open on the same gate inverts the priority order.

**Explicitly not permitted by this verdict (exhaustive, for the avoidance of doubt):**
no edit to `_scan_sql_text`'s attribution loop; no `cte_names` argument added at the live call
site; no change to `_attribute_bare_identifier`'s or `attribute_table_identifier`'s resolution
order; no change to the `cte_names` default; no flag, path pattern, per-module or per-file
restriction that would make state 3 reachable anywhere; no ADR-011 amendment; no scenario
execution or promotion; no real-tree ownership binding (separately
`BLOCKED: OWNER_APPROVAL_REQUIRED`).

**If someone later wants to re-open (A), the evidence that would be required — stated so the bar
is not renegotiated downward later:**

1. A recorded decision resolving §3.4's governing silence, pinning state 3's position in the D3.2
   precedence order as a contract term. If the proposal is to make state 3 last-resort
   (consulted only after states 1/2/4/5 and before state 6), that is a change to ADR-011's
   identifier-attribution semantics and needs its own ADR amendment or successor decision and a
   fresh named-lead dispatch — **not** a bounded implementation increment. Whether it also needs
   owner approval as a material architecture change is itself part of that decision, and is not
   settled here.
2. With state 3 pinned last-resort, a **positive** demonstration that the only reachable
   divergence from today's baseline is state-6-ERROR-becomes-clean, with the state-2 masking path
   shown mechanically foreclosed by construction (not by test corpus size) — because that is the
   only shape under which a D8 disclosure can honestly discharge the residual.
3. A production-side control that inspects a *collected* binding rather than only subtracting
   bindings, closing the §2.2 asymmetry — or an argued, recorded demonstration that no such
   control is needed once (2) holds.
4. A fresh independent review round that is *not* self-approved by the implementing tier, and
   that re-verifies (2) and (3) by its own execution.

Until all four exist in the repository, the **ORCHESTRATOR QUALIFICATION HOLD stands** and state
3 remains unreachable.

---

*No file other than this one was created, modified, deleted or appended by this operation: no
source, test, ADR, review record, scenario catalog, ledger, bug registry, `CURRENT_STATE.md`,
`CURRENT_HANDOFF.md`, `REVIEW_IN_FLIGHT.md`, no `git add`, no commit, no `graphify update`. No
owner-reserved action was taken or implied — no spend, no paid service, no real member data, no
production deploy or promotion, and no material product/pricing/business/architecture/scope
change (verdict B withholds a change rather than making one).*
