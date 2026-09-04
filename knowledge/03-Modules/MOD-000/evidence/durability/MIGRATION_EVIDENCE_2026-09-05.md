---
doc: MIGRATION_EVIDENCE
status: LIVE
date: 2026-09-05
---

# BUG-017 remediation — vault migration evidence record

Owner decision (2026-09-05): migrate the vault to EIP Appendix D literally,
rather than ratify the deviation ADR-001 had documented. Full decision
record and path-migration map: `knowledge/04-Decisions/ADR-002-vault-migration-to-eip-appendix-d.md`.

## Execution log

```
$ git mv knowledge/01-Modules knowledge/03-Modules
$ git mv knowledge/02-Decisions knowledge/04-Decisions
$ git mv knowledge/03-ExternalGates/EIP_STATUS_CONTRADICTION.md knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md
$ git mv knowledge/04-Capabilities/CAPABILITY_POLICY.md knowledge/00-System/CAPABILITY_POLICY.md
$ git mv knowledge/04-Capabilities/CAPABILITY_REGISTRY.md knowledge/00-System/CAPABILITY_REGISTRY.md
$ git mv knowledge/04-Capabilities/module-capabilities.schema.yaml knowledge/00-System/module-capabilities.schema.yaml
$ git mv knowledge/04-Capabilities/evidence knowledge/05-QA/capability-evidence
$ git mv knowledge/03-Modules/MOD-000/module-capabilities.yaml knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml
$ git mv knowledge/03-Modules/MOD-000/evidence/model-routing/MODEL_ROUTE_INDEX.md knowledge/05-QA/MODEL_ROUTE_INDEX.md
```

All 8 moves via `git mv`, tracked by Git as renames (confirmed via
`git status --porcelain` showing `R` for every path) — `git log --follow`
retains full history on every moved file.

## Reference update

45 files referenced old paths (found via `grep -rl` across `.md/.py/.yaml/
.yml/.json/.txt`). Corrected via scripted `sed` substitution (9 ordered
rules, most-specific-first) plus targeted manual fixes for
context-sensitive cases:
- `SESSION_BOOTSTRAP.md`'s "External gates / owner approvals" line split
  into two correct pointers (`EXTERNAL_GATES.md` + `OWNER_APPROVALS.md`).
- `EXTERNAL_GATES.md` fully rewritten to match Appendix D's own field
  list (EXT ID, gate class, gated capability, owner, blocks, evidence,
  status, last verified) — this closes the remainder of F5-014's earlier
  finding about that file's schema.
- `DEVELOPMENT_CONSTITUTION.md`'s bare `knowledge/04-Capabilities/`
  directory mention corrected to the two specific new file paths.
- `CURRENT_STATE.md`'s Module Approval Certificate path corrected to the
  Appendix-D-required `knowledge/03-Modules/MOD-000/APPROVAL.md` (was
  previously an ad hoc `evidence/` path).
- `SCENARIO_CATALOG.md`'s one brace-expansion-pattern reference
  (not caught by literal-string sed) fixed manually.
- **Deliberately NOT rewritten:** `ADR-001`'s own historical path table
  (describes the pre-migration state on purpose) and
  `TEST_RUN_PHASE3_2026-09-04.md`'s illustrative fake path (never a real
  reference, used in a Notion-drift negative-test writeup).

## Broken-reference / orphan scan

`evidence_integrity_check.py` upgraded during this same remediation to
auto-discover and scan **every** `.md`/`.yaml`/`.yml` file under
`knowledge/` and `.claude/` plus root `CLAUDE.md` (86 files), rather than
a curated list — a hardcoded list is exactly how a prior dangling
reference survived three phases undetected.

- **Before migration** (after moves, before new-file authoring): 22 real
  findings, all of them the EIP-required files not yet existing (expected
  mid-migration state, not a defect).
- **After migration** (all new files authored, all references corrected):
  **0 broken references**, 4 expected-absent forward references (the
  not-yet-created `APPROVAL.md`, the intentionally-fake `WRONG/PATH`
  illustrative text, the hypothetical `canary.md`, and — same file —
  `APPROVAL.md` referenced a second time from the new `STATUS.md`).

## Baseline integrity

All 4 governing baseline hashes re-verified identical before and after
migration (3 docx files + design bundle manifest, byte-for-byte match to
`PROJECT_INDEX.md`'s recorded values). The migration never touched any
governing baseline artifact.

## Validator

`validate_catalog.py` re-run after migration: PASS, 0 errors (unchanged
from pre-migration — the migration didn't touch scenario content, only
its container directory's name).

## Fresh-session restoration proof

See `knowledge/03-Modules/MOD-000/evidence/durability/FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`.
**Corrected note:** this section originally (and incorrectly) cited that
file as already containing a clean proof before it had even been
written. Pass 1 of that proof actually returned `BLOCKED:
SESSION_RESTORE_FAILURE` — it caught this exact document (and BUG-017's
status field) claiming completion ahead of verification. Both were
corrected in response; see that file for the full account, including its
Pass 2 result.

## Result

**BUG-017: structural migration complete, reference validation clean,
baseline integrity confirmed. Fresh-session restoration: Pass 1 BLOCKED
(caught this document's own premature claims — see above and the linked
proof file), corrected, Pass 2 pending/see linked file for outcome.**
BUG-017 remains open until Pass 2 comes back clean — not closed by this
document's own say-so.
