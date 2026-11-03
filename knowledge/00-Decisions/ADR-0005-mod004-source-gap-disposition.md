# ADR-0005 — MOD-004 PLT-01 source-gap disposition: missing commands, events and read models

- ID: ADR-0005
- Status: ACCEPTED
- Review: VR-ADR0005-20261103-001 APPROVED
- Decision-Key: mod004-plt01-source-gap-disposition
- Covers: knowledge/03-Modules/MOD-004/MOD-004.md

**Scope and limits.** This ADR is ACCEPTED, as a disposition record only, and that acceptance was operationally conditional on its own independent exact-diff review and its own exact-SHA push CI. Both are now recorded for the flip commit `32fc20b` in Next-gate checklist item 4, on the disclosed-assertion terms set out there and in the next paragraph: the reviewed bytes and the CI run are verifiable, while the review's performance and performer are asserted. Any edit made after `32fc20b` is new bytes needing its own review and CI, and none is claimed. It is documentation and design only, which ADR-0002 D12.1 makes legal now, and it authorizes nothing: no code, migration, schema, table, dependency, capability activation, command, event, projection, permission or environment preparation. It decides how each recorded source gap is *disposed* (escalate to the owner, defer to a named module, or carry as a design proposal), not what any gap's content should be, and it answers none of the owner questions it surfaces. It claims no module acceptance, Ready state, Scenario Review PASS, product PASS or satisfaction of PLT-01-R01..R07. `Covers` names only `knowledge/03-Modules/MOD-004/MOD-004.md`, the uncontrolled file where the gap register is kept today as prose, so it grants nothing the validator enforces and claims nothing.

**Review header: what it refers to.** **`VR-ADR0005-20261103-001` is a document-assigned label**, not an identifier that the review's own artifacts carry. It labels the independent Opus review performed on 2026-11-03 of the PROPOSED bytes of this file, SHA-256 `7dc32499e8eb21b1d71e6ad253e96b4471afdd53af43df2e260f2b97ed86dfe7`, published as commit `5c891b944562390b4cb12a54fa843442b5bb3f1c` with exact-SHA push CI run `41686359863` completed success (OUTCOME APPROVED). That review ran in the Claude Code session that commissioned it, so it has **no runner run-evidence artifact and no `review_bound_verified` field**: reviews after the runner's retirement leave no `*.evidence.json`, and this paragraph is the only account of it. Its performance, its performer and the reviewer's lack of write tools are asserted here and are not independently verifiable. The bytes it covered are verifiable: that SHA-256 is the content of this file at `5c891b9`. The governance validator checks only the format of the id (`^[A-Za-z0-9._-]{3,64} APPROVED$`) and does not verify that a review exists. **That review covered the PROPOSED draft, not this status change.** This status change needed its own independent exact-diff review and its own exact-SHA push CI, and both are recorded for `32fc20b` in Next-gate checklist item 4 rather than by this header, which is not retroactively a review of the flip. Every edit made after `32fc20b` is new bytes needing its own review and CI; none is claimed.

**Authority path.** The standing authority for this file is ADR-0001 (ACCEPTED, key `governance-foundation-change-control`), which covers `knowledge/00-Decisions/` and is not part of this change. This ADR cannot authorize its own file: `check-change --decision ADR-0005` blocks (Next-gate checklist item 1). The `Review` header is explained in the preceding paragraph.

## Context
**Pinned sources.** EIP v2.0 Lean Foundation, SHA-256 `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f`; TSD v1.4.2 Foundation Clarification, SHA-256 `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33`. Quoted text below is from the read-only extract `mod004-pinned-source-evidence-20261017.md` (SHA-256 `a094e28fb84b26ef591371a64a96d4d741aa6c5d8de381da523cbb46346975ac`) and its manifest `mod004-pinned-source-evidence-20261017.manifest.json` (SHA-256 `8842f472673cb661e32e2d9fbc5ac73eadd837e929ad2208880469f9d3ac4e1a`), kept outside the repository in `~/Library/Application Support/Veyro/mission-runner/reviews/`. ADR-0002 and MOD-004.md name this bundle without pinning its hash; this ADR pins both files. Both hashes were checked with `shasum -a 256` on 2026-11-03, and the manifest's `bundle_sha256` equals the extract's hash. The four sections this ADR relies on were each re-hashed from the extract's fenced block (every line as printed with its `¶N: ` prefix, LF-terminated) and match the manifest:

