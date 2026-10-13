---
doc: DOM002_CONCURRENCY_PATTERN_CODE_REVIEW_ROUND1
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
reviewer: veyro-code-reviewer (fresh context, independent)
review_round: 1
date: 2026-10-04
verdict: BLOCKED (P0=0, P1=2, P2=2, P3=6)
scope: backend/tests/harness/concurrency.py + backend/tests/integration/test_concurrency_harness.py ONLY
---

# Independent code review — GOV-01-R02 DOM-002 concurrency/versioning test pattern (round 18 implementation, review round 1)

## 0. Bounded scope and what this review does NOT cover

Reviewed **only** the two files round 18 (2026-10-04) created:

- `backend/tests/harness/concurrency.py` (165 lines, untracked, sha256 `d1b7fd2e…52121f`)
- `backend/tests/integration/test_concurrency_harness.py` (129 lines, untracked, sha256 `f970fde2…833bf2`)

Deliberately **not** reviewed, re-adjudicated, or claimed about: ADR-010 Amendment A2/R04,
SCN-MOD001-067, BUG-048, CAP-008's own qualification, BUG-050/051, or any other module's
code. Where findings below reference `test_architecture_gate_rls.py`,
`tenant_isolation.py`, `conftest.py` or `validate_architecture_gates.py`, that is solely
to characterise a defect **caused by the two files under review** — no judgment is offered
on those files themselves. No file was edited; no fix was implemented.

## 1. Reviewer runtime model identity (self-observation)

Stated from inside my own context: I am running as **Opus 5, exact model ID
`claude-opus-5`**. `knowledge/05-QA/tools/mr_verify.py:108` sets
`EXPECTED_TIER_BY_AGENT["veyro-code-reviewer"] = "opus"`, so my runtime tier **matches**
the expected tier for this role. I have no reason to believe I am running at a downgraded
tier. I did not run `mr_verify.py` against myself (self-attestation is not evidence); the
orchestrating session must verify externally against this transcript.

**Orchestrating-session independent verification (added post-review, not self-attested):**
the dispatching session ran `knowledge/05-QA/tools/mr_verify.py` directly against this
subagent's real transcript file
(`agent-a46dcce700155caa7.jsonl`, `spawnDepth: 1`, `requestShape: foreground`, per its own
`.meta.json`), not against this report's prose:

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    <project-transcripts>/23fb371d-598e-479a-8397-a51a2b6a337b/subagents/agent-a46dcce700155caa7.jsonl \
    opus veyro-code-reviewer
{
  "verdict": "PASS",
  "reason": "104 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": ["claude-opus-5"],
  "expected_tier": "opus"
}
```

**MR evidence: PASS — 104/104 assistant turns, 100% `claude-opus-5`, matching the
`EXPECTED_TIER_BY_AGENT` requirement for `veyro-code-reviewer`.** No mid-task
substitution/fallback. Model assurance for this review round is independently
confirmed, not merely self-reported — the no-silent-downgrade rule
(`MODEL_ROUTING.md`) is satisfied.

## 2. Live repository state at review time

```
$ git rev-parse HEAD
b8edb2629dc359fcbd2aa575349ba6ce2899df9d
```

Both reviewed files are **untracked** (`??`), consistent with the round-18 record's "no
commit/push" claim. 259 entries in `git status --porcelain` at start and at end — HEAD
unchanged, nothing staged, committed, stashed or reset by this review. Both reviewed files
were re-hashed at the end of the review and are byte-identical to what I read.

Environment: Colima running (`macOS Virtualization.Framework`, aarch64, docker runtime);
`/opt/homebrew/bin/docker` → `Cellar/docker/29.6.0/bin/docker`, matching
`postgres.py`'s pinned `TRUSTED_DOCKER_CLI_REALPATH`. CAP-008 is `review_status: APPROVED`
(2026-10-04, round-17 Opus assurance) per `CAPABILITY_REGISTRY.md:25`, so the reviewed
files' reliance on the disposable-Postgres capability is **not** unregistered or
unqualified capability use. The two files introduce **no new capability** (psycopg plus the
existing session fixtures only).

## 3. Governing sources read directly this session

| Source | What was verified |
|---|---|
| `.claude/rules/backend/concurrency.md` | the 5 DOM-002 controls + the fail-closed rule (verbatim) |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:590` | DOM-002 row → "Ties to: **GOV-01-R02; CONC category**" |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:589` | DOM-001 row → "Ties to: **§24.1 gate 2**" |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:128-140` | GOV-01-R02 IN-scope = the *test architecture* (harness/contracts/fixtures) later domain modules plug into |
| `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §4 (≈L383) | gate 2 = **Module dependency/SQL lint** (`CROSS_DOMAIN_SQL_IMPORT`/`REVERSE_EDGE_NOT_EVENT_DRIVEN`) |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md:418-447` | `SCN-MOD001-009` header tag + the round-18 disclosure note |
| `CURRENT_STATE.md:4`, `CURRENT_HANDOFF.md:4`, `STATUS.md:4`, `TEST_RESULTS.md:5` | the implementer's own claims (treated as claims, verified below) |
| `backend/tests/integration/conftest.py` | the generic `pg`/`admin` session fixtures (L33-43) and `runtime_password` (L45-50) |
| `.claude/rules/global/owner-reserved-restrictions.md`, `.claude/rules/infra/secrets.md` | no spend, no real member data, no Production, no committed credential-shaped value |

