---
doc: DOM002_CONCURRENCY_PATTERN_CODE_REVIEW_ROUND2
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
reviewer: veyro-code-reviewer (fresh context, independent — never saw this codebase before this task)
review_round: 2
responds_to: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND1-2026-10-04.md
remediation_under_review: knowledge/03-Modules/MOD-001/evidence/implementation/DOM002-ROUND1-REMEDIATION-2026-10-04.md
date: 2026-10-04
verdict: PASS (P0=0, P1=0, P2=1, P3=4) — all four of round 1's P1/P2 findings CONFIRMED FIXED by this reviewer's own execution; one new P2 and four new P3s require remediation; SCN-MOD001-009 explicitly NOT promoted
scope: backend/tests/harness/concurrency.py + backend/tests/integration/test_concurrency_harness.py + backend/tests/integration/test_concurrency_harness_order_independence.py + the durable-record edits to REQUIREMENTS.md / SCENARIOS.md / STATUS.md / TEST_RESULTS.md ONLY
---

# Independent code review round 2 — GOV-01-R02 DOM-002 concurrency/versioning test pattern (round-1 remediation re-review)

## 0. Bounded scope and what this review does NOT cover

Reviewed **only**:

| Artifact | State at review time | sha256 | Lines |
|---|---|---|---|
| `backend/tests/harness/concurrency.py` | untracked (`??`) | `980de4e7…9f7634f` | 260 |
| `backend/tests/integration/test_concurrency_harness.py` | untracked (`??`) | `8eb4bd40…6ac9c13f` | 187 |
| `backend/tests/integration/test_concurrency_harness_order_independence.py` | untracked (`??`) | `322f276d…8b2cb49e` | 63 |

Plus the durable-record edits the remediation claims it made to
`knowledge/03-Modules/MOD-001/REQUIREMENTS.md` (DOM-002 row), `SCENARIOS.md`
(`SCN-MOD001-009` entry), `STATUS.md`, and `TEST_RESULTS.md`.

Deliberately **not** reviewed, re-adjudicated, or claimed about: ADR-010 Amendment A2/R04,
`SCN-MOD001-067`, `BUG-048`, `BUG-050`/`BUG-051` themselves, CAP-008's own qualification, or
any file belonging to any module other than MOD-001's DOM-002 slice. Where findings below
reference `tenant_isolation.py`, `postgres.py`, `conftest.py`, `test_architecture_gate_rls.py`
or `tools/validate_architecture_gates.py`, that is solely to characterise behaviour **caused
by the three files under review** — no judgment is offered on those files themselves.

**No file in the repository was edited by this review** other than this report. No
`git add`/`commit`/`push`/`reset`/`stash`/`checkout -- <file>`/`clean` was run. No scenario
was promoted. No fix was implemented.

Every claim in the round-1 report, the remediation record, `CURRENT_STATE.md` and
`CURRENT_HANDOFF.md` was treated as an **unverified assertion to re-derive**, not as fact.
Every command below was run by this reviewer; every output block is actual captured output,
not a paraphrase of someone else's record.

## 1. Reviewer runtime model identity (self-observation — NOT sufficient evidence)

Stated from inside my own context: I am running as **Opus 5, exact model ID
`claude-opus-5`**. `knowledge/05-QA/tools/mr_verify.py:108` sets
`EXPECTED_TIER_BY_AGENT["veyro-code-reviewer"] = "opus"` (verified by direct read this
session), so this self-observation is consistent with the expected tier for this role.

**This self-observation is not evidence on its own.** A model cannot attest its own
identity — that is precisely the failure mode `MODEL_ROUTING.md`'s no-silent-downgrade rule
and `mr_verify.py` exist to close. **The orchestrating session must independently run
`knowledge/05-QA/tools/mr_verify.py` against this subagent's real transcript file
(`…/subagents/agent-<id>.jsonl`), not against this report's prose**, and record the result
before treating this round's verdict as model-assured. I did not run `mr_verify.py` against
myself and make no attestation claim. I did not attempt to locate my own transcript path.

**Orchestrating-session independent verification (added post-review, not self-attested):**
the dispatching session located this subagent's real transcript file
(`~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/ded6b190-d571-4926-bed2-db25ef13ea76/subagents/agent-a8d9c44b42ee6b36c.jsonl`)
and ran `mr_verify.py` directly against it, not against this report's prose:

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/ded6b190-d571-4926-bed2-db25ef13ea76/subagents/agent-a8d9c44b42ee6b36c.jsonl \
    opus veyro-code-reviewer
{
  "verdict": "PASS",
  "reason": "102 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": ["claude-opus-5"],
  "expected_tier": "opus"
}
```

**MR evidence: PASS — 102/102 assistant turns, 100% `claude-opus-5`, matching the
`EXPECTED_TIER_BY_AGENT` requirement for `veyro-code-reviewer`.** No mid-task
substitution/fallback. Model assurance for this review round is independently confirmed, not
merely self-reported. Live state re-confirmed at verification time: `git rev-parse HEAD` =
`95b1911b74d39cbe98e2fc4c81fdea9580f372ef` (unchanged from §2), `git status --porcelain | wc -l`
= 263 (unchanged), the new report file itself being the one addition since dispatch. Docker
state re-confirmed clean: 2 containers (`veyro-mod001-harness-7196bf51` pre-existing,
`frosty_bhabha` pre-existing/unrelated), 2 volumes (one anonymous attached to the pre-existing
container, `tradingview-mcp-session` named/unrelated) — matching this report's own §4.10/§4.12
claim that the reviewer's drill-created leak was fully cleaned up and nothing was left behind.

## 2. Live repository state at review time

```
$ git rev-parse HEAD
95b1911b74d39cbe98e2fc4c81fdea9580f372ef

$ git status --porcelain | wc -l
     263
```

HEAD is **not** round 1's `b8edb26` — it has advanced by three commits
(`b86446d` → `b8edb26` → `95b1911 "Claim DOM-002 independent code review round 2 before
dispatch"`), re-checked rather than assumed. All three reviewed files are **untracked**
(`??`), consistent with the remediation's "no commit/push" claim.

At the end of the review, re-checked: `git rev-parse HEAD` still `95b1911…`,
`git status --porcelain | wc -l` still **263**, all three files still `??`. Nothing staged,
committed, stashed, reset, or discarded by this review. The ~260 uncommitted files from
unrelated work were not touched.

Environment: Colima engine live; `/opt/homebrew/bin/docker` reports CLI `29.6.0`, matching
`postgres.py`'s pinned `TRUSTED_DOCKER_CLI_VERSION` (note: `which docker` resolves to
`/usr/local/bin/docker`, i.e. Docker Desktop's CLI is first on `PATH` — `postgres.py` ignores
`PATH` and uses the pinned realpath, so CAP-008's engine-binding defense is load-bearing on
this machine right now, exactly as round 16 §18.4 recorded). venv `backend/.venv`,
Python 3.14.5, pytest 9.1.1. Live PostgreSQL 16 container per pytest session.

