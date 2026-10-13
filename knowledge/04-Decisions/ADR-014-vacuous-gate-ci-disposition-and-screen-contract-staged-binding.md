---
doc: ADR-014
status: Accepted (2026-10-13) — bounded engineering interpretation; no owner approval required (see "Conformance and owner-reserved determination")
date: 2026-10-13
decided_by: veyro-lead (fresh-context Opus architecture session, runtime model id claude-opus-5-5; bounded operation M1-C-03 / R2a, operation 6dccca8d-260b-4e5c-92f7-f4da9a24a02c; no code change, no review, no scenario disposition)
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 1 RLS lint, gate 4 permission lint, gate 5 screen contract lint, and the integrated C05 pipeline)
requested_by: knowledge/03-Modules/MOD-001/evidence/implementation/M1-C-03-R1-EXIT-SEMANTICS-DETERMINATION-2026-10-13.md ("ADR required" section, lines 186-214; commit c59a2ff)
relates_to: ADR-009 (INCONCLUSIVE definition, D2), ADR-010 (D3.6 empty manifest skeleton; ERROR-not-empty rule). Neither is amended.
---

# ADR-014: Vacuous-gate CI disposition and screen-contract staged binding

Status: Accepted

## Numbering note

The R1 determination drafted this decision as "ADR-011". That number was
already taken by `ADR-011-gate2-module-deps-input-contract.md` (as were
ADR-012 and ADR-013). This ADR is the recorded form of that draft under the
next free number; the draft label carries no separate authority.

## Context

MOD-001 must ship real CI-blocking architecture gates while, under WIP=1,
owning no tenant tables, no API operations and no canonical screens. Later
modules populate those inputs.

- TSD §24.1 gates are quantified over what exists: RLS lint "every tenant
  table…" (`knowledge/00-System/TSD_MIRROR.md:11599-11601`); permission lint
  "API commands/queries declare action/resource/scope; unregistered
  permission names fail build" (`TSD_MIRROR.md:11614-11615`); screen
  contract lint maps every V1 Screen ID to a BFF/read model or typed command
  manifest row "before feature release" (`TSD_MIRROR.md:11617-11618`).
- TSD Appendix F: `contracts/ui/screen-contracts.yaml` is materialized from
  the canonical design-registry export and validated against OpenAPI,
  AsyncAPI and the frontend route registry (`TSD_MIRROR.md:17338-17342`);
  mandatory fields (`TSD_MIRROR.md:17344-17347`); registry V1 count ==
  manifest rows == frontend route-registry V1 rows, mismatch is P1 and
  blocks feature freeze (`TSD_MIRROR.md:17349-17351`).
- EIP MOD-001 card: implements all six §24.1 gates, imports the canonical
  screen registry, generates `screen-contracts.yaml`, and proves with
  deliberate fixtures the controls cannot be bypassed
  (`knowledge/00-System/EIP_MIRROR.md:4233-4242`).
- EIP Appendix F: exact 170 count model and surface vocabulary mapping
  (`EIP_MIRROR.md:17997`, `18003-18006`); canonical source checked in before
  MOD-001 approval; rows generated from source metadata and module/domain
  ownership; hand-authored placeholder Screen IDs forbidden
  (`EIP_MIRROR.md:17999-18015`). Generating the manifest "plus
  count/route/contract lint" is a MOD-001 Implementation Complete
  deliverable, not a Ready precondition (`EIP_MIRROR.md:18038-18043`).
- EIP P2-N2: MOD-001 generates the manifest at Implementation Complete;
  non-UI modules prove no canonical screen resolves to them
  (`EIP_MIRROR.md:197-200`).
- GOV-01-R04: test *content* for not-yet-existing domains is out of scope —
  "the gate exists and blocks on it"
  (`knowledge/03-Modules/MOD-001/REQUIREMENTS.md:254-257`); exit evidence is
  a dry-run over the near-empty repo with every stage passing or correctly
  skipping "rather than silently omitted" (`REQUIREMENTS.md:267-269`), and a
  valid-fixture plus deliberate-violation proof per gate
  (`REQUIREMENTS.md:281-286`; obligation table `REQUIREMENTS.md:579`).
- MOD-001 owns zero canonical screens; the manifest carries an explicit
  `MOD-001: []` entry (`REQUIREMENTS.md:597`, `713-716`).
