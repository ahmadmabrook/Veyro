#!/usr/bin/env python3
r"""
Unit tests for knowledge/05-QA/tools/mr_verify.py (BUG-037 fix, Round 2,
2026-09-29).

Round 1 fixed BUG-037's reported symptom (harness's current Opus id
`claude-opus-5-5` rejected) by widening `_FAMILY_RE` to a shape-matching
regex (`^claude-opus-\d+([.-]\d+)*$`). A fresh-context
`veyro-security-reviewer` found this silently accepts any real,
unqualified id of the right shape (`claude-opus-4-0`, `claude-opus-6-0`,
`claude-sonnet-4-5-20250929`, ...) -- a fail-open regression, worse than
the original fail-closed bug. Round 2 replaces the regex with
`_QUALIFIED_MODELS`, an exact per-tier allowlist. This suite proves the
allowlist fix and that nothing else regressed:

  1. Positive -- only the 3 ids this project has actually confirmed
     qualified (`claude-opus-5`, `claude-opus-5-5`, `claude-sonnet-5`)
     verify PASS, for the bare tier and for each of the 3 ADR-005 agents
     at their correct tier.
  2. Negative -- every id NOT on the allowlist is BLOCKED, even when it
     is real, well-formed, or was accepted by round 1's regex: the
     dot-separated forms (`claude-opus-5.5`, `claude-sonnet-5.5`, never
     independently confirmed as real), `claude-sonnet-5-5` (never
     observed for Sonnet -- only Opus has a "-5-5" id), a real historical
     Opus id (`claude-opus-4-1-20250805`), a plausible next-minor-version
     id (`claude-opus-5-6`), and a trailing-newline variant of a
     qualified id (proves exact-equality membership, no strip/normalize).
  3. Negative (regression) -- claude-opus-9-nonexistent-model-id (the N-9
     fixture) still BLOCKED.
  4. Negative (regression) -- a transcript resolving claude-sonnet-5-5
     against an agent registered opus (veyro-critical-engineer) is
     BLOCKED via the caller-supplied/registered-tier mismatch path (fires
     before the allowlist check, so unaffected by round 2).
  5. Negative (regression) -- a near-miss label for one of the ADR-005
     agents is still BLOCKED as an ambiguous near-miss (also fires before
     the allowlist check).

Run directly with `python3 knowledge/05-QA/tools/tests/test_mr_verify.py`
(no pytest dependency needed) or with pytest.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mr_verify import extract_models, verify


def _transcript_models(model: str, turns: int = 5) -> list[str]:
    """Build `turns` synthetic assistant-type JSONL rows all resolving to
    `model`, write them to a temp file, and run them through the real
    extract_models() file-streaming path -- not a hand-built list -- so
    the test exercises the same code path a real transcript would."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "transcript.jsonl"
        rows = [
            json.dumps({"type": "assistant", "message": {"model": model}})
            for _ in range(turns)
        ]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        with open(path, encoding="utf-8") as fh:
            return extract_models(fh)


# --- 1. Positive: only the 3 confirmed-qualified ids, bare tier + new agents ---

def test_opus_5_5_passes_bare_tier():
    models = _transcript_models("claude-opus-5-5")
    result = verify(models, "opus")
    assert result["verdict"] == "PASS", result


def test_opus_5_passes_bare_tier():
    models = _transcript_models("claude-opus-5")
    result = verify(models, "opus")
    assert result["verdict"] == "PASS", result


def test_opus_5_5_passes_critical_engineer():
    models = _transcript_models("claude-opus-5-5")
    result = verify(models, "opus", "veyro-critical-engineer")
    assert result["verdict"] == "PASS", result


def test_sonnet_5_passes_bare_tier():
    models = _transcript_models("claude-sonnet-5")
    result = verify(models, "sonnet")
    assert result["verdict"] == "PASS", result


