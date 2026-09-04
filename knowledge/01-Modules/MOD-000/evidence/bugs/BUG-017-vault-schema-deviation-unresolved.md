---
doc: BUG-017
status: OPEN — requires owner decision, not a same-turn code fix
found_date: 2026-09-04
found_by: Phase 5 independent review (F5-012)
severity: P1
---

# BUG-017: `knowledge/` vault schema deviates from EIP Appendix D — restructure-or-ratify decision needed

## What is wrong

The actual vault structure (`01-Modules/`, `03-ExternalGates/`,
`04-Capabilities/`, an ad hoc `evidence/` tree) does not match EIP
Appendix D's specified schema (`03-Modules/`, per-module STATUS/
REQUIREMENTS/etc. files, `05-QA/` index set, `01-Product/`,
`02-Architecture/`, `04-Decisions/`, `06-Sessions/`, `07-Releases/`). Full
detail and rationale: `knowledge/02-Decisions/ADR-001-vault-schema-deviation-from-eip-appendix-d.md`.

## Why this is filed as a bug rather than just fixed

A full mechanical restructure touches nearly every durable file and every
cross-reference to it — a large, high-blast-radius change that is itself
arguably a material architecture change under
`.claude/rules/owner-reserved-restrictions.md` item 4. Two legitimate
resolutions exist (physically restructure to match Appendix D, or formally
amend the project's own governing docs to ratify the actual structure as
the accepted deviation) and choosing between them is not a call an agent
should make unilaterally mid-review.

## Remediation required

Owner or `veyro-lead` (Opus, architecture-tier decision) to choose:
(a) restructure the vault to match Appendix D, executed as its own
dedicated, carefully-tested chunk (not a drive-by edit — the
evidence-integrity checker and dozens of cross-references would need
updating in lockstep); or
(b) amend `CLAUDE.md`/`SESSION_BOOTSTRAP.md` to formally declare the
current structure the project's permanent, ratified deviation from
Appendix D, closing the gap by documentation rather than by moving files.

Partial mitigation already applied same-chunk (does not require this
decision): `knowledge/02-Decisions/` (ADR mechanism) and
`knowledge/00-System/{EXTERNAL_GATES,OWNER_APPROVALS}.md` created —
these were genuinely just-missing files, not part of the restructure
question.

## Affected

SCN-005, SCN-007, SCN-047, SCN-062, SCN-065, SCN-066, the §18 certificate
Obsidian-currency field. **Blocks MOD-000 certification: YES** until (a) or
(b) above is decided and executed.
