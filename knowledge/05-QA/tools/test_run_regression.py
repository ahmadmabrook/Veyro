"""Regression tests for run_regression.py (BUG-044, 2026-10-01): the
retired-CAP-007 test_bash_guard.py suite must be excluded from the
aggregate gate, not run as though it can still pass, while continuing to
fail closed if CAP-007 is ever reinstated.
Run: backend/.venv/bin/python -m pytest <this file> -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_regression as rr

PASS_CMD = ["python3", "-c", "import sys; sys.exit(0)"]
FAIL_CMD = ["python3", "-c", "import sys; sys.exit(1)"]


def test_retired_capability_excludes_its_suite_as_na():
    checks = [("verify_baselines.py", PASS_CMD), ("test_bash_guard.py", FAIL_CMD)]
    results = rr.run_all(checks, retired_ids={"CAP-007"})
    by_name = {name: (ok, summary) for name, ok, summary in results}
    assert by_name["test_bash_guard.py"][0] is None, "retired-capability suite must be excluded (ok=None), not run"
    assert "RETIRED" in by_name["test_bash_guard.py"][1]
    assert "OWN-006" in by_name["test_bash_guard.py"][1] and "ADR-007" in by_name["test_bash_guard.py"][1]
    assert by_name["verify_baselines.py"][0] is True, "unrelated checks must still actually run"


def test_na_result_not_counted_in_all_pass_or_tally():
    checks = [("verify_baselines.py", PASS_CMD), ("test_bash_guard.py", FAIL_CMD)]
    results = rr.run_all(checks, retired_ids={"CAP-007"})
    scored = [(n, ok, s) for n, ok, s in results if ok is not None]
    assert len(scored) == 1
    assert all(ok for _, ok, _ in scored), "a real FAIL under the excluded suite must not poison the aggregate"


def test_reinstated_capability_resumes_real_gating_and_fails_closed():
    # CAP-007 NOT in retired_ids -- simulates reinstatement. The suite must
    # actually run again and participate in pass/fail like any other check.
    checks = [("test_bash_guard.py", FAIL_CMD)]
    results = rr.run_all(checks, retired_ids=set())
    name, ok, summary = results[0]
    assert ok is False, "once not retired, the suite must be actually executed and must fail closed on a real failure"
    assert ok is not None


def test_reinstated_capability_passes_through_a_real_pass():
    checks = [("test_bash_guard.py", PASS_CMD)]
    results = rr.run_all(checks, retired_ids=set())
    name, ok, summary = results[0]
    assert ok is True


def test_only_the_named_suite_is_retirement_eligible():
    # A capability other than CAP-007 being retired must not exempt
    # unrelated checks -- only RETIRED_SUITE_FOR_CAPABILITY's own mapping.
    checks = [("verify_baselines.py", FAIL_CMD)]
    results = rr.run_all(checks, retired_ids={"CAP-001", "CAP-002"})
    name, ok, summary = results[0]
    assert ok is False, "unrelated checks must still fail closed regardless of unrelated retirements"


def test_retired_capability_ids_reads_live_registry():
    ids = rr.retired_capability_ids()
    assert "CAP-007" in ids, "the real registry currently marks CAP-007 RETIRED -- this must be read live, not hardcoded"


# ---- BUG-045: run_regression.py's own wiring to the shared lifecycle resolver ----

def test_retired_capability_ids_reports_no_conflicts_for_real_registry():
    conflicts: list = []
    ids = rr.retired_capability_ids(conflicts)
    assert conflicts == [], f"real registry must resolve cleanly, got {conflicts}"
    assert "CAP-007" in ids


def test_retired_capability_ids_only_returns_retired_bucket(monkeypatch, tmp_path):
    fake_registry = tmp_path / "CAPABILITY_REGISTRY.md"
    fake_registry.write_text(
        "**CAP-007 status update (2026-09-28): RETIRED.**\n"
        "CAP-007's `lifecycle_status` is now **`REVOKED`**\n"
        "**CAP-005 status update (2026-10-05): REINSTATED.**\n"
        "CAP-005's `lifecycle_status` is now **`ACTIVE`**\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rr.cdc, "REGISTRY", fake_registry)
    conflicts: list = []
    ids = rr.retired_capability_ids(conflicts)
    assert ids == {"CAP-007"}, "only the RETIRED bucket may be returned -- an ACTIVE/reinstated id must not appear"
    assert conflicts == []


def test_unauthorized_marker_does_not_exclude_the_suite(monkeypatch, tmp_path):
    # An unbacked CAP-007 RETIRED marker (no corroborating field sentence)
    # must not exclude test_bash_guard.py -- the suite keeps running/
    # gating normally, and the conflict is surfaced, not swallowed.
    fake_registry = tmp_path / "CAPABILITY_REGISTRY.md"
    fake_registry.write_text("**CAP-007 status update (2026-10-05): RETIRED.**\n", encoding="utf-8")
    monkeypatch.setattr(rr.cdc, "REGISTRY", fake_registry)
    conflicts: list = []
    ids = rr.retired_capability_ids(conflicts)
    assert ids == set()
    assert len(conflicts) == 1

    results = rr.run_all([("test_bash_guard.py", FAIL_CMD)], retired_ids=ids)
    name, ok, summary = results[0]
    assert ok is False, "an unresolved/unauthorized retirement claim must not suppress real gating"



def test_lifecycle_conflict_fails_aggregate_even_when_checks_pass(monkeypatch, tmp_path, capsys):
    registry = tmp_path / "CAPABILITY_REGISTRY.md"
    registry.write_text("**CAP-007 status update (2026-10-05): RETIRED.**\n", encoding="utf-8")
    monkeypatch.setattr(rr.cdc, "REGISTRY", registry)
    monkeypatch.setattr(rr, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rr, "CHECKS", [("verify_baselines.py", PASS_CMD)])
    assert rr.main() == 1, "registry-integrity conflict must fail the aggregate, even if every individual check passes"
    output = capsys.readouterr().out
    assert "[PASS] verify_baselines.py" in output
    assert "LIFECYCLE CONFLICTS (aggregate FAIL" in output
    assert "AGGREGATE RESULT: FAIL (1/1 checks passed)" in output


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_checks_use_invoking_python_interpreter():
    assert all(cmd[0] == sys.executable for _, cmd in rr.CHECKS)
