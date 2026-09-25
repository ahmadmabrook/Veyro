---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---

<!-- Target path once applied: .claude/rules/infra/release.md -->

# Rule: Infra/SRE — Release, Rollback/Canary, and Cost Baseline (`infra/**` binding)

Authored per DC-21 (EIP §4.3/Appendix H — Infra/SRE/CI profile) and
Appendix H.3's content standard, grounded in EIP Appendix H.3's Infra/SRE
rule-content summary (see `iac.md` for the full quoted text; this file
covers the "rollback/canary controls, cost tags/budgets... and release
readiness" portions specifically).

## Why this rule exists

MOD-001 owns GOV-01-R05 (progressive delivery, canary, feature flags,
automated rollback, release evidence — `REQUIREMENTS.md` GOV-01-R05) and
its own security-implications text is explicit that a rollback trigger
which can be called arbitrarily "would itself be a DoS vector." MOD-001's
plan (`IMPLEMENTATION.md` §3, "Canary/rollout with SLO/guardrail
monitoring" row) already states the bypass-protection convention as
"Automated rollback trigger tied to real guardrail signals, not a
manually-callable endpoint" — this rule makes that binding rather than
planning-document prose, and adds the cost/budget and release-evidence
constraints Appendix H.3 also names, which the implementation plan does
not yet state as a standing rule anywhere.

## Required controls

1. **Automated rollback is tied to genuine SLO/guardrail signals — never
   a manually or externally callable endpoint.** Per GOV-01-R05's own
   security-implications text, an arbitrarily-triggerable rollback is a
   denial-of-service vector: an attacker (or a mistaken caller) could
   force repeated rollbacks against a healthy release. The rollback
   mechanism's only trigger path is the pipeline's own SLO/guardrail
   evaluation crossing a pre-declared threshold — never an
   unauthenticated or convenience HTTP endpoint, CLI flag, webhook, or
   manual override callable by a human operator or external system. This
   matches `IMPLEMENTATION.md` §3's Canary row exactly: "Automated
   rollback trigger tied to real guardrail signals, not a
   manually-callable endpoint" — no carve-out of any kind, including an
   audited one, since no cited source authorizes one. This is the same
   security constraint as observability's SLO-guardrail requirement
   (`observability.md` control 2), stated here as a release-control
   boundary specifically: the rollback surface's attack profile, not
   just its evidence quality.
2. **Canary/rollout mechanics stay inside LOCAL/QA/staging — never real
   production traffic.** Per `IMPLEMENTATION.md` §2's own environment
   table and GOV-01-R05's "Owner/external gates" text: "any real
   production canary/rollout remains DC-16 owner-reserved (no Production
   promotion). MOD-001's own proof is local/QA-environment only." No
   canary/rollout drill, real or scripted, targets a production
   endpoint or real user traffic without a recorded `OWN-<NNN>` entry in
   `OWNER_APPROVALS.md` — which, per DC-16's absolute restriction, would
   not be grantable for a Production-promotion action regardless.
3. **Any paid CI/infra capacity requires a recorded `OWNER_APPROVALS.md`
   reference before activation — never assumed or silently provisioned.**
   Per `REQUIREMENTS.md`'s repeated "Owner/external gates" text across
   GOV-01-R03/R04/R07 (a paid SAST SaaS, a paid code-signing CA, a paid
   macOS CI runner tier, a real Apple/Google developer account are all
   named examples), any infra or CI capacity that carries a cost —
   whether a paid GitHub Actions runner tier, a paid third-party
   scanning/monitoring SaaS, or a paid cloud resource of any kind —
   requires an `OWN-<NNN>` entry in
   `knowledge/00-System/OWNER_APPROVALS.md` naming the specific service
   and cost, recorded *before* the service is activated, per DC-16's
   no-paid-services-without-approval restriction. Default to free/
   open-source/already-available tooling first (`IMPLEMENTATION.md` §7's
   own default), and treat a paid-tier requirement as a stop-and-report
   condition, not something to provision and flag afterward.
4. **Every promotion produces the full `RB-GOV-01` release-evidence field
   set — not a partial or best-effort subset.** Per GOV-01-R05's
   implementation obligations, a release-evidence record captures what
   got deployed, from what commit, with what test evidence, signed how
   — and per `RB-GOV-01`'s own evidence-contract text (see
   `observability.md` control 3 for the full field list), every
   applicable field is populated for every promotion event, real or
   synthetic. A promotion that completes without a corresponding
   evidence record is not release-complete, regardless of whether the
   underlying deploy mechanism succeeded — this mirrors GOV-01-R04's
   acceptance criterion that no CI gate is bypassable, applied to the
   release-evidence step specifically.

## Fail-closed rule

A canary/rollback mechanism with a manually-callable trigger, a
promotion targeting a production or unapproved-real-traffic destination,
a paid-capacity activation with no recorded owner approval, or a
promotion with an incomplete evidence record does not ship. A session
that reaches any of these conditions reports `BLOCKED:
OWNER_APPROVAL_REQUIRED` (for the DC-16-governed cases) or fixes the
evidence gap before declaring the promotion complete — never proceeds
and backfills the record afterward.
