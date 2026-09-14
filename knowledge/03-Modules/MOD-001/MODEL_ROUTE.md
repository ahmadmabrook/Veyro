---
doc: MOD-001_MODEL_ROUTE
status: LIVE — DRAFT (planning stage)
module: MOD-001
updated: 2026-09-14
---

# MOD-001 — Model Route (per-module)

Appendix D field: "Per-module routing decisions/escalations and MR IDs;
proves required Opus assurance roles and automatic Sonnet implementation
routing without owner model selection." Full cross-module index:
`knowledge/05-QA/MODEL_ROUTE_INDEX.md` (to be updated once this module's
routing has real runtime evidence, not during planning).

**This session's own routing (planning turn):** the orchestrating
session ran on Sonnet throughout (bootstrap, verification, requirement
materialization, module specification, Scenario Catalog authoring) per
`OWN-003`'s accepted operating model — routine execution on Sonnet,
every Opus-reserved judgment call delegated to a fresh-context Opus
subagent. The one Opus-reserved judgment call this turn is the
independent Scenario Review, which this session dispatches to
`veyro-scenario-reviewer` (Opus, fresh context) rather than deciding
itself — see `SCENARIOS.md`'s Review Log for that dispatch's outcome
and model-tier evidence.

**Corrected (Scenario Review round 1, P0-3/P1-9): this previously
claimed "no new agent, no routing change, no ADR needed" — false. A
real fresh-context Opus review found MOD-001's own GOV-01-R02 critical
slice (tenant-isolation/RLS harness, authn negative-credential fixture)
squarely inside EIP §4.1's Opus-critical-slice trigger list, with the
named `veyro-critical-engineer` role still unregistered — and found two
§4.3 surface profiles (Infra/SRE/CI, Backend) genuinely activating for
MOD-001's real scaffold/harness content, contrary to `CAPABILITIES.md`'s
original "none activated" claim. Both were delegated to `veyro-lead`
(Opus) per `OWN-003` rather than decided on Sonnet — see
`knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`
for the full reasoning. Three new agents are now required:
`veyro-critical-engineer` (Opus, bounded to 3 named slices),
`veyro-infra-sre-engineer` (Sonnet), `veyro-backend-engineer` (Sonnet,
bounded — excludes the critical-slice harness itself). Registration is
blocked this session by a second capability gap (`BUG-029` —
`.claude/agents/**` is Edit/Write-denied) and routed to the owner.**

**Planned routing for MOD-001 implementation (future turn, not this
one):** matches `MODEL_ROUTING.md`'s existing role→agent table plus the
three additions above:

| Task class | Agent | Model |
|---|---|---|
| Routine implementation (repo scaffolding, CI config, non-critical-slice harness code, validators) | `veyro-implementer` | Sonnet |
| Infra/SRE/CI surface work (`infra/**`, CI workflows, observability) | `veyro-infra-sre-engineer` | Sonnet |
| Backend surface work (`backend/**`, bounded — excludes the critical-slice harness) | `veyro-backend-engineer` | Sonnet |
| **Critical-slice work: tenant-isolation/RLS harness, authn negative-credential fixture, RLS+permission architecture gates only** | `veyro-critical-engineer` | **Opus** |
| Deterministic test authoring | `veyro-test-author` | Sonnet |
| Architecture/module-planning decisions (this document's own authoring, ADR-005) | `veyro-lead` | Opus |
| Independent Scenario Review | `veyro-scenario-reviewer` | Opus, fresh context |
| Independent code/config review (once implementation exists) | `veyro-code-reviewer` | Opus, fresh context |
| Actual manual QA (once implementation exists) | `veyro-manual-qa` | Opus, fresh context |
| Security/performance assurance (once implementation exists) | `veyro-security-reviewer`, `veyro-performance-reviewer` | Opus |
| Module certification | `veyro-gatekeeper` | Opus, fresh context |

**Escalation triggers relevant to MOD-001 specifically:** the
tenant-isolation/RLS harness (GOV-01-R02) and the six architecture gates
(§24.1) are security-sensitive surfaces per `MODEL_ROUTING.md`'s
standing escalation list — any judgment call about whether those gates'
implementation is correct/sufficient routes to Opus (`veyro-security-reviewer`
or `veyro-lead`), never decided by Sonnet alone. Mechanical execution
(running the gate, recording pass/fail against a pre-declared
condition) may run on Sonnet per DC-17's Blocker-tier SEC/AUTHZ/DR
clarification — the same operating model MOD-000 already established.

**No silent downgrade occurred this turn** — every Opus-reserved action
(Scenario Review, the ADR-005 architecture decision) was dispatched as a
real `Agent` call with `model: opus` set explicitly, not self-decided.

**ADR-005's binding pre-Definition-of-Ready conditions on model
routing, not yet satisfied:** (1) the three new agent files exist —
blocked by `BUG-029`, owner action needed; (2) independent fresh-context
Opus review of `veyro-critical-engineer`'s definition, once authored;
(3) routing-qualification-drill re-run (SCN-MOD000-080/081 pattern)
against the new role, evidence under
`knowledge/03-Modules/MOD-001/evidence/model-routing/`; (4) MR-linked
evidence (`MR-MOD001-<YYYYMMDD>-<NNN>`); (5) this file and
`MODEL_ROUTING.md` reflecting the registered (not merely planned) state.
None of these can complete until `BUG-029` resolves.
