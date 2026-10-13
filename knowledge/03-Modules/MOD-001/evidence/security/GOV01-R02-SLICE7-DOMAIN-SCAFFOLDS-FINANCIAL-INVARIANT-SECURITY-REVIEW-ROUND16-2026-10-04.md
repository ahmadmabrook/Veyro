---
review: GOV-01 R02 Slice 7 — domain scaffolds / financial-invariant security review
round: 16
segment: 3 of 3
module: MOD-001
bug: BUG-050
date: 2026-10-04
reviewer: veyro-security-reviewer (independent, no memory of prior rounds)
model: claude-opus-5
status: COMPLETE — PASS P0=0/P1=0/P2=3/P3=4. All three segments complete. Segment 1: hash verification, nine round-15 mutant reconstructions (all confirmed closed) with three counterfactual controls, R14-1 regression, real suite/lint/type runs. Segment 2: Docker-volume/VM-disk finding (R16-1, P2, filed separately as BUG-051), execution-witness closure judgment (not required), 6-token derivation query (47 files, reconciled), R15-5/R12-4 CAP-008 scope-minimality disposition. Segment 3 (final): independent verification of BUG-051's fix by execution, the live CAP-008/Postgres drills for SCN-MOD001-132 and SCN-MOD001-133 (previously blocked by the full VM disk, precondition now cleared), a fresh independent Opus capability-security re-review of CAP-008, full aggregate state, and the final verdict. **VERDICT: PASS, P0=0/P1=0/P2=3/P3=4** (see §19). SCN-MOD001-133 acceptance criteria MET and promotable; SCN-MOD001-132 acceptance criteria MET on live evidence but promotion gated administratively via CAP-008's non-APPROVED status (R16-3 + R16-5, both documentation-only, no new drill required). BUG-050 CAN CLOSE — all four of round 15's conditions plus segment 2's disclosure precondition are satisfied. BUG-051 CAN CLOSE conditional on the R16-3 wording correction. CAP-008: KEEP QUALIFIED, APPROVED withheld pending the two conditions in §18.4. No scenario promoted, no bug closed, no registry/REVIEW_IN_FLIGHT edit, no commit or push by this reviewer.
---

# Round 16 — Segment 1 (mutant re-verification + regression + real suite runs)

## Scope of this segment

Bounded, deliberately partial. Segment 1 covers only:

1. Hash verification of the three in-scope files.
2. Independent reconstruction of the nine round-15 mutants (throwaway copies only) against the current fixed code.
3. Regression check of the four original R14-1 shapes plus the disclosed `G1c` no-decoy gap.
4. Real execution of the Slice-7 test pair, the full backend suite, the full backend suite including the six domain scaffolds, and the lint/format/type gates.

Explicitly **deferred to segments 2-3** and NOT attempted here: execution-witness judgment,
6-token derivation query, live CAP-008 / Postgres drill, R15-5 (CAP-008 scope-minimality)
disposition, and the final PASS/BLOCKED verdict. **This segment issues no verdict.**

No scenario promoted, no bug closed, no `REVIEW_IN_FLIGHT.md` edit, no commit, no push.

## 1. Hash verification

Run from `backend/`: `shasum -a 256 tests/contract/test_financial_invariant_scaffold.py tests/contract/test_domain_scaffold_inventory.py tests/contract/_execution_suppression_guard.py`

| File | Observed SHA-256 | Matches dispatch-expected? |
|---|---|---|
| `tests/contract/test_financial_invariant_scaffold.py` | `471910a18461d8b12f878daa2a8f26eee4742fd8e0dfde91c3db515bcdee4b32` | **Yes** |
| `tests/contract/test_domain_scaffold_inventory.py` | `b7cd06f1b0be7f14cd9d85002f3af717eef40b557755cc4570e94842b63861c3` | **Yes** |
| `tests/contract/_execution_suppression_guard.py` | `c55fa51485ca4d9b2e88b089c93824c73492afe038b3a53c23f616bdff7c44d4` | **Yes** |

All three match the dispatch's expected values exactly. Code is confirmed unchanged
since the round-15 remediation. For continuity: round 15's report recorded the
**pre**-remediation hashes `5565338125bc…` (financial-invariant) and `ef6d23fa49a7…`
(inventory); both differ from the values above, which is the expected consequence of
the round-15 remediation touching both files.

Disk check (a prior interrupted attempt chased a transient `No space left on device`):
`df -h /tmp` → **231Gi available**, 75% used. The condition does not reproduce.

## 2. Round-15 mutant reconstruction (nine mutants)

### 2.1 Method

Every mutant was rebuilt **from prose only** — round 15's report and BUG-050's
round-15 section — not from any diff or any copied script. Construction:
`rsync -a --exclude .venv --exclude __pycache__ --exclude '*cache'` of the real
`backend/` tree into `/tmp/r16seg1/base` (368K), with `.venv` **symlinked** to the
real one; each variant is an independent `copytree` of that base, mutated textually
by `/tmp/r16seg1/build.py`. Every textual substitution asserts an exact
occurrence count before applying, so a silently-missed mutation is impossible.
The real repository tree was never written to; `/tmp/r16seg1` is deleted at the
end of this segment.

Per-variant command (from the variant directory):

```
./.venv/bin/python -m pytest tests/contract/test_financial_invariant_scaffold.py -q -p no:cacheprovider
```

(`tests/contract/test_domain_scaffold_inventory.py` for `d3`/`d4`.)

Base mutant **T6** — `ctx.prec = 27` inserted immediately after
`ctx.traps[Inexact] = True` inside `assert_debits_equal_credits` — is present in
`s1`-`s5`, `p1`, `x2`, `G9b`-`G10d`, and `G1c`. `d3`/`d4` instead break the `access`
domain scaffold genuinely (`SELECT 1 ... == (1,)` changed to `== (2,)`), the same
domain round 15 used.

### 2.2 Controls

| Variant | Shape | Result | exit |
|---|---|---|---|
| `v00_base` | unmutated copy | **23 passed** in 0.02s | 0 |
| `v01_t6_only` | T6 alone, no suppression | **1 failed, 22 passed** | 1 |

`v01_t6_only` fails on the boundary test's anchored `match=`, with the exact
cross-route mislabel round 15 described — observed verbatim this session:

```
E       AssertionError: Regex pattern did not match.
E         Expected regex: '^DEBITS_NE_CREDITS'
E         Actual message: "DEBITS_CREDITS_UNEVALUABLE_PRECISION: leg amounts could not be
                           summed without rounding at the decimal context's 28-significant-digit
                           precision, so this invariant could not be evaluated"
```

So T6 is a genuine, detectable defect in every variant below — a mutant that
returns green is a real false clean, not a no-op.

### 2.3 All nine round-15 mutants — **CONFIRMED CLOSED**

Each now fails as a **collection error for the whole file** (pytest exit code **2**),
raised by the eager module-level `assert_execution_not_suppressed(...)` call before
any test runs. That is a stricter outcome than round 15's remediation strictly
needed (a failed test, exit 1) and is the louder signal the guard module's own
docstring claims for itself.

| Variant | Shape reconstructed | Round-15 result (false clean) | **Round-16 result on fixed code** | exit | Guard sub-assertion that fired |
|---|---|---|---|---|---|
| `s1` | T6 + `@pytest.mark.skip` on boundary test **and** on the guard test | `21 passed, 2 skipped`, exit 0 | **1 error (collection)** | **2** | suppressing marker, `_execution_suppression_guard.py:164` |
| `s2` | T6 + skip boundary + **vacuous redefinition** of the guard test | `22 passed, 1 skipped`, exit 0 | **1 error (collection)** | **2** | redefinition, line 147 |
| `s3` | T6 + skip boundary + **post-definition rebind** of the guard test | `22 passed, 1 skipped`, exit 0 | **1 error (collection)** | **2** | rebind, line 151 |
| `s4` | T6 + `from pytest import mark` + `@mark.skip(...)` on boundary test | `22 passed, 1 skipped`, exit 0 | **1 error (collection)** | **2** | suppressing marker, line 164 |
| `s5` | T6 + `import pytest as pt` + `@pt.mark.skip(...)` | `22 passed, 1 skipped`, exit 0 | **1 error (collection)** | **2** | suppressing marker, line 164 |
| `p1` | T6 + `pytestmark = [pytest.mark.skip(reason=...)]` (list form) | `23 skipped`, exit 0 | **1 error (collection)** | **2** | module-level `pytestmark`, line 126 |
| `x2` | T6 + `pytestmark = pytest.mark.skip(reason=...)` (single form) | `23 skipped`, exit 0 | **1 error (collection)** | **2** | module-level `pytestmark`, line 126 |
| `d3` | `access` broken + `@pytest.mark.skip` on **both** inventory guard functions | `2 skipped`, exit 0 | **1 error (collection)** | **2** | suppressing marker, line 164 |
| `d4` | `access` broken + **both** inventory guard names rebound to a no-op | `2 passed`, exit 0 | **1 error (collection)** | **2** | rebind, line 151 |

Exact assertion text observed this session (abridged to the `E` line):

```
s1:  E AssertionError: watched test(s) carry a suppressing marker in
       test_financial_invariant_scaffold.py:
       {'test_precision_boundary_within_context_still_compares_exactly': ['skip'],
        'test_critical_negative_tests_are_not_suppressed': ['skip']}
s2:  E AssertionError: watched test(s) redefined more than once in
       test_financial_invariant_scaffold.py:
       {'test_critical_negative_tests_are_not_suppressed': 2}
s3:  E AssertionError: watched test(s) rebound to another value after definition in
       test_financial_invariant_scaffold.py:
       ['test_critical_negative_tests_are_not_suppressed']
s4:  E AssertionError: watched test(s) carry a suppressing marker in
       test_financial_invariant_scaffold.py:
       {'test_precision_boundary_within_context_still_compares_exactly': ['skip']}
s5:  (identical text to s4)
p1:  E AssertionError: module-level `pytestmark` in test_financial_invariant_scaffold.py
       applies a suppressing marker to every test in the file: ['skip']
x2:  (identical text to p1)
d3:  E AssertionError: watched test(s) carry a suppressing marker in
       test_domain_scaffold_inventory.py:
       {'test_all_six_domain_scaffold_paths_exist': ['skip'],
        'test_all_six_domain_scaffolds_pass': ['skip']}
d4:  E AssertionError: watched test(s) rebound to another value after definition in
       test_domain_scaffold_inventory.py:
       ['test_all_six_domain_scaffold_paths_exist', 'test_all_six_domain_scaffolds_pass']
```

Note `s1` names **both** suppressed watched names in one message, and `d3`/`d4`
likewise name both inventory guards — the mechanism is whole-module, not
first-hit-and-stop.

### 2.4 Counterfactual controls — the guard is what closes them, not an artifact of reconstruction

A mutant that errors could in principle be erroring for an unrelated reason
introduced by this session's own reconstruction. Three counterfactual variants
(`s1n`, `d3n`, `d4n`) are byte-identical to `s1`/`d3`/`d4` except that the single
eager `assert_execution_not_suppressed(...)` call is commented out:

| Variant | Result with the eager guard call disabled | exit | Round-15's recorded number |
|---|---|---|---|
| `s1n` | **21 passed, 2 skipped** | **0** | `21 passed, 2 skipped`, exit 0 — **exact match** |
| `d3n` | **2 skipped** | **0** | `2 skipped`, exit 0 — **exact match** |
| `d4n` | **2 passed** | **0** | `2 passed`, exit 0 — **exact match** |

This reproduces round 15's three headline false cleans exactly, including `d4`'s
affirmative `2 passed` against a genuinely broken `access` scaffold — the output
round 15 called the most deceptive in the lineage. The only difference between the
green and the erroring run is the one guard call. **The remediation is therefore
load-bearing and is the sole cause of the kills in §2.3.**

### 2.5 Note on `d3`/`d4` and CAP-008

`d3`/`d4` are verified **without any Docker/Postgres involvement**: the guard fires
at import time, so collection aborts before `test_all_six_domain_scaffolds_pass`
can spawn its pytest subprocess. The counterfactuals `d3n`/`d4n` likewise never
reach Postgres (`d3n`'s guards are skipped; `d4n`'s are rebound to a no-op). This
is a real property of the remediation, not a workaround, and it is why the
deferred live CAP-008 drill was not needed for this part of the charge.

## 3. R14-1 regression shapes + disclosed `G1c` gap

### 3.1 The four original R14-1 shapes — still closed (no regression)

Guard test itself **untouched** in all four; only the boundary test
(`test_precision_boundary_within_context_still_compares_exactly`) is suppressed,
composed with T6.

| Variant | Shape | Result | exit | Guard sub-assertion |
|---|---|---|---|---|
| `G9b` | `@pytest.mark.skip(reason="flaky on CI, re-enable later")` | **1 error (collection)** | **2** | suppressing marker `['skip']`, line 164 |
| `G9c` | `@pytest.mark.xfail(reason="known issue")` | **1 error (collection)** | **2** | suppressing marker `['xfail']`, line 164 |
| `G10` | second, vacuous `def` of the boundary test appended | **1 error (collection)** | **2** | redefinition `{...: 2}`, line 147 |
| `G10d` | post-definition module-level rebind to a no-op callable | **1 error (collection)** | **2** | rebind, line 151 |

All four still fail. Round 14's fix is not regressed by round 15's refactor into
the shared module; the kill simply moved from a collected test's assertion
(exit 1) to an import-time collection error (exit 2).

### 3.2 The disclosed `G1c` no-decoy walker-blindness gap — still survives green

Reconstructed exactly as rounds 13-15 describe: T6 plus a **local** shadow
`_COMPARISON_MATCH = r"^DEBITS"` inserted inside
`test_precision_boundary_within_context_still_compares_exactly`, immediately before
its `pytest.raises(...)` call, **with no decoy call site anywhere** (a fifth
`match=` site would trip the `== 4` count backstop and kill the mutant).

| Variant | Result | exit |
|---|---|---|
| `G1c` | **23 passed** in 0.02s | **0** |

**Still green — unchanged and deliberately open.** This is the intended outcome:
`G1c` is a *walker-blindness* gap (the call site is visible and does run, but the
AST walker cannot resolve the local name binding), a different class from the
*execution-suppression* gaps the round-15 mechanism closes. Confirming it still
survives establishes that the round-15 remediation did **not** accidentally close
a deliberately-open, honestly-disclosed gap, and did not widen the guard's reach
beyond its stated scope. Nothing was silently closed; nothing was silently opened.

## 4. Real suite / gate execution

Repo HEAD at the start of this segment: `96f1707147f477a249193e1c076edb4e5ce5e3b6`.
All commands run from `/Users/ahmadmabrouk/Desktop/Veyro/backend` using
`./.venv/bin/...`.

### 4.1 Results

| # | Command | Exit | Result | vs round 15 |
|---|---|---|---|---|
| 1 | `./.venv/bin/python -m pytest tests/contract/test_financial_invariant_scaffold.py tests/contract/test_domain_scaffold_inventory.py -q` | **1** | **1 failed, 24 passed** in 61.14s | round 15: `25 passed`. **REGRESSED — environmental, see §4.2** |
| 2 | `./.venv/bin/python -m pytest -q` | **1** | **1 failed, 59 passed, 135 errors** in 191.33s | round 15: `195 passed`. **REGRESSED — same environmental cause** |
| 3 | `./.venv/bin/python -m pytest tests app/modules -q` | **1** | **1 failed, 59 passed, 141 errors** in 251.73s | round 15: `201 passed`. **REGRESSED — same environmental cause** |
| 4 | `./.venv/bin/ruff check .` | **0** | **All checks passed!** | matches round 15 |
| 5 | `./.venv/bin/ruff format --check .` | **1** | **7 files would be reformatted, 42 already formatted** | matches round 15's 7-file figure (42 vs 41 formatted: one net new file in the tree) |
| 6 | `./.venv/bin/mypy --strict app tests` | **0** | **Success: no issues found in 48 source files** | round 15 ran `mypy --strict .` → 47 files; this segment ran the dispatched `app tests` form → 48 |

