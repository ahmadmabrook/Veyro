# R04 gate 6 — COM-01 reservation entity-list decision (veyro-lead)

Dispatch of record: `R04-GATE6-RESERVATION-ENTITY-DECISION-DISPATCH-2026-10-09.md`, sole runner operation `e4f32c73-700b-4208-836a-11435e040cec`. This is one bounded architecture judgment. It is not a review, not an implementation, and not a scenario, gate, or module verdict. No code, test, checker, registry, inventory, ADR file, or control-state file was written, and no agent was dispatched. Gate 6 stays `ERROR/GATE_NOT_IMPLEMENTED`. SCN-014/015/131 stay NOT EXECUTED. MOD-001 exit stays 0/8.

Inputs I read rather than re-derived: `R04-GATE6-SOURCE-NORMALIZATION-LEAD-DECISION-2026-10-09.md` (D1-D5 and the orchestrator source-accuracy hold), and `R04-GATE6-ENTITLEMENT-SOURCE-RECONCILIATION-2026-10-09.md` (which left the COM-01 reservation representation open). All TSD line numbers below are from `knowledge/00-System/TSD_MIRROR.md` at sha256 `292f4335588bfe1e35e72719835ccab318dbe548e7eb520870eb879922bcf6db`, re-hashed this session. That mirror is derived and not a hash-pinned baseline. Its fidelity to the TSD docx was not re-verified here.

**Naming note.** "ADR-008" and "ADR-018" here mean the TSD's own §3 ADR table (mirror line 710 onward). They are not the project ADRs of the same numbers in `knowledge/04-Decisions/`.

## 1. Source facts (directly inspected)

| # | Source | Mirror lines | What it says about COM-01 entity naming |
|---|---|---|---|
| S1 | §10.12 summary cell "Authoritative entities" | 3645-3652 | Nine names: MembershipProduct, MembershipAgreement, Membership, **MemberEntitlementGrant**, **EntitlementReservation**, EntitlementPolicy, Freeze, LifecycleChange, ContractVersion. |
| S2 | §10.12 Technical Realization Notes, "Authoritative entities/tables are…" | 3728-3732 | Eight names. Both `MemberEntitlementGrant` and `EntitlementReservation` are missing, and a generic **`Entitlement`** appears in their place. The queries line (3741-3742) repeats the generic `Entitlement`. |
| S3 | Same notes subsection | 3747-3751 | "unique active entitlement reservation keys; version checked on grant updates", then "MemberEntitlementGrant is the fulfillment authority. Reservation is atomic and expiring". The notes subsection therefore uses the summary's concepts in its own prose, and contradicts its own list. |
| S4 | §10.12 command inventory | 3734-3737 | `GrantEntitlement`, `ReserveEntitlement`, `ConsumeEntitlement`, `ReleaseEntitlement`. These are verbs, so they do not decide entity names. |
| S5 | P0-02 audit-closure row | 164-166 | Cites §15.2, §10.12 and ADR-008/018. Says COM-01 owns `MemberEntitlementGrant` with atomic reserve/consume/release, and says "SaaS PlanEntitlement renamed". This shows a deliberate post-audit rename, which the notes list does not reflect. |
| S6 | TSD ADR-008 (Accepted) | 764-770 | COM-01 owns `MemberEntitlementGrant` and its reserve→consume→release lifecycle. PLT-03 uses the distinct term `PlanEntitlement`. **It does not name `EntitlementReservation` or `Entitlement`.** |
| S7 | TSD ADR-018 (Accepted) | 833-837 | COM-01 owns `MemberEntitlementGrant` with atomic reserve/consume/release/revoke/expire, idempotency and optimistic version checks. **It does not name `EntitlementReservation` or `Entitlement`.** |
| S8 | §15.2 Entitlement Engine (normative) | 10507-10552 | Defines `MemberEntitlementGrant(...)` and says the grant and PlanEntitlement "are never interchangeable". Reserve records `reservation_id`, purpose/resource, expiry and `idempotency_key` under a unique active reservation constraint. This describes a distinct reservation record but gives it no CamelCase entity name. It is name-agnostic for the reservation and contains no summary-vs-notes precedence rule. |
| S9 | Appendix E.1 "Core tables and aggregate persistence" | 17140, 17171-17173 | Lists `app.member_entitlement_grant` (COM-01, "Fulfilment authority") and **`app.entitlement_reservation`** (COM-01; id, grant_id, purpose_ref, qty, expires_at, state, idempotency_key; "Atomic reserve/consume/release") as **separate** COM-01 tables. |
| S10 | Appendix E.1 `app.booking` (OPS-02) | ~17213-17216 | Carries `entitlement_reservation_id`. This is a cross-domain foreign reference to the reservation as its own record. |
| S11 | §24.1 domain-contract uniqueness lint | 11643-11653 | CI "compares normalized authoritative-entity sets". It states no fail predicate for entities, no aliasing allowance, and no source-precedence rule. It presupposes that each domain has one comparable set. |
| S12 | MOD-001 `REQUIREMENTS.md` GOV-01-R04 | 234-266 | Places real-domain content out of scope ("content is later modules' job"). It names no COM-01 entity. |
| S13 | MOD-001 `IMPLEMENTATION.md` §4 gate-6 row; `SCENARIOS.md` SCN-014/015/131 | 387; 573-600, 1056-1080 | Synthetic domains only. **None pre-commits to any of the three candidate names.** |

