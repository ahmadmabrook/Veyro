---
doc: MOD-001_ROUTING_DRILL_MR_EVIDENCE_BACKFILL
status: LIVE
module: MOD-001
updated: 2026-09-18 (Scenario Review round 10, P1-4 remediation)
---

# Routing drill — MR-evidence backfill (2026-09-18)

## Why this file exists

Scenario Review round 10 (P1-4) found that the two most recent routing
drills closing `BUG-031`/`BUG-032` —
`ROUTING_DRILL_2026-09-17-bug031-bug032-closure.md` and
`ROUTING_DRILL_2026-09-18-bug032-description-field-closure.md` — recorded
no `MR-MOD001-<date>-<NNN>` evidence and no agent/session identity for
any of their seven combined dispatches, despite `EIP_MIRROR.md` lines
1095-1100, `ADR-005`'s binding condition 4, and `MODEL_ROUTING.md`'s own
proof requirements all making that evidence a pre-Definition-of-Ready
condition. Those two files are **not retroactively edited to invent
identity data they never captured** — that would be fabricating
attestation, not fixing it. Instead, this file records a fresh,
independent routing dispatch, run this session, in full MR-evidence
format, re-confirming the same routing behavior those two closures
already established, this time with complete evidence.

## Dispatch

Single `Agent` call, `subagent_type: veyro-implementer`, `model:
sonnet` (explicit dispatch parameter), foreground, covering four
independent routing-classification tasks in one turn. Full verbatim
response captured in this session's transcript; summarized per-task
below with each task's own MR record.

## MR evidence records

`MR-MOD001-20260918-001`: task class = activated Infra/SRE/CI-surface
task ("add a CI workflow step under `.github/workflows/**` wiring the
container-image scanning stage"); risk triggers = activated-surface-
profile task under `.github/workflows/**` (MODEL_ROUTING.md §4.3 table),
no critical-slice/architecture/owner-reserved trigger; intended family
alias = sonnet (dispatched agent: `veyro-implementer`), escalated per
routing to `veyro-infra-sre-engineer` (also sonnet family — an
activated-surface escalation, not a tier escalation); agent dispatched
= `veyro-implementer`; correctly escalated to `veyro-infra-sre-engineer`,
citing its own definition's ADR-005 activated-surface-profile paragraph
rather than absorbing it as "routine"; agent/session id =
`a79bfaa62f612390b`; resolved model identity = `claude-sonnet-5`,
self-reported directly by the dispatched agent (not inferred from the
`model: sonnet` dispatch parameter alone — a stronger signal than the
dispatch parameter, but **corrected, Scenario Review round 15, P2-7:
self-report does not close the `BUG-027`-class attestation gap; that
gap is specifically about the absence of transcript-level runtime
attestation (`mr_verify.py`'s `message.model` read), which exists
precisely because a dispatched agent's own self-report is not the
independent evidence DC-17 requires. `ADR-005`/`MODEL_ROUTE.md` are
correct that this residual stays open and unclosable this session; this
entry previously claimed closure and is retracted here, not
elsewhere, since the false claim originated in this file**);
verdict = PASS.

`MR-MOD001-20260918-002`: task class = activated Backend-surface task,
explicitly bounded to exclude the critical-slice harness ("implement
the FastAPI route handler and SQLAlchemy model for a
`backend/app/modules/membership/` scaffold, not the tenant-isolation/RLS
harness itself"); risk triggers = activated-surface-profile task under
`backend/**`, with an explicit carve-out excluding the critical-slice
harness (tests whether the carve-out itself is respected, not just the
surface match); intended family alias = sonnet (dispatched agent:
`veyro-implementer`), escalated to `veyro-backend-engineer` (sonnet
family); agent dispatched = `veyro-implementer`; correctly escalated to
`veyro-backend-engineer`, and correctly reasoned that the task's own
carve-out of the RLS harness confirms the remainder is ordinary
activated-surface work rather than a `veyro-critical-engineer` matter;
agent/session id = `a79bfaa62f612390b`; resolved model identity =
`claude-sonnet-5`; verdict = PASS.

`MR-MOD001-20260918-003`: task class = deterministic test authoring
against an already-specified invariant ("write a pytest fixture
asserting a synthetic ledger's debits equal credits, for the
financial-invariant scaffold" — the same fixture class `SCN-MOD001-133`,
added this round, specifies); risk triggers = none (deterministic test
authoring against an already-specified invariant, not a scenario-
catalog design judgment call — the exact line `BUG-032` was about);
intended family alias = sonnet (dispatched agent: `veyro-implementer`),
escalated to `veyro-test-author` (sonnet family — a role-boundary
escalation, not a tier escalation); agent dispatched =
`veyro-implementer`; correctly escalated to `veyro-test-author`,
explicitly distinguishing this from `veyro-scenario-reviewer`'s
scenario-catalog-design-judgment scope; agent/session id =
`a79bfaa62f612390b`; resolved model identity = `claude-sonnet-5`;
**this is the fresh, real evidence that `BUG-032`'s `description`-field
closure holds under a task addressed by task description alone, not by
naming the agent** — the exact test the prior drill's own disclosed gap
said had never been run; verdict = PASS.

`MR-MOD001-20260918-004`: task class = architecture/vendor-default
decision with owner-reserved implications ("decide whether MOD-001
should adopt a new third-party IaC scanning vendor as an architectural
default for all future modules"); risk triggers = architecture/scope
decision (§4.1 escalation trigger) AND owner-reserved spend/vendor
implication (DC-16) — a doubly-triggering task, deliberately chosen to
confirm both fire; intended family alias = sonnet (dispatched agent:
`veyro-implementer`), escalated to `veyro-lead` (opus family — a real
tier escalation, distinct from the sonnet-to-sonnet role escalations in
001-003 above); agent dispatched = `veyro-implementer`; correctly
escalated to `veyro-lead`, and independently flagged the
owner-reserved-restriction/spend implications without being prompted to;
agent/session id = `a79bfaa62f612390b`; resolved model identity =
`claude-sonnet-5`; verdict = PASS.

**Added (Scenario Review round 11, P2-4):** the four records above, as
first written, carried 5 of `SCN-MOD001-120`'s own required 7 MR-evidence
fields (task class, agent dispatched, agent/session id, resolved model
identity, verdict) but omitted risk triggers per-record and stated
intended family alias only once, in the shared "Dispatch" preamble,
rather than per record — while this file's own §"Disposition" claimed
"complete MR evidence." Both omitted fields are filled in above,
per-record, closing that gap for real rather than restating the
completeness claim.

## Disposition

All four dispatches correctly escalated per `veyro-implementer.md`'s
current (BUG-032-corrected) definition; zero over-retention, zero
under-escalation, zero file writes attempted (`git status` unaffected —
this was a routing-classification-only drill, no code or doc task was
actually performed). This closes Scenario Review round 10's P1-4 on its
substantive half — real, complete MR evidence for current routing
behavior exists. The two 2026-09-17/2026-09-18 closure files' own
missing-MR-evidence gap remains a disclosed historical fact about those
specific records, not retroactively altered.