## 4. Tests and checks actually run (exact commands, actual output)

All runs on the live approved Colima binding with a real disposable PostgreSQL 16.15
container (`server_version=160015`, verified in-session), venv `backend/.venv`
(Python 3.14.5, pytest 9.1.1).

### 4.1 Static checks — PASS

```
$ .venv/bin/ruff check tests/harness/concurrency.py tests/integration/test_concurrency_harness.py
All checks passed!                                                       exit=0

$ .venv/bin/mypy --strict tests/harness/concurrency.py tests/integration/test_concurrency_harness.py
Success: no issues found in 2 source files                               exit=0

$ .venv/bin/ruff format --check <same two files>
2 files would be reformatted                                             exit=1
```

`ruff format` drift is **not** treated as a finding: `ruff format --check tests/ app/`
reports "9 files would be reformatted, 41 files already formatted" repo-wide, and the
repository has no `.github/workflows` at all, so `ruff format` is not an enforced project
standard. The two new files are consistent with existing practice.

### 4.2 Focused suite — PASS 3/3 (confirms the implementer's claim)

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
test_single_writer_succeeds_and_increments_version PASSED   [ 33%]
test_concurrent_writers_lost_update_detected       PASSED   [ 66%]
test_naive_unversioned_update_loses_the_update      PASSED   [100%]
3 passed in 1.59s
```

### 4.3 Default-order regression suites — PASS (confirms "zero regressions", in default order only)

```
$ .venv/bin/python -m pytest tests/integration -q
139 passed in 14.14s

$ .venv/bin/python -m pytest tests -q
199 passed in 25.54s
```

Independently reproduces the round-18 claim of **199/199**. See P1-1/P1-2: this result is
**contingent on pytest's default alphabetical file ordering** and is not order-independent.

### 4.4 Ordering drill — FAILS (P1-1)

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py \
      "tests/integration/test_architecture_gate_rls.py::test_p1_canonical_harness_passes" -q
...
tests/integration/conftest.py:48:
tests/harness/tenant_isolation.py:124: in create_tenant_table
    admin.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, rt))
E   psycopg.errors.InsufficientPrivilege: permission denied for schema harness
ERROR tests/integration/test_architecture_gate_rls.py::test_p1_canonical_harness_passes
3 passed, 1 error in 1.49s
```

### 4.5 RLS-gate catalog drill — FAILS (P1-2)

Role/schema setup forced first so P1-1 cannot mask P1-2:

```
$ .venv/bin/python -m pytest \
      "…test_architecture_gate_rls.py::test_p1_canonical_harness_passes" \
      tests/integration/test_concurrency_harness.py \
      "…test_architecture_gate_rls.py::test_p4_p5_p6_manifest_platform_table_sequence_and_reviewed_definer" -q
...
>       assert restored.status == gates.PASS, f"fixture not restored: {restored.render()}"
E       AssertionError: fixture not restored: [rls] FAIL — checked 1 subject(s)
E           RLS_TABLE_UNCLASSIFIED: harness.versioned_widget — no tenant_id column and not a manifest platform table
E       assert 'FAIL' == 'PASS'
tests/integration/test_architecture_gate_rls.py:133: AssertionError
1 failed, 4 passed in 2.08s
```

