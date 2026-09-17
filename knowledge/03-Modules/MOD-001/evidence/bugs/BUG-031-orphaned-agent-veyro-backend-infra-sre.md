---
doc: BUG-031
module: MOD-001
severity: P0 (escalated from P1, Scenario Review round 7 — see "Escalation" section below)
status: OPEN — BLOCKING for Definition of Ready
filed: 2026-09-16 (Scenario Review round 6, P1-4)
escalated: 2026-09-16 (Scenario Review round 7, independent BUG-031 Ready-gate impact review)
---

# BUG-031 — `veyro-backend-engineer`/`veyro-infra-sre-engineer` unreachable from any `.claude/agents/*.md` escalation path

## Finding

Independently confirmed by round 6's fresh-context `veyro-scenario-reviewer`
(re-confirmed by direct grep this session): neither `veyro-backend-engineer`
nor `veyro-infra-sre-engineer` is named as an escalation target by any file
under `.claude/agents/`. `veyro-implementer.md`'s own escalation list names
only `veyro-lead`, `veyro-security-reviewer`, `veyro-performance-reviewer`,
`veyro-code-reviewer`, `veyro-gatekeeper`, and `veyro-critical-engineer`.
`veyro-lead.md`'s names only `veyro-critical-engineer`, `veyro-implementer`,
and `veyro-gatekeeper`. Both agents are registered (they exist, are
dispatchable directly by name, and are listed `REGISTERED` in
`evidence/module-capabilities.yaml`) but **unreachable** — nothing routes
to them automatically.

This is the identical defect class `BUG-030` was: an agent whose
escalation text silently fails to route to it, not a reference to a
nonexistent agent. `BUG-030` was filed and closed as P0 because it
blocked the ADR-005-registered critical-slice escalation path entirely.
**This instance was originally filed P1, not P0 (round 6), on the
reasoning that a reasoned disposition existed and the defect was not
yet load-bearing — superseded the same day by round 7's independent
re-examination, which found the defect IS already load-bearing (see
"Escalation" section below). Severity is now P0, matching `BUG-030`.**

`SCN-MOD001-120(a)` (added round 4, corrected round 5 to test
reachability) will catch this mechanically once
`tools/validate_agent_definitions.py` exists and runs in CI — but that
tool doesn't exist yet (planning stage), so the gate that would catch
this in production isn't live today, and the gap sits undetected outside
independent Scenario Review.

## Original disposition (round 6, filed P1, non-blocking for Ready) — SUPERSEDED

- No current work depends on either agent being reachable — MOD-001
  itself has not started implementation, and `backend/**`/`infra/**`
  don't exist as real directories yet (planning stage).
- `CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`'s own P2-1
  finding already recorded this exact gap and recommended closing it
  "before real `backend/**`/`infra/**` implementation, not before DoR"
  — a reasoned disposition existed, but it lived only inside a review-
  findings file and was never propagated to `STATUS.md`'s own gate
  checklist or `BUG_REGISTRY.md`, which is the actual defect round 6
  caught (a documentation-propagation gap, not a newly-discovered
  routing defect).
