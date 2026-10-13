> **Lead transcription note (2026-10-03).** The review below was produced by the read-only
> `veyro-security-reviewer` Task agent (agentId `a3808f47640a91c01`, model route `opus`),
> spawned fresh-context by the orchestrating lead session. The reviewer had no Write tool,
> so the lead copied its final message into this file verbatim, with no content changes.
> After transcription the lead independently did the following:
> - **Model route re-run:** `/opt/homebrew/bin/python3.13 knowledge/05-QA/tools/mr_verify.py <agent transcript> opus veyro-security-reviewer` gave PASS, exit 0: "60 turn(s), 100% consistent, model 'claude-opus-5-5' matches required tier 'opus'". The transcript had 0 `"stop_reason":"refusal"` rows. Final transcript SHA-256: `40772bcf34123e84a10371a839c5e230cb4d781ef22b1945442a74d5f0b7dcdb`.
> - **NR3-1 code-read spot-check:** `backend/tests/harness/migration_safety.py:501-511` selects `id` unconditionally in both branches (`SELECT id, status …` and `SELECT id …`). This is consistent with the reviewer's finding.
> - **HEAD:** still `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.
>
> The lead edited no implementation file, promoted no scenario, closed no bug and made no commit or push.

**Editorial correction (lead, 2026-10-03):** Expanded the abbreviated BUG-049 path in the file-hash table to its existing literal path so evidence-integrity validation does not treat the abbreviation as a missing file. Findings and executed results are unchanged.

---

# GOV-01-R02 Migration-Safety Harness: Independent Security Re-Review Round 3 (2026-10-03)

**Date:** 2026-10-03. The session started at about 12:46 +03:00.
**Reviewer role:** veyro-security-reviewer. I acted as a fresh-context, independent, read-only security re-reviewer.
**Fresh-context statement:** I took no part in any of the following: the original implementation, the Round-1, Round-2 or Round-3 remediations, the original independent review, the Round-1 re-review, or the Round-2 re-review. I used their written records only as claims to test. Every result below comes from my own execution in this session, except where a line is marked "code-read".

**Model assurance (my own run):**
- **Command:** `/opt/homebrew/bin/python3.13 knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-security-reviewer`. This is Python 3.13.13, not the system python3 3.9.
- **Transcript:** `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/9c498e6b-9224-404a-9875-eff74262e804/subagents/agent-a3808f47640a91c01.jsonl`. Its `meta.json` shows agentType `veyro-security-reviewer` and model `opus`.
- **First run, before any review work:** PASS, exit 0, "9 turn(s), 100% consistent, model 'claude-opus-5-5'".
- **Second run, at the end:** PASS, exit 0, "58 turn(s), 100% consistent, model 'claude-opus-5-5'".
- **Transcript SHA-256 at the second run:** `5f08b0d8a0328a9bd09e6af3f2d3a320d8500c6828911ac051ce52651015e09e`. This hash will change as this final message is appended, so the lead should re-run the check after receiving it.
- **Stop reasons:** zero `"stop_reason":"refusal"` rows. There was no safeguard event, no fallback and no non-Opus route.

**Scope:** BUG-049's Round-3 remediation of the Round-2 re-review's findings: NR2-1 (P1), NR2-2, NR2-3 and NR2-4 (P2), and the P3 items NR2-5 to NR2-10. I also checked the C3/C4 deferrals, SCN-022 eligibility, and how SCN-070, SCN-066 and SCN-113 relate to this harness. R04, ADR-010 and Amendment A2 are out of scope; I did not read, run or comment on them.

**Read-only attestation:**
- I created, edited or deleted no repository file. The three code files and the BUG-049, BUG_REGISTRY and SCENARIOS files hash identically before and after the review.
- HEAD and `origin/main` are both `e516bedabf3d654ad3ae16d948b8f3522739ddc2` at start and end.
- I made no commit or push, promoted no scenario and closed no bug.
- All scratch files lived only in `/tmp/veyro-r3-review/`. I deleted that directory, and `ls` confirms "No such file or directory".

---

## Verdict: **BLOCKED** (P0 = 0, P1 = 0, P2 = 2, P3 = 4)

The Round-2 blocking P1 (NR2-1) is **resolved**, and so is NR2-2. Every one of the 12 required mutants is now killed by its intended test, as a call-phase assertion failure. There were no harness, collection, import or fixture errors.

The review still blocks, for one reason. **NR2-3 was only partly fixed, and the records say it was fully fixed.**
- `validate_post_contract` still leaks a bare `psycopg.errors.UndefinedColumn` when `id` is renamed or dropped after `contract`.
- That is exactly probe V12 from the Round-2 review, which was named explicitly in NR2-3's evidence.
- The function's own docstring, BUG-049, the BUG_REGISTRY row and the implementation evidence all state the leak is fixed for "a dropped or renamed `status`/`id` column".
- This fails closed, so it is not a false clean. It is an unresolved P2 inside BUG-049's own scope, plus a recurrence of the NR2-4 overclaim pattern (DC-10).
- Under DC-08 (`DEVELOPMENT_CONSTITUTION.md:63`), an open P2 prevents module certification. BUG-049 is therefore not closure-eligible.

---

## Files reviewed (SHA-256)

| File | SHA-256 | Against BUG-049's post-Round-3 claim |
|---|---|---|
| `backend/tests/harness/migration_safety.py` | `8d7a1bd9a098b50d134e3199b13a127ea7a37f3b0f60b961db5722555fe76b2e` | Matches |
| `backend/tests/integration/test_migration_safety_harness.py` | `79650a915aa7bc27fa5533f3e618bab608dcf4edd3c63f9e4d3ea19538c5f65c` | Matches |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` | Matches |
| `backend/tests/harness/postgres.py` | `3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67` | Same as Round-1 and Round-2 |
| `backend/tests/harness/authn.py` | `2dc6403648b9d3bab19a983a9878802a840f79948606ee85c5c17f827ce271be` | Not modified by this slice. Context only. |
| `backend/migrations/rls-manifest.json` | `913cf0836377e812c24a7dccc0f99f8703dda23b66cfa7f7b19b42b18d50b085` | Not touched by this harness. Context only. |
| `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-049-migration-safety-rollback-verification-false-clean.md` | `489b2bc1252a80429725c4482a5eb7f5bde1343072c48368ae543a05e895b74f` | n/a |
| `knowledge/05-QA/BUG_REGISTRY.md` | `023e03afdec26b83ea9b5512590eea60ab0dc0a46d8567d12359fcfc8bf1e842` | n/a |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` | `b0b3462bed39456e16d3412b04e8ada2d14293eeedf88035ab2a6cdd8f52da94` | Unchanged since Round-1 and Round-2 |
| `knowledge/03-Modules/MOD-001/STATUS.md` | `5aa499101f4cc0fc1e9c0f4aea7cee618f06357a14cc70c284ab8b195c01b22b` | n/a |
| `knowledge/03-Modules/MOD-001/TEST_RESULTS.md` | `c0cbf6dfa3de2bf3da7032a1a082ad8702cf273a526343a6b7b2d32e29997654` | n/a |
| `knowledge/03-Modules/MOD-001/evidence/implementation/GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md` | `01a299df5027b618c0100b6c37e727b09a974c534d83302141db0419229ef5d4` | n/a |

## Environment and database

- **Python:** `backend/.venv/bin/python` (3.14.5) for tests, Ruff and mypy. `/opt/homebrew/bin/python3.13` for `mr_verify.py` and JUnit parsing.
- **Colima:** already running (macOS Virtualization.Framework, aarch64, docker runtime, socket `~/.colima/default/docker.sock`). I did not start, stop or reconfigure it.
- **CAP-008:** `CAPABILITY_REGISTRY.md:23` shows it APPROVED, with the pinned digest `postgres@sha256:721873c3…`. The server reported 16.15.
- **How the database ran:** every database interaction went through `tests.harness.postgres.disposable_postgres()`:
  - published on loopback `127.0.0.1` only (`postgres.py:61`);
  - runtime-generated password;
  - `--rm` plus forced removal on exit.
- **No other database or backend was used.**
- **`docker ps -a`:**
  - before the review: only `frosty_bhabha` (`mikeh1975/tradingview-mcp:latest`), which I did not touch;
  - after every execution step and at the end: only `frosty_bhabha`. Every container I created was reaped.
- **Data:** synthetic only (integer ids 0–11 and the labels `inactive`, `active`, `pending`). No real member data, no spend, no deploy.
- **No CI claim.** `.github/` does not exist, so all timings are local only.

## Test run results

All commands ran with cwd `backend/` unless stated.

| # | Command | Result | Exit |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest tests/unit/test_migration_safety_harness.py tests/integration/test_migration_safety_harness.py -q -p no:cacheprovider` | **46 passed in 2.76 s** | 0 |
| 2 | Same files with `--collect-only -q` | 46 items: 15 unit (3+1+3+1+3+4 parametrized and plain) + 31 integration (counted by `def test_` in the file) | 0 |
| 3 | `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` | **165 passed in 20.02 s** | 0 |
| 4 | `.venv/bin/ruff check` on the 3 files (ruff 0.16.9) | `All checks passed!` | 0 |
| 5 | `.venv/bin/ruff check .` | `All checks passed!` | 0 |
| 6 | `.venv/bin/mypy` on the 3 files (mypy 2.3.1) | `Success: no issues found in 3 source files` | 0 |
| 7 | `.venv/bin/mypy .` | `Success: no issues found in 24 source files` | 0 |
| 8 | Mutation loop (see below), 16 runs including the `NONE` baseline | Table below. Baseline: 46 passed. | per run |
| 9 | `PYTHONPATH=. .venv/bin/python /tmp/veyro-r3-review/probes.py` (one disposable container, 11 probes) | Table below | 0 |
| 10 | `knowledge/05-QA/tools/run_regression.py` | **Not run.** It writes a run record into the repo. The latest record, `RUN_20261003T094409Z.txt`, predates this review. | n/a |

