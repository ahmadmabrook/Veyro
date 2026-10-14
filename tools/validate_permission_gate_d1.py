#!/usr/bin/env python3
"""
ADR-014 D1 four-state disposition for TSD §24.1 gate 4 (permission lint).

`validate_architecture_gates.py --gate permission` reports ADR-009's three
statuses plus INCONCLUSIVE, and maps INCONCLUSIVE to exit 2 -- the same code
as ERROR. A valid zero-operation registry (`{"version": 2, "permissions":
{}}` plus an empty `contracts/openapi/`) is therefore indistinguishable, by
status or by exit code, from an unreadable input. ADR-014 D1 requires gate 4
to report exactly one of PASS | FAIL | ERROR | NOT_APPLICABLE, where
NOT_APPLICABLE is the CI-visible disposition of ADR-009 D2's INCONCLUSIVE
(vacuous) and is permitted only when all three of D1's conditions hold.

This module is that disposition adapter and nothing else. It calls
`run_permission_gate` unchanged and maps its report; it does not re-implement
or relax any ADR-009 check, and it does not touch the shared `_finish`
status/exit semantics or any other gate. Every state other than PASS and a
fully qualified NOT_APPLICABLE is non-zero.

## D1's three conditions, as implemented

1. **Inputs exist and parse.** Delegated entirely to the gate: a missing,
   symlinked or unparseable `--registry`, a bad `--openapi-dir`, or any other
   `PERMISSION_GATE_INPUT_INVALID` is reported by the gate as ERROR and is
   ERROR here (exit 2). Nothing else is inspected in that case.
2. **Zero real items, with a printed reason.** The in-scope real-item count
   is the number of API operations the gate actually checked
   (`len(report.checked)`). NOT_APPLICABLE needs that count to be exactly 0
   *and* the gate's own `PERMISSION_GATE_VACUOUS` violation to be the only
   one present. The count and a machine-readable `reason=` token are printed
   on the first line of every run, in text and JSON mode alike.
3. **Fixture self-test in the same run.** Before any NOT_APPLICABLE or PASS
   is reported, this process runs the gate twice more, in-process, against
   the two committed fixtures under `tools/fixtures/permission-gate-d1/`:
   the conforming fixture must come back PASS, and the deliberate-violation
   fixture must come back FAIL *with* `UNREGISTERED_PERMISSION`. Running in
   one process is what makes this the same job by construction, so no CI
   wiring is required for condition 3 to be genuinely satisfied. If either
   outcome is absent -- including because a fixture is missing, unreadable,
   mutated into a mere input ERROR, or emptied into a vacuous INCONCLUSIVE --
   the result is FAIL, per D1 condition 3's own wording.

Vacuous input never yields PASS, and NOT_APPLICABLE is never reported as or
collapsed into PASS: it carries its own state string and its own exit code.
A gate run with any real operation in scope is dispositioned on the gate's
own verdict over every such operation (ADR-014 D1: no partial
NOT_APPLICABLE within gate 4).

## Exit codes

    0  PASS             real operations in scope, gate found no violation,
                        fixture self-test satisfied
    1  FAIL             gate violations, or D1 conditions 2/3 not met
    2  ERROR            gate input fault, or an unexpected gate status
    4  NOT_APPLICABLE   qualified under D1 conditions 1-3

A required status check may treat exit 4 as non-blocking; it must not treat
exit 4 as a PASS, and must not treat any other non-zero exit as passing.

## What this does not do

It is not a gate-4 PASS, not architecture-gate credit, and not the ADR-014
D1 CI wiring: no workflow invokes it yet, and the C05 aggregate that must
consume the four states does not exist. A NOT_APPLICABLE here means only
"gate 4 had nothing real to check, and proved on this run that it still
catches a planted violation".
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_architecture_gates import (  # import follows the sys.path bootstrap above
    DEFAULT_OPENAPI_DIR,
    DEFAULT_REGISTRY,
    ERROR,
    FAIL,
    INCONCLUSIVE,
    PASS,
    REPO_ROOT,
    GateReport,
    run_permission_gate,
)

NOT_APPLICABLE = "NOT_APPLICABLE"
D1_STATES = (PASS, FAIL, ERROR, NOT_APPLICABLE)
D1_EXIT_CODES = {PASS: 0, FAIL: 1, ERROR: 2, NOT_APPLICABLE: 4}

# The gate's own vacuous code, from `_finish`'s `{GATE}_GATE_VACUOUS` scheme.
# Restated rather than derived so a future rename of that scheme cannot
# silently widen what this adapter accepts as proof of zero real items.
VACUOUS_CODE = "PERMISSION_GATE_VACUOUS"
# The ADR-009 D3/D4 per-operation failure code the deliberate-violation
# fixture must produce. A fixture that fails for any other reason (a parse
# fault, say) does not demonstrate that the permission check itself bites.
VIOLATION_CODE = "UNREGISTERED_PERMISSION"

DEFAULT_FIXTURE_DIR = REPO_ROOT / "tools" / "fixtures" / "permission-gate-d1"
CONFORMING_FIXTURE = "conforming"
VIOLATING_FIXTURE = "violating"

# Machine-readable `reason=` tokens. Each state has exactly one reason, and
# each reason names the condition that decided it.
REASON_REAL_OPERATIONS_CONFORM = "REAL_OPERATIONS_CONFORM"
REASON_ZERO_REAL_OPERATIONS = "ZERO_REAL_OPERATIONS"
REASON_GATE_VIOLATIONS = "GATE_VIOLATIONS"
REASON_SELF_TEST_NOT_SATISFIED = "SELF_TEST_NOT_SATISFIED"
REASON_VACUOUS_WITHOUT_ZERO_ITEM_PROOF = "VACUOUS_WITHOUT_ZERO_ITEM_PROOF"
REASON_GATE_INPUT_ERROR = "GATE_INPUT_ERROR"
REASON_UNEXPECTED_GATE_STATUS = "UNEXPECTED_GATE_STATUS"


@dataclass(frozen=True)
class SelfTestResult:
    """Outcome of D1 condition 3's in-process fixture self-test."""

    conforming_status: str
    violating_status: str
    violating_codes: tuple[str, ...]
    satisfied: bool
    detail: str


