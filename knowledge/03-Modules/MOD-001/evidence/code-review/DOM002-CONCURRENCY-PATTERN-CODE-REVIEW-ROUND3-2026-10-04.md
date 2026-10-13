---
doc: DOM002_CONCURRENCY_PATTERN_CODE_REVIEW_ROUND3
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
reviewer: veyro-code-reviewer (fresh context, independent — never saw this codebase or any prior conversation about it before this task)
review_round: 3
responds_to: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND2-2026-10-04.md
remediation_under_review: knowledge/03-Modules/MOD-001/evidence/implementation/DOM002-ROUND2-REMEDIATION-2026-10-04.md
date: 2026-10-04
verdict: PASS (P0=0, P1=0, P2=2, P3=4) — R2-2/R2-3/R2-5 CONFIRMED FIXED and R2-4's deferral upheld by this reviewer's own execution; R2-1 is PARTIALLY FIXED (the leak it named is closed, but the fix introduces a demonstrated over-reap and its regression lock leaves BUG-051's volume half unlocked); SCN-MOD001-009 explicitly NOT promoted
scope: backend/tests/harness/concurrency.py + backend/tests/integration/test_concurrency_harness.py + backend/tests/integration/test_concurrency_harness_order_independence.py + the durable-record edits to REQUIREMENTS.md / SCENARIOS.md / STATUS.md / TEST_RESULTS.md ONLY
---

# Independent code review round 3 — GOV-01-R02 DOM-002 concurrency/versioning test pattern (round-2 remediation re-review)

## 0. Bounded scope, and what this review does NOT cover

Reviewed **only** the three files below, at the exact content hashes recorded here
(`shasum -a 256`, captured by me at review start and re-confirmed byte-identical at review
end):

| Artifact | git state | sha256 | Lines |
|---|---|---|---|
| `backend/tests/harness/concurrency.py` | untracked (`??`) | `154bf88f11da8ff92a635741b5256599307aaac546294b2b332cc6ee2cbb6759` | 266 |
| `backend/tests/integration/test_concurrency_harness.py` | untracked (`??`) | `2828f34b7af3548f841c47071294b8a01c9de885dd5f6a59363a74168be5f49d` | 195 |
| `backend/tests/integration/test_concurrency_harness_order_independence.py` | untracked (`??`) | `9a1956ee5d78b9a728a8a8fcc49664e384d23558fcb3ed2f77b3a84167e7f72a` | 139 |

Plus the durable-record edits the round-2 remediation claims it made to
`knowledge/03-Modules/MOD-001/REQUIREMENTS.md`, `SCENARIOS.md`, `STATUS.md`,
`TEST_RESULTS.md`, and `DOM002-ROUND1-REMEDIATION-2026-10-04.md`.

Deliberately **not** reviewed, re-adjudicated, promoted, or claimed about: ADR-010 Amendment
A2 / GOV-01-R04, `SCN-MOD001-067`, `BUG-048`, `BUG-050`, `BUG-051` themselves, CAP-008's own
qualification evidence (only its *current registry status* was re-verified), or any file
belonging to any module other than MOD-001's DOM-002 slice. Where findings reference
`postgres.py`, `conftest.py`, `tenant_isolation.py`, `authn.py`, `migration_safety.py`,
`test_architecture_gate_rls.py` or `tools/validate_architecture_gates.py`, that is solely to
characterise behaviour **caused by the three files under review** — no judgment is offered on
those files themselves.

**No file in the repository was edited by this review other than this report.** No
`git add`/`commit`/`push`/`reset`/`stash`/`checkout -- <file>`/`clean` was run. No scenario was
promoted. No fix was implemented. Every mutant, counterfactual and destructive drill ran in a
throwaway `/tmp/veyro_r3` copy (deleted at the end) or as a purely in-memory monkeypatch in a
throwaway Python process — never against the real repo's tracked or untracked state.

Every claim in the round-2 report, the round-2 remediation record, `STATUS.md`,
`TEST_RESULTS.md` and `CURRENT_STATE.md` was treated as an **unverified hypothesis to
re-derive**. Every command below was run by me this session; every output block is actual
captured output, not a paraphrase of round 1's or round 2's record.

## 1. Reviewer runtime model identity (self-observation — explicitly NOT evidence on its own)

Stated from inside my own context: I am running as **Opus 5, exact model ID
`claude-opus-5`**. `knowledge/05-QA/tools/mr_verify.py:106-108` sets
`EXPECTED_TIER_BY_AGENT["veyro-code-reviewer"] = "opus"` (verified by direct read this
session), so this self-observation is consistent with the expected tier for this role.

**This self-observation is not evidence.** A model cannot attest its own identity — that is
precisely the failure mode `MODEL_ROUTING.md`'s no-silent-downgrade rule and `mr_verify.py`
exist to close. I did not run `mr_verify.py` against myself and make no attestation claim.

**Transcript path for the orchestrator's independent `mr_verify.py` run.** My strongest
candidate, derived from the session id visible in my own tool-result spill path
(`…/fc3fa64f-3226-4db9-b8c5-597ba03d68f7/tool-results/`) and the only subagent transcript
actively growing under that session:

```
/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc3fa64f-3226-4db9-b8c5-597ba03d68f7/subagents/agent-aeec218ea8828024b.jsonl
```

Parsed metadata from that file's first rows: `sessionId = fc3fa64f-3226-4db9-b8c5-597ba03d68f7`,
`agentId = aeec218ea8828024b`. **The orchestrating session must confirm this is my transcript
and run `mr_verify.py <path> opus veyro-code-reviewer` against the real `.jsonl`, not against
this report's prose**, and record the result here and in `CURRENT_STATE.md`. If it does not
return PASS for tier `opus`, this round's verdict is `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` per
`DEVELOPMENT_CONSTITUTION.md` line 21, regardless of its technical content.

## 2. Live repository and environment state at review time

```
$ git rev-parse HEAD
3c55a88a7eb34bda08984a704f9a44ac1f437c55

$ git status --porcelain | wc -l
     266
```

HEAD matches the dispatch note's `3c55a88a7eb34bda08984a704f9a44ac1f437c55` exactly.
Porcelain count observed by me was **266**, not the 265 the dispatch note stated; I did not
reconcile that single-entry difference beyond confirming it was stable, and I treat my own
start-of-review snapshot as the baseline. All three reviewed files are **untracked** (`??`),
consistent with the remediation's "no commit/push" claim.

At review end, re-checked:

```
$ git rev-parse HEAD
3c55a88a7eb34bda08984a704f9a44ac1f437c55
$ git status --porcelain | wc -l
     266
$ diff <(git status --porcelain) /tmp/r3_baseline_porcelain.txt
  -> WORKING TREE IDENTICAL TO BASELINE
```

Byte-identical porcelain output, start to finish. Nothing staged, committed, stashed, reset,
or discarded. The three reviewed files' sha256 values are unchanged from §0.

**Docker baseline, captured before I did anything at all** (this matters: one stale harness
container pre-existed my session and must not be attributed to these files or to me):

```
$ docker ps -a --format '{{.ID}}|{{.Names}}|{{.CreatedAt}}|{{.Status}}'
49aaace83b82|veyro-mod001-harness-7196bf51|2026-10-04 05:00:35 +0300|Up 3 hours
db38a5fff8eb|frosty_bhabha|2026-10-01 15:16:46 +0300|Up 2 days

$ docker volume ls -q
712bec68008ece99c2974826cc2f384d370b4c6bfa6054854ee98cf2ec361acf   (anonymous, attached to 7196bf51)
tradingview-mcp-session                                            (named, unrelated)
```

`veyro-mod001-harness-7196bf51` is the same pre-existing leaked container rounds 1 and 2 both
recorded. I left it alone throughout, and every drill below confirms the code under review
also leaves it alone. **Final state, re-verified at review end: the same 2 containers and the
same 2 volumes, byte-identical to the baseline lists.** Every container and volume my own
drills created was removed by me by exact name/ID (`docker rm -f -v <exact-name>`); I never
ran `docker prune`, never `-a`, never a blanket removal.

Environment: Colima engine live, `docker context show` → `colima`. venv `backend/.venv`,
Python 3.14.5, pytest 9.1.1, no `pytest-xdist` or other parallel-execution plugin installed
(`pip list | grep -iE 'xdist|parallel|forked'` → no match) and no `addopts` in
`pyproject.toml` — a fact that bounds finding **R3-1**'s reachability and that I checked
specifically rather than assuming.

**CAP-008 status re-verified directly, not assumed.** Round 2 asserted `APPROVED`; I re-read
`knowledge/00-System/CAPABILITY_REGISTRY.md:25` and split the row on `|`. Column 7
(`review_status`) reads verbatim: "**APPROVED (2026-10-04, third independent fresh-context
Opus capability-security review, P0=0/P1=0/P2=0-blocking)**", evidenced by
`CAP008-POST-R16-INDEPENDENT-ASSURANCE-2026-10-04.md` (agentId `aa793a97c80f82668`,
`mr_verify.py` PASS 70/70 `claude-opus-5`), `approved_by` = `veyro-security-reviewer` (Opus),
expiry 2026-12-31. The registry front matter's `current_as_of` still narrates round 16's
"KEEP QUALIFIED" position; that is the *historical* entry, superseded by the row's own
`review_status` field. CAP-008 is therefore **APPROVED and registered** today.

