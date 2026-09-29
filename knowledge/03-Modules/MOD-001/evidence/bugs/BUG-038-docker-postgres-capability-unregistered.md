---
doc: BUG-038
module: MOD-001
severity: P1 (proposed by the independent reviewer; supply-chain governance gap, not a harness code defect)
status: OPEN (2026-09-29)
filed: 2026-09-29 by veyro-security-reviewer (Opus), independent Slice-5 review; not fixed by the filer (reviewers do not implement)
---

# BUG-038 — Docker Engine + `postgres:16-alpine` are an unregistered, unqualified capability, relied on for Blocker-severity evidence

## Finding

Slice 5's Blocker-severity scenario evidence (SCN-MOD001-027, SCN-MOD001-067)
rests entirely on Postgres itself correctly enforcing RLS/role
privileges — `backend/tests/harness/postgres.py:32` starts a real,
disposable `postgres:16-alpine` container via Docker Engine (Docker
Desktop, engine 29.7.2). Neither Docker Engine nor the pinned Postgres
image has:

- a row in `knowledge/00-System/CAPABILITY_REGISTRY.md`,
- any qualification evidence (positive/negative test per
  `CAPABILITY_POLICY.md` stage 5),
- an independent Opus capability-security approval.

This is the same class of gap `CAPABILITY_POLICY.md`'s fail-closed rule
exists to catch: *"Any capability not present in `CAPABILITY_REGISTRY.md`
with status `APPROVED` is not usable on this project... If a session
finds itself about to invoke an unregistered or unqualified capability
against real project work... it must stop and report
`BLOCKED: CAPABILITY_UNREGISTERED`."* EIP §4.2 stage 4 independently
requires "Independent Opus capability-security review for any
third-party executable" before use.

The Slice-5 dispatch (see `CURRENT_HANDOFF.md`'s chunk-64 entry) framed
starting Docker and pulling the image as "a real capability gap found
and closed before dispatch... a free, local-only, synthetic-data-only
capability, no owner approval needed" — which addressed the
*owner-approval* question (correctly: no spend, no real data) but
skipped the separate *capability-registration/qualification* lifecycle
(`CAPABILITY_POLICY.md` stages 4-7) entirely.

## Why this matters here specifically

This is not a generic "you used Docker" complaint. The two scenarios
this capability underpins are both catalog **Blocker**-severity
(SCN-027 AUTHN, SCN-067 LIFE) precisely because a false-clean result
here would propagate into every later module's isolation/auth
evidence — the same "false-negative generator installed at the
foundation" concern `ADR-005` used to justify registering
`veyro-critical-engineer` in the first place. Trusting an unqualified
third-party executable as the ground truth for exactly the evidence
class this project treats as highest-severity is the same failure mode
one level down the stack.

## Mitigating factors independently verified (this is not a "the harness is broken" finding)

- The image is pinned by content digest
  (`postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`),
  traced by the reviewer to the official `docker.io/library/postgres`
  repository (`RepoDigests` check).
- Container port bound to `127.0.0.1` only; `--rm`, force-removed in a
  `finally`; 0 leftover containers confirmed after every run.
- Zero spend (local-only), zero real data (synthetic fixtures only).
- The harness fails closed (raises, does not silently skip/mock) when
  Docker is unavailable.

## Open sub-question, not resolved by this filing

**Docker Desktop's licensing terms** have historically required a paid
subscription for commercial use above a company-size threshold. The
reviewer did not verify current terms or whether they apply to this
project/owner's organization. This is a **licensing/spend** question,
not a security one — if it turns out Docker Desktop's terms require a
paid tier here, that is owner-reserved under DC-16 (no paid services
without recorded owner approval) and must route there, not be decided
by any agent. Not asserted as a blocker here; flagged for whoever
qualifies this capability to check as part of that qualification's own
provenance/license review (DC-19).

## Suggested remediation (for whoever is routed it, subject to independent review — not applied by this filing)

1. Run `CAPABILITY_POLICY.md`'s stages 4-7 for "Docker Engine (local,
   loopback-only) + `postgres:16-alpine`@pinned-digest": independent
   evaluation, positive/negative qualification test, registration in
   `CAPABILITY_REGISTRY.md` (as CAP-008 or next available id) with
   scope explicitly bounded to local-only/`127.0.0.1`/synthetic-data,
   `rollback_target` (fall back to no local Postgres — harness fails
   closed), and an independent Opus approval.
2. As part of that qualification, resolve the Docker Desktop licensing
   sub-question above (or explicitly route it to the owner if it turns
   out to be material).
3. Until closed, do not build the R04 RLS-lint/permission-lint gates
   (`ADR-005`'s third critical-engineer slice) on top of this same
   unqualified substrate — that is the "next critical slice" this bug
   blocks, per the reviewer's own explicit judgment.

## Impact on Slice 5's own scenario dispositions

SCN-MOD001-027 and SCN-MOD001-067: harness-level evidence is
technically sound (see the independent review at
`knowledge/03-Modules/MOD-001/evidence/security/SLICE5-INDEPENDENT-REVIEW-2026-09-29.md`),
but neither is recorded as an unconditional PASS while this bug is
open — both carry a disposition of BLOCKED pending this bug's closure
(SCN-067 is additionally, and independently, blocked on the R04 gate
not existing yet — a separate, already-disclosed precondition, not
this bug).
