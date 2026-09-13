---
doc: SKILL_SCOPING_POLICY
status: LIVE
date: 2026-09-13
---

# Skill Scoping Policy — Project-Scoped vs. Nested

Authored for Phase 10 readiness (SCN-MOD000-093 — "Project/nested Skill
policy documented," EIP §21.1 Required outputs). `.claude/skills/` does
not exist on this project yet (BUG-004 — no Skill has been needed so
far); this policy is authored proactively so the decision is governed
when the first one is.

## Definitions

- **Project-scoped Skill**: lives at .claude/skills/&lt;name&gt;/SKILL.md
  inside this repository. Available only to sessions working in this
  repo. Committed to Git, versioned with the rest of `knowledge/`.
- **Nested Skill**: a Skill invoked from within another Skill's own
  execution (a Skill that itself triggers a sub-Skill), or a Skill
  intended for reuse across multiple projects/repos beyond this one.

## When a project-scoped Skill is appropriate

- The task is specific to this project's own structure, conventions, or
  durable state (e.g. "reconcile the canonical scenario matrix against
  Notion" — meaningless outside this repo's own schema).
- The gap was found via `CAPABILITY_POLICY.md`'s stage 1-2 (inventory
  found no existing reusable Skill; the gap is real and specific to
  MOD-000/Veyro).
- No other project would plausibly reuse it as-is.

## When a nested Skill is appropriate

- The capability is genuinely general-purpose (would work unmodified in
  an unrelated project) and is being invoked as a sub-step of a larger,
  project-scoped Skill's own workflow.
- The capability needs to be shared across multiple repos/projects the
  same owner/organization maintains, where duplicating a project-scoped
  copy into each repo would create drift (the same "duplicated fact
  goes stale" problem this project's own Phase 9 restoration proof
  found repeatedly in its own durable files — the same discipline
  applies to Skills).

## Decision procedure

1. Follow `CAPABILITY_POLICY.md`'s normal 9-stage lifecycle in full —
   this policy only resolves the project-scoped-vs-nested question,
   it does not shortcut inventory, evaluation, or qualification.
2. Default to **project-scoped** unless a concrete, named reuse case
   (not a hypothetical one) justifies nesting — per DC-12's discipline
   against premature abstraction, "this might be useful elsewhere
   someday" is not sufficient justification.
3. A nested Skill still gets a `SKL-<NNN>` id and a
   `CAPABILITY_REGISTRY.md` row per `skl-rule-id.schema.yaml`, scoped
   and reviewed identically to a project-scoped one — nesting changes
   where the Skill lives and who else can invoke it, not whether it
   goes through qualification.
4. If a nested Skill's dependency graph could create a cycle with
   another Skill/Rule (this project's own or another project's), that
   is activation-blocking per `CAPABILITY_POLICY.md`'s dependency-cycle
   prohibition — checked explicitly before nesting, since a nested
   Skill's dependencies are less visible than a project-scoped one's.

## Owner-reserved note

Creating a Skill intended for reuse across multiple projects/repos may
itself be a decision with cross-project scope implications. If a
proposed nested Skill would be shared with or affect a repo outside
this one, that crosses into "material architecture/scope change"
territory per `.claude/rules/owner-reserved-restrictions.md` item 4 —
flag it for owner approval rather than deciding unilaterally.
