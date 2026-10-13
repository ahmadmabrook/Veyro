---
doc: DOM002_ROUND4_REMEDIATION
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
responds_to: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND4-2026-10-04.md
remediation_session: same retained MOD-001 GOV-01-R02 implementation session (Sonnet), not an independent review
date: 2026-10-04
---

# DOM-002 concurrency pattern — round-4 code-review remediation

## 0. What this is

Bounded remediation of round-4's verdict **PASS (P0=0, P1=0, P2=0, P3=6)**
— `mr_verify.py` PASS 107/107 `claude-opus-5`, independently attested by
the orchestrator against the reviewer's real transcript before this
session was dispatched. `REVIEW_IN_FLIGHT.md`'s round-4 claim was already
`CLEAR` at this session's start; left untouched throughout.

Round 4 confirmed all six of round 3's findings genuinely fixed by its own
execution and found no P0/P1/P2 of its own — the pattern that defeated
rounds 2 and 3 (a fix introducing new defects on the same code path) did
not repeat at blocking severity. It did find six new P3s, three of them in
the round-3 fix itself (R4-1, R4-3, R4-5 — all latent, not live) and three
adjacent (R4-2 a latent multi-container precondition, R4-4 a forward-
binding documentation/atomicity gap in the plug-in template, R4-6 two
stale durable records). Per the task's own priority, **R4-4 is addressed
first** below.

**Model-routing determination (recorded, not silently assumed):** none of
R4-1 through R4-6 required Opus-reserved architectural judgment. `ADR-005`
Decision 1 bounds the Opus-tier `veyro-critical-engineer` role to exactly
three slices (the tenant-isolation/RLS harness, the authn negative-
credential fixture pattern, and the RLS/permission architecture-lint
gates) — DOM-002's concurrency pattern was already established as outside
that set in round 18's own original routing determination, and nothing in
round 4's findings changes that: each finding came with a concrete,
bounded recommended fix from the review itself (fold two statements into
one, consume an env var, separate a Go-template list, export a shared
constant, guard a warning, reconcile stale text), none of which is a
system-design or security-architecture decision. No Opus subagent was
dispatched; all six fixes were implemented directly in this session.

## 1. R4-4 (highest priority) — non-atomic 404-vs-409 disambiguation in the copyable plug-in pattern

**Defect.** `update_versioned`'s version-checked `UPDATE` and its
existence-disambiguation check were two separate statements on an
autocommit connection (`backend/tests/integration/conftest.py:41`), each
taking its own snapshot. A writer that inserted the probed row in the gap
between them made the already-returned "zero rows updated" and the
now-true "row exists" disagree, raising `VersionConflict` (409-shaped) for
a row that did not exist when the `UPDATE` actually ran — 404 was the
truthful answer. `concurrency.py`'s own "Plug-in point" section instructs
MOD-002/019/020/034/037 by name to mirror this exact shape for their real
aggregates under real concurrency, so the gap was forward-binding, not
merely a MOD-001 self-test defect.

**Independently reproduced before fixing:** two real connections to the
same disposable Postgres instance. Connection A ran the version-checked
`UPDATE` against a row that did not yet exist (0 rows affected);
connection B then inserted that exact row; connection A's separate
existence check then saw it and the (pre-fix) logic would raise
`VersionConflict` — confirmed live:

```
UPDATE rowcount (row doesn't exist yet): 0
conn_b inserted the row AFTER the UPDATE ran
existence probe (separate statement) now sees: True
=> current update_versioned would raise VersionConflict here, which is WRONG
```

**Fix — made the disambiguation atomic, not merely disclosed the gap**
(the review's own "either/or", choosing the stronger option because this
is the piece five later modules are told to copy). `update_versioned` now
issues one `WITH` statement:

```sql
WITH existing AS (SELECT 1 FROM {t} WHERE id = %s),
     attempt  AS (UPDATE {t} SET version = version + 1, {assignments}
                  WHERE id = %s AND version = %s RETURNING 1)
SELECT (SELECT count(*) FROM existing)::int, (SELECT count(*) FROM attempt)::int
```

PostgreSQL gives every part of a single statement that is not chained via
`RETURNING` the same snapshot, taken once at that statement's start — the
`existing` and `attempt` CTEs cannot disagree about what existed, because
there is no second statement left to take a different, later snapshot.
`_row_exists` (the now-dead second-statement helper) was removed. Control
2's "one atomic statement" requirement is strengthened, not weakened —
still exactly one round trip.

