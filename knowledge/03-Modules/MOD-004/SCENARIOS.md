# MOD-004 — Scenario Catalog (EIP §9 / §9.1)

**Status: DRAFT CATALOG. NOT Scenario Review. NOTHING EXECUTED. NOTHING PASS.** Every scenario below is
**NOT RUN**. This document enumerates executable acceptance contracts as EIP ¶777 requires of Claude before a
module can pass Scenario Review; it is not that review, not an independent QA deepening, not a test result, not
evidence, not a product PASS, not a Ready judgment, not a capability activation and not module acceptance. No
PLT-01 registry row exists, so no `product_pass` value is asserted here. No scenario below authorizes code: code
timing is governed by ADR-0002 D12 and `MOD-004.md` "Ready and code timing", which require Ready **and** an ACTIVE
EIP ¶754 capability manifest. Neither holds.

**What this document changes.** The `MOD-004.md` section "Scenario Catalog and §9.1 category mapping" recorded
category intent only: no enumerated scenario IDs, no per-scenario QA disposition, no test mapping. This file supplies
the enumeration EIP ¶881-882 requires: every row carries an
explicit QA disposition and a ¶881 test-mapping **kind** (see "On test mapping" — no row is bound to a named test
yet). It adds no requirement, waives none, and decides no owner-reserved value.

## Authority for writing this now

EIP ¶777 (pinned extract, below): "Before a module can pass Scenario Review, Claude must write a comprehensive
Scenario Catalog and an independent QA context must deepen it." Writing the catalog is the drafting step the source
assigns to Claude; the independent deepening and Scenario Review are separate later gates and are **not** performed
here. ADR-0002 D12(1) records that stdlib-only documentation and design are legal now. Task selection and
reconciliation of requirement documents against the four pinned baselines are delegated confirmations under
`knowledge/00-Decisions/OWNER-2026-11-05-delegation-activation-and-exception-closure.md` "What is delegated"
items (1) and (2). `knowledge/03-Modules/` is not an ADR-0001-controlled path.

Nothing in that delegation reaches an owner-reserved value. Where a scenario needs one — a hierarchy depth or
cardinality limit, a retention duration, a region, a KMS key, a plan tier, a deletion approver or quorum — the row
names the value **OWNER-RESERVED** and states the question. No such value is invented, defaulted or inferred.

## Sources (hash-verified at authoring time; fail closed on mismatch)

Verified by direct SHA-256 comparison before this file was written:

| Artifact | SHA-256 |
|---|---|
| `Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx` | `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f` |
| `Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx` | `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33` |
| `Gym_OS_Master_Product_Blueprint_v1_English.docx` | `80f4b381df26919b358b3e64e209c67beba2ba9224c0f4df3951d3b179d426ef` |
| extract `mod004-pinned-source-evidence-20261017.md` | `a094e28fb84b26ef591371a64a96d4d741aa6c5d8de381da523cbb46346975ac` |
| extract `mod004-pinned-source-evidence-20261017.manifest.json` | `8842f472673cb661e32e2d9fbc5ac73eadd837e929ad2208880469f9d3ac4e1a` |
| extract `mod004-ready-scenarios-source-supplement-20261017.md` | `85fe2c7eae9fe6e948dadb4c671cabb5b2ab5ac17560f5287d359e8514bc7388` |
| extract `mod004-dependencies-capabilities-source-supplement-20261017.md` | `6e0de7a25c34f3a8982d1e4bb78e24091d9a8008816c0a1b4318adeaa50d29cc` |

Two of the four extract hashes are pinned in `MOD-004.md`: `85fe2c7e…` (the Ready/scenarios supplement) in its
Sources list, and `6e0de7a2…` (the dependencies/capabilities supplement) where it records the capability evidence.
The two `mod004-pinned-source-evidence-20261017` hashes are pinned nowhere in `MOD-004.md`, and the delegation record
cites none of the four. All seven values above were therefore verified here by hashing the artifacts directly, not by
matching a prior citation. The extracts are read-only artifacts held outside the repository in the preserved evidence
tree; they are read, never written. **Finding F3 recorded them as not reachable to a reviewer. As of this writing
all seven artifacts above are readable on the development host and hash-match their pinned values, so a reviewer
with host read access can verify every citation below.** That is a statement of present reachability only: it is
not an owner act, does not close F3's separate "produce or expose the pinned TSD PLT-04 and LIF-01 extracts" half,
and no new pinned extract is produced here.

**Paragraph prefix rule.** Both documents number paragraphs 741-783, so every citation in that range carries an
explicit `EIP` or `TSD` prefix, per `MOD-004.md` Sources. Outside that range, ¶1194-1245 are TSD and ¶1934-1969 and
¶5084-5148 are EIP, as that file records. EIP §8 (paragraphs 746-773) and the head of EIP §9 (775-783) fall inside it and
so carry an explicit `EIP` prefix wherever cited. §9 continues to ¶879 and §9.1 runs ¶880-883; both lie outside the
overlap. `MOD-004.md` states its unprefixed ranges as a closed whitelist that does not include them, so citing
¶857 and ¶879-883 unprefixed as EIP is **this document's own declared extension**, not that convention.

A **second declared extension** is needed, and is named here rather than left implicit: five Source cells continue a
prefix given earlier in the same cell instead of repeating it — `¶1190` (SCN-017), `¶10558` (SCN-080), `¶450`
(SCN-105), `¶4762-4763` and `¶4969` (SCN-107). All five are TSD, and in SCN-105 the nearest explicit prefix is two
citations back rather than immediately adjacent. These five are **not** safe because the numbers are unambiguous:
both baselines carry substantive text at every one of them, and two are plausibly confusable — EIP ¶1190 is a
review-status line and EIP ¶4762 reads "Tier 2". They are safe because the continuation is explicit inside the cell
and each was resolved against the pinned TSD and matches the cell citing it. Prefix continuation is declared
separately because `MOD-004.md`'s whitelist is closed and because the resolver below deliberately refuses to perform
it, reporting all five as unresolved rather than guessing.
Those two extensions and the three `MOD-004.md` ranges together settle every bare citation in this file.

