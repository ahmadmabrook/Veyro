---
doc: MOD-001_IMPLEMENTATION
status: LIVE — PLAN ONLY, NOT YET IMPLEMENTED
module: MOD-001
updated: 2026-09-17 (BUG-031/BUG-032 CLOSED — "registered and routable" claim now true for all 3 agents, independently verified; §12 still carries round 7's real backend-side mechanisms)
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
│   │   │   └── _shared/            #   owned domain (empty until MOD-002+
│   │   ├── contracts/               #   claims a domain); _shared/ holds
│   │   └── main.py                 #   cross-cutting (auth middleware
│   ├── alembic/                    #   scaffold, tenant-context resolver)
│   ├── tests/
│   │   ├── unit/
│   │   ├── component/
│   │   ├── integration/
│   │   └── contract/
│   └── pyproject.toml
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
│   │   └── src/commonMain/         #   shared logic/UI, iosMain/androidMain
│   ├── iosApp/                     #   hold native adapters only
│   ├── androidApp/
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
│   └── screen-contracts.yaml       #   (event contract lint gate, EVT-001);
│                                   #   generated by MOD-001's own tooling,
│                                   #   contains an explicit empty MOD-001
│                                   #   entry (REQUIREMENTS.md §4)
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
| **6 architecture gates** (RLS, module-dependency/SQL, event-contract, permission, screen-contract, domain-contract-uniqueness lint) | Every push/PR | Source tree + `contracts/` | Pass/fail per gate + violation report | Yes, each independently | Same validators run locally (`tools/validate_architecture_gates.py`) | Named violation type + offending file/line | Deliberate-violation fixtures proven denied — see §4 below. Bypass protection is enforced at the branch-protection required-status-check layer, not the workflow file's own content: a same-PR gate-step edit, `[skip ci]`, `workflow_dispatch`, and a fork-PR origin are all proven (SCN-MOD001-020) not to un-gate the merge. **Corrected (Scenario Review round 3, P1-4):** three further classes are resisted and must stay closed — required-check name drift, direct/force push, and `pull_request_target` running base-branch code with secrets; a fourth, branch-protection admin override, is a disclosed, deliberate GitHub-level escape hatch (owner-controlled via "include administrators"), not a gate defect — its existence and who holds it must be recorded, never silently assumed away |
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
| **Sensitive-logging lint (added, Scenario Review round 6, P1-1)** | Every push/PR | Source tree (log statements) | Pass/fail + named pattern-class report | Yes | `tools/validate_sensitive_logging.py` locally (SCN-MOD001-122) | Named file/line + secret- or PII-pattern-class report | Runs against the full committed source tree, not a partial local view |
| **Abuse-negative fixture harness (added, Scenario Review round 6, P1-1)** | Once a later domain module builds real abuse-scenario content on top of it | Synthetic abusive/legitimate request-shape fixtures | Pass/fail classification | Yes, once applicable | `tools/abuse_negative_fixture_harness.py` locally (SCN-MOD001-123) | Classification report | The harness itself is MOD-001's obligation; fixture *content* for specific business flows is a later domain module's obligation, same split as the offline-fixture pattern above |
| **Idempotency-contract lint (added, Scenario Review round 6, P0-1)** | Every push/PR touching a command declaration for an externally-retryable mutation | Command/endpoint declaration | Pass/fail + named-missing-element report | Yes | `tools/validate_idempotency_contract.py` locally (SCN-MOD001-016 part a) | Named missing-element report (key-tuple scoping, retention window, stored-hash field, 409-code reference, command_id propagation, or provider-derivative field) | Runs against the actual committed command declaration, not a developer's local, possibly-stale copy — same pattern as the API/event schema-compatibility row above |
| **Agent-definition/model-alias/MR-evidence check (added, Scenario Review round 5, P1-4)** | Every push/PR touching `.claude/agents/**`, plus every CI run for MR-evidence content | `.claude/agents/*.md` escalation text; MR evidence records | Pass/fail + named-defect report | Yes | `tools/validate_agent_definitions.py` locally (SCN-MOD001-120) | Named unreachable-agent, dangling-reference, or missing-MR-field report | Runs against the full committed agent-definition set, not a partial local view — distinct from the TSD §24.1 architecture gates in §4 below, since this checks EIP §4.1's own routing-evidence requirement, not a data/schema architecture rule |
| **ADR conformance check (added, Scenario Review round 5, P1-4)** | Every push/PR | `ADR_CONFORMANCE.md`, the module's own API surface and migration harness | Pass/fail per mapped ADR | Yes, once applicable | `tools/validate_adr_conformance.py` locally (SCN-MOD001-119) | Named ADR-nonconforming-change report | Runs against the actual committed API/migration code, not `ADR_CONFORMANCE.md`'s own prose claim |

**No gate is certification theater** — every row above has a concrete
input, output, and failure-evidence artifact. Several rows are correctly
marked "once applicable" because no domain module exists yet; the gate
mechanism itself (the CI workflow step, the validator script) is what
MOD-001 delivers now, exercised against synthetic/trivial fixtures where
no real domain content exists to test.

## 4. Architecture-gate negative-fixture plan (TSD §24.1's six gates)

Per the mission's explicit instruction: synthetic/test fixtures only,
never destructive tests against real project baselines.

| Gate | Valid fixture | Deliberate violation fixture | Expected fail-closed output | CI location | Local invocation | Evidence artifact |
|---|---|---|---|---|---|---|
| **1. RLS lint** | A tenant table with `tenant_id NOT NULL` + RLS policy + `FORCE ROW LEVEL SECURITY` | A tenant table missing `FORCE ROW LEVEL SECURITY`, queried under the **production-equivalent, non-privileged runtime role** (TSD §24.1, `TSD_MIRROR.md` lines 11599-11601: "runtime role cannot own/bypass. Negative isolation tests run with production-equivalent role" — **corrected, Scenario Review round 1 P1-4**: the original draft here specified a `BYPASSRLS`-capable role, which is exactly the elevated attribute the TSD's negative-test rule excludes, and would have made the fixture untestable/meaningless) | CI fails with a named `RLS_NOT_ENFORCED` violation citing the table | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate rls` | `evidence/security/RLS_GATE_FIXTURE_<date>.md` |
| **2. Module dependency/SQL lint** | A module importing only its own owned table prefix/schema, or an approved read-model interface; **for the four intentional bidirectional pairs, the one §6.3-listed synchronous edge may import the opposite interface** (TSD `TSD_MIRROR.md` lines 11606-11608; **added, Scenario Review round 1 P1-5** — the original draft only covered the owned-prefix rule, missing this normative half of the gate) | A module's code directly importing another module's raw table/ORM model; **or the reverse-direction synchronous import on one of the four §6.3 bidirectional pairs (the edge the TSD requires stay event-driven)** | CI fails with `CROSS_DOMAIN_SQL_IMPORT` citing the importing/imported module pair, or `REVERSE_EDGE_NOT_EVENT_DRIVEN` for the §6.3 case | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate module-deps` | Same directory |
| **3. Event contract lint** | An event referenced in code that exists in the AsyncAPI/JSON-Schema registry | An event referenced in code with no matching registry entry | CI fails with `UNREGISTERED_EVENT_CONTRACT` citing the event name | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate event-contract` | Same directory |
| **4. Permission lint** | An API command/query declaring `action`/`resource`/`scope` | A command/query with an undeclared or unregistered permission name | CI fails with `UNREGISTERED_PERMISSION` citing the endpoint | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate permission` | Same directory |
| **5. Screen contract lint** | A V1 Screen ID mapped to a BFF/read-model or typed command manifest row | A Screen ID with no mapped BFF/command row before feature release | CI fails with `UNMAPPED_SCREEN_CONTRACT` citing the Screen ID | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate screen-contract` | Same directory |
| **6. Domain contract uniqueness lint** | Two domains with disjoint command inventories, event sets, runbook IDs, SLI/SLO signal names | Two domains reusing an identical `RB-<DOMAIN>` ID, or a domain's SLO naming a foreign domain's signal (e.g. booking-capacity in a billing SLO) | CI fails with `DOMAIN_CONTRACT_COLLISION` citing both domains and the colliding artifact | Architecture-gates CI step | `tools/validate_architecture_gates.py --gate domain-uniqueness` | Same directory |

**Added (Scenario Review round 1, P1-9 → `ADR-005` Decision 2, Part
3):**

| Gate | Valid fixture | Deliberate violation fixture | Expected fail-closed output | CI location | Local invocation | Evidence artifact |
|---|---|---|---|---|---|---|
| **7. Surface-profile activation** | A source file under a surface's path scope (e.g. `backend/app/main.py`) whose owning module's `module-capabilities.yaml` correctly records the matching activated §4.3 profile | A source file of a deferred surface's own file type (e.g. a `.tsx` file under `admin-web/`) added while `module-capabilities.yaml` still shows that profile deferred/unmarked; **and (added round 3, P1-6) a source file appearing under a top-level path matching NONE of the 10 named §4.3 globs at all** | CI fails with `SURFACE_PROFILE_NOT_ACTIVATED` citing the path and the missing profile for a named-but-unactivated surface, or a catch-all unknown-surface denial for a path matching no named glob | Architecture-gates CI step (new 7th check) | `tools/validate_architecture_gates.py --gate surface-profile` | `evidence/security/SURFACE_PROFILE_GATE_FIXTURE_<date>.md` |

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
guess at.

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
Distinguishing actual MOD-001 implementation obligations from harnesses
for future modules:

- **MOD-001 implementation obligations:** the RLS/permission lint gates
  themselves (they ARE the tenant-isolation/authz enforcement mechanism,
  not just a test of one); secret-scanning in CI (secrets/dependency
  hygiene); a sensitive-logging lint (no secret/PII patterns in log
  statements — a real, buildable static check); dependency-vulnerability
  scanning.
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
  (new row, §3 pipeline table below — added round 7, P1-2)**: TSD
  §24.3's real-device smoke-test requirement names two subjects —
  "platform-capability adapters" and "critical offline flows." SCN-050
  covers offline flows only; this row is the capability-adapter half
  (a synthetic native-adapter-boundary fixture, e.g. camera/biometric/
  push-token stub, smoke-tested on both real-device-equivalent CI
  runners).
- **Toolchain-matrix consistency checker (new tool, §1 tools inventory
  — added round 7, P1-2)**: `tools/validate_toolchain_matrix.py` checks
  `mobile/TOOLCHAIN_MATRIX.md`'s pinned versions against the actual
  committed Gradle/Xcode/CI-runner config, rejecting drift (SCN-051/099
  test *internal* matrix consistency; this tool is the mechanism that
  makes the matrix authoritative against real config, not just
  internally self-consistent).
- **Isolated-PR toolchain-upgrade qualification gate (new row, §3
  pipeline table below — added round 7, P0-2)**: TSD §24.3's rule that
  "toolchain upgrades are isolated pull requests with Android+iOS
  build, UI, accessibility and performance qualification before merge"
  — a CI stage that runs the full dual-platform qualification suite
  specifically when a PR touches `mobile/TOOLCHAIN_MATRIX.md`, blocking
  merge until all four qualification dimensions pass.

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
- **Lifecycle-stage field** (extends `RUNBOOK.md`'s existing
  release-evidence field set): every release-evidence record carries a
  `lifecycle_stage` field (`beta`/`GA`/`deprecated`), and a lint (new
  row, §3 pipeline table below) rejects a release-evidence record with
  no lifecycle-stage field or an out-of-order stage transition
  (`deprecated`→`beta` without an explicit re-release path).

| Stage (TSD §24.1 order) | Trigger | Input | Output | Blocking? | Local equivalent | Failure evidence | Bypass protection |
|---|---|---|---|---|---|---|---|
| **Mobile CI runner assignment (GOV-01-R07)** | Every push/PR touching `mobile/**` | Workflow job definitions | Android jobs on Linux, iOS jobs on macOS/Xcode | Yes | Same convention checked locally against the workflow file | CI log naming the runner/job pair | Runner assignment pinned in the committed workflow file, not a developer's local runner choice |
| **Common-code-change dual-platform regression trigger (GOV-01-R07)** | Every push/PR touching a common-code path (serialization/local-schema/sync/auth/routing/shared-Design-System) | Changed-file path list | Both platforms' regression suites triggered | Yes | Same path-filter rule run locally | CI log naming the triggering path and both triggered jobs | Path-filter rule reads the actual committed diff, not a developer's local claim about which paths changed |
| **Real-device smoke test, offline-flow half (GOV-01-R07, added round 7 — SCN-050 tests this row)** | Every push/PR touching an offline-flow path | Changed-file path list | The fixture is flagged as requiring the offline-smoke-test job | Yes | Same path-filter/flagging rule run locally | CI log naming the triggering path and the flagged job | Flagging rule reads the actual committed diff, not a developer's local claim about which paths changed |
| **Real-device smoke test, capability-adapter half (GOV-01-R07, added round 7)** | On merge to main, alongside the offline-flow half above | Synthetic native-adapter-boundary fixture | Pass/fail per adapter | Yes | Cannot fully replicate locally (needs real-device-equivalent CI runners) | Evidence bundle artifact | Runs only from CI's real-device-equivalent runners, never a developer's local simulator claim |
| **Isolated-PR toolchain-upgrade qualification gate (GOV-01-R07, added round 7, P0-2)** | Every PR touching `mobile/TOOLCHAIN_MATRIX.md` | Android+iOS build/UI/a11y/perf qualification suites | Pass/fail, all 4 dimensions | Yes | Same suites run locally against the proposed toolchain bump | Named failing-dimension report | Gate keys on the actual changed file path, not a developer's self-report that "this PR is isolated" |
| **Changelog generation (GOV-01-R08, added round 7, P1-2)** | Every release | Merged PR list since last release | Changelog entry | Yes | `tools/generate_changelog.py` run locally | Missing/malformed changelog-entry report | Runs against the actual committed PR/commit history, not a developer's hand-written draft |
| **Release-lifecycle-stage lint (GOV-01-R08)** | Every release | Release-evidence record | Pass/fail + named-defect report | Yes | Same lint run locally against a synthetic record | Named missing-field or out-of-order-transition report | Runs against the actual committed release-evidence record, not a developer's local draft |
