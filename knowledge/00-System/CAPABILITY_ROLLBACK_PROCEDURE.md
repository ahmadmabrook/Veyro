---
doc: CAPABILITY_ROLLBACK_PROCEDURE
status: LIVE
date: 2026-09-13
---

# Capability Rollback / Removal Procedure

Authored for Phase 10 readiness (SCN-MOD000-088 — "Rollback/removal
procedure documented per capability," EIP §4.2 stage 7's
`rollback_target` field). This is the generic procedure every capability
row's `rollback_target` value is executed against; it is not a
per-capability document, since the per-capability specifics already
live in each `CAPABILITY_REGISTRY.md` row's own `rollback_target` cell.

## When this procedure applies

Any time a registered capability (CAP-/SKL-/RULE- id) must stop being
relied upon: it was found unsafe, it regressed, its `next_review_due`
lapsed with no re-evaluation planned, the owner decided to discontinue
it, or a replacement capability supersedes it.

## Procedure

1. **Locate the row.** Find the capability's row in
   `CAPABILITY_REGISTRY.md` and read its `rollback_target` cell — this
   states the exact action to take (e.g. CAP-007's: "Remove the
   `PreToolUse` key from `.claude/settings.json` and start a fresh
   session"). Execute exactly that documented action, not an improvised
   substitute — if the documented action is unclear or no longer
   accurate, that is itself a defect to fix (correct the cell), not a
   reason to guess.

2. **Check for an owner-reserved action.** If the `rollback_target`
   action itself touches an owner-reserved surface (editing
   `.claude/settings.json`, spending money, touching production, real
   member data), the rollback follows the same owner-reserved rule as
   any other action of that class — the session executing the rollback
   does not perform that step unilaterally; it reports
   `BLOCKED: OWNER_APPROVAL_REQUIRED` and names which restriction
   applies, per `.claude/rules/owner-reserved-restrictions.md`.

3. **Update the registry row.** Set `lifecycle_status: REVOKED` (or
   `DEPRECATED` if the capability is being phased out but not
   immediately removed) in the same commit as the rollback action. Do
   not leave a revoked capability's row silently unchanged — a stale
   `ACTIVE` status on a capability that no longer functions is exactly
   the kind of drift this project's own Phase 5-9 history has
   repeatedly found and corrected in other durable files.

4. **Check module bindings.** Search `knowledge/03-Modules/*/evidence/module-capabilities.yaml`
   for any module declaring a dependency on the rolled-back capability
   (`capability_id` field). Per `CAPABILITY_POLICY.md`'s fail-closed
   rule, a module may not depend on anything less than `APPROVED` —
   remove the dependency entry, or replace it with the successor
   capability's id if one exists, in the same commit.

5. **Re-run affected validators.** At minimum `validate_capabilities.py`
   (confirms no module still declares a dependency on a non-`APPROVED`
   capability) and `evidence_integrity_check.py` (confirms no dangling
   evidence-path reference to the rolled-back capability's now-stale
   files). If the rollback affects a Bash-guard-adjacent capability
   (CAP-007's class), also re-run `.claude/security/tests/test_bash_guard.py`.

6. **Record the rollback as durable evidence.** Create a dated file
   named ROLLBACK_&lt;date&gt;.md under the rolled-back capability's own
   evidence folder in knowledge/05-QA/capability-evidence/, stating:
   what was rolled back, why, who/what authorized it (citing an
   `OWN-<NNN>` row in `OWNER_APPROVALS.md` if step 2 applied), what the
   `rollback_target` action actually was, and confirmation the
   validators in step 5 passed afterward. Link this file from the
   registry row's `evidence` cell alongside the original qualification
   evidence — do not overwrite the original evidence, since the
   qualification history remains a legitimate historical record per
   this project's "preserve history" convention.

7. **If a successor capability is being registered in the same action**,
   follow `CAPABILITY_POLICY.md`'s normal 9-stage lifecycle for it from
   stage 1 (Inventory) — a rollback does not exempt a replacement from
   qualification, even if the replacement is "the same thing, newer
   version." Per stage 9 (Re-evaluate), a material version/scope/
   provenance change always triggers a fresh stage 4-5 pass regardless.

## What this procedure deliberately does not cover

- **Automated/scripted rollback execution.** No capability on this
  project to date has a rollback action complex enough to warrant a
  script (every current `rollback_target` cell is a short, manually
  executable instruction — delete a hook registration, fall back to a
  named alternative, revert to `knowledge/`-only operation). Building
  rollback automation for a hypothetical future complex capability
  before one exists would be speculative engineering this project's own
  DC-12 discipline (best practices, no premature abstraction) argues
  against.
- **MOD-001+ product-capability rollback.** This procedure governs
  MOD-000's own control-plane capabilities. A future product module may
  need additional rollback considerations specific to a live product
  surface (e.g. a feature-flagged capability with real user traffic) —
  that is out of MOD-000's scope and would be authored when MOD-001+
  actually introduces such a capability.