def test_sonnet_5_passes_backend_engineer():
    models = _transcript_models("claude-sonnet-5")
    result = verify(models, "sonnet", "veyro-backend-engineer")
    assert result["verdict"] == "PASS", result


def test_sonnet_5_passes_infra_sre_engineer():
    models = _transcript_models("claude-sonnet-5")
    result = verify(models, "sonnet", "veyro-infra-sre-engineer")
    assert result["verdict"] == "PASS", result


# --- 2. Negative: ids not on the allowlist, including real/plausible ones ---

def test_dot_separated_forms_now_blocked():
    # Never independently confirmed as real observed ids -- accepted by
    # the pre-BUG-037 regex only because N-9's hardening pass wrote that
    # pattern defensively, not because dot-form was ever actually seen.
    for model in ("claude-opus-5.5", "claude-sonnet-5.5"):
        tier = model.split("-")[1]
        result = verify([model, model], tier)
        assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", (model, result)


def test_sonnet_5_5_blocked():
    # Only Opus has ever actually resolved to a "-5-5" id in this
    # project. Must not silently pass on family-shape resemblance to the
    # qualified Opus id.
    models = _transcript_models("claude-sonnet-5-5")
    result = verify(models, "sonnet")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result


def test_real_historical_opus_id_blocked():
    # A real historical Opus id, never qualified under this project's
    # current tier check -- proves the allowlist fails closed on real
    # provider ids, not just fabricated ones.
    result = verify(["claude-opus-4-1-20250805"], "opus")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result


def test_plausible_next_minor_version_blocked():
    result = verify(["claude-opus-5-6"], "opus")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result


def test_trailing_newline_not_silently_matched():
    # Proves exact-equality membership through the full extract_models()
    # pipeline: a newline embedded in the model field's own value (not
    # line-level whitespace, which extract_models legitimately strips)
    # must not be stripped/normalized away before the allowlist check.
    models = _transcript_models("claude-opus-5-5\n")
    result = verify(models, "opus")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result


# --- 3. Negative regression: N-9 fabricated-id fixture still BLOCKED ---

def test_n9_fabricated_id_still_blocked():
    result = verify(["claude-opus-9-nonexistent-model-id"], "opus")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result


# --- 4. Negative regression: registered-tier mismatch still fires for a new agent ---

def test_registered_tier_mismatch_blocks_new_agent():
    models = _transcript_models("claude-sonnet-5-5")
    result = verify(models, "sonnet", "veyro-critical-engineer")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result
    assert "disagrees with the registered tier" in result["reason"], result


# --- 5. Negative regression: near-miss ambiguous label still blocked for a new agent ---

def test_near_miss_label_still_blocked_for_new_agent():
    # "veyro-backend-engineer-v2" canonicalizes to a superstring of the
    # registered "veyro-backend-engineer" -- an ambiguous near-miss, not
    # an exact match and not a genuinely distinct label.
    models = _transcript_models("claude-opus-5-5")
    result = verify(models, "opus", "veyro-backend-engineer-v2")
    assert result["verdict"] == "BLOCKED: MODEL_ASSURANCE_UNVERIFIED", result
    assert "ambiguous near-miss label" in result["reason"], result


if __name__ == "__main__":
    test_opus_5_5_passes_bare_tier()
    test_opus_5_passes_bare_tier()
    test_opus_5_5_passes_critical_engineer()
    test_sonnet_5_passes_bare_tier()
    test_sonnet_5_passes_backend_engineer()
    test_sonnet_5_passes_infra_sre_engineer()
    test_dot_separated_forms_now_blocked()
    test_sonnet_5_5_blocked()
    test_real_historical_opus_id_blocked()
    test_plausible_next_minor_version_blocked()
    test_trailing_newline_not_silently_matched()
    test_n9_fabricated_id_still_blocked()
    test_registered_tier_mismatch_blocks_new_agent()
    test_near_miss_label_still_blocked_for_new_agent()
    print("PASS -- all 14 tests passed.")