**Every citation whose paragraph number falls in 741-783 carries its own explicit prefix**, with none relying on
continuation, because inside that range the two baselines are unrelated — EIP ¶756 is the Scenario Review gate while
TSD ¶756 is cache key prefixing — so a bare number there would silently re-point if a table cell were reflowed or a
row inserted above it. This is mechanically checked rather than asserted, by
`tools/module_docs/cite_check.py` in this repository: it requires both baseline hashes and fails closed on a
mismatch, resolves every explicitly prefixed citation to its paragraph text, and hard-fails any bare citation whose
cited **span** touches 741-783. It deliberately does **not** guess which baseline a bare citation outside that range
means — inheriting the nearest preceding prefix leaks across list items, headings and table rows, and a confident
wrong resolution is worse than an honest unresolved one — so it reports those (71 of the 258 citations here) and the
declared ranges above settle them. Topic match is not machine-checkable; `--table` prints the citation-to-source
listing a reviewer judges it from, and `--self-check` runs ten assertions over the cases this guard exists for: a
span entering the overlap from below, one leaving it, a bare reversed span, a **prefixed** reversed span, an en-dash
span, an out-of-range paragraph, and a refusal to inherit a preceding prefix. A span whose end precedes its start is
reported as malformed rather than resolved, and each assertion fails if its own fix is reverted. At
these bytes it reports **0 hard failures**.

## Required rule, derived not chosen (EIP ¶1948 module card, then EIP ¶881)

EIP ¶881, as extracted: Required is rule-derived, never a discretionary reduction by Claude. A scenario is Required
if its category is one of HP, NEG, AUTHN, AUTHZ, TEN, SEC, PRIV, CONC, IDEM, NET, PART, OFF, REC, DATA, INT, PERF,
OBS, MIG or DR **when that category is applicable**; or if it traces to a Critical requirement; or if it touches
money, access, identity, consent, restricted data, tenant isolation, physical safety or irreversible consequence.
Reviewers may add Required scenarios and may never downgrade a rule-required one. Non-Required is limited to
cosmetic, redundant-variant and explicitly low-risk ALT/LOC/A11Y variants that do not affect an acceptance contract.
LOC and A11Y are Required for any module owning localization/RTL/accessibility infrastructure, shared
UI/Design-System code, or a mobile production-qualification verdict, regardless of canonical screen ownership.

Consequences for MOD-004. Each is derived from the paragraphs named, not chosen; where a step is inferential it is
labelled **[INFERENCE]**, and every such step here runs in the conservative direction (more Required rows, never
fewer):

- **§9.1 is authoritative, not the module card.** EIP ¶776: "For product-implementation modules MOD-004..MOD-074,
  §9.1 is authoritative and prevails over Appendix G and **module-card matrices**." The card's "Required scenario
  categories" row is such a matrix, so where card and §9.1 conflict, §9.1 governs. Nothing here rests on the card
  overriding §9.1.
- **The card and §9.1 do not conflict, they compound.** EIP ¶1948 reads: `R: HP, VAL, NEG, BND, AUTHN, AUTHZ, TEN,
  SEC, PRIV, CONC, IDEM, NET, PART, OFF, REC, LIFE, DATA, INT, LOC, A11Y, PERF, OBS, MIG, DR | O: ALT`. ¶881 never
  says a category is *not* Required; it permits reviewers to add Required scenarios and forbids downgrading one. A
  card marking that raises a category to `R` therefore adds, and EIP ¶776's prevalence clause is not engaged. That is
  how VAL, BND, LIFE, LOC and A11Y are Required here even though ¶881's own category list omits them. **[INFERENCE]:**
  ¶881 grants the add-only permission to *reviewers*, and reading a module-card matrix as exercising it is this
  document's inference — which EIP ¶776 makes worth naming, since it subordinates module-card matrices to §9.1. For VAL,
  BND and LIFE nothing turns on it: ¶881's Non-Required clause is confined to ALT/LOC/A11Y variants, so those three
  could never have been Non-Required on any reading.
- **LOC and A11Y specifically.** ¶881's final sentence turns on owning localization/RTL or accessibility
  *infrastructure*, shared UI/Design-System code, or a mobile production-qualification verdict — none of which
  MOD-004 owns. Its closing "regardless of canonical screen ownership" makes those three triggers fire irrespective
  of screen ownership; reading it as also *excluding* screen ownership as a trigger would go beyond the text, so the
  clause is simply **not** the basis used here. The ¶1948 marking is, under the compounding rule above. Their disposition is deferred to UI acceptance
  because no contract fields or UI exist; that deferral is recorded, not claimed as satisfied.
- **¶881's own clauses add further Required rows.** Every PLT-01-R01..R07 requirement is **Critical** (EIP ¶5095,
  ¶5103, ¶5111, ¶5119, ¶5127, ¶5135, ¶5143), and tenant isolation and access are explicit ¶881 triggers
  (TSD ¶10557). The Critical-trace clause is sufficient on its own and forces Required onto any row tracing to
  R01-R07 whatever its category — including two ALT rows (108, 109).
- **No row below is Non-Required.** ¶881 confines Non-Required to cosmetic, redundant-variant and explicitly
  low-risk ALT/LOC/A11Y variants **"that do not affect an acceptance contract"**; the card marks LOC and A11Y `R`;
  the Critical-trace clause reaches 108 and 109; and the remaining ALT row is still an acceptance contract on this
  document's own definition, so the second condition fails for it too. All 110 rows are Required.
