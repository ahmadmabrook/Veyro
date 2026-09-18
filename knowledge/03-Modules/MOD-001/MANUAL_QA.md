---
doc: MOD-001_MANUAL_QA
status: LIVE — PLAN ONLY (no implementation exists to QA yet)
module: MOD-001
updated: 2026-09-19 (Scenario Review round 14 — corrected, P2-5: this
line had gone stale at round 13's own body edits — SCN-138/139 mapping
rows added, surface count corrected to 10, surface 10's negative proof
replaced with a real mechanical completeness check)
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
10. **Exploratory-testing procedure (added, Scenario Review round 12,
    P1-1)** — GOV-01-R01's 7th test-pyramid layer per
    `REQUIREMENTS.md`/`TEST_PLAN.md` line 27 ("Exploratory | Claude
    manual QA (`MANUAL_QA.md`) | Always mandatory"), distinct from
    surface 5 (failure-diagnostics, i.e. deliberately breaking a gate
    and checking the report). `veyro-manual-qa` (Opus, fresh context)
    performs one real, undirected exploratory pass over the running
    MOD-001 surfaces (no pre-scripted steps, Claude's own judgment
    about what to probe) and records what it found in a QA record
    that names each surface probed and what was checked on it.
    Positive proof (`SCN-MOD001-137`'s exploratory half): the
    exploratory pass runs and produces such a record. Negative proof
    (`SCN-MOD001-106`'s exploratory half — **corrected, Scenario
    Review round 13, P2-6: this previously described an informal "the
    record names concrete things" heuristic with no actual denial
    mechanism, unlike every other negative case in this catalog**):
    `veyro-manual-qa` is deliberately asked to probe a named list of
    surfaces but the resulting QA record omits one of them; a
    mechanical completeness check (the same class of presence check
    `SCN-MOD001-121`'s Appendix H.1 field-presence check already uses
    elsewhere in this catalog) diffs the record's named-surfaces list
    against the requested list and flags the missing surface by name
    — a real, checkable denial, not a judgment call about whether the
    record "looks" thorough.

**None of this has been executed** — implementation has not started.
This is the plan `veyro-manual-qa` (Opus, fresh context) will execute
against once MOD-001 has real code to QA, per DC-04/DC-07 (fresh-context
QA, never the implementing session's own narrative).

## Scenario → manual-surface mapping (added, Scenario Review round 1, P1-8)

Every Required scenario in `SCENARIOS.md` — regardless of its own
"Automation" field — needs at least one real, Claude-driven execution
before MOD-001 approval, per Appendix G/§9.1/DC-05. This table maps
each of the 10 manual-QA surfaces above (**corrected, Scenario Review
round 13, P2-2: was "9," stale since round 12 added surface 10 in the
same edit**) to the scenario IDs it will
actually execute, so no Required scenario is left with an implicit or
absent manual-execution path:

| Manual-QA surface | Scenario IDs it executes |
|---|---|
| 1. Local developer bootstrap | 001, 002, 003, 036, 071 |
| 2. CI workflow behavior | 004-015, 020, 023, 024, 034, 084-096, 098, 102, 103, 110, 111, 112 |
| 3. Environment setup (QA/staging) | 037, 038, 041, 049, 068, 069, 073, 074, 101 |
| 4. Generated artifacts | 017, 018, 042, 057, 063, 091, 093, 098 |
| 5. Failure diagnostics | 003, 011, 013, 019, 025, 038, 085-090, 106, 109, 116, 124 |
| 6. Migration drill | 022, 059, 066, 070, 113, 114 |
| 7. Release/rollback drill | 044-048, 058, 060, 067, 072, 107, 108 |
| 8. Mobile build/toolchain bootstrap | 050-055, 099, 100, 115, 117 |
| 9. Model-routing qualification drill | 104, 105 |
| 10. Exploratory-testing procedure | 106 (negative/manual half), 137 (positive/manual half) |

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
baseline gap) and had no manual-surface mapping — fixed (headers added
round 7, Editorial — this fragment previously had none and would not
render as a table):**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-122 (sensitive-logging lint) | 2. CI workflow behavior | a static CI lint, same class as the other gate/lint checks in surface 2 (e.g. SCN-029's secret-leak detection) |
| SCN-123 (abuse-negative fixture pattern) | 2. CI workflow behavior | a harness-pattern scenario, same class as SCN-032's offline-fixture pattern, which this table's own catch-all already routes to surface 2 by default |

**Added (Scenario Review round 7, P0-1/P1-5): SCN-124/125 were new this
round and had no manual-surface mapping — fixed:**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-124 (baseline-artifact-binding validator, remaining 4 conditions) | 5. Failure diagnostics | same validator/family as SCN-025, already mapped there |
| SCN-125 (GOV-01-R08 maintenance/customer-communication template) | 4. Generated artifacts | `RELEASE_TRAIN.md` is a generated/authored artifact checked for required-section completeness, same class as SCN-121's Appendix H.1 check |

**Added (Scenario Review round 8, P0-1): SCN-126 was new this round and
had no manual-surface mapping — fixed:**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-126 (input/output data-exposure lint) | 2. CI workflow behavior | a static CI lint against the committed OpenAPI contract, same class as the other gate/lint checks in surface 2 |

**Added (Scenario Review round 9, P0-1): SCN-127/128/129 were new this
round and had no manual-surface mapping — fixed:**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-127 (toolchain-matrix real-config validation, white-label/KMP fields) | 8. Mobile build/toolchain bootstrap | same surface as SCN-051's own toolchain-matrix check |
| SCN-128 (isolated-PR toolchain-upgrade qualification gate) | 2. CI workflow behavior | a CI gate check, same class as the other gate checks in surface 2 |
| SCN-129 (real-device smoke test, capability-adapter half) | 8. Mobile build/toolchain bootstrap | same surface as SCN-050's own offline-flow smoke-test half |

**Added (Scenario Review round 11, P1-1): SCN-130 through SCN-136 were
new in round 10 and had no manual-surface mapping at all — fixed:**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-130 (gate 3, event-contract owner-approval sub-clause) | 2. CI workflow behavior | an architecture-gates CI step, same class as SCN-008/019, already mapped there |
| SCN-131 (gate 6, domain-uniqueness shared-contract-exception sub-clause) | 2. CI workflow behavior | an architecture-gates CI step, same class as SCN-014/015, already mapped there |
| SCN-132 (six named domain suite scaffolds wired) | 2. CI workflow behavior | a CI-run pytest scaffold check, same class as the other CI-gate/harness checks in surface 2 |
| SCN-133 (financial-invariant test harness) | 2. CI workflow behavior | a CI-run pytest fixture check, same class as SCN-132 above |
| SCN-134 (SAST scanning) | 2. CI workflow behavior | a CI scanning-stage check, same class as SCN-094's dependency scanning, already mapped there |
| SCN-135 (container-image scanning) | 2. CI workflow behavior | same scanning-stage class as SCN-134 |
| SCN-136 (IaC scanning) | 2. CI workflow behavior | same scanning-stage class as SCN-134 |

**Added (Scenario Review round 11, P1-1, separately from the round-10
batch above — SCN-137 is round 11's own new scenario, not one of the
seven inherited from round 10; grouping it under that batch's header
was itself a round-11 defect, fixed at the source in round 12, E-2):**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-137 (GOV-01-R01 per-layer harness positive execution) | 2. CI workflow behavior (6 automated layers); 10. Exploratory-testing procedure (7th layer, corrected round 12 P1-1 — surface 5 is failure diagnostics, not exploratory testing) | same class as SCN-106/116 for the automated half, already mapped there; the exploratory half is surface 10's own subject |

**Added (Scenario Review round 13, P1-1): SCN-138/139 were new in
round 12 and had no manual-surface mapping at all — the exact gap
class round 11's own P1-1 found for SCN-130-136 one round earlier,
reproduced by round 12 for its own new scenarios — fixed:**

| Scenario | Manual-QA surface | Why |
|---|---|---|
| SCN-138 (gate 7, deferred-surface build/toolchain carve-out — positive) | 2. CI workflow behavior | an architecture-gates CI step, same class as SCN-102/103/112, already mapped there |
| SCN-139 (gate 7, deferred-surface build/toolchain carve-out — negative/boundary) | 2. CI workflow behavior | same class as SCN-138 above |