These numbers match BUG-049's Round-3 claims exactly: 46/46 (15 + 31) and 165/165, with Ruff and mypy clean (24 files).

## Mutation testing (in memory only)

**Method:**
- A pytest plugin at `/tmp/veyro-r3-review/mutant_plugin.py`, loaded with `-p mutant_plugin` and `PYTHONPATH=.:/tmp/veyro-r3-review`.
- In `pytest_configure`, the plugin read `migration_safety.py`'s source and applied the mutant's string replacements. Each replacement had to match exactly once, or the run would abort with `SystemExit`; none aborted.
- It then exec'd the mutated source into the already-imported module's namespace, before the test modules were collected.
- The repository file was never written; its hash is unchanged.
- Each run produced a JUnit XML file. I parsed it to check three things: (a) every failure is a `<failure>` (call phase), not an `<error>` (setup or collection); (b) the failing test is the intended one; (c) the failure is the intended assertion.

**Results:**
- Every run reported `errors=0` and `skipped=0`.
- The `NONE` baseline under the plugin gave 46 passed.
- No unit test failed under any mutant.

| Mutant | What it removes (exact in-memory edit) | Suite result | Killing test(s) and failure reason (file:line) |
|---|---|---|---|
| **N2** | `verify_rollback` constraint comparison (`if False and live_constraints != …`, at `:652`) | 2 failed / 44 passed, exit 1 | `test_rollback_verification_detects_pk_only_drop`: `Failed: DID NOT RAISE RollbackVerificationError` (`integration:471`). `test_rollback_verification_detects_a_check_constraint_added`: same (`:491`). **KILLED** |
| **N3** | `verify_rollback` default comparison (shape compared on `(data_type, not_null)` only, at `:646`) | 1 failed, exit 1 | `test_rollback_verification_detects_a_default_added_on_status_code`: DID NOT RAISE (`:511`). **KILLED** |
| **N4** | `verify_rollback` full column-set comparison (`:634`) | 1 failed, exit 1 | `test_rollback_verification_detects_an_extra_column`: DID NOT RAISE (`:527`). **KILLED** |
| **N6** | `verify_rollback` `id` shape (the `("id", snapshot.id_shape)` entry removed, at `:641`) | 1 failed, exit 1 | `test_rollback_verification_detects_id_retyped_to_bigint`: DID NOT RAISE (`:544`). **KILLED** |
| **P2** | `validate_post_contract` constraint comparison (`:490`) | 2 failed, exit 1 | `test_validate_post_contract_detects_pk_dropped_plus_duplicate_row`: `assert False = any(…startswith("TABLE_CONSTRAINTS_CHANGED"))` (`:572`). `…_detects_a_check_constraint_added`: same (`:607`). **KILLED** |
| **P3** | `validate_post_contract` default comparison (`:485`, compared on `(data_type, not_null)` only) | 1 failed, exit 1 | `…_detects_a_default_added_on_status`: `any(…"STATUS_SHAPE_REGRESSED")` is False (`:618`). **KILLED** |
| **P4** | `validate_post_contract` column-set comparison (`:472`) | 2 failed, exit 1 | `…_detects_an_extra_column` (`:629`) and `…_names_a_dropped_surviving_column_instead_of_raising` (`:677`): `any(…"COLUMN_SET_CHANGED")` is False. **KILLED** |
| **P5** | `validate_post_contract` `status` shape (loop reduced to `id` only, at `:476`) | 2 failed, exit 1 | `…_detects_status_not_null_dropped` (`:583`) and `…_detects_a_default_added_on_status` (`:618`): `any(…"STATUS_SHAPE_REGRESSED")` is False. **KILLED** |
| **P6** | `validate_post_contract` `id` shape (loop reduced to `status` only, at `:476`) | 1 failed, exit 1 | `…_detects_id_retyped_to_bigint`: `any(…"ID_SHAPE_REGRESSED")` is False (`:594`). **KILLED** |
| **P8** | `STATUS_MISMATCH` (`if False and mismatched`, at `:523`) | 1 failed, exit 1 | `…_detects_a_changed_status_value`: `any(…"STATUS_MISMATCH")` is False (`:643`). **KILLED** |
| **P9** | `LEGACY_COLUMN_STILL_PRESENT` append replaced by `pass` (`:468`) | 1 failed, exit 1 | `…_detects_legacy_column_still_present`: `assert [] == ['LEGACY_COLUMN_STILL_PRESENT']` (`:656`). **KILLED** |
| **P10** | P2 plus the row-count/duplicate `extend` replaced by `pass` (`:490`, `:513`) | 2 failed, exit 1 | Same two tests as P2 (`:572`, `:607`). **KILLED** |
| P1 *(extra)* | Row-count/duplicate `extend` only (`:513`) | **46 passed**, exit 0 | Survives. Equivalent or shadowed, as the Round-2 review accepted: duplicates need a PK drop, which `TABLE_CONSTRAINTS_CHANGED` catches; a lost or added row is caught by `STATUS_MISMATCH` or `ROW_SET_CHANGED`. Defence in depth that no test pins (residual, see below). |
| G1 *(extra, Round-3 guard)* | `_column_exists` shape-loop guard disabled (`:477`) | 1 failed, exit 1 | `…_names_a_dropped_surviving_column_instead_of_raising`: `AssertionError: expected exactly one row, got none` raised in the call (`:676`). **KILLED** (the NR2-3 regression this test exists to catch) |
| G2 *(extra, Round-3 guard)* | `status_column_exists = True` (`:501`) | 1 failed, exit 1 | Same test: `psycopg.errors.UndefinedColumn: column "status" does not exist` (`:676`). **KILLED** |

