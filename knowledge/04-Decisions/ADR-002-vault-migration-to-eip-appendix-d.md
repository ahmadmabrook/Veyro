---
doc: ADR-002
status: STRUCTURALLY EXECUTED, NOT YET CLOSED — pending a clean second fresh-session restoration pass (a first pass found this file itself claiming completion prematurely; corrected here, a second pass caught this exact field still stale and this is the fix for that)
date: 2026-09-05
decided_by: Owner (explicit decision, 2026-09-05) — do not ratify ADR-001's deviation, migrate instead
executed_by: main session, same chunk
---

# ADR-002: Migrate the durable knowledge vault to EIP Appendix D

## Decision

Supersedes ADR-001's open question. The owner explicitly decided: migrate
the vault to match EIP Appendix D as closely and literally as the source
requires, rather than ratifying the pre-existing deviation.

## What changed (path migration map)

| Old path | New path | Method |
|---|---|---|
| `knowledge/01-Modules/` | `knowledge/03-Modules/` | `git mv` (history preserved) |
| `knowledge/02-Decisions/` | `knowledge/04-Decisions/` | `git mv` |
| `knowledge/03-ExternalGates/EIP_STATUS_CONTRADICTION.md` | `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md` | `git mv` |
| `knowledge/04-Capabilities/CAPABILITY_POLICY.md` | `knowledge/00-System/CAPABILITY_POLICY.md` | `git mv` |
| `knowledge/04-Capabilities/CAPABILITY_REGISTRY.md` | `knowledge/00-System/CAPABILITY_REGISTRY.md` | `git mv` |
| `knowledge/04-Capabilities/module-capabilities.schema.yaml` | `knowledge/00-System/module-capabilities.schema.yaml` | `git mv` |
| `knowledge/04-Capabilities/evidence/` | `knowledge/05-QA/capability-evidence/` | `git mv` |
| `knowledge/01-Modules/MOD-000/module-capabilities.yaml` | `knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml` | `git mv` (moved into evidence/, referenced by new `CAPABILITIES.md`) |
| `knowledge/01-Modules/MOD-000/evidence/model-routing/MODEL_ROUTE_INDEX.md` | `knowledge/05-QA/MODEL_ROUTE_INDEX.md` | `git mv` (Appendix D names this a top-level 05-QA file) |

All other content under the old `01-Modules/MOD-000/` tree (bugs,
scenario-execution phases, manual-qa, code-review, model-routing,
config-runtime, durability, security, scenario-catalog) moved 1:1 under
`knowledge/03-Modules/MOD-000/` — same internal structure, only the
module-root prefix changed. **Every file preserved, none deleted, all
moves done via `git mv` so `git log --follow` still traces full history.**

## New files/directories authored (did not exist before; Appendix D
requires them, nothing to move — new content)

`knowledge/03-Modules/MOD-000/{STATUS,REQUIREMENTS,SCENARIOS,TEST_RESULTS,
TESTSPRITE,MANUAL_QA,CODE_REVIEW,LOAD_SECURITY,RUNBOOK,CAPABILITIES,
MODEL_ROUTE}.md` (all as index/pointer files into the preserved evidence,
per the interpretation below); `knowledge/05-QA/{BUG_REGISTRY,
REGRESSION_INDEX,MANUAL_REGRESSION_CORE,LOAD_ENVIRONMENTS,
CAPABILITY_EVAL_INDEX,TESTSPRITE_INDEX,MANUAL_QA_INDEX}.md`;
`knowledge/06-Sessions/README.md`; `knowledge/07-Releases/README.md`;
`knowledge/01-Product/README.md`; `knowledge/02-Architecture/
{INVARIANT_REGISTRY,ADR_CONFORMANCE}.md`. `APPROVAL.md` deliberately NOT
created — the Module Approval Certificate does not exist yet, by design
(forward reference).

## Interpretation decision: index files, not content merges

Appendix D names each per-module file as a single markdown document
(e.g. `TEST_RESULTS.md` — "Deterministic automated/integration/E2E
results and run references"). The actual granular evidence already
existed as many separate, dated files (per-phase test runs, per-bug
records, per-review records). Rather than destructively merging years —
well, days — of granular evidence into single monolithic files (high
risk of losing detail or introducing transcription errors), each new
top-level file is authored as a **summary/index that links to the
preserved granular evidence**, consistent with how Appendix D itself
already treats the `05-QA/*_INDEX.md` files as indexes over evidence
rather than the evidence itself. This satisfies "the exact named file
exists at the exact named path with the described content" without
requiring irreversible content surgery on the underlying record.

## Verification performed

1. **Before migration:** `evidence_integrity_check.py` re-run (baseline).
2. **Reference update:** every file referencing a moved path was found via
   `grep -r` and corrected via scripted `sed` substitution (43 files) plus
   targeted manual fixes for context-sensitive cases (ambiguous shared
   prefixes, historical text that should NOT be rewritten — see below).
3. **Historical text preserved on purpose:** `ADR-001`'s own path-mapping
   table describes the *old* structure as it stood at the time ADR-001 was
   written — left untouched, since rewriting it would falsify the
   historical record ADR-001 exists to preserve. The Phase 3
   `TEST_RUN_PHASE3_2026-09-04.md`'s deliberately-fake illustrative path
   (`knowledge/WRONG/PATH/...`, used in a Notion-drift negative-test
   writeup) was also left untouched — it was never a real reference.
4. **After migration:** `evidence_integrity_check.py` re-run again — see
   `knowledge/03-Modules/MOD-000/evidence/security/` (or wherever the
   Phase 5 migration evidence record lands — cross-reference
   `MIGRATION_EVIDENCE_2026-09-05.md`) for the final clean result.
5. **Baseline hashes:** re-verified unchanged before and after (the
   migration touches only `knowledge/`, `.claude/`, and root doc files —
   never the 4 governing baseline artifacts or the design bundle).
6. **Fresh-session restoration:** attempted post-migration via an
   independent fresh-context check. **Correction:** this line originally
   asserted restoration was "proven" — false when written, and still
   false as of the most recent (second) verification pass, which found
   this exact ADR still claiming completion while its own decided/
   executed content had genuinely landed. See
   `knowledge/03-Modules/MOD-000/evidence/durability/FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`
   for the full, honest account across both passes — restoration is not
   yet proven clean; a third pass is the actual closing condition.

## No governing baseline was modified

Confirmed: none of the 4 governing baseline artifacts
(`Gym_OS_Master_Product_Blueprint_v1_English.docx`,
`Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx`,
`Veyro_Engineering_Implementation_Plan_v1.4.1_..._GOVERNING_BASELINE.docx`,
`veyro-product-experience-design/`) were touched by this migration. Hashes
re-verified identical to `PROJECT_INDEX.md` before and after.