- Filing this as a tracked, durable bug (rather than leaving the
  disposition to live only inside one review's findings file) is the
  fix: `BUG_REGISTRY.md`'s "0 open P1 bugs" claim was false while this
  gap sat undocumented there.

**This disposition did not survive independent re-examination — see
"Escalation" below.**

## Escalation (round 7): disposition A — BLOCKING for Definition of Ready

Per the mission's own explicit rule ("Do NOT trust that non-blocking
classification merely because this prompt states it"), a fresh
independent Opus review (`veyro-security-reviewer`, dedicated to
exactly this question, not the general Scenario Review) re-examined
whether "no current work depends on either agent being reachable" was
actually true, rather than assumed. It was not:

- **The planning set has already routed activated-profile work to the
  wrong agent.** `SCENARIOS.md` `SCN-MOD001-037`/`038` (QA-environment
  bootstrap, touching `infra/environments/qa/` — the activated
  Infra/SRE/CI surface's own path) were routed to `veyro-implementer`,
  not `veyro-infra-sre-engineer`. `ADR-005` itself explicitly rejects
  this exact substitution ("Letting `veyro-implementer` stand in for
  the two named surface engineers is rejected... Applying the standard
  in one place and not the other would be inconsistent in the
  project's own favour"). This is not a dormant gap waiting for
  implementation to begin — it is a live inconsistency in the plan
  itself, today. **Fixed this round: `SCN-037`/`038` retitled to
  `veyro-infra-sre-engineer`.**
- **The plan's own first implementation act touches both surfaces.**
  `IMPLEMENTATION.md` §1 makes `backend/`, `infra/environments/{local,qa,staging}/`,
  `infra/ci/`, and `.github/workflows/` part of the repository topology
  created by GOV-01-R01 — MOD-001's own first Critical requirement, not
  a later one. There is no "first slice" concept anywhere in this
  module's plan that defers backend/infra work to a later point where
  this could be fixed without blocking anything — `grep`-confirmed
  absent.
- **Nothing fails closed in between.** The `surface_profile_activation`
  gate keys on `module-capabilities.yaml`'s profile rows, not
  reachability, so it passes while this gap persists. The only
  mechanical catcher (`SCN-MOD001-120(a)`, behind
  `tools/validate_agent_definitions.py`) is itself an unbuilt MOD-001
  deliverable with no scheduled position — built during the very phase
  whose risk it exists to catch. Per `ADR-005`'s own standard ("the
  difference between a legitimate deferral and a drifting one is
  whether anything fails closed when it is violated"), this is a
  drifting deferral, not a sanctioned one.
- **`ADR-005`/`MODEL_ROUTING.md` do not actually sanction this
  deferral.** `ADR-005`'s Decision 2 Timing section defers the two
  profiles' *agents and rule families existing with real content* —
  module deliverables inside MOD-001's own implementation scope. It
  says nothing about deferring *reachability*, which is an owner-only
  `.claude/agents/**` edit outside module scope entirely.
  `MODEL_ROUTING.md` is simply silent on timing. Silence is not
  sanction.
- **`STATUS.md`'s own Definition-of-Ready gate is internally
  inconsistent with calling this non-blocking.** `STATUS.md` defines
  Ready as gated on an independent round returning
  `MOD-001 SCENARIO REVIEW APPROVED` with **P0=0/P1=0**. An open P1
  bug is definitionally incompatible with a P1=0 gate; "non-blocking
  P1" was an internally contradictory disposition on the project's own
  terms, not merely a judgment call that happened to be wrong.
- **Both agents' description text is auto-delegation-shaped** ("Use
  for... Do NOT use for... route to...") — they are written to be
  discovered by description-matching, which somewhat mitigates but does
  not close the gap, since `veyro-implementer.md`'s own escalation text
  (the thing a routine-execution session actually consults) still names
  neither agent.

**Severity escalated P1 → P0**, matching `BUG-030`'s own precedent for
the identical defect class. **Disposition: BLOCKING for Definition of
Ready** — MOD-001 cannot be honestly declared Ready while this is open,
and implementation must not begin at all until it closes, since the
plan's first implementation act touches both `infra/**` and
`backend/**` and no gate exists that would fail closed in between.

## Required before closure

1. **The core fix is owner-gated and still open.** `veyro-implementer.md`
   needs an escalation clause routing `infra/**`/CI-workflow work to
   `veyro-infra-sre-engineer` and `backend/**` work to
   `veyro-backend-engineer` while those profiles are activated — the
   same `.claude/agents/**` edit class `BUG-029`/`BUG-030` required,
   which this guarded session cannot make itself (`Edit`/`Write`
   denied on that path). The exact patch text has been drafted and
   handed to the user in this session's own reply, per the `BUG-030`
   precedent (owner applies it directly, this session verifies
   byte-for-byte after).
2. Once applied: re-run a routing drill (same shape as
   `ROUTING_DRILL_2026-09-14.md`'s corrected drill) proving real
   escalation from `veyro-implementer` to each of the two agents for an
   in-scope task.
3. Confirm `SCN-MOD001-120(a)`'s reachability check would pass against
   the patched files (cannot execute for real yet — no CI, no built
   tool — but the fixture logic can be walked by hand against the real
   files).

**Not closable this session** — this is an owner action, identical in
kind to `BUG-029`/`BUG-030`. **MOD-001 remains NOT READY until this
closes and is independently re-verified.**

## Cross-references

- `knowledge/03-Modules/MOD-001/evidence/model-routing/CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`
  (P2-1 — the original, undertracked finding)
- `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-030-existing-agent-file-edit-capability-gap.md`
  (the identical defect class, previously closed for `veyro-critical-engineer`)
- `knowledge/03-Modules/MOD-001/SCENARIOS.md` SCN-MOD001-120(a) (the
  scenario that will mechanically catch this once its tool exists)
- `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-032-orphaned-agent-veyro-test-author.md`
  (a related-but-distinct finding, same defect class, different agent
  and root cause, found via SCN-120(a)'s own round-7 correction)
