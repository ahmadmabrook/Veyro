---
doc: M1-C-09-R07-MOBILE-CI-GATE
module: MOD-001
requirement: GOV-01-R07
subgoal: M1-C-09-R07-MOBILE-CI-GATE
date: 2026-10-09
status: LOCAL CANDIDATE — NO CI RUN, NO REVIEW, NO SCENARIO PASS CLAIMED
---

# C09 finish call: SCN-127 fail-open fix + minimum R07 mobile CI gate candidate

## 1. SCN-MOD001-127 fail-open defect — FIXED (local)

Defect: `shared_module_version` row `mobile/ghost | 0.2.0-synthetic` with no `mobile/ghost/build.gradle.kts` returned `[]`
(the loop only walked modules declared in config).
Fix: `tools/validate_toolchain_matrix.py` now emits `SHARED_MODULE_CONFIG_MISSING: <module> ...` for every matrix-versioned
module with no committed KMP build file. Docstring updated.
Negative test: `SharedModuleTests.test_matrix_module_without_committed_config_denied` (exact single-defect assertion).

Replay (local, system python3 `unittest`): 16 tests OK — 127(a) drift (3 tests), 127(b) whitelabel (3), 127(c) shared module
(missing / second-module positive / ghost / drift), positive (fixture, committed repo, CLI exit codes), fail-closed (2).
`python3 tools/validate_toolchain_matrix.py` → `PASS`.

## 2. R07 mobile CI trigger/gate candidate

Files: `.github/workflows/mobile-ci.yml` (new, distinct from C07 `test-pyramid.yml`, which is untouched),
`tools/validate_mobile_ci_workflow.py`, `tools/tests/test_validate_mobile_ci_workflow.py`.

Wiring: `pull_request` `paths:` = `mobile/**` + the workflow + the two validators. Every job runs on every matching change,
so a `mobile/shared/**` change triggers `android-regression` and `ios-regression`; a `mobile/TOOLCHAIN_MATRIX.md` change
triggers build (`android-build`, `ios-build`), UI, accessibility, performance jobs. Android jobs pinned `ubuntu-24.04`.
iOS jobs (`ios-build`, `ios-regression`, `ios-smoke`) commit no runner label (`runs-on: ${{ vars.VEYRO_IOS_RUNNER_LABEL }}`,
variable intentionally unset). No macOS reference, no secrets, no `uses:`, `permissions: {}`.
Static check denies: stale/missing path filter (SCN-100), missing job named by dimension (SCN-128 negative), non-Linux
Android runner (SCN-101), committed/macOS iOS runner (SCN-056), forbidden references.

Local result: `python3 tools/validate_mobile_ci_workflow.py` → PASS (wiring only). 10 tests OK.
Combined run in `backend/.venv` pytest: surface-profile + workflow-trust + toolchain-matrix + mobile-ci = 75 passed.
`validate_workflow_trust.py` → PASS (new workflow ALLOW). `validate_repo_skeleton.py` → PASS.

## 3. Individual local dispositions

| Scenario | Disposition |
|---|---|
| 127 a/b/c + positive | Replayed locally, all green; ghost-module negative added. Not independently reviewed. |
| 052 | Path-filter → both regression jobs: proven statically (`test_common_code_change_triggers_android_and_ios_regression`). Real CI trigger: NOT_EXECUTED. Regression jobs are DENY placeholders. |
| 100 | Path-filter self-test against real `mobile/` file list + stale-filter negative: proven locally. |
| 055 | Android `runs-on` pinned; iOS job present, no runner class: proven statically. Real job metadata from GitHub: NOT_EXECUTED. |
| 101 | Misassignment negative uses non-macOS fixture (windows-2022) and macOS-label negative: proven locally. |
| 074 | Manual re-trigger runner resolution: NOT_EXECUTED (no `workflow_dispatch`/re-trigger path authored; pinned label is static, which is only partial support). |
| 128 | Workflow-graph wiring check by my own script: proven. `validate_architecture_gates.py --gate toolchain-qualification` still exits 2 `GATE_NOT_IMPLEMENTED` (R04 critical slice; not touched). Android build real pass/fail: NOT_EXECUTED. Scenario NOT passed. |
| 129 | Android adapter smoke fixture + broken-stub negative: NOT_EXECUTED (needs mobile source, DEFERRED profile/SCN-139). iOS smoke job wiring only. |
| 050 | Offline-flow-touched path flagging: NOT_EXECUTED (no offline-flow path list or smoke job authored this call). |

## 4. Mandatory blockers (not faked)

1. **B-ANDROID-BUILD**: no Gradle wrapper/distribution in repo; `mobile/**/build.gradle.kts` are non-buildable stubs.
   `android-build` validates matrix-vs-config then DENIES. A real, qualified build path remains mandatory. A Gradle
   wrapper and its capability qualification are ordinary technical work, not by themselves an owner decision; this
   call's audited budget did not include that implementation.
2. **B-GATE-128**: `--gate toolchain-qualification` is owned by the GOV-01-R04 critical slice (`veyro-critical-engineer`);
   not implemented; deliberately untouched.
3. **B-NO-REMOTE-RUN**: workflow never run; GitHub behaviour with an unset `vars.*` in `runs-on` is UNVERIFIED (it may
   fail workflow validation rather than leave jobs pending). Not a required status check. No `actionlint` available locally.
4. **B-PLACEHOLDERS**: regression, UI, a11y, perf, iOS jobs are fail-closed DENY placeholders; no harness exists.
5. **B-CHECKPOINT**: `operation_budget.py checkpoint` rejected the two new files `tools/validate_mobile_ci_workflow.py` and
   `tools/tests/test_validate_mobile_ci_workflow.py` ("untracked file; declare it before dispatch"); control code not edited.
   Checkpoints succeeded for `tools/validate_toolchain_matrix.py`, its test, and `.github/workflows/mobile-ci.yml`.

## 5. Parent reconciliation

Parent independently replayed the four focused files: **75/75 PASS**. The mobile CI validator initially failed two
Ruff alias rules; a mechanical `ruff check --fix` on that file resolved both, then its 10 tests and the matrix's 16
tests passed again. This is still only a local candidate. The workflow's jobs deliberately fail, the iOS `runs-on`
variable is unset with unverified GitHub behavior, and the required toolchain gate exits 2. **Do not commit or activate
this workflow as a required status or claim any C09 scenario PASS on this evidence.** C09's 6/6 audited calls are used;
the shared API/permission source belongs to existing C04, and C09 remains held for real build/gate/live proof.

Not touched: R04 gates, C07 CAP-011 CI effect, `test-pyramid.yml`, control code/dashboard. No push, spend, secrets, data.
