# GOV-01-R02 Migration-Safety Harness: Independent Security Re-Review Round 2 (2026-10-03)

**Date:** 2026-10-03 (run from 12:17 to 12:23, +03:00)
**Reviewer role:** veyro-security-reviewer. I acted as a fresh-context, independent, read-only security re-reviewer.
**Fresh-context statement:** I took no part in the original GOV-01-R02 migration-safety harness implementation, its Round-1 or Round-2 remediation, the original independent review, or the Round-1 re-review. I used their written records only as claims to test. Every result below comes from my own execution in this session, except where a line is explicitly marked "code-read".
**Scope:** I reviewed the BUG-049 Round-2 remediation (NF-1 through NF-6) and conditions C1 to C4 from the Round-1 re-review, against these files:
- `backend/tests/harness/migration_safety.py`
- `backend/tests/integration/test_migration_safety_harness.py`
- `backend/tests/unit/test_migration_safety_harness.py`
- `backend/tests/harness/postgres.py` (supporting)

R04, ADR-010 and Amendment A2 are out of scope. I did not read, run or comment on them.
**Persistence note (lead session):** The reviewer is read-only. A new orchestrator lead session dispatched it (agentId `ac2083e2c1f4717aa`) and transcribed its returned text verbatim into this new file. The lead added only this note and the model-assurance section. The prior review files were not overwritten. The lead independently re-confirmed: the three code-file hashes; that HEAD and `origin/main` are `e516bed…`; that `/tmp/veyro-r02-round2-review` is absent; that only `frosty_bhabha` is present in `docker ps -a`; that the integration suite contains only two PK tests (`:346`, `:369`) and only one `validate_post_contract` negative (`:250`, empty snapshot); and that SCN-MOD001-066 exists at `SCENARIOS.md:1445`.

**Editorial correction (lead, 2026-10-03):** The command table's generic output-path placeholder was changed to prose because the evidence-integrity checker interpreted it as a literal missing file. The review finding and executed results are unchanged.

**Verdict: BLOCKED.** The shipped code now detects every broken-rollback shape I was asked to cover, including NF-1, and the positive controls are clean with `rows_checked` equal to the live row count. But condition C1 is not fully met:
- The PK-only-drop negative test that C1 explicitly required does not exist.
- Four of the five new NF-1 comparison elements (constraints, defaults, full column set, `id` shape) can each be deleted while the whole suite stays green. I confirmed on real Postgres that each deletion reintroduces a false clean.
- The NF-3 fix in `validate_post_contract` has no negative test at all.

---

## Files reviewed (SHA-256)

