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
turns, a mismatch against the expected family, or an unreadable
transcript file. This is deliberately strict — for exactly the reason
EIP §4.1 requires it: an Opus-required assurance role silently running on
Sonnet must never look like a pass.

## Phase 7 security-review hardening (2026-09-06, SEC-08/SEC-09)

A fresh-context `veyro-security-reviewer` found and proved three real
bypasses of the tier-enforcement this tool exists to provide:

1. **Label normalization gap (SEC-08).** `EXPECTED_TIER_BY_AGENT` was
   consulted only on an exact dict-key match, so `"veyro-code-reviewer "`
   (trailing space), `"Veyro-Code-Reviewer"` (different case), or an
   omitted label entirely all fell through to the caller-supplied tier
   with no cross-check — reproducing the exact defect N-9 was supposed to
   have closed, via a trivially different string. Fixed: the label is now
   normalized (`.strip().lower()`) before lookup, and the CLI now
   requires it (exits 2 if omitted) so tier is always taken from the
   registered map, never from an unverified caller-supplied string alone.
2. **Row-type/sentinel gap (SEC-09a).** `extract_models` read the
   `model` field off *any* JSON object with a `message` dict, not just
   `type: "assistant"` rows — a crafted `type: "user"` row with a
   spoofed `model` field would count. Fixed: only `type == "assistant"`
   rows are considered.
3. **`<synthetic>` sentinel misdiagnosis (SEC-09b).** The harness emits
   out-of-band `<synthetic>` rows (e.g. session-limit notices) that are
   not model output at all. The old code folded these into the same
   "inconsistent model values" bucket as a genuine substitution, so
   running this tool against any main/orchestrating-session transcript
   that had ever hit a rate limit produced a false "possible
   substitution/fallback" diagnosis. Fixed: `<synthetic>` rows are now
   explicitly ignored (not appended to `models` at all) rather than
   treated as a distinct-but-real model value.
4. **Unreadable-transcript gap (SEC-09c).** A missing/unreadable path
   previously raised a bare `FileNotFoundError`/`OSError` traceback
   instead of this tool's own `BLOCKED:` convention. Fixed: file access
   is wrapped and emits the standard verdict shape on any I/O error.
5. **Memory amplification (PERF-03, `veyro-performance-reviewer`).** The
   tool previously did `Path(path).read_text()` + `.splitlines()`,
   materializing the whole transcript plus a full line-list copy —
   measured at ~4.9x RSS amplification (a 25.8 MB transcript peaked at
   142.3 MB RSS). Fixed: the file is now iterated line-by-line via a
   plain `open()` file-object, which `extract_models` already consumed
   one line at a time — O(1) memory instead of O(file size), same
   semantics, no behavior change.
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

# The harness's own out-of-band sentinel for a rate-limit/session notice —
# not a model's output, must never be treated as a distinct model value
# (that was SEC-09b: it produced a false "possible substitution" verdict
# on any transcript that had ever hit a rate limit).
_SYNTHETIC_SENTINEL = "<synthetic>"


def extract_models(lines) -> list[str]:
    """Pull every `model` field from assistant-type JSONL rows in `lines`
    (any iterable of raw text lines — a list from .splitlines(), or an
    open file object for streaming). Tolerant of non-JSON/malformed lines
    (treated as noise, not fatal) — but a transcript with ZERO valid
    model fields is itself a finding. Ignores non-assistant rows (SEC-09a)
    and the harness's own '<synthetic>' sentinel (SEC-09b)."""
    models = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue  # malformed line — not itself proof of substitution, just noise
        if obj.get("type") != "assistant":
            continue
        message = obj.get("message")
        model = message.get("model") if isinstance(message, dict) else None
        if not model or model == _SYNTHETIC_SENTINEL:
            continue
        models.append(model)
    return models


