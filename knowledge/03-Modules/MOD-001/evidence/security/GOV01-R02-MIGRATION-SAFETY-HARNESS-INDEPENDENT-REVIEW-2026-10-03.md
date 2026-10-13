# GOV-01-R02 Migration-Safety Harness — Independent Security Review (2026-10-03)

**Reviewer:** veyro-security-reviewer (Opus), fresh context, agentId `aecd2fcc231d5e33f` — no involvement in implementing this slice.
**Transcription note:** veyro-security-reviewer has no write tool (Read/Grep/Glob/Bash only). The lead session copied the review body below word for word from the reviewer's final report and filled in only the "Model assurance" section. The lead added no findings and changed no verdict.

**Verdict: BLOCKED.** There is one P1: rollback verification reports a clean result for rollbacks that regress the schema or lose data.

## Files reviewed (SHA-256 matches the implementer's claim)
- `backend/tests/harness/migration_safety.py` — `78afcb7d…fe9c4`
- `backend/tests/integration/test_migration_safety_harness.py` — `35b343f9…a6d`
- `backend/tests/unit/test_migration_safety_harness.py` — `3689b9d9…160`
- All three files are untracked (`??`). `backend/tests/harness/postgres.py` was read only to check the disposable-database path.

## Commands run and results
1. **Positive path.** `backend/.venv/bin/python -m pytest tests/unit/test_migration_safety_harness.py tests/integration/test_migration_safety_harness.py -v` gave **15 passed in 1.55s (1.91s wall)**. It ran on a disposable Colima `postgres:16-alpine` container, pinned by digest.
2. **Full suite.** `pytest tests/ -q` gave **134 passed in 18.71s (18.91s wall)**, with no regressions.
3. **Broken-rollback probes.** The reviewer wrote a temporary script in `/tmp/veyro-r02-probe/`, outside the repo, and deleted it afterwards. It ran against its own disposable container, `veyro-mod001-harness-c11d6349`, which was then removed. Each probe ran the full sequence, then contract, then a broken rollback, then `verify_rollback`:

| # | Breakage shape | Result |
|---|---|---|
| A | `status_code` restored as `text`, with the right digits | **RETURNED CLEAN** (false clean) |
| B | Data correct, but `NOT NULL` not restored | **RETURNED CLEAN** (false clean) |
| C | `status_code` correct, but rollback overwrites the `status` data | **RETURNED CLEAN** (false clean, data loss) |
| D | `status_code` correct, but rollback drops the `status` column | **RETURNED CLEAN** (false clean, data loss) |
| E | Values moved to the wrong rows | Detected, `ROLLBACK_VERIFICATION_FAILED` |
| F | One row deleted | Detected |
| G | One row inserted | Detected |
| H | Rollback does nothing | Fails, but unnamed (`UndefinedColumn`) |
| I | Column re-added with NULLs | Fails, but unnamed (`TypeError`) |
| J | Zero rows, using the harness's own broken rollback | **RETURNED CLEAN, rows_checked=0** |
| K | Every row has code 0, using the harness's own broken rollback | **RETURNED CLEAN** (the broken constant happens to match the data) |
| L | Upgrade, correct rollback, upgrade again | Works, but no test in the suite covers it |
| M | Data changed after the snapshot, then `validate_post_contract` | Detected, `STATUS_MISMATCH` |

4. **Fail-closed checks.**
   - Unreachable engine (`DOCKER_HOST=unix:///tmp/.../nonexistent.sock`): **4 errors, 0 skipped**, exit 1, `RuntimeError` at `postgres.py:92`.
   - Bad DSN (`127.0.0.1:1`): raises `OperationalError`.
   - Skip markers: none in `migration_safety.py` or the integration test, and none configured in `pyproject.toml`.
   - Swallowed exceptions: none in the harness. Its only `except` (`migration_safety.py:109`) re-raises as `ValueError`. `postgres.py:188-191` swallows only cleanup errors, after the primary failure has already surfaced.
   - Leftover containers: none from the harness. The pre-existing `frosty_bhabha` container was not touched.

## Findings

**P1-1 — Rollback verification only compares the values in one column, so it reports clean on schema regressions and data loss.**
- **Where:** `backend/tests/harness/migration_safety.py:355-361`.
  - `verify_rollback` selects only `id, status_code` (355-357).
  - It casts each value with `int(code)` (358), which hides the `text`-type regression in shape A.
  - It compares only against the snapshot's `status_code` (359-360).
  - It never checks column type, nullability, whether the `status` column still exists, or the `status` data.
- **Effect:** shapes A, B, C and D all return `RollbackVerificationResult`. C and D are destructive, data-losing rollbacks that are reported clean.
- **Overclaims, all disproved by execution:**
  - `migration_safety.py:31-35` says the harness "never silently 'passes' a broken rollback".
  - `migration_safety.py:349-354` says it returns a result "only when every row genuinely matches".
  - The implementer's evidence, `GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md:139-145`, repeats the claim.