| Source | Section | Paragraphs | SHA-256 |
|---|---|---|---|
| TSD | §10.1 PLT-01 implementation contract | ¶1194-1245 | `deed9cdc913bf23b9c280b799c7c8025317996afb2ae242daa76473fcaadcf8f` |
| TSD | §7.5 tenant-placement/relocation contract | ¶775-783 | `c3cc0e023a0cbd2998dc742e6345421a1920e8f3e35716990967a7eef89e2d3b` |
| EIP | Appendix B PLT-01-R01..R07 rows | ¶5084-5148 | `0cd342289184036a1388410f135f1674004bada1d800b32ee2b2ce697ae83a34` |
| EIP | §21.5 MOD-004 module card | ¶1934-1969 | `17661ca243fe8702ffba78d1ae8f4a09c3c23050e1740196d687120148f7f19e` |

This is source evidence, not an owner decision, waiver, PASS or acceptance. The extract is not in the repository working tree, so a reviewer working only from the repository cannot re-check the quotations; MOD-004.md Next-gate checklist item 6 already records that making the extracts reachable is an owner action.

**Numbering convention.** This bundle is **1-based** (its manifest: "1-based paragraph indexes"). TSD ¶1204, ¶1206, ¶1216, ¶1222, ¶1237, ¶1238 and ¶1241, TSD ¶775-783, and EIP ¶1934-1969 and ¶5084-5148 are 1-based, and every other TSD or EIP paragraph cited here, except EIP ¶754 (below), lies inside those ranges. EIP ¶8740, ¶8741 and ¶1959, which ADR-0002 and MOD-004.md cite from the zero-based screen-ownership supplement, are zero-based (¶1959 there is ¶1960 in this bundle); this ADR relies on none of them for content. EIP ¶754 is outside this bundle and is cited only as ADR-0002 cites it. Every citation carries an explicit `EIP` or `TSD` prefix; unprefixed paragraph numbers inside quotations of ADR-0002 are TSD.

**Requirements.** EIP Appendix B names MOD-004 as completing module for each of R01..R07 (EIP ¶5097, ¶5105, ¶5113, ¶5121, ¶5129, ¶5137, ¶5145), each "Full requirement implemented and completed in the listed module." (EIP ¶5100, ¶5108, ¶5116, ¶5124, ¶5132, ¶5140, ¶5148). The EIP §21.5 card adds "No special waiver. All Development Constitution gates apply." (EIP ¶1954) and "No standing module-specific approval, but DC-16 always reserves spend, paid activation, real-member-data processing, production promotion and material business/product changes to the owner." (EIP ¶1964).

| Req | Paragraph | Requirement text |
|---|---|---|
| R01 | EIP ¶5098 | "Provision, activate, suspend, archive and delete tenants through a controlled lifecycle." |
| R02 | EIP ¶5106 | "Model organization, legal entity, brand, region, location, department and cost-center hierarchies." |
| R03 | EIP ¶5114 | "Enforce tenant-aware identifiers, storage paths, search indexes, events, caches, logs and background jobs." |
| R04 | EIP ¶5122 | "Support tenant templates, cloning, defaults, regional settings and configuration inheritance." |
| R05 | EIP ¶5130 | "Provide data residency, deployment-region and encryption-key assignment policies." |
| R06 | EIP ¶5138 | "Allow multi-brand ownership with separate branding, catalogs, pricing, domains, applications and policies." |
| R07 | EIP ¶5146 | "Maintain tenant lifecycle history and prevent hard deletion before legal, billing and retention gates pass." |

**The inventories, verbatim.**
- Entities, TSD ¶1204 (nine): "Tenant, Organization, LegalEntity, Brand, Region, Location, Department, CostCenter, TenantConfiguration".
- Commands, TSD ¶1237 (seven): "Command inventory: ProvisionTenant, ActivateTenant, SuspendTenant, ChangeOrgHierarchy, AssignRegion, RelocateTenant, ArchiveTenant. Every command declares permission, idempotency, expected aggregate version and transaction boundary."
- Events, TSD ¶1206 (six): "tenant.provisioned, tenant.activated, tenant.suspended, organization.updated, location.opened, brand.created". TSD ¶1241 repeats them: "Published events: tenant.provisioned, tenant.activated, tenant.suspended, organization.updated, location.opened, brand.created. Consumed dependencies: Platform foundation; dependencies are accessed by stable contracts/projections, never direct write-table joins."
- Projections, TSD ¶1238: "Queries/read models: List/detail and history projections for Tenant, Organization, LegalEntity, Brand; role/surface-specific attention/summary read models for Internal SaaS Console; Admin Web; APIs; every projection exposes freshness/version metadata when asynchronously built."
- Lifecycle, TSD ¶1222 (five transitions): "Provision, activate, suspend, archive and delete tenants through a controlled lifecycle."

