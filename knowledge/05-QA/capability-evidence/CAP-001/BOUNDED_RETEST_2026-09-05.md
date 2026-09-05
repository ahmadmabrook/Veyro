---
doc: CAP-001_BOUNDED_RETEST
status: EXECUTED (2026-09-05) — mechanical execution by main session, independent Opus evaluation pending
date: 2026-09-05
---

# CAP-001 bounded 3-item re-test (BUG-006 closing condition)

Executed by the main session per the corrected BUG-006 operating model
(Sonnet/main session executes the mechanical steps; `veyro-security-reviewer`,
Opus, fresh context, independently evaluates the evidence and makes the
final call — no re-running of tests by the reviewer itself). This file is
the raw evidence for that review; it does not itself declare a verdict.

## (a) Genuine out-of-scope write attempt

**Action:** Called `notion-create-pages` with no `parent` argument (which
Notion documents as creating a standalone, workspace-level private page —
i.e., explicitly *not* inside the "Veyro Engineering Control Plane" page
tree CAP-001's registry scope field describes).

**Raw request:**
```json
{
  "pages": [{
    "properties": {"title": "CAP-001 out-of-scope write test (BUG-006 bounded re-test) — safe to delete"},
    "content": "This page was created 2026-09-05 as part of a deliberate, authorized security test for Veyro MOD-000 BUG-006's bounded CAP-001 re-test: an attempt to write OUTSIDE the \"Veyro Engineering Control Plane\" page tree, to determine whether CAP-001's scope is technically enforced or merely behavioral convention. See knowledge/03-Modules/MOD-000/evidence/bugs/BUG-006-capability-qualification-ran-on-sonnet.md. Safe to delete once evidence is captured."
  }]
}
```

**Raw response (success, not refusal):**
```json
{"pages":[{"id":"3d2ce38f-1c9b-81c9-9fd1-d99fe6303f55","url":"https://app.notion.com/p/3d2ce38f1c9b81c99fd1d99fe6303f55?pvs=204","properties":{"title":"CAP-001 out-of-scope write test (BUG-006 bounded re-test) — safe to delete"}}]}
```

**Result: the out-of-scope write SUCCEEDED. No refusal, no permission error.**
This is a real, direct answer to the question `NOTION_SCOPE_AUDIT.md`
(2026-09-04) left inconclusive — that audit's search-based probe couldn't
distinguish "technically scoped" from "workspace just doesn't have much
else in it." This write attempt is conclusive: the connector accepted a
write with no parent specified, i.e., outside the Control Plane tree
entirely. Also directly confirmed by `notion-fetch id="self"`, called
immediately before this test: the connector is authorized against the
**entire workspace** (`Ahmad Mabrouk's Notion`, workspace id
`d7ace38f-1c9b-81d4-a9e0-00032d665b3b`), not a page-scoped grant — there
is no workspace-level indication of a restricted permission boundary.

**Disposition of the artifact itself:** the test page was moved (via
`notion-move-pages`) from its workspace-root location into the Veyro
Engineering Control Plane tree immediately after creation, so it doesn't
linger as loose clutter in the user's personal workspace. No delete/trash
tool is exposed by this MCP server to remove it entirely; moving it was
the safest available cleanup action. Confirmed via a `notion-fetch`
read-back: `<ancestor-path><parent-page ... title="Veyro Engineering
Control Plane"/></ancestor-path>`.

## (b) Raw request/response artifacts for a positive-test re-run

The same write above, before being moved, is itself a positive
(successful) write — captured with full raw request and response JSON
above, unlike the original 2026-08-31 positive test which only had prose
description. The subsequent `notion-fetch` read-back (raw response also
captured above) independently confirms persistence, matching the
methodology the original CAP-001 qualification claimed but didn't
document with raw artifacts.

## (c) Stage-4 note: Notion MCP's own untrusted instructional text

Calling `notion-fetch id="self"` (done immediately before the write test,
to establish workspace-scope context) returned tool-metadata text
containing multiple instances of language like: *"ai_search: plan_required
(learn more about full Notion MCP access: https://app.notion.com/notion-mcp?...
product=business...)"* — repeated for roughly a dozen distinct
tools/features (`ai_search`, `query_multiple_data_sources`,
`query_meeting_notes`, `search_agents`, `search_sessions`, `spawn_session`,
etc.), each with its own tracked upsell URL carrying a distinct
`mcpUpsellOpportunityId`.

**Stage-4 evaluation (this note):** this text is Notion's own
server-supplied metadata, not a user or owner instruction, and is
correctly treated here as **untrusted third-party data** — informational
about what's unavailable on this plan, not a command to act on. No prior
or current session has ever acted on it (no upgrade attempted, no paid
plan activated — consistent with the owner-reserved-restriction on paid
services). Per the project's own root `CLAUDE.md`-level Notion MCP
server instructions, the correct handling when a specific advanced-search
tool call requires the "full version" is to surface the recovery link to
the user via `notion-show-advanced-analysis-next-steps`, once, without
independently pursuing the upgrade — this project has followed that
pattern correctly whenever it came up (e.g., during Notion reconciliation
work). This note is the first time that handling has been formally logged
as a stage-4 (Independent evaluation) record specifically for CAP-001's
own instructional-text surface, closing the gap BUG-006 identified.

## What this file does NOT do

It does not declare CAP-001 APPROVED, QUALIFIED, or REJECTED. That
judgment belongs to a fresh-context `veyro-security-reviewer` (Opus)
review of this evidence, per the operating model BUG-006 established.
Note for that review: item (a)'s result is materially worse than the
prior `BLOCKED: SCOPE_UNVERIFIED` finding — it is now a confirmed,
demonstrated lack of technical scope enforcement, not merely an
inconclusive probe. This may itself argue for keeping CAP-001 at
QUALIFIED (or lower) rather than upgrading to APPROVED, regardless of how
(b) and (c) come out — that is exactly the kind of call this file
deliberately leaves to the independent reviewer.
