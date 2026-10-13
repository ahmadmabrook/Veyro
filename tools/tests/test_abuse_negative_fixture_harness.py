"""
Unit tests for tools/abuse_negative_fixture_harness.py (MOD-001, GOV-01-R03/R04
— the card's mandatory Security-scope baseline control "abuse-negative
scenarios"; SCN-MOD001-123).

SCN-MOD001-123's own steps drive tests 1-5: exercise the harness "against a
synthetic abusive-request-shape fixture and a synthetic legitimate one",
expect it to "correctly distinguish the abusive shape from the legitimate
one", and expect that "a request-shape with no matching fixture rule fails
closed (denied, not silently allowed)". Both shapes the scenario names are
covered: the rate-limit-shaped request flood and the parameter-tampering
fixture.

  1. test_legitimate_shapes_are_allowed - the positive: an under-threshold
     request count and an allowlist-conforming payload -> ALLOW, both rule
     kinds, exit 0.
  2. test_request_flood_shape_is_denied - over-threshold request count ->
     DENY, REQUEST_COUNT_OVER_THRESHOLD, deterministically distinct from
     the at-threshold boundary case.
  3. test_parameter_tampering_shape_is_denied - a payload carrying a
     parameter name outside the declared allowlist -> DENY,
     PARAMETER_NOT_IN_ALLOWLIST; a missing declared-required name ->
     DENY, REQUIRED_PARAMETER_MISSING.
  4. test_unknown_unmatched_and_malformed_rules_all_deny - the scenario's
     fail-closed step, across every class: unknown rule kind, missing rule
     /rule kind, declared-inputs mismatch, malformed rule parameters,
     inputs that do not match the declaration, a wrongly-typed input,
     unlabeled fixture, empty case list, non-JSON file, unreadable path.
     Never an ALLOW, never a silent pass.
  5. test_report_does_not_echo_payload_values - the proof: a payload whose
     values are a distinctive sentinel is classified and reported, and the
     sentinel appears nowhere in the rendered report or CLI output.
  6. test_cli_exit_code_matches_verdict - `main()` driven as a real
     subprocess: exit 0 on the legitimate fixture, exit 1 on each abusive
     one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from abuse_negative_fixture_harness import (
    FIXTURE_KIND,
    RULE_PARAMETER_ALLOWLIST,
    RULE_REQUEST_COUNT_THRESHOLD,
    VERDICT_ALLOW,
    VERDICT_DENY,
    classify_case,
    classify_fixture,
    main,
    render_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HARNESS_SCRIPT = REPO_ROOT / "tools" / "abuse_negative_fixture_harness.py"

# A distinctive, explicitly-synthetic sentinel: never credential-shaped, and
# chosen so test 5 can prove the report never republishes a payload value.
SENTINEL_VALUE = "SYNTHETIC-SENTINEL-VALUE-DO-NOT-ECHO"

THRESHOLD_RULE = {
    "kind": RULE_REQUEST_COUNT_THRESHOLD,
    "declared_inputs": ["observed_request_count", "observed_window_seconds"],
    "max_requests_per_window": 10,
    "window_seconds": 60,
}
ALLOWLIST_RULE = {
    "kind": RULE_PARAMETER_ALLOWLIST,
    "declared_inputs": ["payload"],
    "allowed_parameters": ["resource_id", "quantity"],
    "required_parameters": ["resource_id"],
}


def _fixture(rule: dict, cases: list[dict], **overrides) -> dict:
    fixture = {
        "fixture_kind": FIXTURE_KIND,
        "synthetic": True,
        "fixture_id": "SYNTHETIC-FIXTURE-001",
        "rule": rule,
        "cases": cases,
    }
    fixture.update(overrides)
    return fixture


def _counts(count: int, *, window: int = 60) -> dict:
    return {"observed_request_count": count, "observed_window_seconds": window}


def _assert_denied(classification, code: str) -> None:
    assert classification.verdict == VERDICT_DENY, classification
    assert classification.code == code, classification


def test_legitimate_shapes_are_allowed():
    under_threshold = classify_case(THRESHOLD_RULE, {"inputs": _counts(9)}, case_id="legit-rate")
    assert under_threshold.verdict == VERDICT_ALLOW, under_threshold
    assert under_threshold.code == "WITHIN_REQUEST_THRESHOLD"

    conforming = classify_case(
        ALLOWLIST_RULE,
        {"inputs": {"payload": {"resource_id": "SYNTHETIC-1", "quantity": 2}}},
        case_id="legit-params",
    )
    assert conforming.verdict == VERDICT_ALLOW, conforming
    assert conforming.code == "PARAMETERS_WITHIN_ALLOWLIST"

    report = classify_fixture(
        _fixture(
            THRESHOLD_RULE,
            [{"case_id": "legit-rate", "expected": VERDICT_ALLOW, "inputs": _counts(9)}],
        )
    )
    assert report.problems == [], report.problems
    assert "PASS" in render_report(report, path=Path("fixture.json"))


def test_request_flood_shape_is_denied():
    flood = classify_case(THRESHOLD_RULE, {"inputs": _counts(500)}, case_id="flood")
    _assert_denied(flood, "REQUEST_COUNT_OVER_THRESHOLD")
    assert "500 request(s) in 60s" in flood.detail

    # Deterministic boundary: at the limit allows, one over denies.
    assert classify_case(THRESHOLD_RULE, {"inputs": _counts(10)}).verdict == VERDICT_ALLOW
    assert classify_case(THRESHOLD_RULE, {"inputs": _counts(11)}).verdict == VERDICT_DENY

    # An observed window the rule never declared cannot be compared -> DENY.
    _assert_denied(
        classify_case(THRESHOLD_RULE, {"inputs": _counts(1, window=1)}), "WINDOW_MISMATCH"
    )

    report = classify_fixture(
        _fixture(
            THRESHOLD_RULE,
            [{"case_id": "flood", "expected": VERDICT_DENY, "inputs": _counts(500)}],
        )
    )
    assert report.problems == [], report.problems
    assert report.classifications[0].verdict == VERDICT_DENY


def test_parameter_tampering_shape_is_denied():
    tampered = classify_case(
        ALLOWLIST_RULE,
        {"inputs": {"payload": {"resource_id": "SYNTHETIC-1", "is_admin": True}}},
        case_id="tampered",
    )
    _assert_denied(tampered, "PARAMETER_NOT_IN_ALLOWLIST")
    assert "is_admin" in tampered.detail

    _assert_denied(
        classify_case(ALLOWLIST_RULE, {"inputs": {"payload": {"quantity": 2}}}),
        "REQUIRED_PARAMETER_MISSING",
    )
    _assert_denied(
        classify_case(ALLOWLIST_RULE, {"inputs": {"payload": ["resource_id"]}}),
        "MALFORMED_INPUT",
    )

    report = classify_fixture(
        _fixture(
            ALLOWLIST_RULE,
            [
                {
                    "case_id": "tampered",
                    "expected": VERDICT_DENY,
                    "inputs": {"payload": {"resource_id": "SYNTHETIC-1", "is_admin": True}},
                }
            ],
        )
    )
    assert report.problems == [], report.problems


def test_unknown_unmatched_and_malformed_rules_all_deny():
    # Unknown, missing, and non-object rules: every case under them is denied.
    for rule in (
        {"kind": "sql_injection_heuristic", "declared_inputs": ["payload"]},
        {"declared_inputs": ["payload"]},
        {"kind": "", "declared_inputs": ["payload"]},
        "not-an-object",
        None,
    ):
        _assert_denied(classify_case(rule, {"inputs": _counts(1)}), "UNUSABLE_RULE")

    # Declared inputs that are not what the rule kind actually reads.
    drifted = dict(THRESHOLD_RULE, declared_inputs=["observed_request_count"])
    unusable = classify_case(drifted, {"inputs": _counts(1)})
    _assert_denied(unusable, "UNUSABLE_RULE")
    assert "DECLARED_INPUTS_MISMATCH" in unusable.detail

    # Malformed rule parameters.
    for bad in (
        dict(THRESHOLD_RULE, max_requests_per_window=0),
        dict(THRESHOLD_RULE, window_seconds="60"),
        dict(ALLOWLIST_RULE, allowed_parameters=[]),
        dict(ALLOWLIST_RULE, required_parameters=["not_in_allowlist"]),
    ):
        _assert_denied(classify_case(bad, {"inputs": _counts(1)}), "UNUSABLE_RULE")

    # Inputs that do not match the declaration exactly, and bad input types.
    _assert_denied(
        classify_case(THRESHOLD_RULE, {"inputs": _counts(1) | {"client_ip": "x"}}),
        "INPUTS_DO_NOT_MATCH_DECLARATION",
    )
    _assert_denied(
        classify_case(THRESHOLD_RULE, {"inputs": {"observed_request_count": 1}}),
        "INPUTS_DO_NOT_MATCH_DECLARATION",
    )
    _assert_denied(classify_case(THRESHOLD_RULE, {"inputs": _counts(-1)}), "MALFORMED_INPUT")
    _assert_denied(
        classify_case(THRESHOLD_RULE, {"inputs": {**_counts(1), "observed_request_count": True}}),
        "MALFORMED_INPUT",
    )
    _assert_denied(classify_case(THRESHOLD_RULE, {"inputs": []}), "MALFORMED_CASE")
    _assert_denied(classify_case(THRESHOLD_RULE, "not-a-case"), "MALFORMED_CASE")

    # Fixture-level fail-closed classes, each a problem list, never a pass.
    legit_case = [{"case_id": "c", "expected": VERDICT_ALLOW, "inputs": _counts(1)}]
    unlabeled = classify_fixture(_fixture(THRESHOLD_RULE, legit_case, fixture_kind="other"))
    assert any("FIXTURE_NOT_LABELED_SYNTHETIC" in p for p in unlabeled.problems)
    not_synthetic = classify_fixture(_fixture(THRESHOLD_RULE, legit_case, synthetic="true"))
    assert any("FIXTURE_NOT_LABELED_SYNTHETIC" in p for p in not_synthetic.problems)
    assert any(
        "UNKNOWN_RULE_KIND" in p
        for p in classify_fixture(
            _fixture({"kind": "nope", "declared_inputs": []}, legit_case)
        ).problems
    )
    assert any("NO_CASES" in p for p in classify_fixture(_fixture(THRESHOLD_RULE, [])).problems)
    assert any("MALFORMED_FIXTURE" in p for p in classify_fixture(["not", "an", "object"]).problems)

    # A case that omits its own expected verdict, and one whose expectation is
    # contradicted by the harness: both recorded as problems.
    no_expectation = classify_fixture(
        _fixture(THRESHOLD_RULE, [{"case_id": "c", "inputs": _counts(1)}])
    )
    assert any("MISSING_EXPECTED_VERDICT" in p for p in no_expectation.problems)
    mismatch = classify_fixture(
        _fixture(
            THRESHOLD_RULE,
            [{"case_id": "c", "expected": VERDICT_ALLOW, "inputs": _counts(999)}],
        )
    )
    assert any("VERDICT_MISMATCH" in p for p in mismatch.problems)
    assert "MISMATCH" in render_report(mismatch, path=Path("fixture.json"))

    # Unreadable and non-JSON files deny rather than classifying nothing.
    with tempfile.TemporaryDirectory() as tmp:
        bad_json = Path(tmp) / "broken.json"
        bad_json.write_text("{not json", encoding="utf-8")
        assert main([str(bad_json)]) == 1
        assert main([str(Path(tmp) / "absent.json")]) == 1


def test_report_does_not_echo_payload_values():
    fixture = _fixture(
        ALLOWLIST_RULE,
        [
            {
                "case_id": "tampered",
                "expected": VERDICT_DENY,
                "inputs": {"payload": {"resource_id": SENTINEL_VALUE, "is_admin": SENTINEL_VALUE}},
            }
        ],
    )
    report = classify_fixture(fixture)
    assert report.problems == [], report.problems
    rendered = render_report(report, path=Path("fixture.json"))
    # The offending parameter *name* is reported; no payload value is.
    assert "is_admin" in rendered
    assert SENTINEL_VALUE not in rendered
    assert SENTINEL_VALUE not in report.classifications[0].detail

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tampering.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(HARNESS_SCRIPT), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert SENTINEL_VALUE not in completed.stdout + completed.stderr


def test_cli_exit_code_matches_verdict():
    distinguishing = _fixture(
        THRESHOLD_RULE,
        [
            {"case_id": "legit", "expected": VERDICT_ALLOW, "inputs": _counts(9)},
            {"case_id": "flood", "expected": VERDICT_DENY, "inputs": _counts(500)},
        ],
    )
    unknown_rule = _fixture(
        {"kind": "unmatched_shape", "declared_inputs": ["payload"]},
        [{"case_id": "c", "expected": VERDICT_ALLOW, "inputs": {"payload": {}}}],
    )

    with tempfile.TemporaryDirectory() as tmp:
        for name, fixture, expected_exit in (
            ("distinguishing.json", distinguishing, 0),
            ("unknown_rule.json", unknown_rule, 1),
        ):
            path = Path(tmp) / name
            path.write_text(json.dumps(fixture), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(HARNESS_SCRIPT), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == expected_exit, completed.stdout + completed.stderr
            assert "SCN-MOD001-123" in completed.stdout