- **OFF and LIFE are not waived.** The card marks both `R`. EIP ¶766, which bars N/A unless the module card itself
  states it, is the **Load/Security/Resilience gate** row rather than a scenario-category rule, so reading it across
  to categories is an **[INFERENCE]** of this document, in the refusing-to-waive direction only; `MOD-004.md`
  "Applicability and N/A" states the category rule directly. What is unresolved is which concrete surface each
  applies to, MOD-004 having no client, offline, application or session surface in the sources read. Each keeps one
  row recording that unresolved applicability.

**Minimum count (EIP ¶882).** The bands are: standard product ≥12; UI/mobile-heavy ≥18; integration/data ≥20;
concurrency/security-critical ≥24; financial/access/life-safety ≥30. MOD-004 is concurrency/security-critical
(Foundation/Control risk class, EIP ¶1955-1956; RLS and pooling concurrency, TSD ¶748) **and** access-bearing (roles,
privileged console, tenant isolation). ¶882 states the bands and sets no rule for an overlap, so taking the stricter
of the two is an **[INFERENCE]** of this document, in the conservative direction only, and the floor it yields is
**≥30**. Nothing turns on it: 110 Required clears ≥24 and ≥30 alike. ¶882 adds that the Required count must be at least the number of Critical
requirements/slices mapped to the module: 7 requirements (R01-R07) and 7 proposed slices (S1-S7). ¶882 sets no
maximum. This catalog enumerates **110** scenarios, **all 110 Required**. The count satisfies the floor; it
is not evidence and no row is executed.

**Stable IDs (EIP ¶883).** `SCN-MOD-004-<NNN>`, immutable once evidence is linked; superseded artifacts retain
lineage. No ID below has evidence linked, so none is yet frozen by that rule.

**Mandatory manual execution (EIP ¶857, §12).** Every Required scenario must be manually executed by Claude at
least once before module approval; TestSprite and automated coverage may additionally execute the same scenario and
never replace the manual run. The `Manual` obligation is therefore implicit for all 110 rows and is not
repeated per row.

## Column meanings

- **Req** — `R` rule-Required. Every row is `R`. Where the Source column names a Critical requirement or a ¶881
  trigger, that is the basis; otherwise the basis is the EIP ¶1948 card marking for the row's category, and the
  section heading says so.
- **Scenario** — synthetic stimulus → required observation. An acceptance contract, not an example.
- **QA disposition** (¶881's four permitted kinds) — `AUTO` deterministic automated test; `TS` TestSprite;
  `MANX` manual exploratory; `NONAUT` justified non-automatable evidence. No row is left without one.
- **On "test mapping".** ¶881 requires "an explicit QA disposition and executable test mapping (automated,
  TestSprite, manual exploratory, or justified non-automatable evidence)". No executable test exists for any row
  yet, so the mapping here is the disposition **kind** drawn from ¶881's own four-item vocabulary, not a reference to
  a test artifact or `TR-` ID. That is this document's reading of the clause; binding each row to a named test is
  outstanding work, not something this file claims to have done.
- **Blocked by** — what prevents execution today. `—` means only the absent S1 code and environment block it; a named
  entry is an additional, independent blocker. Gap IDs are ADR-0005's register. **One exception:** the published S0
  slice `backend/app/tenancy_s0.py` and its tests already implement `ProvisionTenant` envelope shape validation — a
  field allowlist and an `expected_version` bound — so SCN-014, SCN-016, SCN-031 and the envelope half of SCN-001 have
  existing published code to build on. That code is shape validation only: no I/O, no authorization, no tenant
  isolation, and its original product review stands CHANGES_REQUESTED, so no row below is credited as executed.

Every row's status is **NOT RUN**. There is no status column because no other value is possible yet.

## HP — Happy path (EIP ¶783: does the complete intended journey succeed?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-001 | R | `ProvisionTenant` with a well-formed synthetic envelope → one `platform_scope` registry row; returns `(tenant_id, replayed=false)` | TSD ¶1237; ADR-0002 D6.3; R01 EIP ¶5098 | AUTO | — |
| SCN-MOD-004-002 | R | Activate a provisioned tenant → lifecycle state becomes active; transition recorded | R01 EIP ¶5098; TSD ¶1228 | AUTO | — |
| SCN-MOD-004-003 | R | Suspend an active tenant → suspended; no tenant data destroyed | R01 EIP ¶5098 | AUTO | — |
| SCN-MOD-004-004 | R | Archive a suspended tenant → archived; archive is not deletion | R01 EIP ¶5098; TSD ¶1222 | AUTO | A1 (no delete command, ESCALATE) |
| SCN-MOD-004-005 | R | Every accepted lifecycle transition appends exactly one history entry | R07 EIP ¶5146; TSD ¶1228 | AUTO | — |
| SCN-MOD-004-006 | R | Create an organization node under an active tenant → node bound to that tenant only | R02 EIP ¶5106; TSD ¶1204 | AUTO | Hierarchy cardinalities OWNER-RESERVED |
| SCN-MOD-004-007 | R | Create a brand under a tenant → brand bound to tenant; `brand.created` published | R02 EIP ¶5106; TSD ¶1204, ¶1206 | AUTO | A5 (PROPOSE; no command designed) |
| SCN-MOD-004-008 | R | Open a location under a brand → location bound to tenant and parent | R02 EIP ¶5106; TSD ¶1204, ¶1206 | AUTO | A6 (PROPOSE; no command designed) |
| SCN-MOD-004-009 | R | Maintain a legal entity, department and cost center under one tenant | R02 EIP ¶5106; TSD ¶1204 | AUTO | A7, A8, A9 (PROPOSE) |
| SCN-MOD-004-010 | R | `resolve_placement` (harness-only) for a tenant with no region → `UNASSIGNED`, no region invented | ADR-0002 D6.3; TSD ¶776 | AUTO | — |
| SCN-MOD-004-011 | R | Each successful command writes its outbox row in the same transaction as its state change | TSD ¶1216, ¶1237 (event names ¶1206) | AUTO | MOD-010 absent |

