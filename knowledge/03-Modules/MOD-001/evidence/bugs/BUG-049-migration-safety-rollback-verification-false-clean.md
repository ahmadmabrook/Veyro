---
doc: BUG-049
module: MOD-001 (file: backend/tests/harness/migration_safety.py, `verify_rollback`)
severity: P1 (false-clean security defect — a broken rollback reported as verified-correct, on a security-control harness GOV-01-R02 treats as highest severity)
status: CLOSED (2026-10-03, Round 6 independent security re-review PASS, P0/P1/P2=0). Earlier OPEN status and five blocked rounds below are historical.
filed: 2026-10-03 by the orchestrating session, per the findings of a fresh independent `veyro-security-reviewer` (Opus) review that executed real probes against the harness
---

# BUG-049 — `verify_rollback` reported false-clean results on 4 broken-rollback shapes

**Superseded-sections notice (added 2026-10-03, Round 3, NR2-8):** the
"Finding", "Why this is P1, not lower", and "Fix" sections immediately
below describe only the Round-1 state of the code (shapes A-D) and its
Round-1 fix. That fix was real but incomplete — Round 2 found and fixed
a further false-clean family (NF-1/NF-3), and Round 3 (this update)
found and fixed a test-coverage gap in the Round-2 fix (NR2-1/NR2-2/
NR2-3). Read "Round 2" and "Round 3" further down for the current
state; the sections immediately below are preserved verbatim as
historical record, not current claims.

## Finding (Round 1 — historical, see notice above)

The first implementation of GOV-01-R02's migration-safety harness
(`GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md`) was independently
reviewed by a fresh-context `veyro-security-reviewer` (Opus,
`mr_verify.py`-attested, 34 turns, 100% `claude-opus-5-5`). The review
executed real probes against the real disposable Colima Postgres
harness — not a code-reading review — and found `verify_rollback`
reported a clean result (no `RollbackVerificationError`) for 4 distinct
broken-rollback shapes:

| Shape | Breakage | Result before fix |
|---|---|---|
| A | `status_code` restored as `text` instead of `integer`, same digits | **false clean** |
| B | Data correct, `NOT NULL` constraint not restored | **false clean** |
| C | `status_code` correct, but rollback overwrites/destroys the surviving `status` column's data | **false clean, data loss** |
| D | `status_code` correct, but rollback drops the surviving `status` column entirely | **false clean, data loss** |

Root cause: `verify_rollback` only ever selected `id, status_code`,
cast each value with `int(code)` (which silently coerces/hides a type
regression), and compared only against the snapshot's `status_code`
values — it never checked column type, nullability, whether the
`status` column still existed, or the `status` column's data. Full
finding detail, commands run, and probe methodology:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-INDEPENDENT-REVIEW-2026-10-03.md`.

## Why this is P1, not lower (Round 1 — historical, see notice above)

GOV-01-R02's own requirements text treats this requirement class as a
security control, and the module's acceptance criterion is literally
"detects a deliberately broken rollback" — a verification step that
reports a destructive, data-losing rollback as clean defeats the
control's entire purpose. The harness's own docstrings overclaimed
("never silently 'passes' a broken rollback") in a way the review
disproved by direct execution, not inference.

## Fix (Round 1 — historical, see notice above; local, same-day, same slice — `veyro-backend-engineer`/Sonnet,
`mr_verify.py`-attested, 38 turns, 100% `claude-sonnet-5`)

- Captured a fuller pre-contract `DataIntegritySnapshot`: it now
  carries each surviving column's schema shape (`ColumnShape`: Postgres
  data type + `NOT NULL`) for both `status_code` and `status`, in
  addition to full per-row data for both columns (already present).
- `verify_rollback` now checks, in order: both columns still exist
  (named failure, not a leaked `UndefinedColumn`, if either is
  missing); both columns' schema shape matches the snapshot (named
  failure on a type or nullability regression — closes shapes A/B);
  full row data for *both* `status_code` and `status` matches the
  snapshot (closes shapes C/D, the data-loss shapes); any `NULL`
  value or non-integer `status_code` after rollback is a named failure
  rather than a leaked `TypeError`.
- Added 2 new real, Colima-executed negative integration tests
  reproducing shape A (wrong type) and shape C (data loss on the
  surviving column) directly, each asserting
  `RollbackVerificationError` with `.code ==
  "ROLLBACK_VERIFICATION_FAILED"`.
- Corrected the module's own docstrings to describe what is now
  actually checked, citing this finding.

Independently re-verified by the orchestrating session (not taken on
the subagent's report): 22/22 targeted tests pass (was 15 — net +7:
the 2 new P1 negative tests plus 5 more for the P2 items below), 141/141
full backend suite, Ruff clean, mypy clean (repo-wide), all 4 baseline
hashes PASS, repo-skeleton/baseline-binding/migration-ordering/
capability-drift validators PASS, `git diff --check` clean, HEAD ==
`origin/main` unchanged (`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no
commit, no push.