**Supporting paragraphs, verbatim.**
- TSD ¶1216: "Transactional outbox for state changes; idempotent consumers. Durable workflow orchestration for multi-step/timer/provider processes."
- TSD ¶776: "Tenant placement is a control-plane record with source cluster, target cluster, region, encryption-key assignment and relocation state. The product plane resolves placement before issuing database credentials or signed service routes."
- TSD ¶777: "Relocation stages: preflight → target provision → snapshot/copy → change-data catch-up → write freeze → final delta → integrity/financial reconciliation → route switch → cache/session invalidation → observation window → source quarantine → source deletion after retention gate."
- TSD ¶778: "The cutover uses a relocation_epoch included in requests/events. Commands carrying the old epoch are rejected after route switch. All copied row counts, ledger control totals, outbox high-water marks, object references and search/read projections are reconciled before source deletion."
- TSD ¶1230 and ¶1231: "No cross-tenant query, cache, file, event or search result is permitted." and "Destructive lifecycle actions require approvals, retention checks and an immutable audit record."
- TSD ¶1242: "Failure/degraded behavior: Write commands fail atomically; asynchronous effects retry idempotently; stale read models carry freshness and cannot authorize a consequence-bearing mutation beyond budget."

**What ADR-0002 already records.** ADR-0002 D8.3 (outside its accepted D1-D6 scope; its header lists "later source gaps (D8.3)" as still OPEN) reads: "Source gaps are recorded, not filled: R01 and R04 name deletion, cloning and templates but ¶1237 has no delete/clone/template commands; ¶1206 has no archived/deleted/relocated events; published `brand.created` and `location.opened` have no matching commands; there is no maintenance command for LegalEntity, Department, CostCenter or TenantConfiguration; ¶1238 read models cover four of nine entities. A later ADR must decide these before code." ADR-0002 D7 adds: "There is no encryption-key assignment command in ¶1237, and durable workflow orchestration (¶1216) has no complete owner or design: both OPEN." ADR-0002 D13 defers "the delete/clone/template/key-assignment commands and missing events (D8.3); workflow orchestration (D7)". ADR-0002 Next-gate checklist item 6 asks for a "Later ADR" on them, and MOD-004.md Next-gate checklist item 8 asks for an "ADR for missing commands/events/read models and the other source gaps." MOD-004.md "Source gaps to resolve by ADR, not in code" records the same gaps as prose. This is that ADR.

**Why a new file rather than an ADR-0002 edit.** `OWNER-2026-10-28-mod004-d16-design-admission.md` (Smallest admissible route, item 6) names ADR-0002 as the only file the admitted D16 design root may change. Keeping this disposition out of ADR-0002 leaves that file's byte history uncomplicated for whatever the owner later decides about that lineage. This ADR neither revisits nor asks anything about D16.

## Decision
Marking, as in ADR-0002: **[SRC]** means mandated by the cited source paragraph. **[INFERENCE]** means an engineering reading extending a source paragraph, flagged so review can challenge it. **[PROPOSAL]** means a concrete engineering choice offered here with rationale; it is not an owner business-policy decision and, in this ADR, it authorizes nothing. In this section "ADR-0002 D…" always means ADR-0002; bare "D1".."D4" mean this ADR's decisions. Register rows are labelled A1-A10, B1-B4, C1-C2 and W1 (the workflow row is W1, not D1, to avoid confusion with this ADR's decisions).

### D1. The disposition rule [INFERENCE]
No pinned paragraph states how a source gap is to be resolved, or that the inventories in TSD ¶1204, ¶1206, ¶1237, ¶1238 and ¶1241 are exhaustive. Each gap is therefore disposed by the consequence of closing it. The clauses are ordered; the first that matches governs.
1. **ESCALATE** if closing the gap would move domain or module authority, change which module completes an EIP Appendix B requirement, amend or contradict a pinned document, add or change a business rule, value, duration, threshold, default, approver or quorum, or touch anything DC-16 reserves. Record the exact minimal question and decide nothing. Where an existing recorded question covers the gap, reuse it instead of writing a second.
2. **DEFER** to a named module if the gap needs a mechanism another module owns per `tools/mission_runner/module_catalog.json` or a pinned card. A deferral never defers the Appendix B requirement, which stays wholly MOD-004's (EIP ¶5097 and its six siblings above), and is never a PASS.
3. **PROPOSE** as a [PROPOSAL] design item if closing the gap is a naming or structural choice inside PLT-01's own command, event or projection surface that adds no business semantics, no owner-reserved value and no new cross-module contract or authority. A proposal authorizes no code, migration, schema, dependency or capability activation.
4. **Default.** A gap that matches no clause cleanly, or more than one ambiguously, is treated under clause 1. Ambiguity resolves toward the owner, never toward a proposal.

