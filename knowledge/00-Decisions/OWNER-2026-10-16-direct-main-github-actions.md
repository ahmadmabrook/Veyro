# Owner decision 2026-10-16 — GitHub-only source sync and Actions CI/CD (direct-main)

**Status: APPROVED by the owner, effective 2026-10-16. IMPLEMENTED IN SOURCE ONLY — NO LIVE PROOF YET.** No Actions run on `main` under this decision has been observed, and no module is certified by this document.

## Decision
- GitHub is used only for source sync and GitHub Actions CI/CD.
- Sonnet implements and runs focused deterministic tests. An independent Opus reviews the exact proposed change. The OpenClaw operator commits and pushes directly to `main` only after local verification and that review.
- After each push the actual Actions run on the pushed SHA must be observed. On failure the operator remediates forward or makes a safe revert.
- Not used: pull requests, feature-branch development, GitHub reviewers or approvals, the trusted-check signer / GitHub App gate, a custom App, a hosted Opus gate.

## Scope and supersession
Supersedes **only** the wording of EIP v2.0 §21.2 (MOD-001 card) and the MOD-001 module that requires feature-branch PR CI, protected-`main` with an approving review and a "real reviewer route", and a trusted base-branch / trusted-check gate. It does not supersede any product, security, delivery, rollback, quality or certification requirement, the Foundation scope, or the owner's 2026-10-15 screen-contract timing decision.

The EIP `.docx` and `PROJECT_INDEX.md` stay byte-for-byte unmodified because the source-binding pin hashes them; changing them would invalidate the pin. This record, not an edit to those files, carries the supersession.

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
One runner and one repository writer at a time. The existing Continuous Runner stays PAUSE with no writer during the migration. The owner has explicitly authorized resuming the existing runner after the migration and one-writer verification are complete (not yet done). The runner does not invoke the trusted gate under any setting: `VEYRO_GATE_MODE=publish` (or any value other than `off`) is rejected at startup, fail closed.

## Historical PR #10 and #12
Draft PR #10 (and PR #12) are preserved as historical records and are not deleted or rewritten. Their content is reconciled onto `main` through the direct-push sequence above, with the same review and CI proof; the owner has explicitly authorized safely reconciling and closing them once the relevant changes are preserved on `main` (not yet done). Historical evidence (PR runs, the PR #11 negative drill, trusted-gate slices) stays labeled historical in MOD-001.

## Module certification
Direct push to `main` does not replace module acceptance. MOD-001 still needs its acceptance criteria met with real evidence and a final independent module review; no module is certified by process change alone. Missing proof is recorded as BLOCKED, never PASS.

## Evidence still required (not claimed)
Successful push run on `main` for the first SHA carrying this change; negative/failure-handling proof under this model; final MOD-001 review.
