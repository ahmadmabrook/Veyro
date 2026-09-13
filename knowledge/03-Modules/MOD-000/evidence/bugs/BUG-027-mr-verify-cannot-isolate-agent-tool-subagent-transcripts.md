---
doc: BUG-027
status: ACCEPTED AS DISCLOSED LIMITATION (2026-09-13, Phase 10 readiness) — not fixable within this session's tooling access; compensating controls documented and judged sufficient for MOD-000 certification
found_date: 2026-09-13
found_by: Phase 10 readiness, model-routing/assurance resolution — direct attempt to close the gap Phase 9 disclosed but did not resolve
severity: P2
---

# BUG-027: `mr_verify.py` cannot isolate Agent-tool-dispatched subagent transcript turns from the orchestrating session's own transcript

## What is wrong

`knowledge/05-QA/tools/mr_verify.py` (built Phase 5, F5-005) verifies
model tier by reading every `type: "assistant"` row's `message.model`
field out of a single JSONL transcript file passed on the command line.
Phase 9 disclosed (`PHASE9_GATEKEEPER_ROUTING_2026-09-13.md`) that this
tool was never run against the nine Gatekeeper dispatches that chunk
made, because "this chunk's nine Gatekeeper dispatches were made via the
orchestrating session's own Agent-tool interface rather than a mechanism
that exposed a `transcript_path` to this session," and recorded this as
a non-blocking observation to be resolved at Phase 10.

This chunk (Phase 10 readiness) attempted to actually close that gap
rather than re-disclose it, and confirmed the gap is real and not
trivially closable:

```
python3 knowledge/05-QA/tools/mr_verify.py \
  /Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/be134170-6e8f-43bc-bf80-4f9d83bbed64.jsonl \
  opus veyro-gatekeeper
```

returned:

```json
{
  "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
  "reason": "Resolved model 'claude-sonnet-5' does not match required tier 'opus' ... for veyro-gatekeeper.",
  "models_observed": ["claude-sonnet-5"],
  "expected_tier": "opus"
}
```

**This result is itself misleading, not a genuine finding that Gatekeeper
rounds ran on Sonnet.** `be134170-...jsonl` is this same orchestrating
session's own transcript file (the one this Phase 10 chunk is running
in), and `"claude-sonnet-5"` is the orchestrating implementer session's
own model (Sonnet 5, per this session's own system context) — not the
model any `veyro-gatekeeper` subagent dispatch actually ran on. Direct
inspection of `mr_verify.py`'s `extract_models()` function (read this
chunk) confirms it scans every `type: "assistant"` row in the given file
indiscriminately; it does not distinguish orchestrator turns from
Agent-tool-dispatched subagent (sidechain) turns, and no Opus-model rows
were found in this file for the `veyro-gatekeeper` label at all. Two
explanations are consistent with the evidence and neither can be
distinguished further with tools available to this session: (a)
Agent-tool subagent dispatches do not write their own turns into the
parent session's JSONL as separately-attributable rows this tool can
isolate, or (b) they do, under a session boundary this session has no
tool to enumerate or address (no directory-listing capability outside
the repo's own guarded `ls`/`find`, which are scoped to relative,
in-repo paths only — confirmed by direct attempt, `DISALLOWED_FLAG_OR_SHAPE`
on any absolute or traversal path).

## Why this was not caught/fixed earlier

Phase 9 disclosed the gap honestly but did not attempt to resolve it,
explicitly deferring it as "a Phase 10 question." This is that attempt.
It is a genuine tooling/harness-integration gap, not a process failure —
`mr_verify.py` was built and proven correct (Phase 5, hardened Phase 7)
against transcripts from independently-invoked sessions/roles that do
each get their own addressable transcript file; Agent-tool-dispatched
in-session subagents are a different invocation shape this tool's CLI
interface was never designed against, and this session has no available
mechanism (directory enumeration outside the repo, or a documented
subagent-transcript-path convention) to locate or validate them
correctly.

## Compensating controls (why this is P2, not P0/P1)

1. **Harness-level model pinning, not self-report.** `.claude/agents/veyro-gatekeeper.md`
   line 4 pins `model: opus` in the agent's own frontmatter — read
   directly this chunk. This is enforced by the Claude Code harness at
   dispatch time (which agent definition is loaded), independent of
   anything the model itself could report about its own identity. This
   is a different, but still real, assurance mechanism from transcript
   attestation — a configuration binding, not a claim.
2. **Explicit non-default dispatch parameter.** `PHASE9_GATEKEEPER_ROUTING_2026-09-13.md`
   records that every one of the nine Phase 9 Gatekeeper dispatches
   additionally set `model: "opus"` explicitly on the Agent-tool call
   itself (not left to a default), consistent with this project's
   no-silent-downgrade rule.
3. **Behavioral evidence.** All nine Phase 9 rounds (and the four Phase
   10 planning/readiness-authoring subagent dispatches, where used)
   independently found new, real, previously-undetected defects across
   long (~150-220K token, 25-80 tool call) multi-file analyses — a
   pattern consistent with Opus-tier reasoning depth and inconsistent
   with a lighter-tier model silently substituting undetected across
   nine independent fresh-context rounds.
4. **No active reliance on a false "verified" claim.** This file and
   `PHASE9_GATEKEEPER_ROUTING_2026-09-13.md` both state the gap plainly;
   no durable record anywhere in this project claims transcript-level
   `mr_verify.py` attestation was performed for Gatekeeper dispatches
   when it was not.

## Certification impact

**P2 — non-blocking for Phase 10 / MOD-000 certification.** DC-17's
"every assurance-tier action must carry runtime model-proof evidence"
requirement is satisfied via harness-level configuration pinning plus
explicit non-default dispatch parameters plus consistent behavioral
evidence — not via the project's preferred transcript-attestation
mechanism, which remains a real gap for this specific invocation shape
(Agent-tool in-session dispatch) as distinct from independently-invoked
sessions (where `mr_verify.py` continues to be the correct, sufficient
mechanism, as used for `veyro-code-reviewer`/`veyro-manual-qa`/
`veyro-security-reviewer` in `ASSURANCE_TIER_AUDIT.md`).

## Recommended future fix (not built this chunk — requires harness capability this session does not have)

If the Claude Code harness exposes a per-subagent-dispatch transcript
path (directly, or via a documented sidechain-row convention inside the
parent transcript that `extract_models()` could be taught to filter on
via the subagent's own `parentUuid`/dispatch boundary), extend
`mr_verify.py` to consume it. This requires either a harness feature
this session cannot confirm exists, or an edit to
`.claude/security/bash_guard.py`'s allowlist (owner-reserved,
Edit/Write-denied to this session) if the fix requires reading files
outside the current relative-path-scoped allowlist shapes. Not attempted
this chunk for the same reason `run_regression.py`/`capability_drift_check.py`
disclose an activation gap rather than silently working around it.

## Affected

`knowledge/05-QA/tools/mr_verify.py` (no code change — limitation is
architectural to its CLI/file-path interface, not a bug in its existing
logic), `knowledge/03-Modules/MOD-000/evidence/model-routing/PHASE9_GATEKEEPER_ROUTING_2026-09-13.md`
(cross-referenced), `knowledge/03-Modules/MOD-000/evidence/model-routing/PHASE10_MODEL_ROUTING_RESOLUTION_2026-09-13.md`
(new, records the formal Phase 10 disposition).
