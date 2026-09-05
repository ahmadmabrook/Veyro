---
doc: CAPABILITY_EVAL_INDEX
status: LIVE
updated: 2026-09-05
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
| CAP-005 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` | none yet run | ACTIVE | 2026-12-04 |
| CAP-006 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` | invalid-deep-link-scheme negative control, same file | ACTIVE | 2026-12-04 |

**Corrected 2026-09-05 (fourth Phase 5 re-review, NF4-3): this table
previously said `next_review_due` was "not yet set" for every row after
`CAPABILITY_REGISTRY.md` had already populated it (2026-09-05,
`last_reviewed_at`/`next_review_due` = 2026-12-04, 90-day cadence) for
all 4 rows above — this index just hadn't been synced to that. Fixed;
`lifecycle_status` (all `ACTIVE`) added per `CAPABILITY_REGISTRY.md`'s
own new "Lifecycle status" section.

Also indexed here: the capability-governance drill
(`capability-evidence/GOVERNANCE_DRILL/DRILL.md`) — inventory, gap
detection, bounded discovery, reuse, fail-closed, and fresh-session reuse
all tested with real evidence, all PASS.
