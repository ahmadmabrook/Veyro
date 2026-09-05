---
doc: CAPABILITY_REGISTRY
status: LIVE
updated: 2026-09-05 (Phase 5, BUG-006 independent Opus review — see additions below)
---

# Capability Registry

Every row here is a capability this project may depend on. `review_status: APPROVED` requires both `qualified_by` (who ran the tests, may be Sonnet) AND `approved_by` (the Opus assurance role that independently reviewed the evidence and made the final call) populated — a row with only `qualified_by` is at most `QUALIFIED`. This table is the honest current state, not aspirational.

**2026-09-05 update:** `veyro-security-reviewer` (Opus, fresh context) independently reviewed CAP-001 and CAP-002's existing qualification evidence per the corrected model in `CAPABILITY_POLICY.md`. Verdicts below. Full reasoning: `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-006-capability-qualification-ran-on-sonnet.md`.

| id | capability | provenance | version | content_hash | scope | review_status | qualified_by | qualified_date | approved_by | approved_date | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CAP-001 | Notion MCP (`mcp__notion__*`) | **Third-party** hosted MCP (Notion's own server), reached via a user-authorized connector — corrected 2026-09-05, was mislabeled "First-party Anthropic-connected" | live server, tools observed 2026-08-31 | N/A (hosted) | **Intended** use: the Veyro Engineering Control Plane page tree (9 named databases) only. **Confirmed 2026-09-05, not just "unconfirmed": there is no technical page-tree restriction.** The connector is authorized against the entire workspace (`notion-fetch id="self"`), and a direct out-of-scope write (no `parent` specified) succeeded with no permission error — see `evidence/security/NOTION_SCOPE_AUDIT.md` and `knowledge/05-QA/capability-evidence/CAP-001/BOUNDED_RETEST_2026-09-05.md`. "Scope" here is a project-convention boundary this session enforces by discipline, not one Notion's own permission grant enforces. | **QUALIFIED, not APPROVED** (downgraded 2026-09-05; bounded re-test executed 2026-09-05, independent Opus review pending) | veyro-implementer (Sonnet) | 2026-08-31 | — (independent review found the original evidence insufficient; second review of the bounded re-test evidence above still pending — see verdict below) | — | `knowledge/05-QA/capability-evidence/CAP-001/{positive_test,negative_test,BOUNDED_RETEST_2026-09-05}.md` |
| CAP-002 | TestSprite CLI | Third-party CLI, installed on host (`~/.nvm/.../bin/testsprite`) | 0.8.0 | N/A (external binary, not project-controlled) | **Narrowed 2026-09-05** to exactly what was tested: `test scaffold`, `test lint` (offline, no network); `doctor`, `usage` (authenticate to `api.testsprite.com`, read-only, non-billed — corrected from "offline"). `test create`/`test code`/`test plan` and all live-cloud commands (`test run`/`test rerun`/`testlist run`) are explicitly OUT of scope — **not** approved "by extension," they were never tested. | APPROVED (narrowed scope above) | veyro-test-author (Sonnet) | 2026-08-31 | veyro-security-reviewer (Opus, fresh context) | 2026-09-05 | `knowledge/05-QA/capability-evidence/CAP-002/{positive_test,negative_test,SCOPE_NOTE}.md` |
| CAP-003 | `docx` skill | Anthropic first-party public skill (`/mnt/skills/public/docx`) | as shipped in this environment | not independently hashed (first-party, trusted by default) | read/create/edit .docx files | APPROVED (first-party default-trust, per policy exemption) | bootstrap session | 2026-08-31 | N/A (exemption clause) | N/A | used to read baseline docx during MOD-000 bootstrap |
| CAP-004 | Bash/Read/Write/Edit (core harness tools) | First-party Claude Code harness | N/A | N/A | full project filesystem + shell | APPROVED (first-party/harness exemption — corrected 2026-09-05, previously said "out of scope for this policy" which contradicted the exemption clause's own text that harness-native capabilities still get a registry row/scope/provenance and remain subject to this policy's other rules) | N/A | N/A | N/A (exemption clause) | N/A | N/A |
| CAP-005 | Browser tools (`mcp__Claude_Browser__*`) | First-party Claude Code harness browser pane | as shipped in this environment | N/A (harness-native) | navigate/read/interact with pages for manual-QA evidence gathering | QUALIFIED (positive test real; no negative/malformed-input test yet — not APPROVED until one exists and an Opus role reviews it) | veyro-manual-qa (fresh context, Opus) | 2026-09-04 | — (self-qualified by the same Opus run; per the reviewer/implementer-separation principle, a distinct Opus review should still confirm this, not yet done) | — | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |
| CAP-006 | iOS Simulator control (`mcp__Claude_Code_iOS_Simulator__*`) | First-party Claude Code harness simulator bridge | as shipped in this environment | N/A (harness-native) | boot/attach/interact with iOS Simulator for manual-QA evidence gathering | QUALIFIED (positive+negative test real; `approved_by` not yet populated by a distinct reviewer — same note as CAP-005) | veyro-manual-qa (fresh context, Opus) | 2026-09-04 | — | — | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |

**Honest note on CAP-005/CAP-006:** both were qualified by `veyro-manual-qa` acting in an Opus context, which is a real improvement over CAP-001/CAP-002's Sonnet-only history — but the qualifying agent and the "independent" reviewer would currently be the same invocation, which doesn't satisfy reviewer/implementer separation either. Left as `QUALIFIED` rather than `APPROVED` until a distinct fresh-context Opus review confirms them, consistent with how CAP-001 was just downgraded for a related reason.

## Qualification history

- CAP-001 Notion MCP: qualified 2026-08-31 (positive: database created + row written + read back; negative: malformed-value write rejected — **not** an out-of-scope write, corrected 2026-09-05: the registry previously overclaimed "out-of-scope write rejected" when only a malformed-value write was ever attempted). Independent Opus review (2026-09-05) found this insufficient to support `APPROVED` — see BUG-006 for the specific re-test required.
- CAP-002 TestSprite: qualified 2026-08-31, tests re-run/extended 2026-09-01 (Phase 2). Independent Opus review (2026-09-05) confirmed `APPROVED` with the scope narrowed to what was actually tested — see BUG-006 for the specific corrections made.
- CAP-005/CAP-006: qualified 2026-09-04 by a real fresh-context Opus manual-QA run — the strongest evidence tier on this registry, but not yet independently re-reviewed by a distinct Opus invocation.

## Rejected / revoked

(none yet)

## Fail-closed reminder

No module task may depend on a capability whose `review_status` is not `APPROVED`, except the qualification drill itself. See `CAPABILITY_POLICY.md`.