The three reviewed files introduce **no new capability**: psycopg, the existing `conftest.py`
session fixtures, `subprocess`/`sys`/`pathlib`, and — new this round — `DockerRoute` /
`trusted_docker` imported from `tests/harness/postgres.py`, i.e. the project's own already-
registered CAP-008 route rather than bare `docker` on `PATH`. I verified by direct read that
`_harness_containers` and the cleanup `rm` both go through that route
(`test_concurrency_harness_order_independence.py:50`, `:65-73`, `:87`, `:102`). **No
unregistered or unqualified capability use found.** Findings R3-1 through R3-4 are defects in
*how* the approved capability's lifecycle is managed on a new code path, not unregistered-
capability findings.

**Owner-reserved restrictions** (`.claude/rules/global/owner-reserved-restrictions.md`): no
spend (all tooling local/free), no real member data (synthetic `uuid4()` ids and
`"writer-a"`/`"writer-b"`/`"initial"` literals only), no Production deploy, no material
product/pricing/business/architecture/scope change. **No owner-reserved-restriction violation
found, and nothing in this slice would require one.**

**`.claude/rules/infra/secrets.md`**: I grepped all three files for
`password|secret|token|api_key|apikey|BEGIN .* PRIVATE KEY|postgres://|postgresql://`. The
single hit is a *comment* at `test_concurrency_harness_order_independence.py:61` quoting
`postgres.py`'s container-name construction `f"veyro-mod001-harness-{secrets.token_hex(4)}"` —
a naming scheme, not a credential. No credential-shaped literal, no connection string with
embedded credentials, no `.env` reference. **No secrets-rule violation.**

## 3. Governing sources read directly this session

| Source | What I verified in it |
|---|---|
| `.claude/rules/backend/concurrency.md` | the 5 DOM-002 controls + the fail-closed rule, verbatim (lines 29-77) |
| `.claude/rules/global/owner-reserved-restrictions.md` | the 4 absolute restrictions |
| `.claude/rules/infra/secrets.md` | the 3 required controls + fail-closed rule |
| `.claude/rules/backend/database.md`, `architecture.md`, `api.md`, `performance.md`, `infra/release.md` | adjacent-profile controls, checked for cross-rule conflict; none found — this slice adds no route handler, no domain sub-package, no tenant table, no migration, no log statement |
| `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md` | lines 18-25: Opus-only code review, fresh context, no self-approval (**DC-06**), no silent downgrade; DC-10 evidence-over-assertion; DC-16 owner-reserved |
| `knowledge/00-System/CAPABILITY_REGISTRY.md:25` | CAP-008 `review_status: APPROVED` (full column-by-column split, §2) |
| `knowledge/00-System/REVIEW_IN_FLIGHT.md` | `current_claim: IN_FLIGHT — MOD-001 DOM-002 concurrency pattern independent code review **round 3**`, watchdog `66643874-e295-4d53-a846-ee79cb6c3a44`, dispatched 2026-10-04T04:30:12Z — **matches this exact dispatch.** Left untouched by me |
| `knowledge/05-QA/tools/mr_verify.py:106-108` | `EXPECTED_TIER_BY_AGENT["veyro-code-reviewer"] = "opus"` |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md:589-590` | DOM-001 row → "§24.1 gate 2"; DOM-002 row → "GOV-01-R02; CONC category" + the durable reject-and-retry decision |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md:418-470` | `SCN-MOD001-009` header, still `NOT EXECUTED`, with the explicit "NOT promoted and NOT [claimed PASS]" text at line 442 |
| `knowledge/03-Modules/MOD-001/STATUS.md` lines 4-6, `TEST_RESULTS.md` line 5 | the implementer's own claims (treated as claims; verified in §4/§5) |
| `backend/tests/integration/conftest.py:33-42` | `pg` and `admin` are both `scope="session"` over `disposable_postgres()` — the factual basis for judging **R2-3** |
| `backend/tests/harness/postgres.py` (full) | `SUPERUSER = "postgres"`; `disposable_postgres`'s container naming, `--rm` + `finally`-block `docker rm -f -v`, and its own documented best-effort-swallow disposition at `:203-207` |

## 4. Tests, drills and probes actually run (exact commands, actual captured output)

All commands run from `/Users/ahmadmabrouk/Desktop/Veyro/backend` unless noted.

### 4.1 Static checks — PASS

```
$ .venv/bin/ruff check tests/harness/concurrency.py tests/integration/test_concurrency_harness.py tests/integration/test_concurrency_harness_order_independence.py
All checks passed!                                              exit=0

$ .venv/bin/ruff check .
All checks passed!                                              exit=0

$ .venv/bin/mypy --strict tests/harness/concurrency.py tests/integration/test_concurrency_harness.py tests/integration/test_concurrency_harness_order_independence.py
Success: no issues found in 3 source files                       exit=0

$ .venv/bin/mypy tests/ --strict
Success: no issues found in 28 source files                      exit=0
```

### 4.2 Focused suite — PASS 4/4, Docker state unchanged

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
test_single_writer_succeeds_and_increments_version                      PASSED [ 25%]
test_concurrent_writers_lost_update_detected                            PASSED [ 50%]
test_update_versioned_distinguishes_missing_row_from_version_conflict   PASSED [ 75%]
test_naive_unversioned_update_loses_the_update                          PASSED [100%]
4 passed in 1.69s

containers after: veyro-mod001-harness-7196bf51 (pre-existing only)   volumes: 2
```

### 4.3 Order-independence file including the new R2-1 regression test — PASS 3/3

```
$ BEFORE: veyro-mod001-harness-7196bf51 | vols=2
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -v
test_concurrency_before_canonical_rls_harness_test_review_4_4           PASSED [ 33%]
test_concurrency_between_two_rls_gate_invocations_review_4_5            PASSED [ 66%]
test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1   PASSED [100%]
3 passed in 6.14s
$ AFTER:  veyro-mod001-harness-7196bf51 | vols=2
```

The file now takes a `timeout` parameter (`_run_pytest(*args, timeout: float = 180)`,
`:76`) exactly as the remediation claims. Container and volume counts are unchanged across the
run, and the pre-existing stale container is untouched.

### 4.4 R2-1 drill 1 — is the forced-timeout path real, and is the cleanup actually running? (5 consecutive runs, observed via `docker events`)

Round 2's methodology was a before/after `docker ps` diff. I went one level deeper and watched
the engine's own event stream, so I could see whether a container was genuinely created and
who destroyed it — a `ps` diff alone cannot distinguish "created then reaped" from "never
created."

```
$ docker events --filter type=container --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' &
$ .venv/bin/python -m pytest "…::test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1" -q

RUN 1  1 passed in 1.59s
    1791088487 create  veyro-mod001-harness-7da6eea8
    1791088487 start   veyro-mod001-harness-7da6eea8
    1791088488 kill    veyro-mod001-harness-7da6eea8
    1791088488 die     veyro-mod001-harness-7da6eea8
    1791088488 destroy veyro-mod001-harness-7da6eea8
  containers now: veyro-mod001-harness-7196bf51   vols=2