## VAL — Validation (EIP ¶789: what invalid field/state is rejected and how?) — Required by the EIP ¶1948 card

Rows 012, 015 also trace to a Critical requirement independently; 013, 014, 016 and 017 rest on the card marking.

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-012 | R | Malformed tenant UUID → rejected; no partial write; raw input not echoed in the error | R01 Critical (EIP ¶5095); TSD ¶745 | AUTO | — |
| SCN-MOD-004-013 | R | Missing tenant context → fails closed; never falls back to an unrestricted query | TSD ¶745 | AUTO | — |
| SCN-MOD-004-014 | R | Invalid `expected_version` (negative, non-integer, present-null, bool, float, huge int) → rejected without resource blow-up | TSD ¶1237; ADR-0002 D6.3 | AUTO | TSD ¶1237 / D6.3 version discrepancy OPEN |
| SCN-MOD-004-015 | R | Hierarchy rule violation (cycle, self-parent, cross-tenant parent) → rejected | R02 Critical (EIP ¶5103) | AUTO | Hierarchy rules OWNER-RESERVED |
| SCN-MOD-004-016 | R | Unknown or extra envelope field → rejected, not silently ignored | `contracts/engineering/mod004-s0-scenario-qa.md` (S0 envelope contract); implemented by the S0 field allowlist | AUTO | — |
| SCN-MOD-004-017 | R | Every rejection carries the request `correlation_id` | TSD ¶737, ¶1190 establish that the context *contains* it; that a **rejection response** carries it is an authored contract, not a sourced requirement | MANX | No API surface designed |

## NEG — Negative / must never succeed (EIP ¶792)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-018 | R | Cross-tenant `SELECT` as the actual runtime role → zero rows, not an error that leaks existence | TSD ¶748; EIP ¶1950 | AUTO | — |
| SCN-MOD-004-019 | R | `INSERT` carrying a foreign `tenant_id` → rejected by policy, not by application code alone | TSD ¶744, TSD ¶745 | AUTO | — |
| SCN-MOD-004-020 | R | `ALTER TABLE … DISABLE ROW LEVEL SECURITY` as the runtime role → denied | TSD ¶743, TSD ¶744 | AUTO | — |
| SCN-MOD-004-021 | R | `SET ROLE` from the runtime role to the table-owner role → denied | TSD ¶743; ADR-0002 D5 | AUTO | — |
| SCN-MOD-004-022 | R | Query with no application tenant filter as the runtime role → only own-tenant rows | TSD ¶748 | AUTO | — |
| SCN-MOD-004-023 | R | Session-level (not `LOCAL`) `SET` of the tenant GUC on a pooled connection → does not yield unrestricted access; caught by lint, the primitive and leak-after-reuse tests | TSD ¶746; ADR-0002 D4, D9 | AUTO | — |
| SCN-MOD-004-024 | R | No `TRUNCATE` or `REFERENCES` grant to a runtime role exists (TRUNCATE ignores RLS) | ADR-0002 D5, D6.2 | AUTO | — |
| SCN-MOD-004-025 | R | No tenant table is granted to `PUBLIC`; catalog check proves it | TSD ¶744 | AUTO | — |

## BND — Boundary (EIP ¶795: what happens at min/max/empty/expiry boundaries?)

Required through the EIP ¶1948 card marking, as for VAL and LIFE. Three of the six rows (027, 028, 029) also trace
to a Critical requirement and are Required on that ground independently; the other three rest on the card alone.

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-026 | R | Query with absent tenant context → zero rows or a closed-fail error, never an unrestricted result | TSD ¶745 | AUTO | — |
| SCN-MOD-004-027 | R | Nil UUID and maximum UUID as `tenant_id` → handled deterministically, no policy bypass | R01 Critical | AUTO | — |
| SCN-MOD-004-028 | R | Hierarchy at the decided maximum depth, and at depth+1 → accepted and rejected respectively | R02 Critical | AUTO | Depth limit **OWNER-RESERVED** (unresolved item 3) |
| SCN-MOD-004-029 | R | Hierarchy at the decided maximum node cardinality, and at cardinality+1 | R02 Critical | AUTO | Cardinality **OWNER-RESERVED** (unresolved item 3) |
| SCN-MOD-004-030 | R | Large tenant count (registry at scale) → policy evaluation still isolates and still meets its SLO | TSD ¶1244; EIP ¶1952 | AUTO | Load environment undecided |
| SCN-MOD-004-031 | R | `expected_version` at its documented upper bound and bound+1 → accepted and rejected; huge ints rejected without resource blow-up | `backend/app/tenancy_s0.py` `EXPECTED_VERSION_MAX = 2**31 - 1`; `contracts/engineering/mod004-s0-scenario-qa.md` S0-07; ADR-0002 D6.3 (version semantics) | AUTO | **Divergence to resolve at S1:** the published S0 constant is 2^31-1; ADR-0002 D2.3 proposes `version bigint NOT NULL` (`[PROPOSAL]`, not `[SRC]`); and the pinned TSD ¶1190 gives `AggregateMetadata { … version: int … }`. S0-07 records the S0 envelope behaviour as PASS for that envelope only — and that disposition sits in a packet whose own header calls itself a DRAFT evidence candidate pending an independent review that has not occurred, and records all its rows NOT RUN |

## AUTHN — Authentication (EIP ¶798: missing/expired/revoked identity?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-032 | R | Command with no actor identity → fails closed; no state change, no outbox row | TSD ¶1237 | AUTO | MOD-007 identity absent |
| SCN-MOD-004-033 | R | Catalog check: `veyro_app` and worker roles are LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS and own no tenant table | TSD ¶743 | AUTO | — |
| SCN-MOD-004-034 | R | Expired or revoked actor credential → rejected, not degraded to anonymous | TSD ¶1237 | AUTO | MOD-007 absent; circular dependency recorded in `MOD-004.md` |
| SCN-MOD-004-035 | R | D6.7 transport and caller authentication for the `placement.resolve.v1` contract (`resolve_placement`) → only the designed caller path reaches it | ADR-0002 D6.7 | AUTO | D6.7 is `[PROPOSAL; transport OPEN]` and defers caller authentication expressly |