The 7 `ruff format` files, listed by name this session, are all pre-existing
Slice-5/6 harness files and **none is Slice-7**, exactly as rounds 13-15 recorded:
`tests/harness/authn.py`, `tests/harness/migration_safety.py`,
`tests/harness/postgres.py`, `tests/harness/tenant_isolation.py`,
`tests/integration/test_architecture_gate_rls.py`,
`tests/integration/test_authn_harness.py`,
`tests/integration/test_migration_safety_harness.py`.

### 4.2 The three suite regressions share one environmental root cause — and it is real, not transient

**Every one of the 1 failure + 141 errors in run 3 is the same cause.** A grep over
the full-suite output returns 136 occurrences of `psycopg.OperationalError` and zero
other error classes:

```
psycopg.OperationalError: connection failed: connection to server at "127.0.0.1",
port 33737 failed: could not receive data from server: Connection refused
```

The disposable Postgres container starts and then dies before accepting connections.
Traced to ground this session rather than assumed:

```
colima status        -> colima is running, aarch64, runtime docker, mountType virtiofs
colima ssh -- df -h /var/lib/docker
                     -> /dev/vdb1  20G  19G  13M  100%  /var/lib/docker
docker system df     -> Local Volumes  473  ACTIVE 1  SIZE 18.94GB  RECLAIMABLE 18.94GB (100%)
docker ps -a         -> mikeh1975/tradingview-mcp:latest | Up 2 days | frosty_bhabha
```

Direct probe, which gives the definitive message:

```
docker run -d --name r16probe2 -e POSTGRES_PASSWORD=probe postgres:16-alpine
docker logs r16probe2
  -> 2026-10-04 00:19:53.342 UTC [33] FATAL:  could not write to file
     "pg_wal/xlogtemp.33": No space left on device
     child process exited with exit code 1
     initdb: removing contents of data directory "/var/lib/postgresql/data"
```

**`No space left on device` DOES currently reproduce.** The dispatch noted a prior
round-16 attempt chased this message and that it "does not currently reproduce"
because the host has 231 GiB free. That reasoning was measuring the wrong disk: the
host is fine, and the **Colima VM's own 20 GB `/var/lib/docker` is 100% full**. The
earlier smoke test passed only because
`test_financial_invariant_scaffold.py` needs no database at all.

**Cause: the CAP-008 Postgres fixture leaks one anonymous Docker volume per
container.** `tests/harness/postgres.py:173` runs
`docker run -d --rm --name <name> ... postgres`, and the official `postgres` image
declares `VOLUME /var/lib/postgresql/data`, so every container gets an anonymous
volume. The error-path teardown at line 189 is `docker("rm", "-f", name)` — **no
`-v`** — so on that path the volume survives the container. Verified by inspection:

```
docker volume inspect <any>  -> Labels: {"com.docker.volume.anonymous": ""}
                                Driver: local,  ~40MB each
colima ssh -- ls -l /var/lib/docker/volumes (by date)
  -> 1 x 2026-10-01   412 x 2026-10-03   61 x 2026-10-04
```

473 orphaned anonymous volumes, 18.94 GB, **100% reclaimable**, created in a burst
on 2026-10-03/04 — i.e. during this very review lineage's repeated suite runs.
The harness has been filling its own engine's disk round after round, and round 16
is the round it finally crossed 20 GB.

**This is a finding, and this segment deliberately does not rate it.** Three
properties make it more than housekeeping, and segments 2-3 should weigh them:

