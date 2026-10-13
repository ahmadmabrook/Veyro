# Gate-3 R1 P2-4 — bracket-expression false greens

Date: 2026-10-09. Sole runner operation `39b2f0d2-8966-40d6-bb4d-25b95d969d63`. Classification: **MANDATORY_NOW** correction of the existing P2-4 control, not an optional generalized parser.

The previous local P2-4 record reported 17 focused tests/Ruff/compile/shell syntax passing. At the next live-enforcement boundary, two concrete negative probes against `tools.validate_workflow_trust.evaluate_workflow_text` returned `[]` (ALLOW) despite the hazardous `pull_request_target` conjunction:

1. `secrets[format('DEPLOY_KEY')]` alongside `github.event.pull_request.head.sha` — dynamic index access was not recognized as a non-`GITHUB_TOKEN` secret reference.
2. `github.event.pull_request['head'].sha` alongside `secrets.DEPLOY_KEY` — index access to the PR-head context was not recognized as a fork-head reference.

Both fixtures use synthetic labels and no real secret. GitHub's [Contexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts) documents index syntax (`github['sha']`) as an Actions expression access method. The observed failure invalidates a claim that the authored lint is ready for live required-status enforcement. The previous local checks remain true for their limited fixture set, but **P2-4 is not locally complete**. No remote mutation occurred in this operation; upstream `main` still has no required status check and requires one approving PR review, while the fork `main` is unprotected. Existing PRs, F14 14/14 closure, gate-3 consumed review, and scenario counts are unchanged.

Minimum next correction: fail closed on nonliteral/dynamic secret indexing and recognize bracket-indexed PR-head references, with both negative controls and the existing clean-workflow positive controls. Verify focused tests/Ruff/compile before any live CI installation. Do not broaden to a generic YAML or expression engine or dispatch a new reviewer by inference.
