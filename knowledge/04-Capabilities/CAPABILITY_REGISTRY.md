---
doc: CAPABILITY_REGISTRY
status: LIVE
updated: 2026-08-31
---

# Capability Registry

Every row here is a capability this project may depend on. `review_status: APPROVED` is required before real (non-drill) use per `CAPABILITY_POLICY.md`. This table is the honest current state, not aspirational.

**Corrected 2026-09-04 (Phase 5, F5-003):** the sentence previously here ("Nothing below is APPROVED yet") directly contradicted the table, which has shown all four rows `APPROVED` since 2026-08-31 — a stale artifact from an early drafting pass, never updated. Separately, and more substantively: `CAPABILITY_POLICY.md` line 48 requires qualification runs to route to Opus ("Qualification runs... are assurance-tier work -> route to Opus per `DEVELOPMENT_CONSTITUTION.md`"), but CAP-001 and CAP-002's `qualified_by` fields below (honestly, not hidden) show Sonnet-tier agents. This is a real policy violation, filed as **BUG-006** — see `evidence/bugs/BUG-006-capability-qualification-ran-on-sonnet.md`. Not fixed in this pass (requires either re-running qualification through a properly tooled Opus-tier role, which does not yet exist as a registered agent, or an owner-recorded deviation) — tracked, non-blocking for this specific edit, blocking for Phase 10 certification.

| id | capability | provenance | version | content_hash | scope | review_status | qualified_by | qualified_date | evidence |
|---|---|---|---|---|---|---|---|---|---|
| CAP-001 | Notion MCP (`mcp__notion__*`) | First-party Anthropic-connected MCP, user-authorized connector | live server, tools observed 2026-08-31 | N/A (hosted) | read/write to user's Notion workspace; used for Veyro Engineering Control Plane databases only | APPROVED | veyro-implementer (this session, Sonnet) | 2026-08-31 | `knowledge/04-Capabilities/evidence/CAP-001/{positive_test,negative_test}.md` |
| CAP-002 | TestSprite CLI | Third-party CLI, installed on host (`~/.nvm/.../bin/testsprite`) | 0.8.0 | N/A (external binary, not project-controlled) | **offline plan authoring/validation only** (`test scaffold`, `test lint`); live cloud execution (`test run` etc.) explicitly OUT of scope — consumes pre-existing paid credit balance, needs owner approval first | APPROVED (offline scope only) | veyro-test-author (this session, Sonnet) | 2026-08-31 | `knowledge/04-Capabilities/evidence/CAP-002/{positive_test,negative_test,SCOPE_NOTE}.md` |
| CAP-003 | `docx` skill | Anthropic first-party public skill (`/mnt/skills/public/docx`) | as shipped in this environment | not independently hashed (first-party, trusted by default) | read/create/edit .docx files | APPROVED (first-party default-trust) | bootstrap session | 2026-08-31 | used to read baseline docx during MOD-000 bootstrap |
| CAP-004 | Bash/Read/Write/Edit (core harness tools) | First-party Claude Code harness | N/A | N/A | full project filesystem + shell | APPROVED (harness-native, out of scope for this policy) | N/A | N/A | N/A |
| CAP-005 | Browser tools (`mcp__Claude_Browser__*`) | First-party Claude Code harness browser pane | as shipped in this environment | N/A (harness-native) | navigate/read/interact with pages for manual-QA evidence gathering | QUALIFIED (positive test real: filled + submitted a real form across 5 control types, server echoed all values back; no negative/malformed-input test yet run — not APPROVED until one exists) | veyro-manual-qa (fresh context, **Opus**) | 2026-09-04 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |
| CAP-006 | iOS Simulator control (`mcp__Claude_Code_iOS_Simulator__*`) | First-party Claude Code harness simulator bridge | as shipped in this environment | N/A (harness-native) | boot/attach/interact with iOS Simulator for manual-QA evidence gathering | APPROVED (positive: full interactive lifecycle with PID-verified background/foreground; negative: an invalid deep-link scheme correctly failed distinctly from a valid one — exit 115 vs exit 0) | veyro-manual-qa (fresh context, **Opus**) | 2026-09-04 | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |

## Qualification history (corrected 2026-09-04 — this section was stale, described a state from before qualification actually ran)

- CAP-001 Notion MCP: qualified 2026-08-31 (positive: database created + row written + read back; negative: malformed/out-of-scope write rejected). See `evidence/CAP-001/`.
- CAP-002 TestSprite: qualified 2026-08-31, offline scope only (positive: scaffold + lint; negative: malformed lint). See `evidence/CAP-002/`.
- Both qualifications ran on Sonnet-tier agents, which is the open policy violation tracked as **BUG-006** (see note above) — not yet remediated.

## Rejected / revoked

(none yet)

## Fail-closed reminder

No module task may depend on a capability whose `review_status` is not `APPROVED`, except the qualification drill itself. See `CAPABILITY_POLICY.md`.
