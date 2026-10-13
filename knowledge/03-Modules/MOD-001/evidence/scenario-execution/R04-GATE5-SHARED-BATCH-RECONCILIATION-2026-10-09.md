# R04 gate-5 shared synthetic batch — mechanical reconciliation (2026-10-09)

Operation `653041ec-59a4-4b9d-a062-082ba5842759`; **MANDATORY_NOW**, one bounded local deterministic batch. [Raw fixtures and CLI reports](knowledge/03-Modules/MOD-001/evidence/scenario-execution/R04-GATE5-SHARED-SYNTHETIC-BATCH-2026-10-09.json) are retained as JSON. Validator SHA-256 `8aa553592128e7ffdb921d41fa179f6e46067ab856fa4505bef7b47c10127565`. No new writer or reviewer, remote action, real customer/member data, credential, or Production use.

| Required scenario | Exact observed CLI result | Mechanical criterion | Disposition |
|---|---|---|---|
| SCN-MOD001-012 | `PASS` / exit 0; canonical `SCR-001`→`bff:members.profile_read`, `SCR-002`→`command:billing.refund_create` | Mapped synthetic IDs accepted | Executed mechanically; not promoted |
| SCN-MOD001-013 | `FAIL` / exit 1; equal 2-vs-2 rows with `SCR-002` absent; sole `UNMAPPED_SCREEN_CONTRACT` cites `SCR-002` | Unmapped ID denied without count-mismatch confound | Executed mechanically; Opus-tier judgment pending |
| SCN-MOD001-110 | `FAIL` / exit 1; canonical 2 versus generated 1; `SCREEN_CONTRACT_COUNT_MISMATCH` detail cites `expected 2, actual 1` (also cites missing `SCR-002`) | Dropped-row count mismatch denied by name | Executed mechanically; Opus-tier judgment pending |

The raw report and expected fields were asserted after actual CLI invocation using temporary synthetic registry/manifest files. Both negatives intentionally return `FAIL`/exit 1; that is expected denial, not scenario FAIL. The scenario catalog is updated only to **EXECUTED — PENDING INDEPENDENT SECURITY/SCENARIO ASSURANCE (not promoted)**. The code-bearing gate-5 snapshot still needs minimum governed independent review; this operation does not create or consume a review entitlement. Separate implementation-complete generator/real canonical import, route/contract lint and CI enforcement remain mandatory under Appendix F/`IMPLEMENTATION.md` §10; the previous fixed-format local gate alone does not certify R04. Gate-3 P2-4 PR #3 remains held. Gate-2 F01–F14 14/14 CLOSED, gate-5 review/remediation 0/0, MOD-001 exit 0/8, SCN-070 cap unchanged.

Next: governing-source refresh for changed scenario catalog, then select the minimum mandatory canonical-generator/route-contract completion unit (or reconcile its exact existing implementation status) before any gate-5 assurance dispatch. No scenario PASS or module certification inferred.
