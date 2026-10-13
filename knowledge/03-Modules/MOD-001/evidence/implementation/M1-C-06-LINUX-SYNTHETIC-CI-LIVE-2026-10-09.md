# M1-C-06 — Linux synthetic-only CI live result (2026-10-09)

## Bounded authority and payload

This is the CI/live portion of the R03 scanner capability qualification, under the existing sole-writer lease and the independent bounded synthetic-drill determination in `../security/M1-C-06-CAPABILITY-SECURITY-DETERMINATION-2026-10-09.md`. The target was the existing public true fork `veyro-labs/Veyro`, disposable branch `ci/c06-qual-20261009`, based on fork `main` at `51056e51a29216b431e36b55284ea7262e45cc8a`. The sole commit `f684831372af4e9f25da37ab2e420857e0a122a8` added exactly `.github/workflows/c06-synthetic-scanner-qualification.yml` and `ruff.toml` (the fork already held the matching `backend/pyproject.toml`). Preflight found no `secrets.`, `uses:`, or `pull_request_target:` reference in the workflow. No product code, regulated/customer data, real credentials, ACPX raw evidence, default branch, upstream PR, or protected ref was pushed or mutated.

## Live GitHub observation

- [Run 37946867580](https://github.com/veyro-labs/Veyro/actions/runs/37946867580), push event on the exact disposable branch and commit above, concluded **success** at 2026-10-09T14:48:07Z.
- [Job 113875289239](https://github.com/veyro-labs/Veyro/actions/runs/37946867580/job/113875289239) concluded **success**. All four substantive steps succeeded: exact-SHA tokenless sparse fetch of the two configuration files; SHA-256 verification before extraction of pinned Linux gitleaks 8.30.1 and Ruff 0.16.9 artifacts; synthetic gitleaks governed-shape drill; and synthetic Ruff S608 governed-shape drill with the actual two Ruff configuration files as read-only config, not scan targets.
- Live log readback contained 33 `PASS` check lines, zero `FAIL` check lines, and `failures: 0` from each scanner drill. Positive, negative, suppression bypass, error-exit, empty/missing-target fail-closed, and nonvacuity probes were executed; the job used runner-generated synthetic targets under `RUNNER_TEMP` only.
- Readback confirmed fork branch SHA `f684831372af4e9f25da37ab2e420857e0a122a8`, upstream `main` unchanged at `f85a17ba...`, and upstream PR #1 still OPEN/unmerged.

## Disposition and limits

The required **synthetic Linux CI drill passed** and corroborates the prior local deterministic synthetic qualification. It does **not** promote CAP-009 or CAP-010 to approved real-tree/production/CI gate use, does not run either scanner on the Veyro tree, and is not a scenario or R03 gate PASS. The independently reviewed bounded verdict and its conditions remain in force. Next: reconcile the R03 capability decision and the 13 individual scenario dispositions as one C06 batch, using this evidence and the existing mandatory foundation proof; move OSV/dependency-vulnerability/typecheck-CI work only to already-planned C05.
