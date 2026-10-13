---
doc: BUG-051
status: CLOSED (2026-10-04, round 16 segment 3's independent re-review, 120/120 turns `claude-opus-5` orchestrator-attested) — fix verified correct/minimal/sufficient by execution (§14.1-14.3), R16-3's root-cause misdescription corrected in every location the review named, conditional closure criterion satisfied
module: MOD-001
severity: P2
filed: 2026-10-04 (round 16, R16-1 — GOV-01-R02 Slice-7 independent security review, segment 2)
---

# BUG-051 — CAP-008 Postgres fixture leaked an anonymous Docker volume every fixture-using session, unconditionally

**Title corrected 2026-10-04 (round 16 segment 3, R16-3):** the original title said "on the error-path teardown." That is false — see "The defect" below for the corrected mechanism.

## Why this is a separate bug, not a BUG-050 finding

Round 16 (segment 2, §8.2) gave this disposition explicitly, and it is
adopted here rather than re-derived: BUG-050 is a *false-clean* bug
across all fifteen prior rounds — the harness reporting green when a
financial invariant or domain scaffold is genuinely broken. This defect
is the opposite failure mode — the suite goes loudly red (fail-closed,
non-zero exit, every domain named as not-confirmed) — so folding it into
BUG-050 would blur the one distinction that lineage exists to sharpen.
The fix also lands in a different file (`tests/harness/postgres.py`,
plus a `CAPABILITY_REGISTRY.md` scope correction) than any of BUG-050's
Slice-7 fixes, and it outlives BUG-050: the leak affects every CAP-008
consumer (Slice-5's tenant-isolation, authn, and migration-safety
harnesses all share this same fixture), not only Slice-7's two files.

## The defect

**Corrected 2026-10-04 (round 16 segment 3, R16-3) — this section previously
described the defect as an error-path-only leak, "one ~40MB leak per
failed/erroring session." That was false, disproved by direct, empirical
before/after testing on the live engine (round 16 §14.2), not merely argued:
the leak occurred on every single fixture-using session, unconditionally,
whether it succeeded or failed.** The corrected mechanism:

`backend/tests/harness/postgres.py`'s `disposable_postgres()` context
manager runs `docker run -d --rm ...` against the pinned `postgres:16-alpine`
image, which declares `VOLUME /var/lib/postgresql/data` — so every container
Docker creates gets an anonymous data volume. `--rm` only reaps a container
that **exits on its own**; this container never does (`postgres` runs until
killed). So on every invocation — not only a failing one — the `finally`
block is reached with the container still running, and the `rm` call there,
not `--rm`, is what actually removes it. Before the fix, that call was plain:

```python
docker("rm", "-f", name)
```

No `-v`. Since this call — not `--rm` — removes the container on every path,
its anonymous volume survived every single time: a leak with no ceiling,
roughly ~40MB per fixture-using pytest session (success or failure alike),
on a fixed-size 20GB Colima VM disk. This simpler mechanism is also the
better explanation of the observed evidence: 472 orphaned volumes
accumulated in roughly two days (round 16 §14.4), far more sessions than this
lineage had failures in that window.

## How it was found and how severe it got

Round 16 segment 1 hit a transient-looking `No space left on device`
error while trying to run a live CAP-008/Postgres drill, traced it past
a first dead end (231GiB free on the *host* — the wrong disk), and found
the Colima VM's own `/var/lib/docker` at **100% (19G/20G) full**.
`docker system df` showed **473 local volumes, 472 dangling, 18.94GB,
100% reclaimable**. `colima ssh -- ls -l /var/lib/docker/volumes`
dated the accumulation to 2026-10-03/04 — i.e. across this very
BUG-050 review lineage's own repeated suite runs. Segment 2 (§8.1)
independently re-derived every figure from scratch and confirmed them
exactly. This session (round-16 bounded continuation) re-derived them a
third time, independently, before touching anything (see §1 below).

**Impact while unfixed:** every Postgres-backed test failed closed with
`psycopg.OperationalError: ... could not receive data from server` —
136 occurrences in one full-suite run, zero other error classes. The
disposable-Postgres container itself failed to start
(`FATAL: could not write to file "pg_wal/xlogtemp.33": No space left on
device`). SCN-MOD001-132's live acceptance criteria could not be
re-verified in this environment at all until this bug's fix shipped.

## Severity: P2 (round 16's rating, confirmed here)

**Not P1**: fail-closed throughout. The inventory check reported
`domain scaffold inventory not clean (exit=4)` naming all six domains as
not-confirmed rather than claiming a false pass; no real member data is
involved (synthetic fixtures only); no credential or spend is
implicated.

**Not P3**: three properties lift it above housekeeping — (i) it is a
self-inflicted availability failure of a blocking test gate
(`.claude/rules/backend/performance.md` control 3: "No gate is
skippable under load... through a timeout, a resource-exhausted CI
runner"); (ii) it contradicted CAP-008's own registered scope text
("force-removed on exit"), a material registry-accuracy defect under
`CAPABILITY_POLICY.md` stage 9 independent of the disk being full; (iii)
it is monotonic and unbounded on a fixed-size disk, guaranteed to recur
on a schedule set only by how often the suite runs.

## Fix (this session, retained routine-implementation tier)

### 1. Independent re-verification before touching anything

Re-derived, not inherited:

```
docker system df                                    -> Local Volumes 473 ACTIVE 1 SIZE 18.94GB RECLAIMABLE 18.94GB (100%)
docker volume ls -q | wc -l                          -> 473
docker volume ls -f dangling=true -q | wc -l         -> 472
docker volume ls -f dangling=false --format '{{.Name}}'                -> tradingview-mcp-session
docker volume ls -f dangling=true --format '{{.Name}} {{.Labels}}' | grep -v com.docker.volume.anonymous
                                                      -> (empty — every dangling volume is anonymous)
docker ps --filter name=frosty_bhabha --format '{{.Names}} {{.Image}} {{.Status}}'
                                                      -> frosty_bhabha mikeh1975/tradingview-mcp:latest Up 2 days
docker inspect frosty_bhabha --format '{{json .Mounts}}'
                                                      -> [{"Type":"volume","Name":"tradingview-mcp-session", ... }]  (only mount)
docker volume prune --help                           -> "-a, --all  Remove all unused volumes, not just anonymous ones"
```

All figures matched round 16's independently-derived numbers exactly.
Two independent safety mechanisms confirmed before any deletion: (a)
reference counting — `tradingview-mcp-session` is mounted by the
running `frosty_bhabha`, so it has a non-zero reference count and is
excluded from the dangling set; (b) the anonymous-only default on this
Docker version (29.8.1) — `docker volume prune -f` without `-a` removes
only anonymous volumes, and `tradingview-mcp-session` is named, not
anonymous, so it would be excluded even in the counterfactual where
`frosty_bhabha` were stopped.

### 2. Cleanup

```
docker volume prune -f
```

No `-a`, no `docker system prune`. Result: **472 volumes removed, 1
remaining** (confirmed `docker volume ls -q | wc -l` → `1`,
`docker volume inspect tradingview-mcp-session` still present at
`/data`, `docker ps --filter name=frosty_bhabha` still `Up`, untouched).
`colima ssh -- df -h /var/lib/docker`: **100% (19G/20G) → 5%
(793M/20G)**, 18.94GB reclaimed.

### 3. Root-cause fix

`backend/tests/harness/postgres.py:202`  (corrected 2026-10-04, round 17/R17-3 — the comments added for R16-3 shifted this call's line number; the citation was not updated to match until now):

```diff
- docker("rm", "-f", name)
+ docker("rm", "-f", "-v", name)
```

**Corrected 2026-10-04 (round 17, R17-1 — fresh independent Opus
capability-security assurance review, `CAP008-POST-R16-INDEPENDENT-ASSURANCE-2026-10-04.md`):
this sentence itself still asserted the disproven error-path/happy-path
framing, inside the very file whose correction it was meant to complete.**
`-v` removes the container's anonymous volume(s) along with the container
on this teardown call. Per the corrected "defect" section above, this call
is the *only* teardown route and it runs on every invocation — `--rm`
never fires, because the container never exits on its own, so there is
no separate happy-path cleanup for this to "match."

### 4. Regression check added

`backend/tests/unit/test_harness_postgres_fail_closed.py`:
`test_error_path_teardown_removes_the_anonymous_volume` (name retained for
continuity with existing records; **the teardown it pins runs on every
invocation, not only an error path** — see the corrected "defect" section
above and the test's own corrected docstring) — pins the teardown's exact
argv via the file's existing fake-docker-CLI test harness (no live
Docker/CAP-008 needed to run it). The pre-existing
`test_port_and_cleanup_use_the_same_trusted_route`'s own assertion was
also updated to expect `-v` in the teardown argv, since it already
pinned this call's shape and would otherwise now be silently wrong.

**Confirmed load-bearing, not tautological:** reverted the fix in a
throwaway copy of `tests/` (`/tmp/bug051check/`, deleted after use, real
tree never touched) and re-ran both tests — both fail without `-v`,
both pass with it.

### 5. Live verification

| Check | Before | After |
|---|---|---|
| `docker volume ls -q \| wc -l` before a real Postgres smoke (`test_domain_scaffold_inventory.py`, live CAP-008 container) | 1 | 1 (unchanged) |
| `docker volume ls -q \| wc -l` before/after the focused Slice-7 pair, full backend suite, full suite incl. six domain scaffolds | 1 | 1 (unchanged) |
| Focused pair | — | **25/25 PASS** |
| Full backend | — | **196/196 PASS** (195 + 1 new regression test) |
| Full incl. six domain scaffolds | — | **202/202 PASS** (201 + 1 new regression test) |
| `ruff check .` | — | **All checks passed!** |
| `ruff format --check` on the two touched files | — | one pre-existing, unrelated formatting finding in `postgres.py` (a `docker("run", ...)` call predating this fix — confirmed via `git stash`/`ruff format --check` that it exists identically on the pre-fix file; `postgres.py` is already one of the 7 pre-existing Slice-5/6 files rounds 13-16 record as out-of-scope for reformatting) |
| `mypy --strict app tests` | — | clean |

## Companion registry correction

`CAPABILITY_REGISTRY.md`'s CAP-008 row claimed the fixture is
"force-removed on exit" — true of the container, not (until this fix)
its volume. Corrected in place, dated, original text preserved, per
`CAPABILITY_POLICY.md` stage 9's "material change... mandatory return to
stage 4-5" rule. `review_status` corrected from `APPROVED` to
`QUALIFIED` (`qualified_by`: Sonnet) — **not** self-advanced to a fresh
`APPROVED`, since only an Opus assurance role may set that per this
policy's own `approved_by` field definition. Full material-change
record: `knowledge/05-QA/capability-evidence/CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md`.
Two further scope-text corrections staged in the same edit, per round
16 §11.5's conditions (not blockers, but required disclosures): the
loopback-publish guard narrowed to describe host-reachability only (it
does not isolate from in-VM bridge peers), and the co-resident
unregistered `mikeh1975/tradingview-mcp:latest` workload disclosed in
the scope field the same way the writable home-mount already is.

## What this fix does not touch

- R15-5/R12-4 (CAP-008 scope-minimality — the co-resident container's
  mere presence) — round 16 §11 disposed of this as non-blocking,
  requiring owner disposition by CAP-008's `next_review_due`
  (2026-12-31), not a code fix. Untouched by this bug.
- The optional dedicated-bridge-network hardening round 16 §11.5
  condition 3 proposed — explicitly not a blocker, left for a future
  round.
- BUG-050 and its own open findings — unrelated, untouched, still OPEN.

## Closed (2026-10-04)

**Round 16 segment 3** (orchestrator-attested 120/120 turns `claude-opus-5`
across the full round) independently re-verified this fix by execution,
not by reading this record: re-derived every safety figure from scratch
(§13 of the review); confirmed `-v` is the correct and sufficient
mechanism via direct inspection of the pinned image's declared `VOLUME`
and a search across the whole backend tree confirming one teardown route
covers all three consumers (§14.1); reproduced the leak on the live
engine with the pre-fix shape and confirmed its absence with the fixed
shape, using a real container cycle, not inference (§14.2); independently
reverted the fix in a throwaway copy and confirmed both regression tests
fail, with the right message (§14.3); and ran three full suites plus two
deliberately-failing live drills against real CAP-008 Postgres with zero
volume residue in every case (§15, §16.1).

**The one blocking finding, R16-3 — this record's own title and body
misdescribed the leak as error-path-only/per-failed-session when it was
unconditional, once per fixture-using session — is corrected above**, in
`CAPABILITY_REGISTRY.md`'s CAP-008 scope field, in
`CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md`, in `postgres.py`'s
two teardown comments, and in the regression test's docstring/assertion
message. Round 16 §19.4 named this correction as the one precondition for
closure: "the fix is correct, minimal, in the right place, and
independently verified by execution... the one thing to fix before
closing is R16-3... the remedy is a wording change, not more work."
That condition is satisfied.

Closed by the retained routine-implementation tier, on the strength of
round 16's own independently-attested verdict (§19.1: R16-1 **RESOLVED**)
plus this session's correction of R16-3 — not a self-certification of
security judgment, which round 16 itself already performed and recorded.
`REVIEW_IN_FLIGHT.md` was `CLEAR` at this session's start (round 16's
report complete, independently attested) and remains untouched — no
review dispatched this turn.

## Addendum, round 17 (2026-10-04): the R16-3 correction above was itself still wrong in one place — now fixed

A fresh independent Opus capability-security assurance review
(`CAP008-POST-R16-INDEPENDENT-ASSURANCE-2026-10-04.md`, agentId
`aa793a97c80f82668`, `mr_verify.py` PASS 70/70 `claude-opus-5`),
dispatched specifically to verify whether this bug's own R16-3 closure
condition had actually landed, found **R17-1 (P2)**: this file's own §3
"Root-cause fix" section (two sentences above the diff block) still read
"`-v` removes the container's anonymous volume(s) along with the
container on this teardown path too, **matching what `--rm` already does
on the happy path**" — the exact disproven happy-path/error-path framing
R16-3 corrected everywhere else, surviving in the one place this record's
own closure was staked on. Self-contradicted this file's own corrected
"defect" section 100 lines above, and the `status:` front-matter closed
this bug on the false premise that the correction was complete in every
location.

**Corrected the same day** with the reviewer's own supplied replacement
text (§3 above now reads correctly: the teardown call is the *only*
route and runs on every invocation, so there is no separate happy path
for `-v` to "match"). The reviewer also found the line-number citation
here (`postgres.py:189`) stale — the comments added for R16-3 shifted
the real teardown call to line 202 — filed as **R17-3 (P3)**, also
corrected the same day, here and in `CAPABILITY_REGISTRY.md` and
`CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md`.

This bug remains **CLOSED** — R17-1/R17-3 are corrections to this
record's own text, not new defects in the fix itself, which the same
review re-confirmed sound (`-v` fix live at line 202, both regression
tests still accurate). Not independently re-reviewed after this
addendum; the correction is bounded and mechanical (an exact
reviewer-supplied sentence), consistent with the review's own finding
that "nothing technical is outstanding."
