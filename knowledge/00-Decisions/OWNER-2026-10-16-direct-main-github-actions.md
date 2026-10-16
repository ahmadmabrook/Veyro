# Owner decision 2026-10-16 — GitHub-only source sync and Actions CI/CD (direct-main)

**Status: APPROVED by the owner, effective 2026-10-16. MIGRATED; FIRST POST-PUSH RUN OBSERVED SUCCESS. NO MODULE CERTIFIED.** Earlier wording on this page said "implemented in source only — no live proof yet"; that was true before the first push and is now historical. See "Verified evidence (2026-10-16)". This document certifies no module.

## Decision
- GitHub is used only for source sync and GitHub Actions CI/CD.
- Sonnet implements and runs focused deterministic tests. An independent Opus reviews the exact proposed change. The OpenClaw operator commits and pushes directly to `main` only after local verification and that review.
- After each push the actual Actions run on the pushed SHA must be observed. On failure the operator remediates forward or makes a safe revert.
- Not used: pull requests, feature-branch development, GitHub reviewers or approvals, the trusted-check signer / GitHub App gate, a custom App, a hosted Opus gate.

## Scope and supersession
Supersedes **only** the wording of EIP v2.0 §21.2 (MOD-001 card) and the MOD-001 module that requires feature-branch PR CI, protected-`main` with an approving review and a "real reviewer route", and a trusted base-branch / trusted-check gate. It does not supersede any product, security, delivery, rollback, quality or certification requirement, the Foundation scope, or the owner's 2026-10-15 screen-contract timing decision.

The EIP `.docx` and `PROJECT_INDEX.md` stay byte-for-byte unmodified because the source-binding pin hashes them; changing them would invalidate the pin. This record, not an edit to those files, carries the supersession.

## Negative-proof supersession
The owner-approved rule that nothing is pushed until local tests and Opus review pass supersedes the earlier MOD-001 acceptance wording that required an intentionally failing remote Actions run. It is replaced by local negative/failure-recovery proof: a failing local check, verifier or release fails closed, advancement stops, and remediation or safe rollback is exercised and re-verified. An accidental failing `main` run still triggers stop/remediate/revert. This does not waive CI on every actual `main` push (exact-SHA push-event `success` is still required) or any product, security, delivery or certification gate.

## Safe direct-push sequence (every change)
1. Single writer implements the smallest coherent change inside declared paths.
2. Local checks pass: the workflow's own steps (compile, workflow shape, unit suites, backend lint/type/tests, container build/smoke, rollback rehearsal, negative source-binding check) or a documented equivalent.
3. An independent Opus reviews the exact diff to be pushed (not a summary); unresolved P0/P1 findings block the push.
4. The operator pushes the reviewed commit to `main`. No force-push, no history rewrite, no `--no-verify` style bypass.
5. The operator checks the push-event run for that exact SHA. Only a completed `success` on that SHA counts; an older run, another event or another commit does not.
6. Recording the result (success, failure, remediation) is part of the change's evidence.

## Branch-rule minimum and no broad bypass
- `main` must retain at minimum: no force-push, no deletion, and no history rewrite. Required-check and PR-review rules from the previous design may be removed or relaxed only as far as needed for the operator to push directly.
- No broad bypass: no admin override list beyond the single operator identity, no disabling of Actions, no widening of workflow permissions (`contents: read` only), no secrets or deployment in this workflow. `tools/mission_runner/workflow_check.py` runs in CI and fails on added triggers, write permissions, secrets, environments or gate settings.
- Any GitHub settings change is made by the owner or with the owner's explicit instruction and recorded; it is not performed by the implementing agent.

## Failure response
- A failed or cancelled run on `main` is a stop: no further feature work is pushed until the head is green.
- Remediate with the smallest forward fix, reviewed and verified as above, or revert the offending commit with a new revert commit (no history rewrite). Rerunning without a code change is permitted only for demonstrated infrastructure flake, and the flake is recorded.
- The mission runner's post-push observation shows only push runs on `main` for the exact observed remote head and reports staleness or mismatch with the local HEAD. It is not a pre-push gate and cannot make a failed run green.

## Production gate
No production deployment, cloud environment, spend or customer data without separate explicit owner authorization. This decision authorizes source sync and CI only. Cloud staging, secrets and rollback remain unconfigured.

