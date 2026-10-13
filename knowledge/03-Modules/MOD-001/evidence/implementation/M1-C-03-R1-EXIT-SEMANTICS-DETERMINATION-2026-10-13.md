# M1-C-03 R1 — Gate 1/4/5 + C05 Exit-Semantics Determination (2026-10-13)

Status: COMPLETE

Runtime model id: claude-opus-5-5 (fresh-context architecture role; bounded
determination only — no code change, no review, no scenario disposition).

Inputs read: `/Users/ahmadmabrouk/.openclaw/workspace-veyro/control/R1_SOURCE_EXCERPTS_2026-10-13.md`
(line-numbered excerpts; citations below are to the original files), plus
targeted reads of `knowledge/04-Decisions/ADR-009-permission-lint-input-contract.md`
and `ADR-010-rls-gate-runtime-envelope-manifest-predicate.md`.

## Question

For MOD-001 exit, must gates 1 (RLS lint), 4 (permission lint), 5 (screen
contract lint) and the integrated C05 pipeline prove (A) a real CI-blocking
fail-closed mechanism with deliberate-violation and conforming synthetic
fixtures over the current repository surface, or (B) full real population
now (170 screens bound to real routes/APIs, real permission registry)? And
how must each gate behave on `main` with empty real inputs?

## Controlling text

- TSD §24.1 gates are universally quantified over what exists: RLS lint
  "every tenant table…" (`TSD_MIRROR.md:11599-11601`); permission lint "API
  commands/queries declare…; unregistered permission names fail build"
  (`TSD_MIRROR.md:11614-11615`); screen contract lint "every V1 Screen ID…
  maps to a BFF/read model or typed command manifest row **before feature
  release**" (`TSD_MIRROR.md:11617-11618`).
- EIP MOD-001 card Special rule: MOD-001 "implements all six TSD §24.1
  architecture gates", "imports the canonical screen registry, generates
  screen-contracts.yaml", and "proves with deliberate fixtures that
  architecture… controls cannot be bypassed" (`EIP_MIRROR.md:4233-4242`).
- GOV-01-R04 OUT of scope: test *content* for domains that don't exist yet —
  "the gate exists and blocks on it; content is later modules' job"
  (`knowledge/03-Modules/MOD-001/REQUIREMENTS.md:254-257`). Evidence: "full
  pipeline dry-run against the current (near-empty) repo, every stage passing
  or correctly skipping (not-yet-applicable) rather than silently omitted"
  plus a deliberate-violation proof per gate (`REQUIREMENTS.md:267-275`);
  acceptance: passing valid-fixture proof AND deliberate-violation fail-closed
  proof per gate (`REQUIREMENTS.md:281-286`). Obligation table: "each as a
  real CI-blocking check, each with a deliberate-violation fixture proving
  fail-closed" (`REQUIREMENTS.md:579`).
- Appendix F (TSD): manifest materialized from the canonical design-registry
  export and validated against OpenAPI/AsyncAPI/frontend route registry
  (`TSD_MIRROR.md:17338-17342`); release gate registry V1 count == manifest
  rows == frontend route-registry V1 rows, mismatch is P1 and "blocks feature
  freeze" (`TSD_MIRROR.md:17349-17351`).
- Appendix F (EIP): MOD-001 must import the registry and materialize
  `screen-contracts.yaml` "plus the generated mapping rows below before any
  UI-bearing module can become Ready"; exact 170 count model; canonical
  source checked in/deterministically referenced "before MOD-001 approval";
  hand-authored placeholder Screen IDs forbidden; rows generated from source
  metadata and module/domain ownership (`EIP_MIRROR.md:17999-18015`).
  Generating the manifest "plus count/route/contract lint is a MOD-001
  Implementation Complete deliverable" (`EIP_MIRROR.md:18038-18043`).
- P2-N2: "Appendix F Ready condition is scoped to UI-bearing modules;
  MOD-001 generates the manifest at Implementation Complete; non-UI modules
  prove no canonical screen resolves to them" (`EIP_MIRROR.md:197-200`).
- MOD-001 owns zero canonical screens; manifest carries an explicit empty
  `MOD-001: []` entry (`REQUIREMENTS.md:597`, `693-716`).
- ADR-009 D2: real registry contents belong to the authorization module;
  MOD-001 commits synthetic fixtures; an empty skeleton registry/OpenAPI dir
  "yields INCONCLUSIVE (vacuous), never PASS" (`ADR-009…md:145-149`).
  ADR-010 D3.6: MOD-001 commits only the empty RLS-manifest skeleton
  (`ADR-010…md:269`, `453`); catalog/query failure is ERROR, never an empty
  result (`ADR-010…md:80`).

