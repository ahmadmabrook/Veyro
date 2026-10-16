# ADR-0001 — Governance foundation: registry, ADR change control, frozen baseline

- ID: ADR-0001
- Status: PROPOSED
- Decision-Key: governance-foundation-change-control
- Covers: governance/, knowledge/00-Decisions/, tools/governance/, tools/mission_runner/runner.py, tools/mission_runner/module_catalog.json, tools/mission_runner/workflow_check.py, .github/workflows/

**This ADR is PROPOSED. It authorizes nothing.** It has no review reference and is not ACCEPTED; a PROPOSED ADR cannot authorize a controlled change (`check-change` returns `CHANGE_ADR_NOT_ACCEPTED`). No owner approval, reserved action or module acceptance is implied.

## Context
EIP v2.0 §21.3 gives MOD-002 (Product, Architecture, Data & AI Governance, Foundation wave, prerequisite MOD-001) the smallest enforceable source-of-truth, ADR/change-control, requirement ownership/traceability and approved-baseline checks. TSD GOV-02 (§10.55) is an internal Product Operations concept, confidential and tenant-scoped, Tier 2, with INV-GOV-02 and RB-GOV-02. Appendix B maps GOV-02-R01..R08 to MOD-002. Today there is a validator (`tools/governance/governance_check.py`) but no recorded decision on what it governs, so controlled paths have no decision record to cite.

## Decision
Adopt, as a proposal, this foundation mechanism:
1. `governance/registry.json` (schema `veyro.governance.registry/1`) is the single machine-readable record of the pinned `PROJECT_INDEX.md` hash and authority rows, the reserved-action names (DC-16), the GOV-02 classification (concept metadata only) and the eight requirement records, each owned by exactly one module.
2. Changes to the controlled paths listed in Covers require an ACCEPTED ADR whose Covers lists the path and which is not itself part of the change.
3. Frozen paths (the four authority rows and `PROJECT_INDEX.md`, plus any `OWNER-*` record) are never changed under an ADR; they need a later owner record that lists them.
4. `governance_check.py check --root .` and `check-change` are the enforcement points; they are read-only and fail closed.

## Rationale
A small stdlib-only validator over plain files is verifiable by the existing runner and CI without new services, matches the Foundation scope, and keeps authority (owner records) separate from engineering decisions (ADRs).

## Alternatives considered
- Prose-only governance documents: rejected, not enforceable.
- A database-backed registry or workflow engine: rejected, out of Foundation scope and would imply an unbuilt control-plane store.
- Reusing the owner baseline record as authority for later changes: rejected; the validator refuses it.

## Consequences
- Edits to governance code, registry, decisions, the runner, the module catalog, the workflow checker and CI workflows become blocked until an ACCEPTED, independently reviewed ADR covers them. The proposed Covers list is limited to governance-controlled dependencies this foundation and the upcoming CI slice (S3) need. It deliberately excludes frozen baseline paths. Although Covers lists the `knowledge/00-Decisions/` directory, `OWNER-*` records in it remain frozen by the validator and are never ADR-authorized, despite the directory prefix.
- FOUNDATION status in the registry means mapped and in scope, not implemented or PASS. The eight capabilities remain open beyond the mechanism listed in MOD-002.md.
- Accepting this ADR needs an independent review whose ID is recorded in a `Review` header; none exists yet.

## Invariant
INV-GOV-02: no controlled or frozen path changes without the decision record the validator requires, and no requirement is reported as product PASS by structural evidence alone.

## Rollout and rollback
Rollout: the runner runs `governance_check.py check --root .`; CI wiring is a later slice (S3). Acceptance of this ADR is a separate, independently reviewed step. Rollback: revert the commit that introduced these files with a new revert commit (no history rewrite); no data, schema or runtime state is created, so nothing else needs undoing.
