---
doc: BUG_REGISTRY
status: LIVE
updated: 2026-09-05
---

# Cross-Module Bug Registry

Appendix D field: "Cross-module defect ledger with retest/regression state."

Per-module detail files remain the durable source (`knowledge/03-Modules/<MOD>/evidence/bugs/BUG-*.md`) — this is the cross-module index required by Appendix D, generated from those files.

| Bug | Module | Severity | Status | Retest/regression evidence |
|---|---|---|---|---|
| BUG-001 | MOD-000 | Major | FIXED | Manifest re-verified byte-identical (chunk 1 + Phase 5 gatekeeper independent rebuild) |
| BUG-002 | MOD-000 | Blocker | CLOSED | Git recovery proof, clone-and-verify passed |
| BUG-003 | MOD-000 | Major | CLOSED | Deletion manifest + absence verification |
| BUG-004 | MOD-000 | Minor | FIXED | Wording corrected, no rerun needed |
| BUG-005 | MOD-000 | Major | FIXED | Re-tested for real in the Phase 5 manual-QA re-run (Accessibility confirmed still correctly BLOCKED) |
| BUG-006 | MOD-000 | Blocker per SCN-055's catalog severity (CAP-001); resolved for CAP-002 | **CLOSED (2026-09-05)** — CAP-002 APPROVED scope-narrowed; CAP-001 APPROVED, scope de-rated, with binding caveats | Third, distinct independent Opus review evaluated the bounded re-test (out-of-scope write attempt **succeeded**, confirming no technical scope enforcement) and approved with binding caveats now encoded in `.claude/rules/notion-mcp-scope-discipline.md`. Residual connector-scope-vs-policy deviation filed separately as BUG-010 (non-blocking). See `evidence/bugs/BUG-006-*.md`. |
| BUG-007 | MOD-000 | P1 | **MOSTLY FIXED** | All 33 detail blocks authored, independently reviewed by fresh-context `veyro-scenario-reviewer` (1 safety defect + 8 overclaimed/mislabeled findings fixed). Structural gap remains open: 7/19 mandatory categories rest on a single, mostly-unexecuted scenario (narrowed from 8 after SCN-071's correction) — a live DC-05 gap, not closed. |
| BUG-008 | MOD-000 | Blocker | FIXED | Real fresh-context Opus manual-QA re-run, all 4 remediated findings verified |
| BUG-009 | MOD-000 | P2 | **CLOSED (2026-09-05)** | Distinct independent Opus review approved both CAP-005 (public-endpoint-only caveat) and CAP-006 (stock-app-only caveat), confirming it was not the qualifying invocation for either. Sequencing gap (evidence gathered while QUALIFIED, not APPROVED) disclosed honestly, not hidden. |
| BUG-010 | MOD-000 | P2 | OPEN (owner decision required, not blocking) | CAP-001's Notion connector is authorized workspace-wide, broader than `CAPABILITY_POLICY.md`'s scope rule permits. Options recorded in `knowledge/04-Decisions/ADR-003-*.md`: re-scope the connector, or formally accept the risk in `OWNER_APPROVALS.md`. Compensating control (`.claude/rules/notion-mcp-scope-discipline.md`) in effect now. |
| BUG-017 | MOD-000 | P1 | **CLOSED (2026-09-05)** | Vault migrated to EIP Appendix D, 3 independent fresh-context restoration passes (Pass 1/2 each caught a real premature-completion claim; Pass 3 confirmed clean). See `FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`. |

**Corrected 2026-09-05 (round 2, after BUG-006/BUG-009 closed and BUG-010 filed): 0 open Blocker-severity bugs, 1 open P2 (BUG-010, owner-decision-pending, not certification-blocking), 0 fully-open Major/P1 bugs (BUG-007 is P1/mostly-fixed with a disclosed, narrowing structural gap; BUG-017 is closed). This table must be re-synced whenever any bug file's status changes — it is not auto-generated.**