**Isolation check:**
- Each of N3, N4 and N6 fails exactly one test, which is its intended isolated test.
- N2 fails exactly the two constraint-isolated tests.
- No other test fails under any of them, so none of the five new rollback negatives is shadowed.
- In the unmutated code, each of the five also asserts the detail substring of the specific check it targets: `"table constraints changed"` at `:474` and `:494`, `"status_code column shape regressed"` at `:514`, `"column set changed"` at `:530`, and `"id column shape regressed"` at `:547`.
- This shows the intended check is the one that fires, not just that some check fires.

## Probe results (real CAP-008 disposable Postgres 16.15, 12 synthetic rows)

Each `validate_post_contract` probe ran the full sequence, then the snapshot, then `contract`, then the stated DDL. Each `verify_rollback` probe ran the full sequence, then the snapshot, then `contract`, then the correct `rollback_contract`, then the stated DDL.

| # | Function | Mutation | Outcome |
|---|---|---|---|
| V00 | validate_post_contract | Positive control | `[]` (clean), live = 12 |
| V10 | validate_post_contract | `status` dropped | Named: `COLUMN_SET_CHANGED:expected=['id', 'status'] got=['id']` |
| V11 | validate_post_contract | `status` renamed to `status2` | Named: `COLUMN_SET_CHANGED:…` |
| **V12** | validate_post_contract | **`id` renamed to `id2`** | **UNNAMED `psycopg.errors.UndefinedColumn: column "id" does not exist`** |
| **V12b** | validate_post_contract | **`id` dropped** | **UNNAMED `psycopg.errors.UndefinedColumn`** |
| **V12c** | validate_post_contract | **`id` and `status` both renamed** | **UNNAMED `psycopg.errors.UndefinedColumn`** |
| R00 | verify_rollback | Positive control | CLEAN, `rows_checked = 12` = live 12 |
| R10 | verify_rollback | `status` dropped | Named: `ROLLBACK_VERIFICATION_FAILED: column 'status' is missing after rollback` |
| R11 | verify_rollback | `status` renamed | Named: same |
| R12 | verify_rollback | `id` renamed | Named: `ROLLBACK_VERIFICATION_FAILED: column set changed after rollback …` |
| R12b | verify_rollback | `id` dropped | Named: same |

