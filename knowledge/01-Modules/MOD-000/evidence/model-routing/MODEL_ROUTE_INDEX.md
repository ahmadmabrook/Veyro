---
doc: MODEL_ROUTE_INDEX
status: LIVE
updated: 2026-09-01
---

# Model Route Index — Veyro

Durable index of every model-routing binding and its qualification status. Mirrors the Notion "Model Routes and Agent Runs" database; on divergence, this file (Git) wins.

| Agent | Intended tier | Qualification status | Evidence |
|---|---|---|---|
| `veyro-lead` | Opus | Not yet individually runtime-tested (role not yet invoked for real work) | — |
| `veyro-implementer` | Sonnet | **QUALIFIED** — self-reported `claude-sonnet-5`, definition body verbatim-confirmed | `RUNTIME_PROOF.md` |
| `veyro-scenario-reviewer` | Opus, fresh | Not yet individually runtime-tested | — |
| `veyro-code-reviewer` | Opus, fresh | Not yet individually runtime-tested | — |
| `veyro-manual-qa` | Opus, fresh | Not yet individually runtime-tested (used in 2026-08-31 manual QA drill only as a *pattern*, not invoked by name — real invocation still pending) | — |
| `veyro-security-reviewer` | Opus | Not yet individually runtime-tested | — |
| `veyro-performance-reviewer` | Opus | Not yet individually runtime-tested | — |
| `veyro-gatekeeper` | Opus, fresh | **QUALIFIED** — self-reported `claude-opus-5`, definition body verbatim-confirmed | `RUNTIME_PROOF.md` |
| `veyro-test-author` | Sonnet | Not yet individually runtime-tested | — |

## Cross-cutting proofs (apply to all agents, not per-row)

- Custom agent registration mechanism: **PASS** (fresh-session proof, `SETTINGS_HOOK_RULE_PROOF.md`)
- Invalid/misnamed agent request fails closed, no silent substitution: **PASS**
- True Opus-infrastructure-unavailability -> `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`: **BLOCKED/UNVERIFIED**, cannot be safely forced

## Note

Only 2 of 9 agents have been individually invoked and self-report-verified so far (one Sonnet, one Opus) — sufficient to qualify the *mechanism* (named-agent routing works correctly end-to-end for both tiers), not to claim every individual role has been exercised. The remaining 7 rows will fill in as those roles are actually used for real MOD-000 work (scenario catalog review, code review, manual QA, security/performance review, test authoring).
