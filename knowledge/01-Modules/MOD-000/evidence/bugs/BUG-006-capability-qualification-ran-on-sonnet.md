---
doc: BUG-006
status: OPEN
found_date: 2026-09-04
found_by: Phase 5 independent review (veyro-code-reviewer, fresh context, Opus) — finding F5-004/F5-003, confirms catalog SCN-MOD000-055's own pre-declared "Expected audit result if run today: FAIL"
severity: P1 (Blocker per SCN-055's catalog severity)
---

# BUG-006: Capability qualification (CAP-001, CAP-002) ran on Sonnet, not Opus

## What is wrong

`CAPABILITY_POLICY.md` line 48: "Qualification runs (positive/negative
tests, independent evaluation of third-party capability text) are
assurance-tier work -> route to Opus per `DEVELOPMENT_CONSTITUTION.md`."

`CAPABILITY_REGISTRY.md`'s own table (never hidden) records:
- CAP-001 `qualified_by: veyro-implementer (this session, Sonnet)`
- CAP-002 `qualified_by: veyro-test-author (this session, Sonnet)`

Both violate the policy's own routing rule. `SCENARIO_CATALOG.md`'s
SCN-MOD000-055 detail block had already identified this exact defect and
pre-declared "Expected audit result if run today: FAIL" — but it was never
filed as a bug, so it never appeared in the "0 open bugs" count that Phases
1-4 all reported.

## Why it wasn't caught by Phases 1-4

The scenario's own text carried the finding as prose ("this violates
CAPABILITY_POLICY.md's explicit routing... that excuse is struck"), which
every phase's evidence-integrity checking treated as narrative, not as a
tracked defect, because the checker only scans `evidence/bugs/` for bug
counts and never cross-references scenario prose for self-declared FAILs.
(This class of gap is now also filed — see `evidence/bugs/BUG-007-*.md`
for the broader validator/checker weakness.)

## Why it is not yet fixed

No currently-registered agent is both (a) Opus-tier and (b) tooled with
the access needed to actually *perform* a qualification run (Notion MCP
tools for CAP-001, Bash for CAP-002's TestSprite CLI, plus Write to record
evidence) — `veyro-security-reviewer` and `veyro-lead` (the two Opus roles
closest in mandate) are deliberately review-only (Read/Grep/Glob/Bash for
`veyro-security-reviewer`; no Write, no Notion tools), consistent with
role-separation (a reviewer should not also be the implementer performing
the thing it reviews). Fixing this by simply granting those tools to a
reviewer agent would itself reintroduce role-collapsing (see finding
F5-018). The correct fix is either (a) a new, purpose-built Opus-tier
"capability qualifier" agent role, or (b) an owner-recorded deviation
accepting the existing Sonnet-tier evidence with a documented risk
rationale. Both are architecture-level decisions, not a same-turn config
edit — deferred, tracked here, not silently worked around.

## Remediation required

1. Decide (owner or `veyro-lead`, Opus, architecture-tier decision) between:
   (a) register a new Opus-tier agent role scoped specifically to
   capability-qualification execution, with the minimum tools needed
   (Bash + Notion MCP tools + Write, nothing broader), or
   (b) record an explicit owner-approved deviation in
   `knowledge/03-ExternalGates/` accepting the existing Sonnet-tier
   qualification evidence for CAP-001/CAP-002 specifically, with a written
   risk rationale (both are first-party/local low-risk tools per the
   existing — now corrected — `module-capabilities.yaml` note).
2. If (a): re-run CAP-001 and CAP-002 qualification (real positive +
   negative tests) through the new agent; update `qualified_by` fields;
   produce `evidence/model-routing/ASSURANCE_TIER_AUDIT.md`.
3. Either way: re-run SCN-MOD000-055 and record its corrected disposition
   in the catalog (currently still reads "Expected audit result if run
   today: FAIL" — must be updated to the actual re-audit result, not left
   as a prediction).

## Affected

SCN-MOD000-055, SCN-MOD000-030, `CAPABILITY_REGISTRY.md`,
`module-capabilities.yaml`, `evidence/CAP-001/`, `evidence/CAP-002/`.

**Blocks MOD-000 certification: YES** (Blocker severity, unresolved).
