---
doc: ADR-001
status: RECORDED (retroactive — see note below)
date: 2026-09-04
decided_by: main session, Phase 5 remediation (retroactively documenting a deviation made in chunk 1, 2026-08-31)
---

# ADR-001: `knowledge/` vault schema deviates from EIP Appendix D

## Note on retroactivity

This ADR is being recorded on 2026-09-04 (Phase 5 of MOD-000), but the
deviation it documents was made in chunk 1 (2026-08-31), when the vault
skeleton was first created. `DEVELOPMENT_CONSTITUTION.md`'s DC-09 requires
material deviations to have an ADR *before* implementation; this one
doesn't, because no ADR mechanism existed yet at the time (that's the
deviation itself: no `knowledge/04-Decisions/` directory was ever created,
even though `SESSION_BOOTSTRAP.md` referenced it from the start). Found by
the Phase 5 independent review (finding F5-012/F5-013). Recorded now,
honestly labeled as retroactive rather than pretending it was done
up-front.

## Decision

The actual `knowledge/` vault does not follow EIP Appendix D's specified
schema. Differences, as found by Phase 5:

| EIP Appendix D specifies | Actual repo has |
|---|---|
| `knowledge/03-Modules/MOD-xxx/{STATUS,REQUIREMENTS,SCENARIOS,TEST_RESULTS,TESTSPRITE,MANUAL_QA,CODE_REVIEW,LOAD_SECURITY,APPROVAL,RUNBOOK,CAPABILITIES,MODEL_ROUTE}.md` | `knowledge/03-Modules/MOD-000/` with an `evidence/` subtree (bugs, scenario-execution/phase{1-4}, manual-qa, model-routing, config-runtime, durability, tests) plus `scenario-catalog/` and `module-capabilities.yaml` |
| `knowledge/00-System/EXTERNAL_GATES.md`, `OWNER_APPROVALS.md` | `knowledge/03-ExternalGates/` (directory of individual gate files) |
| `knowledge/00-System/CAPABILITY_POLICY.md` / `CAPABILITY_REGISTRY.md` | `knowledge/04-Capabilities/` |
| `knowledge/05-QA/{BUG_REGISTRY,REGRESSION_INDEX,TESTSPRITE_INDEX,MANUAL_QA_INDEX,MODEL_ROUTE_INDEX,CAPABILITY_EVAL_INDEX,MANUAL_REGRESSION_CORE,LOAD_ENVIRONMENTS}.md` | No `05-QA/` — individual files scattered under `01-Modules/MOD-000/evidence/` and `00-System/` |
| `knowledge/01-Product/`, `02-Architecture/`, `04-Decisions/`, `06-Sessions/`, `07-Releases/` | None exist; `02-Decisions/` created by this ADR |

## Rationale for not doing a full mechanical restructure now

A full rename/move to match Appendix D exactly would touch essentially
every durable file in the repo and every cross-reference inside them (the
evidence-integrity checker alone tracks dozens of `knowledge/...` paths).
That is itself a large, high-blast-radius change — arguably a material
architecture change in its own right, which under
`.claude/rules/owner-reserved-restrictions.md` item 4 ("no material
product, pricing, business, architecture, or scope change without explicit
owner approval") should not be executed unilaterally by an agent mid-review
without the owner weighing in on whether the current, working, actual-path
structure should be preserved (with the EIP's own paths corrected instead)
or the repo should be physically reorganized to match Appendix D literally.

## What this ADR does now (lower-risk, does not require owner sign-off)

1. Creates `knowledge/04-Decisions/` (this file), closing SESSION_BOOTSTRAP.md's
   dangling reference and giving the project an actual ADR mechanism going
   forward, per DC-09.
2. Records the deviation honestly, rather than leaving it undocumented.

## What remains open (requires an owner decision — filed as BUG-017)

Whether to (a) physically restructure the vault to match Appendix D
exactly, or (b) formally amend the project's own governing documents
(`CLAUDE.md`, `SESSION_BOOTSTRAP.md`) to declare the actual structure as
the accepted, permanent deviation from Appendix D. Either is a legitimate
outcome; neither should be chosen unilaterally by an agent. See
`evidence/bugs/BUG-017-vault-schema-deviation-unresolved.md`.

## Also created by this same Phase 5 pass (independent of the restructure question)

- `knowledge/00-System/EXTERNAL_GATES.md` and `OWNER_APPROVALS.md` —
  genuinely missing per Appendix D and referenced by `SESSION_BOOTSTRAP.md`
  step 3 as things to check; authored as thin index files pointing at the
  existing `knowledge/03-ExternalGates/` directory content (additive, does
  not require moving anything, low risk).
