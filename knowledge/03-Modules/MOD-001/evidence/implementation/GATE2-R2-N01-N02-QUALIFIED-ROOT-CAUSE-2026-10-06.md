---
doc: GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE
module: MOD-001
work_unit: GOV-01-R04 — TSD §24.1 gate 2 (module-dependency / cross-domain SQL lint)
scenarios_in_scope: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
date: 2026-10-06
role: veyro-lead (registered architecture / ADR-decision role, Opus tier, fresh bounded
  adjudication dispatch). NOT an independent code review, NOT a security review, NOT a
  gate-2 round verdict, NOT a scenario verdict, NOT a module certification. Advances no
  review counter.
model: claude-opus-5[1m] — Opus 5 (1M context), as reported by this environment
model_attestation: NONE RUN BY THIS SESSION — see §10
decision_type: qualified root-cause / architecture-contract adjudication
primary_outcome: R2-N01 is an ADR-011 extraction-totality contract gap (R2-N02 UPHELD as
  the root cause, R2-N01 as its instance). Binding amendment authored as a dated addendum
  to ADR-011 (clause D6.7 + D7.1 amendment-by-reference + D8 truthfulness correction).
  Within existing governing scope; NO owner approval required.
b_hold_verdict: B HOLD CONTINUES, unchanged and unreopened. One false premise in its §4
  corrected (§7).
scenario_verdict: NO SCENARIO PROMOTED. SCN-MOD001-006/-007/-095/-096 remain NOT EXECUTED
  and unpromoted. MOD-001 uncertified. WIP=1; MOD-002 locked.
snapshot_source_sha256: b9e012a47a10935fc5dd390383b6907131c65be01372b5b02dc6d0b47e8e6484
snapshot_tests_sha256: 83779ff7c49626be57200374024f4b262879d86291b4d3b116581c4b38ac0288
git_head: e481b814a80923849dddfe7a49319112aae7b023 (unchanged by this session)
fixture_scope: fixture-scoped; real-tree domain ownership DEFERRED and separately
  BLOCKED: OWNER_APPROVAL_REQUIRED
---

# Gate-2 R2-N01 / R2-N02 — qualified root-cause and contract adjudication

## 0. Question decided, and bounds honored

**Exactly four questions, as dispatched:**

1. Is R2-N01 an ADR-011 extraction-totality **contract** gap, or a code-only defect?
2. What is the exact fail-closed invariant, and what are the bounded acceptance /
   negative-test obligations for **all plain literal table positions**?
3. Is this within existing governing scope, or does it require owner approval?
4. What is the explicit B HOLD / scenario verdict?

**Bounds honored — none of the following was designed, proposed, or performed:** live CTE
state-3 wiring; any reorder of D3.2 precedence; any code or test implementation; any review
dispatch; any scenario promotion; any module certification. No `cte_names` argument, call
site, default, or resolution order was touched or recommended. No
`contracts/modules/ownership.json` was authored or made authorable.

**Baseline integrity:** `verify_baselines.py` **PASS 4/4** this session (Blueprint
`80f4b381…`, TSD `0d41c8a1…`, EIP `e5b5ec3b…`, design bundle `c96f77ab…`) against
`PROJECT_INDEX.md`. Precedence applied throughout: Blueprint > TSD v1.4.1 > design bundle >
EIP v1.4.1.

**Artifacts read** (paths, so a future reader can retrace): `SESSION_BOOTSTRAP.md`;
`PROJECT_INDEX.md`; `CURRENT_STATE.md` (current `current_as_of` entry only — the file is 464
lines and was not read end to end); `DEVELOPMENT_CONSTITUTION.md`; `MODEL_ROUTING.md`;
`REVIEW_IN_FLIGHT.md`; `AUTONOMOUS_CONVERGENCE_STATE.json`;
`knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md` (in full);
`evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2-2026-10-06.md` (in full);
`evidence/implementation/GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md` (in full, the
B HOLD); `GATE2-R1-F01-R2-ROUND-COUNTER-RECONCILIATION-2026-10-06.md`;
`MOD-001/REQUIREMENTS.md` GOV-01-R04; `MOD-001/SCENARIOS.md` SCN-006/007/095/096 rows;
`MOD-001/IMPLEMENTATION.md` §4 gate-2 row; `TSD_MIRROR.md` §24.1 gate-2 (lines 11603-11608)
and §6.3 (lines 1521-1577); and the live source
`tools/validate_architecture_gates.py` at the cited lines.

**`CURRENT_HANDOFF.md` was NOT read** — it is 258.2 KB and exceeded the single-read limit;
this session did not page through it. Disclosed rather than omitted. Nothing in this decision
depends on it, and the convergence state's own `nextAutonomousAction` (§8) independently
establishes that this dispatch is the sanctioned next action.

---

## 1. Verdict

**R2-N01 is an ADR-011 extraction-totality contract gap. R2-N02 is UPHELD, and is promoted
from "a finding alongside R2-N01" to "the root cause of which R2-N01 is one instance."**