## AUTHZ — Authorization (EIP ¶801: can a lower role/scope escalate?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-036 | R | Runtime role cannot obtain `veyro_cp_platform` membership — direct, inherited or via `SET` | ADR-0002 D5; TSD ¶743 | AUTO | — |
| SCN-MOD-004-037 | R | Steady-state membership of `veyro_cp_platform` is exactly zero; catalog proves it | ADR-0002 D5, D6.2 | AUTO | — |
| SCN-MOD-004-038 | R | A NOCREATEROLE migrator cannot grant itself platform membership | ADR-0002 D6.2; TSD ¶743 | AUTO | — |
| SCN-MOD-004-039 | R | `pg_db_role_setting` defaults cannot inject or pre-set tenant context for any role | ADR-0002 D5 | AUTO | — |
| SCN-MOD-004-040 | R | Per-command permission enforced for every lifecycle and hierarchy command | TSD ¶1237 | AUTO | MOD-008 absent; sequencing unresolved |
| SCN-MOD-004-041 | R | Destructive lifecycle action without approvals, retention check and audit record → refused | TSD ¶10557, ¶1231 | AUTO | MOD-008 audit absent; approvers/quorum **OWNER-RESERVED** |

## TEN — Cross-tenant isolation (EIP ¶804: can another tenant/location influence or observe state?)

The seven TSD ¶749-772 layers, each with its own release gate. All seven are currently unevidenced.

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-042 | R | **PostgreSQL layer** — automated cross-tenant fuzz/integration corpus finds zero cross-tenant row | TSD ¶752-754 | AUTO | — |
| SCN-MOD-004-043 | R | Composite-FK cross-parent attempt (child under a parent in another tenant) → rejected | ADR-0002 D2.3 (composite FK `(tenant_id, parent_id)`) | AUTO | D2.3 is `[PROPOSAL]`, not `[SRC]` |
| SCN-MOD-004-044 | R | Pool connection reused across tenants → leak-after-reuse test proves no residual context | TSD ¶746, TSD ¶748; ADR-0002 D9 | AUTO | — |
| SCN-MOD-004-045 | R | **Cache layer** — same logical key in two tenants cannot collide; no user-composed raw key | TSD ¶755-757 | AUTO | R03 cache part OPEN; no cache exists |
| SCN-MOD-004-046 | R | **Search layer** — zero cross-tenant result corpus; `tenant_id` mandatory, pre-filter and post-filter authorization | TSD ¶758-760 | AUTO | R03 search part OPEN; no index exists |
| SCN-MOD-004-047 | R | **Object storage layer** — attempted path manipulation out of `tenant/<tenant_id>/…` → denied | TSD ¶761-763 | AUTO | R03 storage part OPEN; per-class KMS **OWNER-RESERVED** |
| SCN-MOD-004-048 | R | **Object storage layer** — signed URL after expiry → denied | TSD ¶761-763 | AUTO | As above |
| SCN-MOD-004-049 | R | **Events/jobs layer** — message without valid tenant context → quarantined, not processed | TSD ¶764-766 | AUTO | MOD-010 absent |
| SCN-MOD-004-050 | R | **Telemetry layer** — `tenant_id` emitted as a controlled attribute, never unbounded user text; no restricted data in logs or traces | TSD ¶767-769 | AUTO | Observability platform absent |
| SCN-MOD-004-051 | R | **AI layer** — adversarial cross-tenant prompt corpus retrieves nothing from another tenant; tool policy applied before execution | TSD ¶770-772 | AUTO | R03 AI part OPEN; no retrieval surface |

## SEC — Security / abuse (EIP ¶807: how does abuse/replay/injection/rate-limit behave?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-052 | R | Catalog assertion: every tenant-owned table has `tenant_id UUID NOT NULL`, ENABLE RLS and FORCE RLS | TSD ¶744 | AUTO | — |
| SCN-MOD-004-053 | R | Catalog assertion: no runtime role holds BYPASSRLS or SUPERUSER at any time | TSD ¶743 | AUTO | — |
| SCN-MOD-004-054 | R | Every view over a tenant table is `security_invoker = true` **and** on the explicit reviewed allowlist; any other such view is banned by default | ADR-0002 D5 | AUTO | — |
| SCN-MOD-004-055 | R | Every `SECURITY DEFINER` function is on the reviewed allowlist; an unreviewed one fails the gate | TSD ¶747 | AUTO | — |
| SCN-MOD-004-056 | R | Replay of an already-applied command envelope → no second effect, no second outbox row | TSD ¶1237; ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-057 | R | Injection attempt through the tenant GUC value (quoting, cast abuse) → policy still fails closed | TSD ¶745 | AUTO | — |
| SCN-MOD-004-058 | R | Secrets and restricted values are redacted in every error, log and trace path | TSD ¶769 | AUTO | — |

## PRIV — Privacy / consent (EIP ¶810: are consent, purpose and restricted fields enforced?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-059 | R | Field and resource classification is enforced at field/resource level; tenant context and authorization are mandatory | TSD ¶1243 | AUTO | Classification enforcement is MOD-009 |
| SCN-MOD-004-060 | R | Restricted data never appears in logs, traces or diagnostics | TSD ¶769 | AUTO | — |
| SCN-MOD-004-061 | R | Break-glass actor evidence recorded for every delegated support action | TSD ¶1243 | NONAUT | No support/break-glass path exists in S1 by design; MOD-008 absent |

