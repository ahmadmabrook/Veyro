---
doc: MOD-001_MANUAL_QA
status: LIVE — PLAN ONLY (no implementation exists to QA yet)
module: MOD-001
updated: 2026-09-16 (Scenario Review round 6 pre-review check — SCN-122/123 mapping added, missing since round 5)
---

# MOD-001 — Manual QA Plan

Per DC-04 (Claude actual manual QA is mandatory — automation cannot
substitute) and the mission's instruction to derive real manual surfaces
rather than inventing consumer UI tests, since MOD-001 is
engineering-infrastructure, not consumer product.

## Planned manual-QA surfaces (once implementation exists)

1. **Local developer bootstrap** — a genuinely fresh clone of the repo,
   following only committed documentation, brought up to a running
   local environment (§2 of `IMPLEMENTATION.md`). Claude actually runs
   the bootstrap commands and observes the result, not just reads them.
2. **CI workflow behavior** — trigger a real PR (against a disposable
   branch/fixture, never against `main` or the governing baselines) and
   observe the GitHub Actions run through to completion, both a passing
   case and a deliberately-broken case per gate (§4 of `IMPLEMENTATION.md`).
3. **Environment setup (QA/staging)** — actually stand up the QA and
   staging environment configs and confirm they boot, using CAP-005
   (Browser, public/unauthenticated-endpoint scope) where a web surface
   exists to hit.
4. **Generated artifacts** — inspect a real signed build artifact,
   `screen-contracts.yaml`'s generated output, and a release-evidence
   record for the correct field set (`RB-GOV-01`'s contract).
5. **Failure diagnostics** — deliberately break a gate and confirm the
   failure message/report is genuinely actionable (names the file,
   line, and violation type), not just "FAILED".
6. **Migration drill** — a real Alembic expand→migrate→switch→contract
   cycle against a disposable QA database, plus a deliberately
   out-of-order destructive migration proven rejected.
7. **Release/rollback drill** — a real synthetic canary deploy-and-
   rollback cycle in staging (never real traffic/real Production).
8. **Mobile build/toolchain bootstrap** — using CAP-006 (iOS Simulator,
   stock-Apple-apps-only scope currently; MOD-001's own mobile toolchain
   matrix, once it exists, is a document/CI-convention check, not a real
   app build — MOD-006 owns the real mobile app).
9. **Model-routing qualification drill** — a real dispatch to
   `veyro-implementer` with a critical-slice task and a routine task,
   confirming escalation to `veyro-critical-engineer` fires correctly
   and doesn't over-fire. Executed — see
   `evidence/model-routing/ROUTING_DRILL_2026-09-14.md`'s "Corrected
   drill" section for the real result.

**None of this has been executed** — implementation has not started.
This is the plan `veyro-manual-qa` (Opus, fresh context) will execute
against once MOD-001 has real code to QA, per DC-04/DC-07 (fresh-context
QA, never the implementing session's own narrative).

## Scenario → manual-surface mapping (added, Scenario Review round 1, P1-8)

Every Required scenario in `SCENARIOS.md` — regardless of its own
"Automation" field — needs at least one real, Claude-driven execution
before MOD-001 approval, per Appendix G/§9.1/DC-05. This table maps
each of the 9 manual-QA surfaces above to the scenario IDs it will
actually execute, so no Required scenario is left with an implicit or
absent manual-execution path:

| Manual-QA surface | Scenario IDs it executes |
|---|---|
| 1. Local developer bootstrap | 001, 002, 003, 036, 071 |
| 2. CI workflow behavior | 004-015, 020, 023, 024, 034, 084-096, 098, 102, 103, 110, 111, 112 |
| 3. Environment setup (QA/staging) | 037, 038, 041, 049, 068, 069, 073, 074, 101 |
| 4. Generated artifacts | 017, 018, 042, 057, 063, 091, 093, 098 |
| 5. Failure diagnostics | 003, 011, 013, 019, 025, 038, 085-090, 106, 109, 116 |
| 6. Migration drill | 022, 059, 066, 070, 113, 114 |
| 7. Release/rollback drill | 044-048, 058, 060, 067, 072, 107, 108 |
| 8. Mobile build/toolchain bootstrap | 050-055, 099, 100, 115, 117 |
| 9. Model-routing qualification drill | 104, 105 |

**Corrected (Scenario Review round 2, P1-7): SCN-102-105 were entirely
absent from this mapping — fixed above (102/103 → surface 2; 104/105 →
new surface 9). 092 and 094 were double-listed inside both the `084-096`
range and the "remaining" list below — removed from the remaining
list, kept only in surface 2's range.** Remaining Required scenarios
not listed above (016, 021, 021b, 026-033, 035, 039, 040, 043, 056,
061, 062, 064, 065, 075-083, 097) are executed as part of the
CI-workflow-behavior surface (surface 2) by default, since they are
CI-gate/harness checks with no distinct manual surface of their own —
recorded explicitly here rather than left absent.

**Added (Scenario Review round 4, P1-7/P1-8): `SCENARIOS.md` Group N
(SCN-118 through SCN-121) was new this round and had no manual-surface
mapping at all — fixed:**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-118 (import/validation contract) | 2. CI workflow behavior | `IMPLEMENTATION.md` §10's import procedure is CI-invoked validation, same class as the other gate checks in surface 2 |
| SCN-119 (ADR-004/ADR-015 conformance) | 2. CI workflow behavior | §18 ADR-conformance check is a gate/lint, same class as surface 2's other CI checks |
| SCN-120 (agent-definition/MR-evidence validator) | 9. Model-routing qualification drill | tests agent-definition files and routing-evidence integrity, the same subject matter as surface 9 |
| SCN-121 (Appendix H.1 manifest completeness) | 4. Generated artifacts | `evidence/module-capabilities.yaml` is itself a generated artifact being checked for required-field completeness, same class as surface 4's other artifact inspections |

**Added (Scenario Review round 5, P0-2): SCN-122/123 were new this
round (closing the card's sensitive-logging/abuse-negative security-
baseline gap) and had no manual-surface mapping — fixed:**

| SCN-122 (sensitive-logging lint) | 2. CI workflow behavior | a static CI lint, same class as the other gate/lint checks in surface 2 (e.g. SCN-029's secret-leak detection) |
| SCN-123 (abuse-negative fixture pattern) | 2. CI workflow behavior | a harness-pattern scenario, same class as SCN-032's offline-fixture pattern, which this table's own catch-all already routes to surface 2 by default |
