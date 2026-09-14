---
doc: BUG-029
status: OPEN — OWNER ACTION NEEDED
module: MOD-001
severity: P1 (blocks ADR-005 Decision 1/2's binding pre-DoR conditions; does not block the rest of MOD-001 planning)
opened: 2026-09-14
---

# BUG-029 — No guard-compliant path to create new `.claude/agents/*.md` files

## Finding

ADR-005 (`knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`)
requires registering three new agents before MOD-001's Definition of
Ready: `veyro-critical-engineer` (Opus, Decision 1) and
`veyro-infra-sre-engineer`/`veyro-backend-engineer` (Sonnet, Decision
2). Both the orchestrating session (this one) and the `veyro-lead`
subagent dispatched to decide ADR-005 attempted to write these files
and were denied:

- `veyro-lead`'s dispatch had only `Read`/`Bash` tools (no `Write`/`Edit`
  in its grant for this invocation), and every Bash-based write path
  (`printf`, bare `python3`, heredoc/redirection) is denied by
  `.claude/security/bash_guard.py`'s composition ban — it correctly
  refused to fabricate a workaround and handed back the full ADR text
  for a session that could write it.
- This orchestrating session has `Write`/`Edit` tools, but
  `.claude/settings.json`'s permission `deny` list contains
  `Edit(.claude/agents/**)` and `Write(.claude/agents/**)` (confirmed by
  direct `grep`, lines 137-138) — the same protection class as
  `.claude/security/**`. A direct `Write` attempt for
  `.claude/agents/veyro-critical-engineer.md` was denied:
  `File is in a directory that is denied by your permission settings.`

This is the same capability-gap species as `BUG-028` (no guard-compliant
docx read path), applied to a different protected directory. It is a
correct, intentional protection — agent definitions are exactly the kind
of security-relevant, tamper-sensitive file this project's `.claude/`
protection scheme exists to guard, and no session should be able to
silently create or alter its own governing agent roster.

## Decision

Per the `BUG-028` precedent, this is routed to the owner rather than
worked around. The three files' exact required content are prepared
below (or in this session's own commit, once the owner applies them) for
the owner to create directly, outside this guarded session.

**File 1: `.claude/agents/veyro-critical-engineer.md`**
**File 2: `.claude/agents/veyro-infra-sre-engineer.md`**
**File 3: `.claude/agents/veyro-backend-engineer.md`**

Exact content for all three: see this session's own chat transcript (the
content was drafted and presented to the owner directly, since it could
not be committed to a scratch file path the owner could easily diff
against — a plain scratchpad file works fine for this, unlike the
docx-mirror case, which is why the owner may instead be handed the
content directly rather than a shell command to run).

## Status

**OPEN — OWNER ACTION NEEDED.** Not resolved until all three files exist
under `.claude/agents/` and this session (or a continuation) confirms
`Read` access to them and proceeds with ADR-005's remaining binding
conditions (independent review of the critical-engineer definition,
routing-drill re-run, MR evidence, `MODEL_ROUTING.md` update).

## Non-goals

This bug does not authorize, and no session should attempt, editing
`.claude/settings.json` to remove or narrow the `.claude/agents/**` deny
rule — that protection is correct and should stay in force. The fix is
an owner action outside the guard, not a guard change.