## CONC — Concurrency / race (EIP ¶813: what if actors act simultaneously?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-062 | R | Optimistic version conflict on the same aggregate → one writer wins, loser rejected with a version error | TSD ¶1239 | AUTO | — |
| SCN-MOD-004-063 | R | Two concurrent `ProvisionTenant` calls with the same idempotency key → exactly one row; one result carries `replayed=true` | ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-064 | R | Concurrent same-aggregate lifecycle commands serialize; no interleaved illegal transition | TSD ¶1228, TSD ¶1239 | AUTO | Depends on the same undefined legal-transition graph as SCN-080 |
| SCN-MOD-004-065 | R | 1,000 concurrent mixed-tenant reads → isolation holds for every one | EIP ¶1952; TSD ¶1239 | AUTO | Load environment undecided |
| SCN-MOD-004-066 | R | Noisy-neighbour load from one tenant does not breach another tenant's SLO | EIP ¶1952 | AUTO | Load environment undecided |

## IDEM — Idempotency / retry (EIP ¶816: what if the client/provider repeats after timeout?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-067 | R | Repeat of `ProvisionTenant` with the same key and identical payload → `replayed=true`, no duplicate row | ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-068 | R | Same idempotency key with a mismatched payload → rejected as a payload mismatch, original unchanged | ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-069 | R | Outbox consumer processes the same event twice → one effect | TSD ¶1216, ¶1237 | AUTO | MOD-010 absent |

## NET — Network / timeout (EIP ¶819: what if the network fails before/after server commit?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-070 | R | Timeout before commit → no registry row, no outbox row; retry succeeds cleanly | TSD ¶1216, ¶1242 | AUTO | — |
| SCN-MOD-004-071 | R | Disconnect after commit with unknown outcome → retry returns `replayed=true`, no duplicate effect | TSD ¶1216, ¶1242; ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-072 | R | Lost acknowledgement → no duplicate outbox row and no lost outbox row | TSD ¶1216, ¶1237, ¶1242 | AUTO | MOD-010 absent |

## PART — Partial failure (EIP ¶822: what if one dependency succeeds and another fails?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-073 | R | Outbox write fails after the state change → whole transaction rolls back; neither effect survives | TSD ¶1242; ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-074 | R | `provision_tenant` rollback behaviour under an injected mid-function failure → no partial tenant | ADR-0002 D6.3 | AUTO | — |
| SCN-MOD-004-075 | R | Relocation partially applied, then retried → reconciliation reaches one consistent placement | TSD ¶777-778 | AUTO | S5 absent; W1 (ESCALATE, NQ3); B3 |

## OFF — Offline / degraded (EIP ¶825: what is allowed offline and what must fail closed?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-076 | R | Resolve OFF applicability for MOD-004 against a cited source rule, then either enumerate its scenarios or record a card-stated N/A | EIP ¶825; EIP ¶766 (N/A only where the module card states it) | NONAUT | **Applicability undetermined.** No client or offline surface found in the sources read. Not waived |

## REC — Recovery / reconciliation (EIP ¶828: how is authoritative state reconciled/rebuilt?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-077 | R | RB-PLT-01 stuck-command repair completes without rewriting history | TSD ¶1245 | NONAUT | Runbook not written; reconciliation owner undesigned |
| SCN-MOD-004-078 | R | Authoritative state rebuilt from history and outbox → reconciliation counts match | TSD ¶1245 (reconciliation), TSD ¶778 (control totals) | AUTO | Reconciliation owner undesigned |

## LIFE — App / session lifecycle (EIP ¶831: backgrounded, killed or resumed?) — Required by the EIP ¶1948 card

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-079 | R | Resolve LIFE applicability against a cited source rule. Tenant lifecycle is **not** LIFE and is covered by R01/R07 under DATA, AUTHZ, PART and REC | EIP ¶831; EIP ¶766 | NONAUT | **Applicability unresolved.** No application or session surface exists in MOD-004. Not waived |

## DATA — Data integrity (EIP ¶834: which invariant proves stored state is correct?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-080 | R | Every lifecycle state transition is covered by an invariant/property test, and an illegal transition is impossible rather than merely unused | TSD ¶1245 ("invariant/property tests for each state transition"); TSD ¶1228 (history, deletion gate). **INV-PLT-01 is not the basis:** TSD ¶10557 states a cross-tenant prohibition and destructive-action controls and contains no transition invariant; ¶10558 is its evidence anchor | AUTO | **The legal-transition graph is undefined in the pinned sources.** TSD ¶1222 names five transitions (provision, activate, suspend, archive, delete) and ADR-0005 records that none of ¶1222, ¶1237 or ¶1206 names a resume or unsuspend; defining the graph is S1 design work |
| SCN-MOD-004-081 | R | Hard deletion is blocked until legal, billing and retention gates pass | R07 EIP ¶5146; TSD ¶1231 | AUTO | A1 (ESCALATE); retention durations and gate criteria **OWNER-RESERVED** |
| SCN-MOD-004-082 | R | Lifecycle history is append-only; no update or delete path exists for a history row | R07 EIP ¶5146; TSD ¶1228 | AUTO | — |
| SCN-MOD-004-083 | R | No orphan hierarchy node can exist after any accepted command or any rollback | R02 EIP ¶5106 | AUTO | — |
| SCN-MOD-004-084 | R | Tenant-scoped uniqueness holds via composite unique keys; the same natural key in two tenants is legal | TSD ¶753 | AUTO | — |
| SCN-MOD-004-085 | R | Relocation reconciliation row counts match before and after, per `relocation_epoch` | TSD ¶777-778 | AUTO | S5 absent; B3, W1 |

