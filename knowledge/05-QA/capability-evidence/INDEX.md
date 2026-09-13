---
doc: CAPABILITY_EVIDENCE_INDEX
status: LIVE
updated: 2026-09-13 (Phase 9 restoration proof, fourth Gatekeeper pass P1-2 — this file had gone stale since 2026-08-31, omitting 5 of 7 registered capabilities, an un-swept sibling of the identical omission already fixed twice in CAPABILITY_EVAL_INDEX.md)
---

# Capability Evidence Index

One subfolder per capability id (`CAP-NNN/`), containing `positive_test.md` and `negative_test.md` once run. All 7 capabilities below have completed qualification; a new capability row starts here empty until its drill executes.

| capability id | positive test | negative test | status |
|---|---|---|---|
| CAP-001 Notion MCP | PASS (`CAP-001/positive_test.md`) | PASS (`CAP-001/negative_test.md`) | **APPROVED**, scope de-rated, binding caveats (2026-09-05) |
| CAP-002 TestSprite CLI | PASS, offline scope (`CAP-002/positive_test.md`) | PASS (`CAP-002/negative_test.md`) | **APPROVED (offline scope only)** — live execution BLOCKED pending owner credit-spend approval, see `SCOPE_NOTE.md` |
| CAP-003 `docx` skill | N/A — first-party default-trust exemption per `CAPABILITY_POLICY.md` | N/A, same exemption | **APPROVED** (first-party default-trust) |
| CAP-004 Core harness tools (Bash/Read/Write/Edit) | N/A — first-party/harness-native exemption | N/A, same exemption | **APPROVED** (harness-native) |
| CAP-005 Browser tools | PASS (`evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md`) | none yet run | **APPROVED** (2026-09-05, distinct fresh-context Opus review, public/unauthenticated/stateless-endpoint scope) |
| CAP-006 iOS Simulator control | PASS (same file) | invalid-deep-link-scheme negative control, same file | **APPROVED** (2026-09-05, same review, stock-Apple-apps-only scope) |
| CAP-007 PreToolUse Bash security guard | PASS (`evidence/security/BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`, 194/194 + ~250 adversarial fixtures) | same file (fail-closed on unknown/composed/wrapped commands) | **APPROVED, ACTIVE** (2026-09-08, fourth independent fresh-context Opus review + owner live-activation verification) |

Update this table, and add the corresponding `CAP-NNN/` folder with test evidence, whenever a qualification test runs. Cross-link from `CAPABILITY_REGISTRY.md`'s `evidence` column.
