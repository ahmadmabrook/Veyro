---
doc: MOD-001_IMPLEMENTATION
status: LIVE — PLAN ONLY, NOT YET IMPLEMENTED
module: MOD-001
updated: 2026-09-18 (Scenario Review round 12 — gate 7's carve-out enumerated (was open-ended "etc."); gate 1's elevated-role/nullable-tenant_id and gate 6's identical-command-inventory sub-clauses fixtured; the pipeline-table gate count fixed from "6" to "7" with gate 7's own missing row added; validate_toolchain_matrix.py given a CI-stage row; this line's own provenance corrected, having gone stale at "round 9" through rounds 10 and 11's real edits to this file)
---

# MOD-001 — Implementation Plan (repository, environments, CI/CD, architecture gates)

**This is a plan. No code, repo structure, or CI configuration described
below has been created yet.** Implementation begins in a later turn,
after Definition of Ready is met (see `STATUS.md`).

Stack references below are drawn from TSD's own "Reference Choice"
technology table (`TSD_MIRROR.md` lines 970-1034), which the TSD itself
labels non-mandatory ("not a mandated vendor unless explicitly stated. A
reviewer may recommend alternatives if they preserve the contracts,
SLOs and operational model") — this plan follows the reference choices
rather than inventing an alternative stack, since no reason to deviate
has been found.

## 1. Repository topology

Derived from TSD's reference stack + Appendix H.2's `.claude/` layout
(`EIP_MIRROR.md` lines 20646-20685) + TSD's "modular monolith" backend
guidance (`TSD_MIRROR.md` line 513: "Start with a modular monolith").

```
Veyro/
├── .claude/                        # already exists (MOD-000)
│   ├── agents/                     # already exists. **Corrected (Scenario
│   │                               #   Review round 1, P0-3/P1-9 → ADR-005):
│   │                               #   "adds no new agents" was wrong.**
│   │                               #   MOD-001 requires 3 new agents:
│   │                               #   veyro-critical-engineer (Opus,
│   │                               #   bounded to 3 critical slices),
│   │                               #   veyro-infra-sre-engineer (Sonnet),
│   │                               #   veyro-backend-engineer (Sonnet,
│   │                               #   bounded). All 3 registered and
│   │                               #   routable (BUG-029/030 closed;
│   │                               #   BUG-031 CLOSED 2026-09-17 — owner
│   │                               #   applied the escalation patch to
│   │                               #   veyro-implementer.md, commit
│   │                               #   0afa609, independently verified
│   │                               #   byte-for-byte and by a 6-case
│   │                               #   routing drill proving real
│   │                               #   escalation to all 3, plus
│   │                               #   veyro-test-author for BUG-032).
│   ├── rules/                      # already exists (4 files); MOD-001
│   │                               #   scaffolds the 11 Appendix H.2 families
│   │                               #   as directories, but **corrected (same
│   │                               #   ADR-005 finding): the backend/ and
│   │                               #   infra/ families need REAL content
│   │                               #   (matching the 2 activated §4.3
│   │                               #   profiles), not empty scaffolds — the
│   │                               #   other 9 stay empty/ready-to-populate**
│   │                               #   until their own owning module claims
│   │                               #   them
│   └── skills/                     # does not exist yet (BUG-004, MOD-000);
│                                   #   MOD-001 creates it only if a real
│                                   #   need is found during implementation,
│                                   #   per BUG-004's own precedent — not
│                                   #   speculatively
├── knowledge/                      # already exists (MOD-000) — unchanged
├── backend/                        # NEW — Python 3.13+/FastAPI/Pydantic/
│   ├── app/                        #   SQLAlchemy 2/Alembic, modular
│   │   ├── modules/                #   monolith: one sub-package per
│   │   │   ├── _shared/            #   owned domain (empty until MOD-002+
│   │   │   ├── membership/         #   claims a domain); _shared/ holds
│   │   │   ├── booking/            #   **six named domain scaffolds added,
│   │   │   ├── payment/            #   Scenario Review round 10, P0-2 —
│   │   │   ├── ledger/             #   GOV-01-R02's own text commits
│   │   │   ├── pos/                #   MOD-001 to "documented, empty-but-
│   │   │   └── access/             #   wired suite scaffolds for
│   │   │                           #   membership/booking/payment/ledger/
│   │   │                           #   POS/access", which this topology
│   │   │                           #   had never actually added — each of
│   │   │                           #   the six is `__init__.py` + a single
│   │   │                           #   `tests/test_scaffold_live.py`
│   │   │                           #   placeholder fixture proving the
│   │   │                           #   harness (not product behavior) is
│   │   │                           #   live, owned by its future module
│   │   │                           #   (MOD-004/MOD-015+/MOD-019+/MOD-021+)
│   │   │                           #   until claimed, per §4's boundary**
│   │   ├── contracts/               #   claims a domain); _shared/ holds
│   │   ├── main.py                 #   cross-cutting (auth middleware
│   │   ├── version_negotiation.py  #   scaffold, tenant-context resolver)
│   │   │                           #   NEW, §12 (GOV-01-R07, round 7,
│   │   │                           #   corrected round 8 P1-3 — this
│   │   │                           #   file was named in §12's prose but
│   │   │                           #   never added here) — real backend
│   │   │                           #   min-version/optional-vs-forced-
│   │   │                           #   update/kill-switch enforcement,
│   │   │                           #   proven by SCN-MOD001-115
│   │   └── crash_remote_config_intake.py # NEW, §12 (GOV-01-R07, round
│   │                                #   7, corrected round 8 P1-3) —
│   │                                #   synthetic crash-report/remote-
│   │                                #   config intake endpoints,
│   │                                #   proven by SCN-MOD001-117
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── component/
│   │   ├── integration/
│   │   └── contract/
│   │       └── test_financial_invariant_scaffold.py # NEW, Scenario
│   │           #   Review round 10 P0-2 — a placeholder double-entry
│   │           #   invariant fixture (synthetic ledger rows, asserts
│   │           #   debits==credits) proving the financial-invariant
│   │           #   test harness itself is live; no real payment/ledger
│   │           #   logic, per GOV-01-R02's own scaffold-not-product rule
│   ├── pyproject.toml
│   └── Dockerfile                  # NEW, Scenario Review round 11, P1-3 —
│                                    #   minimal disposable build scaffold
│                                    #   (no application logic, no base-
│                                    #   image pin beyond a placeholder tag)
│                                    #   so `SCN-MOD001-135`'s container-
│                                    #   image scan has a real committed
│                                    #   target, same precedent as round
│                                    #   10's Gradle stubs for SCN-127(a);
│                                    #   `docker compose`/an equivalent was
│                                    #   already this plan's assumed local
│                                    #   deployment mechanism (§2 above), so
│                                    #   this is not a new tool decision
├── admin-web/                      # NEW — TypeScript/React/Next.js,
│   ├── app/                        #   empty shell; real screens arrive
│   ├── components/                 #   with the module that owns them
│   │                               #   (MOD-001 owns none — §4 of
│   │                               #   REQUIREMENTS.md)
│   └── tests/
├── frontdesk-web/                  # NEW — Next.js PWA + Veyro Edge Bridge
│   └── (same shape as admin-web)   #   integration point, empty shell
├── mobile/                         # NEW — Kotlin Multiplatform + Compose
│   ├── shared/                     #   Multiplatform; commonMain holds
│   │   ├── src/commonMain/         #   shared logic/UI, iosMain/androidMain
│   │   └── build.gradle.kts        #   NEW, Scenario Review round 10 P1-2 —
│   │                               #   real pinned Kotlin/KMP/Gradle-plugin
│   │                               #   version stub (no application logic),
│   │                               #   the actual "committed Gradle config"
│   │                               #   SCN-127(a) diffs the matrix against;
│   │                               #   without this file the matrix had
│   │                               #   nothing real to diverge from
│   ├── androidApp/                 #   hold native adapters only
│   │   └── build.gradle.kts        #   NEW, round 10 P1-2 — real pinned
│   │                               #   AGP/Gradle-wrapper version stub
│   ├── iosApp/
│   ├── TOOLCHAIN_MATRIX.md         # NEW, §12 (GOV-01-R07) — pinned
│   │                               #   Kotlin/KMP/Compose/Gradle/Xcode/AGP
│   │                               #   compatibility matrix
│   └── RELEASE_POLICY.md           # NEW, §12 (GOV-01-R07) — min-supported-
│                                   #   version/forced-update/kill-switch
│                                   #   policy, crash-monitoring/remote-
│                                   #   config integration points
├── RELEASE_TRAIN.md                # NEW, §12 (GOV-01-R08) — release-train
│                                   #   cadence + changelog convention
├── contracts/                      # NEW — cross-service shared schemas:
│   ├── openapi/                    #   OpenAPI specs (permission lint,
│   ├── events/                     #   screen contract lint inputs);
│   │   └── asyncapi/               #   AsyncAPI/JSON-Schema event registry
│   ├── screen-contracts.yaml       #   (event contract lint gate, EVT-001);
│   │                               #   generated by MOD-001's own tooling,
│   │                               #   contains an explicit empty MOD-001
│   │                               #   entry (REQUIREMENTS.md §4)
│   └── SHARED_CONTRACT_EXCEPTIONS.md # NEW, Scenario Review round 10 P0-1
│                                   #   — the register gate 6's shared-
│                                   #   contract-exception approval clause
│                                   #   (TSD §24.1) checks against; empty
│                                   #   until a real cross-domain exception
│                                   #   is approved
├── infra/                          # NEW — IaC (exact tool TBD at
│   ├── environments/               #   implementation time — TSD names no
│   │   ├── local/                  #   specific IaC vendor read so far),
│   │   ├── qa/                     #   environment configs, CI-runner
│   │   └── staging/                #   definitions. No `production/` — DC-16
│   └── ci/                         #   owner-reserved, not scaffolded until
│                                   #   the owner explicitly authorizes it
├── .github/workflows/              # NEW — CI pipeline definitions
│                                   #   (reuses this repo's existing GitHub
│                                   #   remote; GitHub Actions, no new
│                                   #   vendor — see CAPABILITIES.md)
└── tools/                          # NEW — MOD-001's own validators:
    ├── validate_architecture_gates.py   # the 6 TSD §24.1 gates
    ├── validate_capability_manifest.py  # extends MOD-000's pattern to
    │                                    #   any module, not just MOD-000
    ├── validate_scenario_matrix.py      # generalizes validate_catalog.py
    ├── validate_baseline_binding.py     # generalizes verify_baselines.py
    ├── validate_external_gates.py       # new (§20/§21/§22.0 consistency)
    ├── validate_appendix_i.py           # new (invariant/runbook traceability)
    ├── validate_appendix_b_traceability.py # new, Scenario Review round
    │                                    #   11 P1-4 — REQUIREMENTS.md §3's
    │                                    #   own text named this as a tool
    │                                    #   MOD-001 "must build" (no split
    │                                    #   requirement exists for MOD-001
    │                                    #   itself; future modules' Scenario
    │                                    #   Reviews run it), but it was
    │                                    #   never added to this inventory —
    │                                    #   rejects a split requirement
    │                                    #   whose designated completing
    │                                    #   module executes before any of
    │                                    #   its execution-slice modules;
    │                                    #   proven by SCN-085
    ├── validate_data_exposure.py        # new, Scenario Review round 8 P0-1
    │                                    #   (SCN-126: card security baseline
    │                                    #   "input/output data exposure" —
    │                                    #   OpenAPI response/request
    │                                    #   schema-field allowlist)
    ├── validate_sensitive_logging.py    # new, Scenario Review round 6 P1-1
    │                                    #   (SCN-122: card security baseline)
    ├── abuse_negative_fixture_harness.py # new, Scenario Review round 6 P1-1
    │                                    #   (SCN-123: card security baseline)
    ├── validate_idempotency_contract.py # new, Scenario Review round 6 P0-1
    │                                    #   (SCN-016: the card's 6-element
    │                                    #   idempotency-contract lint —
    │                                    #   key-tuple scoping, retention
    │                                    #   window, stored-hash field, 409
    │                                    #   code reference, command_id
    │                                    #   propagation, provider-derivative
    │                                    #   field — distinct from SCN-016's
    │                                    #   own runtime dedup/409 behavior
    │                                    #   check, which needs no separate
    │                                    #   tool)
    ├── validate_agent_definitions.py    # new, Scenario Review round 5 P1-4
    │                                    #   (SCN-120: reachability +
    │                                    #   dangling-reference check over
    │                                    #   .claude/agents/*.md, plus the
    │                                    #   7-field MR-evidence check per
    │                                    #   EIP §4.1)
    ├── validate_adr_conformance.py      # new, Scenario Review round 5 P1-4
    │                                    #   (SCN-119: ADR-004/ADR-015
    │                                    #   conformance per ADR_CONFORMANCE.md)
    ├── validate_toolchain_matrix.py     # new, §12 (GOV-01-R07, round 7,
    │                                    #   corrected round 8 P1-3 — §12's
    │                                    #   own prose named this tool but
    │                                    #   never added it here) — checks
    │                                    #   mobile/TOOLCHAIN_MATRIX.md's
    │                                    #   pinned versions against real
    │                                    #   committed Gradle/Xcode/CI-
    │                                    #   runner config, distinct from
    │                                    #   SCN-051/099's internal-
    │                                    #   consistency-only checks
    ├── generate_changelog.py           # new, §12 (GOV-01-R08, round 7,
    │                                    #   corrected round 8 P1-3) —
    │                                    #   proven by SCN-MOD001-107
    └── generate_screen_contracts.py     # imports the canonical registry
```

No governing-baseline docx, no `knowledge/` file, and no existing
`.claude/` file is modified or moved by this plan — everything above is
additive.

## 2. Environment boundaries

| | LOCAL | QA | STAGING |
|---|---|---|---|
| **Purpose** | Individual developer iteration; MOD-001's own harness self-tests run here by default | Automated CI runs (every PR); the environment MOD-001's own architecture-gate/CI validators execute against | Pre-production rehearsal: canary/rollout drills, migration drills, release-evidence generation rehearsal |
| **Configuration source** | `.env.local` (gitignored) + `infra/environments/local/` defaults | `infra/environments/qa/` + CI-injected secrets (GitHub Actions encrypted secrets, not committed) | `infra/environments/staging/` + a separate secret scope from QA |
| **Secrets mechanism** | Local `.env` file, developer-managed, never committed (extends this repo's existing `.gitignore`) | GitHub Actions repository/environment secrets | GitHub Actions environment secrets, distinct environment scope from QA (so a QA credential leak cannot reach staging) |
| **Permitted data** | Synthetic/fixture data only | Synthetic/fixture data only | Synthetic/fixture data only — **no real member data in any of the three**, per DC-16, unaffected by environment tier |
| **Prohibited data** | Real member data, real payment credentials, real production secrets | Same | Same |
| **Deployment mechanism** | Manual (`docker compose up` or equivalent — exact tool selected at implementation time) | Automatic on CI green (GitHub Actions workflow) | Automatic on QA-gate green, gated by a manual approval step (still not Production) |
| **Migration policy** | Alembic upgrade/downgrade run manually by the developer | Alembic upgrade run automatically as a CI stage, against a disposable QA database, following TSD §24.2's expand→migrate→switch→contract ordering | Same as QA, plus the rollback-runbook (`RB-GOV-01`) drill runs here |
| **Reset/seed policy** | Reset freely, any time, by the developer | Reset on every CI run (ephemeral database per run, or truncate-and-reseed) | Reset on a scheduled cadence (e.g. nightly) — never mid-drill |
| **Observability** | Local logs only | CI-run logs archived as workflow artifacts | Same as QA, plus the canary/SLO-guardrail monitoring GOV-01-R05 requires |
| **External services** | None (mocked/stubbed) | Sandboxed equivalents only (per TSD §24.1: "Integration tests with PostgreSQL/event/workflow/provider sandboxes") | Sandboxed equivalents only — no real payment/messaging provider credentials |
| **Promotion gates** | N/A (no promotion out of local) | Must pass all TSD §24.1 CI stages before promoting to staging | Must pass staging's E2E/synthetic/load-subset/a11y/localization gates (TSD §24.1) before any further promotion — which does not exist in this plan, since Production is owner-reserved |
| **Rollback** | Discard local changes | Re-run CI on the prior commit (no persistent QA state to roll back) | The `RB-GOV-01` runbook's own procedure, drilled synthetically |

**Production is explicitly not represented in this topology.** DC-16 (No
deploys/promotion to Production) means no `infra/environments/production/`
directory, no production secret scope, and no production deployment
workflow exist in this plan or will be scaffolded during MOD-001
implementation without explicit, separately recorded owner approval in
`OWNER_APPROVALS.md`.

## 3. CI/CD quality-gate specification

Derived directly from TSD §24.1's own pipeline-stage ordering
(`TSD_MIRROR.md` lines 11595-11654), mapped to GitHub Actions workflow
jobs (reusing the existing GitHub remote):

| Stage (TSD §24.1 order) | Trigger | Input | Output | Blocking? | Local equivalent | Failure evidence | Bypass protection |
|---|---|---|---|---|---|---|---|
| Format/lint/type checks | Every push/PR | Source tree | Pass/fail + lint report | Yes | Same linter run locally | CI log + lint report artifact | Runs via the pinned CI workflow file only; no `--no-verify`-equivalent flag exposed |
| **6 of the 7 architecture gates** (RLS, module-dependency/SQL, event-contract, permission, screen-contract, domain-contract-uniqueness lint — **corrected, Scenario Review round 12, P2-1: this row's title and enumeration still said "6," uncorrected since round 1 P1-9 added the 7th (surface-profile-activation) gate; §4, §5.3, `SCN-111`, and `TEST_PLAN.md` were all fixed to "7" starting round 2/3, this row alone was missed**) | Every push/PR | Source tree + `contracts/` | Pass/fail per gate + violation report | Yes, each independently | Same validators run locally (`tools/validate_architecture_gates.py`) | Named violation type + offending file/line | Deliberate-violation fixtures proven denied — see §4 below. Bypass protection is enforced at the branch-protection required-status-check layer, not the workflow file's own content: a same-PR gate-step edit, `[skip ci]`, `workflow_dispatch`, and a fork-PR origin are all proven (SCN-MOD001-020) not to un-gate the merge. **Corrected (Scenario Review round 3, P1-4):** three further classes are resisted and must stay closed — required-check name drift, direct/force push, and `pull_request_target` running base-branch code with secrets; a fourth, branch-protection admin override, is a disclosed, deliberate GitHub-level escape hatch (owner-controlled via "include administrators"), not a gate defect — its existence and who holds it must be recorded, never silently assumed away |
| **7th architecture gate: surface-profile activation (added, Scenario Review round 12, P2-1 — this gate has existed since round 1 P1-9 but never had its own §3 pipeline row; §4's gate-7 row pointed back at "the new 7th check" inside this very row, which never named it)** | Every push/PR | Source tree + `module-capabilities.yaml` | Pass/fail + violation report | Yes | Same validator run locally (`tools/validate_architecture_gates.py --gate surface-profile`) | Named `SURFACE_PROFILE_NOT_ACTIVATED`/unknown-surface violation + offending path | Deliberate-violation and carve-out-boundary fixtures proven denied/allowed — see §4 gate 7 below (`SCN-MOD001-102`/`103`/`112`/`138`/`139`) |
| Unit tests | Every push/PR | `backend/tests/unit/`, mobile/web unit suites | Pass/fail + coverage | Yes | `pytest`/platform-native runner locally | Test report artifact | N/A — no known bypass class yet; will be re-examined once real tests exist |
| Domain contract / tenant-isolation / authorization / financial-invariant tests | Every push/PR (once a domain exists) | Fixture DB + RLS-enabled schema | Pass/fail | Yes, once applicable | Same suite locally against a local Postgres | Report artifact naming the failed invariant ID | RLS enforced at the database role level, not just application code — cannot be bypassed by application-layer changes alone |
| SAST / dependency / secret / container / IaC scanning + SBOM/provenance | Every push/PR | Source tree, dependency manifest, container image, IaC files | Findings report + SBOM | Yes (secret/critical-vuln findings block; advisory findings do not, per tool default) | Same scanners run locally | Findings report artifact | Scanner runs from the pinned workflow; no scanner-skip flag committed |
| Build signed immutable artifact/image | On merge to main | Source tree | Signed artifact + provenance record | Yes | A dev-only self-signed build locally | Signature verification log | Signing key held in CI secrets, not the repo; a locally-built artifact cannot carry a valid CI signature |
| Integration tests | Every push/PR | Sandboxed Postgres/event/workflow/provider fixtures | Pass/fail | Yes, once applicable | Docker-composed sandbox locally | Report artifact | N/A yet |
| API/event schema compatibility + migration-safety checks | Every push/PR touching `contracts/` or `backend/alembic/` | OpenAPI/AsyncAPI diffs, Alembic migration diff | Pass/fail + compatibility report | Yes | Same checker locally | Named incompatible-change report | Schema-diff tool runs against the actual committed contract files, not a developer's local, possibly-stale copy |
| Deploy to staging + E2E/synthetic/load-subset/a11y/localization gates | On merge to main, after all above pass | Staging environment | Pass/fail + evidence bundle | Yes | Cannot fully replicate locally (needs the shared staging environment) — this is the one stage with no local equivalent, disclosed as such | Evidence bundle artifact | Staging deploy only triggers from CI, never a developer's local `kubectl`/deploy command (no such credential exists locally) |
| Canary/rollout with SLO/guardrail monitoring | After staging gates pass | Staging environment | Promote/rollback decision | Yes | N/A (needs staging) | Rollback-trigger log | Automated rollback trigger tied to real guardrail signals, not a manually-callable endpoint |
| Promote or rollback; publish release metadata | End of pipeline | Canary result | Release-evidence record (`RB-GOV-01` field set) | Yes | N/A | Release-evidence artifact | N/A |
| Domain contract uniqueness lint | Every push/PR, once >1 domain exists | All domains' contracts | Pass/fail + cross-domain conflict report | Yes, once applicable | `tools/validate_architecture_gates.py` locally | Named conflicting-domain-pair report | Runs against the full committed contract set, not a partial local view |
| **Input/output data-exposure lint (added, Scenario Review round 8, P0-1)** | Every push/PR touching `contracts/openapi/` | OpenAPI response/request schemas | Pass/fail + named field-shape report | Yes | `tools/validate_data_exposure.py` locally (SCN-MOD001-126) | Named undeclared-response-field or extra-request-field report | Runs against the actual committed OpenAPI contract, not a developer's local, possibly-stale copy |
| **Sensitive-logging lint (added, Scenario Review round 6, P1-1)** | Every push/PR | Source tree (log statements) | Pass/fail + named pattern-class report | Yes | `tools/validate_sensitive_logging.py` locally (SCN-MOD001-122) | Named file/line + secret- or PII-pattern-class report | Runs against the full committed source tree, not a partial local view |
| **Abuse-negative fixture harness (added, Scenario Review round 6, P1-1)** | Once a later domain module builds real abuse-scenario content on top of it | Synthetic abusive/legitimate request-shape fixtures | Pass/fail classification | Yes, once applicable | `tools/abuse_negative_fixture_harness.py` locally (SCN-MOD001-123) | Classification report | The harness itself is MOD-001's obligation; fixture *content* for specific business flows is a later domain module's obligation, same split as the offline-fixture pattern above |
| **Idempotency-contract lint (added, Scenario Review round 6, P0-1)** | Every push/PR touching a command declaration for an externally-retryable mutation | Command/endpoint declaration | Pass/fail + named-missing-element report | Yes | `tools/validate_idempotency_contract.py` locally (SCN-MOD001-016 part a) | Named missing-element report (key-tuple scoping, retention window, stored-hash field, 409-code reference, command_id propagation, or provider-derivative field) | Runs against the actual committed command declaration, not a developer's local, possibly-stale copy — same pattern as the API/event schema-compatibility row above |
| **Agent-definition/model-alias/MR-evidence check (added, Scenario Review round 5, P1-4)** | Every push/PR touching `.claude/agents/**`, plus every CI run for MR-evidence content | `.claude/agents/*.md` escalation text; MR evidence records | Pass/fail + named-defect report | Yes | `tools/validate_agent_definitions.py` locally (SCN-MOD001-120) | Named unreachable-agent, dangling-reference, or missing-MR-field report | Runs against the full committed agent-definition set, not a partial local view — distinct from the TSD §24.1 architecture gates in §4 below, since this checks EIP §4.1's own routing-evidence requirement, not a data/schema architecture rule |
| **ADR conformance check (added, Scenario Review round 5, P1-4)** | Every push/PR | `ADR_CONFORMANCE.md`, the module's own API surface and migration harness | Pass/fail per mapped ADR | Yes, once applicable | `tools/validate_adr_conformance.py` locally (SCN-MOD001-119) | Named ADR-nonconforming-change report | Runs against the actual committed API/migration code, not `ADR_CONFORMANCE.md`'s own prose claim |
| **Capability-manifest/governance validation (added, Scenario Review round 11, P1-4)** | Every push/PR touching `.claude/agents/**`, `.claude/rules/**`, `.claude/skills/**`, or `module-capabilities.yaml` | Those files | Pass/fail + named-defect report | Yes | `tools/validate_capability_manifest.py` locally | Named cyclic-dependency, overdue-lifecycle-review, or missing-mandatory-Rule report | Runs against the actual committed capability set, extending MOD-000's `validate_capabilities.py` pattern to any module |
| **Scenario-matrix validation (added, Scenario Review round 11, P1-4)** | Every push/PR touching any module's `SCENARIOS.md` | The touched Scenario Catalog | Pass/fail + named-defect report | Yes | `tools/validate_scenario_matrix.py` locally (generalizes `validate_catalog.py`) | Named O-on-Required-category, missing-G.4-justification, or PERF/Load-inconsistency report | Runs against the actual committed catalog, not a cached prior count |
| **Baseline-binding validation (added, Scenario Review round 11, P1-4)** | Every push/PR touching `PROJECT_INDEX.md` or `SESSION_BOOTSTRAP.md` | Those files + the 4 governing baseline artifacts | Pass/fail + named-defect report | Yes | `tools/validate_baseline_binding.py` locally (generalizes `verify_baselines.py`) | Named missing/ambiguous/mismatched identity-hash report | Runs against the actual committed baseline hashes, folding `REQUIREMENTS.md` §3's manual-per-session check into the CI-gate layer |
| **External-gate consistency validation (added, Scenario Review round 11, P1-4)** | Every push/PR touching `EXTERNAL_GATES.md` or a module's execution card | Those files | Pass/fail + named-defect report | Yes | `tools/validate_external_gates.py` locally | Named §20/§21/§22.0-mismatch or unresolved-gated-capability report | Runs against the actual committed registry/card/binding set |
| **Appendix-I traceability validation (added, Scenario Review round 11, P1-4)** | Every push/PR touching an `INV-<DOMAIN>`/`RB-<DOMAIN>` entry or a mapped ADR | Those entries | Pass/fail + named-defect report | Yes | `tools/validate_appendix_i.py` locally | Named unmapped-invariant or unconformed-ADR report | Runs against MOD-001's own `DOM-001`/`DOM-002`/`EVT-001`/`IAM-002`/`INV-GOV-01`/`RB-GOV-01` entries first, per `REQUIREMENTS.md` §3 |
| **Appendix-B traceability validation (added, Scenario Review round 11, P1-4)** | Every push/PR touching a split-requirement's designated completing or execution-slice module | Split-requirement module-ownership metadata | Pass/fail + named-defect report | Yes, once a split requirement exists | `tools/validate_appendix_b_traceability.py` locally (SCN-MOD001-085) | Named ordering-violation report (completing module executing before an execution-slice module) | New tool this round — no split requirement exists for MOD-001 itself, so this gate is currently a no-op pass; it is the mechanism future modules' Scenario Reviews will run |
| **Toolchain-matrix real-config validation (added §1 tools inventory round 7, P1-2 — corrected round 12, P1-3: had no CI-stage row of its own, so `SCN-MOD001-127`'s entire mechanism had no pipeline trigger and was unexecutable as planned)** | Every push/PR touching `mobile/TOOLCHAIN_MATRIX.md` or `mobile/**/build.gradle.kts` | The matrix doc + real committed Gradle/Xcode/CI-runner config | Pass/fail + named-drift report | Yes, once applicable | `tools/validate_toolchain_matrix.py` locally (SCN-MOD001-127) | Named pinned-version-vs-real-config drift report | Runs against the actual committed matrix and Gradle/CI-runner files, not the matrix's own internal-consistency claim (that half is SCN-051/099) |

**No gate is certification theater** — every row above has a concrete
input, output, and failure-evidence artifact. Several rows are correctly
marked "once applicable" because no domain module exists yet; the gate
mechanism itself (the CI workflow step, the validator script) is what
MOD-001 delivers now, exercised against synthetic/trivial fixtures where
no real domain content exists to test.

## 4. Architecture-gate negative-fixture plan (TSD §24.1's six gates
plus the 7th, ADR-005-added surface-profile-activation gate — **corrected,
Scenario Review round 12, P2-1: this heading undercounted, same as §3's
pipeline row**)

Per the mission's explicit instruction: synthetic/test fixtures only,
never destructive tests against real project baselines.

| Gate | Valid fixture | Deliberate violation fixture | Expected fail-closed output | CI location | Local invocation | Evidence artifact |
|---|---|---|---|---|---|---|
| **1. RLS lint** | A tenant table with `tenant_id NOT NULL` + RLS policy + `FORCE ROW LEVEL SECURITY`, owned by a role distinct from the production-equivalent runtime role | A tenant table missing `FORCE ROW LEVEL SECURITY`, queried under the **production-equivalent, non-privileged runtime role** (TSD §24.1, `TSD_MIRROR.md` lines 11599-11601: "runtime role cannot own/bypass. Negative isolation tests run with production-equivalent role" — **corrected, Scenario Review round 1 P1-4**: the original draft here specified a `BYPASSRLS`-capable role, which is exactly the elevated attribute the TSD's negative-test rule excludes, and would have made the fixture untestable/meaningless); **or (added, Scenario Review round 12, P0-2 — the same source line's "runtime role cannot own/bypass" and a nullable `tenant_id` had no fixture of their own, a Blocker-tier TSD normative clause left untested eleven rounds) a table where the runtime role is the table owner or carries `BYPASSRLS`, or a tenant table with `tenant_id` left nullable** | CI fails with a named `RLS_NOT_ENFORCED` violation citing the table, or `RLS_RUNTIME_ROLE_ELEVATED` citing the role/table pair, or `RLS_TENANT_ID_NULLABLE` citing the column | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate rls` | `evidence/security/RLS_GATE_FIXTURE_<date>.md` |
| **2. Module dependency/SQL lint** | A module importing only its own owned table prefix/schema, or an approved read-model interface; **for the four intentional bidirectional pairs, the one §6.3-listed synchronous edge may import the opposite interface** (TSD `TSD_MIRROR.md` lines 11606-11608; **added, Scenario Review round 1 P1-5** — the original draft only covered the owned-prefix rule, missing this normative half of the gate) | A module's code directly importing another module's raw table/ORM model; **or the reverse-direction synchronous import on one of the four §6.3 bidirectional pairs (the edge the TSD requires stay event-driven)** | CI fails with `CROSS_DOMAIN_SQL_IMPORT` citing the importing/imported module pair, or `REVERSE_EDGE_NOT_EVENT_DRIVEN` for the §6.3 case | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate module-deps` | Same directory |
| **3. Event contract lint** | An event referenced in code that exists in the AsyncAPI/JSON-Schema registry; **a registered event's compatibility/classification change carrying a recorded owner-approval reference** (`TSD_MIRROR.md` lines 11610-11612: "compatibility and classification changes require owner approval" — **added, Scenario Review round 10, P0-1**, the normative second half of this gate, disclosed unfixtured since round 1 and carried nine rounds) | An event referenced in code with no matching registry entry; **or a registered event's schema/classification diff with no owner-approval reference attached** (`OWNER_APPROVALS.md` row ID or equivalent) | CI fails with `UNREGISTERED_EVENT_CONTRACT` citing the event name, or `EVENT_CHANGE_UNAPPROVED` citing the event and the unapproved diff | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate event-contract` | Same directory; owner-approval reference resolved against `OWNER_APPROVALS.md` |
| **4. Permission lint** | An API command/query declaring `action`/`resource`/`scope` | A command/query with an undeclared or unregistered permission name | CI fails with `UNREGISTERED_PERMISSION` citing the endpoint | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate permission` | Same directory |
| **5. Screen contract lint** | A V1 Screen ID mapped to a BFF/read-model or typed command manifest row | A Screen ID with no mapped BFF/command row before feature release | CI fails with `UNMAPPED_SCREEN_CONTRACT` citing the Screen ID | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate screen-contract` | Same directory |
| **6. Domain contract uniqueness lint** | Two domains with disjoint authoritative-entity sets, command inventories, published-event sets, runbook IDs, SLI/SLO signal names, and failure-vocabulary (`REQUIREMENTS.md` line 260-264 names all six comparison dimensions — **corrected, Scenario Review round 12, P0-2: this row previously named only four of the six**); **or two domains sharing an identical `RB-<DOMAIN>` ID / command inventory where an explicit shared-contract exception is on record** (`TSD_MIRROR.md` lines 11646-11648: "fail unless an explicit shared-contract exception is approved" — **added, Scenario Review round 10, P0-1**, the normative escape clause of this gate, disclosed unfixtured since round 1 and carried nine rounds; without this half the gate as specified would false-positive on a legitimately approved shared contract) | Two domains reusing an identical `RB-<DOMAIN>` ID, **or reusing an identical command inventory** (added, Scenario Review round 12, P0-2 — TSD `TSD_MIRROR.md` lines 11643-11653 names identical command inventories and reused RB-IDs as two independent fail conditions in one sentence; round 10 fixtured only the RB-ID half, leaving the command-inventory half as a valid-fixture exception case with no violation fixture of its own), or a domain's SLO naming a foreign domain's signal (e.g. booking-capacity in a billing SLO), **with no recorded shared-contract exception for that specific pair** | CI fails with `DOMAIN_CONTRACT_COLLISION` citing both domains and the colliding artifact (command-inventory or RB-ID collision, or cross-domain SLO-signal reuse), unless a matching shared-contract-exception record resolves it, in which case CI passes citing the exception ID | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate domain-uniqueness` | Same directory; shared-contract exceptions resolved against a `contracts/SHARED_CONTRACT_EXCEPTIONS.md` register (new, this round) |

**Disclosed residual (Scenario Review round 12, P0-2, closing the
Blocker-severity gap for real on the two conditions named above; the
remaining two of the six comparison dimensions are lower-severity and
left disclosed rather than fixtured this round):** an
authoritative-entity-set collision and a failure-vocabulary collision
(the sixth dimension) have no violation fixture of their own yet —
both compare free-form prose/naming rather than a structured ID space
like `RB-<DOMAIN>` or a command inventory, so a synthetic fixture for
either needs a real normalization rule (e.g. what counts as the "same"
failure-vocabulary term across two domains' independently-written
docs) that does not yet exist and would be invented, not derived, if
written this round. Tracked as an Implementation Complete obligation
for `tools/validate_architecture_gates.py --gate domain-uniqueness`,
not a Definition-of-Ready blocker — the RB-ID and command-inventory
conditions above are the two the TSD states as an explicit,
structured, machine-checkable pair in one sentence, which is why they
were prioritized for real fixtures this round.

**Added (Scenario Review round 1, P1-9 → `ADR-005` Decision 2, Part
3):**

| Gate | Valid fixture | Deliberate violation fixture | Expected fail-closed output | CI location | Local invocation | Evidence artifact |
|---|---|---|---|---|---|---|
| **7. Surface-profile activation** | A source file under a surface's path scope (e.g. `backend/app/main.py`) whose owning module's `module-capabilities.yaml` correctly records the matching activated §4.3 profile; **or a build/toolchain/CI configuration file under a surface's path scope (e.g. `mobile/shared/build.gradle.kts`, `mobile/androidApp/build.gradle.kts`, added round 10 P1-2) — carved out under ADR-005's own dividing line: "build, toolchain, and CI configuration for a surface is Infra/SRE/CI-profile work; the surface's own profile activates when the surface's own source code appears" (added, Scenario Review round 11, P2-1 — this carve-out existed only as ADR prose until now, and without it the gate as specified would deny MOD-001's own committed Gradle stubs against their still-DEFERRED KMP Mobile/Android Host profiles); the carve-out's recognized extension/filename set is closed, not open-ended — **corrected, Scenario Review round 12, P0-1: the previous "etc." made this an unfalsifiable pass condition, the same species round 3 had already removed from the gate-8/`SCN-108` lifecycle-lint** — exactly: `.gradle.kts`, `.gradle`, `.xcconfig`, `Package.swift`, `Podfile`, `package.json`, `package-lock.json`, `gradle.properties`, `settings.gradle.kts`, `gradle-wrapper.properties`. Proven by `SCN-MOD001-138` (positive: a listed extension under a deferred surface passes) and `SCN-MOD001-139` (negative: the carve-out's own boundary — a `.kt` application file under the same deferred `mobile/shared/src/` path still denies, proving the carve-out is extension-scoped, not surface-wide)** | A source file of a deferred surface's own *application* file type (e.g. a `.tsx` file under `admin-web/`, a `.kt` application-logic file under `mobile/shared/src/`) added while `module-capabilities.yaml` still shows that profile deferred/unmarked; **and (added round 3, P1-6) a source file appearing under a top-level path matching NONE of the 10 named §4.3 globs at all** | CI fails with `SURFACE_PROFILE_NOT_ACTIVATED` citing the path and the missing profile for a named-but-unactivated surface, or a catch-all unknown-surface denial for a path matching no named glob; passes for a recognized build/toolchain/CI file matching the closed extension/filename set above under a deferred surface, citing the Infra/SRE/CI carve-out | Architecture-gates CI step (new 7th check) | `tools/validate_architecture_gates.py --gate surface-profile` | `evidence/security/SURFACE_PROFILE_GATE_FIXTURE_<date>.md` |

**Corrected (Scenario Review round 2, P1-6; further corrected round
3): the original marker-only design was fail-open.** General Web
(`web/**`), Edge (`edge/**`) and Data/AI (`data-ai/**`) had no
directory in §1's topology and therefore no marker for a marker-only
check to read — a module creating one of those paths with real code
would trip nothing. And a single `mobile/.profile-pending` marker could
not express three distinct deferred profiles (KMP Mobile
`mobile/shared/**`, iOS Host `mobile/iosApp/**`, Android Host
`mobile/androidApp/**`). **Fixed:** all 10 §4.3 path prefixes named in
`MODEL_ROUTING.md`'s surface-profile table now carry an explicit
deferral marker (`evidence/module-capabilities.yaml`'s
`repository_paths_surfaces` list), including the six with no directory
yet — `mobile/` carries three sub-markers, one per distinct profile.
With all 10 named paths now marked, the residual fail-open case is not
among them: it's a *completely unlisted* top-level surface (`SCN-MOD001-112`)
that matches none of the 10 globs — a marker-keyed check has no row to
consult for such a path by construction, so gate 7 additionally
requires the capability-governance validator to flag any new top-level
directory that matches neither a known infrastructure path
(`backend/**`, `infra/**`, `contracts/**`, `tools/**`,
`.github/workflows/**`) nor a named §4.3 glob, as an explicit
unknown-surface denial requiring a `module-capabilities.yaml` decision
before merge — rather than silently allowing it through absence.

Each deferred empty shell's marker file names the §4.3 profile that
must activate before real code lands there; the check reads that
marker (or, for not-yet-created path prefixes, the absence of a
directory doesn't matter — the marker's *declaration* in
`module-capabilities.yaml` is what the check consults) the moment matching
source files appear) rather than an inferred mapping, so the deferral
is a declared, checkable contract, not an absence a validator has to
guess at. **Clarified (Scenario Review round 11, Editorial-1):** the
nine `.profile-pending` marker file paths `module-capabilities.yaml`
names are exactly this — declared entries the check consults — not
filesystem artifacts §1's topology above is expected to list; none of
them exist as real files until the module that first touches that
surface creates both the directory and the marker together.

Each gate's fixtures are synthetic tables/files created and destroyed
within the test harness's own throwaway schema/fixture directory — never
against `knowledge/`, the governing baselines, or any real project state.

## 5. Load / performance scope (bounded, per the EIP card's own field)

The EIP card's "Load / performance" field (`EIP_MIRROR.md` line
4230-4231) reads, verbatim: "CI runner and environment smoke-load;
validate no gate is bypassable." This module's load/performance
obligation is explicitly **not** application-scale business load
testing (that belongs to later domain modules per GOV-01-R03's own
IN/OUT boundary). Planned scope:

1. **CI runner smoke-load** — the full pipeline (§3 above) completes
   within a **pre-declared 15-minute budget** on a synthetic/trivial
   repo state (`SCN-MOD001-068`). **Corrected (Scenario Review round 2,
   P1-4): this previously said the budget would be "set from that
   measurement (no invented number here)," which is self-referential
   and unfalsifiable — `SCENARIOS.md` SCN-068 already fixed this on the
   scenario side (round 1, P1-7); this file was not updated to match at
   the time.** 15 minutes is a deliberately tight ceiling for a pipeline
   with no real product code yet (GitHub Actions' free-tier per-job
   timeout default is 6 hours). If the first real measurement exceeds
   it, the budget is revisited via a recorded decision, not silently
   loosened.
2. **Environment smoke-load** — LOCAL/QA/staging environments boot
   successfully under 10 concurrent requests against a trivial
   health-check endpoint, each responding within 2 seconds
   (`SCN-MOD001-069`); proves the environment itself isn't the
   bottleneck, not that the (nonexistent) product can handle load.
3. **Gate-bypass-under-load validation** (`SCN-MOD001-111`, added round
   2 — this scope item had no scenario before) — confirm none of the 7
   architecture gates (the 6 from TSD §24.1 plus the surface-profile-
   activation gate added per `ADR-005` — **corrected, round 3: this
   previously said "6," stale after gate 7 was added**) or CI stages
   can be skipped by racing/concurrent pipeline runs, timeout-induced
   partial execution, or a resource-exhausted CI runner silently
   passing.

## 6. Security scope (bounded, per the EIP card's own field)

Verbatim from the card (`EIP_MIRROR.md` lines 4267-4271): "Mandatory
baseline: authentication/authorization as applicable, tenant isolation,
input/output data exposure, secrets/dependency hygiene, sensitive
logging, privacy classification and abuse-negative scenarios."
**Corrected (Scenario Review round 8, P0-1): "input/output data
exposure" — one of the card's 7 mandatory baseline items — had no
disposition anywhere in this section (round 5's own P0-2 finding
miscounted this baseline as having 3 uncovered items when it actually
named 2, and never caught the third; rounds 6/7 inherited the
arithmetic error unchallenged).** Distinguishing actual MOD-001
implementation obligations from harnesses for future modules:

- **MOD-001 implementation obligations:** the RLS/permission lint gates
  themselves (they ARE the tenant-isolation/authz enforcement mechanism,
  not just a test of one); secret-scanning in CI (secrets/dependency
  hygiene); a sensitive-logging lint (no secret/PII patterns in log
  statements — a real, buildable static check); dependency-vulnerability
  scanning; **an input/output data-exposure lint (added round 8,
  P0-1)** — a schema-level allowlist check, distinct from the
  permission lint (which checks *action* declarations, not *field*
  shape): every OpenAPI response schema field must be explicitly
  declared (no undeclared/wildcard serialization that could leak an
  internal column), and every request schema rejects extra/undeclared
  fields (no hidden-field injection past validation). A real, buildable
  static check against the committed OpenAPI contract, distinct from
  RLS (row-level tenant isolation), sensitive-logging (log statements),
  privacy classification (data tagging), secret scanning (committed
  files), and abuse-negative (fixture harness) — none of which cover
  field-level response/request shape.
- **Harnesses for future modules, not MOD-001 implementation itself:**
  the actual authentication mechanism (MOD-007/008's scope); real
  privacy classification of real data fields (no real fields exist yet
  — MOD-001 builds the *lint* that will enforce a classification tag
  once fields exist); abuse-negative scenario *content* for specific
  business flows (MOD-001 builds the fixture pattern/harness those
  scenarios will use).

## 7. Capability dependencies

See `CAPABILITIES.md` for the full gap analysis. Summary: no new
approved capability is required to reach Definition of Ready this
session. Tool/vendor selections named above (GitHub Actions, pytest-class
tooling, Alembic) are implementation-time decisions following the TSD's
own non-mandatory reference stack — not commitments requiring owner
approval, since none involves spend, real data, or Production at the
planning stage.

## 8. Owner/external gates

None standing for MOD-001 itself (EIP card: "External gates — None").
DC-16's always-on restrictions apply throughout: no paid CI tier, no
paid scanning SaaS, no real Apple/Google developer account, no real
signing certificate, no production environment — all explicitly
deferred above, not decided here.

## 9. Rollback strategy (module-level)

If MOD-001 implementation needs to be rolled back after starting: no
production state exists to roll back (DC-16 — no Production promotion
ever occurred), so rollback is git-level (revert the implementation
commits) plus a QA/staging environment reset (§2's own reset policy) —
no data-migration rollback is needed unless a synthetic migration drill
was mid-flight, in which case `RB-GOV-01`'s own procedure applies to
that drill's disposable fixture schema only.

## 10. Import/validation contract (Appendix F Ready precondition, added Scenario Review round 4 P1-5)

Appendix F's MOD-001 row (`EIP_MIRROR.md` lines 18033-18043) makes
"access to the canonical approved UX registry and the import/
validation contract" a **Ready precondition** — distinct from
generating `screen-contracts.yaml` itself, which is explicitly
Implementation Complete work. Access to the registry is already
satisfied (§0 below); this section is the contract's actual design,
closing the one part of that precondition that wasn't done yet.

**Source registry format** (`veyro-product-experience-design/project/veyro-registry-data.js`
line 4, verbatim): 8 fields per row — `[id, module, name, phase,
status, roles, ar, note]`. `phase ∈ {V1, V1.5, V2, ENT}`; `status ∈
{DONE, GAP, NO-UI, V1.5, V2, ENT}`; `ar ∈ {BUILT, CONTRACT, NEEDS,
N/A}`. Per the registry's own header comment: "Surface and domain are
derived from the id prefix — never stored" (e.g. `ADM-`, `CON-`, `SYS-`).

**Import contract:**

1. **Read:** parse `R` (the exported array) from `veyro-registry-data.js`
   directly — never re-key or re-derive the data from a screenshot,
   remembered name, or inferred route (Appendix F's own explicit
   prohibition, `EIP_MIRROR.md` line 18008-18009).
2. **Filter:** select only rows where `phase === 'V1'` — V1.5/V2/ENT
   rows are out of scope for the current release gate's count.
3. **Resolve surface:** derive the surface from the `id` prefix per
   the registry's own mapping (`ADM-` → Admin, `CON-` → Console,
   `SYS-` → Backend-only/no-UI, etc. — Appendix F's own surface
   vocabulary, `EIP_MIRROR.md` line 17997).
4. **Resolve owning module:** map each row's surface + `module` field
   (a domain word like "Membership", "Payments") to its owning
   implementation module via Appendix B's execution-slice mapping —
   not MOD-001's own judgment call; MOD-001 imports Appendix B's
   existing mapping, it does not invent one.
5. **Multi-domain resolution:** where a screen's primary
   mutation/route contract belongs to one module but a secondary
   concern touches another (the card's own text, `EIP_MIRROR.md` lines
   18043-18049), resolve to the module owning the **primary
   mutation/route contract** — the secondary module is recorded as a
   read-only reference, not ownership.
6. **Validation failure shape:** a row that resolves to zero or
   multiple owning modules, or whose `id` prefix matches no known
   surface, is a validation failure — reported with the specific `id`
   and the reason (no owner found / ambiguous owner / unknown prefix),
   never silently dropped or defaulted.

**What this contract does NOT do (Implementation Complete scope,
correctly deferred):** actually running this import against the real
registry and emitting `screen-contracts.yaml`; the count/route/contract
lint (170-count equality check); wiring this into CI. Those happen once
MOD-001 implementation starts.

## 11. Already-satisfied half of the Appendix F Ready precondition

"The canonical source artifact must be checked into or
deterministically referenced by the Veyro repository before MOD-001
approval" (`EIP_MIRROR.md` lines 18006-18009) — **already true**:
`veyro-product-experience-design/` is checked into this repository and
hash-pinned in `PROJECT_INDEX.md` (manifest hash `c96f77ab...`,
re-verified via `verify_baselines.py` this session, PASS). No action
needed on this half; recorded here so it isn't mistaken for an open
item.

## 12. Mobile release/version and release-lifecycle foundations (GOV-01-R07/R08, added Scenario Review round 6 P1-2)

**Corrected (Scenario Review round 6, P1-2): GOV-01-R07's and
GOV-01-R08's own "Implementation obligations" text in `REQUIREMENTS.md`
never became a concrete file/CI-stage plan here — twelve scenarios
(SCN-050/051/052/055/074/099/100/101/107/108/115/117) depended on
mechanisms this file never named.** **Corrected again (Scenario Review
round 7): that fix did not hold end-to-end for 5 of the 12 (SCN-115,
117, 050, 051/099, 107) — deferring backend-side obligations to MOD-006
mis-assigned them (TSD §24.3's version-negotiation rule is a *backend*
rule: "Backend APIs preserve compatibility... server can expose
capability/version negotiation"), and three named TSD §24.3 rules
(white-label metadata, isolated-PR toolchain qualification, KMP
shared-module versioning) were never traced at all (round 7's P0-2).
Both fixed below.** Fixed:

**GOV-01-R07 (mobile release/version foundations):**
- `mobile/TOOLCHAIN_MATRIX.md` (new, §1 topology) — the pinned
  Kotlin/KMP/Compose/Gradle/Xcode/AGP toolchain compatibility matrix,
  authored before real mobile code exists so MOD-006 inherits a fixed
  target; referenced from the CI workflow file, per
  `REQUIREMENTS.md`'s own "Evidence obligations" text. Carries a
  `shared_module_version` field per KMP module (TSD §24.3: "shared KMP
  modules are versioned in source/build provenance") and a
  `whitelabel_release_metadata` section, one row per branded app/store
  (TSD §24.3's white-label rule) — **both added round 7, P0-2**.
- `mobile/RELEASE_POLICY.md` (new, §1 topology) — the documented
  minimum-supported-version, forced-update, and kill-switch **policy**.
- **`backend/app/version_negotiation.py` (new, §1 topology — added
  round 7, P1-2)** — the real backend-side enforcement code TSD §24.3
  actually assigns to the backend, not to the mobile app: minimum-
  supported-version check, optional-vs-forced-update decision, and the
  kill-switch's own authorization check (only an authorized release
  decision — a signed release-evidence record — may activate it, per
  `REQUIREMENTS.md`'s security-implication text). `mobile/RELEASE_POLICY.md`
  above is the policy *document*; this is the policy's *enforcement*,
  correctly scoped to MOD-001 (backend) rather than deferred to MOD-006
  (which owns only the client-side prompt/block UI, not the
  negotiation decision itself). Proven by `SCN-MOD001-115`.
- **`backend/app/crash_remote_config_intake.py` (new, §1 topology —
  added round 7, P1-2)** — synthetic backend-side intake endpoints for
  (a) crash-report ingestion (recorded/surfaced, not silently dropped)
  and (b) remote-config fetch (rollout-percentage changes only — TSD
  §24.3: remote config controls rollout, not contract repair, so this
  endpoint cannot itself bypass `version_negotiation.py`'s kill-switch
  block). Both are real, executable synthetic endpoints proving the
  integration *pattern* MOD-006 will point a real crash/remote-config
  SDK at — not a markdown interface description, and not deferred
  product functionality. Proven by `SCN-MOD001-117`.
- **CI runner-assignment convention** (new row, §3 pipeline table
  below): Android jobs pinned to Linux runners, iOS jobs pinned to
  macOS/Xcode runners, per TSD §24.3.
- **Common-code-change path-filter rule** (new row, §3 pipeline table
  below): a CI path filter that triggers both platforms' regression
  suites whenever a change touches serialization/local-schema/sync/
  auth/routing/shared-Design-System paths — tested by SCN-100/101's
  synthetic common-code-change fixture.
- **Real-device smoke-test CI convention, capability-adapter half
  (new row, §3 pipeline table below — added round 7, P1-2; proven
  round 9, P0-1; rescoped round 10, P1-1; propagated round 11, P1-2)**:
  TSD §24.3's real-device smoke-test requirement names two subjects —
  "platform-capability adapters" and "critical offline flows." SCN-050
  covers offline flows only; this row is the capability-adapter half
  (a synthetic native-adapter-boundary fixture, e.g. camera/biometric/
  push-token stub). Real execution runs on a standard (non-macOS)
  Android CI runner; the iOS half is proven present and required-
  status-checked on the release-candidate trigger path via workflow-
  graph inspection, with its own real execution deferred to real
  implementation time — a real-device-equivalent macOS iOS runner
  would conflict with `SCN-MOD001-056` (Blocker: no paid macOS CI
  runner tier referenced anywhere in MOD-001's committed
  configuration). Proven by `SCN-MOD001-129` (added round 9; rescoped
  round 10, P1-1, after its original "both real-device-equivalent CI
  runners" text was found to conflict with `SCN-056` and MOD-001's own
  mobile-out-of-scope boundary).
- **Toolchain-matrix consistency checker (new tool, §1 tools inventory
  — added round 7, P1-2; proven round 9, P0-1)**: `tools/validate_toolchain_matrix.py`
  checks `mobile/TOOLCHAIN_MATRIX.md`'s pinned versions against the
  actual committed Gradle/Xcode/CI-runner config, rejecting drift
  (SCN-051/099 test *internal* matrix consistency; this tool is the
  mechanism that makes the matrix authoritative against real config,
  not just internally self-consistent) — proven, along with the
  matrix's `whitelabel_release_metadata`/`shared_module_version`
  fields, by `SCN-MOD001-127` (added round 9 — round 8's own
  disposition that these were "covered by existing scenario families'
  own intent" was independently found false, since this very paragraph
  says the opposite).
- **Isolated-PR toolchain-upgrade qualification gate (new row, §3
  pipeline table below — added round 7, P0-2; rescoped round 10, P1-1;
  propagated round 11, P1-2)**: TSD §24.3's rule that "toolchain
  upgrades are isolated pull requests with Android+iOS build, UI,
  accessibility and performance qualification before merge" — a CI
  stage, specifically triggered when a PR touches
  `mobile/TOOLCHAIN_MATRIX.md`, that wires all 4 qualification
  dimensions (build — with separate Android and iOS jobs under it —
  UI, accessibility, performance) as required jobs on the
  toolchain-upgrade trigger path. Real execution runs for the Android
  build/UI/accessibility jobs on standard (non-macOS) runners; the iOS
  build job's real execution is deferred to real implementation time
  (same `SCN-056` paid-macOS-runner constraint as the row above), but
  its presence and required-status-check wiring is checked now via
  workflow-graph/job-metadata inspection, blocking merge until all 4
  dimensions are wired and the runnable ones pass.

**GOV-01-R08 (release lifecycle):**
- `RELEASE_TRAIN.md` (new, §1 topology, repo root) — the release-train
  cadence convention, the "maintenance" policy (how long each release
  train line receives fixes — **added round 7, P1-5**, previously
  named nowhere despite being explicit Appendix B text), and a
  customer-communication template hook (**added round 7, P1-5**; per
  `REQUIREMENTS.md`'s own IN-scope text, a template only, since no real
  customer channel exists before a later module — DC-16).
- **Changelog tool (new, §1 tools inventory — added round 7, P1-2)**:
  `tools/generate_changelog.py`, wired to the release pipeline (new row,
  §3 pipeline table below) — SCN-107 tests "a changelog entry via the
  changelog tool," which previously named a convention document, not a
  tool.
- **Lifecycle-stage field** — **corrected (Scenario Review round 8,
  P1-3): this previously claimed to "extend `RUNBOOK.md`'s existing
  release-evidence field set," which is false; `RUNBOOK.md`'s 7-field
  evidence contract is `RB-GOV-01`'s own card-mandated rollback-
  incident record (`EIP_MIRROR.md` lines 22386-22394) and is a
  distinct artifact from the one this bullet describes.** GOV-01-R08's
  release-lifecycle record is a separate, per-release artifact (not a
  per-incident one) carrying a `lifecycle_stage` field
  (`beta`/`GA`/`deprecated`); a lint (new row, §3 pipeline table below)
  rejects a record with no lifecycle-stage field or an out-of-order
  stage transition (`deprecated`→`beta` without an explicit re-release
  path). `SCN-108` tests this record; `SCN-048`/`058` continue to test
  `RUNBOOK.md`'s own, unrelated 7-field rollback-evidence contract —
  the two are not the same record and this section no longer implies
  they are.

| Stage (TSD §24.1 order) | Trigger | Input | Output | Blocking? | Local equivalent | Failure evidence | Bypass protection |
|---|---|---|---|---|---|---|---|
| **Mobile CI runner assignment (GOV-01-R07)** | Every push/PR touching `mobile/**` | Workflow job definitions | Android jobs on Linux, iOS jobs on macOS/Xcode | Yes | Same convention checked locally against the workflow file | CI log naming the runner/job pair | Runner assignment pinned in the committed workflow file, not a developer's local runner choice |
| **Common-code-change dual-platform regression trigger (GOV-01-R07)** | Every push/PR touching a common-code path (serialization/local-schema/sync/auth/routing/shared-Design-System) | Changed-file path list | Both platforms' regression suites triggered | Yes | Same path-filter rule run locally | CI log naming the triggering path and both triggered jobs | Path-filter rule reads the actual committed diff, not a developer's local claim about which paths changed |
| **Real-device smoke test, offline-flow half (GOV-01-R07, added round 7 — SCN-050 tests this row)** | Every push/PR touching an offline-flow path | Changed-file path list | The fixture is flagged as requiring the offline-smoke-test job | Yes | Same path-filter/flagging rule run locally | CI log naming the triggering path and the flagged job | Flagging rule reads the actual committed diff, not a developer's local claim about which paths changed |
| **Real-device smoke test, capability-adapter half (GOV-01-R07, added round 7, proven round 9, rescoped round 10 P1-1 — `SCN-MOD001-129`)** | On merge to main, alongside the offline-flow half above | Synthetic native-adapter-boundary fixture (Android); iOS job wiring on the release-candidate trigger path | Pass/fail per adapter (Android, real); presence + required-status-check (iOS, workflow-graph) | Yes | Android: cannot fully replicate locally (needs a real Android CI runner); iOS: workflow-graph inspection can be run locally against the workflow file | Evidence bundle artifact (Android); workflow-graph inspection report (iOS) | Android smoke test runs only from CI's real Android runner, never a developer's local simulator claim; iOS real execution is deferred to real implementation per `SCN-MOD001-056` (no paid macOS CI runner tier referenced in MOD-001's committed configuration) |
| **Isolated-PR toolchain-upgrade qualification gate (GOV-01-R07, added round 7, P0-2, proven round 9, rescoped round 10 P1-1 — `SCN-MOD001-128`)** | Every PR touching `mobile/TOOLCHAIN_MATRIX.md` | Android build/UI/a11y/perf qualification suites (real); iOS build job wiring (workflow-graph) | Pass/fail, all 4 dimensions wired, runnable ones (Android/UI/a11y) pass for real | Yes | Android/UI/a11y suites run locally against the proposed toolchain bump; iOS job-wiring checked locally via workflow-graph inspection | Named failing-dimension report; iOS reports missing/non-required-status wiring, not a failed build | Gate keys on the actual changed file path, not a developer's self-report that "this PR is isolated"; iOS build's real execution deferred to real implementation per `SCN-MOD001-056` |
| **Changelog generation (GOV-01-R08, added round 7, P1-2)** | Every release | Merged PR list since last release | Changelog entry | Yes | `tools/generate_changelog.py` run locally | Missing/malformed changelog-entry report | Runs against the actual committed PR/commit history, not a developer's hand-written draft |
| **Release-lifecycle-stage lint (GOV-01-R08)** | Every release | Release-evidence record | Pass/fail + named-defect report | Yes | Same lint run locally against a synthetic record | Named missing-field or out-of-order-transition report | Runs against the actual committed release-evidence record, not a developer's local draft |
