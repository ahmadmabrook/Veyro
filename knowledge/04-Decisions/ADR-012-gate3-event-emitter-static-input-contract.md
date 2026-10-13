---
doc: ADR-012
status: DECIDED (2026-10-09) — conforming to the governing baseline; no owner approval required (see "Conformance determination")
date: 2026-10-09
decided_by: veyro-lead (registered architecture/ADR-decision role, single fresh-context bounded adjudication dispatch under sole-runner operation `4da17026-3e88-4c61-8484-52998ff8cb2d`; `claude-opus-5[1m]` — Opus 5 (1M context), as reported by that environment). Not the gate-3 implementer and not the author of the root-cause record this adjudicates. No code, security, or scenario review approval is given or implied.
authored_by: the orchestrating session, transcribing the dispatched decision per `knowledge/00-System/MODEL_ROUTING.md` ("the orchestrating session may author the *text* that records a decision an Opus subagent actually made"). Two count/scope refinements made against first-hand verification are marked inline as such.
model_attestation: Independently verified by the sole orchestrator after dispatch: `mr_verify.py` PASS, 54/54 turns `claude-opus-5`, required `veyro-lead`/Opus tier; see `knowledge/03-Modules/MOD-001/evidence/model-routing/MR-MOD-001-20261009-003.json`. This attests model routing only, not implementation or review approval.
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 3 — event contract lint)
requested_by: knowledge/03-Modules/MOD-001/evidence/implementation/GATE3-R1-P1-1-DYNAMIC-CALLEE-ROOTCAUSE-2026-10-09.md §13 ("an ADR is required, and it is a new contract record rather than a bounded correction"), and GATE3-R1-P1-1-ADR-DECISION-DISPATCH-2026-10-09.md
originating_finding: gate-3 independent security/scenario review R1 §6 P1-1 (`GATE3-EVENT-CONTRACT-SECURITY-SCENARIO-REVIEW-R1-2026-10-09.md`), PARTIALLY_REMEDIATED / BLOCKED
---

# ADR-012: Gate-3 (event contract) emitter input contract — static emitter-reference recognition, per-reference escape accounting, the canonical-name requirement, and the error taxonomy

## Scope limit — read this before anything else

**This ADR binds gate 3's *static input contract only*:** which syntactic
positions count as a reference to the event emitter inside the gate's scan
scope, what the gate must do when such a reference is not inspectable, and
which outcome code and status every terminal state maps to.

**It binds no event, no event schema, and no event classification.** No
event is added, removed, re-classified, or made compatible or incompatible
by this ADR. The `EVENT_CHANGE_UNAPPROVED` half of gate 3 — TSD §24.1's
*"compatibility and classification changes require owner approval"* — is
untouched and remains owner-reserved exactly as it is.

**It does not assert where events may legally be emitted.** The scan scope
stays `backend/app/**` and is **disclosed, not asserted as exclusive**.
Nothing here says `backend/app/**` is the only legal emission surface; see
"Conformance determination" for why that distinction is what keeps this
decision inside engineering authority.

**It closes no finding.** P1-1 remains PARTIALLY_REMEDIATED / BLOCKED. See
"What this decision does not do."

## Context

### The governing text

TSD §24.1, architecture enforcement gates, verified by the deciding dispatch
first-hand against the governing docx (`Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx`,
SHA-256 matching `knowledge/00-System/PROJECT_INDEX.md`), not only against
`TSD_MIRROR.md`:

> *"Event contract lint: every event referenced by flow/code exists in
> AsyncAPI/JSON Schema registry; compatibility and classification changes
> require owner approval."*

Two properties of that sentence size this ADR. First, the obligation is on
*every event referenced by flow/code* — so a reference the gate cannot see
is an unmet obligation, not an out-of-scope case. Second, the clause's own
owner-reservation is scoped to the **event-semantics axis** (compatibility
and classification), which `EVENT_CHANGE_UNAPPROVED` already enforces. The
baseline reserves that axis to the owner and says nothing reserving the
lint's input contract.

`SCN-MOD001-019` independently requires denial for an unregistered event
reference.

### The defect

Gate-3 review R1 finding **P1-1** demonstrated that an aliased emitter
escapes the matcher and the gate reports **PASS**. A bounded remediation
landed a file-local binding resolver
(`GATE3-R1-P1-1-ALIAS-PARTIAL-VERIFICATION-2026-10-09.md`), which closed the
reviewer's literal fixture but left the reviewer's **second** closure
condition — *unresolvable or dynamic emitter-shaped calls cannot silently
pass* — unmet.

The root-cause record
(`GATE3-R1-P1-1-DYNAMIC-CALLEE-ROOTCAUSE-2026-10-09.md`) measured the
residue and identified the root cause as a **status inversion**: on one
identical escaping module, the escaping module *alone* yields
INCONCLUSIVE / `EVENT_CONTRACT_GATE_VACUOUS` / exit 2 (wrapper DENY), while
the **same** module beside one valid canonical call yields PASS / exit 0
(wrapper PASS). Adding *correct* code upgrades the verdict from denial to
PASS. Partial recognition is strictly safer than total recognition failure.

