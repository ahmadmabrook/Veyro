#!/usr/bin/env python3
"""
Unit test for tools/validate_migration_ordering.py (MOD-001, GOV-01-R06).

Proves both directions against an isolated `tempfile.TemporaryDirectory`
fixture, never a real migrations tree — no real product schema exists yet
(R06's own "OUT of scope" line).

  1. test_empty_directory_passes — no records dir at all -> PASS (no
     product schema exists yet, this is not a missing-directory error).
  2. test_valid_four_phase_change_passes — a real
     expand->migrate->switch->contract sequence for one change_id, every
     TSD §24.2 field present -> PASS.
  3. test_contract_without_switch_fails_closed — the scenario's own
     literal case (a destructive contract-phase migration attempted out
     of order) -> OUT_OF_ORDER_PHASE, naming the change_id and the
     missing prior phase, not a silent partial pass.
  4. test_missing_required_field_fails_closed — a record missing
     `rollback_strategy` -> MISSING_REQUIRED_FIELD, naming the file and
     field.
  5. test_invalid_phase_value_fails_closed — a record with
     `phase: deploy` (not one of the 4 TSD stages) -> INVALID_PHASE.
  6. test_repeated_phase_is_allowed — two `expand` files for the same
     change_id before `migrate` -> PASS (multiple expand steps are a
     real pattern, not an ordering violation).

Run directly with
`python3 tools/tests/test_validate_migration_ordering.py` (no pytest
dependency needed) or with pytest if available.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_migration_ordering import validate_directory

VALID_FIELDS = {
    "owner": "jane@example.com",
    "lock_impact": "none",
    "rollback_strategy": "drop the new object",
    "validation_query": "SELECT 1",
}


def _write_record(root: Path, filename: str, change_id: str, phase: str, **overrides) -> None:
    fields = {"change_id": change_id, "phase": phase, **VALID_FIELDS, **overrides}
    lines = ["---"]
    for key, value in fields.items():
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append("Synthetic fixture record — not a real migration.")
    (root / filename).write_text("\n".join(lines), encoding="utf-8")


def test_empty_directory_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "does_not_exist"
        assert validate_directory(root) == []


def test_valid_four_phase_change_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        _write_record(root, "0003_widget_switch.yaml", "add_widget_column", "switch")
        _write_record(root, "0004_widget_contract.yaml", "add_widget_column", "contract")
        assert validate_directory(root) == []


def test_contract_without_switch_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_migrate.yaml", "add_widget_column", "migrate")
        _write_record(root, "0003_widget_contract.yaml", "add_widget_column", "contract")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "OUT_OF_ORDER_PHASE" in problems[0]
        assert "add_widget_column" in problems[0]
        assert "0003_widget_contract.yaml" in problems[0]


def test_missing_required_field_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(
            root, "0001_widget_expand.yaml", "add_widget_column", "expand",
            rollback_strategy="",
        )
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "MISSING_REQUIRED_FIELD" in problems[0]
        assert "rollback_strategy" in problems[0]


def test_invalid_phase_value_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_deploy.yaml", "add_widget_column", "deploy")
        problems = validate_directory(root)
        assert len(problems) == 1, problems
        assert "INVALID_PHASE" in problems[0]


def test_repeated_phase_is_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_record(root, "0001_widget_expand_a.yaml", "add_widget_column", "expand")
        _write_record(root, "0002_widget_expand_b.yaml", "add_widget_column", "expand")
        _write_record(root, "0003_widget_migrate.yaml", "add_widget_column", "migrate")
        assert validate_directory(root) == []


if __name__ == "__main__":
    test_empty_directory_passes()
    test_valid_four_phase_change_passes()
    test_contract_without_switch_fails_closed()
    test_missing_required_field_fails_closed()
    test_invalid_phase_value_fails_closed()
    test_repeated_phase_is_allowed()
    print("PASS — all 6 tests passed.")