1. It is a **self-inflicted availability failure of a blocking test gate** — the
   exact condition `.claude/rules/backend/performance.md` control 3 forbids
   ("No gate is skippable under load... through a timeout, a resource-exhausted CI
   runner"). SCN-MOD001-132's live acceptance criteria cannot currently be
   re-verified in this environment at all.
2. It **contradicts CAP-008's registered scope text**, which describes the fixture
   as "a disposable Postgres container per pytest session, bound to `127.0.0.1`,
   `--rm`, force-removed on exit." The container is force-removed; its storage is
   not. The registered description overstates the cleanup actually performed.
3. The 473 volumes are **retained database state from every prior test session**.
   The content is synthetic fixtures only (no real member data — §5), so this is a
   hygiene and capability-scope issue rather than a data-exposure one, but the
   retention was neither intended nor disclosed.

**Crucially, the suite failures are fail-closed, not false cleans.** The inventory
check reported `domain scaffold inventory not clean (exit=4)` with all six domains
named as not-confirmed, and the suite exited non-zero. The harness never claimed a
domain passed when nothing proved it. That is the correct behaviour under
infrastructure failure and is itself a (negative-path) confirmation of
SCN-MOD001-132's fail-closed criterion.

**No remediation was attempted.** This reviewer did not run `docker volume prune`,
`docker system prune`, or any other cleanup: that would destroy owner-side
environment state and alter the very conditions a later segment needs to observe,
and it is outside a review-only dispatch. Recommended to the orchestrator, not
performed.

### 4.3 Side effects of this segment, disclosed

| Action | Effect | Disposition |
|---|---|---|
| `docker run --rm ... postgres:16-alpine` (probe `r16probe`) | The local image tag was dangling (`postgres:<none>`), so this re-pulled it. Pull digest: `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` — **exact match to CAP-008's registered pin**. Free registry pull, no spend. | Image tag restored from dangling to `postgres:16-alpine`; net improvement, disclosed rather than hidden |
| Probe containers `r16probe`, `r16probe2` | Both removed (`--rm` and `docker rm -fv` respectively) | No residue; `rm -fv` also removed `r16probe2`'s anonymous volume |
| `/tmp/r16seg1/` mutant tree (19 variants, `.venv` symlinked) | Outside the repository | Deleted at segment end |
| Repository tree | **Not written to.** No source file edited, no commit, no push, no scenario promoted, no bug closed, `REVIEW_IN_FLIGHT.md` untouched | — |

An incidental benefit of the digest match above: CAP-008's pinned image digest is
independently re-confirmed this segment **without** performing the deferred live
drill.

## 5. Observations carried forward to segments 2-3

Recorded as observations only. **This segment issues no severity ratings and no
verdict.**

1. **The round-15 remediation is correct for all nine shapes it claimed, verified by
   execution and by counterfactual** (§2.3, §2.4). The mechanism is stronger than
   round 15 strictly promised: it fails *collection* (exit 2) rather than a single
   test (exit 1), and it names every suppressed watched name in one message.
2. **No regression and no accidental closure** (§3). The four R14-1 shapes still
   fail; the deliberately-open, disclosed `G1c` walker-blindness gap still survives
   green at `23 passed`.
3. **NEW, needs a severity rating in segment 2:** the CAP-008 Postgres fixture leaks
   one anonymous Docker volume per container and has filled the Colima VM's 20 GB
   Docker disk with 473 orphaned volumes (18.94 GB, 100% reclaimable), making every
   Postgres-dependent test fail with `No space left on device` (§4.2). Candidate
   remediation is one character — `docker("rm", "-f", name)` →
   `docker("rm", "-f", "-v", name)` at `tests/harness/postgres.py:189` — plus a
   one-time `docker volume prune` the owner (not an agent) should authorize, plus a
   correction to CAP-008's registered scope text, which currently overstates cleanup.
4. **R15-5 / R12-4 is now in its seventh consecutive round.** The unregistered
   third-party container `mikeh1975/tradingview-mcp:latest` is still `Up 2 days` on
   CAP-008's engine, and its 418 MB image now shares a disk that has run out. Its
   disposition remains explicitly deferred to a later segment per the dispatch.
5. **Still open for segments 2-3**, untouched here: the execution-witness judgment
   (round 15 §12's `pytest_sessionfinish` proposal), the 6-token derivation query and
   its file-count reconciliation, the live CAP-008 / Postgres drill (currently
   **blocked** by item 3 — this should be read as a precondition, not a choice), the
   R15-5 disposition, and the final PASS/BLOCKED verdict.
6. **Standing charge, partial coverage only.** No real member data, credential, or
   spend was observed or introduced by anything this segment executed: the mutant
   tree used synthetic fixtures exclusively, the probe container used a throwaway
   password passed by environment variable, and the only network action was a free
   registry pull of an already-registered, digest-pinned image. A full
   supply-chain / scope-minimality assessment against `CAPABILITY_POLICY.md` is
   **deferred to segment 2** and must not be read as complete here.


## 6. Tree integrity at segment end

| Boundary | Observed |
|---|---|
| Three in-scope file hashes, segment start vs end | **Identical** (`471910a1…`, `b7cd06f1…`, `c55fa514…`) — no source file edited by this reviewer |
| `git rev-parse HEAD` at segment start | `96f1707147f477a249193e1c076edb4e5ce5e3b6` |
| `git rev-parse HEAD` at segment end | `b86446dcd283a5afeb86c612fb2657f769268748` — **changed during the segment, by the orchestrator, not by this reviewer.** `git show --stat` confirms it is `Checkpoint active bounded BUG-050 review segment`, a 4-line addition to `BUG050-ROUND16-WATCHDOG-CHECKPOINT-2026-10-04.md` only. No backend or Slice-7 file touched. Recorded rather than silently normalized. |
| Commit / push by this reviewer | **None** |
| Working tree additions by this reviewer | Exactly one untracked file: this report |
| `REVIEW_IN_FLIGHT.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`, `SCENARIOS.md`, `STATUS.md`, `BUG-050…md` | Read only where needed, **not modified** |
| Scenario promotion / BUG-050 closure | **None** — not this segment's authority, and no verdict is issued |
| Throwaway artifacts | `/tmp/r16seg1/` (19 variants) **deleted** at segment end |

## 7. Reviewer identification (for orchestrator-side `mr_verify.py`)

- **Resolved runtime model identity, as reported by this session's own environment:** `claude-opus-5` (named `Opus 5`).
- **No self-attestation performed.** Following rounds 13-15's convention, this reviewer did **not** run `mr_verify.py` against its own transcript; independent attestation with arguments `opus veyro-security-reviewer` is the orchestrating session's job.

---

# Round 16 — Segment 2 (volume-leak disposition, execution-witness judgment, derivation query, R15-5 disposition)

## Scope of this segment

Bounded, deliberately partial. Segment 2 covers exactly four items:

1. The Docker anonymous-volume leak / full Colima VM disk — independent verification, severity rating, prune-safety proof, proposed (not executed) remediation, and its confound status.
2. Judgment on whether the `pytest_sessionfinish` execution witness (round 15 §12) is *required* for BUG-050 closure.
3. The 6-token derivation query, re-run and reconciled against round 15's 45.
4. The R15-5 / R12-4 CAP-008 scope-minimality disposition, carried undisposed since round 10.

Explicitly **NOT** done here, and still owed by segment 3: the live CAP-008 / Postgres
drill and the final PASS/BLOCKED verdict. **This segment issues no verdict.** No
scenario promoted, no bug closed, no `REVIEW_IN_FLIGHT.md` edit, nothing under
`backend/` touched, no Docker volume pruned, no container stopped or removed, no
commit, no push.

## 8. Item 1 — Docker anonymous-volume leak and the full Colima VM disk

### 8.1 Independent verification of the orchestrator's figures

Re-run this session from scratch rather than inherited. Every orchestrator-supplied
number reproduces exactly:

| Measurement | Orchestrator's figure | This session's observation | Match |
|---|---|---|---|
| `colima ssh -- df -h /mnt/lima-colima` | `/dev/vdb1 20G 19G 13M 100%` | `/dev/vdb1  20G  19G  13M  100%  /mnt/lima-colima` | **Exact** |
| Same device via `/var/lib/docker` | (implied same fs) | `/dev/vdb1  20G  19G  13M  100%  /var/lib/docker` — confirms both paths are the *same* filesystem, not two | **Exact** |
| `docker system df` local volumes | 473 total, 1 active, 18.94GB, 100% reclaimable | `Local Volumes  473  1  18.94GB  18.94GB (100%)` | **Exact** |
| `docker volume ls -f dangling=true -q \| wc -l` | 472 | **472** (against `docker volume ls -q \| wc -l` = **473**) | **Exact** |
| `frosty_bhabha` volume | named `tradingview-mcp-session`, not anonymous, not among the 473 dangling | `type=volume name=tradingview-mcp-session src=/var/lib/docker/volumes/tradingview-mcp-session/_data dst=/data`; container `running`, image `mikeh1975/tradingview-mcp:latest`; `docker volume ls -f dangling=true -q \| grep -c tradingview` → **0** | **Exact** (one nuance below) |
| Sample anonymous volume labels | `{"com.docker.volume.anonymous": ""}` | `labels=map[com.docker.volume.anonymous:]` | **Exact** |

One **correction** to the orchestrator's phrasing, stated because precision matters
here: `tradingview-mcp-session` *is* one of the 473 (473 total volumes = 472 dangling
+ 1 in-use). It is correctly **not** among the **472 dangling** ones. The orchestrator's
intent was right; the arithmetic is cleaner stated this way, and the 473/472 difference
is exactly and only that one named, in-use volume.

Colima itself is up (`macOS Virtualization.Framework`, `aarch64`, runtime `docker`,
`mountType virtiofs`). Engine versions: client **29.8.1**, server **29.5.2**.

Segment 1's §4.2 independently established the same picture by a different route
(the `r16probe2` container's `FATAL: could not write to file "pg_wal/xlogtemp.33":
No space left on device`) and traced the mechanism to
`backend/tests/harness/postgres.py` — `docker run -d --rm` against an image declaring
`VOLUME /var/lib/postgresql/data`, with an error-path teardown of
`docker("rm", "-f", name)` carrying **no `-v`**. Two independent derivations, one
conclusion. This segment accepts that mechanism as established and does not re-derive it.

### 8.2 (a) Severity rating and where this finding belongs

**Rating: P2. Filed as its own bug, NOT as a BUG-050 finding. Non-blocking for
BUG-050's own closure criteria, but blocking for segment 3's live CAP-008 drill
until remediated.**

Designated **R16-1** for reference within this report, but the disposition is that it
should be filed as a **separate bug** (suggested `BUG-051`, number to be assigned by
the orchestrator) against `backend/tests/harness/postgres.py` and CAP-008's registry
row — *not* appended to BUG-050.

Reasoning for separateness, stated as a real argument rather than a label:

1. **Different defect class, different file, different owner.** BUG-050 is, in its
   own title and across all fifteen prior rounds, a *false-clean* bug: the harness
   reporting green when a financial invariant or a domain scaffold is genuinely
   broken. R16-1 is the precise opposite failure mode — the suite goes **loudly red**
   (1 failure, 141 errors, non-zero exit, every domain explicitly named as
   not-confirmed). Nothing about R16-1 causes a false clean. Folding an availability
   defect into a false-clean bug would blur the one distinction this lineage has spent
   fifteen rounds sharpening.
2. **Different remediation surface.** BUG-050's fixes have all landed in
   `tests/contract/`. R16-1's fix lands in `tests/harness/postgres.py` plus a
   `CAPABILITY_REGISTRY.md` scope-text correction — neither of which is BUG-050
   territory, and both of which need their own review.
3. **It outlives BUG-050.** The leak affects every CAP-008 consumer, present and
   future (Slice-5 tenant-isolation, authn, migration-safety harnesses all use the
   same fixture). Attaching it to BUG-050 would mean it closes when BUG-050 closes,
   which is wrong.

Reasoning for **P2** rather than P1 or P3:

- **Not P1**, because it is fail-closed. Segment 1 §4.2 verified this and it is the
  decisive fact: the inventory check reported `domain scaffold inventory not clean
  (exit=4)` naming all six domains as not-confirmed, and the suite exited non-zero.
  No green was claimed on unproven ground. There is also no data-exposure dimension —
  the 18.94 GB is synthetic fixture database state only, with no real member data
  (consistent with the owner-reserved restriction and with CAP-008's own registered
  scope), and no credential or spend is implicated (the volumes are local, the only
  network action in this lineage was a free registry pull).
- **Not P3**, because it is not housekeeping. Three properties lift it above that:
  (i) it is a **self-inflicted availability failure of a Blocking CI gate** — the
  condition `.claude/rules/backend/performance.md` control 3 names directly ("No gate
  is skippable under load... through a timeout, a resource-exhausted CI runner"), and
  SCN-MOD001-132's live acceptance criteria **cannot be re-verified in this
  environment at all** right now; (ii) it **contradicts CAP-008's registered scope
  text**, which claims the fixture is "force-removed on exit" and whose qualification
  record claims "zero leftovers" — the container is force-removed, its storage is
  not, so the approved registry row overstates the cleanup actually performed, which
  under `CAPABILITY_POLICY.md` stage 9 is a material divergence between registered and
  actual behavior; (iii) it is **monotonic and unbounded** — one ~40 MB volume per
  fixture container, with no ceiling, on a fixed 20 GB disk, so it is guaranteed to
  recur on a schedule set only by how often the suite runs.

Point (ii) deserves emphasis as a supply-chain/registry finding in its own right:
under `CAPABILITY_POLICY.md`, `scope` is a **required** supply-chain review field, and
a capability whose registered scope misdescribes its actual filesystem footprint is
not accurately registered. That is a registry-accuracy defect independent of the disk
being full, and it would survive a prune.

### 8.3 (b) Why pruning the 472 cannot touch `frosty_bhabha` — exact mechanism

Two independent mechanisms each make this safe. Either alone would be sufficient;
both hold.

**Mechanism 1 — reference counting (`dangling` = zero container references).**
Docker's volume prune removes only volumes "not used by at least one container",
where *container* means any container in any state, running or stopped, not merely
running ones. The `dangling=true` filter on `docker volume ls` evaluates the identical
predicate, which is why the two sets are the same set. `tradingview-mcp-session` is
mounted by `frosty_bhabha` (state `running`, verified above), so its reference count
is 1, so it is excluded from the dangling set — demonstrated empirically this session,
not assumed: the dangling enumeration contains **472** entries while the total is
**473**, and `grep -c tradingview` over the dangling list returns **0**. The prune
candidate set is therefore *literally* the 472 anonymous volumes, enumerated, with
`tradingview-mcp-session` provably outside it.

**Mechanism 2 — the anonymous-only default (Docker ≥ 23.0).** On this engine,
`docker volume prune --help` reports `-a, --all  Remove all unused volumes, not just
anonymous ones`. Without `-a`, the plain `docker volume prune -f` form removes
**only anonymous volumes**. `tradingview-mcp-session` is a *named* volume. So even in
the counterfactual where `frosty_bhabha` were stopped and removed — dropping its
volume's reference count to zero and making it dangling — the un-flagged prune still
would not delete it. Verified that this layer is not vacuous: filtering the dangling
set for non-anonymous entries (`docker volume ls -f dangling=true --format '{{.Name}}
{{.Labels}}' | grep -v com.docker.volume.anonymous`) returns **nothing** — all 472
candidates carry the `com.docker.volume.anonymous` label, so `-a` buys nothing here
and must not be used.

**The operative safety constraint, stated plainly: the command must be
`docker volume prune -f` and must NOT carry `-a`/`--all`.** With `-a` the second
mechanism is forfeited and only reference counting protects the named volume — still
correct today, but needlessly one-deep. Likewise `docker system prune --volumes` must
not be substituted: it would additionally remove the stopped-container and image
layers, including potentially the 411 MB reclaimable image state, which is outside
this finding's charge and would destroy owner-side environment state.

### 8.4 (c) Proposed remediation — NOT EXECUTED

**This segment ran none of the following.** They are proposals for a separate
implementation session, to be verified afterwards by a human or an independent
reviewer. Running them here would both exceed a review-only dispatch and destroy the
very environment state segment 3 may need to observe.

**Step 1 — one-time reclamation (owner-authorized, implementation session):**

```
docker volume prune -f
```

No `-a`. No `docker system prune`. Expected: ~472 volumes removed, ~18.94 GB
reclaimed.

**Step 2 — the actual root-cause fix (one character, in `backend/`, NOT touched by
this segment):** at `backend/tests/harness/postgres.py:189`, the error-path teardown

```
docker("rm", "-f", name)        ->        docker("rm", "-f", "-v", name)
```

`-v` removes anonymous volumes associated with the container. The happy path already
uses `--rm` on `docker run`, which does the same thing on normal exit; the leak is the
error path only, which is also why it accumulated fastest in rounds that failed. Per
ponytail laddering this is the minimum correct fix — no new abstraction, no cleanup
harness, no fixture-scoped volume registry. **A reviewer should check this claim
rather than take it from here: confirm by reading the file that line 189 is the only
`rm -f` without `-v` on any teardown path, and that no third teardown route exists.**

**Step 3 — registry correction (`CAPABILITY_REGISTRY.md`, CAP-008 `scope` field):**
amend the "force-removed on exit" language so it describes the storage footprint
truthfully. Until step 2 ships, the honest text is that the container is force-removed
but its anonymous data volume is retained on the error path. After step 2 ships, the
text can state container-and-volume removal. Per `CAPABILITY_POLICY.md` stage 9, a
scope change of this kind is a material change and should route back through stages
4-5 rather than being edited in place without evidence.

**Step 4 — verification (for whoever performs steps 1-2, and for the reviewer after):**

```
docker volume ls -q | wc -l                      # expect ~1 (tradingview-mcp-session only)
docker volume inspect tradingview-mcp-session    # expect: still present, still /data
docker ps --filter name=frosty_bhabha            # expect: still Up, untouched
colima ssh -- df -h /var/lib/docker              # expect: well under 100%
docker system df                                 # expect: Local Volumes ~1
```

Then, as the regression check that the *fix* (not just the cleanup) works — the
smallest thing that fails if the logic breaks: record `docker volume ls -q | wc -l`,
run the full backend suite once, re-record, and assert the count is unchanged. A
delta means step 2 did not take. That single before/after count is the whole check;
no fixture, no framework.

### 8.5 (d) Confound status — stated plainly

**Segment 1:** confounded, and segment 1 said so itself. Its three suite regressions
(runs 1-3 of §4.1) are entirely this condition — segment 1 grepped the full-suite
output and found **136 occurrences of `psycopg.OperationalError` and zero other error
classes**. Those three rows must **not** be read as Slice-7 regressions. Segment 1's
mutant work (§2), its regression work (§3), and its lint/format/type gates (§4.1 rows
4-6) are **not** confounded: §2.5 establishes that the eager guard fires at import
time, so `d3`/`d4`/`d3n`/`d4n` abort collection before any Postgres contact, and the
financial-invariant file needs no database at all.

**This segment (segment 2):** not confounded. Items 1-4 are filesystem, AST-free
document, and judgment work; none touches Postgres.

**Segment 3:** **blocked, as a precondition and not a choice.** The disk is still at
**100% / 13M free** as of this segment's own measurement, taken after segment 1's
probes were cleaned up. A live CAP-008 / Postgres drill cannot succeed in this
environment until step 1 above is performed by an authorized session.
SCN-MOD001-132's live acceptance criteria are therefore **not re-verifiable right
now**, and segment 3 must say exactly that rather than substituting a stale
rounds-11B-13 citation, working around it with a non-Postgres proxy, or quietly
narrowing its charge. If segment 3 runs after remediation, it should record the
remediation's own verification output (§8.4 step 4) as a precondition in its report.

## 9. Item 2 — is the `pytest_sessionfinish` execution witness required for closure?

**Judgment: NO. BUG-050 can be legitimately closed, and SCN-MOD001-132/133 promoted,
without building the execution witness — but NOT on the current record, because round
15 §12's description of the three remaining shapes is factually wrong on two of
them. The precondition for closure is a disclosure correction, not a new mechanism.**

This is a judgment with a prerequisite attached, not a deferral.

### 9.1 First, a correction: two of §12's three shapes are already closed

Round 15 §12 names a `pytest_sessionfinish` witness as the only mechanism that can
close three shapes "no import-time AST check can ever see in principle": a
conftest.py-level skip, an in-body `pytest.skip()`, and `-k`/`-m` deselection. That
claim was tested this session rather than accepted. It does not hold for the
mechanism round 15 actually built.

Method: a throwaway two-file package in `/tmp/r16seg2_k` / `/tmp/r16seg2_cf*`
(outside the repository, deleted at segment end; `backend/` never touched) in which a
module-level `raise AssertionError("IMPORT_TIME_GUARD_FIRED")` stands in for the eager
`assert_execution_not_suppressed(...)` call, alongside one marked test. Run with the
repo's own `backend/.venv` interpreter.

| Invocation | Does the eager import-time guard still fire? | Observed |
|---|---|---|
| plain `pytest -q` | **Yes** | `ERROR ... IMPORT_TIME_GUARD_FIRED`, `Interrupted: 1 error during collection` |
| `pytest -q -k zzz_no_match` | **Yes** | identical collection error |
| `pytest -q -m zzz_no_match` | **Yes** | identical collection error |
| `pytest -q --collect-only` | **Yes** | identical, `no tests collected, 1 error` |
| conftest `pytest_collection_modifyitems` adding `pytest.mark.skip` to every item | **Yes** | identical collection error |
| conftest `collect_ignore = ["test_witness.py"]` | **No** | `no tests ran in 0.00s`, exit 0 |
| `pytest --ignore=test_witness.py` | **No** | `no tests ran in 0.00s`, exit 0 |

The mechanism is simple and decisive: **`-k` and `-m` filter by *deselection*, which
happens after collection, and collection imports the module.** An import-time
assertion has therefore already fired before any filter is applied. The same is true
of a conftest `pytest_collection_modifyitems` skip, which also runs post-import.

So, of §12's three shapes:

1. **`-k`/`-m` deselection — NOT a gap in round 15's mechanism. §12 is simply
   incorrect here.** The claim was true of *round 14's* mechanism, where the guard was
   itself a collected test that `-k` could deselect. Round 15 changed the mechanism
   from a collected test to an eager module-level call and the claim was carried
   forward unrevised. This is a stale inherited assertion, and it is the kind of
   inaccuracy this lineage exists to catch.
2. **conftest-level skip — half a gap, and §12 does not distinguish the halves.**
   The marker-injection shape (`pytest_collection_modifyitems`) does **not** evade the
   eager guard. The collection-prevention shape (`collect_ignore`) does. Only the
   latter is real, and it is not really "a skip" — it is "the file never runs," which
   is a different class (see §9.2).
3. **in-body `pytest.skip()` — a real gap in the current guard, but NOT invisible
   "in principle" to an AST check**, which is what §12 asserts. An in-body
   `pytest.skip()` is a plain `Call` node inside the watched function's body, in the
   same file the walker already parses for decorators, `pytestmark`, redefinitions and
   rebinds. The current guard does not look for it; that is an omission, not an
   impossibility. Closing it is on the order of five lines in the existing walker —
   flag any `pytest.skip`/`skip(` call reachable in a watched function body — and
   needs no new mechanism, no hook, and no session-scoped state.

**The genuinely irreducible residue is therefore one class, not three: the file is
never collected at all** (`collect_ignore`, `--ignore`, or simply invoking pytest
against a narrower path).

### 9.2 Why the execution witness does not actually close that residue either

This is the structural reason the answer is "no" rather than "not yet."

A `pytest_sessionfinish` hook has to live somewhere. If it lives in the watched test
file, then anything that prevents that file from being collected also prevents the
hook from registering — the residue is untouched. If it lives in a `conftest.py`, it
closes "the watched file was not collected," but the conftest is now the target, and
the same question recurs one level up: what asserts that *this* conftest was loaded,
and was not itself `-p no:`-disabled, replaced, or bypassed by a narrower rootdir?

**The witness does not terminate the regress. It relocates it.** That is the decisive
point, and it is the one §12's "would close ... in one mechanism" framing misses. Any
in-repository mechanism is defeatable by an actor who can also edit the repository or
choose the invocation — which, by construction, is exactly the actor every one of
these shapes posits. The only controls that genuinely terminate the regress live
*outside* the mechanism being defended: a fixed, reviewed CI invocation, and the fact
that changing it is itself a reviewed diff. Those controls already exist here and are
not improved by a hook.

### 9.3 What SCN-132/133 actually ask for

Read against each scenario's own written text in `SCENARIOS.md`, neither requires
tamper-resistance against a hostile editor. Both ask for *detection power*.

**SCN-MOD001-133** — "Expected: the harness asserts debits equal credits and passes on
a balanced synthetic set. Negative case: the same harness run against a deliberately
unbalanced synthetic set (a debit with no matching credit) fails, citing the specific
invariant violated — **proving the harness itself detects a real violation, not a
rubber-stamp pass**." The named threat is a *rubber-stamp harness* — a check with no
detection power of its own. That is the original BUG-050 defect (net-amount-only
comparison), and it is fixed and verified. Nothing in SCN-133 contemplates an
adversary editing the test file.

**SCN-MOD001-132** — "the CI test-run step reports a non-zero exit naming that
specific domain's missing/failing scaffold, rather than silently reporting the suite
green with five domains actually collected." This one is closer to the suppression
family, since under-collection is explicitly named. But the contemplated cause is
stated right alongside it: "one of the six domains' `test_scaffold_live.py` fixtures
is **deleted or deliberately broken**." The control for that is the inventory check,
which exists and demonstrably works — segment 1 §4.2 observed it reporting
`domain scaffold inventory not clean (exit=4)` with all six domains named, under a
genuine infrastructure failure it had never been designed for. That is the criterion,
satisfied, on the negative path, unplanned.

Round 15 §12 already records both scenarios' acceptance criteria as **MET on live
code**. Every mechanism in the R14-1 → R15-4 lineage — the marker checks, the
`pytestmark` check, the redefinition and rebind checks, the whole
`_execution_suppression_guard.py` module — is **defense in depth above and beyond what
either scenario asks for**. That is not a criticism of building it; it is the reason
its residual gaps cannot block a scenario that never asked for it.

### 9.4 Is there a meaningful difference between the two defeat classes? Yes — a threat-model difference

The dispatch asks this directly, and the answer is the load-bearing one.

**In-file edits are in the diff and review surface, and the realistic failure is
non-adversarial.** The archetype is an engineer adding
`@pytest.mark.skip(reason="flaky on CI, re-enable later")` with no intent to hide
anything, which then silently disables a financial-invariant negative test
indefinitely. That change *passes code review precisely because it looks routine* —
which is exactly the condition under which an automated guard earns its keep. Guards
are good at catching the plausible accident that review waves through. This is why
rounds 14 and 15 were right to build what they built, and why `G1c` being
honestly disclosed rather than silently carried matters.

**Invocation-time flags are not in the diff surface, are not controllable by any
in-file mechanism, and require a deliberate act by someone who already controls the
test command.** There is no accidental `-k` that hides a failure forever: `-k` is
typed once, at a shell, by a person, and does not persist into CI. Against an actor
who *can* change the CI invocation, no in-repository mechanism holds, because that
actor can equally change the mechanism. The appropriate control is organizational —
a reviewed CI workflow — and it is already in place.

Conflating these two classes is, in this reviewer's judgment, the engine of the
fifteen-round regress. Each round has treated a newly-imagined adversarial-editor
shape as a defect of standing equal to the original false clean, extended the
source-text surface by one shape, and handed the next round a new adjacent shape to
find. There is no termination condition in that loop, because the space of ways a
determined editor can neuter a test in its own file is unbounded. **The loop does not
end by finding a better mechanism. It ends by deciding the mechanism is proportionate
to the threat and writing down what it does not cover.**

### 9.5 Disposition

Not a recommendation to build it later — a judgment that it should not gate closure:

1. **The execution witness is NOT required for BUG-050 closure or for promoting
   SCN-132/133.** It does not close the one irreducible shape, it relocates it, and
   neither scenario's acceptance language requires the class of defense it belongs to.
2. **Closure IS blocked on correcting the disclosure.** The current record (round 15
   §12, and anything downstream repeating it) misstates two of three remaining shapes.
   A closure resting on an inaccurate gap statement would be the same species of
   defect as the original bug — a claim stronger than the evidence. Before BUG-050
   closes, the residual-gap statement should read: **(i)** `G1c` walker-blindness via
   local name shadowing, open and disclosed, unchanged; **(ii)** in-body
   `pytest.skip()` in a watched test, open, AST-visible, cheap to close; **(iii)**
   the watched file is never collected (`collect_ignore`/`--ignore`/narrowed path),
   open, **not closable by any in-repository mechanism** including the proposed
   witness, controlled instead by the reviewed CI invocation; and **(iv)** `-k`/`-m`
   deselection and conftest marker-injection are **NOT** gaps — the eager import-time
   call already defeats both, demonstrated in §9.1.
3. **One optional cheap addition, explicitly not required:** the ~5-line in-body
   `pytest.skip()` check in the existing walker. A remediator may take it; a reviewer
   should not block on it. Nothing else in this family should be built for a
   placeholder scaffold harness.
4. **Recommended standing position:** cap the source-text guard where it is. Future
   rounds that discover a sixteenth adjacent editor-shape should record it against
   the disclosure in (2) rather than extend the mechanism, unless the shape is one a
   routine, well-intentioned edit could plausibly produce.

## 10. Item 3 — 6-token derivation query, re-run and reconciled

### 10.1 The query and the result

The recorded 6-token baseline, taken from BUG-050's own round-10 section (which
adopted it after NR10-3 established that round 9 had silently run six tokens while
recording only five), re-run from the repository root this session:

```
rg -l 'BUG-050|test_financial_invariant_scaffold|SCN-MOD001-133|SCN-MOD001-132|test_domain_scaffold_inventory|test_scaffold_live' knowledge .claude | sort
```

**Result: 47 files.** Round 15's remediation recorded **45**. **Delta: +2.**

Per BUG-050's own standing instruction, this was re-derived rather than inherited;
45 was not carried forward as a fixed number.

### 10.2 The +2, named file by file

| # | File | mtime | Why it is new since round 15's 45-count |
|---|---|---|---|
| 46 | `knowledge/03-Modules/MOD-001/evidence/implementation/BUG050-ROUND16-WATCHDOG-CHECKPOINT-2026-10-04.md` | created **2026-10-04 01:34**, last modified **03:35** | The round-16 dispatching watchdog's own checkpoint. Did not exist when the round-15 remediation ran its query (that query preceded the BUG-050 record write at 01:21). |
| 47 | `knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND16-2026-10-04.md` | created **2026-10-04 03:09**, last modified **03:26** (and again by this segment) | **This report.** Segment 1 wrote it; segment 2 is appending to it. Self-excluded by the same logic NR9-4/NR10-3 settled and round 15 §9 applied to its own report. |

**45 + 1 + 1 = 47, reconciling exactly. Nothing is unaccounted for.**

### 10.3 Verification that nothing else entered the set

Two independent checks, because mtime alone is not sufficient when files are rewritten
in place.

**Check 1 — mtime ordering.** Every file in the 47 with an mtime later than the
round-15 remediation's query is either one of the two above or a **re-edit of a file
already inside the 45**, not a new entry: `CURRENT_STATE.md` (01:18),
`CURRENT_HANDOFF.md` (01:19), `MOD-001/STATUS.md` (01:19), `MOD-001/TEST_RESULTS.md`
(01:20), `BUG-050-financial-invariant-placeholder-false-clean.md` (01:21),
`BUG_REGISTRY.md` (01:22) — all six are the round-15 remediation's own documentation
burst, and all six appear in round 15 §9's own list of re-edits inside the then-41 —
plus `REVIEW_IN_FLIGHT.md` (03:05), likewise already inside the 41 per round 15 §9 and
re-touched here only by the round-16 dispatch claim. **Not modified by this
reviewer**; recorded as observation.

**Check 2 — birth time (`stat -f %SB`), as a cross-check on in-place rewrites.** Only
two files in the 47 have a birth time later than the round-15 remediation's edit burst
(which closes at 01:22): the two named in §10.2, at **01:34** and **03:09**. One
apparent third hit, `BUG_REGISTRY.md` at **01:22**, is a false positive of this method
and is called out rather than quietly dropped: its birth time was reset by the
editing tool's write-then-rename, and the file long predates round 15 (round 15 §9
lists it at 00:38 inside the then-41). The same reset explains the 01:18-01:21 birth
times on `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `STATUS.md`, `TEST_RESULTS.md` and
the BUG-050 record, none of which is remotely new. Both methods agree on the same
two genuine additions.

### 10.4 Stale-currency / false-attestation check

No previously-unknown live-claim document surfaced. **This is the fifth consecutive
round with no stale-currency finding.**

The one new non-report file, `BUG050-ROUND16-WATCHDOG-CHECKPOINT-2026-10-04.md`, was
read in full. It correctly claims **no verdict and no model attestation** —
explicitly, and repeatedly across its six recovery updates ("This checkpoint does not
claim a verdict or model attestation"; "This is an interruption, not a verdict"; "Do
not mark tests PASS or close BUG-050"). It records three prior interrupted round-16
attempts (a 429 rate limit, a rejected test-tool call, a 1200-second cron timeout),
an orchestrator-side `mr_verify.py` PASS of 82/82 turns at `claude-opus-5` for
segment 1, and the segment-2 dispatch — all consistent with this session's own
observations. It introduces no false attestation.

The 6-token query is retained as the round-17 baseline. It is dynamic by design;
**47 must be re-derived, not copied forward.** A successor should expect at minimum
+1 for this report's own later segments if they land as separate files, and should
reconcile rather than normalize any delta.

**Per the dispatch, the full backend and Slice-7 suites were NOT re-run by this
segment.** Segment 1 §4 holds those results, including the environmental regression
item 1 explains.

## 11. Item 4 — R15-5 / R12-4 CAP-008 scope-minimality: DISPOSITION

Carried undisposed since round 10. This section gives it a verdict.

### 11.1 Verdict

> **DOES NOT BLOCK** SCN-MOD001-132 or SCN-MOD001-133 promotion, and **DOES NOT
> BLOCK** BUG-050 closure. The co-resident container's mere presence is **not** a
> `CAPABILITY_POLICY.md` fail-closed violation, and scope-minimality does **not**
> require CAP-008 to run on a dedicated engine.
>
> It **IS** a real scope-minimality deviation, and as of this round it is no longer a
> theoretical one. **Escalated from "carried, pending" to a STANDING ENVIRONMENTAL
> DEVIATION REQUIRING OWNER DISPOSITION**, with a deadline of CAP-008's own
> `next_review_due` (**2026-12-31**), and with two registry-accuracy corrections
> required at or before that re-evaluation.

### 11.2 Why it is not a fail-closed violation

`CAPABILITY_POLICY.md`'s fail-closed rule binds on **use**: "If a session finds itself
about to **invoke** an unregistered or unqualified capability against real project
work... it must stop and report `BLOCKED: CAPABILITY_UNREGISTERED`."

No Veyro code, harness, test, agent, or rule invokes `mikeh1975/tradingview-mcp`.
It is not in `CAPABILITY_REGISTRY.md` because it is not a project capability — it is
an unrelated personal workload of the owner's, running on the owner's own machine.
Treating co-residence as "use" would make the policy unsatisfiable on any developer
machine that runs anything else, which is not a reading the policy's own text
supports. **The fail-closed rule is not triggered.**

### 11.3 Why scope-minimality does not require a dedicated engine

The rule is: "No capability may be **granted** broader scope (filesystem, network,
spend) than the specific gap requires." It constrains what *the project grants a
capability*. It is not a requirement that the owner's machine run nothing else.

Two further reasons, both grounded rather than asserted:

1. **Policy precedent inside CAP-008's own row.** CAP-008's registered `scope` field
   already states: "The local Colima VM presently mounts the user home directory
   writable (**broader effective filesystem reach than the fixture needs**); image
   acquisition/updates may use external package or registry network, so 'no network
   beyond loopback' is not claimed." The project has already accepted a
   broader-than-minimal condition **by disclosing it** rather than by blocking, and
   that row carries a `review_status: APPROVED` from an independent Opus review
   (`COLIMA_OPUS_R2_APPROVAL_2026-10-02.md`, P0=0/P1=0). Consistency requires the same
   disposition here; inventing a stricter standard for the co-resident container than
   the already-approved writable home mount would be arbitrary.
2. **Owner-reserved territory.** Requiring a dedicated Docker engine means requiring
   the owner to restructure their personal computing environment. Per
   `.claude/rules/global/owner-reserved-restrictions.md` an agent does not make that
   call. An agent can escalate it; it cannot impose it, and it should not use a
   scenario promotion as leverage to force it.

### 11.4 What HAS changed this round, and why "no observed interaction" no longer holds

The premise justifying six rounds of deferral was that no cross-contamination had been
observed. **That premise is now false.** Two concrete couplings, both verified this
session:

**(a) Shared finite disk — demonstrated, not theoretical.** Item 1: both workloads
draw on one 20 GB `/dev/vdb1`, which is now 100% full, and CAP-008's harness is
currently unable to start a Postgres container at all. Stated fairly so the finding
is not inflated: **the co-resident container did not cause this.** The CAP-008 fixture
leak accounts for 18.94 GB of ~19 GB used (≈98%); the tradingview image is ~0.42 GB
(≈2%). Blaming `frosty_bhabha` for the outage would be wrong and this report does not.
But the resource is genuinely shared and finite, and contention between the two is now
an observed fact rather than a hypothetical.

**(b) Shared default bridge network — and it narrows a control CAP-008 claims.** This
is the more substantive of the two, and it appears not to have been stated in prior
rounds.

Verified by inspection this session: `frosty_bhabha` is attached to the default
`bridge` network at **172.17.0.2** (`netmode=bridge`, no published ports). Verified by
reading `backend/tests/harness/postgres.py`: the fixture's `docker run` at line 173-176
passes **no `--network` flag**, so every Postgres fixture container also lands on that
same default bridge.

The consequence: `-p {LOOPBACK}::5432` (line 176) and the guard at line 181-183 that
asserts the publish address is `127.0.0.1` constrain **host** reachability only. They
do not constrain in-VM bridge peers, which can reach the fixture's port 5432 directly
on its container IP without going through the published host port at all. CAP-008's
remediation evidence presents the loopback-publish guard as an isolation control; a
reader would reasonably infer more isolation from it than it actually provides in the
presence of a co-resident container.

**Mitigating facts, verified this session so the finding is not overstated:**
`frosty_bhabha` runs `Privileged=false`, with `CapAdd=[]`, **no Docker socket mount**,
**no host bind mounts** (its only mount is the named volume
`tradingview-mcp-session` at `/data`), and no published ports. It therefore cannot
control the engine, cannot reach the host filesystem, and is not reachable from
outside. The fixture database holds **synthetic fixture data only** — no real member
data, consistent with the owner-reserved restriction and with CAP-008's registered
scope — and exists only for the duration of one pytest session. **No interaction
between the two workloads has been observed.** This is *reachability*, not
*compromise*, and it is rated accordingly.

### 11.5 Conditions attached to this disposition

Not blockers for SCN-132/133 or BUG-050. Conditions on CAP-008's next re-evaluation,
due **2026-12-31**, and per `CAPABILITY_POLICY.md` stage 9 a scope-description change
of this kind routes back through stages 4-5 rather than being edited in place:

1. **Registry accuracy — disclose the shared engine.** CAP-008's `scope` field should
   name the co-resident-unregistered-workload condition the same way it already names
   the writable home mount. Today it does not, and the row therefore understates the
   capability's actual trust environment.
2. **Registry accuracy — narrow the loopback claim.** The loopback-publish guard
   should be described as constraining **host** reachability, not as general network
   isolation, since §11.4(b) shows it does not constrain in-VM bridge peers.
3. **Optional, proportionate hardening — proposed, NOT executed, not a blocker.** A
   dedicated user-defined bridge for the fixture (`docker network create
   veyro-fixture` once, plus `--network veyro-fixture` on the fixture's `docker run`)
   would restore the isolation a reader currently infers, at the cost of one flag.
   This is the lazy fix and is noted alongside item 1's `-v` fix since both land in
   the same two lines of the same file. **This segment did not make either edit** —
   `backend/` was not touched.
4. **Owner decision required, and it is genuinely the owner's.** Whether to move
   `frosty_bhabha` off this engine, accept the deviation formally, or re-scope CAP-008
   is an owner call about the owner's own machine. An agent cannot dispose of it.
   What an agent **can** stop doing is deferring it for a seventh round, which is what
   this section does.

### 11.6 On the deferral itself

Six-plus rounds of "recorded, not touched" is, at this point, its own defect — the
same species of drift `CAPABILITY_POLICY.md` stage 9 exists to prevent, where a
capability's registered description and its actual operating conditions diverge
without anyone deciding anything. The honest reading is that prior rounds were correct
that it did not block, and incorrect to leave it undisposed on that basis.
Non-blocking is a disposition; "pending" is not.

### 11.7 Incidental verification of item 1's proposed fix

While reading `postgres.py` for §11.4(b), the root cause item 1 proposed was
confirmed directly rather than left to the reader: line **189** is
`docker("rm", "-f", name)` with **no `-v`**, and it is the only `rm` teardown in the
file (line 174's `--rm` is the happy-path flag on `docker run`). There is no third
teardown route. **The file was read only; nothing under `backend/` was modified.**

## 12. Segment 2 close — boundaries honored

| Boundary | Status |
|---|---|
| Docker volumes pruned | **None.** 473 volumes / 472 dangling at segment start and at segment end |
| `frosty_bhabha` touched | **No.** Inspected read-only (`docker inspect`); still `running`, unmodified |
| Any container stopped/removed/created | **None.** No `docker run` this segment |
| Files under `backend/` edited | **None.** `tests/harness/postgres.py` read only |
| SCN-MOD001-132 / 133 | **Not promoted** |
| BUG-050 | **Not closed** |
| `REVIEW_IN_FLIGHT.md` | **Not edited** |
| Final round-16 PASS/BLOCKED verdict | **Not issued** — segment 3's job |
| Commit / push | **None** |
| Full backend / Slice-7 suites re-run | **No** — per dispatch; segment 1 §4 holds those |
| Throwaway artifacts | `/tmp/r16seg2_k`, `/tmp/r16seg2_cf`, `/tmp/r16seg2_cf2`, `/tmp/r16seg2_tokens_now.txt` — outside the repository, deleted at segment end |
| Repository writes by this segment | Exactly one file: this report |

### 12.1 Standing supply-chain / member-data / spend charge — segment 2's portion

Segment 1 §5.6 covered this partially and flagged a full assessment as deferred here.
Segment 2's portion, covering its own actions and the two capability questions in its
charge:

- **Real member data:** none observed, none introduced. The CAP-008 fixture content
  (18.94 GB across 472 volumes) is synthetic fixture database state only, consistent
  with CAP-008's registered scope and the owner-reserved restriction. The `/tmp` test
  packages contained three trivial synthetic files.
- **Credentials:** none read, written, or committed. No `.env` file was read; no
  credential-shaped value appears in this report. Per
  `.claude/rules/infra/secrets.md`, nothing credential-shaped was authored.
- **Spend:** none. No network egress at all this segment — no registry pull, no
  package install, no paid service. All Docker operations were local read-only
  inspections.
- **Third-party capability treated as trusted without qualification evidence:**
  one, and it is §11's subject — `mikeh1975/tradingview-mcp:latest` is unregistered
  and unqualified, but is also **not used** by the project, which is why §11.2 finds
  no fail-closed violation. No other unregistered capability was invoked by this
  segment. Everything this segment ran is harness-native (`Bash`/`Read`) or the
  already-APPROVED CAP-008 toolchain used read-only.
- **Capability granted broader scope than its stated need:** two, both now disposed
  rather than carried — CAP-008's shared-engine/shared-bridge condition (§11, with
  registry corrections required by 2026-12-31) and CAP-008's already-disclosed
  writable-home-mount, which remains accurately disclosed in the registry and is
  unchanged this round.

**This assessment covers segment 2's own actions and its four charged items only. It
is not a whole-round supply-chain clearance, and segment 3 must not read it as one.**

---

# Round 16 — Segment 3 (final): BUG-051 fix review, live CAP-008 drills, CAP-008 re-review, final verdict

## Scope of this segment

Final segment. Covers, and is the only segment that issues a verdict:

1. Independent security review of BUG-051's fix (the `-v` teardown change, its
   regression test, and the volume-count-stable evidence claimed in BUG-051 and the
   CAP-008 registry row) — by execution, not by reading the fix's own record.
2. The live CAP-008 / Postgres drills for **SCN-MOD001-132** and **SCN-MOD001-133**,
   blocked in segment 2 as a precondition, now attempted for real.
3. A fresh independent Opus capability-security re-review of **CAP-008** itself,
   which the registry row names as the next legally allowed action for that row.
4. Accurate aggregate state: full backend suite, the six domain scaffolds, lint/format/
   type gates, and the project's governance validators — with pre-existing/known
   findings named as such rather than normalized away.
5. The final round-16 **PASS/BLOCKED** verdict with P0-P3 counts and explicit
   dispositions.

Nothing in segments 1-2 is re-done and then re-claimed; where this segment cites those
results it says so. Boundaries honored throughout and audited in §20: no Docker volume
pruned, `frosty_bhabha` untouched, nothing under `backend/` edited, no scenario
promoted, no bug closed, `REVIEW_IN_FLIGHT.md` and `CAPABILITY_REGISTRY.md` not edited,
no commit, no push.

## 13. Precondition re-verification — the environment the orchestrator described

Re-derived from scratch this segment, not accepted on faith. Every orchestrator-supplied
figure reproduces:

| Measurement | Orchestrator's claim | This segment's observation | Match |
|---|---|---|---|
| `colima ssh -- df -h /var/lib/docker` | 793M used / 18G avail / 5% (was 100%) | `/dev/vdb1  20G  793M  18G  5%  /var/lib/docker` — and `/mnt/lima-colima` resolves to the same `/dev/vdb1`, confirming one filesystem, not two | **Exact** |
| `docker volume ls -q \| wc -l` | 1 (was 473) | **1** | **Exact** |
| Identity of the one remaining volume | `frosty_bhabha`'s own named `tradingview-mcp-session`, untouched | `docker volume ls --format '{{.Name}} {{.Labels}}'` → `tradingview-mcp-session` with **no** `com.docker.volume.anonymous` label | **Exact** |
| `frosty_bhabha` still running | still `Up` | `frosty_bhabha \| mikeh1975/tradingview-mcp:latest \| Up 2 days` — the only container on the engine | **Exact** |
| `git rev-parse HEAD` | unchanged | `b86446dcd283a5afeb86c612fb2657f769268748` — identical to segment 1's recorded segment-end HEAD | **Exact** |
| Changes are uncommitted working-tree edits | expected for this project mid-round | `git status --porcelain` shows `backend/tests/harness/postgres.py` and `backend/tests/unit/test_harness_postgres_fail_closed.py` as ` M`; the three Slice-7 contract files remain `??` (untracked, as in every prior round) | **Exact** |

`docker system df` additionally reports **Local Volumes 1 / 0B / 0B reclaimable** —
i.e. the 18.94 GB of reclaimable volume state segments 1-2 measured is genuinely gone,
not merely hidden from one listing. Images 2 (829.5MB, 411.3MB reclaimable) and
Containers 1 are unchanged from segment 2's picture.

**Precondition satisfied. Segment 2's §8.5 block on the live CAP-008 drill is lifted,
and the drills in §15 below ran for real.**

### 13.1 FINDING R16-2 (P3, disclosure-accuracy) — an in-scope Slice-7 file changed after segments 1-2 verified its hash, and the dispatch to this segment did not say so

Found by re-hashing the three in-scope files before doing anything else, which is why
this is recorded rather than missed:

| File | Segment 1's verified hash | This segment's observed hash | Changed? |
|---|---|---|---|
| `tests/contract/test_financial_invariant_scaffold.py` | `471910a18461d8b1…` | **`8988b3e0d3a4cd25051b3a120e4ea003eddf05764070e67ab44c660ddac8b56d`** | **YES** |
| `tests/contract/test_domain_scaffold_inventory.py` | `b7cd06f1b0be7f14…` | `b7cd06f1b0be7f14bb9d85002f3af717…` (full: `b7cd06f1b0be7f14bb9d85002f3af717eef40b557755cc4570e94842b63861c3`) | No |
| `tests/contract/_execution_suppression_guard.py` | `c55fa51485ca4d9b…` | `c55fa51485ca4d9b2e88b089c93824c73492afe038b3a53c23f616bdff7c44d4` | No |

File mtimes: the financial-invariant file was written at **03:55:56**, *after* the
Sonnet session's 03:50:59 edits to `postgres.py`/`test_harness_postgres_fail_closed.py`.

**Rated P3, not higher, because the change IS honestly disclosed at source** —
BUG-050's own round-16 section records the new hash `8988b3e0…` verbatim, names it as
"this session's own docstring-only edit," and explains it as applying segment 2 §9.5's
*mandatory disclosure correction* (the precondition segment 2 attached to BUG-050
closure). That is exactly the right thing to have done and it was recorded, not hidden.

**What is nevertheless a finding:** the dispatch that opened this segment enumerated
the Sonnet session's changes as the `postgres.py` one-liner, the prune, the regression
test, the CAP-008 registry correction, and the QUALIFIED downgrade — and did **not**
mention that a Slice-7 file under active security review had also been edited. A
segment-3 reviewer that trusted the dispatch's enumeration and re-used segment 1's hash
table would have reviewed a file that no longer exists at that hash. The defect is in
the hand-off summary, not in the record; it is disclosed here so the chain is complete.

**Independently verified as docstring-only, behaviorally, since no git baseline exists
for an untracked file** (so a textual diff is impossible, and "docstring-only" cannot
be taken on the editor's word). See §14.3: the three reconstructed mutants behave
identically to segment 1's recorded results against the edited file, and §16's run of
the file reports the same 23 tests. A logic change would have to be one that preserves
test count, pass/fail behavior, *and* all three mutant kill signatures — which is not a
realistic accidental shape.

## 14. Independent review of BUG-051's fix

Reviewed as a security reviewer, by execution. BUG-051's own record and the CAP-008
material-change evidence were read, then set aside; every claim below was re-derived.

### 14.1 Is `-v` the correct and sufficient mechanism? — YES, verified

Three things had to be true for `-v` (rather than a separate `docker volume rm`, a
named volume, or a cleanup harness) to be the right fix. All three verified directly:

| Question | Method | Observed |
|---|---|---|
| Does the pinned image actually declare a `VOLUME`? | `docker image inspect <pinned digest> --format '{{json .Config.Volumes}}'` | `{"/var/lib/postgresql/data":{}}` — **yes**, exactly one |
| Is the resulting volume **anonymous** (which `docker rm -v` reaps) or **named** (which it does not)? | `docker inspect <container>`, then `docker volume inspect` on the created volume | `type=volume`, 64-hex name, `labels=map[com.docker.volume.anonymous:]`, `driver=local`, mounted at `/var/lib/postgresql/data` — **anonymous**. `docker rm -v` is precisely the right instrument; a named volume would have needed a separate `docker volume rm` and `-v` would **not** have touched it |
| Is line 197 the only teardown route, so one fix covers all callers? | `grep` for `"rm"` / `docker(` / `subprocess.run` / `disposable_postgres` across `backend/tests` and `backend/app` | **Yes.** One `rm` call site (`tests/harness/postgres.py:197`); line 174's `--rm` is the `docker run` flag, not a teardown. Three consumers — `app/modules/conftest.py:27` (the six domain scaffolds), `tests/integration/conftest.py:35`, `tests/integration/test_migration_safety_harness.py:68` — **all** route through `disposable_postgres()`. The fix lands once, where every caller passes through |

Segment 2 §11.7 asserted the "only teardown route" property from reading the file;
this segment confirms it by search across the whole backend tree, which is the stronger
form of the same check.

### 14.2 Empirical before/after across a real container cycle — the leak reproduces, and the fix stops it

Not inferred from the argv. Two real containers were created on the live CAP-008
engine using the **pinned digest**, reproducing each teardown shape exactly:

| Step | Command shape | Volume count before | Volume count after | Delta |
|---|---|---|---|---|
| Baseline | — | — | **1** (`tradingview-mcp-session`) | — |
| **A — pre-fix shape** | `docker run -d --rm … <pinned> ; docker rm -f <name>` (**no `-v`**) | 1 | **2** | **+1 — LEAK REPRODUCED** |
| (cleanup of A's leak) | `docker volume rm <the one exact id>` — **not** a prune | 2 | 1 | -1 |
| **B — fixed shape** | `docker run -d --rm … <pinned> ; docker rm -f -v <name>` | 1 | **1** | **0 — NO LEAK** |

The volume A leaked was identified by set difference (`comm -13`) against a captured
baseline list, not by counting, so the identification is exact:
`e4416e3a0182053ed0bad51f819422fbcdc752a6e3bc984bbb54b090a9712939`. It carried the
`com.docker.volume.anonymous` label. It was removed **by its exact id**; no prune of
any kind was run, and `tradingview-mcp-session` plus `frosty_bhabha` were confirmed
present and `Up` afterwards.

**Conclusion: the fix is correct, minimal, and sufficient. BUG-051's root-cause
remediation is sound.**

### 14.3 The regression test is load-bearing, not tautological — independently re-confirmed

BUG-051 claims it reverted the fix in a throwaway copy and both tests failed. That
claim was not taken on trust; it was reconstructed independently: `rsync` of
`backend/` into `/tmp/r16s3rev/` (`.venv` symlinked, `__pycache__`/caches excluded),
one control copy and one copy with `docker("rm", "-f", "-v", name)` textually reverted
to `docker("rm", "-f", name)` under an exact-occurrence-count assertion, so a
silently-missed mutation is impossible. Real tree never written to; tree deleted at
segment end.

| Copy | Result | exit |
|---|---|---|
| Control (unmutated) | **17 passed** in 7.87s | 0 |
| `-v` reverted | **2 failed, 15 passed** in 7.21s | 1 |

Both failures are the right ones, with the right message:

```
FAILED tests/unit/test_harness_postgres_fail_closed.py::test_port_and_cleanup_use_the_same_trusted_route
FAILED tests/unit/test_harness_postgres_fail_closed.py::test_error_path_teardown_removes_the_anonymous_volume
E  AssertionError: error-path teardown ['rm', '-f', 'veyro-mod001-harness-96cc33a6'] omits -v;
   the container's anonymous Postgres data volume would leak
E  assert '-v' in ['-f', 'veyro-mod001-harness-96cc33a6']
```

**The new test pins the right thing and genuinely fails on revert.** The companion
update to `test_port_and_cleanup_use_the_same_trusted_route` was also necessary and
correct — that test already pinned this call's argv, so leaving it unchanged would have
left a second, silently-stale assertion. Two independent tests now fail on a revert,
which is better than one. The test needs no live Docker (it drives the file's existing
fake-docker-CLI seam), so it runs in CI where the live drill cannot.

This also independently re-verifies §13.1's claim that the edit to
`test_financial_invariant_scaffold.py` was docstring-only: the control copy's suite is
unchanged, and §16's run of the Slice-7 pair reports the same test count and the same
pass/fail behavior segment 1 recorded.

### 14.4 FINDING R16-3 (P2) — the fix is right, but *why* it was needed is recorded wrongly, and that wrong text is now live in `CAPABILITY_REGISTRY.md`

This is the one substantive finding against BUG-051's remediation, and it originates in
**this review's own segments 1-2**, which is stated plainly rather than attributed
downstream.

**The claim, as it appears in five places:** that the leak was an *error-path* defect —
that `--rm` reaped the volume on the happy path, so the leak cost "one ~40MB leak per
**failed/erroring** session."

- `BUG-051`'s title ("…leaks anonymous Docker volumes **on the error-path teardown**") and its body ("The happy-path `docker run … --rm` reaps that volume along with the container on normal exit")
- `backend/tests/harness/postgres.py`'s new inline comment at the teardown
- the same file's `except RuntimeError: pass` comment ("best effort: `--rm` also reaps it")
- the new regression test's docstring ("one leak per failed/erroring session")
- **`CAPABILITY_REGISTRY.md`'s CAP-008 `scope` field**, in the dated 2026-10-04 correction itself
- and, upstream of all of them, this report's own §4.2 ("so on that path the volume survives") and §8.4 step 2 ("the leak is the error path only, which is also why it accumulated fastest in rounds that failed")

**It is false.** Step A in §14.2 is the disproof, and it was constructed to match the
harness's real control flow rather than a hypothetical: the container was **still
running** (`Up 4 seconds`) when `docker rm -f` executed, and the volume leaked anyway.
That is not an error path — it is what `disposable_postgres()` does on **every single
invocation**. Reading the control flow confirms the mechanism: `docker run -d --rm`
starts a long-lived container, and the `finally` block is reached with that container
still running on the success path too, so `rm -f` — not `--rm` — is what actually
removes it, every time. `--rm` only fires when a container *exits on its own*, which
this container never does.

**So the pre-fix leak was one anonymous volume per pytest session that used the
fixture, unconditionally — not one per failure.** This is the simpler and better
explanation of the observed evidence, and it resolves something the error-path story
never did: 472 volumes accumulated across roughly two days, which is far more sessions
than this lineage had failures.

**Why P2 and not P3:** the erroneous sentence is live in `CAPABILITY_REGISTRY.md`'s
CAP-008 `scope` field — a **required** supply-chain field under `CAPABILITY_POLICY.md`
— inside the very dated correction whose entire purpose was to make that field
truthful after segment 2 §8.2(ii) found it untruthful. A scope field that is still
factually wrong *after* its accuracy correction is the same registry-accuracy defect
class segment 2 rated P2, and it is directly load-bearing on the CAP-008 verdict in
§18. It also understates the defect's accumulation rate by roughly an order of
magnitude, which is exactly the number a reader uses to judge how fast the condition
recurs if the fix is ever lost.

**Why not P1:** no behavior is wrong. The fix is correct and verified (§14.2); the
regression guard is correct and verified (§14.3); the registry's *present-tense* claim
("now accurate for both container and volume") is **true**. What is wrong is the
historical narrative explaining the defect — serious for a governance record, not a
live security exposure.

**Required correction (specific, one-line-scale, cannot be made by this review-only
segment):** in `BUG-051`, in `CAPABILITY_REGISTRY.md`'s CAP-008 `scope` field, in
`CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md`, in `postgres.py`'s two comments
and in the regression test's docstring, replace "error-path"/"per failed/erroring
session" with the accurate statement: *the container is still running when the `finally`
block's `rm` executes, so that call — not `--rm` — removes it on every path; without
`-v` the anonymous volume leaked once per fixture-using pytest session, unconditionally.*
This report's own §4.2 and §8.4 should be read as superseded on this point by §14.2.

### 14.5 FINDING R16-4 (P3) — two narrow teardown gaps the fix does not close, and one comment that misstates its own fallback

Not blockers; recorded because a reviewer who checked only the `-v` change would miss
them, and because one of them is the same "a comment claims a safety property it does
not have" shape as R16-3.

1. **The `except RuntimeError: pass` around the teardown swallows a failed cleanup, and
   its stated justification is wrong.** The comment reads "best effort: `--rm` also
   reaps it, and the original error matters more." The second clause is sound — masking
   the original exception would be worse. The first is not: per §14.4 the container is
   still running at that point, so `--rm` reaps nothing. If the `rm` call fails (it can
   — `DockerRoute` raises `RuntimeError` on a non-zero exit **and** on
   `subprocess.TimeoutExpired` at its 120s timeout), the result is a still-running
   container *and* a leaked volume, silently. The swallow itself is defensible; the
   comment justifying it is not, and should say "best effort: a failed cleanup leaks a
   container and its volume, but masking the original error would be worse."
2. **A container created by a failing `docker run` gets no teardown at all.** The
   `docker("run", …)` call sits *outside* the `try:` whose `finally` performs cleanup,
   so a `run` that creates a container and then reports non-zero leaves nothing to
   remove it. Narrow (with `--rm`, most start failures are self-reaping) and not worth
   a code change on a test fixture by itself — recorded so it is a known, disclosed
   residue rather than an unexamined one.

Neither changes the disposition of BUG-051's fix, which §14.2 and §14.3 confirm is
correct.

## 15. The live CAP-008 / Postgres drills — RUN FOR REAL this segment

Segment 2 §8.5 blocked these as a precondition. The precondition is cleared (§13), and
every drill below was executed by this reviewer against the live Colima engine. Volume
and container counts were recorded around every drill, which doubles as the independent
before/after confirmation of BUG-051's "volume count stable" claim that §14 owed.

### 15.1 Does SCN-MOD001-133 need live Postgres at all? — **NO**, checked rather than assumed

The dispatch asked this directly and warned against assuming. Checked two ways:

1. **By imports.** `tests/contract/test_financial_invariant_scaffold.py` imports only
   `ast`, `dataclasses`, `decimal`, `enum`, `pathlib`, `uuid`, `pytest`, and the local
   `_execution_suppression_guard`. **No `psycopg`, no harness import, no fixture
   request.** It touches no conftest that provides a database.
2. **By execution, with Docker accounting.** Volumes `1` and containers `1` before;
   **`23 passed in 0.03s`, exit 0**; volumes `1` and containers `1` after. A run that
   contacted Docker could not complete in 0.03s.

**The live-Postgres requirement belongs entirely to SCN-MOD001-132's six domain
scaffolds, not to SCN-133.** The dispatch's hypothesis is correct. This is also why
segment 1 could validly run this file while the disk was full, and why §2.5's claim
that the nine mutants needed no Docker holds.

The `23 passed` figure matches segment 1 exactly, against the file at its **new** hash
— the behavioral half of §13.1's docstring-only verification.

### 15.2 SCN-MOD001-132 positive case — all six domain scaffolds against a real disposable Postgres

The six scaffolds share one session-scoped container via
`app/modules/conftest.py`'s `scaffold_pg` → `disposable_postgres()`, confirmed by
reading that conftest.

```
app/modules/membership/tests/test_scaffold_live.py::test_scaffold_live PASSED [ 16%]
app/modules/booking/tests/test_scaffold_live.py::test_scaffold_live    PASSED [ 33%]
app/modules/payment/tests/test_scaffold_live.py::test_scaffold_live    PASSED [ 50%]
app/modules/ledger/tests/test_scaffold_live.py::test_scaffold_live     PASSED [ 66%]
app/modules/pos/tests/test_scaffold_live.py::test_scaffold_live        PASSED [ 83%]
app/modules/access/tests/test_scaffold_live.py::test_scaffold_live     PASSED [100%]
============================== 6 passed in 1.62s ===============================
```

Volumes `1` → `1`; containers `1` → `1`. Each scaffold does real work, not a no-op:
it executes `SELECT 1` against the live connection **and** exercises the shared
`_shared.tenant_context` resolver contract.

**A real container was proven to exist, not inferred from a green result.** Because
1.6s is fast for a Postgres start, the run was repeated with a concurrent poller
against `docker ps`:

```
veyro-mod001-harness-030cd87f | 721873c34ceb | 127.0.0.1:33768->5432/tcp
```

Three of CAP-008's registered scope claims are confirmed live in that single line: the
image id `721873c34ceb…` is the **pinned digest**
`sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`; the publish
address is **`127.0.0.1`**, on an ephemeral port; and the container is gone afterwards
with containers back to `1` and volumes back to `1`.

### 15.3 SCN-MOD001-132 through its own CI gate — the inventory check

```
tests/contract/test_domain_scaffold_inventory.py::test_all_six_domain_scaffold_paths_exist PASSED
tests/contract/test_domain_scaffold_inventory.py::test_all_six_domain_scaffolds_pass       PASSED
============================== 2 passed in 1.86s ===============================
```

Volumes `1` → `1`. This gate spawns its own `pytest` subprocess over the six paths and
parses the JUnit XML per domain by name, so it is a genuinely independent confirmation
of §15.2 rather than a restatement.

### 15.4 SCN-MOD001-132 negative case — both variants SCN-132's own text names

SCN-132's acceptance language requires that "one of the six domains'
`test_scaffold_live.py` fixtures is **deleted or deliberately broken**" produces "a
non-zero exit **naming that specific domain's** missing/failing scaffold, rather than
silently reporting the suite green with five domains actually collected." Both variants
were run, in a throwaway `rsync` copy at `/tmp/r16s3neg/tree` (`.venv` symlinked, real
tree never written to, deleted at segment end), with the mutation applied under an
exact-occurrence-count assertion.

**Variant A — deliberately broken** (`access`'s `SELECT 1 … == (1,)` → `== (2,)`, the
same domain and shape round 15 used):

```
E  AssertionError: domain scaffold inventory not clean (exit=1): {'access': 'failed'}
E  FAILED app/modules/access/tests/test_scaffold_live.py::test_scaffold_live
E  1 failed, 5 passed in 1.56s
FAILED tests/contract/test_domain_scaffold_inventory.py::test_all_six_domain_scaffolds_pass
1 failed, 1 passed in 1.82s
```

Inventory-gate exit code: **1**. Direct six-scaffold run exit code: **1**
(`1 failed, 5 passed`). **Exactly one domain named — `{'access': 'failed'}` — the other
five correctly reported clean. Non-zero exit. No green suite with five collected.**

**Variant B — deleted** (the `access` scaffold file removed outright):

```
E  AssertionError: missing domain scaffold(s): ['access']
E  AssertionError: domain scaffold inventory not clean (exit=4): {'membership': 'EXPECTED_EXACTLY_ONE_GOT_0:[]', …,
   'access': 'EXPECTED_EXACTLY_ONE_GOT_0:[]'}
```

Exit code: **1**. `test_all_six_domain_scaffold_paths_exist` names **exactly
`['access']`**, satisfying the "naming that specific domain" criterion precisely.
Observation, not a finding: the companion `test_all_six_domain_scaffolds_pass` is less
precise on this variant — a missing path argument makes pytest exit 4 before collecting
*anything*, so all six report `EXPECTED_EXACTLY_ONE_GOT_0`. That is strictly
fail-closed (it never claims a domain passed) and the specific domain is still named by
the sibling test, so the criterion is met; it is recorded so a future reader is not
surprised by the six-domain message.

**Volume count stayed at `1` and container count at `1` across every drill in §15,
including the two deliberately failing runs in §15.4.** Drill 4 is the important one:
it genuinely exercised the failure path — the exact path BUG-051 says leaked — and
produced **zero** volume residue. That is this segment's own independent confirmation
of the registry's and BUG-051's "volume count stable before/after" claim, obtained by
running the cycle rather than by reading the record.

### 15.5 Disposition of the two scenarios' acceptance criteria

| Scenario | Acceptance criteria, as written in `SCENARIOS.md` | This segment's live finding |
|---|---|---|
| **SCN-MOD001-133** | balanced synthetic set passes; deliberately unbalanced set fails citing the specific invariant, proving real detection, not a rubber stamp | **MET.** 23/23 pass live (§15.1); segment 1 §2.2's `v01_t6_only` control shows a genuine defect is detected with the specific anchored invariant message, and §2.3's nine mutants show the detection cannot be suppressed. No CAP-008 dependency |
| **SCN-MOD001-132** | all six placeholder fixtures pass, proving discovery + fixture DB connection + `_shared` tenant resolver are live; deleted-or-broken domain yields a non-zero exit naming that domain | **MET on evidence.** Positive: 6/6 live against a real pinned-digest, loopback-published container (§15.2, §15.3). Negative: both variants, non-zero exit, the specific domain named (§15.4). **Promotion is nevertheless gated — see §18.4 — because this evidence is produced by CAP-008, whose `review_status` is currently `QUALIFIED`, not `APPROVED`** |

## 16. Accurate aggregate state — re-run in full this segment

All commands run from `/Users/ahmadmabrouk/Desktop/Veyro/backend` using `./.venv/bin/...`,
with `-p no:cacheprovider`. Docker volume count recorded around the whole block.

### 16.1 Suites, lint, format, types

| # | Command | Exit | Result | vs segment 1 (disk-full) | vs round 15 |
|---|---|---|---|---|---|
| 1 | `pytest tests/contract/test_financial_invariant_scaffold.py tests/contract/test_domain_scaffold_inventory.py -q` | **0** | **25 passed** in 1.85s | seg 1: `1 failed, 24 passed` — **regression resolved** | round 15: `25 passed` — **restored** |
| 2 | `pytest -q` (full backend) | **0** | **196 passed** in 23.46s | seg 1: `1 failed, 59 passed, 135 errors` — **resolved** | round 15: `195 passed`; **+1 = BUG-051's new regression test**, accounted for exactly |
| 3 | `pytest tests app/modules -q` (incl. the six domain scaffolds) | **0** | **202 passed** in 24.08s | seg 1: `1 failed, 59 passed, 141 errors` — **resolved** | round 15: `201 passed`; **+1 = same new test** |
| 4 | `ruff check .` | **0** | **All checks passed!** | matches | matches |
| 5 | `ruff format --check .` | 1 | **7 files would be reformatted, 42 already formatted** | matches | matches |
| 6 | `mypy --strict app tests` | **0** | **Success: no issues found in 48 source files** | matches | matches |

**Volume count `1` before run 1 and `1` after run 3; container count `1` throughout
(only `frosty_bhabha`).** Three full suites — including every Postgres-backed
integration, authn, migration-safety and tenant-isolation test, plus the six domain
scaffolds — produced **zero** volume residue. Before the fix, each of those sessions
would have leaked one ~40 MB volume (§14.4). This is the strongest available
confirmation that BUG-051's fix holds under real load, and it is this segment's own,
not a citation.

Segment 1's three suite regressions are hereby confirmed **environmental and fully
resolved**, exactly as segment 2 §8.5 predicted. They were never Slice-7 regressions.

### 16.2 The `ruff format` finding is PRE-EXISTING and KNOWN — named, not normalized

Exit 1 on run 5 is a real non-zero exit and is reported as such. The seven files,
enumerated by name this segment:

```
tests/harness/authn.py                            tests/integration/test_architecture_gate_rls.py
tests/harness/migration_safety.py                 tests/integration/test_authn_harness.py
tests/harness/postgres.py                         tests/integration/test_migration_safety_harness.py
tests/harness/tenant_isolation.py
```

**Identical to segment 1's list, file for file.** All seven are Slice-5/6 harness
files; **none is a Slice-7 file**; rounds 13, 14, 15 and 16-segment-1 all record the
same seven. `postgres.py` appears on the list but was already on it before BUG-051
touched it — BUG-051's record independently confirmed this via `git stash`, and the
pre-existing offender visible in the diff output is a long `admin.execute(sql.SQL(...))`
line in `test_architecture_gate_rls.py` and a `docker("run", …)`-era wrapping in
`postgres.py`, neither introduced by the `-v` change.

**Disposition: pre-existing, known, disclosed across four consecutive rounds,
out-of-scope for Slice-7, not a round-16 finding and not a blocker.** Recorded here
only so the non-zero exit is not silently dropped.

### 16.3 Governance validators

**A correction to the dispatch's premise, stated because it matters:** the dispatch
asked this segment to "reuse that list" of governance validators "segment 1's report
names." **Segment 1 named no governance validators** — its §4.1 ran only pytest ×3,
`ruff check`, `ruff format --check`, and `mypy`. There is no segment-1 validator list to
reuse. Rather than invent a new set, this segment ran the project's own standing
aggregate (`knowledge/05-QA/tools/run_regression.py`), which *is* the project's
authoritative definition of its validator set, plus the two validators that bear
directly on this review's charge.

| Validator | Exit / Result | Disposition |
|---|---|---|
| `knowledge/00-System/verify_baselines.py` | **PASS, exit 0** — all 4 governing baseline hashes `[MATCH]` against `PROJECT_INDEX.md` (Blueprint `80f4b381…`, TSD `0d41c8a1…`, EIP `e5b5ec3b…`, design bundle `c96f77ab…`) | Clean. The four governing baselines are unmodified |
| `knowledge/05-QA/tools/capability_drift_check.py` | **PASS** — 8 capabilities checked, no drift | Clean. Notable: it reports **"CAP-008: not yet approved — version/hash snapshot present but not compared, since there is no approval for it to have drifted from."** The tooling independently corroborates §18's premise |
| `knowledge/00-System/validate_capabilities.py` | **PASS** — "7 capability/capabilities, all registered and APPROVED" | **PASS, but see FINDING R16-5 below — CAP-008 is not among the 7** |
| `knowledge/05-QA/tools/run_regression.py` (aggregate) | **FAIL — 3/4 checks passed, 1 N/A** | One failing check; see §16.4 |
| `knowledge/05-QA/tools/resolution_bound.py` | Not run — it is a parameterized budget calculator (`<elapsed_seconds> <tokens_used> <time_limit> <token_limit>`), not a pass/fail validator | Correctly not applicable |

### 16.4 The aggregate regression FAIL — named, and its cause identified

```
[PASS] verify_baselines.py
[PASS] validate_catalog.py        — 0 errors, 1 warning (non-blocking, tracked)
[PASS] validate_capabilities.py   — 7 capabilities, all registered and APPROVED
[FAIL] evidence_integrity_check.py
  - STALE: knowledge/00-System/CURRENT_HANDOFF.md last committed 2026-09-29
    (updated: field says 2026-10-01), but tracked module evidence has a later
    commit dated 2026-10-04
[N/A]  test_bash_guard.py         — CAP-007 RETIRED (OWN-006/ADR-007)
AGGREGATE RESULT: FAIL (3/4 checks passed, 1 N/A excluded)
```

**The single finding is mechanically correct and is an artifact of this project's own
mid-round convention, not a new defect.** Verified directly:
`git log -1 -- knowledge/00-System/CURRENT_HANDOFF.md` → **`Tue Sep 29 08:27:21 2026`
(`e516bed`)**, while `git status` shows that file as ` M` with uncommitted round-15/16
content. The checker compares *committed* dates; this project deliberately does not
commit mid-round (segment 1 §6 and segment 2 §12 both record "no commit" as a
boundary). So the check is right about the committed tree and the working tree is
simply ahead of it.

**Stated honestly rather than normalized away:** this specific `STALE
CURRENT_HANDOFF.md` finding is **not** recorded as a known non-blocking item in
`CURRENT_STATE.md` or `BUG_REGISTRY.md` in this form. `evidence_integrity_check.py`
does have a disclosed defect history (`BUG-033`, P2, OPEN — a hardcoded MOD-000-only
bug-linkage glob), but that is a *different* check within the same tool and is not what
fired here. So: **mechanically correct, cause identified, expected to clear on the
round's commit, not previously disclosed in this specific form, and not a blocker for
this verdict** — but it does mean the project's own aggregate regression currently
reads FAIL, and a reader of this report should know that rather than infer "all
validators green."

### 16.5 FINDING R16-5 (P2) — CAP-008 is in no module capability manifest, so no mechanical gate checks its `review_status`

Found while reconciling `validate_capabilities.py`'s "7 capabilities, all … APPROVED"
against the registry's 8 rows.

- `validate_capabilities.py` validates **`knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml`**, which declares exactly **7** `capability_id`s: **CAP-001 … CAP-007**. **CAP-008 is absent.**
- `grep -rln "CAP-008" knowledge/03-Modules/*/evidence/module-capabilities.yaml` → **no match in any module manifest.**
- `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` is a **surface-profile** manifest (ten §4.3 path/profile entries); it contains **no `capability_id` key at all**, so there is no MOD-001 capability manifest for the validator to read.
- `knowledge/03-Modules/MOD-001/CAPABILITIES.md` mentions **CAP-008 zero times** (`grep -c` → `0`) — it is a 109-line planning-era document predating CAP-008's 2026-09-29 registration, and still describes the test-runner stack as a future "build/select during implementation" decision.

**Consequence, which is the finding:** CAP-008 is the **trust anchor of MOD-001's live
GOV-01-R02 harness** — the one third-party, non-first-party, non-harness-native
capability this module actually executes against — and it is currently
`review_status: QUALIFIED`, **not `APPROVED`**. `CAPABILITY_POLICY.md`'s fail-closed
rule is unambiguous: *"Any capability not present in `CAPABILITY_REGISTRY.md` with
status `APPROVED` is not usable on this project."* Yet **every governance validator
reports PASS on the capability dimension**: `validate_capabilities.py` because CAP-008
is outside the manifest it reads, and `capability_drift_check.py` because it correctly
declines to compare an unapproved row and PASSes anyway. **A module relying on a
non-`APPROVED` third-party capability therefore trips no mechanical gate.** The policy's
fail-closed rule is, for CAP-008, enforced only by agent behavior — the same
single-point-of-failure shape `.claude/rules/global/notion-mcp-scope-discipline.md`
exists to compensate for on CAP-001.

**P2, not P1:** CAP-008 is not an *unqualified* capability treated as trusted — it has
unusually thorough qualification evidence (license provenance from upstream `LICENSE`
files, a pinned image digest, pinned VM/engine/CLI versions, an 8/8 positive+negative
drill set, two prior independent Opus reviews, and a loopback/engine-identity harness
that fails closed). The gap is in **mechanical enforcement and manifest registration**,
not in the underlying assurance. **P2, not P3,** because `CAPABILITY_POLICY.md` stage 7
makes manifest registration a precondition for module reliance ("before any module may
depend on it"), and MOD-001 has depended on it since BUG-038 closed.

**Required remediation (not performed — review-only):** add CAP-008 to a MOD-001
capability manifest that `validate_capabilities.py` actually reads, and refresh
`MOD-001/CAPABILITIES.md` to name it. This is a governance/documentation fix, not a
code change.

## 17. Standing supply-chain / member-data / spend charge — segment 3's portion

Segment 1 §5.6 covered this partially and segment 2 §12.1 covered its own four items,
each explicitly disclaiming whole-round coverage. This completes it for segment 3.

- **Real member data:** none observed, none introduced. Every drill in §14-§16 ran against synthetic fixtures only. The six domain scaffolds assert `SELECT 1` and a `uuid4()`-derived tenant id — no data of any kind, let alone member data. The two probe containers (§14.2) ran an empty `initdb`. The two throwaway trees contained copies of synthetic test fixtures.
- **Credentials:** none read, written, or committed. No `.env`/`.env.local` was read. The two probe containers used the explicitly-fake, clearly-labeled `POSTGRES_PASSWORD=EXAMPLE_NOT_A_REAL_PASSWORD` passed by environment variable, never in argv, per `.claude/rules/infra/secrets.md` control 1. No credential-shaped value appears anywhere in this report. The harness's own `secrets.token_urlsafe(24)` password is never rendered (`field(repr=False)`), independently confirmed by the suite's `test_superuser_password_never_in_docker_argv_or_error` passing in §14.3's control run.
- **Spend:** **none.** No network egress at all this segment — no registry pull (both probes used the already-present pinned image; `docker image inspect` confirmed it locally without a pull), no package install, no paid service, no paid CI tier. Every Docker operation was local.
- **Third-party capability treated as trusted without qualification evidence:** **two to report, neither a fail-closed violation.** (a) `mikeh1975/tradingview-mcp:latest` remains unregistered and unqualified, and remains **not used** by any Veyro code — segment 2 §11.2's finding that the fail-closed rule is not triggered stands, re-verified read-only this segment (§18.2). (b) **CAP-008 itself is currently `QUALIFIED`, not `APPROVED`** — see §16.5 and §18. It is not trusted *without* evidence (its evidence is extensive and was re-verified this segment); the defect is that no mechanical gate notices the status. Everything else this segment ran is harness-native (`Bash`/`Read`).
- **Capability granted broader scope than its stated need:** **two, both disclosed and both re-verified live this segment.** (a) The Colima VM mounts the user home directory **writable** — confirmed live: `lima-3c04c9ed71d6b8a3 on /Users/ahmadmabrouk type virtiofs (rw,relatime)`. Broader filesystem reach than a Postgres fixture needs; accurately disclosed in CAP-008's registered `scope`. (b) The fixture passes **no `--network`** flag (confirmed: `postgres.py:174`'s `docker run` argv has no `--network`), so it shares the default bridge with any co-resident container — accurately disclosed in the registry's 2026-10-04 correction, per segment 2 §11.5 condition 2. **The proportionate fix for (b) remains the one-flag dedicated bridge segment 2 §11.5 condition 3 proposed; it is still not built, still not a blocker.**
- **Owner-reserved restrictions:** none approached. No paid service, no spend, no real member data, no deploy/Production promotion, no material product/pricing/business/architecture/scope change.

## 18. CAP-008 — fresh independent Opus capability-security re-review

`CAPABILITY_REGISTRY.md`'s CAP-008 row and
`CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md` §6 both name "a fresh independent
Opus capability-security re-review" as the next legally allowed action for this row.
**This section is that re-review.** Performed as part of this report given the bounded
dispatch; §18.6 records that a dedicated `capability-evidence/CAP-008/` record may
still be wanted, without letting that defer the verdict.

Per `CAPABILITY_POLICY.md`'s fail-closed rule, "qualification drills themselves (steps
4-5) are the only context where an unregistered or unqualified capability may be
touched, and only against synthetic fixtures." **That is the authority under which
§14-§16's live CAP-008 exercises were run** — a stage 4-5 re-run against synthetic
fixtures exclusively, which is exactly what this row's own stage-9 material-change
return requires.

### 18.1 Registered pins vs the live environment — every one matches

Re-derived this segment, not inherited:

| Registered value | Live observation | Match |
|---|---|---|
| Colima **0.10.3** | `colima version 0.10.3` (`git commit 00f6c297e92a…`) | **Yes** |
| Lima **2.2.0** | `limactl --version` → `limactl version 2.2.0` | **Yes** |
| Docker Engine (server, in-VM) **29.5.2** | `docker info` → `ServerVersion 29.5.2` | **Yes** |
| Docker CLI (client) **29.6.0** | `/opt/homebrew/bin/docker --version` → `Docker version 29.6.0, build fb59821d45` | **Yes** |
| Engine identity tuple `{Name: colima, ServerVersion: 29.5.2, OperatingSystem: Ubuntu 24.04.4 LTS}` | `docker info` → `colima \| 29.5.2 \| Ubuntu 24.04.4 LTS` | **Yes, all three** |
| Pinned CLI realpath `/opt/homebrew/Cellar/docker/29.6.0/bin/docker` | `/opt/homebrew/bin/docker` → `../Cellar/docker/29.6.0/bin/docker`; `os.path.realpath` confirms | **Yes** |
| Pinned image `postgres@sha256:721873c34ceb9f88…` | Live fixture container observed running image id `721873c34ceb` (§15.2) | **Yes** |
| VM: `macOS Virtualization.Framework`, `aarch64`, runtime `docker`, `mountType virtiofs`, socket `~/.colima/default/docker.sock` | `colima status` reports all five identically | **Yes** |

**No version, digest, or provenance drift. `capability_drift_check.py` independently
agrees (PASS, no drift, §16.3).** CAP-008's technical qualification evidence is intact
and current.

### 18.2 A strong positive finding — the P1-1 engine-binding defense is load-bearing *right now*, not theoretically

This was not expected and is the most important thing this re-review found in CAP-008's
favour. The **first `docker` on this machine's `PATH` is Docker Desktop's CLI**:

```
which -a docker  ->  /usr/local/bin/docker            <- FIRST
                     /opt/homebrew/bin/docker          <- the approved one
                     /Users/ahmadmabrouk/.docker/bin/docker
/usr/local/bin/docker -> /Applications/Docker.app/Contents/Resources/bin/docker
docker --version     -> Docker version 29.8.1, build 4a63305      (Docker Desktop's)
/opt/homebrew/bin/docker --version -> Docker version 29.6.0, build fb59821d45  (approved)
```

A harness invoking bare `docker` would **today, on this machine**, run Docker Desktop's
CLI — the exact capability whose licence eligibility is the unresolved question that
drove the whole Colima rebind, and whose activation is withheld. CAP-008's P1-1
remediation (pinned CLI realpath + pinned CLI version check + isolated empty
`--config` + stripped `DOCKER_*` env + explicit `--host` + engine-identity tuple check,
all fail-closed with no mock fallback) is therefore not defence-in-depth against a
hypothetical — **it is the only thing standing between this harness and an unapproved
engine binding, and it works.** The §15 drills passed, which means `_trusted_cli()` and
the version gate both resolved to 29.6.0 while a 29.8.1 Desktop CLI sat earlier on
`PATH`. The suite's own negative tests
(`test_docker_on_path_is_never_used`, `test_desktop_cli_symlinked_at_trusted_path_is_rejected`,
`test_desktop_engine_on_default_route_is_rejected_before_run`,
`test_caller_docker_host_cannot_bypass_engine_identity`) all pass (§14.3 control, §16.1
runs 2-3). **This materially increases confidence in CAP-008's assurance.**

### 18.3 FINDING R16-6 (P3) — prior segments measured the Docker environment through Docker Desktop's CLI

A direct corollary of §18.2, recorded for measurement hygiene rather than as a defect
of substance. Segment 2 §8.1 recorded "Engine versions: client **29.8.1**, server
29.5.2," and BUG-051's §1 records `docker --version -> Docker version 29.8.1, build
4a63305`. Per §18.2 that client is **Docker Desktop's CLI**, not the approved 29.6.0
one — both sessions used bare `docker`, which resolves to `/usr/local/bin/docker`.

Their **figures remain correct** (the ambient Docker context points at the Colima
socket, which is why their volume enumerations matched what the trusted CLI reports),
so no conclusion in segment 2 or BUG-051 is invalidated. The point is narrower and
worth fixing in habit: a capability review of CAP-008 should take its measurements
through CAP-008's own trusted route. **Every Docker observation in this segment
(§13, §14.2, §15, §16.1) used `/opt/homebrew/bin/docker` explicitly** for exactly this
reason. It also explains an inconsistency a reader would otherwise hit: the registry
says CLI 29.6.0, two records say 29.8.1, and both are accurate about different binaries.

### 18.4 Verdict on `review_status`: **KEEP `QUALIFIED` — do NOT restore `APPROVED` on this evidence**

P0 = **0**. P1 = **0**. P2 = **2** (both OPEN, both documentation-only). P3 = **1**.

Stated plainly, because the dispatch asked for a plain answer: **I would not move
CAP-008 to `APPROVED` this segment, and the reason is not the technical evidence —
which is complete, current, and verified by execution above — but the accuracy of the
registry row that `APPROVED` would certify.**

**Blocker 1 — R16-3 (§14.4), P2.** The CAP-008 `scope` field contains a statement I
have empirically disproved: that `--rm` reaped the volume on the happy path and the
leak cost one volume per *failed/erroring* session. The container is still running when
the teardown executes, so the pre-fix leak was one volume per fixture-using session,
unconditionally. `scope` is a **required** supply-chain field under
`CAPABILITY_POLICY.md`, and this false sentence sits *inside the dated correction whose
sole purpose was to make that field truthful* after segment 2 found it untruthful.
Setting `APPROVED` would certify a required field I have proven wrong — the same
species of defect (a claim stronger than the evidence) that this sixteen-round lineage
exists to catch. The present-tense cleanup claim is true; the explanation is not.

**Blocker 2 — R16-5 (§16.5), P2.** `CAPABILITY_POLICY.md` stage 7 requires registration
"**before** any module may depend on it," and CAP-008 appears in **no** module
capability manifest — so `validate_capabilities.py` never evaluates it and no
mechanical gate notices that MOD-001's live harness depends on a non-`APPROVED`
capability. Approving the row without closing this would leave the policy's fail-closed
rule enforced, for this capability, by agent diligence alone.

**This is a conditional hold, deliberately bounded so it cannot become a seventeenth
round of regress.** The conditions are exhaustive, specific, documentation-only, and
require **no new drills**:

1. Correct the "error-path"/"per failed session" characterization in `CAPABILITY_REGISTRY.md`'s CAP-008 `scope` field, in `BUG-051`, in `CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md`, in `postgres.py`'s two teardown comments, and in the regression test's docstring (§14.4 gives the replacement wording).
2. Add CAP-008 to a MOD-001 capability manifest that `validate_capabilities.py` reads, and name it in `MOD-001/CAPABILITIES.md` (§16.5).

**Once those two land, `APPROVED` may be restored by an Opus assurance role on the
strength of this section plus §14-§16, with no further drill required** — §18.1
re-confirmed every pin, §18.2 confirmed the engine binding is load-bearing, §15.2
confirmed digest/loopback/disposability live, and §14.2/§16.1 confirmed zero volume
residue across three full suites. **Nothing technical is outstanding.** A reviewer who
restores `APPROVED` after those edits is not rubber-stamping; the drills are in this
report.

**The Sonnet session's own disposition was correct and is endorsed:** downgrading to
`QUALIFIED` rather than self-re-approving was the right call under
`CAPABILITY_POLICY.md`'s `approved_by` field and its model-routing rule, and the
material-change evidence file is a genuine stage 4-5 re-run, not a self-approval. That
restraint is the reason this re-review had something real to evaluate.

**One documentation conflict to flag:** `VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md` §4
asserts "the capability remains usable" while at `QUALIFIED`.
`CAPABILITY_POLICY.md`'s fail-closed rule says the opposite — "Any capability not
present in `CAPABILITY_REGISTRY.md` with status `APPROVED` is **not usable** on this
project." The practical effect is small (the only use since the downgrade has been
qualification drills, which the policy permits) but the sentence should not stand as
written; it should say the capability is **not usable for real project work** at
`QUALIFIED`, and is touchable only under stage 4-5 drills, pending re-approval.

### 18.5 Carried CAP-008 items, unchanged by this re-review

| Item | Status |
|---|---|
| **R15-5 / R12-4** — co-resident unregistered `mikeh1975/tradingview-mcp:latest` sharing the engine, disk and default bridge | **Segment 2 §11's disposition stands, unchanged.** Not a fail-closed violation (not invoked by any Veyro code); a real scope-minimality deviation requiring **owner** disposition by CAP-008's `next_review_due` **2026-12-31**. Posture re-verified read-only this segment: `netmode=bridge`, `172.17.0.2`, `Privileged=false`, `CapAdd=[]`, no port bindings, only the named `tradingview-mcp-session` mount — no Docker socket, no host bind mounts. Unchanged, untouched |
| Writable home-directory VM mount | Confirmed live (`rw,relatime`), accurately disclosed in the registered scope. Unchanged |
| Dedicated-bridge hardening (segment 2 §11.5 condition 3) | Still not built, still explicitly **not** a blocker. Would close §17(b) at the cost of one flag |

### 18.6 Form of this record

This re-review is recorded here rather than as a separate
`knowledge/05-QA/capability-evidence/CAP-008/` file, per the dispatch's bounded scope.
**A dedicated CAP-008 capability-evidence record is still worth creating** — the
`capability-evidence/CAP-008/` directory is where that row's assurance history lives,
and a future reader looking for "the Opus re-review that followed the volume-leak
correction" will look there first. That is a filing recommendation for the orchestrator
or a later session; it does not qualify or weaken the verdict in §18.4, which is given
in full here.

## 19. FINAL ROUND-16 VERDICT

> ## **PASS — P0 = 0 / P1 = 0 / P2 = 3 / P3 = 4**

No P0 and no P1. Round 16's full charge across all three segments is complete: the
round-15 remediation is independently verified correct and load-bearing (segment 1),
round-15 §12's overclaim is corrected and the open items are disposed (segment 2), and
BUG-051's fix is independently verified by execution with the live CAP-008 drills run
for real and CAP-008 itself re-reviewed (segment 3). Every claim marked PASS below was
either executed by this segment or is explicitly cited to the segment that executed it.

### 19.1 Findings ledger

| ID | Sev | Segment | Finding | Status |
|---|---|---|---|---|
| **R16-1** | **P2** | 2 | CAP-008 Postgres fixture leaked an anonymous Docker volume per container, filling the Colima VM's 20 GB disk (473 volumes / 18.94 GB) and blocking every live Postgres test | **RESOLVED** — filed as BUG-051, fixed, and **independently verified by execution this segment** (§14.2, §14.3, §15, §16.1). Bug not closed by this reviewer |
| **R16-3** | **P2** | 3 | The `scope` field of CAP-008 in `CAPABILITY_REGISTRY.md` — plus BUG-051, the material-change record, two `postgres.py` comments and the new test's docstring — state the leak was *error-path only* / "per failed session". Empirically false: the container is still running at teardown, so the leak was **one volume per fixture-using session, unconditionally** | **OPEN** — documentation-only correction; **blocks CAP-008 → `APPROVED`** (§14.4, §18.4) |
| **R16-5** | **P2** | 3 | CAP-008 appears in **no** module capability manifest and zero times in `MOD-001/CAPABILITIES.md`, so `validate_capabilities.py` never evaluates it and no mechanical gate notices MOD-001 depending on a non-`APPROVED` capability | **OPEN** — governance/documentation fix; **blocks CAP-008 → `APPROVED`** (§16.5, §18.4) |
| **R16-2** | P3 | 3 | `test_financial_invariant_scaffold.py` changed hash after segments 1-2 verified it (docstring-only, correctly disclosed in BUG-050's own round-16 section) — but the dispatch opening this segment did not mention the edit | **OPEN (disclosure/hand-off)** — independently verified docstring-only (§13.1, §15.1) |
| **R16-4** | P3 | 3 | Teardown's `except RuntimeError: pass` comment justifies itself with "`--rm` also reaps it," which is false; and `docker("run", …)` sits outside the `try:` whose `finally` cleans up, so a container created by a failing `run` gets no teardown | **OPEN** — narrow, disclosed, not worth a code change on a test fixture by itself (§14.5) |
| **R16-6** | P3 | 3 | Segment 2 and BUG-051 measured the Docker environment with bare `docker`, which on this machine resolves to **Docker Desktop's** CLI (29.8.1), not CAP-008's approved 29.6.0. Their figures are correct; the habit is not | **OPEN (hygiene)** — explains the 29.6.0-vs-29.8.1 apparent conflict (§18.3) |
| **R16-7** | P3 | 3 | `run_regression.py` aggregate reads **FAIL (3/4)** on `evidence_integrity_check.py`'s `STALE CURRENT_HANDOFF.md`. Mechanically correct — that file last committed 2026-09-29 while evidence trees committed 2026-10-04 — an artifact of this project's mid-round no-commit convention; **not** previously disclosed in this specific form | **OPEN (expected to clear on commit)** (§16.4) |

**Carried, previously disposed, not re-rated and not blocking:** `G1c` walker-blindness
(deliberately open, disclosed, still green — segment 1 §3.2); **R15-5 / R12-4**
co-resident-workload scope-minimality (segment 2 §11 — owner disposition due
**2026-12-31**); the 7-file `ruff format` finding (pre-existing Slice-5/6, four
consecutive rounds, no Slice-7 file — §16.2).

### 19.2 Scenario dispositions

| Scenario | Disposition |
|---|---|
| **SCN-MOD001-133** | **MET — acceptance criteria satisfied on live code, promotable.** Needs no Postgres (verified two ways, §15.1); **23/23 pass live, exit 0**; detection power proven by segment 1's `v01_t6_only` control and by nine mutants that cannot suppress it (§2.3) and three counterfactuals proving the guard is the sole cause of the kills (§2.4). Not promoted by this reviewer — not this segment's authority |
| **SCN-MOD001-132** | **MET on evidence, PROMOTION GATED BY R16-3 + R16-5 (via CAP-008), not by any defect in the scenario.** Positive: **6/6 live** against a real pinned-digest, loopback-published, residue-free container (§15.2), independently re-confirmed through its own CI gate (§15.3). Negative: **both** variants its own text names — broken (`exit 1`, `{'access': 'failed'}`, five others clean) and deleted (`exit 1`, `missing domain scaffold(s): ['access']`) (§15.4). The gate is purely administrative: its evidence is produced by CAP-008, which is `QUALIFIED`, and `CAPABILITY_POLICY.md`'s fail-closed rule makes a non-`APPROVED` capability unusable for real project work. **Two documentation edits (§18.4) clear it with no new drills.** Not promoted by this reviewer |

### 19.3 BUG-050 — **CAN CLOSE**

All four conditions round 15's own "next legally allowed action" set, and the one
precondition segment 2 §9.5 attached, are now satisfied:

1. **Verify the R15-1/R15-2/R15-3/R15-4 fixes by execution** — done, segment 1 §2.3/§2.4: all nine mutants die as collection errors (exit 2), with three counterfactuals reproducing round 15's false cleans exactly, proving the remediation is the sole cause of the kills. Re-confirmed this segment against the file at its **new** hash (§15.1, §14.3 control).
2. **Decide the execution-witness question** — done, segment 2 §9: not required; a `pytest_sessionfinish` witness relocates rather than closes the one irreducible residue.
3. **Re-derive the 6-token query** — done, segment 2 §10: **47 files**, reconciled exactly (45 + the round-16 watchdog checkpoint + this report).
4. **Re-verify both scenarios live with CAP-008** — done, this segment §15. This was the last outstanding item and it is now discharged with real output.
5. **Segment 2 §9.5's closure precondition — correct the inaccurate residual-gap disclosure** — **done by the retained Sonnet session and verified by this reviewer**: `test_financial_invariant_scaffold.py`'s docstring now states all four points segment 2 required — `-k`/`-m` and conftest marker-injection are **not** gaps; in-body `pytest.skip()` is a real, AST-visible, cheap-to-close gap deliberately not built; the one irreducible residue is the file never being collected, controlled by the reviewed CI invocation; `G1c` remains open and disclosed. Read in full this segment (§13.1).

**Nothing technical remains outstanding on BUG-050.** The three P2s in §19.1 are not
BUG-050 findings: R16-1/R16-3 belong to BUG-051 and CAP-008 (segment 2 §8.2 disposed
R16-1 as explicitly **not** a BUG-050 finding, and R16-3 is a correction to that same
record), and R16-5 is a capability-registry gap. **BUG-050 is not closed by this
reviewer** — that is the orchestrator's or a dedicated session's action.

### 19.4 BUG-051 — **CAN CLOSE, conditional on the R16-3 text correction**

The fix is **correct, minimal, in the right place, and independently verified by
execution** (§14.1-§14.3): `-v` is the right instrument for an anonymous volume
declared by `VOLUME` in the pinned image; the leak reproduces on the pre-fix shape and
does not on the fixed one; the single teardown route covers all three consumers; the
regression test genuinely fails on revert and needs no live Docker; and three full
suites plus two deliberately-failing drills produced zero volume residue. The prune was
safe and `tradingview-mcp-session`/`frosty_bhabha` are verifiably untouched.

**The one thing to fix before closing is R16-3** — the bug's own title and body
misdescribe when the leak occurred. Closing a bug on an inaccurate root-cause
description is the defect this lineage exists to catch, and the remedy is a wording
change, not more work. **Not closed by this reviewer.**

### 19.5 CAP-008 — **KEEP `QUALIFIED`**

P0=0 / P1=0 / P2=2 (R16-3, R16-5) / P3=1 (R16-6). Every registered pin matches live,
no drift, and the P1-1 engine-binding defense was found to be actively load-bearing
(§18.2 — Docker Desktop's CLI is first on `PATH` on this machine). **`APPROVED` is
withheld only because two required-field/manifest accuracy conditions are open; both
are documentation-only and neither requires a new drill.** Full reasoning and the exact
two conditions: §18.4. Registry **not edited** by this reviewer.

## 20. Segment 3 close — boundaries honored

| Boundary | Status |
|---|---|
| Docker volume pruned | **None.** No `docker volume prune` (or `-a`, or `docker system prune`) was run in any form. The only volume removal was `docker volume rm <exact-id>` on the single anonymous volume **this segment's own probe container created** (§14.2) — disclosed, not a prune |
| `frosty_bhabha` touched | **No.** Read-only `docker inspect`/`docker ps` only. Still `Up 2 days`, image, mounts, network and privileges unchanged |
| `tradingview-mcp-session` volume | **Untouched.** Present at segment start and end; the only volume on the engine at both points |
| Containers created by this segment | Two probes (`r16s3probeA`, `r16s3probeB`) plus the harness's own disposable fixture containers. **All removed.** Final state: `docker ps -a` → `frosty_bhabha` only; `docker volume ls` → `tradingview-mcp-session` only; VM disk **5% (793M/20G)**, unchanged from segment start |
| Files under `backend/` edited | **None.** `postgres.py`, the unit test and the three Slice-7 files were read only. End-of-segment hashes identical to start: `8988b3e0…`, `b7cd06f1…`, `c55fa514…`, `4672daec…` (postgres.py), `56305e45…` (unit test) |
| SCN-MOD001-132 / 133 | **Not promoted** |
| BUG-050 / BUG-051 | **Not closed** |
| `REVIEW_IN_FLIGHT.md` | **Not edited** |
| `CAPABILITY_REGISTRY.md` | **Not edited.** CAP-008 verdict stated in §18.4 for the orchestrator or a later session to apply |
| `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `BUG_REGISTRY.md`, `SCENARIOS.md`, `STATUS.md`, `BUG-050…md`, `BUG-051…md` | Read where needed, **not modified** |
| `git rev-parse HEAD` | `b86446dcd283a5afeb86c612fb2657f769268748` at segment start **and end** — unchanged |
| Commit / push | **None** |
| Repository writes by this segment | **Two, both disclosed.** (1) This report. (2) `knowledge/05-QA/tools/regression-runs/RUN_20261004T013017Z.txt` — **unintended**: `run_regression.py --help` does not print usage, it executes the aggregate run and writes its own record. An append-only evidence artifact in the runs directory recording a real run; no governed file touched. Recorded rather than quietly left |
| Throwaway artifacts | `/tmp/r16s3rev/` (revert-check trees), `/tmp/r16s3neg/tree/` (negative-case tree), and all `/tmp/r16s3_*.txt` capture files — all outside the repository, all **deleted** at segment end |
| Owner-reserved restrictions | None approached — no spend, no paid service, no real member data, no Production promotion, no material scope change (§17) |

## 21. Reviewer identification (for orchestrator-side `mr_verify.py`)

- **Resolved runtime model identity, as reported by this session's own environment:** `claude-opus-5` (named `Opus 5`).
- **No self-attestation performed.** Following rounds 13-15 and segments 1-2, this reviewer did **not** run `mr_verify.py` against its own transcript; independent attestation with arguments `opus veyro-security-reviewer` is the orchestrating session's job.
- **No memory of prior rounds.** Segments 1 and 2 were read as documents, in full; every figure this segment relies on from them is cited to them explicitly, and every figure this segment asserts was executed here.
