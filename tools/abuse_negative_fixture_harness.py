"""
Abuse-negative fixture harness (MOD-001, GOV-01-R03/R04 — the card's mandatory
Security-scope baseline control "abuse-negative scenarios"; SCN-MOD001-123).

Per `REQUIREMENTS.md`'s own "Abuse-negative fixture harness" row (added
Scenario Review round 6, P1-1), MOD-001's obligation is "the fixture
pattern/harness later domain modules will build real abuse scenarios on top
of (MOD-001's own obligation is the harness, not business-flow-specific abuse
content)". `IMPLEMENTATION.md` §6 states the same split explicitly: MOD-001
builds the fixture pattern; "abuse-negative scenario *content* for specific
business flows" belongs to the later domain module that owns that flow.
`IMPLEMENTATION.md` §3's pipeline row names the input as "synthetic
abusive/legitimate request-shape fixtures", the output as "pass/fail
classification", and the evidence artifact as a "classification report". The
upstream authority both files cite is the card's Security-scope baseline
(`EIP_MIRROR.md` lines 4267-4271), cited here secondhand via those two
project files rather than quoted.

## What this is, and deliberately is not

It is a pure, offline classifier over a declarative JSON fixture. It is NOT
an HTTP server, NOT a rate limiter, NOT a production security control, and
NOT a generic rule engine or plugin system — exactly two rule kinds are
supported, both named in SCN-MOD001-123's own steps ("a rate-limit-shaped
request-flood fixture, a parameter-tampering fixture"), and adding a third is
a source change here, not a config/plugin extension point. No future-flow
abuse content lives in this file; that is the owning domain module's work.

## Fixture shape

    {
      "fixture_kind": "synthetic-abuse-negative",   # exact label, required
      "synthetic": true,                            # must be literally true
      "fixture_id": "...",
      "rule": {
        "kind": "request_count_threshold",          # or parameter_allowlist
        "declared_inputs": [...],                   # exactly the keys the
                                                    # rule kind reads
        ...rule parameters...
      },
      "cases": [{"case_id": "...", "expected": "ALLOW"|"DENY",
                 "inputs": {...}}]
    }

`request_count_threshold` (the rate-limit *shape*, not a rate limiter) reads
exactly `observed_request_count` and `observed_window_seconds`, against rule
parameters `max_requests_per_window` and `window_seconds`.

`parameter_allowlist` (the parameter-tampering shape) reads exactly `payload`,
against rule parameters `allowed_parameters` and `required_parameters`. Only
the payload's *key names* are ever read; its values are never inspected.

## Fail-closed, and value-free reporting

Anything the harness cannot fully understand is DENIED, never allowed: an
unreadable or non-JSON file, a fixture missing the synthetic label, a missing
/unknown rule kind, a rule whose `declared_inputs` do not match what that kind
actually reads, malformed rule parameters, a case whose inputs do not match
the declaration exactly, a wrongly-typed input, and an empty case list.

The classification report prints only identifiers (fixture/case ids), rule
kinds and parameters, and parameter *names*. It never prints a payload value,
so a denial cannot republish fixture content into a CI log — the same
constraint `.claude/rules/infra/secrets.md` control 1 puts on committed
fixture content, applied to this tool's output.

This tool never writes to the fixture it reads — read-only, always.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURE_KIND = "synthetic-abuse-negative"

RULE_REQUEST_COUNT_THRESHOLD = "request_count_threshold"
RULE_PARAMETER_ALLOWLIST = "parameter_allowlist"

# The exact input keys each rule kind reads. A fixture must declare these
# verbatim, so a fixture cannot quietly feed an input the rule never consults.
DECLARED_INPUTS: dict[str, tuple[str, ...]] = {
    RULE_REQUEST_COUNT_THRESHOLD: ("observed_request_count", "observed_window_seconds"),
    RULE_PARAMETER_ALLOWLIST: ("payload",),
}
SUPPORTED_RULE_KINDS = tuple(sorted(DECLARED_INPUTS))

VERDICT_ALLOW = "ALLOW"
VERDICT_DENY = "DENY"


@dataclass
class Classification:
    """One case's verdict. `detail` is value-free by construction."""

    case_id: str
    verdict: str
    code: str
    detail: str
    expected: str | None = None


