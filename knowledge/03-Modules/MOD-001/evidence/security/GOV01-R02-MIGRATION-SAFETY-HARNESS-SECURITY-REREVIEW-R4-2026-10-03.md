> **Lead transcription note (2026-10-03).** The review below was produced by the read-only
> `veyro-security-reviewer` Task agent (agentId `ab34e763f2432ae26`, model route `opus`),
> spawned fresh-context by a new orchestrating lead session. The reviewer had no Write tool,
> so the lead copied its final message into this file verbatim, with no content changes.
> After transcription the lead independently did the following:
> - **Model route re-run (final transcript):** `/opt/homebrew/bin/python3.13 knowledge/05-QA/tools/mr_verify.py` on the agent transcript (/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/9578db7d-d368-4576-a001-3250936143ac/subagents/agent-ab34e763f2432ae26.jsonl) with `opus veyro-security-reviewer` gave PASS, exit 0: "59 turn(s), 100% consistent, model 'claude-opus-5-5' matches required tier 'opus'". The transcript had 0 `"stop_reason":"refusal"` rows; meta.json agentType `veyro-security-reviewer`, model `opus`. Final transcript SHA-256: `737e1b637bc83e00fdc4b67ea2dc52ba7ef08f2d394e7537fb4b3a812a6927f5`.
> - **NR4-1 code-read spot-check:** `backend/tests/harness/migration_safety.py` lines 525 and 528 call `int(r[0])` on raw `id` values with no NULL/type guard. Consistent with the finding.
> - **NR4-2 code-read spot-check:** the four column-identity tests in `backend/tests/integration/test_migration_safety_harness.py` (around lines 678–735) assert only `"status" in violation` / `"id" in violation`. Consistent with the finding.
> - **HEAD / origin/main:** still `e516bedabf3d654ad3ae16d948b8f3522739ddc2`. Harness and integration-test SHA-256 re-confirmed as `ca697365d117ea3654333835402fc6ab063f2a4c5be1243e86cb2d05faa0a6be` and `b60bc3f4b2798aad54b656cb99bffdf06e335566f2821ca3407930a6ad2a57eb`.
>
> The lead edited no implementation file, promoted no scenario, closed no bug, touched no R04/ADR-010 material, and made no commit or push.

---

# GOV-01-R02 Migration-Safety Harness: Independent Security Re-Review Round 4 (2026-10-03)

**Date:** 2026-10-03
**Role:** veyro-security-reviewer, read-only.
**Fresh-context statement:** I had no part in the original implementation, in any remediation round (1–4), or in any prior review (the independent review, re-review, R2 or R3). I treated every prior record as a claim to test. Every result below is from my own execution in this session unless it is marked "code-read".

**Model attestation (my own transcript):**
- Transcript: /Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/9578db7d-d368-4576-a001-3250936143ac/subagents/agent-ab34e763f2432ae26.jsonl. Its meta.json gives agentType `veyro-security-reviewer`. It was the newest-mtime transcript of that type.
- Start run (`backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py` with that transcript, `opus veyro-security-reviewer`): PASS, exit 0, "8 turn(s), 100% consistent, model 'claude-opus-5-5'". SHA-256 `0e18bf8ec0a002bd897eb6b519a92285ec6639fb19b5acf3f6ae9d4f5d003926`, 0 `"stop_reason":"refusal"` rows.
- End run (`/opt/homebrew/bin/python3.13 knowledge/05-QA/tools/mr_verify.py`, same arguments): PASS, exit 0, "57 turn(s), 100% consistent, model 'claude-opus-5-5'". SHA-256 `f623f5db1db3f7da46b0a39ddc13e7ea971f3f6cd12e03d952b30d10c793470a`, 0 refusal rows.
- There was no safeguard stop, no fallback and no non-Opus turn. The hash will change once this final message is appended, so the lead should re-run the check after transcription.

**Read-only attestation:**
- HEAD and `origin/main` were both `e516bedabf3d654ad3ae16d948b8f3522739ddc2` at start and at end.
- `git status --porcelain` showed 167 entries at start and at end.
- All nine hashed files below are byte-identical before and after.
- Scratch work lived only in /tmp/veyro-r4-review. It was deleted, and `ls` now returns "No such file or directory".
- `docker ps -a` at start, after every run and at end showed only `frosty_bhabha` (not mine, untouched). Every disposable container was reaped.
- I made no commit or push, promoted no scenario and closed no bug.

---

## Verdict: **BLOCKED** (P0 = 0, P1 = 0, P2 = 2, P3 = 4)

