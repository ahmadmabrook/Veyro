# ADR-0003 — Control the preserved acceptance-receipt verifier

- ID: ADR-0003
- Status: ACCEPTED
- Review: MR-MOD-002-20261029-ADR0003-R1 APPROVED
- Decision-Key: preserved-acceptance-receipt-verifier-coverage
- Covers: tools/mission_runner/acceptance_receipt.py

## Decision

Place the small, offline verifier of preserved MOD-001–MOD-003 acceptance receipts under ADR-0001's existing controlled-path change process. It checks historical receipt bytes and their already-recorded review/CI claims; it grants no runner operating permission, new module acceptance, or exception to product gates. The verifier remains separate from queue and runner lifecycle code so local task execution has no GitHub availability dependency.

This ADR adds one Covers path to the existing process, not a new governance mechanism. It becomes effective only after exact-diff independent review, non-force publication, and successful push CI on this ADR's own SHA. The implementation commit must follow separately, with its own review, local checks, and exact-SHA push CI.