---

## Findings (most severe first)

**P0:** none. **P1:** none.

### P2

**NR3-1. NR2-3 is not fully resolved: `validate_post_contract` still leaks an unnamed `UndefinedColumn` when the surviving `id` column is renamed or dropped after `contract`.**

- **Where:** `backend/tests/harness/migration_safety.py:501-511`.
  - The Round-3 fix guards the shape loop (`:477`) and guards selecting `status` (`:501`).
  - Both row-query branches still select `id` unconditionally: `SELECT id, status …` at `:504` and `SELECT id …` at `:510`.
- **Evidence:** probes V12, V12b and V12c above. The Round-2 review's NR2-3 evidence listed V12 (`id` renamed) by name alongside V10 and V11.
- **Tests:** the only Round-3 test for this (`integration:664-677`) covers the `status`-dropped case only. No test covers a renamed `status`, a renamed or dropped `id`, or both.
- **Severity:** P2, the same as NR2-3. It fails closed, so it is not a false clean and loses no data. But it breaks the module's named, stable, machine-checkable failure contract (`:88-93`) on exactly the shape a prior review named.
- **Contrast:** `verify_rollback` handles every equivalent shape (R10–R12b) with a named error, because its column-set check (`:633-638`) raises before any row query.
- **Required fix:**
  - When `id` is missing, skip the row-level queries. `COLUMN_SET_CHANGED` already fires; optionally also emit an explicit `ID_MISSING` or `<COL>_MISSING`.
  - Add integration negatives for: `id` renamed, `id` dropped, and `status` renamed. Each should assert a returned, named violation and that no exception is raised.