**File hashes after fix:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `94058301e6a5968917f2221aab914b54c1a72c4f8a2df28a04d5e367ad72bde6` |
| `backend/tests/integration/test_migration_safety_harness.py` | `d13edf33014263b2e9aed9df21bfc222c93f5b67a9e1668e27f3b3908258edd7` |
| `backend/tests/unit/test_migration_safety_harness.py` | `3689b9d9828185b6b430c6524d1c534bed0373fb53bc6167da67939c4c629160` (unchanged — no pure logic needed a new unit test) |

## Related findings fixed in the same pass (not separately numbered —
same root cause family, same remediation slice)

- **P2-1 (empty/degenerate snapshot vacuously passes):** fixed —
  `verify_rollback`/`validate_post_contract` now raise
  `MigrationPhaseError("EMPTY_SNAPSHOT", ...)` on a zero-row snapshot
  instead of treating it as ground truth.
- **P2-2 (unnamed failures):** fixed — a missing column or an all-NULL
  restored column now raise `RollbackVerificationError`, not a raw
  `UndefinedColumn`/`TypeError`.
- **P2-3 (upgrade→downgrade→upgrade untested):** fixed — a new test
  runs `contract` again after a genuinely correct rollback.
- **P2-4 (resumability/throttle-interruption and TSD §24.2 rolling-deploy
  N-1 compatibility):** explicitly NOT fixed — out of GOV-01-R02's
  acceptance criterion per the review's own eligibility section.
  Disclosed honestly via a docstring note on `migrate_backfill`/the
  module header instead of a fix, per explicit scope instruction.
- **P2-5 (no technical safeguard against a non-disposable DB):**
  explicitly NOT re-engineered — disclosed via a docstring/comment note
  stating the limitation precisely (safety today is entirely the test
  fixture's own `disposable_postgres()` discipline), per explicit
  instruction not to build new enforcement in this bounded slice.

P2-6 (an evidence-document mislabeling) and P2-7 (CI budget measured
locally only, no real CI runner exists yet) are documentation-only
corrections, made directly in
`GOV01-R02-MIGRATION-SAFETY-HARNESS-2026-10-03.md` itself, not in this
bug file.

## Round 2 — fresh independent re-review found the defect family recurred (2026-10-03)

A second fresh-context `veyro-security-reviewer` (Opus, `mr_verify.py`-
attested, 40 turns, 100% `claude-opus-5-5`, no participation in the
original implementation, the Round-1 fix, or the Round-1 review)
re-reviewed the Round-1 fix by executing new probes. Full record:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-2026-10-03.md`.

**Verdict: BLOCKED, 1 new P1 (NF-1).** Shapes A-D are confirmed genuinely
fixed. But `verify_rollback` built an id-keyed dict before comparing
rows, so a rollback that dropped the table's primary key and then
duplicated rows (12→13 or 12→24) silently collapsed back to the
expected id set and reported clean — with a `rows_checked` value that
didn't even match the live row count. The original P1-1 fix's own
required-fix list had named "constraints" as a comparison element;
that element was never implemented or disclosed as skipped. Scope
extended (not a new bug number) per the reviewer's own recommendation
("keep BUG-049 open, extend its scope to NF-1 and fix it there").

**Fixed same day, same slice** — `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested, 70 turns, 100% `claude-sonnet-5`, no
fallback):
- `row_count_or_duplicate_violations`: a new pure function comparing
  the live row count against the snapshot's and detecting duplicate
  `id`s directly from the raw row list, computed *before* any
  id-keyed dict is built — the exact collapsing step that let the
  defect through.
