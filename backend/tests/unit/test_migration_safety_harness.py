"""Pure-logic unit tests for `tests.harness.migration_safety`'s non-database
functions: the status_code<->status mapping, the generic integer-map diff
(`diff_int_maps` — kept as a standalone pure utility; NOT called by
`verify_rollback`/`validate_post_contract`, corrected 2026-10-03 security
re-review round 2, NR2-9, since this line previously claimed otherwise),
and the row-count/duplicate-id check those two functions do rely on
(`row_count_or_duplicate_violations`). No database, no mocking — these are
genuinely pure functions, so they get genuine unit tests rather than a
re-mocked integration test."""

from __future__ import annotations

import pytest

from tests.harness.migration_safety import (
    STATUS_BY_CODE,
    code_for_status,
    diff_int_maps,
    row_count_or_duplicate_violations,
    status_for_code,
)


@pytest.mark.parametrize(("code", "expected"), list(STATUS_BY_CODE.items()))
def test_status_for_code_matches_the_declared_mapping(code: int, expected: str) -> None:
    assert status_for_code(code) == expected


def test_status_for_code_rejects_an_unmapped_code() -> None:
    with pytest.raises(ValueError, match="no status mapping for status_code=999"):
        status_for_code(999)


@pytest.mark.parametrize(("code", "status"), list(STATUS_BY_CODE.items()))
def test_code_for_status_is_the_inverse_of_status_for_code(code: int, status: str) -> None:
    assert code_for_status(status_for_code(code)) == code


def test_code_for_status_rejects_an_unmapped_status() -> None:
    with pytest.raises(ValueError, match="no status_code mapping for status='not-a-real-status'"):
        code_for_status("not-a-real-status")


def test_diff_int_maps_is_empty_when_every_expected_key_matches() -> None:
    assert diff_int_maps({1: 10, 2: 20}, {1: 10, 2: 20, 3: 999}) == {}


def test_diff_int_maps_reports_mismatches_and_missing_keys() -> None:
    expected = {1: 10, 2: 20, 3: 30}
    actual = {1: 10, 2: 99}  # 2 is wrong, 3 is missing entirely
    assert diff_int_maps(expected, actual) == {2: (20, 99), 3: (30, None)}


def test_diff_int_maps_never_reports_an_extra_key_not_in_expected() -> None:
    # Row-set-growth is a distinct harness-level concern, not this pure
    # function's job. Corrected 2026-10-03 (security re-review round 2,
    # NR2-9): `verify_rollback`'s `row_set_changed` is not the primary
    # detector for growth — a growth case changes the live row count, so
    # `row_count_or_duplicate_violations` catches and raises on it first;
    # `row_set_changed` is redundant for that specific shape.
    assert diff_int_maps({1: 10}, {1: 10, 2: 20}) == {}


# --- row_count_or_duplicate_violations (added 2026-10-03, security re-review
# NF-1/NF-3: the pure logic behind the row-count/duplicate-id detection,
# pinned directly rather than only exercised indirectly via a real Postgres
# integration test) -----------------------------------------------------------


def test_row_count_or_duplicate_violations_is_empty_for_a_clean_unique_id_list() -> None:
    assert row_count_or_duplicate_violations([0, 1, 2, 3], expected_count=4) == []


def test_row_count_or_duplicate_violations_reports_a_changed_row_count() -> None:
    violations = row_count_or_duplicate_violations([0, 1, 2], expected_count=4)
    assert len(violations) == 1
    assert "row count changed" in violations[0]


def test_row_count_or_duplicate_violations_reports_a_duplicate_id() -> None:
    # Same count as expected (4), but id 1 is duplicated and id 3 is missing
    # — exactly the shape an id-keyed dict would silently collapse away.
    violations = row_count_or_duplicate_violations([0, 1, 1, 2], expected_count=4)
    assert len(violations) == 1
    assert "duplicate id(s) found: [1]" in violations[0]


def test_row_count_or_duplicate_violations_reports_both_when_both_apply() -> None:
    # 12 -> 24, every id duplicated (probe N9's exact shape).
    violations = row_count_or_duplicate_violations([0, 0, 1, 1], expected_count=2)
    assert len(violations) == 2
