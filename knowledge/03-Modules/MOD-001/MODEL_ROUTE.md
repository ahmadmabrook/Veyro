---
doc: MOD-001_MODEL_ROUTE
status: LIVE — DRAFT (planning stage)
module: MOD-001
updated: 2026-09-19 (Scenario Review round 14, P2-4 — the Infra/SRE/CI
row's path scope corrected from non-glob "CI workflows, observability"
to concrete globs, propagating round 13's own `MODEL_ROUTING.md` fix
here for the first time; BUG-032 CLOSED for real via a second
owner-applied description-field patch, independently verified;
BUG-031 remains CLOSED — all agents and routing layers now genuinely
consistent)
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
for the full reasoning. Three new agents were required:
`veyro-critical-engineer` (Opus, bounded to 3 named slices),
`veyro-infra-sre-engineer` (Sonnet), `veyro-backend-engineer` (Sonnet,
bounded — excludes the critical-slice harness itself). **Corrected
(Scenario Review round 4, P1-3): this previously said "registration is
blocked... routed to the owner" — stale.** All three are now
**registered and routable** — `BUG-029` (creation) is CLOSED for all
three, and `BUG-030`/`BUG-031` (routing integration) are CLOSED for all
three, verified by corrected routing drills dispatched to
`veyro-implementer`. **Historical note (Scenario Review round 7):
`veyro-backend-engineer`/`veyro-infra-sre-engineer` were briefly
registered-but-not-routable, escalated `BUG-031` to P0 (disposition A —
BLOCKING for Definition of Ready) after an independent review found the
planning set itself routed activated-profile work (`SCN-037`/`038`) to
`veyro-implementer` instead, contradicting `ADR-005`'s own explicit
rejection of exactly that substitution. Closed 2026-09-17 — owner
applied the drafted escalation patch (commit `0afa609`); this session
independently verified it byte-for-byte and re-ran the routing drill,
proving real escalation to both agents.** `veyro-test-author`'s
identical unreachability gap (`BUG-032`) had a second, distinct
half — the `veyro-implementer.md` `description` frontmatter field
still claimed test authoring for itself even after the escalation-text
patch, since Claude Code uses that field for automatic *selection*, a
different layer than the body text's post-dispatch escalation rule.
Round 8 (2026-09-17) caught this and re-opened `BUG-032` on that half;
a second owner patch (commit `740ac75`, 2026-09-18) fixed the
`description` field itself, independently verified byte-for-byte plus
a fresh dispatch confirming the field and body now agree. **`BUG-032`
CLOSED (2026-09-18), both halves.** See
`knowledge/03-Modules/MOD-001/evidence/model-routing/ROUTING_DRILL_2026-09-14.md`,
`knowledge/03-Modules/MOD-001/evidence/model-routing/ROUTING_DRILL_2026-09-17-bug031-bug032-closure.md`,
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-031-orphaned-agent-veyro-backend-infra-sre.md`,
and `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-032-orphaned-agent-veyro-test-author.md`.

**Planned routing for MOD-001 implementation (future turn, not this
one):** matches `MODEL_ROUTING.md`'s existing role→agent table plus the
three additions above:

| Task class | Agent | Model |
|---|---|---|
| Routine implementation outside the two activated surfaces below (top-level scaffolding not scoped to `backend/**`/`infra/**`, validators, `contracts/**`, `tools/**`) | `veyro-implementer` | Sonnet |
| Infra/SRE/CI surface work (`infra/**`, `.github/workflows/**` — **corrected, Scenario Review round 14, P2-4: was the non-glob "CI workflows, observability," stale since round 13's P2-5 fix to `MODEL_ROUTING.md`**) — **corrected, Scenario Review round 7: previously overlapped with the row above's "CI config," an ambiguity `ADR-005` itself rejects (lines 448-452: "Letting `veyro-implementer` stand in for the two named surface engineers is rejected")** | `veyro-infra-sre-engineer` | Sonnet |
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
tenant-isolation/RLS harness (GOV-01-R02) and all seven architecture
gates (the six TSD §24.1 gates plus the ADR-005-added surface-profile-
activation gate — **corrected, Scenario Review round 13, P2-1: was
"the six architecture gates (§24.1)," leaving gate 7's five Blocker/
Opus scenarios with no stated escalation trigger in this document**)
are security-sensitive surfaces per `MODEL_ROUTING.md`'s
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
routing (status as of the most recent Scenario Review round — see
`SCENARIOS.md` §5 for the authoritative, current account; not
restated in full here to avoid the exact propagation-gap species that
has recurred across this catalog's review rounds — **corrected,
Scenario Review round 10, Editorial-2: this line previously pinned
"six" review rounds, itself stale by three rounds, the identical
species this line's own point warns about; deliberately not replaced
with a fresher pinned number**):**
(1) the three new agent files exist, are registered, AND are
routable — **caveat added, Scenario Review round 6, P1-4, escalated
round 7, CLOSED 2026-09-17: `veyro-critical-engineer` was always both
(proven by the routing drill below); `veyro-backend-engineer`/
`veyro-infra-sre-engineer` were registered but unreachable from any
`.claude/agents/*.md` escalation path for a time — filed as `BUG-031`,
escalated to P0 (an independent review found MOD-001's own planning
set had already routed activated-Infra-profile work to
`veyro-implementer` instead, exactly the substitution `ADR-005`
rejects). Closed 2026-09-17: the owner applied the drafted escalation
patch, independently verified byte-for-byte, and a 6-case routing
drill proved real escalation to both agents (plus `veyro-test-author`,
closing the related `BUG-032`) — see
`evidence/model-routing/ROUTING_DRILL_2026-09-17-bug031-bug032-closure.md`.
All three agents are now genuinely registered and routable**;
(2) independent review of the critical-engineer definition/routing has
run — **two rounds**, round 1 (`evidence/model-routing/CRITICAL_ENGINEER_DEFINITION_REVIEW_2026-09-14.md`,
BLOCKED, led to filing `BUG-030`) and round 2, after the fix
(`evidence/model-routing/CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`,
APPROVED — **corrected, Scenario Review round 4 P0-1: round 2's result
was previously referenced only in prose, with no durable evidence file,
until this correction**);
(3) a corrected routing drill (dispatched to `veyro-implementer`, the
correct subject) has run — see
`evidence/model-routing/ROUTING_DRILL_2026-09-14.md`'s "Corrected
drill" section for its own verdict;
(4) MR evidence is recorded, with resolved model identity formally
**accepted as a disclosed, non-blocking `BUG-027`-class residual** — see
`ADR-005`'s own addendum, not "not yet formally accepted" as this line
previously (and incorrectly) said;
(5) `MODEL_ROUTING.md`'s critical-slice row reflects current
registration state.

For which of these are fully satisfied vs. still open, see
`knowledge/03-Modules/MOD-001/STATUS.md`'s gate checklist — that file,
not this one, is the single place this project now tracks the
condition-by-condition status, per the same de-duplication fix
`CURRENT_STATE.md`/`STATUS.md`/`SCENARIOS.md` all adopted this round.