### D2. The open/closed reading of the inventories [INFERENCE, offered for the reviewer to challenge]
TSD ¶1237 and ¶1238 each carry a generative rule over their class: "Every command declares permission, idempotency, expected aggregate version and transaction boundary." and "every projection exposes freshness/version metadata when asynchronously built". The second clause of ¶1238 ("role/surface-specific attention/summary read models for Internal SaaS Console; Admin Web; APIs") names a class rather than an enumeration. TSD ¶1206 is a bare list with no accompanying rule over the published-event class. TSD ¶1241 repeats that list and does carry a rule ("dependencies are accessed by stable contracts/projections, never direct write-table joins"), but its subject is consumed dependencies, not the published-event class, so it generates nothing about which events may be added.

Reading adopted: the command inventory (TSD ¶1237) and the projection inventory (TSD ¶1238) are open to additions that an EIP Appendix B requirement needs. An addition to the published event set (TSD ¶1206, ¶1241) is a cross-module contract change, because the outbox envelope, idempotent consumers and the MOD-010 bus depend on it (ADR-0002 D8.2), and so it escalates (NQ1).

Counter-reading, stated so the reviewer can choose it: a generative rule says what each listed member must declare, not that the list may grow. "Command inventory:" is an enumeration whose closure the text neither states nor denies, and TSD ¶1238's first clause enumerates four entities. On that reading a command that an Appendix B requirement needs but TSD ¶1237 omits is a defect in the pinned source for the owner, not an engineering addition (NQ2).

This is consistent with ADR-0002 D15.6, which treats an event outside TSD ¶1206 as "a source-gap addition that requires owner/Opus decision", and with D15.10 Q3. It does not answer Q3: Q3 concerns the one event `brand.appearance_changed`, which this ADR neither adds nor assesses, and it stays OPEN.

Label evidence that cuts against this ADR's own position, stated so the reviewer can weigh it. The pinned label of the event list is "Key events" (TSD ¶1205, immediately above the ¶1206 list), not "Published events" or "All events". "Key" leans toward the six names being illustrative rather than exhaustive, which would support an open reading for events as well as for commands and projections and would remove the ground for the NQ1 escalation. TSD ¶1241 labels the same six "Published events", which leans the other way, so the two labels together do not settle the reading. This ADR escalates anyway because the final clause of D1 (clause 4) resolves a gap that matches no clause cleanly toward the owner and never toward a proposal. NQ1 leaves the owner room to reach the other outcome: its option (c), only an accepted engineering ADR.

### D3. The gap register
Every row cites its source paragraph. "Existing question" means a question already recorded in ADR-0002's "Unresolved owner-reserved choices" (cited as ADR-0002 Unresolved item N) or in MOD-004.md's list of the same name; no new question is asked for those rows. TSD ¶1237's `ChangeOrgHierarchy` is the nearest-named command to A5-A9 and `organization.updated`, `location.opened` and `brand.created` are the nearest events; this ADR does not assert that `ChangeOrgHierarchy` covers any of A5-A9 (MOD-004.md "Source gaps" makes the same non-assertion).

**A. Commands absent from TSD ¶1237**

