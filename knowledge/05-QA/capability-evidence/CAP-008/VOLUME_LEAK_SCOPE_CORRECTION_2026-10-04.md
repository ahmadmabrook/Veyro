---
doc: CAP-008_VOLUME_LEAK_SCOPE_CORRECTION
status: LIVE — material-change evidence, staged per CAPABILITY_POLICY.md stage 9; NOT a self-approval
date: 2026-10-04
session: retained routine-implementation (Sonnet), continuing the BUG-050 Slice-7 ACPX lineage, round-16 bounded continuation
---

# CAP-008 material-change evidence: anonymous-volume leak fix + scope-text correction

## Why this file exists

`CAPABILITY_POLICY.md` stage 9: "a material change to a capability
(version bump, scope change, provenance change) triggers a mandatory
return to stage 4-5 before continued reliance." Round 16's independent
Opus security review (segment 2, §8.2 point (ii)) found that CAP-008's
registered `scope` field states the fixture is "force-removed on exit,"
when in fact only the container was force-removed — its anonymous
Postgres data volume was retained, which is a material divergence
between registered and actual behavior under this policy. Round 16
§11.5 separately found the registered scope omits a disclosure of the
co-resident unregistered workload sharing the same engine/disk, and
that the loopback-publish guard is described more broadly than what it
actually constrains.

**Corrected 2026-10-04, round 16 segment 3 (finding R16-3, P2): this
file's own first-pass correction (below, superseded in substance by
this notice, original text preserved for history) itself misdescribed
*when* the leak occurred, calling it "the error-path teardown" and "per
failed/erroring session."** Empirically disproved by a real container
cycle on the live engine (round 16 §14.2): the container is still
running when the `finally` block's teardown executes — it never exits
on its own, so `--rm` never reaps it — so that `rm` call removes the
container on **every single invocation**, not only a failing one. The
pre-fix leak was therefore one anonymous volume per fixture-using
pytest session, unconditionally, not one per failure. See §2 below for
the corrected account; the original §2 text is preserved beneath it,
struck through in substance only (not deleted), per this project's
standing convention of correcting records in place rather than erasing
them.

This file is the stage 4-5 re-run this session performed in response —
**evidence for the orchestrator/a fresh Opus reviewer to evaluate, not a
re-approval**. Per `CAPABILITY_POLICY.md`'s own `approved_by` field
definition, only an Opus assurance role may set `review_status:
APPROVED`. This session is Sonnet-tier routine implementation and does
not do so.

## 1. Independent re-verification of round 16's findings (this session)

Re-derived from scratch, not inherited:

```
docker system df            -> Local Volumes  473  ACTIVE 1  SIZE 18.94GB  RECLAIMABLE 18.94GB (100%)
docker volume ls -q | wc -l                        -> 473
docker volume ls -f dangling=true -q | wc -l       -> 472
docker volume ls -f dangling=false --format '{{.Name}}'  -> tradingview-mcp-session
docker volume ls -f dangling=true --format '{{.Name}} {{.Labels}}' | grep -v com.docker.volume.anonymous
                                                    -> (empty — every dangling volume is anonymous)
docker ps --filter name=frosty_bhabha --format '{{.Names}} {{.Image}} {{.Status}}'
                                                    -> frosty_bhabha mikeh1975/tradingview-mcp:latest Up 2 days
docker inspect frosty_bhabha --format '{{json .Mounts}}'
                                                    -> [{"Type":"volume","Name":"tradingview-mcp-session", ...}]  (only mount)
docker volume prune --help                         -> "-a, --all  Remove all unused volumes, not just anonymous ones"
docker --version                                   -> Docker version 29.8.1, build 4a63305
```

All figures match round 16 segment 1/2's independently-derived numbers
exactly. The two safety mechanisms round 16 §8.3 proved (reference
counting excludes the named, in-use `tradingview-mcp-session`; the
anonymous-only default excludes it a second, independent way even in the
counterfactual) were re-checked directly above rather than trusted from
the report.

## 2. Remediation performed this session

**Cleanup (owner-authorized per the round-16 review's own safety proof,
re-verified independently above before running):**

```
docker volume prune -f
```

No `-a`. Result: **472 volumes removed, 1 remaining
(`tradingview-mcp-session`)**, confirmed by `docker volume ls -q | wc -l`
→ `1` and `docker volume inspect tradingview-mcp-session` still present
at `/data`. `docker ps --filter name=frosty_bhabha` confirmed still `Up`,
untouched. `colima ssh -- df -h /var/lib/docker`: **100% (19G/20G) →
5% (793M/20G)**, 18.94 GB reclaimed.