**NR3-1 behaviour is fixed (executed).** Each of the four cases now returns named violations and raises no exception: `id` renamed, `id` dropped, `status` renamed, `status` dropped.

**Rollback false-clean has not regressed (executed).** Every rollback-verifier mutant that could produce a false clean is killed.

The review is still BLOCKED for two P2 reasons:
1. **NR4-1.** `validate_post_contract` still leaks bare `TypeError`/`ValueError` when `id` is present but holds NULL or non-integer values. This is the same named-failure defect class as NR2-3 and NR3-1. `verify_rollback` already guards these shapes.
2. **NR4-2.** The NR3-3 "tests now pin the specific column name" claim is false. Mutants that report the wrong column, or report no column change at all, survive all 49 tests. Three durable records state the claim, which makes this the third occurrence of the DC-10 overclaim pattern (after NR2-4 and NR3-2).

Under DC-08 (`knowledge/00-System/DEVELOPMENT_CONSTITUTION.md:61-64`), open P2s block closure.

---

## Findings (most severe first)

### P2

**NR4-1. `validate_post_contract` leaks a bare `TypeError`/`ValueError` when `id` exists but holds NULL or non-integer values (executed).**
- **Where:** `backend/tests/harness/migration_safety.py:525` and `:528`. Both run `int(r[0])` on raw `id` values with no guard.
- **Executed probes** (disposable CAP-008 Postgres 16.15, 12 synthetic rows; full sequence, then `contract`, then the stated DDL):

| Probe | DDL after contract | Outcome |
|---|---|---|
| V15 | `id` renamed to `id2`, then a new nullable `id text` column added | **RAISED `builtins.TypeError`**: int() argument … not 'NoneType' |
| V18 | PK dropped, `id` NOT NULL dropped, one `id` set to NULL | **RAISED `builtins.TypeError`** (same message) |
| V19 | `id` retyped to `text`, one `id` set to `'x'` | **RAISED `builtins.ValueError`**: invalid literal for int() with base 10: 'x' |
| V20 (control) | `status` NOT NULL dropped, one `status` set to NULL | Named: `STATUS_SHAPE_REGRESSED…`, `STATUS_MISMATCH:{0: ('inactive', 'None')}` |

- **Contrast:**
  - `verify_rollback` guards exactly these shapes with named errors: the NULL-id check at `:689-690` and the int-conversion `try` at `:695-700`. That guard came from the original review's P2-2.
  - The module's named-failure contract (`:88-93`) says the harness never raises "a bare assertion failure or generic exception".
- **Severity:** P2, the same rating R3 gave NR3-1 and R2 gave NR2-3. It fails closed (an exception, not a false clean) and loses no data. But it is an unnamed driver/Python exception in the validation function SCN-MOD001-022 depends on.
- **Required fix** (either option):
  - Mirror `verify_rollback`'s guards: emit a named violation such as `ID_VALUE_INVALID` instead of calling `int()` unguarded. Add integration negatives for V18 and V19; V15 is optional because it is covered by the same guard.
  - Or split this into a new tracked bug by explicit, recorded decision.

**NR4-2. The NR3-3 claim that tests pin column identity is false, and three records overclaim it (executed; DC-10, third recurrence).**
- **Tests:** `backend/tests/integration/test_migration_safety_harness.py:678`, `:702`, `:719` and `:735` assert only `"status" in violation` or `"id" in violation`.
  - The violation text always starts `expected=['id', 'status']` (probes V10–V12b).
  - So both substrings are present whichever column is missing.
  - In the rename cases, `id2` and `status2` also contain the asserted substring.
  - Nothing distinguishes `id` from `status`, or rename from drop.
- **In-memory mutants** (the repo was never written; JUnit-parsed; every failure was a call-phase `<failure>`, `errors=0`):

| Mutant | Edit to the `COLUMN_SET_CHANGED` text (`migration_safety.py:482`) | Result |
|---|---|---|
| K2 | Constant `COLUMN_SET_CHANGED:expected=['id', 'status'] got=['id', 'status']` (reports no change) | **49 passed. SURVIVES** |
| K4 | `expected`/`got` labels swapped | **49 passed. SURVIVES** |
| K3 | Only `got={live}` emitted | 2 failed (the two *drop* tests). **Survives both rename tests** |
| K5 | Reports the *new* column as missing (`missing={live - expected}`, which gives `['id2']`) | 2 failed (the two drop tests). **Survives both rename tests**, so a wrong-column label passes |

