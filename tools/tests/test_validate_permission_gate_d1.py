#!/usr/bin/env python3
"""
Focused tests for tools/validate_permission_gate_d1.py (MOD-001, GOV-01-R04 —
ADR-014 D1 four-state disposition of TSD §24.1 gate 4).

Four axes, per the D1 contract:

* positive  — real conforming operations in scope report PASS/0;
* negative  — real violations, and each unmet D1 condition, report FAIL/1;
* vacuous   — a valid zero-operation registry reports NOT_APPLICABLE/4, which
              is the defect this unit exists to fix (the gate alone reports
              INCONCLUSIVE/2, indistinguishable from ERROR), and never PASS;
* error     — a missing/symlinked/unparseable input reports ERROR/2 and stops
              before any other condition is evaluated.

The self-test fixtures are the *committed* ones under
`tools/fixtures/permission-gate-d1/`, exercised here as real files. Mutating
them in a disposable copy is how the tests prove the self-test is
load-bearing rather than decorative.

Run directly (`python3 tools/tests/test_validate_permission_gate_d1.py`) or
with pytest.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from validate_architecture_gates import (
    ERROR,
    FAIL,
    INCONCLUSIVE,
    PASS,
    GateReport,
    Violation,
)
from validate_permission_gate_d1 import (
    CONFORMING_FIXTURE,
    D1_EXIT_CODES,
    D1_STATES,
    DEFAULT_FIXTURE_DIR,
    NOT_APPLICABLE,
    REASON_GATE_INPUT_ERROR,
    REASON_GATE_VIOLATIONS,
    REASON_REAL_OPERATIONS_CONFORM,
    REASON_SELF_TEST_NOT_SATISFIED,
    REASON_UNEXPECTED_GATE_STATUS,
    REASON_VACUOUS_WITHOUT_ZERO_ITEM_PROOF,
    REASON_ZERO_REAL_OPERATIONS,
    VACUOUS_CODE,
    VIOLATING_FIXTURE,
    VIOLATION_CODE,
    evaluate_d1,
    judge_self_test,
    main,
    run_gate4_d1,
    run_self_test,
)

ADAPTER = TOOLS / "validate_permission_gate_d1.py"

EMPTY_REGISTRY = '{"version": 2, "permissions": {}}'


# --- helpers ------------------------------------------------------------------


def _inputs(tmp, registry_text=EMPTY_REGISTRY, docs=None):
    """Build a gate-4 input pair under `tmp`: an openapi dir and a registry."""
    root = Path(tmp)
    openapi = root / "openapi"
    openapi.mkdir()
    (openapi / ".gitkeep").write_text("")
    for name, doc in (docs or {}).items():
        (openapi / name).write_text(doc if isinstance(doc, str) else json.dumps(doc))
    registry = root / "registry.json"
    registry.write_text(registry_text)
    return openapi, registry


def _copy_fixtures(tmp):
    dest = Path(tmp) / "fixtures"
    shutil.copytree(DEFAULT_FIXTURE_DIR, dest)
    return dest


def _report(status, *, checked=(), codes=()):
    return GateReport("permission", status,
                      [Violation(c, "-", "synthetic") for c in codes], list(checked))


def _self_test():
    """The real, unmutated self-test outcome — satisfied, by construction."""
    return run_self_test()


# --- committed fixtures and constants -----------------------------------------


def test_exit_codes_are_distinct_and_only_pass_is_zero():
    assert set(D1_EXIT_CODES) == set(D1_STATES)
    assert len(set(D1_EXIT_CODES.values())) == len(D1_STATES), D1_EXIT_CODES
    assert D1_EXIT_CODES[PASS] == 0
    # NOT_APPLICABLE must never collapse onto PASS's exit code, and must never
    # share ERROR's — sharing ERROR's code is the exact defect being fixed.
    assert D1_EXIT_CODES[NOT_APPLICABLE] not in (0, D1_EXIT_CODES[ERROR])


def test_committed_self_test_fixtures_are_satisfied():
    result = _self_test()
    assert result.satisfied, result.detail
    assert result.conforming_status == PASS, result.detail
    assert result.violating_status == FAIL, result.detail
    assert VIOLATION_CODE in result.violating_codes, result.detail


# --- vacuous: the defect this unit fixes --------------------------------------


def test_valid_zero_operation_registry_is_not_applicable_not_inconclusive():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        result = run_gate4_d1(openapi, registry)
    # The underlying gate still says INCONCLUSIVE — unchanged, deliberately.
    assert result.gate_status == INCONCLUSIVE, result.render()
    assert result.gate_codes == (VACUOUS_CODE,), result.render()
    # The D1 disposition is the four-state one ADR-014 requires.
    assert result.state == NOT_APPLICABLE, result.render()
    assert result.reason == REASON_ZERO_REAL_OPERATIONS
    assert result.real_operations == 0
    assert result.exit_code == D1_EXIT_CODES[NOT_APPLICABLE]
    assert result.exit_code != 0, "NOT_APPLICABLE must not be reported as a PASS"


def test_not_applicable_states_it_is_not_a_pass():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        result = run_gate4_d1(openapi, registry)
    assert result.state == NOT_APPLICABLE
    assert "not a PASS" in " ".join(result.notes)
    assert "not a PASS" in result.render()
    assert "not a PASS" in json.loads(result.to_json())["notes"][1]


def test_status_line_carries_machine_readable_reason_and_zero_count():
    """ADR-014 D1 condition 2: the zero count is *printed* with a reason."""
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        result = run_gate4_d1(openapi, registry)
    assert result.status_line() == (
        f"PERMISSION_GATE_D1_STATE={NOT_APPLICABLE} "
        f"reason={REASON_ZERO_REAL_OPERATIONS} real_operations=0")
    assert result.render().splitlines()[0] == result.status_line()
    assert "SATISFIED" in result.self_test_line()


def test_real_tree_defaults_are_a_committed_qualified_not_applicable():
    """The committed `contracts/` skeletons must themselves qualify.

    ADR-014 D1's consequences require gate 4's empty skeleton inputs to be
    committed; without them the real tree is ERROR, not NOT_APPLICABLE.
    """
    result = run_gate4_d1()
    assert result.state == NOT_APPLICABLE, result.render()
    assert result.real_operations == 0, result.render()


# --- positive ------------------------------------------------------------------


def test_real_conforming_operation_passes():
    with tempfile.TemporaryDirectory() as tmp:
        src = DEFAULT_FIXTURE_DIR / CONFORMING_FIXTURE
        openapi, registry = _inputs(
            tmp, (src / "registry.json").read_text(),
            {"api.json": (src / "openapi" / "api.json").read_text()})
        result = run_gate4_d1(openapi, registry)
    assert result.state == PASS, result.render()
    assert result.reason == REASON_REAL_OPERATIONS_CONFORM
    assert result.real_operations == 1
    assert result.exit_code == 0


# --- negative ------------------------------------------------------------------


def test_real_violation_fails():
    with tempfile.TemporaryDirectory() as tmp:
        src = DEFAULT_FIXTURE_DIR / VIOLATING_FIXTURE
        openapi, registry = _inputs(
            tmp, (src / "registry.json").read_text(),
            {"api.json": (src / "openapi" / "api.json").read_text()})
        result = run_gate4_d1(openapi, registry)
    assert result.state == FAIL, result.render()
    assert result.reason == REASON_GATE_VIOLATIONS
    assert result.gate_codes == (VIOLATION_CODE,)
    assert result.exit_code == 1


def test_a_single_violation_among_conforming_operations_still_fails():
    """ADR-014 D1: there is no partial NOT_APPLICABLE within gate 4."""
    with tempfile.TemporaryDirectory() as tmp:
        good = json.loads((DEFAULT_FIXTURE_DIR / CONFORMING_FIXTURE
                           / "openapi" / "api.json").read_text())
        bad = json.loads((DEFAULT_FIXTURE_DIR / VIOLATING_FIXTURE
                          / "openapi" / "api.json").read_text())
        good["paths"].update(bad["paths"])
        openapi, registry = _inputs(
            tmp, (DEFAULT_FIXTURE_DIR / CONFORMING_FIXTURE / "registry.json").read_text(),
            {"api.json": good})
        result = run_gate4_d1(openapi, registry)
    assert result.state == FAIL, result.render()
    assert result.real_operations == 2, result.render()


# --- negative: D1 condition 3 (the self-test must be load-bearing) ------------


def _mutated_fixture_run(tmp, mutate):
    """Run the adapter over valid empty inputs but a mutated fixture tree."""
    fixtures = _copy_fixtures(tmp)
    mutate(fixtures)
    openapi, registry = _inputs(Path(tmp) / "inputs")
    return run_gate4_d1(openapi, registry, fixtures)


def _assert_self_test_fail(result, *fragments):
    assert result.state == FAIL, result.render()
    assert result.reason == REASON_SELF_TEST_NOT_SATISFIED, result.render()
    assert result.exit_code == 1
    assert not result.self_test.satisfied
    for fragment in fragments:
        assert fragment in result.self_test.detail, result.self_test.detail


def test_missing_fixture_tree_fails_rather_than_qualifying():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        openapi, registry = _inputs(Path(tmp) / "inputs")
        result = run_gate4_d1(openapi, registry, Path(tmp) / "absent-fixtures")
    _assert_self_test_fail(result, "conforming fixture reported")


def test_repaired_violation_fixture_fails_the_self_test():
    """If the planted defect is 'fixed', the self-test no longer proves anything."""
    def repair(fixtures):
        shutil.copy(DEFAULT_FIXTURE_DIR / CONFORMING_FIXTURE / "openapi" / "api.json",
                    fixtures / VIOLATING_FIXTURE / "openapi" / "api.json")

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        result = _mutated_fixture_run(tmp, repair)
    _assert_self_test_fail(result, f"deliberate-violation fixture reported {PASS}")


def test_emptied_conforming_fixture_fails_the_self_test():
    def empty(fixtures):
        (fixtures / CONFORMING_FIXTURE / "openapi" / "api.json").unlink()

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        result = _mutated_fixture_run(tmp, empty)
    _assert_self_test_fail(result, f"conforming fixture reported {INCONCLUSIVE}")


def test_violation_fixture_degraded_to_input_error_fails_the_self_test():
    """A fixture that merely fails to parse does not prove the check bites."""
    def corrupt(fixtures):
        (fixtures / VIOLATING_FIXTURE / "openapi" / "api.json").write_text("{not json")

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        result = _mutated_fixture_run(tmp, corrupt)
    _assert_self_test_fail(result, f"deliberate-violation fixture reported {ERROR}")


def test_every_gate4_fail_cites_unregistered_permission():
    """Pins why the `VIOLATION_CODE` arm is unreachable by fixture mutation.

    Gate 4's only per-operation failure code is `UNREGISTERED_PERMISSION`;
    every other fault is ERROR. So mutating the violation fixture into a
    different *kind* of defect either keeps that code or turns the report into
    an ERROR — it cannot produce a FAIL carrying some other code. The arm is
    unit-tested directly below instead of pretended-covered here.
    """
    def other_defect(fixtures):
        doc = json.loads(
            (fixtures / VIOLATING_FIXTURE / "openapi" / "api.json").read_text())
        op = doc["paths"]["/members/{id}/dossier"]["get"]
        op["x-veyro-permission"]["resource"] = "members.profile"
        del op["x-veyro-authentication"]
        (fixtures / VIOLATING_FIXTURE / "openapi" / "api.json").write_text(json.dumps(doc))

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        result = _mutated_fixture_run(tmp, other_defect)
    assert result.self_test.violating_status in (FAIL, ERROR), result.self_test.detail
    if result.self_test.violating_status == FAIL:
        assert result.self_test.violating_codes == (VIOLATION_CODE,), result.self_test.detail


def test_judge_self_test_rejects_a_fail_without_the_permission_code():
    """FAIL alone is not enough: it must be the ADR-009 permission check."""
    result = judge_self_test(
        _report(PASS, checked=["api.json:GET /x (x)"]),
        _report(FAIL, checked=["api.json:GET /y (y)"], codes=["SOME_OTHER_CODE"]))
    assert not result.satisfied, result.detail
    assert VIOLATION_CODE in result.detail


def test_judge_self_test_accepts_only_the_exact_pair_of_outcomes():
    good_conforming = _report(PASS, checked=["api.json:GET /x (x)"])
    good_violating = _report(FAIL, checked=["api.json:GET /y (y)"], codes=[VIOLATION_CODE])
    assert judge_self_test(good_conforming, good_violating).satisfied
    for conforming in (_report(FAIL, codes=[VIOLATION_CODE]), _report(ERROR),
                       _report(INCONCLUSIVE, codes=[VACUOUS_CODE])):
        assert not judge_self_test(conforming, good_violating).satisfied
    for violating in (_report(PASS, checked=["api.json:GET /y (y)"]), _report(ERROR),
                      _report(INCONCLUSIVE, codes=[VACUOUS_CODE])):
        assert not judge_self_test(good_conforming, violating).satisfied


def test_symlinked_fixture_registry_fails_the_self_test():
    def symlink(fixtures):
        target = fixtures / CONFORMING_FIXTURE / "registry.json"
        real = fixtures / "elsewhere.json"
        target.rename(real)
        target.symlink_to(real)

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        result = _mutated_fixture_run(tmp, symlink)
    _assert_self_test_fail(result, f"conforming fixture reported {ERROR}")


# --- error ---------------------------------------------------------------------


def test_missing_registry_is_error_not_not_applicable():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        registry.unlink()
        result = run_gate4_d1(openapi, registry)
    assert result.state == ERROR, result.render()
    assert result.reason == REASON_GATE_INPUT_ERROR
    assert result.exit_code == 2


def test_unparseable_registry_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp, "{not json")
        result = run_gate4_d1(openapi, registry)
    assert result.state == ERROR, result.render()
    assert result.reason == REASON_GATE_INPUT_ERROR


def test_wrong_version_registry_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp, '{"version": 1, "permissions": {}}')
        result = run_gate4_d1(openapi, registry)
    assert result.state == ERROR, result.render()


def test_missing_openapi_dir_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        shutil.rmtree(openapi)
        result = run_gate4_d1(openapi, registry)
    assert result.state == ERROR, result.render()


def test_input_error_outranks_a_broken_self_test():
    """Condition 1 is evaluated first; nothing downstream is trustworthy."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        openapi, registry = _inputs(Path(tmp) / "inputs")
        registry.unlink()
        result = run_gate4_d1(openapi, registry, Path(tmp) / "absent-fixtures")
    assert result.state == ERROR, result.render()
    assert result.reason == REASON_GATE_INPUT_ERROR
    assert not result.self_test.satisfied


