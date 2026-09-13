---
doc: PHASE10_MODEL_ROUTING_RESOLUTION
status: LIVE
date: 2026-09-13
---

# Phase 10 — formal resolution of the Phase 9-disclosed `mr_verify.py` Gatekeeper-attestation gap

Phase 9 (`PHASE9_GATEKEEPER_ROUTING_2026-09-13.md`) disclosed but did not
resolve: `mr_verify.py` was never run against the nine Phase 9
Gatekeeper Agent-tool dispatches, and recorded this as "a Phase 10
question, not a Phase 9 blocker." Per this chunk's own instruction to
explicitly address and resolve or accept the gap (not silently ignore
it), this file records the resolution.

## What was done this chunk

`mr_verify.py` was actually run against this orchestrating session's own
transcript file, targeting the `veyro-gatekeeper` label at `opus` tier.
It returned `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`, observing only
`claude-sonnet-5`. Direct inspection of `mr_verify.py`'s own
`extract_models()` logic, combined with this session's inability to
enumerate any per-subagent transcript file (no directory-listing
capability exists outside the repo's own guarded, relative-path-scoped
`ls`/`find`), established that this result reflects the orchestrating
session's own model field, not any `veyro-gatekeeper` subagent's — the
tool's file-based CLI interface cannot isolate Agent-tool-dispatched
subagent turns from the session that dispatched them. Full detail:
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-027-mr-verify-cannot-isolate-agent-tool-subagent-transcripts.md`
(new this chunk).

## Formal disposition

**ACCEPTED AS A DISCLOSED, NON-BLOCKING LIMITATION for MOD-000
certification.** This is not a silent gap — BUG-027 documents it in
full, including the misleading nature of the raw tool output, so no
future session mistakes the BLOCKED result above for a genuine
tier-substitution finding.

**Compensating controls judged sufficient** (detailed in BUG-027):
harness-level `model: opus` frontmatter pinning in
`.claude/agents/veyro-gatekeeper.md` (a configuration-enforced
guarantee, not a self-report); explicit non-default `model: "opus"` set
on every individual Agent-tool dispatch call across all nine Phase 9
rounds (`PHASE9_GATEKEEPER_ROUTING_2026-09-13.md`'s own table); and
consistent Opus-tier-depth behavioral evidence (new genuine defects
found across all nine independently-dispatched fresh-context rounds).
`mr_verify.py` itself remains fully correct and required for its proven
use case — independently-invoked sessions/roles with their own
addressable transcript file (`veyro-code-reviewer`, `veyro-manual-qa`,
`veyro-security-reviewer`, per `ASSURANCE_TIER_AUDIT.md`) — this
resolution narrows the gap to exactly one invocation shape (Agent-tool
in-session dispatch of `veyro-gatekeeper` and, by the same reasoning,
`veyro-scenario-reviewer`/`veyro-lead`/`veyro-performance-reviewer` when
dispatched the same way).

## Why this does not block Phase 10 certification

DC-17 requires "runtime model-proof evidence" for every assurance-tier
action. The compensating controls above satisfy the *intent* of DC-17
(preventing an undisclosed, undetected tier downgrade) through a
configuration-level and behavioral evidence chain rather than the
project's preferred transcript-attestation mechanism. This is
materially different from having no assurance mechanism at all, and is
recorded honestly as a narrower, still-real gap — not resolved to
"transcript-verified," which would be a false claim BUG-027 exists
specifically to prevent.

## Forward-looking recommendation (not a Phase 10 blocker)

If a future session or the harness itself exposes a documented,
addressable per-subagent-dispatch transcript path, `mr_verify.py`
itself should be extended to consume it (not a new script this time —
per the same reasoning `capability_drift_check.py`'s own docstring
gives for why *it* had to be new: `mr_verify.py`'s own SHA-256 hash is
pinned in `.claude/security/bash_guard.py`'s allowlist and must not be
edited in-place without an owner-authorized guard edit first). Closing
BUG-027 for real. Tracked in `BUG_REGISTRY.md`, not attempted this
chunk. (Corrected 2026-09-13, third certification-scope Gatekeeper
round, Editorial: the sentence above previously read ambiguously as if
`capability_drift_check.py` — which is NOT allowlist-pinned, that is
precisely its own disclosed activation gap — were the pinned file.)
