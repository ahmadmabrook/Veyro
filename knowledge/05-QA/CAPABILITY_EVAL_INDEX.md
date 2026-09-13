---
doc: CAPABILITY_EVAL_INDEX
status: LIVE
updated: 2026-09-13 (Phase 9 restoration proof, third Gatekeeper pass P1-2 — CAP-003/CAP-004 were still omitted after round 2 fixed only CAP-007's identical omission; also fixed the correction note's stale "4 rows" reference)
---

# Capability Evaluation Index

Appendix D field: "Qualification/eval evidence for project and external
Skills/Rules/plugins/MCP/hooks/tools, including positive/negative tests,
periodic review evidence, next-review-due enforcement and change-triggered
re-evaluation."

Durable authority: `knowledge/00-System/CAPABILITY_REGISTRY.md`. Raw
qualification evidence, preserved from `knowledge/04-Capabilities/evidence/`
during the 2026-09-05 vault migration (git history intact via `git mv`):
`knowledge/05-QA/capability-evidence/`.

| CAP ID | Positive test | Negative test | Lifecycle status | Next review due |
|---|---|---|---|---|
| CAP-001 | `capability-evidence/CAP-001/positive_test.md` | `capability-evidence/CAP-001/negative_test.md` | ACTIVE | 2026-12-04 |
| CAP-002 | `capability-evidence/CAP-002/positive_test.md` | `capability-evidence/CAP-002/negative_test.md` | ACTIVE | 2026-12-04 |
| CAP-003 | N/A — first-party default-trust exemption per `CAPABILITY_POLICY.md` (exemption covers content-hash/from-scratch qualification, not `review_status` itself — this row still exists to record lifecycle state, per `CAPABILITY_POLICY.md`'s own rule that the exemption doesn't extend that far) | N/A, same exemption | ACTIVE | 2026-12-04 |
| CAP-004 | N/A — first-party/harness-native exemption, same basis as CAP-003 | N/A, same exemption | ACTIVE | 2026-12-04 |
| CAP-005 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` | none yet run | ACTIVE | 2026-12-04 |
| CAP-006 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` | invalid-deep-link-scheme negative control, same file | ACTIVE | 2026-12-04 |
| CAP-007 | `evidence/security/BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md` (positive: 194/194 tests + ~250 adversarial fixtures) | same file (negative: fail-closed on unknown/composed/wrapped commands, tamper/symlink/exception probing of hash-pinning) | ACTIVE | 2026-12-07 |

**Corrected 2026-09-05 (fourth Phase 5 re-review, NF4-3):** this table
previously said `next_review_due` was "not yet set" for every row after
`CAPABILITY_REGISTRY.md` had already populated it (2026-09-05,
`last_reviewed_at`/`next_review_due` = 2026-12-04, 90-day cadence) for
the rows that existed at the time — this index just hadn't been synced
to that. Fixed; `lifecycle_status` (all `ACTIVE`) added per
`CAPABILITY_REGISTRY.md`'s own new "Lifecycle status" section.

Also indexed here: the capability-governance drill
(`capability-evidence/GOVERNANCE_DRILL/DRILL.md`) — inventory, gap
detection, bounded discovery, reuse, fail-closed, and fresh-session reuse
all tested with real evidence, all PASS.
