---
doc: MOD-001_RUNBOOK
status: LIVE — PLAN ONLY (no implementation exists to drill against yet)
module: MOD-001
updated: 2026-09-15 (added, Scenario Review round 4, P1-6)
---

# MOD-001 — RUNBOOK: RB-GOV-01

Appendix I (`EIP_MIRROR.md` lines 22386-22394) maps `RB-GOV-01` to
MOD-001: "Bad deployment/schema/config release rollback." The EIP
card's own Required-outputs text requires "the module RUNBOOK.md where
a domain is owned" (line 4180-4181) — MOD-001 owns GOV-01 and this
runbook.

## Trigger

A deployed release (application code, database schema, or
configuration) is found to be bad after promotion — a failing SLO
guardrail, a migration that broke a downstream consumer, or a
configuration change with an unintended effect.

## Procedure

1. **Detect.** The canary/SLO-monitoring mechanism (GOV-01-R05,
   `IMPLEMENTATION.md` §3's canary/rollout stage) flags the guardrail
   breach, or an operator flags it manually.
2. **Halt.** Stop further rollout percentage increase immediately.
3. **Decide: rollback vs. forward-fix.** For a schema change, prefer
   forward-fix (per TSD §24.2's own expand/contract philosophy — a
   schema rollback is often more dangerous than fixing forward) unless
   the bad change is purely application-code, in which case a direct
   rollback to the prior release is safe.
4. **Execute.** Application rollback: redeploy the prior signed
   artifact. Schema forward-fix: apply a new, additive migration
   correcting the issue — never a destructive rollback of an already-
   promoted schema change.
5. **Reconcile.** Confirm no data was written in a now-invalid shape
   during the bad window; run the reconciliation check against the
   affected tables/aggregates.
6. **Record evidence** (see field set below).
7. **Follow-up.** Assign an owner for the post-incident fix and any
   process gap that let the bad release promote.

## Evidence-contract fields (per TSD's own text, `EIP_MIRROR.md` line
22386-22394)

Every invocation of this runbook records:

- **Affected tenant/scope** — which tenant(s) or "all" were exposed to
  the bad release.
- **Command/aggregate version** — the exact command/event version
  involved, for aggregates using optimistic concurrency (DOM-002).
- **Authoritative rows** — which rows/records were touched during the
  bad window.
- **Outbox/inbox/DLQ/provider state** — where applicable, the state of
  any in-flight events or provider dispatches at the time of rollback.
- **Reconciliation result** — the outcome of step 5 above.
- **Repair/correction reference** — a link to the forward-fix migration
  or rollback commit.
- **Owner and follow-up action** — who owns the post-incident fix.

## Drill status

**Not yet drilled for real** — implementation has not started. The
synthetic drill this runbook will be exercised against is
`SCN-MOD001-058` (release/rollback drill, Blocker, Manual — 
`veyro-manual-qa`). This document is the procedure that drill executes
against, not a substitute for actually running it.