@dataclass(frozen=True)
class D1Result:
    state: str
    reason: str
    real_operations: int
    gate_status: str
    gate_codes: tuple[str, ...]
    self_test: SelfTestResult
    notes: tuple[str, ...] = field(default=())

    @property
    def exit_code(self) -> int:
        return D1_EXIT_CODES[self.state]

    def status_line(self) -> str:
        """D1 condition 2's machine-readable line. Always printed, every run."""
        return (f"PERMISSION_GATE_D1_STATE={self.state} reason={self.reason} "
                f"real_operations={self.real_operations}")

    def self_test_line(self) -> str:
        return (f"PERMISSION_GATE_D1_SELF_TEST="
                f"{'SATISFIED' if self.self_test.satisfied else 'NOT_SATISFIED'} "
                f"conforming={self.self_test.conforming_status} "
                f"violating={self.self_test.violating_status}")

    def render(self) -> str:
        lines = [self.status_line(), self.self_test_line(),
                 f"gate status: {self.gate_status}"
                 + (f" ({', '.join(self.gate_codes)})" if self.gate_codes else ""),
                 f"self-test: {self.self_test.detail}"]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps({
            "state": self.state,
            "reason": self.reason,
            "real_operations": self.real_operations,
            "gate_status": self.gate_status,
            "gate_codes": list(self.gate_codes),
            "self_test": {
                "satisfied": self.self_test.satisfied,
                "conforming_status": self.self_test.conforming_status,
                "violating_status": self.self_test.violating_status,
                "violating_codes": list(self.self_test.violating_codes),
                "detail": self.self_test.detail,
            },
            "notes": list(self.notes),
        }, indent=2, sort_keys=True)


def _fixture_report(fixture_dir: Path, name: str, resolver_root: Path) -> GateReport:
    """Run the unmodified gate against one committed fixture.

    A fixture whose paths are missing or symlinked reaches the gate's own
    input checks and comes back ERROR, which `run_self_test` then treats as
    an unmet outcome. Nothing here pre-validates the fixture tree, so this
    adapter cannot accidentally become a second, weaker copy of the gate's
    input contract.
    """
    root = fixture_dir / name
    return run_permission_gate(root / "openapi", root / "registry.json", resolver_root)


def run_self_test(fixture_dir: Path = DEFAULT_FIXTURE_DIR,
                  resolver_root: Path = REPO_ROOT) -> SelfTestResult:
    """ADR-014 D1 condition 3, in this process.

    The conforming fixture must PASS and the deliberate-violation fixture
    must FAIL citing `UNREGISTERED_PERMISSION`. Anything else -- including an
    exception escaping the gate -- is an unmet outcome, never a satisfied
    self-test.
    """
    try:
        conforming = _fixture_report(fixture_dir, CONFORMING_FIXTURE, resolver_root)
        violating = _fixture_report(fixture_dir, VIOLATING_FIXTURE, resolver_root)
    except Exception as exc:  # noqa: BLE001 -- an escaped throw is an unmet outcome, not a pass.
        return SelfTestResult("UNAVAILABLE", "UNAVAILABLE", (), False,
                              f"self-test could not run: {type(exc).__name__}: {exc}")

    return judge_self_test(conforming, violating)


def judge_self_test(conforming: GateReport, violating: GateReport) -> SelfTestResult:
    """Decide whether two fixture reports meet D1 condition 3's both-outcomes bar.

    Split out from `run_self_test` so the bar itself is unit-testable against
    report shapes a committed fixture cannot currently produce. In particular
    the `VIOLATION_CODE` arm: gate 4's only per-operation failure code is
    `UNREGISTERED_PERMISSION` today (every other fault is ERROR), so no
    fixture mutation reaches that arm. It is kept because "the fixture
    FAILed" and "the permission check bit" are not the same claim, and a
    future ADR-009 failure code would separate them.
    """
    conforming_status, violating_status = conforming.status, violating.status
    violating_codes = tuple(sorted(violating.codes()))
    problems = []
    if conforming_status != PASS:
        problems.append(f"conforming fixture reported {conforming_status}, expected {PASS}")
    if violating_status != FAIL:
        problems.append(f"deliberate-violation fixture reported {violating_status}, "
                        f"expected {FAIL}")
    elif VIOLATION_CODE not in violating_codes:
        problems.append(f"deliberate-violation fixture FAILed without {VIOLATION_CODE} "
                        f"(codes: {', '.join(violating_codes) or 'none'})")
    if problems:
        return SelfTestResult(conforming_status, violating_status, violating_codes, False,
                              "; ".join(problems))
    return SelfTestResult(
        conforming_status, violating_status, violating_codes, True,
        f"conforming fixture {PASS} and deliberate-violation fixture {FAIL} "
        f"({VIOLATION_CODE}) in this run",
    )


