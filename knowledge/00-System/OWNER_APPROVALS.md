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
| OWN-003 | Accept Sonnet-tier orchestration as the durable operating model for MOD-000 (and future modules): the orchestrating session coordinates/executes and delegates every Opus-reserved judgment call to a fresh-context Opus subagent it spawns; it does not make an architecture/ADR/gate-verdict-class decision unilaterally on its own authority | `MODEL_ROUTING.md`'s new "Orchestrating-session tier vs. delegated-role tier" section; `ADR-004` | 2026-09-06 | `knowledge/04-Decisions/ADR-004-orchestrating-session-model-tier.md`, `knowledge/00-System/MODEL_ROUTING.md`, `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-012-orchestrating-session-unattested-model-tier.md` |

**Two open items currently require an owner decision** but have not yet
received one (corrected 2026-09-06, Phase 7 re-review, RR-6: a prior
version of this file and `BUG-016` both claimed this second item had
already been "routed to the owner" here — it had not; that gap is fixed
now, not silently left):

1. See `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md`
   (BLOCKED: OWNER_APPROVAL_REQUIRED). Will get an `OWN-002` row once
   decided. (Corrected 2026-09-06, Phase 7 SEC-14: this previously also
   said `OWN-001`, colliding with the row above it.)
2. **Design-bundle demo-data question (BUG-016, Phase 7 SEC-10, 2026-09-06):**
   `veyro-product-experience-design/project/veyro-screen.js` and several
   `.dc.html` files in the same frozen, unmodifiable design baseline
   contain 12 email-shaped strings and 6 Jordanian-format phone numbers
   used as UI mockup demo data. Whether any of these correspond to a
   real, reachable mailbox or phone line cannot be determined from repo
   content alone, and this project has no technical means to alter the
   baseline regardless. Is any of this real, and if so, does its
   presence in a frozen, approved design baseline require any action
   beyond the current read-only, no-processing status quo? See
   `knowledge/03-Modules/MOD-000/evidence/security/
   DATA_CLASSIFICATION_AUDIT.md`'s 2026-09-06 correction section for the
   full finding. Will get an `OWN-004` row once decided.

Any session that receives explicit owner approval for an otherwise
owner-reserved action must add a row here (with an `OWN-<NNN>` ID) and a
matching evidence file, in the same commit as the approved action.
