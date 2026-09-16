---
doc: BUG-031
module: MOD-001
severity: P1
status: OPEN — disposition recorded, non-blocking for Definition of Ready
filed: 2026-09-16 (Scenario Review round 6, P1-4)
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
This instance is filed P1, not P0, because a reasoned disposition exists
and the defect is not yet load-bearing: `veyro-backend-engineer`/
`veyro-infra-sre-engineer` exist to implement `backend/**`/`infra/**`
surface work once real implementation begins (per ADR-005 Decision 2),
and no such implementation has started — nothing currently needs to
route to them for real work. The gap becomes load-bearing, and would
need to be P0, the day either surface's real implementation begins.

`SCN-MOD001-120(a)` (added round 4, corrected round 5 to test
reachability) will catch this mechanically once
`tools/validate_agent_definitions.py` exists and runs in CI — but that
tool doesn't exist yet (planning stage), so the gate that would catch
this in production isn't live today, and the gap sits undetected outside
independent Scenario Review.

## Why P1, not P0

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

## Required before closure

Either:
1. `veyro-implementer.md` and/or `veyro-lead.md` gain an escalation
   sentence naming both agents (the same fix pattern `BUG-030` used) —
   requires an owner-applied `.claude/agents/**` edit, same protection
   class as `BUG-030`; or
2. Both agents are confirmed to route via a different, already-correct
   mechanism this bug's finding missed (re-verification, not a new
   patch).

**Must close before real `backend/**`/`infra/**` implementation begins.**
Not required before MOD-001's own Definition of Ready, since Ready
governs planning/specification completeness, not runtime reachability
of implementation-phase agents that have nothing to implement yet.

## Cross-references

- `knowledge/03-Modules/MOD-001/evidence/model-routing/CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`
  (P2-1 — the original, undertracked finding)
- `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-030-existing-agent-file-edit-capability-gap.md`
  (the identical defect class, previously closed for `veyro-critical-engineer`)
- `knowledge/03-Modules/MOD-001/SCENARIOS.md` SCN-MOD001-120(a) (the
  scenario that will mechanically catch this once its tool exists)
