---
doc: MOD-000_CAPABILITIES
status: LIVE
updated: 2026-09-12 (Phase 9 restoration proof re-review, Gatekeeper P1-3 — this file had gone stale since 2026-09-05: omitted CAP-007 entirely, understated CAP-005, and described closed BUG-006 as an open defect)
---

# MOD-000 — Capabilities (per-module manifest)

Appendix D field: "Per-module capability manifest: selected §4.3 profiles,
exact Rules/Skills/tools, CAP/SKL/RULE IDs, missing capability blockers
and qualification evidence."

**§4.3 profiles selected:** none — MOD-000 is control-plane bootstrap, not
a Backend/Admin-Web/Mobile/etc. surface module, so no §4.3 surface-agent
profile applies to it directly.

**Capabilities used, by CAP ID** (full registry: `knowledge/00-System/CAPABILITY_REGISTRY.md`; `validate_capabilities.py` re-confirms all 7 APPROVED live on every run):

| CAP ID | Capability | review_status | Qualification evidence |
|---|---|---|---|
| CAP-001 | Notion MCP | APPROVED, scope de-rated, binding caveats (2026-09-05) | `knowledge/05-QA/capability-evidence/CAP-001/`, `.claude/rules/notion-mcp-scope-discipline.md` |
| CAP-002 | TestSprite CLI (offline scope) | APPROVED (offline scope only) | `knowledge/05-QA/capability-evidence/CAP-002/` |
| CAP-003 | `docx` skill | APPROVED (first-party default-trust) | registry entry only |
| CAP-004 | Core harness tools (Bash/Read/Write/Edit) | APPROVED (harness-native) | registry entry only |
| CAP-005 | Browser tools | **APPROVED** (2026-09-05, distinct fresh-context Opus review, public/unauthenticated/stateless-endpoint scope) | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md`, `evidence/bugs/BUG-009-*.md` |
| CAP-006 | iOS Simulator control | APPROVED (2026-09-05, same review, stock-Apple-apps-only scope) | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |
| CAP-007 | PreToolUse Bash security guard (`bash_guard.py`) | **APPROVED, ACTIVE** (2026-09-08, fourth independent Opus review + owner live-activation verification) | `evidence/security/BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`, `evidence/security/BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md` |

**Missing capability blockers:** none currently blocking Phase 1-9 work.
CAP-001's qualification tier is CLOSED (BUG-006, 2026-09-05) — the
residual connector-scope-vs-policy deviation is tracked separately,
non-blocking, as BUG-010/`ADR-003` (owner decision pending).

**Rules/Skills used:** `.claude/rules/owner-reserved-restrictions.md`,
`.claude/rules/knowledge-vault-durability.md`,
`.claude/rules/notion-mcp-scope-discipline.md` (CAP-001's binding
compensating control, added 2026-09-05),
`.claude/rules/admin-privileged-console-baseline.md` (binds forward to
MOD-029, not consumed by MOD-000 itself). No project-scoped `.claude/skills/`
exists (none has been needed — BUG-004).
