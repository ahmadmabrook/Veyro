---
doc: BUG-030
status: CLOSED
module: MOD-001
severity: P0 (blocked all routing from Sonnet tier to veyro-critical-engineer; never blocked non-routing MOD-001 planning)
opened: 2026-09-14
closed: 2026-09-14
---

# BUG-030 — Cannot edit *existing* `.claude/agents/*.md` files either (routing integration gap)

## Finding

Independent fresh-context review of `veyro-critical-engineer.md`
(dispatched to `veyro-security-reviewer`, Opus) found the definition
itself sound but identified a real, separate defect: **nothing actually
routes to the new role.** `.claude/agents/veyro-implementer.md` line 12
enumerates its own escalation targets ("veyro-lead for architecture;
veyro-security-reviewer or veyro-performance-reviewer for assurance;
veyro-code-reviewer for review; veyro-gatekeeper only for final
certification") and does not name `veyro-critical-engineer`. A Sonnet
`veyro-implementer` session that picks up GOV-01-R02's tenant-isolation/
RLS harness is directed by its own charter to escalate to `veyro-lead`
— exactly the fallback `ADR-005` Decision 1 examined and rejected
("Stretching it to cover critical *implementation* is the same category
error"). `veyro-lead.md`'s own description also still calls itself the
"critical-engineering-decision role" (a lesser, P2-severity instance of
the same drift).

This is `BUG-029`'s exact capability-gap species (`.claude/agents/**` is
Edit/Write-denied in `.claude/settings.json`), but for **existing**
files rather than new ones — `BUG-029`'s closure was correctly scoped to
file *creation* only (see that bug's own "Non-goals" section) and does
not cover this. Confirmed by the same protection this session already
found: the deny rule is a directory glob (`Edit(.claude/agents/**)`,
`Write(.claude/agents/**)`), so it applies uniformly to new and existing
files.

## Why this is P0, not P1

Without this fix, the routing-qualification drill required by `ADR-005`
binding condition 3 cannot pass: dispatching a critical-slice-shaped
task to `veyro-implementer` (the correct subject of the drill per
`SCN-MOD000-080`'s own pattern — see the independent review's P0-2
finding) will not escalate to `veyro-critical-engineer`, because nothing
in `veyro-implementer`'s own charter tells it to. The role exists but is
unreachable through normal routing. `MODEL_ROUTING.md`'s "REGISTERED"
claim is therefore true of the file's existence but not yet true of the
routing behavior it exists to provide.

## Required fix

Two edits to existing `.claude/agents/*.md` files, content prepared
below for the owner to apply directly (same pattern as `BUG-028`/
`BUG-029`):

**`.claude/agents/veyro-implementer.md` line 12** — change:

> If a task turns out to be architecture-level, security/performance-sensitive, or a critical engineering decision, stop and say it needs the matching Opus assurance role (veyro-lead for architecture; veyro-security-reviewer or veyro-performance-reviewer for assurance; veyro-code-reviewer for review; veyro-gatekeeper only for final certification) rather than proceeding — do not silently absorb assurance-tier work, and do not route everything to veyro-gatekeeper specifically.

to:

> If a task turns out to be architecture-level, security/performance-sensitive, or a critical engineering decision, stop and say it needs the matching Opus assurance role (veyro-lead for architecture; veyro-security-reviewer or veyro-performance-reviewer for assurance; veyro-code-reviewer for review; veyro-gatekeeper only for final certification) rather than proceeding — do not silently absorb assurance-tier work, and do not route everything to veyro-gatekeeper specifically. If a task is a registered critical implementation slice (currently, per ADR-005: MOD-001's tenant-isolation/RLS test harness, its authentication negative-credential fixture pattern, or the RLS-lint/permission-lint architecture gates — see knowledge/00-System/MODEL_ROUTING.md's critical-slice row for the current, authoritative list), stop and say it needs veyro-critical-engineer (Opus), not veyro-lead.

**`.claude/agents/veyro-lead.md`** — the `description` field's phrase
"Architecture and critical-engineering-decision role" should be
narrowed to avoid implying `veyro-lead` covers critical *implementation*
now that `veyro-critical-engineer` is registered — suggested rewording:
"Architecture and critical-engineering-*decision* role (design/ADR-level
only — critical-slice *implementation* routes to veyro-critical-engineer
once a slice is registered for the active module)."

## Status

**CLOSED (2026-09-14).** Owner applied both edits directly to
`.claude/agents/veyro-implementer.md` and `.claude/agents/veyro-lead.md`
outside this guarded session (commit `9f5efd4`). This session
independently verified, not merely trusted:

1. Read both files back and confirmed byte-for-byte match against the
   exact patch text handed to the owner.
2. `git log`/`git status` confirm the commit exists and local HEAD ==
   `origin/main`.
3. Ran the corrected routing drill — three real dispatches, all to
   `veyro-implementer` (the correct subject this time): a genuine
   ADR-005 critical-slice task correctly escalated to
   `veyro-critical-engineer`; a genuine routine task was correctly
   retained by `veyro-implementer` itself; a genuine architecture/scope
   task correctly escalated to `veyro-lead`. All three responses
   required real task classification, not charter-echo alone — see
   `knowledge/03-Modules/MOD-001/evidence/model-routing/ROUTING_DRILL_2026-09-14.md`'s
   "Corrected drill" section for full detail, including file-write
   claims verified via `git status` rather than self-report (correcting
   the first invalid attempt's own P1-3 finding).

The role now exists (`BUG-029`) AND is genuinely reachable through
normal routing (`BUG-030`). Both binding-condition gaps ADR-005's
Decision 1 depended on are closed.

## Non-goals

This bug does not authorize, and no session should attempt, weakening
`.claude/settings.json`'s `.claude/agents/**` protection. The fix is two
owner-applied content edits, not a guard change.