A grep of the whole mirror finds `EntitlementReservation` only at line 3649. The generic `Entitlement` appears as a list item only at lines 3731 and 3742. Neither name collides with another domain's entity list, so this choice creates no new cross-domain overlap and removes none.

## 2. Decision

### Q1. Canonical COM-01 entity name

**Selected: the §10.12 summary set (S1) is the canonical COM-01 authoritative-entity set for any future source-pinned inventory. It includes `EntitlementReservation` and `MemberEntitlementGrant` as two distinct entities.**

The three candidates do not actually compete for one slot. Each one fares as follows:

- **`MemberEntitlementGrant` (the ADR name) is confirmed, not a rival.** It appears in S1 itself. TSD ADR-008 and ADR-018 (S6, S7) are its strongest authority. Neither ADR addresses the reservation record's entity name, so they neither support nor contradict `EntitlementReservation`.
- **`EntitlementReservation` is settled by the summary, with corroboration.** §15.2 alone does not settle the name, because it is name-agnostic (S8). What settles it is S1 together with three things:
  - Appendix E.1 (S9) defines a separate COM-01 `app.entitlement_reservation` table, with its own lifecycle state, expiry and idempotency key, alongside `app.member_entitlement_grant`.
  - OPS-02 holds a foreign key to it (S10).
  - The notes subsection's own prose treats reservation as a distinct atomic, expiring record (S3).

  §15.2 supplies the normative existence and shape of that record, and the summary supplies its only CamelCase name in the TSD.
- **The notes' `Entitlement` has the weakest claim.** It is a generic term, and the post-audit rename (S5) was made precisely to stop such terms being "interchangeable" (S8). Its own subsection contradicts it (S3). No higher-specificity accepted source uses it as an entity name. Treating `Entitlement` as canonical would collapse grant and reservation into one entity, against S8 and S9. That would be a real architecture change, and this decision does not make it.

**The sources are reconcilable, not irreconcilable.** Every accepted normative source (S5-S10) agrees with the summary. Only the notes' list item is out of line, and its own prose disagrees with it.

### Q2. Disclosure and precedence rule (mechanically applicable)

This refines D3 of the prior normalization decision and keeps its default. Intra-domain disagreement stays ERROR `DOMAIN_CONTRACT_SOURCE_INCONSISTENT` and is never auto-resolved by an extractor. It may be resolved only by a pinned, recorded reconciliation entry. That narrows the prior decision's "no text says which representation wins" statement, which the orchestrator hold already flagged as unsupported. It does not reverse D1-D5.

The source tiers, from highest to lowest:

- **T1 (accepted normative):** P0 closure rows, Accepted TSD §3 ADRs, normative Part text (for example §15.2), and Appendix E.1 table ownership.
- **T2:** the §10.x summary "Authoritative entities" cell.
- **T3:** the §10.x Technical Realization Notes "Authoritative entities/tables are…" (or "aggregates are…") line.

The extractor rule, for each domain_id:

1. Extract T2 and T3 verbatim under D2's lexical normalization, using exact case-sensitive identifiers.
2. If T2 equals T3, the entity set is T2. Done.
3. If they differ, look up a reconciliation entry keyed by `(domain_id, mirror_sha256)`. If none exists, or if its sha256 does not match the pinned mirror, emit ERROR `DOMAIN_CONTRACT_SOURCE_INCONSISTENT` (exit 2). Never pick T2 or T3 by default.
4. If a matching entry exists, use its `selected` representation (T2 or T3). It is valid only if every name in `selected` minus `other` cites at least one T1 line span that corroborates it, and it carries a decision-record reference. Otherwise emit ERROR.
5. Always emit a non-blocking `SOURCE_VARIANT` disclosure carrying `{domain_id, selected, rejected_names, missing_names, citations, decision_ref}`. The variant is never silently dropped. Rejected names are never added to the entity set, and they are never used as aliases in the cross-domain comparison.

The T1 citation is a human-recorded pointer. The extractor checks that the line span exists in the pinned mirror. It does not perform semantic matching, so snake_case to CamelCase mapping for E.1 is the recorder's job, not the extractor's.

The COM-01 entry this decision authorizes, as content for whichever later increment builds the register:

```
domain_id: COM-01
mirror_sha256: 292f4335588bfe1e35e72719835ccab318dbe548e7eb520870eb879922bcf6db
selected: T2   # lines 3645-3652
rejected_names: [Entitlement]                                # T3 lines 3731, 3742
missing_names: [MemberEntitlementGrant, EntitlementReservation]  # absent from T3
citations:
  MemberEntitlementGrant: [164-166, 764-770, 833-837, 10509-10513, 17166-17169]
  EntitlementReservation: [10516-10519, 17171-17173, 17213-17216]
decision_ref: R04-GATE6-RESERVATION-ENTITY-LEAD-DECISION-2026-10-09.md
note: T3 "Entitlement" is a pre-rename generic label (P0-02); not an alias, not an entity.
```

