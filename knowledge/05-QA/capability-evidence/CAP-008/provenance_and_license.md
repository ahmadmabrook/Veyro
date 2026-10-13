---
doc: CAP-008_PROVENANCE_AND_LICENSE
capability: CAP-008 (Docker Engine / Docker Desktop local + postgres:16-alpine@pinned-digest)
status: STAGES 1-3 COMPLETE; STAGE 5 POSITIVE DRILL NOT RUN (blocked); STAGE 6 NEGATIVE DRILL PASS
run_by: Sonnet (claude-sonnet-5), bounded qualification-prep session, 2026-10-01 11:11-11:40 UTC
---

# CAP-008 — provenance, license, and qualification-prep evidence

Scope of this file: `CAPABILITY_POLICY.md` stages 1-3 (inventory, gap
detection, discovery) plus the factual provenance/license assessment
`BUG-038`'s "open sub-question" asked for, plus one real negative/fail-closed
drill. **No Docker Desktop daemon was started by this session.** No
container was created. No spend. Stage 5's positive runtime drill is
explicitly NOT attempted here — see "Blocker" section below.

## Stage 1 — Inventory

`CAPABILITY_REGISTRY.md` checked directly (`grep -n "CAP-008"`, full row
read). No existing `APPROVED` capability covers "local Docker Engine +
pinned `postgres:16-alpine` image." CAP-008 is confirmed the correct,
non-duplicate registry entry for this gap; it already exists as a `PENDING`
row (added 2026-09-29) with no reuse candidate found then or now.

## Stage 2 — Gap detection

Already named precisely by `BUG-038`
(`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-038-docker-postgres-capability-unregistered.md`):
`backend/tests/harness/postgres.py` depends on a real, local, disposable
Postgres container for the GOV-01-R02 tenant-isolation/RLS harness
(`backend/tests/integration/test_tenant_isolation_harness.py`), and that
dependency had no registry row, no qualification evidence, and no Opus
approval. Not re-litigated here; cited as the authoritative gap statement.

## Stage 3 — Discovery (bounded)

No new source search was needed or performed: the capability in question is
already the exact one in live use by the harness (not a candidate being
shopped for). Bounded to the two already-identified, named sources:

- **Docker Engine / Docker Desktop** — official vendor, `docker.com`/Docker
  Inc. Already running locally (client 29.6.0, confirmed this session —
  see "Local environment state" below).
- **`postgres:16-alpine`** — official `docker.io/library/postgres`
  repository, pinned by content digest
  `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`,
  `RepoDigests`-traced to the official repo by the independent Slice-5
  `veyro-security-reviewer` (`knowledge/03-Modules/MOD-001/evidence/security/SLICE5-INDEPENDENT-REVIEW-2026-09-29.md`).
  Not re-verified by this session (no `docker pull`/`docker image inspect`
  was run — that would require the daemon up, out of scope for this
  synthetic/read-only pass); cited as prior independent evidence, not
  re-claimed as newly produced here.

No unbounded/unsolicited source was fetched or executed. Resolution budget
(`CAPABILITY_POLICY.md` stage 3) not exhausted — this is the existing,
already-identified target, not a search.

## License provenance — PostgreSQL (non-blocking)

Official source: https://www.postgresql.org/about/licence/ (fetched this
session). The PostgreSQL License is a liberal, OSI-approved permissive
license (similar to BSD/MIT): permission to use, copy, modify, and
distribute the software and its documentation for any purpose, without fee
and without a written agreement, subject to standard copyright-notice
preservation and an "AS IS" warranty disclaimer. No field-of-use,
company-size, or revenue restriction of any kind. This confirms (does not
newly discover) the "PostgreSQL's permissive licence remains separately
confirmed" line already recorded in the 2026-10-01 06:16 UTC checkpoint.
**Not a blocker.**

## License provenance — Docker Desktop (BLOCKER — owner fact, not resolved here)

Official source: https://docs.docker.com/subscription/desktop-license/
(fetched this session). Docker Desktop is free to use for exactly these
categories: **personal use**; **education**; **non-commercial open source
projects**; and **small businesses — fewer than 250 employees AND less
than USD 10 million in annual revenue** (both conditions required, not
either). Use outside those categories (larger commercial/business use,
government entities) requires a paid Docker Pro/Team/Business
subscription.

