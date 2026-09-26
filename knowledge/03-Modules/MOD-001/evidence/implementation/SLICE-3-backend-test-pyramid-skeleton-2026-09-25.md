---
doc: MOD-001_IMPLEMENTATION_SLICE_3
status: LIVE
module: MOD-001
updated: 2026-09-25
---

# MOD-001 implementation slice 3 — backend test-pyramid skeleton (GOV-01-R01)

## What this slice is

The first `backend/**`/CI-adjacent MOD-001 implementation slice, and the
first slice dispatched after `BUG-035` Round 5 closed (RULE-001..009
`APPROVED`/`ACTIVE`, unblocking `backend/**`/`infra/**`/CI implementation
per `ADR-005` Decision 2's pre-implementation condition). Builds the
first coherent increment of GOV-01-R01 (test-pyramid infrastructure,
`REQUIREMENTS.md` GOV-01-R01): the `backend/` Python repository skeleton,
directory conventions and runner configuration for 4 of the pyramid's
named layers (static/lint, unit, component, integration, contract), and
a skeleton-completeness validator.

**Why this slice, this scope:** GOV-01-R01 is dependency-safe ("none
beyond MOD-000's control-plane tooling" per `REQUIREMENTS.md`) and is
the first requirement in the module's own approved dependency order
(R02/R03/R04/R05/R07 all declare a dependency on R01; R06/R08 depend on
R04/R05 respectively). `SCENARIOS.md` Group A ("Repository skeleton,"
SCN-MOD001-001/002/003) scopes the skeleton itself as a distinct unit
from Group B's architecture gates (GOV-01-R04) and from the CI-wiring
half of the pyramid table (`IMPLEMENTATION.md` §3). This slice is
deliberately bounded to what is achievable without a new capability
qualification: it covers `backend/**` only (not `admin-web/`,
`frontdesk-web/`, `mobile/`, `contracts/`, `infra/`, or
`.github/workflows/` — each a separate future slice), and it proves the
pyramid layers **locally only** — no GitHub Actions workflow file is
created this slice. See "Disclosed scope gap: CI wiring deferred" below
for why.

## Governing requirement / scenario coverage

- `REQUIREMENTS.md` GOV-01-R01 ("test pyramid... directory conventions,
  runner configuration, and CI wiring"; evidence obligations: "a passing
  run of each layer's harness against a trivial/synthetic fixture" (HP)
  and proof the harness "correctly fails/blocks on a broken fixture"
  (NEG)).
- `SCENARIOS.md` SCN-MOD001-001 (HP, backend-portion only — the full
  scenario also names admin-web/frontdesk-web/mobile/contracts/infra/
  .github/workflows, none of which this slice builds), SCN-MOD001-002
  (VAL, local lint/type-check passes clean on the scaffold-only tree),
  SCN-MOD001-003 (NEG, fails closed on a missing required path).

## Routing

Not a registered critical slice (`ADR-005` Decision 1 scopes
`veyro-critical-engineer` to exactly the tenant-isolation/RLS harness,
the authn negative-credential fixture, and the RLS+permission gates —
GOV-01-R02/R04 territory, not this slice). Three dispatches, all Sonnet:

- `veyro-backend-engineer` — `backend/**` scaffold (per `ADR-005`
  Decision 2's Backend surface-profile activation).
- `veyro-test-author` — the pyramid-layer scaffold-liveness fixtures and
  the NEG-evidence attempt (deterministic test authoring).
- `veyro-implementer` — `tools/validate_repo_skeleton.py` (routine,
  outside the two activated surfaces, matching `MODEL_ROUTE.md`'s
  existing `tools/**` routing used for slices 1/2).

## Deliverables

**Backend skeleton** (`veyro-backend-engineer`): `backend/pyproject.toml`
(Python `>=3.13`, dev-only deps `pytest`/`ruff`/`mypy` — deliberately no
`fastapi`/`pydantic`/`sqlalchemy`/`alembic` yet, since no application
code exists to need them; `[tool.pytest.ini_options]` `testpaths =
["tests"]`; `[tool.ruff]`/`[tool.mypy]` minimal config), `backend/app/__init__.py`,
`backend/app/modules/__init__.py`, `backend/app/modules/_shared/__init__.py`
(docstring-only, no code, per `.claude/rules/backend/architecture.md`
control 3), `backend/tests/{unit,component,integration,contract}/__init__.py`,
`backend/.gitignore` (extends the secrets convention — `.env.local` never
committed, per `.claude/rules/infra/secrets.md`).

**Pyramid-layer fixtures** (`veyro-test-author`): one scaffold-liveness
test per layer — `backend/tests/{unit,component,integration,contract}/test_scaffold_live.py`,
each a single `assert 1 + 1 == 2` with a one-line docstring marking it as
scaffold proof, not product content.

**Skeleton validator** (`veyro-implementer`): `tools/validate_repo_skeleton.py`
(argparse CLI matching `validate_baseline_binding.py`'s conventions; a
`REQUIRED_PATHS` list seeded with exactly this slice's 7 real paths,
explicitly documented as growing with each future topology slice rather
than hardcoding the full future tree — a hardcoded full tree would make
the tool report a false `MISSING_REQUIRED_PATH` against legitimate
not-yet-built work); `find_missing_paths()` is a pure, directly-testable
function. `tools/tests/test_validate_repo_skeleton.py` proves both
directions against an isolated `tempfile.TemporaryDirectory` fixture
(never the real repo tree): all-present passes, one-file-missing names
that file, and — the scenario's own literal case —
`shutil.rmtree()`-ing the fixture's `backend/` directory correctly names
every nested required path individually, none silently dropped.

## Independent verification this session performed

I (the orchestrating session) read every file the three agents produced
in full (not taken on their say-so):

- `backend/pyproject.toml`: confirmed `testpaths = ["tests"]`, dev-only
  dependency group, no premature production deps.
- `backend/app/modules/_shared/__init__.py`: confirmed docstring-only, no
  code — correct under `architecture.md` control 3 (and control 5, which
  says an empty scaffold does not yet carry the domain-boundary
  constraints regardless).
- `tools/validate_repo_skeleton.py`: manually re-traced `find_missing_paths`
  against its own `REQUIRED_PATHS` list and confirmed the top-level-
  directory-deletion case (a `Path.exists()` check per nested path, not a
  single parent check) correctly produces one named entry per missing
  path rather than collapsing to a vague single line — agrees with the
  authoring agent's own trace, no discrepancy found.
- `tools/tests/test_validate_repo_skeleton.py`: confirmed all 3 test
  functions use an isolated `tempfile.TemporaryDirectory`, never the real
  `backend/` tree, and that test 3's `shutil.rmtree(root / "backend")`
  matches SCN-MOD001-003's own literal scenario text exactly.
- `git status`: confirmed only `backend/`, `tools/validate_repo_skeleton.py`,
  `tools/tests/`, and the one evidence file are new — no unexpected
  writes outside this slice's declared scope.

**Independently re-confirmed the guard block, not taken on trust:** ran
`python3 --version` and `python3 tools/validate_repo_skeleton.py` myself
via Bash. Both denied, identical text to what all three agents
separately reported: `PreToolUse:Bash hook error: BLOCKED:
DISALLOWED_FLAG_OR_SHAPE — python3 did not match its allowlisted
read-only shape`.

## Execution residual — PARTIALLY CLOSED 2026-09-26 (`BUG-036` Tier 1)

**Superseded update, 2026-09-26:** `BUG-036`'s Tier 1 owner patch
(commit `e971523c3a665020df601b685d8f4b092ead7052`) added
`tools/validate_repo_skeleton.py` and
`tools/tests/test_validate_repo_skeleton.py` to `bash_guard.py`'s
`_ALLOWED_PYTHON_SCRIPTS`. This session independently verified the
applied diff matched the drafted patch exactly, recomputed both scripts'
SHA-256 fresh (`162750a3e8a52afb93cf6ed3087df3814e7d5cd9150a1e152f3f11f8cdaf5d91`
and `bcae0d8a81fdd41972b5398f14ded7bed806cc6f8c1a274316095ab8aa2ed919`
respectively, both matching the guard's entries), ran the full 194-test
`bash_guard.py` regression suite (194/194 PASS), and **actually executed
both scripts for real**:

```
$ python3 tools/validate_repo_skeleton.py
======================================================================
MOD-001 REPOSITORY-SKELETON REQUIRED-PATH VALIDATOR
======================================================================

Root checked: /Users/ahmadmabrouk/Desktop/Veyro
Required paths checked: 7

PASS — all 7 required paths present.

$ python3 tools/tests/test_validate_repo_skeleton.py
PASS — all 3 tests passed.
```

**Both are real, observed PASS results** — the validator ran against the
real repo tree (not a mock), and its own unit-test file ran all 3 of its
isolated-fixture assertions for real, including the
`shutil.rmtree`-the-`backend/`-directory case, and reported PASS. Both
scripts' Group-A traceability (SCN-MOD001-001's backend-portion,
SCN-MOD001-003's fail-closed logic) now has genuine executed evidence,
not hand-tracing alone.

**Still not executed — Tier 1 does not cover this half:** the 4
`backend/tests/{unit,component,integration,contract}/test_scaffold_live.py`
scaffold-liveness fixtures need `pytest`, which has no command family in
the guard at all (`UNKNOWN_COMMAND` — confirmed by direct attempt this
session: `python3 -m pytest` and bare `pytest` both still denied,
unaffected by Tier 1, exactly as `BUG-036`'s own analysis predicted).
This is `BUG-036` Tier 2's scope, not yet built or reviewed — see that
bug's file for the current state (owner has confirmed `pytest`/`ruff`/
`mypy` not installed; Tier 2's guard extension is drafted, pending an
owner install decision and independent security review). The
NEG-evidence attempt in `SLICE-3-neg-fixture-proof-2026-09-25.md` (a
deliberately-broken fixture, denial attempts) also remains unexecuted for
the identical reason and is unaffected by this update.

**What IS now claimed, beyond the original slice:** `tools/validate_repo_skeleton.py`
and its own test file are proven correct by real execution, not only by
inspection. **What is still NOT claimed:** that `pytest` collects/runs
the 4 scaffold-liveness fixtures, or that `ruff`/`mypy` pass clean on
`backend/` — none of that is observed yet, and none of it can be until
Tier 2 lands.

## Historical residual record (accurate as of 2026-09-25, partially superseded above)

**None of this slice's Python was executed.** Same structural gap as
`BUG-025`/`SLICE-1`/`SLICE-2`: `.claude/security/bash_guard.py`'s
`python3` family (`_python_readonly`) only allows execution of 7
pre-existing SHA-256-pinned scripts; neither `tools/validate_repo_skeleton.py`
nor any file under `backend/` is on that list, and `pytest` has no
recognized command family in the guard at all (confirmed by direct code
inspection this session and independently by two of the three
dispatched agents). `rm`/`unlink` are also absent from the guard
entirely (`BLOCKED: UNKNOWN_COMMAND`), which is why the `pyramid-fixtures`
agent's temporary broken-fixture file could not be deleted — it was
written only to the session scratch directory (outside git, outside the
project tree) and never touched `backend/tests/`, so no cleanup gap
carries into the committed tree. See
`knowledge/03-Modules/MOD-001/evidence/implementation/SLICE-3-neg-fixture-proof-2026-09-25.md`
for the full, separately-documented NEG-evidence attempt (4 independent
denial attempts, byte-identical guard text each time).

## Disclosed scope gap: CI wiring deferred (new observation, not a new bug)

GOV-01-R01's own IN-scope text names "CI wiring" alongside directory
conventions and runner configuration. This slice deliberately does not
create any `.github/workflows/*.yml` file. Reason: `.claude/rules/infra/iac.md`
control 5 requires every `uses:` action referenced in any
`.github/workflows/**` file to be pinned to a commit SHA **and** to carry
an `APPROVED` `CAP-<NNN>` row in `CAPABILITY_REGISTRY.md` after clearing
the full `CAPABILITY_POLICY.md` 9-stage lifecycle — explicitly with "no
publisher-based carve-out," even for `actions/checkout`/`actions/setup-python`.
No such `CAP-<NNN>` row exists yet for any GitHub Action. Committing a
workflow file that GitHub Actions would execute on a future push, before
that qualification exists, would violate `iac.md`'s own fail-closed rule
("does not merge"). This mirrors `CAPABILITIES.md`'s own pre-existing
disposition for "CI pipeline execution" ("DC-19 supply-chain review for
any third-party Action used"). This is not filed as a new bug — it is a
direct, foreseeable reading of an already-`APPROVED` rule, not a defect
in it — but is recorded here so a future session does not silently
scaffold `.github/workflows/**` without first running that
qualification. The remaining GOV-01-R01 layers (E2E, mobile UI,
exploratory-procedure documentation) and all CI wiring remain future
slices.

## Traceability

- Requirement: GOV-01-R01 (`REQUIREMENTS.md` §1).
- Scenarios: SCN-MOD001-003 (NEG, fail-closed logic) now `EXECUTED —
  PASS` (2026-09-26, real run of `tools/validate_repo_skeleton.py` and
  its own test file, see above). SCN-MOD001-001 (partial — backend-portion
  only) and SCN-MOD001-002 (VAL — needs `ruff`/`mypy`, Tier 2) remain
  `NOT EXECUTED` — logic-traced only.
- Model routing: `veyro-backend-engineer`/Sonnet, `veyro-test-author`/Sonnet,
  `veyro-implementer`/Sonnet. No critical-slice or Opus role required.
- Related evidence: `SLICE-3-neg-fixture-proof-2026-09-25.md` (NEG-evidence
  attempt, full detail).
- Commit: recorded in this slice's own commit (see `CURRENT_HANDOFF.md`
  for the SHA).
