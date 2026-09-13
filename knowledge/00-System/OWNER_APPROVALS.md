---
doc: OWNER_APPROVALS
status: LIVE
updated: 2026-09-13 (Phase 10, OWN-002 recorded — owner adjudicated the EIP front-matter-vs-§21.1 self-contradiction, closing EXT-01)
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
| OWN-002 | Adjudicate the EIP v1.4.1 front-matter-vs-§21.1 self-contradiction (EXT-01) in favor of the front matter: the governing EIP (`VEYRO-EIP-1.4.1-20260827`) is treated as fully approved and final, exactly as its own cover page and Document Control table state. The §21.1 body text's "this candidate... cannot be promoted until independent re-audit closure is recorded" language is adjudicated to be a drafting inconsistency in the source document itself, not a live blocker on this project — no actual re-audit-closure record exists or is required beyond this adjudication. This closes EXT-01. | Applies solely to interpreting the EIP's own internal self-contradiction; does not alter, rename, or regenerate any governing baseline artifact | 2026-09-13 | `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md`, `knowledge/00-System/EXTERNAL_GATES.md` |

**One open item currently requires an owner decision** but has not yet
received one:

1. **Design-bundle demo-data question (BUG-016, Phase 7 SEC-10, 2026-09-06):**
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
   full finding. Will get an `OWN-004` row once decided. (Renumbered
   2026-09-13: this was item 2 until OWN-002 was recorded above, closing
   item 1.)

Any session that receives explicit owner approval for an otherwise
owner-reserved action must add a row here (with an `OWN-<NNN>` ID) and a
matching evidence file, in the same commit as the approved action.
