---
doc: MOD-001_REQUIREMENTS
status: LIVE — DRAFT (planning stage, not yet independently reviewed)
module: MOD-001
updated: 2026-09-17 (Scenario Review round 8 — the card's mandatory Security-baseline's third uncovered item, "input/output data exposure", finally traced to new SCN-126, closing round 5's own miscounted P0-2 finding)
---

# MOD-001 — Requirements

Sourced directly from `knowledge/00-System/EIP_MIRROR.md` (owner-produced
pandoc extract of `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx`,
independently verified this session against the governing baseline — see
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-028-docx-read-capability-gap.md`)
and `knowledge/00-System/TSD_MIRROR.md` (same verification, against
`Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx`). Every
citation below names an exact mirror line range so a future session can
re-locate the source text without re-deriving it. On any conflict
between this file and the governing `.docx` (re-hashed via
`verify_baselines.py`), the docx wins — the mirrors are a read
convenience, not a governing artifact.

## 0. Module identity (EIP §21.2, `EIP_MIRROR.md` lines 4099-4302)

- **Module:** MOD-001 — Repository, CI/CD, Environments & Quality Engineering
- **Wave:** Foundation
- **TSD scope:** GOV-01
- **Prerequisites:** MOD-000 (satisfied — APPROVED)
- **Objective (verbatim):** "Create the production repository skeleton,
  local/QA/staging environments, CI/CD quality gates, contract/schema
  checks, deterministic test harnesses and release controls."
- **Risk class:** Foundation/Control
- **Required scenario categories (verbatim):** "R: HP, VAL, NEG, BND,
  AUTHN, AUTHZ, TEN, SEC, PRIV, CONC, IDEM, NET, PART, OFF, REC, LIFE,
  DATA, INT, LOC, A11Y, PERF, OBS, MIG, DR | O: ALT" — 24 Required
  categories, 1 Optional (ALT). Cross-verified independently against
  Appendix G's three category-matrix tables (`EIP_MIRROR.md` lines
  19585, 19748, 19911): MOD-001's row is R in every column except ALT
  (O) — exact match, no discrepancy found.
- **Model route:** Automatic §4.1 route — Opus planning/lead; Sonnet
  primary routine implementation and deterministic tests; risk-triggered
  auto-escalation to Opus; independent fresh-context Opus Scenario
  Review, Code Review, Manual QA and Gatekeeper. **Corrected (Scenario
  Review round 1, P0-3/P1-9): this originally claimed "no new agent
  required" — false.** GOV-01-R02's tenant-isolation/RLS harness and
  authn negative-credential fixture pattern are a real EIP §4.1
  critical slice needing a dedicated role, and two §4.3 surface
  profiles (Infra/SRE/CI, Backend) genuinely activate for MOD-001's own
  scaffold/harness content. Three new agents were required
  (`veyro-critical-engineer`, `veyro-infra-sre-engineer`,
  `veyro-backend-engineer`) — all now registered and, for the critical
  slice, independently confirmed routable. See
  `knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`
  and `MODEL_ROUTE.md` for the full routing detail.
- **Screens: NONE.** See §4 below — this is a real finding, not an
  omission.
- **External gates:** None (per the card, verbatim: "External gates —
  None").
- **Owner approval:** No standing module-specific approval; DC-16's
  standing owner-reserved restrictions (spend, paid activation, real
  member data, Production promotion, material business/product change)
  apply throughout, unchanged.
- **Requirement ownership:** 8 Blueprint requirement/slice trace links
  in Appendix B — these are exactly GOV-01-R01 through GOV-01-R08 below;
  Appendix B's own columns (`EIP_MIRROR.md` lines 11843-11846:
  Requirement ID / Domain / Priority / Phase / Completing module /
  Requirement / Execution slice module(s) / Slice scope) show all 8 as
  Priority=Critical, Phase=Foundation, Completing module=MOD-001,
  Execution slice module(s)=MOD-001, Slice scope="Full requirement
  implemented and completed in the listed module." MOD-001 is a
  single-slice module for all 8 — no split-requirement completing-module
  ordering issue applies here (contrast with modules like MOD-073, which
  the mirror shows completing multi-slice requirements from earlier
  modules).

## 1. GOV-01-R01 through R08 (EIP Appendix B, `EIP_MIRROR.md` lines 17540-17580)

Each requirement below carries the fields the mission specifies:
Requirement ID, authoritative source, exact scope, IN/OUT of scope,
implementation obligations, evidence obligations, scenario coverage,
dependencies, acceptance criteria, security implications,
performance/load implications, owner/external gates.

### GOV-01-R01 — Test pyramid

**Source:** EIP Appendix B, `EIP_MIRROR.md` line 17540-17543 (verbatim):
"Test pyramid covering unit, component, integration, contract,
end-to-end, mobile UI and exploratory testing." Cross-referenced against
EIP §10 "Testing and QA Strategy" (`EIP_MIRROR.md` lines 1888-1960),
which names the same layers plus per-layer gate expectations.

- **IN scope:** establishing the actual test-pyramid *infrastructure* —
  directory conventions, runner configuration, and CI wiring — for each
  of: static/lint, unit, component, integration, contract (API/event
  schema), end-to-end, mobile UI, and exploratory testing. Each layer's
  CI gate expectation from §10's table (blocking vs. required-for-scope)
  is encoded as an actual CI stage, not prose.
- **OUT of scope:** authoring the *product* test content of later
  domain modules (e.g. MOD-004's tenant-lifecycle unit tests). MOD-001
  builds the harness/pyramid/contracts every later module plugs into,
  per the mission's own instruction not to prematurely implement
  business modules.
- **Implementation obligations:** per-layer test runner config (unit,
  component, integration, contract, E2E, mobile UI); a documented
  exploratory-testing procedure (Claude manual QA, per DC-04 — automation
  cannot substitute); CI stage wiring for each layer with the correct
  blocking/non-blocking behavior per §10's table.
- **Evidence obligations:** a passing run of each layer's harness against
  a trivial/synthetic fixture (proving the harness itself works, since no
  product code exists yet to test); CI logs showing each stage executed
  in the correct pipeline position.
- **Scenario coverage:** HP (harness runs green on a trivial fixture),
  NEG (harness correctly fails/blocks on a broken fixture), BND
  (harness behavior at pyramid-layer boundaries — e.g. a test
  mis-tagged as unit that actually hits a database).
- **Dependencies:** none beyond MOD-000's control-plane tooling.
- **Acceptance criteria:** all seven layers have a runnable harness;
  each layer's CI gate blocking behavior matches §10's table; a
  deliberately broken fixture at each layer is proven to fail the
  correct gate (not silently pass).
- **Security implications:** none direct; the harness must not leak
  secrets in test fixtures or logs (ties to GOV-01-R04's secret scanning).
- **Performance/load implications:** none at this requirement's own
  level — load/perf testing itself is GOV-01-R03's scope.
- **Owner/external gates:** none.

### GOV-01-R02 — Critical workflow suite architecture

**Source:** `EIP_MIRROR.md` line 17545-17549 (verbatim): "Critical
workflow suites for authentication, tenant isolation, membership,
booking, payment, ledger, POS, access and migration."

- **IN scope:** the *test architecture* — harness, contracts, fixtures,
  and CI gates — that later domain modules (MOD-004 tenant, MOD-007/008
  auth, MOD-015+ payment/ledger, MOD-019/020 booking, MOD-021/022 access,
  migration tooling under GOV-01-R06) will plug their real suites into.
  This explicitly includes: a tenant-isolation test harness capable of
  running a query/action as a non-privileged runtime role and asserting
  RLS denial (proves TSD §24.1's RLS lint gate); an authentication
  negative-credential fixture pattern; a migration-safety test harness
  (expand/migrate/contract ordering, per TSD §24.2).
- **OUT of scope:** implementing the actual membership/booking/payment/
  ledger/POS/access business logic those suites will one day exercise —
  that is MOD-004/MOD-015+/MOD-019+/MOD-021+'s own scope, per the
  mission's explicit "must establish the test architecture/contracts/
  harnesses required for them without prematurely implementing their
  business modules."
- **Implementation obligations:** a tenant-isolation test harness (RLS
  negative-role fixture); an authentication test harness (invalid/expired
  credential fixtures); a migration-safety harness implementing TSD
  §24.2's expand→migrate/backfill→switch→contract sequence as a testable
  contract; documented, empty-but-wired suite scaffolds for membership/
  booking/payment/ledger/POS/access, each with a placeholder fixture
  proving the harness itself is live (not proving product behavior that
  doesn't exist yet).
- **Evidence obligations:** a real RLS-negative-role denial proof (the
  same class of drill MOD-000's own Phase 3/7 work already established
  a pattern for, applied here to a real product-shaped fixture table);
  a real migration-safety harness run against a synthetic expand/
  contract migration.
- **Scenario coverage:** AUTHN, AUTHZ, TEN (Required, Critical — tenant
  isolation harness proven), MIG (Required — migration-safety harness
  proven), BND, NEG.
- **Dependencies:** GOV-01-R01's test-pyramid infrastructure (this
  requirement's suites sit inside that pyramid's integration/contract
  layers).
- **Acceptance criteria:** the tenant-isolation harness denies a real
  cross-tenant access attempt under a non-privileged runtime role; the
  migration-safety harness runs a synthetic expand/contract migration
  and detects a deliberately broken rollback; each named domain
  (membership/booking/payment/ledger/POS/access) has a wired, empty
  suite scaffold ready for its owning module.
- **Security implications:** this requirement IS a security control
  (tenant isolation, authn). Any weakness here undermines every later
  module's isolation guarantees — highest-severity requirement in this
  module.
- **Performance/load implications:** the migration-safety harness must
  itself run within CI time budgets; large-backfill *simulation* (not
  real backfill) should be bounded.
- **Owner/external gates:** none directly; real payment/ledger provider
  credentials remain owner-reserved (DC-16) and are explicitly out of
  scope for MOD-001's placeholder scaffolds.

### GOV-01-R03 — Load, performance, security, accessibility, localization, offline and failure testing foundations

**Source:** `EIP_MIRROR.md` line 17551-17554 (verbatim): "Load,
performance, security, accessibility, localization, offline and failure
testing."

- **IN scope:** the *foundations* — harness/tooling/CI wiring — for
  each of: load testing (CI-runner and environment smoke-load only, per
  the module card's own "Load / performance" field — not full
  application-scale load, see `IMPLEMENTATION.md` §5 **— corrected,
  Scenario Review round 2, P2-1: this previously cited a nonexistent
  "§12 below" within this file**), performance baselining,
  security scanning (SAST/dependency/secret/container/IaC per TSD
  §24.1), accessibility (a11y) tooling, localization (RTL/Arabic)
  tooling, offline-testing patterns (relevant to later edge/mobile/POS
  modules), and failure/chaos-style testing (network partition, timeout,
  degraded-mode fixtures).
- **OUT of scope:** application-scale load tests belonging to later
  domain modules; full production accessibility audits of screens that
  don't exist yet (MOD-001 owns zero screens — see §4 below).
- **Implementation obligations:** SAST/dependency/secret/container/IaC
  scanning wired into CI (this overlaps directly with GOV-01-R04's CI
  gates — implemented once, satisfies both); an a11y lint tool wired for
  future UI-bearing modules; an RTL/localization lint; a
  network-partition/timeout fixture harness (NET/PART categories); an
  offline-mode fixture pattern for later edge/mobile consumers.
- **Evidence obligations:** each scanner/linter run at least once
  against this repo's own current (near-empty) tree, producing a real
  report (even if "0 findings" — the tool working is the evidence, not a
  finding count); a real network-timeout drill against an unreachable
  host with `git status` proven unaffected before/after (same pattern
  MOD-000's own Phase 5 NET scenario used).
- **Scenario coverage:** SEC, PRIV, NET, PART, OFF, LOC, A11Y, PERF —
  all Required per Appendix G's MOD-001 row.
- **Dependencies:** GOV-01-R04's CI gate wiring (shared implementation).
- **Acceptance criteria:** every named tool (SAST, dependency,
  secret, container, IaC, a11y, RTL-lint) runs successfully in CI
  against the current repo state; a real NET/PART fixture proves
  fail-safe behavior.
- **Security implications:** direct — this requirement includes the
  security-scanning tooling itself.
- **Performance/load implications:** explicitly bounded to CI-runner
  and environment smoke-load per the module card (`IMPLEMENTATION.md`
  §5); not application load.
- **Owner/external gates:** none for tooling; any paid scanning
  service (e.g. a commercial SAST SaaS) would need DC-16 owner approval
  before activation — default to free/open-source/already-available
  tooling first, per the capability-gap analysis in `CAPABILITIES.md`.

### GOV-01-R04 — CI gates

**Source:** `EIP_MIRROR.md` line 17556-17559 (verbatim): "CI gates for
lint, test, vulnerability, schema compatibility, migration safety and
artifact signing." Cross-referenced against TSD §24.1 (`TSD_MIRROR.md`
lines 11595-11654), which is the authoritative pipeline-stage
enumeration.

- **IN scope:** every CI pipeline stage TSD §24.1 names: format/lint/
  type checks; the six architecture enforcement gates (RLS lint, module
  dependency/SQL lint, event contract lint, permission lint, screen
  contract lint, domain contract uniqueness lint — see §5 below, this is
  also this module's EIP-card "Special rule"); unit tests; domain
  contract/tenant-isolation/authorization/financial-invariant tests;
  SAST/dependency/secret/container/IaC scanning + SBOM/provenance;
  signed immutable artifact/image build; integration tests against real
  sandboxes; API/event schema compatibility + migration safety checks;
  staging deploy + E2E/synthetic/load-subset/a11y/localization gates;
  canary/feature-flag rollout with SLO monitoring; promote-or-rollback +
  release metadata publication.
- **OUT of scope:** the actual domain contract/tenant-isolation/
  authorization/financial-invariant test *content* for domains that
  don't exist yet — the gate exists and blocks on it; content is later
  modules' job.
- **Implementation obligations:** an actual CI pipeline definition (this
  project's TSD names no specific CI vendor in what I've read so far —
  `IMPLEMENTATION.md` §3 plans without inventing one) implementing every
  stage above in TSD §24.1's order; the domain contract uniqueness lint
  specifically
  (compares normalized authoritative-entity sets, command inventories,
  published-event sets, runbook IDs, SLI/SLO signals and failure-
  vocabulary across all 57 §10 domains — a real, non-trivial validator
  MOD-001 must build).
- **Evidence obligations:** a full pipeline dry-run against the current
  (near-empty) repo, every stage passing or correctly skipping
  (not-yet-applicable) rather than silently omitted; a deliberate-
  violation proof for each of the 6 architecture gates (§5) plus for
  vulnerability/schema-compatibility/migration-safety/artifact-signing.
- **Scenario coverage:** every category this module is Required for
  touches a CI gate somewhere; specifically BND, NEG, SEC, MIG, DATA,
  OBS.
- **Dependencies:** GOV-01-R01 (test pyramid), GOV-01-R02 (workflow
  suite harnesses), GOV-01-R06 (migration-safety detail).
- **Acceptance criteria:** every TSD §24.1 stage runs; every one of the
  6 architecture gates has a passing valid-fixture proof AND a
  deliberate-violation fail-closed proof (`IMPLEMENTATION.md` §4's
  table); no gate is bypassable at the **CI-workflow-configuration
  layer** — **corrected (Scenario Review round 2, P1-2): this
  previously described a local shell-invocation bypass model
  (absolute-path/wrapper/shell-composition tricks, mirroring
  `bash_guard.py`), which round 1's own P1-3 finding already ruled the
  wrong threat model for a CI gate and corrected in `SCENARIOS.md`
  SCN-020/`IMPLEMENTATION.md` §3 — this file was not updated to match
  at the time.** **Further corrected (Scenario Review round 3, P1-4): the
  original wording said the gate must "resist" all four real bypass
  classes uniformly — that overstated the case for one of them.**
  Required-status-check name drift, direct/force push bypassing the PR
  path, and `pull_request_target` running base-branch workflow code
  with secrets are genuine gaps the gate must resist and close.
  Branch-protection admin override is different in kind: GitHub's
  "include administrators" setting is an explicit, owner-level design
  choice — if enabled, admin override doesn't exist; if disabled, it
  remains possible but requires an actual admin account and produces
  an audit trail. The acceptance criterion is therefore: the gate
  resists (g) name drift, (h) force push, and (i) `pull_request_target`
  outright, and for (f) admin override, the criterion is that the
  escape hatch's existence and who holds it is explicitly recorded as
  a disclosed, deliberate residual — not silently assumed away, and
  not something the gate itself can or should "resist" (see SCN-020's
  own detail block for the full, current test procedure and expected
  results, corrected to match this distinction).
- **Security implications:** direct and central — CI gates are a
  primary security control (secret scanning, SAST, dependency
  vulnerability, artifact signing/provenance).
- **Performance/load implications:** pipeline runtime itself must be
  bounded (CI-runner smoke-load, GOV-01-R03).
- **Owner/external gates:** artifact signing may imply a code-signing
  key/certificate — provisioning one is DC-16 owner-reserved if it
  requires a paid CA or production credential; a self-signed/dev-only
  signing key is in scope for MOD-001's own proof without owner
  involvement, real production signing infrastructure is not.

### GOV-01-R05 — Progressive delivery

**Source:** `EIP_MIRROR.md` line 17561-17564 (verbatim): "Progressive
delivery, canary, feature flags, automated rollback and release
evidence." Cross-referenced against `INV-GOV-01`/`RB-GOV-01`
(`EIP_MIRROR.md` lines 21708-21715, 22386-22394): "Every production
artifact is reproducible, signed and traceable to source and tests" is
release-blocking; `RB-GOV-01` names "Bad deployment/schema/config
release rollback" as MOD-001's owned runbook.

- **IN scope:** canary/percentage rollout mechanics; feature-flag
  integration points (noting MOD-005 owns the actual flag *management*
  product per Appendix B's PLT-02 rows — MOD-001 owns the CI/release
  *plumbing* that consumes flags, not the flag admin UI); automated
  rollback triggered by SLO/guardrail breach; release-evidence
  generation (what got deployed, from what commit, with what test
  evidence, signed how).
- **OUT of scope:** the feature-flag *administration product* (MOD-005,
  PLT-02) — MOD-001 only needs a consumption contract/integration point.
- **Implementation obligations:** a canary/rollout mechanism (even a
  minimal scripted percentage-based one, given no cloud infra exists
  yet); an automated-rollback trigger tied to a synthetic guardrail; a
  release-evidence record format (`RB-GOV-01`'s own evidence-contract
  fields: affected tenant/scope, command/aggregate version, authoritative
  rows, outbox/inbox/DLQ/provider state where applicable, reconciliation
  result, repair/correction reference, owner/follow-up action).
- **Evidence obligations:** a synthetic canary deploy-and-rollback drill,
  end to end, in the local/QA environment (never staging/production
  real traffic without owner approval).
- **Scenario coverage:** REC (recovery — Required), OBS (Required),
  DR (Required).
- **Dependencies:** GOV-01-R04 (CI gates), GOV-01-R06 (migration
  rollback specifically).
- **Acceptance criteria:** a deliberately-bad synthetic release triggers
  automated rollback; release evidence is generated and matches
  `RB-GOV-01`'s required field set.
- **Security implications:** a rollback mechanism that can be triggered
  maliciously would itself be a DoS vector — the trigger condition must
  be tied to genuine SLO/guardrail signals, not an arbitrary external
  call.
- **Performance/load implications:** canary monitoring windows must be
  short enough to bound blast radius, long enough to catch real
  regressions — a tuning decision for later, documented as an open
  parameter here, not invented arbitrarily.
- **Owner/external gates:** any real production canary/rollout remains
  DC-16 owner-reserved (no Production promotion). MOD-001's own proof is
  local/QA-environment only.

### GOV-01-R06 — Database-change policy/tooling

**Source:** `EIP_MIRROR.md` line 17566-17570 (verbatim):
"Backward-compatible database changes, expand-contract pattern,
zero-downtime migration and rollback strategy." Directly grounded in TSD
§24.2 "Database Migration Policy" (`TSD_MIRROR.md` lines 11655-11669,
full text): "Expand -> migrate/backfill -> switch reads/writes ->
contract. Destructive contract happens only after all deployed versions
stop using old shape. Large backfills are online/resumable jobs with
progress and throttling; never a single deployment transaction. Every
migration records owner, expected lock/write impact, rollback/
forward-fix strategy and data validation query. Schema and application
deployment ordering is tested against at least previous supported
version for rolling deploy compatibility."

- **IN scope:** the migration-safety CI check (already named under
  GOV-01-R04); a migration-record template capturing TSD §24.2's 4
  required fields (owner, expected lock/write impact, rollback/
  forward-fix strategy, data validation query); a rolling-deploy
  compatibility test (N-1 version compatibility).
- **OUT of scope:** any actual product schema — none exists yet.
- **Implementation obligations:** a migration tool/convention enforcing
  expand→migrate→switch→contract ordering; a lint rejecting a
  destructive (contract-phase) migration that isn't preceded by an
  expand+backfill+switch sequence; a migration-record template file.
- **Evidence obligations:** a synthetic 4-phase migration run end to
  end against a throwaway schema, including a deliberately-destructive
  migration attempted out of order and proven rejected.
- **Scenario coverage:** MIG (Required, Critical-adjacent), DATA
  (Required), BND, NEG.
- **Dependencies:** none beyond GOV-01-R04's CI wiring.
- **Acceptance criteria:** the lint rejects an out-of-order destructive
  migration; a valid 4-phase migration passes; rollback strategy is
  present and testable for at least the synthetic case.
- **Security implications:** a migration tool with unrestricted DDL
  access is itself a high-privilege surface — must run under a scoped
  role, not superuser, consistent with TSD's RLS/role-separation
  philosophy (§24.1's RLS lint).
- **Performance/load implications:** large-backfill throttling is a
  direct performance requirement per §24.2's own text.
- **Owner/external gates:** none for the tooling; real production
  database credentials remain owner-reserved.

### GOV-01-R07 — Mobile release/version foundations

**Source:** `EIP_MIRROR.md` line 17572-17575 (verbatim): "Mobile
version support policy, store rollout, crash monitoring and remote
configuration." Directly grounded in TSD §24.3 "Mobile Release Policy"
(`TSD_MIRROR.md` lines 11670-11700, full text) — backend API
compatibility for minimum supported app versions; remote config for
rollout, not contract repair; explicit minimum-version/optional-forced-
update/kill-switch policy; white-label per-brand release metadata; a
pinned Kotlin/KMP/Compose/Gradle/Xcode/AGP toolchain compatibility
matrix with isolated-PR toolchain upgrades; CI builds Android on
Linux runners, iOS on macOS/Xcode runners, with real-device smoke tests
for platform-capability adapters and critical offline flows; a
common-code change touching serialization/local-schema/sync/auth/
routing/shared-Design-System triggers both platforms' regression
suites.
- **IN scope:** the version-support/kill-switch *policy document and
  its enforcement contract* (not the mobile app itself — MOD-006 owns
  KMP+Compose mobile implementation per Appendix B); the pinned
  toolchain compatibility matrix; crash-monitoring integration point;
  remote-config integration point; the cross-platform regression-trigger
  rule for common-code changes.
- **OUT of scope:** the actual mobile application code (MOD-006);
  Android/iOS store account provisioning (may be owner-reserved spend —
  DC-16).
- **Implementation obligations:** a documented minimum-supported-version
  and forced-update policy; a pinned toolchain versions file (even
  before real mobile code exists, so MOD-006 inherits a fixed target);
  CI runner assignment (Android→Linux, iOS→macOS/Xcode) as a pipeline
  convention; the common-code-change→both-platform-regression trigger
  rule encoded as a CI path-filter rule. **Concrete plan: `IMPLEMENTATION.md`
  §12 (added Scenario Review round 6, P1-2 — this text had never been
  turned into a named file/CI-stage plan until then).**
- **Evidence obligations:** the toolchain matrix file exists and is
  referenced from CI config; the path-filter rule is testable with a
  synthetic "common-code" file change proving both platform regression
  jobs get triggered.
- **Scenario coverage:** MIG, INT, PERF (build/toolchain qualification),
  OBS (crash monitoring).
- **Dependencies:** GOV-01-R01 (test pyramid's "mobile UI" layer).
- **Acceptance criteria:** toolchain matrix file exists; policy document
  exists; synthetic common-code-change test proves the dual-platform
  regression trigger fires.
- **Security implications:** forced-update/kill-switch is itself a
  security control (reserved for security/critical incompatibility per
  §24.3) — must not be triggerable without the equivalent of an
  authorized release decision.
- **Performance/load implications:** real-device smoke tests are
  release-gating per §24.3, though full mobile devices are a MOD-006-era
  concern — MOD-001 establishes the CI convention only.
- **Owner/external gates:** real Apple/Google developer account
  provisioning and any paid CI macOS-runner capacity are DC-16
  owner-reserved (spend) — MOD-001's own proof stays scoped to the
  policy/toolchain-matrix/CI-convention layer, not real store
  submission.

### GOV-01-R08 — Release lifecycle

**Source:** `EIP_MIRROR.md` line 17577-17580 (verbatim — **corrected,
Scenario Review round 1, P2-3: the original quote here read "beta, GA,
deprecation," which is not the mirror's actual text**): "Release train,
changelog, maintenance, beta/GA/deprecation lifecycle and customer
communication."

- **IN scope:** a release-train cadence convention; a changelog
  generation convention; **a maintenance policy — how long each release
  train line receives fixes (added Scenario Review round 7, P1-5: the
  card's own text lists "maintenance" as a distinct item from
  changelog, but this section previously conflated the two with no
  independent disposition)**; a beta→GA→deprecation lifecycle
  state machine (as a documented policy + a lint that a release
  declares its own lifecycle stage); a customer-communication template
  hook (even if the "customer" is internal/synthetic at this stage, since
  MOD-001 precedes any real customer-facing module).
- **OUT of scope:** actual customer communications content/copy for
  product features that don't exist yet; real per-release-line
  maintenance-window decisions for domain modules that don't exist yet
  (the *policy document* is MOD-001's obligation, not applying it to
  real releases).
- **Implementation obligations:** a release-train schedule/cadence
  document; a maintenance-window policy document (added round 7, P1-5);
  a changelog file/tool convention wired to the release pipeline
  (GOV-01-R05); a customer-communication template hook (added round 7,
  P1-5 — previously IN scope but absent from this list entirely); a
  lifecycle-stage field in the release-evidence record (ties to
  `RB-GOV-01`'s evidence contract). **Concrete plan: `IMPLEMENTATION.md`
  §12 (added Scenario Review round 6, P1-2, extended round 7, P1-5 —
  this text had never been turned into a named file/CI-stage plan until
  then).**
- **Evidence obligations:** a synthetic release cycle producing a
  changelog entry and a lifecycle-stage-tagged release-evidence record;
  `RELEASE_TRAIN.md` itself containing both the maintenance policy and
  the customer-communication template (added round 7, P1-5).
- **Scenario coverage:** OBS, DR (deprecation as a controlled,
  reversible-until-committed process). **`SCN-MOD001-125` (added round
  7, P1-5) covers maintenance-policy/customer-communication-template
  presence, previously untested.**
- **Dependencies:** GOV-01-R05 (release evidence format).
- **Acceptance criteria:** a synthetic release produces a changelog
  entry and a correctly-tagged lifecycle stage; `RELEASE_TRAIN.md`
  contains a maintenance policy and a customer-communication template
  (added round 7, P1-5).
- **Security implications:** none direct.
- **Performance/load implications:** none direct.
- **Owner/external gates:** any real customer communication channel
  (email/SMS provider) is DC-16 owner-reserved spend — out of scope for
  MOD-001's own proof.

## 2. Traceability summary

| Requirement | Source (EIP_MIRROR.md) | Priority | Completing module | Slice scope |
|---|---|---|---|---|
| GOV-01-R01 | lines 17540-17543 | Critical | MOD-001 | Full — single slice |
| GOV-01-R02 | lines 17545-17549 | Critical | MOD-001 | Full — single slice |
| GOV-01-R03 | lines 17551-17554 | Critical | MOD-001 | Full — single slice |
| GOV-01-R04 | lines 17556-17559 | Critical | MOD-001 | Full — single slice |
| GOV-01-R05 | lines 17561-17564 | Critical | MOD-001 | Full — single slice |
| GOV-01-R06 | lines 17566-17570 | Critical | MOD-001 | Full — single slice |
| GOV-01-R07 | lines 17572-17575 | Critical | MOD-001 | Full — single slice |
| GOV-01-R08 | lines 17577-17580 | Critical | MOD-001 | Full — single slice |

No TBD placeholders survive above — every requirement has real,
docx-sourced scope, IN/OUT boundaries, and acceptance criteria. See
`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` for how these translate
into actual repo/CI/environment structure, and
`knowledge/03-Modules/MOD-001/SCENARIOS.md` for the Scenario Catalog.

## 3. Additional MOD-001-owned EIP/TSD control obligations

Beyond GOV-01-R01..R08, the mission requires discovering every other
explicit EIP/TSD reference that assigns MOD-001 ownership. Found by
direct search of both mirrors (not assumed exhaustive — a future
Scenario Review pass should re-search independently):

| Obligation | Source | What MOD-001 must build | Ties to |
|---|---|---|---|
| **Six TSD §24.1 architecture gates** | `TSD_MIRROR.md` lines 11597-11653; EIP card "Special rule", `EIP_MIRROR.md` line 4233-4234 ("MOD-001 implements all six TSD §24.1 architecture gates") | (1) RLS lint; (2) module dependency/SQL lint; (3) event contract lint; (4) permission lint; (5) screen contract lint; (6) domain contract uniqueness lint — each as a real CI-blocking check, each with a deliberate-violation fixture proving fail-closed | GOV-01-R04 |
| **Capability-governance validation gates** | EIP card, `EIP_MIRROR.md` lines 4122-4157, 4233-4256; Appendix H.1-H.3, lines 20590-20740 | Validate `.claude/agents`/`.claude/rules`/`.claude/skills`/`module-capabilities.yaml`; reject cyclic capability dependencies, overdue lifecycle reviews, manifests missing mandatory privileged-surface Rules; require every Appendix H.2 rule family to resolve to an Appendix H.3 content standard | Reuses MOD-000's `validate_capabilities.py`/`CAPABILITY_REGISTRY.md` pattern — extend, don't duplicate |
| **Baseline-artifact binding schema validation** | `EIP_MIRROR.md` lines 4140-4143, 4253-4256, 4260-4263 | Require `PROJECT_INDEX.md` entries for all governing baselines with non-empty cryptographic hashes and `SESSION_BOOTSTRAP.md` enforcement metadata; reject use of an unapproved candidate EIP or a missing/ambiguous/mismatched identity+hash | Already substantively satisfied by MOD-000's `verify_baselines.py` — MOD-001 must fold this into the CI-gate layer (currently a manual per-session check, not yet a CI gate); `SCN-MOD001-025`/`026` (mismatch case) + `SCN-MOD001-124` (the other 4 fail-closed conditions — **added round 7, P0-1**, since only the mismatch case had a scenario until then) |
| **Appendix-B traceability validator** | `EIP_MIRROR.md` lines 4144-4147 | Reject any split requirement whose designated completing module executes before any of its execution-slice modules | New tool — no split requirements exist for MOD-001 itself (§0 above), but MOD-001 must build the *validator* future modules' Scenario Reviews will run |
| **Idempotency-contract lint** | `EIP_MIRROR.md` lines 4148-4157 | For externally retryable mutations: scoped Idempotency-Key tuple, retention window (>=24h, longer for payment/fiscal), stored request hash/result, stable 409 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`, `command_id` propagation to outbox/provider dispatch, deterministic provider idempotency derivatives | `IMPLEMENTATION.md` §1/§3 (`tools/validate_idempotency_contract.py`, added round 6 P0-1); `SCN-MOD001-016` part (a) — **corrected, Scenario Review round 6 P0-1: this row previously pointed at nothing but a requirement/category name, and the only linked scenario tested runtime dedup behavior, not the lint itself** |
| **AsyncAPI/versioned JSON-Schema event-registry validation** | `EIP_MIRROR.md` line 4156-4157 | Blocking CI check that every event referenced by flow/code exists in the AsyncAPI/JSON-Schema registry | Same mechanism as the event contract lint gate above (EVT-001 invariant) |
| **Scenario-matrix validator** | `EIP_MIRROR.md` lines 4158-4165 | Reject any O value for a §9.1-listed category; any N value without a G.4 per-module justification; any forbidden no-screen LOC/A11Y waiver on localization/shared-UI/mobile-qualification modules; any PERF/Load inconsistency in either direction | Reuses/extends MOD-000's `validate_catalog.py` — that tool already does an equivalent check for MOD-000's own catalog; MOD-001 must generalize it to validate *any* module's catalog, since this is the tool later modules' Scenario Reviews depend on |
| **External-gate consistency validator** | `EIP_MIRROR.md` lines 4166-4172 | Assert §20 registry External == §21 card External gates == §22.0 binding set; validate Gate class/Gated-capability metadata; reject a SOFTWARE_ONLY edge lacking durable non-use proof, or whose dependent consumes an unresolved gate's named capability | New tool — MOD-000's own `STATUS.md` "Gated-capability non-use evidence" field is the manual precursor; MOD-001 must make this mechanical |
| **Appendix-I traceability validator** | `EIP_MIRROR.md` lines 4172-4179 | Reject a module whose owned domain has an `INV-<DOMAIN>`/`RB-<DOMAIN>` entry with no mapped proving test/runbook, or a mapped ADR with no conformance state | New tool. MOD-001 itself owns/co-owns `DOM-001`, `DOM-002`, `EVT-001`, `IAM-002`, `INV-GOV-01`, `RB-GOV-01` (below) — must satisfy this validator against its own module first |
| **DOM-001** — no cross-domain direct table writes | `EIP_MIRROR.md` lines 20890-20897 (Appendix I.1); co-owned with MOD-002, MOD-010 | Proven by the module dependency/SQL lint gate | §24.1 gate 2 |
| **DOM-002** — optimistic concurrency/versioning per mutable aggregate | `EIP_MIRROR.md` lines 20899-20906; co-owned with MOD-002, MOD-019, MOD-020, MOD-034, MOD-037 | Proven by a concurrency/versioning test pattern in the test-pyramid's persistence layer | GOV-01-R02; CONC category |
| **EVT-001** — every material state transition emits a durable versioned domain event via the transactional outbox | `EIP_MIRROR.md` lines 20926-20933; co-owned with MOD-010 | Proven by the event contract lint gate | §24.1 gate 3 |
| **IAM-002** — authorization enforced in the domain application layer even when the UI hides an action | `EIP_MIRROR.md` lines 20953-20960; co-owned with MOD-008 | Proven by the permission lint gate | §24.1 gate 4 |
| **INV-GOV-01** — tenant isolation/finance/access tests release-blocking; every production artifact reproducible, signed, traceable to source and tests | `EIP_MIRROR.md` lines 21708-21715 | Proven by the full CI pipeline (GOV-01-R04) plus artifact signing specifically | GOV-01-R04 |
| **RB-GOV-01** — bad deployment/schema/config release rollback runbook | `EIP_MIRROR.md` lines 22386-22394 | A real, documented rollback runbook with the evidence-contract fields TSD names (affected tenant/scope, command/aggregate version, authoritative rows, outbox/inbox/DLQ/provider state, reconciliation result, repair/correction reference, owner/follow-up action) | GOV-01-R05 |
| **TSD §24.2 Database Migration Policy** | `TSD_MIRROR.md` lines 11655-11669 | Full text folded into GOV-01-R06 above | GOV-01-R06 |
| **TSD §24.3 Mobile Release Policy** | `TSD_MIRROR.md` lines 11670-11700 | Full text folded into GOV-01-R07 above | GOV-01-R07 |
| **Screens** | `EIP_MIRROR.md` lines 4273-4278; design bundle registry (`veyro-product-experience-design/project/veyro-registry-data.js`) | **Zero canonical V1 screens resolve to MOD-001.** See §4 below — real finding, not a gap. |  |

**Added after Scenario Review round 1 (P0-1, P0-2, P0-4) — the review's
own re-search this table invited turned up real gaps:**

| Obligation | Source | What MOD-001 must build | Ties to |
|---|---|---|---|
| **Forced-fallback model-assurance negative test** | `EIP_MIRROR.md` lines 1109-1111 (verbatim: "MOD-000 and MOD-001 must include a forced-fallback negative test proving that any unresolved/substituted lower tier becomes BLOCKED: MODEL_ASSURANCE_UNVERIFIED rather than PASS"); restated in the card's manual-QA field, lines 4197-4198 | A test proving a forced Opus→Sonnet substitution on an Opus-designated task reports `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`, never silent PASS | SCN-MOD001-075 |
| **~14 additional deliberate-violation drills named in the card's own manual-QA field** | `EIP_MIRROR.md` lines 4188-4228 — malformed/conflicting-path Rule; manifest missing mandatory profile; unregistered third-party Skill/plugin/MCP/hook; altered approved Skill version without re-evaluation; circular capability dependency; exhausted capability-resolution budget; overdue ACTIVE capability; MOD-029 manifest missing admin/privileged-console; H.3 standard removed for an H.2 family; inverted Appendix-B completing/slice row; generic Security baseline on a Tier-1 module; 4 scenario-matrix-validator fail-closed cases (O on §9.1 category, N without G.4, forbidden LOC/A11Y=N, PERF/Load inconsistency both directions); external-gate-validator card/registry/§22 mismatch plus its 2 conditional-edge cases; Appendix-I mapping/evidence removal | Each is a real, separately-buildable validator check MOD-001's `tools/` must implement and prove fails closed | SCN-MOD001-076 through 093 |
| **Dependency-vulnerability CI gate** | GOV-01-R04 itself (`EIP_MIRROR.md` lines 17556-17559: "CI gates for lint, test, **vulnerability**, schema compatibility, migration safety and artifact signing") — this is a Critical requirement's own text, not a secondary obligation, and the first draft of this table had no scenario for it | A real dependency-vulnerability scanner proven to block on a known-CVE fixture | SCN-MOD001-094 |

**Added after Scenario Review round 4 (P1-5, P1-6, P1-7, P1-8):**

| Obligation | Source | What MOD-001 must build | Ties to |
|---|---|---|---|
| **Import/validation contract (Appendix F Ready precondition)** | `EIP_MIRROR.md` lines 18033-18037 (verbatim: "Ready requires access to the canonical approved UX registry and the import/validation contract") | A documented schema/interface (not the generator itself — that is Implementation Complete work) defining how the eventual `screen-contracts.yaml` generator will consume the canonical registry: which registry fields it reads (`id, module, name, phase, status, roles, ar, note` per the registry's own 8-field format), how it resolves a multi-domain screen to its owning module, and what a validation failure looks like | `IMPLEMENTATION.md` §10 (new); SCN-MOD001-118 |
| **Appendix I: ADR-004 (REST/JSON+OpenAPI with surface BFFs) and ADR-015 (expand/migrate/contract schema evolution)** | `EIP_MIRROR.md` lines 21028, 21117 — both map MOD-001, both require "Module spec + tests/QA + `ADR_CONFORMANCE.md` + §18 ADR conformance PASS" | An `ADR_CONFORMANCE.md` record stating MOD-001's conformance state against both ADRs (ADR-004: MOD-001's own API surfaces, if any, follow REST/JSON+OpenAPI; ADR-015: the migration-safety harness itself follows expand/migrate/contract) | `ADR_CONFORMANCE.md`; `IMPLEMENTATION.md` §3 (`tools/validate_adr_conformance.py`, added round 5 P1-4); SCN-MOD001-119 |
| **`RUNBOOK.md`** | EIP card's own Required-outputs text (`EIP_MIRROR.md` line 4180-4181: "the module RUNBOOK.md where a domain is owned") — MOD-001 owns GOV-01 (line 11817) and `RB-GOV-01` (line 22386) | A real runbook document for `RB-GOV-01` ("bad deployment/schema/config release rollback") with the evidence-contract fields TSD names | `knowledge/03-Modules/MOD-001/RUNBOOK.md` (new); ties to GOV-01-R05/R06 |
| **CI/control check over `.claude/agents/` definitions and model-alias/MR-evidence well-formedness** | `EIP_MIRROR.md` lines 4121-4124: "CI/control checks validate all six TSD §24.1 architecture gates, **Veyro project-agent definitions, model aliases/MR evidence**, .claude/rules syntax/path scopes/conflicts..." — MR-evidence field list per §4.1 (`EIP_MIRROR.md` lines 1095-1100): task class, lifecycle role, risk triggers, intended family alias, resolved model identity, agent/session ID, verdict (7 fields) | A validator distinct from SCN-075's runtime-substitution test: (1) **reachability** — every registered implementation agent is named by at least one escalation path in `.claude/agents/*.md` (the exact class of defect `BUG-030` was — an agent whose escalation text silently failed to name it, per `BUG_REGISTRY.md`'s own text, not a reference to a nonexistent agent); (2) dangling-reference — no escalation path names an agent that doesn't exist; (3) MR evidence records carry all 7 required fields, structurally complete — **corrected, Scenario Review round 5 P1-2/P1-3: the original description here conflated (1) with (2) and understated (3)'s field count as 4** | `IMPLEMENTATION.md` §3 (`tools/validate_agent_definitions.py`, added round 5 P1-4); SCN-MOD001-120 |
| **Appendix H.1 manifest completeness** | `EIP_MIRROR.md` lines 20597-20601: manifest "must also record capability dependency IDs, per-gap resolution-attempt counters/budget evidence, lifecycle review state and rollback target where applicable" | `evidence/module-capabilities.yaml` must carry these four fields (explicit N/A with rationale where genuinely inapplicable, matching the file's own existing convention for `required_rule_ids` etc.) | `evidence/module-capabilities.yaml`; SCN-MOD001-121 |
| **Input/output data-exposure lint** (added, Scenario Review round 8, P0-1) | `EIP_MIRROR.md` lines 4267-4271 (card's mandatory Security-scope baseline: "input/output data exposure"); `IMPLEMENTATION.md` §6 — **round 5's own P0-2 finding miscounted this baseline's uncovered items as 3 and named only 2 (sensitive logging, abuse-negative); this third item was never caught until round 8** | Every OpenAPI response schema field explicitly declared (no undeclared/wildcard serialization); every request schema rejects extra/undeclared fields — a schema-level allowlist check distinct from the permission lint (action declarations, not field shape) and from SCN-029/122/043 (committed-file secrets, log statements, data-classification tagging respectively) | `IMPLEMENTATION.md` §1/§3 (`tools/validate_data_exposure.py`); SCN-MOD001-126 |
| **Sensitive-logging lint** (added, Scenario Review round 6, P1-1) | `EIP_MIRROR.md` lines 4267-4271 (card's mandatory Security-scope baseline: "sensitive logging"); `IMPLEMENTATION.md` §6 | No secret/PII-shaped pattern in log statements — a real, buildable static check, distinct from SCN-029's secret-scanning (which scans committed files, not log statements) | `IMPLEMENTATION.md` §1/§3 (`tools/validate_sensitive_logging.py`); SCN-MOD001-122 |
| **Abuse-negative fixture harness** (added, Scenario Review round 6, P1-1) | `EIP_MIRROR.md` lines 4267-4271 (card's mandatory Security-scope baseline: "abuse-negative scenarios"); `IMPLEMENTATION.md` §6 | The fixture pattern/harness later domain modules will build real abuse scenarios on top of (MOD-001's own obligation is the harness, not business-flow-specific abuse content) | `IMPLEMENTATION.md` §1/§3 (`tools/abuse_negative_fixture_harness.py`); SCN-MOD001-123 |

This table is not claimed exhaustive even now. A future session (or a
further Scenario Review round) should re-search both mirrors for
`MOD-001` before treating this list as final —
`EIP_MIRROR.md` alone has 490+ line-level hits for the string, the
majority of which are the templated `screen-contracts.yaml`/"must be
materialized by MOD-001" boilerplate repeated in every other module's
own card (§4 below explains why that boilerplate does not create
screen-content work for MOD-001 itself).

## 4. Screen/UX applicability, and MOD-001's real Ready precondition (Appendix F)

**Corrected (Scenario Review round 4, P1-5): the framing below was
wrong about which EIP text actually governs MOD-001's Ready condition.**
The original version of this section quoted the §21.2 card's own
generic "Screens" field boilerplate ("...before this module can be
Ready") — the same sentence, with only the surface name substituted,
that repeats near-verbatim across dozens of other module cards
(`EIP_MIRROR.md` lines 4553, 4641, 4860, 5164, 5273, 5365, 5449, 5539,
5620, 5696, 5775, 5863, 5942, 6025, 6131, 6246, and many more). It is
NOT the authoritative text for MOD-001's own Ready condition — Appendix
F is, and Appendix F's own MOD-001-specific row explicitly overrides
the boilerplate. The EIP's own changelog confirms this directly:
"Canonical screen mapping retained; v1.2 removes **the circular Ready
condition for MOD-001/non-UI modules**" (`EIP_MIRROR.md` lines
177-178), and "Appendix F Ready condition is scoped to UI-bearing
modules; **MOD-001 generates the manifest at Implementation Complete**;
non-UI modules prove no [screen ownership]" (lines 197-199).

**Appendix F's MOD-001 row, verbatim (`EIP_MIRROR.md` lines
18033-18043):** "Ready requires access to the canonical approved UX
registry and the import/validation contract. Generating
screen-contracts.yaml plus count/route/contract lint is a MOD-001
**Implementation Complete deliverable, not a Ready precondition**."

This means MOD-001's real Ready precondition on this axis has two real
parts, neither of which is "generate screen-contracts.yaml":

1. **"Access to the canonical approved UX registry"** — verified
   already satisfied: the canonical V1 design registry
   (`veyro-product-experience-design/`) is one of the four governing
   baselines, checked into this repository and hash-pinned in
   `PROJECT_INDEX.md` (manifest hash `c96f77ab...`, re-verified this
   session via `verify_baselines.py`, PASS). Appendix F's own
   project-wide release-gate text (`EIP_MIRROR.md` lines 18006-18009)
   makes this an explicit, separate requirement — "the canonical source
   artifact must be checked into or deterministically referenced by the
   Veyro repository before MOD-001 approval; screenshots, remembered
   names, inferred routes or newly invented identifiers are not
   acceptable substitutes" — and it already is, durably, not merely
   asserted.
2. **"The import/validation contract"** — **CLOSED this round (Scenario
   Review round 4).** This is a planning-stage deliverable (a documented
   schema/interface defining how MOD-001's eventual
   `screen-contracts.yaml` generator will consume the canonical
   registry — what fields it reads, how it resolves multi-domain
   screens, what a validation failure looks like), distinct from
   building the generator itself (which is Implementation Complete
   work, per Appendix F's own explicit carve-out). **Round 4 found the
   contract's design missing and closed the gap by authoring it in
   full: `IMPLEMENTATION.md` §10 documents the source registry's 8-field
   format, the 6-step import procedure (read, filter to `phase ===
   'V1'`, resolve surface, resolve owning module, multi-domain
   resolution, validation-failure shape), and `SCN-MOD001-118` (added
   round 4, `NOT EXECUTED` — it tests the generator that consumes this
   design, which does not exist until implementation begins) specifies
   the test that will prove the design against representative input
   once that generator exists.**
   The precondition is on the contract's *design* existing, per Appendix
   F's own carve-out that the generator/lint itself is Implementation
   Complete work — the design exists now; building and running the
   generator against it remains correctly out of scope for Ready.

**Zero canonical V1 registry screens resolve to MOD-001 as an *owned
surface*, independently confirmed** against the design bundle's own
screen registry (`veyro-product-experience-design/project/veyro-registry-data.js`,
170 screens across 6 surface sections: `ADMIN`, `FRONT DESK`, `COACH`,
`MEMBER`, `CONSOLE`, `BACKEND-ONLY`). `CONSOLE` (`CON-01` through
`CON-17`) is tenant support/ops/billing, owned by a support/ops/admin
module (most plausibly MOD-029, per
`.claude/rules/admin-privileged-console-baseline.md`), not MOD-001.
`BACKEND-ONLY` (`SYS-01` through `SYS-08`) are product business jobs
owned by their respective domain modules (MOD-015+), not MOD-001's
engineering-infrastructure scope. This "zero owned screens" finding is
unaffected by the correction above — it was always correct; what was
wrong was treating the *generic* boilerplate as MOD-001's Ready
condition instead of Appendix F's real, MOD-001-specific one.

**Conclusion:** MOD-001 owns zero screen-registry rows (unaffected).
Its real Ready precondition on this axis — the import/validation
contract's *design* (`IMPLEMENTATION.md` §10) plus the already-
satisfied canonical-registry-checked-in requirement — is now
**satisfied in full**, as of round 4's remediation. Generating
`screen-contracts.yaml` itself, with an explicit empty `MOD-001: []`
entry once built, remains correctly planned as Implementation Complete
work in `IMPLEMENTATION.md`, not a Ready precondition — that part of
the original conclusion was already right.
