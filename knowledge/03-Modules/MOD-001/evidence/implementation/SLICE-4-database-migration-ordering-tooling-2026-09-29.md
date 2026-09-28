---
doc: MOD-001_IMPLEMENTATION_SLICE_4
status: LIVE
module: MOD-001
updated: 2026-09-29
---

# MOD-001 implementation slice 4 — database-change policy/tooling (GOV-01-R06)

## What this slice is

The first MOD-001 implementation slice dispatched under autonomous
development mode (`OWN-006`/`ADR-007`), and the first slice after
`BUG-036`'s Round 6 closure removed the last disclosed local-execution
gap. Builds GOV-01-R06's IN-scope tooling: a migration-record template
capturing TSD §24.2's 4 required fields, and a stdlib-only lint
(`tools/validate_migration_ordering.py`) enforcing TSD §24.2's
expand→migrate→switch→contract phase ordering per logical change.

**Why this slice, this scope:** GOV-01-R02 (critical-slice territory —
tenant-isolation/RLS harness, authn negative-credential fixture — routed
to `veyro-critical-engineer` per `ADR-005` Decision 1, not this session's
to implement) and GOV-01-R04 (CI gates) both remain correctly blocked —
R04 specifically on GitHub-Actions-per-Action capability qualification,
per `STATUS.md`'s own standing note. GOV-01-R01's 3 remaining named gaps
(E2E, mobile UI, exploratory-testing procedure) were each checked and
found correctly non-actionable right now, not merely deferred by choice:
mobile UI has no real surface to test under the still-DEFERRED Android/iOS
Host profiles (`IMPLEMENTATION.md` line 340, `SCENARIOS.md` round-15
finding); E2E is architecturally tied to a staging deploy gate with "no
local equivalent" (`IMPLEMENTATION.md` line 347) and no staging
environment exists; the exploratory-testing procedure is already fully
documented (`MANUAL_QA.md` §10, authored Scenario Review round 12) and
its remaining step is a real `veyro-manual-qa` execution pass against a
*running* MOD-001 surface, which does not exist yet either. None of the
three is dependency-safe to force right now. GOV-01-R06 declares "none
beyond GOV-01-R04's CI wiring" as its own dependency, and — like Slices
1-3's validators — its actual acceptance criteria (a lint that rejects
out-of-order migrations, a valid sequence that passes) are fully checkable
locally without CI wiring itself existing yet. This is why R06, not R03/
R05/R07/R08, was picked as the next bounded, dependency-safe unit.

**Deliberately no new dependency:** TSD/`MANUAL_QA.md` surface 6 names
Alembic as the eventual real migration-drill tool, but no product schema
exists yet (R06's own "OUT of scope" line) to run Alembic against, and
`CAPABILITIES.md`'s own precedent for GOV-01-R01 explicitly defers
concrete-tool selection to real implementation rather than inventing a
stack this planning turn didn't mandate. What TSD §24.2 actually requires
right now — ordering discipline, a fixed record schema — is fully
checkable as a static lint with zero new dependencies, matching this
project's existing `validate_*.py` self-contained convention. Alembic (or
any other tool) can be introduced later, at the point a real schema
exists, without needing to change this lint's contract.

## Governing requirement

