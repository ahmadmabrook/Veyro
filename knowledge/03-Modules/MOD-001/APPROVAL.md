# MOD-001 — Final Module Approval Certificate

**Status: APPROVED — FOUNDATION ONLY, ACTIVATION PENDING OWN CI.**

This approval covers the foundation scope below only. It becomes operative only after the activation commit (the commit carrying this file and the MOD-001.md status change) receives its own exact-diff Opus review and then its own exact-head GitHub Actions success. No CI result is claimed here for that commit, and no future SHA or run is recorded.

## Scope
Foundation only: Repository, CI/CD, Environments & Quality Engineering (workflow, local staging profile, rollback rehearsal, screen-identity validation, TestSprite demonstration). Risk class Foundation/Control. No production or broader domain certification.

## Evidence

### Final independent foundation module review (read-only)
- Gatekeeper review `MR-MOD-001-20261016-001`, resolved model `claude-opus-5-5`, route verified, `OUTCOME: APPROVED`, foundation only. This is the final independent foundation module review.
- It is a result about the foundation state. It is **not** a review of the activation diff; that exact-diff Opus review is separately **pending**.

### Candidate certificate CI (observed by the operator, not by the gatekeeper)
- Candidate certificate commit `32e60151d1e828b46a7012010cc29e9411016b54` (`32e6015`): push-event run [38882100880](https://github.com/ahmadmabrook/Veyro/actions/runs/38882100880) on `main`, run `success`, Foundation job `success`. Observed by the operator through authenticated `gh`.
- Earlier runs: [38880380778](https://github.com/ahmadmabrook/Veyro/actions/runs/38880380778) on `bdd7f33982793faac174624bc6ae463d283c8dc6` and migration run [38878981069](https://github.com/ahmadmabrook/Veyro/actions/runs/38878981069) on `6cbf62239d80b6b8ca4bd6bad3d5544a22328885`, both `success`, observed the same way.
- These runs cover those SHAs only. They say nothing about the activation commit.

### Local and demonstration evidence
- Negative drill (local only): `workflow_check.py` on a temporary workflow copy with an injected `pull_request` trigger exited 1; the unchanged workflow exited 0. The candidate was never pushed.
- Rollback: a bad image failed smoke in the local A/B rehearsal and the original image was restored.
- TestSprite: one health demonstration passed 3/3 provider steps.
- Screen identity: 170 canonical Screen IDs verified (identity only).
- Deferred: 1530 unresolved per-screen contract fields go to the owning product modules per the owner's 2026-10-15 decision. `check-complete` stays a visible failing gate.
- Known gap: two macOS sandbox tests skip on Ubuntu, so CI does not cover that isolation path.
- Dashboard guard: `/api/state` reports a header-ACCEPTED module as `accepted=false` unless the CI snapshot is fresh, `main-push`, branch `main`, matches the local HEAD, and has a completed successful `Veyro Foundation CI` push run on that exact head with no pending or failed push run. This prevents premature display only; it does not certify the module.

## Requirement verdicts (EIP card items 1-7, foundation scope)
1. **CI on push to `main` (lint, type-check, build, targeted test): PASS (foundation).** Evidence: push runs 38878981069, 38880380778 and 38882100880 `success` on their exact SHAs. Does not cover the activation commit.
2. **Direct-main controls: PASS (foundation), narrowly.** Evidence: no force-push, no deletion, `enforce_admins` true, read-only workflow permissions, and exact-change Opus review before push under the owner's 2026-10-16 direct-main decision. The retired PR/reviewer/trusted-check wording is N/A by that decision. The activation commit's own review is pending.
3. **Safe dev/staging delivery, secrets, basic rollback: PASS for local staging and rollback only; cloud DEFERRED.** Evidence: local A/B rollback rehearsal. Cloud staging, real secrets and production are not authorized and not claimed.
4. **TestSprite setup with one supported demonstration: PASS.** Evidence: one health demonstration, 3/3 provider steps; checked-in plan and result. Health endpoint only.
5. **Test mechanism and mapping of product-domain gates: PASS for the mechanism; product-domain gates DEFERRED** to the first owning modules. No absent workflow or screen is certified.
6. **Canonical 170 V1 Screen IDs: PASS for identity only.** Evidence: `check-identity` exact ID set, hash and deterministic regeneration. The 1530 per-screen contract fields are **DEFERRED** to the owning product modules by owner decision; `check-complete` remains failing and is not waived.
7. **Deferred product acceptance mapped to first implementing modules: DEFERRED (mapping recorded, acceptance not claimed).** Traceability is kept in MOD-001.md; no product acceptance is asserted.

## Not authorized and not claimed
- No cloud, production or real-secret use is authorized or exercised.
- No product, financial, tenant-isolation or privacy certification.
- No deliberate failing remote run was made; local negative proof is not a remote run.

## Activation condition
Operational acceptance of MOD-001, and permission to start MOD-002, require all of these, in order:
1. Local checks pass for the activation commit.
2. A separate independent exact-diff Opus review of the activation commit approves (**pending**).
3. A direct, non-force push to `main`.
4. The activation commit's own exact-SHA `push`-event Actions run completes `success`, with the Foundation job `success`.
5. The operator rechecks the CI feed and only then resumes the runner. Until step 4 the runner stays PAUSED.

If the activation commit's run fails or is cancelled, the runner stays PAUSED, the MOD-001.md header is reverted to PROGRESS through a new, safe revert or fix commit (no force-push, no history rewrite), and no next module starts.

The activation commit alone is not operationally accepted until its own run completes. The MOD-001.md header treats acceptance as conditional on that run. The dashboard projection is read-only and gates the **current HEAD**, not the activation commit specifically: it shows `accepted=true` only when the CI snapshot matches the local HEAD with a successful push run. A later HEAD would be gated by its own run. The operator must still verify step 4 exactly, for the activation commit's own SHA, and may not rely on the dashboard for it.

## Execution detail (operator choice)
The operator chose conditional same-commit header activation: the header status change ships in the activation commit, with the read-only dashboard CI projection and the PAUSE hold as the safeguards until step 4 completes. This is a narrow execution detail only. It does not change the foundation scope, the EIP acceptance requirements or the verdicts above.
