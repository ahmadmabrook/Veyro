---
doc: OWNER_APPROVALS
status: LIVE
updated: 2026-09-28 (OWN-006 recorded — owner authorized retiring CAP-007's Bash guard enforcement for local dev friction, backfilled after commit `058ed27` shipped without a same-commit row, ADR-007)
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
| OWN-002 | Adjudicate the EIP v1.4.1 front-matter-vs-§21.1 self-contradiction (EXT-01) in favor of the front matter: the governing EIP (`VEYRO-EIP-1.4.1-20260827`) is treated as fully approved and final, exactly as its own cover page and Document Control table state. The §21.1 body text's "this candidate... cannot be promoted until independent re-audit closure is recorded" language is adjudicated to be a drafting inconsistency in the source document itself, not a live blocker on this project — no actual re-audit-closure record exists or is required beyond this adjudication. This closes EXT-01. | Applies solely to interpreting the EIP's own internal self-contradiction; does not alter, rename, or regenerate any governing baseline artifact | 2026-09-13 | `knowledge/00-System/external-gates-evidence/EIP_STATUS_CONTRADICTION.md`, `knowledge/00-System/EXTERNAL_GATES.md` |
| OWN-003 | Accept Sonnet-tier orchestration as the durable operating model for MOD-000 (and future modules): the orchestrating session coordinates/executes and delegates every Opus-reserved judgment call to a fresh-context Opus subagent it spawns; it does not make an architecture/ADR/gate-verdict-class decision unilaterally on its own authority | `MODEL_ROUTING.md`'s new "Orchestrating-session tier vs. delegated-role tier" section; `ADR-004` | 2026-09-06 | `knowledge/04-Decisions/ADR-004-orchestrating-session-model-tier.md`, `knowledge/00-System/MODEL_ROUTING.md`, `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-012-orchestrating-session-unattested-model-tier.md` |
| OWN-005 | Confirm the repeated rule requiring MOD-001 to obtain a completely clean full independent Scenario Review round after every same-session remediation was never intended to create an unbounded review loop, and authorize replacing it with a bounded Convergence Gate for MOD-001's remaining planning-review cycle (and, absent a module-specific override, future modules): P0/P1 standards unchanged, independent fresh-context assurance remains mandatory, a real source-backed present planning defect that materially prevents safe/correct implementation from starting remains blocking, explicitly governed implementation-time deferred work is not a Ready blocker merely for being unimplemented, and P2/Editorial/cleanup/optional-hardening/documentation items do not trigger another full planning-review cycle unless an authoritative governing source explicitly makes that item a Ready condition. Does not replace later Code Review, Manual QA, Security Review, Performance/Load Review, Gatekeeper certification, cumulative regression, or formal module approval. | Applies to MOD-001's planning-review stopping rule only; does not alter any governing baseline artifact, does not lower any technical acceptance criterion, does not declare MOD-001 Ready, does not authorize Scenario Review Round 17 or implementation | 2026-09-19 | `knowledge/04-Decisions/ADR-006-mod001-scenario-review-bounded-convergence-gate.md`, `knowledge/03-Modules/MOD-001/STATUS.md`, `knowledge/03-Modules/MOD-001/SCENARIOS.md` §5 |
| OWN-006 | Retire CAP-007's Bash `PreToolUse` guard enforcement (`.claude/security/bash_guard.py` reduced to an inert, unregistered stub; `.claude/settings.json` permissions narrowed to `Bash(*)` allow / empty deny / `defaultMode: bypassPermissions`) in favor of unrestricted local Bash execution for routine development, removing the recurring allowlist-extension friction that kept `BUG-036` open across 5 rounds. Module certification gates (Scenario Review, Code Review, Manual QA, Security/Performance Review, Gatekeeper), WIP=1, and the 4 owner-reserved absolute restrictions (no prod deploy, no paid spend, no real member data, no destructive remote git / workspace-external actions) are explicitly NOT altered by this decision. | `.claude/security/bash_guard.py`, `.claude/settings.json` permissions block; no other file. Action itself executed in commit `058ed27` (2026-09-28) without a same-commit row — this row backfills that gap the same day it was caught, per explicit owner confirmation to log and continue rather than revert. | 2026-09-28 | `knowledge/04-Decisions/ADR-007-autonomous-development-mode-cap007-retirement.md`, commit `058ed27f8fb3fec0886a2cd4caa115c13ef42d21` |

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