| Row | Gap | Source | Disposition | Note |
|---|---|---|---|---|
| A1 | Delete tenant. `ArchiveTenant` exists; no delete command | EIP ¶5098 (R01), ¶5146 (R07); TSD ¶1222, ¶1231, ¶1237 | ESCALATE | Existing question: ADR-0002 Unresolved item 2 (lifecycle retention periods, legal/billing/retention gate criteria, deletion approvals and who approves destructive actions). Also behind MOD-008 immutable audit (TSD ¶1231); ADR-0002 OWNER-Q1 and its default are unchanged |
| A2 | Clone tenant | EIP ¶5122 (R04); TSD ¶1225, ¶1237 | ESCALATE | Existing question: ADR-0002 Unresolved item 3 (template and default contents) |
| A3 | Template, defaults and configuration-inheritance commands | EIP ¶5122 (R04); TSD ¶1225, ¶1237 | ESCALATE | Existing question: ADR-0002 Unresolved item 3. The MOD-005 overlap with R04 is recorded in MOD-004.md "Structural dependency and overlap risks" |
| A4 | Encryption-key assignment | EIP ¶5130 (R05); TSD ¶776, ¶1226, ¶1237 | ESCALATE | Existing question: ADR-0002 Unresolved item 1 (regions, data-residency policy, KMS/encryption keys, spend; DC-16). MOD-009 (catalog objective names key management) is mechanism traceability only. ADR-0002 D7's proposal that key assignment "holds a reference, never key material" is neither adopted nor changed here |
| A5 | Brand create/maintain. `brand.created` is published; no matching command | TSD ¶1204, ¶1206, ¶1237; EIP ¶5106 (R02) | PROPOSE | Gives ADR-0002 D15.10 Q5 a disposition (a design item) without asserting that `ChangeOrgHierarchy` covers it; Q5 stays OPEN until a proposal is reviewed. Touches no brand theme or appearance authority (ADR-0002 D15 core unchanged); the R06 extent (EIP ¶5138) stays owner-reserved |
| A6 | Location create/maintain. `location.opened` is published; no matching command | TSD ¶1204, ¶1206, ¶1237; EIP ¶5106 (R02) | PROPOSE, for the PLT-01 Location record only | Hours and capacity overlap scheduling/access modules and stay escalated (unresolved overlap recorded in ADR-0002 D14 and the MOD-004.md Screens ADM-SET-02 row) |
| A7 | LegalEntity maintenance | TSD ¶1204, ¶1237; EIP ¶5106 (R02) | PROPOSE, for the PLT-01 LegalEntity record only | The tax-number overlap (tax owner not assigned) stays escalated (ADR-0002 D14 and the MOD-004.md Screens ADM-SET-01 row) |
| A8 | Department maintenance | TSD ¶1204, ¶1237; EIP ¶5106 (R02) | PROPOSE | Hierarchy cardinalities stay owner-reserved (ADR-0002 Unresolved item 3) and are not decided |
| A9 | CostCenter maintenance | TSD ¶1204, ¶1237; EIP ¶5106 (R02) | PROPOSE | As A8 |
| A10 | TenantConfiguration maintenance | TSD ¶1204, ¶1237; EIP ¶5122 (R04: regional settings, configuration inheritance) | ESCALATE | Existing question: the PLT-01/MOD-005 configuration boundary (ADR-0002 Unresolved item 4, "configuration overlap (MOD-005)"; MOD-004.md lists MOD-005 with R04) |

**B. Events absent from TSD ¶1206 and ¶1241.** All four rows ESCALATE under clause 1 because a published event is a cross-module contract (D2), and all four are disposed by one consolidated new question, NQ1. The names in B1-B3 are descriptive labels formed on the ¶1206 naming pattern [INFERENCE]; they are not proposed event names and no event is added.

| Row | Gap | Source | Disposition | Note |
|---|---|---|---|---|
| B1 | An archived event (`tenant.archived`) against `ArchiveTenant` | TSD ¶1206, ¶1222, ¶1237, ¶1241; ADR-0002 D8.3 | ESCALATE (NQ1) | |
| B2 | A deleted event (`tenant.deleted`) | TSD ¶1206, ¶1222, ¶1241; ADR-0002 D8.3 | ESCALATE (NQ1) | Also depends on A1: there is no delete command to publish it |
| B3 | A relocated event (`tenant.relocated`) against `RelocateTenant` | TSD ¶777-778 (`relocation_epoch` "included in requests/events"), ¶1206, ¶1237; ADR-0002 D8.3 | ESCALATE (NQ1) | |
| B4 | [INFERENCE] A placement or region-change event against `AssignRegion` | TSD ¶776 (placement record: region, encryption-key assignment, relocation state), ¶1206, ¶1237 | ESCALATE (NQ1) | No document records this as a gap. It is added here because `AssignRegion` changes placement state and ¶1206 has no event for it |