- **Why it blocks:** GOV-01-R02's security-implications text treats any weakness here as highest severity. The acceptance criterion is met word for word for only one fixture shape: the constant-0 backfill at `:310-313` and `:329-336`, tested at `integration/test_migration_safety_harness.py:147-161`. It is not met by a general detector of rollback equivalence.
- **Required fix:**
  - Compare the full schema shape (columns, types, nullability, constraints) against a snapshot taken before contract.
  - Compare full row data for every column that should survive.
  - Add negative tests for at least one data-loss shape (C or D) and one shape a schema-only check would miss.
  - Correct the docstrings.

**P2-1 — Empty or degenerate ground truth passes as clean.**
- `verify_rollback` (`:362-367`) and `validate_post_contract` (`:264-292`) report clean when there are zero rows (probe J).
- Whether the harness's own broken variant is detected depends on the fixture containing codes other than 0 (probe K).
- The suite only guards against this indirectly, through `rows_checked == ROW_COUNT` at `integration:176` and in `test_scn022_full_sequence…` at `:136`.
- **Fix:** refuse an empty snapshot with a named error.

**P2-2 — Some failures are unnamed.**
- Shapes H and I fail with a raw `UndefinedColumn` or `TypeError` from `:355-358` instead of a `RollbackVerificationError`.
- This still fails closed, but breaks the "named, stable" contract that the docstring at `:72-79` promises.

**P2-3 — Upgrade → downgrade → upgrade is never tested.**
- No test runs `contract` again after `rollback_contract`; the integration file ends at `:177`.
- Probe L shows the sequence works, but the suite doesn't prove it.
- Rollback exists only for the contract phase. Switch and expand have none.

**P2-4 — TSD §24.2 coverage gaps.**
- Resumability and throttling are claimed (`:165-192`) but never exercised: there is no interrupted-backfill test, and `throttle_s` is always 0.
- §24.2 ¶4, rolling-deploy compatibility with the previous version (`.claude/rules/backend/database.md` control 9), is not covered.
- Neither is in R02's acceptance criterion. This is recorded so nobody assumes they are proven.

**P2-5 — Nothing stops the harness from running against a non-disposable database.**
- The harness functions accept any connection (`:134-140` and onward), and the test fixture runs `DROP SCHEMA … CASCADE` (`integration:71,75`).
- This is safe today only because the `pg` fixture is always `disposable_postgres()` (`integration:54-57`). That fixture enforces loopback and the Colima engine and generates a random password at runtime.
- No credentials are committed, and only synthetic data is used.

**P2-6 — The implementer's evidence credits rollback detection to SCN-070.**
- `GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md:253-257` files rollback detection under SCN-070.
- SCN-070 (`SCENARIOS.md:1518-1522`) is the lint for out-of-order destructive migrations. Rollback detection belongs to GOV-01-R02's acceptance criterion.
- The test file's own docstring (`integration:7-12`) draws this line correctly.

**P2-7 — CI budget measured locally only.**
- Local timings are 1.91s for this harness and 18.9s for the full suite, well inside the 15-minute smoke budget.
- The repo has no `.github/workflows` yet, so the budget on a real CI runner can't be proven.

## Supply chain, data and scope
- No new dependencies. The harness uses the already-registered psycopg and CAP-008 Colima, with the image pinned by digest at `postgres.py:46`.
- No real member data, no spend, no network deploys.
- Scope stays inside the GOV-01-R02 harness: no business logic, and no R04 or ADR-010 files changed.

## Model route (implementation)
- ADR-005 L121-124 explicitly excludes the migration-safety harness from the critical slices and routes it normally.
- None of the escalation triggers in `MODEL_ROUTING.md:109-116` apply.
- `veyro-backend-engineer` on Sonnet is therefore the correct route, and `veyro-critical-engineer` was not required.
- The implementer's own transcript was not checked with `mr_verify.py` in this review.

## Eligibility
- **SCN-022:** satisfied as written.
  - The phases complete in order, and switching before backfill is refused (`integration:101-126`).
  - The validation query confirms integrity on 12 rows (`:129-141`) and catches data changed after the snapshot (probe M).
  - It can be marked passed on its own terms, but the slice verdict is BLOCKED. The lead decides whether to promote SCN-022 before P1-1 is fixed. This review changes no scenario status.
- **GOV-01-R02 broken-rollback criterion:** NOT satisfied as a security control. The one fixture shape is detected, but four broken-rollback shapes pass clean (P1-1).
- **SCN-070:** this harness earns it no credit. Its static out-of-order proof comes from Slice 4 (`tools/validate_migration_ordering.py`, `SLICE-4-database-migration-ordering-tooling-2026-09-29.md`), and nothing in this slice adds to or re-proves it.

## Model assurance (filled in by the lead session)
- Command: `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-security-reviewer`
- Transcript: `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/04e763e1-c65f-4cdb-b8a7-f6d5b7a2ab44/subagents/agent-aecd2fcc231d5e33f.jsonl`
- Transcript SHA-256: `fcf05d3ffbf45fb63739e30cf9e93bfd672039fa488ee0af24b25aac40092a02`
- Result: **PASS** (exit 0). Across 34 turns the transcript is 100% consistent on `claude-opus-5-5`, which matches the required `opus` tier.

## Constraints honoured
- No implementation, test, scenario-status, STATUS, TEST_RESULTS, R04/ADR-010, bug-registry, or `knowledge/00-System` file was edited.
- No commit or push.
- Temporary files and containers were cleaned up.