## Per-gate verdicts

### Gate 1 — RLS lint: **A**

Universally quantified over tenant tables that exist (`TSD_MIRROR.md:11599`);
card requires deliberate-fixture proof (`EIP_MIRROR.md:4239-4242`); real
table content is later modules' (`REQUIREMENTS.md:254-257`); ADR-010 already
scopes MOD-001 to an empty manifest skeleton plus the synthetic harness
(`ADR-010…md:269`, `421`, `453`). No source requires real product tenant
tables at MOD-001 exit — none can exist under WIP=1.

### Gate 4 — Permission lint: **A**

Quantified over API commands/queries that exist (`TSD_MIRROR.md:11614-11615`);
ADR-009 D2 explicitly assigns real registry contents to the authorization
module and limits MOD-001 to schema + synthetic fixtures + optional empty
skeleton (`ADR-009…md:145-149`). B (real permission registry now) would
contradict a DECIDED ADR and the R04 OUT-of-scope line.

### Gate 5 — Screen contract lint: **A for binding; NOT pure A — the
import/generation step is required real work now** (neither B as framed nor
SOURCES_SILENT)

- Required at MOD-001 exit (real, not synthetic): import the checked-in
  canonical registry and generate `contracts/ui/screen-contracts.yaml` with
  all 170 V1 rows carrying the identity/ownership columns derivable from
  source metadata — screen_id, surface, owning implementation module, wave,
  owner_domain — and the explicit `MOD-001: []` entry
  (`EIP_MIRROR.md:17999-18015`, `18038-18043`, `4236-4237`; `EIP_MIRROR.md:197-200`;
  `REQUIREMENTS.md:713-716`). The registry-count == manifest-count (170)
  equality and per-surface split (85/16/19/35/15) are checkable now and must
  be enforced now (`EIP_MIRROR.md:18003-18006`).
- NOT required at MOD-001 exit (A): binding each row to a real route,
  BFF/read model, commands, permissions, realtime channels — those artifacts
  do not exist until owning modules unlock. TSD places the binding
  obligation "before feature release" (`TSD_MIRROR.md:11618`) and the
  route-registry count equality at "feature freeze" (`TSD_MIRROR.md:17351`),
  not at MOD-001 exit. The lint mechanism for those checks must exist and be
  fixture-proven now (`EIP_MIRROR.md:18040-18041` "count/route/contract lint").
- Sources are silent on how not-yet-bound mandatory fields
  (`TSD_MIRROR.md:17344-17347`) are represented in a generated row. This is
  an engineering/architecture representation choice, not a product/business
  one → resolved by ADR (below), not owner decision. Constraint: Screen IDs
  themselves may never be placeholders (`EIP_MIRROR.md:18015`).

### Integrated C05 pipeline: **A**

`REQUIREMENTS.md:267-269` defines the exit evidence as a dry-run over the
current near-empty repo with every stage "passing or correctly skipping
(not-yet-applicable) rather than silently omitted", plus per-gate
deliberate-violation and valid-fixture proofs (`REQUIREMENTS.md:281-286`).
Real domain content is excluded (`REQUIREMENTS.md:254-257`).

**Option B is rejected for all four** — no source requires it, and the only
real-population obligation (gate 5's 170-row import) is satisfiable now from
the checked-in registry.

## Required empty-input behavior on `main` today

Never PASS on vacuous input (ADR-009 D2, `ADR-009…md:149`); never silently
omitted (`REQUIREMENTS.md:268-269`). Each gate job emits one of PASS / FAIL /
ERROR / NOT_APPLICABLE, where NOT_APPLICABLE is the CI-visible disposition of
ADR-009's INCONCLUSIVE (vacuous) and is allowed only if ALL hold:

1. The gate's discovery inputs exist and parse (gate 1: RLS manifest
   skeleton + catalog reachable under ADR-010 session discipline; gate 4:
   `contracts/permissions/registry.json` + `contracts/openapi/`; gate 5: the
   canonical registry export + generated manifest). Missing/unparseable
   input, or a catalog/query error, is ERROR → job fails (`ADR-010…md:80`).
2. The in-scope real-item count is exactly zero and is printed with a
   machine-readable reason string (e.g. `NOT_APPLICABLE: 0 real tenant
   tables; owning modules locked under WIP=1`).
3. The same job ran the gate's fixture self-test in that run — the
   deliberate-violation fixture FAILed and the conforming fixture PASSed. If
   the self-test did not run or did not produce both outcomes → FAIL. This
   prevents a vacuous NOT_APPLICABLE from masking a broken gate.

