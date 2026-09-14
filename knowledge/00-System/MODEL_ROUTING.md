---
doc: MODEL_ROUTING
status: LIVE
updated: 2026-09-06 (Phase 7, BUG-012/ADR-004/OWN-003 — added the orchestrating-session-tier section below; this front matter date had gone stale, still saying 2026-09-01, caught by Phase 9's second Gatekeeper pass, Editorial)
---

# Model Routing — Veyro

Governed engineering asset per EIP §4.1 ("Automated Model & Agent Routing") and §21.1 required outputs ("MODEL_ROUTING.md + MR schema"). Material changes require an ADR, independent review, the MOD-000 routing qualification drill, and MR-linked evidence before the next assurance gate (§4.1).

## Orchestrating-session tier vs. delegated-role tier (added 2026-09-06, Phase 7 BUG-012/ADR-004/OWN-003)

This table's "Model" column states the tier required for the *judgment*
named in each role — architecture review, code review, security review,
certification, etc. It does not, on its own, say what tier the top-level
orchestrating/lead session itself must run on when it is coordinating
work rather than making one of these judgment calls directly.

A Phase 7 security review found this ambiguous in practice: the
orchestrating session had been authoring ADR text, making Phase gate
determinations, and self-verifying remediation, on Sonnet, without this
table ever saying whether that was compliant or not (`BUG-012`).

**Owner decision (`OWN-003`, 2026-09-06):** Sonnet-tier orchestration is
the accepted operating model. The orchestrating session's own role is
coordination and execution — routing work, writing files, running
checks, and **delegating every Opus-reserved judgment call in the table
below to a fresh-context Opus subagent it spawns** (architecture review,
code review, scenario review, manual QA, security/performance review,
and certification all go through a spawned `veyro-*` Opus agent, never
decided directly by the orchestrating session on its own authority). The
orchestrating session may author the *text* that records a decision an
Opus subagent (or the owner) actually made, but must not make an
architecture/ADR/gate-verdict-class judgment call unilaterally on Sonnet
and present it as settled without that delegation. See
`knowledge/04-Decisions/ADR-004-orchestrating-session-model-tier.md` for
the full options considered and `knowledge/00-System/OWNER_APPROVALS.md`
for the approval record.

## Role -> Agent mapping (EIP §4.1 name vs. actual registered `.claude/agents/veyro-*`)

The EIP's §4.1 routing table names roles generically; this project's actual registered agents (created in MOD-000 chunk 3, confirmed registered/invocable in chunk 5) use different, more specific names. This table is the authoritative reconciliation — no other document should be assumed to carry an implicit renaming.

| EIP §4.1 role/name | Actual registered agent | Model | Notes |
|---|---|---|---|
| "Architecture, ADRs, module planning, dependency/risk decisions" — veyro-lead / veyro-architect | `veyro-lead` | Opus | EIP names both `veyro-lead` and `veyro-architect` as alternates; only `veyro-lead` is registered. No separate `veyro-architect` agent exists — `veyro-lead` covers this role fully. |
| "Routine production implementation..." — veyro-developer | `veyro-implementer` | Sonnet | Renamed. `veyro-developer` does not exist as a registered agent name; `veyro-implementer` is the actual implementation. |
| "Critical implementation slices: authn/authz, tenant isolation/RLS, payments, ledger, entitlements, booking races, access decisions, privacy/deletion, fiscalization, crypto/security boundaries" — veyro-critical-engineer | **Registration pending owner action (`BUG-029`) — see `ADR-005`** | Opus | **Closed via `knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md` Decision 1 (2026-09-14), not via the fallback text below, which is now scoped to an execution *mode* rather than a substitute for the role.** MOD-001's GOV-01-R02 (tenant-isolation/RLS harness, authentication negative-credential fixture pattern) and the RLS/permission architecture gates (GOV-01-R04) are the first real critical slices this project has hit (MOD-000 had none). Per ADR-005: `.claude/agents/veyro-critical-engineer.md` must be authored and registered (Opus) before MOD-001's Definition of Ready, bounded to exactly those 3 slices — not all of MOD-001. **File creation is itself blocked this session** (`.claude/agents/**` is Edit/Write-denied by `.claude/settings.json`, confirmed by direct attempt) — filed as `BUG-029`, routed to the owner, same pattern as `BUG-028`. Within the registered role, the EIP's own execution-mode fallback remains available: Opus (`veyro-critical-engineer`) either implements the slice directly, or fixes the critical design and directs `veyro-implementer` (Sonnet) for the remaining routine implementation — the router records which mode was used (§4.1: "Router records whether Opus directly implemented or supervised"). See SCN-MOD000-080/081 for the escalation-drill pattern this role's own qualification re-run (once registered) will follow. |
| "Deterministic unit/integration/E2E test authoring..." — veyro-test-engineer / veyro-developer | `veyro-test-author` | Sonnet | Renamed. |
| "Scenario Catalog deepening and QA design" — veyro-scenario-reviewer | `veyro-scenario-reviewer` | Opus, fresh context | Exact match. |
| "Independent full code review" — veyro-code-reviewer | `veyro-code-reviewer` | Opus, fresh context | Exact match. |
| "Actual Claude manual QA" — veyro-manual-qa | `veyro-manual-qa` | Opus, fresh context | Exact match. |
| "Security/privacy review and load/performance analysis" — veyro-security-reviewer / veyro-performance-reviewer | `veyro-security-reviewer`, `veyro-performance-reviewer` | Opus | Exact match, both registered. |
| "Final module approval / unlock decision" — veyro-gatekeeper | `veyro-gatekeeper` | Opus, fresh context | Exact match. |

## §4.3 surface-profile agents (added 2026-09-14, ADR-005 Decision 2)

The role→agent table above covers §4.1's lifecycle roles only; it
previously had no rows at all for §4.3's ten surface-specific
implementation-specialist profiles (Backend, Admin Web, general Web,
Front Desk/POS, KMP Mobile, iOS Host, Android Host, Edge, Data/AI,
Infra/SRE) — a real gap `ADR-005` found while resolving MOD-001's
profile-activation question. DC-21: these "become binding starting
MOD-001." Honest registration status, per that ADR's decision that an
empty, code-free directory shell does not itself activate a profile,
but two profiles genuinely activate for MOD-001's own real content:

| §4.3 profile | Path scope | Registered agent | Status |
|---|---|---|---|
| Infra/SRE/CI | `infra/**`, CI, observability | `veyro-infra-sre-engineer` | **ACTIVATED for MOD-001** — registration pending owner action, `BUG-029` |
| Backend | `backend/**` | `veyro-backend-engineer` | **ACTIVATED for MOD-001, bounded** (excludes the critical-slice harness itself — see `veyro-critical-engineer`) — registration pending owner action, `BUG-029` |
| Admin Web | `admin-web/**` | not yet registered | Deferred — no real admin-web source code exists yet |
| General Web | `web/**` (non-admin) | not yet registered | Deferred |
| Front Desk/POS | `frontdesk-web/**` (+ Edge Bridge) | not yet registered | Deferred |
| KMP Mobile | `mobile/shared/**` | not yet registered | Deferred |
| iOS Host | `mobile/iosApp/**` | not yet registered | Deferred |
| Android Host | `mobile/androidApp/**` | not yet registered | Deferred |
| Edge | `edge/**` | not yet registered | Deferred — no `edge/` surface owned by any module yet |
| Data/AI | data-ai-scoped paths | not yet registered | Deferred |

Each deferred profile activates when the module that first adds real
source code under its path scope registers the corresponding agent —
enforced mechanically, not left to interpretation, by MOD-001's own
`surface_profile_activation` CI check (`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md`
§4), which fails closed if a surface path acquires source files of its
own type without the owning module's `module-capabilities.yaml`
recording the matching activated profile. Cross-cutting Security,
Privacy, Tenant Isolation, Financial, Access/Life-Safety, Localization/
RTL, Accessibility, Load, and Observability controls are additive and
apply to MOD-001 now, independent of any surface-profile activation
state (DC-21's own text).

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
