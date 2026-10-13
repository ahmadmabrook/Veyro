# Gate-3 R1 P1-1 — dynamic-callee root cause and minimum enforceable emitter contract

**Date:** 2026-10-09 · **Record type:** design-only root-cause/design analysis ·
**Status of the finding:** P1-1 remains **PARTIALLY_REMEDIATED / BLOCKED**.

## 0. Scope, authority, and what this record is not

Design-only worker under the existing sole Veyro runner lease. One fresh-context
`veyro-lead` Opus subagent was dispatched for architecture judgment (the single
authorized dispatch); no further agents. No product code, test, workflow, or other
evidence file was created, edited, or deleted. No review role was performed, no
independent review was dispatched or implied, no remote mutation, no scenario
promotion.

This record **does not** claim PASS for anything. It does not close P1-1, does not
close SCN-008/019/020/130, does not produce a GOV-01-R04 certificate, and yields no
MOD-001 exit credit. MOD-001 exit remains 0/8; gate-2 F01–F14 remain 14/14 closed;
WIP=1 holds; MOD-002 stays locked. The owner's single gate-3 review entitlement is
**consumed** — nothing here requests, authorizes, or implies a second review.
P1-2 and P2-1..P2-4 are untouched and remain blockers independently of this analysis.

All measurement in §2, §6, §7 and §10 ran against the live validator in throwaway
`/tmp` trees. The repository working tree was not modified. One incidental side
effect is disclosed in §15.

Inputs read: gate-3 R1 review §6 P1-1 (`GATE3-EVENT-CONTRACT-SECURITY-SCENARIO-REVIEW-R1-2026-10-09.md`
lines 341-373); the partial-verification record
(`GATE3-R1-P1-1-ALIAS-PARTIAL-VERIFICATION-2026-10-09.md`, bullet 7 naming the
unclosed dependency); the current validator (`tools/validate_architecture_gates.py`
lines 1383-1595); the landed regression test
(`tools/tests/test_validate_architecture_gates.py` lines 443-525); TSD §24.1's
gate-3 obligation as carried in `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §4
row 3; `SCN-MOD001-019`; `ADR-009`/`ADR-010`/`ADR-011`; and
`.github/workflows/scn020-trusted-event-contract.yml` lines 247-267.

## 1. Classification

`MANDATORY_NOW`, unchanged from the partial-verification record. TSD §24.1 requires
every code-referenced event to exist in the registry; `SCN-MOD001-019` requires
denial for an unregistered reference. The exact shape below makes the required
status check report green while an unregistered event is emitted. This is a
certification blocker and cannot be deferred.

## 2. The exact false PASS, measured

The reviewer's unclosed dependency, replayed verbatim against the current validator.
Source placed in the scanned tree beside one valid canonical emitter call, with
`veyro.created` registered and `veyro.missing` absent:

```python
# case.py
from veyro.bus import emit_event
def identity(f): return f
publish = identity(emit_event)
publish("veyro.missing")