- `_table_constraints`: snapshots and compares the table's own
  primary-key/unique/check constraint set via `pg_get_constraintdef`
  (Postgres's own rendering, robust to representation differences —
  not a hand-rolled string match).
- `ColumnShape` gained a `default` field; `_column_names` now compares
  the full live (non-dropped) column set, catching an extra column a
  broken rollback introduced; `id`'s own shape is now compared too,
  not just `status_code`/`status`.
- `rows_checked` on a passing result is now the live row count actually
  compared, never the snapshot's count.
- The analogous weakness in `validate_post_contract` (NF-3 — same
  id-keyed-dict multiplicity blindness, no shape check on the
  surviving `status` column) was **code-fixed** using the same
  primitives, but — corrected 2026-10-03, Round 3, NR2-4 — this was
  not backed by any test at the time; the second independent
  re-review found every check in that fix could be deleted with the
  suite green (NR2-2). See "Round 3" below for the tests that now
  pin it.
- Corrected 2026-10-03, Round 3, NR2-4 (the prior count here was
  wrong): **2** new negative integration tests reproduce the
  PK-drop-plus-duplicate shapes (12→13, 12→24) directly
  (`integration:346-387` at the time), plus 4 unit tests of the pure
  `row_count_or_duplicate_violations` helper (one of which is a
  positive/boundary case, not a negative test). 3 more integration
  tests pin previously-correct-but-unpinned detector branches the
  re-review's mutation testing flagged as surviving (NF-2: a
  `NOT NULL`-only `status_code` regression, an extra row with a new
  id, a `status`-column shape regression); 1 more pins the
  upgrade→downgrade→upgrade negative cycle (NF-6 residual).
  `diff_int_maps`'s docstring corrected to state it's no longer called
  by `verify_rollback`/`validate_post_contract` (NF-4).