## INT — Integration / provider (EIP ¶837: slow, wrong, duplicated or unavailable?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-086 | R | KMS slow or unavailable at key assignment → fails closed, no tenant left with an unassigned-but-claimed key | R05 EIP ¶5130; TSD ¶776 | AUTO | A4 (ESCALATE); KMS keys **OWNER-RESERVED**, DC-16 |
| SCN-MOD-004-087 | R | Bus unavailable after commit → the command still commits atomically with its outbox row; publication retries idempotently; no effect is lost and none is published twice | TSD ¶1216, ¶1242 | AUTO | MOD-010 absent |
| SCN-MOD-004-088 | R | Billing or retention gate provider unavailable at a destructive action → refuse, never assume pass | R07 EIP ¶5146; TSD ¶1231 | AUTO | MOD-015 absent |
| SCN-MOD-004-089 | R | Contract tests for every published API and event hold against the recorded contract | TSD ¶1245 (event list ¶1241) | AUTO | APIs and events not designed; B1-B4 (ESCALATE), C1 (PROPOSE) |

## LOC — Localization / RTL (EIP ¶840) — Required by the EIP ¶1948 module card

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-090 | R | Regional settings and locale/currency defaults inherit correctly down the hierarchy | R04 EIP ¶5122 | AUTO | Default contents **OWNER-RESERVED**; A3, A10 (ESCALATE) |
| SCN-MOD-004-091 | R | Arabic/RTL, mixed Arabic-Latin text, currency and date render correctly on the owned screen IDs | EIP ¶840, ¶1948 | TS | No UI or contract fields; disposition deferred to UI acceptance, not waived |

## A11Y — Accessibility (EIP ¶843) — Required by the EIP ¶1948 module card

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-092 | R | Keyboard-only and assistive-technology completion of each owned screen's primary task (CON-04, ADM-SET-01, ADM-SET-02, ADM-SET-06 V1) | EIP ¶843, ¶1948 | TS | No UI; D14 mapping unreviewed; ADM-SET-06 V2 boundary OPEN |
| SCN-MOD-004-093 | R | Dynamic text sizing does not truncate or hide any consequence-bearing control on an owned screen | EIP ¶843 | TS | As above |

## PERF — Performance / load (EIP ¶846: does it meet SLO under expected and peak load?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-094 | R | RLS overhead measured against a no-RLS baseline and recorded | EIP ¶1952 | AUTO | Environment absent; nothing measured |
| SCN-MOD-004-095 | R | Policy and tenant resolution p95 under 100 ms at expected load | TSD ¶1244 | AUTO | Environment absent |
| SCN-MOD-004-096 | R | Tier-1 control-path availability objective 99.95%+ demonstrated for the measured window | TSD ¶1244 | NONAUT | Environment absent |

## OBS — Observability / audit (EIP ¶849: can operators prove what happened without leaking data?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-097 | R | The `correlation_id` set at command entry is propagated into cache namespace, event envelope, logs/traces, object paths, search filters, jobs and AI retrieval | TSD ¶739 (propagation), TSD ¶737, TSD ¶746, TSD ¶1190 | AUTO | — |
| SCN-MOD-004-098 | R | `tenant_id` is a controlled telemetry attribute with bounded cardinality | TSD ¶768 | AUTO | — |
| SCN-MOD-004-099 | R | SLIs for the PLT-01 commands are emitted and queryable | TSD ¶1244 | AUTO | Observability platform absent |
| SCN-MOD-004-100 | R | Operator can reconstruct what happened from history plus telemetry **without** an interim access log in S1 | ADR-0002 D6.4; `MOD-004.md` OWNER-Q1 default | NONAUT | **OWNER-Q1 PENDING; default is no interim log in S1.** Full audit proof is MOD-008 and is not claimed here |

## MIG — Migration / compatibility (EIP ¶852: can old/current versions/data be moved safely?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-101 | R | Migration lint rejects a new tenant table lacking `tenant_id` | TSD ¶747 | AUTO | BLK-SKL-MIGRATION-LINT OPEN; no migrations exist |
| SCN-MOD-004-102 | R | Migration lint rejects a new tenant table lacking FORCE RLS, a policy, or the expected tenant-leading indexes | TSD ¶747 | AUTO | As above |
| SCN-MOD-004-103 | R | Migration lint rejects a new tenant table lacking runtime-role negative tests, and rejects an unreviewed `SECURITY DEFINER` function | TSD ¶747 | AUTO | As above |
| SCN-MOD-004-104 | R | D5 mutation corpus: one deliberately failing migration per lint rule, each detected | ADR-0002 D5; TSD ¶747 | AUTO | Corpus authorable as text now; execution needs the lint and a database |

## DR — Disaster recovery / continuity (EIP ¶855: does recovery preserve consequence-bearing truth?)

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-105 | R | Tier-1 continuity: service restored within the stated objective with no consequence-bearing loss | TSD ¶1211-1212 (tier designation), ¶1244 (99.95%+ objective), ¶450 (Tier-1 replica and warm standby) | NONAUT | Backup/restore environment absent |
| SCN-MOD-004-106 | R | Relocation rollback then reconciliation preserves one authoritative placement | TSD ¶777-779 | AUTO | S5 absent; W1, B3 |
| SCN-MOD-004-107 | R | Restore to the Tier-1 targets — RPO ≤5 min and RTO ≤60 min on region failure — proven by a tested promotion runbook, with measured RPO/RTO and control totals recorded | TSD ¶450 (ADR-022, Accepted), ¶4762-4763, ¶4969 | NONAUT | Backup/restore environment absent; the targets hold only while replica health and a warm-standby drill prove them (TSD ¶4763) |

## ALT — Alternate valid paths (EIP ¶786) — the one optional category

ALT is the only category EIP ¶1948 marks `O`, yet all three rows here are **Required**, so this catalog has no
Non-Required row at all. 108 and 109 trace to a Critical requirement (R01, R02), and ¶881's Critical-trace clause is
a free-standing sufficient condition that no category marking overrides. 110 traces to none, so only ¶881's
Non-Required clause could reach it — and that clause is confined to variants "that do not affect an acceptance
contract", while this document defines every row as an acceptance contract. Absence of a Critical trace is necessary
for `N`, not sufficient, and the second condition fails. Marking it Required is the direction ¶881 allows: adding is
always permitted, downgrading never is.