# --- evaluate_d1: the pure mapping, including shapes the gate cannot emit ------


def test_evaluate_d1_rejects_inconclusive_with_items_in_scope():
    result = evaluate_d1(
        _report(INCONCLUSIVE, checked=["api.json:GET /x (x)"], codes=[VACUOUS_CODE]),
        _self_test())
    assert result.state == FAIL, result.render()
    assert result.reason == REASON_VACUOUS_WITHOUT_ZERO_ITEM_PROOF


def test_evaluate_d1_rejects_inconclusive_without_the_vacuous_code():
    result = evaluate_d1(_report(INCONCLUSIVE, codes=["SOMETHING_ELSE"]), _self_test())
    assert result.state == FAIL, result.render()
    assert result.reason == REASON_VACUOUS_WITHOUT_ZERO_ITEM_PROOF


def test_evaluate_d1_rejects_an_unknown_gate_status():
    result = evaluate_d1(_report("SKIPPED"), _self_test())
    assert result.state == ERROR, result.render()
    assert result.reason == REASON_UNEXPECTED_GATE_STATUS
    assert result.exit_code == 2


def test_evaluate_d1_never_returns_a_state_outside_the_four():
    self_test = _self_test()
    for status in (PASS, FAIL, ERROR, INCONCLUSIVE, "SKIPPED", ""):
        for checked in ((), ("api.json:GET /x (x)",)):
            for codes in ((), (VACUOUS_CODE,), ("OTHER",)):
                result = evaluate_d1(_report(status, checked=checked, codes=codes), self_test)
                assert result.state in D1_STATES, (status, checked, codes, result.state)
                if result.state in (PASS, NOT_APPLICABLE):
                    assert result.self_test.satisfied


