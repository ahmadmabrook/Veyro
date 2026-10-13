---
doc: DOM002_ROUND2_REMEDIATION
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
responds_to: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND2-2026-10-04.md
remediation_session: same retained MOD-001 GOV-01-R02 implementation session (Sonnet), not an independent review
date: 2026-10-04
---

# DOM-002 concurrency pattern — round-2 code-review remediation

## 0. What this is

Bounded remediation of round-2's verdict **PASS (P0=0, P1=0, P2=1, P3=4)** —
`mr_verify.py` PASS 102/102 `claude-opus-5`, independently verified by the
orchestrating session against this reviewer's own transcript. PASS cleared
the blocking bar; the one P2 and four P3s are real defects that still
require remediation per the review's own §9. This is implementation
remediation, not a self-approval — see §7 for the next independent-review
action. `REVIEW_IN_FLIGHT.md`'s round-2 claim was already `CLEAR` at this
session's start (recorded 2026-10-04T04:19:19Z); left untouched.

## 1. R2-1 (P2, highest priority) — subprocess-timeout container/volume leak

**Defect:** `test_concurrency_harness_order_independence.py`'s `_run_pytest`
called `subprocess.run(..., timeout=180)` with no cleanup on the timeout
path. A `TimeoutExpired` SIGKILLs the nested pytest child, whose only
container teardown is its own `disposable_postgres`'s `finally`-block
`docker rm -f -v` — SIGKILL cannot run that, and the container never exits
on its own, so nothing else ever reaps it either. This is BUG-051's exact
mechanism on a newly-added code path.