| ID | Req | Scenario | Source | QA | Blocked by |
|---|---|---|---|---|---|
| SCN-MOD-004-108 | R | Provision then activate as two calls reaches the same state as any designed single-call path | R01 EIP ¶5098 | AUTO | No single-call path is designed |
| SCN-MOD-004-109 | R | Hierarchy built top-down and bottom-up reach the same valid shape | R02 EIP ¶5106 | AUTO | Cardinalities **OWNER-RESERVED** |
| SCN-MOD-004-110 | R | Equivalent read via list projection and via detail projection agree | TSD ¶1238 | AUTO | C1 (PROPOSE); projections undesigned |

## Requirement traceability (EIP ¶882 floor: Required ≥ number of Critical requirements/slices)

**This is not the complete mapping EIP ¶756 requires for Scenario Review.** It maps 39 of the 110 rows to a PLT-01
requirement; the remaining 71 — among them every RLS negative (018-025), six of the seven SEC rows (all but 056), and
the migration-lint rows (101-104) — trace to a TSD or ADR-0002 control rather than to a named requirement. The slice
table below leaves 14 rows in no slice and places three in two. EIP ¶756 requires that "all Required requirements/
behaviors mapped" before Scenario Review passes; that mapping is outstanding and is part of why Scenario Review is
OPEN.

| Critical requirement | Text (EIP Appendix B) | Scenarios |
|---|---|---|
| PLT-01-R01 ¶5098 | Provision, activate, suspend, archive and delete tenants through a controlled lifecycle | 001-005, 012, 027, 056, 064, 080, 108 |
| PLT-01-R02 ¶5106 | Model organization, legal entity, brand, region, location, department and cost-center hierarchies | 006-009, 015, 028, 029, 083, 109 |
| PLT-01-R03 ¶5114 | Enforce tenant-aware identifiers, storage paths, search indexes, events, caches, logs and background jobs | 042-051, 098 |
| PLT-01-R04 ¶5122 | Support tenant templates, cloning, defaults, regional settings and configuration inheritance | 090 |
| PLT-01-R05 ¶5130 | Provide data residency, deployment-region and encryption-key assignment policies | 010, 047, 048, 086, 106 |
| PLT-01-R06 ¶5138 | Allow multi-brand ownership with separate branding, catalogs, pricing, domains, applications and policies | 007 |
| PLT-01-R07 ¶5146 | Maintain tenant lifecycle history and prevent hard deletion before legal, billing and retention gates pass | 004, 005, 041, 081, 082, 088 |

R04 and R06 each trace to a single scenario. That is the honest state, not an omission to be padded: R04's template, clone and configuration content is A2, A3 and A10 (all ESCALATE), and R06's multi-brand catalog, pricing, domain and policy separation depends on A5 (PROPOSE) and on the ADM-SET-06 V2 boundary, which is owner-reserved. The LOC and A11Y rows for the owned screens were previously credited to R06 and are not: they test localization and accessibility, not multi-brand ownership. No scenario is invented to thicken either row.

| Proposed slice | Scenarios |
|---|---|
| S1 PostgreSQL isolation core | 001, 010, 012-014, 018-027, 031-039, 042-044, 052-058, 062-064, 067-068, 070-071, 073-074, 080, 082, 084, 097-098, 100-104 |
| S2 lifecycle, history, deletion guard | 002-005, 041, 064, 081-082, 088 |
| S3 hierarchy and multi-brand | 006-009, 015, 028-029, 083, 109 |
| S4 templates and inheritance | 090, 110 |
| S5 placement, region, key, relocation epoch | 010, 075, 085-086, 106 |
| S6 tenant-scoped cache, search, storage, event, log, AI primitives | 045-051 |
| S7 APIs, screen contracts, TestSprite, load, RB-PLT-01, DR | 017, 065-066, 077-078, 089, 091-096, 105, 107 |

## Coverage summary

110 scenarios, **all 110 Required**; no row qualifies as Non-Required under ¶881's closed list. All 24 categories the
¶1948 card marks `R` are represented. Every row carries a QA disposition and a ¶881 test-mapping **kind**; binding
rows to named tests is outstanding, as "On test mapping" records. The Required count clears the ≥30 floor, the
7-requirement floor and the 7-slice floor.

**0 executed. 0 PASS. 0 evidence.** Execution needs, at minimum: Ready, an ACTIVE EIP ¶754 capability manifest, the
S1 code that does not exist (the published S0 envelope-validation slice covers the shape half of four rows and
nothing else), and a database environment that cannot be provisioned without the owner's pre-pull
security approval. Sixty-four of the 110 rows carry a named additional blocker in their own row; the remaining 46 are blocked
only by that universal absence.

## What this catalog does not do

- Not Scenario Review, and not the independent QA deepening EIP ¶777 requires after this drafting step.
- Not an execution result, a PASS, a product PASS, a Gatekeeper verdict, a TestSprite result or a security PASS.
- Not a Ready judgment and not a capability activation; the manifest stays PROVISIONAL with `gate_eligible: false`.
- Not code authorization. No scenario here permits product code outside the published S0 slice.
- Not an answer to OWNER-Q1, OWNER-Q2, ADR-0002 D15.10 Q1-Q8, or any unresolved owner-reserved choice; each such
  value is named OWNER-RESERVED where a scenario needs it.
- Not a change to any ADR-0005 disposition: ESCALATE rows stay escalated and no PROPOSE row is designed here.
- Not a waiver of OFF, LIFE, LOC or A11Y. Each is recorded OPEN or deferred with its cited rule.
- Not a closure of finding F3. Present reachability of the seven hash-verified source artifacts is recorded as a
  fact; producing or exposing the pinned TSD PLT-04 and LIF-01 extracts remains outstanding.
