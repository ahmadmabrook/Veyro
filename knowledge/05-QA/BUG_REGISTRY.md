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
| BUG-006 | MOD-000 | **Blocker for CAP-001** (per SCN-055's catalog severity); resolved for CAP-002 | **CLOSED for CAP-002 (APPROVED, scope narrowed); OPEN for CAP-001 — bounded re-test executed 2026-09-05, independent Opus review pending** | `veyro-security-reviewer` (Opus, fresh context) independently reviewed both, closing CAP-002. CAP-001's bounded 3-item re-test (out-of-scope write attempt, raw artifacts, stage-4 note) executed 2026-09-05 — see `evidence/bugs/BUG-006-*.md` and `evidence/CAP-001/BOUNDED_RETEST_2026-09-05.md`. Real finding: the out-of-scope write **succeeded** (confirmed no technical scope enforcement, worse than the prior "unverified"). Closure still requires an independent Opus review of this evidence, not this session's own say-so. |
| BUG-007 | MOD-000 | P1 | **MOSTLY FIXED** | All 33 detail blocks authored, independently reviewed by fresh-context `veyro-scenario-reviewer` (1 safety defect + 8 overclaimed/mislabeled findings fixed). Structural gap remains open: 8/19 mandatory categories rest on a single, mostly-unexecuted scenario — a live DC-05 gap, not closed. |
| BUG-008 | MOD-000 | Blocker | FIXED | Real fresh-context Opus manual-QA re-run, all 4 remediated findings verified |
| BUG-009 | MOD-000 | P2 | OPEN | CAP-005/CAP-006 qualified and previously mis-reported as approved by the same invocation that qualified them; two durable misreports fixed. Independent Opus review of CAP-005/CAP-006 pending — see `evidence/bugs/BUG-009-*.md`. |
| BUG-017 | MOD-000 | P1 | **CLOSED (2026-09-05)** | Vault migrated to EIP Appendix D, 3 independent fresh-context restoration passes (Pass 1/2 each caught a real premature-completion claim; Pass 3 confirmed clean). See `FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`. |

**Corrected 2026-09-05 (second Phase 5 re-review, N-2): this table and its "0 open Blocker-severity bugs" line had drifted from the actual per-bug files it's supposed to index — a real defect, since this table (not the per-file detail) is what the DC-08 zero-known-defects gate reads. Accurate as of this edit: 1 open Blocker-class item (BUG-006/CAP-001 — Blocker per its own catalog-severity note), 1 open P2 (BUG-009), 0 fully-open Major/P1 bugs (BUG-007 is P1/mostly-fixed with a disclosed structural gap, BUG-017 is closed). This table must be re-synced whenever any bug file's status changes — it is not auto-generated.**
