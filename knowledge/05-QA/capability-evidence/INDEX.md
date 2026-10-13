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
| CAP-007 PreToolUse Bash security guard | PASS (`evidence/security/BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`, 194/194 + ~250 adversarial fixtures) | same file (fail-closed on unknown/composed/wrapped commands) | **APPROVED, ACTIVE 2026-09-08 through 2026-09-27** (fourth independent fresh-context Opus review + owner live-activation verification); **RETIRED 2026-09-28** (`OWN-006`/`ADR-007`, commit `058ed27`; corrected 2026-10-01, this row had kept saying plain "ACTIVE") |
| CAP-008 Docker Engine (via Colima 0.10.3/Lima 2.2.0, local VM, no Docker Desktop) + `postgres:16-alpine`@pinned-digest | PASS, real, re-run against the P1-1-remediated harness (`CAP-008/SONNET_REQUALIFICATION_2026-10-02.md` — 8/8 drills incl. positive/unreachable/wrong-engine/ambient-substitution, exit 0; 16/16 + 51/51 tests, ruff/mypy clean) | PASS, real (same file — unreachable-socket, Desktop-identity-impersonation via safe synthetic endpoint, zero container-create reached it) | **APPROVED (2026-10-02; fresh attested Opus re-review P0=0/P1=0)** — first Opus review returned P0=0/P1=2 (`CAP-008/COLIMA_OPUS_REVIEW_2026-10-02.md`); P1-1 harness fix code-reviewed **APPROVED P0=0/P1=0** (`knowledge/03-Modules/MOD-001/evidence/code-review/CAP008-P1-1-colima-binding-code-review-2026-10-02.md`); P1-2 provenance recorded (`CAP-008/COLIMA_VM_PROVENANCE_2026-10-02.md`). A separate read-only Opus capability-security re-review approved the combined remediation (`CAP-008/COLIMA_OPUS_R2_APPROVAL_2026-10-02.md`); registry `approved_by` and review date are populated. Supersedes the Docker Desktop binding below (history preserved, not deleted). `BUG-038` OPEN, untouched; no self-approval. |
| CAP-008 — **historical** Docker Engine/Desktop binding (superseded 2026-10-02, kept for the record) | **NOT RUN** — blocked, Docker Desktop license-eligibility unresolved (`CAP-008/provenance_and_license.md`) | PASS, re-confirmed twice (`CAP-008/negative_test.md`) | **SUPERSEDED** — no longer the registered binding; this row is history, not current state. See `CAPABILITY_REGISTRY.md`'s `updated:` front matter for the full chain. |

Update this table, and add the corresponding `CAP-NNN/` folder with test evidence, whenever a qualification test runs. Cross-link from `CAPABILITY_REGISTRY.md`'s `evidence` column.
