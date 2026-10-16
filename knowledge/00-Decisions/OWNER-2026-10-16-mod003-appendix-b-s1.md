# Owner decision — MOD-003 Appendix B S1 companion exception (publication pending)

**Status: APPROVED by the owner on 2026-10-16; operative for MOD-003 S1 only after the publication conditions below.**

## Authority and exact binding

The owner approved the narrow companion-record exception in the Veyro OpenClaw direct conversation on 2026-10-16, in response to the explicit choice “Approve narrow companion-record exception (recommended)”. This is an owner choice, not an agent-generated acceptance verdict. The approved source is `knowledge/03-Modules/MOD-003/REQUIREMENTS.md` as committed at `9f410845d307aa122f56a475d7c57c2f9f850b1a`, SHA-256 `411806241de57c4866e9d87dc01f495858fdda9017726911804ea10274bc1765`.

For MOD-003 **S1 only**, that file's `IN (S1)` and `OUT` cells (table columns 4 and 6) for **WHT-02-R01 through WHT-02-R08** materialize the eight EIP Appendix B ¶7651 IN/OUT cells without changing the pinned EIP binary or its source hashes. The approval applies to all eight rows exactly as bound above, including the three rows with no S1 IN work (R05–R07), and makes no other behavior IN. The `IN (S2, proposed)` cells (column 5) remain OUT and unapproved; a later S2 requires its own decision and verification. Do not edit the bound file under this authority; any altered version needs fresh review and owner disposition.

## Bound source status reconciliation

The bound REQUIREMENTS.md remains byte-for-byte unchanged. Its `PROPOSED` header and the statements that the Appendix B cell is not materialized and an owner decision is pending describe the pre-decision state. **Once this record is published under the conditions below, this record is the owner decision those statements anticipate, and supersedes them only for the exact eight S1 `IN (S1)`/`OUT` cells.** The source's `IN (S2, proposed)` column, “Proposed execution owner for OUT” column, and any other proposals or unimplemented behavior remain proposed/unapproved. The source file itself is not a certificate; no Scenario Review PASS follows automatically.

## Retained obligations and limits

MOD-006 remains the **original Appendix B owner accountable for the remaining WHT-02-R01..R08 obligations**. The OUT behaviors are not waived, PASS, completed, or silently assigned to another module. The bound requirement file names proposed execution owners (MOD-004 or implementing product modules for some portions), but those proposals are not approved exact delivery-module assignments by this decision. Before MOD-006 or a dependent product module claims the remainder complete or deferred, record concrete execution-module ownership and enforceable acceptance gates for every outstanding behavior. The catalogue currently titles MOD-006 “KMP + Compose Multiplatform Production Qualification”; this apparent EIP/catalogue scope conflict remains open and must be reconciled before claiming MOD-006 completion. This decision preserves the original EIP accountability; it does not resolve that conflict by implication.

This exception permits the MOD-003 S1 Scenario Review to evaluate the bounded S1 evidence. It does **not** grant Scenario Review PASS, MOD-003 acceptance, a product or release certification, or a waiver of tests, independent review, security/accessibility obligations, CI, or later owner decisions. R01–R08 `product_pass` remain false; incomplete or unmapped tests stay OPEN/DEFERRED. MOD-006's future gate remains open. There is no production authorization, payment, credential, or cloud approval.

## Publication and evidence

Owner approval: direct conversation reply on 2026-10-16, “Approve narrow companion-record exception (recommended)”. Original message is preserved in the conversation; this file records it prospectively and does not backdate an EIP edit. Exact-diff independent Opus review, local checks, non-force direct-main push, and exact-head successful GitHub Actions remain prerequisites to treating this repository record as published. Until then the operational Scenario Review hold remains.