@dataclass
class FixtureReport:
    fixture_id: str = "<unnamed>"
    rule_kind: str = "<unknown>"
    classifications: list[Classification] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_name_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(name, str) for name in value)


def _deny(case_id: str, code: str, detail: str) -> Classification:
    return Classification(case_id, VERDICT_DENY, code, detail)


def _allow(case_id: str, code: str, detail: str) -> Classification:
    return Classification(case_id, VERDICT_ALLOW, code, detail)


def _validate_rule_parameters(kind: str, rule: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if kind == RULE_REQUEST_COUNT_THRESHOLD:
        for name in ("max_requests_per_window", "window_seconds"):
            if not _is_positive_int(rule.get(name)):
                problems.append(f"MALFORMED_RULE_PARAM: `rule.{name}` must be a positive integer")
        return problems

    allowed = rule.get("allowed_parameters")
    required = rule.get("required_parameters")
    if not _is_name_list(allowed) or not allowed:
        problems.append(
            "MALFORMED_RULE_PARAM: `rule.allowed_parameters` must be a non-empty list of "
            "parameter names"
        )
        allowed = []
    if not _is_name_list(required):
        problems.append(
            "MALFORMED_RULE_PARAM: `rule.required_parameters` must be a list of parameter names"
        )
    elif allowed and not set(required) <= set(allowed):
        problems.append(
            "MALFORMED_RULE_PARAM: every `rule.required_parameters` name must also appear in "
            "`rule.allowed_parameters`"
        )
    return problems


def validate_rule(rule: Any) -> tuple[str | None, list[str]]:
    """Returns `(rule_kind, problems)`. A non-empty `problems` list means the
    rule is unusable, so every case under it must be denied rather than
    evaluated."""
    if not isinstance(rule, dict):
        return None, ["MISSING_RULE: fixture has no `rule` object"]
    kind = rule.get("kind")
    if not isinstance(kind, str) or not kind:
        return None, ["MISSING_RULE_KIND: `rule.kind` is absent or not a non-empty string"]
    if kind not in DECLARED_INPUTS:
        return None, [
            (
                f"UNKNOWN_RULE_KIND: {kind!r} is not a supported rule kind "
                f"(supported: {', '.join(SUPPORTED_RULE_KINDS)})"
            )
        ]

    problems: list[str] = []
    declared = rule.get("declared_inputs")
    if not _is_name_list(declared):
        problems.append(
            "MISSING_DECLARED_INPUTS: `rule.declared_inputs` must be a list of input names"
        )
    elif tuple(declared) != DECLARED_INPUTS[kind]:
        problems.append(
            f"DECLARED_INPUTS_MISMATCH: rule kind {kind} reads exactly "
            f"{list(DECLARED_INPUTS[kind])}, fixture declares {list(declared)}"
        )
    problems.extend(_validate_rule_parameters(kind, rule))
    return kind, problems


def _classify_request_count(
    case_id: str, rule: dict[str, Any], inputs: dict[str, Any]
) -> Classification:
    count = inputs["observed_request_count"]
    window = inputs["observed_window_seconds"]
    for name, value in (("observed_request_count", count), ("observed_window_seconds", window)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return _deny(case_id, "MALFORMED_INPUT", f"`{name}` must be a non-negative integer")

    declared_window = rule["window_seconds"]
    if window != declared_window:
        return _deny(
            case_id,
            "WINDOW_MISMATCH",
            f"observed window {window}s does not match the rule's declared {declared_window}s "
            f"window, so the comparison the rule declares cannot be made",
        )

    limit = rule["max_requests_per_window"]
    if count > limit:
        return _deny(
            case_id,
            "REQUEST_COUNT_OVER_THRESHOLD",
            f"{count} request(s) in {window}s exceeds the declared limit of {limit}",
        )
    return _allow(
        case_id,
        "WITHIN_REQUEST_THRESHOLD",
        f"{count} request(s) in {window}s is within the declared limit of {limit}",
    )


def _classify_parameter_allowlist(
    case_id: str, rule: dict[str, Any], inputs: dict[str, Any]
) -> Classification:
    payload = inputs["payload"]
    if not isinstance(payload, dict):
        return _deny(
            case_id,
            "MALFORMED_INPUT",
            "`payload` must be a JSON object of parameter name -> value; only its names are read",
        )

    # Key names only. Payload values are never read and never reported.
    present = sorted(payload)
    tampered = [name for name in present if name not in set(rule["allowed_parameters"])]
    if tampered:
        return _deny(
            case_id,
            "PARAMETER_NOT_IN_ALLOWLIST",
            f"parameter name(s) outside the declared allowlist: {tampered}",
        )

    absent = [name for name in rule["required_parameters"] if name not in payload]
    if absent:
        return _deny(
            case_id,
            "REQUIRED_PARAMETER_MISSING",
            f"declared-required parameter name(s) absent: {absent}",
        )
    return _allow(
        case_id,
        "PARAMETERS_WITHIN_ALLOWLIST",
        f"{len(present)} parameter name(s), all within the declared allowlist",
    )


def classify_case(rule: Any, case: Any, *, case_id: str = "<unnamed>") -> Classification:
    """Public classification entry point for a single synthetic request shape.

    Fail-closed in its own right: an unusable rule, a malformed case, or inputs
    that do not match the rule's own `declared_inputs` exactly all return
    `VERDICT_DENY`. A caller can never obtain an ALLOW from a shape this
    harness did not fully understand."""
    kind, rule_problems = validate_rule(rule)
    if rule_problems or kind is None:
        return _deny(case_id, "UNUSABLE_RULE", "; ".join(rule_problems))
    if not isinstance(case, dict):
        return _deny(case_id, "MALFORMED_CASE", "case must be a JSON object")
    inputs = case.get("inputs")
    if not isinstance(inputs, dict):
        return _deny(case_id, "MALFORMED_CASE", "`inputs` must be a JSON object")

    declared = DECLARED_INPUTS[kind]
    missing = [name for name in declared if name not in inputs]
    undeclared = sorted(name for name in inputs if name not in declared)
    if missing or undeclared:
        return _deny(
            case_id,
            "INPUTS_DO_NOT_MATCH_DECLARATION",
            f"missing={missing} undeclared={undeclared} (names only; values are never read)",
        )

    if kind == RULE_REQUEST_COUNT_THRESHOLD:
        return _classify_request_count(case_id, rule, inputs)
    return _classify_parameter_allowlist(case_id, rule, inputs)


def classify_fixture(fixture: Any) -> FixtureReport:
    """Classify every case in a loaded fixture, recording a problem for each
    case whose verdict disagrees with its own declared `expected` verdict."""
    report = FixtureReport()
    if not isinstance(fixture, dict):
        report.problems.append("MALFORMED_FIXTURE: top level must be a JSON object")
        return report

    fixture_id = fixture.get("fixture_id")
    if isinstance(fixture_id, str) and fixture_id:
        report.fixture_id = fixture_id
    if fixture.get("fixture_kind") != FIXTURE_KIND or fixture.get("synthetic") is not True:
        report.problems.append(
            f"FIXTURE_NOT_LABELED_SYNTHETIC: `fixture_kind` must be {FIXTURE_KIND!r} and "
            f"`synthetic` must be literally true"
        )
        return report

    kind, rule_problems = validate_rule(fixture.get("rule"))
    report.rule_kind = kind or "<unknown>"
    if rule_problems:
        report.problems.extend(rule_problems)
        return report

    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        report.problems.append(
            "NO_CASES: `cases` must be a non-empty list; a fixture with nothing to classify is "
            "denied, never reported as a pass"
        )
        return report

    for index, case in enumerate(cases):
        raw_id = case.get("case_id") if isinstance(case, dict) else None
        case_id = raw_id if isinstance(raw_id, str) and raw_id else f"<case index {index}>"
        expected = case.get("expected") if isinstance(case, dict) else None
        classification = classify_case(fixture["rule"], case, case_id=case_id)
        if expected in (VERDICT_ALLOW, VERDICT_DENY):
            classification.expected = expected
            if classification.verdict != expected:
                report.problems.append(
                    f"{case_id}: VERDICT_MISMATCH: fixture expected {expected}, harness "
                    f"classified {classification.verdict} ({classification.code})"
                )
        else:
            report.problems.append(
                f"{case_id}: MISSING_EXPECTED_VERDICT: `expected` must be {VERDICT_ALLOW!r} or "
                f"{VERDICT_DENY!r}"
            )
        report.classifications.append(classification)
    return report


def load_fixture(path: Path) -> tuple[Any, list[str]]:
    """Read and parse a fixture file, failing closed on anything unreadable or
    not valid JSON rather than returning an empty object."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"UNREADABLE_FIXTURE: {path}: {exc}"]
    try:
        return json.loads(text), []
    except json.JSONDecodeError as exc:
        return None, [f"MALFORMED_FIXTURE: {path}: not valid JSON: {exc}"]


def render_report(report: FixtureReport, *, path: Path) -> str:
    """The classification report (`IMPLEMENTATION.md` §3's evidence artifact).
    Identifiers, rule kinds/parameters and parameter names only — no values."""
    lines = [
        "=" * 70,
        "MOD-001 ABUSE-NEGATIVE FIXTURE HARNESS (GOV-01-R03/R04, SCN-MOD001-123)",
        "=" * 70,
        "",
        f"Fixture file: {path}",
        f"Fixture id:   {report.fixture_id}",
        f"Rule kind:    {report.rule_kind}",
        f"Cases classified: {len(report.classifications)}",
    ]
    if report.classifications:
        lines.append("")
        for item in report.classifications:
            expected = item.expected or "<undeclared>"
            agreement = "match" if item.expected == item.verdict else "MISMATCH"
            lines.append(
                f"  - case={item.case_id} verdict={item.verdict} expected={expected} "
                f"[{agreement}] code={item.code} detail={item.detail}"
            )
    if report.problems:
        lines.extend(["", f"DENY: {len(report.problems)} problem(s) found:"])
        lines.extend(f"  - {problem}" for problem in report.problems)
    else:
        lines.extend(
            [
                "",
                (
                    "PASS - every case classified as the fixture declared; abusive shapes "
                    "denied, legitimate shapes allowed."
                ),
            ]
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Abuse-negative fixture harness (MOD-001, GOV-01-R03/R04, "
        "SCN-MOD001-123). Classifies the synthetic request shapes in an explicitly-"
        "synthetic JSON fixture against that fixture's own declared rule, and prints a "
        "classification report. Dependency-free and offline: no HTTP server and no rate "
        "limiter are involved. Fails closed (exit 1) on anything it cannot fully "
        "understand, and never prints a payload value.",
    )
    p.add_argument(
        "fixture",
        type=Path,
        help="Path to an explicitly-synthetic abuse-negative JSON fixture "
        f"(`fixture_kind: {FIXTURE_KIND}`, `synthetic: true`). Required: the harness has no "
        "default fixture, so it can never pass green over a path nobody named.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path: Path = args.fixture

    fixture, load_problems = load_fixture(path)
    if load_problems:
        report = FixtureReport(problems=load_problems)
    else:
        report = classify_fixture(fixture)

    print(render_report(report, path=path))
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