**NR3-2. Records and a docstring overclaim the NR2-3 fix (DC-10). The NR2-4 overclaim pattern has recurred.**

- **Where:**
  - `migration_safety.py:453-457`, the docstring. It says that a dropped or renamed `status`/`id` column "previously leaked a bare `AssertionError` or `UndefinedColumn` instead of reporting the named `COLUMN_SET_CHANGED`", which implies both are now fixed.
  - BUG-049 `:299-305`: "fixing NR2-3's leaked exception … by branching on column existence and reporting `COLUMN_SET_CHANGED` instead of crashing".
  - BUG_REGISTRY header `:24-26` and row `:146`: "the exception-leak fixed by guarding with `_column_exists`".
  - Implementation evidence `:471-474`.
- **Evidence:** NR3-1. The lead's own spot-check covered only the `status` path (implementation evidence `:494-496`), which is why it was missed.
- **Required fix:** correct all four places when NR3-1 is fixed, or state the `id` limitation precisely if NR3-1 is deferred.

### P3

**NR3-3. The `validate_post_contract` missing-column test does not pin which column is named.**
- `integration:677` asserts only that some violation starts with `COLUMN_SET_CHANGED`.
- The violation text does carry `expected=[…] got=[…]`, so the column can be derived (probe V10). But a mutant that emitted wrong sets would survive.
- On the "named missing-column failure" requirement:
  - **`verify_rollback`: fully met.** Its message is `column 'status' is missing after rollback` (R10), and `integration:275` asserts `"status_code" in detail`.
  - **`validate_post_contract`: met in output, unpinned in the test.**
- Recommendation: assert `"status" not in got`, or emit `STATUS_MISSING`.

