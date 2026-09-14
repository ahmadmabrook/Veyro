---
doc: MOD-001_TEST_PLAN
status: LIVE — DRAFT (planning stage)
module: MOD-001
updated: 2026-09-14
---

# MOD-001 — Test Plan

This is the test-execution plan corresponding to `SCENARIOS.md`'s
catalog and `IMPLEMENTATION.md`'s CI-gate specification. It names how
each Required scenario category will actually be exercised once
implementation exists; it does not itself contain results (see
`TEST_RESULTS.md`, empty pending implementation).

## Test layers and their harness (per GOV-01-R01, TSD §10)

| Layer | Harness | Blocking? (TSD §10) |
|---|---|---|
| Static/lint | Linter + the 7 architecture-gate validators (6 from TSD §24.1 plus the surface-profile-activation gate added per `ADR-005` — **corrected, Scenario Review round 2 P2**, was "6") | Blocking |
| Unit | `pytest` (backend), platform-native (mobile/web) | Required for meaningful logic |
| Component | Platform-native component test runners | Required per surface |
| Integration | Docker-composed Postgres/event/workflow/provider sandboxes | Required for integrations |
| Contract | OpenAPI/AsyncAPI schema-diff checker | Blocking for exposed contracts |
| E2E | A browser-driven or platform E2E runner (tool TBD at implementation time) | Required for user-visible modules — MOD-001 has none itself; harness only |
| Mobile UI | Platform-native (Compose UI test / XCUITest-equivalent) | Required per surface |
| Exploratory | Claude manual QA (`MANUAL_QA.md`) | Always mandatory |
| Security/privacy | SAST/dependency/secret scanners + RLS/permission gate fixtures | Mandatory for sensitive modules — MOD-001 is one |
| Load/resilience | CI-runner/environment smoke-load only (§5 of `IMPLEMENTATION.md`) | Mandatory for performance-sensitive modules and release gates |
| Regression | Every prior approved critical journey re-run | Always blocking before approval. **Corrected (Scenario Review round 2, P2): not "trivial"** — DC-11 becomes binding starting MOD-001 and requires re-running all 5 of MOD-000's own governance scripts plus its 194-test Bash-guard suite on every MOD-001 CI run (`SCN-MOD001-061`), a real, non-trivial obligation from MOD-001's first CI run onward, not a placeholder that becomes meaningful later. |
| Migration/DR | Alembic expand/migrate/contract harness + rollback drill | Blocking for schema/data/recovery modules |
| Localization/a11y | RTL lint + a11y lint tooling | Blocking for UI-bearing/shared-UI/mobile-qualification modules — MOD-001 builds the tooling; has no screens of its own to check it against |

## Execution status

**Not yet executed.** Implementation has not started. This table will
gain real pass/fail/evidence-path columns once MOD-001 implementation
exists and each layer's harness has actually run.
