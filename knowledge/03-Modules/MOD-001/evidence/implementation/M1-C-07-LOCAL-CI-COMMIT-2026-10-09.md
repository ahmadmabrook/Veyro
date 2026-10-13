# M1-C-07 local CI candidate commit — 2026-10-09

Result: **COMMITTED LOCALLY (candidate, unreviewed, never run).**

- Commit: `22bb42464bf7569ed116836b10163fab01560959` (parent `e481b814a80923849dddfe7a49319112aae7b023`, tree `4fd77faed7d37cf5ce3b3344242fd79d88d51313`)
- New local-only ref: `refs/heads/m1-c07-candidate-20261009` (created with a zero-old-value `update-ref`, so it could not overwrite an existing ref; none existed).
- `main`, the shared index and the working tree were not changed. The commit was built from an alternate temporary index based on HEAD. No `git add -A`. Nothing pushed; no remote, branch default or PR touched. This is not a publication grant.

## Paths (9; `git diff HEAD..ref`)
A `.github/workflows/test-pyramid.yml`
A `tools/run_scoped_pytest.py`
A `tools/assert_ci_python313.py`
A `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt`
A `tools/validate_idempotency_contract.py`
A `tools/tests/test_validate_idempotency_contract.py`
A `contracts/idempotency/synthetic-widget-create.json`
M `backend/tests/harness/postgres.py` (B6 Linux route)
M `backend/tests/unit/test_harness_postgres_fail_closed.py` (B6 unit tests)

## Closure rationale
- Workflow-referenced scripts, lock and test source all exist as regular 100644 blobs in the commit; `knowledge/05-QA/tools/run_regression.py` exists at HEAD (HEAD version used, see below).
- The suites run whole directories; the committed tree holds only HEAD's tracked tests plus the two modified files. Imports of every committed test/harness resolve inside the committed tree (static check on an extracted tree; AST parse of all six committed `.py` files; JSON parse of the declaration). No test was executed for this step.
- Idempotency lint and its test import only stdlib and each other; the declaration path matches the workflow.

## Deliberately excluded
- Untracked C05/DOM-002 tests/harness (`tenant_context.py`, `concurrency.py`, `migration_safety.py`, `test_architecture_gate_rls.py`, concurrency/migration tests, contract scaffold tests). Not imported by anything committed.
- BUG-048 hunks in `harness/authn.py` and `test_tenant_isolation_harness.py` (not needed).
- Modified `run_regression.py`, `capability_drift_check.py`, `validate_migration_ordering.py` and its tests (SCN-070 / BUG-043..047 work; the regression job runs HEAD's version, whose local result is FAIL as the workflow already states).
- `requirements-typecheck-linux-x86_64-cp313.wheels.sha256`, `tools/tests/test_run_scoped_pytest.py`, `test_assert_ci_python313.py`, `m1c07_b6_route_check.py`: not referenced by any workflow job.

## Caveat for the reviewer
`backend/tests/harness/postgres.py` is mixed at file level: besides B6 it carries the BUG-051 `rm -f -v` teardown (which the workflow's comments rely on) and the DOM-002 R3/R4 container-token hunks. These cannot be split without editing code, which this call forbade, so they ride along. The reviewer must read the full `HEAD..ref` diff of that file.

## Content checks
- Staged blobs equal working-tree files (sha256 match for all 9).
- Grep of staged payload for secrets and personal paths: only hit is the labelled placeholder `SENTINEL_NOT_A_REAL_PASSWORD_x9`. No scanner was run.
- sha256 of committed blobs:
  - `.github/workflows/test-pyramid.yml` fa578f3e69aea25dd7e5387ee9254858e59afa3537ee610e99b347ce84331028
  - `tools/run_scoped_pytest.py` 626210e6f5c7385e7a4e7b1a07bfcf784494eb2fd014616f745da23f0abb88cb
  - `tools/assert_ci_python313.py` ea51c067d5d75ff2ba1bb7602e37a0a5c88f9908a18c40d957d65b825a4a3d9c
  - `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` 5e7596d408190a6103ffe1e3988f1c88ea33a34306302cc7de6f0570340e95de
  - `tools/validate_idempotency_contract.py` 3336e41c8355e4f45b4293197a3fb82e35c2d4d622f1de71b5fa5f916ae9f41c
  - `tools/tests/test_validate_idempotency_contract.py` f5d5fc135e1f4c880bfc04897829501967459c553ab9b718026f2f908a31d301
  - `contracts/idempotency/synthetic-widget-create.json` 6740955254f80864b7b65053b3309b7541aceff4e25256801e5d0c83c66c1be3
  - `backend/tests/harness/postgres.py` 2adb59210ff8ef8fd17aa33ab9514f492cf65b4c83a28a81333aea09870dd0cc
  - `backend/tests/unit/test_harness_postgres_fail_closed.py` c8f3378147dbbcbfdc75064ee975ffc066059f82ff7a1ff7dc12239ee8840ee0

## Remaining before any claim
Independent mandatory review of the commit; live Linux/CI execution of every job; own CAP row for the hosted-runner Docker engine (outside CAP-008 scope); CAP-011 approval. Until then: no CI result, no required status check, no scenario PASS, CAP-011 stays QUALIFIED — NOT APPROVED.