**Verification:**

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
5 passed in 1.60s   # 4 prior + 1 new
```

Re-ran the original two-connection race against the fixed code: the first
call now correctly raises `RowNotFound` (the row genuinely did not exist
when the one statement ran); a second, independent call after a real
insert succeeds normally.

**New regression test** (concrete, structural — not a timing-dependent
mirror of the race, since the fix makes the race window impossible to
reopen from outside a single statement by construction):
`test_update_versioned_executes_exactly_one_statement` counts real
`execute()` calls on the connection during the disambiguation
(zero-rowcount) path and asserts exactly one. **Proven non-vacuous**: in a
throwaway copy, reverted `update_versioned` to the pre-fix two-statement
shape and re-ran this exact test — it failed, reporting "2 round trip(s)
… expected exactly 1". Real repo files confirmed untouched by that drill
(`git status --porcelain`, unchanged `??` before/after).

## 2. R4-1 — `warnings.warn` itself not unconditionally non-raising

**Defect.** `_cleanup_container`'s docstring promised "never raises", but
`warnings.warn` is not an inherently non-raising primitive — under
`filterwarnings = ["error"]` (or `pytest -W error`) it raises, which would
replace the real `TimeoutExpired` the `finally` is meant to preserve.
`pyproject.toml` has no such entry today, so this was latent, not live.

**Fix.** New `_warn(message)` helper wraps each call in
`warnings.catch_warnings()` + `simplefilter("always")`, overriding any
outer filter for that one call only. All three `_cleanup_container` call
sites now go through `_warn` instead of `warnings.warn` directly.

**Verification (OBSERVED, in-process, no real Docker risk):** monkeypatched
a route whose `rm` fails, called `_cleanup_container` under
`warnings.simplefilter("error")` (the exact condition `filterwarnings =
["error"]` creates) — the warning printed and the function returned its
degraded result normally; no exception escaped. Also re-ran the existing
`test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1`
under `python -W error` directly: `1 passed`.

## 3. R4-3 — `_anonymous_volume_of`'s Go template concatenates multiple mounts with no separator

**Defect.** `'{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}'`
emits every matching volume name back-to-back with nothing between them.
With exactly one volume (the pinned image's own single declared `VOLUME`)
the result happens to be a valid id; with two or more it is an unsplittable
garbage string matching no real volume, and both downstream checks
(`is not None`, `not in docker volume ls`) would then pass vacuously —
re-vacuating the R3-2 lock the moment the image or fixture ever declared a
second mount.

**Fix.** Renamed to `_anonymous_volumes_of`, added a `\n` separator to the
template, returns `list[str]` via `splitlines()` instead of a single
optional string. `_cleanup_container` and `_run_pytest`'s
`cleanup_outcome["volumes"]` (now plural) carry the full list; the
regression test asserts every reported volume, not just one, is gone.

**Verification (OBSERVED, live, real two-named-volume + one-anonymous-volume
container):** the fixed function returned `['r4vol-a', 'r4vol-b',
'<real-anonymous-id>']` — three distinct, individually valid IDs — where
the pre-fix template would have concatenated them into one unsplittable
string. Probe container and both named volumes removed by hand afterward;
state confirmed back to baseline.

## 4. R4-2 — `CONTAINER_TOKEN_ENV_VAR` breaks under an overlapping multi-container process tree

**Defect.** An env var is inherited by the whole process tree; two
`disposable_postgres()` calls with overlapping lifetimes in the same
process (demonstrated with the session-scoped `pg` and
`test_migration_safety_harness.py`'s own module-scoped `pg`) would both
try to use the same fixed token, and the second `docker run` collides with
the first, still-running container.

**Independently reproduced before fixing:**

```
$ VEYRO_HARNESS_CONTAINER_TOKEN=r4reprocoll .venv/bin/python -m pytest \
      tests/integration/test_concurrency_harness.py \
      tests/integration/test_migration_safety_harness.py -q
5 passed, 36 errors in 2.26s
RuntimeError: `docker run` exit 125: ... Conflict. The container name
"/veyro-mod001-harness-r4reprocoll" is already in use ...
```

No leak resulted (confirmed via `docker ps`/`docker volume ls`) — the
collision fails before that invocation's own `try`/`finally`, matching the
review's own "mitigating facts."

**Fix.** `disposable_postgres()` now does
`token = os.environ.pop(CONTAINER_TOKEN_ENV_VAR, "") or secrets.token_hex(4)`
instead of `os.environ.get(...)` — only the *first* container created in a
process honours a caller-supplied token; every subsequent one in the same
process always falls back to a fresh random token, removing the collision
class entirely rather than only documenting it (the review's own
"stronger, and cheap" recommendation).

**Verification:**

```
$ VEYRO_HARNESS_CONTAINER_TOKEN=r4fixedcoll .venv/bin/python -m pytest \
      tests/integration/test_concurrency_harness.py \
      tests/integration/test_migration_safety_harness.py -q