Non-claims for B. (i) TSD ¶1222 names five lifecycle transitions (provision, activate, suspend, archive, delete). None of TSD ¶1222, ¶1237 or ¶1206 names a resume or unsuspend transition, command or event, so none is claimed or invented. (ii) ADR-0002 D15.10 Q3 stays OPEN. (iii) The outbox relay and the bus stay MOD-010's (ADR-0002 D8.2); their sequencing stays unresolved. (iv) No event is proposed for the twelve relocation stages of TSD ¶777; those are workflow states (W1), not published events.

**C. Read models absent from TSD ¶1238**

| Row | Gap | Source | Disposition | Note |
|---|---|---|---|---|
| C1 | Region, Location, Department, CostCenter and TenantConfiguration have no named projection. TSD ¶1238 names list/detail and history projections for four of the nine TSD ¶1204 entities (Tenant, Organization, LegalEntity, Brand) | TSD ¶1204, ¶1238; ADR-0002 D8.3 | PROPOSE | Which of the five actually need a projection follows the consuming screens and APIs and is OPEN. TSD ¶1238 and ¶1242 freshness rules apply to any projection built; no staleness-budget value is set here (ADR-0002 D8.5, OPEN). R03's search/read-model release-gate layer (EIP ¶1946, ¶5114) stays OPEN |
| C2 | [INFERENCE] The role/surface-specific attention/summary read models for the Internal SaaS Console, Admin Web and APIs have no design. Not recorded as a gap in ADR-0002 or MOD-004.md | TSD ¶1238 | DEFER | To the owner of each consuming screen or API as MOD-004.md Screens records them (for example MOD-029 for CON-01 and CON-03, recorded there as [INFERENCE]; the catalog objective is "internal SaaS operations, support diagnostics and customer-success controls without unsafe tenant bypass"). Every screen contract field is null today. MOD-004 supplies tenant-scoped projections only. Any cross-tenant read needs an ADR-0002 D6.3 allowlist entry (an ADR change) that is **not** made here, and no cross-tenant projection is designed or authorized (TSD ¶1230). This ADR assigns no screen and re-decides no mapping |

**D. Workflow orchestration**

| Row | Gap | Source | Disposition | Note |
|---|---|---|---|---|
| W1 | TSD ¶1216 durable workflow orchestration and the twelve-stage relocation workflow of TSD ¶777 have no command, owner or design | TSD ¶777-778, ¶1216, ¶1240; ADR-0002 D7 | ESCALATE (NQ3), a new question | Clause 1: which module owns durable orchestration is a module-authority question. The catalog lists MOD-055 "Automation & Workflow Orchestration" (wave V1.5; objective "tenant automations with bounded actions, retries, approvals and loop protection"), but no pinned paragraph read here says it is the ¶1216 mechanism for control-plane provisioning and relocation, so no owner is inferred. The stages, freeze windows and reconciliation are not designed here |

This ADR proposes no orchestrator, scheduler, broker, dispatcher or approval framework, and does not start, restart, repair or rebuild the development runner, which is retired as an execution path. The directory `tools/mission_runner/` is not retired: it is tracked, live code under ADR-0001 and ADR-0004 whose tests CI runs, and this ADR reads `tools/mission_runner/module_catalog.json` from it (D1 clause 2, W1).

### D4. Consequences of each clause
1. **ESCALATE** rows (A1-A4, A10, B1-B4, W1) stay open at the owner. R01, R04, R05 and R07 stay OPEN in MOD-004.md behind the escalated rows. That scoping is not a claim that the other requirements are closed: MOD-004.md also records R02 and R06 as OPEN and R03 as mapped for PostgreSQL only with its events, jobs, search, storage, telemetry and AI parts OPEN, and this ADR changes none of that. Nothing is built around the escalated rows; stubbing a missing command and claiming completion would be a waiver (MOD-004.md Unresolved item 4).
2. **DEFER** (C2) names the module a mechanism belongs to and nothing more. It is not a PASS, a waiver or an assignment of ownership, and the requirement stays MOD-004's. Any dependency or sequencing it implies is the cross-module sequencing question already recorded (ADR-0002 Unresolved item 4).
3. **PROPOSE** rows (A5-A9, C1) are design items only. A [PROPOSAL] authorizes nothing and names no permission, authority head, grant, approval, idempotency or version semantics; TSD ¶1237 requires each command to declare permission, idempotency, expected aggregate version and transaction boundary, so any later design must, and this ADR declares none. Each item needs its own review before it enters MOD-004.md as design, and code stays gated by Ready and an ACTIVE capability manifest.
4. **Default to clause 1** raises the count of escalations. That cost is accepted: it is cheaper than engineering absorbing owner policy.

