# Owner decision — MOD-004 V1 brand-appearance design approval (publication pending)

**Status: OWNER APPROVAL of the scoped MOD-004 V1 brand-appearance design recorded on 2026-10-17 (publication pending). It fulfils the ADM-SET-06 V1 UI ownership condition set in OWNER-2026-10-17-mod004-brandtheme-v1. MOD-004 becomes the operative ADM-SET-06 owner only when this record has been independently reviewed, locally attested and published with a successful exact-SHA CI run. Before that, ownership is NOT operative. This is not an R06 PASS, a Scenario Review PASS, Module Ready, implementation authorization or an acceptance verdict.**

## Authority and exact binding

The verified owner replied in OpenClaw direct chat to prompt message `8005a170-f41f-4330-8263-4fc9e9f6a466` with the exact words: “Approve this scoped V1 design”.

The prompt identified the reviewed MOD-004 V1 brand-appearance proposal in ADR-0002 D15 and its bound Opus review and exact-SHA CI. It asked for approval of:

- the PLT-01 `BrandAppearance` (accent color and tenant-scoped logo reference);
- the `SetBrandAppearance` command;
- the read-only `plt01.brand_appearance.v1` contract for MOD-066 consumption;

while keeping the V2 single-writer handoff and all other gates open. The read-only contract is approved by name; whether that approval extends to the `brand.appearance_changed` event interface (D15.10 Q3) is not established and is OPEN (see the status table below).

This is the separate owner approval of the concrete design that the earlier owner direction (`knowledge/00-Decisions/OWNER-2026-10-17-mod004-brandtheme-v1.md`, ADR-0002 D14 condition) made a prerequisite. That earlier record is historical direction and is not edited here.

Approved design candidate (as presented in the prompt):

- Commit: `a1830aeda11653af8fee12161fab446534a80ce0`
- Foundation CI run `39025873140`: success
- ADR-0002 file SHA-256: `a46bbd589c10b1db0202b843107a79f8cd3c6888ab597e08ea45a8bd9ede490d`
- MOD-004 module spec file SHA-256: `d364d9a6a51992ff23c95dbaab85cd3945ff3bb1509305d2d97e830edf3d1740`
- Prior Opus review `mod004-brandtheme-v1-design-remediation-opus-review-20261017`: APPROVED/VERIFIED and exact-bound to those files. The initial CHANGES_REQUESTED verdict and the remediation remain in the historical task records.

These hashes are the binding identifiers carried in the prompt. This record does not state that the owner independently reviewed source hashes. The pinned EIP and TSD source evidence is cited through ADR-0002 D14/D15 and is unchanged.

Owner message time: not recorded here; none is invented. The original message is preserved in the conversation.

## Scoped consequence

1. The ADM-SET-06 V1 UI ownership condition in ADR-0002 D14 is **fulfilled** by this approval of the D15 design.
2. **MOD-004 becomes the operative ADM-SET-06 owner when, and only when,** this record is independently reviewed, locally attested and published with exact-SHA CI. Publication of this record is the trigger. Nothing here makes ownership operative earlier.
3. The approved scope is limited to the three items named above. V2 single-writer handoff for MOD-066/WHT-01 stays open and is not decided here.
4. **Scenario Review remains BLOCKED**, including after ownership becomes operative, until all of the following are resolved: the Appendix F ¶8741 route/contract lint for ADM-SET-06, the missing `REQUIREMENTS.md`, and OWNER-Q2 (PENDING). Operative ownership does not lift this block.

## Status of ADR-0002 D15.10 questions

This record answers only the approval described in the quoted reply. Nothing below is decided on the owner's behalf.

| Question | Status in this record |
|---|---|
| Q1 | **Split.** *Approved (scoped V1 design):* `BrandAppearance` as the PLT-01 aggregate with PLT-01 as V1-only writer, and the V1 field-level authority split, as presented in the prompt. *OPEN (V2 handoff):* whether WHT-01 owns logo or color in V2, and any separately reviewed, owner-approved single-writer handoff, migration or coexistence boundary. No MOD-066 writer authority is claimed before V2 and no duplicate writer is allowed. |
| Q2 | OPEN. Traceability/amendment question on EIP ¶8740 and TSD WHT-01 ¶3406 is not answered. OWNER-Q2 (Scenario Review timing) is PENDING. |
| Q3 | **OPEN (partly).** The owner's reply approved the named read-only contract `plt01.brand_appearance.v1` for MOD-066 consumption. D15.7 defines that contract's interfaces as the `GetBrandAppearance`/`ListBrandAppearanceHistory` queries and the `brand.appearance_changed` event. The prompt as recorded here does not show that the owner was asked about, or answered, adding `brand.appearance_changed` to the PLT-01 event set (not in TSD ¶1206). Whether the owner's approval of the contract covers the event interface is therefore not established by existing evidence and is not decided here. The event addition, its name and the MOD-010 relay stay OPEN. D15.7 is unchanged. |
| Q4 | OPEN. Color token model, contrast/guardrail rule and thresholds. |
| Q5 | OPEN. Brand creation/maintenance command source and whether `ChangeOrgHierarchy` covers it. |
| Q6 | OPEN. Logo storage flow; no tenant-scoped object-storage layer exists and an accent-only V1 alternative is not chosen here. |
| Q7 | OPEN. Permission names and masking with MOD-007/008. |
| Q8 | OPEN. MOD-007/008 circularity and MOD-010 outbox sequencing. |

The approval of the V1 design in this record therefore does not close Q2–Q8, and the V2 half of Q1 stays open.

## What this record does not state

- It does not claim R06 complete, a Scenario Review PASS, Module Ready, contract lint PASS or implementation authorization.
- It does not set any route, read-model, command, permission or behavior field in `contracts/ui/screen-contracts.yaml`, and `owning_module` is not changed here.
- It does not make logo storage available or approve any storage, upload or cloud resource.
- It is not a MOD-066 V1 reslice, a MOD-066 acceptance, or a V2 handoff decision.
- It decides nothing on MOD-007/008/010 sequencing or on permission or guardrail thresholds.
- It gives no spending, paid-activation or cloud approval.
- The owner did not answer OWNER-Q2 (Scenario Review timing). It stays PENDING. No other owner question is answered or expanded.
- It does not edit the ADR, module spec, pinned sources, registry or any other file. Follow-up edits need their own reviewed changes.

## Retained obligations

The 170-screen count is unchanged. Strict tenant isolation and RLS stay in force. There are no duplicate cross-domain writes: MOD-004 must not write WHT-01 tables, WHT-01 must not write PLT-01 tables, and any brand data keeps a single authoritative write path. All R01–R07 obligations of MOD-004 stay in force, including R06 completion. All product, security, privacy, accessibility, CI and acceptance gates stay in force: Scenario Review, code review, manual QA, TestSprite/A11Y evidence, load evidence, independent review and Approval Certificate. DC-16 reservations are unchanged. There is no production, payment, credential or cloud approval.

## Publication and evidence

Exact-diff independent review, local owner attestation, a non-force direct-main publication and a successful GitHub Actions run on the exact pushed SHA are prerequisites for ownership to become operative. None is claimed for this record here.
