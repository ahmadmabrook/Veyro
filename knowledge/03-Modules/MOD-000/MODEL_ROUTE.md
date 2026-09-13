---
doc: MOD-000_MODEL_ROUTE
status: LIVE
updated: 2026-09-12 (Phase 9 restoration proof re-review, Gatekeeper P2-2 — this file had gone stale since 2026-09-05, still describing closed BUG-006 as an open routing-policy violation)
---

# MOD-000 — Model Route (per-module)

Appendix D field: "Per-module routing decisions/escalations and MR IDs;
proves required Opus assurance roles and automatic Sonnet implementation
routing without owner model selection."

Full cross-module index: `knowledge/05-QA/MODEL_ROUTE_INDEX.md`. Runtime
proof evidence: `knowledge/03-Modules/MOD-000/evidence/model-routing/RUNTIME_PROOF.md`.

Routing decisions made for MOD-000: routine implementation and
deterministic test authoring routed to `veyro-implementer`/`veyro-test-author`
(Sonnet); scenario review, code review, manual QA, security review, and
Gatekeeper certification routed to their respective fresh-context Opus
agents. Escalation triggers fired correctly in Phase 3's drills (Sonnet
declining to make an owner-reserved rule-change decision unilaterally).

**Resolved item:** CAP-001/CAP-002 qualification originally ran on
Sonnet, not Opus — a real routing-policy violation, tracked as BUG-006.
**CLOSED (2026-09-05)**: a distinct fresh-context Opus
`veyro-security-reviewer` review independently evaluated both
capabilities (CAP-002 APPROVED scope-narrowed; CAP-001 APPROVED,
scope de-rated, with binding caveats) — see `evidence/bugs/BUG-006-*.md`.
Separately, `BUG-012` (orchestrating-session model tier running
architecture/ADR/gate-verdict work on Sonnet, unattested) is also
**CLOSED (2026-09-06)** via owner decision `OWN-003`: Sonnet-tier
orchestration is the accepted operating model, with every Opus-reserved
judgment call delegated to a fresh-context Opus subagent — see `ADR-004`,
`knowledge/00-System/MODEL_ROUTING.md`. Real per-agent runtime-tier
evidence (transcript cross-checks, not self-report) exists in
`knowledge/03-Modules/MOD-000/evidence/model-routing/ASSURANCE_TIER_AUDIT.md`
and is reflected in `knowledge/05-QA/MODEL_ROUTE_INDEX.md`.

**MR ID adoption:** the `MR-<MOD>-<YYYYMMDD>-<NNN>` evidence scheme is not
yet formally adopted for every routed task (see F5-005/F5-029 in
`evidence/code-review/CR-MOD000-001.md`). This file will link real MR IDs
once that scheme is in use.