def evaluate_d1(report: GateReport, self_test: SelfTestResult) -> D1Result:
    """Map one gate report plus one self-test outcome onto ADR-014 D1's four states.

    Decision order is deliberate and fail-closed: an input fault outranks
    everything (nothing downstream is trustworthy), then real violations,
    then D1 condition 3, and only then the two permitted green-ish states.
    """
    real = len(report.checked)
    codes = tuple(sorted(report.codes()))
    common = {"real_operations": real, "gate_status": report.status, "gate_codes": codes,
              "self_test": self_test}

    if report.status == ERROR:
        return D1Result(ERROR, REASON_GATE_INPUT_ERROR, notes=(
            ("D1 condition 1 (inputs exist and parse) is not met; no further condition "
             "was evaluated."),), **common)
    if report.status == FAIL:
        return D1Result(FAIL, REASON_GATE_VIOLATIONS, notes=(
            (f"gate 4 reported {len(report.violations)} violation(s) over {real} "
             f"operation(s) in scope."),), **common)
    if report.status not in (PASS, INCONCLUSIVE):
        return D1Result(ERROR, REASON_UNEXPECTED_GATE_STATUS, notes=(
            (f"gate 4 returned {report.status!r}, which is outside ADR-009's status set; "
             "refusing to disposition it."),), **common)
    if not self_test.satisfied:
        return D1Result(FAIL, REASON_SELF_TEST_NOT_SATISFIED, notes=(
            ("ADR-014 D1 condition 3: the fixture self-test did not produce both required "
             "outcomes in this run, so neither PASS nor NOT_APPLICABLE may be reported."),),
            **common)
    if report.status == PASS:
        return D1Result(PASS, REASON_REAL_OPERATIONS_CONFORM, notes=(
            f"gate 4 checked {real} real operation(s) and found no violation.",), **common)
    # INCONCLUSIVE: ADR-009 D2's vacuous leg. Qualified only on D1 condition 2.
    if real == 0 and codes == (VACUOUS_CODE,):
        return D1Result(NOT_APPLICABLE, REASON_ZERO_REAL_OPERATIONS, notes=(
            ("ADR-014 D1 conditions 1-3 are met: inputs parsed, zero real operations are in "
             "scope, and the fixture self-test produced both outcomes in this run."),
            ("NOT_APPLICABLE is not a PASS and is not gate-4 credit; it records only that "
             "gate 4 had zero real operations in scope on this run."),), **common)
    return D1Result(FAIL, REASON_VACUOUS_WITHOUT_ZERO_ITEM_PROOF, notes=(
        (f"gate 4 reported {INCONCLUSIVE} with {real} operation(s) in scope and codes "
         f"{list(codes)}; D1 condition 2 requires exactly zero real operations evidenced by "
         f"{VACUOUS_CODE} alone."),), **common)


def run_gate4_d1(openapi_dir: Path = DEFAULT_OPENAPI_DIR,
                 registry_path: Path = DEFAULT_REGISTRY,
                 fixture_dir: Path = DEFAULT_FIXTURE_DIR,
                 resolver_root: Path = REPO_ROOT) -> D1Result:
    """Run gate 4 over the real inputs, run D1's self-test, and disposition both."""
    report = run_permission_gate(openapi_dir, registry_path, resolver_root)
    return evaluate_d1(report, run_self_test(fixture_dir, resolver_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ADR-014 D1 four-state disposition for TSD §24.1 gate 4 (permission lint)")
    parser.add_argument("--openapi-dir", type=Path, default=DEFAULT_OPENAPI_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR,
                        help="root holding the conforming/ and violating/ self-test fixtures "
                             "required by ADR-014 D1 condition 3")
    parser.add_argument("--json", action="store_true", help="emit the disposition as JSON")
    args = parser.parse_args(argv)

    try:
        result = run_gate4_d1(args.openapi_dir, args.registry, args.fixture_dir)
    except Exception as exc:  # noqa: BLE001 -- outermost funnel: never exit 0 without a verdict.
        print(f"PERMISSION_GATE_D1_STATE={ERROR} reason={REASON_UNEXPECTED_GATE_STATUS} "
              f"real_operations=0")
        print(f"error: unexpected {type(exc).__name__} escaped the adapter: {exc}",
              file=sys.stderr)
        return D1_EXIT_CODES[ERROR]
    print(result.to_json() if args.json else result.render())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
