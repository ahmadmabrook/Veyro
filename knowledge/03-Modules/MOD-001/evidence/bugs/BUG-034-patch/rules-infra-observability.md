<!-- Target path once applied: .claude/rules/infra/observability.md -->

# Rule: Infra/SRE — Observability, SLO, and DR-Evidence Baseline (`infra/**` binding)

Authored per DC-21 (EIP §4.3/Appendix H — Infra/SRE/CI profile) and
Appendix H.3's content standard, grounded in EIP Appendix H.3's Infra/SRE
rule-content summary (see `iac.md` for the full quoted text; this file
covers the "OpenTelemetry/SLO/DR evidence" portion specifically).

## Why this rule exists

MOD-001's environment plan
(`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §2) names staging's
observability obligation as "the canary/SLO-guardrail monitoring
GOV-01-R05 requires," and `REQUIREMENTS.md` GOV-01-R05's acceptance
criteria require "a deliberately-bad synthetic release triggers automated
rollback" with the trigger "tied to genuine SLO/guardrail signals, not an
arbitrary external call." MOD-001 also owns `RB-GOV-01`
(`REQUIREMENTS.md` GOV-01-R05, `EIP_MIRROR.md` lines 22386-22394), the
rollback runbook, with a named evidence-contract field set. None of this
is self-enforcing without a rule binding the CI/infra tooling itself to
produce structured, inspectable evidence rather than prose claims.

## Required controls

1. **CI/infra tooling itself emits structured, machine-parseable output
   — not prose-only pass/fail claims.** Every validator, scanner, and
   pipeline stage MOD-001 builds
   (`IMPLEMENTATION.md` §3's full gate table) produces a named,
   inspectable failure-evidence artifact — a report, a log, or an
   artifact file — as that table's own "Failure evidence" column
   already specifies per stage. A gate that only prints a bare pass/fail
   with no named violation type or offending file/line does not meet
   this bar; the standard is the same one `IMPLEMENTATION.md` §3 already
   holds every row to, restated here as a binding constraint on new
   tooling rather than left as planning-document prose alone. Where a
   CI stage or infra script is itself long-running or has multiple
   internal steps, its own logs and any traces it emits follow structured
   (not free-text-only) log conventions, so a later OpenTelemetry-based
   consumer could parse them without inventing a new format per tool.
2. **Staging's canary/rollout carries real SLO-guardrail monitoring
   evidence, not a manual eyeball check.** Per GOV-01-R05's acceptance
   criteria, the automated-rollback trigger is tied to a "genuine
   SLO/guardrail signal" — a named, pre-declared threshold (e.g. error
   rate, latency percentile, or an equivalent synthetic-fixture
   stand-in, since MOD-001 precedes real product traffic) evaluated by
   the pipeline itself, not a person watching a dashboard and deciding.
   The canary/rollout drill (`IMPLEMENTATION.md` §2's "Rollback" row;
   GOV-01-R05's "Evidence obligations") produces a durable record of
   what signal fired, what threshold it crossed, and what action
   resulted — this record is what closes GOV-01-R05's acceptance
   criterion, not a narrative description of the drill having happened.
3. **Every rollback/DR action produces `RB-GOV-01` evidence-contract
   fields, real or synthetic.** Per `REQUIREMENTS.md`'s own text
   (`EIP_MIRROR.md` lines 22386-22394), the required field set is:
   affected tenant/scope, command/aggregate version, authoritative rows,
   outbox/inbox/DLQ/provider state (where applicable), reconciliation
   result, repair/correction reference, and owner/follow-up action. A
   rollback drill — synthetic, per `IMPLEMENTATION.md` §9's own
   module-level rollback-strategy text, since no production state exists
   to roll back — that does not populate all applicable fields of this
   set has not actually closed the runbook's evidence obligation, even
   if the underlying rollback mechanism worked.

## Fail-closed rule

A CI/infra tool, canary/rollout mechanism, or rollback drill that cannot
produce the structured evidence required above does not count as
satisfying GOV-01-R05 or `RB-GOV-01`, regardless of whether the
underlying action succeeded. A session that cannot produce the evidence
reports the gap honestly rather than describing the action as complete.
