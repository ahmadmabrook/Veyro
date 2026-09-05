---
doc: ADR-003
status: RETROACTIVE — documents a pre-existing deviation discovered 2026-09-05, not a decision made before implementation
date: 2026-09-05
decided_by: not yet — owner decision required (see below); this ADR records the finding and options, per DC-09's requirement that a deviation discovered after the fact still gets an ADR
found_by: Third independent Opus review (veyro-security-reviewer, distinct fresh-context invocation, BUG-006/CAP-001 bounded re-test evaluation)
---

# ADR-003: CAP-001 (Notion MCP) connector authorization is broader than `CAPABILITY_POLICY.md`'s scope rule permits

## What was found

`CAPABILITY_POLICY.md` states: "No capability may be granted broader
scope (filesystem, network, spend) than the specific gap requires." The
gap CAP-001 (Notion MCP) exists to fill is read/write access to nine
named databases under the "Veyro Engineering Control Plane" page tree.
The actual grant, confirmed 2026-09-05 by a direct out-of-scope write
test (`knowledge/05-QA/capability-evidence/CAP-001/BOUNDED_RETEST_2026-09-05.md`),
is authorization against the owner's **entire personal Notion workspace**
— `notion-create-pages` with no `parent` succeeded, creating a
standalone page outside the Control Plane tree with no permission error.

This is a real, standing policy deviation, not a hypothetical risk. It
predates this ADR — the connector was authorized this way from the
project's start (2026-08-31); this ADR documents it retroactively, as
DC-09 requires for any deviation discovered after the fact, rather than
leaving it unrecorded.

## What is NOT the finding

This is not evidence of any actual misuse. Across the project's full
history, the only write ever made outside the Control Plane tree is the
one deliberate, documented test that discovered this gap, immediately
moved into the Control Plane tree afterward. It is also not a finding
about read access to pre-existing non-Veyro content — that was never
technically tested (see the correction applied to
`NOTION_SCOPE_AUDIT.md` the same day); only page-creation authorization
was demonstrated.

## Why this matters

The owner's Notion workspace may contain the owner's own real personal
content unrelated to Veyro. An errant write there (a bug in a future
session's tool call, a malformed parameter, a genuinely mistaken
"parent") would not be blocked by Notion's own permission model — only
by this project's own behavioral discipline. That is a materially
weaker safety property than "the connector can't reach it," and this
project's own review discipline exists specifically to avoid presenting
a weaker property as if it were the stronger one.

## Options (owner decision required — this ADR does not choose one)

**(a) Re-authorize the Notion connector scoped to the Control Plane page
tree**, converting this from a behavioral control into a technical one.
This is the reviewer's stated preference — it retires the caveat set
below entirely once done, and directly matches `CAPABILITY_POLICY.md`'s
own scope rule. Concretely: the owner would need to reconnect/reconfigure
the Notion MCP connector (via Notion's own connector/integration
permission settings) to grant page-level access only to the "Veyro
Engineering Control Plane" page and its descendants, rather than the
whole workspace. This is an out-of-band action the owner performs
outside Claude Code, not something any session can do to its own tool
grant.

**(b) Accept the workspace-wide authorization as-is**, recorded as an
explicit owner-approved risk acceptance in
`knowledge/00-System/OWNER_APPROVALS.md` (a new `OWN-<NNN>` row), with
the compensating behavioral control below (`.claude/rules/notion-mcp-scope-discipline.md`)
as the ongoing mitigation. This keeps the current, already-working setup
but leaves the technical gap open permanently, relying on discipline
rather than enforcement.

**Until the owner chooses (a) or (b), CAP-001 remains APPROVED for
continued in-scope use** (per the third independent review's verdict —
see `CAPABILITY_REGISTRY.md`), gated on the compensating control below,
**not** `BLOCKED: OWNER_APPROVAL_REQUIRED` — the reviewer explicitly
distinguished "the capability is not defective, its authorization
configuration is" from a reason to halt otherwise-legitimate,
already-scoped project work. This is a real, live gap to close, not a
certification blocker on its own.

## Compensating control (in effect now, regardless of which option the owner picks)

`.claude/rules/notion-mcp-scope-discipline.md` (authored alongside this
ADR) encodes: every `notion-create-pages` call must specify an explicit
`parent` inside the Control Plane tree (never omitted); no read/update/move
of any page outside that tree without `BLOCKED: OWNER_APPROVAL_REQUIRED`
being reported first; the registry's scope field states demonstrated vs.
inferred capability precisely, never implying technical enforcement that
doesn't exist.

## Affected

`CAPABILITY_REGISTRY.md` (CAP-001 row), `CAPABILITY_POLICY.md` (scope
rule, currently unmet for this one capability),
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-006-*.md`,
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-010-cap-001-connector-scope-broader-than-policy.md`.
Does not block MOD-000 certification on its own (CAP-001 is APPROVED with
caveats, not BLOCKED) but should be resolved — pick (a) or (b) — before
Phase 10.