- **Records that overclaim:**
  - `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-049-migration-safety-rollback-verification-false-clean.md:389-392`
  - `knowledge/05-QA/BUG_REGISTRY.md` header `:22-25` and row `:175` ("each pin the specific column name in the violation text, not just that some violation exists")
  - `knowledge/03-Modules/MOD-001/evidence/implementation/GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md:548-551`
- **Severity:** the test weakness alone would be P3, as R3 rated NR3-3. The false record of evidence strength is P2, following the NR2-4 and NR3-2 precedent.
- **Required fix:** assert the exact missing column. For example, parse the `got=` list and assert `"id" not in got and "id2" in got`. Or emit a dedicated `<COL>_MISSING` tag and assert equality. Then correct the three records.

### P3

**NR4-3. The NR3-5 wording "correction" is itself inaccurate (code-read plus executed contrast).**
- **Where:** BUG-049 `:299-304`. It now says LEGACY_COLUMN_STILL_PRESENT fires because "the legacy column is already gone" and from "the first `contract`'s own absence of the legacy column".
- **What actually happens:** the test (`integration:646-656`) never calls `contract` at all. `status_code` survives, and that is why the violation fires. Probe V16 also shows the violation only fires while `status_code` is present.
- **Also:** the test's docstring at `:649-650` still opens with "after a no-op re-contract".
- **Fix:** rewrite as "`contract` is never called, so `status_code` remains".

**NR4-4. The `id` early return's fail-closed property rests on an invariant the function never asserts (executed).**
- **Where:** `migration_safety.py:512-513` returns `violations` as-is when `id` is missing. It relies on `COLUMN_SET_CHANGED` having fired, which needs `"id" in snapshot.column_names`.
- **Probe V17:** a hand-built `DataIntegritySnapshot` with `id` removed from `column_names`, plus `id` dropped live, returned **`[]`**, a clean result.
- **Reachability:** `capture_snapshot` cannot produce such a snapshot, because `_column_shape(..., "id")` would fail first. So this is not reachable through the harness API.
- **Note:** before Round 4 the same input raised an exception. The early return turned a fail-closed path into a conditionally fail-open one.
- **Fix:** on that path, append a named violation if `violations` is empty.

**NR4-5. Docstring and record precision (code-read plus executed).**
- **(a)** `:463-464` and `:504-506` say the early return relies on an "already-collected `COLUMN_SET_CHANGED`". When `status_code` is still present, that violation is not collected; V16 returns only `['LEGACY_COLUMN_STILL_PRESENT']`. It still fails closed.
- **(b)** The code docstring labels the `id` fix "security re-review round 3 … this round". The records call it "Round 4". These are two numbering schemes, consistent internally but confusing.
- **(c)** No repo record names the Round-4 implementer transcript; there is only a turn count. I located it through meta.json (see the commands table).
  - **Typmod disclosure (NR3-6) is accurate (executed):** `atttypid::regtype::text` gives `character varying` for both `varchar(50)` and `varchar(100)`, while `format_type` gives `(50)` and `(100)`. The disclosure is at `:646-651`.
  - **C3 inline marker (NR3-4) is present** at BUG-049 `:221-223`.

**NR4-6. Two `verify_rollback` checks are shadowed. This is defence in depth only, with no false clean (executed).**
- **RC:** the missing-column `raise` at `:656` replaced by `pass`. Result: 49 passed. The column-set check at `:659` catches the same shapes, with `status_code` in the message.
- **RD:** the row-count/duplicate check at `:706` disabled. Result: 49 passed. The PK-drop-plus-duplicate tests are caught first by the constraint check, because duplicates need a PK drop.
- Both are equivalent today. This is the same residual R3 recorded for `validate_post_contract`'s P1 mutant.

---

## Primary focus: NR3-1 and NR3-2 status

| Item | Status | Evidence |
|---|---|---|
| NR3-1 behaviour (four cases) | **RESOLVED** | Probes V12 (`id` renamed), V12b (`id` dropped), V11 (`status` renamed), V10 (`status` dropped), V12c (both renamed) and V12d (both dropped) all **returned** named violations with no exception. Exact outputs are in the commands table, row 3. Mutant K1 (guard removed) is killed by both `id` tests with `psycopg.errors.UndefinedColumn`. |
| NR3-1 tests pin column identity | **NOT MET** | NR4-2 (K2 and K4 survive all tests; K3 and K5 survive the rename tests) |
| NR3-2 (overclaim of `id` fixed) | **RESOLVED for the cited claim; pattern recurred** | All four places now accurately say `id` was not fixed until Round 4. A new overclaim appears (NR4-2). |
| NR3-3 | **NOT RESOLVED** (claimed resolved) | NR4-2 |
| NR3-4 | Resolved | BUG-049 `:221-223` |
| NR3-5 | **Corrected wrongly** | NR4-3 |
| NR3-6 | Resolved, and the disclosure is accurate | Typmod probe (executed) |