CAP-008 (`CAPABILITY_REGISTRY.md:25`) is **`review_status: APPROVED` (2026-10-04, third
independent fresh-context Opus capability-security review)** — verified by direct read. The
three reviewed files therefore rely on an **approved, registered** capability, not an
unregistered or unqualified one. They introduce **no new capability**: psycopg, the existing
session fixtures, and `subprocess` (already used by `postgres.py` for the same docker
binding) only. See finding **R2-1**, which is a defect in *how* the approved capability's
lifecycle is handled on a new code path, not an unregistered-capability finding.

Owner-reserved restrictions (`.claude/rules/global/owner-reserved-restrictions.md`): no spend
(all tooling free/local), no real member data (synthetic `uuid4()`/`"writer-a"` fixtures
only), no Production deploy, no material product/pricing/business/architecture/scope change.
`.claude/rules/infra/secrets.md`: no credential-shaped value is committed — the harness
password comes from `secrets.token_urlsafe(24)` at runtime in `postgres.py`, and the three
reviewed files contain no literal credential. **No owner-reserved-restriction violation
found.**

## 3. Governing sources read directly this session

| Source | What was verified |
|---|---|
| `.claude/rules/backend/concurrency.md` | the 5 DOM-002 controls + the fail-closed rule, verbatim |
| `.claude/rules/global/owner-reserved-restrictions.md` | the 4 absolute restrictions |
| `.claude/rules/infra/secrets.md` | no committed credential-shaped value |
| `.claude/rules/backend/database.md`, `architecture.md`, `api.md`, `performance.md` | adjacent-profile controls, for cross-rule conflicts (none found; the slice adds no route handler, no domain sub-package, no tenant table) |
| `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md:18-25` | Opus-only code review, fresh context, no self-approval (DC-06) |
| `knowledge/00-System/CAPABILITY_POLICY.md` + `CAPABILITY_REGISTRY.md:25` | CAP-008 `APPROVED`; no new capability introduced |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:589-590` | DOM-001 row → "§24.1 gate 2"; DOM-002 row → "GOV-01-R02; CONC category" + the new P3-5 durable decision text |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:126-140` | GOV-01-R02 IN scope = the *test architecture* later domain modules plug into |
| `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md:383` | gate 2 = **Module dependency/SQL lint** (`CROSS_DOMAIN_SQL_IMPORT`/`REVERSE_EDGE_NOT_EVENT_DRIVEN`) |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md:418-470` | `SCN-MOD001-009` header tag, the round-18 disclosure, the round-1/remediation paragraph |
| `STATUS.md`, `TEST_RESULTS.md`, `CURRENT_STATE.md:1-60`, `CURRENT_HANDOFF.md:1-10` | the implementer's own claims (treated as claims; verified in §4/§5/§6) |
| `knowledge/00-System/REVIEW_IN_FLIGHT.md` | `current_claim: IN_FLIGHT — … round 2`, watchdog `66643874-…`, dispatched 2026-10-04T03:48:59Z — matches this dispatch |
| `backend/tests/integration/conftest.py` | the session-scoped `pg`/`admin`/`runtime_password` fixtures |
| `backend/tests/harness/postgres.py:47`, `:166-205` | `SUPERUSER = "postgres"`; `disposable_postgres`'s `finally`-block `docker rm -f -v` teardown |
| `backend/tests/harness/tenant_isolation.py:49`, `:119-124` | `OWNER_ROLE = "veyro_schema_owner"`; `CREATE SCHEMA … AUTHORIZATION OWNER_ROLE` + `GRANT USAGE ON SCHEMA harness` |
| `tools/validate_architecture_gates.py:647-654`, `:816-824` | the gate scans **every** non-`pg_`/non-`information_schema` namespace by default; `RLS_TABLE_UNCLASSIFIED` logic |
| `knowledge/05-QA/tools/mr_verify.py:106-109` | `EXPECTED_TIER_BY_AGENT["veyro-code-reviewer"] = "opus"` |

## 4. Tests, drills and probes actually run (exact commands, actual output)

### 4.1 Static checks — PASS

```
$ .venv/bin/ruff check tests/harness/concurrency.py tests/integration/test_concurrency_harness.py tests/integration/test_concurrency_harness_order_independence.py
All checks passed!                                                        exit=0

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/mypy --strict tests/harness/concurrency.py tests/integration/test_concurrency_harness.py tests/integration/test_concurrency_harness_order_independence.py
Success: no issues found in 3 source files                                exit=0

$ .venv/bin/mypy tests/ --strict
Success: no issues found in 28 source files
```

`ruff format --check` — **verified round 1's non-blocking disposition rather than assuming
it**:

```
$ .venv/bin/ruff format --check <the 3 reviewed files>
2 files would be reformatted, 1 file already formatted                    exit=1

$ .venv/bin/ruff format --check tests/ app/
9 files would be reformatted, 42 files already formatted

$ ls -la /Users/ahmadmabrouk/Desktop/Veyro/.github
ls: .../.github: No such file or directory
```

Repo-wide drift is real and pre-existing (9 of 51 files), and there is **no** `.github`
workflow directory at all, so `ruff format` is not an enforced project standard. The new
order-independence file is already format-clean. **Not a finding**, same disposition as
round 1, now independently re-verified.

### 4.2 Focused suite — PASS 4/4

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
test_single_writer_succeeds_and_increments_version                        PASSED [ 25%]
test_concurrent_writers_lost_update_detected                              PASSED [ 50%]
test_update_versioned_distinguishes_missing_row_from_version_conflict     PASSED [ 75%]
test_naive_unversioned_update_loses_the_update                            PASSED [100%]
4 passed in 1.65s
```

### 4.3 P1-1 re-check — round 1's exact §4.4 ordering drill — PASS, no `InsufficientPrivilege`

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py \
      "tests/integration/test_architecture_gate_rls.py::test_p1_canonical_harness_passes" -q
