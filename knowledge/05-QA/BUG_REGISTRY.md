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
| BUG-007 | MOD-000 | P1 | **CLOSED (2026-09-05)** | All 33 detail blocks authored, independently reviewed. All 19 mandatory categories PROVEN via real execution, independently re-confirmed by THREE separate fresh-context reviews (third, fourth, fifth), all finding no fabrication. Third review found 1 P1 + 12 P2/Editorial (self-fixed); fourth found 1 new P1 + 4 P2/3 Editorial (self-fixed); fifth returned **P0=0, P1=0, verdict APPROVED**, with 4 P2 + 3 Editorial (all the same recurring propagation-gap species, none certification-blocking), self-fixed. Closed on the fifth review's own independent confirmation, not this session's say-so. |
| BUG-008 | MOD-000 | Blocker | FIXED | Real fresh-context Opus manual-QA re-run, all 4 remediated findings verified |
| BUG-009 | MOD-000 | P2 | **CLOSED (2026-09-05)** | Distinct independent Opus review approved both CAP-005 (public-endpoint-only caveat) and CAP-006 (stock-app-only caveat), confirming it was not the qualifying invocation for either. Sequencing gap (evidence gathered while QUALIFIED, not APPROVED) disclosed honestly, not hidden. |
| BUG-010 | MOD-000 | P2 | OPEN (owner decision required, not blocking) | CAP-001's Notion connector is authorized workspace-wide, broader than `CAPABILITY_POLICY.md`'s scope rule permits. Options recorded in `knowledge/04-Decisions/ADR-003-*.md`: re-scope the connector, or formally accept the risk in `OWNER_APPROVALS.md`. Compensating control (`.claude/rules/notion-mcp-scope-discipline.md`) in effect now. |
| BUG-017 | MOD-000 | P1 | **CLOSED (2026-09-05)** | Vault migrated to EIP Appendix D, 3 independent fresh-context restoration passes (Pass 1/2 each caught a real premature-completion claim; Pass 3 confirmed clean). See `FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`. |
| BUG-011 | MOD-000 | P2 | **FIXED (2026-09-05)** | Phase 5 accessibility evidence file's reasoning was incomplete (implied VoiceOver could not be started at all; a Phase 6 run found it can be, via `launchctl`/`kickstart`, just can't be made to announce-capturably or gesture-navigate). Verdict unchanged (still correctly BLOCKED); reasoning corrected. See `evidence/bugs/BUG-011-*.md`. |

**Corrected 2026-09-05 (Phase 6): 0 open Blocker-severity bugs, 0 open Major/P1 bugs. 1 open P2 (BUG-010, owner-decision-pending, not certification-blocking). BUG-006, BUG-007, BUG-009, BUG-011, and BUG-017 are all CLOSED/FIXED, independently confirmed where applicable, not self-certified. This table must be re-synced whenever any bug file's status changes — it is not auto-generated.**
