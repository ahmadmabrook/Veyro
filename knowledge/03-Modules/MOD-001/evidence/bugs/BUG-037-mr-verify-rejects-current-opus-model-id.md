---
doc: BUG-037
module: MOD-000 (tool: knowledge/05-QA/tools/mr_verify.py), surfaced by MOD-001
severity: P1 (proposed by the filer; blocks DC-17 runtime model attestation for every Opus-tier assurance action; fails closed, so no false-clean risk)
status: OPEN (2026-09-29)
filed: 2026-09-29 by veyro-critical-engineer (Opus) during MOD-001 Slice 5 (GOV-01-R02); not fixed by the filer (see "Why not fixed here")
---

# BUG-037 — `mr_verify.py` rejects the harness's current Opus model id (`claude-opus-5-5`), and lacks 3 ADR-005 agents

## Finding (real execution, not inference)

The MOD-001 Slice 5 dispatch tried to attest its own runtime tier with the
project's own attestation tool, against its own subagent transcript:

```
$ python3 knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/eca6420e-750e-4f5a-8636-1c4a7d0a68db/subagents/agent-a3ead2c53ad28b026.jsonl \
    opus veyro-critical-engineer
{
  "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
  "reason": "Resolved model 'claude-opus-5-5' does not match required tier 'opus' (expected pattern ^claude-opus-\\d+(\\.\\d+)*$) for veyro-critical-engineer.",
  "models_observed": ["claude-opus-5-5"],
  "expected_tier": "opus"
}
exit=1
```

The transcript itself is a genuine Opus transcript: every assistant turn's
harness-populated `message.model` field is `claude-opus-5-5` (127/127 at the
time of the check; one distinct value, no substitution). The tool fails
anyway.

## Root cause (confirmed)

Two independent defects:

1. **Family regex too narrow for the provider's current id shape.**
   `_FAMILY_RE["opus"] = ^claude-opus-\d+(\.\d+)*$` (tightened 2026-09-05,
   N-9, to reject `claude-opus-9-nonexistent-model-id`) accepts
   `claude-opus-5` and `claude-opus-5.5` but not the dash-separated minor
   version the harness actually resolves today:

   ```
   claude-opus-5    True
   claude-opus-5-5  False
   claude-opus-5.5  True
   ```

   Every Opus assurance attestation (Code Review, Security, Manual QA,
   Gatekeeper, critical-engineer) therefore returns `BLOCKED:
   MODEL_ASSURANCE_UNVERIFIED` from here on, even though the underlying
   evidence is sound. The same shape change presumably applies to the
   Sonnet pattern (not independently observed this session).

2. **`EXPECTED_TIER_BY_AGENT` lacks the three agents `ADR-005` registered.**
   `veyro-critical-engineer` (opus), `veyro-backend-engineer` (sonnet) and
   `veyro-infra-sre-engineer` (sonnet) are absent, so the tool cannot
   enforce their *registered* tier. It silently falls through to the
   caller-supplied tier, which is the weaker check the map exists to prevent.

## DC-17 dimension (governance, not just tooling)

DC-17's sub-clause requires that "provider-side model-family changes that
could affect assurance capability (e.g. a model alias resolving to a
different underlying model) must be re-qualified... not assumed to still
satisfy the tier requirement." Every prior MR record in this project attests
`claude-opus-5`/`claude-sonnet-5`. `opus` now resolves to `claude-opus-5-5`.
Widening the regex is a mechanical fix. Accepting `claude-opus-5-5` as
satisfying the Opus tier is a re-qualification decision that belongs to an
independent Opus assurance role, not to the tool's own patch.

## Why not fixed here

`mr_verify.py` is the tool that attests the filer's own tier. If the filer
edited it until it returned PASS for its own transcript, that would be exactly
the self-certification §4.1 ("No self-review") forbids. It is also outside the
bounded Slice 5 scope (`ADR-005` Decision 1). So it is recorded and routed.

## Suggested fix (for whoever is routed it, subject to independent review)

- `_FAMILY_RE`: `^claude-opus-\d+([.-]\d+)*$` (and the same for sonnet).
  This still rejects any alphabetic suffix, so N-9's
  `claude-opus-9-nonexistent-model-id` negative case keeps failing. Add a
  positive fixture for `claude-opus-5-5`, and keep the N-9 negative fixture.
- Add the three ADR-005 agents to `EXPECTED_TIER_BY_AGENT`.
- Record the DC-17 re-qualification of `claude-opus-5-5` (and the current
  Sonnet id) via an independent Opus review, with MR evidence.

## Impact on MOD-001 Slice 5

Slice 5's MR record
(`knowledge/03-Modules/MOD-001/evidence/model-routing/CRITICAL_ENGINEER_SLICE5_DISPATCH_2026-09-29.md`)
records the raw transcript evidence (100% `claude-opus-5-5`) and this
tool's BLOCKED verdict side by side. It does not claim tool-attested PASS.