### 4.6 Semantic probes (throwaway script outside the repository, since deleted)

```
PROBE1 missing-row -> VersionConflict: version conflict on harness.versioned_widget: id=1f6080f4-… expected_version=1
PROBE2 blind update: version before=1 after two blind writes=1 (stale=True)
PROBE3 stale(b=1) blind writer rowcount=1 final=('writer-b', 2) -> writer-a's versioned write lost
PROBE4 admin autocommit=True backend_pid=59 server=160015
```

### 4.7 Mutation sensitivity drill — 5/5 mutants killed (the drill round 18 asserted but did not run)

Run against a throwaway copy of the whole `tests/` tree at `/tmp/veyro_mutant` (baseline
there: `3 passed`); repository untouched; copy deleted afterwards.

| Mutant | Change to `concurrency.py` | Result |
|---|---|---|
| M1 | `update_versioned` loses its `AND version = %s` predicate | **KILLED** — `Failed: DID NOT RAISE VersionConflict` (test 2) |
| M2 | `rowcount == 0` returns silently instead of raising (control 3 violation) | **KILLED** — `DID NOT RAISE VersionConflict` (test 2) |
| M3 | conflict silently retried as a blind overwrite (control 3's named prohibition) | **KILLED** — `DID NOT RAISE VersionConflict` (test 2) |
| M4 | the deliberately-broken `update_unversioned_blind` *repaired* to be version-checked | **KILLED** — `assert 0 == 1` at test file L121 (test 3) |
| M5 | version checked but never incremented (control 2's second half) | **KILLED** — tests 1 **and** 2 fail |

M4 is the direct answer to "could test 3 pass vacuously": **no** — test 3 is load-bearing
and dies when the broken fixture stops being broken.

## 5. Control-by-control assessment against `.claude/rules/backend/concurrency.md`

| Control | Verdict | Evidence |
|---|---|---|
| 1 — explicit version column | **SATISFIED** | `concurrency.py:103-106` creates `version integer NOT NULL DEFAULT 1` |
| 2 — read/check/increment in **one atomic statement** | **SATISFIED** | `concurrency.py:141-144` is a single `UPDATE … SET version = version + 1, {assignments} WHERE id = %s AND version = %s`; parameter order (`[*params, row_id, expected_version]`) matches placeholder order because `assignments` is interpolated before the `WHERE`. Verified live; M1 and M5 both killed |
| 3 — typed conflict, never silently overwritten/swallowed/retried | **SATISFIED with a defect** | `VersionConflict` (`concurrency.py:74-85`) is raised at `:146` and is **never** caught anywhere in the repo (`grep -rn "except VersionConflict\|except Exception"` → no match in either file; `VersionConflict` appears in no other module). M2/M3 killed. **But** it is not *distinguishable* from a missing row — see P2-1 |
| 4 — lost-update resolution is an explicit documented decision | **SATISFIED** | reject-and-retry, `concurrency.py:22-29`; also named in `STATUS.md:4`. Durability caveat: P3-5 |
| 5 — append-only exemption | **N/A** | the fixture aggregate is mutable by design; no gap |
| Fail-closed rule — a deliberately-broken version-check fixture must be shown to fail closed, not silently pass | **SATISFIED** | `update_unversioned_blind` (`concurrency.py:150-158`) + test 3; now additionally demonstrated by the 5/5 mutation drill in §4.7, which round 18 itself did not run (P3-2) |

## 6. Findings

### P1-1 — `create_versioned_table` creates the shared `harness` schema without `AUTHORIZATION`, clobbering the tenant-isolation harness's schema ownership and hard-erroring the whole GOV-01-R02 integration suite under a different execution order

`backend/tests/harness/concurrency.py:100`

```python
admin.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
```

The tenant-isolation harness creates the *same* schema with an explicit owner
(`backend/tests/harness/tenant_isolation.py:119`: `CREATE SCHEMA IF NOT EXISTS {}
AUTHORIZATION {OWNER_ROLE}`), then `SET ROLE`s to that owner
(`as_schema_owner`, L105) to grant USAGE and create the tenant table.

Because `CREATE SCHEMA IF NOT EXISTS … AUTHORIZATION …` is a **no-op when the schema
already exists** (it does not reassign ownership), whichever fixture runs first decides who
owns `harness`. `test_concurrency_harness.py:44-46` registers `_widget_table` as a
**session-scoped `autouse`** fixture, so if any test in that module runs before
`runtime_password`, schema `harness` ends up owned by `postgres`, and
`create_tenant_table`'s `GRANT USAGE ON SCHEMA harness` — executed as the non-superuser
`veyro_owner` — fails with `InsufficientPrivilege` (reproduced verbatim in §4.4). That
error occurs in `conftest.py:48`, i.e. in the **session fixture chain**, so it takes down
the tenant-isolation, authn, migration-safety and architecture-gate-RLS suites together,
not just one test.

This is **latent, not currently breaking**: pytest's default collection order puts
`test_architecture_gate_rls.py` before `test_concurrency_harness.py` alphabetically, which
is why §4.3 is green. It becomes real under any of: explicit file arguments in another
order, a `-k`/`-m` selection that reaches the concurrency module first, a random-order or
`xdist` plugin, or a future file rename. The round-18 claim that the pattern "reuses only
the generic `pg`/`admin` fixtures … not the tenant-isolation-specific ones"
(`CURRENT_STATE.md:4`) is accurate about *fixtures* but materially incomplete: the pattern
also shares the same database **and the same `harness` schema**, and mutates its ownership.

### P1-2 — `harness.versioned_widget` is an unclassified relation inside the ADR-010 RLS gate's scanned scope, and is never dropped, so it makes that Blocker-tier gate report FAIL whenever a gate test runs after the concurrency module

`backend/tests/harness/concurrency.py:103-106` + `:163` (`VERSIONED_WIDGET =
VersionedTable("harness", "versioned_widget")`), and
`backend/tests/integration/test_concurrency_harness.py:44-46` (the fixture has **no
teardown** — the table persists for the whole session).

`tools/validate_architecture_gates.py:816-824` judges **every** `r`/`p` relation in a
scanned schema, regardless of grants:

```python
for rel in catalog.relations:            # D4.1, D4.4
    if rel.schema not in scanned: continue
    if rel.kind in ("r", "p"):
        if not rel.has_tenant_id:
            if manifest.platform_scope_relations.get(q) != "table":
                v.append(Violation("RLS_TABLE_UNCLASSIFIED", q, …))
```

`harness.versioned_widget` is an ordinary table with no `tenant_id`, and
`backend/migrations/rls-manifest.json` contains `"platform_scope_relations": {}` — so it is
`RLS_TABLE_UNCLASSIFIED` by construction. The gate's default scope makes this unavoidable
by relocating the table: `test_architecture_gate_rls.py:105-108`'s `_gate()` helper passes
no `schemas`, and `validate_architecture_gates.py:654` then scans **every** non-`pg_`,
non-`information_schema` namespace. Reproduced verbatim in §4.5, where it breaks
`_broken()`'s post-restore `assert restored.status == gates.PASS`
(`test_architecture_gate_rls.py:133`) — the invariant that keeps every ADR-010 negative
case honest.

Also latent today for the same ordering reason as P1-1. The consequence if it ever fires is
worse than a red test: a reviewer sees the ADR-010 RLS gate FAIL and would reasonably
suspect the gate or the RLS fixture, not a concurrency harness table.

Cheapest fixes (for the implementer to choose, not prescribed here): make `_widget_table` a
`yield` fixture that `DROP TABLE`s (and drops the schema if it created it), and/or create
the aggregate in a schema the harness owns exclusively while also giving
`create_versioned_table` an explicit `AUTHORIZATION`/ownership contract so P1-1 cannot
recur. Note that relocation **alone** does not fix P1-2, because the gate scans all
schemas by default.

### P2-1 — a zero rowcount conflates "another writer moved the version" with "the row does not exist", so `VersionConflict` is raised for an undiagnosed condition while the docstring claims it is "distinguishable"

`backend/tests/harness/concurrency.py:145-146`

```python
if rowcount == 0:
    raise VersionConflict(table, row_id, expected_version)
```

A zero rowcount has (at least) two causes: version mismatch, and `id` not present.
Demonstrated (§4.6, PROBE1): calling `update_versioned` for a `uuid4()` that was never
inserted raises `VersionConflict … expected_version=1` — a false conflict report for a
missing row, with a fabricated "expected version" that was never read from anything.

This contradicts the harness's own claim at `concurrency.py:12-13` ("surfaced as a typed,
**distinguishable** `VersionConflict`"). Control 3 is still met on the dimension the rule
actually names (the conflict is not silently overwritten, swallowed, or auto-retried), so
this is P2 rather than P1 for the harness as it stands. It is flagged firmly because
`concurrency.py:31-37` explicitly advertises this function as the **plug-in template** for
DOM-002's co-owners (MOD-002, MOD-019, MOD-020, MOD-034, MOD-037) and tells them to
"mirror `update_versioned`'s … shape" and reuse `VersionConflict` "as the API boundary
error `.claude/rules/backend/api.md`'s typed-errors control requires." Copied verbatim into
a real aggregate, that maps a not-found to a conflict/409 at the API boundary. It should be
fixed before any domain module adopts the pattern — e.g. `… RETURNING version` (or
`RETURNING id`) and a second, narrow existence check that distinguishes the two outcomes
with two distinct typed errors. No test asserts anything about the missing-row case today.

### P2-2 — the fail-closed differential's own docstrings overstate what test 3 runs: it is not "the identical two-writer shape"

`backend/tests/integration/test_concurrency_harness.py:104-111` ("run the **identical**
two-writer shape through the deliberately-broken comparison fixture") and
`backend/tests/harness/concurrency.py:14-20` ("run the same concurrent-writers shape
against it").

The versioned negative (test 2, L77-80) establishes its shape by having both writers
**read version N first**. Test 3 (L112-119) reads no version at all — it issues two
unconditional blind `UPDATE`s. So the shapes are not identical, and the differential is
established at a weaker point than claimed: test 3 proves only that an `UPDATE` with no
version predicate overwrites, which is true independently of whether a version column
exists.

The genuinely identical shape is available and strictly stronger; I ran it (§4.6, PROBE3):
both writers read version 1, the *versioned* writer A commits to version 2, then the blind
writer B — still holding stale version 1 — succeeds anyway, producing
`final=('writer-b', 2)` with writer A's committed write lost. That is the defect DOM-002
exists to prevent, demonstrated against the real `update_versioned` path rather than
against two blind writes.

To be precise about what is and is not wrong: test 3 **is** load-bearing (M4 in §4.7 kills
it), so the proof is sound; the *description* of it in two docstrings is inaccurate. In an
evidence artifact whose entire purpose is proving a proof method, an inaccurate description
of the method is a real finding.

### P3-1 — the blind path's version staleness is never asserted

Demonstrated (§4.6, PROBE2): after two `update_unversioned_blind` writes the `version`
column is still `1`. Adding `assert read_version(...) == before` to test 3 would prove the
broken path leaves the aggregate's version **stale**, i.e. the lost update is invisible to
any later version check — a cheap, materially stronger piece of DOM-002 evidence than the
value-overwrite assertion alone (`test_concurrency_harness.py:128`).

### P3-2 — the "shown to tell correct from broken" claim was asserted, not demonstrated

`concurrency.py:14-20` states the pattern "can be shown to tell correct from broken …
proving the proof method is sensitive to the defect rather than passing vacuously." Round
18 recorded no mutation/sensitivity evidence for this, although the project's own
established idiom does exactly that (e.g. `TEST_RESULTS.md:7-9`: "reverted the fix in a
throwaway copy and confirmed both regression tests fail", "independently reproduced all
nine mutants"). The claim turns out to be **true** — §4.7 kills 5/5 mutants — so this is a
missing-evidence finding, not a false claim. §4.7 is now that evidence.

### P3-3 — "racing writers" is unqualified in two module records, though the harness itself discloses the ceiling accurately

`concurrency.py:39-45` is accurate and commendably candid: the harness "simulates
concurrency (two sequential, deterministic 'writers' …), not real parallel load." I verified
the ceiling is real (§4.6, PROBE4): both writers are the **same** connection
(`backend_pid=59`, `autocommit=True`), so no transaction ever interleaves and no row lock
is ever contended. Checking the task's question of whether the claim is overstated
elsewhere: `STATUS.md:4` and `SCENARIOS.md:437` say "racing writers" without the simulated
caveat in the same sentence. `SCN-MOD001-009`'s own Steps text does say "simulated, not
real load", which largely mitigates this for `SCENARIOS.md`. Minor wording, flagged for
accuracy only. Separately worth noting: a second connection was trivially available
(`pg.superuser_dsn`), so two genuinely separate sessions would have cost almost nothing and
would allow a real interleaved read-then-write.

### P3-4 — `one_row` and the `Conn` alias are duplicated rather than reused

`concurrency.py:58` and `:88-92` re-declare what `tests/harness/tenant_isolation.py:47` and
`:69` already provide (and which `test_architecture_gate_rls.py` imports from there). This
may well be a deliberate choice to keep the concurrency harness decoupled from the
tenant-isolation harness — if so, say so in a comment, because as written it reads as
drift from the existing harness idiom the round-18 record claims to "mirror".

### P3-5 — control 4's documented decision lives only in a docstring and a front-matter `updated:` line

The reject-and-retry decision is recorded in `concurrency.py:22-29` and named in
`STATUS.md:4`. Control 4 requires it be "recorded in the owning domain module's own
documentation". `STATUS.md`'s `updated:` front matter is chronological — future rounds
demote it to `prior_updated_*` history (the file already carries five such entries), so the
decision has no durable home in `IMPLEMENTATION.md` or `REQUIREMENTS.md`. Technically
satisfied today; fragile.

### P3-6 — two small robustness nits

`concurrency.py:88-92`: `one_row` raises `AssertionError`, which is elided under `python -O`
(inherited from `tenant_isolation.py`, so consistent, but worth knowing). `concurrency.py:
101-106`: `CREATE TABLE IF NOT EXISTS` would silently accept a pre-existing table of the
wrong shape; harmless against a disposable container, but it is the same
"`IF NOT EXISTS` masks a mismatch" idiom that produces P1-1. There is also no check that
`len(params)` matches the placeholder count in `assignments` (`update_versioned`'s
signature, `:130-137`), leaving a caller footgun that surfaces only as a psycopg error.

### Out-of-scope observation (not a finding against these files)

One leaked harness container was present before this review began:
`veyro-mod001-harness-7196bf51`, `Up About an hour`, created **before** the reviewed files
were written (file mtime 05:44; container ~05:09). It is therefore not attributable to the
two files under review or to this review. Recorded factually only; dangling-volume count
was 0, and every container my own runs created was reaped (BUG-051 territory — explicitly
out of this review's charge).

## 7. Explicit disposition of the R04 / "TSD §24.1 gate 2" label discrepancy

**CONFIRMED — the implementer's reading is correct, and I reach it independently.**

1. `REQUIREMENTS.md:590`'s DOM-002 row routes the proof obligation, verbatim, to
   "**GOV-01-R02; CONC category**". There is no R04 tie on that row.
2. `IMPLEMENTATION.md` §4's gate table defines gate 2 as the "**Module dependency/SQL
   lint**" (`CROSS_DOMAIN_SQL_IMPORT` / `REVERSE_EDGE_NOT_EVENT_DRIVEN`). Gate 2 is not
   concurrency, and no gate in the six (or the ADR-005-added seventh) is.
3. Corroboration the round-18 record did not cite: the **immediately preceding**
   `REQUIREMENTS.md:589` row — DOM-001 — is the one that legitimately reads "Proven by the
   module dependency/SQL lint gate | **§24.1 gate 2**". `SCN-MOD001-009`'s tag is almost
   certainly a copy-paste from the adjacent DOM-001 row, which strengthens "mislabel"
   over "a real but undocumented R04 dependency".
4. `REQUIREMENTS.md:128-140` confirms GOV-01-R02's IN scope is precisely "the *test
   architecture* — harness, contracts, fixtures, and CI gates — that later domain modules
   … will plug their real suites into." A synthetic-aggregate concurrency/versioning
   **pattern** sits squarely inside that, which independently supports R02 routing rather
   than merely negating R04.

So: `SCN-MOD001-009`'s header tag "GOV-01-R04, TSD §24.1 gate 2 (DOM-002)" is **inaccurate
in its R04/gate-2 portion**; its `CONC` category is correct and consistent with R02. The
disclosure at `SCENARIOS.md:425-447` states these facts accurately, and disclosing rather
than silently rewriting a catalog entry was the right call. **Recommendation (for a future
Scenario Review round, not for an implementation session):** correct the header to
"GOV-01-R02, CONC (DOM-002)" and remove the R04/gate-2 prerequisite, after which the only
remaining obstacle to promotion is the technical one in §8.

I did **not** re-adjudicate whether round 18 was independent of the BLOCKED ADR-010 A2/R04
model-assurance gate — that is outside this review's scope. My disposition is confined to
the R02-vs-R04/gate-2 routing question.

## 8. Verdict — demonstrated result vs. scenario promotion (kept separate)

**Demonstrated result (what the 3 tests actually prove on `harness.versioned_widget`):
GENUINE.** Re-executed live: 3/3 pass; `ruff check` and `mypy --strict` clean; the
`update_versioned` SQL is genuinely atomic (one statement, version in `WHERE`, increment in
`SET`, correct parameter ordering); `VersionConflict` is typed and is never swallowed or
auto-retried anywhere; the fail-closed differential is load-bearing and not vacuous
(5/5 mutants killed, including one that repairs the broken fixture); the three tests are
mutually order-independent (each takes a fresh `uuid4()` row, the `widget` teardown is
post-`yield` so it runs on assertion failure, and every query is id-scoped). Caveats: the
"distinguishable" claim is not met for the missing-row case (P2-1), and the "identical
two-writer shape" description of test 3 is inaccurate (P2-2).

**Scenario promotion: `SCN-MOD001-009` must NOT be promoted — and I would withhold
promotion even if the label question in §7 were resolved today.** Round 18's own decision
not to promote is correct, but my reason is additional and technical: P1-1 and P1-2 mean
this pattern cannot currently coexist order-independently with the rest of the GOV-01-R02
suite it is supposed to join. A scenario whose passing evidence depends on pytest's
alphabetical file ordering, and which can silently turn the ADR-010 RLS gate red, is not
promotable regardless of how its header is tagged.

**OVERALL: BLOCKED — P0=0, P1=2, P2=2, P3=6.**

Nothing in this verdict is a finding about the correctness of the DOM-002 *semantics*,
which are sound. Both P1s are shared-fixture-hygiene defects with cheap, local fixes.

## 9. Next action

1. **Implementation session (Sonnet is appropriate; this is harness hygiene, not an
   ADR-005 Decision 1 slice):** fix P1-1 and P1-2 together — give `create_versioned_table`
   an explicit schema-ownership contract so it can never silently take ownership of a
   schema the tenant-isolation harness owns, and give `_widget_table` a real teardown that
   removes the table (and the schema, if it created it) so no RLS-gate invocation can ever
   see it. Then re-run the two drills in §4.4 and §4.5 as regression proof, plus the full
   suite in **both** orders. Address P2-1 and P2-2 in the same pass: distinguish missing-row
   from version-conflict with two typed errors before any domain module copies the
   template, and either make test 3 use the real identical two-writer shape (§4.6 PROBE3
   shows it works) or correct both docstrings to describe what it actually does.
2. **Do not promote `SCN-MOD001-009`** on this round's evidence.
3. **Future Scenario Review round:** correct the `SCN-MOD001-009` header tag per §7.
4. **Re-review:** this report's P1s are reproducible by the exact commands in §4.4/§4.5;
   a round-2 reviewer should re-run those first, and should re-run the §4.7 mutation drill
   against any changed `update_versioned`.
5. Orchestrating session: run `mr_verify.py` against this review's transcript (§1) and
   clear the `REVIEW_IN_FLIGHT.md` claim (watchdog `66643874-e295-4d53-a846-ee79cb6c3a44`).