RUN 2  (…-fb3c0cc8)  create/start/kill/die/destroy   containers now: 7196bf51 only   vols=2
RUN 3  (…-ddccfe01)  create/start/kill/die/destroy   containers now: 7196bf51 only   vols=2
RUN 4  (…-1bffc032)  create/start/kill/die/destroy   containers now: 7196bf51 only   vols=2
RUN 5  (…-1556dc9f)  create/start/kill/die/destroy   containers now: 7196bf51 only   vols=2
```

**R2-1's named leak is genuinely closed on this machine, 5/5.** A real container is created by
the SIGKILLed child every time, and the parent's `finally` reaps it (`kill`/`die`/`destroy`
within ~1 s). Volume count returns to 2 every time. This is the strongest form of the claim
round 2 asked a round-3 reviewer to re-derive, and it holds.

### 4.5 R2-1 drill 2 — timing margins behind the hand-picked `timeout=1.2` (basis for finding R3-3)

The remediation justifies `timeout=1.2` only as "matching the review's own §4.10 empirically-
validated value," i.e. one observation on one machine. I measured both margins myself.

**Lower bound — how long until the child creates its container:**

```
$ (Popen the exact nested command; poll docker ps until a new harness container appears)
time-to-container-create = 0.358s  (budget 1.2s)
time-to-container-create = 0.350s  (budget 1.2s)
time-to-container-create = 0.365s  (budget 1.2s)
```

**Upper bound — how long the child takes to finish normally:**

```
$ /usr/bin/time -p .venv/bin/python -m pytest -q tests/integration/test_concurrency_harness.py
real 1.85 / real 1.72 / real 1.84 / real 1.74 / real 1.86
```

So the valid window for the timeout value is roughly **[0.36 s, 1.72 s]**. At `1.2`, the
headroom to a *false failure* (child finishes before the timeout → `pytest.raises(
TimeoutExpired)` reports DID NOT RAISE) is only ~0.5 s, about **1.45×** — and the child's
duration is quantised by `_wait_ready`'s `time.sleep(0.5)` retry loop (`postgres.py:221`), so
a host on which Postgres answers the *first* connect attempt would land under 1.2 s.

**Vacuity demonstration (the more serious direction).** In the throwaway copy I lowered the
timeout below the container-create time and re-ran the same test:

```
timeout=0.15 -> 1 passed in 0.44s   harness container events during the drill: (NONE)
timeout=0.05 -> 1 passed in 0.36s   harness container events during the drill: (NONE)
```

**The test passes while no container is ever created.** Its only assertion is
`after == before`, which is trivially satisfied when there was nothing to clean up — it has no
positive assertion that the forced timeout actually produced a container to reap. A cold image
pull or a contended Colima VM pushes the child past 1.2 s before `docker run`, and the R2-1
regression lock silently evaporates with no signal. → **R3-3**.

### 4.6 R2-1 drill 3 — does the name-filter / before-after diff really identify only this invocation's own containers? (basis for finding R3-1)

Two independent problems, both demonstrated.

**(a) The Docker `name=` filter is an unanchored substring match, not a prefix match.**

```
$ docker create --name "unrelated-veyro-mod001-harness-xyz" postgres@sha256:721873c3… true
$ docker ps -a --filter name=veyro-mod001-harness- --format '{{.Names}}'
unrelated-veyro-mod001-harness-xyz          <-- matched, despite not being the harness prefix
veyro-mod001-harness-7196bf51
$ docker rm -f -v unrelated-veyro-mod001-harness-xyz     (exact name only; decoy removed by me)
```

The constant is named `_HARNESS_CONTAINER_PREFIX` and the code comment says it "Must match
`disposable_postgres`'s own naming scheme exactly," but the filter never anchors it. The
comprehension at `:73` (`{n for n in names.splitlines() if n}`) does not re-check
`startswith` either.

**(b) The diff is scoped by *time window*, not by *provenance*.** I started an unrelated
container with a matching name from a concurrent thread, timed to land inside the
`subprocess.run` window, then let `_run_pytest` run to its forced timeout:

```
$ .venv/bin/python /tmp/r3_d3_overreap.py        (throwaway script, in-memory import)
decoy present before drill: ''
[decoy] created veyro-mod001-harness-decoy01 (unrelated actor, NOT created by _run_pytest's child)
[drill] TimeoutExpired fired as expected
decoy present AFTER drill: ''
RESULT: OVER-REAPED (unrelated container destroyed)
```

**And it is not limited to the timeout path.** The `finally` runs on *every* invocation, so I
repeated the drill on the normal success path (`timeout` left at its 180 s default, child exits
0):

```
$ .venv/bin/python /tmp/r3_d6_success_overreap.py
[decoy] created veyro-mod001-harness-decoy02
child returncode: 0 (0 == normal success, no timeout)
decoy AFTER: ''
RESULT: OVER-REAPED ON THE SUCCESS PATH
```

So the over-reap window opens three times per run of this file, on every ordinary suite
execution — not only in the rare timeout case. → **R3-1**.

**The under-reap / pre-existing direction is safe, and I verified it rather than assuming it:**
`veyro-mod001-harness-7196bf51` was present in `before` on every single drill above and
survived all of them untouched.

### 4.7 R2-1 drill 4 — mutation test on the cleanup itself: is the *volume* half regression-locked? (basis for finding R3-2)

BUG-051's documented incident was 473 orphaned anonymous **volumes** / 18.94 GB, and the new
test is named `test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1`. I
mutated only the `-v` flag out of the cleanup call in the throwaway copy:

```
M8: docker("rm", "-f", "-v", name)  ->  docker("rm", "-f", name)

$ BEFORE vols=2 containers=veyro-mod001-harness-7196bf51
$ .venv/bin/python -m pytest "…::test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1" -q
1 passed in 1.68s
$ AFTER  vols=3 containers=veyro-mod001-harness-7196bf51
$ docker volume ls -q
712bec68008ece…   (pre-existing)
adce02b6cd07a4…   (LEAKED by the mutant)
tradingview-mcp-session
```

**M8 SURVIVED.** The test passed while leaking an anonymous volume. It asserts on the container
set only; the volume half of BUG-051's mechanism — the half that actually caused the incident —
is not regression-locked at all. → **R3-2**.

The leaked volume was then removed by me by exact name after confirming by `docker volume
inspect` that it was not the pre-existing one (`created=2026-10-04T07:37:24+03:00` vs the
pre-existing `712bec68…`'s `05:00:35`):

```
$ docker volume rm adce02b6cd07a4fb659e2758a28a548a524ee765a9255ce98ac5b071d21cae59
$ diff <(docker volume ls -q|sort) <(sort /tmp/r3_baseline_volumes.txt)
  -> VOLUMES MATCH BASELINE EXACTLY
```

### 4.8 R2-1 drill 5 — is a cleanup failure reported, or silently swallowed? (basis for finding R3-4)

**(i) A failing `docker rm` is swallowed entirely.** In-memory monkeypatch of the module's
`trusted_docker` to a route that raises on `rm`:

```
$ .venv/bin/python /tmp/r3_d4_cleanupfail.py
before: {'veyro-mod001-harness-7196bf51'}
exception surfaced to caller: TimeoutExpired
message mentions a leak/cleanup problem?: False
after: {'veyro-mod001-harness-ee1a5cdc', 'veyro-mod001-harness-7196bf51'}
RESULT: SILENTLY LEAKED {'veyro-mod001-harness-ee1a5cdc'} with no signal
```

Container **and** its anonymous volume (`c2b10ec22afb…`, read via `docker inspect`) leaked; the
only exception the caller ever sees is the `TimeoutExpired`, with nothing mentioning the
cleanup failure. In the R2-1 regression test the trailing `assert after == before` would catch
this loudly, but the two *production-path* tests (`…review_4_4`, `…review_4_5`) carry no such
post-condition, so there a cleanup failure is completely silent — BUG-051's mechanism
re-reachable through the fix's own `except RuntimeError: pass` (`:103-104`).

**(ii) The `finally`'s own `docker ps` call is NOT guarded, and masks the real exception.**
Only the `rm` sits inside `try/except RuntimeError`; the `leaked = _harness_containers(docker)
- before` line at `:99` does not:

```
$ .venv/bin/python /tmp/r3_d5_mask.py
exception surfaced: RuntimeError | `docker ps` exit 1: simulated engine hiccup during cleanup
RESULT: REAL TimeoutExpired MASKED by cleanup-path failure
=== docker state === veyro-mod001-harness-4040a71b | Up 1 second    vols=3
```

This is precisely what the function's own docstring says the design avoids — "a cleanup failure
here is swallowed rather than masking the real subprocess outcome/exception" (`:84-86`) — and it
leaks a container as well. Cleaned up by me by exact name:
`docker rm -f -v veyro-mod001-harness-4040a71b`, volumes back to 2. → **R3-4**.

### 4.9 R2-2 verification — same-session setup-failure drill, plus the counterfactual that proves my probe works

The remediation's own record flagged that an earlier two-session attempt at this check was
methodologically unsound. I used a single pytest session throughout: injected failure in the
`widget` fixture between `insert` and `yield`, and a probe module collected *after* the
concurrency module in the **same** session, sharing the same disposable container.

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py tests/integration/test_zzz_r3_leak_probe.py -q -s
RuntimeError: R3-DRILL injected setup failure between create and yield   (x3, as designed)
R3-LEAK-PROBE []
2 passed, 3 errors in 1.59s
```

**Zero leftover relation** despite three fixture setup failures — the `try`/`finally` ran.

**Counterfactual, to prove my probe is not vacuous** (reverted the R2-2 fix to a bare
post-`yield` drop, same injected failure, same single session):

```
R3-LEAK-PROBE [('concurrency_harness.versioned_widget',)]
AssertionError: LEAKED: [('concurrency_harness.versioned_widget',)]
1 failed, 1 passed, 3 errors in 1.66s
```

My probe detects the leak when the fix is absent and reports clean when it is present.
**R2-2 is genuinely fixed.** I also confirmed by direct read that the fix's placement is
correct: `create_versioned_table` sits *outside* the `try` (`:74-80`), which is right — if the
`CREATE TABLE` itself raises, no table exists to drop, and the only statements that can raise
after a successful create (`uuid4()`, `insert`) are inside the guarded block.

File restored to pristine in the throwaway copy afterwards (`shasum` back to
`2828f34b…49bd`).

### 4.10 R2-3 verification — docstring vs actual fixture scoping

`concurrency.py:183-193` now reads, verbatim: "Does not drop the schema — `SCHEMA` is reused
across tests *within* a session and owns nothing else worth tearing down. (Round-2 review
R2-3: this previously also said "across sessions", which is false — `conftest.py`'s `pg`
fixture is session-scoped over `disposable_postgres()`, which gives every pytest session a
fresh container and therefore a fresh, empty database; no schema survives a session boundary
regardless of what this function does.)"

I verified the factual basis independently rather than taking the docstring's word:
`conftest.py:33-36` is `@pytest.fixture(scope="session") def pg()` wrapping
`disposable_postgres()`, and `postgres.py:169` generates a fresh
`veyro-mod001-harness-{secrets.token_hex(4)}` container name per invocation with
`finally`-block `docker rm -f -v`. The corrected docstring matches actual behaviour.
**R2-3 is fixed.**

### 4.11 R2-5 verification — my own `grep` of `STATUS.md`

Round 2's finding was that the round-1 remediation record *claimed* a simulated/sequential
qualifier in `STATUS.md` that did not exist. I re-grepped the live file myself:

```
$ grep -n -i -E "simulated|sequential|Known ceiling|racing writers" knowledge/03-Modules/MOD-001/STATUS.md
4: … **R2-5** (… verified false by the reviewer's own `grep`) — fixed by actually adding that
   qualifying sentence to the entry's active text …
5: … The "racing writers" language throughout this round means the harness's own documented
   simulated, sequential shape (two deterministic writers over one connection, never two
   genuinely concurrent transactions) — see the harness module's own "Known ceiling" section —
   never real parallel load. …
6: … exactly one of two racing writers succeeds …        (round-18 historical entry, unqualified)
```

**The qualifying sentence genuinely exists now** (line 5, the `prior_updated_round18remediation1`
entry), immediately adjacent to the "racing writers" phrasing it qualifies. The still-unqualified
occurrence is only in the older `prior_updated_round18` historical entry, which is defensible
under this project's append-don't-rewrite convention. The active entry (line 4) describes the
fix accurately and honestly notes "the sentence itself remains live in this file" even though
chronological supersession has since demoted its host entry. **R2-5 is fixed, and the record's
claim is now true.** No new record-accuracy defect here.

### 4.12 R2-4 re-assessment — live confirmation of the exception shape

```
R3-PROBE-C RNF<:VC? False  VC<:RNF? False  | bases RNF= (<class 'Exception'>,) VC= (<class 'Exception'>,)
```

Still two sibling classes off `Exception` with no shared base — the finding's factual premise
holds. I also re-verified there is still no external consumer: repo-wide

```
$ grep -rn "VersionConflict\|RowNotFound\|update_versioned\|update_unversioned_blind" . \
    --exclude-dir=.venv --exclude-dir=__pycache__ | grep -v tests/harness/concurrency.py | grep -v test_concurrency_harness
  (no output)
```

**Zero callers outside the slice**, so the deferral's first premise ("no current caller needs
it") is independently true. See §7 for my disposition.

### 4.13 Mutation sensitivity — round 2's §4.8 set re-run against the current code, 6/6 killed

Run in the throwaway copy (baseline there: `4 passed`); every mutant reverted to a byte-identical
pristine source afterwards (`shasum` confirmed back to `154bf88f…6759`); copy deleted.

| Mutant | Change | Summary | Result |
|---|---|---|---|
| **M1** | `update_versioned` loses its `AND version = %s` predicate | `1 failed, 3 passed` — `Failed: DID NOT RAISE VersionConflict` | **KILLED** |
| **M2** | zero rowcount returns 0 silently instead of raising | `2 failed, 2 passed` — `DID NOT RAISE VersionConflict` **and** `DID NOT RAISE RowNotFound` | **KILLED** |
| **M5** | version checked in `WHERE` but never incremented in `SET` | `3 failed, 1 passed` — `assert 1 == (1 + 1)`, `DID NOT RAISE VersionConflict` | **KILLED** |
| **M6** | existence check removed, so every zero rowcount raises `VersionConflict` | `1 failed, 3 passed` — `VersionConflict … surfaces inside pytest.raises(RowNotFound)` | **KILLED** |
| **M4a** | the deliberately-broken `update_unversioned_blind` "repaired" into refusing to write | `1 failed, 3 passed` — `assert 0 == 1` | **KILLED** |
| **M7** | broken fixture keeps no version predicate but **does** bump the version | `1 failed, 3 passed` — `assert 4 == (1 + 1)` | **KILLED** |

### 4.14 P1-2-ONLY mutant against the order-independence file — still independently regression-locked

Round 2 asked specifically that this be re-run, because it is the drill proving the *teardown*
half of the P1 fix is locked independently of the schema half. I neutralised only
`drop_versioned_table`'s body, retaining the `concurrency_harness` schema fix:

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -q
E   RLS_TABLE_UNCLASSIFIED: concurrency_harness.versioned_widget — no tenant_id column and not a manifest platform table
E   ADR010-P1-EVIDENCE {"gate": "rls", "status": "FAIL", "violations": [{"code": "RLS_TABLE_UNCLASSIFIED",
      "subject": "concurrency_harness.versioned_widget"}]}
FAILED …::test_concurrency_before_canonical_rls_harness_test_review_4_4
FAILED …::test_concurrency_between_two_rls_gate_invocations_review_4_5
2 failed, 1 passed in 6.68s
```

Both drill tests die with the exact round-1 P1-2 signature; the R2-1 timeout test correctly
passes (it is independent of teardown). Container/volume counts unchanged through the mutant
run, incidentally confirming the new cleanup also behaves on a child that *fails* rather than
times out.

### 4.15 Independent live catalog + typed-error probe (re-deriving P1-1 and P2-1 from the database, not from the code)

Probe module collected **after** the concurrency module, with the RLS gate's canonical harness
test also in the session so both schemas exist:

```
R3-SCHEMA-OWNERS [('concurrency_harness', 'postgres'), ('harness', 'veyro_schema_owner'),
                  ('harness_auth', 'veyro_schema_owner'), ('public', 'pg_database_owner')]
R3-RELATIONS     [('harness', 'access_grant', 'r'), ('harness_auth', 'audit_event', 'r'),
                  ('harness_auth', 'identity', 'r'), ('harness_auth', 'session', 'r')]
R3-WIDGETISH     []
R3-PROBE-A missing-row   -> RowNotFound    | no row at concurrency_harness.versioned_widget: id=e5a72e99-…
R3-PROBE-B stale-version -> VersionConflict| version conflict on concurrency_harness.versioned_widget: id=d17be0bb-… expected_version=1
R3-PROBE-D conn usable, version now = 2
R3-PROBE-E backend_pid/autocommit: (59,) True
R3-PROBE-F columns: [('id','uuid','NO',None), ('version','integer','NO','1'), ('value','text','NO',None)]
6 passed in 1.87s
```

Independently confirms, from the catalog rather than from a constant: `concurrency_harness` is
owned by `postgres` while `harness` keeps `veyro_schema_owner` **with the concurrency module
running first** (P1-1's exact former failure condition); **zero** surviving `widget`-shaped
relation; the version column really is `integer NOT NULL DEFAULT 1`; the two typed errors are
genuinely raised for their two genuinely different causes; and the connection is still usable
afterwards, so the extra existence check leaves no aborted-transaction residue. `backend_pid`
is a single value with `autocommit=True`, independently confirming the harness's own disclosed
"Known ceiling" (simulated/sequential over one connection) is an accurate self-description.

### 4.16 No duplicate writer / no competing schema owner — my own repo-wide greps

```
$ grep -rn "concurrency_harness" . --exclude-dir=.venv --exclude-dir=.git --exclude-dir=__pycache__ \
    | grep -v "^./backend/tests/harness/concurrency.py" | grep -v "test_concurrency_harness"
  -> only prose in REQUIREMENTS.md:590, SCENARIOS.md:462, and the round-1/2 evidence records

$ grep -rn "CREATE SCHEMA" backend tools --exclude-dir=.venv
  backend/tests/integration/test_architecture_gate_rls.py:379:  "CREATE SCHEMA gate_other" …
  backend/tests/harness/authn.py:47:                            CREATE SCHEMA harness_auth AUTHORIZATION …
  backend/tests/harness/concurrency.py:171:                     CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}
  backend/tests/harness/migration_safety.py:194:                CREATE SCHEMA IF NOT EXISTS {table.schema}
  backend/tests/harness/tenant_isolation.py:119:                CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION …

$ grep -rn "GRANT.*ON SCHEMA" backend tools --exclude-dir=.venv
  -> all hits name `harness`, `harness_auth`, or a gate fixture schema; none name concurrency_harness

$ grep -rln "versioned_widget\|VERSIONED_WIDGET" backend tools --exclude-dir=.venv
  backend/tests/integration/test_concurrency_harness.py
  backend/tests/harness/concurrency.py
```

**Exactly one code path creates or owns `concurrency_harness`** (`concurrency.py:171`), and
nothing anywhere else creates it, grants on it, or references it or its table. No race, no
duplicate ownership. The `AUTHORIZATION` clause is therefore decisive on the only path that
can win the create, which is what makes the P1-1 fix sound rather than merely renamed.

### 4.17 Full-suite regression, both collection orders — 203/203 and 203/203

```
$ .venv/bin/python -m pytest tests -q
203 passed in 31.98s
   containers after: veyro-mod001-harness-7196bf51 only   vols=2

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q
203 passed in 33.29s
   containers after: veyro-mod001-harness-7196bf51 only   vols=2
```

Observed by me, identical counts in both orders. Arithmetic reconciles against round 2's
independently-observed 202: 202 + 1 new R2-1 regression test = **203**, matching the
remediation record's and `TEST_RESULTS.md`'s claim. Notably, a full suite run leaves the
container and volume counts exactly as it found them — including the three nested subprocess
sessions.

### 4.18 Governing baselines

```
$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
  [MATCH] Gym_OS_Master_Product_Blueprint_v1_English.docx: 80f4b381…426ef
  [MATCH] Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx: 0d41c8a1…158e8
  [MATCH] Veyro_Engineering_Implementation_Plan_v1.4.1…docx: e5b5ec3b…866b6
  [MATCH] veyro-product-experience-design: c96f77ab…6dbb
PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.      exit=0
```

No governing baseline was modified, renamed, or regenerated by this round. **No drift from the
governing baselines found in the reviewed slice.**

## 5. Control-by-control assessment against `.claude/rules/backend/concurrency.md`

Re-derived end to end from the current code and my own live probes, not from round 2's table.

| Control | Verdict | My evidence |
|---|---|---|
| **1** — every mutable aggregate's table carries an explicit version column | **SATISFIED** | `concurrency.py:175-180` creates `id uuid PRIMARY KEY, version integer NOT NULL DEFAULT 1, {columns}` — literally the rule's own example form. Confirmed at the catalog level, not just in source: §4.15 `R3-PROBE-F` → `('version','integer','NO','1')` |
| **2** — every mutation reads, checks and increments the version in **one atomic statement** | **SATISFIED** | `concurrency.py:241-244` is a single `UPDATE … SET version = version + 1, {assignments} WHERE id = %s AND version = %s`. Parameter order `[*params, row_id, expected_version]` matches placeholder order because `assignments` is interpolated ahead of the `WHERE`. `_row_exists` runs **only** on `rowcount == 0`, i.e. only when no mutation occurred, so it never splits the mutation. M1 (predicate removed) and M5 (increment removed) both **KILLED** (§4.13), proving each half load-bearing |
| **3** — a version mismatch is a typed, distinguishable conflict, never silently overwritten/swallowed/retried | **SATISFIED** | `VersionConflict` (`:124-137`) and `RowNotFound` (`:140-149`) raised at `:245-248`. My live probe raises the two different types for the two different causes and confirms neither is a subclass of the other (§4.12/§4.15). Repo-wide grep finds **no** `except` anywhere that catches either type, and **no caller outside the slice at all** (§4.12), so nothing swallows or auto-retries them. M2 and M6 both **KILLED** |
| **4** — lost-update behavior is an explicit documented decision | **SATISFIED** | reject-and-retry, stated at `concurrency.py:26-37` and recorded durably/non-chronologically in `REQUIREMENTS.md:590`'s own DOM-002 traceability row (read directly), correctly scoped to this fixture and naming `concurrency_harness.versioned_widget` consistently with the code |
| **5** — append-only exemption | **N/A** | the fixture aggregate is mutable by design; no gap |
| **Fail-closed rule** — a deliberately-broken version-check fixture must be shown to fail closed, not silently pass | **SATISFIED** | `update_unversioned_blind` (`:252-260`) + test 4, in the genuinely identical two-writer shape (both writers read the same version, equality asserted at `:172`, writer A goes through the real `update_versioned`). Proven non-vacuous by **M4a** (test 4 dies the moment the broken fixture stops being broken) and **M7** (the version/value-mismatch assertion is the only one that catches a blind write that also increments) |

**All 5 controls plus the fail-closed rule are satisfied. No concurrency-rule violation.** Every
finding below is about the *test harness's own container/volume hygiene and record accuracy* —
none of them weakens the DOM-002 proof itself.

## 6. Round-2 disposition audit (my own determination, not the remediation record's table)

| Round-2 finding | My verdict | Basis (my own execution/reading) |
|---|---|---|
| **R2-1** (P2) subprocess-timeout container/volume leak | **PARTIALLY FIXED** | The named leak is genuinely closed: §4.4's 5/5 `docker events` runs show a real container created by the SIGKILLed child and reaped by the parent's `finally` every time, with volume count returning to baseline. But the fix introduces a **demonstrated over-reap** of unrelated concurrently-created containers on *every* invocation, not only on timeout (§4.6, → **R3-1**), its regression lock leaves BUG-051's **volume** half completely unlocked (§4.7 M8 SURVIVED, → **R3-2**), the chosen `timeout=1.2` is vacuity-prone and undocumented (§4.5, → **R3-3**), and the cleanup path both swallows `rm` failures with zero signal and lets an unguarded `ps` failure mask the real exception (§4.8, → **R3-4**) |
| **R2-2** (P3) `widget` fixture teardown not `try`/`finally`-guarded | **CONFIRMED FIXED** | §4.9 — same-session injected-failure drill shows `R3-LEAK-PROBE []`; the counterfactual with the fix reverted shows `LEAKED: [('concurrency_harness.versioned_widget',)]`, proving my probe non-vacuous. Fix placement independently checked as correct (create outside the `try`) |
| **R2-3** (P3) docstring falsely claimed the schema is reused "across sessions" | **CONFIRMED FIXED** | §4.10 — `concurrency.py:183-193` now says "within a session" with the reason stated; I verified the underlying fact myself from `conftest.py:33-36` (`scope="session"` over `disposable_postgres()`) rather than trusting the docstring |
| **R2-4** (P3) `VersionConflict`/`RowNotFound` share no base class — **deferred** | **DEFERRAL UPHELD** (see §7) | §4.12 — premise confirmed (both direct `Exception` subclasses, neither a subclass of the other) and the deferral's own first reason independently verified (zero callers outside the slice, repo-wide). One residual gap in the deferral's stated mitigation → **R3-5** |
| **R2-5** (P3) `STATUS.md` did not contain the simulated/sequential qualifier the round-1 record claimed | **CONFIRMED FIXED** | §4.11 — my own `grep` finds the qualifying sentence genuinely present at `STATUS.md:5`, adjacent to the "racing writers" phrasing. The record's claim is now true, and the still-unqualified occurrence is confined to the older historical entry |
| **P3-6 disposition correction** (requested by round 2, not a numbered finding) | **CONFIRMED DONE** | `DOM002-ROUND1-REMEDIATION-2026-10-04.md` carries a dated addendum rather than a silent edit, consistent with the project's append-don't-rewrite convention; `TEST_RESULTS.md:5` also records it |

**Summary: 3/4 remaining P3s CONFIRMED FIXED (R2-2, R2-3, R2-5), R2-4's deferral upheld, and
the single P2 (R2-1) PARTIALLY FIXED** — its named leak closed, but with four newly-demonstrated
residual defects on the same code path.

## 7. R2-4 deferral — my own disposition

**The deferral remains reasonable and I do not reverse it**, on grounds I verified rather than
accepted:

1. The factual premise holds (§4.12): the two classes are correctly *distinguished*, which is
   what rule control 3 actually requires. Nothing in `concurrency.md` requires a shared base.
2. "No current caller needs it" is independently true — my repo-wide grep found **zero**
   consumers of either exception outside the three reviewed files.
3. Adding a shared base later is strictly additive and backward-compatible, so waiting creates
   no migration cost. Inventing a `ConcurrencyError` now, before any of DOM-002's five
   co-owning modules exists to validate the shape, risks carrying an unused abstraction.

One thing is **not** right, though, and I record it as **R3-5**: the deferral's own stated
mitigation is that "a future adopter of this plug-in template should re-read `concurrency.py`'s
own 'Plug-in point' docstring section and R2-4's text in the round-2 report." I read that
docstring section (`concurrency.py:65-77`) in full. It tells adopters to "reuse
`VersionConflict`/`RowNotFound` (or your own typed equivalents) as the API boundary errors"
and says nothing about the absent shared base, R2-4, or the deferral. An adopter reading only
the code — the likeliest path — would never discover the deferral exists.

## 8. `SCN-MOD001-009` and ADR-010 — explicitly not touched

I verified by direct read that `SCENARIOS.md:418` still carries `… · Automated ·
veyro-implementer/Sonnet · **NOT EXECUTED**` and that line 442 states "**This scenario
(SCN-MOD001-009) is NOT promoted and NOT [claimed PASS]**". Nothing in the three reviewed
files, in the round-2 remediation, or in `STATUS.md`/`TEST_RESULTS.md` promotes it; the
remediation record's §8 explicitly disclaims promotion, and I confirmed that disclaimer is
accurate against the live files.

**`SCN-MOD001-009` is NOT promoted by this review, and nothing this review endorses promotes
it.** Three independent reasons: promotion is categorically a Scenario Review / Gatekeeper act
under DC-06/DC-07, not a code-review act; the scenario's own header still names an
`GOV-01-R04 / TSD §24.1 gate 2` prerequisite whose label question belongs to a future Scenario
Review round; and findings **R3-1** and **R3-2** are open P2s on one of the three files.

I did **not** adjudicate, decide, or touch **ADR-010 Amendment A2 or GOV-01-R04**, and I
express no opinion on the round-1/round-2 analysis of the `SCN-MOD001-009` header label beyond
noting that `REQUIREMENTS.md:590`'s DOM-002 row reads "GOV-01-R02; CONC category" while line
589's DOM-001 row is the one reading "§24.1 gate 2" — a reading I took from the primary file,
offered as observation only, not as a disposition.

I did **not** alter `knowledge/00-System/REVIEW_IN_FLIGHT.md`. Its `current_claim` still reads
`IN_FLIGHT` for this exact round-3 dispatch; clearing it is the orchestrator's job.

## 9. Findings

### R3-1 (P2) — the R2-1 cleanup identifies containers by *time window* and by an *unanchored substring* filter, not by provenance, so it force-removes (`rm -f -v`) an unrelated concurrent actor's container — on every invocation, not just on timeout

`backend/tests/integration/test_concurrency_harness_order_independence.py:65-73`, `:87-104`

```python
def _harness_containers(docker: DockerRoute) -> set[str]:
    """Every currently-running-or-stopped container whose name matches this
    project's disposable-Postgres naming scheme — never a broader query, so
    diffing two calls can only ever identify containers this harness itself
    could have created, never an unrelated container."""
    names = docker("ps", "-a", "--filter", f"name={_HARNESS_CONTAINER_PREFIX}", "--format", "{{.Names}}")
    return {n for n in names.splitlines() if n}
