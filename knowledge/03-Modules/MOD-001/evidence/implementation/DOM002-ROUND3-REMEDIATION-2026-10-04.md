---
doc: DOM002_ROUND3_REMEDIATION
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
responds_to: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND3-2026-10-04.md
remediation_session: same retained MOD-001 GOV-01-R02 implementation session (Sonnet), not an independent review
date: 2026-10-04
---

# DOM-002 concurrency pattern — round-3 code-review remediation

## 0. What this is

Bounded remediation of round-3's verdict **PASS (P0=0, P1=0, P2=2, P3=4)**
— `mr_verify.py` PASS 130/130 `claude-opus-5`, independently verified by
the orchestrator against the reviewer's real transcript (orchestrator
attestation addendum, round-3 report §"Orchestrator attestation
addendum"). `REVIEW_IN_FLIGHT.md`'s round-3 claim was already `CLEAR` at
this session's start; left untouched. This is implementation remediation,
not a self-approval — see §8 for the next independent-review action.

Round 3 confirmed R2-2/R2-3/R2-5 genuinely fixed and R2-4's deferral
upheld by its own independent execution. It found R2-1 only **partially**
fixed: the named container/volume leak was genuinely closed (5/5 live
`docker events` runs), but the fix it introduced carried four new defects
on the same code path (R3-1, R3-2 — both P2 — and R3-3, R3-4, R3-5, R3-6 —
all P3).

## 1. R3-1 (P2, highest priority) — over-reap of an unrelated concurrent container

**Defect:** round 2's cleanup diffed `veyro-mod001-harness-*` containers
before/after the `subprocess.run` call. The diff was scoped by *time
window*, not by *provenance* (any container matching the prefix that
appeared during the window was removed, regardless of who created it), and
the name filter itself was an unanchored substring match (`docker ps -a
--filter name=veyro-mod001-harness-` also matched
`unrelated-veyro-mod001-harness-xyz`). The review demonstrated this live,
on both the timeout path and the ordinary success path.

**Independently reproduced before fixing:** created a decoy container
named `veyro-mod001-harness-decoy0{1,2}` from a background job timed to
land ~0.5s into the `subprocess.run` window, then ran the (then-current,
unfixed) regression test. The decoy was destroyed by the test's own
cleanup — confirmed live, matching the review's finding exactly.

**Fix — provenance scoping, not a sharper filter:** `tests/harness/
postgres.py`'s `disposable_postgres()` now accepts an optional
`VEYRO_HARNESS_CONTAINER_TOKEN` environment variable; if set, its value
becomes the container's random-suffix token instead of a freshly generated
one (additive/backward-compatible — every other caller, unset, is
byte-for-byte identical to the prior behavior). `test_concurrency_harness_
order_independence.py`'s `_run_pytest` now generates a per-invocation
token, passes it to the child via that env var, and therefore knows the
*exact* container name the child's own `disposable_postgres()` will use
*before the child even starts*. Cleanup checks for and removes that one
exact name — never a prefix sweep, never a time-window diff. A
`secrets.token_hex(4)` collision with a genuinely unrelated container is
cryptographically negligible, not a timing question.

**Verification — the same decoy drill, post-fix:** re-ran the identical
mid-window decoy drill against the fixed code. The decoy
(`veyro-mod001-harness-decoy03`) survived, confirmed `Up 1 second` after
the test completed, then removed by hand. Docker state (containers +
volumes) returned to the pre-existing baseline (`veyro-mod001-harness-
7196bf51` + 2 volumes) before and after every drill in this round.

## 2. R3-2 (P2) — volume half of BUG-051 not regression-locked; M8 mutant survived

**Defect:** the regression test asserted on the container set only. Round
3's **M8** mutant (drop `-v` from the `rm` call) left the test passing
while a real anonymous volume leaked (`2 → 3`).

**Independently reproduced before fixing:** applied the identical M8
mutant in a throwaway copy — test passed, live volume count rose from 2
to 3, leaked volume confirmed via `docker volume ls -q` and removed by
hand.

**Fix:** the cleanup path now captures the exact container's anonymous
volume ID via `docker inspect ... --format '{{range .Mounts}}...{{end}}'`
*before* removing it, and reports that ID back to the caller (via the new
`cleanup_outcome` output-parameter — see §3). The regression test asserts
that specific volume ID is absent from `docker volume ls -q` after
cleanup.

**Verification:** re-ran the identical M8 mutant against the fixed test —
now **fails** with an explicit `AssertionError` naming the leaked volume
ID. Leaked volume removed by hand; state confirmed back to baseline.

## 3. R3-3 (P3) — vacuous timeout test, no positive "a container was created" assertion

**Defect:** the only assertion (`after == before`) is equally satisfied
by "nothing was ever created" and "something was created and reaped" — an
unlucky `timeout` value (too short for a cold image pull or a contended
host) would make the test pass with no signal that its own premise never
held.

**Fix:** `_run_pytest` gained an optional `cleanup_outcome: dict[str,
object] | None` output-parameter. When supplied, the `finally` records
whether a container existed, whether it was removed, and its volume ID
into that dict — the only way to observe this on the `TimeoutExpired`
path, since no return value is ever reached there. The regression test
passes its own dict and asserts `container_was_created is True` *before*
asserting anything about cleanup, so an environment where the timeout is
too short now fails loudly and specifically rather than passing trivially.