The reviewer hedged R2-N02's severity in its own §9 ("P1 is arguable … a reader who regards
ADR amendment as implied by R2-N01's fix could rate it P2"). That hedge is resolved
**against** the P2 reading: a code-only fix at the observed sites closes the instances and
leaves the class unconstrained, which is precisely the failure mode ADR-011's own
"Alternatives considered" table rejected when it declined to merely widen the regexes. The
contract must move first; the code follows the contract.

**A binding amendment is needed and is authorized under the existing governing baseline.**
It is recorded as a dated, narrowly scoped addendum to ADR-011 — new clause **D6.7**, plus an
amendment-by-reference to **D7.1** and a correction to **D8**'s completeness claim. ADR-011's
historical decision text is preserved byte-unchanged; the addendum is appended, per this
project's own convention. **No owner approval is required** (§6).

**B HOLD: continues, unchanged, unreopened** (§7). **No scenario promoted** (§9).

---

## 2. Independent reproduction — I did not take the review's word for it

R2-N01's reproducer was re-executed from scratch on my own synthetic fixture
(`/tmp/g2lead/`, outside the repository; two modules `membership`/COM-01/`mem_` and
`billing`/COM-03/`bil_` — a real §6.3 pair — `default_schema: "public"`, no cross-module
Python import anywhere, the SQL string the sole content of `membership/q.py`). Source and
test SHA-256 re-verified identical to the reviewed snapshot before and after.

| SQL (sole content of `membership/q.py`) | exit | verdict |
|---|---|---|
| `SELECT a FROM bil_invoices` | 1 | FAIL — control |
| `SELECT a FROM mem_roster JOIN bil_invoices ON 1=1` | 1 | FAIL — control |
| `SELECT a FROM mem_roster` | 0 | PASS — control |
| `UPDATE mem_roster SET x = (SELECT y FROM bil_invoices)` | 1 | FAIL — control |
| `SELECT a FROM mem_roster, bil_invoices` | **0** | **PASS — defect** |
| `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` | **0** | **PASS — defect** |
| `DELETE FROM mem_roster USING bil_invoices` | **0** | **PASS — defect** |
| `SELECT a FROM mem_roster, bil_invoices, bil_ledger` | **0** | **PASS — defect, 2 missed** |
| `SELECT a FROM mem_roster, ONLY bil_invoices` | **0** | **PASS — defect** |
| `INSERT INTO mem_t SELECT x FROM mem_a, bil_invoices` | **0** | **PASS — defect, NEW** |
| `SELECT a FROM mem_roster, nobody_owns_this` | **0** | **PASS — defect, NEW** |

**CONFIRMED, not merely plausible.** R2-N01 reproduces exactly as reported. Two of the eleven
rows are my own additions and are **not** in the review's list; both matter (§3.3, §3.4).

The disclosure was re-read on the comma-list PASS. The run reports
`[module-deps] PASS — checked 6 subject(s)` and the D8 note reads `1 table-position
identifier reference(s) extracted and attributed`, and the phrase **"the counts are complete
for this run"** appears **5 times** in that same report. Two table-position identifiers were
present in fully static text the scanner received and examined; one was never extracted. The
completeness claim is **affirmatively false** on precisely the dimension D8 exists to make
trustworthy.

---

## 3. Causal chain

### 3.1 The three-layer pipeline, and which layers the contract governs

Gate 2's SQL path is three layers:

