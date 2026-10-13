---
doc: ADR-009
status: DECIDED — operational reconciliation in progress; no module gate credit
date: 2026-10-13
decided_by: Owner (OWN-008)
---

# ADR-009: Lean evidence location for MOD-001 through MOD-074

## Decision and authority

The owner explicitly approved the narrow evidence-location amendment recorded as OWN-008 on 2026-10-13. This ADR records the EIP Appendix D process deviation required by DC-09. It supersedes OWN-001/ADR-002's choice of literal per-module Appendix D document paths only for active MOD-001 through MOD-074 operations. Historical records, including MOD-000 evidence, remain historical and immutable. The approved Blueprint, TSD, UX bundle and EIP DOCX are not edited, renamed or re-hashed. The EIP mirror retains the Appendix D baseline text and labels this later owner-approved operational override rather than silently rewriting the baseline.

For these modules, `knowledge/03-Modules/MOD-XXX/MOD-XXX.md` is the sole active operational Markdown document and evidence index. It becomes the Gatekeeper certificate only after a genuine independent approval, with reviewer identity, verdict and verification recorded; a pre-approval index must say NOT CERTIFIED. Routine separate report Markdown and a module-local `evidence/` directory are not required and must not be regenerated to satisfy obsolete paths. Use immutable CI run artifacts, immutable ACP execution/review artifacts and existing approved `knowledge/05-QA/` records for independent proof. Index every mandatory item by stable run/commit identifier and SHA-256 where applicable. Track current defects in the existing `knowledge/05-QA/BUG_REGISTRY.md`.

## Unchanged acceptance gates

This is storage/documentation structure only. Reproducible test/run proof, independent fresh-context review, qualified resolved model identity, real manual QA or EIP §12.1 owner-assisted fallback, traceability, defect/retest tracking, security and integrity checks, and Gatekeeper certification remain mandatory. No CAP-012 or MOD-001 credit arises from this decision. WIP=1, singleton runner/sole writer and read-only Dashboard remain unchanged. Sonnet performs routine implementation/qualification; Opus performs required independent approval and high-risk assurance.

## Reconciliation boundary

Update only active lower-tier contracts, references and validators that require the obsolete locations; do not create a documentation migration project or rewrite historical citations as if they were current. A validator must fail closed on missing mandatory *proof*, not on absence of an obsolete Markdown path. The frozen EIP Appendix D continues to state its original schema; this explicit owner-approved exception governs the named modules. Any proposed in-place change to the approved EIP DOCX or unapproved broader deviation requires separate approval. No such change is made here.