41 passed in 5.02s
```

Docker state unchanged before/after.

## 5. R4-5 — hand-duplicated container-name prefix; narrow vacuity message

**Defect.** `test_concurrency_harness_order_independence.py` kept its own
copy of `"veyro-mod001-harness-"`, with a comment asserting it "must match"
`postgres.py`'s scheme but nothing enforcing that. The `container_was_
created is False` assertion message named only the timeout-too-short
cause, when drift or an early child failure are equally possible causes —
and in the drift case, cleanup aims at a name that was never created,
leaking the real one.

**Fix.** `postgres.py` now exports `CONTAINER_NAME_PREFIX` and a
`container_name(token) -> str` helper; the order-independence file imports
both instead of keeping its own copy, and builds the container name via
`container_name(token)`. The vacuity-assertion message now names all three
causes (timeout value, early child failure, naming-scheme drift) and
states the current prefix value for diagnostic visibility.

**Verification:** full suite re-run, 204/204 both orders (see §7) —
confirms the single-sourced name still matches what `disposable_postgres`
actually creates (the order-independence drills, which depend on this
matching exactly, all still pass).

## 6. R4-6 — two durable records still claimed CAP-008 is QUALIFIED/not-APPROVED

**Defect.** `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`
and `CAPABILITIES.md` both still stated CAP-008's `review_status` as
`QUALIFIED (not APPROVED)` and "not usable for real project work" —
accurate when round 16 wrote it, stale since round 17 (same day) restored
`APPROVED` in `CAPABILITY_REGISTRY.md`, where it has stayed through
rounds 2/3/4 of this very remediation lineage.

**Fix.** Added a dated reconciliation paragraph to both files' relevant
sections (append, not rewrite — the original QUALIFIED-era text is kept
as the historical record of round 16's own state, per this project's
convention), plus a front-matter `updated:` entry on `CAPABILITIES.md`
(renamed the round-16 entry to `prior_updated_round16seg3`, no key
collision).

**Verification:**

```
$ backend/.venv/bin/python knowledge/00-System/validate_capabilities.py
RESULT: PASS — 8 capability/capabilities, all registered and APPROVED with required fields present.

$ backend/.venv/bin/python tools/validate_capability_manifest.py \
      --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml
RESULT: PASS — 10 capability/Rule ID(s) discovered, all registered and APPROVED with required fields present; ...
```

## 7. Full regression evidence

```
$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python -m mypy tests/
Success: no issues found in 28 source files

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py \
      tests/integration/test_concurrency_harness_order_independence.py -v
8 passed in 7.71s

$ .venv/bin/python -m pytest tests -q                                       # default order
204 passed in 30.15s

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q   # reversed order
204 passed in 29.44s

$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.

$ backend/.venv/bin/python knowledge/00-System/validate_capabilities.py
RESULT: PASS — 8 capability/capabilities, all registered and APPROVED with required fields present.

$ backend/.venv/bin/python tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml
RESULT: PASS — 10 capability/Rule ID(s) discovered, all registered and APPROVED with required fields present.
```

204 = 203 (round-3-remediation baseline) + 1 new test
(`test_update_versioned_executes_exactly_one_statement`). Zero regressions
in either collection order. Docker state (`veyro-mod001-harness-7196bf51`
pre-existing + 2 volumes) confirmed unchanged across every drill and every
full-suite run this round.

## 8. Scope discipline confirmed

No edit to `R04`, `ADR-010`, `SCN-067`, `BUG-048`. `SCN-MOD001-009` is
**not promoted and not claimed PASS** by this remediation. WIP=1
respected — no other module touched. `REVIEW_IN_FLIGHT.md` left untouched
(already `CLEAR`). Files changed this round: `backend/tests/harness/
concurrency.py` (R4-4 atomicity fix, `_row_exists` removed), `backend/
tests/integration/test_concurrency_harness.py` (R4-4 regression test),
`backend/tests/harness/postgres.py` (R4-2 `pop`, R4-5 exported naming
helper), `backend/tests/integration/test_concurrency_harness_order_
independence.py` (R4-1/R4-3/R4-5 fixes), `knowledge/03-Modules/MOD-001/
evidence/module-capabilities.yaml` and `CAPABILITIES.md` (R4-6
reconciliation), plus this file and the standard `STATUS.md`/
`TEST_RESULTS.md`/`CURRENT_STATE.md`/`CURRENT_HANDOFF.md` checkpoint
updates. No commit/push — all new/changed files remain either untracked
or part of this session's existing uncommitted set; nothing reset,
stashed, or discarded.

## 9. Next independent-review action

A round-5 review, if dispatched, should re-run this report's §1-§6
commands directly: the two-connection TOCTOU reproduction against the
fixed `update_versioned` (expect `RowNotFound`, not `VersionConflict`),
the `test_update_versioned_executes_exactly_one_statement` non-vacuity
check (revert to two statements, confirm it fails), the `-W error` drill
against `_cleanup_container`, a real multi-volume container against
`_anonymous_volumes_of`, the multi-container-process-tree collision drill
(expect no collision now), and the two capability-manifest validators
against the reconciled durable records. It should also re-run round 4's
own §4 eleven-mutant set and round 3's §4.9/§4.15 drills it deliberately
skipped, against whatever changed.
