#!/usr/bin/env python3
"""
MR (Model Route) runtime-identity verification tool.

Authored 2026-09-05 for F5-005 remediation. Investigates and implements
the EIP §4.1 requirement: "an observable session transcript/status/
warning record sufficient to detect substitution/fallback" — not just a
model's own self-report.

## What was investigated

Grepped this project's own live session transcripts (JSONL, one line per
turn) and found every assistant-role message carries a `model` field
(e.g. "claude-opus-5", "claude-sonnet-5") — populated by the harness/API
response metadata, not authored by the model's own output text. Verified
across 20 real subagent transcripts from this same session: every
Opus-tier agent (veyro-security-reviewer, veyro-code-reviewer,
veyro-manual-qa, veyro-gatekeeper, veyro-lead, veyro-scenario-reviewer)
showed 100% "claude-opus-5" across every turn of its transcript (not just
the first message); every Sonnet-tier agent (veyro-implementer,
veyro-test-author) showed 100% "claude-sonnet-5". No environment variable
exposes this (checked — real negative finding, `env | grep -i model`
returns nothing naming the resolved model); the transcript file is the
real signal.

## What this tool does

Given a transcript file (JSONL, one JSON object per line, each with a
`model` field on assistant messages) and an expected model family
substring, verify:
1. At least one assistant message exists (the transcript isn't empty/the
   agent never actually ran).
2. Every `model` value found is identical (no mid-task substitution).
3. That single value matches the expected family.

Emits BLOCKED: MODEL_ASSURANCE_UNVERIFIED (not a bare Python exception)
on any of: no assistant messages found, inconsistent model values across
turns, or a mismatch against the expected family. This is deliberately
strict — for exactly the reason EIP §4.1 requires it: an Opus-required
assurance role silently running on Sonnet must never look like a pass.
"""
import json
import re
import sys
from pathlib import Path

EXPECTED_TIER_BY_AGENT = {
    "veyro-lead": "opus", "veyro-implementer": "sonnet",
    "veyro-scenario-reviewer": "opus", "veyro-code-reviewer": "opus",
    "veyro-manual-qa": "opus", "veyro-security-reviewer": "opus",
    "veyro-performance-reviewer": "opus", "veyro-gatekeeper": "opus",
    "veyro-test-author": "sonnet",
}

# Family pattern per tier: "claude-<tier>-<version>", version = digits/dots only,
# nothing trailing after it. Tightened 2026-09-05 (second Phase 5 re-review, N-9):
# the prior check was `expected_tier in observed` (substring), which a fabricated
# model id like "claude-opus-9-nonexistent-model-id" would pass -- confirmed by
# the reviewer. This anchors both ends so only a genuine family+version string
# matches.
_FAMILY_RE = {
    "opus": re.compile(r"^claude-opus-\d+(\.\d+)*$"),
    "sonnet": re.compile(r"^claude-sonnet-\d+(\.\d+)*$"),
}


def extract_models(transcript_text: str) -> list[str]:
    """Pull every assistant-message `model` field from JSONL transcript text.
    Tolerant of non-JSON/malformed lines (treated as noise, not fatal) —
    but a transcript with ZERO valid model fields is itself a finding."""
    models = []
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # malformed line — not itself proof of substitution, just noise
        model = obj.get("message", {}).get("model") if isinstance(obj.get("message"), dict) else None
        if model:
            models.append(model)
    return models


def verify(transcript_text: str, expected_tier: str, agent_label: str = "") -> dict:
    """Returns a dict: {"verdict": "PASS"|"BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
    "reason": str, "models_observed": [...], "expected_tier": expected_tier}"""
    # Enforced 2026-09-05 (second Phase 5 re-review, N-9): EXPECTED_TIER_BY_AGENT was
    # defined and never referenced, so a caller could pass "sonnet" for
    # veyro-code-reviewer and get PASS. If agent_label names a known role, its
    # registered tier is authoritative -- a caller-supplied tier that disagrees
    # with it is itself a finding, not silently accepted.
    if agent_label in EXPECTED_TIER_BY_AGENT:
        registered_tier = EXPECTED_TIER_BY_AGENT[agent_label]
        if registered_tier != expected_tier.lower():
            return {
                "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
                "reason": f"Caller-supplied expected_tier '{expected_tier}' disagrees with the registered tier '{registered_tier}' for agent '{agent_label}' in EXPECTED_TIER_BY_AGENT — refusing to verify against a possibly-wrong tier.",
                "models_observed": [], "expected_tier": expected_tier,
            }
    models = extract_models(transcript_text)
    if not models:
        return {
            "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
            "reason": f"No model field found in transcript for {agent_label or 'agent'} — cannot verify runtime identity at all.",
            "models_observed": [], "expected_tier": expected_tier,
        }
    distinct = sorted(set(models))
    if len(distinct) > 1:
        return {
            "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
            "reason": f"Inconsistent model values across the same transcript ({distinct}) — possible substitution/fallback mid-task for {agent_label or 'agent'}.",
            "models_observed": distinct, "expected_tier": expected_tier,
        }
    observed = distinct[0]
    tier_key = expected_tier.lower()
    pattern = _FAMILY_RE.get(tier_key)
    if pattern is None:
        return {
            "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
            "reason": f"Unknown expected tier '{expected_tier}' — must be one of {sorted(_FAMILY_RE)}.",
            "models_observed": distinct, "expected_tier": expected_tier,
        }
    if not pattern.match(observed):
        return {
            "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
            "reason": f"Resolved model '{observed}' does not match required tier '{expected_tier}' (expected pattern {pattern.pattern}) for {agent_label or 'agent'}.",
            "models_observed": distinct, "expected_tier": expected_tier,
        }
    return {
        "verdict": "PASS",
        "reason": f"{len(models)} turn(s), 100% consistent, model '{observed}' matches required tier '{expected_tier}'.",
        "models_observed": distinct, "expected_tier": expected_tier,
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: mr_verify.py <transcript_file> <expected_tier: opus|sonnet> [agent_label]")
        sys.exit(2)
    path, expected_tier = sys.argv[1], sys.argv[2]
    agent_label = sys.argv[3] if len(sys.argv) > 3 else ""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    result = verify(text, expected_tier, agent_label)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