**Verification — both directions, in a throwaway copy:** lowered
`_FORCED_TIMEOUT_S` to `0.05` (well under the measured ~0.36s
container-create time) and re-ran — the test now fails with `AssertionError:
no container was ever created before the forced timeout fired —
_FORCED_TIMEOUT_S=0.05 may be too short for this environment; every
assertion below would otherwise pass vacuously`, exactly the loud failure
R3-3 asked for instead of a silent pass. Restored `_FORCED_TIMEOUT_S =
1.2` (unchanged from round 2 — the exact value is no longer load-bearing
for correctness now that the test self-validates; a comment in the source
documents the measured `[~0.36s, ~1.72s]` margin from the round-3 report).

## 4. R3-4 (P3) — unguarded existence probe could mask the real exception; swallowed `rm` failure gave no signal

**Defect:** only the `rm` call was wrapped in `try/except RuntimeError:
pass`; the `docker ps` existence probe itself was not, so a failure there
replaced the real `TimeoutExpired` with an unrelated `RuntimeError`. And a
failing `rm` was swallowed with zero signal anywhere.

**Fix:** extracted a `_cleanup_container` helper. Every step (existence
probe, volume inspect, `rm`) is independently wrapped; any failure is
reported via `warnings.warn` (never raised) and the function degrades to
doing less rather than letting a cleanup-path exception replace whatever
the caller's own `try` is already propagating.

**Verification — both directions, via in-process monkeypatch (no real
Docker calls, no real leak risk):**

```
>>> _cleanup_container(FailingPsRoute(), "...")
UserWarning: R2-1/R3-4 safety net: could not confirm whether ... exists;
cleanup skipped for this invocation: simulated engine hiccup during cleanup
-> (False, False, None)   # no exception raised, no masking

>>> _cleanup_container(FailingRmRoute(), "...")
UserWarning: R2-1/R3-4 safety net: failed to remove leaked container ...
(its volume 'somevolume123' may also be leaked): simulated rm failure
-> (True, False, 'somevolume123')   # signaled, not silent
```

## 5. R3-5 (P3) — R2-4's deferral undiscoverable from the code adopters actually read

**Defect:** the deferral's own stated mitigation ("re-read concurrency.
py's Plug-in point section and R2-4's text") pointed at a section that, in
fact, said nothing about the absent shared base class.

**Fix:** added one paragraph to `concurrency.py`'s "Plug-in point" section
stating plainly that `VersionConflict`/`RowNotFound` share no base class,
that this is a recorded upheld deferral (not an oversight), and why.

## 6. R3-6 (P3) — unclosed parenthesis in a docstring

**Disposition:** moot. The entire module docstring of `test_concurrency_
harness_order_independence.py` was rewritten as part of this round's R3-1
fix (the whole "why this cleanup exists" narrative changed along with the
mechanism), and the rewritten text does not reproduce the malformed
sentence. No separate edit was needed.

## 7. Full regression evidence

```
$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python -m mypy tests/
Success: no issues found in 28 source files

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
4 passed in 1.67s

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -v
3 passed in 6.22s

$ .venv/bin/python -m pytest tests -q                                       # default order
203 passed in 30.10s

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q   # reversed order
203 passed in 28.31s

$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.

$ backend/.venv/bin/python knowledge/00-System/validate_capabilities.py
RESULT: PASS — 8 capability/capabilities, all registered and APPROVED with required fields present.
```

Docker state (`docker ps -a --filter name=veyro-mod001-harness-`, `docker
volume ls -q`) confirmed unchanged across every run in this round: the
one pre-existing, out-of-scope `veyro-mod001-harness-7196bf51` container
(recorded as pre-existing by rounds 1/2/3 alike) plus 2 volumes (its
anonymous volume + the unrelated named `tradingview-mcp-session`) — never
touched, never pruned.

203 = 202 (round-2-remediation baseline) + 1 (the R2-1 regression test,
unchanged count — its internals were rewritten but it is still exactly
one test function; the file also still has 3 test functions total, same
as round 2). Zero regressions in either collection order.

## 8. Scope discipline confirmed

No edit to `R04`, `ADR-010`, `SCN-067`, `BUG-048`. `SCN-MOD001-009` is
**not promoted and not claimed PASS** by this remediation. WIP=1
respected — no other module touched. Files changed this round:
`backend/tests/harness/postgres.py` (additive `CONTAINER_TOKEN_ENV_VAR`
support, backward-compatible for every existing caller),
`backend/tests/integration/test_concurrency_harness_order_independence.py`
(R3-1/R3-2/R3-3/R3-4 fix, rewritten cleanup mechanism), `backend/tests/
harness/concurrency.py` (R3-5 docstring addition), plus this file and the
standard `STATUS.md`/`TEST_RESULTS.md`/`CURRENT_STATE.md`/
`CURRENT_HANDOFF.md` checkpoint updates. No commit/push — all
new/changed files remain either untracked or part of this session's
existing uncommitted set; nothing reset, stashed, or discarded.

## 9. Next independent-review action

A round-4 review, if dispatched, should re-run this report's §1-§4
commands directly: the decoy over-reap drill (now expected to show the
decoy surviving), the M8 mutant (now expected to fail with a named leaked
volume), the `_FORCED_TIMEOUT_S=0.05` vacuity drill (now expected to fail
loudly with the "no container was ever created" message), and the two
monkeypatch drills in §4 (now expected to warn rather than mask/swallow
silently). It should also re-run round 2's §4.13 mutation set and round
1/2/3's P1-2-only mutant against any changed `update_versioned`/teardown,
and re-verify that `postgres.py`'s `CONTAINER_TOKEN_ENV_VAR` addition is
genuinely a no-op for every caller that does not set it (the tenant-
isolation, authn, and migration-safety harnesses' own test suites, all
green in both collection orders in §7, are the evidence for that today).
