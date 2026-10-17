# Owner decision — MOD-004 ADM-SET-06 scope choice A (publication pending)

**Status: OWNER DIRECTION (OWNER-Q3 option A) recorded on 2026-10-17 (publication pending). Ownership of ADM-SET-06 is NOT operative: it is conditional on separate owner approval of a concrete PLT-01 brand-theme subset/command design. This is a direction, not a waiver, a PASS, an engineering design, an architecture approval, or an acceptance verdict.**

## Authority and exact binding

The verified owner replied in the 2026-10-17 Veyro OpenClaw direct conversation to the exact ADM-SET-06 choice with: “A — MOD-004 V1: add a PLT-01 brand-theme subset/command and stable MOD-066 consumption.” This is an owner choice, not an agent architectural approval. The owner did not approve a detailed engineering design, and none exists.

Owner message ID: OPEN (not available to this record; none is invented). Exact reply time: OPEN. The original message is preserved in the conversation; this file records it prospectively and does not backdate any edit to the pinned EIP, TSD or Blueprint.

## Source conflict resolved (prospectively)

This record resolves OWNER-Q3 as defined in `knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md` D14 and in `knowledge/03-Modules/MOD-004/MOD-004.md` (Screens, ADM-SET-06 row, Unresolved owner-reserved choices). The conflict, as recorded there:

- **TSD WHT-01 (MOD-066, wave V2)** makes `BrandTheme` and `CreateBrandTheme` authoritative (TSD ¶3372, ¶3405, ¶3406; no cross-domain write-table access, ¶3376). Pinned extract `mod004-wht01-screen-primary-mutation-source-20261017.md`, extract SHA-256 `9a397c037be5ac57d7d0902006826a0e85bc8b6c4922da608fd1f24ca440720b`; source TSD SHA-256 `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33`; zero-based paragraphs.
- **TSD PLT-01** has the Brand entity and `brand.created` but no theme command (TSD ¶1204, ¶1206, ¶1237). Source: the TSD pinned evidence, source TSD SHA-256 `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33`.
- **EIP Appendix B PLT-01-R06** (EIP ¶5133-5140) assigns separate branding to MOD-004. Source: `mod004-pinned-source-evidence-20261017.md`, source EIP SHA-256 `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f`.
- **EIP MOD-066 card** (EIP ¶4166, ¶4188) and the V1 registry containing ADM-SET-06 within the 170-screen count (EIP Appendix F ¶8704). Source: `mod004-screen-ownership-source-supplement-20261017.md`, extract SHA-256 `4923b9ad3d631b99c17cc46f4e4c235ee2df8285cbd89c02d12d529dce6a3502`, source EIP SHA-256 `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f`.

The owner chose option A as a direction over B (MOD-066 after a V1 reslice) and C (re-phase out of V1 and rebaseline the 170 count). The pinned documents are unchanged. This record does not resolve the conflict operatively. It records the direction only, subject to the condition below.

## Bounded decision

**Condition (ADR-0002 D14).** MOD-004 UI ownership of ADM-SET-06 occurs only AFTER a separate owner approval of a concrete PLT-01 brand-theme subset/command design (with its stable consumption contract). That approval has not been given, and no detailed design has been presented to the owner. Until it is given, ADM-SET-06 **remains OPEN with no UI implementation owner** in the operative ADR, module spec and screen maps, and Scenario Review remains **blocked** on it. The owner choice is a direction, not a waiver, not a PASS and not an ownership assignment in force.

1. **Direction:** ADM-SET-06 stays in V1 and, conditionally on the approval above, its UI ownership becomes **MOD-004**. The 170-screen count is unchanged and no rebaseline occurs.
2. A **PLT-01 brand-theme subset/command must be designed** in MOD-004 scope, with a **stable consumption contract** that MOD-066/WHT-01 can consume. That design does not exist yet and needs separate owner approval.
3. MOD-066 keeps **WHT-01 authority for its full V2 features** (CMS, app builder, build and store release, and the rest of the WHT-01 scope). This decision does not move that authority and does not reslice MOD-066 into V1.
4. **No duplicate cross-domain writes.** MOD-004 must not write WHT-01 tables, and WHT-01 must not write PLT-01 tables. The design must define a single authoritative write path for any brand-theme data, and a stable command/query/event contract between the domains in place of direct table access. Which side is authoritative for each field is OPEN until the design is reviewed.
5. The actual **command, field, API, permission, masking, idempotency, event and read-model contracts are OPEN**. They need **independent architecture review before any implementation.** The R06 extent (brands, catalogs, pricing, domains, applications, policies) remains owner-reserved beyond this subset; custom domains remain DC-16 spend.

## What this record does not state

- No detailed design exists, and no design is approved.
- It is not an R06 PASS, a Scenario Review PASS, Module Ready, contract lint PASS, or implementation authorization.
- It is not a MOD-066 V1 reslice or a MOD-066 acceptance.
- It sets no route, read-model, command, permission or behavior field in `contracts/ui/screen-contracts.yaml`, and `owning_module` is not changed here.
- It does not answer OWNER-Q2 (Scenario Review timing), which stays PENDING, or any other owner question.
- It does not change the ADR-0002 acceptance, D14 text, MOD-004 spec, registry, runner or UI contracts. Those follow-up edits need their own reviewed changes.

## Retained obligations

All R01–R07 obligations of MOD-004 stay in force, including R06 completion. All product, security, tenant-isolation, privacy, accessibility, CI and acceptance gates stay in force: the module-card Scenario Review, code review, manual QA, TestSprite/A11Y evidence, load evidence, independent review and Approval Certificate. The MOD-007/008 dependency circularity, the tax-number and hours/capacity overlaps, and DC-16 reservations (spend, paid activation, real-member data, production promotion, material product changes) are unchanged. There is no production, payment, credential or cloud approval.

## Publication and evidence

Exact-diff independent Opus review, the local governance check where applicable, a non-force direct-main push, and a successful GitHub Actions run on the exact pushed SHA are prerequisites to treating this record as published. None is claimed here. Until then, and independently until the separate owner approval of the concrete brand-theme subset/command design, ADM-SET-06 remains OPEN in the ADR, module spec and operative maps, and Scenario Review stays blocked. Publication does not make ownership operative.