Independently re-verified by the orchestrating session: 32/32 targeted
tests (was 22), 151/151 full backend suite (was 141), Ruff clean, mypy
clean (repo-wide, 24 files), all 4 baseline hashes PASS, repo-skeleton/
baseline-binding/migration-ordering/capability-drift validators PASS,
`git diff --check` clean, HEAD == `origin/main` unchanged
(`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no commit, no push.

**File hashes after Round 2:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `c51df06564c3833e4ff06032962464bbe49221e2494f41717db494fa9a1c5f01` |
| `backend/tests/integration/test_migration_safety_harness.py` | `d13829c604684221e402c13cbaa2f2b055f02d3575fe9606f48749a0641b5ab8` |
| `backend/tests/unit/test_migration_safety_harness.py` | `57ec706021c4e45a4e3d7fa08cc2f6c996482060b812c4527d4940ba6dcbd404` |

**Disclosed, explicitly out of scope even after Round 2** (stated in
the harness's own docstring, per the re-review's own adjudication that
these are not part of GOV-01-R02's acceptance criterion): foreign-key
constraints (this fixture table has none to compare against) and any
non-table schema object (indexes, triggers).

## C3 — resumability/throttling (P2-4) governed tracking

`migrate_backfill`'s docstring already disclosed that `throttle_s` is
always 0 in this harness's own tests and that no interrupted-backfill
test exists. Recording that disclosure here, durably, as the re-review's
condition C3 requires (a governed bug or scenario note, not only a
docstring): TSD §24.2's rolling-deploy (N-1) compatibility clause has
its own governed home, **SCN-MOD001-113** (`SCENARIOS.md:2223`, GOV-01-R06,
NOT EXECUTED) — this harness does not exercise it and makes no claim to.
Resumability and throttling *themselves* (as opposed to N-1 compatibility)
have no dedicated tracked scenario or bug of their own beyond this
disclosure and the harness's own docstring **(corrected below, NR2-7 —
this sentence was wrong; SCN-MOD001-066 is exactly that governed home,
see the correction after the C4 section)**; they are not part of
GOV-01-R02's acceptance criterion ("runs a synthetic expand/contract
migration and detects a deliberately broken rollback"), so no code
fix is owed here. If a future module needs real interruption-recovery
or throttling behavior proven, that is new scope, tracked against
whichever requirement owns it then — not silently assumed proven by
this harness's existence.

## C4 — forward-binding note on non-test reuse (P2-5)

`migration_safety.py`'s functions accept any `psycopg` connection and
the test fixture runs `DROP SCHEMA ... CASCADE`; this is safe today
only because every real caller is the test fixture's own
`disposable_postgres()`. Recording this as an explicit forward-binding
condition, per the re-review's C4: **any future, non-test reuse of
these functions (e.g. a later module importing `migration_safety.py`'s
helpers directly, rather than only running its own tests against them)
must independently re-establish the same discipline — a disposable,
loopback-only, randomly-credentialed database — before connecting them
to anything else.** This harness provides no technical enforcement of
that; the obligation is on the future caller, and this paragraph is
that caller's notice. **Also added 2026-10-03 (Round 3, NR2-10):** this
same notice is now stated directly in `migration_safety.py`'s own
top-of-module docstring too, so a future importer reads it without
needing to find this bug file first — this paragraph's record is not
superseded, just no longer the only place the notice lives.

**Correction 2026-10-03 (Round 3, NR2-7):** the sentence above
originally said resumability and throttling have "no dedicated tracked
scenario or bug of their own" — that was wrong. **SCN-MOD001-066**
(`SCENARIOS.md:1445`, Blocker, GOV-01-R06, "large-backfill throttling
and recovery", NOT EXECUTED) is exactly that governed home. The
deferral itself remains legitimate (resumability/throttling are not
part of GOV-01-R02's own acceptance criterion); only the "no governed
home" claim was inaccurate.

## Round 3 — a third fresh independent re-review found the Round-2 fix's own tests were incomplete (2026-10-03)

A third fresh-context `veyro-security-reviewer` (Opus, `mr_verify.py`-
attested, 46 turns, 100% `claude-opus-5-5`, no participation in the
implementation or either prior review) re-reviewed the Round-2 fix by
executing new probes and 28 in-memory mutations. Full record:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R2-2026-10-03.md`.

**Verdict: BLOCKED (P0=0, P1=1, P2=3, P3=6).** The live code was
confirmed correct — every required broken-rollback shape, including
every NF-1/NF-3 shape, is genuinely detected, and `rows_checked`
equals the live row count on every clean result. The blocking problem
(**NR2-1**) was test coverage, not behavior: the constraint,
default, full-column-set, and `id`-shape comparisons in
`verify_rollback` could each be individually deleted via mutation
testing while the suite stayed green, because the only 2 tests
exercising those branches both dropped the PK *and* duplicated rows —
so the constraint check and the row-count check shadowed each other,
and no test isolated any single comparison. The PK-only-drop test the
Round-2 fix's own required-fix list had named was never added.
**NR2-2** (P2): `validate_post_contract`'s entire NF-3 fix had zero
negative tests — every check in it, including the pre-existing
`STATUS_MISMATCH` and `LEGACY_COLUMN_STILL_PRESENT`, could be deleted
with the suite green. **NR2-3** (P2): a dropped or renamed surviving
column after `contract` leaked a bare `AssertionError`/`UndefinedColumn`
from `validate_post_contract` instead of a named violation.

**Fixed the same day**, again via `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested: 81 turns, 100% `claude-sonnet-5`, no
fallback):
- 5 new integration tests, each isolating exactly one `verify_rollback`
  NF-1 comparison with nothing else changed (so no shadowing): PK-only
  drop, a CHECK constraint added, a DEFAULT added on `status_code`, an
  extra column, `id` retyped to `bigint`.
- 8 new integration tests for `validate_post_contract`, each asserting
  the specific named violation string (not just `!= []`): PK-drop+
  duplicate (`TABLE_CONSTRAINTS_CHANGED`), `status` NOT NULL dropped
  (`STATUS_SHAPE_REGRESSED`), `id`→bigint (`ID_SHAPE_REGRESSED`), a
  CHECK added (`TABLE_CONSTRAINTS_CHANGED`), a DEFAULT on `status`
  (`STATUS_SHAPE_REGRESSED`), an extra column (`COLUMN_SET_CHANGED`), a
  changed `status` value (`STATUS_MISMATCH`), and the legacy
  `status_code` column still present (`LEGACY_COLUMN_STILL_PRESENT`).
  **Wording corrected twice now — first attempt (Round 4, NR3-5) was
  itself wrong, caught by the Round-4 re-review's NR4-3:** this V14 test
  never calls `contract()` at all (not "a second time" — not even
  once), so `status_code` genuinely still exists and that is exactly
  why `LEGACY_COLUMN_STILL_PRESENT` fires. The prior correction said
  "the legacy column is already gone" — backwards. The test's own
  docstring always stated this correctly; only this summary's two
  successive attempts at paraphrasing it were wrong.
- `validate_post_contract` restructured to guard with `_column_exists`
  before comparing `id`/`status` shape or selecting `status` values —
  fixing NR2-3's leaked exception for the `status` column (and a second
  instance of the same class the fix found one level down, in the
  row-selection query itself) by branching on column existence and
  reporting `COLUMN_SET_CHANGED` instead of crashing. **Overclaim,
  corrected 2026-10-03, Round 4 (NR3-2): this fix and this sentence
  both implied `id` was covered too — it was not.** Both row-query
  branches still selected `id` unconditionally, so a renamed or dropped
  `id` still leaked a bare `UndefinedColumn` (probes V12/V12b/V12c in
  the Round-3 review, NR3-1). 1 new test proved the `status`-dropped
  case reports a named violation, never raises; the `id` case was not
  actually fixed or tested until Round 4 below.
- Docstring corrections: `_table_constraints`/`verify_rollback` no
  longer wrongly claim foreign keys are "deliberately out of scope"
  (the constraint query has no `contype` filter; FKs would be detected,
  the fixture simply has none to test against — NR2-6); the same
  docstrings now disclose the real residual gaps an identity column,
  a collation change, a constraint rename, and an identical-definition
  duplicate constraint would not catch (NR2-5); the unit-test module
  docstring's stale `diff_int_maps` claim and a stale
  `row_set_changed` comment were corrected (NR2-9); the C4
  non-disposable-database notice was added to `migration_safety.py`'s
  own top-of-module docstring (NR2-10, also recorded in the C4 section
  above).
- Mutation re-verification (in-memory only, scratch plugin under
  `/tmp/`, never written to the repo, deleted afterward, hashes
  unchanged throughout): all 12 previously-surviving mutants the
  review named (constraint/default/column-set/id-shape checks in both
  functions, plus `STATUS_MISMATCH` and `LEGACY_COLUMN_STILL_PRESENT`
  in `validate_post_contract`) are now killed by the new tests.

Independently re-verified by the orchestrating session: 46/46 targeted
tests (was 32 — exactly 15 unit + 31 integration, confirmed by direct
count, not taken on the subagent's word per NR2-4's own lesson),
165/165 full backend suite (was 151), Ruff clean, mypy clean
(repo-wide, 24 files), all 4 baseline hashes PASS, repo-skeleton/
baseline-binding/migration-ordering/capability-drift validators PASS,
`git diff --check` clean, HEAD == `origin/main` unchanged
(`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no commit, no push. Also
independently spot-checked the actual code for the NR2-3 fix and one
new isolated test (the PK-only-drop test), confirmed each genuinely
isolates its target condition with no shadowing, before accepting the
subagent's mutation-kill claims rather than re-running all 12 mutations
from scratch.

**File hashes after Round 3:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `8d7a1bd9a098b50d134e3199b13a127ea7a37f3b0f60b961db5722555fe76b2e` |
| `backend/tests/integration/test_migration_safety_harness.py` | `79650a915aa7bc27fa5533f3e618bab608dcf4edd3c63f9e4d3ea19538c5f65c` |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` |

## Round 4 — a fourth fresh independent re-review found the NR2-3 fix was itself incomplete, and that the record overclaimed it (2026-10-03)

A fourth fresh-context `veyro-security-reviewer` (Opus, `mr_verify.py`-
attested: 58 turns across the session, 100% `claude-opus-5-5`, no
participation in the implementation or any of the three prior reviews)
re-reviewed the Round-3 fix by executing 11 new probes and the 12
required mutants plus 3 extra. Full record:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R3-2026-10-03.md`.

**Verdict: BLOCKED (P0=0, P1=0, P2=2, P3=4).** NR2-1 and NR2-2 (the
Round-3 fixes) were confirmed fully resolved — every required mutant
is killed, none shadowed. The blocking problem: **NR3-1** —
`validate_post_contract`'s NR2-3 fix only guarded the `status` column;
both of its row-query branches still selected `id` unconditionally, so
a renamed or dropped `id` after `contract` still leaked a bare
`psycopg.errors.UndefinedColumn` instead of the named
`COLUMN_SET_CHANGED` violation that already fires for it. **NR3-2**:
the module docstring, BUG-049 (this file), the `BUG_REGISTRY.md` row,
and the implementation evidence record all stated the leak was fixed
for "a dropped or renamed `status`/`id` column" — overclaiming `id` as
covered when it was not (the exact NR2-4 overclaim pattern, recurring).

**Fixed the same day** via `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested: 39 turns, 100% `claude-sonnet-5`, no
fallback): `validate_post_contract` now checks `_column_exists(conn,
table, "id")` before any row-level query and returns early with the
already-collected violations (which already include `COLUMN_SET_CHANGED`
naming `id`) if it's missing — skipping the row queries entirely rather
than reaching them. 3 new negative integration tests: `id` renamed,
`id` dropped, `status` renamed (the one missing case alongside the
already-existing `status`-dropped test). The existing `status`-dropped
test and all 3 new tests were tightened (**NR3-3**) to assert the
specific column name appears in the `COLUMN_SET_CHANGED` violation
text, not just that some `COLUMN_SET_CHANGED` violation exists.
**Overclaim, corrected 2026-10-03, Round 5 (NR4-2): this was false.**
`"id" in violation`/`"status" in violation` is a vacuous substring
check — both substrings appear in the literal word "expected" and in
a renamed column's own new name (`id2`, `status2`), so a mutant
reporting the constant, unchanged text (claiming no column changed at
all), or one that swaps which list is `expected` vs `got`, survived
all 49 tests undetected. See "Round 5" below for the real fix. Docstring
corrected to accurately state `status` was fixed in Round 2 and `id`
in Round 4, not both at once (NR3-2's code-file instance).
One more disclosure added: `_column_shape`'s `atttypid::regtype` cast
drops typmod, so a `varchar(n)` length change would go undetected —
latent today, no current column has a typmod (**NR3-6**).

Independently re-verified by the orchestrating session: 49/49 targeted
tests (was 46 — exactly the 3 new tests, confirmed by direct count),
168/168 full backend suite (was 165), Ruff clean, mypy clean (repo-wide,
24 files), all 4 baseline hashes PASS, repo-skeleton/baseline-binding/
migration-ordering/capability-drift validators PASS, `git diff --check`
clean, HEAD == `origin/main` unchanged
(`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no commit, no push. Also
independently read the actual `validate_post_contract` fix and the 3
new tests before accepting the subagent's report.

**File hashes after Round 4:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `ca697365d117ea3654333835402fc6ab063f2a4c5be1243e86cb2d05faa0a6be` |
| `backend/tests/integration/test_migration_safety_harness.py` | `b60bc3f4b2798aad54b656cb99bffdf06e335566f2821ca3407930a6ad2a57eb` |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` (unchanged — NR3-1/2/3/6 touched no unit-tested pure logic) |

**NR3-4 (this file's C3 section lacking an inline correction marker)**
is fixed above, in place, rather than here — see the C3 section's own
inline note.

## Round 5 — a fifth fresh independent re-review found a second leaked-exception shape and a false "tests pin column identity" claim (2026-10-03)

A fifth fresh-context `veyro-security-reviewer` (Opus, `mr_verify.py`-
attested: 57 turns across the session, 100% `claude-opus-5-5`, no
participation in the implementation or any of the four prior reviews)
re-reviewed the Round-4 fix by executing new probes (V15/V18/V19/V20)
and 4 in-memory mutants (K2–K5). Full record:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R4-2026-10-03.md`.

**Verdict: BLOCKED (P0=0, P1=0, P2=2, P3=4).** NR3-1's four cases
(`id`/`status` renamed/dropped) were confirmed resolved — each now
returns a named violation, raises no exception. Two new P2s:
**NR4-1** — `validate_post_contract` still leaked a bare
`TypeError`/`ValueError` via unguarded `int()` calls when the live `id`
column existed but held a NULL or non-integer value (e.g. its
`NOT NULL` dropped and a row set to NULL; `id` retyped to `text` with
non-numeric content) — the same named-failure defect class as
NR2-3/NR3-1, which `verify_rollback` already guarded but
`validate_post_contract` did not. **NR4-2** — the Round-4 claim that
the 4 column-identity tests "pin the specific column name" was false:
`"id" in violation`/`"status" in violation` is a vacuous substring
check (both substrings appear in the literal word "expected" and in a
renamed column's own new name), so a mutant reporting the constant,
unchanged `expected == got` text, or one swapping the `expected`/`got`
labels, survived all 49 tests — the DC-10 overclaim pattern recurring a
third time (after NR2-4 and NR3-2).

**Fixed the same day** via `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested: 95 turns, 100% `claude-sonnet-5`, no
fallback): `validate_post_contract`'s row-processing loop now guards
every raw `id` value — a NULL `id` or a non-integer `id` each append a
named `ID_VALUE_INVALID` violation and the row is excluded, rather
than leaking an exception (confirmed separately: a NULL `status` was
already fail-closed — it stringifies to `"None"`, which can never
equal a real mapped status, so it always surfaces as a genuine
`STATUS_MISMATCH`, never a silent false match). 2 new negative
integration tests: `id` NOT NULL dropped plus one row set to NULL
(V18), `id` retyped to `text` plus one row set to `'x'` (V19). A new
`ID_MISSING` violation was also added to the early-return path if it
would otherwise return empty violations (**NR4-4**, a defensive-only
fix for a path not reachable through the real harness API). For NR4-2:
all 4 column-identity tests were tightened to parse the exact
`expected=[...]`/`got=[...]` lists out of the violation text and
assert the precise set difference (the original column genuinely
absent, the new/missing state genuinely present) — proven by
re-running the K2 (constant-text) and K4 (swapped-label) mutants
in-memory only (never written to the repo): both are now killed,
4 call-phase `AssertionError`s each. Docstring corrected (**NR4-5a**):
the early-return's fail-closed property was previously attributed only
to `COLUMN_SET_CHANGED`, when `LEGACY_COLUMN_STILL_PRESENT` is what
actually fires if the legacy column is still present — corrected to
state *some* violation fires in either branch, not a specific one.

**Independently re-verified by the orchestrating session:** 51/51
targeted tests (was 49 — exactly the 2 new tests), 170/170 full backend
suite (was 168), Ruff clean, mypy clean (repo-wide, 24 files), all 4
baseline hashes PASS, repo-skeleton/baseline-binding/migration-ordering/
capability-drift validators PASS, `git diff --check` clean, HEAD ==
`origin/main` unchanged (`e516bedabf3d654ad3ae16d948b8f3522739ddc2`),
no commit, no push. Also independently read the actual
`validate_post_contract` fix and all 4 tightened column-identity tests
before accepting the subagent's K2/K4 mutation-kill claims.

**File hashes after Round 5:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `9ee88b41620f0b79476e51a388b35484e5f1a8d93b4f314d54699a0798132f04` |
| `backend/tests/integration/test_migration_safety_harness.py` | `5266bedb10ca1abe4495cd73f8dc55c7fe196698104196633294e60b8f4e0f97` |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` |

**NR4-3 (the NR3-5 wording "correction" above was itself wrong) and
NR4-5(a) (docstring precision)** are both fixed above, in place. The
Round-4 reviewer's own turn-count/transcript-path precision note
(NR4-5c) is a note about that review's own record, not this file's —
no action owed here.

**NR4-6 (two `verify_rollback` checks shadowed, defense-in-depth only,
no false clean possible):** disclosed, not fixed — the review itself
rated this informational, the same residual class already accepted for
`validate_post_contract`'s row-count/duplicate check in Round 3.

## Historical pre-R6 status — superseded

This bug is **OPEN (Round 5)** — the live defect behavior found across
all five rounds (shapes A-D, NF-1/NF-3, NR2-1/NR2-2/NR2-3, NR3-1, and
NR4-1) is fixed and independently re-verified by the orchestrating
session's own test/lint/governance runs, but **not self-closed**. Per
this project's established convention (a locally fixed bug counts as
not-closed until a session independent of the fix confirms it), only a
**sixth** fresh independent `veyro-security-reviewer` pass — with no
participation in the implementation or any of the five prior reviews —
may close this bug.

## Closure reconciliation (2026-10-03)

The sixth fresh, independent, read-only `veyro-security-reviewer` on `claude-opus-5-5` returned **PASS, P0=0/P1=0/P2=0** after executing the approved Colima/Postgres harness, adversarial malformed-ID and rollback probes, mutation variants, 51/51 focused tests, 170/170 full backend tests, Ruff, mypy, capability drift, and four-baseline verification. Independent transcript verification passed 85/85 turns with no fallback. The review explicitly found every live BUG-049 false-clean or bare-error shape from Rounds 1–5 fixed and marked this bug closure-eligible. See `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R5-2026-10-03.md` (review Round 5, sixth independent reviewer overall).

**Decision: CLOSED.** This is separate orchestrator reconciliation of the independent PASS, not implementer self-approval. The review's NR5-1–NR5-4 P3 documentation/test-precision notes remain disclosed in the review and do not reopen the P1 defect; NR5-5 is CAP-008 environment scope, with reachability only inferred, not established. SCN-MOD001-022 is separately promoted from executed evidence. SCN-059/066/070/113 receive no credit. R04/SCN-067 remain BLOCKED and BUG-048 OPEN on ADR-010 A2/model assurance.