## Single runner and writer
One runner and one repository writer at a time. The existing Continuous Runner stayed PAUSE with no writer during the migration (historical). The migration is now complete and no competing writer was verified; the owner has explicitly authorized resuming the existing runner, but **resume has not happened yet** and the runner remains PAUSE with a free writer lock. No next module is accepted. The runner does not invoke the trusted gate under any setting: `VEYRO_GATE_MODE=publish` (or any value other than `off`) is rejected at startup, fail closed.

## Historical PR #10 and #12
Draft PR #10 (and PR #12) are preserved as historical records and are not deleted or rewritten. Outcome (2026-10-16): PR #10 head `9af46fa` is an ancestor of `main`; GitHub automatically labeled PR #10 MERGED when the same commits arrived by direct push (no PR merge action was performed). PR #12 was CLOSED without merge or branch deletion; its remote head `5e8a928` remains, and its PR guard / hosted gate code was intentionally not imported because the owner retired it. Historical evidence (PR runs, the PR #11 negative drill, trusted-gate slices) stays labeled historical in MOD-001 and is not current acceptance evidence.

## Module certification
Direct push to `main` does not replace module acceptance. MOD-001 still needs its acceptance criteria met with real evidence and a final independent module review; no module is certified by process change alone. Missing proof is recorded as BLOCKED, never PASS.

## Verified evidence (2026-10-16, independently observed by OpenClaw)
- **Pre-push local checks:** 106 runner/dashboard tests; 169 retained trusted-gate library tests; screen identity 170 IDs (identity only, not full contracts); Python 3.13 wheel-only hash-lock install, Ruff, mypy and 6 backend tests; Docker build; two-image A/B rollback rehearsal (bad image failed smoke, original image restored); YAML parse; workflow shape; JS syntax. An independent `claude-opus-5-5` exact-patch review ended `OUTCOME: APPROVED`, no P0/P1.
- **Branch protection (owner-authorized, narrow):** required PR review and the required pre-push Foundation status were removed. `enforce_admins` remains true, `allow_force_pushes` false, `allow_deletions` false, no rulesets.
- **Push and CI:** OpenClaw moved the existing feature head onto local `main`, committed migration `6cbf62239d80b6b8ca4bd6bad3d5544a22328885` and pushed non-force directly to `origin/main`. The actual push-event run [38878981069](https://github.com/ahmadmabrook/Veyro/actions/runs/38878981069) on that exact SHA completed `success`, Foundation job `success`. This is **post-push** evidence, not a pre-push gate. No production deploy.
- **Services:** the existing runner LaunchAgent restarted with the reviewed code (PID 65475): still PAUSE, writer lock free, no queued or running worker. The existing Dashboard LaunchAgent was repointed from a separate UI worktree to the reviewed command-center assets on `main` (PID 65728): HTTP 200 on loopback 8766, module catalog and records serving, MOD001 `accepted=false`. Neither service was duplicated. The runner's public CI feed is currently unavailable because its last read-only GitHub API attempt timed out; the dashboard must not claim green from that feed. The run above was verified independently through the authenticated `gh` CLI.
- **Failure handling, local only:** workflow validator mutation tests reject invalid triggers and permissions; dashboard verdict tests reject failed, pending, stale, wrong-head and unrelated-success cases; the actual local A/B rollback rehearsal made a bad image fail smoke and restored the original image. On 2026-10-16, after the CI success, the operator also ran an explicit safe local negative drill: a temporary copy of the workflow with an injected `pull_request` trigger was passed to `workflow_check.py` and exited 1, then the unchanged repo workflow exited 0. The failed candidate was never committed or pushed, so advancement stopped at local verification. Local-only: not a failed GitHub Actions run, not a remote run, and not module acceptance.

## Evidence still required (not claimed)
- **No remote negative run exists or is claimed.** No failing `main` run has occurred; none will be knowingly made. Local negative proof (above) is not a remote run. Whether the replaced acceptance criteria are met is for the final independent MOD-001 reviewer. Not all MOD-001 criteria are accepted.
- Final independent MOD-001 module review and acceptance.
- Runner resume by OpenClaw/operator after migration and one-writer verification (already authorized, not performed; no owner action pending) and the selection/acceptance of any next module.