| File | SHA-256 | Against BUG-049's post-Round-2 claim |
|---|---|---|
| `backend/tests/harness/migration_safety.py` | `c51df06564c3833e4ff06032962464bbe49221e2494f41717db494fa9a1c5f01` | Matches |
| `backend/tests/integration/test_migration_safety_harness.py` | `d13829c604684221e402c13cbaa2f2b055f02d3575fe9606f48749a0641b5ab8` | Matches |
| `backend/tests/unit/test_migration_safety_harness.py` | `57ec706021c4e45a4e3d7fa08cc2f6c996482060b812c4527d4940ba6dcbd404` | Matches |
| `backend/tests/harness/postgres.py` | `3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67` | Same as the Round-1 re-review |
| `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-049-migration-safety-rollback-verification-false-clean.md` | `23513a7f0e79289ffcf9e5986cda6fbb54312d5a68532f13c689855fa31b6dec` | n/a |
| `knowledge/05-QA/BUG_REGISTRY.md` (BUG-049 row is line 106) | `288e381fa9b8d4da30e896f3b91083f1e0792b05840a5c0f2da975dbc8b9505b` | n/a |
| `knowledge/03-Modules/MOD-001/evidence/implementation/GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md` | `bed9c112cb33ad1b2b3a5e113ca0e472bc28861e2a4dcba3c779d00b846594ea` | n/a |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` | `b0b3462bed39456e16d3412b04e8ada2d14293eeedf88035ab2a6cdd8f52da94` | Unchanged since the Round-1 re-review |
| Original review (`…INDEPENDENT-REVIEW-2026-10-03.md`) | `f6b7e41ef9d8e86ee49dd3df476c6f46b241c0c95ba1e8b712f48d9e9c4adf3d` | Same as the Round-1 re-review recorded |
| Round-1 re-review (`…SECURITY-REREVIEW-2026-10-03.md`) | `9b636576d5f861c00f2e15cd2784bd8ac8bccdfac975a6df5d5c528e7e6a42d8` | n/a |

**Repository state:**
- HEAD and `origin/main` are both `e516bedabf3d654ad3ae16d948b8f3522739ddc2`, before and after the review.
- The three harness/test files, BUG-049 and the implementation evidence are untracked (`??`).
- `postgres.py`, `SCENARIOS.md` and `BUG_REGISTRY.md` are modified but uncommitted (`M`).

**Hash stability:** I re-hashed the three code files after the probe run, the mutation run, the mutant-confirmation run and the gate runs. They were byte-identical every time. The knowledge files were also unchanged at the end.

## Environment and containers

- **Python:** `backend/.venv/bin/python`. I did not use the system python3.
- **Colima:** `colima status` showed it already running (macOS Virtualization.Framework, aarch64, docker runtime, socket `~/.colima/default/docker.sock`). I did not start, stop or reconfigure it.
- **CAP-008:** `CAPABILITY_REGISTRY.md:23` shows it **APPROVED** (2026-10-02), with next review due 2026-12-31.
- **How the database ran:** every database interaction went through `tests.harness.postgres.disposable_postgres()`:
  - pinned CLI realpath and an isolated config directory;
  - engine identity checked before anything runs;
  - pinned image digest `postgres@sha256:721873c3…` (server reported 16.15);
  - published on loopback `127.0.0.1` only (guard at `postgres.py:182-183`);
  - runtime password from `secrets.token_urlsafe`, kept out of argv;
  - `--rm` plus forced removal on exit.
- **`docker ps -a` before:** only `frosty_bhabha` (`mikeh1975/tradingview-mcp:latest`, Up 45 hours). I did not touch it.
- **Containers I created:**
  - probe run: `veyro-mod001-harness-2ae68e84`;
  - mutant-confirmation run: `veyro-mod001-harness-d5c04b3c`;
  - FK probe: `veyro-mod001-harness-94650c86`;
  - about 32 pytest-module containers (mutation runs and gates).
- **`docker ps -a` after each step and at the end:** only `frosty_bhabha`. Every container I created was reaped.
- **No CI claim.** `.github/` does not exist, so every timing below is local evidence only.

## Commands and results

| # | Command (cwd `backend/` unless stated) | Result | Exit | Timing |
|---|---|---|---|---|
| 1 | `PYTHONPATH=. .venv/bin/python /tmp/veyro-r02-round2-review/probes.py` (harness API, one disposable container, 55 probes) | Table below | 0 | 4.15 s real |
| 2 | Mutation loop: `MUTANT=<m> PYTHONPATH=.:/tmp/veyro-r02-round2-review .venv/bin/python -m pytest -p mutant_plugin -p no:cacheprovider -q tests/integration/test_migration_safety_harness.py`, for `NONE` plus 27 mutants | Table below. Baseline `NONE` gave 17 passed. | per run | about 2.1 s per run |
| 3 | `PYTHONPATH=.:/tmp/... .venv/bin/python /tmp/.../mutant_probe.py` (each surviving mutant applied in memory, then run against the probe shape it should catch) | Table below | 0 | — |
| 4 | `PYTHONPATH=. .venv/bin/python /tmp/.../fk_probe.py` | FK added after rollback: DETECTED (`table constraints changed…FOREIGN KEY…`) | 0 | — |
| 5 | `.venv/bin/python -m pytest tests/unit/test_migration_safety_harness.py tests/integration/test_migration_safety_harness.py -q -p no:cacheprovider` | **32 passed in 2.17 s** (15 unit + 17 integration) | 0 | 2.49 s real |
| 6 | `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` | **151 passed in 19.70 s** | 0 | 19.89 s real |
| 7 | `.venv/bin/ruff check` on the 3 files | `All checks passed!` | 0 | — |
| 8 | `.venv/bin/mypy` on the 3 files | `Success: no issues found in 3 source files` | 0 | — |
| 9 | `knowledge/05-QA/tools/run_regression.py` | **Skipped.** It is not read-only: lines 145-149 always write a timestamped run record into the regression-runs directory. I confirmed no new `RUN_*` file appeared during this review (the latest, `RUN_20261003T085453Z`, predates it). | n/a | n/a |

**How the mutation harness worked:** a pytest plugin's `pytest_configure` re-executed a string-mutated copy of `migration_safety.py`'s source into the live module namespace before test collection. Each mutation had to match exactly once or the run aborted. The repository file was never written; its hash was unchanged after the run.

## Probe results (real disposable Postgres 16.15; 12 synthetic rows)

Each `verify_rollback` probe ran: full expand/backfill/switch, then snapshot, then `contract`, then the correct `rollback_contract`, then the stated mutation, then `verify_rollback`. "pre" rows changed the table before the snapshot was taken. Every `validate_post_contract` probe ran: full sequence, then snapshot, then `contract`, then the mutation, then `validate_post_contract`.

| # | Function | Mutation | Outcome | Named error / violations (truncated) | rows_checked | Live rows |
|---|---|---|---|---|---|---|
| R00 | verify_rollback | **Positive control:** correct rollback | CLEAN | — | 12 | 12 |
| R01 | verify_rollback | PK dropped only | DETECTED | `ROLLBACK_VERIFICATION_FAILED`: table constraints changed (`['PRIMARY KEY (id)']` → `[]`) | — | 12 |
| R02 | verify_rollback | PK dropped + 1 exact duplicate (12→13) | DETECTED | same (constraint check fires first) | — | 13 |
| R03 | verify_rollback | PK dropped + every row duplicated (12→24) | DETECTED | same | — | 24 |
| R04 | verify_rollback | `DEFAULT 0` added on `status_code` | DETECTED | status_code shape regressed (default) | — | 12 |
| R05 | verify_rollback | `DEFAULT 'x'` added on `status` | DETECTED | status shape regressed | — | 12 |
| R06 | verify_rollback | `DEFAULT 0` added on `id` | DETECTED | id shape regressed | — | 12 |
| R07 | verify_rollback | pre: `status DEFAULT 'inactive'`; rollback removes it | DETECTED | status shape regressed (default `'inactive'::text` → None) | — | 12 |
| R08 | verify_rollback | pre: same default; rollback changes it to `'active'` | DETECTED | status shape regressed | — | 12 |
| R08c | verify_rollback | Control: pre default kept | CLEAN | — | 12 | 12 |
| R09 | verify_rollback | Extra column added | DETECTED | column set changed | — | 12 |
| R10 | verify_rollback | `status` dropped | DETECTED | `column 'status' is missing after rollback` | — | 12 |
| R11 | verify_rollback | `status` renamed | DETECTED | `column 'status' is missing` | — | 12 |
| R12 | verify_rollback | `id` renamed | DETECTED | column set changed | — | 12 |
| R13 | verify_rollback | `id` → bigint | DETECTED | id shape regressed | — | 12 |
| R14 | verify_rollback | `status_code` → bigint | DETECTED | status_code shape regressed | — | 12 |
| R15 | verify_rollback | `status_code` → text | DETECTED | status_code shape regressed | — | 12 |
| R16 | verify_rollback | `status` → varchar | DETECTED | status shape regressed (`character varying`) | — | 12 |
| R17 | verify_rollback | `status_code` DROP NOT NULL | DETECTED | status_code shape regressed | — | 12 |
| R18 | verify_rollback | `status` DROP NOT NULL | DETECTED | status shape regressed | — | 12 |
| R19 | verify_rollback | `id` DROP NOT NULL (needs PK drop first) | DETECTED | id shape regressed | — | 12 |
| R20 | verify_rollback | pre: `status` nullable; rollback SET NOT NULL | DETECTED | status shape regressed | — | 12 |
| R21 | verify_rollback | pre: `id` nullable, no PK; rollback SET NOT NULL | DETECTED | id shape regressed | — | 12 |
| R21c | verify_rollback | Control: pre `id` nullable, left unchanged | CLEAN | — | 12 | 12 |
| R22 | verify_rollback | pre: `status_code` nullable; the harness's own rollback forces NOT NULL | DETECTED | status_code shape regressed. Correct: the rollback does not reproduce the original shape. | — | 12 |
| R23 | verify_rollback | `CHECK (status_code >= 0)` added | DETECTED | table constraints changed | — | 12 |
| R24 | verify_rollback | `UNIQUE (id, status)` added | DETECTED | table constraints changed | — | 12 |
| R25 | verify_rollback | PK replaced by `UNIQUE (id)` | DETECTED | table constraints changed | — | 12 |
| R26 | verify_rollback | `widget_pkey` redefined, same name, as `PRIMARY KEY (id, status_code)` | DETECTED | table constraints changed | — | 12 |
| R27 | verify_rollback | pre: CHECK `ck_status`; same name redefined | DETECTED | table constraints changed | — | 12 |
| R28 | verify_rollback | pre: CHECK `ck_status`; renamed only | **CLEAN** | — (names are not compared) | 12 | 12 |
| R29 | verify_rollback | pre: CHECK `ck_status`; identical-definition duplicate added under a new name | **CLEAN** | — (frozenset collapses identical definitions) | 12 | 12 |
| R30 | verify_rollback | CHECK added `NOT VALID` | DETECTED | table constraints changed | — | 12 |
| R31 | verify_rollback | `id` made `GENERATED ALWAYS AS IDENTITY` | **CLEAN** | — (`attidentity` is not compared) | 12 | 12 |
| R32 | verify_rollback | `status` collation changed to `"C"` | **CLEAN** | — (`attcollation` is not compared) | 12 | 12 |
| R33 | verify_rollback | `status_code` re-added as a stored generated column | DETECTED | status_code shape regressed (generation expression shows as default) | — | 12 |
| R34 | verify_rollback | One row's `status_code` changed | DETECTED | 1 row mismatched | — | 12 |
| R35 | verify_rollback | One row deleted | DETECTED | `row count changed: expected 12, found 11` | — | 11 |
| R36 | verify_rollback | The harness's `rollback_contract_broken` | DETECTED | 8 rows mismatched | — | 12 |
| R37 | verify_rollback | Unique index (not a constraint) added | CLEAN | Disclosed as out of scope (indexes) | 12 | 12 |
| R38 | verify_rollback | Trigger added | CLEAN | Disclosed as out of scope (triggers) | 12 | 12 |
| R39 | verify_rollback | FOREIGN KEY added | DETECTED | table constraints changed | — | 12 |
| V00 | validate_post_contract | **Positive control** | CLEAN `[]` | — | n/a | 12 |
| V01 | validate_post_contract | PK dropped + 1 duplicate | DETECTED | `TABLE_CONSTRAINTS_CHANGED`; `row count changed 12→13`; `duplicate id(s) [0]` | n/a | 13 |
| V02 | validate_post_contract | PK dropped + all duplicated | DETECTED | `TABLE_CONSTRAINTS_CHANGED`; `row count 12→24`; duplicates `[0..11]` | n/a | 24 |
| V03 | validate_post_contract | PK dropped only | DETECTED | `TABLE_CONSTRAINTS_CHANGED` | n/a | 12 |
| V04 | validate_post_contract | `status` NOT NULL dropped | DETECTED | `STATUS_SHAPE_REGRESSED` | n/a | 12 |
| V05 | validate_post_contract | `status` → varchar | DETECTED | `STATUS_SHAPE_REGRESSED` | n/a | 12 |
| V06 | validate_post_contract | `id` → bigint | DETECTED | `ID_SHAPE_REGRESSED` | n/a | 12 |
| V07 | validate_post_contract | CHECK added | DETECTED | `TABLE_CONSTRAINTS_CHANGED` | n/a | 12 |
| V08 | validate_post_contract | DEFAULT added on `status` | DETECTED | `STATUS_SHAPE_REGRESSED` | n/a | 12 |
| V09 | validate_post_contract | Extra column | DETECTED | `COLUMN_SET_CHANGED` | n/a | 12 |
| V10 | validate_post_contract | `status` dropped | **UNNAMED-EXC** | `AssertionError: expected exactly one row, got none` | n/a | 12 |
| V11 | validate_post_contract | `status` renamed | **UNNAMED-EXC** | same | n/a | 12 |
| V12 | validate_post_contract | `id` renamed | **UNNAMED-EXC** | same | n/a | 12 |
| V13 | validate_post_contract | One `status` changed | DETECTED | `STATUS_MISMATCH` | n/a | 12 |
| V14 | validate_post_contract | Legacy column re-added | DETECTED | `LEGACY_COLUMN_STILL_PRESENT` | n/a | 12 |
| V15 | validate_post_contract | `status` collation → `"C"` | **CLEAN** | — | n/a | 12 |

On every clean `verify_rollback` result, `rows_checked` equalled the live row count.

## Mutation table (integration suite, 17 tests; baseline 17 passed)

| Mutant | What it removes | Suite result | Verdict |
|---|---|---|---|
| M1 | `status` shape check (`verify_rollback`) | 1 failed | Killed (C2 met) |
| M2 | `status_code` shape check | 2 failed | Killed |
| M3 | `status` data dropped from the row comparison | 1 failed | Killed |
| M4 | `row_set_changed` | 17 passed | Survives. **Acceptable (equivalent):** a set difference with the same count and no duplicates always produces a `mismatches` entry. |
| M5 | Empty-snapshot guard (`verify_rollback`) | 1 failed | Killed |
| M6 | NOT NULL ignored for `status_code` | 1 failed | Killed (C2 met) |
| M7 | NULL-value check | 17 passed | Survives. Acceptable: shadowed by the `not_null` shape check. |
| M8 | Empty-snapshot guard (`validate_post_contract`) | 1 failed | Killed |
| N1 | Row-count/duplicate check (`verify_rollback`) | 17 passed | Survives. Acceptable as defence in depth **only if N2 is pinned**, because for this PK'd fixture it is shadowed by the constraint check plus the data mismatch check. |
| **N2** | **Constraint comparison (`verify_rollback`)** | **17 passed** | **Survives. Not acceptable.** Confirmed on real Postgres: PK-only drop and CHECK-added both become CLEAN with `rows_checked=12`. |
| **N3** | **Default comparison (`verify_rollback`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: `DEFAULT 0` on `status_code` becomes CLEAN. |
| **N4** | **Full column-set comparison (`verify_rollback`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: extra column becomes CLEAN. |
| N5 | `rows_checked` reports the snapshot count | 17 passed | Survives. **Acceptable (equivalent):** on any non-raising return, the live count equals the snapshot count, because any mismatch raises at `:627-629`. |
| **N6** | **`id` shape comparison (`verify_rollback`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: `id`→bigint becomes CLEAN. |
| N7 | Row-count AND constraint checks (`verify_rollback`) | 2 failed | Killed. The PK-duplicate tests pin only the pair, not either check alone. |
| N8 | Explicit column-existence check | 17 passed | Survives. Acceptable: the column-set check still raises the named error. |
| N9 | Data-mismatch check (keeps only `row_set_changed`) | 3 failed | Killed |
| P1 | Row-count/duplicate check (`validate_post_contract`) | 17 passed | Survives. Acceptable alone (shadowed by the constraint check, confirmed), but see P10. |
| **P2** | **Constraint comparison (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** |
| **P3** | **Default comparison (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** |
| **P4** | **Column-set comparison (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: extra column becomes CLEAN. |
| **P5** | **`status` shape (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: V2-shape (`status` DROP NOT NULL) becomes CLEAN. This is exactly probe V2 from the previous review. |
| **P6** | **`id` shape (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** |
| P7 | `ROW_SET_CHANGED` (`validate_post_contract`) | 17 passed | Survives. Acceptable once the others are pinned (redundant). |
| **P8** | **`STATUS_MISMATCH` (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: a changed `status` becomes CLEAN. This is the core of the SCN-022 validation query. |
| **P9** | **`LEGACY_COLUMN_STILL_PRESENT`** | **17 passed** | **Survives. Not acceptable.** Confirmed: becomes CLEAN. |
| **P10** | **Row-count AND constraints (`validate_post_contract`)** | **17 passed** | **Survives. Not acceptable.** Confirmed: probe V1 (PK drop plus duplicate) becomes CLEAN. This is the exact NF-3 false clean, unpinned. |

---

## Findings (most severe first)

**P0:** none.

### P1

**NR2-1. BUG-049's Round-2 fix lacks the regression tests C1 explicitly required. Each new NF-1 comparison except row-count can be deleted with the suite green, and each deletion reintroduces a real false clean.**

- **Where:**
  - `backend/tests/harness/migration_safety.py:580-585` (column set), `:587-596` (`id` shape and defaults within `ColumnShape`), `:598-603` (constraints).
  - `backend/tests/integration/test_migration_safety_harness.py:337-387`. These are the only NF-1 tests, and both drop the PK and duplicate rows, so the constraint check and the row-count check shadow each other.
- **Evidence:**
  - Mutants N2, N3, N4 and N6 all survive with 17 of 17 passing.
  - Applying each mutant in memory and running the matching probe on real Postgres turned DETECTED into **CLEAN, `rows_checked=12`** for: PK-only drop, CHECK added, `DEFAULT 0` on `status_code`, an extra column, and `id`→bigint.
- **Unmet requirements:**
  - The Round-1 re-review's NF-1 required fix said verbatim: "Add negative tests for PK drop with a duplicate row, **and for a PK-only drop**". The PK-only-drop test does not exist.
  - C1 itself requires the fix "with negative tests".
- **Why P1, even though today's code is correct:**
  - This is a P1 false-clean defect family that has already recurred twice.
  - The previous review made exactly this class (surviving mutants on correct code, NF-2/C2) a blocking condition.
  - Without pinning tests, a future edit can silently reintroduce the defect the bug exists to prevent. The project's evidence-over-assertion rule (DC-10, `DEVELOPMENT_CONSTITUTION.md:37`) is then met only by deleted probe scripts.
- **This is not a live false clean.** All required C1 shapes are detected by the current code.
- **Required fix:** add real Colima integration negatives, each asserting `ROLLBACK_VERIFICATION_FAILED`, for:
  - PK-only drop (R01);
  - a CHECK or UNIQUE added (R23 or R24);
  - a DEFAULT added (R04);
  - an extra column (R09);
  - `id` → bigint (R13).

  Optionally also a default removal using a "pre" snapshot (R07). Then re-run mutants N2, N3, N4 and N6 to confirm they are killed.

### P2

**NR2-2. The NF-3 remediation (`validate_post_contract`) has zero negative tests. Every check in it, including the pre-existing `STATUS_MISMATCH` and `LEGACY_COLUMN_STILL_PRESENT`, can be removed with the suite green.**

- **Where:** `migration_safety.py:423-481`. The only assertions on `validate_post_contract` in the suite are `== []` (`integration:150-151, 309-310, 325`) and `EMPTY_SNAPSHOT` (`:250-257`).
- **Evidence:**
  - Mutants P2 to P6 and P8 to P10 survive.
  - Confirmed on real Postgres: under P10 the exact V1 false clean (PK drop plus duplicate row) returns; under P5 the V2 false clean (`status` DROP NOT NULL) returns; under P8 a corrupted `status` value reports `[]`.
- **Why it matters:** this is SCN-MOD001-022's own "validation query confirms data integrity". As things stand, the suite would stay green if `validate_post_contract` were reduced to `return ValidationResult([])`.
- **Fix:** add negative integration tests mirroring V01, V04, V06, V07, V08, V09, V13 and V14.

**NR2-3. `validate_post_contract` leaks an unnamed `AssertionError` when a surviving column is dropped or renamed after contract.**

- **Where:** `migration_safety.py:455-456`. `_column_shape` is called unconditionally, and it reaches `one_row` at `:69-73` / `:316-324`.
- **Evidence:** probes V10 (`status` dropped), V11 (`status` renamed) and V12 (`id` renamed) each raise `AssertionError: expected exactly one row, got none` instead of returning a violation.
- **Severity:** it fails closed, so this is not a false clean. But it is the same class as the original review's P2-2, which was fixed only in `verify_rollback`, and it contradicts the module's "named, stable, machine-checkable failures" contract (`:76-81`).
- **Fix:** guard with `_column_exists`, or skip the shape loop when `COLUMN_SET_CHANGED` already fired, and emit a named violation such as `<COL>_MISSING`.

**NR2-4. Recorded claims that execution does not support (DC-10).**

- **Test-count claims:**
  - BUG-049 `:160-161` and the implementation evidence `:384-386` say "4 new negative integration tests reproduce the PK-drop-plus-duplicate shapes".
  - There are 2 such integration tests (`integration:346-387`).
  - The other additions are 4 unit tests of the pure `row_count_or_duplicate_violations` helper (`unit:62-83`), one of which is a positive case.
  - The total of 32 (15 unit + 17 integration) is correct; the description is not.
- **NF-3 claim:**
  - BUG-049 `:157-159` and BUG_REGISTRY `:106` state the NF-3 gap was "fixed the same way".
  - The code is fixed, but no test backs it (NR2-2).
- **Fix:** both records should be corrected when NR2-1 and NR2-2 are remediated.

### P3

**NR2-5. Schema-shape coverage residuals that are not disclosed** (`_column_shape` at `:318`, `_table_constraints` at `:349-353`). These produce clean results:
- an identity column (R31, `attidentity` not compared);
- a collation change (R32 and V15, `attcollation` not compared);
- a constraint rename only (R28, names not compared);
- an identical-definition duplicate CHECK (R29). The frozenset collapses it: the same multiplicity-collapse pattern as NF-1, at the constraint level, but behaviourally inert.
- Code-read only: `atttypid::regtype` drops typmod, so a `varchar(n)` length change would be missed. No current column carries a typmod.

None of these is in GOV-01-R02's acceptance criterion and none loses data. But the module header at `:30-31` ("`verify_rollback` never silently 'passes' a broken rollback") is broader than what is compared. Recommendation: disclose these next to the existing FK/index/trigger out-of-scope sentence (`:569-573`), or compare `attidentity`, `attcollation`, `format_type(atttypid, atttypmod)` and constraint names.

**NR2-6. Docstrings understate FK coverage.** `_table_constraints` (`:342-343`) says "not foreign keys", and `verify_rollback` (`:569-570`) calls FKs "deliberately out of scope". But the query does not filter `contype`, and probe R39 shows an added FK **is** detected. This is harmless (it understates rather than overclaims), but it is inaccurate.

**NR2-7. The C3 record is factually wrong about governed coverage.** BUG-049 `:200-203` says resumability and throttling "have no dedicated tracked scenario or bug of their own". **SCN-MOD001-066** (`SCENARIOS.md:1445-1455`, Blocker, GOV-01-R06 "large-backfill throttling and recovery", NOT EXECUTED) is exactly that home. The deferral itself is legitimate; the record should cite SCN-066.

**NR2-8. NF-5 is still open.** In the implementation evidence:
- `:137-149` ("`verify_rollback` diffs the restored column…") and the original "Real execution" block (`:162-182`, 15 and 134 passed) carry no inline superseded marker.
- `:349-350` "superseded by Round 2 below" marks only the Round-1 remediation section.

**NR2-9. Stale test-file text (NF-4 residue).**
- `unit:1-5` still says the diff is something "the rollback-verification step relies on".
- `unit:51-52` names `row_set_changed` as the row-set-growth check. Row growth is now caught first by the row-count check, and `row_set_changed` is redundant (mutant M4 is equivalent).

**NR2-10. The C4 notice sits only where a future caller is unlikely to read it.** It is in BUG-049 `:210-223` and the integration-test comment `:53-61`. The harness module docstring itself (`migration_safety.py:1-54`), which a future importer would read, carries no pointer to it. The notice is accurate; this is a placement suggestion only.

---

## Per-condition adjudication

| Item | Adjudication | Evidence |
|---|---|---|
| **C1 / NF-1** | **Behaviour RESOLVED; condition NOT CLEARED** | **Resolved:** every required shape is DETECTED with a named `ROLLBACK_VERIFICATION_FAILED` (R01–R27, R30, R33–R36). The positive control is clean with `rows_checked` (12) equal to the live count; `:640` reports `len(rows)`. **Not cleared:** the required PK-only-drop test is absent, and the constraint, default, column-set and `id`-shape comparisons are unpinned (NR2-1). |
| **C2 / NF-2** | **RESOLVED for its original scope** | Mutants M1 and M6 are killed (`integration:394-450`). The extra-row test (`:414-431`) exists. Old M4 still survives, but it is now an equivalent mutant (redundant with the row-count and mismatch checks), so that is acceptable. The NF-2 *class* recurs for the Round-2 code (NR2-1, NR2-2). |
| **C3 / P2-4** | **SATISFIED, with an inaccuracy** | Recorded in a governed bug file (BUG-049 `:191-208`) and in the harness docstring (`:221-226`), which is precise: `throttle_s` is always 0 and there is no interruption test. N-1 compatibility is correctly pointed at SCN-113. The claim that there is "no dedicated scenario" is wrong, because SCN-066 exists (NR2-7). |
| **C4 / P2-5** | **SATISFIED** | BUG-049 `:210-223` gives a precise, accurate forward-binding notice. I confirmed by `grep` that the only importers are the unit and integration test files, and that `DROP SCHEMA … CASCADE` is at `integration:81`. There is still no technical enforcement, which is disclosed. Placement suggestion in NR2-10. |
| **NF-3** | **Behaviour RESOLVED, unpinned** | V01–V09, V13 and V14 are DETECTED, and V00 is clean. Zero negative tests exist and every check survives mutation (NR2-2). There is an unnamed exception on a dropped or renamed column (NR2-3). |
| **NF-4** | **Mostly RESOLVED** | The `diff_int_maps` docstring (`:145-154`) is now accurate: I confirmed it is not called by the harness. The `RollbackVerificationError` docstring (`:89-100`) and the `verify_rollback` "only when every check above agrees" claim (`:553-557`) are now true for the listed checks, based on my probes. Residue is in the unit-test text (NR2-9) and the FK understatement (NR2-6). |
| **NF-5** | **NOT RESOLVED** | NR2-8. |
| **NF-6** | **RESOLVED** | The negative cycle test exists (`integration:313-330`). The lack of switch/expand rollback is now stated in `rollback_contract`'s docstring (`:513-516`). |

## Supply chain, data and scope

- **No new dependency or capability.** The harness uses psycopg plus CAP-008, which is APPROVED: digest-pinned image, pinned Colima CLI and engine identity. No third-party capability is treated as trusted without qualification evidence.
- **No credential in source.** The password is generated at runtime, passed through the environment rather than argv, and `superuser_password` is `repr=False` (`postgres.py:103, 170-178`).
- **Synthetic data only.** Integer ids and the three synthetic status labels. No real member data, no spend, no deploy, no network beyond loopback for the database.
- **Scope breadth.** The harness functions accept any connection and do destructive DDL. Mitigation is by discipline only (C4). This is acceptable for test-only use and correctly forward-bound.

## Scenario mapping (nothing promoted by this review)

- **SCN-MOD001-022** (`SCENARIOS.md:633`, NOT EXECUTED):
  - The literal steps are evidenced: phases run in order, switch-before-backfill fails closed (`integration:111-136`), and the validation query passes on a correct run (`:139-151`, V00).
  - The validation query's negative power is real by probe (V01–V14) but unpinned by the suite (NR2-2).
  - I recommend not promoting it until NR2-2 is fixed.
- **GOV-01-R02 "detects a deliberately broken rollback"** (no SCN of its own): met in behaviour for the harness fixture (R36) and for every required shape. Regression protection is incomplete (NR2-1).
- **SCN-MOD001-070** (`:1518`): no credit from this slice, which is correct. It belongs to the static ordering lint.
- **SCN-MOD001-113** (`:2223`): not exercised. It is the governed home for N-1 compatibility.
- **SCN-MOD001-066** (`:1445`): not exercised. It is the governed home for resumability and throttling (NR2-7).

## BUG-049 recommendation

**Not closure-eligible.** The live defect behaviour (shapes A–D, NF-1 and NF-3) is fixed and verified by execution. But NF-1's explicitly required negative tests are incomplete (NR2-1), NF-3 has no tests (NR2-2), and the bug and registry records overstate test coverage (NR2-4).

To become closure-eligible:
- add the tests listed under NR2-1 and NR2-2 and show the corresponding mutants are killed;
- name the NR2-3 exception path;
- correct NR2-4, NR2-7 and NR2-8.

A further fresh independent review should then confirm. I have not closed BUG-049 and have not edited `BUG_REGISTRY.md`.

## Overall verdict

**BLOCKED** (P0 = 0, P1 = 1, P2 = 3, P3 = 6).

The only blocking item is NR2-1 (C1's required negative tests). NR2-2 is strongly recommended in the same pass.

## Constraints honoured

- **No repository file was created, edited or deleted.** Hashes of the three code files were unchanged after every execution step. The knowledge files were unchanged at the end.
- **`run_regression.py` was not run,** because it writes into the repo.
- **No commit or push.** HEAD and `origin/main` are still `e516bed…`.
- **No promotion or closure.** SCN-MOD001-022 was not promoted and BUG-049 was not closed. No prior work by me was self-approved; I had none.
- **R04, ADR-010 and Amendment A2 were not read, run or commented on.**
- **Scratch files stayed outside the repo.** The probe scripts and mutation plugin lived only under `/tmp/veyro-r02-round2-review/`. That directory was deleted, and `ls` confirms "No such file or directory".
- **Database only through the approved path.** CAP-008 Colima `disposable_postgres()`: loopback, runtime password, pinned digest, `--rm`. Colima was not started, stopped or reconfigured, and `frosty_bhabha` was untouched. Every container I created was reaped.
- **No owner-reserved action.** Synthetic data only; no spend, no real member data, no deploy, no CI claim.
- **No safeguard refusal and no sign of model fallback** occurred during this review.

## Model assurance (filled in by the lead session)

- **Command:** `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-security-reviewer`
- **Transcript:** `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/5b2ff69a-b7f8-45dd-a6e0-991870f590d7/subagents/agent-ac2083e2c1f4717aa.jsonl` (agentId `ac2083e2c1f4717aa`)
- **Transcript SHA-256:** `ab6f879b441f69a76f6d2e938b7037fd973ded016195bdf468d9e7de44f7c0a0`
- **Result: PASS** (exit 0). All 46 turns are `claude-opus-5-5`, which matches the required `opus` tier.
- **Stop reasons:** 17 `tool_use` and 1 `end_turn`, with no `refusal` stop reason. Every textual mention of "safeguard" in the transcript was prompt text, file content or the reviewer's own attestation. None was a safeguard event, and no fallback model was observed.
- **Hashes and repository state:** The lead independently re-hashed the three code files after the review, and they matched the table above. HEAD and `origin/main` are `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.
