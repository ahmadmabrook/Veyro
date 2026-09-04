---
doc: MODEL_ROUTING
status: LIVE
updated: 2026-09-01
---

# Model Routing — Veyro

Governed engineering asset per EIP §4.1 ("Automated Model & Agent Routing") and §21.1 required outputs ("MODEL_ROUTING.md + MR schema"). Material changes require an ADR, independent review, the MOD-000 routing qualification drill, and MR-linked evidence before the next assurance gate (§4.1).

## Role -> Agent mapping (EIP §4.1 name vs. actual registered `.claude/agents/veyro-*`)

The EIP's §4.1 routing table names roles generically; this project's actual registered agents (created in MOD-000 chunk 3, confirmed registered/invocable in chunk 5) use different, more specific names. This table is the authoritative reconciliation — no other document should be assumed to carry an implicit renaming.

| EIP §4.1 role/name | Actual registered agent | Model | Notes |
|---|---|---|---|
| "Architecture, ADRs, module planning, dependency/risk decisions" — veyro-lead / veyro-architect | `veyro-lead` | Opus | EIP names both `veyro-lead` and `veyro-architect` as alternates; only `veyro-lead` is registered. No separate `veyro-architect` agent exists — `veyro-lead` covers this role fully. |
| "Routine production implementation..." — veyro-developer | `veyro-implementer` | Sonnet | Renamed. `veyro-developer` does not exist as a registered agent name; `veyro-implementer` is the actual implementation. |
| "Critical implementation slices: authn/authz, tenant isolation/RLS, payments, ledger, entitlements, booking races, access decisions, privacy/deletion, fiscalization, crypto/security boundaries" — veyro-critical-engineer | **not yet registered** | Opus | Real gap, recorded honestly (not papered over). See SCN-MOD000-080/081. Until a dedicated `veyro-critical-engineer` agent is authored, this role is covered by `veyro-lead` (architecture) directing `veyro-implementer` (Sonnet) under explicit Opus supervision, per the EIP's own fallback text ("Opus or Opus-led pair... may direct Sonnet implementation after the critical design is fixed"). MOD-000 itself does not contain any critical implementation slices (no authn/authz/payments/etc. in a control-plane bootstrap module), so this gap has not blocked MOD-000 to date, but must be closed before MOD-001+ touches any critical slice. |
| "Deterministic unit/integration/E2E test authoring..." — veyro-test-engineer / veyro-developer | `veyro-test-author` | Sonnet | Renamed. |
| "Scenario Catalog deepening and QA design" — veyro-scenario-reviewer | `veyro-scenario-reviewer` | Opus, fresh context | Exact match. |
| "Independent full code review" — veyro-code-reviewer | `veyro-code-reviewer` | Opus, fresh context | Exact match. |
| "Actual Claude manual QA" — veyro-manual-qa | `veyro-manual-qa` | Opus, fresh context | Exact match. |
| "Security/privacy review and load/performance analysis" — veyro-security-reviewer / veyro-performance-reviewer | `veyro-security-reviewer`, `veyro-performance-reviewer` | Opus | Exact match, both registered. |
| "Final module approval / unlock decision" — veyro-gatekeeper | `veyro-gatekeeper` | Opus, fresh context | Exact match. |

## Escalation triggers (Sonnet -> Opus, automatic)

Per §4.1: "Automatically escalate to Opus when criticality triggers fire." Standing triggers for this project:

- Task touches authn/authz, tenant isolation, payments/ledger/entitlements, booking-race logic, access decisions, privacy/deletion, fiscalization, or crypto/security boundaries (§4.1's named critical-slice list).
- Task would alter architecture, scope, security posture, finance, tenant isolation, or life-safety behavior.
- Task requires spend, real member data, or Production action (owner-reserved — routes to a `BLOCKED: OWNER_APPROVAL_REQUIRED` report regardless of tier, per DC-16, not a tier escalation exactly, but the same trigger family).
- A capability qualification run (positive/negative test, third-party evaluation) — per `CAPABILITY_POLICY.md`'s "Model-routing interaction" clause.

See SCN-MOD000-080 (positive: escalation fires) and SCN-MOD000-081 (negative: no over-escalation on routine work).

## No-silent-downgrade rule (restated from `DEVELOPMENT_CONSTITUTION.md`, EIP §4.1)

Accepted proof of correct-tier execution requires BOTH the configured agent/model-family alias AND runtime evidence (resolved model identity, agent/session/run id). The version-controlled `model: opus` declaration alone is insufficient. If Opus is required and cannot be runtime-verified, the correct report is `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` — never silent proceed on Sonnet. See SCN-MOD000-025/026/028.

## MR evidence format (EIP §4.1: "Each route emits MR-<MOD>-<YYYYMMDD>-<NNN> evidence")

Each routed assurance-tier task should produce an MR record with: task class, lifecycle role, risk triggers (if any), intended family alias, resolved model identity/tier runtime evidence, agent/session ID, verdict. Prior MOD-000 routing evidence (`knowledge/03-Modules/MOD-000/evidence/model-routing/RUNTIME_PROOF.md`) captures this content but not yet under the formal `MR-<MOD>-<YYYYMMDD>-<NNN>` ID scheme — adopting the ID scheme for future routing evidence is a tracked follow-up (see SCN-MOD000-027's existing correction note), not retroactively applied to already-written evidence.