The E.1 line spans are approximate to ±2 lines because of how Pandoc wraps table rows. The implementer must re-pin exact spans against the hash before use. **I did not create a reconciliation entry for PLT-03.** The same rule would very likely resolve it (S5, S6 and §15.2 support `PlanEntitlement`), but deciding it is outside this dispatch.

### Q3. May a synthetic-only P1/P2 ADR proceed now?

**Yes.** P1 (command inventory) and P2 (RB-ID) never read the entity dimension. COM-01's command inventory and `RB-COM-01` are unaffected by this question. SCN-014/015/131 use synthetic domains only (S13). Under D1, real-domain content is outside MOD-001 (S12). Under the prior decision's §5 increment, the entity dimension returns `DOMAIN_DIMENSION_NOT_IMPLEMENTED` (exit 2) regardless.

Recording this extraction rule therefore neither performs nor requires the real 57-domain extraction, and it does not make gate 6 any less ERROR. A scoped project ADR (in `knowledge/04-Decisions/`, routed by the parent) may adopt D1-D5, with Q2's precedence rule as its entity-source clause, limited to synthetic P1/P2 enforcement.

## 3. Owner-reservation classification

This is a **technical source-hierarchy and extraction-methodology decision**, within veyro-lead authority:

- It edits no baseline.
- It adds, removes, renames, or re-owns no entity. Both `MemberEntitlementGrant` and `EntitlementReservation` already exist as COM-01 records in accepted TSD text (S1, S8, S9).
- It changes no product, pricing, business, or scope.

**No `OWNER_APPROVAL_REQUIRED` criterion is met, and no owner stop is raised.** An owner or architecture change *would* be needed only to adopt the notes' reading, where `Entitlement` is a single merged entity, because that contradicts S8 and S9. This decision rejects that reading.

## 4. Residuals (deliberately open)

- The real 57-domain extraction, any live domain-contract document, and the live reconciliation and exception registers do not exist. Gate 6 stays `ERROR/GATE_NOT_IMPLEMENTED`.
- The TSD baseline itself keeps the lexical inconsistency (S2 vs S1). Correcting it would be a baseline erratum. It is not needed for this rule, and it is not proposed here.
- Mirror-to-docx fidelity is unverified. The reconciliation entry is valid only for the stated mirror hash.
- PLT-03 (`PlanEntitlement` vs `EntitlementGrant`) and the B2B-01/02 "aggregates" phrasing need their own reconciliation entries or stay ERROR.
- Entity-set fail semantics (identical-set only, per D3) are unchanged. The six-dimension enforcement remains unresolved, as the dispatch requires.

## 5. Next bounded action now legally available

The parent may route one project ADR to `knowledge/04-Decisions/`. That ADR records D1-D5 plus §2 Q2's precedence and reconciliation-entry rule, limited to synthetic fixtures. After that, a veyro-implementer increment may implement `--gate domain-uniqueness` for P1/P2 plus pair-specific exception resolution against synthetic fixtures only, with every other dimension returning `DOMAIN_DIMENSION_NOT_IMPLEMENTED`.

Neither step executes a scenario, grants PASS, promotes gate 6, or certifies MOD-001. Each needs its own independent review before any scenario credit.

## Attestation

Role: `veyro-lead` (architecture judgment). I was invoked as model Opus 5.5, model ID `claude-opus-5-5`. Runner operation: `e4f32c73-700b-4208-836a-11435e040cec`, as given in the dispatch. This process's environment reports `CLAUDE_CODE_SESSION_ID=5ad57cb7-e84e-4e1c-bf58-95cea3e672f9`, which I did not verify against any external ledger. Repository HEAD at decision time: `e481b814a80923849dddfe7a49319112aae7b023`. I wrote exactly one file, this record.

## Orchestrator verification and lean boundary

The guarded operation completed exit 0. The actual named `veyro-lead` child transcript independently passed `mr_verify.py`: **23/23 turns `claude-opus-5-5`**. Private transcript identity/hash and session linkage are in `evidence/model-routing/MR-MOD-001-20261009-006.json`. The phrase “no agent was dispatched” above means the lead did not delegate onward; the ACP parent did dispatch this one lead Task. No independent reviewer was dispatched.

For the next *synthetic-only* ADR, adopt only the decision needed to keep P1/P2 and the pair-specific exception fail-closed while the other four dimensions remain ERROR. The proposed general-purpose T1/T2/T3 reconciliation-entry mechanism is **OPTIONAL now**, with no tracked delivery obligation; revisit only if the future real-domain inventory requires it. The COM-01 source decision is recorded here, and the 57-domain inventory is not being populated in this increment. Do not turn the decision record into a live registry or claim that the full gate is ready. No scenario or module promotion follows from this decision.
