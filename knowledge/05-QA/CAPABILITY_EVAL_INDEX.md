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

| CAP ID | Positive test | Negative test | Next review due |
|---|---|---|---|
| CAP-001 | `capability-evidence/CAP-001/positive_test.md` | `capability-evidence/CAP-001/negative_test.md` | not yet set (known gap — `next_review_due` field exists in policy per SCN-058 but not populated per-row yet) |
| CAP-002 | `capability-evidence/CAP-002/positive_test.md` | `capability-evidence/CAP-002/negative_test.md` | not yet set |
| CAP-005 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` | none yet run | not yet set |
| CAP-006 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` | invalid-deep-link-scheme negative control, same file | not yet set |

**Known gap:** `next_review_due` enforcement is not yet populated for any
row (F5-016's remediation added the *field* to the policy schema; backfilling
actual dates for each capability is separate follow-up work).

Also indexed here: the capability-governance drill
(`capability-evidence/GOVERNANCE_DRILL/DRILL.md`) — inventory, gap
detection, bounded discovery, reuse, fail-closed, and fresh-session reuse
all tested with real evidence, all PASS.