**Fix:** `_run_pytest` now takes a `timeout` parameter and brackets the
`subprocess.run` call in `try`/`finally`. The `finally` diffs
`veyro-mod001-harness-*` containers (via the project's own `trusted_docker()`
route — never bare `docker` on `PATH`) immediately before and after the
call, and force-removes (`docker rm -f -v`) only the containers that
appeared during this specific invocation. This never touches a
pre-existing or unrelated container, and never calls `prune`. In the
non-timeout path this is a no-op (the child's own teardown already removed
its container before the parent's `subprocess.run` returns).

**Correction (round 3, 2026-10-04):** the sentence above — "This never
touches a pre-existing or unrelated container" — was **false as written**.
Round-3 code review finding R3-1 demonstrated live that the before/after
diff this section describes is scoped by *time window*, not by
*provenance*: a container created by a wholly unrelated concurrent process
during the `subprocess.run` window was force-removed by this cleanup, on
both the timeout path and the ordinary success path. The *pre-existing*
half of the claim was and remains true (a container present in `before`
always survives); the *unrelated-concurrent* half was not. See
`DOM002-ROUND3-REMEDIATION-2026-10-04.md` §1 for the fix (provenance
scoping via a per-invocation container-name token, not a diff) and its
independent live verification.

**New regression test:**
`test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1` —
forces a real `subprocess.TimeoutExpired` (`timeout=1.2`, matching the
review's own §4.10 empirically-validated value) against a real nested
pytest invocation, then asserts the container set is unchanged from before
the call.

**Verification — live, both directions:**

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -v
test_concurrency_before_canonical_rls_harness_test_review_4_4             PASSED
test_concurrency_between_two_rls_gate_invocations_review_4_5              PASSED
test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1     PASSED
3 passed in 6.24s
```

Docker state before and after: unchanged (`veyro-mod001-harness-7196bf51`
only, the same pre-existing/unrelated container both round-1 and round-2
reviews recorded — confirmed via `docker ps -a --filter name=veyro-mod001-harness-`).

**Non-vacuity, in a throwaway full-structure copy under `/tmp` (deleted
after):** removed the `try`/`finally` cleanup (restored the pre-fix
`_run_pytest` body) and re-ran the exact same new test:

```
FAILED test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1
E   AssertionError: leaked containers after a forced timeout: {'veyro-mod001-harness-498b7412'}
```

The leaked container was then removed with a targeted
`docker rm -f -v veyro-mod001-harness-498b7412` (never `prune`), confirmed
back to the single pre-existing container. Real repo file confirmed
untouched throughout (`git status --porcelain` on the file, unchanged
`??` before/after).

## 2. R2-2 (P3) — `widget` fixture's teardown not `try`/`finally`-guarded

**Defect:** `create_versioned_table(...); row_id = ...; insert(...); yield
row_id; drop_versioned_table(...)` — a bare post-`yield` statement never
runs if anything between the create and the `yield` raises, leaking the
table for the rest of the session (reproduced live by the review's own
§4.11 drill).

**Fix:** everything from immediately after `create_versioned_table` through
the `yield` is now wrapped in `try`/`finally`, matching the idiom the
sibling test (`test_update_versioned_distinguishes_missing_row_from_version_conflict`)
already used for its own inline create/drop.

**Verification — reproduced the review's own §4.11 drill in a throwaway
copy, properly this time** (failing test and a catalog probe in the *same*
pytest session, sharing the same disposable container — the first attempt
at this check used two separate sessions and was discarded as methodologically
unsound before being recorded here): injected `raise RuntimeError(...)`
between `insert` and `yield`, ran the failing test followed by a probe test
querying `pg_tables` for any `%widget%` relation, in one `pytest` invocation:

```
tests/integration/test_concurrency_harness.py::test_single_writer... ERROR (injected failure, expected)
tests/integration/test_zzz_leak_probe.py::test_zzz_widget_leftover_probe PASSED
LEAK-PROBE []
1 passed, 1 error
```

No leftover relation — the `finally` ran despite the injected failure.
Throwaway copy and probe file deleted; real repo untouched.

## 3. R2-3 (P3) — docstring inaccuracy in `drop_versioned_table`

**Defect:** the docstring claimed the schema is "reused across
tests/sessions"; the "sessions" half is false — `conftest.py`'s `pg`
fixture gives every pytest session a fresh container, so no schema can
survive a session boundary regardless of this function's own behavior.

**Fix:** corrected to "reused across tests *within* a session", with a
parenthetical explaining why the "sessions" claim was wrong. No behavior
change — this was a documentation-only defect.

## 4. R2-5 (P3) — remediation record overclaimed a `STATUS.md` fix that didn't exist

**Defect:** `DOM002-ROUND1-REMEDIATION-2026-10-04.md`'s own P3-3 entry
claimed the round-18-remediation `STATUS.md` entry was "stating the
qualifier explicitly" (the simulated/sequential caveat for "racing
writers"). The review verified by direct `grep` that zero such qualifier
existed anywhere in `STATUS.md` at the time.

**Fix (chose to make the original claim true rather than only correct the
record, per the review's own offered either/or):** added the qualifying
sentence to `STATUS.md`'s active `updated:` entry: "The 'racing writers'
language throughout this round means the harness's own documented
simulated, sequential shape ... never real parallel load." The prior,
now-historical `prior_updated_round18` entry is left as-is, per this
project's append-don't-rewrite convention for historical record text —
only the still-active entry needed the correction.

## 5. P3-6 disposition correction (not a numbered round-2 finding, but explicitly requested)

Round 1's P3-6 disposition claimed "no realistic path to a leftover
wrong-shape table remains" for the `IF NOT EXISTS` masking risk. Round 2's
R2-2 finding demonstrated that claim was wrong at the time it was written.
§2 above closes the specific path R2-2 demonstrated. Corrected in
`DOM002-ROUND1-REMEDIATION-2026-10-04.md`'s own P3-6 bullet with a dated
addendum pointing back here, rather than silently editing the original
claim — consistent with this project's append-don't-rewrite convention for
evidence records once filed.

## 6. R2-4 (P3) — deferred, not fixed

**Finding:** `VersionConflict` and `RowNotFound` share no common base class
(both inherit directly from `Exception`), so a future domain adopter
wanting a single broad `except` for "any optimistic-concurrency failure on
this aggregate" has no type to catch without a tuple that goes stale when
a third error type is added.

**Disposition: DEFERRED**, per the review's own explicit framing of this as
"a judgment call for whoever adopts the template" rather than a defect in
this harness's own behavior (§8 of the round-2 report states this
directly). Reasons for deferring rather than fixing now:

1. **No current caller needs it.** The only two callers of either
   exception today are this harness's own four tests, which already
   `except` each type by name. A shared base class would have zero
   consumers until a real domain module (MOD-002/019/020/034/037) adopts
   the pattern.
2. **The right shape depends on the adopter, not on this harness.** A real
   domain's API boundary (`.claude/rules/backend/api.md`'s typed-errors
   control) may want the broad catch mapped to a specific HTTP status, a
   specific retry policy, or folded into that domain's own existing error
   hierarchy — decisions this synthetic fixture has no basis to make on a
   future adopter's behalf. Inventing a `ConcurrencyError` base now, before
   any real adopter exists to validate the shape, risks guessing wrong and
   then carrying an unused abstraction (or a breaking rename later).
3. **Zero cost to defer.** The two exceptions are correctly distinguished
   today (`DOM-002` rule control 3's actual requirement); adding a shared
   base later is a backward-compatible, additive change (both classes
   already fully exist and are used by name) — there is no migration cost
   created by waiting.

This disposition is recorded here, not silently dropped — a future
adopter of this plug-in template should re-read `concurrency.py`'s own
"Plug-in point" docstring section and R2-4's text in the round-2 report
before assuming a shared base exists.

## 7. Full regression evidence

```
$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python -m mypy tests/
Success: no issues found in 28 source files

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
4 passed in 1.63s

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -v
3 passed in 6.24s

$ .venv/bin/python -m pytest tests -q                                       # default order
203 passed in 28.59s

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q   # reversed order
203 passed in 29.04s

$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.
```

203 = 202 (round-1-remediation baseline) + 1 new R2-1 regression test.
Zero regressions in either collection order.

## 8. Scope discipline confirmed

No edit to `R04`, `ADR-010`, `SCN-067`, `BUG-048`. `SCN-MOD001-009` is
**not promoted and not claimed PASS** by this remediation. WIP=1
respected — no other module touched. Files changed this round:
`backend/tests/integration/test_concurrency_harness_order_independence.py`
(R2-1 fix + new regression test), `backend/tests/integration/
test_concurrency_harness.py` (R2-2 fix), `backend/tests/harness/
concurrency.py` (R2-3 docstring fix), `knowledge/03-Modules/MOD-001/
STATUS.md` (R2-5 fix), `knowledge/03-Modules/MOD-001/evidence/
implementation/DOM002-ROUND1-REMEDIATION-2026-10-04.md` (P3-6 addendum),
plus this file, plus the standard `CURRENT_STATE.md`/`CURRENT_HANDOFF.md`/
`TEST_RESULTS.md` checkpoint updates. No commit/push — all new/changed
files remain either untracked or part of this session's existing
uncommitted set; nothing reset, stashed, or discarded.

## 9. Next independent-review action

A round-3 review, if dispatched, should re-run this report's §1 command
directly and re-run the review's own §4.10 drill methodology (lower the
timeout until `TimeoutExpired` actually fires, diff `docker ps -a`/`docker
volume ls` before and after, clean up only what the drill itself created).
It should also re-run §4.11's same-session setup-failure drill against the
fixed `widget` fixture, and re-run the round-2 report's §4.8 mutation set
against any changed `update_versioned`. `REVIEW_IN_FLIGHT.md` was not
touched by this remediation and should be claimed fresh by whoever
dispatches round 3.