**This repository contains no fact establishing which category, if any,
applies to this project or its owner's organization.** Per
`.claude/rules/global/owner-reserved-restrictions.md` (no paid services or
spend of any kind, no exceptions without recorded owner approval in
`knowledge/00-System/OWNER_APPROVALS.md`) and per the absolute instruction
this qualification pass was run under, this session does **not** assume
free eligibility, does **not** activate any Docker Desktop
subscription/spend, and treats this as an explicit, named blocker to full
CAP-008 qualification/approval — not something inferred or guessed from
project size or non-commercial appearance. **Record this as
`BLOCKED: OWNER_APPROVAL_REQUIRED` (eligibility category confirmation)
until the owner states which category applies, or until CAP-008's scope is
formally re-routed to a different local engine that carries no such
ambiguity (see "Viable no-spend alternative" below).**

## Local environment state (read-only checks only, this session)

- `docker info` (client-only, daemon query): daemon **not reachable**
  (`Cannot connect to the Docker daemon at
  unix:///Users/ahmadmabrouk/.docker/run/docker.sock`), exit 1. This
  session did not start the Docker Desktop application or its daemon —
  the command above only queries an existing daemon socket; it cannot and
  did not launch the app.
- `pgrep -fl "Docker.app|com.docker"`: only `com.docker.vmnetd`
  (a privileged helper, not the daemon) was running; Docker Desktop itself
  was not running before or after this session.
- No `veyro-mod001-harness-*` container exists (trivially true — the
  daemon is down, nothing can be running).

## Stage 6 — negative/fail-closed drill (real, executed this session)

Invoked the project's own harness entry point directly (not a synthetic
stand-in):

```
backend/.venv/bin/python -c "
import sys; sys.path.insert(0, 'backend/tests')
from harness.postgres import disposable_postgres
try:
    with disposable_postgres(ready_timeout_s=5):
        print('UNEXPECTED: container started')
except RuntimeError as e:
    print('FAIL-CLOSED CONFIRMED:', str(e)[:200])
"
```

Result: `FAIL-CLOSED CONFIRMED: \`docker run\` exit 1: Cannot connect to
the Docker daemon at unix:///Users/ahmadmabrouk/.docker/run/docker.sock.
Is the docker daemon running?; the GOV-01-R02 harness needs a local Docker
engine and ne[...]` — a clean `RuntimeError`, no mock/fallback, no
container created, no leftovers (`docker ps -a --filter
name=veyro-mod001-harness` also fails closed, consistent with no daemon).
This independently reproduces, against live harness code rather than the
generic CLI, the same fail-closed behavior the 2026-10-01 06:16 UTC
checkpoint already recorded once via `docker info` only.

**PASS** — the harness correctly refuses to silently substitute a mock or
skip when its trust anchor is unavailable.

## Stage 5 — positive runtime drill: NOT RUN (explicitly deferred, not a failure)

A positive drill (start the pinned `postgres:16-alpine` container,
loopback-only, synthetic fixture query/role check, teardown, leftover
check) requires the Docker daemon running, which requires Docker Desktop
running, which is gated on the unresolved license-eligibility blocker
above. This session was explicitly scoped to synthetic/read-only
preparation and does not start Docker Desktop while that blocker stands.
**Not attempted; not a FAIL — a recorded precondition gap.**

## Viable no-spend alternative (for the record, not activated)

If the owner's eligibility category cannot be confirmed as free-use, or is
confirmed as requiring payment, a technically viable no-spend alternative
exists without silently changing CAP-008's registered identity: a
non-Docker-Desktop local Postgres substrate (e.g. the open-source Docker
Engine alone on Linux CI runners where Desktop's license terms do not
apply, or a native local `postgres:16` binary/`postgres.app`-style install,
or `podman` with its own, separately-licensed terms) could replace Docker
Desktop specifically while keeping the same pinned official
`postgres:16-alpine` image and the harness's existing fail-closed
contract. This is **not evaluated or chosen here** — it would itself need
its own stages 1-7 qualification pass if pursued, and is recorded only so
the next session does not have to rediscover that an alternative exists.

## What this file does and does not establish

Establishes: stages 1-3 complete for CAP-008; PostgreSQL license
non-blocking; Docker Desktop's exact free-use categories, sourced from the
official page; one real negative/fail-closed drill, PASS; current local
Docker daemon state (down, not started by this or any session action
here).

Does not establish: Docker Desktop license eligibility for this
project/owner (owner-only fact, unresolved); a positive runtime drill
(blocked on the above); CAP-008 `QUALIFIED` or `APPROVED` status (stage 5
is incomplete — qualification requires both positive and negative
evidence per `CAPABILITY_POLICY.md` stage 5, and only an Opus assurance
role may ever mark `APPROVED` per the same policy's model-routing
section); closure of `BUG-038` (unrelated authority — bugs close via their
own filer/review chain, not via evidence-gathering); promotion of
SCN-MOD001-027/067.