**NR3-4. The C3 paragraph in BUG-049 still carries its corrected-wrong sentence with no inline marker.**
- The sentence at `:219-221` ("no dedicated tracked scenario or bug of their own") is still in place.
- Its correction sits in a separate paragraph at `:248-255`, placed after the C4 section.
- A reader of the C3 section alone gets the wrong claim. Add an inline "(corrected below, NR2-7)" marker.

**NR3-5. "No-op re-contract" wording.**
- BUG-049 `:297-298` describes the V14 test as a "no-op re-contract".
- The test (`integration:646-656`) never calls `contract`, which its own docstring states correctly.
- Wording only.

**NR3-6. Residual disclosures.**
- **Typmod not disclosed (code-read):** the disclosed-residuals list at `migration_safety.py:621-626` omits the Round-2 review's typmod residual. `atttypid::regtype` at `:330` drops typmod, so a `varchar(n)` length change would go unseen. No current column has a typmod.
- **Legacy column short-circuits the schema checks:** while `status_code` is still present, `validate_post_contract` skips every schema check (`:467-469`). It still returns a non-empty result, so it fails closed. Informational.
- **P1 mutant still unpinned:** the row-count/duplicate check in `validate_post_contract` can be removed with the suite green (equivalent today, as above).

## Status of the prior Round-2 findings

| Item | Status | Evidence |
|---|---|---|
| **NR2-1 (P1)** | **RESOLVED** | Five isolated `verify_rollback` negatives exist (`integration:460-547`): PK-only drop, CHECK added, DEFAULT on `status_code`, extra column, `id` to bigint. Each asserts `ROLLBACK_VERIFICATION_FAILED` plus its own check's detail substring. N2, N3, N4 and N6 are each killed by exactly their intended test(s), with DID NOT RAISE. Nothing else fails, so nothing is shadowed. |
| **NR2-2 (P2)** | **RESOLVED** | Eight `validate_post_contract` negatives exist (`integration:557-656`), each asserting a specific named violation; V14 asserts exact list equality. P2, P3, P4, P5, P6, P8, P9 and P10 are all killed by intended assertion failures. |
| **NR2-3 (P2)** | **PARTIALLY RESOLVED, NOT CLEARED** | `status` dropped or renamed: now named (V10, V11; G1 and G2 killed). `id` renamed or dropped: still an unnamed `UndefinedColumn` (V12, V12b, V12c). See NR3-1. |
| **NR2-4 (P2)** | **RESOLVED for the cited claims; pattern recurred** | Count claims are now accurate (2 PK-plus-duplicate tests, 46 = 15 + 31, 165). The NF-3 "fixed the same way" claim is now true, because tests back it. A new overclaim exists for NR2-3 (NR3-2). |
| NR2-5 (P3) | Mostly resolved | Residuals disclosed at `:621-626` and `:363-365`. Typmod omitted (NR3-6). |
| NR2-6 (P3) | Resolved | FK wording corrected at `:359-363` and `:616-621`. |
| NR2-7 (P3) | Resolved, with placement nit | SCN-066 is now cited (BUG-049 `:248-255`). See NR3-4. |
| NR2-8 (P3) | Resolved | Superseded markers present in the implementation evidence at `:142-150` and `:174`, and in BUG-049 `:15-23`. |
| NR2-9 (P3) | Resolved | Unit docstring at `:1-9` and comment at `:54-60` corrected. |
| NR2-10 (P3) | Resolved | C4 notice now in the module docstring at `migration_safety.py:55-65`. |

## C3/C4 deferral assessment

- **C3 (resumability and throttling, P2-4): a legitimate deferral, properly recorded. It does not hide a gap.**
  - GOV-01-R02's acceptance criterion is "runs a synthetic expand/contract migration and detects a deliberately broken rollback". Resumability and throttling are not part of it.
  - The gap has a governed, Blocker-severity home: **SCN-MOD001-066** (`SCENARIOS.md:1445`, GOV-01-R06, NOT EXECUTED).
  - `migrate_backfill`'s docstring (`:233-238`) states that `throttle_s` is always 0 and that no test interrupts a backfill.
  - One caveat: the docstring's opening line ("an online, resumable, throttled loop") describes mechanism, not proof. Nobody may cite this harness as SCN-066 evidence.
