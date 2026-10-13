---
doc: GOV01-R02-MIGRATION-SAFETY-HARNESS
status: EVIDENCE — ROUND 5 REMEDIATED LOCALLY, PENDING A SIXTH FRESH INDEPENDENT RE-REVIEW
module: MOD-001
updated: 2026-10-03, Round 5 local remediation; latest independent review
remained BLOCKED on NR4-1/NR4-2 (P2=2). See the Round-5 section and
BUG-049 for the executed results and full review history.
---

# GOV-01-R02 — Migration-safety test harness (routine, bounded slice)

**This record is evidence only. It does not self-approve SCN-MOD001-022 or
SCN-MOD001-070, does not certify this slice, and does not update
`STATUS.md`, `SCENARIOS.md`, `CURRENT_STATE.md`, or `CURRENT_HANDOFF.md` —
those are explicitly out of scope for this session and are left for
reconciliation by a separate pass (independent review first, per this
project's established model for every other MOD-001 slice).**

## Scope

Bounded, routine (non-critical-slice) implementation of GOV-01-R02's
**migration-safety test harness** obligation only — `REQUIREMENTS.md`
GOV-01-R02 and TSD §24.2 (`TSD_MIRROR.md` lines 11655-11669). This is the
half of GOV-01-R02 explicitly left open after Slice 5
(`SLICE-5-gov01-r02-tenant-isolation-auth-harness-2026-09-29.md`), which
covered only the tenant-isolation/RLS harness and the authentication
negative-credential fixture pattern (the two `ADR-005` Decision 1
critical-slice items). The migration-safety harness is not one of
`ADR-005`'s three named critical slices, so it was routed to the
registered `veyro-backend-engineer` (Sonnet, ADR-005 Decision 2 /
EIP §4.3 Backend profile), not `veyro-critical-engineer`.

**Explicitly out of scope and untouched this session** (per the governing
task instructions): `tools/validate_architecture_gates.py` and its test
file, `backend/tests/integration/test_architecture_gate_rls.py`, `ADR-010`
and any `knowledge/**/security/**` record, `backend/migrations/
rls-manifest.json`, the RLS/authn critical-slice harness files
(`backend/tests/harness/tenant_isolation.py`, `authn.py`, `postgres.py`),
`backend/tests/integration/conftest.py`,
`backend/tests/unit/test_harness_postgres_fail_closed.py`, and every
top-level MOD-001/`knowledge/00-System` governance document. R04/ADR-010
Amendment A2 remains BLOCKED on the separately-tracked Anthropic
safeguard/model-fallback issue
(`R04-A2-MODEL-ASSURANCE-CHECKPOINT-2026-10-03.md`) — unrelated to, and
unaffected by, this slice.

Still open under GOV-01-R02 after this slice (not attempted this
session): the six named domain suite scaffolds, the financial-invariant
placeholder, and the DOM-002 concurrency/versioning test pattern — per
`STATUS.md`'s own "still open" list as of Slice 5.

## Model-route attestation (real, independent — not self-reported)

Implementation was dispatched to the registered `veyro-backend-engineer`
agent (Sonnet tier per `MODEL_ROUTING.md`/`ADR-005` Decision 2 and
`mr_verify.py`'s own `EXPECTED_TIER_BY_AGENT` map) via the Agent/Task
tool, as a single self-contained subagent run. Its real per-task
transcript (not the orchestrating session's own transcript) was located
at:

```
~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/606346da-f643-4da3-8ff6-c28d73a306dd/subagents/agent-a9a270b6bd5cfe2c5.jsonl
```

Independently verified with the project's own tool, not taken on the
subagent's self-report:

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/606346da-f643-4da3-8ff6-c28d73a306dd/subagents/agent-a9a270b6bd5cfe2c5.jsonl \
    sonnet veyro-backend-engineer

{
  "verdict": "PASS",
  "reason": "45 turn(s), 100% consistent, model 'claude-sonnet-5' matches required tier 'sonnet'.",
  "models_observed": ["claude-sonnet-5"],
  "expected_tier": "sonnet"
}
```

45/45 turns `claude-sonnet-5`, no mid-task substitution, no fallback —
unlike the separately-tracked R04/A2 `MODEL_ASSURANCE_UNVERIFIED`
incident, this run is clean.

## Files created (new only — nothing pre-existing was edited)

Confirmed by `git status --porcelain` before and after: only these 3
paths appeared, as untracked new files. Every file shown as modified (M)
or untracked (??) in the pre-existing working tree at session start
(the in-progress R04/ADR-010 work, assorted commit-message scratch
files, etc.) is byte-for-byte unchanged — diffed by `git status`
showing no new modifications to any of them.

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `78afcb7d457c2ec1b4b64a0171c2c56a9bbe92091432ef677f2ef27d573fe9c4` |
| `backend/tests/integration/test_migration_safety_harness.py` | `35b343f97640fd19c2cd2a0a7e3893826f6a4721982b17eed2a3d63a00b34a6d` |
| `backend/tests/unit/test_migration_safety_harness.py` | `3689b9d9828185b6b430c6524d1c534bed0373fb53bc6167da67939c4c629160` |

`git diff --check`: clean (0 whitespace errors). `git rev-parse HEAD`
and `git rev-parse origin/main` both `e516bedabf3d654ad3ae16d948b8f3522739ddc2`
— unchanged; no commit, no push.

## What was built

`backend/tests/harness/migration_safety.py` is a new, self-contained
harness module — deliberately independent of `tenant_isolation.py`/
`authn.py`/`conftest.py` (no RLS, no tenant context, no shared fixture
state; it spins up its own disposable Postgres container via
`disposable_postgres()` from the existing, unmodified
`tests.harness.postgres`). It defines a synthetic `migration_harness.
widget` table evolving a legacy `status_code integer` to a new `status
text` column — the classic expand/contract "retype a column safely"
pattern — and implements all 4 TSD §24.2 phases as real SQL:

- **`expand`** — additive: adds the new nullable column.
- **`migrate_backfill`** — a bounded, batched, per-batch-committed loop
  (never one single deployment transaction), with an optional throttle
  hook — the "online/resumable... progress and throttling" shape TSD
  §24.2 names.
- **`switch`** — fails closed with a named `MigrationPhaseError`
  (`SWITCH_BEFORE_BACKFILL_COMPLETE`) if any row still lacks the new
  value, otherwise enforces `NOT NULL` — the point reads/writes move to
  the new shape.
- **`contract`** — the one destructive phase: drops the legacy column.

`run_full_sequence` chains expand→migrate→switch and returns a
`DataIntegritySnapshot` captured just before `contract` runs (the data
is unrecoverable from the live table once the destructive phase
completes). `validate_post_contract` is SCN-MOD001-022's own
post-migration validation query: confirms the legacy column is really
gone, no row was gained or lost, and every row's new value still matches
what its (now-dropped) legacy value meant.

**Superseded (2026-10-03, Round 3, NR2-8) — the paragraph below
describes only the original pre-fix code and is historical, not a
current claim.** `verify_rollback` no longer just "diffs the restored
column" against the snapshot — after 2 further remediation rounds it
also compares schema shape (type, nullability, default), the table's
full constraint set, and the full live column set, and detects
row-count/duplicate-row changes directly, all pinned by dedicated
isolated tests as of Round 3. See "Remediation", "Remediation, Round
2", and "Remediation, Round 3" below for the current, accurate state.

**The GOV-01-R02 acceptance criterion** ("the migration-safety harness
runs a synthetic expand/contract migration and detects a deliberately
broken rollback") is proven by a real, correct `rollback_contract`
(re-adds the dropped column, backfills it via the true reverse mapping)
versus `rollback_contract_broken` (re-adds the column but backfills every
row with the same wrong constant). `verify_rollback` diffs the restored
column against the pre-contract snapshot and raises a dedicated
`RollbackVerificationError` — a named, stable failure (`.code ==
"ROLLBACK_VERIFICATION_FAILED"`), never a bare `AssertionError` — the
moment any row disagrees or the row set changed. The integration suite
proves both directions (the broken rollback is caught; a genuinely
correct rollback verifies clean with `rows_checked == 12`), so the
detector is shown to be real rather than a check that always fails.

**Deliberately not reimplemented:** SCN-MOD001-070's "out-of-order
destructive-phase rejection" is already fully covered by the existing,
unmodified `tools/validate_migration_ordering.py` (GOV-01-R06, Slice 4)
and its own `test_contract_without_switch_fails_closed` test — this
session's harness is the GOV-01-R02 half (actually executing and
rollback-verifying a real migration), not a second implementation of
the static ordering lint.

## Real execution (Round 1 — historical, superseded by later rounds' real execution further below, see NR2-8)

Targeted new tests, against the real disposable Colima/`postgres:16-alpine`
container (no mocks):

```
$ backend/.venv/bin/python -m pytest backend/tests/unit/test_migration_safety_harness.py \
    backend/tests/integration/test_migration_safety_harness.py -v
...
15 passed in 1.57s
```

Full backend suite (unit + component + contract + integration):

```
$ backend/.venv/bin/python -m pytest backend/tests/ -v
...
134 passed in 18.33s
```

(134 = the 132 unit+integration tests the subagent itself ran, plus the
2 pre-existing `component`/`contract` scaffold-liveness tests outside
that narrower path — consistent, not a discrepancy.)

Lint/type-check, scoped to the 3 new files:

```
$ backend/.venv/bin/ruff check backend/tests/harness/migration_safety.py \
    backend/tests/integration/test_migration_safety_harness.py \
    backend/tests/unit/test_migration_safety_harness.py
All checks passed!

$ cd backend && .venv/bin/mypy tests/harness/migration_safety.py \
    tests/integration/test_migration_safety_harness.py \
    tests/unit/test_migration_safety_harness.py
Success: no issues found in 3 source files
```

Full-repo lint/type-check (confirms zero regression elsewhere):

```
$ backend/.venv/bin/ruff check backend/
All checks passed!

$ cd backend && .venv/bin/mypy .
Success: no issues found in 24 source files
```

Baselines and governance validators, all independently re-run clean:

```
$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.

$ backend/.venv/bin/python tools/validate_repo_skeleton.py
PASS — all 7 required paths present.

$ backend/.venv/bin/python tools/validate_baseline_binding.py
PASS — all 4 governing baselines correctly bound; SESSION_BOOTSTRAP.md
enforcement metadata present.

$ backend/.venv/bin/python tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml
RESULT: PASS — 7 capability/Rule ID(s), all registered and APPROVED.

$ backend/.venv/bin/python tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml
RESULT: PASS — 9 capability/Rule ID(s), all registered and APPROVED.

$ backend/.venv/bin/python tools/validate_migration_ordering.py
PASS — every migration record is complete and phase-ordered correctly
(or no records exist yet). [No new `.yaml` records were written into
backend/migrations/records/ — per TEMPLATE.md's own text, that directory
is reserved for the first real schema-owning product module, not this
synthetic harness.]

$ backend/.venv/bin/python knowledge/05-QA/tools/capability_drift_check.py
RESULT: PASS — 8 capabilities checked, no drift detected.

$ backend/.venv/bin/python knowledge/05-QA/tools/run_regression.py
AGGREGATE RESULT: PASS (4/4 checks passed, 1 N/A excluded — test_bash_guard.py
correctly N/A, CAP-007 retired per OWN-006/ADR-007).
Record written: knowledge/05-QA/tools/regression-runs/RUN_20261003T083652Z.txt
```

`tools/validate_architecture_gates.py` was deliberately **not** run —
out of scope and frozen per the governing task instructions (unrelated
R04/ADR-010 work in progress on that file).

## Scenario disposition (not self-promoted)

- **SCN-MOD001-022** (positive, GOV-01-R06/TSD §24.2 framing in the
  catalog, GOV-01-R02 implementation obligation) — real evidence now
  exists (`test_scn022_each_phase_completes_in_order`,
  `test_scn022_full_sequence_passes_post_migration_validation`), status
  left at **NOT EXECUTED** in `SCENARIOS.md` (untouched this session).
  Per this project's established model (every prior MOD-001 slice), only
  an independent `veyro-security-reviewer` (Opus) may move this
  scenario's recorded disposition.
- **SCN-MOD001-070** (negative companion) — **corrected 2026-10-03,
  per the independent review's P2-6 finding:** this slice earns SCN-070
  no credit. SCN-070 is specifically the static out-of-order
  destructive-migration lint negative, already proven in Slice 4
  (`tools/validate_migration_ordering.py`,
  `SLICE-4-database-migration-ordering-tooling-2026-09-29.md`); nothing
  in this slice adds to or re-proves it. The original version of this
  record wrongly filed `test_rollback_verification_detects_a_deliberately_broken_rollback`
  under SCN-070 — that test proves GOV-01-R02's own "detects a
  deliberately broken rollback" acceptance criterion directly, a
  distinct obligation with no SCN number of its own in `SCENARIOS.md`,
  not a SCN-070 proof. SCN-070 itself remains **NOT EXECUTED** in
  `SCENARIOS.md` (untouched this session), unaffected either way by
  this slice.
- `ADR_CONFORMANCE.md`'s ADR-015 entry ("Conformance state: PLANNED, not
  yet proven... PASS once SCN-022/070/113/114 execute and pass for
  real") is likewise left untouched — that document is a top-level
  MOD-001 doc out of this session's scope to edit, and in any case its
  own PASS condition explicitly requires SCN-022/070 to actually execute
  *and* be reviewed, not merely executed once.

## CI-budget disclosure (independent review P2-7)

Local timings (1.83-1.91s for the targeted harness tests, ~18.7-18.9s
for the full backend suite) are well inside the 15-minute CI smoke-load
budget `IMPLEMENTATION.md` §5 names, but the repository has no
`.github/workflows` yet — there is no real CI runner to measure this
against. This is disclosed, not proven; the budget claim is local-only
until CI wiring exists.

## Remediation (2026-10-03, same day, same slice)

A fresh independent `veyro-security-reviewer` (Opus, fresh context, no
participation in this slice, `mr_verify.py`-attested: 34 turns, 100%
`claude-opus-5-5`) reviewed the implementation above by executing real
probes against the real disposable Colima Postgres harness, not by
reading code. **Verdict: BLOCKED, P1=1.** Full review:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-INDEPENDENT-REVIEW-2026-10-03.md`.

The P1 (filed as `BUG-049`): `verify_rollback` reported a clean result
for 4 distinct broken-rollback shapes the reviewer constructed and ran
for real — a wrong column type, a missing `NOT NULL`, and two shapes
that clobbered or dropped the surviving `status` column outright (data
loss). This directly contradicted the module's own docstring claims
("never silently 'passes' a broken rollback") and this record's earlier
text repeating that claim — both disproved by execution, not opinion.

**Fixed the same day**, dispatched again to `veyro-backend-engineer`
(Sonnet, `mr_verify.py`-attested: 38 turns, 100% `claude-sonnet-5`, no
fallback). `verify_rollback` now captures and checks both surviving
columns' schema shape (type, nullability) and full row data, not just
`status_code` values, and names every failure path rather than leaking
a database-driver exception. Also fixed in the same pass: P2-1 (empty
snapshot now refused with a named `EMPTY_SNAPSHOT` error instead of
vacuously passing), P2-2 (2 previously-unnamed failure shapes now raise
`RollbackVerificationError`), P2-3 (a new test proves `contract` can
run again after a genuinely correct rollback). P2-4 (resumability/
throttle-interruption testing, TSD §24.2's rolling-deploy N-1
compatibility) and P2-5 (no technical safeguard against a
non-disposable database) were deliberately **not** re-engineered — both
are outside GOV-01-R02's acceptance criterion per the review's own
eligibility section, and are instead disclosed honestly via docstring/
comment notes in the harness itself, per explicit scope instruction not
to expand this bounded slice. Full detail: `BUG-049`'s own file,
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-049-migration-safety-rollback-verification-false-clean.md`.

**Independently re-verified by the orchestrating session** (not taken
on the remediating subagent's report): 22/22 targeted tests (was 15 —
net +7: 2 new P1 negative tests, 2 for P2-1, 2 for P2-2, 1 for P2-3),
141/141 full backend suite (was 134 — the +7 new tests), Ruff clean,
mypy clean (repo-wide, 24 files), all 4 baseline hashes PASS,
repo-skeleton/baseline-binding/migration-ordering/capability-drift
validators PASS, `git diff --check` clean, HEAD ==
`origin/main` unchanged (`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no
commit, no push. Both model-route attestations (implementer and
reviewer) independently confirmed via `mr_verify.py` — neither
self-reported.

**File hashes after remediation:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `94058301e6a5968917f2221aab914b54c1a72c4f8a2df28a04d5e367ad72bde6` |
| `backend/tests/integration/test_migration_safety_harness.py` | `d13edf33014263b2e9aed9df21bfc222c93f5b67a9e1668e27f3b3908258edd7` |
| `backend/tests/unit/test_migration_safety_harness.py` | `3689b9d9828185b6b430c6524d1c534bed0373fb53bc6167da67939c4c629160` (unchanged — no new pure logic needed a unit test this round) |

**P2-6 (this record's own misattribution of rollback detection to
SCN-070) is corrected above**, in the "Scenario disposition" section,
not here — the review found that this record's first version filed the
rollback-detection test under SCN-070, which is incorrect; that section
now states the correction directly rather than duplicating it.

This slice was **not self-approved and not closed** after Round 1 —
superseded by Round 2 below.

## Remediation, Round 2 (2026-10-03, same day)

A second fresh independent `veyro-security-reviewer` (Opus, fresh
context, no participation in the original implementation, the Round-1
fix, or the Round-1 review; `mr_verify.py`-attested: 40 turns, 100%
`claude-opus-5-5`) re-reviewed the Round-1 fix by executing new probes.
Full review: `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-2026-10-03.md`.

**Verdict: BLOCKED, 1 new P1 (NF-1).** Shapes A-D are confirmed
genuinely fixed. The new defect: `verify_rollback` built an id-keyed
dict before comparing rows, so a rollback that dropped the table's
primary key and then duplicated rows (12→13 or 12→24) silently
collapsed back to the expected id set and reported clean — with a
`rows_checked` value that didn't match the live row count. The
original P1-1 required-fix's own "compare constraints" element had
never been implemented or disclosed as skipped. `BUG-049`'s scope was
extended to cover this (not a new bug number), per the reviewer's own
recommendation.

**Fixed the same day**, again via `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested: 70 turns, 100% `claude-sonnet-5`, no
fallback): a new pure `row_count_or_duplicate_violations` function
detects a live row-count change or duplicate `id` directly from the
raw row list, computed before any dict is built; a new
`_table_constraints` helper compares the table's primary-key/unique/
check constraint set via Postgres's own `pg_get_constraintdef`
rendering (robust to representation differences); `ColumnShape` gained
a `default` field and the full live column set is now compared
(catching an extra column a broken rollback introduced); `id`'s own
shape is now compared, not just `status_code`/`status`; `rows_checked`
on a passing result is now the live row count actually compared, never
the snapshot's count. The analogous gap in `validate_post_contract`
(NF-3) was fixed using the same primitives. 4 new negative tests
reproduce the PK-drop-plus-duplicate shapes directly; 3 more pin
previously-correct-but-unpinned detector branches the re-review's
mutation testing flagged as surviving (NF-2: a `NOT NULL`-only
regression, an extra row, a `status`-shape regression); 1 more pins the
negative upgrade→downgrade→upgrade cycle (NF-6 residual). Full detail:
`BUG-049`'s own Round 2 section.

**Independently re-verified by the orchestrating session:** 32/32
targeted tests (was 22), 151/151 full backend suite (was 141), Ruff
clean, mypy clean (repo-wide, 24 files), all 4 baseline hashes PASS,
repo-skeleton/baseline-binding/migration-ordering/capability-drift
validators PASS, `git diff --check` clean, HEAD == `origin/main`
unchanged (`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no commit, no
push.

**File hashes after Round 2:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `c51df06564c3833e4ff06032962464bbe49221e2494f41717db494fa9a1c5f01` |
| `backend/tests/integration/test_migration_safety_harness.py` | `d13829c604684221e402c13cbaa2f2b055f02d3575fe9606f48749a0641b5ab8` |
| `backend/tests/unit/test_migration_safety_harness.py` | `57ec706021c4e45a4e3d7fa08cc2f6c996482060b812c4527d4940ba6dcbd404` |

**C3 (resumability/throttling governed tracking) and C4 (forward-binding
note on non-test reuse)** are recorded durably in `BUG-049`'s own file
(its "C3"/"C4" sections), not duplicated here — both are disclosures,
not code fixes, and remain legitimately deferred per the re-review's
own adjudication (neither is part of GOV-01-R02's acceptance
criterion).

**SCN-MOD001-022 vs SCN-MOD001-070 remain distinguished** exactly as
corrected after Round 1 (see "Scenario disposition" above) — Round 2
changes neither scenario's disposition. **No CI-runner claim is made**
here or in BUG-049: `.github/` does not exist, so all timing figures
above are local-only evidence, not CI evidence.

This slice was **not self-approved and not closed** after Round 2 —
superseded by Round 3 below.

## Remediation, Round 3 (2026-10-03, same day)

A third fresh independent `veyro-security-reviewer` (Opus, fresh
context, no participation in the implementation or either prior
review; `mr_verify.py`-attested: 46 turns, 100% `claude-opus-5-5`)
re-reviewed the Round-2 fix by executing 55 new probes and 28
in-memory mutations. Full review:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R2-2026-10-03.md`.

**Verdict: BLOCKED (P0=0, P1=1, P2=3, P3=6).** The live code was
confirmed correct — every required broken-rollback shape is genuinely
detected and `rows_checked` equals the live row count on every clean
result. The blocking problem (**NR2-1**) was missing regression tests,
not behavior: 4 of the 5 new NF-1 comparisons (constraint, default,
column-set, `id`-shape) in `verify_rollback` could each be individually
deleted via mutation testing while the suite stayed green, because the
only 2 existing tests both dropped the primary key *and* duplicated
rows, so the constraint check and the row-count check shadowed each
other and no test isolated a single comparison; the PK-only-drop test
the Round-2 fix's own required-fix list had named was never added.
**NR2-2** (P2): `validate_post_contract`'s entire NF-3 fix had zero
negative tests. **NR2-3** (P2): a dropped or renamed surviving column
after `contract` leaked a bare `AssertionError`/`UndefinedColumn`
instead of a named violation.

**Fixed the same day** via `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested: 81 turns, 100% `claude-sonnet-5`, no
fallback): 5 new integration tests each isolating exactly one
`verify_rollback` NF-1 comparison with nothing else changed (PK-only
drop, a CHECK constraint added, a DEFAULT added, an extra column,
`id`→bigint); 8 new integration tests for `validate_post_contract`
each asserting a specific named violation string (`TABLE_CONSTRAINTS_CHANGED`,
`STATUS_SHAPE_REGRESSED`, `ID_SHAPE_REGRESSED`, `COLUMN_SET_CHANGED`,
`STATUS_MISMATCH`, `LEGACY_COLUMN_STILL_PRESENT`); the exception leak
fixed for the `status` column by guarding with `_column_exists` (and a
second instance of the same class found one level down, in the
row-selection query, fixed the same way). **Overclaim, corrected
2026-10-03, Round 4, NR3-2: this sentence read as if both `status` and
`id` were covered; only `status` was.** See "Remediation, Round 4"
below for the `id` path, which was not actually fixed until that
round. All 12 previously-surviving mutants the review named
re-confirmed killed via an in-memory-only mutation harness (scratch
plugin under `/tmp/`, never written to the repo, deleted afterward,
hashes unchanged throughout). Docstring corrections: `_table_constraints`/
`verify_rollback` no longer wrongly claim FKs are "deliberately out of
scope" (NR2-6); real residual comparison gaps (identity column,
collation, constraint rename, identical-definition duplicate
constraint) now disclosed (NR2-5); stale unit-test docstring text
corrected (NR2-9); the C4 non-disposable-database notice added to
`migration_safety.py`'s own top-of-module docstring (NR2-10). Full
detail: `BUG-049`'s own "Round 3" section.

**Independently re-verified by the orchestrating session:** 46/46
targeted tests (was 32 — exactly 15 unit + 31 integration, confirmed by
direct count after the review's own NR2-4 finding that a prior count
claim was wrong), 165/165 full backend suite (was 151), Ruff clean,
mypy clean (repo-wide, 24 files), all 4 baseline hashes PASS,
repo-skeleton/baseline-binding/migration-ordering/capability-drift
validators PASS, `git diff --check` clean, HEAD == `origin/main`
unchanged (`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no commit, no
push. Also independently spot-checked the actual remediated code
(`validate_post_contract`'s NR2-3 fix, and the isolated PK-only-drop
test) before accepting the subagent's mutation-kill claims.

**File hashes after Round 3:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `8d7a1bd9a098b50d134e3199b13a127ea7a37f3b0f60b961db5722555fe76b2e` |
| `backend/tests/integration/test_migration_safety_harness.py` | `79650a915aa7bc27fa5533f3e618bab608dcf4edd3c63f9e4d3ea19538c5f65c` |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` |

**NR2-4 (test-count/claim accuracy), NR2-7 (SCN-066 governed home for
resumability/throttling), and NR2-8 (marking Round-1 sections
superseded)** are corrected directly in this document (see the
superseded-notice inline above, "What was built" and "Real execution")
and in `BUG-049`'s own file — not duplicated again here.

This slice was **not self-approved and not closed** after Round 3 —
superseded by Round 4 below.

## Remediation, Round 4 (2026-10-03, same day)

A fourth fresh independent `veyro-security-reviewer` (Opus, fresh
context, no participation in the implementation or any of the three
prior reviews; `mr_verify.py`-attested: 58 turns across the session,
100% `claude-opus-5-5`) re-reviewed the Round-3 fix by executing 11 new
probes and the 12 required mutants plus 3 extra. Full review:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R3-2026-10-03.md`.

**Verdict: BLOCKED (P0=0, P1=0, P2=2, P3=4).** NR2-1 and NR2-2 were
confirmed fully resolved — every required mutant killed, none
shadowed. The blocking problem: **NR3-1** — the Round-3 NR2-3 fix only
guarded `validate_post_contract`'s `status` column; both of its
row-query branches still selected `id` unconditionally, so a renamed
or dropped `id` after `contract` still leaked a bare
`psycopg.errors.UndefinedColumn` instead of the named
`COLUMN_SET_CHANGED` violation that already fires for it. **NR3-2**:
this document, `BUG-049`, and the `BUG_REGISTRY.md` row all overclaimed
the leak as fixed for both `status` and `id` — the NR2-4 overclaim
pattern recurring a second time (see the inline correction above).

**Fixed the same day** via `veyro-backend-engineer` (Sonnet,
`mr_verify.py`-attested: 39 turns, 100% `claude-sonnet-5`, no
fallback): `validate_post_contract` now checks `id`'s existence before
any row-level query and returns early with the already-collected
violations (which already include `COLUMN_SET_CHANGED` naming `id`) if
it's missing. 3 new negative integration tests: `id` renamed, `id`
dropped, `status` renamed (the one missing case alongside the
already-existing `status`-dropped test). The existing `status`-dropped
test and all 3 new tests were tightened (NR3-3) to assert the specific
column name appears in the `COLUMN_SET_CHANGED` violation text, not
just that some such violation exists. Docstring corrected to state
`status` was fixed in Round 2/3 and `id` in Round 4, not both at once.
One more disclosure added: `atttypid::regtype` drops typmod, so a
`varchar(n)` length change would go undetected (NR3-6, latent — no
current column has a typmod). Full detail: `BUG-049`'s own "Round 4"
section.

**Independently re-verified by the orchestrating session:** 49/49
targeted tests (was 46 — exactly the 3 new tests, confirmed by direct
count), 168/168 full backend suite (was 165), Ruff clean, mypy clean
(repo-wide, 24 files), all 4 baseline hashes PASS, repo-skeleton/
baseline-binding/migration-ordering/capability-drift validators PASS,
`git diff --check` clean, HEAD == `origin/main` unchanged
(`e516bedabf3d654ad3ae16d948b8f3522739ddc2`), no commit, no push. Also
independently read the actual `validate_post_contract` fix and the 3
new tests before accepting the subagent's report.

**File hashes after Round 4:**

| File | SHA-256 |
|---|---|
| `backend/tests/harness/migration_safety.py` | `ca697365d117ea3654333835402fc6ab063f2a4c5be1243e86cb2d05faa0a6be` |
| `backend/tests/integration/test_migration_safety_harness.py` | `b60bc3f4b2798aad54b656cb99bffdf06e335566f2821ca3407930a6ad2a57eb` |
| `backend/tests/unit/test_migration_safety_harness.py` | `8b79ba813c599bd4077189c6e2b2430ff6c43bfc0b55b3d0ae92fda3152093f1` |

**NR3-4 (C3 inline marker) and NR3-5 (wording)** are corrected in
`BUG-049`'s own file, not duplicated here.

This Round-4 record is historical; the independent review remained BLOCKED.
The current result and next action are below.

## Remediation, Round 5 (2026-10-03)

The fifth fresh independent review remained **BLOCKED (P2=2)**. Its
executed evidence is in
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R4-2026-10-03.md`.
NR4-1 found bare conversion errors for NULL or non-integer live `id`
values in `validate_post_contract`. NR4-2 found that substring-based
column-identity assertions were vacuous, despite the recorded claim.

The retained `veyro-backend-engineer` Sonnet session fixed both locally.
The validator now emits `ID_VALUE_INVALID` rather than leaking a generic
conversion exception. Two Colima integration negatives cover NULL and
non-integer `id` values. The four column-set negatives parse and assert
the exact expected and live column lists; in-memory K2 and K4 mutants
now fail at those assertions. The engineer's transcript independently
passed `mr_verify.py`: 95/95 turns on `claude-sonnet-5`.

After pruning unused Colima Docker volumes that had exhausted its
writable disk, the approved Postgres fixture ran again. Local results:
**51/51 focused**, **170/170 backend**, Ruff and mypy clean, all four
baseline hashes and evidence-integrity checks PASS. The unrelated
running Docker container was not stopped. These are local results, not
CI evidence. Current file hashes are recorded in `BUG-049`'s Round-5
section and were rechecked against disk. HEAD remains equal to
`origin/main` at `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.

**BUG-049 remains OPEN (Round 5).** This implementation record does not
approve SCN-MOD001-022, credit SCN-MOD001-070, or close the slice.
R04/ADR-010 Amendment A2 remains separately BLOCKED on model assurance.

## Next legally allowed action

A sixth **fresh, independent** `veyro-security-reviewer` Opus session
must review the Round-5 files and executed evidence. Only a passing
review followed by governed reconciliation may close BUG-049 or promote
SCN-MOD001-022. Do not reuse the implementation or any prior review
session for that judgment. No commit or push has occurred.

## Independent R5 result and reconciliation (2026-10-03)

The sixth fresh Opus security reviewer independently returned PASS (P0/P1/P2=0) after executing 51/51 focused, 170/170 backend, live Colima adversarial and mutation probes, Ruff/mypy and governance checks. The reviewer transcript independently passed `mr_verify.py` (85/85 `claude-opus-5-5` turns). Full review: `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R5-2026-10-03.md`. BUG-049 is now CLOSED and SCN-MOD001-022 PASS by separate orchestrator reconciliation; SCN-059/066/070/113 remain NOT EXECUTED. The Round-4 claim of column-identity assertion strength above is historical and corrected only by Round 5. The review disclosed P3 NR5-1–NR5-4 precision items and CAP-008-scope NR5-5; these are not functional P0/P1/P2 defects. No CI or R04 approval is claimed.