- ADR-009 D2: an empty skeleton registry/OpenAPI directory "yields
  INCONCLUSIVE (vacuous), never PASS"
  (`knowledge/04-Decisions/ADR-009-permission-lint-input-contract.md:145-149`).
  ADR-010: catalog/query error is ERROR, never an empty result
  (`knowledge/04-Decisions/ADR-010-rls-gate-runtime-envelope-manifest-predicate.md:80`);
  MOD-001 commits only the empty RLS-manifest skeleton (`ADR-010…md:269-270`, `453`).

Two gaps remain. ADR-009 defines INCONCLUSIVE but not how a required CI
status check disposes of it. Appendix F lists mandatory binding fields but
is silent on how a generated row represents fields whose owning module has
not yet been implemented.

## Decision

### D1 — Four-state gate result and qualified NOT_APPLICABLE

Gates 1, 4 and 5 and the C05 aggregate each report exactly one of
PASS | FAIL | ERROR | NOT_APPLICABLE. NOT_APPLICABLE is the CI-visible
disposition of ADR-009's INCONCLUSIVE (vacuous). It is permitted only if all
three of the following hold. If any one fails, the result is FAIL, or ERROR
for input or catalog faults:

1. **Inputs exist and parse.** For gate 1 that means the RLS manifest
   skeleton plus a catalog reachable under ADR-010 session discipline. For
   gate 4 it means `contracts/permissions/registry.json` plus
   `contracts/openapi/`. For gate 5 it means the canonical registry export
   plus the generated manifest. A missing or unparseable input, or a
   catalog/query error, is ERROR (`ADR-010…md:80`).
2. **Zero real items, with a printed reason.** The in-scope real-item count
   is exactly zero and is printed with a machine-readable reason string.
3. **Fixture self-test in the same job.** The same job ran the gate's
   fixture self-test in that run, and the deliberate-violation fixture
   FAILed while the conforming fixture PASSed. If the self-test did not run,
   or did not produce both outcomes, the result is FAIL.

Vacuous input never yields PASS. A gate that has any real item in scope
checks every such item fully; there is no partial NOT_APPLICABLE within
gate 4 or gate 1. A required status check treats NOT_APPLICABLE as
non-blocking only under conditions 1–3.

The C05 aggregate is green only if every stage reports PASS or qualified
NOT_APPLICABLE. Any FAIL, any ERROR, or a missing or unparseable stage
report blocks.

### D2 — Screen-contract manifest generated now, binding staged per row

1. **Generated, not hand-written.** At MOD-001 Implementation Complete,
   `contracts/ui/screen-contracts.yaml` is generated from the checked-in
   `veyro-product-experience-design/project/veyro-registry-data.js`.
2. **What counts as a row.** A canonical V1 row is a registry row that
   `resolve()` marks `isV1` and whose surface is one of the five UI surfaces
   in the EIP count model. The eight `Backend / no UI` (`SYS-*`) rows are
   excluded (`EIP_MIRROR.md:17997`).
3. **Surface names are mapped explicitly.** The registry's surface labels
   (`Veyro Admin`, `Front Desk & POS`, `Veyro Coach`, `Veyro Member`,
   `Internal Console`) map to the EIP vocabulary (Admin, Front Desk & POS,
   Coach, Member, Internal SaaS Console) through an explicit, checked
   mapping. A label outside the mapping is ERROR.
4. **Identity and ownership fields are real and validated now.** These are
   screen_id, surface, owning implementation module, wave and owner_domain.
   Owning module, wave and domain come from the EIP Appendix F
   module/surface ownership rules (`EIP_MIRROR.md:17999-18015` and the table
   that follows), never from hand assignment. The gate-5 identity check
   runs now and must PASS. It verifies all of the following:
   - V1 UI row count == manifest row count == 170;
   - the per-surface split is 85/16/19/35/15;
   - every row's owner resolves;
   - the `MOD-001: []` entry is present;
   - no Screen ID exists in the manifest that does not exist in the source.

   Gate 5 as a whole is never NOT_APPLICABLE.
5. **Binding fields stay explicitly unbound until the owner implements
   them.** The binding fields are the remaining TSD Appendix F mandatory
   fields: route, primary_read_model, queries, commands, realtime_channels,
   permissions, assurance, masking_variant, offline_mode,
   expected_error_codes, and the empty/loading/error states
   (`TSD_MIRROR.md:17344-17347`). They carry `binding_status: UNBOUND`
   until the owning module implements the screen. UNBOUND is an explicit
   marker, never an empty or invented value. Screen IDs themselves are
   never placeholders (`EIP_MIRROR.md:18015`).
