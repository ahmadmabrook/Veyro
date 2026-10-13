# Gate-3 P2-4 upstream draft installation PR — 2026-10-09

Sole-runner operation `cf3bfb99-4743-496a-8aa8-814b4db84ff4`. **MANDATORY_NOW** bounded upstream installation candidate for the exact independent-review P2-4 standing-CI-control defect, not a review, merge, scenario verdict or certification. Contract refresh acknowledged at `8c8a3320eeeb5602caacb52dee08a7dedb4291c1708a5ca98f19f08163eef2d1`; governing hashes matched. MOD-001 is HIGH; existing lean scope review covers continued mandatory work (`scopeReviewRequired=false`).

Preflight: `ahmadmabrook/Veyro` PUBLIC, protected default `main` at `f85a17ba28cf55a209b0129ea8e9ceacc6a9edb9`, admins enforced, one approving PR review required, no required status check. Branch `gate3-p24-workflow-trust-20261009` was absent. Upstream PR #1 was OPEN/unmerged and its head unchanged. The exact payload was limited to two already verified, secret-free files:

| File | SHA-256 |
| --- | --- |
| `.github/workflows/workflow-trust.yml` | `44d57f37fe17dcb8163604021468320c5c475bd0a5d43864fb09e9771f8c4b96` |
| `tools/validate_workflow_trust.py` | `301635d5034759dd7a8abc968d77f2ab3239606c6c00e3e11b60e51ac19afe63` |

Those bytes match the local P2-4 verified control and the protected true-fork default-branch fixture. Known credential/private-key markers were absent. A fresh shallow upstream clone at the exact main SHA staged only those two paths; `git diff --cached --check` passed. Normal non-force push created head `8c7978013250dcc2acccf908c4ccad8e8309009c` on the new branch, leaving upstream `main` unchanged.

[Draft PR #3](https://github.com/ahmadmabrook/Veyro/pull/3) targets upstream `main` at `f85a17b` and GitHub readback confirms only the two listed files. It is OPEN/DRAFT, `reviewDecision=REVIEW_REQUIRED`, `mergeStateStatus=BLOCKED`, and has no status checks reported. Upstream protection readback still has one approval required, admins enforced and `required_status_checks=null`; PRs #1/#2 remain OPEN/unmerged at their prior heads. No existing protection was weakened, no reviewer dispatched, no PR merged.

The fork clean/negative live inputs remain in `GATE3-R1-P2-4-FORK-REQUIRED-STATUS-POSITIVE-2026-10-09.md` and `GATE3-R1-P2-4-PROTECTED-FORK-NEGATIVE-BATCH-2026-10-09.md`. They establish technical behavior in the sacrificial true fork, not upstream deployment or qualified assurance. The new PR itself cannot supply a trusted `pull_request_target` status from an upstream default branch that does not yet contain the definition/validator; the current absence of such a check is not a PASS or failure of the candidate.

**Remaining exact boundaries:** Upstream branch protection's existing one-approval requirement must be met without bypass or weakening before merge. The material executable validator/workflow also still needs legitimate bounded independent code/security assurance; the sole owner-authorized gate-3 review was consumed on an earlier BLOCKED snapshot, and this PR does not reset that entitlement. After an authorized protected merge, the upstream required context still must be configured and live positive/negative enforcement observed before P2-4 could be considered for formal disposition. SCN-020 and gate-3 scenarios remain unpromoted; MOD-001 exit remains 0/8. R04 gate-2 original findings, including R1-F14, remain formally CLOSED 14/14 only.

Next bounded action after a contract refresh at the prepared-PR-to-approval/assurance boundary: reconcile the exact independent-review and GitHub-approval authorities and continue any already-authorized mandatory MOD-001 work. Do not create a reviewer, mark P2-4 closed, request an automatic retry, or merge PR #3 by inference.
