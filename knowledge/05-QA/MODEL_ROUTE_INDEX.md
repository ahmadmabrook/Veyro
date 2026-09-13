---
doc: MODEL_ROUTE_INDEX
status: LIVE
updated: 2026-09-12 (Phase 9 restoration proof, BUG-026 — file had gone stale since 2026-09-01, contradicting ASSURANCE_TIER_AUDIT.md and CURRENT_STATE.md about which agents have real runtime-tier evidence)
---

# Model Route Index — Veyro

Durable index of every model-routing binding and its qualification status. Mirrors the Notion "Model Routes and Agent Runs" database; on divergence, this file (Git) wins.

| Agent | Intended tier | Qualification status | Evidence |
|---|---|---|---|
| `veyro-lead` | Opus | **QUALIFIED** — cross-checked real transcript, 100% `claude-opus-5` across all turns | `ASSURANCE_TIER_AUDIT.md` |
| `veyro-implementer` | Sonnet | **QUALIFIED** — self-reported `claude-sonnet-5`, definition body verbatim-confirmed | `RUNTIME_PROOF.md` |
| `veyro-scenario-reviewer` | Opus, fresh | **QUALIFIED** — cross-checked real transcript, 100% `claude-opus-5` across all turns | `ASSURANCE_TIER_AUDIT.md` |
| `veyro-code-reviewer` | Opus, fresh | **QUALIFIED** — `mr_verify.py`-attested across multiple Phase 5 review-round transcripts, 100% `claude-opus-5` | `ASSURANCE_TIER_AUDIT.md`, `CR-MOD000-001.md` |
| `veyro-manual-qa` | Opus, fresh | **QUALIFIED** — `mr_verify.py`-attested Phase 6 transcript, 203 turns, 100% `claude-opus-5` (not self-report) | `ASSURANCE_TIER_AUDIT.md`, `CAPABILITY_DRILL_PHASE6_2026-09-05.md` |
| `veyro-security-reviewer` | Opus | **QUALIFIED** — cross-checked real transcript (BUG-006 review, 37 turns), 100% `claude-opus-5`; reused across Phase 7 rounds 3/4 and Phase 8 BUG-024 adjudication | `ASSURANCE_TIER_AUDIT.md`, `ASSURANCE_TIER_AUDIT_2026-09-05_output.txt` |
| `veyro-performance-reviewer` | Opus | Not yet individually runtime-tested via `mr_verify.py`/transcript audit distinct from the general Phase 7 performance narrative — left honest, not inferred | — |
| `veyro-gatekeeper` | Opus, fresh | **QUALIFIED** — self-reported `claude-opus-5`, definition body verbatim-confirmed | `RUNTIME_PROOF.md` |
| `veyro-test-author` | Sonnet | **QUALIFIED** — cross-checked real transcript, 100% `claude-sonnet-5` across all turns | `ASSURANCE_TIER_AUDIT.md` |

**Correction 2026-09-12 (Phase 9, BUG-026, and re-review fix same chunk):**
this table previously said 7 of 9 agents were "Not yet individually
runtime-tested," unchanged since 2026-09-01. That was stale and
contradicted `ASSURANCE_TIER_AUDIT.md` (2026-09-05), which had already
cross-checked 20 real subagent transcripts across Phases 3-5 and found
`veyro-lead`, `veyro-code-reviewer`, `veyro-manual-qa`,
`veyro-security-reviewer`, `veyro-scenario-reviewer`, and
`veyro-test-author` (6 of the 7 previously-marked-unconfirmed rows) each
100% correct-tier. The first fix pass this chunk missed the
`veyro-test-author` row despite `ASSURANCE_TIER_AUDIT.md` line 49
covering it explicitly — caught by independent Gatekeeper re-review and
corrected in the same chunk. **`veyro-performance-reviewer` is the one
row genuinely not covered by that audit** (it names 6 Opus + 2 Sonnet
agents, not `veyro-performance-reviewer`) and is left honestly
unconfirmed, not inferred. See
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-026-model-route-index-stale-contradiction.md`.

## Cross-cutting proofs (apply to all agents, not per-row)

- Custom agent registration mechanism: **PASS** (fresh-session proof, `SETTINGS_HOOK_RULE_PROOF.md`)
- Invalid/misnamed agent request fails closed, no silent substitution: **PASS**
- True Opus-infrastructure-unavailability -> `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`: **BLOCKED/UNVERIFIED**, cannot be safely forced
