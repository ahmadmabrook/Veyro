---
doc: CAPABILITY_REGISTRY
status: LIVE
updated: 2026-08-31
---

# Capability Registry

Every row here is a capability this project may depend on. `review_status: APPROVED` is required before real (non-drill) use per `CAPABILITY_POLICY.md`. Nothing below is APPROVED yet — MOD-000's qualification drill (positive/negative tests) has not run. This table is the honest current state, not aspirational.

| id | capability | provenance | version | content_hash | scope | review_status | qualified_by | qualified_date | evidence |
|---|---|---|---|---|---|---|---|---|---|
| CAP-001 | Notion MCP (`mcp__notion__*`) | First-party Anthropic-connected MCP, user-authorized connector | live server, tools observed 2026-08-31 | N/A (hosted) | read/write to user's Notion workspace; used for Veyro Engineering Control Plane databases only | APPROVED | veyro-implementer (this session, Sonnet) | 2026-08-31 | `knowledge/04-Capabilities/evidence/CAP-001/{positive_test,negative_test}.md` |
| CAP-002 | TestSprite CLI | Third-party CLI, installed on host (`~/.nvm/.../bin/testsprite`) | 0.8.0 | N/A (external binary, not project-controlled) | **offline plan authoring/validation only** (`test scaffold`, `test lint`); live cloud execution (`test run` etc.) explicitly OUT of scope — consumes pre-existing paid credit balance, needs owner approval first | APPROVED (offline scope only) | veyro-test-author (this session, Sonnet) | 2026-08-31 | `knowledge/04-Capabilities/evidence/CAP-002/{positive_test,negative_test,SCOPE_NOTE}.md` |
| CAP-003 | `docx` skill | Anthropic first-party public skill (`/mnt/skills/public/docx`) | as shipped in this environment | not independently hashed (first-party, trusted by default) | read/create/edit .docx files | APPROVED (first-party default-trust) | bootstrap session | 2026-08-31 | used to read baseline docx during MOD-000 bootstrap |
| CAP-004 | Bash/Read/Write/Edit (core harness tools) | First-party Claude Code harness | N/A | N/A | full project filesystem + shell | APPROVED (harness-native, out of scope for this policy) | N/A | N/A | N/A |

## Pending qualification (this MOD-000 chunk registers; a later chunk qualifies)

- CAP-001 Notion MCP: about to be used to create the 9 control-plane databases. Positive test = database created + one real row written + read back. Negative test = attempt write with malformed/out-of-scope payload, confirm rejection or safe no-op, not silent corruption. Scope is fixed to the 9 named databases only — no other Notion content is to be touched.
- CAP-002 TestSprite: capability discovery/qualification is its own later MOD-000 chunk (manual QA control-path drill). Not qualified in this chunk.

## Rejected / revoked

(none yet)

## Fail-closed reminder

No module task may depend on a capability whose `review_status` is not `APPROVED`, except the qualification drill itself. See `CAPABILITY_POLICY.md`.
