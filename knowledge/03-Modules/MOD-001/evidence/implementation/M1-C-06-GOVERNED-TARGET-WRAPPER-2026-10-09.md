---
doc: M1-C-06 governed-target candidate and 43-dispatch scope re-audit
status: CANDIDATE_ONLY — NOT APPROVED FOR REAL-TREE OR CI SCANNING
date: 2026-10-09
runner_operation: 52ae65a6-40e7-4cb2-bffb-1086e799cd3a
bounded_operation: M1-C-06
---

# Observed increment

The sole guarded Opus ARCHITECTURE_CRITICAL dispatch `M1-C-06-v26` produced a local, untracked scanner preflight candidate, target manifest, inert workflow candidate and synthetic tests. Its guard ended `SOFT_NO_PROGRESS` at 903 seconds because the newly authored paths were not among the four paths declared to the operation budget. Preserve the artifacts; this is not an R03 or capability approval and is not a reason to replay the same work.

| Artifact | SHA-256 |
|---|---|
| `tools/governed_scanner_preflight.py` | `12bec989dab689e34cd810e2de61927a18a6f3aadeae136c0eae3a0cc6a34ff2` |
| `tools/governed_scanner_targets.json` | `2471bbfd163353f782c75eea4fce35fe2b0bd149bcca5d18e64ecdb1ba0996c7` |
| `tools/tests/test_governed_scanner_preflight.py` | `f8387e943ce36f6d19ee24bd365dc06902e0f94dd2abe48a6f7f8f468bdaf2c5` |
| `.github/workflows/c06-real-tree-scanner-candidate.yml` | `d761be9d309dbdaae52bcb2d40dcdac1b50a7cc94a7990bf4b526e26ae8e74e5` |

Independent local deterministic verification after the interrupted call: `backend/.venv/bin/python -m pytest tools/tests/test_governed_scanner_preflight.py -q -p no:randomly` **43 passed**; `git diff --check` on the four candidate paths emitted no errors. Read-only preflight enumerated **458 tracked files, 41 Python files and four declared gitleaks-default-allowlist exclusions** at HEAD `e481b814a80923849dddfe7a49319112aae7b023`. Both preflights reported `authorised_for_real_tree_scan=False`; both `scan` CLI probes stopped at `BLOCKED` without invoking either scanner against a Veyro file. The candidate workflow is untracked, unrun, non-required and intentionally inert. No R03 scenario was disposed.

The broader `tools/tests` run reported **7 failed / 1110 passed / 31 subtests passed**. The seven failures are the existing gitleaks qualification tests requiring `VEYRO_GITLEAKS_BIN` to point to the hash-verified upstream binary; local Homebrew identity remains ineligible. This broad result is not a scanner capability pass.

# Immediate mandatory-scope audit at 43 dispatches

`M1-C-06` remains **BLOATED** but operation-loop status is **CLEAR**: 43 distinct dispatches, zero retries and 2/21 compressed operations formally complete. The existing `SPLIT` stands. OSV dependency-vulnerability and integrated typecheck-CI belong to already-planned `M1-C-05`; no new operation is added and neither task is repeated here.

The candidate closes only the *stated target/preflight* part of C09-X/C10-X. It does **not** implement a real-tree scanner call in the CLI: `scan` unconditionally returns blocked after authorisation checks. Nor does a byte-equal HEAD check prove that a commit had qualified review. The synthetic tests do not yet demonstrate the required actual gitleaks default-global-allowlist miss versus governed detection on a planted excluded-path placeholder. The Linux extracted-binary identity and a trusted, reviewed workflow remain open. These are exact mandatory deficiencies, not optional hardening. CAP-009/010 current bounded scopes remain unchanged; no real-tree SAST, secret scan, CI gate or scenario PASS may be inferred.

Minimum legal continuation, with a fresh contract refresh before dispatch: first reconcile the candidate against C09-X/C10-X and correct only the missing executable/synthetic proof under the already-planned C06 boundary, with accurate tracked paths. Then obtain the mandatory independent code/security/capability decision on that exact snapshot; only a qualified grant can precede a Veyro-file scan. Thereafter collect actual advisory and live CI proof, batch individual R03 scenario dispositions, and close C06. Do not dispatch OSV or integrated typecheck-CI in C06. No owner decision is presently required: technical correction and qualification remain legal on the near side of the hard boundary.
