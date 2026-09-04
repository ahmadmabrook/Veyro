---
doc: OWNER_APPROVALS
status: LIVE
updated: 2026-09-04 (created, Phase 5 F5-012)
---

# Owner Approvals (index)

EIP Appendix D-named durable file (`OWN-<NNN>` records). Created 2026-09-04
during Phase 5 remediation — did not exist before, a real gap (finding
F5-012). **Corrected 2026-09-05:** the sentence above ("zero owner-approval actions
to date") was accurate through Phase 4 but went stale — a real
DC-16(d)-class decision (material architecture change) was made and
executed 2026-09-05 without a row logged here, a real gap an independent
fresh-session restoration check caught. Fixed same day, see OWN-001
below. Every owner-reserved-restriction *refusal* drill (Phase 3) still
correctly has nothing to log here — those tested that no exception was
granted, which is a different thing from an actual approval.

| OWN ID | Action approved | Scope | Date | Evidence |
|---|---|---|---|---|
| OWN-001 | Migrate the `knowledge/` vault to match EIP Appendix D literally, rather than ratify the existing deviation (BUG-017) | The full path-migration map in `ADR-002`; no governing baseline artifact | 2026-09-05 | `knowledge/04-Decisions/ADR-002-vault-migration-to-eip-appendix-d.md`, `knowledge/03-Modules/MOD-000/evidence/durability/MIGRATION_EVIDENCE_2026-09-05.md` |

One open item currently requires an owner decision but has not yet
received one — see `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md`
(BLOCKED: OWNER_APPROVAL_REQUIRED). It will get an `OWN-001` row here once
the owner records a decision.

Any session that receives explicit owner approval for an otherwise
owner-reserved action must add a row here (with an `OWN-<NNN>` ID) and a
matching evidence file, in the same commit as the approved action.