That sentence is already decided against in this project, one gate over.
`ADR-011` addendum **D6.7.2** states the invariant for gate 2 and replaces
the offending `if not idents:` guard with an accounting comparison; **D6.7.4**
adds that the recognition vocabulary *"is a floor that lowers the ERROR
rate; it is **not** the fail-closed mechanism, and no clause of this ADR may
be read as making the gate's soundness depend on it."* Gate 3's
`None if checked else …` aggregate guard **is** that `if not idents:` guard.

**Why the principle was never transposed:** each implemented architecture
gate has an ADR fixing its input contract and error taxonomy — `ADR-009`
(gate 4, permission lint), `ADR-010` (gate 1, RLS runtime envelope),
`ADR-011` (gate 2, module-deps). **Gate 3 was the only implemented gate with
no ADR at all.** P1-1 is the consequence, not a novel class. This ADR closes
that asymmetry.

## Decision

### D1 — Recognition is retained unchanged, and only widens

A node is an **emitter reference** if it is: an `ast.Name` whose `id` is in
the module's emitter-name set; an `ast.Attribute` with `attr ==
"emit_event"`; or a literal `getattr(<expr>, "emit_event")` call (2–3
positional arguments, no keywords). The emitter-name set is built exactly as
the partial remediation landed it — the canonical name, `from … import`
bindings at any level, plus assignment/walrus/annotated/parameter-default
bindings resolved to a fixed point.

`_event_emitter_names` and `_is_event_emitter_ref` are **retained as
landed**; nothing is deleted. Recognition only ever widens what is examined,
so retaining it is safe.

### D2 — Only a Load-context node is a *use*

A `Store`/`Del` target names a binding; it does not use the emitter's value.
This must be expressed as `isinstance(node.ctx, ast.Load)` — **not** as
"exclude assignment targets", which would reopen the class-body rename case.

**D2a — this covers `ast.Attribute`, not only `ast.Name`.** An
`ast.Attribute` with `attr == "emit_event"` in `Store` or `Del` context is a
binding target, not a use: `self.emit_event = x` and `del obj.emit_event`
would otherwise ERROR for no reason, and `self.emit_event = emit_event`
would double-report. This narrowing satisfies the admission test in D7
unconditionally — a binding target is never evaluated as a value, by Python
semantics — and loses nothing, because every real escape through such an
assignment is already caught at its right-hand side.

*(D2a is a correction to the root-cause record's §5, which scoped this rule
to `ast.Name` only.)*

### D3 — Per-reference accounting (the fail-closed core)

Every recognized emitter use must be the **direct callee** of a call — the
test is `parent is an ast.Call and parent.func is node`.

- **If it is:** the existing argument check applies unchanged — exactly one
  positional string-literal argument, no keywords, value present in the
  registry; otherwise **FAIL `UNREGISTERED_EVENT_CONTRACT`**, naming the
  event id or `"non-literal event id"`.
- **If it is not:** **ERROR `EVENT_EMITTER_UNINSPECTABLE`**, naming
  `file:line` and the syntactic position.

**D3a — an `ast.NamedExpr` is never itself a reference; the reference is the
node inside it.** Candidate references are `Name` (Load), `Attribute` (Load),
and literal-`getattr` `Call` nodes only, and there is **no unwrapping at the
callee position**. Read without this rule, D3 yields *two* findings for
`(publish := emit_event)("veyro.missing")` — the `NamedExpr` is a direct
callee (FAIL on the id) and the inner `Name` is not (ERROR escape).
`NamedExpr` unwrapping is retained **only** inside `_is_event_emitter_ref`
for binding right-hand-side resolution, where it belongs.

Measured consequence: `(publish := emit_event)("veyro.created")` moves
**PASS → ERROR**. This is correct on D4's own logic — the walrus creates a
module-scope non-canonical binding as re-exportable as `publish =
emit_event` — and it is what makes the allowed-shape table below literally
exhaustive, which it otherwise is not.

*(D3a is a correction to the root-cause record's §5, which left `NamedExpr`
under-specified at the callee position and did not disclose this reversal.)*

### D4 — Canonical name only; renaming is itself an escape

D3 already denies every *value*-level renaming, because a renamed binding's
right-hand side is a use that is not a callee. One shape has no Load-context
use to catch and therefore needs stating explicitly:

> `from <mod> import emit_event as <alias>` where `alias != "emit_event"` is
> itself **ERROR `EVENT_EMITTER_UNINSPECTABLE`**.

A plain `from <mod> import emit_event` (no rename, any level) is allowed.

**This rule is load-bearing, not tidiness.** It closes an in-tree cross-file
re-export fail-open of the same class as P1-1. Measured on the live
validator, beside one valid canonical call:

```python
# a.py
from veyro.bus import emit_event as publish
# b.py — inside the scan scope, contains nothing recognizable
from a import publish
publish("veyro.missing")
```

→ `status=PASS`, `violations=[]`, exit 0. A ban on *assignment*-aliasing
alone does **not** close this (also measured ALLOW): `a.py` has no
Load-context use to catch and `b.py` has nothing to recognize. The only
alternatives that close it are a cross-module import model plus
`ast.Attribute` widening to resolved emitter names — rejected below as a
global false-positive class over every `.send()`/`.publish()` in the backend
— or this rule, which closes it **module-locally with no cross-module model
at all**: `a.py` is ERROR at its own import line, and `b.py` needs no rule.

**Narrowing is the critical path here, not widening.** Recognizing more
indirection is an open-ended vocabulary chase, which is exactly what D6.7.4
forbids as a soundness basis. D4 keys on the emitter's own name, which this
contract fixes.

### D5 — Tier-2 string recognition

An `ast.Constant` whose value is exactly the string `"emit_event"`, and
which is not the recognized literal attribute argument of a D1 `getattr`
emitter reference, is **ERROR `DYNAMIC_EVENT_EMITTER_REFERENCE`**.

This closes string-keyed reflective lookup (`globals()["emit_event"]`),
`getattr(bus, NAME)` with `NAME = "emit_event"`, and
`operator.attrgetter("emit_event")`. It is consistent rather than novel: the
existing literal-`getattr` rule already treats that same string as
identifying the emitter.

**D5 is exact-match only and must be described that way.** It does not close
reflective access generally — `globals()["emit" + "_event"]` defeats it. See
"Residual limits".

### D6 — Status polarity: an escape is ERROR, not FAIL

**Both D3's escape and D5's dynamic reference are ERROR (exit 2), not FAIL
(exit 1).** `ADR-011`'s own Alternatives table decided this one gate over:
*"Treat an unaccounted position as FAIL rather than ERROR → Rejected — the
gate cannot name an owner it does not know."* Transposed: the gate cannot
name the **event id**. An escape is a statement about inspectability, not a
proven unregistered emission, so `UNREGISTERED_EVENT_CONTRACT` would assert
a fact the gate does not have. `.claude/rules/infra/observability.md`
control 1's named-violation-type requirement is satisfied by a code that
says only what is actually known.

ERROR **dominates any concurrent FAIL** in the same run. Both statuses fail
CI and both DENY through the wrapper, which is what §24.1 requires; ERROR
additionally keeps the report's partition honest.

Verified status/exit mapping (`tools/validate_architecture_gates.py:335`):
`EXIT_CODES = {PASS: 0, FAIL: 1, INCONCLUSIVE: 2, ERROR: 2}`.

**Implementation consequence, verified:** `_finish` (lines 385-395) yields
FAIL if `violations`, else INCONCLUSIVE if `vacuous`, else PASS — it
**cannot express ERROR**. The escape path must therefore construct and
return a `GateReport` directly, per the gate-2 precedent in the same file at
lines 8163-8167, which returns `GateReport("module-deps", ERROR, violations
+ error_class, sorted(checked), notes + […])` — a mixed outcome that reports
both partitions and preserves `checked`. **Raising `GateInputError` would be
wrong:** that handler returns a report with no `checked` and no `notes`,
discarding every inspected subject and every concurrent violation, and would
mislabel a code defect as a gate-input defect.

### D7 — No exemptions in v1

Per D6.7.7's *"no skip, exempt, allowlist, or suppression path of any
kind"* and D6.7.1's rule that narrowing is never free and requires its own
recorded decision.

**The one proposed exemption is REFUSED for v1.** The root-cause record
proposed admitting string constants that are elements of an `__all__`
assignment, under the admission test *"the position provably cannot yield a
callable reference to the emitter."*

**The admission test is adopted and pre-recorded**; the exemption is not.
`__all__` is a **consumed value**: star-import machinery and the
`getattr(mod, n) for n in mod.__all__` re-export idiom both read it. The
exemption is sound only on the narrower claim that such consumption
preserves the canonical name — true for the literal form, but that makes it
a *vocabulary-keyed* narrowing (`__all__` is itself just a name, and
`__all__ = BASE + ["emit_event"]` defeats the literal form), which is the
error D6.7.4 names. Measured: `backend/app/**` contains zero `__all__`
occurrences, so refusing costs nothing today. Admit only by ADR amendment on
a real occurrence, with the narrowing justified to D6.8.5's
constructive-losslessness standard.

**No test-path exemption.** Test modules live inside the scan scope
(`backend/app/modules/*/tests/`). A test path free to reference the emitter
is itself an emission surface. `mock.patch.object(bus, "emit_event")` is
ERROR under D5; the dotted `mock.patch("veyro.bus.emit_event")` stays clean
and is the spelling convention to use — **but it must not be presented as
the *safe* form.** Both install a replacement emitter; the dotted form is
clean only because it is outside D5's exact-match reach (residual 2), which
is a reach limit, not a security property. Measured: `backend/app/**`
contains zero `mock`/`patch` occurrences.

### D8 — The aggregate vacuity guard is retained, and is not the mechanism

`None if checked else "no emit_event references inspected"` **stays**: the
trusted workflow's `NOT_APPLICABLE` path requires
`EVENT_CONTRACT_GATE_VACUOUS`, and today's real tree legitimately returns
INCONCLUSIVE / vacuous / exit 2.

But the ADR, the gate comment, and any evidence citing it must label it a
**non-vacuity disclosure, explicitly not the fail-closed mechanism** —
D6.7.4's exact framing. An escapes-only tree yields `checked=[]` *and* ERROR
status; since the wrapper's `vacuous` tuple requires `gate_status ==
'INCONCLUSIVE'`, it cannot be mistaken for the `NOT_APPLICABLE` path.

### D9 — Forward runtime obligation, booked not implemented

The complete guarantee is runtime, not static. Booked as binding on
whichever module implements the emitter:

> `emit_event` must not emit an event id absent from the registry. The id
> must be validated against the registry, and a miss must produce a named,
> logged refusal — **never a silent drop-and-continue.**

This is the only control covering residuals 1 and 2, and it holds
regardless of how the callee was obtained. There is nothing to add it to
today — `backend/app/**` contains zero emitter references — which is exactly
why booking it now is cheap.

**Deliberately left open: raise-versus-refuse-and-alert.** That is a runtime
availability/failure-mode decision belonging to the emitter module's own
design, and in a member-facing path it edges toward owner-reserved
territory. This ADR fixes the invariant, not the failure mode. If the
implementing module finds this clause conflicts with a baseline
requirement, it reports a finding against this ADR rather than dropping the
clause, on ADR-011's own Follow-up amendment path.

## Accepted shapes

**Allowed — exhaustive.** Any other contact with the emitter inside the scan
scope is rejected.

| Allowed shape | Condition |
|---|---|
| `emit_event("<id>")` | one positional string literal, no keywords, `<id>` present in the registry |
| `<expr>.emit_event("<id>")` | same |
| `getattr(<expr>, "emit_event")("<id>")` | literal attribute argument (2–3 positional args, no keywords); same |
| `from <mod> import emit_event` | no rename, any import level; combined with any of the above |

**Rejected.**

| Shape | Code | Status / exit |
|---|---|---|
| A recognized emitter use that is not the direct callee of a call — Call argument, keyword argument, Dict/Tuple/List element, Assign/AnnAssign RHS, class-body or instance-attribute assignment, IfExp, Return, or any other non-callee position | `EVENT_EMITTER_UNINSPECTABLE` | ERROR / 2 |
| `from <mod> import emit_event as <alias>`, `<alias> != "emit_event"` (D4) | `EVENT_EMITTER_UNINSPECTABLE` | ERROR / 2 |
| `(<alias> := emit_event)(…)` — walrus binding to a non-canonical name, even in callee position (D3a) | `EVENT_EMITTER_UNINSPECTABLE` | ERROR / 2 |
| `ast.Constant` exactly `"emit_event"` that is not the literal attribute argument of a recognized D1 `getattr` reference (D5) | `DYNAMIC_EVENT_EMITTER_REFERENCE` | ERROR / 2 |
| Direct-callee emitter call whose argument is not exactly one positional string literal | `UNREGISTERED_EVENT_CONTRACT` (`"non-literal event id"`) | FAIL / 1 — **already correct, must not regress** |
| Direct-callee emitter call with a literal id absent from the registry | `UNREGISTERED_EVENT_CONTRACT` (naming the id) | FAIL / 1 — **already correct, must not regress** |
| Registered event's schema/classification diff with no resolving `OWN-NNN` | `EVENT_CHANGE_UNAPPROVED` | FAIL / 1 — **unchanged by this ADR** |

One source line may legitimately produce **both** an escape and a
resolved-callee finding. Tests must therefore assert status, code and
subject **membership**, never whole-list equality.

**Why this removes no real capability.** Measured on the live validator: an
in-tree pass-through wrapper emitting a **registered** event
(`def publish(e): emit_event(e)`) is **already** FAIL / exit 1 today, because
the inner call's argument is not a literal. The set of legal,
registry-conforming emissions is therefore identical before and after this
contract. D4 does not remove a capability the gate ever permitted; it
converts a class of shapes from *silently tolerated* to *denied*.

## Residual limits

The gate's claim is bounded to **statically recognizable emitter references
within `backend/app/**`**. The following are **outside this gate's static
reach and are not claimed.** They are *not* fail-closed, and neither the
gate comment nor any evidence artifact may say they are:

1. **An emitter wrapped in a module outside the scan scope** — `from
   veyro.helpers import publish; publish("veyro.missing")`. The scanned
   module contains no reference to recognize. Measured PASS on the current
   validator and on the root-cause record's prototype alike. Disclosed; the
   scope is **not** widened and `backend/app/**` is **not** asserted
   exclusive.
2. **A dynamically constructed symbol name** — string arithmetic
   (`globals()["emit" + "_event"]`), computed `getattr`, `importlib`,
   computed `attrgetter`. D5 is exact-match only. The dotted
   `mock.patch("veyro.bus.emit_event")` convention lives here: outside D5's
   reach, **not** safer.
3. **The emitter reaching the scanned tree through an object the gate never
   sees** — e.g. a container populated outside the scope.
4. **Binding collection is file-wide rather than lexically scoped** — an
   over-approximation toward a violation, i.e. the fail-closed direction.
   Retained, and kept disclosed.

**The invariant to implement and test against**, transposed from D6.7.2 and
to be stated positively in the gate comment so the next reader can test
against it rather than re-derive it:

> For any event source module M, the gate's outcome must be no weaker — on
> the ordering `clean < FAIL < ERROR` — than the outcome it would produce
> for M if the recognizer had recognized nothing. **Partial recognition may
> never be safer than total recognition failure.**

The absence of that sentence is what allowed P1-1. The only complete control
is runtime (D9), booked forward, not claimed now.

## Disclosed contract reversal — this implementation is not purely additive

**This must not be absorbed quietly in a test edit.** The contract reverses
expectations in a landed regression test that the **now-consumed** gate-3
review inspected:

- **One landed positive-case assertion inverts PASS → ERROR**
  (`test_validate_architecture_gates.py:470-473`): an aliased emitter
  emitting a *registered* event is asserted to PASS and to appear in
  `checked`. D4 makes it ERROR.
- **Eight of the nine landed denial assertions invert FAIL / exit 1 → ERROR
  / exit 2** — the eight-entry `denied` dict (lines 476-504) plus the
  separate non-literal-id case (lines 508-511). Only *"getattr with a
  literal attribute"* stays FAIL, because it is the one case whose emitter
  reference is a direct callee.
- **Separately, a measured live behavior inverts:**
  `(publish := emit_event)("veyro.created")` currently returns PASS / exit 0
  and becomes ERROR under D3a. *(Refinement on first-hand verification: this
  shape is a measured live behavior, not a landed positive-case assertion —
  the landed test exercises the walrus only as a denial case. The deciding
  dispatch characterized it as a second inverting positive case; the
  accurate count of landed positive assertions that invert is **one**.)*
- The three "must not manufacture emitters out of unrelated code" negative
  cases (lines 513-525) do **not** invert and must stay PASS.

**Why reversing a reviewed expectation is nonetheless within engineering
authority.** Relative to the live gate, every clause of this contract adds
denial surface and removes none: there is no input the current validator
denies and this contract clears. Every reversal therefore moves strictly
*toward* denial on `clean < FAIL < ERROR` — `PASS → ERROR` and `FAIL →
ERROR` — which is the same ordering D6.7.2 and D6.8.4 use to separate a safe
change from an unsafe one. A reviewed expectation reversed *upward* is not
an erosion of the review's protection; it is the review's own finding
carried further than the partial remediation carried it. (`ADR-011`'s D6.8,
the one clause that *removed* refusal surface, had to supply a constructive
losslessness argument — that argument is not needed here and is not
claimed.)

**No review entitlement arises from this reversal.** The owner's single
gate-3 review entitlement is **consumed**, and nothing in this ADR requests,
authorizes, or implies another. A second independent review exists to catch
the *weakening* of a reviewed guarantee; there is no weakening here, by the
monotonicity above, and the reversal originates in the reviewer's own second
closure condition — *"make an unresolvable or dynamic emitter-shaped call a
violation rather than an omission"* — which the partial remediation did not
meet. It moves toward the finding, not away from it.

**The honest caveat, stated plainly so the owner can read it differently.**
D4 *does* constrain how future module code may reference the bus: no
aliasing or indirection of the emitter inside the scanned tree. The
assessment is that this is non-material, for the measured reason above — it
forbids only shapes the gate already refuses to let emit a literal id, there
are zero present occurrences, and it is reversible by ADR amendment. But it
is a constraint, and it is recorded here rather than buried.

## Alternatives rejected

| Alternative | Consequence | Verdict |
|---|---|---|
| A reflective-construct denylist (`globals`/`locals`/`vars`/`__dict__`/`eval`/`attrgetter`/…) | Name-keyed, open-ended, itself aliasable; adopting it recreates precisely the error D6.7.4 names — making the gate's soundness depend on a vocabulary | **Rejected.** D5 keys on the emitter's own name, fixed by this contract |
| Widen `ast.Attribute` matching to the module's resolved emitter-name set (to catch the class-body rename directly) | Flags every unrelated attribute call on a common verb (`.send()`, `.publish()`) in any module that aliases — a real false-positive class with no fail-closed benefit, since D3 already denies that case at its assignment line | **Rejected** |
| Exempt function-local bindings (permit a local alias, deny module-scope ones) | It is an exemption, which D6.7.7 refuses; it adds scope analysis; and it buys nothing — a module-level import alias remains inherently re-exportable, so the positive alias case inverts either way | **Rejected** |
| Close the cross-file re-export hole by recognizing more indirection (cross-module import model + Attribute widening) | Requires a cross-module import graph plus the rejected Attribute widening — a global false-positive class, for a boundary that still exists | **Rejected.** D4 closes it module-locally for free |
| Widen the scan scope to `backend/**` or `tools/**` | Measured false positive immediately, on the validator's own `CANONICAL_EVENT_EMITTER = "emit_event"` line (`tools/validate_architecture_gates.py:1453`): real present cost, partial benefit, boundary still present — and it can never include site-packages | **Rejected** |
| Assert `backend/app/**` as the only legal event-emission surface | A standing architecture constraint on every future module — engages `.claude/rules/global/owner-reserved-restrictions.md` item 4 | **Rejected as outside engineering authority.** Disclose, do not assert |
| Treat the escape as FAIL rather than ERROR | The gate cannot name the event id; `UNREGISTERED_EVENT_CONTRACT` would assert a fact it does not have | **Rejected** (D6) |
| Fold the new outcomes into the existing vocabulary | The outcomes differ in both status and exit code, and the existing code asserts a fact the escape case cannot assert | **Rejected.** Precedent: gate 1's round-12 additions; gate 2's `MODULE_DEPS_SOURCE_UNINSPECTABLE` |
| A generic dataflow or taint framework | `ADR-011`'s Alternatives table already rejected the analogous "full residue accounting" as out of scope, and the argument is stronger here — the escape rule needs no dataflow at all, since the escape itself is the enforceable event | **Rejected** |
| Disclose the escape as a residual and proceed | A residual disclosure can honestly describe a false-*fail*; it cannot discharge a false-*clean*. The current state is a green required check over an unregistered emission | **Rejected** |

## Conformance determination

Conforms to Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1. This ADR
changes:

- **no TSD scope** — it implements §24.1's own gate-3 obligation (*"every
  event referenced by flow/code exists in … registry"*), read first-hand
  from the governing docx by the deciding dispatch, and leaves §24.1's own
  owner-reserved axis (compatibility and classification changes) entirely
  untouched;
- **no event, schema, or classification** — no event is added, removed, or
  re-classified; `EVENT_CHANGE_UNAPPROVED` is unchanged;
- **no architecture** — the event bus's existence, interface, ownership,
  module boundaries, domain model, and event set are all untouched. What is
  constrained is the *spelling of call sites inside one lint's scan scope*;
- **no product, pricing, or business decision** — a CI lint's input contract
  is none of these;
- **no module scope** — `GOV-01-R04` already requires this gate;
- **no routing** — `ADR-005` is unchanged; implementation routes per the
  existing mapping, so DC-17's routing-change sub-clause is not triggered;
- **no capability** — stdlib `ast` only; no third-party parser is adopted;
- **no CI/IaC surface** — no `.github/**` change is required (see the
  implementation boundary), which also keeps this clear of
  `.claude/rules/infra/iac.md` control 5.

**The load-bearing materiality argument is measured, not asserted.** An
in-tree pass-through wrapper emitting a *registered* event is already FAIL /
exit 1 on the live validator, because the inner call's argument is not a
literal. The set of legal, registry-conforming emissions is therefore
identical before and after this contract. No legal capability is removed;
an already-illegal shape is made loud. That is the gate performing its
§24.1 obligation, not an architecture change. The secondary reasons — zero
present occurrences in `backend/app/**`, and reversibility by ADR amendment
— are true but would not save the decision on their own, and are not relied
on as the primary ground.

**Settled practice, verified first-hand rather than inferred.** `ADR-009`
(gate 4), `ADR-010` (gate 1) and `ADR-011` (gate 2) are each
`status: DECIDED … no owner approval required`, and `OWNER_APPROVALS.md`
carries **OWN-001, 002, 003, 005, 006, 007** — baseline interpretation, the
EIP self-contradiction adjudication, the orchestration operating model, the
review stopping rule, a capability retirement, and the bounded SCN-020 live
scope. **None of the three gate ADRs has a row.** By settled practice a
gate's input contract is a recorded engineering decision.

The sharpest precedent is one the root-cause record does not cite:
**`ADR-009` mandates `x-veyro-permission` and `x-veyro-authentication` on
every future API endpoint and refuses a public-endpoint exemption** — a
strictly *larger* standing constraint on how all future module code must be
written than D4 is, decided at engineering authority with no owner row. And
**`ADR-011` D6.8 is a pure narrowing** — it removes refusal surface —
decided by `veyro-lead` under D6.7.1's own "narrowing requires its own
recorded decision" clause, again with no owner row. Between them, the
project has already settled both halves of the question D4 raises.

This ADR incurs **no spend**, uses **no real member data**, touches **no
production**, and asserts **no material architecture change**. **No owner
approval is required.**

**Two things would change that answer, and are therefore not done here.**
First, asserting that `backend/app/**` is the only legal event-emission
surface would be a standing architecture constraint on every future module,
engaging `owner-reserved-restrictions.md` item 4. This ADR therefore
*discloses* the scope limit rather than asserting exclusivity — and that
choice is what keeps the correction inside engineering authority, leaving
nothing to ask the owner for. Second, **widening the scan scope** is refused
on measured grounds. **If a future session decides either way differently,
it must stop and report `BLOCKED: OWNER_APPROVAL_REQUIRED` naming item 4,
not proceed.**

### An ADR is a prerequisite to implementation, not contemporaneous documentation

**DC-09** requires an ADR *"recorded **before** implementation."* Two
project-internal rules make it a hard precondition here independently of
whether this reaches DC-09's materiality threshold:

1. **ADR-011 D6.7.1, by transposition:** narrowing is never free and
   *"requires its own recorded decision."* D2, D2a, D3a and the refused
   `__all__` exemption are each such a decision. There is no path by which
   an implementer may make them.
2. **The polarity and taxonomy decisions are not implementation choices.**
   ERROR-vs-FAIL determines the CI exit code and therefore what the trusted
   wrapper does; two new violation codes change `IMPLEMENTATION.md` §4 row
   3, a planning artifact. An implementer who picked these would be
   self-authorizing.

Gate 3 was additionally the only implemented architecture gate with no ADR
(009 = gate 4, 010 = gate 1, 011 = gate 2; verified by directory listing —
eleven ADRs existed, none for gate 3). Landing this without an ADR would
leave the one gate whose soundness was just found defective as the one gate
with no recorded contract.

## Implementation boundary — exact and finite

Ordered, under the sole lease, by the **implementation tier** — not by any
review role, and not by the design worker who produced the root-cause
record. **This ADR authorizes no implementation by itself**; steps 2-7 are a
separate, later, bounded operation.

**Files that may change — exactly four, and no others:**

1. `tools/validate_architecture_gates.py` — `run_event_contract_gate`, the
   `_is_event_emitter_ref` call sites, the gate-3 header comment (lines
   1383-1405), and the `_emitter_binding_candidates` docstring sentence
   (line 1492).
2. `tools/tests/test_validate_architecture_gates.py` — the existing
   `test_event_contract_aliased_emitter_cannot_yield_a_green_pass` (lines
   443-525) plus two new functions.
3. `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §4 row 3.
4. This ADR (authored first).

**Steps:**

1. **Author this ADR and have it accepted — prerequisite to step 2.**
   *(Done: this file.)*
2. Implement D2/D2a, D3/D3a, D4, D5 in `run_event_contract_gate`, returning
   `GateReport(…, ERROR, violations + error_class, sorted(checked), notes)`
   directly on the escape path per the 8163-8167 precedent. Retain
   `_event_emitter_names` and `_is_event_emitter_ref` as landed. Retain the
   vacuity guard, relabeled per D8.
3. Replace the gate comment at 1383-1405 and correct the
   `_emitter_binding_candidates` docstring at line 1492. That docstring —
   **not a comment, as the root-cause record describes it** — currently
   claims *"an attribute target such as `self.emit_event = emit_event` needs
   no resolution, since the resulting `self.emit_event(...)` call matches on
   the attribute name."* That holds only when the attribute name is
   preserved; `self.send = emit_event` preserves nothing and passes today.
   State the "Residual limits" invariant positively, and list the four
   residuals in **"outside this gate's static reach and is not claimed"**
   terms — never "fails closed."
4. Update the existing test's expectations per "Disclosed contract
   reversal", replacing whole-list equality with membership assertions, and
   add `test_event_contract_escaped_emitter_cannot_yield_a_green_pass` and
   `test_event_contract_ordinary_indirection_is_not_an_emitter`. Every case
   keeps one legitimate canonical call present, so no verdict can come from
   an empty scan. The second test pins the non-interference set — identity
   wrapper, dict-of-callables dispatch, `globals()[key]`, non-literal
   `getattr(obj, attr)`, decorator, and a local function sharing an alias
   name — each leaving `checked` at exactly the one legitimate call.
5. **Record these mutation checks as killed.** A surviving mutant is a
   blocker for the dispatch, not a note: drop D2's `ast.Load` test
   (legitimate aliases self-report as their own escapes); drop D2a's
   Attribute-context test; drop D3a's `NamedExpr` rule (double-counting
   returns); drop D4 (the cross-file import-alias re-export reopens); drop
   D5 (string-keyed reflective lookup reopens); downgrade the escape from
   ERROR to FAIL (polarity lost); restore `_finish`'s aggregate vacuity
   guard as the only accounting (the status inversion returns).
6. Update `IMPLEMENTATION.md` §4 row 3 — whose "expected fail-closed output"
   cell currently names exactly `UNREGISTERED_EVENT_CONTRACT` or
   `EVENT_CHANGE_UNAPPROVED` — to add the two new codes with their
   ERROR/exit-2 status, plus a deliberate-violation fixture for an aliased
   or escaped emitter. Do not touch rows 1, 2, 4, 5, 6. Record the dotted
   `mock.patch("veyro.bus.emit_event")` test convention **with its "outside
   D5's reach, not safer" caveat**.
7. Re-run the focused file, scoped Ruff, compile, and the 4/4 baseline
   check. Record results. **Claim no scenario PASS.**

**No `.github/**` change is required — verified.**
`.github/workflows/scn020-trusted-event-contract.yml` lines 247-267 admit
exactly two paths: `status == 0 and gate_status == 'PASS' and bootstrap !=
'true'`, or the `empty and vacuous` tuple (`status == 2`, `gate_status ==
'INCONCLUSIVE'`, `codes == ['EVENT_CONTRACT_GATE_VACUOUS']`). Everything else
reaches an unconditional `SystemExit('… DENY …')`. An ERROR report carrying
either new code therefore **denies through the existing wrapper with no
workflow edit**, and the `NOT_APPLICABLE` allowance is unaffected because any
escape makes `vacuous` false.

**Explicitly out of scope, and to stay out:** widening the scan scope;
asserting `backend/app/**` as the exclusive emission surface; a
reflective-API denylist; `ast.Attribute` widening to resolved emitter names;
lexical scoping of bindings; any cross-module import graph; any generic
dataflow or taint framework; any `.github/**` edit; gate 2's U1/U2 **B
HOLD**; the P3 items; and **P1-2 and P2-1..P2-4, which are separate
corrections**. Also out of scope: committing the two untracked validator
files (see Disclosures) — a separate governance step, not this
implementation's business.

## What this decision does not do

- **Closes no finding.** P1-1 remains **PARTIALLY_REMEDIATED / BLOCKED**;
  the false PASS reproduces on the live validator exactly as before.
  **P1-2 and P2-1..P2-4 are untouched and remain independent blockers.**
- **Grants no review entitlement.** The owner's single gate-3 review
  entitlement is **consumed**. Nothing here requests, authorizes, or implies
  another, and no review counter advances.
- **Gives no code, security, or scenario review approval**, and performs no
  review role.
- **Yields no scenario credit** — SCN-MOD001-008/019/020/130 remain
  unpromoted — **no GOV-01-R04 certificate**, and **no MOD-001 exit
  credit**. MOD-001 exit remains **0/8**; gate-2 F01-F14 remain 14/14
  closed; gate-3 assurance remains **BLOCKED**; **WIP=1 holds; MOD-002 stays
  locked.**
- **Authorizes no implementation by itself.** Steps 2-7 above are a
  separate, later, bounded operation.
- Incurs no spend, uses no real member data, takes no production action, and
  performs no remote mutation.

## Disclosures

**Verified first-hand by the deciding dispatch:** TSD §24.1's
event-contract-lint clause, extracted from the governing docx in `/tmp`
(hash matching `PROJECT_INDEX.md`) — not only from `TSD_MIRROR.md`.
`OWNER_APPROVALS.md`'s complete row set and the absence of any
ADR-009/010/011 row. The live gate at 1383-1595; `_finish` at 385-395;
`EXIT_CODES` at 335; the gate-2 ERROR precedent at 8163-8167; line 1492's
overstatement. The landed test at 443-525. The wrapper's accept/deny tuples
at 247-267. `IMPLEMENTATION.md` §4 row 3's exact denial vocabulary. The
zero-occurrence measurements in `backend/app/**` (23 `.py` files; zero each
of `emit_event`, `getattr(`, `__all__`, `mock`, `patch`, `globals(`,
`locals(`, `vars(`). Four live-validator measurements: the identity-wrapper,
assignment-alias re-export and import-alias re-export cases all
`PASS / exit 0`; the in-tree wrapper with a *registered* event already
`FAIL / exit 1`; the walrus-as-callee and import-alias positive cases both
currently `PASS / exit 0`.

**Independently re-verified by the authoring session before transcription:**
`EXIT_CODES` at line 335; `_finish`'s inability to express ERROR (385-395);
the gate-2 `GateReport(… ERROR …)` precedent (8163-8167); the line-1492
docstring overstatement; `OWNER_APPROVALS.md`'s six rows and the absence of
any gate-ADR row; and the landed test's structure — the positive assertion
at 470-473, the eight-entry `denied` dict with its `status == FAIL` and
exact-list-equality assertions (476-504), the separate non-literal-id case
(508-511), and the three non-interference PASS cases (513-525).

**Not verified first-hand by either session:** the root-cause record's §10
21-fixture prototype corpus and its 0-rejections-across-70-files sweep (the
prototype was not rebuilt); the `tools/validate_architecture_gates.py:1453`
prototype rejection (the line and its content were confirmed; the
prototype's rejection of it was not re-run); and the remaining escape shapes
(b)-(i), (o) of the root-cause record's §2 — three of seven were measured
and the mechanism in `_event_emitter_names`/`_is_event_emitter_ref` makes the
rest follow, but they are **inferred, not measured**.

**Corrections this ADR makes to the root-cause record**, each recorded
because the implementation boundary depends on it: §5's D2 analogue is
under-scoped to `ast.Name` (corrected by D2a); §5 leaves `ast.NamedExpr`
under-specified at the callee position and yields double findings as written,
and the walrus-as-callee reversal is a real behavior change §13 does not
disclose (corrected by D3a); §13 under-counts the test reversal — the
`denied`-loop status assertion inverts for eight of nine denial cases, not
only the list equality and one positive case; §8's `__all__` admission-test
framing is imprecise and the exemption is refused on a different ground
(D7); §8's dotted-`mock.patch` convention must not be framed as safer (D7);
§12's runtime obligation should not fix "raising on miss" (D9); and §13's
materiality argument is correct but led with the weaker reasons — the
already-FAIL in-tree-wrapper measurement is the load-bearing one.

**Correction this ADR makes to the deciding dispatch**, on first-hand
verification: the dispatch reported that *two* landed positive-case
expectations invert. The landed test contains **one** positive assertion
(lines 470-473); the walrus-with-a-registered-event PASS is a measured live
behavior, not a landed assertion. The reversal section states the accurate
count.

**Observed, not acted on.** `git status --porcelain` reports both
`tools/validate_architecture_gates.py` and
`tools/tests/test_validate_architecture_gates.py` as **untracked (`??`)**,
confirmed independently by both sessions. The SHA-256 values cited in
`GATE3-R1-P1-1-ALIAS-PARTIAL-VERIFICATION-2026-10-09.md` bullet 5 therefore
pin **uncommitted** files, and this ADR's own line anchors cite files with no
commit. **Worth resolving before any certification step relies on those
hashes.** Outside this operation's charge; nothing was changed.

**Files changed by this operation:** this ADR only. No validator, test,
workflow, planning, or other evidence file was created, edited, or deleted.
All reproduction by the deciding dispatch ran in throwaway `/tmp` trees
against the live validator, loaded with `PYTHONDONTWRITEBYTECODE=1` so no
bytecode cache was written to `tools/`. Nothing committed or pushed. No
`REVIEW_IN_FLIGHT.md` claim was written, since no review was dispatched.

**Model routing.** The architecture judgment was routed to exactly one
fresh-context `veyro-lead` Opus subagent per `ADR-005` and
`MODEL_ROUTING.md`; no other agent was dispatched. The orchestrating session
authored this text, which records that dispatch's decision, per
`MODEL_ROUTING.md`'s orchestrating-session clause and `OWN-003`.

## Follow-up

**For the gate-3 implementation tier:** implement D2-D5 and D8 literally,
in the order and within the file set fixed above. Do not narrow any clause;
D6.7.1 applies by transposition — narrowing is never free and requires its
own recorded decision, which means an amendment to this ADR, not an
implementer's judgment call.

**For whichever module implements the emitter:** D9 is binding on you. If it
conflicts with a baseline requirement, report a finding against this ADR
rather than dropping the clause.

**Not delegated and not authorized by this ADR:** any second independent
gate-3 review; any scenario promotion; any scope widening; any exclusivity
assertion about `backend/app/**`.