## Rollback-verifier regression (no false clean possible)

- Probes R00–R06 (executed):
  - Correct rollback is CLEAN with `rows_checked=12`.
  - The deliberately broken rollback, `id` renamed or dropped, `status` renamed or dropped, and a single wrong `status_code` value all raise `ROLLBACK_VERIFICATION_FAILED` with a named detail.
- Mutants (executed):
  - **N2** is killed by the PK-only and CHECK tests.
  - **N3** is killed by the DEFAULT test.
  - **N4** is killed by the extra-column test.
  - **N6** is killed by the `id`-to-bigint test.
  - **RM** (row-mismatch check disabled) is killed by three tests, including the GOV-01-R02 acceptance test `test_rollback_verification_detects_a_deliberately_broken_rollback`.
  - All are DID NOT RAISE call-phase failures.

## C3/C4 deferrals

- **C3** (resumability/throttling) is still legitimately outside GOV-01-R02's acceptance criterion. Its governed home is SCN-MOD001-066, and the records now say so. `migrate_backfill`'s disclosure (`:233-238`) is intact. Nobody may cite this harness as SCN-066 evidence.
- **C4** (non-disposable database) is disclosed in the module docstring (`:55-65`), in BUG-049's C4 section and in `integration:53-61`. It has no technical enforcement, which is acceptable for test-only use. Every database interaction I ran went through `disposable_postgres()` (loopback, runtime password, `--rm`).

## Scenario eligibility

- **SCN-MOD001-022** (`knowledge/03-Modules/MOD-001/SCENARIOS.md:633`, NOT EXECUTED):
  - Depends on the positive sequence (`integration:111-151`, passing) and on the negative power of `validate_post_contract`.
  - The literal steps are substantively evidenced.
  - **Not promotion-eligible yet**: NR4-1 is an open P2 in the very validation function this scenario relies on, and NR4-2 is an open P2 over that function's test evidence.
  - Promote once both are fixed or explicitly split, and a fresh review closes BUG-049.
- **SCN-MOD001-070** (`:1518`): depends only on the static ordering lint (Slice 4). It gets no credit from this harness, so BUG-049 does not affect it.
- **SCN-MOD001-066** (`:1445`): the resumable/throttled backfill is not exercised. It is C3's governed home and is unaffected.
- **SCN-MOD001-113** (`:2223`): N-1 rolling-deploy compatibility is not exercised, and the harness makes no claim to it. It is unaffected.

## Eligibility statements

- **BUG-049 closure-eligible: NO.** NR4-1 and NR4-2 are open P2s.
- **SCN-MOD001-022 promotion-eligible: NO.**
- **SCN-MOD001-070, 066 and 113:** unchanged, NOT EXECUTED, and none depends on BUG-049's closure.