## Rationale
One reviewed rule beats per-gap ad hoc judgement: the same gap would otherwise be classified differently by each future author, as the open Q3 and Q5 in ADR-0002 D15.10 show. Escalations arrive as exact minimal questions, which turns MOD-004.md Next-gate checklist item 7 from a standing prose list into questions the owner can answer one at a time. The fail-closed default in D1 clause 4 keeps engineering from absorbing owner policy by describing it as structure.

## Alternatives considered
- Amend ADR-0002 D8.3 in place: rejected. ADR-0002 is the file the D16 design root may write (see Context), so its byte history should stay uncomplicated, and D8.3 sits outside ADR-0002's accepted scope.
- Escalate every gap: rejected. It would make the owner decide consequence-free naming and structure choices (A5-A9, C1).
- Propose every gap: rejected. It would have an engineering ADR add business policy (retention, approvers, template contents, key policy) and a cross-module event contract.
- Leave the gaps as MOD-004.md prose: rejected. That prose records the gaps but is not a decision record, the file is not ADR-controlled, and checklist item 8 asks for an ADR.

## Consequences
- Dispositions are recorded for 17 register rows: 10 ESCALATE (A1-A4 and A10 to existing questions, B1-B4 to NQ1, W1 to NQ3), 1 DEFER (C2) and 6 PROPOSE (A5-A9, C1). No row's content is decided.
- Whether recording dispositions satisfies ADR-0002 D8.3's "A later ADR must decide these before code" is for the reviewer to judge; this ADR does not claim that MOD-004.md checklist item 8 or ADR-0002 checklist item 6 is closed.
- R01, R04, R05 and R07 stay OPEN behind the escalated rows. That is scoped to those rows: R02 and R06 are also OPEN and R03 is mapped for PostgreSQL only with its other parts OPEN (MOD-004.md Requirement map), so no reader should infer that R02, R03 or R06 is closed. PROPOSE rows move no requirement to "mapped" or "planned".
- Three new owner questions are created (NQ1-NQ3); no existing question is altered or answered.
- A "Closed" answer to NQ2 converts A5-A9 from PROPOSE to ESCALATE. Nothing is built meanwhile, so being overturned costs nothing.
- Each PROPOSE item is later designed under its own reviewed ADR or MOD-004.md change.

## Unresolved owner-reserved choices (not decided here)
Exactly three new questions. Each is NOT ASKED and no owner answer is assumed. For NQ2 this ADR proceeds on the Open reading as [INFERENCE] (D2), with the conversion rule stated at NQ2.

**NQ1 (disposes B1-B4).** "Does extending the PLT-01 published event set beyond the six events in TSD ¶1206/¶1241 need (a) an owner decision, (b) a controlled traceability note to the pinned documents, or (c) only an accepted engineering ADR?" It does not answer ADR-0002 D15.10 Q3, which concerns the single event `brand.appearance_changed` and stays OPEN.

**NQ2 (bears on A5-A9).** "Is the TSD ¶1237 command inventory a closed list, so that a missing command an Appendix B requirement needs is a defect in the pinned source for the owner, or is it open to extension by an accepted engineering ADR? Closed / Open." This ADR adopts Open as [INFERENCE] (D2). A "Closed" answer converts A5-A9 from PROPOSE to ESCALATE; since nothing is built meanwhile, the cost of being overturned is nil. NQ2 is asked of ¶1237 only: whether a "Closed" answer is meant to reach TSD ¶1238 (C1) is for the owner to say, and this ADR assumes nothing.

**NQ3 (disposes W1).** "Which module owns durable workflow orchestration (TSD ¶1216) for PLT-01's multi-step provisioning and relocation processes?"

Pointers, unchanged: ADR-0002's "Unresolved owner-reserved choices" items 1-7 (including OWNER-Q1 and OWNER-Q2 PENDING and OWNER-Q3 ANSWERED) and D15.10 Q1-Q8, and MOD-004.md's list of the same name. A1-A4 and A10 reuse items 1-4 and ask nothing new.

