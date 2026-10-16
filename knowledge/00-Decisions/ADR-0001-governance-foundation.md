# ADR-0001 — Governance foundation: registry, ADR change control, frozen baseline

- ID: ADR-0001
- Status: ACCEPTED
- Review: MR-MOD-002-20261016-024 APPROVED
- Decision-Key: governance-foundation-change-control
- Covers: governance/, knowledge/00-Decisions/, tools/governance/, tools/mission_runner/runner.py, tools/mission_runner/module_catalog.json, tools/mission_runner/workflow_check.py, .github/workflows/

**This ADR is ACCEPTED, but operationally conditional.** The decision text review is recorded in the `Review` header; acceptance takes operational effect only once the exact-SHA push CI of the acceptance candidate commit succeeds. It authorizes no owner-reserved action and implies no module or product acceptance and no broader governance claim.

## Context
EIP v2.0 §21.3 gives MOD-002 (Product, Architecture, Data & AI Governance, Foundation wave, prerequisite MOD-001) the smallest enforceable source-of-truth, ADR/change-control, requirement ownership/traceability and approved-baseline checks. TSD GOV-02 (§10.55) is an internal Product Operations concept, confidential and tenant-scoped, Tier 2, with INV-GOV-02 and RB-GOV-02. Appendix B maps GOV-02-R01..R08 to MOD-002. Today there is a validator (`tools/governance/governance_check.py`) but, before this acceptance, no accepted decision on what it governs, so controlled paths had no accepted decision record to cite.

## Decision
Adopt this foundation mechanism:
1. `governance/registry.json` (schema `veyro.governance.registry/1`) is the single machine-readable record of the pinned `PROJECT_INDEX.md` hash and authority rows, the reserved-action names (DC-16), the GOV-02 classification (concept metadata only) and the eight requirement records, each owned by exactly one module.
2. Changes to the controlled paths listed in Covers require an ACCEPTED ADR whose Covers lists the path and which is not itself part of the change.
3. Frozen paths (the four authority rows and `PROJECT_INDEX.md`, plus any `OWNER-*` record) are never changed under an ADR; they need a later owner record that lists them.
4. `governance_check.py check --root .` and `check-change` are read-only and fail closed. The static `check` runs in CI. Operator-run `check-change` becomes a mandatory local pre-push step only AFTER this ADR is accepted (after the acceptance commit's exact-SHA CI succeeds), not now; it is never CI-enforced. The Review header format check is not runner evidence verification (see Enforcement scope).
5. Once ACCEPTED, this ADR is standing authority for the paths in its Covers. It is not per-change approval and has no expiry. It does not relax the owner direct-main process: every change still needs exact-diff independent review and exact-SHA push CI, and a workflow path in Covers cannot relax OWNER direct-main constraints. Standing authority NEVER authorizes a DC-16 reserved action; removal or narrowing of `reserved_actions`; changes to frozen rows or any `OWNER-*` freeze; or weakening of the validator's Reserved-Action, Owner-Approval, frozen-path or self-authorization checks. Those changes need an `OWNER-*` record, which is owner authority and separate from ADR review.

## Enforcement scope
- CI runs only the static `governance_check.py check --root .`. Operator-run `check-change` becomes a mandatory local pre-push step only AFTER acceptance (after the acceptance commit's exact-SHA CI success), not now; CI never enforces it.
- The `Review` header is only format-checked. The validator does not verify that the referenced review exists in the runner.

## Pre-acceptance basis
Before acceptance, ADR-0001 is not in force and `check-change` is not adopted. Controlled-path edits through acceptance, including e0d14c1 and this acceptance candidate, rely only on the existing OWNER direct-main process (exact-diff independent review plus exact-SHA push CI). They do not rely on this ADR or on any reviewer-granted exception. `check-change` becomes mandatory locally only after the acceptance commit's exact-SHA CI succeeds. If acceptance CI fails, that same OWNER-process basis permits a reviewed forward fix or revert of that acceptance commit only, including reviewed forward fixes of the acceptance change until the first exact-SHA CI success on a head with ADR-0001 ACCEPTED; there is no broader exception. Later amendments use the two-commit bridge below.

## Rationale
A small stdlib-only validator over plain files is verifiable by the existing runner and CI without new services, matches the Foundation scope, and keeps authority (owner records) separate from engineering decisions (ADRs).

## Alternatives considered
- Prose-only governance documents: rejected, not enforceable.
- A database-backed registry or workflow engine: rejected, out of Foundation scope and would imply an unbuilt control-plane store.
- Reusing the owner baseline record as authority for later changes: rejected; the validator refuses it.

## Consequences
- Edits to governance code, registry, decisions, the runner, the module catalog, the workflow checker and CI workflows become blocked until an ACCEPTED, independently reviewed ADR covers them. The proposed Covers list is limited to governance-controlled dependencies this foundation and the upcoming CI slice (S3) need. It deliberately excludes frozen baseline paths. Although Covers lists the `knowledge/00-Decisions/` directory, `OWNER-*` records in it remain frozen by the validator and are never ADR-authorized, despite the directory prefix.
- FOUNDATION status in the registry means mapped and in scope, not implemented or PASS. The eight capabilities remain open beyond the mechanism listed in MOD-002.md.
- Accepting this ADR needs an independent review whose ID is recorded in a `Review` header; MR-MOD-002-20261016-024 is recorded. The header is format-checked only, not verified against runner review existence.
- The CI slice (S3) passed CI at e0d14c1; this acceptance candidate's own exact-SHA push CI has not been claimed here and must succeed before acceptance is operational. The S3 reference here concerns workflow coverage only; this ADR makes no product PASS, MOD-002 acceptance, or AI, data, tenant, privacy or runtime certification claim.

## Invariant
INV-GOV-02: no controlled or frozen path changes without the decision record the validator requires, and no requirement is reported as product PASS by structural evidence alone.

## Rollout and rollback
Rollout: the runner and CI run the static `governance_check.py check --root .`; `check-change` becomes an operator-run pre-push step only after acceptance and is not enforced by CI. Acceptance of this ADR is a separate, independently reviewed step under the pre-acceptance basis above.

Rollback and amendment: commit e0d14c1 also contains Mission Control, so it cannot simply be reverted to remove this ADR. Any later amendment, rollback, rejection or supersession of ADR-0001 takes two commits, with no history rewrite:
1. Add a separate ACCEPTED ADR with a different Decision-Key (the bridge ADR) whose Covers includes this ADR-0001 file and also lists a planned successor ADR file, under ADR-0001 authority. The successor ADR must share the ADR-0001 Decision-Key (`governance-foundation-change-control`) to supersede it.
2. Use that ADR to edit, revert, reject or supersede ADR-0001.

No data, schema or runtime state is created, so nothing else needs undoing.
