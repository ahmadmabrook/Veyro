# SCN-020(a) corrected live replay — 2026-10-09

**Disposition of case (a): DENIED by the trusted required check. SCN-MOD001-020 as a whole remains BLOCKED/NOT PROMOTED; cases (b)-(i) are pending.** This is a live GitHub observation, not independent security review or module certification.

The sole runner operation `92002f1b-3cc6-4762-9113-2e1e9131a6ac` refreshed the contract, reverified all four baseline hashes, and used the existing PUBLIC `ahmadmabrook/Veyro` repository and disposable, unmerged [PR #1](https://github.com/ahmadmabrook/Veyro/pull/1). The trusted default-branch workflow and validator were already at main `f85a17ba28cf55a209b0129ea8e9ceacc6a9edb9`; strict branch protection required only `architecture-event-contract-trusted` from GitHub Actions app ID `15368`, with administrator enforcement and force-push/deletion disabled. The candidate-controlled old check was no longer required.

An empty synthetic sync commit `d0b84469caf7ffc531f7816b91f04fb57c8be89a` triggered [trusted run 37850864672](https://github.com/ahmadmabrook/Veyro/actions/runs/37850864672), event `pull_request_target`. Its log identified trusted SHA `f85a17b`, candidate SHA `d0b8446`, protected-base SHA `36457b4`, and `UNREGISTERED_EVENT_CONTRACT`; the trusted job/check concluded **failure**, app ID `15368`, while PR #1 stayed BLOCKED. This first live run establishes that the default-branch check is actually triggered for a PR targeting the nondefault disposable base.

For the exact (a) replay, the sole candidate change was one `continue-on-error: true` line on the old `.github/workflows/event-contract.yml` validation step. Commit `10ab7e2367c5b40e4096a70f9e54a09d9b5e28ec` was pushed to the disposable head; no main, protected-base, validator, registry, real-data or secret file changed. `git diff --check` passed before the push. At that one head SHA:

| Live observation | Immutable evidence | Result |
| --- | --- | --- |
| Candidate-controlled old `pull_request` check | [run 37850953256](https://github.com/ahmadmabrook/Veyro/actions/runs/37850953256), job/check `architecture-event-contract` | **success** — reproduces the former false-success bypass, but this context is no longer required |
| Trusted default-branch `pull_request_target` check | [run 37850950695](https://github.com/ahmadmabrook/Veyro/actions/runs/37850950695), job/check `architecture-event-contract-trusted` | **failure**; log reports trusted `f85a17b` and `UNREGISTERED_EVENT_CONTRACT`, final DENY/exit 1 |
| Required status and merge | GitHub check-runs API, disposable-base protection API, and PR #1 API in [live snapshot JSON](SCN020-A-TRUSTED-REPLAY-LIVE-SNAPSHOT-2026-10-09.json) | Required context is trusted check from app `15368`; PR state **OPEN/BLOCKED**, `mergedAt=null` |

The candidate's `continue-on-error` setting therefore did not make the **required** check pass or the PR mergeable. This is one corrected live disposition of (a), preserving the historical pre-remediation success. **It does not yet prove** that the candidate cannot suppress, rename, or spoof the trusted check; those remaining attack classes and (b)-(i) must receive individual live dispositions. The single independent gate-3 review authorization remains unconsumed, and R04 gate-2 F01-F14 remain CLOSED.
