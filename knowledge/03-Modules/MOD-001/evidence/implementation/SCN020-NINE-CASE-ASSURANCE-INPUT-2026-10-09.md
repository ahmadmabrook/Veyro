# SCN-020 nine-case assurance input (not a verdict)

Classification: **MANDATORY_NOW** — the Blocker SCN-020 evidence clause requires a protection snapshot and nine independent attempt outcomes before qualified security/scenario judgment. Runner operation `5aed266e-4f8b-4c21-8d19-5fdf396e6025`; no reviewer dispatched in this reconciliation. Gate-2 F01–F14 closure and all review counters are unchanged.

The protected disposable upstream base remains `36457b4dbe309355c5fede5f56c451371bcfd1f6`; upstream PR #1 is open/unmerged, and the true-fork-origin upstream PR #2 is open/blocked. The pinned required context is `architecture-event-contract-trusted` from GitHub Actions app 15368, strict and admin-enforced; direct and force pushes are disabled. Default-branch workflow and executable validator, not candidate PR files, produce the required status. The case records below are execution observations, not SCN-020 PASS.

| Case | Live disposition and primary evidence |
| --- | --- |
| (a) `continue-on-error` | Candidate-controlled old check passed while trusted required check failed and PR remained blocked: `SCN020-A-TRUSTED-REPLAY-2026-10-09.md`. |
| (b) `[skip ci]` | Trusted check still failed and PR blocked: `SCN020-BC-AND-SAME-NAME-SPOOF-2026-10-09.md`. |
| (c) candidate workflow edit | Candidate no-op check passed; trusted required check failed and PR blocked: same B/C record. |
| (d) `workflow_dispatch` | Nonrequired dispatch succeeded, required PR check failed and PR blocked: `SCN020-DG-LIVE-PROBES-2026-10-09.md`. |
| (e) true fork PR | `veyro-labs/Veyro` PR #2 required check failed and PR blocked: `SCN020-EI-TRUE-FORK-LIVE-2026-10-09.md`. |
| (f) admin merge | Actual pinned merge request on fork-local sacrificial PR #1 returned HTTP 405, required status failing; base unchanged: `SCN020-F-SACRIFICIAL-ADMIN-MERGE-2026-10-09.md`. |
| (g) job rename | Required trusted context remained unsatisfied and PR blocked: `SCN020-DG-LIVE-PROBES-2026-10-09.md`. |
| (h) direct/force push | Direct push and non-fast-forward force-with-lease against only sacrificial protected ref denied GH006; refs unchanged: `SCN020-H-SACRIFICIAL-FORCE-PUSH-2026-10-09.md`. |
| (i) `pull_request_target` fork-ref/secret | True-fork candidate-only workflow requesting a configured synthetic canary never ran; trusted default-main run 37857138121 failed and PR #2 blocked: `SCN020-I-CONFIGURED-CANARY-FORK-REF-2026-10-09.md`. |

**Exact (i) limitation for reviewer adjudication:** The configured non-sensitive canary is a branch-restricted *environment* secret, not a repository-wide secret. This confinement follows the owner's sacrificial-scope authorization, but the scenario literally says “repository secrets.” The execution proves candidate-head workflow inertness and required-status denial; it does not prove how a default-branch workflow that actually checked out a fork head and referenced a repository-wide secret would behave. Do not silently equate these claims or promote (i) without the named independent judgment. A repo-wide secret on the real upstream is not inferred authorized by a disposable-scope permission.

The one owner-authorized fresh independent gate-3 review is **required** for this code-bearing security-critical surface and named `veyro-security-reviewer`/Opus scenario disposition. It remains **unconsumed**. The review should determine whether each specific observation satisfies its exact criterion, particularly the (i) scope caveat, and assess the bounded trusted workflow/validator snapshot; it must not revisit gate-2 findings or certify MOD-001. Source: `SCENARIOS.md` SCN-020 and SCN-008/019/130, `REQUIREMENTS.md` GOV-01-R04, TSD §24.1 gate 3, Development Constitution DC-06/DC-10/DC-17. No optional work was added.