.....                                                                    [100%]
5 passed in 1.97s
```

Round 1's output here was `3 passed, 1 error` with
`psycopg.errors.InsufficientPrivilege: permission denied for schema harness`. That error is
gone.

**Code-level ownership contract read directly (not inferred from a schema rename):**
`concurrency.py:108` sets `SCHEMA = "concurrency_harness"`, and
`create_versioned_table` (`:159-180`) runs

```python
admin.execute(
    sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
        schema, sql.Identifier(SUPERUSER)
    )
)
```

with `SUPERUSER` imported from `tests/harness/postgres.py` (`= "postgres"`, verified at
`postgres.py:47`), which is the same role `admin` connects as (`conftest.py:40` →
`pg.superuser_dsn` → `postgres.py:113` → `self.dsn(SUPERUSER, …)`).

I did **not** stop at reading. `CREATE SCHEMA IF NOT EXISTS … AUTHORIZATION …` is still a
no-op on an already-existing schema and still does **not** reassign ownership, so the
determinism claim rests entirely on *exclusivity*. Verified exclusivity mechanically:

```
$ grep -rn "concurrency_harness" . | grep -v /.venv/ | grep -v /.git/ \
      | grep -v backend/tests/harness/concurrency.py | grep -v test_concurrency_harness
knowledge/03-Modules/MOD-001/SCENARIOS.md:462:…
knowledge/03-Modules/MOD-001/evidence/implementation/DOM002-ROUND1-REMEDIATION-2026-10-04.md:25:…
```

Only prose. **No other code anywhere creates, grants on, or references
`concurrency_harness`**, so no other `CREATE SCHEMA IF NOT EXISTS` can win the race and the
`AUTHORIZATION` clause is decisive on the one path that creates it.

**Live catalog proof (throwaway copy, probe module collected AFTER the concurrency module,
so the defect ordering is the one exercised):**

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py \
      tests/integration/test_zzz_catalog_probe.py -q -s
PROBE-SCHEMA-OWNERS [('concurrency_harness', 'postgres'), ('harness', 'veyro_schema_owner'),
                     ('harness_auth', 'veyro_schema_owner'), ('public', 'pg_database_owner')]
5 passed in 1.69s
```

`concurrency_harness` → `postgres`; `harness` → `veyro_schema_owner`. The tenant-isolation
harness keeps its own schema ownership **even when the concurrency module runs first** — the
exact condition that produced round 1's P1-1. The ownership contract genuinely holds.

### 4.4 P1-2 re-check — round 1's exact §4.5 ordering — PASS, no `RLS_TABLE_UNCLASSIFIED`

```
$ .venv/bin/python -m pytest \
      "tests/integration/test_architecture_gate_rls.py::test_p1_canonical_harness_passes" \
      tests/integration/test_concurrency_harness.py \
      "tests/integration/test_architecture_gate_rls.py::test_p4_p5_p6_manifest_platform_table_sequence_and_reviewed_definer" -q
......                                                                   [100%]
6 passed in 2.08s
```

Round 1's output here was `1 failed, 4 passed` with
`RLS_TABLE_UNCLASSIFIED: harness.versioned_widget`. Gone.

**Teardown code read directly.** `test_concurrency_harness.py:61-72`:

```python
@pytest.fixture
def widget(admin: Conn) -> Iterator[UUID]:
    create_versioned_table(admin, VERSIONED_WIDGET, VERSIONED_WIDGET_COLUMNS)
    row_id = uuid4()
    insert(admin, VERSIONED_WIDGET, row_id, {"value": "initial"})
    yield row_id
    drop_versioned_table(admin, VERSIONED_WIDGET)
```

Default (function) scope, **not** session-scoped, **not** `autouse`, and the drop is a real
post-`yield` finalizer. The former `_widget_table` session-scoped autouse fixture is gone
(`grep -n 'scope="session"' test_concurrency_harness.py` → no match). The fourth test
(`:122-138`) manages its own table with an explicit `try/finally`. See **R2-2** for the one
residual gap in this shape.

**Direct catalog verification that nothing `versioned_widget`-shaped survives the module**
(not inferred from the gate test passing — an independent `pg_class` query, run from a probe
module collected after the concurrency module in the same session):

```
PROBE-RELATIONS [('harness', 'access_grant', 'r'), ('harness_auth', 'audit_event', 'r'),
                 ('harness_auth', 'identity', 'r'), ('harness_auth', 'session', 'r')]
PROBE-WIDGETISH []
```

Zero surviving relations whose name contains `widget`. The only residue is the
`concurrency_harness` **schema** itself (empty), which the RLS gate does not flag — it judges
relations, not namespaces (`validate_architecture_gates.py:816-824`, read directly), and both
gate drills above confirm this empirically.

### 4.5 P2-1 re-check — live two-typed-error probe (my own, not the project's test)

`update_versioned` read directly (`concurrency.py:222-243`):

```python
    stmt = sql.SQL("UPDATE {} SET version = version + 1, {} WHERE id = %s AND version = %s").format(
        table.ident, assignments
    )
    rowcount = conn.execute(stmt, [*params, row_id, expected_version]).rowcount
    if rowcount == 0:
        if not _row_exists(conn, table, row_id):
            raise RowNotFound(table, row_id)
        raise VersionConflict(table, row_id, expected_version)
    return rowcount
```

The disambiguation is a real `SELECT EXISTS (SELECT 1 FROM {} WHERE id = %s)`
(`_row_exists`, `:212-219`), executed **only** on the zero-rowcount path — so the mutation
itself remains one atomic statement (rule control 2 is not weakened).

My own probe, against the live harness — a `uuid4()` never inserted, and separately a real
row with a stale version:

```
PROBE-A missing-row    -> RowNotFound: no row at concurrency_harness.versioned_widget: id=9fc871b4-…
PROBE-B stale-version  -> VersionConflict: version conflict on concurrency_harness.versioned_widget: id=cdd4dc26-… expected_version=1
PROBE-C RowNotFound is VersionConflict subclass? False / False; bases RNF=(<class 'Exception'>,) VC=(<class 'Exception'>,)
PROBE-D conn still usable, version = 2
PROBE-E backend_pid / autocommit: (59,) True
```

Two genuinely different typed exceptions, neither a subclass of the other (PROBE-C — so
`except VersionConflict` cannot silently swallow a `RowNotFound`, and vice versa), and the
connection is left usable afterwards (PROBE-D — the extra statement leaves no aborted-
transaction residue). Round 1's PROBE1 produced
`VersionConflict … expected_version=1` for the missing-row case; that fabricated conflict
report is gone. **P2-1 is genuinely fixed, not merely renamed.** (See **R2-4** for a minor
API-shape note on the two classes having no shared base.)

PROBE-E independently re-confirms the harness's own disclosed ceiling (P3-3): both "writers"
share one connection (`backend_pid=59`, `autocommit=True`), so no transaction interleaves and
no row lock is ever contended.

### 4.6 P2-2 re-check — the two-writer precondition, read and re-run

`test_naive_unversioned_update_loses_the_update` (`:141-187`) now reads:

```python
    writer_a_version = read_version(admin, VERSIONED_WIDGET, row_id)
    writer_b_version = read_version(admin, VERSIONED_WIDGET, row_id)
    assert writer_a_version == writer_b_version  # identical precondition to the negative test above

    update_versioned(admin, VERSIONED_WIDGET, row_id, writer_a_version,
                     sql.SQL("value = %s"), ["writer-a"])

    rowcount_b = update_unversioned_blind(admin, VERSIONED_WIDGET, row_id,
                                          sql.SQL("value = %s"), ["writer-b"])
    assert rowcount_b == 1
    …
    assert value == "writer-b"
    assert version == writer_a_version + 1
```

This is genuinely the same shape as `test_concurrent_writers_lost_update_detected`
(`:88-119`): both writers read the same starting version, the equality is asserted, writer A
commits through the **real** `update_versioned`, and writer B — still holding its stale read
— goes through `update_unversioned_blind`. Round 1's P2-2 defect (two blind writes, no
version read at all) is gone. Both docstrings now describe what the code actually does, and
`concurrency.py:18-24` matches.

The P3-1 assertion is present and checks what it claims: `assert version ==
writer_a_version + 1` while `value == "writer-b"` — i.e. the version column is a false
positive. §4.8's mutant **M7** proves this assertion is load-bearing, not decorative.

### 4.7 Order-independence regression file — PASS 2/2, and proven non-vacuous

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -v
test_concurrency_before_canonical_rls_harness_test_review_4_4   PASSED [ 50%]
test_concurrency_between_two_rls_gate_invocations_review_4_5    PASSED [100%]
2 passed in 4.56s
```

**Non-vacuity proof 1 — faithful full pre-fix defect shape** (shared unowned `"harness"`
schema with no `AUTHORIZATION`, session-scoped `autouse` `_widget_table`, **and**
`drop_versioned_table` neutralised, since no teardown existed pre-fix). Reconstructed in a
throwaway full copy (`backend/` + `tools/` under `/tmp/veyro_r2`, import path confirmed
self-contained via `tests.harness.concurrency.__file__ ==
/private/tmp/veyro_r2/backend/tests/harness/concurrency.py`):

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -q
E   psycopg.errors.InsufficientPrivilege: permission denied for schema harness
E   AssertionError: fixture not restored: [rls] FAIL — checked 1 subject(s)
E       RLS_TABLE_UNCLASSIFIED: harness.versioned_widget — no tenant_id column and not a manifest platform table
FAILED …::test_concurrency_before_canonical_rls_harness_test_review_4_4
FAILED …::test_concurrency_between_two_rls_gate_invocations_review_4_5
2 failed in 4.23s
```

Both tests fail, each with **round 1's exact error signature** for the defect it pins.

