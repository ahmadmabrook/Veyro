<!-- Target path once applied: .claude/rules/infra/iac.md -->

# Rule: Infra/SRE — Infrastructure-as-Code (IaC) Baseline (`infra/**` binding)

Authored per DC-21 (EIP §4.3/Appendix H — Infra/SRE/CI profile) and
Appendix H.3's content standard ("concrete, testable constraints... avoid
overengineering"), grounded in EIP Appendix H.3's Infra/SRE rule-content
summary: "reviewable infrastructure-as-code, least privilege,
externalized secrets, reproducible environments, rollback/canary
controls, cost tags/budgets, OpenTelemetry/SLO/DR evidence and release
readiness; no Production action or paid capacity commitment may execute
without the approvals required by DC-16." This file covers the
reviewable-IaC, least-privilege, and reproducible-environment portions;
secrets live in `secrets.md`, observability/DR in `observability.md`,
rollback/canary/cost/release-evidence in `release.md`.

## Why this rule exists

MOD-001 (`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §1-§2) plans
`infra/environments/{local,qa,staging}/` as the committed source of
truth for every non-local environment, with CI (`IMPLEMENTATION.md` §3)
running "the same validators run locally" as its own bypass-protection
convention. Nothing about that plan is self-enforcing without a rule
that binds it — an agent could apply a config change directly against a
QA/staging target, or scaffold a `production/` tree, without anything
stopping it short of this file.

## Required controls for any `infra/**` or CI-workflow change

1. **No environment configuration is applied anywhere without first
   being committed and reviewed.** Every change to
   `infra/environments/{local,qa,staging}/` or `.github/workflows/**`
   lands as a reviewed commit before it takes effect anywhere. There is
   no direct-apply path against a QA or staging target that bypasses the
   committed config — matches `IMPLEMENTATION.md` §2's own "Configuration
   source" row (`infra/environments/<tier>/` is the named source for
   every tier) and §3's "Local equivalent" column, which requires the
   same validators to run locally as run in CI.
2. **CI/deploy credentials are least-privilege and tier-scoped.** A
   credential scoped to one environment tier (LOCAL/QA/STAGING) is never
   reused across tiers — matches `IMPLEMENTATION.md` §2's own "Secrets
   mechanism" row, which requires STAGING to use "a separate secret
   scope from QA (so a QA credential leak cannot reach staging)." No
   CI/deploy credential is granted broader scope (e.g. repo-admin,
   org-admin, or a superuser database role) than the specific
   environment-tier action it performs requires. A migration credential
   in particular runs under a scoped role, never a superuser/owner role
   (ties to GOV-01-R06's own security-implications text).
3. **Each environment tier is fully defined by its own committed config
   — no manual, undocumented drift.** LOCAL, QA, and STAGING are each
   reproducible from `infra/environments/<tier>/` plus (for LOCAL only)
   the developer's own gitignored `.env.local` — see `secrets.md` for
   the secrets half of this boundary. A manual change made directly
   against a running QA or staging environment, without a corresponding
   committed config change, is a drift defect, not an accepted
   convenience — matches `IMPLEMENTATION.md` §2's "Reset/seed policy" row
   (QA resets every CI run; staging resets on a scheduled cadence),
   which only holds if the environment's definition is fully
   reconstructible from committed source.
4. **No `infra/environments/production/` directory, no production secret
   scope, and no production deployment workflow exist without an
   explicit `OWNER_APPROVALS.md` entry.** This is DC-16's owner-reserved
   restriction (no deploys/promotion to Production) applied to this
   surface directly, and it is this rule's single most load-bearing
   constraint. Concretely: no directory named `production` (or an
   equivalent alias) under `infra/environments/`; no GitHub Actions
   environment, secret scope, or workflow job targeting a production
   deployment target; no IaC module, Terraform/Pulumi/CloudFormation
   stack, or equivalent provisioning a production-tier resource. This
   holds regardless of whether the action would involve real spend —
   DC-16's Production-promotion restriction is independent of, and
   additional to, its no-paid-services restriction. Creating any of the
   above requires a recorded `OWN-<NNN>` entry in
   `knowledge/00-System/OWNER_APPROVALS.md` naming the specific
   production action, made *before* the directory/config/workflow is
   created — not backfilled after the fact.

## Fail-closed rule

An `infra/**` or CI-workflow change that cannot satisfy all four
controls above does not merge. A session that reaches a point where a
production directory, secret scope, or deployment workflow appears to be
required reports `BLOCKED: OWNER_APPROVAL_REQUIRED` naming DC-16, rather
than scaffolding it and waiting for review to catch it.
