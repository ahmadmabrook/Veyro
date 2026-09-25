---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---
<!-- Target path once applied: .claude/rules/infra/secrets.md -->

# Rule: Infra/SRE — Secrets Externalization Baseline (`infra/**` binding)

Authored per DC-21 (EIP §4.3/Appendix H — Infra/SRE/CI profile) and
Appendix H.3's content standard, grounded in EIP Appendix H.3's Infra/SRE
rule-content summary (see `iac.md` for the full quoted text; this file
covers the "secrets externalized" portion specifically).

## Why this rule exists

MOD-001's environment-boundary plan
(`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §2) already names a
distinct secrets mechanism per tier — a local `.env` file, GitHub Actions
repository/environment secrets for QA, and a separate GitHub Actions
environment-secret scope for staging specifically so that "a QA
credential leak cannot reach staging." MOD-001's CI plan (§3) also names
"SAST / dependency / secret / container / IaC scanning" as a blocking
CI gate. Neither of those is self-enforcing without a rule binding
agent behavior to them — an agent authoring config, fixtures, or
documentation could commit a real-looking secret value without the CI
scanner ever running against that specific change, or could bridge two
tiers' secret scopes for convenience.

## Required controls

1. **No secret is ever committed to the repository, in any form.** This
   covers credentials, API keys, tokens, connection strings with
   embedded credentials, private keys, and signing keys — whether in
   source, config, fixtures, test data, or documentation. This is the
   constraint the CI secret-scanning gate
   (`IMPLEMENTATION.md` §3's "SAST / dependency / secret / container /
   IaC scanning" row, blocking) exists to catch mechanically; this rule
   is the corresponding authoring-time constraint an agent must not rely
   on the scanner alone to enforce. A fixture or example that needs a
   credential-shaped value uses an explicitly-fake, clearly-labeled
   placeholder (e.g. `EXAMPLE_NOT_A_REAL_KEY`), never a plausible-looking
   real-shaped value.
2. **Per-environment secret scope is isolated — a QA credential must
   never reach staging, and vice versa.** Per
   `IMPLEMENTATION.md` §2's own "Secrets mechanism" row: QA uses "GitHub
   Actions repository/environment secrets"; staging uses "GitHub Actions
   environment secrets, distinct environment scope from QA (so a QA
   credential leak cannot reach staging)." No workflow job, script, or
   config file reads a secret from one tier's scope while running
   against another tier's target. No secret value is duplicated across
   tier-scoped GitHub Actions environments as a matter of convenience —
   each tier provisions and rotates its own.
3. **Local secrets follow the gitignored `.env` convention, developer-
   managed, never committed.** Per `IMPLEMENTATION.md` §2's "Configuration
   source" and "Secrets mechanism" rows: LOCAL uses `.env.local`
   (gitignored) plus `infra/environments/local/` defaults. This file is
   never added to git (verify against the repository's existing
   `.gitignore`, extending it rather than replacing it), never
   referenced by a committed CI workflow (CI has its own GitHub Actions
   secret scope per control 2), and never copied into a fixture or
   evidence file that itself gets committed.

## Fail-closed rule

Any change that would commit a credential-shaped value, bridge two
environment tiers' secret scopes, or reference an uncommitted local
`.env` file from a committed CI workflow does not merge. If it is
unclear whether a given value is a real secret or a synthetic
placeholder, treat it as a real secret and do not commit it.