6. **When the per-row checks bite.** Per-row binding checks report
   qualified NOT_APPLICABLE under D1 while the row's owning module is
   unimplemented. Once that module is marked implemented, binding is
   mandatory for that row, and an UNBOUND row whose owning module is marked
   implemented FAILs.
7. **Route-registry count equality is enforced at feature freeze/release**
   (`TSD_MIRROR.md:11618`, `17349-17351`). Its lint mechanism and
   deliberate-violation fixture must exist and be proven now
   (`EIP_MIRROR.md:18040-18041`).

## Corrections to the R1 draft

The draft was verified against the sources above. It was accurate except
for the following points, which this ADR corrects or tightens:

1. **Number.** "ADR-011" was already taken; this decision is recorded as
   ADR-014.
2. **"All canonical V1 rows" is not 170.** The registry contains 186 rows.
   `resolve()` marks 178 as `isV1`, split as Admin 85, Front Desk & POS 16,
   Coach 19, Member 35, Internal Console 15, and Backend / no UI 8. This was
   verified this session by evaluating the registry's own `resolve()`. 170
   is only correct after the eight `SYS-*` backend rows are excluded, so D2
   states that exclusion and the surface-label mapping explicitly. Because
   of this, `REQUIREMENTS.md:696`'s description of the registry as "170
   screens across 6 surface sections" is imprecise. That file is noted
   here but not edited in this operation.
3. **Binding field list was incomplete.** The draft listed only some of the
   binding fields. D2 lists the full TSD Appendix F mandatory set, adding
   `assurance` and `expected_error_codes`.
4. **D1's scope was wider than its evidence.** The draft wrote D1 as
   applying to "every architecture gate", but R1 determined gates 1, 4 and
   5 and C05 only. Some workflows already emit NOT_APPLICABLE without D1's
   in-job fixture self-test:
   - `.github/workflows/event-contract.yml:65-67` (gate 3);
   - `.github/workflows/domain-uniqueness.yml:85-87` (gate 6);
   - the applicability steps in `test-pyramid.yml`.

   This ADR neither ratifies nor invalidates those paths. Whether to
   reconcile them with D1 before C05 aggregates them is a follow-up
   decision. Until then, C05 must not count any of them as qualified
   NOT_APPLICABLE under D1 unless it meets conditions 1–3.

## Consequences

- **Gate 1 and gate 4.** Next implementation work wraps each gate in the
  four-state result with an in-job fixture self-test. For gate 4 it also
  commits the empty `contracts/permissions/registry.json` and
  `contracts/openapi/` skeletons if they are absent.
- **Gate 5.** Next implementation work builds the generator (the R2b
  next action), the identity lint, the per-row binding checks, and the
  stage-gated route-count lint. It also adds deliberate-violation
  fixtures for:
  - count mismatch;
  - invented ID;
  - UNBOUND row whose owner is marked implemented;
  - unknown surface label;
  - route-registry mismatch at the release stage;

  plus a conforming fixture.
- **C05.** One aggregating required check, with a dry-run evidence file
  recording each stage's disposition on `main`.
- **What this ADR does not do.** It changes no code, CI, scenario state,
  review counter or gate verdict, and promotes nothing. Each gate still
  needs its implementation, independent review and scenario execution
  before any PASS is claimed.
- **Future obligations.** Each UI-bearing module inherits a hard
  obligation to bind its rows before it can claim implementation.

## Conformance and owner-reserved determination

This ADR interprets TSD §24.1 and Appendix F, EIP Appendix F and P2-N2, and
ADR-009/ADR-010, choosing an engineering representation (the CI result
state and the UNBOUND marker) where those sources are silent. It does not
change:

- product scope, screens, pricing or business rules;
- the 170 count model or the forbidden-placeholder rule;
- ADR-009's never-PASS-on-vacuous rule or ADR-010's ERROR semantics;
- module ownership;
- any baseline text.

It relaxes no gate. NOT_APPLICABLE is stricter than ADR-009's bare
INCONCLUSIVE because it adds the in-job self-test. Binding is deferred
only to the TSD's own feature-release and feature-freeze points.

None of the four owner-reserved restrictions is touched: no spend, no real
member data (the registry is design metadata), no production action, and
no material product, architecture or scope change. Owner approval is
therefore not required.

Source of determination: commit c59a2ff. Runtime model id:
claude-opus-5-5.