| Layer | Function | ADR-011 clause |
|---|---|---|
| **1 — trigger** | `_is_sql_ish` / `_TRIGGER_VERB_RE`: is this text SQL at all? | **D6.1** — a deliberate over-approximation |
| **2 — extraction** | `_extract_table_identifiers`: text → multiset of table-position identifiers | **none** |
| **3 — attribution + backstop** | `attribute_table_identifier` (D3.2's six states) and the D6.3 I-1 zero-identifier backstop | **D3.2, D6.3, D7.1** |

**ADR-011 governs layers 1 and 3 and says nothing whatsoever about layer 2.** D3.2's opening
sentence — "Every identifier in a table position resolves to exactly one of six states" —
and D8's self-evidencing requirement both *presuppose* that layer 2 delivers every table
position to layer 3. The ADR never imposes that obligation. That silence is the gap.

Verified in source: `_TABLE_KEYWORD_RE` (`:2674`) is the five-keyword set
`FROM|JOIN|INTO|UPDATE|TABLE`, and `_extract_table_identifiers` (`:2821-2835`) takes
**one identifier per keyword match**. The code's own comment at `:2672-2673` states the
layer-2 silence outright: *"widening extraction itself is separate, still-unimplemented
SQL-lexer work (ADR-011 D6)."* The implementer knew layer 2 was partial and believed layer 3
covered it.

### 3.2 The precise mechanism: partial extraction is **less safe** than total failure

Layer 3's backstop is **statement-scoped**, not position-scoped:

```python
idents = _extract_table_identifiers(text)
if not idents:                      # fires only when NOTHING extracted
    if _implies_table_position(text):
        ... MODULE_DEPS_SOURCE_UNINSPECTABLE  (ERROR, exit 2)
```

So the first identifier that extracts cleanly **disarms the refusal that would otherwise
have covered the whole statement**. Every remaining table position in that statement becomes
invisible — not disclosed, not counted, not noted.

This is the heart of it, and it is a **contract-level property, not a coding slip**:

> **In the current design, extracting one identifier is strictly less safe than extracting
> none.**

D6.1's monotonicity argument — "a broader trigger can only ever yield strictly more ERRORs,
so it may be widened freely" — is sound for layer 1 and **does not transfer to layer 2**.
Trigger breadth is monotone toward refusal. Extraction *partiality* is monotone toward
**silence**, because a partial result simultaneously (a) misses positions and (b) suppresses
the backstop. ADR-011 adopted the layer-1 monotonicity argument and never noticed that the
layer it left unspecified has the opposite polarity. That inversion is R2-N02, and it is the
root cause.

The code's own comment at `:2678-2682` asserts the property this defect defeats — *"a keyword
the extractor cannot yet resolve must still fail closed via the backstop below, never pass
silently"* — **unconditionally**. It holds only for statements with zero extracted
identifiers. The docstring of `_scan_sql_statement` (`:3209`) makes the same unconditional
claim: *"No identifier falls through without reaching one of the six states above."* True of
*extracted* identifiers; false of identifiers *in the text*. Both are honest statements of
intent that the statement-scoped guard does not deliver.

### 3.3 The defect defeats **two** of D3.2's fail-closed states, not one — not in the review

The review framed R2-N01 as a false *clean* over **state 2** (another module's table,
`CROSS_DOMAIN_SQL_IMPORT`). My row `SELECT a FROM mem_roster, nobody_owns_this` → **PASS
exit 0** establishes that **state 6** (`MODULE_DEPS_TABLE_UNATTRIBUTED`, ERROR-on-unknown) is
defeated by the identical mechanism.

That materially enlarges the finding. State 6 **is** ADR-011's polarity inversion — the
single clause the ADR identified as what "makes the governing allow-list text enforceable"
and as the defence-in-depth that would catch R1-F01 "even if D3.1 normalisation regressed."
Under R2-N01 both layers of that defence are bypassed at once, because neither is consulted.
ADR-011 **D9** rejects *"'Unowned ⇒ benign note', in any form"*, and reasons explicitly that
"the point of 'in any form' is that the prohibited thing is the *effect*, not the spelling."
The live behaviour is **worse than the prohibited note**: there is no note at all, and the
report affirmatively asserts the count is complete. The thing D9 forbids is present in a
strictly more harmful form than the form D9 named.

### 3.4 An independent second hole: the table-position keyword vocabulary is itself incomplete

`_TABLE_POSITION_KEYWORDS` (`:1503-1504`) is `{FROM, JOIN, INTO, UPDATE, TABLE, ONLY,
REFERENCES}`. **`USING` is absent.** It is in neither the extractor's set nor the backstop's
set. So `DELETE FROM mem_roster USING bil_invoices` is missed **twice over**: the extractor
never visits the `USING` position, and the backstop — even if it were position-scoped —
would not recognise a position there either.

This is a second, logically independent defect riding the same reproducer. It matters because
it proves the remedy cannot be "scope the backstop to the table position" alone (the
reviewer's own §11 suggestion): a position introduced by a keyword in **no** list is invisible
to a position-scoped backstop too. Vocabulary completeness must be a **floor**, and the
fail-closed property must not depend on it. §4 is built on that constraint.

### 3.5 Why the test suite is silent

466 tests pass with the defect live. The shape `SELECT * FROM a, b` **does** appear in the
corpus (`test_validate_architecture_gates.py:3785`, `:3967`, `:3977`, `:4024`, `:4119`,
`:4938`) but only inside `_cte_scopes` / `_collect_cte_names` **pure-helper** tests — i.e.
exclusively through the helper the B HOLD forbids wiring, and never as an extraction or
attribution assertion. ADR-011's Follow-up mutation list targets "the **new clean states**"
(states 3/4/5, `_root`, a report counter) and contains **no mutant against layer 2 at all**.
The corpus could not have caught this, and the contract never asked it to. §5 fixes that.

### 3.6 Causal chain, stated as a chain

1. §24.1 is written as an **allow-list** ("may reference **only** their owned table
   prefix/schema"), so an unrecognised identifier may never reach PASS.
2. ADR-011 D3.2 implements that by **inverting the polarity**: state 6 ERRORs on anything
   unrecognised. D6.1 secures layer 1 with a monotone over-approximation. D6.3 secures the
   zero-identifier case.
3. ADR-011 **never states an obligation on layer 2**, and D7.1 instead treats extraction as a
   given primitive ("the discriminator is whether an identifier was actually extracted").
4. The implementer therefore built layer 2 as a narrow five-keyword, one-identifier-per-match
   recogniser, documented it as "still-unimplemented SQL-lexer work," and relied on D6.3's
   backstop to fail closed — a reliance the code states in terms.
5. D6.3's backstop is **statement-scoped** (`if not idents:`), so partial extraction disarms
   it. Partial extraction is therefore less safe than no extraction.
6. Consequence: any statement mixing one extractable table position with any other table
   position yields a silent **PASS exit 0**, defeating **state 2** (cross-domain FAIL) and
   **state 6** (unattributed ERROR) simultaneously, with a report that claims its counts are
   complete.
7. Root cause = step 3 (the contract's layer-2 silence, R2-N02). Instance = step 6
   (R2-N01). A fix applied only at step 6's observed sites restores the instances and leaves
   step 3 — and therefore the class — untouched.

---

## 4. The binding fail-closed invariant (contract text: ADR-011 addendum, clause D6.7)

The amendment is recorded in
`knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md` under
**"Addendum 2026-10-06"**. Its operative content, restated here so this record stands alone:

**D6.7.1 — Monotone-bias rule (extraction is an over-approximation).** The extractor must
over-approximate the true table-position set, for the mirror of D6.1's reason: an
**over**-extracted identifier reaches D3.2 state 6 and ERRORs — loud, bounded, correctable —
while an **under**-extracted one reaches no state at all and is silently clean. Where the
lexer must guess, it guesses toward extracting. Consequently **narrowing the extractor is
never a free optimisation** and requires its own recorded decision.

**D6.7.2 — Per-position fail-closed rule (the operative R2-N01 fix).** The D6.3 I-1 backstop
and the dangling-keyword refusal are evaluated **per table position**, never per statement.
A triggered statement in which **any** recognised table-position signal did not yield an
identifier carried to D3.2 attribution is **ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE`** naming
that signal, **regardless of how many other identifiers extracted cleanly**. The
`if not idents:` guard is replaced by an accounting comparison between recognised signals and
attributed identifiers. Stated as the invariant to test against:

> For any statement text T, the gate's outcome must be **no weaker** — on the ordering
> `clean < FAIL/ERROR` — than the outcome it would produce for T if the extractor had
> returned nothing. **Partial extraction may never be safer than total extraction failure.**

**D6.7.3 — List positions.** A table-position keyword introducing a list (`FROM`, `JOIN`,
`INTO`, `USING`, `REFERENCES`, `ONLY`, and the `_BARE_VERB_FORMS`) extends across commas at
the same parenthesis depth until a clause boundary or statement end. **Every element is its
own table position** and is individually subject to D6.7.2. An element the lexer cannot
reduce to an identifier is ERROR, never dropped. Where the clause boundary is itself
uncertain, the walk **continues** (over-extraction, per D6.7.1) rather than stopping — an
over-extracted column name ERRORs at state 6, which is the safe direction.

**D6.7.4 — Vocabulary is a floor, not the mechanism.** `_TABLE_POSITION_KEYWORDS` must remain
a superset of the extractor's keyword set and must additionally include **`USING`** (absent
today — a demonstrated hole, §3.4). Vocabulary completeness is a floor that lowers the ERROR
rate; it is **not** the fail-closed mechanism, and no clause may be read as making the gate's
soundness depend on it. A keyword added to one set widens both at once — the existing
`_implies_table_position` seam already exists for exactly this and must be preserved.

**D6.7.5 — D8 truthfulness.** "the counts are complete for this run" may **not** be asserted
for the table-reference attribution dimension unless the run established D6.7.2's accounting
held for every subject. Otherwise the figure is disclosed as a **lower bound**, in the same
terms D7.2 already requires for the FAIL partition. The current unconditional sentence is
affirmatively false and must be removed or conditioned. A false completeness claim is worse
than a disclosed limit: it is the sentence a reader relies on when judging whether a PASS
means anything.

**D6.7.6 — D7.1 amended by reference.** D7.1's discriminator — "whether an identifier was
actually extracted" — is well-founded only under D6.7.1-.3. It now reads: *whether every
recognised table position yielded an identifier.* A silently-unextracted position is
`MODULE_DEPS_SOURCE_UNINSPECTABLE`, never invisible. D7.1's disjointness with
`MODULE_DEPS_TABLE_UNATTRIBUTED` is unchanged and still holds.

**D6.7.7 — Explicit non-expansion.** D6.7 authorizes **nothing** beyond the above. It does
not authorize a third-party SQL parser (D9's deferral stands); does not touch D3.2 state 3,
`cte_names`, the live call site, the `cte_names` default, or the resolution order (the B HOLD
stands and governs that lane); does not touch real-tree domain ownership (owner-reserved,
untouched, not a dependency); and adds no skip, exempt, allowlist, or suppression path of any
kind.

### 4.1 Alternatives rejected

| Alternative | Consequence | Verdict |
|---|---|---|
| Widen `_TABLE_KEYWORD_RE` only | Moves R2-N01's seven observed instances without touching the class; the partial-extraction-disarms-backstop asymmetry survives intact and the next unlisted keyword reproduces the P0. This is the closed-deny-list-over-an-open-input-space treadmill ADR-011's own Alternatives table already rejected once | **Rejected** |
| Scope the backstop to the table position, vocabulary unchanged (reviewer's §11 suggestion) | Necessary but **not sufficient**: a position introduced by a keyword in no list — `USING` today, §3.4 — is invisible to a position-scoped backstop too | **Rejected as the whole fix; adopted as D6.7.2, one of four parts** |
| Keep statement scope, ERROR when `len(idents) < len(signals)` | Same defect at a different threshold — it still reasons over the statement aggregate, and a statement with two signals and two identifiers extracted from the *same* position passes | **Rejected** |
| Full residue accounting: classify **every** identifier-shaped token, unclassified ⇒ ERROR | Structurally the most sound shape, and the long-term target. But classifying every column, alias, function and type name *is* parsing, which needs the D9-deferred parser capability; and it would ERROR on ordinary SQL at a rate that generates exactly the pressure to weaken the gate that D6.3's own correction exists to avoid | **Rejected for now**; logged in §8 as the shape to adopt if a parser capability is ever qualified |
| Treat an unaccounted position as **FAIL** rather than ERROR | Identical reasoning to ADR-011's existing state-6 row: the gate cannot name an owner it does not know, so a FAIL would have to cite an owner it never resolved | **Rejected** — ERROR, exit 2, is the honest classification; both fail CI, which is what §24.1 requires |
| Disclose R2-N01 as a residual under D8 and proceed | D8 can honestly describe a false-***fail***; it cannot discharge a false-***clean***. This is the B HOLD's own §2.3 reasoning, and it applies here with the polarity turned against the gate. A formally D8-compliant, substantively misleading report is the outcome to avoid | **Rejected** |
| Defer until the real-tree manifest exists (no current real-tree exposure) | SCN-MOD001-007 is **Blocker**-tier and **fixture-scoped**; its denial must be reliable on fixtures *now*. R2 established it is not. Deferring would promote a Blocker scenario on a denial the project has demonstrated is unreliable | **Rejected** |
| Narrow D6.1's trigger to offset the higher ERROR rate D6.7 produces | Trades a loud refusal for a silent skip — the exact exchange D6.1 was written to forbid | **Rejected**, and explicitly forbidden to the implementer (§5.4) |

---

## 5. Code and test acceptance criteria for a later implementer

Routing is unchanged: **`veyro-implementer` (Sonnet)** per ADR-005 and ADR-011's own
Follow-up. No clause of D6.7 requires Opus-reserved judgment — each is a concrete bounded
obligation with its stated expected outcome. ADR-005 Decision 1's three Opus-critical slices
for MOD-001 do not include gate 2's SQL extractor. **No routing change; no ADR-005
amendment.**

### 5.1 Negative corpus — every row asserts an **exact outcome code**, never merely non-zero

Fixture: two modules, `membership`/COM-01/`mem_` and `billing`/COM-03/`bil_`,
`default_schema: "public"`, **no** cross-module Python import anywhere (so the table
identifier is the sole cross-module signal). Note `public_interfaces` entries are validated
strictly under `modules.<name>.` — a run authored as `app.modules.<name>.<x>` is refused as
`MODULE_DEPS_GATE_INPUT_INVALID` before the scan, which is correct and must not be mistaken
for a scan result. Each row must be asserted **both** as a `.py` string literal **and**
through a `.sql` file.

| # | SQL | Required outcome |
|---|---|---|
| N1 | `SELECT a FROM mem_roster, bil_invoices` | `CROSS_DOMAIN_SQL_IMPORT` naming membership→billing and COM-01→COM-03, exit 1. `MODULE_DEPS_SOURCE_UNINSPECTABLE` exit 2 is acceptable **only** if the lexer declines that element. **Never exit 0.** |
| N2 | `SELECT a FROM mem_roster, nobody_owns_this` | `MODULE_DEPS_TABLE_UNATTRIBUTED`, exit 2 — **state 6 restored** (§3.3) |
| N3 | `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` | non-zero, exact code asserted |
| N4 | `DELETE FROM mem_roster USING bil_invoices` | non-zero — requires D6.7.4's `USING` addition |
| N5 | `SELECT a FROM mem_roster, bil_invoices, bil_ledger` | non-zero **and** the report must account for **both** missed identifiers (2, not 1) |
| N6 | `SELECT a FROM mem_roster, ONLY bil_invoices` | non-zero, exact code asserted |
| N7 | `INSERT INTO mem_t SELECT x FROM mem_a, bil_invoices` | non-zero, exact code asserted |
| N8 | `SELECT a FROM mem_roster m, bil_invoices b` | non-zero — bare-alias list form |
| N9 | `SELECT a FROM mem_roster AS m, bil_invoices AS b` | non-zero — `AS`-alias list form |
| N10 | `SELECT a FROM mem_roster, "BIL_INVOICES"` | non-zero — D3.1 case preservation composed with D6.7.3 |

### 5.2 Positive controls — must still PASS exit 0, so the fix is not vacuous over-ERRORing

A fix that ERRORs on everything satisfies §5.1 and is worthless. These rows are what
distinguish an attribution-based fix from a blanket refusal, and **P2 is the discriminating
one**:

| # | SQL | Required outcome |
|---|---|---|
| P1 | `SELECT a FROM mem_roster` | PASS exit 0 |
| **P2** | `SELECT a FROM mem_roster, mem_events` | **PASS exit 0** — same-module comma list must stay clean |
| P3 | `SELECT 1` / `SELECT now()` / bare `ANALYZE` / bare `VACUUM` | PASS exit 0 — D6.3's clean zero-table class preserved unchanged |
| P4 | `SELECT a FROM mem_x JOIN mem_y USING (id)` | **PASS exit 0** — `USING (col)` in a join condition is a **column** list, not a table position. This is the one real false-positive hazard D6.7.4's `USING` addition creates; the corpus must pin **both** directions (N4 and P4) or the addition is unsafe |
| P5 | the permitted §6.3 COM-01→COM-03 synchronous edge | PASS exit 0, unchanged |

### 5.3 Mutation controls — a surviving mutant is a **blocker for the dispatch**, not a note

ADR-011's Follow-up mutation set contains no layer-2 mutant (§3.5). These are added:

- **M-E1** restore `if not idents:` statement scope → N1 must fail.
- **M-E2** remove `USING` from the keyword set → N4 must fail.
- **M-E3** stop the comma-continuation walk after the first element → N5 must fail.
- **M-E4** make an unaccounted position clean instead of ERROR → every N row must fail.
- **M-E5** hardcode the signal/identifier accounting comparison true → every N row must fail.
- **M-E6** re-assert "counts are complete for this run" unconditionally → a report-**text**
  assertion must fail (D6.7.5 needs its own test; no behavioural test covers a note's wording).
- **M-E7** narrow the extractor so it silently drops one list element → must be killed, which
  is what proves D6.7.1's bias is **tested** rather than merely documented.

### 5.4 Scope boundaries — what the implementer may NOT do

No change to D3.2 state 3, `cte_names`, the live call site, the `cte_names` default, or any
resolution order (**B HOLD**, §7). No third-party SQL parser (**D9**). No
`contracts/modules/ownership.json` (**owner-reserved**). No skip / exempt / allowlist /
path-pattern / per-module / per-file suppression (**D9**). **No narrowing of D6.1's trigger
to compensate for D6.7's higher ERROR rate.** No scenario execution or promotion. No
self-review and no self-certification.

### 5.5 Evidence obligations

Re-run §2's eleven-row table verbatim and record each exit code. Record the D8 attribution
note text for N1 **before and after**, so the removal of the false completeness claim is
auditable. Pin source and test SHA-256 before and after. Demonstrate **non-vacuity** by
reintroducing the pre-fix shape in a throwaway full-structure copy outside the repository and
confirming each negative test then fails with the expected signature — this project's
standing convention. Carry **"fixture-scoped; real-tree domain ownership DEFERRED"** on the
face of the record. Report the full test count and `ruff`/`mypy` status honestly, including
any pre-existing unrelated failures rather than normalizing them away.

### 5.6 One adjacent precondition, not re-adjudicated

R2-N04's `tools/validate_architecture_gates.py:249-257` paragraph documents, as current
behaviour, the exact "unowned ⇒ not flagged — only counted and disclosed in a note" terminal
state **D9 forbids "in any form"**. Its severity and routing stay as R2 set them (P2,
self-contained, no contract change needed). But under **DC-12** that paragraph must be
corrected **before** the D6.7 remediation record can honestly claim the extraction-totality
work is finished: leaving it standing is what would let a future session "restore" the
behaviour this decision exists to forbid. Stated as a precondition of record honesty, not as
a new finding of mine.

---

## 6. Scope and authority determination

**Within existing governing scope. NO owner approval required.**

The authority is ADR-011's own Follow-up, which delegates exactly this: *"Judge whether this
ADR itself has a gap — if so, report it as a finding against ADR-011, **which `veyro-lead`
amends**."* R2-N02 is that finding, this role is that role, and this is that amendment. The
same Verdict B split under which ADR-011 was itself decided without owner approval
("an ADR fixing gate 2's input contract — schema and semantics only, binding no real
domain") covers D6.7, which is strictly narrower than ADR-011.

Conformance against Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1 — D6.7 changes:

- **no TSD scope.** It *implements* §24.1's own allow-list wording ("may reference **only**
  their owned table prefix/schema") and §6.3's rejection of "direct repository/table
  coupling," both read this session from `TSD_MIRROR.md` (§24.1 at lines 11603-11608; §6.3's
  rule at line 1577). A foreign key to another module's table is §6.3's textbook instance and
  it currently PASSes. D6.7 moves the implementation **toward** the governing text, not away.
- **no domain model.** No directory is bound to any domain code, prefix, or schema; no
  manifest is authored or made authorable. ADR-011's scope limit is inherited verbatim.
- **no product, pricing, or business decision.** A CI lint's extraction contract is none.
- **no module scope.** GOV-01-R04 already requires this gate, with "a deliberate-violation
  fail-closed proof" for each of the seven gates as an explicit acceptance criterion
  (`REQUIREMENTS.md`). D6.7 is what makes gate 2's proof real.
- **no routing change.** ADR-005 unchanged; implementation stays `veyro-implementer`
  (Sonnet). DC-17's routing-change sub-clause is not triggered (§5).
- **no capability.** Stdlib-only lexical work. **D6.7 does not force a parser** — signal
  counting, comma-continuation at parenthesis depth, and accounting comparison are all
  lexically decidable with the functions already present (`_lex_dotted_identifier`,
  `_implies_table_position`, `_d8_statement_subjects`). The parser-requiring alternative was
  identified and **rejected** (§4.1, "full residue accounting"). D9's deferral stands, so no
  `CAPABILITY_POLICY.md` lifecycle is opened and no registry row is needed.
- **strictly more refusal, never more clean.** Every D6.7 clause adds ERROR surface; none
  removes any. It is impossible for D6.7 to weaken any gate — the same monotonicity argument
  D6.1 made for layer 1, applied this time to the layer where it actually holds.

**No spend. No paid service. No real member data (synthetic fixtures under `/tmp` only). No
deploy or production action. No material product/pricing/business/architecture/scope change.**

The one owner-reserved item on this surface — binding the six `backend/app/modules/`
scaffolds to domain codes and owned table prefixes — remains **`BLOCKED:
OWNER_APPROVAL_REQUIRED`**, is untouched by this decision, and is **not** a dependency of
anything here.

---

## 7. B HOLD verdict — CONTINUES, with one false premise corrected

**The U1/U2 qualified B HOLD remains governing and fully in force. It is not reopened, not
weakened, and not re-litigated.** Nothing in R2-N01 or D6.7 argues for live state-3 wiring;
R2-N01 is reachable **today with `cte_names` empty**, it is a false *clean* rather than the
false *fail* the B HOLD accepted, and remediation requires touching state 3 in **no**
direction. The B HOLD's own exhaustive prohibition list (§4: no edit to `_scan_sql_text`'s
attribution loop's `cte_names` argument, no change to `_attribute_bare_identifier`'s or
`attribute_table_identifier`'s resolution order, no change to the `cte_names` default, no
flag or path restriction making state 3 reachable) is carried into D6.7.7 unchanged, and its
four-item re-opening bar is **not** renegotiated downward by anything here.

**One correction I am obliged to record.** The B HOLD's §4 characterises the scanner's
current state as *"maximally fail-closed."* **That premise is false**, and I confirmed it by
my own execution (§2), not by accepting the R2 reviewer's claim. The B HOLD's *verdict*
survives untouched — it withheld a change, and withholding was and remains correct — but the
priority rationale built on that premise was reasoned over the CTE lane in isolation and did
not have R2-N01 in view. The R2 reviewer called this "a finding about the scanner, not about
the hold" (§6); I agree, and record it as a bounded premise correction rather than a
redecision. Consistency note, so this is not misread as tension: the B HOLD's §4 directed
effort back to "the oldest highest-severity still-open round-1 finding (the P0, R1-F01
class)." **R2-N01 *is* the R1-F01 class, re-opened one layer down.** This decision and that
direction point the same way.

**Also unchanged:** ADR-011 **D3.3/D3.4's governing silence** on state 3's position in the
precedence order, logged in the B HOLD's §3.4, is **not** resolved here and was not
permitted to be. D6.7 adds no precedence term. Any future proposal to make state 3
last-resort still needs its own recorded decision and a fresh named-lead dispatch, exactly as
the B HOLD states.

---

## 8. Dependencies, blockers, and what is not decided here

**No blocker on the amendment itself** — it is authorized under the existing baseline (§6)
and lands with this decision. The remediation that follows is gated, in order, on:

1. The ADR-011 addendum existing in the repository — **satisfied by this decision**.
2. A bounded **`veyro-implementer` (Sonnet)** dispatch against §5, routing unchanged.
3. R2-N04's `:249-257` correction, as a record-honesty precondition (§5.6).
4. A fresh independent **round-3 `veyro-code-reviewer` (Opus)** review, not self-approved
   (DC-06), verifying §5.1/§5.2 by its own execution and re-attempting the §2 reproducer.
5. A `REVIEW_IN_FLIGHT.md` `IN_FLIGHT` claim written **before** that dispatch returns, per
   `SESSION_BOOTSTRAP.md` §4. The claim is **CLEAR** as of this session and I did not write
   to it — this decision dispatched no review.

**Round-count position, verified not assumed:** `AUTONOMOUS_CONVERGENCE_STATE.json` records
this unit at `reviewRoundsCompleted: 2`, `remediationRoundsCompleted: 1`,
`convergenceStatus: ACTIVE`, `noProgressIterations: 0`. SCN-070's five-review history and
DOM-002's four are **separate semantic units** with their own preserved counters and
restrictions; neither bears on this unit, and neither was reset, reused, or touched. **No
absolute-cap condition is met here.** The same file's `nextAutonomousAction` reads *"one
bounded qualified veyro-lead/Opus root-cause/ADR-011 extraction-totality decision for
R2-N01/N02 before code/test remediation"* — this decision is that sanctioned action,
executed within its stated bounds.

**Explicitly not decided here, routed to their owners:**

- **R2-N03** (P2, D7.4 dedup/ordering unimplemented for the main violation lists), **R2-N04**
  (P2, stale/self-contradictory module docstring), **R2-N05** (P3, seven round-1 P3s outside
  the tracked finding projection — a **DC-08** shape needing a projection reconciliation, not
  an implementation increment), **R2-N06** (P3, R1-F14 evidence-currency inconsistency). All
  four are outside this dispatch's single question. R2 established each needs **no new
  contract**, and I concur — none requires an ADR term. R2-N05 in particular surfaces
  **R1-F19**, an explicitly unmet ADR-011 Follow-up directive (pin a root `ruff.toml`, re-run,
  record the figure under the pinned config); the 299 → 881 `E501` drift between two unpinned
  measurements is the demonstration of why it matters. Not re-adjudicated here.
- **Full residue accounting / third-party SQL parser (CAP-009 candidate).** The structurally
  strongest shape (§4.1) and the long-term target. Requires the full `CAPABILITY_POLICY.md`
  lifecycle, a registry row, and a decision on where `tools/` dependencies live. D9's
  deferral stands. The `_extract_table_refs`-class seam ADR-011 preserved is what keeps this
  a one-function replacement later, with §5's corpora as its unchanged acceptance test.
- **Real-tree domain ownership** — owner-reserved, unchanged, untouched, not a dependency.
- **CI wiring** — no `.github/workflows/` and no committed CI config exist (R2 reconfirmed
  independently), so Verdict A.4's premise stays moot. Inventing a skip path remains
  forbidden.
- **Governance records.** `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `SCENARIOS.md`,
  `BUG_REGISTRY.md`, `REVIEW_IN_FLIGHT.md`, `AUTONOMOUS_CONVERGENCE_STATE.json` and the
  evidence index were deliberately **not** edited by this session. The orchestrator should
  reference this decision and the ADR-011 addendum when next reconciling. Note for that
  reconciliation: R2-N01 is a confirmed **P0** on a Blocker-tier gate and, under **DC-08**,
  belongs in `BUG_REGISTRY.md` as a durable Bug rather than living only as narrative inside a
  review report — filing it is the orchestrator's action, not mine, and I did not file it.

---

## 9. Scenario and certification verdict — explicit

**NO SCENARIO IS PROMOTED, PASSED, OR SIGNED OFF BY THIS DECISION.**

| Scenario | Status | Position |
|---|---|---|
| SCN-MOD001-006 (own prefix / approved interface → PASS) | **NOT EXECUTED**, unpromoted | Code assurance supported per R2 §8; **not** a scenario PASS |
| SCN-MOD001-007 (another module's raw table → `CROSS_DOMAIN_SQL_IMPORT`) | **NOT EXECUTED**, unpromoted | The raw-table half's denial is **NOT RELIABLE** — R2-N01 confirmed by my own execution (§2). This is the blocking scenario |
| SCN-MOD001-095 (§6.3 pair, permitted direction → PASS) | **NOT EXECUTED**, unpromoted | Code assurance supported; **not** a scenario PASS |
| SCN-MOD001-096 (same pair, reverse → `REVERSE_EDGE_NOT_EVENT_DRIVEN`) | **NOT EXECUTED**, unpromoted | Code assurance supported; **not** a scenario PASS |

The round-2 combined independent review's verdict **BLOCKED** stands and is not altered by
this decision. **MOD-001 remains uncertified.** No Module Approval Certificate is issued,
implied, or made closer by this document. **WIP=1 holds; MOD-002 stays locked.** Under
**DC-08**, a confirmed P0 on a Blocker-tier gate independently bars certification until
closed. This is an architecture decision, not an approval of anything — **DC-14**: no
session's own reasoning is equivalent to reviewer or owner approval, and nothing here is
treated as such.

---

## 10. Model / session identity, and what this session did not do

- **Model:** `claude-opus-5[1m]` — Opus 5 (1M context), as reported by this environment.
  Correct tier for the architecture/ADR-decision role (`MODEL_ROUTING.md` row 1; DC-17's Opus
  list).
- **Role identity:** named `veyro-lead`, dispatched as a fresh bounded single-question
  adjudication. Not the gate-2 implementer; not the R1 or R2 reviewer; I did not author,
  edit, or advise on `tools/validate_architecture_gates.py`, its tests, ADR-011, the round-1
  or round-2 review, or the B HOLD.
- **Model attestation: NONE RUN BY THIS SESSION.** `mr_verify.py` was not run against this
  dispatch's own transcript — self-attestation is of little value and the tool is the
  orchestrating session's to run. Stated rather than omitted, consistent with ADR-011's own
  and the B HOLD's own posture. If an attestation is wanted for the record, the orchestrator
  should attest this transcript. R2's own Opus attestation is at
  `evidence/model-routing/GATE2-R2-OPUS-ATTESTATION-2026-10-06.md`.
- **Repository state:** `git rev-parse HEAD` = `e481b814a80923849dddfe7a49319112aae7b023`,
  **unchanged**. `git status --porcelain` = 426 entries, all pre-existing WIP, **nothing
  reset, stashed, staged, committed, pushed, or discarded**. Source and test SHA-256
  re-verified identical to the reviewed snapshot after all probing.
- **Files written by this session: exactly two** — this record, and the dated addendum
  appended to `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md` (historical
  decision text preserved byte-unchanged; appended, never rewritten). **No** source, test,
  scenario catalog, bug registry, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
  `REVIEW_IN_FLIGHT.md`, `AUTONOMOUS_CONVERGENCE_STATE.json`, evidence-index, or
  `graphify update` write.
- **Probe artifacts** live under `/tmp/g2lead/`, outside the repository, synthetic only.
- **Owner-reserved restrictions observed in full:** no paid service, no spend, no real member
  data, no deploy or production action, no material product/pricing/business/architecture/
  scope change.
- **Bounds honored:** no live CTE state-3 wiring designed or performed; no D3.2 precedence
  reorder; no code or test implemented; no review dispatched; no scenario promoted; no module
  certified. **Stopping here, as dispatched.**