## Not claimed
- No code, migration, schema, table, column, index, dependency, PostgreSQL or `psycopg` pull, capability activation or environment preparation.
- MOD-004 is not Ready. The EIP ¶754 capability manifest, `contracts/engineering/module-capabilities.yaml`, is PROVISIONAL with `gate_eligible: false` and four OPEN blockers (`BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`, `BLK-SKL-MIGRATION-LINT`, `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW`, `BLK-RULE-QUALIFICATION`).
- No module acceptance, Ready state, Scenario Review PASS, product PASS or satisfaction of PLT-01-R01..R07. Scenario Review stays BLOCKED (ADR-0002 D14, OWNER-Q2).
- All seven release-gate isolation layers remain unevidenced.
- No command, event or projection is added to the product, and no permission, authority head, operator grant, approval quorum, aggregate-version or AAL-3 semantics is defined.
- No new D16 attempt, root rename or counter reset is proposed or implied. The four recorded `CHANGES_REQUESTED` outcomes of the D16 design lineage (`OWNER-2026-10-28-mod004-d16-design-admission.md` line 12) and the one design attempt recorded as consumed stand exactly as recorded; any further D16 work needs the owner first. A reviewer with access to the preserved archive can verify the consumed attempt in `~/Veyro-Migration-Archive-20261101/07-worker-owned-preserved/v2-mission-runner-state/v2/state.json`, which records for task root `mod004-d16-dual-version-sonnet-20261026` `status` FAILED, `attempts` 1, `max_attempts` 1 and `finished_at` 2026-10-30T10:04:39+00:00 (read only; it records a failure, not an approval).
- No frozen-baseline, `OWNER-*`, `contracts/**`, workflow, runner, registry or governance change, and no DC-16 action.
- No orchestrator, scheduler, broker, dispatcher or approval framework.
- No cross-tenant read path, and no change to the ADR-0002 D6.3 allowlist.
- No paragraph renumbered and no source text invented. Every reading beyond quoted text is labelled [INFERENCE].
- ADR-0002 D15.10 Q1-Q8 and OWNER-Q1 and OWNER-Q2 stand exactly as recorded, and OWNER-Q3 stands as ANSWERED.
- ADR-0002 is unchanged by this ADR. MOD-004.md gains only a cross-reference to this ADR in its source-gaps section and in checklist item 8, which ticks nothing, answers nothing and decides nothing.

## Next-gate checklist
1. [ ] Governance `check --root .` and `check-change` with ADR-0001 as the cited decision, piping the changed paths on stdin. `check-change --decision ADR-0005` is expected to BLOCK, because an ADR cannot authorize its own file; that is the control working, not a defect. Observed on 2026-11-03: while PROPOSED it blocked as `CHANGE_ADR_NOT_ACCEPTED`; once ACCEPTED both `CHANGE_SELF_AUTHORIZING` and `CHANGE_ADR_NOT_COVERING` fire together (the ADR's own file is part of the change, and `Covers` names only MOD-004.md).
2. [x] Done for the PROPOSED bytes committed as `5c891b9`: independent Opus exact-diff review labelled `VR-ADR0005-20261103-001`, OUTCOME APPROVED, performed on 2026-11-03. Its performance is asserted, not independently verifiable (see the review paragraph under Scope and limits). This item's original wording asked that the review challenge D2's reading and each row's disposition with the pinned extract readable to the reviewer; this record does not separately confirm either.
3. [x] Done for `5c891b9`: non-force publication and exact-SHA push CI run `41686359863` completed success. This covers the PROPOSED bytes only.
4. [x] Done for the ACCEPTED flip committed as `32fc20b`: an independent Opus exact-diff review of that commit's exact bytes (this file `ab357462…9862`, `knowledge/03-Modules/MOD-004/MOD-004.md` `17c6b41c…7e7f`) returned OUTCOME APPROVED, and its exact-SHA push CI run `41689089778` completed success. Like the review named in item 2, that review ran in the Claude Code session that commissioned it, so it produced no runner run-evidence artifact and carries no `review_bound_verified` field: its performance, its performer and the reviewer's lack of write tools are asserted here and are not independently verifiable, while the bytes it covered are. This item's original wording also asked for a `Review: <id> APPROVED` header for the approved review of the flip itself. That clause is met in format only: the header still refers to the review of the PROPOSED bytes, and a flip-specific header would itself be a further edit needing a further review, without end. The header is not retroactively a review of the flip. Any further edit to this file needs its own review and its own exact-SHA CI, and none is claimed.
5. [ ] NQ1-NQ3 put to the owner; no answer assumed.
6. [x] Done in `32fc20b`: the MOD-004.md cross-reference to this ADR (source-gaps section and checklist item 8), covered by the review and CI recorded in item 4. MOD-004.md checklist item 8 remains `[ ]` and is not ticked by accepting, publishing or cross-referencing this ADR.
