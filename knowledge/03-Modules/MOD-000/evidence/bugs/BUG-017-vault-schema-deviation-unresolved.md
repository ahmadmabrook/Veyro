---
doc: BUG-017
status: CLOSED (2026-09-05) — owner decided (migrate, don't ratify); migration executed; three independent fresh-context restoration passes run (Pass 1 BLOCKED, Pass 2 BLOCKED on a different file, Pass 3 clean); see note below for the full honest account
found_date: 2026-09-04
found_by: Phase 5 independent review (F5-012)
severity: P1
---

# BUG-017: `knowledge/` vault schema deviates from EIP Appendix D — restructure-or-ratify decision needed

## Update 2026-09-05 — decided, migration executed, closure pending re-verification

The owner explicitly decided: migrate to Appendix D, do not ratify the
deviation. Full decision + path map: `knowledge/04-Decisions/ADR-002-vault-migration-to-eip-appendix-d.md`.
Execution log: `knowledge/03-Modules/MOD-000/evidence/durability/MIGRATION_EVIDENCE_2026-09-05.md`.

**This bug is not being closed yet, on purpose.** A fresh-context
restoration proof (run as part of this same remediation, per the standing
"don't self-certify" discipline) found a real problem: this session had
started writing `MIGRATION_EVIDENCE_2026-09-05.md` as if the migration
were already fully verified — including a sentence claiming this exact
bug file had been updated to CLOSED (it hadn't) and a citation to a
fresh-session-restoration-proof file that didn't exist yet at the time it
was cited. The fresh session correctly refused to paper over the
contradiction and reported `BLOCKED: SESSION_RESTORE_FAILURE`. That
finding is itself the honest, correct outcome of the exercise — see
`knowledge/03-Modules/MOD-000/evidence/durability/FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`
for the full account, kept as the real record of what happened, not
smoothed over.

**Remediation in response:** every file the fresh session flagged as
inconsistent (`CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
`knowledge/03-Modules/MOD-000/STATUS.md`, this file, and — caught only by
a subsequent Pass 2 — `ADR-002`) was corrected. **Closed now, honestly,
after three independent fresh-context restoration passes, not after
one:** Pass 1 found the original 5-file contradiction (BLOCKED). Pass 2
confirmed those 5 were fixed but found a 6th file (`ADR-002`) still
claiming completion (BLOCKED). Pass 3, after `ADR-002` was also
corrected, confirmed all six files now genuinely agree and reported no
contradiction. Full account: `knowledge/03-Modules/MOD-000/evidence/durability/FRESH_SESSION_RESTORE_PROOF_2026-09-05.md`.
This bug's closure is not this session's own say-so — it rests on Pass
3's independent confirmation.

## Original finding (2026-09-04)

## What is wrong

The actual vault structure (`01-Modules/`, `03-ExternalGates/`,
`04-Capabilities/`, an ad hoc `evidence/` tree) does not match EIP
Appendix D's specified schema (`03-Modules/`, per-module STATUS/
REQUIREMENTS/etc. files, `05-QA/` index set, `01-Product/`,
`02-Architecture/`, `04-Decisions/`, `06-Sessions/`, `07-Releases/`). Full
detail and rationale: `knowledge/04-Decisions/ADR-001-vault-schema-deviation-from-eip-appendix-d.md`.

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
decision): `knowledge/04-Decisions/` (ADR mechanism) and
`knowledge/00-System/{EXTERNAL_GATES,OWNER_APPROVALS}.md` created —
these were genuinely just-missing files, not part of the restructure
question.

## Affected

SCN-005, SCN-007, SCN-047, SCN-062, SCN-065, SCN-066, the §18 certificate
Obsidian-currency field. **Blocks MOD-000 certification: YES** until (a) or
(b) above is decided and executed.
