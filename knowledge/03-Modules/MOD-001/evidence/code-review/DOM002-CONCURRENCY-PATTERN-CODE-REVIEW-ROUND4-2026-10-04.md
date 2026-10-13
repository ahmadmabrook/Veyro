---
doc: DOM002_CONCURRENCY_PATTERN_CODE_REVIEW_ROUND4
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
reviews: knowledge/03-Modules/MOD-001/evidence/implementation/DOM002-ROUND3-REMEDIATION-2026-10-04.md
prior_round: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND3-2026-10-04.md
role: veyro-code-reviewer (independent, fresh context, no memory of rounds 1-3 or of the remediation session)
verdict: PASS with findings — P0=0, P1=0, P2=0, P3=6
date: 2026-10-04
---

# Independent code review round 4 — GOV-01-R02 DOM-002 concurrency/versioning test pattern (round-3 remediation re-review)

## 0. Bounded scope, and what this review does NOT cover

In scope, read as actual source this session (never from the remediation record's prose):

| File | Scope |
|---|---|
| `backend/tests/harness/concurrency.py` | whole file (`VersionedTable`, `VersionConflict`, `RowNotFound`, `create_versioned_table`, `drop_versioned_table`, `insert`, `read_version`, `_row_exists`, `update_versioned`, `update_unversioned_blind`) |
| `backend/tests/integration/test_concurrency_harness.py` | whole file (4 tests + `widget` fixture) |
| `backend/tests/integration/test_concurrency_harness_order_independence.py` | whole file (3 tests + `_container_exists`, `_anonymous_volume_of`, `_cleanup_container`, `_run_pytest`) |
| `backend/tests/harness/postgres.py` | **only** `disposable_postgres()` and the new `CONTAINER_TOKEN_ENV_VAR` support (`:167-221`). The rest of the file is the pre-existing shared CAP-008 capability and is not re-reviewed here. |

Explicitly **not** done, by instruction:

* `SCN-MOD001-009` **not promoted** and **not claimed PASS**. Independently confirmed still
  `NOT EXECUTED` at `knowledge/03-Modules/MOD-001/SCENARIOS.md:418` and still carrying its own
  "**This scenario (SCN-MOD001-009) is NOT promoted and NOT** …" disclosure at `:442`.
* **No Module Approval Certificate.** That is the Gatekeeper role, not this one.
* **No edit to `ADR-010` or `R04`**, nor to `SCN-067`/`BUG-048`.
* **No production code changed.** `git status --porcelain -- backend/` at the end of this review
  is byte-identical to its state at the start (same 3 modified + same untracked set). Every
  mutation in this review was applied to a throwaway copy under `/tmp/r4/`, never in `backend/`.
* **No Docker resource predating this review was touched, and nothing was pruned.** See §5.

This review's job was narrow: verify, by my own execution, whether round 3's six findings are
genuinely fixed, whether the fix introduced anything new (round 3's own experience was that
round 2's fix introduced four new defects on the same code path), and whether the slice drifts
from the governing baselines or the owner-reserved restrictions.

## 1. Methodology

Every claim below is labelled either **OBSERVED** (I executed it this session and the captured
output is reproduced) or **READ** (I determined it by reading the source/durable record, with no
execution). Nothing in the remediation record was accepted as true on its own.

Throwaway-copy mechanics, so the real tree was never mutated:

* For `test_concurrency_harness_order_independence.py`: `/tmp/r4/make_mutant.py` copies the real
  file to `/tmp/r4/mutants/test_<tag>.py`, applies one single-anchor mutation (asserting the
  anchor occurs exactly once), and — as a **drill-harness adjustment, not part of any mutation,
  disclosed here** — repoints `BACKEND_ROOT` from its `Path(__file__).resolve().parents[2]`
  derivation to the literal backend root, since the copy lives outside the repo.
* For `concurrency.py`: `/tmp/r4/make_conc_mutant.py` writes a mutated copy plus a pytest plugin
  that pre-seeds `sys.modules["tests.harness.concurrency"]` with it. This runs the **real,
  unmodified** repo test files against a **mutated** harness module — no repo file is edited and
  no test file is copied. For the two order-independence drills, the plugin is propagated into
  the nested child pytest via `PYTEST_ADDOPTS`, so parent and child both see the mutant.

Tooling used (project's own venv, confirmed present): `backend/.venv/bin/python` (3.14.5,
pytest 9.1.1), `.venv/bin/python -m ruff`, `.venv/bin/python -m mypy`.

## 2. Static checks and the real suites — all OBSERVED

```
$ backend/.venv/bin/python -m ruff check .
All checks passed!

$ backend/.venv/bin/python -m mypy tests/
Success: no issues found in 28 source files

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py \
      tests/integration/test_concurrency_harness_order_independence.py -v
tests/integration/test_concurrency_harness.py::test_single_writer_succeeds_and_increments_version PASSED
tests/integration/test_concurrency_harness.py::test_concurrent_writers_lost_update_detected PASSED
tests/integration/test_concurrency_harness.py::test_update_versioned_distinguishes_missing_row_from_version_conflict PASSED
tests/integration/test_concurrency_harness.py::test_naive_unversioned_update_loses_the_update PASSED
tests/integration/test_concurrency_harness_order_independence.py::test_concurrency_before_canonical_rls_harness_test_review_4_4 PASSED
tests/integration/test_concurrency_harness_order_independence.py::test_concurrency_between_two_rls_gate_invocations_review_4_5 PASSED
tests/integration/test_concurrency_harness_order_independence.py::test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1 PASSED
============================== 7 passed in 7.80s ===============================

$ .venv/bin/python -m pytest tests -q                                      # default order
203 passed in 33.35s

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q  # reversed order
203 passed in 30.13s

$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match …/PROJECT_INDEX.md exactly.

$ backend/.venv/bin/python knowledge/00-System/validate_capabilities.py
RESULT: PASS — 8 capability/capabilities, all registered and APPROVED with required fields present.
```

203/203 in both collection orders matches the remediation's own §7 claim exactly, independently
re-derived. Docker container/volume state was re-checked immediately after every one of these
runs and was identical to the baseline each time.

## 3. Round-3 findings — per-finding verification

### R3-1 (P2) — over-reap of an unrelated concurrent container → **CONFIRMED FIXED**

**What the code now does (READ).** `test_concurrency_harness_order_independence.py:193-195`
picks a per-invocation token (`secrets.token_hex(4)`, or the caller's) and passes it to the child
through `postgres.py`'s new `CONTAINER_TOKEN_ENV_VAR`; `postgres.py:181-182` makes that token the
container's suffix, so the parent knows the exact name before the child starts. Cleanup
(`:209` → `_cleanup_container` at `:131-168`) targets that **one exact name** and nothing else.
The membership test at `:111-117` is an exact-string `in` against `docker ps -a --format
{{.Names}}` lines — no `--filter name=`, no `startswith`, no before/after diff anywhere in the
file. The time-window diff and the loose filter that caused R3-1 are both gone by construction.

**Drill 1 — mid-window decoy, timeout path (OBSERVED, `/tmp/r4/r4_d1_overreap_timeout.py`).**
A decoy matching the harness prefix exactly was created from a concurrent thread timed to land
0.5 s into the `subprocess.run` window, i.e. the same shape round 3 used to destroy a decoy:

```
decoy present BEFORE: ''
baseline containers BEFORE: ['veyro-mod001-harness-7196bf51']
[decoy] created veyro-mod001-harness-r4decoy1 at +0.5s (create took 0.08s) — unrelated actor,
        NOT created by _run_pytest's child
[drill] TimeoutExpired fired as expected
decoy present AFTER: 'veyro-mod001-harness-r4decoy1\tCreated'
RESULT: DECOY SURVIVED (no over-reap)
containers AFTER: ['veyro-mod001-harness-r4decoy1', 'veyro-mod001-harness-7196bf51']
```

The child's own container is absent from `containers AFTER` — so the real leak R2-1 was about is
still being closed, while the unrelated container is left alone.

**Drill 2 — the ordinary success path, plus the unanchored-substring half (OBSERVED,
`/tmp/r4/r4_d2_overreap_success.py`).** Round 3 found the over-reap fired on *every* invocation,
not only on timeout, so I repeated it with the default 180 s timeout (child exits 0), and added a
second decoy named `unrelated-veyro-mod001-harness-r4xyz` — the exact shape that defeated round
2's `--filter name=` prefix assumption:

```
[decoy] created unrelated-veyro-mod001-harness-r4xyz
substring filter sees: ['unrelated-veyro-mod001-harness-r4xyz', 'veyro-mod001-harness-r4decoy1',
                        'veyro-mod001-harness-7196bf51']
[decoy] re-created veyro-mod001-harness-r4decoy1 at +0.5s mid-window
child returncode: 0 (0 == normal success, no timeout)
prefixed decoy AFTER: True
substring decoy AFTER: True
RESULT: BOTH DECOYS SURVIVED ON SUCCESS PATH
```

Note the first line of output: Docker's `name=` filter is *still* an unanchored substring match
(it still matches `unrelated-…`). The fix did not make the filter safer — it stopped using a
filter at all, which is the stronger resolution. Both decoys and their anonymous volumes were
then removed by me by exact name (`docker rm -f -v`), and volumes diffed back to baseline
exactly.

**Verdict: confirmed-fixed, both paths, including the substring half.**

### R3-2 (P2) — volume half of BUG-051 not regression-locked; "M8" survived → **CONFIRMED FIXED**

**What the code now does (READ).** `_anonymous_volume_of` (`:120-128`) reads the exact
container's volume mount via `docker inspect` *before* removal; `_cleanup_container` returns it
(`:168`); `_run_pytest`'s `finally` reports it through `cleanup_outcome["volume"]` (`:213`); the
regression test asserts that specific ID is absent from `docker volume ls -q` afterwards
(`:266`).

**Drill (OBSERVED).** Control copy first, then the identical M8 mutation
(`docker("rm", "-f", "-v", name)` → `docker("rm", "-f", name)`), both in `/tmp/r4/mutants/`:

```
### CONTROL (unmutated copy) ###      vols before: 2 → 1 passed in 1.59s → vols after: 2
### M8 MUTANT (rm without -v) ###     vols before: 2
>           assert volume not in docker("volume", "ls", "-q").splitlines()  # R3-2
E           AssertionError: assert '32168c6712a54930d985d6cf9b59d65aba0bb2d606eb64b843c5ac85bbddb7f7'
E             not in ['712bec68008ece…', '32168c6712a54930…', 'tradingview-mcp-session']
1 failed in 1.57s                     vols after: 3
```

**M8 is now KILLED**, and pytest's assertion rewriting does name the leaked volume ID, which is
what the remediation claimed. The leak is real (2 → 3), so the test is not passing/failing on a
stale value. I confirmed the leaked volume was mine and not the pre-existing one before removing
it by exact ID (`created=2026-10-04T09:24:24+03:00` vs the pre-existing `712bec68…`'s
`05:00:35`), then diffed volumes back to baseline.

**Verdict: confirmed-fixed.** See **R4-3** for a latent vacuity I found inside this new fix.

### R3-3 (P3) — vacuous timeout test → **CONFIRMED FIXED**

**What the code now does (READ).** `_run_pytest` gained the `cleanup_outcome` output-parameter
(`:175`, written at `:210-213` inside the `finally`, which is the only place reachable on the
`TimeoutExpired` path). The test asserts `container_was_created is True` **first** (`:256-260`),
then volume presence, then removal, then live absence.

**Drill (OBSERVED).** `_FORCED_TIMEOUT_S = 1.2` → `0.05` in a throwaway copy:

```
E       AssertionError: no container was ever created before the forced timeout fired —
        _FORCED_TIMEOUT_S=0.05 may be too short for this environment; every assertion below
        would otherwise pass vacuously
E       assert False is True
E        +  where False = …{'container_was_created': False, 'container_removed': False, 'volume': None}.get
1 failed in 0.28s
```

Loud, specific, and no container or volume was left behind. **Verdict: confirmed-fixed.**

**Timing margin independently re-measured on this host (OBSERVED,
`/tmp/r4/r4_d7_timing.py`)** — the source comment at `:99-108` cites round 3's
`~0.36s` / `~1.72-1.86s` window:

```
child container first observed at ~0.46s (polling via docker ps, so this is an upper bound)
child full normal completion: 2.04s (returncode 0)
_FORCED_TIMEOUT_S = 1.2 -> inside the window? True
```

`1.2` still sits inside the valid window here (~0.74 s of headroom below, ~0.84 s above). The
comment's claim that the exact value is no longer load-bearing for *correctness* is accurate —
the `container_was_created` assertion is what now catches a bad value.

### R3-4 (P3) — unguarded probe masking the real exception; silently swallowed `rm` failure → **CONFIRMED FIXED** (with the new caveat in R4-1)

**What the code now does (READ).** `_cleanup_container` (`:131-168`) wraps each of the three
steps — existence probe (`:139-147`), volume inspect (`:151-158`), `rm` (`:159-167`) —
independently; each failure path emits `warnings.warn` and returns a degraded result rather than
raising. `DockerRoute.__call__` (`postgres.py:83-94`) converts every `OSError`/
`subprocess.SubprocessError`/non-zero exit into `RuntimeError`, so `except RuntimeError` is the
right and sufficient catch for this route.

**Drill — through the real `_run_pytest` path, on a real forced timeout (OBSERVED,
`/tmp/r4/r4_d3_r34_guards.py`).** The module's `trusted_docker` was monkeypatched to a wrapper
route that delegates everything except one failing subcommand:

```
--- drill: docker 'ps' fails during cleanup ---
exception surfaced to caller: TimeoutExpired
   WARN: R2-1/R3-4 safety net: could not confirm whether veyro-mod001-harness-r4ps0001 exists;
         cleanup skipped for this invocation: `docker ps` exit 1: simulated engine hiccup …
RESULT: REAL TimeoutExpired PRESERVED (not masked)
container leaked by the degraded cleanup: True
   reviewer cleanup: removed veyro-mod001-harness-r4ps0001 (+ volume 9ccd0101c998cd50…)

--- drill: docker 'rm' fails during cleanup ---
exception surfaced to caller: TimeoutExpired
   WARN: R2-1/R3-4 safety net: failed to remove leaked container veyro-mod001-harness-r4rm0001
         (its volume '47ae11ed0b3b8311…' may also be leaked): `docker rm` exit 1: simulated …
RESULT: REAL TimeoutExpired PRESERVED (not masked)
   reviewer cleanup: removed veyro-mod001-harness-r4rm0001 (+ volume 47ae11ed0b3b8311…)
```

Both halves fixed: the probe failure no longer replaces the real exception, and the `rm` failure
now produces a signal that even names the possibly-leaked volume. Both drill containers and
volumes were removed by me by exact name; state returned to baseline. **Verdict:
confirmed-fixed**, with the config-conditional regression recorded as **R4-1**.

### R3-5 (P3) — R2-4's deferral not discoverable from the code → **CONFIRMED FIXED**

`concurrency.py:77-88` now states it plainly inside the "Plug-in point" section — the place
round 3 said it had to be: "`VersionConflict` and `RowNotFound` deliberately share no common
base class (both are direct `Exception` subclasses) — this is a recorded, upheld deferral
(round-2 review R2-4), not an oversight". READ, and consistent with the live class definitions at
`:135` and `:151` (both `Exception`). **Verdict: confirmed-fixed.**

### R3-6 (P3) — malformed sentence / unclosed parenthesis in a docstring → **CONFIRMED FIXED**

The order-independence module docstring was rewritten (`:1-72`) and does not reproduce the
malformed sentence. Checked mechanically rather than by eye, over all four in-scope files
(OBSERVED, AST walk of every module/class/function docstring):

```
tests/harness/concurrency.py: OK (all docstring parens/backticks balanced)
tests/integration/test_concurrency_harness.py: OK (all docstring parens/backticks balanced)
tests/integration/test_concurrency_harness_order_independence.py: OK (…balanced)
tests/harness/postgres.py: OK (…balanced)
```

**Verdict: confirmed-fixed (moot, as claimed).**

### Backward-compatibility of the `postgres.py` change — **CONFIRMED**

The remediation claimed every non-setting caller is byte-identical to the prior behaviour.
Verified three ways:

1. **READ** — `git diff` of `postgres.py` shows the token change is exactly two lines
   (`:181-182`): `token = os.environ.get(CONTAINER_TOKEN_ENV_VAR) or secrets.token_hex(4)` then
   `name = f"veyro-mod001-harness-{token}"`, replacing `name = f"veyro-mod001-harness-{secrets.token_hex(4)}"`.
   With the var unset the expression is the prior call, unchanged. (The rest of the file's large
   diff vs HEAD is the pre-existing uncommitted CAP-008 `DockerRoute`/Colima work, out of scope.)
2. **OBSERVED** — an *empty-string* value correctly falls through the `or` to a random token:
   `empty string …: container created -> veyro-mod001-harness-00ff1d41`.
3. **OBSERVED** — 203/203 in both collection orders, which exercises the tenant-isolation, authn,
   migration-safety and scaffold harnesses that all call `disposable_postgres()` without the var.

See **R4-2** for the one case where the var is *not* a safe no-op, and **R4-5** for the
name-scheme duplication it introduces.

## 4. Mutation controls — 11 mutants, 11 killed (all OBSERVED)

Baseline in every case: `tests/integration/test_concurrency_harness.py` = `4 passed in 1.59s`.

| # | Mutant | Target | Result |
|---|---|---|---|
| M1 | version predicate neutered: `WHERE id = %s AND version = %s` → `… AND %s IS NOT NULL` | `concurrency.py:252` | **KILLED** — `Failed: DID NOT RAISE VersionConflict`; `1 failed, 3 passed` |
| M2 | `if rowcount == 0:` → `if False:` (silent zero rowcount) | `concurrency.py:256` | **KILLED** — `DID NOT RAISE VersionConflict` **and** `DID NOT RAISE RowNotFound`; `2 failed, 2 passed` |
| M5 | version checked but never incremented: `SET version = version + 1, {}` → `SET {}` | `concurrency.py:252` | **KILLED** — `assert 1 == (1 + 1)` + `DID NOT RAISE VersionConflict`; `3 failed, 1 passed` |
| M6 | existence check removed, so every zero rowcount is a `VersionConflict` | `concurrency.py:257-258` | **KILLED** — `test_update_versioned_distinguishes_missing_row_from_version_conflict` fails; `1 failed, 3 passed` |
| M4a | broken comparison fixture "repaired" to refuse the write (`return 0`) | `concurrency.py:271` | **KILLED** — `assert 0 == 1`; `1 failed, 3 passed` |
| M7 | broken fixture keeps no version predicate but *does* bump the version | `concurrency.py:270` | **KILLED** — `assert 3 == (1 + 1)`; `1 failed, 3 passed` |
| P1-1 | `SCHEMA = "concurrency_harness"` → `"harness"` (share the tenant-isolation schema again) | `concurrency.py:119` | **KILLED** — child dies `psycopg.errors.InsufficientPrivilege: permission denied for schema harness`; `…review_4_4` FAILED |
| P1-2 | `drop_versioned_table` body neutralised (teardown only, schema fix retained) | `concurrency.py:205` | **KILLED** — `RLS_TABLE_UNCLASSIFIED: concurrency_harness.versioned_widget …`, `ADR010-P1-EVIDENCE … "status": "FAIL"`; `2 failed, 1 passed in 6.43s` |
| M8 | `rm -f -v` → `rm -f` (the BUG-051 volume mechanism) | order-indep. `:160` | **KILLED** — see §3/R3-2; was SURVIVING in round 3 |
| short | `_FORCED_TIMEOUT_S = 1.2` → `0.05` | order-indep. `:108` | **KILLED** — see §3/R3-3; would have been a vacuous pass in round 3 |
| prefix | `_HARNESS_CONTAINER_PREFIX` drifted from `postgres.py`'s naming scheme | order-indep. `:97` | **KILLED** — the `container_was_created` assertion fires (see **R4-5** for the misleading message, and note this run leaked a real container, removed by me) |

M1/M2/M5/M6/M4a/M7 reproduce round 3's §4.13 set at 6/6, and P1-1/P1-2 reproduce rounds 1-3's
schema-ownership and teardown locks. **Not re-run this round, disclosed:** round 3's §4.9 R2-2
same-session setup-failure drill (the `widget` fixture's `try`/`finally` at
`test_concurrency_harness.py:75-80` was READ and is correct, but I did not re-execute the
injected-failure drill), round 3's §4.15 live `pg_namespace`-owner catalog probe (superseded for
my purposes by the P1-1 mutant above, which is the mechanical lock), and round 3's §4.16
repo-wide duplicate-writer greps.

## 5. Docker state — before, throughout, after (all OBSERVED)

Baseline captured before any drill, matching what the dispatch brief recorded as pre-existing and
out of scope:

```
$ docker ps -a --filter name=veyro-mod001-harness- --format '{{.Names}}|{{.Status}}'
veyro-mod001-harness-7196bf51|Up 4 hours

$ docker volume ls -q | sort
712bec68008ece99c2974826cc2f384d370b4c6bfa6054854ee98cf2ec361acf    (7196bf51's anonymous volume)
tradingview-mcp-session                                              (unrelated, named)
```

Final state:

```
$ docker ps -a --filter name=veyro-mod001-harness- --format '{{.Names}}|{{.Status}}|{{.CreatedAt}}'
veyro-mod001-harness-7196bf51|Up 5 hours|2026-10-04 05:00:35 +0300 +03

$ docker volume ls -q | sort | diff /tmp/r4/baseline_volumes.txt -
VOLUMES IDENTICAL TO BASELINE
```

The pre-existing container was present in every intermediate check and was never stopped,
removed or modified; its creation timestamp is unchanged. Resources I created and then removed
**by exact name/ID only** (never `prune`, never a filter sweep): decoy containers
`veyro-mod001-harness-r4decoy1` and `unrelated-veyro-mod001-harness-r4xyz` (+ their anonymous
volumes `1491608d5aa4…`, `f1cff5602017…`); drill containers `…-r4ps0001`, `…-r4rm0001`,
`…-r4werr01`, `…-9b6522f2` (+ volumes `9ccd0101c998…`, `47ae11ed0b3b…`, `717bb08fead9…`,
`f78d5c22c3c9…`); the M8-leaked volume `32168c6712a5…`; and probe resources `r4-multivol`,
`r4probe-a`, `r4probe-b` (+ its anonymous volume `34f8f3fe27a8…`). Volumes were diffed back to
baseline after every drill, not only at the end.

## 6. Control-by-control assessment against `.claude/rules/backend/concurrency.md`

| Control | Status | Basis |
|---|---|---|
| 1 — explicit version column | SATISFIED | `concurrency.py:188-190` creates `version integer NOT NULL DEFAULT 1` (READ); M5 confirms the column is load-bearing (OBSERVED) |
| 2 — read/check/increment in one atomic statement | SATISFIED | single `UPDATE … SET version = version + 1, … WHERE id = %s AND version = %s` (`:252`, READ); M1 and M5 both killed (OBSERVED) |
| 3 — mismatch surfaced as a typed, distinguishable conflict | SATISFIED for the harness's own sequential fixture | `VersionConflict`/`RowNotFound` (`:135`, `:151`), raised at `:256-259`; M2/M6 killed (OBSERVED). **The 404-vs-409 disambiguation is not atomic under real concurrency — see R4-4.** |
| 4 — lost-update resolution is an explicit documented decision | SATISFIED | reject-and-retry, stated in the module docstring `:26-37` and cross-recorded non-chronologically in `REQUIREMENTS.md`'s DOM-002 traceability row (READ) |
| 5 — append-only exemption | N/A | the fixture aggregate is mutable by design |
| Fail-closed rule — a deliberately-broken version-check fixture must be shown to fail closed | SATISFIED | `update_unversioned_blind` (`:263-271`) + `test_naive_unversioned_update_loses_the_update`; M4a and M7 both killed (OBSERVED) |

## 7. Owner-reserved restrictions, capability governance, secrets

All READ unless marked.

* **No paid services / no spend.** Everything runs on the local CAP-008 Colima engine and the
  already-pinned `postgres:16-alpine` digest. No network service, no account, no activation.
* **No real member data.** Fixture rows are `uuid4()` ids and the literals `initial`,
  `updated-once`, `writer-a`, `writer-b`, `x` (`test_concurrency_harness.py`). Nothing
  PII-shaped anywhere in the four files.
* **No Production deploy/promotion.** Nothing in scope touches a deploy path.
* **No material product/pricing/business/architecture/scope change.** The change set is a test
  harness plus its own regression tests; `SCN-MOD001-009` is untouched and unpromoted (OBSERVED
  by grep).
* **Secrets rule (`.claude/rules/infra/secrets.md` control 1) — no credential-shaped committed
  value.** `postgres.py:183` generates `secrets.token_urlsafe(24)` at runtime; it reaches Docker
  via `extra_env` (`:191`), never argv (`:185`'s `-e POSTGRES_PASSWORD` with no value), and
  `DisposablePostgres.superuser_password` is `field(repr=False)` (`:103`) so it cannot surface in
  a traceback. `DockerRoute.__call__`'s error text deliberately includes only the subcommand and
  docker's stderr (`:77-78`, `:88-94`). The new token is not a secret and is not credential-shaped.
* **Capability governance (DC-19).** The only capability exercised is CAP-008, which is
  registered in `CAPABILITY_REGISTRY.md` and whose `review_status` field now reads **APPROVED
  (2026-10-04, third independent fresh-context Opus capability-security review)**;
  `validate_capabilities.py` returns `PASS — 8 … all registered and APPROVED` (OBSERVED). No
  unregistered capability is used by this slice. **However two module-level durable records still
  assert the opposite — see R4-6.**
* **Security probe of the new env var (OBSERVED, `/tmp/r4/r4_d5_token_validation.py`).** Because
  the token is interpolated into a `docker run` argv, I probed for argument injection:

  ```
  argv-injection probe: token that looks like a docker flag:
      container created -> veyro-mod001-harness---privileged
  invalid container-name characters: RuntimeError: `docker run` exit 125: docker: Error response
      from daemon: Invalid container name (veyro-mod001-harness-BAD/TOKEN), only
      [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed
  ```

  A flag-looking token is consumed as the *value* of `--name` (the container is literally named
  `veyro-mod001-harness---privileged`, **not** run privileged) because the route builds a list
  argv with no shell (`postgres.py:82-86`). An out-of-charset token fails closed on Docker's own
  name validation. **No injection path; no P0/P1/P2 security finding.** A defence-in-depth note
  is folded into R4-2.

## 8. Findings

Six findings, all P3. Nothing found at P0/P1/P2.

### R4-1 (P3, new-defect) — `_cleanup_container`'s "Never raises" contract is false under `filterwarnings = ["error"]`, and the masking R3-4 closed comes straight back

**Where.** `backend/tests/integration/test_concurrency_harness_order_independence.py:131-168`.
The docstring promises, at `:136-138`: "Never raises — a failure at any step is reported via
`warnings.warn` and the function degrades to doing less, never to masking whatever exception is
already propagating from the caller's own `try` (R3-4 …)". The three `warnings.warn` calls are at
`:142-146`, `:154-158` and `:161-166`, all inside `_run_pytest`'s `finally` (`:208-213`).

**Why it is a defect.** `warnings.warn` is not a non-raising primitive — under an `error` filter
it raises the warning as an exception. `backend/pyproject.toml`'s `[tool.pytest.ini_options]`
currently sets only `testpaths = ["tests"]`, so there is no `filterwarnings` entry today and the
calls are benign. One line of configuration (`filterwarnings = ["error"]`, or a `pytest -W error`
invocation — both standard hardening for a project at this rigor level) turns every one of them
into an exception thrown from a `finally`, which replaces the real `TimeoutExpired`. That is
R3-4's exact defect, reintroduced through the mechanism chosen to fix it.

**Demonstrated (OBSERVED, `/tmp/r4/r4_d4_werror.py`)** — identical drill to §3/R3-4's `rm`
failure, run under `warnings.simplefilter("error")`, which is precisely what
`filterwarnings = ["error"]` does:

```
pytest filterwarnings currently configured in backend/pyproject.toml: (none)
under -W error, exception surfaced to caller: UserWarning | R2-1/R3-4 safety net: failed to
    remove leaked container veyro-mod001-harness-r4werr01 (its volume '717bb08fead…
RESULT: REAL TimeoutExpired MASKED by the cleanup-path warning
reviewer cleanup: removed veyro-mod001-harness-r4werr01 (+ volume 717bb08fead96746…)
```

A secondary, lower-stakes half of the same point: in the two production-path tests
(`…review_4_4`, `…review_4_5`, which pass no `cleanup_outcome` and assert nothing about cleanup)
a warning is an *advisory* signal only — it appears in pytest's warnings summary and does not
fail the run. That is strictly better than round 2's silent `except RuntimeError: pass`, so R3-4
is genuinely fixed; it is simply the weakest end of the signal spectrum.

**Recommended next action.** Make the cleanup path's signalling incapable of raising — e.g. wrap
each `warnings.warn` in `with warnings.catch_warnings(): warnings.simplefilter("always")`, or
emit through a non-raising channel — so the docstring's "Never raises" is unconditionally true.
If instead the behaviour is accepted as-is, amend the docstring to state the `-W error`
exception, since an inaccurate "never raises" contract on a `finally`-path helper is the kind of
claim a later maintainer will reasonably rely on.

### R4-2 (P3, new-defect) — `CONTAINER_TOKEN_ENV_VAR` carries an undocumented "exactly one container per process tree" precondition, and a real multi-container session breaks

**Where.** `backend/tests/harness/postgres.py:167-182` (the comment block and
`token = os.environ.get(CONTAINER_TOKEN_ENV_VAR) or secrets.token_hex(4)`).

**Why it is a defect.** The comment documents the change as unconditionally additive — "Unset
(every other caller, today and historically) is byte-identical to the prior unconditional
`secrets.token_hex(4)` behavior" — which is true, but it never states the precondition that
applies when the var *is* set. An environment variable is inherited by the entire process tree,
while `disposable_postgres()` has four independent call sites, two of which have **overlapping
lifetimes**: the session-scoped `pg` at `backend/tests/integration/conftest.py:32-35` and the
module-scoped `pg` at `backend/tests/integration/test_migration_safety_harness.py:66-69` (which
shadows it for that module only). With a fixed token, the second `docker run` collides with the
first container, which is still alive.

**Demonstrated (OBSERVED).**

```
$ VEYRO_HARNESS_CONTAINER_TOKEN=r4coll01 .venv/bin/python -m pytest \
      tests/integration/test_concurrency_harness.py \
      tests/integration/test_migration_safety_harness.py -q
4 passed, 36 errors in 2.32s

E  RuntimeError: `docker run` exit 125: docker: Error response from daemon: Conflict. The
   container name "/veyro-mod001-harness-r4coll01" is already in use by container
   "c274ef75e737…". You have to remove (or rename) that container to be able to reuse that name.
```

**Mitigating facts, verified rather than assumed.** It fails *loud*, not silent: the collision
raises at `postgres.py:186`, which is *before* that invocation's `try`/`finally`, so the
already-running first container is never touched by the failing caller and is still reaped by its
own fixture finalizer — Docker state returned to baseline exactly after the drill (OBSERVED). And
no current caller trips it: `_run_pytest` scopes the var to a single child whose argument lists
(`CONCURRENCY`, `GATE_CANONICAL`, `GATE_CATALOG` — `:88-93`) all resolve to the one
session-scoped `pg`. So this is a latent trap for the next maintainer, not a live break. Hence
P3, not P2.

**Recommended next action.** State the precondition explicitly in `postgres.py:167-176` and in
`_run_pytest`'s docstring ("valid only for a process tree that creates exactly one container").
Stronger, and cheap: have `disposable_postgres` *consume* the variable —
`token = os.environ.pop(CONTAINER_TOKEN_ENV_VAR, "") or secrets.token_hex(4)` — so the first
container in a process honours it and any subsequent one falls back to a random token, which
removes the in-process collision class entirely. Optionally add a charset assertion on the token
(defence in depth; §7 shows the current failure is already closed and non-injectable, so this is
about diagnostics, not security).

### R4-3 (P3, new-defect) — `_anonymous_volume_of`'s Go template concatenates multiple mounts into one non-existent ID, which would silently re-vacuate the R3-2 lock just added

**Where.** `backend/tests/integration/test_concurrency_harness_order_independence.py:120-128`:

```python
    raw = docker(
        "inspect", name, "--format",
        '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}',
    )
    return raw or None
```

**Why it is a defect.** The `range` emits each volume name with no separator. With one mount the
result is a valid ID (which is why the fix works today). With two or more it is a concatenation
of IDs that matches nothing, and *both* downstream assertions then pass on garbage: `:262`'s
`assert volume is not None` is satisfied by any non-empty string, and `:266`'s
`assert volume not in docker("volume", "ls", "-q").splitlines()` is trivially true for an ID that
never existed. The R3-2 regression lock would go green while leaking every volume — the same
vacuity class as R3-3, inside R3-2's own fix. Nothing in the file or the harness asserts that the
container has exactly one volume mount.

**Demonstrated (OBSERVED)** — the production template run against a deliberately two-mount
container (plus the image's own declared `VOLUME`, so three):

```
production template output on a 2-volume container:
r4probe-ar4probe-b34f8f3fe27a8d0ef5723332ae7db1ed06004626da34d5482f88fc70dbb45b997
(each real volume, for comparison):
r4probe-a|r4probe-b|34f8f3fe27a8d0ef5723332ae7db1ed06004626da34d5482f88fc70dbb45b997|
--- is the concatenated string a real volume id? ---
NO (so 'assert volume not in volume ls' would pass vacuously)
```

Latent today: the pinned `postgres:16-alpine` digest declares exactly one `VOLUME`, which I
confirmed live. It stops being latent the moment the image is bumped to one that declares a
second mount, or the fixture ever adds a `-v`.

**Recommended next action.** Emit a separator and handle the list — e.g.
`'{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}\n{{end}}{{end}}'`, return
`raw.splitlines()`, assert the expected count, and assert *every* returned ID is absent after
cleanup. That makes the assertion true-by-construction rather than true-by-image-coincidence.

### R4-4 (P3, new-defect) — `update_versioned`'s 404-vs-409 disambiguation is not atomic, and the "Plug-in point" section tells five later modules to copy it

**Where.** `backend/tests/harness/concurrency.py:252-260`. The `UPDATE` (`:255`) and the
`_row_exists` probe (`:257`) are two separate statements, executed on an autocommit connection
(`backend/tests/integration/conftest.py:41`: `psycopg.connect(pg.superuser_dsn,
autocommit=True)`), i.e. in two separate transactions. The docstring at `:249-251` and the module
docstring at `:14-17` both state the disambiguation flatly, with no atomicity caveat; the "Known
ceiling" paragraph (`:90-97`) discloses the *simulation* ceiling but not this one.

**Why it is a defect.** Between the `UPDATE` affecting zero rows and the existence probe, another
writer can insert the row, and the function then raises `VersionConflict` for a row that did not
exist when the update ran — a 409 where 404 is the truthful answer. The harness's own fixture is
single-connection and sequential, so this cannot fire in MOD-001's own tests. But
`concurrency.py:65-88` instructs MOD-002, MOD-019, MOD-020, MOD-034 and MOD-037 by name to
"mirror `update_versioned`'s `WHERE id = %s AND version = %s` … shape for your own mutations, and
reuse `VersionConflict`/`RowNotFound` … as the API boundary errors `.claude/rules/backend/api.md`'s
typed-errors control requires" — i.e. adopters are pointed at this exact disambiguation for real
aggregates under real concurrency, which is the entire point of DOM-002.

**Demonstrated (OBSERVED, `/tmp/r4/r4_d6_toctou.py`)** — row absent at `UPDATE` time, a second
independent connection inserts it inside the window:

```
row absent at UPDATE time; a concurrent writer inserts it in the window
RESULT: VersionConflict (version conflict on concurrency_harness.versioned_widget:
        id=2bd58052-6887-40c7-915f-88bf48bb2390 expected_version=1)
        ^ WRONG TYPE: no row existed when the UPDATE ran, so there was no version to conflict
          with. A real API boundary would answer 409 Conflict where 404 Not Found is truthful.
```

(The window was opened deterministically by making the probe's own call site insert the row from
a second connection first; the two statements' non-atomicity is the property being shown, not the
particular scheduling.)

**Why P3 and not higher.** No failing scenario, no product defect, no false-clean evidence for
any claim MOD-001 actually makes — the harness is correct for the aggregate it tests, and the
rule's controls 1-4 are all satisfied (§6). The exposure is forward-binding documentation.

**Recommended next action (highest-priority of these six).** Either make the disambiguation
atomic — one statement, or both statements inside a single explicit transaction, which is also
what `.claude/rules/backend/architecture.md` control 7 will require of any real adopter's
application-service method — or, at minimum, add the caveat to both the "Known ceiling" and
"Plug-in point" sections so no MOD-002+ adopter inherits a latent 409-for-404. This should be
resolved before the first real adoption, independently of MOD-001's own certification.

### R4-5 (P3, new-defect) — the `container_was_created` assertion message names only one of at least three causes, and mis-attributes name-scheme drift

**Where.** `backend/tests/integration/test_concurrency_harness_order_independence.py:256-260`
(message: "`_FORCED_TIMEOUT_S={…} may be too short for this environment`"), in combination with
`:95-97`'s hand-duplicated `_HARNESS_CONTAINER_PREFIX = "veyro-mod001-harness-"` whose own
comment says it "Must match `disposable_postgres`'s own naming scheme exactly
(`tests/harness/postgres.py`): `f"veyro-mod001-harness-{token}"`" — with nothing enforcing it,
because `postgres.py` exports no prefix constant or name-builder (the literal lives at
`postgres.py:182`).

**Why it is a defect.** `container_was_created is False` has at least three causes: the timeout
being too short (the one named), the child failing before it created a container, and the two
copies of the naming scheme having drifted. In the drift case the message actively points the
reader at the wrong thing — and that case also leaks a real container, because cleanup was
aiming at a name that never existed.

**Demonstrated (OBSERVED)** — the prefix-drift mutant from §4:

```
E       AssertionError: no container was ever created before the forced timeout fired —
        _FORCED_TIMEOUT_S=1.2 may be too short for this environment; …
1 failed in 1.51s

### leaked by the prefix mutant (the child's real container, now unreapable) ###
veyro-mod001-harness-9b6522f2|Up 1 second
veyro-mod001-harness-7196bf51|Up 5 hours
```

(I removed `veyro-mod001-harness-9b6522f2` and its anonymous volume `f78d5c22c3c9…` by exact
name; volumes diffed back to baseline.)

**The good news, verified.** The duplication *is* regression-locked — the mutant is KILLED, not
survived, so drift cannot ship silently. This is a diagnostics and single-source-of-truth
finding, not a correctness hole.

**Recommended next action.** Export the naming scheme from `postgres.py` (a
`CONTAINER_NAME_PREFIX` constant or a `container_name(token)` helper) and have the
order-independence module import it, removing the second copy; and broaden the assertion message
to name the drift and early-child-failure causes alongside the timeout one.

### R4-6 (P3, drift) — two MOD-001 durable records still state CAP-008 is `QUALIFIED (not APPROVED)` and "not usable for real project work", contradicting the registry and the live gate

**Where.**
* `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml:11-19` — "CAP-008's
  `review_status` is QUALIFIED, not APPROVED … `validate_capabilities.py` is therefore EXPECTED
  to report CAP-008 as not satisfying this dependency until that re-review restores APPROVED."
* same file, `:38-46` (`required_status:`) — "QUALIFIED (not APPROVED) as of 2026-10-04 … Per
  CAPABILITY_POLICY.md this capability is not usable for real project work at QUALIFIED —
  touchable only under stage 4-5 re-qualification drills".
* `knowledge/03-Modules/MOD-001/CAPABILITIES.md:5` (front-matter `updated:`) and `:108-115` —
  same QUALIFIED-not-APPROVED framing.

**Against what.** `knowledge/00-System/CAPABILITY_REGISTRY.md`'s CAP-008 row now carries
`**APPROVED (2026-10-04, third independent fresh-context Opus capability-security review,
P0=0/P1=0/P2=0-blocking)**`, and the gate agrees (OBSERVED):
`RESULT: PASS — 8 capability/capabilities, all registered and APPROVED with required fields present.`

**Why it matters here rather than being a bookkeeping nit.** Every drill in this review ran a
real CAP-008 container, and `postgres.py` is in this review's scope, so "is this slice's
capability use registered and approved?" is a question I had to answer. Per the authoritative
source — the registry — it is: **no unregistered or unqualified capability use, no
`CAPABILITY_POLICY.md` fail-closed violation.** But two module-level durable records now tell a
future fresh-context session the opposite, including a prediction about the gate's output that is
observably false. Per DC-10/DC-15 the vault is the durable authority a later session reads
instead of a transcript; a stale "not usable for real project work" on the trust anchor of the
whole GOV-01-R02 harness family is exactly the kind of false signal that discipline exists to
prevent. Both files are in the current uncommitted set, so this is reconcilable now.

**Recommended next action.** Reconcile both files to the registry row (status, the "not usable"
sentence, and the "EXPECTED to report … not satisfying" prediction), keeping the round-16 history
as history rather than as current state. Out of the four-file code scope, so recorded here as an
adjacent finding for the module owner rather than as a code defect.

## 9. Verdict

**PASS with findings. P0 = 0, P1 = 0, P2 = 0, P3 = 6.**

All six round-3 findings are confirmed fixed by my own execution, not by reading the remediation
record: R3-1 by two live decoy drills on both the timeout and success paths (the decoy survives
where round 3 destroyed it, and the unanchored-substring decoy survives too), R3-2 by the M8
mutant now failing and naming the leaked volume where it previously survived, R3-3 by the
artificially-short timeout now failing loudly where it previously passed vacuously, R3-4 by both
monkeypatch drills through the real `_run_pytest` path showing the `TimeoutExpired` preserved and
the `rm` failure signalled, R3-5 by reading the new paragraph in the place round 3 required it,
and R3-6 by a mechanical docstring balance check across all four files.

The pattern that defeated rounds 2 and 3 — a fix that introduces new defects on the same code
path — did **not** repeat at P2. The three new defects I found in the fix itself (R4-1, R4-3,
R4-5) are all latent rather than live: each requires a configuration change, an image change, or
a maintainer edit before it can fire, and each is either loud or already regression-locked when
it does. That is a materially different risk profile from round 3's R3-1 (destructive on every
invocation) and R3-2 (a surviving mutant producing false-clean evidence).

Under the Development Constitution's "zero known defects at approval" rule (DC-08), P3 findings
do not block certification. Under DC-12 they are still real engineering debt, and **R4-4 should
be resolved before any MOD-002+ module adopts the pattern**, since that is the point at which a
documentation gap becomes a production 409-for-404.

Nothing found at P0/P1/P2. No owner-reserved restriction is approached, let alone crossed. No
unregistered or unqualified capability is used. No governing baseline is modified
(`verify_baselines.py` PASS 4/4, OBSERVED). Full suite 203/203 in both collection orders
(OBSERVED). Docker state identical to the pre-review baseline (OBSERVED).

## 10. Next action

1. **Module owner / implementation session** — address R4-4 first (atomicity or disclosure in
   `concurrency.py`'s "Known ceiling" + "Plug-in point"), then R4-1 (make the cleanup path's
   signalling genuinely non-raising, or correct the "Never raises" docstring), R4-3 (separator +
   list handling + mount-count assertion in `_anonymous_volume_of`), R4-5 (single-source the
   container-name scheme from `postgres.py`; broaden the assertion message), R4-2 (document the
   one-container-per-process-tree precondition, and consider `os.environ.pop`).
2. **Module owner** — reconcile R4-6's two durable records to `CAPABILITY_REGISTRY.md`'s current
   CAP-008 `APPROVED` status before the next gate that reads them.
3. **Orchestrator** — clear `knowledge/00-System/REVIEW_IN_FLIGHT.md`'s round-4 claim
   (`IN_FLIGHT — DOM-002 code review round 4, claimed by Veyro watchdog
   66643874-e295-4d53-a846-ee79cb6c3a44`) only after independently attesting this report against
   this reviewer's real transcript via `mr_verify.py`, per that file's own rule. No model-identity
   self-attestation is made in this report by instruction.
4. **A round-5 review, if dispatched**, should re-run §3's four drills and §4's 11-mutant set
   against whatever changes land, and should additionally re-execute the two controls I
   deliberately skipped: round 3's §4.9 same-session setup-failure drill against the `widget`
   fixture's `try`/`finally`, and round 3's §4.15 live `pg_namespace`-owner catalog probe.
5. **`SCN-MOD001-009` remains NOT promoted and NOT claimed PASS.** Certification remains a
   separate Gatekeeper action; this report is not one.

## Appendix — drill artifacts

All outside the repository tree, retained for re-execution:
`/tmp/r4/make_mutant.py`, `/tmp/r4/make_conc_mutant.py`, `/tmp/r4/mutants/` (mutated copies and
their loader plugins), `/tmp/r4/r4_d1_overreap_timeout.py`, `/tmp/r4/r4_d2_overreap_success.py`,
`/tmp/r4/r4_d3_r34_guards.py`, `/tmp/r4/r4_d4_werror.py`, `/tmp/r4/r4_d5_token_validation.py`,
`/tmp/r4/r4_d6_toctou.py`, `/tmp/r4/r4_d7_timing.py`, `/tmp/r4/baseline_containers.txt`,
`/tmp/r4/baseline_volumes.txt`.

## Dispatching-session capture addendum — 2026-10-04 (recorded by the fresh orchestrating
## session that dispatched this review, not by the reviewer itself)

This review was dispatched via the `Agent` tool, `subagent_type: veyro-code-reviewer`
(registered Opus-tier role), from orchestrating session
`8add29a5-1560-4893-ab8d-94f6ad777385`. The reviewer's own report (above) correctly declined to
self-attest model identity or transcript location, per its dispatch instructions — that
information is recorded here instead, for the orchestrator's `mr_verify.py` step:

- **Agent id:** `a008ec2c41fc4d96f`
- **Actual transcript file:**
  `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/8add29a5-1560-4893-ab8d-94f6ad777385/subagents/agent-a008ec2c41fc4d96f.jsonl`
  (227 lines/turns in the raw transcript; the subagent's own self-reported `tool_uses: 53`,
  `subagent_tokens: 205553`, `duration_ms: 1024676`)
- **Transcript metadata file:**
  `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/8add29a5-1560-4893-ab8d-94f6ad777385/subagents/agent-a008ec2c41fc4d96f.meta.json`
  — confirms `agentType: veyro-code-reviewer`, `description: "DOM-002 concurrency pattern
  round-4 independent code review"`.
- **Reviewer's self-reported verdict (unverified by this dispatching session):** PASS,
  P0=0/P1=0/P2=0/P3=6 (R4-1..R4-6, full detail in §9 above).

**This dispatching session did NOT run `mr_verify.py`** against the transcript above and does
**not** attest the reviewer's model tier — per this task's explicit instruction, that
independent verification step belongs to the orchestrator (the watchdog that holds the
`REVIEW_IN_FLIGHT.md` round-4 claim), to be run against the real transcript file path recorded
above before the claim is cleared or any verdict is treated as PASS. This dispatching session
also did not clear `REVIEW_IN_FLIGHT.md`, promote `SCN-MOD001-009`, certify the module, alter
ADR-010/R04, or change any production code. Pre-dispatch Docker baseline (1 container
`veyro-mod001-harness-7196bf51` + 2 volumes) was confirmed unchanged after the review completed;
`git status --porcelain -- backend/` shows no production-code files added or modified beyond
the pre-existing uncommitted set already present at session start.
