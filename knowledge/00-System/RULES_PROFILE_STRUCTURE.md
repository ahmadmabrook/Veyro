---
doc: RULES_PROFILE_STRUCTURE
status: LIVE
date: 2026-09-13
---

# `.claude/rules/` Profile Structure

Authored for Phase 10 readiness (SCN-MOD000-094 — "Initial `.claude/rules`
profile structure exists," EIP §21.1 Required outputs + the special rule
that a missing mandatory surface/profile rule causes `BLOCKED`, not
silent proceeding). This is the formal mapping of surface → required
rule set that a flat file listing does not provide on its own.

## Profile table

| Surface | Required rule(s) | Why |
|---|---|---|
| **All surfaces (every session, every module)** | `owner-reserved-restrictions.md` | Absolute, no-exception owner-reserved boundaries (no spend, no real member data, no production deploy, no material scope change) apply regardless of what the session is doing. |
| **All surfaces** | `knowledge-vault-durability.md` | Durable-state-authority rule (Git/`knowledge/` wins over Notion) applies to every session touching durable state. |
| **Notion MCP usage (`mcp__notion__*` tool calls)** | `notion-mcp-scope-discipline.md` | CAP-001's binding compensating control — required specifically because CAP-001 has no technical scope enforcement (ADR-003/BUG-010); a session using Notion MCP without this rule loaded would have no discipline substituting for the missing technical boundary. |
| **MOD-029 admin/privileged-console work (forward-binding, no such surface exists yet)** | `admin-privileged-console-baseline.md` | Binds forward to whichever module eventually builds an internal admin/support console; not consumed by any module's current work (MOD-000 has no such surface), but must be loaded/consulted the moment such a module starts, per the special rule below. |

## The special rule (missing mandatory profile → BLOCKED)

If a session's current task touches a surface named in the table above
and the corresponding rule is not present/loadable, the session must
report `BLOCKED: OWNER_APPROVAL_REQUIRED` or `BLOCKED: CAPABILITY_GAP`
(whichever fits) rather than proceeding without it. This has real
supporting evidence already: BUG-004 itself is an instance of a session
correctly noting a missing capability (`.claude/skills/`) rather than
fabricating one, and the Notion-scope bounded re-test (BUG-006) is an
instance of a session correctly identifying that a technical control was
missing and that the compensating rule was the only thing standing in
for it — the detection half of this special rule has been exercised in
practice, not just declared.

## How this table is maintained

When a new `.claude/rules/*.md` file is authored (per DC-20's automatic
path-scoped Rule synthesis, or a `RULE-<NNN>` registration per
`skl-rule-id.schema.yaml`), add a row here in the same commit, naming
the surface(s) it governs. When a new module surface is introduced
(e.g. MOD-001's first product surface), check this table for any
existing rule that should bind to it (the way `admin-privileged-console-baseline.md`
already binds forward to MOD-029) before assuming no rule applies.

## Current gap, honestly disclosed

This table's "detection" half (sessions correctly reporting BLOCKED when
a needed rule is genuinely absent) has real supporting evidence, cited
above. The "structure" half — this table existing at all as a formal
surface→rule mapping, rather than four flat files a session must infer
relevance from — did not exist before this document. Both halves are
now satisfied by this document's existence plus the pre-existing
detection evidence; no further action is required to close this gap for
Phase 10.