def verify(models: list[str], expected_tier: str, agent_label: str = "") -> dict:
    """Returns a dict: {"verdict": "PASS"|"BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
    "reason": str, "models_observed": [...], "expected_tier": expected_tier}.
    `models` is the already-extracted list from extract_models() — kept as
    a separate parameter (not re-deriving from raw text here) so callers
    can stream a large transcript without holding the whole file in memory
    (PERF-03)."""
    # Enforced 2026-09-05 (second Phase 5 re-review, N-9), hardened 2026-09-06
    # (Phase 7, SEC-08): EXPECTED_TIER_BY_AGENT was defined and never properly
    # enforced against label variation, so a caller could pass a
    # differently-cased or trailing-spaced label and get PASS on a wrong tier.
    # If agent_label names a known role (case/whitespace-normalized), its
    # registered tier is authoritative -- a caller-supplied tier that disagrees
    # with it is itself a finding, not silently accepted.
    normalized_label = (agent_label or "").strip().lower()
    canonical_label = re.sub(r"[^a-z0-9]", "", normalized_label)
    # Hardened 2026-09-06 (Phase 7 re-review, RR-4): the SEC-08 fix above
    # normalized case/whitespace but only cross-checked the tier if the
    # normalized label landed EXACTLY in EXPECTED_TIER_BY_AGENT. A
    # fresh-context re-review proved a one-character-different label
    # (`"veyro_code_reviewer"` — underscores instead of hyphens — or
    # `"veyro-code-reviewer-phase7"` — an extra suffix) still fell
    # straight through to the caller-supplied tier with no cross-check,
    # letting a Sonnet transcript attest clean for an Opus-designated
    # role via a near-miss label. Canonicalizing to alphanumeric-only
    # closes the separator-variant case directly (it becomes an exact
    # canonical match); a canonical label that merely CONTAINS or IS
    # CONTAINED BY a registered role's canonical form (but isn't exactly
    # it) is treated as an ambiguous attempted-but-malformed reference to
    # that role and BLOCKED outright, rather than silently accepted —
    # this must not affect a genuinely distinct/unregistered label (e.g.
    # "main-orchestrating-session-mod000", used for BUG-012/SEC-01
    # evidence), which shares no canonical overlap with any registered
    # role and correctly falls through to the tier check below.
    canonical_registry = {re.sub(r"[^a-z0-9]", "", k): k for k in EXPECTED_TIER_BY_AGENT}
    if normalized_label not in EXPECTED_TIER_BY_AGENT and canonical_label in canonical_registry:
        normalized_label = canonical_registry[canonical_label]  # exact modulo separators
    elif normalized_label not in EXPECTED_TIER_BY_AGENT and canonical_label:
        for canon_key, real_key in canonical_registry.items():
            if canon_key != canonical_label and (canon_key in canonical_label or canonical_label in canon_key):
                return {
                    "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
                    "reason": f"agent_label '{agent_label}' does not exactly match the registered role '{real_key}' but closely resembles it — refusing to verify an ambiguous near-miss label. Use the exact registered name, or a clearly distinct label for an unregistered/ad-hoc session.",
                    "models_observed": [], "expected_tier": expected_tier,
                }
    if normalized_label in EXPECTED_TIER_BY_AGENT:
        registered_tier = EXPECTED_TIER_BY_AGENT[normalized_label]
        if registered_tier != expected_tier.lower():
            return {
                "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
                "reason": f"Caller-supplied expected_tier '{expected_tier}' disagrees with the registered tier '{registered_tier}' for agent '{agent_label}' in EXPECTED_TIER_BY_AGENT — refusing to verify against a possibly-wrong tier.",
                "models_observed": [], "expected_tier": expected_tier,
            }
    if not models:
        return {
            "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
            "reason": f"No assistant-turn model field found in transcript for {agent_label or 'agent'} — cannot verify runtime identity at all.",
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
    if len(sys.argv) < 4:
        print("Usage: mr_verify.py <transcript_file> <expected_tier: opus|sonnet> <agent_label>")
        print("agent_label is mandatory (2026-09-06, SEC-08): tier is taken from")
        print("EXPECTED_TIER_BY_AGENT, never from an unverified caller-supplied string alone.")
        sys.exit(2)
    path, expected_tier, agent_label = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            models = extract_models(fh)
    except OSError as e:
        result = {
            "verdict": "BLOCKED: MODEL_ASSURANCE_UNVERIFIED",
            "reason": f"Could not read transcript file '{path}': {e}",
            "models_observed": [], "expected_tier": expected_tier,
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)
    result = verify(models, expected_tier, agent_label)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