Per gate today:
- Gate 1: NOT_APPLICABLE-with-reason (zero real tenant tables) iff 1–3 hold.
- Gate 4: NOT_APPLICABLE-with-reason (zero real OpenAPI operations) iff 1–3
  hold; any operation present must be fully checked (no partial N/A).
- Gate 5: **not** NOT_APPLICABLE as a whole. The registry↔manifest identity
  check (170 == 170, per-surface split, ownership resolution, `MOD-001: []`,
  no hand-authored IDs) runs and must PASS — mismatch FAILs. Only the
  per-row binding and route-registry-count sub-checks report
  NOT_APPLICABLE-with-reason (rows whose owning module is not yet
  implemented; release/feature-freeze stage not reached), under the same
  conditions 1–3. Once a row's owning module claims implementation, its
  binding sub-check becomes mandatory for that row.
- C05: overall job green iff every stage is PASS or qualified
  NOT_APPLICABLE; any FAIL/ERROR or missing stage report blocks.

## Minimum bounded file-level mechanism work remaining (next implementation step)

Not re-verified against the current tree in this session (excerpt-bounded);
the implementer must diff against existing `tools/` before writing.

- Gate 1: the RLS lint entry point emits the four-state result with the
  NOT_APPLICABLE predicate above; a CI job step runs the ADR-010 negative
  and positive fixture set before the real scan in the same job; result
  artifact records counts + reason.
- Gate 4: same wrapper for the ADR-009 permission lint (INCONCLUSIVE →
  NOT_APPLICABLE only under conditions 1–3); commit empty skeleton
  `contracts/permissions/registry.json` + `contracts/openapi/` if absent;
  CI step runs violation/conforming fixtures in-job.
- Gate 5: importer/generator from the checked-in
  `veyro-product-experience-design/project/veyro-registry-data.js` →
  `contracts/ui/screen-contracts.yaml` (170 rows, identity/ownership
  columns, binding fields in the ADR-defined unbound representation,
  `MOD-001: []`); lint enforcing identity checks now and binding/route-count
  checks per row/stage; deliberate-violation fixtures (count mismatch,
  invented ID, unbound row whose owner is marked implemented, route-registry
  mismatch at release stage) and a conforming fixture.
- C05: one workflow aggregating the gate jobs as required status checks,
  failing on any FAIL/ERROR/missing report; dry-run evidence file capturing
  each stage's disposition on `main`.

## ADR required: **yes** (engineering, no owner approval needed)

ADR-009 defines INCONCLUSIVE but not its CI disposition; Appendix F is
silent on unbound-field representation. Draft:

> **ADR-011 (draft): Vacuous-gate CI disposition and screen-contract
> staged binding.**
> Context: MOD-001 must ship CI-blocking architecture gates while owning no
> tenant tables, API operations or screens; later modules populate inputs
> under WIP=1 (`REQUIREMENTS.md:254-257`, `267-269`; `ADR-009…md:145-149`).
> D1: Every architecture gate reports PASS | FAIL | ERROR | NOT_APPLICABLE.
> NOT_APPLICABLE (the CI disposition of ADR-009 INCONCLUSIVE) requires
> parseable discovery inputs, zero in-scope real items with a printed
> reason, and an in-job fixture self-test in which the violation fixture
> FAILs and the conforming fixture PASSes; otherwise FAIL/ERROR. Never PASS
> on vacuous input. A required status check treats NOT_APPLICABLE as
> non-blocking only under these conditions.
> D2: `screen-contracts.yaml` is generated at MOD-001 Implementation
> Complete with all canonical V1 rows; identity/ownership fields are real
> and validated now (count 170, per-surface split, `MOD-001: []`, no
> hand-authored IDs). Binding fields (route, primary_read_model, queries,
> commands, permissions, realtime_channels, masking/offline/error states)
> carry an explicit `binding_status: UNBOUND` until the owning module
> implements the screen; an UNBOUND row whose owning module is marked
> implemented FAILs; route-registry count equality is enforced at feature
> freeze/release (`TSD_MIRROR.md:11618`, `17351`).
> Conformance: interprets TSD §24.1/Appendix F and EIP Appendix F/P2-N2
> without changing scope, product, pricing or architecture; no owner
> approval required. Decider: veyro-lead.

## Owner decision

None required. No SOURCES_SILENT verdict on a product/business choice; the
one silence (unbound-field representation) is engineering-level and
resolved by the ADR above.
