# SCN-020 public-hosting precondition reconciliation — 2026-10-09

Scope: MANDATORY_NOW, existing GOV-01-R04 / SCN-MOD001-020 protection prerequisite. No product code, test, review, scenario execution, or remote configuration changed in this operation.

Owner decision: `control/SCN020_OWNER_DECISION_2026-10-08.md` and `control/SCN020_CREDENTIAL_RECONCILIATION_2026-10-09.md` in the OpenClaw workspace. The owner manually made the existing repository PUBLIC and directs that it remain PUBLIC. The three local credential-bearing raw files were contained/redacted under that reconciliation and must not be published. The earlier private-repository HTTP 403 remains historical, not a current feature denial.

Live read-only GitHub observations under the sole runner operation `5511841a-6df1-499f-baff-944b31c253a4`:

- `gh repo view ahmadmabrook/Veyro --json visibility,defaultBranchRef,isPrivate,url`: PUBLIC, `main`.
- `gh api repos/ahmadmabrook/Veyro`: authenticated admin permission; Actions enabled and allowed actions `all`.
- `gh api repos/ahmadmabrook/Veyro/rulesets`: HTTP 200, empty list. Public-hosting feature is available, but no rule exists.
- `gh api repos/ahmadmabrook/Veyro/branches/main/protection`: HTTP 404 `Branch not protected`, not the prior HTTP 403. Do not protect or use `main` as the disposable target.
- `gh api repos/ahmadmabrook/Veyro/actions/workflows`: zero live workflows. Remote has only `refs/heads/main` at `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.
- The proposed `.github/workflows/event-contract.yml`, `tools/validate_architecture_gates.py`, and `contracts/events/{registry,baseline}.json` remain local untracked files, absent from `origin/main`. The local worktree also has substantial unrelated uncommitted work, which must not enter the synthetic PR fixture.

Disposition: hosting capability precondition is now **AVAILABLE**, but SCN-020 remains **NOT EXECUTED / NOT PASS** until a disposable target branch has enforced required status, the minimum synthetic PR is exercised against all nine bypass classes, and evidence is captured. Create a clean isolated checkout/worktree from the pinned remote commit, carry only the gate's needed non-secret files, configure only the disposable target branch's required check and direct-push/administrator behavior, and use synthetic payloads. Do not infer status-check enforcement from a PR alone. The independent gate-3 review authorization remains unconsumed and may be used only after required execution/evidence if governing boundary requires it. F14 remains formally CLOSED; no gate-2 reopen or module certification.