**Root-cause fix (`backend/tests/harness/postgres.py:202`, corrected 2026-10-04, round 17/R17-3 — the R16-3 comment additions shifted this call's line number, uncorrected here until now):**

```diff
- docker("rm", "-f", name)
+ docker("rm", "-f", "-v", name)
```

**Regression check added** (`backend/tests/unit/test_harness_postgres_fail_closed.py`,
`test_error_path_teardown_removes_the_anonymous_volume`, name retained for
continuity): pins the teardown's exact argv — the call that runs on
**every** invocation, not only an error path, since the container never
exits on its own and so is never reaped by `--rm` — via the file's
existing fake-docker-CLI harness (no live Docker needed to run it).
Confirmed load-bearing by reverting the fix in a throwaway copy and
re-running: both this new test and the pre-existing
`test_port_and_cleanup_use_the_same_trusted_route` fail without `-v`,
pass with it.

**Live verification:** volume count recorded before and after a real
Postgres smoke (`test_domain_scaffold_inventory.py`, real CAP-008
container) and the full backend suite — **stable at 1 in both cases**,
confirming the fixed teardown leaves no residue on any run. Full
detail/exact commands/counts: BUG-051's own bug record and this round's
`CURRENT_STATE.md`/`CURRENT_HANDOFF.md` checkpoint.

**Corrected 2026-10-04, round 16 segment 3 (R16-3):** this paragraph
and the one above previously said "the happy path (`--rm`) and the
now-fixed error path both leave no residue" and described the pinned
call as "the error-path teardown." Both phrasings are wrong in the same
way: `--rm` never fires for this harness's containers (they never exit
on their own), so there is no separate "happy-path" cleanup route to
contrast against an "error path" — the single `rm -f -v` call in the
`finally` block is the *only* teardown mechanism, and it runs
identically on every invocation, successful or not.

## 3. Scope-text correction (CAPABILITY_REGISTRY.md, CAP-008 row)

The registered `scope` field is corrected in place, dated, original text
preserved per this project's standing convention (never silently
rewritten):

- **"Force-removed on exit"** — now accurate for both the container and
  its anonymous volume, following the fix in §2 above. **Corrected
  2026-10-04, round 16 segment 3 (R16-3): this bullet previously said
  the pre-fix state was "container force-removed, volume retained on
  the error path" — false. The container is never reaped by `--rm` at
  all (it never exits on its own); the `finally` block's `rm` call
  removes it on every invocation. Pre-fix, that left the volume behind
  on every fixture-using session, not only a failing one.**
- **Co-resident unregistered workload disclosed.** The scope field now
  names the shared-engine condition the same way it already discloses
  the writable home-directory mount, per round 16 §11.5 condition 1.
- **Loopback claim narrowed.** The scope field now states the
  loopback-publish guard constrains *host* reachability, not general
  network isolation, per round 16 §11.4(b)/§11.5 condition 2 — it does
  not constrain in-VM bridge peers on the same default Docker bridge
  network.

## 4. Review status — explicitly NOT advanced to a fresh APPROVED

Per `CAPABILITY_POLICY.md`'s `approved_by` field ("Opus assurance role
that independently reviewed the evidence and made the final
APPROVED/REJECTED/BLOCKED decision"), this session does not set
`review_status: APPROVED`. The registry row's `review_status` is
corrected from its prior `APPROVED` (2026-10-02, against the
since-corrected scope text) to **`QUALIFIED`** (`qualified_by`: Sonnet,
`qualified_date`: 2026-10-04), reflecting that this session re-ran the
stage-5 positive/negative evidence against the *corrected* scope text and
fix, but that a fresh independent Opus capability-security review of
this corrected state — the only role that may restore `APPROVED` — has
not yet run. This mirrors the exact precedent this registry row itself
already used on 2026-10-02 ("CAP-008 rebind MADE CONCRETE": `qualified_by:
Sonnet`, never self-set to `APPROVED`).

**This is a disposition, not a deferral — and it is also not a license
to keep using the capability for real work.** **Corrected 2026-10-04,
round 16 segment 3 (§18.4's flagged documentation conflict): this
section previously said "the capability remains usable," which
contradicts `CAPABILITY_POLICY.md`'s own fail-closed rule — "Any
capability not present in `CAPABILITY_REGISTRY.md` with status
`APPROVED` is not usable on this project."** CAP-008 is not revoked, and
its qualification evidence is sound per round 16 §7.1/§18.1 (re-confirmed
above and by segment 3's own independent re-review), but at `QUALIFIED`
it is **not usable for real project work** — the only thing this status
permits is further stage 4-5 re-qualification drills against synthetic
fixtures (the exact carve-out round 16 segment 3's own live exercises
relied on), while awaiting the fresh Opus re-review this file stages
evidence for.

## 5. What this session did NOT do

- Did not touch `frosty_bhabha` (inspected read-only only).
- Did not run `docker system prune` or `-a`/`--all` on the volume prune.
- Did not create the optional dedicated-bridge-network hardening round 16
  §11.5 condition 3 proposed (not a blocker; left for a future round's
  own charge, consistent with the dispatch's bounded scope).
- Did not mark `review_status: APPROVED`, did not close BUG-051, did not
  close BUG-050, did not promote SCN-MOD001-132/133.
- Did not commit or push.

## 6. Next legally allowed action

A fresh independent Opus `veyro-security-reviewer` (or capability-security
reviewer) re-reviews this corrected scope text and the fix/regression-test
evidence above, and either restores `review_status: APPROVED` or raises
new findings — before CAP-008's `next_review_due` (2026-12-31), and
before this correction is treated as final.
