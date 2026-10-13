---
doc: BUG-057
module: MOD-001
status: OPEN
priority: P1 (proposed; capability-governance and certification evidence boundary)
requirement: GOV-01-R03, GOV-01-R04, DC-19
scenarios: SCN-MOD001-029, SCN-MOD001-094, SCN-MOD001-134, SCN-MOD001-135, SCN-MOD001-136
---

# BUG-057 — third-party tools used before exact-scope capability approval

## Observed defect

`CAPABILITY_POLICY.md` requires an `APPROVED` registry row before a third-party
capability is used on real project work; only synthetic qualification drills
may touch an unapproved capability. The C06 source-boundary inspection found
that `gitleaks git --staged --redact=100` had already scanned staged Veyro
files during SCN-020 work with no gitleaks registry row. It also found prior
project reliance on Ruff, pytest and mypy without corresponding exact-scope
rows. This is a governance defect in the earlier use, not a claim that those
tools produced incorrect technical output. Historical evidence is preserved,
not retroactively approved or discarded by assertion.

Source: `M1-C-06-SCANNER-CAPABILITY-ROUTE-2026-10-09.md` §1.4; the two
SCN-020 evidence files named there record the staged gitleaks call.

## Current containment

CAP-009 (gitleaks 8.30.1) and CAP-010 (Ruff 0.16.9 including its `S` role)
are now registered as **QUALIFIED, not APPROVED**, with separate synthetic
positive/negative drills, upstream provenance and Linux artifact pins.
The MOD-001 manifest binds both so validators fail closed: six approval-field
errors remain, two capabilities × (not approved, no independent `approved_by`,
no valid `next_review_due`). Ruff lint/format and pytest were also invoked on
project test files during C06 preparation after the gap was identified; those
uses are disclosed as part of this defect, not excused by the synthetic-only
`S` and gitleaks drills. No further real-tree use of gitleaks, Ruff, pytest or
mypy is permitted while its exact-scope approval remains absent. Pytest now has a separate QUALIFIED-only draft row (CAP-011, see the 2026-10-09 pytest update below); mypy remains separately unregistered;
this filing does not silently qualify them or widen CAP-010 to cover them.

**2026-10-09 qualification update:** CAP-010 now has a dedicated synthetic Ruff lint/format drill (11/11 expected outcomes; `M1-C-06-RUFF-LINT-FORMAT-SYNTHETIC-QUALIFICATION-2026-10-09.md`). This extends qualification evidence only: CAP-010 remains QUALIFIED, not APPROVED, and historical project use is not retroactively authorized. At this checkpoint, pytest and mypy remained unregistered; the pytest addendum below supersedes that part.

**2026-10-09 pytest qualification update:** pytest 9.1.1 now has a separate exact-scope draft row, CAP-011, at QUALIFIED, not APPROVED, with its own synthetic drill (`M1-C-06-PYTEST-SYNTHETIC-QUALIFICATION-2026-10-09.md`). Still no pytest run on Veyro tests is permitted under it, historical project pytest use is not retroactively authorized, and mypy remains unregistered. CAP-011 currently qualifies only the isolated temp-fixture invocation, explicitly excluding Veyro tests, config and CI; approval of that narrow row alone would not satisfy the GOV-01-R01/R04 test stage. A synthetic analogue of the intended project-test invocation and exact-scope correction are mandatory before independent determination for real-tree reliance.

**2026-10-09 pytest target-scope update:** the synthetic analogue now exists (`M1-C-06-PYTEST-TARGET-SCOPE-SYNTHETIC-2026-10-09.md`; project-shaped temp tree, no Veyro file touched, all expected outcomes) and CAP-011 is corrected to state the **INTENDED** future local/CI Veyro `backend/tests` use (synthetic fixtures only, no real data) with bounded config/plugin rules. It found two limits the invocation must cover (explicit outside-root paths and their conftest are honoured; missing `testpaths` with no path argument falls back to cwd), so an explicit `realpath`-checked path is mandatory. CAP-011 remains QUALIFIED, not APPROVED; historical project pytest use stays unauthorised; no pytest run on Veyro files is permitted. Remaining dependencies: independent determination and APPROVED fields, a path-allowlist wrapper (not written), a hash-pinned CI install, CI-interpreter evidence. mypy still unregistered. `validate_capabilities.py` now reports nine approval-field errors (CAP-009/010/011 x not approved, no `approved_by`, no valid `next_review_due`), the intended fail-closed hold.

## Closure dependency

1. A separately authorised, fresh independent Opus capability-security
   determination must return an individual verdict for CAP-009 and CAP-010.
   A planned fifth review action is a requirement, not dispatch authority.
2. Only an actual APPROVED verdict followed by complete registry fields and
   passing capability/manifest validators permits real-tree or CI scanner use.
   Reconcile earlier scanner-derived scenario claims on their exact snapshots;
   no retroactive PASS is inferred.
3. Resolve pytest (CAP-011 drafted, QUALIFIED only, awaiting its own independent verdict) and
   mypy's (still unregistered) capability-policy applicability and
   registration/approval before relying on their output for a new governed
   gate. Do not create rows or reviews by analogy without scoped evidence.

This is MANDATORY_NOW because GOV-01-R03/R04 require real CI scanners and the
current capability validator correctly blocks them. It stays inside M1-C-06
and the existing compressed workstream; no new bounded operation or review
entitlement is created. Gate-2 F01–F14 remain closed, all C06 scenarios remain
NOT EXECUTED, and MOD-001 is not certified.
