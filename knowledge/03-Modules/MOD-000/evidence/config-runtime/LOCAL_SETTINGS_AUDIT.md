---
doc: LOCAL_SETTINGS_AUDIT
status: LIVE
updated: 2026-09-04
---

# `.claude/settings.local.json` durable audit (SCN-MOD000-054)

This file is intentionally gitignored (`.gitignore:30`) — Git can never review
its contents, so `knowledge/` must be the durable record of what it contains,
per `.claude/rules/knowledge-vault-durability.md`.

## Finding (Phase 5, F5-001)

As of 2026-09-04, before this audit, the file read:

```json
{
  "enabledMcpjsonServers": ["claude-flow"],
  "enableAllProjectMcpServers": true
}
```

`enableAllProjectMcpServers: true` is a standing pre-authorization for *any*
project-scoped MCP server to activate without capability review —
`claude-flow` is not in `CAPABILITY_REGISTRY.md`. SCN-054's original Phase 1
PASS checked only the `permissions` key and missed this. Corrected disposition
recorded in `SCENARIO_CATALOG.md`'s Phase 5 remediation section.

## Fix (2026-09-04)

```json
{
  "enabledMcpjsonServers": [],
  "enableAllProjectMcpServers": false
}
```

Re-verified: no `.mcp.json` file exists in-project (checked via `find`), so no
capability was actually activated through this path — the exposure was
latent (a standing pre-authorization), not an active compromise.

## Ongoing audit obligation

Because this file is gitignored, every session that touches it must update
this document in the same turn, per SCN-054's pass criteria. Current state
(2026-09-04): no MCP servers enabled, `enableAllProjectMcpServers: false`,
no `permissions` key present (cannot widen the tracked permission baseline
either).
