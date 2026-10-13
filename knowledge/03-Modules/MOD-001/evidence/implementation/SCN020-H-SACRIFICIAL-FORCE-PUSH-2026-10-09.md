# SCN-020(h) sacrificial protected-ref force-push — live disposition

Classification: **MANDATORY_NOW**, same shared SCN-020 scenario batch, under the verified isolated-sacrificial authorization `control/SCN020_SACRIFICIAL_LIVE_AUTHORIZATION_2026-10-09.md`. Sole runner operation `92aebc17-bab0-4d5e-9483-c3d0e3829a56`; no Claude/reviewer dispatch.

## Exact preflight

`SCN020-H-FORCE-PUSH-PREFLIGHT-2026-10-09.json` captures live true-fork parentage, authenticated org-admin access, protected fork-only target `refs/heads/scn020-protected-base-20261009` at `36457b4dbe309355c5fede5f56c451371bcfd1f6`, fork/upstream `main` at `f85a17ba28cf55a209b0129ea8e9ceacc6a9edb9`, and fork-local PR #1 OPEN/unmerged. Strict required trusted check (Actions app 15368), `enforce_admins=true`, `allow_force_pushes=false` were read live. The proposed target SHA `e516bedabf3d654ad3ae16d948b8f3522739ddc2` was an **already-public, existing commit** and direct parent of the current sacrificial base; compare reported the base one commit ahead, so this was a genuine non-fast-forward rewind, not a fast-forward dressed as a force probe. No new content or credential payload was uploaded. Only the fork-local sacrificial ref was in the refspec; an exact-SHA `--force-with-lease` prevented an intervening update from being overwritten.

## Actual attempt and after-state

One `git push --porcelain --force-with-lease=refs/heads/scn020-protected-base-20261009:36457b4dbe309355c5fede5f56c451371bcfd1f6 https://github.com/veyro-labs/Veyro.git e516bedabf3d654ad3ae16d948b8f3522739ddc2:refs/heads/scn020-protected-base-20261009` exited **1**. GitHub rejected it with `GH006: Protected branch update failed`, citing “Changes must be made through a pull request,” expected `architecture-event-contract-trusted`, and **“Cannot force-push to this branch.”** Exact response: `SCN020-H-FORCE-PUSH-ATTEMPT-RESPONSE-2026-10-09.json`.

Live after-readback `SCN020-H-FORCE-PUSH-AFTER-SNAPSHOT-2026-10-09.json` confirms fork-only protected base stayed `36457b4`, synthetic head `db04cec`, both default-main refs stayed `f85a17b`, fork-local PR #1 OPEN/BLOCKED/unmerged, and upstream PRs #1/#2 OPEN/unmerged with unchanged heads/bases. This complements the earlier normal direct-push denial; both halves of (h) were actually attempted.

**Individual case (h) disposition:** direct/force protected-ref bypass **DENIED live**, with exact protected-ref and before/after proof. This does not promote SCN-020 or certify MOD-001. Case (f) actual admin merge also DENIED live; case (i) configured synthetic canary/fork-ref remains **NOT ATTEMPTED**. Gate-3 one-review authorization unconsumed; gate-2 F01–F14 14/14 closed. Next after contract refresh: bounded (i) setup/probe using only isolated synthetic canary, trusted default-main workflow, fork-origin PR and no real secret, with live logs/check/protection disposition.