- `REQUIREMENTS.md` GOV-01-R06 ("Database-change policy/tooling"; TSD
  §24.2, verbatim: "Expand -> migrate/backfill -> switch reads/writes ->
  contract... Every migration records owner, expected lock/write impact,
  rollback/forward-fix strategy and data validation query.")
- Acceptance criteria per that section: "the lint rejects an out-of-order
  destructive migration; a valid 4-phase migration passes; rollback
  strategy is present and testable for at least the synthetic case" — all
  three proven below with real, synthetic fixtures (no real schema
  exists, per this requirement's own OUT-of-scope line).

## Routing

Not a registered critical slice (`ADR-005` Decision 1 scopes
`veyro-critical-engineer` to the tenant-isolation/RLS harness, the authn
negative-credential fixture, and the RLS+permission gates — none of
which this slice touches). Implemented directly by this orchestrating
session (Sonnet), per `OWN-003`'s existing operating model (the
orchestrating session executes routine, non-Opus-reserved work itself
rather than dispatching every slice to a separate agent) — no
architecture/ADR/gate-verdict-class decision was made unilaterally here.

## What was built

- `backend/migrations/TEMPLATE.md` — the migration-record template
  (6-field YAML front matter: `change_id`, `phase`, plus TSD §24.2's 4
  named fields).
- `backend/migrations/records/.gitkeep` — empty on purpose; no product
  schema exists yet, tracked so the directory itself is real.
- `tools/validate_migration_ordering.py` — parses every `*.yaml` record
  in a records directory (filename-sorted), fails closed on a missing/
  empty required field (`MISSING_REQUIRED_FIELD`), an unrecognized
  `phase` value (`INVALID_PHASE`), or a phase appearing for a `change_id`
  before its required predecessor phase (`OUT_OF_ORDER_PHASE`, naming the
  change_id, the phase found, and the phase it needed first). An empty or
  absent records directory is PASS, matching this requirement's own
  "no real schema exists yet" scope.
- `tools/tests/test_validate_migration_ordering.py` — 6 tests against
  isolated `tempfile.TemporaryDirectory` fixtures (never a real
  migrations tree): empty-directory PASS; a real valid 4-phase sequence
  PASS; a destructive contract attempted without a preceding switch
  (the acceptance criterion's own literal case) fails named; a missing
  required field fails named; an invalid phase value fails named; a
  repeated phase (two `expand` files before `migrate`) is correctly
  allowed, not flagged.

## Real execution (this session, not hand-traced)

```
$ backend/.venv/bin/python3 -m pytest tools/tests/ -v
...
tools/tests/test_validate_migration_ordering.py::test_empty_directory_passes PASSED
tools/tests/test_validate_migration_ordering.py::test_valid_four_phase_change_passes PASSED
tools/tests/test_validate_migration_ordering.py::test_contract_without_switch_fails_closed PASSED
tools/tests/test_validate_migration_ordering.py::test_missing_required_field_fails_closed PASSED
tools/tests/test_validate_migration_ordering.py::test_invalid_phase_value_fails_closed PASSED
tools/tests/test_validate_migration_ordering.py::test_repeated_phase_is_allowed PASSED
...
18 passed in 0.06s   # full tools/tests/ suite, all 3 validator test files combined

$ backend/.venv/bin/python3 tools/validate_migration_ordering.py
PASS — every migration record is complete and phase-ordered correctly (or no records exist yet).
```

Full backend regression re-run in the same session (unaffected by this
slice, confirmed not just assumed): `backend/.venv/bin/pytest -v` from
`backend/` — 4/4 scaffold-liveness fixtures PASS; `ruff check .` — all
checks passed; `mypy .` — no issues in 12 source files. Slices 1-3's own
validators re-run: `validate_baseline_binding.py` PASS,
`validate_capability_manifest.py` PASS (both MOD-000 and MOD-001
manifests), `validate_repo_skeleton.py` PASS (7/7 required paths — this
slice added no new required path, since `backend/migrations/**` is not
part of the skeleton-completeness manifest's current scope).

## Disclosed scope gaps

- **No real Alembic (or other) migration tool wired.** By design — see
  "Deliberately no new dependency" above. The lint's record format is
  tool-agnostic; a real migration framework can generate/consume records
  in this shape later without redesigning this validator.
- **Not wired into CI.** GOV-01-R04's CI gates remain blocked pending
  GitHub-Actions-per-Action capability qualification, same disclosed gap
  Slice 3 already carries for its own layers. This tool runs locally only
  for now, same as Slices 1-3's validators before Tier 1/`BUG-036`
  closed their own execution gap.
- **`records/` is empty.** No real product schema exists yet (this
  requirement's own OUT-of-scope line); the first real schema-owning
  module is expected to populate it, exercising this lint against real
  content for the first time.

## Not done this session

Code Review / Manual QA / Security Review / Performance Review /
Gatekeeper certification — none run, per the standing instruction not to
run these prematurely. `STATUS.md` updated to record this slice as
complete; MOD-001 remains **IMPLEMENTATION IN PROGRESS**, not Approved.
