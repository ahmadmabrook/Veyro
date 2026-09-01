---
doc: MOD-000_MODEL_ROUTING_RUNTIME_PROOF
status: LIVE
date: 2026-09-01
---

# MOD-000 Model-Routing Runtime Qualification — through named agents (fresh session)

Supersedes the 2026-08-31 partial version, which relied on the generic `model:` parameter only. This version routes through the actual named `veyro-*` agents, as required.

## Sonnet role — `veyro-implementer`

`Agent(subagent_type: "veyro-implementer")` invoked, asked to self-report.

- Reported model id: **`claude-sonnet-5`** ("Sonnet 5"), quoted verbatim from its own system prompt.
- Reported behavior matched its `.claude/agents/veyro-implementer.md` definition exactly (recited "You implement. You do not certify your own work." and its Opus-escalation clause verbatim).
- Agent run id: `aa78f71602248cd7b` (from the Agent tool's own output).
- **Result: PASS.** Routine-implementation role resolves to Sonnet, through the real named agent, with runtime-observable identity.

## Opus role — `veyro-gatekeeper`

`Agent(subagent_type: "veyro-gatekeeper")` invoked, asked to self-report.

- Reported model id: **`claude-opus-5`** ("Opus 5"), quoted verbatim from its own system prompt.
- Reported behavior matched its `.claude/agents/veyro-gatekeeper.md` definition exactly (ground-truth precedence order, no-self-approval statement, both recited correctly and unprompted).
- Explicitly flagged, on its own initiative, that unrelated boilerplate elsewhere in its injected context mentions other model ids (e.g. an API-usage example referencing `claude-sonnet-4-20250514`) and correctly identified that text as not being its own routing identity — a good sign of the role actually reasoning about assurance carefully rather than pattern-matching the first model string it saw.
- Agent run id: `a3a1ac334da362752`.
- **Result: PASS.** Architecture/assurance/Gatekeeper role resolves to Opus, through the real named agent, with runtime-observable identity.

## Forced-fallback negative test — through the real named-agent routing mechanism

Invoked `Agent(subagent_type: "veyro-gatekeeper-nonexistent-typo")` (deliberate typo of a real agent name).

Result: **hard error before any agent ran** — `Agent type 'veyro-gatekeeper-nonexistent-typo' not found`, with the full authoritative list of available agents (including all 9 real `veyro-*` names) returned as part of the error. No agent was silently substituted, no fallback to a default/generic agent or model occurred.

**Result: PASS** for "invalid/misnamed agent request fails closed via the real routing mechanism."

**Honest scope, unchanged from the prior version:** this proves fail-closed behavior for an *invalid identifier* (agent name here, model id previously). It still does not prove behavior under genuine Opus infrastructure unavailability (a real capacity/outage event on a *valid* request) — that condition remains **BLOCKED/UNVERIFIED**, as it cannot be safely or synthetically forced from within this session. `DEVELOPMENT_CONSTITUTION.md`'s requirement ("if Opus is requested and unavailable, report `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`, not proceed on Sonnet silently") is written into policy and into `veyro-gatekeeper`'s own agent definition, but stays policy-level, not runtime-proven, for that specific scenario.

## Summary

| Item | Result |
|---|---|
| Sonnet routine-implementation role -> `veyro-implementer` -> `claude-sonnet-5` | **PASS** |
| Opus architecture/assurance/Gatekeeper role -> `veyro-gatekeeper` -> `claude-opus-5` | **PASS** |
| Invalid named-agent request fails closed (no silent fallback) | **PASS** |
| True Opus-infrastructure-unavailable -> `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` | **BLOCKED/UNVERIFIED** (cannot be forced safely) |

Model-routing qualification through named agents is now substantively complete, with the one honestly-unresolvable exception noted above (same exception any team would carry — you cannot unit-test a real vendor outage).
