# Gate-3 R1 P2-4 — local workflow-trust lint

Date: 2026-10-09. Sole runner operation: `f052bb8b-34cf-4f3b-b6ce-d59c4b375c73`.

Classification: **MANDATORY_NOW**, limited to the exact qualified P2-4 standing-control blocker. A single guarded implementation operation authored `tools/validate_workflow_trust.py`, its focused tests, and `.github/workflows/workflow-trust.yml`. The runner then made only bounded fail-closed corrections: removed inapplicable Python shebangs (Ruff EXE001); denied failed or empty candidate workflow enumeration; recognized a quoted `on` key; and denied candidate changes/removal of the gate workflow or validator so a PR cannot disable the check after merge. No second Claude dispatch.

The check evaluates candidate workflow files as inert text using the validator from the trusted default-branch SHA. It denies the conjunction `pull_request_target` + non-`GITHUB_TOKEN` secret reference + fork-head reference. It uses no third-party action or secret. Candidate files are never executed. Candidate copies of the enforcement files must byte-match the trusted snapshot.

Observed local verification: 17/17 focused tests pass; Ruff and Python compile pass for both Python files; extracted workflow `run` block passes `bash -n`; the validator allows the two current local workflow files; an empty workflow directory denies with exit 1; four governing baseline hashes match. The guarded operation completed exit 0. No live CI run or branch-protection required-status evidence was obtained in this operation.

Disposition: **LOCAL_VERIFIED, ENFORCEMENT_AND_INDEPENDENT_ASSURANCE_PENDING**. This is not a P2-4 independent closure, a gate-3 review retry, SCN-020 PASS, scenario promotion, or MOD-001 certificate. The already-consumed gate-3 review entitlement is unchanged. Next mandatory boundary: reconcile a trusted default-branch installation and required-status live path under the existing owner authorization, then apply only legitimately available bounded assurance. Keep upstream PR #1 unmerged and preserve all other gates/counters.
