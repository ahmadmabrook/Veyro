---
doc: CAP-008_COLIMA_REBIND_PROPOSAL
capability: CAP-008 — proposed rebind from Docker Desktop to Colima/Lima local engine
status: PROPOSAL ONLY — stage 4/5 evidence gathered fresh this session; NOT self-approved; fresh independent Opus review still required
run_by: Sonnet (claude-sonnet-5), 2026-10-02 ~22:40-22:44 UTC (host clock; repo dates read 2026-10-01 at time of run)
supersedes_for_decision_purposes: nothing — this is additive evidence alongside COLIMA_ALTERNATIVE_DRILL_2026-10-01.md, not a replacement of it
---

# CAP-008 — proposed material rebind to Colima/Lima (concrete, reviewable proposal)

**2026-10-02 addendum:** The candidate binding was registered as `QUALIFIED`,
then a fresh attested Opus review returned **BLOCKED P0=0/P1=2**. The
required harness-routing and VM-provenance remediation is recorded in
`COLIMA_OPUS_REVIEW_2026-10-02.md` and `COLIMA_VM_PROVENANCE_2026-10-02.md`.
The Moby default-branch licence caveat below is superseded by the exact
[`docker-v29.5.2` tag licence](https://raw.githubusercontent.com/moby/moby/docker-v29.5.2/LICENSE).
This file remains the original Sonnet qualification evidence, not an approval.

This file packages the prior session's Colima candidate drill
(`COLIMA_ALTERNATIVE_DRILL_2026-10-01.md`) together with this session's
own independent re-verification into one concrete proposal for whoever
runs the required fresh Opus review. **It does not itself change
`CAP-008`'s `review_status`, does not mark anything `APPROVED`, and does
not close `BUG-038`.** `CAPABILITY_POLICY.md` stage 9 ("a material
change — version bump, scope change, provenance change — triggers a
mandatory return to stage 4-5") governs here: swapping the local engine
backing CAP-008 from Docker Desktop to Colima/Lima is exactly that kind
of provenance change, so stages 4 and 5 were re-run against the new
binding rather than assumed carried-over.

## Why a rebind is being proposed at all

The Docker Desktop binding's blocker (`provenance_and_license.md`,
`QUALIFICATION_RECORD.md`) is that this repository has no fact
establishing which Docker Desktop free-use category applies to this
project/owner, and the owner-reserved no-paid-services rule means that
ambiguity cannot be resolved by assumption. Colima + Lima are MIT /
Apache-2.0 respectively — permissive, no field-of-use or company-size
restriction of any kind — so a Colima-backed engine removes that
blocker's root cause entirely rather than working around it. This is a
**proposal to change what CAP-008 is bound to**, not a claim that the
Docker Desktop row was secretly fine all along.

## Stage 4 (independent evaluation) — upgraded this session beyond package metadata

The prior drill correctly flagged that Homebrew formula metadata alone
is "not a full supply-chain audit." This session fetched the official
upstream `LICENSE` files directly (not brew's description field):

- `github.com/abiosoft/colima` tag `v0.10.3` → MIT License (confirmed
  from the tagged-version file itself).
- `github.com/lima-vm/lima` tag `v2.2.0` → Apache License 2.0 (confirmed
  from the tagged-version file itself).
- `github.com/moby/moby` (Docker Engine, running server version 29.5.2
  inside the Colima VM) → Apache License 2.0 (tagged `v29.5.2` file was
  unavailable — HTTP 404 — so this is confirmed from the current default
  branch, which has carried the same root `LICENSE` for the project's
  entire history; not a per-tag re-verification).
- `github.com/docker/cli` (client, local version 29.6.0) → Apache
  License 2.0 (same default-branch caveat as above).

No non-standard/restrictive terms, no field-of-use or revenue/size
threshold, no paid-tier distinction, in any of the four. This is a
strictly weaker licensing-risk profile than the Docker Desktop binding,
not a sideways move.

## Stage 5 — fresh positive and negative drills, this session, raw results

Preconditions checked first: HEAD `e516bedabf3d654ad3ae16d948b8f3522739ddc2`
unchanged, 97 pre-existing uncommitted/untracked paths preserved, Colima
VM already running (not started by this session — `colima status`
confirmed running before any drill), Docker Desktop app confirmed not
running throughout.

**Positive** — real `disposable_postgres()` invocation against the live
Colima-backed engine:
```
host/port: 127.0.0.1 32771
version: PostgreSQL 16.15 on aarch64-unknown-linux-musl, compiled by ...
select 1+1 -> 2
POSITIVE DRILL PASS
exit:0
```
Loopback binding confirmed (`127.0.0.1`, asserted in-script, not just
eyeballed). `docker ps -a --filter name=veyro-mod001-harness` → empty
immediately after teardown (zero leftovers). Separately confirmed the
pinned digest is what actually ran: `docker image inspect
postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`
→ `RepoDigests` matches exactly, `Architecture: arm64`.

**Negative** — fail-closed with an unreachable engine, Colima VM left
running and untouched (verified both before and after):
```
env DOCKER_HOST=unix:///tmp/veyro-cap008-no-daemon-<ts>.sock <harness invocation>
FAIL-CLOSED CONFIRMED: `docker run` exit 1: failed to connect to the
docker API at unix:///tmp/veyro-cap008-no-daemon-<ts>.sock; ...
exit:0
```
Clean `RuntimeError`, no mock/fallback. `docker ps -a --filter
name=veyro-mod001-harness` → empty after this drill too. The isolated
bad `DOCKER_HOST` approach (rather than stopping the real VM) was chosen
deliberately to get a genuine unreachable-engine negative result without
disturbing host state this session doesn't own the authority to tear
down and rebuild.

## Validators and diff check, same session

`verify_baselines.py` PASS 4/4; `evidence_integrity_check.py` PASS, 0
broken references across 326 files; `capability_drift_check.py` PASS,
8/8, CAP-008 correctly reported as "not yet approved — ... no approval
for it to have drifted from" (no false drift claim); governed aggregate
`run_regression.py` PASS 4/4, 1 N/A (retired CAP-007 suite) excluded,
record `knowledge/05-QA/tools/regression-runs/RUN_20261001T224339Z.txt`.
`git diff --check` clean. HEAD unchanged throughout.

## What this proposal asks the owner / a fresh Opus reviewer to decide

1. **Whether to accept Colima/Lima as CAP-008's registered local-engine
   binding**, replacing (not merely supplementing) the Docker Desktop
   row — a `CAPABILITY_REGISTRY.md` edit naming the exact versions above,
   `review_status` advanced to at most `QUALIFIED` pending that review
   (never `APPROVED` by this or any Sonnet session).
2. **A fresh, independent Opus capability-security review** of this
   evidence package (this file + `COLIMA_ALTERNATIVE_DRILL_2026-10-01.md`
   + `provenance_and_license.md` + `QUALIFICATION_RECORD.md`) — covering
   the VM image/base-OS supply chain (Ubuntu 24.04.4 LTS inside the Lima
   VM) in more depth than this session's license-file check reached, per
   the earlier drill's own flagged limitation.
3. **Rollback target for the new binding**: identical in spirit to the
   Docker Desktop row's — if Colima must be removed, the harness still
   has no mock/fallback and would fail closed; falling back further to
   "no local Postgres" remains the ultimate rollback either way.

This is a proposal, not an inferred approval. No registry `review_status`
change, no `BUG-038` closure, no Slice-5 promotion, and no R04 work
follow from this file by itself.
