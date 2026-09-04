---
doc: NOTION_SCOPE_AUDIT
status: BLOCKED: SCOPE_UNVERIFIED (partial evidence only, not conclusive)
date: 2026-09-04
---

# CAP-001 Notion MCP — technical scope audit (SCN-MOD000-070)

## What was tested

A broad, minimally-discriminating `notion-search` query (`"a"`, no filters,
page_size 10) was run to see whether results outside the "Veyro Engineering
Control Plane" page tree would surface, which would indicate the connector
has broader-than-intended workspace access.

## Result

All 10 returned results were under the "Veyro Engineering Control Plane"
page path. No unrelated workspace content surfaced.

## Why this is not conclusive (honestly recorded, not oversold)

This result is consistent with either of two different explanations, and
this test cannot distinguish them:
1. The connector's actual OAuth-level access is genuinely scoped down to
   only the Veyro Control Plane content (the desired state), or
2. The connector has broader workspace access, but the user's Notion
   workspace simply doesn't contain much else, or a relevance-ranked
   single-letter query didn't surface it.

A conclusive technical audit would need to inspect the actual OAuth grant
/ connector permission scope directly (outside this session's available
tools) or have a known, distinct piece of non-Veyro content in the
workspace to use as a positive control (deliberately search for it and
confirm whether it's reachable).

## Disposition

Per SCN-MOD000-070's own governing text: "good behavior alone, with no
technical boundary, does NOT satisfy this scenario... if it cannot be
confirmed, record BLOCKED: SCOPE_UNVERIFIED." That is the honest
disposition here — real evidence gathered, genuinely inconclusive, not
upgraded to PASS.

**Corrected `CAPABILITY_REGISTRY.md` scope field (2026-09-04):** CAP-001's
scope description should read as the connector's *intended* scope
("Veyro Engineering Control Plane databases only"), not as a claim of
verified technical enforcement — the registry text was ambiguous on this
distinction before Phase 5; this file is now the durable, honest audit
record it pointed to.
