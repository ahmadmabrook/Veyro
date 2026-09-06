---
doc: BUG-012
status: CLOSED (2026-09-06) — owner decision recorded, OWN-003
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-01); re-confirmed genuine and ongoing by an independent Phase 7 re-review
severity: P1
---

# BUG-012: The orchestrating session that has run MOD-000 executed Opus-designated work on Sonnet, unattested

## What is wrong

`knowledge/00-System/MODEL_ROUTING.md` assigns "Architecture, ADRs,
module planning, dependency/risk decisions" to `veyro-lead` → **Opus**
(DC-17: "Every assurance-tier action must carry runtime model-proof
evidence... No silent downgrade"). The top-level interactive session that
has been driving MOD-000 — authoring `ADR-002` and `ADR-003`, making the
Phase 6 scope determination, declaring Phase 1/2/3/4/6 gate verdicts, and
self-verifying P1 closure across multiple Phase 5 review rounds — is not
a `veyro-lead` subagent invocation. It is the raw orchestrating session
itself, and it has never been technically attested.

## Real evidence (technical, not self-report)

`mr_verify.py` (after the Phase 7 SEC-09 fix — see BUG-015 — which
removed a false-positive "inconsistent model" diagnosis caused by the
harness's own `<synthetic>` rate-limit sentinel) run against the actual
main-session transcript:

```
python3 knowledge/05-QA/tools/mr_verify.py \
  ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/1e9c94e4-62b2-4f02-98aa-f8f853e8b232.jsonl \
  opus "main-orchestrating-session-mod000"
```

Result (`knowledge/03-Modules/MOD-000/evidence/security/MAIN_SESSION_MR_VERIFY_2026-09-06.json`):

```json
{
  "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
  "reason": "Resolved model 'claude-sonnet-5' does not match required tier 'opus' ... for main-orchestrating-session-mod000.",
  "models_observed": ["claude-sonnet-5"],
  "expected_tier": "opus"
}
```

13,438 lines, 100% `claude-sonnet-5` across every assistant turn — no
substitution, no fallback, no inconsistency. The tool worked correctly
and fast (streamed, did not need to hold the 26.4 MB transcript in
memory — see BUG-015/PERF-03). The delegated Opus subagent reviews this
session spawned (veyro-code-reviewer, veyro-manual-qa,
veyro-security-reviewer, veyro-performance-reviewer, etc.) are real and
independently attested Opus — this finding does not dispute any of their
verdicts. It is specifically about the tier of the session that
delegated to them and made the calls `MODEL_ROUTING.md` reserves for
`veyro-lead`.

## Why this matters

This is precisely the failure class the model-routing control exists to
catch (DC-17), and every one of the five Phase 5 review rounds — which
each found something real — was pointed at delegated subagents and never
at the delegating session itself.

## What this is NOT

Not a claim that any review work in this project was fabricated. Not a
claim that the ADRs, gate verdicts, or remediation decisions themselves
were wrong on the merits — a Phase 5/6/7 independent Opus reviewer has
re-verified the substance of nearly all of them. This is a claim that one
whole tier of decision-making (architecture/ADR/gate-declaration/
self-verification calls) ran without the attestation `MODEL_ROUTING.md`
requires for that tier, for the entire module to date.

## Why this is not self-remediable

Which model tier the orchestrating session runs as is not a repo file
this agent can edit — it is set by which model the user/owner invokes
Claude Code with. This requires an owner decision, structurally identical
to how BUG-010/ADR-003 (Notion connector scope) was handled: state the
real evidence, present the options, do not silently resolve it either
direction.

## Options for the owner

1. **Formally accept Sonnet-tier orchestration as the durable operating
   model**, on the basis that all Opus-reserved *judgment* work (ADR
   authorship review, architecture decisions, gate certification,
   scenario/code review) is delegated to fresh-context Opus subagents
   invoked BY the orchestrating session, and the orchestrating session's
   own role is coordination/execution, not the reserved judgment itself
   — recorded as a row in `knowledge/00-System/OWNER_APPROVALS.md` and a
   corresponding correction to `MODEL_ROUTING.md`'s role table to state
   this explicitly (today it does not distinguish "the session that
   calls veyro-lead" from "veyro-lead itself").
2. **Require the orchestrating/lead session itself to run on Opus** for
   any turn where it is making an architecture/ADR/gate-verdict-class
   decision directly rather than delegating — a stricter reading of
   DC-17, with real cost/workflow implications the owner should weigh.

## Independent re-confirmation (2026-09-06)

A second, distinct fresh-context `veyro-security-reviewer` re-review
independently re-parsed the main-session transcript (14,100 lines, 3,528
assistant turns at that point) and confirmed 100% `claude-sonnet-5`,
zero Opus turns — genuine and, notably, *ongoing*: the reviewer observed
the orchestrating session rewriting `CURRENT_HANDOFF.md` with new
gate-verdict text while the re-review itself was running, which it
correctly flagged as exactly the class of unattested action this bug
describes, happening in real time. `ADR-004` was confirmed to frame the
decision honestly, presenting both options without self-resolving
either.

## Resolution (2026-09-06)

The owner was asked directly which option to adopt and chose
**Option A: accept Sonnet-tier orchestration**, with every Opus-reserved
judgment call delegated to a fresh-context Opus subagent, never decided
unilaterally by the orchestrating session on its own authority. Recorded
as `OWN-003` in `knowledge/00-System/OWNER_APPROVALS.md`.
`MODEL_ROUTING.md` now states this distinction explicitly (see its new
"Orchestrating-session tier vs. delegated-role tier" section). `ADR-004`
updated to DECIDED.

**Not done as part of this closure:** a retroactive line-by-line audit
of every past ADR/gate-verdict decision in this project for whether it
was genuinely delegated-then-transcribed vs. decided directly on
Sonnet's own authority. Disclosed as a known limitation, not attempted
this chunk — flagged in `ADR-004`.

## Certification impact

No longer blocks Phase 7 PASS on its own — closed via a real owner
decision, not self-waived. `BUG-013`'s residual case is the one
remaining open item blocking Phase 7.

## Affected

`knowledge/00-System/MODEL_ROUTING.md`, `knowledge/00-System/
DEVELOPMENT_CONSTITUTION.md` (DC-17), all durable records authored
directly by the orchestrating session across MOD-000 to date (ADR-002,
ADR-003, and every gate-verdict declaration in `CURRENT_STATE.md`/
`CURRENT_HANDOFF.md`). See also `knowledge/04-Decisions/
ADR-004-orchestrating-session-model-tier.md` for the formal decision
record once the owner responds.
