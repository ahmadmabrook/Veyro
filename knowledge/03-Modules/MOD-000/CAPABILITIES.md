---
doc: MOD-000_CAPABILITIES
status: LIVE
updated: 2026-09-05
---

# MOD-000 — Capabilities (per-module manifest)

Appendix D field: "Per-module capability manifest: selected §4.3 profiles,
exact Rules/Skills/tools, CAP/SKL/RULE IDs, missing capability blockers
and qualification evidence."

**§4.3 profiles selected:** none — MOD-000 is control-plane bootstrap, not
a Backend/Admin-Web/Mobile/etc. surface module, so no §4.3 surface-agent
profile applies to it directly.

**Capabilities used, by CAP ID** (full registry: `knowledge/00-System/CAPABILITY_REGISTRY.md`):

| CAP ID | Capability | review_status | Qualification evidence |
|---|---|---|---|
| CAP-001 | Notion MCP | APPROVED | `knowledge/05-QA/capability-evidence/CAP-001/` |
| CAP-002 | TestSprite CLI (offline scope) | APPROVED (offline scope only) | `knowledge/05-QA/capability-evidence/CAP-002/` |
| CAP-003 | `docx` skill | APPROVED (first-party default-trust) | registry entry only |
| CAP-004 | Core harness tools (Bash/Read/Write/Edit) | APPROVED (harness-native) | registry entry only |
| CAP-005 | Browser tools | QUALIFIED (positive test only) | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |
| CAP-006 | iOS Simulator control | APPROVED | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |

**Missing capability blockers:** none currently blocking Phase 1-5 work.
CAP-001/CAP-002's qualification tier is a known, tracked defect (BUG-006),
not a missing-capability blocker.

**Rules/Skills used:** `.claude/rules/owner-reserved-restrictions.md`,
`.claude/rules/knowledge-vault-durability.md`,
`.claude/rules/admin-privileged-console-baseline.md` (binds forward to
MOD-029, not consumed by MOD-000 itself). No project-scoped `.claude/skills/`
exists (none has been needed — BUG-004).