# flow.py
from veyro.bus import emit_event
emit_event("veyro.created")
```

Result: `status=PASS`, `violations=[]`, `checked=["…/flow.py:2"]`, **exit 0**.

Mechanism, line by line. `_event_emitter_names` (1519-1544) seeds `{emit_event}` from
the `ImportFrom`, then resolves assignment-style bindings to a fixed point — but only
where the bound *value* is itself an expression that statically denotes the emitter
(`_is_event_emitter_ref`, 1456-1483). The value here is `ast.Call(func=Name('identity'))`,
which is neither a `Name` in the set, nor an `.emit_event` attribute, nor a literal
`getattr`. So `publish` never enters the emitter-name set. At the call site
(1566-1570) the callee `Name('publish')` is not in the set, so the node fails the
`_is_event_emitter_ref` test and is skipped by `continue` — it is never added to
`checked` and never argument-checked. The unregistered event is not *unresolved*, it
is **unseen**. Finally `_finish(..., None if checked else "no emit_event references
inspected", ...)` (1591-1592) computes vacuity over the run-aggregate `checked` list,
which the unrelated valid call in `flow.py` has already made non-empty — so the
`EVENT_CONTRACT_GATE_VACUOUS` note never fires, the trusted workflow's
`NOT_APPLICABLE` guard never engages, and the required check reports PASS.

**This is not one shape.** Five further shapes reproduce the identical
`PASS / violations=[] / exit 0` outcome under the same conditions:

| # | Shape | Source (beside the valid call) |
|---|---|---|
| a | identity wrapper (the reviewer's case) | `publish = identity(emit_event)` / `publish("veyro.missing")` |
| b | argument-position escape | `def register(sink): sink("veyro.missing")` / `register(emit_event)` |
| c | container escape | `SINKS = {"p": emit_event}` / `SINKS["p"]("veyro.missing")` |
| d | class-body rename | `class Bus: send = emit_event` / `Bus.send("veyro.missing")` |
| e | string-keyed reflective lookup | `publish = globals()["emit_event"]` / `publish("veyro.missing")` |
| f | conditional callee | `publish = emit_event if True else other` / `publish("veyro.missing")` |
| o | instance-attribute rename | `self.send = emit_event` in `__init__` / `self.send("veyro.missing")` |

Case (o) additionally falsifies a **second** overstatement still live in the gate
comment, at lines 1491-1493: *"an attribute target such as `self.emit_event =
emit_event` needs no resolution, since the resulting `self.emit_event(...)` call
matches on the attribute name."* That holds only when the attribute name is
preserved. `self.send = emit_event` preserves nothing and passes. Since P1-1 was
itself partly a finding about this comment overstating its guarantee, this must be
corrected in the same pass rather than left for a later round to re-discover.

## 3. Root cause

The mechanism in §2 is *how* a reference becomes invisible. It is not the root cause.
The root cause is a status inversion, measured on one identical escaping module:

| Tree | Outcome |
|---|---|
| escaping module **alone** | `INCONCLUSIVE` / `EVENT_CONTRACT_GATE_VACUOUS` / `checked=[]` / **exit 2** → wrapper DENY |
| **same** module **+ one valid canonical call** | `PASS` / `violations=[]` / `checked=1` / **exit 0** → wrapper PASS |

Adding *correct* code to a tree containing an escaped emitter upgrades the gate's
verdict from denial to PASS. Partial recognition is strictly **safer** than total
recognition failure.

That sentence is already decided against in this project, for a different gate.
`ADR-011` addendum D6.7.2 (gate 2, module-deps) states the invariant:

> For any statement text T, the gate's outcome must be **no weaker** — on the
> ordering `clean < FAIL/ERROR` — than the outcome it would produce for T if the
> extractor had returned nothing. **Partial extraction may never be safer than total
> extraction failure.**

and replaces the offending `if not idents:` guard with *"an accounting comparison
between recognised signals and attributed identifiers."* D6.7.4 adds that the
recognition vocabulary *"is a floor that lowers the ERROR rate; it is **not** the
fail-closed mechanism, and no clause of this ADR may be read as making the gate's
soundness depend on it."*

Gate 3's `None if checked else …` at 1591-1592 **is** that `if not idents:` guard,
one gate over. Gate 3 has no per-reference accounting: it reasons over the run
aggregate, so one recognized reference's success masks another's invisibility. Gate
3's soundness therefore rests entirely on recognition completeness — exactly what
D6.7.4 forbids.

**Why the principle was never applied here:** each architecture gate has an ADR
fixing its input contract and error taxonomy — `ADR-009` gate 4 (permission lint),
`ADR-010` gate 1 (RLS runtime envelope), `ADR-011` gate 2 (module-deps). **Gate 3 is
the only implemented gate with no ADR at all.** The D6.7 principle was decided for
gate 2 and never transposed. P1-1 is the consequence, not a novel class.

## 4. Source-use recognition is not callee resolution

The two concerns the current design conflates, and which the contract in §5
separates:

**Source-use recognition** asks: *does this syntactic position denote the emitter?*
It is local, finite, and keyed to the emitter symbol — the canonical name
`emit_event`, a `from … import emit_event [as X]` binding, a literal `.emit_event`
attribute, a literal `getattr(_, "emit_event")` retrieval. In case (a) recognition
**succeeds**: `emit_event` is plainly visible as an argument to `identity(...)`.

**Callee resolution** asks: *is this call's callee the emitter?* It requires following
a value through a binding, and it fails the moment the value passes through anything
the resolver cannot evaluate — a function call, a container, a conditional.

The current gate only ever acts when **both** succeed. Recognition without resolution
produces silence. That is the defect: the emitter value provably leaves the gate's
model at a line the gate can see, and nothing is said.

The correction follows directly, and it is why no dataflow framework is needed: the
gate does not need to know *where* an escaped emitter ends up. It only needs to
observe, locally, that it escaped. An unresolvable callee can only ever receive the
emitter if some scanned module first let it escape in a statically visible position
— so **the escape is the enforceable event**, and it is anchored at the emitter
reference's own line, never at the mystery call. This is the gate-3 analogue of
D6.7.2's accounting comparison: recognized emitter references versus emitter
references that reached a checked callee.

## 5. The minimum enforceable contract

Five rules. One AST pass per file. No cross-module model, no dataflow, no taint,
no exemption table.

**R1 — Recognition (retained unchanged).** A node is an *emitter reference* if, after
unwrapping `ast.NamedExpr`, it is: an `ast.Name` whose `id` is in the module's
emitter-name set; an `ast.Attribute` with `attr == "emit_event"`; or a literal
`getattr(<expr>, "emit_event")` call (2–3 positional args, no keywords). The
emitter-name set is built exactly as the partial remediation landed it — canonical
name, `from … import` aliases at any level, plus assignment/walrus/annotated/
parameter-default bindings resolved to a fixed point. Recognition only ever **widens**
what is examined, so retaining it is safe and nothing landed is deleted.

**R1a — Only a Load-context `Name` is a *use*.** A `Store`/`Del` target names a
binding; it does not use the emitter's value. This must be expressed as
`isinstance(node.ctx, ast.Load)`, **not** as "exclude assignment targets" — the
prototype in §10 flagged every legitimate alias assignment as its own escape until
this was fixed, and generalizing it to "exclude targets" instead reopens case (d).

**R2 — Per-reference accounting (the fail-closed core).** Every recognized emitter
use must be the **direct callee** of a call (`parent` is an `ast.Call` and
`parent.func is node`).
- If it is: the existing argument check applies unchanged — exactly one positional
  string-literal argument, no keywords, value present in the registry; otherwise
  **FAIL `UNREGISTERED_EVENT_CONTRACT`** (naming the event id, or `"non-literal
  event id"`).
- If it is **not**: **ERROR `EVENT_EMITTER_UNINSPECTABLE`**, naming `file:line` and
  the syntactic position.

**R3 — Canonical name only; renaming is itself an escape.** R2 already denies every
*value*-level renaming, because the renamed binding's right-hand side is a use that
is not a callee. One shape has no Load-context use to catch and therefore needs R3
stated explicitly: `from <mod> import emit_event as <alias>` where `alias !=
"emit_event"` is itself **ERROR `EVENT_EMITTER_UNINSPECTABLE`**. A plain
`from <mod> import emit_event` (no rename) is allowed. §7 shows why this rule is
load-bearing rather than tidiness.

**R4 — Tier-2 string recognition.** An `ast.Constant` whose value is exactly the
string `"emit_event"`, and which is not the recognized literal attribute argument of
an R1 `getattr` emitter reference, is **ERROR `DYNAMIC_EVENT_EMITTER_REFERENCE`**.
This closes case (e), and `getattr(bus, NAME)` with `NAME = "emit_event"`, and
`operator.attrgetter("emit_event")`. It is consistent rather than novel: the existing
literal-`getattr` rule already treats that same string as identifying the emitter.
It must **not** be claimed to close reflective access generally — `globals()["emit" +
"_event"]` defeats it (§8).

**R5 — No exemptions in v1.** Per D6.7.7's *"no skip, exempt, allowlist, or
suppression path of any kind"* and D6.7.1's rule that narrowing is never free and
requires its own recorded decision.

**Rejected alternative — a reflective-construct denylist** (`globals`/`locals`/`vars`/
`__dict__`/`eval`/`attrgetter`/…). Name-keyed, open-ended, itself aliasable, and
adopting it would recreate precisely the error D6.7.4 names: making the gate's
soundness depend on a vocabulary. R4 keys on the emitter's own name, which is fixed
by the contract, not on an enumeration of the ways to reach it.

**Rejected alternative — widen `ast.Attribute` matching to the module's resolved
emitter-name set** (to catch case (d) directly). It would flag every unrelated
attribute call on a common verb (`.send()`, `.publish()`) in any module that aliases
— a real false-positive class with no fail-closed benefit, since R2 already denies
case (d) at the assignment line.

**Rejected alternative — exempt function-local bindings** (permitting a local alias
while denying module-scope ones, on the ground that only module-scope names are
importable). It is an exemption, which D6.7.7 refuses, it adds scope analysis, and it
buys nothing: a module-level import alias remains inherently re-exportable, so the
positive alias case inverts either way (§13).

### Status polarity: an escape is ERROR, not FAIL

`ADR-011`'s own Alternatives table decided this: *"Treat an unaccounted position as
FAIL rather than ERROR → Rejected — the gate cannot name an owner it does not know."*
Transposed: the gate cannot name the **event id**. An escape is a statement about
inspectability, not a proven unregistered event, so emitting
`UNREGISTERED_EVENT_CONTRACT` would assert a fact the gate does not have. ERROR
dominates any concurrent FAIL in the same run.

Implementation consequence, verified: `_finish` (385-395) can only yield
FAIL/INCONCLUSIVE/PASS and cannot express ERROR, so the escape path must construct
and return a `GateReport` directly. The precedent is in the same file at 8163-8167,
where gate 2 returns `GateReport("module-deps", ERROR, violations + error_class,
sorted(checked), …)` — a mixed outcome that reports both partitions and preserves
`checked`. Raising `GateInputError` instead would be wrong: it discards `checked` and
every concurrent violation.

## 6. Exactly allowed and rejected shapes

**Allowed — exhaustive.** Any other contact with the emitter inside the scanned tree
is rejected.

| Allowed shape | Condition |
|---|---|
| `emit_event("<id>")` | `<id>` a single string literal, present in the registry |
| `<expr>.emit_event("<id>")` | same |
| `getattr(<expr>, "emit_event")("<id>")` | literal attribute argument; same |
| `from <mod> import emit_event` | no rename; combined with any of the above |

**Rejected — each measured.** "Current" is the live validator; "Contract" is §5.
Every case was run beside one valid canonical call, so no verdict comes from an empty
scan.

| Case | Shape | Current | Contract |
|---|---|---|---|
| a | `publish = identity(emit_event)` | **PASS** | ERROR escape (Call arg) |
| b | `register(emit_event)` | **PASS** | ERROR escape (Call arg) |
| c | `SINKS = {"p": emit_event}` | **PASS** | ERROR escape (Dict) |
| d | `class Bus: send = emit_event` | **PASS** | ERROR escape (Assign) |
| e | `globals()["emit_event"]` | **PASS** | ERROR dynamic ref (R4) |
| f | `publish = emit_event if … else …` | **PASS** | ERROR escape (IfExp) |
| o | `self.send = emit_event` | **PASS** | ERROR escape (Assign) |
| g | `p, q = emit_event, other` | **PASS** | ERROR escape (Tuple) |
| h | `register(sink=emit_event)` | **PASS** | ERROR escape (keyword) |
| i | `def get(): return emit_event` | **PASS** | ERROR escape (Return) |
| j | re-export via assignment alias (§7) | **PASS** | ERROR escape at the binding |
| k | re-export via import alias (§7) | **PASS** | ERROR (R3) |
| l | `emit_event("veyro.missing")` | FAIL | FAIL unregistered *(already correct)* |
| m | `emit_event(name)` | FAIL | FAIL non-literal id *(already correct)* |
| n | `def publish(e): emit_event(e)` in-tree wrapper | FAIL | FAIL non-literal id *(already correct)* |

Cases (l), (m) and (n) are recorded to mark what is **already** fail-closed and must
not regress. (n) matters to the design: an in-tree pass-through wrapper is already
denied today, because the inner call's argument is not a literal. So indirection buys
a legitimate author nothing the gate permits anyway — which is the substantive reason
the §5 contract removes no real capability, not merely the cheaper reason that it is
less code.

## 7. Why renaming must be denied: the in-tree re-export hole

This is the one place where the analysis departed materially from its own starting
design, on measured evidence. The initial candidate contract exempted *resolvable
plain-Name bindings* from the escape rule, on the ground that the resolver already
tracks the new name. That exemption is **unsound at the module boundary**, and the
hole is in-tree, not out-of-tree. Measured, both shapes beside a valid canonical call:

```python
# a.py — a tracked, exempt plain-Name binding at module scope
from veyro.bus import emit_event
publish = emit_event

# b.py — imports the alias under its NEW name; contains no emitter reference
from a import publish
publish("veyro.missing")
```

Current validator: `status=PASS`, `violations=[]`, exit 0. The exemption-based
candidate design: also **ALLOW**, on every file. The same hole exists one step
earlier, with no assignment at all:

```python
# a.py
from veyro.bus import emit_event as publish
# b.py
from a import publish
publish("veyro.missing")
```

Current validator: **PASS**. A ban on *assignment*-aliasing alone does **not** close
this — measured ALLOW — which is why R3 names the import-alias form explicitly.

Module `b.py` is inside the scan scope and contains nothing to recognize. Retaining
the exemption would therefore require a cross-module import model plus Attribute
widening, i.e. a global false-positive class over every `.publish()`/`.send()` in the
backend. Denying the rename closes it **module-locally, with no cross-module model at
all**. Under R2+R3, `a.py` is ERROR at its own binding line in both variants, and
`b.py` needs no rule.

The scope-discipline conclusion therefore runs opposite to the way the task framed
it: **narrowing is the critical path, not widening.** The in-tree re-export hole is
not an "other optional broad alias form" to defer — it is a live fail-open of the
same class as P1-1, closed for free by refusing indirection. The correct statement is
*close by refusing indirection*, not *close by recognizing more indirection*.

## 8. Ordinary unrelated calls, and the disclosed residuals

**Non-interference.** The contract never declares an unresolved call an emitter. A
call is examined only if its callee is a *recognized emitter reference*; a violation
is raised only at a line that *contains* one. Ordinary indirection is untouched:
identity wrappers, dict-of-callables dispatch, `globals()[key]`, non-literal
`getattr(obj, attr)`, decorators, and a local function that merely shares an alias
name are all unaffected. Measured in §10: zero findings across 70 real repository
files, and a purpose-built module containing every one of those constructs stays
`checked=0`. The over-approximation is confined to modules that genuinely reference
the emitter — a small, auditable set — and the remedy there is always to call the
emitter directly under its own name.

**Residuals — disclosed, never claimed as fail-closed.** All three share one
property: the scanned module contains no statically recognizable reference, so
nothing in this design family can see them. The gate's claim is bounded to
*statically recognizable references within `backend/app/**`*.

1. **An emitter wrapped in a module outside the scan scope.** Measured: `from
   veyro.helpers import publish` / `publish("veyro.missing")` beside a valid call →
   `PASS`, `violations=[]` on the current validator and on the prototype alike. This
   is the sharpest case of recognition requiring a source use: there is none to
   recognize. **Ruling: disclose, do not widen the scope and do not assert
   exclusivity** (§13 explains why that choice is what keeps this work inside
   engineering authority). Widening only relocates the boundary — it can never
   include site-packages — and widening to `backend/**` or `tools/**` immediately
   produces a measured false positive on the validator's own
   `CANONICAL_EVENT_EMITTER = "emit_event"` line (`tools/validate_architecture_gates.py:1453`):
   real cost now, partial benefit, boundary still present.
2. **A dynamically constructed symbol name** — string arithmetic, computed
   `getattr`/`importlib`/`attrgetter`. R4 is exact-match only and must be described
   that way.
3. **The emitter reaching the scanned tree through an object the gate never sees**,
   e.g. a container populated outside the scope.

A fourth item is already honestly disclosed in the current comment and should be
kept: binding collection is file-wide rather than lexically scoped, which
over-approximates toward a violation — the fail-closed direction.

**The comment must also state the invariant positively**, transposed from D6.7.2, so
the next reader can test the implementation against it rather than re-deriving it:

> For any event source module M, the gate's outcome must be no weaker — on the
> ordering `clean < FAIL < ERROR` — than the outcome it would produce for M if the
> recognizer had recognized nothing. Partial recognition may never be safer than
> total recognition failure.

The absence of that sentence is what allowed P1-1. Both of the current comment's
overstatements — the one P1-1 named, and the attribute-target claim at 1491-1493
falsified by case (o) — must be corrected in the same pass, and the replacement must
use "is outside this gate's static reach and is not claimed" rather than "fails
closed" for every item above.

**One false-positive class to document rather than exempt.** Test modules live
**inside** the scan scope (`backend/app/modules/*/tests/test_scaffold_live.py`).
`mock.patch.object(bus, "emit_event")` would be ERROR under R4, while the dotted form
`mock.patch("veyro.bus.emit_event")` is not an exact match and stays clean. The
dotted form is therefore the legal route for emitter tests and must be stated in the
ADR and the gate comment, not discovered by whoever first writes one. A test-path
exemption must **not** be granted: a test path that may reference the emitter freely
is an emission surface. Measured: `backend/app/**` currently contains zero
`mock`/`patch` occurrences, so this costs nothing today.

**Recorded disagreement on the one proposed exemption.** The architecture judgment
recommended admitting exactly one — string constants that are elements of an
`__all__` assignment — under the stated admission test *"the position provably cannot
yield a callable reference to the emitter."* The admission test is sound and worth
recording for future auditability. The exemption itself is **not recommended for
v1**: `backend/app/**` contains zero `__all__` occurrences (measured), so it closes
no present need, and D6.7.1 holds that narrowing requires its own recorded decision.
Admitting it pre-emptively spends the project's one principled exemption on a
hypothetical. Recommendation: refuse in v1, pre-record the admission test, and add it
by ADR amendment if and when a real occurrence appears.

## 9. Violation vocabulary and CI compatibility

**New codes, not folded into the existing vocabulary.** Two reasons, the second
decisive: the outcomes differ in both status and exit code (FAIL/1 versus ERROR/2),
and `UNREGISTERED_EVENT_CONTRACT` asserts a fact the escape case cannot assert
(§5, polarity). Precedent: gate 1's round-12 additions
(`RLS_RUNTIME_ROLE_ELEVATED`, `RLS_TENANT_ID_NULLABLE`) landed with the §4 row
updated; gate 2 carries `MODULE_DEPS_SOURCE_UNINSPECTABLE`.
`.claude/rules/infra/observability.md` control 1 independently requires a named
violation type plus offending file/line.

Proposed codes: **`EVENT_EMITTER_UNINSPECTABLE`** (R2/R3 escape, ERROR) and
**`DYNAMIC_EVENT_EMITTER_REFERENCE`** (R4, ERROR).
`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §4 row 3 currently names the denial
vocabulary as exactly `UNREGISTERED_EVENT_CONTRACT` or `EVENT_CHANGE_UNAPPROVED`, and
must be updated in the same change.

**CI compatibility, verified.** `.github/workflows/scn020-trusted-event-contract.yml`
lines 247-267 admit only exit 0 + `status == 'PASS'` + `bootstrap != 'true'`, or the
exact `empty and vacuous` tuple (`status==2`, `INCONCLUSIVE`, `codes ==
['EVENT_CONTRACT_GATE_VACUOUS']`); every other outcome reaches an unconditional
`SystemExit('… DENY …')`. New codes therefore **deny through the existing wrapper
with no workflow edit**, and the `NOT_APPLICABLE` allowance is unaffected because any
escape makes `vacuous` false. No `.github/**` change is required by this design,
which also keeps it clear of `.claude/rules/infra/iac.md` control 5.

## 10. Prototype evidence

A standalone prototype of §5 was written in `/tmp` — not a modified copy of the
validator, and importing nothing from it — purely to establish that the contract is
implementable and discriminating before any implementation is authorized. Against a
21-fixture corpus plus the re-export trees:

| Measurement | Result |
|---|---|
| Legitimate allowed shapes (§6 table 1, plus multi-target assign) | **ALLOW**, correct `checked` counts |
| All escape/unregistered shapes (§6 table 2) | **REJECT**, each at the expected line and position |
| Each escape composed beside a valid canonical call | **REJECT** — the P1-1 condition closed |
| Ordinary unrelated module (identity wrappers, dict dispatch, `globals()[key]`, non-literal `getattr`, decorators, name-sharing local) | **ALLOW**, `checked=0` |
| False-positive sweep, real repo: `backend/app` (23 files), `backend/tests` (28), `knowledge` (19) | **0 rejections / 70 files** |
| Only rejection anywhere in the repository | `tools/validate_architecture_gates.py:1453` — the validator's own `CANONICAL_EVENT_EMITTER = "emit_event"`, **outside** the gate's scan scope |

That single rejection is not a false positive for the gate as scoped, but it is a
precise demonstration of R4's one genuine false-positive class — a module that
legitimately mentions the emitter's name as a string — and it is the measured reason
§8 refuses to widen the scan scope.

**Present-day cost is zero.** `backend/app/**` is 23 `.py` files containing zero
`emit_event` references, zero `getattr(`, zero `globals()/locals()/vars()`, zero
`__all__`, zero `mock`/`patch`. The gate on the real tree today returns
`INCONCLUSIVE` / `EVENT_CONTRACT_GATE_VACUOUS` / `checked=[]` / exit 2. Every rule
proposed here has no effect on any code that exists; the entire exposure — and the
entire benefit — is forward-binding. This is precisely why booking the contract now
is cheap and booking it after the emitter is written is not.

## 11. Focused regression fixtures

Finite and focused, not a corpus. The existing landed test
(`tools/tests/test_validate_architecture_gates.py:443-525`) already establishes the
right conventions and should be extended rather than replaced: every case keeps one
legitimate canonical call present, so no verdict can come from an empty scan, and it
already carries a "must not manufacture emitters out of unrelated code" negative
block. Two new test functions:

**`test_event_contract_escaped_emitter_cannot_yield_a_green_pass`** — positive
control first (canonical, `.emit_event` attribute, and literal-`getattr` callee each
emitting a *registered* event → PASS, each visibly in `checked`), then one case per
rejected row of §6 asserting ERROR status, the expected code, and the citing
`file:line`. Cases (j) and (k) are two-file fixtures. Assertions must check
`status`/code/subject membership rather than whole-list equality, since one source
line can legitimately produce both an escape and a resolved-callee finding (§13).

**`test_event_contract_ordinary_indirection_is_not_an_emitter`** — the §8
non-interference set: identity wrapper, dict-of-callables dispatch, `globals()[key]`,
non-literal `getattr(obj, attr)`, decorator, and a local function sharing an alias
name. Each must leave `checked` at exactly the one legitimate call and stay PASS.

**Mutation checks to record as killed**, since a passing suite is not evidence of a
load-bearing one: drop R1a's `ast.Load` test (legitimate aliases self-report —
discovered live, §13); drop R3 (case (k) re-opens); drop R4 (case (e) re-opens);
downgrade the escape from ERROR to FAIL (polarity lost); and restore
`_finish`'s aggregate vacuity guard as the only accounting (the §3 inversion
returns).

## 12. Next bounded implementation boundary

One bounded correction, in this order, under the sole lease, by the implementation
tier — **not** by this design worker and not by any review role:

1. Author the **gate-3 ADR** (§13) and have it accepted. It is a prerequisite, not
   documentation after the fact: it is where the renaming ban, the ERROR polarity,
   the new codes, the refused exemption, and the three residuals are decided.
2. Implement R1a, R2, R3, R4 in `run_event_contract_gate`, returning `GateReport(…,
   ERROR, …)` directly on the escape path per the 8163-8167 precedent. Retain
   `_event_emitter_names`/`_is_event_emitter_ref` as landed.
3. Replace the gate comment at 1383-1405: correct the attribute-target overstatement
   at 1491-1493, state the §8 invariant positively, and list the three residuals in
   "not claimed" terms.
4. Update the existing regression test's expectations (§13 item 2) and add the two
   test functions in §11, with the mutation checks recorded as killed.
5. Update `IMPLEMENTATION.md` §4 row 3's denial vocabulary; record the
   `mock.patch("veyro.bus.emit_event")` dotted-path convention for tests.
6. Re-run the focused file, scoped Ruff, compile, and the 4/4 baseline check; record
   results without claiming any scenario PASS.

**Explicitly out of scope** and to stay out: widening the scan scope; a
reflective-API denylist; Attribute widening to resolved emitter names; lexical
scoping of bindings; any cross-module import graph; gate 2's U1/U2 **B HOLD**; the
P3 items; and P1-2 / P2-1..P2-4, which are separate corrections. No generic dataflow
or taint framework: `ADR-011`'s Alternatives table already rejected the analogous
"full residue accounting" as out of scope, and the argument is stronger here because
the escape rule needs no dataflow at all.

**Forward obligation to book in the ADR, not to implement now.** The complete
guarantee is runtime, not static: `emit_event` validating its event id against the
registry and raising on miss is complete *regardless of how the callee was obtained*,
and it is the only control that covers residuals 1 and 2. It should be allocated as a
binding obligation on whichever module implements the emitter. There is nothing to
add it to today — zero emitter references exist — which is exactly why booking it now
is cheap.

## 13. Governance dependencies — exact, not inferred

**An ADR is required, and it is a new contract record rather than a bounded
correction.** Gate 3 is the only implemented architecture gate with no ADR (009 =
gate 4, 010 = gate 1, 011 = gate 2; gate 3 absent, verified by directory listing).
This change fixes an input contract, adds two taxonomy codes, adds a status-polarity
rule, bans a code shape, refuses one proposed exemption while pre-recording its
admission test, books three residuals, and allocates one forward obligation. Landing
that without an ADR would leave the one gate whose soundness was just found defective
as the one gate with no recorded contract. The ADR should carry the D6.7 isomorphism
explicitly, so the next reader sees that gate 3 inherited a decided principle rather
than invented one.

**No owner approval is required, and none is inferred or requested.** The baseline
obligation is TSD §24.1 plus `SCN-MOD001-019`'s denial requirement; the reviewer's
"make an unresolvable or dynamic emitter-shaped call a violation rather than an
omission" is a mechanism proposal inside a finding, and a review does not amend the
governing baseline. Taken literally that prescription would flag every unresolved
callee in a FastAPI/SQLAlchemy codebase — the over-approximation this task forbids,
and the same pressure `ADR-011`'s D6.3 correction exists to avoid (*"would ERROR on
ordinary SQL at a rate that generates exactly the pressure to weaken the gate"*). The
§5 contract closes the finding's actual stated defect — aliased or wrapped emitters
escaping while the gate reports PASS — measured on the reviewer's own fixture and on
six further shapes. Verified precedent: `ADR-009`, `ADR-010` and `ADR-011` each fix a
gate's input contract and error taxonomy, and **none of the three has a row in
`OWNER_APPROVALS.md`**; the existing rows cover baseline interpretation, the
orchestration operating model, the review stopping rule, a capability retirement, and
live GitHub scope. By settled practice a gate's input contract is a recorded
engineering decision.

**Two things that would change that answer, and are therefore not done here.**
First, **asserting that `backend/app/**` is the only legal event-emission surface**
would be a standing architecture constraint on every future module, engaging
`.claude/rules/global/owner-reserved-restrictions.md` item 4. §8 therefore rules
*disclose*, not assert — and that choice is what keeps this entire correction inside
engineering authority, leaving nothing to ask the owner for. Second, **widening the
scan scope** is refused on measured grounds (§8). If a future session decides either
way differently, it must stop and report `BLOCKED: OWNER_APPROVAL_REQUIRED` naming
item 4, not proceed.

**One honest caveat that must appear in the ADR in these terms.** The renaming ban
*does* constrain how future module code may reference the bus: no aliasing or
indirection of the emitter inside the scanned tree. The assessment here is that this
is non-material — it forbids only shapes the gate already refuses to let emit a
non-literal id (§6, case n), there are zero present occurrences, and it is reversible
by ADR amendment. But it is a constraint, it is stated plainly so the owner can read
it differently and reject it, and it is **proposed, not self-authorized**.

**Two measured corrections to the architecture judgment received**, recorded because
the implementation boundary in §12 depends on them and neither is a matter of
preference:

1. The judgment held that banning the binding exemption closes the in-tree
   re-export hole. **Banning assignment-aliasing alone does not** — the import-alias
   variant in §7 measured `PASS` on both the current validator and an
   assignment-only-ban prototype. R3 exists to close it and must be stated
   explicitly; without it the hole survives the ban.
2. The judgment held that *"the just-landed regression test stays green."* **It does
   not.** Under the ban, `publish = emit_event; send = publish; send("veyro.missing")`
   produces three findings (two escapes plus the resolved-callee unregistered
   finding), while the landed test at lines 503-504 asserts exact list equality
   against a single `("UNREGISTERED_EVENT_CONTRACT", "veyro.missing")` entry — so it
   fails. Separately, that test's positive case at lines 470-472 asserts that an
   aliased emitter emitting a *registered* event PASSes, which R3 inverts to ERROR.
   **The implementation is therefore not purely additive: it reverses part of the
   contract the P1-1 partial remediation established** — a contract the now-consumed
   review inspected. That reversal is the real cost of closing the re-export hole,
   it is unavoidable under any sound option (§5, rejected alternatives), and it must
   be disclosed in the ADR rather than absorbed quietly in a test edit.

## 14. Why P1-1 is still blocked

The reviewer's second closure condition — unresolvable/dynamic emitter-shaped calls
cannot silently pass — is **still not met**. This record is design and root cause
only: no validator, test, workflow, or planning document was changed, so the false
PASS in §2 reproduces on the live validator exactly as it did before this analysis.
P1-1 remains **PARTIALLY_REMEDIATED / BLOCKED**, pending both the bounded
implementation in §12 and independent assurance of it, which is not authorized by
anything here and for which the single gate-3 entitlement is already consumed. Gate-3
assurance remains BLOCKED on P1-1, P1-2 and P2-1..P2-4 together.

## 15. Disclosures

- **No repository file other than this one was created, edited, or deleted.** All
  reproduction and prototyping ran in throwaway `/tmp` trees against the live
  validator; the gate-3 source and its test were read only.
- One incidental side effect, from the architecture subagent importing the validator
  in its scratch tree: a bytecode cache at
  `tools/__pycache__/validate_architecture_gates.cpython-314.pyc`. `__pycache__/` is
  gitignored (`.gitignore:38`), so this is not a tracked-content change; it was left
  in place rather than deleted, since deleting is also a mutation.
- **Observed, not acted on:** `git status --porcelain` reports both
  `tools/validate_architecture_gates.py` and
  `tools/tests/test_validate_architecture_gates.py` as **untracked** (`??`). The
  SHA-256 values cited in `GATE3-R1-P1-1-ALIAS-PARTIAL-VERIFICATION-2026-10-09.md`
  bullet 5 therefore pin uncommitted files. Worth confirming that is intended before
  any certification step relies on those hashes. Not changed here — committing is
  outside this worker's charge.
- Model routing: architecture judgment was routed to one fresh-context `veyro-lead`
  Opus subagent, per `ADR-005` and `MODEL_ROUTING.md`; the §5 contract, §7's
  measured departure from the initial candidate design, and §13's two corrections are
  this session's own analysis, grounded in execution rather than in that judgment
  alone.
- Nothing committed or pushed. No `REVIEW_IN_FLIGHT.md` claim was written, since no
  review was dispatched.