- **C4 (non-disposable database): properly recorded. No technical enforcement, and that is disclosed.**
  - `grep` confirms the only importers of `migration_safety` are its own unit and integration test files.
  - The notice now lives in the module docstring, in BUG-049 `:229-246`, and in `integration:53-61`.
  - It is acceptable for test-only use and correctly forward-bound to any future importer.

## SCN-022 eligibility, and how it differs from SCN-070, SCN-066 and SCN-113

**SCN-MOD001-022** (`SCENARIOS.md:633`, NOT EXECUTED: a 4-phase migration on a disposable schema, phases complete in order, and a validation query confirms integrity):
- **Positive steps:** evidenced by `integration:111-136` (phases in order, with switch-before-backfill failing closed) and `:139-151` (validation returns `[]`).
- **Validation query's negative power:** now real and pinned by mutation (NR2-2 resolved).
- **Judgment:** substantively eligible on its literal steps. I recommend **not promoting it yet**: NR3-1 is an open P2 in the very validation function SCN-022 depends on, inside BUG-049's own scope. Promote once NR3-1 is fixed and a fresh review closes BUG-049, or once NR3-1 is split into its own tracked bug by an explicit decision. I have not promoted anything.

The three related scenarios cover different ground:

| Scenario | What it covers | Relation to this harness |
|---|---|---|
| **SCN-MOD001-070** (`:1518`, NOT EXECUTED in the catalog) | The **static** ordering lint (`tools/validate_migration_ordering.py`, Slice 4) rejecting a contract-phase migration that comes before its predecessors | Earns no credit from this harness. The harness's runtime `SWITCH_BEFORE_BACKFILL_COMPLETE` guard and its broken-rollback negative are different mechanisms. GOV-01-R02's "detects a deliberately broken rollback" has no SCN number of its own. |
| **SCN-MOD001-066** (`:1445`, Blocker, NOT EXECUTED) | Interrupting a large backfill and resuming from a checkpoint, with throttling | Not exercised. It is the governed home for C3. |
| **SCN-MOD001-113** (`:2223`, Major, NOT EXECUTED) | Rolling-deploy N-1 compatibility | Not exercised; this harness makes no claim to it. |

## Supply chain, data and scope

- **No new dependency or capability.** psycopg plus CAP-008 (APPROVED: pinned digest, loopback only, runtime credential, `--rm`). No third-party capability is treated as trusted without qualification evidence.
- **No credential committed.** The password is generated at runtime.
- **Synthetic data only.** No spend, no deploy, no network beyond loopback.
- **Scope breadth:** the harness functions accept any connection and run destructive DDL. This is mitigated by caller discipline only (C4), which is disclosed and acceptable for test-only use.

## Residual risks and required follow-ups

Required to clear the BLOCKED verdict:
1. Fix NR3-1 and add the three missing negatives (`id` renamed, `id` dropped, `status` renamed).
2. Correct the four NR3-2 overclaims.
3. A fresh, independent review must then confirm before BUG-049 is closed.

Recommended in the same pass:
- NR3-3 (pin the named column in the test);
- NR3-4 (inline correction marker);
- NR3-5 (wording);
- NR3-6 (typmod disclosure; optionally pin the P1 row-count check with a test where it is the only detector, if one can be constructed).

Standing residuals:
- No CI exists, so all evidence is local.
- Identity, collation, constraint-rename, duplicate-constraint and typmod changes are not compared; all but typmod are disclosed.
- Indexes and triggers are out of scope.
- The fixture is tiny (12 rows).
- Database safety relies on caller discipline.

## What was NOT done

- **No repository file was created, edited or deleted.** I wrote no review file; this text is for the lead to transcribe.
- **No commit or push**, no scenario promotion, no bug closure, and no registry, state or scenario edits.
- **`run_regression.py` was not run**, because it writes into the repo.
- **R04, ADR-010 and Amendment A2:** not read, run or commented on.
- **No CI claim.**
- **No database other than CAP-008 Colima** through `disposable_postgres()`. Colima was not started, stopped or reconfigured, and `frosty_bhabha` was untouched.
- **I did not re-run the Round-2 review's full 55-probe set or its 28-mutant set.** I ran the 12 required mutants plus 3 extra (P1, G1, G2) and 11 targeted probes.
- **No self-approval.** I had no prior work on this harness to approve.
