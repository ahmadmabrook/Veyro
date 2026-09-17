---
doc: BUG-032
module: MOD-001
severity: P1
status: CLOSED (2026-09-17) — owner patch applied and independently verified
filed: 2026-09-16 (Scenario Review round 7, P1-4)
closed: 2026-09-17 — see "Closure" section below
---

# BUG-032 — `veyro-test-author` unreachable from any `.claude/agents/*.md` escalation path

## Finding

Independently confirmed by round 7's fresh-context `veyro-scenario-reviewer`
(re-confirmed by direct grep this session): `veyro-test-author` is
registered (it exists as `.claude/agents/veyro-test-author.md` and is
directly dispatchable by name) but is named by zero other agent file's
escalation text — it appears only in its own frontmatter.
`MODEL_ROUTING.md` and `MODEL_ROUTE.md` both route "deterministic test
authoring" to it, but `veyro-implementer.md`'s own description claims
"Routine implementation **and deterministic test authoring**," so
routine-execution sessions absorb that work into `veyro-implementer`
rather than escalating it — an actual, live routing ambiguity, not a
hypothetical one.

This is the same defect *class* as `BUG-030`/`BUG-031` (an agent nothing
routes to) but is explicitly **not a duplicate** of `BUG-031` — it is a
separate agent, found by a separate scenario-catalog gap
(`SCN-MOD001-120(a)`'s prior hardcoded 4-agent list never checked for
it), and its root cause differs: `BUG-031`'s two agents have a clean,
unambiguous ownership split (backend/**, infra/**) that `veyro-implementer`
has no competing claim to; `veyro-test-author`'s scope overlaps with
`veyro-implementer`'s own stated charter, so the "orphan" here is a
role-boundary ambiguity as much as a missing escalation sentence.

## Why P1, and why lower practical risk than BUG-031

- Both `veyro-implementer` and `veyro-test-author` are Sonnet-tier — no
  model-assurance/no-silent-downgrade concern applies (that rule exists
  to prevent an Opus-reserved judgment silently running on Sonnet; this
  is Sonnet-to-Sonnet).
- No architecture decision (`ADR-005` or otherwise) singles out
  `veyro-test-author` the way it singles out the two `BUG-031` agents —
  there is no equivalent "letting `veyro-implementer` stand in is
  rejected" ruling for test authoring.
- Practically, work routed to `veyro-implementer` for test authoring
  still gets done (by design, per its own description) — the defect is
  that a dedicated specialist role exists and nothing ever chooses it
  over the generalist, not that test-authoring work goes undone.

## Required before closure

Either:
1. `veyro-implementer.md` gains an escalation sentence for deterministic
   test-authoring work naming `veyro-test-author` (requires an
   owner-applied `.claude/agents/**` edit, same protection class as
   `BUG-030`/`BUG-031`); or
2. `MODEL_ROUTING.md`/`MODEL_ROUTE.md` are corrected to retire
   `veyro-test-author` as a distinct routing target and fold its scope
   formally into `veyro-implementer`'s own charter, resolving the
   ambiguity the other direction (an architecture decision, not a
   unilateral edit); or
3. Both agents are confirmed to route via a different, already-correct
   mechanism this bug's finding missed (re-verification, not a new
   patch).

Not required before MOD-001's own Definition of Ready by the same
reasoning `BUG-031` was filed non-blocking initially, but see
`BUG-031`'s own evidence file for why that reasoning did NOT hold for
`BUG-031` once the planning set's own routing inconsistency was found —
this bug's disposition has not been independently re-tested against
that same bar and should not be assumed settled merely because this
file states it.

## Closure (2026-09-17)

The owner applied the same patch that closed `BUG-031` — the same
`veyro-implementer.md` edit added a fourth paragraph routing
deterministic test authoring to `veyro-test-author` alongside the
surface-profile paragraphs. This session independently verified the
paragraph's exact text via direct `Read`, and a dedicated routing-drill
dispatch (test-authoring task, part of the same 6-case drill that
closed `BUG-031`) confirmed real escalation: the dispatched
`veyro-implementer` agent quoted the new paragraph verbatim, correctly
distinguished it from `veyro-scenario-reviewer`'s catalog-design-
judgment scope, and declined to author the test cases itself. Full
record: `evidence/model-routing/ROUTING_DRILL_2026-09-17-bug031-bug032-closure.md`.

**BUG-032 CLOSED.** The escalation path for deterministic test
authoring is genuinely present and independently proven to fire.

## Cross-references

- `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-031-orphaned-agent-veyro-backend-infra-sre.md`
  (the related-but-distinct finding this bug is explicitly not a
  duplicate of)
- `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-030-existing-agent-file-edit-capability-gap.md`
  (the original defect class)
- `knowledge/03-Modules/MOD-001/SCENARIOS.md` SCN-MOD001-120(a) (corrected
  this round to derive its checked-agent set from a rule rather than a
  hardcoded list, which is what caught this)
