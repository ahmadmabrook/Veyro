---
doc: R04_CRITICAL_SLICE_SECURITY_REVIEW_R1
module: MOD-001
reviewer: veyro-security-reviewer (fresh independent Claude Opus session)
date: 2026-10-02
status: BLOCKED (P0=0, P1=2, P2=5)
---

# R04 critical-slice security review — Round 1

The fresh read-only ACPX session `veyro-mod001-r04-security-review-20261002`
(Claude session `003334a3-76e5-4e7f-95bf-5b746c3a3ade`) reviewed Slice 6
without participating in implementation. The orchestrator ran `mr_verify.py`
against that session's saved transcript: **PASS, 52 turns, 100%
`claude-opus-5-5`**. The implementing session's independently re-run model
attestation also passed (128 turns, 100% `claude-opus-5-5`); the Slice-6 record's
earlier 102-turn count was captured before that session's final turns.

**Verdict: BLOCKED.** The reviewer ran the R04 integration suite (13/13),
gate unit tests (36/36), full backend suite (64/64), 16/16 mutation kills on
an isolated `/tmp` mirror, 13 adversarial permission and 9 adversarial RLS
probes on the approved Colima binding. No repository file was changed by the
reviewer. Successful existing tests do not override the two reproduced
false-PASS findings:

1. **P1-A — RLS bypass through table privileges.** After granting TRUNCATE on
   `harness.access_grant` to `veyro_runtime`, the RLS gate returned PASS; the
   non-privileged runtime role then truncated the table, reducing the other
   tenant's row count from 3 to 0. The gate checks owner/BYPASSRLS/superuser
   and memberships but not table privileges. Fix: reject runtime privileges
   other than SELECT/INSERT/UPDATE/DELETE on tenant tables, and add a real
   TRUNCATE negative fixture. TRIGGER/REFERENCES need coverage too.
2. **P1-B — permission operation under-scan.** OpenAPI 3.2 `query` and
   `additionalOperations` entries, and uppercase `POST`, went unscanned while
   a valid `GET` caused a PASS. Fix by limiting supported versions to 3.0/3.1
   or scanning 3.2's new fields, and reject unknown path-item keys instead of
   silently ignoring possible operations.

P2 findings: malformed/unhashable registry scopes or deeply nested JSON cause
uncaught exceptions and no structured ERROR (nonzero, so not a false PASS);
tautological policy predicates such as `tenant_id IS NOT NULL` and
`tenant_id = tenant_id` PASS while leaking 3/3 cross-tenant rows, and the
Slice-6 claim that `pg_depend` excludes a string literal per clause is false;
duplicate JSON keys are silently last-wins; the JSON-only permission format,
public-endpoint declaration shape, registry path and extension key need a
recorded `veyro-lead` design decision before CI wiring; command-line
`--non-tenant-table` exemptions lack a committed audit trail. P3: boolean
`true` accepted as registry version 1, and regex `$` permits trailing newline.

Scenario dispositions from this review: **SCN-067 and SCN-004 eligible**
based on directly reproduced literal proofs; **SCN-005/010/011 not yet
eligible** pending P1 remediation and re-review. No scenario was promoted by
the reviewer or orchestrator here. BUG-048's P2/open classification was
confirmed; it causes order-dependent false failures, not false-clean evidence,
and should be closed before CI wiring. A separate fresh code review and a
narrow independent security re-review are required after remediation.

The full reviewer response remains in the ACPX session history; this record
is the durable verdict and finding summary, not a substitute for its probes.

## Implementer remediation status (appended by veyro-critical-engineer; NOT a review verdict)

The verdict above stands: **BLOCKED until a fresh R2 review closes it.**
Implementer-side status per finding, each with real negative fixtures
(details: `evidence/implementation/SLICE-6-gov01-r04-rls-permission-lint-gates-2026-10-02.md`
"Current state"):

| Finding | Implementer status |
|---|---|
| P1-A table-privilege bypass | Remediated, pending R2 (Colima TRUNCATE/SET ROLE/PUBLIC/TRIGGER/REFERENCES fixtures) |
| P1-B operation under-scan | Remediated to ADR-009 D1, pending R2 |
| P2 unhashable scopes / deep JSON | Remediated (structured ERROR), pending R2 |
| P2 tautological predicates + false `pg_depend` claim | Remediated with canonical-predicate check; claim corrected in the Slice-6 record; predicate contract open for `veyro-lead` |
| P2 duplicate JSON keys | Remediated, pending R2 |
| P2 permission contract needs `veyro-lead` | Decided by ADR-009; implemented D1-D4, pending R2 |
| P2 `--non-tenant-table` audit trail | Flag replaced by committed `--non-tenant-manifest`; location open for `veyro-lead` |
| P3 bool version, `$` vs fullmatch | Remediated, pending R2 |
| BUG-048 | Unchanged, P2 OPEN (routine routing) |