## File SHA-256 (identical at start and end)

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `ca697365d117ea3654333835402fc6ab063f2a4c5be1243e86cb2d05faa0a6be` (matches BUG-049's Round-4 claim) |
| `backend/tests/integration/test_migration_safety_harness.py` | `b60bc3f4b2798aad54b656cb99bffdf06e335566f2821ca3407930a6ad2a57eb` (matches) |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` (matches) |
| `backend/tests/harness/postgres.py` | `3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67` |
| `backend/migrations/rls-manifest.json` | `913cf0836377e812c24a7dccc0f99f8703dda23b66cfa7f7b19b42b18d50b085` |
| `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-049-migration-safety-rollback-verification-false-clean.md` | `7b2eab060ca01400226cd7ddf24116a553adf873aa1ab7d6ed8071c6daf8688e` |
| `knowledge/05-QA/BUG_REGISTRY.md` | `db270eef360ba870b3f7e82841dcc60681a71049d23471ce4d45cd047ca03c77` |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` | `b0b3462bed39456e16d3412b04e8ada2d14293eeedf88035ab2a6cdd8f52da94` |
| `knowledge/03-Modules/MOD-001/evidence/implementation/GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md` | `04c0a56bd233d7d541fc86ac898a274d26c2f92adcda3c45d028b45c0b7c850d` |

## Commands and results

Test commands ran from cwd `backend/` with `env -u DOCKER_HOST`, so the CAP-008 Colima socket was used: Colima is running, aarch64, socket `~/.colima/default/docker.sock`, pinned digest `postgres@sha256:721873c3…`, server 16.15, host 127.0.0.1.

| # | Command | Result | Exit |
|---|---|---|---|
| 1 | `/opt/homebrew/bin/python3.13 knowledge/05-QA/tools/mr_verify.py` with the Round-4 implementer transcript (/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/606346da-f643-4da3-8ff6-c28d73a306dd/subagents/agent-a0e66faa085ed7633.jsonl; meta "Fix NR3-1 id-column exception leak", agentType `veyro-backend-engineer`), `sonnet veyro-backend-engineer` | **PASS**: "39 turn(s), 100% consistent, model 'claude-sonnet-5' matches required tier 'sonnet'". SHA-256 `fb701cf6b59b876e2b66584afb9244c83df0daf654e8442352d74bad5126d026`, 0 refusal rows. Matches the recorded "39 turns". | 0 |
| 2 | `PYTHONPATH=. .venv/bin/python /tmp/veyro-r4-review/probes.py` | V00 `[]`<br>V12: `COLUMN_SET_CHANGED:expected=['id', 'status'] got=['id2', 'status']`, `TABLE_CONSTRAINTS_CHANGED:…['PRIMARY KEY (id2)']`<br>V12b: `…got=['status']`, `TABLE_CONSTRAINTS_CHANGED:… got=[]`<br>V11: `…got=['id', 'status2']`<br>V10: `…got=['id']`<br>V12c and V12d: named<br>**V15: bare TypeError**<br>V16: `['LEGACY_COLUMN_STILL_PRESENT']`<br>**V17 (crafted): `[]`**<br>R00 CLEAN 12; R01–R06 all `ROLLBACK_VERIFICATION_FAILED`, named | 0 |
| 3 | `PYTHONPATH=. .venv/bin/python /tmp/veyro-r4-review/probes2.py` | **V18 TypeError, V19 ValueError**; V20 named | 0 |
| 4 | Mutation loop: `MUTANT=<name> PYTHONPATH=.:/tmp/veyro-r4-review .venv/bin/python -m pytest tests/unit/test_migration_safety_harness.py tests/integration/test_migration_safety_harness.py -q -p no:cacheprovider -p mutant_plugin --junitxml=…` (13 runs) | NONE: 49 passed<br>K1: killed (2, UndefinedColumn)<br>**K2: survives**<br>K3: 2 failed (rename tests survive)<br>**K4: survives**<br>K5: 2 failed (rename tests survive)<br>N2: 2 killed; N3, N4, N6: 1 killed each; RM: 3 killed<br>RC and RD: survive (shadowed, NR4-6)<br>All runs `errors=0`, `skipped=0` | per run |
| 5 | `.venv/bin/python -m pytest tests/unit/test_migration_safety_harness.py tests/integration/test_migration_safety_harness.py -q -p no:cacheprovider` | **49 passed** in 3.11 s (49 collected) | 0 |
| 6 | `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` | **168 passed** in 20.28 s | 0 |
| 7 | `.venv/bin/ruff check` on the 3 files, then `.venv/bin/ruff check .` (ruff 0.16.9) | All checks passed (both) | 0 / 0 |
| 8 | `.venv/bin/mypy` on the 3 files, then `.venv/bin/mypy .` (mypy 2.3.1, strict) | Success: 3 files; Success: 24 files | 0 / 0 |
| 9 | `PYTHONPATH=. .venv/bin/python /tmp/veyro-r4-review/typmod.py` | `varchar(50)` and `varchar(100)` both give `character varying` via regtype | 0 |
| 10 | `backend/.venv/bin/python knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py` (repo root, no arguments, read-only) | PASS: 357 files scanned, no broken references beyond expected forward refs | 0 |
| 11 | `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | PASS: 4/4 MATCH | 0 |
| 12 | `knowledge/05-QA/tools/run_regression.py` | **Not run**, because it writes a run record into the repo | n/a |

## Supply chain, data and scope

- No new dependency or capability. The harness uses psycopg plus CAP-008 (APPROVED: pinned digest, loopback only, runtime password, `--rm`). No third-party capability is trusted without qualification evidence.
- No credential appears in any file or output.
- Synthetic data only: integer ids 0–11 and the labels `inactive`, `active` and `pending`. No spend, no deploy, no CI claim (there is no `.github/`; everything ran locally).
- Scope breadth is unchanged: harness functions accept any connection, which is disclosed under C4.

## What was NOT done

- No repository file was created, edited or deleted. I made no commit or push, no scenario promotion, no bug closure, and no registry or state edit.
- R04, ADR-010 and Amendment A2 were not read, run or commented on.
- No database other than the CAP-008 Colima disposable Postgres was used.
- No self-approval: I had no prior work on this harness.