def test_evaluate_d1_pass_requires_a_satisfied_self_test():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "inputs").mkdir()
        unsatisfied = run_self_test(Path(tmp) / "absent-fixtures")
    assert not unsatisfied.satisfied
    for status, checked in ((PASS, ("api.json:GET /x (x)",)), (INCONCLUSIVE, ())):
        result = evaluate_d1(
            _report(status, checked=checked,
                    codes=(VACUOUS_CODE,) if status == INCONCLUSIVE else ()),
            unsatisfied)
        assert result.state == FAIL, result.render()
        assert result.reason == REASON_SELF_TEST_NOT_SATISFIED


# --- CLI -----------------------------------------------------------------------


def test_cli_exit_codes_match_the_states():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        argv = ["--openapi-dir", str(openapi), "--registry", str(registry)]
        assert main(argv) == D1_EXIT_CODES[NOT_APPLICABLE]
        registry.unlink()
        assert main(argv) == D1_EXIT_CODES[ERROR]


def test_cli_subprocess_prints_the_state_line_and_json():
    with tempfile.TemporaryDirectory() as tmp:
        openapi, registry = _inputs(tmp)
        for extra in ([], ["--json"]):
            proc = subprocess.run(
                [sys.executable, "-I", str(ADAPTER), "--openapi-dir", str(openapi),
                 "--registry", str(registry), *extra],
                capture_output=True, text=True, check=False)
            assert proc.returncode == D1_EXIT_CODES[NOT_APPLICABLE], proc.stderr
            if extra:
                assert json.loads(proc.stdout)["state"] == NOT_APPLICABLE
            else:
                assert proc.stdout.startswith(
                    f"PERMISSION_GATE_D1_STATE={NOT_APPLICABLE} "
                    f"reason={REASON_ZERO_REAL_OPERATIONS}"), proc.stdout


def test_cli_rejects_an_unknown_flag_without_exiting_zero():
    proc = subprocess.run(
        [sys.executable, "-I", str(ADAPTER), "--pretend-this-is-fine"],
        capture_output=True, text=True, check=False)
    assert proc.returncode != 0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(dict(globals()).items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"{failures} failure(s)")
    raise SystemExit(1 if failures else 0)