**Non-vacuity proof 2 — P1-2-ONLY mutant** (the schema fix retained, *only*
`drop_versioned_table`'s body removed). This is the sharper question, because round 1 noted
that relocating the table alone does **not** fix P1-2 — the gate scans every schema:

```
E   RLS_TABLE_UNCLASSIFIED: concurrency_harness.versioned_widget — no tenant_id column and not a manifest platform table
E   ADR010-P1-EVIDENCE {"checked": ["harness.access_grant"], "gate": "rls", … "status": "FAIL",
     "violations": [{"code": "RLS_TABLE_UNCLASSIFIED", … "subject": "concurrency_harness.versioned_widget"}]}
… both order-independence tests FAILED
```

The file catches P1-2 **independently of P1-1**. Both halves of the fix are individually
regression-locked. This is stronger coverage than the remediation record claims for itself.

Throwaway copy deleted; real repo confirmed untouched (§2).

### 4.8 Mutation sensitivity — 6/6 mutants killed

Run against a throwaway full copy (baseline there: `4 passed`); every mutant reverted to a
byte-identical pristine source afterwards; copy deleted; real repo untouched.

| Mutant | Change | Result |
|---|---|---|
| **M1** | `update_versioned` loses its `AND version = %s` predicate | **KILLED** — `Failed: DID NOT RAISE VersionConflict` (test 2) |
| **M2** | zero rowcount returns silently instead of raising | **KILLED** — `DID NOT RAISE VersionConflict` (test 2) **and** `DID NOT RAISE RowNotFound` (test 3) |
| **M5** | version checked in `WHERE` but never incremented in `SET` | **KILLED** — `assert 1 == (1 + 1)` (test 1), `DID NOT RAISE VersionConflict` (test 2), `assert 1 == (1 + 1)` (test 4) — 3 failures |
| **M6** | the new existence check removed, so every zero rowcount raises `VersionConflict` | **KILLED** — `tests.harness.concurrency.VersionConflict: version conflict on …` surfaces inside `pytest.raises(RowNotFound)` |
| **M4a** | the deliberately-broken `update_unversioned_blind` "repaired" into refusing to write | **KILLED** — `assert 0 == 1` (test 4) |
| **M7** | broken fixture keeps no version predicate but **does** bump the version | **KILLED** — `assert 3 == (1 + 1)` (test 4) |

M4a answers "is the rewritten test 4 still load-bearing, or did the P2-2 rewrite make it
vacuous?" — **it is load-bearing**: it dies the moment the broken fixture stops being broken.
M7 answers "is the new P3-1 version assertion load-bearing?" — **yes**: it is the only
assertion that catches a blind write that also increments. M6 is the mutant specific to the
P2-1 fix and it is killed.

### 4.9 Full-suite regression, both collection orders — 202/202 and 202/202

```
$ .venv/bin/python -m pytest tests -q
202 passed in 28.27s

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q
202 passed in 28.49s
```

Observed by me, not copied: **202** in both orders, identical count. Arithmetic reconciles
against round 1's independently-observed 199 baseline: 199 + 1 missing-row test + 2
order-independence tests = 202. The "199/199 contingent on alphabetical ordering" condition
round 1 found is resolved.

### 4.10 Container/volume lifecycle drill (basis for finding R2-1)

The new order-independence file spawns nested `pytest` subprocesses, each of which starts its
own CAP-008 Postgres container. I probed the `subprocess.run(..., timeout=180)` failure path
by lowering the timeout in a throwaway copy until `TimeoutExpired` actually fired:

```
=== volumes BEFORE: 2 ===   containers BEFORE: veyro-mod001-harness-7196bf51 (pre-existing)
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -q
E   subprocess.TimeoutExpired: Command '[…, '-m', 'pytest', '-q', 'tests/integration/test_concurrency_harness.py', …]' timed out after 1.2 seconds
E   subprocess.TimeoutExpired: Command '[…, '-m', 'pytest', '-q', '…::test_p1_canonical_harness_passes', …]' timed out after 1.2 seconds
=== containers AFTER ===
veyro-mod001-harness-a71d453e   Up 3 seconds      <-- LEAKED
veyro-mod001-harness-ee385e63   Up 5 seconds      <-- LEAKED
veyro-mod001-harness-7196bf51   Up 2 hours        (pre-existing, untouched)
=== volumes AFTER: 4 ===                          <-- +2 anonymous volumes LEAKED
```

Both leaked containers and both anonymous volumes were then removed by me with a targeted
`docker rm -f -v <name>` naming **only** those two containers — never `prune`, never `-a`.
Final state re-verified: volume count back to **2**, the unrelated named
`tradingview-mcp-session` volume and the `frosty_bhabha` / pre-existing
`veyro-mod001-harness-7196bf51` containers all intact.

### 4.11 Fixture setup-failure drill (basis for finding R2-2)

In a throwaway copy, injected a failure between `create_versioned_table` and `yield` in the
`widget` fixture, then queried the catalog from a later module in the same session:

```
LEAK-PROBE residual versioned_widget relations: [('concurrency_harness.versioned_widget',)]
AssertionError: LEAKED: [('concurrency_harness.versioned_widget',)]
```

A setup failure after the create leaves the table in place for the remainder of the session —
the exact precondition for P1-2.

### 4.12 Out-of-scope environment observation (not a finding against these files)

One leaked harness container, `veyro-mod001-harness-7196bf51`, was present **before** this
review began (`Up 2 hours` at review start, i.e. created before the files under review were
last written) and is the same container round 1 recorded as pre-existing. It is not
attributable to these three files or to this review, and I left it alone. Dangling-volume
count was 2 at review start and 2 at review end (one anonymous, one named
`tradingview-mcp-session`). Every container my own runs created was reaped. BUG-051 territory
— explicitly out of this review's charge.

## 5. Control-by-control assessment against `.claude/rules/backend/concurrency.md`

| Control | Verdict | Evidence |
|---|---|---|
| **1** — every mutable aggregate's table carries an explicit version column | **SATISFIED** | `concurrency.py:177-179` creates `id uuid PRIMARY KEY, version integer NOT NULL DEFAULT 1, {columns}` — literally the rule's own example form. Live-confirmed by test 1's `read_version` round-trip |
| **2** — every mutation reads, checks and increments the version in **one atomic statement** | **SATISFIED** | `concurrency.py:235-238` is a single `UPDATE … SET version = version + 1, {assignments} WHERE id = %s AND version = %s`. Parameter order `[*params, row_id, expected_version]` matches placeholder order because `assignments` is interpolated before the `WHERE`. The new `_row_exists` statement runs **only** when `rowcount == 0`, i.e. only when no mutation occurred, so it does not split the mutation across statements. M1 and M5 both killed, independently proving the predicate and the increment are each load-bearing |
| **3** — a version mismatch is a typed, distinguishable conflict, never silently overwritten/swallowed/retried | **SATISFIED** (round 1's "with a defect" caveat now cleared) | `VersionConflict` (`:124-137`) and `RowNotFound` (`:140-149`) are distinct typed errors raised at `:239-242`. `grep -n "except"` across all three reviewed files → **no match**; `grep -rn "VersionConflict\|RowNotFound\|update_versioned"` repo-wide outside the slice → **no match**, so nothing catches, swallows or auto-retries them anywhere. M2 (silent zero-return) and M6 (one error standing in for both) both killed. The "distinguishable" claim at `:12-17` is now **true**, verified by my own live probe (§4.5), not just by the new test's name |
| **4** — lost-update behavior is an explicit documented decision | **SATISFIED, and round 1's durability caveat cleared** | reject-and-retry, stated at `concurrency.py:26-37` **and** now recorded non-chronologically in `REQUIREMENTS.md:590`'s own DOM-002 traceability row, which names `concurrency_harness.versioned_widget` explicitly and consistently with the renamed schema. No longer dependent on a rotating `STATUS.md` `updated:` line |
| **5** — append-only exemption | **N/A** | the fixture aggregate is mutable by design; no gap |
| **Fail-closed rule** — a deliberately-broken version-check fixture must be shown to fail closed, not silently pass | **SATISFIED** | `update_unversioned_blind` (`:246-254`) + test 4, now in the genuinely identical two-writer shape. Demonstrated non-vacuous by M4a (test 4 dies when the broken fixture is repaired) and M7 (the version assertion is itself load-bearing). The fail-closed proof is strictly stronger than round 1's |

**All 5 controls plus the fail-closed rule are satisfied. No concurrency-rule violation.**

## 6. Round-1 disposition audit (my own determination, not the remediation's table)

| Round-1 finding | My verdict | Basis (my own execution/reading) |
|---|---|---|
| **P1-1** shared unowned `harness` schema clobbers tenant-isolation ownership | **CONFIRMED FIXED** | §4.3 — drill `5 passed`, no `InsufficientPrivilege`; `AUTHORIZATION postgres` read directly at `:171-174`; exclusivity proven by repo-wide grep; **live catalog probe** shows `concurrency_harness`→`postgres` and `harness`→`veyro_schema_owner` with the concurrency module running first |
| **P1-2** persistent unclassified table fails the ADR-010 RLS gate | **CONFIRMED FIXED** | §4.4 — drill `6 passed`, no `RLS_TABLE_UNCLASSIFIED`; fixture is function-scoped with a real post-`yield` drop; **independent `pg_class` probe** shows zero surviving `widget`-shaped relation; §4.7 proof 2 shows the teardown is independently regression-locked. Residual gap → **R2-2** (P3) |
| **P2-1** zero rowcount conflates missing-row with version-conflict | **CONFIRMED FIXED** | §4.5 — `RowNotFound` is a real distinct type (not a subclass either way, PROBE-C); my own live probe raises the two different exceptions for the two different causes; M6 killed. The docstring's "distinguishable" claim is now accurate |
| **P2-2** test 3 is not "the identical two-writer shape" | **CONFIRMED FIXED** | §4.6 — both writers read the same version and the equality is asserted (`:164`); writer A goes through the **real** `update_versioned`; both docstrings corrected; M4a proves the test is still load-bearing after the rewrite |
| **P3-1** blind path's version staleness never asserted | **CONFIRMED FIXED** | `:187` `assert version == writer_a_version + 1` alongside `assert value == "writer-b"`. **M7 proves it load-bearing** (`assert 3 == (1 + 1)`) — this is not a decorative assertion |
| **P3-2** mutation-sensitivity claim asserted, not demonstrated — *remediation: ACKNOWLEDGED, no code change* | **DISPOSITION STILL REASONABLE** | The claim at `:18-24` is now backed by durable evidence in three independent places: round 1 §4.7 (5/5), the remediation record (4/4), and this report §4.8 (6/6, including two mutants nobody has run before). Declining to build a permanent mutation-testing harness for a bounded remediation is proportionate and is consistent with this project's established "reconstruct in a throwaway copy" idiom. **Not stale, no action needed** |
| **P3-3** "racing writers" unqualified in `STATUS.md`/`SCENARIOS.md` | **PARTIALLY FIXED** | `SCENARIOS.md:465-466` **is** fixed — it explicitly says "documented simulated/sequential shape, not real parallel load — see the harness module's 'Known ceiling' section". `STATUS.md` is **not**: `grep -c "racing writers" STATUS.md` → `1` (at the historical `prior_updated_round18` line), and `grep -n -i "simulated\|sequential\|Known ceiling" STATUS.md` → **zero matches anywhere in the file**. The remediation claimed the round-2 `STATUS.md` entry "stat[es] the qualifier explicitly"; it does not. → **R2-5** (P3) |
| **P3-4** `one_row`/`Conn` duplicated rather than reused | **CONFIRMED FIXED** | `concurrency.py:101-105` carries exactly the explanatory comment round 1 asked for ("this harness has zero dependency on the tenant-isolation harness … by design") |
| **P3-5** control-4 decision lives only in a docstring + a rotating front-matter line | **CONFIRMED FIXED** | `REQUIREMENTS.md:590` read directly: the DOM-002 traceability row now carries the reject-and-retry decision durably and non-chronologically, correctly scoped ("Binds only this fixture"), and names the new `concurrency_harness.versioned_widget` identifier consistently with the code |
| **P3-6** two robustness nits (`AssertionError` under `-O`; `IF NOT EXISTS` masking a shape mismatch; no param-count check) — *remediation: ACKNOWLEDGED, no code change* | **DISPOSITION PARTLY STALE** | The `-O` and param-count halves remain fairly dispositioned (consistent with `tenant_isolation.py`; no real caller exists). But the remediation's reasoning for the `IF NOT EXISTS` half — "the table … is dropped after every test … **no realistic path to a leftover wrong-shape table remains**" — is **demonstrably incomplete**: §4.11 shows a concrete intra-session path where the table is *not* dropped. → **R2-2** (P3) |

**Summary: 2/2 P1s CONFIRMED FIXED. 2/2 P2s CONFIRMED FIXED. 4/6 P3s CONFIRMED FIXED
(P3-1/4/5 plus P3-3's `SCENARIOS.md` half), 1 PARTIALLY FIXED (P3-3), 1 ACKNOWLEDGED-
disposition still reasonable (P3-2), 1 ACKNOWLEDGED-disposition partly stale (P3-6).**

## 7. R04 / "TSD §24.1 gate 2" label discrepancy — my own independent disposition

**I independently AGREE with round 1 §7's conclusion, re-derived from primary sources this
session rather than cited from round 1.** My derivation:

1. `REQUIREMENTS.md:590` — the DOM-002 traceability row's own "Ties to" column reads, verbatim,
   "**GOV-01-R02; CONC category**". There is no R04 tie and no gate reference on that row.
2. `IMPLEMENTATION.md:383` — gate 2 in MOD-001's own 6-gate fixture-plan table is
   "**Module dependency/SQL lint**", failing as `CROSS_DOMAIN_SQL_IMPORT` /
   `REVERSE_EDGE_NOT_EVENT_DRIVEN`, run by `tools/validate_architecture_gates.py --gate
   module-deps`. It has nothing to do with concurrency.
3. `REQUIREMENTS.md:589` — the **immediately preceding** row, DOM-001, is the one that
   legitimately reads "Proven by the module dependency/SQL lint gate | **§24.1 gate 2**".
   Adjacency makes copy-paste from the DOM-001 row by far the most parsimonious explanation.
4. `REQUIREMENTS.md:234` — **GOV-01-R04 is "CI gates"**, a scope I checked specifically rather
   than merely negating. A concurrency/versioning *test pattern* is not a CI gate.
5. `REQUIREMENTS.md:126-140` — GOV-01-R02's IN scope is "the *test architecture* — harness,
   contracts, fixtures, and CI gates — that later domain modules … will plug their real suites
   into". A synthetic-aggregate concurrency/versioning pattern sits squarely inside that, which
   positively supports R02 routing rather than only negating R04.

So `SCN-MOD001-009`'s header tag "GOV-01-R04, TSD §24.1 gate 2 (DOM-002)" is **inaccurate in
its R04/gate-2 portion**; its `CONC` category is correct and consistent with GOV-01-R02. I
also agree with round 1 that disclosing rather than silently rewriting the catalog entry was
the right call, and that correcting the header belongs to a **future Scenario Review round**,
not to an implementation session and **not to this code review**. I have not altered it.

**`SCN-MOD001-009` is NOT promoted by this review, and must not be — regardless of how the
label question resolves.** Three independent reasons:

1. **Promotion is categorically out of scope for a code review.** A code review assesses code
   against rules and baselines; scenario promotion is a Scenario Review / Gatekeeper act under
   `DEVELOPMENT_CONSTITUTION.md` DC-06/DC-07. Nothing in this report should be read as
   promoting, PASSing, or certifying any scenario.
2. **Its own header still names an R04/gate-2 prerequisite**, and ADR-010 A2/R04 is
   independently `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` — a state this review did not examine
   and has no authority over.
3. **A technical reason independent of the label:** finding **R2-1** below is an open P2 on one
   of the three files, and R2-2's residual teardown gap can still reproduce the P1-2 condition
   intra-session. Round 1 withheld promotion on the technical ground that the pattern could not
   coexist order-independently with the suite it joins; that specific ground is now cleared, but
   it is replaced by a narrower one, so the conclusion is unchanged.

## 8. Findings

### R2-1 (P2) — the new order-independence file leaks a running Postgres container and its anonymous volume on the `subprocess.run` timeout path, reintroducing BUG-051's exact disk-exhaustion mechanism on a newly-added code path

`backend/tests/integration/test_concurrency_harness_order_independence.py:38-46`

```python
def _run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *args],
        cwd=BACKEND_ROOT, capture_output=True, text=True,
        timeout=180, check=False,
    )
```

On `timeout`, `subprocess.run` **SIGKILLs** the child. The child is a full pytest session that
owns a CAP-008 Postgres container, whose only teardown is the `finally`-block `docker rm -f -v`
in `disposable_postgres` (`postgres.py:193-205`). SIGKILL cannot run that `finally`. And per
CAP-008's own registered scope text and round 16's R16-3 correction, the container **never
exits on its own**, so `--rm` never fires either — that `rm -f -v` call is the *only* thing
that ever removes it or its anonymous `/var/lib/postgresql/data` volume.

Demonstrated live (§4.10): forcing the timeout left **two running containers and two orphaned
anonymous volumes** behind (volume count 2 → 4). This is precisely BUG-051's mechanism — the
defect that previously accumulated 473 orphaned volumes / 18.94 GB and filled the Colima VM's
20 GB disk to 100%, blocking every Postgres-backed test in the project. It is now reachable
again, on a file added *this* round, with no ceiling across repeated runs.

Mitigating facts, stated honestly: `TimeoutExpired` propagates, so the test **fails loudly** —
this is not a silent leak. A normal run of each subprocess takes ~2 s against a 180 s budget,
so the timeout needs a ~90× overrun; plausible triggers are a cold image pull, a contended
Colima VM, or a hung container readiness wait (`_wait_ready`'s own `ready_timeout_s=60`
nests inside the 180 s). That is why this is P2 and not P1.

A second, lower-severity aspect of the same design, recorded for completeness rather than as a
separate finding: when the full suite runs, the parent session already holds a container, so
each subprocess transiently **doubles** the live container/volume count. That stays inside
CAP-008's registered "a disposable Postgres container per pytest session" scope (each session
does get exactly one) and the ports are loopback-published on random ports so they do not
collide — but it is a new peak-resource profile for an approved capability whose registered
scope text was written before nested sessions existed.

Remediation options (for the implementer to choose — not prescribed here): reap any
`veyro-mod001-harness-*` container the parent did not itself create after each subprocess
call, including on the `TimeoutExpired` path; or drive the child with `Popen` plus a graceful
`SIGTERM`-and-wait so the child's `finally` can run before escalating to `SIGKILL`; or pass the
child a pre-agreed container-name prefix the parent can clean up deterministically. Whichever
is chosen, the leak condition should be regression-locked the same way this round's authors
correctly regression-locked P1-1/P1-2.

### R2-2 (P3) — the `widget` fixture's teardown is post-`yield` with no `try/finally`, so any setup failure after `create_versioned_table` leaks the table for the rest of the session — the exact P1-2 condition this round just fixed

`backend/tests/integration/test_concurrency_harness.py:61-72`

The drop at `:72` is a plain post-`yield` statement. Under pytest, a yield-fixture that raises
**before** reaching `yield` never registers its finalizer, so `drop_versioned_table` is never
called and `concurrency_harness.versioned_widget` survives for the remainder of the session.
Demonstrated (§4.11): `LEAKED: [('concurrency_harness.versioned_widget',)]`.

Two reasons this is a real finding rather than a theoretical nit:

1. It is the **same internal inconsistency the file itself already resolves elsewhere** — the
   sibling test `test_update_versioned_distinguishes_missing_row_from_version_conflict`
   (`:129-138`) wraps its own create in exactly the `try/finally` this fixture lacks, so the
   author clearly knew the idiom.
2. It makes the remediation's own P3-6 disposition ("no realistic path to a leftover
   wrong-shape table remains") inaccurate, and it reproduces the Blocker-tier consequence
   round 1 called out as *worse than a red test*: a reviewer seeing the ADR-010 RLS gate go
   `RLS_TABLE_UNCLASSIFIED` would reasonably suspect the gate or the RLS fixture, not a
   concurrency fixture's setup failure.

Reachability is low — the only statements between the create and the `yield` are `uuid4()` and
`insert`, and `insert` fails realistically only against a pre-existing wrong-shape table (the
`CREATE TABLE IF NOT EXISTS` masking risk round 1 flagged as P3-6) or a transient connection
error. The fix is a two-line `try/finally`.

### R2-3 (P3) — `drop_versioned_table`'s docstring claims the schema is "reused across tests/sessions", which is false for sessions

`backend/tests/harness/concurrency.py:183-188`

> "Does not drop the schema — `SCHEMA` is reused across tests/sessions and owns nothing else
> worth tearing down."

The "across tests" half is correct. The "across sessions" half is not: `conftest.py:33-35`'s
`pg` fixture is session-scoped over `disposable_postgres()`, which creates a **fresh container
per pytest session** and force-removes it (with its volume) on teardown. No schema can survive
a session boundary. In an evidence artifact whose purpose is to document a proof method — and
in a module that round 1 already found had two inaccurate docstrings (P2-2) — a false
durability claim about the very object the teardown contract reasons over is worth correcting.
The *behaviour* is fine; only the stated justification is wrong.

### R2-4 (P3) — `VersionConflict` and `RowNotFound` are siblings off `Exception` with no shared base, so the advertised plug-in template gives a domain adopter no single type to catch

`backend/tests/harness/concurrency.py:124` and `:140` (confirmed at runtime, §4.5 PROBE-C:
`bases RNF=(<class 'Exception'>,) VC=(<class 'Exception'>,)`)

The distinction itself is correct and is exactly what P2-1 required — these two must not be
confusable, and they are not. But `concurrency.py:65-77` explicitly advertises this module as
the plug-in template for DOM-002's co-owners (MOD-002, MOD-019, MOD-020, MOD-034, MOD-037) and
tells them to "reuse `VersionConflict`/`RowNotFound` (or your own typed equivalents) as the API
boundary errors `.claude/rules/backend/api.md`'s typed-errors control requires". A real
adopter's route handler usually wants *both* a narrow catch (409 vs 404) **and** a broad one
("any optimistic-concurrency failure from this aggregate"). With no shared base, the broad
case can only be written as a tuple catch that silently goes stale when a third error type is
added. A one-line shared base (e.g. `class ConcurrencyError(Exception)` with both inheriting
from it) would preserve the distinction while making the family extensible. Flagged for
whoever adopts the template, not a defect in the harness's own behaviour.

### R2-5 (P3) — the remediation record's P3-3 disposition is inaccurate: `STATUS.md` does not state the simulated/sequential qualifier anywhere

`DOM002-ROUND1-REMEDIATION-2026-10-04.md:132` claims P3-3 is "FIXED", with `STATUS.md`'s
round-18 entry "left as historical record per this project's append-don't-rewrite convention,
**with the round-2 entry (this remediation) stating the qualifier explicitly**".

Verified directly: `grep -n -i "simulated\|sequential\|Known ceiling" STATUS.md` returns
**zero matches in the entire file**, while `grep -c "racing writers" STATUS.md` returns `1`.
The `SCENARIOS.md` half of P3-3 **is** genuinely fixed (`SCENARIOS.md:465-466` carries the
qualifier and points at the harness's "Known ceiling" section). The `STATUS.md` half is not —
the claimed mitigation does not exist.

Leaving the historical round-18 line unqualified is defensible under this project's
append-don't-rewrite convention; **asserting in a durable evidence record that a qualifier was
added when it was not** is the record-accuracy defect class this project has repeatedly filed
as a finding (NR10-2, R13-1, R14-2, R17-1). Low severity, cheap fix: either add the sentence
the record claims, or correct the record to say the `STATUS.md` half was deliberately left to
the historical entry.

### Durable-record edits — otherwise verified accurate

Every other factual claim I checked in the four durable records is accurate:

- **`REQUIREMENTS.md:590`** — DOM-002 row carries the reject-and-retry decision durably, scoped
  correctly, naming `concurrency_harness.versioned_widget` consistently with the code. ✓
- **`SCENARIOS.md:418-470`** — `SCN-MOD001-009` is still `NOT EXECUTED` / not promoted / not
  claimed PASS; the round-1-and-remediation paragraph is appended rather than overwriting the
  round-18 disclosure; it explicitly flags that its own historical text still says
  `harness.versioned_widget` while the aggregate now lives in `concurrency_harness` — i.e. the
  inconsistency is **disclosed, not silent**, which is the right call. ✓
- **`STATUS.md`** / **`TEST_RESULTS.md`** front matter — "202/202 in both default and reversed
  collection order", "`ruff check .`/`mypy --strict` clean across 28 files", "M1/M2/M5/M6 all
  killed", "new exclusively-owned `concurrency_harness` schema", "per-test create/drop", "new
  typed `RowNotFound`", "§4.4/§4.5 drills re-run clean", "order-independence file proven
  non-vacuous", "`SCN-MOD001-009` still NOT promoted": **every one independently reproduced by
  me** (§4.1-§4.9). The 199 + 1 + 2 = 202 arithmetic reconciles against round 1's own
  independently-observed 199. ✓
- **`REVIEW_IN_FLIGHT.md`** — `current_claim: IN_FLIGHT` for this exact round-2 dispatch,
  watchdog `66643874-e295-4d53-a846-ee79cb6c3a44`. Correctly claimed before dispatch; left
  untouched by me. ✓

No governing baseline (`PROJECT_INDEX.md`'s four protected artifacts) was modified, renamed, or
regenerated by this round. No drift from the governing baselines found in the reviewed slice.

## 9. Verdict

**Demonstrated result — GENUINE and materially stronger than round 1's.** Re-executed live by
me: 4/4 focused tests pass; 202/202 full suite in **both** collection orders with identical
counts; `ruff check` and `mypy --strict` clean; both of round 1's reproducer drills (§4.4/§4.5)
now pass with their exact former error signatures absent; the schema-ownership contract
verified at the **catalog** level, not just by a renamed constant; zero `versioned_widget`-
shaped relation surviving the module, verified by an independent `pg_class` query; `RowNotFound`
and `VersionConflict` proven to be two genuinely distinct typed errors by my own live probe;
the fail-closed differential now using the genuinely identical two-writer shape and proven
load-bearing; **6/6 mutants killed**, including two (M4a, M7) nobody had run before, which
specifically target the P2-2 rewrite and the P3-1 assertion; and the new order-independence
regression file proven non-vacuous **twice over**, including against a P1-2-only revert, which
shows both halves of the P1 fix are individually regression-locked.

**All four of round 1's blocking findings (P1-1, P1-2, P2-1, P2-2) are CONFIRMED FIXED by my
own execution and reading, not by accepting the remediation record's account.**

**OVERALL: PASS — P0=0, P1=0, P2=1, P3=4.**

This follows this project's own established verdict convention (round 16 returned
`PASS — P0=0/P1=0/P2=3/P3=4`): P1=0 clears the blocking bar, while the one P2 and four P3s are
real defects that require remediation and are **not** waived by this verdict. R2-1 in
particular should be fixed before the suite is relied on in any unattended/CI context, because
its consequence class is a documented prior incident (BUG-051) that halted all Postgres-backed
testing in this project.

**PASS here means: these three files, as written, satisfy all five `concurrency.md` controls
and the fail-closed rule, introduce no unregistered or unqualified capability use, violate no
owner-reserved restriction, and show no drift from the governing baselines — with one P2 and
four P3s to remediate.** It is not a certification, not a Gatekeeper approval, and not a
scenario promotion.

**`SCN-MOD001-009` is NOT promoted by this review.** See §7 for the three independent reasons.
No scenario, requirement, bug, or capability status is advanced by this report.

## 10. Next action

1. **Orchestrating session — model assurance (do this first):** run
   `knowledge/05-QA/tools/mr_verify.py <path-to-this-subagent's-real-transcript>.jsonl opus
   veyro-code-reviewer` against this reviewer's **actual transcript file**, not against this
   report's prose, and record the result in this report's §1 and in `CURRENT_STATE.md`. My §1
   self-observation is explicitly **not** evidence. If `mr_verify.py` does not return PASS for
   tier `opus`, this round's verdict is `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` per
   `DEVELOPMENT_CONSTITUTION.md` line 21, regardless of its technical content.
2. **Orchestrating session — clear the claim only after the result is recorded.**
   `REVIEW_IN_FLIGHT.md`'s `current_claim` (round 2, watchdog
   `66643874-e295-4d53-a846-ee79cb6c3a44`) must be cleared **only once the `mr_verify.py`
   result and this verdict are both durably recorded** — per that file's own protocol ("Clear
   on result recorded, not merely on subagent completion"). I did not touch that file.
3. **Implementation session (Sonnet appropriate — harness hygiene and record accuracy, not an
   ADR-005 Decision 1 slice):** remediate **R2-1** (the subprocess-timeout container/volume
   leak — highest priority, and regression-lock it); then **R2-2** (two-line `try/finally` in
   the `widget` fixture), **R2-3** (one-line docstring correction), **R2-5** (either add the
   `STATUS.md` qualifier the record claims, or correct the record). **R2-4** is a judgment call
   for whoever adopts the template and may reasonably be deferred with a recorded disposition.
   While fixing R2-2, also update the remediation record's now-partly-stale P3-6 disposition
   (§6) rather than leaving it standing.
4. **Do not promote `SCN-MOD001-009`** on this round's evidence.
5. **Future Scenario Review round:** correct `SCN-MOD001-009`'s header tag per §7 (to
   "GOV-01-R02, CONC (DOM-002)", removing the R04/gate-2 prerequisite). This is not an
   implementation-session or code-review action.
6. **Round-3 re-review (if dispatched):** R2-1 is reproducible by the exact drill in §4.10
   (lower `timeout` until `TimeoutExpired` fires, then compare `docker ps -a` / `docker volume
   ls` before and after — and clean up only the containers the drill itself created, never
   `prune`). R2-2 is reproducible by the §4.11 drill. A round-3 reviewer should re-run the §4.8
   mutation set against any changed `update_versioned`, and should re-run §4.7's **P1-2-only**
   mutant, since that is the drill that proves the teardown half of the fix is independently
   locked.