```

Two independent defects, both demonstrated live in §4.6:

**(a) The filter is not prefix-anchored.** Docker's `--filter name=` is a substring/regex
match. I created `unrelated-veyro-mod001-harness-xyz` and `docker ps -a --filter
name=veyro-mod001-harness-` listed it. The constant is called `_HARNESS_CONTAINER_PREFIX` and
its comment says it "Must match `disposable_postgres`'s own naming scheme exactly," but
neither the filter nor the set comprehension at `:73` ever anchors it with `startswith`.

**(b) The diff is time-scoped, not provenance-scoped.** `after - before` cannot distinguish
"created by my child" from "created by *anyone* during my window." Demonstrated: a decoy
container created from a concurrent thread inside the `subprocess.run` window was destroyed by
`_run_pytest`'s cleanup, both on the timeout path (`RESULT: OVER-REAPED`) and — because the
`finally` runs unconditionally — on the **normal success path** with `returncode 0`
(`RESULT: OVER-REAPED ON THE SUCCESS PATH`).

Three docstrings and two durable records assert the opposite, and all five are false as
written: `_harness_containers`'s "never an unrelated container"; `_run_pytest`'s "exactly
whichever … container(s) **this specific call created** … scoped by construction to this
call"; the module docstring's "force-removes *only* … containers this specific invocation
created … never anything matching a different name"; the remediation record §1's "This never
touches a pre-existing or unrelated container"; and `TEST_RESULTS.md:5`'s "removing only this
invocation's own leak." The *pre-existing* half of those claims is true and I verified it
(`veyro-mod001-harness-7196bf51` survived every drill untouched); the *unrelated-concurrent*
half is not.

**Consequence:** a `docker rm -f -v` against another process's live Postgres container and its
anonymous data volume — a destructive cross-session action, not a leak. The victim session
fails with confusing connection errors far from the cause.

**Reachability, stated honestly.** It requires a second actor creating a matching-named
container inside a ~2-6 s window, three windows per run of this file. `pytest-xdist` is not
installed and there is no `addopts` parallelism, so intra-suite self-collision is **not**
reachable today (I checked). The realistic trigger is two pytest sessions on the same machine —
which this project's own `REVIEW_IN_FLIGHT.md` documents as a real, already-experienced
occurrence (round 11's two concurrent orchestrating sessions), and which its agent/watchdog
operating model makes recurrent.

**Why P2 and not P1:** it needs a concurrent actor, it only ever destroys synthetic test
containers (no real member data — owner-reserved restriction 2 is not engaged), and it does not
weaken any DOM-002 control. I record that P1 is arguable on consequence grounds, and that the
reachability is materially *higher* than round 2 assessed for R2-1 itself (every run, not a
90× overrun). A prefix-anchored check plus provenance scoping (e.g. having the parent pass the
child a pre-agreed container-name token, as round 2's own third remediation option suggested)
would close both halves; the fix chosen was the first option, which is the one that cannot
distinguish provenance.

### R3-2 (P2) — the new R2-1 regression test does not check volumes at all, leaving BUG-051's actual incident mechanism unlocked; the `-v` mutant SURVIVES

`backend/tests/integration/test_concurrency_harness_order_independence.py:124-139`

The test is named `test_subprocess_timeout_does_not_leak_container_or_volume_review_r2_1` and
its docstring says the safety net "leaves no `veyro-mod001-harness-*` container behind." Its
only assertion is `assert after == before` over **container names**. No volume is ever
enumerated or asserted.

Demonstrated by mutation (§4.7): dropping `-v` from `docker("rm", "-f", "-v", name)` leaves the
test **passing** (`1 passed in 1.68s`) while the volume count goes `2 -> 3` and a real orphaned
anonymous volume (`adce02b6cd07a4…`) is left on the VM disk. **M8 SURVIVED.**

This matters more than a naming nit because the volume half *is* BUG-051. That bug's recorded
incident was 473 orphaned anonymous volumes / 18.94 GB filling the Colima VM to 100% — not
orphaned containers — and `postgres.py:188-207`'s own comment is explicit that plain `rm -f`
"removed the container but left its anonymous volume behind — one ~40MB leak per fixture-using
session, unconditionally." The one new regression test added to guard against reintroducing
that mechanism does not guard the half that caused it, and the test's own name states that it
does. Two lines (snapshot `docker volume ls -q` alongside the container set and assert both)
would close it.

### R3-3 (P3) — `timeout=1.2` is a hand-picked, undocumented value and the test silently becomes vacuous if the child is slower than it, with no positive assertion that anything was ever created

`backend/tests/integration/test_concurrency_harness_order_independence.py:135`

Measured on this machine (§4.5): the child creates its container at **~0.36 s** and finishes
normally at **1.72-1.86 s**, so `1.2` sits inside a valid window of roughly `[0.36 s, 1.72 s]`
with only ~1.45× headroom to a false failure. Lowering the timeout below the create time makes
the test pass while nothing is created:

```
timeout=0.15 -> 1 passed in 0.44s   harness container events: (NONE)
timeout=0.05 -> 1 passed in 0.36s   harness container events: (NONE)
```

Because the assertion is only `after == before`, there is no way for the test to tell "the
cleanup worked" from "there was nothing to clean up." A cold image pull, a contended Colima VM,
or a loaded CI host pushes the child past 1.2 s before `docker run` and the R2-1 regression
lock silently evaporates — a **false pass**, with no signal. In the other direction (a host
where Postgres answers `_wait_ready`'s first connect attempt, skipping its `time.sleep(0.5)`)
the test **false-fails** with `DID NOT RAISE`. The file records no derivation, no margin, and
no guidance; the remediation record justifies the number only as "matching the review's own
§4.10 empirically-validated value," i.e. copied from a single observation on a single machine —
which is exactly the concern. Capturing `_run_pytest`'s own `leaked` set and asserting it was
non-empty would make the test self-validating and timeout-insensitive.

### R3-4 (P3) — the cleanup path swallows an `rm` failure with zero signal, and its *unguarded* `ps` call masks the real exception — the opposite of what its own docstring claims

`backend/tests/integration/test_concurrency_harness_order_independence.py:98-104`

```python
        finally:
            leaked = _harness_containers(docker) - before      # <-- NOT guarded
            for name in leaked:
                try:
                    docker("rm", "-f", "-v", name)
                except RuntimeError:
                    pass                                       # <-- swallowed, no signal
