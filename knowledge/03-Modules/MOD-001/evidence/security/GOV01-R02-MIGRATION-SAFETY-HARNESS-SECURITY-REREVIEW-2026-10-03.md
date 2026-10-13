# GOV-01-R02 Migration-Safety Harness: Independent Security Re-Review (2026-10-03)

**Date:** 2026-10-03
**Reviewer role:** veyro-security-reviewer (fresh-context independent security re-reviewer, read-only; dispatched by a new orchestrator lead session, not the implementation session or the prior reviewer session)
**Model:** claude-opus-5-5. No safeguard refusal and no model fallback occurred (see the model assurance section).
**Scope:** BUG-049 (the original review's P1-1) and P2-1 through P2-7 from `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-INDEPENDENT-REVIEW-2026-10-03.md`, checked against the current versions of the remediated files.
**Fresh-context statement:** The reviewer took no part in the original implementation, its remediation, or the first review. It relied only on their written records and on running the code itself.
**Workspace note:** There is no `AGENTS.md` in the workspace. The governance used is `CLAUDE.md`, `.claude/rules/**`, `DEVELOPMENT_CONSTITUTION.md` and `CAPABILITY_POLICY.md`.
**Persistence note:** The reviewer is read-only. The lead session persisted its returned text verbatim, adding only the model-assurance section and this note. The lead also confirmed NF-1 in the source (`migration_safety.py:472-495`).

**Verdict: BLOCKED.** One new P1 (NF-1). The four broken-rollback shapes named in BUG-049 (A–D) are now genuinely detected. But `verify_rollback` still reports clean on a rollback that drops the primary key and duplicates rows (a row-count change). In that case it reports `rows_checked=12` while 13 or 24 rows exist. The original P1-1 required fix also called for comparing constraints, and that was never implemented or disclosed.

---

## Files reviewed (SHA-256)

| File | SHA-256 | Note |
|---|---|---|
| `backend/tests/harness/migration_safety.py` | `94058301e6a5968917f2221aab914b54c1a72c4f8a2df28a04d5e367ad72bde6` | Matches the post-fix hash in BUG-049 |
| `backend/tests/integration/test_migration_safety_harness.py` | `d13edf33014263b2e9aed9df21bfc222c93f5b67a9e1668e27f3b3908258edd7` | Matches |
| `backend/tests/unit/test_migration_safety_harness.py` | `3689b9d9828185b6b430c6524d1c534bed0373fb53bc6167da67939c4c629160` | Matches (unchanged) |
| `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-049-migration-safety-rollback-verification-false-clean.md` | `7e504eb26c5b69eaf37b73247039c18a911905c56da08b9d16af5946422e4728` | |
| `knowledge/05-QA/BUG_REGISTRY.md` (BUG-049 row, line 77) | `201302cf824e6a29e780480e278622f614e61cd212c3de07f220eb0e1c4f6f10` | Whole-file hash |
| `knowledge/03-Modules/MOD-001/evidence/implementation/GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md` | `78f49ede668b4d341e5416653be10a3d4bc5d151133af22d20804bc2e4e526da` | |
| `backend/tests/harness/postgres.py` (supporting) | `3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67` | |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` (supporting; SCN-022 at line 633, SCN-070 at line 1518, SCN-113 at line 2223) | `b0b3462bed39456e16d3412b04e8ada2d14293eeedf88035ab2a6cdd8f52da94` | |
| Prior review (input) | `f6b7e41ef9d8e86ee49dd3df476c6f46b241c0c95ba1e8b712f48d9e9c4adf3d` | |

- **Repository state:** HEAD and `origin/main` are both `e516bedabf3d654ad3ae16d948b8f3522739ddc2`. The three harness files and the BUG-049, implementation and first-review records are all untracked (`??`).
- **Hash stability:** The three code files were re-hashed after every execution step and were unchanged.

## Environment and approved execution path

- **CAP-008:** `CAPABILITY_REGISTRY.md` line 23 shows the Colima binding **APPROVED** (2026-10-02, independent Opus re-review P0=0/P1=0), next review due 2026-12-31.
- **Colima:** `colima status` reported it already running (macOS Virtualization.Framework, aarch64, docker runtime). The reviewer did not start, stop or reconfigure it.
- **How everything ran:** Every database interaction went through `tests.harness.postgres.disposable_postgres()`. That fixture pins the CLI, isolates the docker config, checks the engine identity, uses a pinned image digest, publishes on loopback `127.0.0.1` only, generates the password at runtime, and runs the container with `--rm` plus a forced removal.
- **Data and spend:** Synthetic data only. No real member data, no paid service, no network deploy.
- **Containers:** Before and after every step the only container present was the pre-existing `frosty_bhabha`, which was not touched. The probe container `veyro-mod001-harness-d3618616` and every pytest-session container were reaped.

## Commands and results

1. **Targeted suite.**
   - Command: `cd backend && .venv/bin/python -m pytest tests/unit/test_migration_safety_harness.py tests/integration/test_migration_safety_harness.py -v`
   - Result: **22 passed in 1.84s** (`real 2.14s`), exit 0. That is 11 unit and 11 integration tests.
2. **Full backend suite.**
   - Command: `cd backend && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider`
   - Result: **141 passed in 18.93s** (`real 19.13s`). This matches the 141/141 claimed in BUG-049.
3. **Ruff.**
   - Command: `.venv/bin/ruff check` on the three files.
   - Result: `All checks passed!`, exit 0.
4. **mypy.**
   - Command: `.venv/bin/mypy` on the three files.
   - Result: `Success: no issues found in 3 source files`, exit 0.
5. **Independent probe script.**
   - What it was: `/tmp/veyro-r02-rereview/probes.py`, outside the repo and deleted afterwards. It used the harness API through `PYTHONPATH=. .venv/bin/python …` against one disposable container.
   - What each probe did: run the full sequence, then contract, then a broken or mutated rollback, then `verify_rollback`. The cycle and validation probes used `validate_post_contract` instead.
   - Result: exit 0. Results are in the table below.
6. **In-memory mutation testing.**
   - How it worked: a pytest plugin (`-p mutant_plugin`, under `/tmp`, deleted afterwards) re-executed a string-mutated copy of the harness source into the live module namespace before collection. The repo file was never written; the post-run SHA-256 was still `94058301…`.
   - What it ran against: `tests/integration/test_migration_safety_harness.py`, once per mutant.
   - Results are in the mutation table below.
7. **Diff/regression checks.** `grep diff_int_maps` over `backend/tests` and `backend/app`, and `ls .github` (No such file or directory).

### Probe results (executed)

| # | Broken-rollback shape | Result |
|---|---|---|
| A | `status_code` restored as `text` with correct digits | DETECTED, `ROLLBACK_VERIFICATION_FAILED` (status_code shape regressed) |
| B | Data correct, `NOT NULL` not restored on `status_code` | DETECTED (shape regressed) |
| C | `status` data clobbered | DETECTED (12 rows mismatched) |
| D | `status` column dropped | DETECTED (`column 'status' is missing`) |
| E | `status_code` values permuted | DETECTED |
| F | One row deleted | DETECTED (`row_set_changed=True`) |
| G | One row inserted (new id) | DETECTED (`row_set_changed=True`) |
| H | Rollback does nothing | DETECTED, named (`status_code` missing) |
| I | `status_code` re-added, all NULL | DETECTED, named (shape regressed) |
| J | Zero-row snapshot with the harness's broken rollback | DETECTED, named `EMPTY_SNAPSHOT` |
| K | All rows code 0, with the harness's constant-0 broken rollback | CLEAN. This is correct, not a false clean: the restored data really does equal the ground truth. |
| N1 | `status_code` restored as `bigint` | DETECTED |
| N2 | `status` retyped to `varchar(20)` | DETECTED (status shape) |
| N3 | `status` `NOT NULL` dropped | DETECTED (status shape) |
| N4 | One row's `status_code` mutated | DETECTED (1 row) |
| N5 | One row's `status` mutated | DETECTED (1 row) |
| N6 | One row's `status` given a trailing space | DETECTED |
| **N7** | **Primary key dropped** | **CLEAN (false clean)** |
| **N8** | **PK dropped, then one exact duplicate row inserted (12 → 13 rows)** | **CLEAN, `rows_checked=12` (false clean, row-count change)** |
| **N9** | **PK dropped, then every row duplicated (12 → 24 rows)** | **CLEAN, `rows_checked=12` (false clean, row-count change)** |
| N10 | `DEFAULT 0` added to `status_code` | CLEAN (not compared) |
| N11 | `CHECK (status_code >= 0)` added | CLEAN (not compared) |
| N12 | Extra column added by the rollback | CLEAN (not compared) |
| N13 | Positive control: correct rollback | CLEAN, `rows_checked=12` (expected) |
| N14 | `id` column retyped to `bigint` | CLEAN (`id` shape not compared) |
| P23a | Cycle: contract → correct rollback → contract | `violations == []` (expected) |
| P23b | Cycle: re-contract is a no-op | `['LEGACY_COLUMN_STILL_PRESENT']` (caught) |
| P23c | Cycle: re-contract corrupts one `status` | `STATUS_MISMATCH` (caught) |
| P23d | Cycle: re-contract drops a row | `ROW_SET_CHANGED`, `STATUS_MISMATCH` (caught) |
| P23e | Two cycles, the second rollback broken | DETECTED, `ROLLBACK_VERIFICATION_FAILED` |
| V1 | Post-contract: PK dropped, then a duplicate row inserted | `violations == []` (false clean in SCN-022 validation) |
| V2 | Post-contract: `status` `NOT NULL` dropped | `violations == []` (not checked) |

### Mutation results (the repo's integration tests run against weakened code)

| Mutant | Effect | Repo suite result |
|---|---|---|
| M1 | `status` shape check removed | **11 passed. Survives.** |
| M2 | `status_code` shape check removed | 1 failed. Killed. |
| M3 | Only `status_code` compared (status ignored) | 1 failed. Killed. |
| M4 | `row_set_changed` check removed | **11 passed. Survives.** |
| M5 | Empty-snapshot guard removed from `verify_rollback` | 1 failed. Killed. |
| M6 | `NOT NULL` ignored in the `status_code` shape comparison | **11 passed. Survives.** |
| M7 | NULL-value check removed | 11 passed. Survives, but acceptable: the shape check shadows it (defence in depth). |
| M8 | Empty-snapshot guard removed from `validate_post_contract` | 1 failed. Killed. |

---

## Findings (most severe first)

**P0:** none.

### P1

**NF-1 (new): `verify_rollback` collapses duplicate rows and never compares table constraints, so a rollback that drops the PK and multiplies rows is reported clean, with a wrong `rows_checked`.**

- **Where.** In `backend/tests/harness/migration_safety.py`:
  - `:472-481` builds `current: dict[int, ...]` keyed by `id`, so duplicate ids silently overwrite one another.
  - `:488` defines `row_set_changed` as set equality of ids, which is blind to multiplicity.
  - `:495` returns `rows_checked=len(expected)`, the snapshot count, not the live row count.
  - `ColumnShape` (`:251-262`) and `DataIntegritySnapshot` (`:291-304`) capture only `{data_type, not_null}` for two columns. They capture no PK, unique or CHECK constraints, no defaults, and no full column set.
- **Evidence.** Probes N7, N8 and N9 executed above: all three returned clean, and N8/N9 reported `rows_checked=12` against tables with 13 and 24 rows.
- **Why this is P1, not lower:**
  - **The original fix was not completed.** P1-1's required fix said to "Compare the full schema shape (columns, types, nullability, constraints)". Constraints were not implemented, and neither BUG-049 nor the docstrings disclose the omission.
  - **The brief's must-detect list includes it.** Row-count changes are explicitly on the list this re-review was asked to confirm.
  - **It is a realistic failure.** A rollback that rebuilds a table without its primary key (for example `CREATE TABLE … AS SELECT`, then re-adding `NOT NULL`) is a common real-world broken-rollback shape. It is exactly the class GOV-01-R02's security text treats as highest severity: data corruption reported as verified-correct.
- **Docstring overclaim.** `:439-443` says a result is returned "only when every check above agrees", and lists "the row set changed". Probes N8/N9 show a changed row multiset passes, and the returned `rows_checked` misstates what was verified.
- **Required fix:**
  - Compare the live `count(*)` to `len(snapshot.rows)`, and/or fail on duplicate ids.
  - Snapshot and compare table-level constraints, at minimum `pg_constraint` `contype` plus `pg_get_constraintdef` for the table.
  - Snapshot and compare column defaults (`pg_get_expr(adbin, adrelid)`) and the full non-dropped column set with shapes, including `id`.
  - Report the live row count in `rows_checked`.
  - Add negative tests for PK drop with a duplicate row, and for a PK-only drop.
  - If any of these comparisons is deliberately left out of scope, the docstring must say exactly which ones.

### P2

**NF-2 (new): three meaningful detector branches have no regression protection in the suite (surviving mutants M1, M4, M6).**

- The code handles all three correctly today: probes N2/N3, G and B all detected.
- But no repo test pins any of them:
  - a `status` shape regression;
  - an extra row with a new id (row-set growth);
  - a `NOT NULL`-only regression on `status_code` (shape B).
- Shape B is one of BUG-049's four named shapes, yet it is proven only by this review's probe, not by the suite. Silently weakening any of the three branches would still leave the suite green.
- **Fix:** add three negative integration tests (B, G, and N2 or N3).

**NF-3 (new): `validate_post_contract` (SCN-022's validation query) has the same multiplicity blindness and does not check the surviving column's shape.**

- `:367-376` uses an id-keyed dict and id set equality.
- Probe V1 (PK dropped plus a duplicate row) and probe V2 (`status` `NOT NULL` dropped after contract) both return `violations == []`.
- This does not invalidate SCN-022's literal steps (see the scenario mapping below), but it weakens "a validation query confirms data integrity".
- **Fix:** the same row-count and constraint/shape comparison as NF-1.

### P3

- **NF-4: dead code and stale docstrings.**
  - `diff_int_maps` (`:136-141`) is no longer called by `verify_rollback`; the only callers are the unit tests, at `unit/test_migration_safety_harness.py:39-52`. Its docstring ("Shared by `verify_rollback`'s mismatch detection") is false.
  - Three unit tests therefore cover dead code, while the live comparison has no unit test.
  - The `RollbackVerificationError` docstring (`:87-91`) still describes only "the just-restored legacy column's data".
- **NF-5: original-section overclaim kept without inline annotation.** The implementation evidence (`GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md:135-147`) still describes the pre-fix "diffs the restored column" behaviour. The Remediation section (`:285-349`) supersedes it, but the original section is not marked as superseded.
- **NF-6: P2-3 residuals.**
  - No negative cycle test in the suite. The fail-closed cycle behaviour is proven only by probes P23b–P23e.
  - Rollback still exists only for the contract phase (none for switch or expand), and this is not stated in the harness docstrings.

---

## Per-finding adjudication

| Finding | Adjudication | Evidence |
|---|---|---|
| **BUG-049 / P1-1** | **PARTIALLY RESOLVED** | **Fixed:** all four named shapes (A, B, C, D) are detected with a named error. Code: `migration_safety.py:452-466` (existence and shape) and `:468-494` (full two-column data). Probes A–D, N1–N6. Tests: `integration:194-232`. **Not fixed:** the required fix's "constraints" element was never implemented, and the row-multiplicity false clean is new (NF-1, probes N7–N9). The suite also does not pin shape B (NF-2). The docstring overclaim is only partly corrected (`:439-443`). |
| **P2-1** (empty or degenerate ground truth) | **RESOLVED** | `_require_nonempty_snapshot` (`:318-327`) is called at `:355` and `:450`. Tests: `integration:238-257`. Probe J gives a named `EMPTY_SNAPSHOT`. Mutants M5 and M8 are killed. Probe K (all code 0) is not a false clean, because the restored data really matches. The negative test's dependence on the fixture is acceptable: `seed_widgets` is deterministic (`:158-165`) and 8 of 12 rows have non-zero codes. |
| **P2-2** (unnamed failures) | **RESOLVED** | Missing column at `:452-454`, NULL values at `:476-479`, non-integer values at `:480-485`. Tests: `integration:264-289`. Probes H and I raise a named `ROLLBACK_VERIFICATION_FAILED`. No probe leaked a driver exception. |
| **P2-3** (upgrade → downgrade → upgrade) | **RESOLVED** (P3 residual NF-6) | `integration:295-310` exercises contract → rollback → verify → contract → validate. Probes P23b–P23e show a broken re-upgrade, or a broken second rollback, is caught. A negative cycle test and switch/expand rollback remain absent (NF-6). |
| **P2-4** (resumability, throttling, N-1 rolling-deploy coverage) | **LEGITIMATELY DEFERRED** | **Disclosure is precise:** `migration_safety.py:46-49` and `:189-194` (states that `throttle_s` is always 0 and that no interruption test exists), plus BUG-049 `:99-103`. **Governed home for N-1:** SCN-MOD001-113 (GOV-01-R06, `SCENARIOS.md:2223`, NOT EXECUTED). **Gap:** resumability and throttling (`database.md` control 8) have no dedicated tracked scenario or bug beyond the disclosures. Condition C3 asks for it to be recorded. **Safe:** it is not part of R02's acceptance criterion. |
| **P2-5** (no guard against a non-disposable database) | **LEGITIMATELY DEFERRED** (with condition) | **Disclosed** precisely at `integration:53-61` and BUG-049 `:104-108`. **Safe today:** the only caller is the `pg` fixture backed by `disposable_postgres()` (`integration:64-73`; `postgres.py:168-191`, loopback guard at `:182-183`, runtime password at `:170`). **Not tracked** anywhere beyond those two places. Condition C4 asks for a forward-binding note. |
| **P2-6** (SCN-070 mis-credit) | **RESOLVED** | Corrected in the implementation evidence at `:255-268`. The integration docstring (`:7-12`) is consistent. Remaining staleness in the original section is P3 only (NF-5). |
| **P2-7** (CI budget measured locally only) | **LEGITIMATELY DEFERRED** | Disclosed at implementation evidence `:276-283`. `.github/` does not exist, so **no CI run exists, and no CI evidence is claimed by this review.** The local timings (1.84s targeted, 18.93s full) are local evidence only, not CI evidence. |

## Supply chain, data and scope

- **No new dependencies.** psycopg and CAP-008 Colima are already registered, and CAP-008 is APPROVED. The image is pinned by digest at `postgres.py:46`.
- **No third-party capability is treated as trusted without qualification evidence.**
- **No credentials committed.** The password is generated at runtime and kept out of argv (`postgres.py:170-178`), and `DisposablePostgres.superuser_password` is `repr=False`.
- **Synthetic data only.** No real member data, no spend, no deploy.
- **Scope breadth.** The harness is no broader than its need, except as noted under P2-5: it accepts any connection, with mitigation by discipline only.

## Scenario mapping (no scenario is promoted by this review)

- **SCN-MOD001-022** (`SCENARIOS.md:633`, NOT EXECUTED).
  - The evidence supports its literal steps: the phases complete in order, switching before backfill is refused (`integration:111-136`), and the validation query passes on a correct run (`:139-151`).
  - NF-3 is a known weakness in how thorough that validation query is.
  - Promotion is the lead's decision through the governed process, and NF-3 should be weighed first.
- **GOV-01-R02 "detects a deliberately broken rollback" criterion** (no SCN ID of its own). Satisfied for the harness's own broken fixture and for shapes A–I. **Not satisfied as a general security control** while NF-1 stands.
- **SCN-MOD001-070** (`SCENARIOS.md:1518`). No credit from this slice; the correction from P2-6 is confirmed. It belongs to Slice 4's static ordering lint.
- **SCN-MOD001-113.** Not exercised. It is the governed home for P2-4's N-1 deferral.

## BUG-049 recommendation

**Not closure-eligible.** The four originally reported shapes are fixed and verified by execution. But the original P1-1's required remediation (constraint comparison) is incomplete, and the same defect family shows a new false clean (NF-1, row-count or duplicate-row change). Either:

- keep BUG-049 open, extend its scope to NF-1 and fix it there; or
- close BUG-049 for shapes A–D only after filing NF-1 as its own P1 bug.

Either way, a fresh independent re-review must follow. This review does not close BUG-049 and does not edit `BUG_REGISTRY.md`.

## Overall verdict

**BLOCKED.**

**Conditions to clear:**
- **C1:** fix NF-1 (row-count or duplicate detection, plus constraint, default and full column-set comparison, plus accurate `rows_checked`), with negative tests.
- **C2:** add the negative tests NF-2 asks for (shape B, an extra row, and a `status` shape regression) so that mutants M1, M4 and M6 are killed.
- **C3:** record the resumability/throttling deferral (P2-4) somewhere governed, either a bug or a scenario note, not only in a docstring.
- **C4:** record the P2-5 non-disposable-database limitation as a forward-binding item before any non-test reuse of the harness functions.
- **Recommended, not blocking alone:** NF-3 alongside C1, and NF-4 through NF-6.

## R04 / ADR-010 Amendment A2

Out of scope. It stays separate and **BLOCKED** (model-assurance stop, `R04-A2-MODEL-ASSURANCE-CHECKPOINT-2026-10-03.md`). No R04 code was read, run, edited or commented on.

## Constraints honoured

- **No repository files changed by the reviewer.** No implementation, test, knowledge, scenario, STATUS, registry, R04/ADR-010 or `knowledge/00-System` file was edited, created or deleted. Hashes of the three code files are unchanged after every run. The lead's only write is this new evidence file.
- **No commit or push.** HEAD is still `e516bed…`.
- **Temporary files removed.** The probe script and mutation plugin lived only under `/tmp/veyro-r02-rereview/`, which was deleted; `ls` confirms it is absent.
- **Execution stayed on the approved path.** Everything ran only through the approved CAP-008 Colima `disposable_postgres()` path: loopback, runtime password, synthetic data. Every container created was removed, and the pre-existing `frosty_bhabha` was not touched.
- **No owner-reserved action.** No spend, no real member data, no deploy.
- **No promotion or closure.** No scenario was promoted, no bug was closed, and no prior work was self-approved.

## Model assurance (filled in by the lead session)

- Command: `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-security-reviewer`
- Transcript: `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/cbb4090f-6c20-4fb4-b4cd-0abb490e1246/subagents/agent-a241099762a24730f.jsonl` (agentId `a241099762a24730f`)
- Transcript SHA-256: `ac4c37834a666d42a26066905e5bfcb7cb99858b87e26642d72a34eae55ed28b`
- Result: **PASS** (exit 0). Across 40 turns the transcript is 100% consistent on `claude-opus-5-5`, which matches the required `opus` tier. No safeguard stop and no fallback model was observed.