```

**(i) Swallowed `rm` failure.** Demonstrated (§4.8): with the `rm` forced to fail, the container
`veyro-mod001-harness-ee1a5cdc` **and** its anonymous volume `c2b10ec22afb…` leaked while the
only exception reaching the caller was the `TimeoutExpired`, with nothing mentioning cleanup.
The R2-1 regression test's trailing assert would catch this, but the two production-path tests
(`…review_4_4`, `…review_4_5`) have no post-condition, so there it is entirely silent — BUG-051's
mechanism re-reachable through the fix's own exception handler. Mitigating and stated fairly:
the docstring *discloses* this as a deliberate best-effort choice mirroring
`postgres.py:203-207`'s own precedent, so it is a disclosed design decision rather than a hidden
defect — which is why this is P3. A `warnings.warn` on a swallowed cleanup failure would give
the missing signal at near-zero cost.

**(ii) Unguarded `ps` masks the real exception.** Only the `rm` is inside the `try`. Demonstrated
(§4.8): with `_harness_containers` failing on the post-call snapshot, the real
`subprocess.TimeoutExpired` is **replaced** by a `RuntimeError` from the cleanup path — precisely
what the same docstring says the design avoids ("swallowed rather than masking the real
subprocess outcome/exception") — and the container leaks as well. Wrapping the snapshot line in
the same guard would make the stated contract true.

### R3-5 (P3) — R2-4's deferral is sound but its stated mitigation does not exist in the place it points to

`backend/tests/harness/concurrency.py:65-77`, vs `DOM002-ROUND2-REMEDIATION-2026-10-04.md:182-185`

The remediation's recorded disposition tells "a future adopter of this plug-in template" to
"re-read `concurrency.py`'s own 'Plug-in point' docstring section and R2-4's text in the
round-2 report." I read that section in full: it instructs adopters to "reuse
`VersionConflict`/`RowNotFound` (or your own typed equivalents) as the API boundary errors"
and contains no mention of the absent shared base, of R2-4, or of the deferral. An adopter
reading the code — the likeliest path for one of DOM-002's five co-owning modules — gets no
pointer. Every other round-1/round-2 disposition in this slice *is* discoverable from the code
(the docstrings carry explicit "round-1 code-review P1-1 fix", "P2-1 fix", "round-2 review
R2-2 fix", "R2-3" markers); this one alone is not. One sentence in the Plug-in point section
would make the deferral discoverable where it matters.

### R3-6 (P3) — documentation accuracy nits in the order-independence module docstring

`backend/tests/integration/test_concurrency_harness_order_independence.py:28-31`

> "That is BUG-051's exact disk-exhaustion mechanism (473 orphaned anonymous volumes /
> 18.94 GB, Colima VM disk to 100%, reachable again on this newly-added code path.
> `_run_pytest` now brackets …"

The parenthesis opened at `(473` is never closed and the sentence runs on into the next. Purely
cosmetic, but these docstrings are treated as evidence artifacts in this project and are quoted
into durable records, which is the only reason it is recorded at all. (The substantive false
claims in the same docstring are covered by **R3-1**, not here.)

### Durable-record edits — otherwise verified accurate

Everything else I checked in the durable records reproduces:

- **`REQUIREMENTS.md:590`** — DOM-002 row ties to "GOV-01-R02; CONC category" and carries the
  reject-and-retry decision durably and non-chronologically, correctly scoped, naming
  `concurrency_harness.versioned_widget` consistently with the code. ✓
- **`SCENARIOS.md:418-470`** — `SCN-MOD001-009` still `NOT EXECUTED`, explicitly not promoted
  and not claimed PASS; the round-18 disclosure and the round-1/remediation paragraph are
  appended, not overwritten. ✓
- **`STATUS.md:4-6`** — the R2-5 qualifier genuinely present (§4.11); the R2-1/R2-2/R2-3/R2-4
  dispositions described match what I found in the code, **except** the "removing only this
  invocation's own leak" characterisation (→ R3-1). ✓ with one exception
- **`TEST_RESULTS.md:5`** — "203/203 passing in both default and reversed collection order
  (202 prior + 1 new R2-1 regression test)", "`ruff check .`/`mypy` clean across 28 files",
  "`verify_baselines.py` PASS, 4/4": **every one independently reproduced by me** (§4.1, §4.17,
  §4.18). Same single exception as above. ✓
- **`DOM002-ROUND1-REMEDIATION-2026-10-04.md`** — P3-6 disposition corrected by dated addendum
  rather than silent edit. ✓
- **`REVIEW_IN_FLIGHT.md`** — `IN_FLIGHT` for this exact round-3 dispatch; left untouched. ✓
- **CAP-008** — `review_status: APPROVED`, re-verified by direct column read (§2). ✓

No governing baseline modified. No unregistered/unqualified capability use. No
owner-reserved-restriction violation. No drift from the governing baselines in the reviewed
slice.

## 10. Verdict

**Demonstrated result — the round-2 remediation is largely genuine, and the DOM-002 proof
itself is sound and materially well-locked.** Re-executed by me: 4/4 focused tests; 3/3
order-independence tests; **203/203 full suite in both collection orders** with identical
counts; `ruff check .` and `mypy --strict` clean (3 files and 28 files); `verify_baselines.py`
PASS 4/4; **6/6 of round 2's mutants killed**; the **P1-2-only mutant still kills both
order-independence drills**, confirming the teardown half of the P1 fix remains independently
regression-locked; schema ownership and the absence of any surviving `widget`-shaped relation
verified from the **catalog**, not from a constant; the two typed errors proven genuinely
distinct by my own live probe; R2-2 proven fixed by a same-session drill plus the counterfactual
that validates the drill itself; R2-3 and R2-5 verified by direct read and `grep`; and R2-1's
named leak confirmed closed 5/5 by `docker events` rather than by a `ps` diff alone.

**R2-2, R2-3 and R2-5 are CONFIRMED FIXED by my own execution. R2-4's deferral is upheld.
R2-1 is PARTIALLY FIXED** — the leak it named is genuinely gone, but the fix chosen introduces
an over-reap that destroys an unrelated concurrent actor's container on every invocation
(**R3-1**), its regression lock leaves BUG-051's own volume mechanism unguarded with a
surviving mutant (**R3-2**), the timeout value is vacuity-prone and undocumented (**R3-3**), and
the cleanup path both swallows failures silently and masks the real exception (**R3-4**).

**OVERALL: PASS — P0=0, P1=0, P2=2, P3=4.**

This follows this project's own established verdict convention (round 2: `PASS —
P0=0/P1=0/P2=1/P3=4`; round 16: `PASS — P0=0/P1=0/P2=3/P3=4`): P1=0 clears the blocking bar,
while the two P2s and four P3s are real defects that require remediation and are **not** waived
by this verdict. **R3-1 and R3-2 should both be fixed before this suite runs in any unattended
or CI context**, because R3-1 performs a destructive cross-session action on every run and
R3-2 leaves the specific mechanism of a documented prior incident (BUG-051) unguarded by the
very test added to guard it. Per `DEVELOPMENT_CONSTITUTION.md`'s zero-known-defects rule, the
two P2s block module certification until remediated, independently of this PASS.

**PASS here means: these three files, as written, satisfy all five `concurrency.md` controls
and the fail-closed rule, introduce no unregistered or unqualified capability use, violate no
owner-reserved restriction, and show no drift from the governing baselines — with two P2s and
four P3s to remediate.** It is not a certification, not a Gatekeeper approval, and not a
scenario promotion.

**`SCN-MOD001-009` is NOT promoted by this review.** See §8. No scenario, requirement, bug, or
capability status is advanced by this report. ADR-010 A2 / GOV-01-R04 were not adjudicated.

## 11. Next action

1. **Orchestrating session — model assurance, do this first.** Run
   `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <path-to-my-real-transcript>.jsonl
   opus veyro-code-reviewer` against my **actual transcript file**, not against this report's
   prose. My strongest candidate is
   `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc3fa64f-3226-4db9-b8c5-597ba03d68f7/subagents/agent-aeec218ea8828024b.jsonl`
   (§1) — **confirm it independently.** Record the result in §1 and in `CURRENT_STATE.md`. If it
   does not return PASS for tier `opus`, this round's verdict is
   `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` per `DEVELOPMENT_CONSTITUTION.md` line 21, regardless
   of technical content.
2. **Orchestrating session — clear the `REVIEW_IN_FLIGHT.md` claim only after the result is
   recorded**, per that file's own protocol ("Clear on result recorded, not merely on subagent
   completion"). I did not touch that file.
3. **Implementation session (Sonnet appropriate — harness hygiene and record accuracy, not an
   ADR-005 Decision 1 slice):**
   - **R3-1 first.** Scope the cleanup by *provenance*, not by a time window — e.g. have the
     parent generate a per-invocation container-name token and pass it to the child (round 2's
     own third remediation option), so the parent removes only names carrying its own token.
     Separately, anchor the name check (`--filter "name=^veyro-mod001-harness-"` or a
     `startswith` on the returned names). Then correct the three docstrings and the two durable
     records (`DOM002-ROUND2-REMEDIATION-2026-10-04.md` §1, `TEST_RESULTS.md:5`) that currently
     assert provenance scoping the code does not have.
   - **R3-2.** Snapshot `docker volume ls -q` alongside the container set in the regression test
     and assert both, so the test's name becomes true and the `-v` flag becomes load-bearing.
     Re-run the **M8** mutant from §4.7 to confirm it is then killed.
   - **R3-3.** Make the regression test self-validating: have `_run_pytest` expose the `leaked`
     set it computed and assert it was non-empty, so the test fails loudly instead of passing
     vacuously when the child never got far enough to create a container. Document the timeout
     value's derivation and the measured `[~0.36 s, ~1.72 s]` window in a comment.
   - **R3-4.** Wrap the `finally`'s own `_harness_containers` call in the same guard so a
     cleanup-path failure cannot mask the real exception, and emit a `warnings.warn` on a
     swallowed `rm` failure so the silent-leak path has a signal.
   - **R3-5.** Add one sentence to `concurrency.py`'s "Plug-in point" section recording that
     `VersionConflict`/`RowNotFound` deliberately share no base class and pointing at R2-4's
     deferral. **R3-6.** Close the parenthesis.
4. **Do not promote `SCN-MOD001-009`** on this round's evidence.
5. **Future Scenario Review round** owns `SCN-MOD001-009`'s header-label question. Not an
   implementation-session or code-review action.
6. **Round-4 re-review, if dispatched.** Every drill in §4 is reproducible as written. The
   decisive ones are: §4.4 (`docker events` rather than a `ps` diff, so "created then reaped" is
   distinguishable from "never created"); §4.6's two over-reap drills, including the
   **success-path** variant, which is the one that establishes reachability; §4.7's **M8**
   mutant, which is the single sharpest test of whether R3-2 was actually fixed; §4.5's timeout-
   margin measurement and the `timeout=0.15`/`0.05` vacuity demonstration; and §4.8's two
   cleanup-failure drills. Re-run §4.13's mutation set against any changed `update_versioned`
   and §4.14's P1-2-only mutant against any changed teardown. Capture the Docker container and
   volume baseline **before doing anything**, because a stale `veyro-mod001-harness-*` container
   pre-exists on this machine and must not be attributed to these files; clean up only what the
   drill itself creates, by exact name, never `prune` and never `-a`.

## Orchestrator attestation addendum — 2026-10-04 05:04 UTC

The watchdog independently verified this reviewer's actual transcript at `.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc3fa64f-3226-4db9-b8c5-597ba03d68f7/subagents/agent-aeec218ea8828024b.jsonl` using `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-code-reviewer`: PASS, 130 turns, 100% `claude-opus-5`. This attests model tier only; the P2/P3 findings remain open for implementation and independent re-review.
