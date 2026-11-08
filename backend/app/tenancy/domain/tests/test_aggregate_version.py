"""Unit tests for the expected-aggregate-version comparison.

These evidence the pure comparison `aggregate_version` makes between two numbers handed to it.
They evidence no concurrency control, no lock, no stored version, no database behaviour, no tenant
isolation and no integration. Every refusal is asserted by its `code`, so no test can pass because
an unrelated refusal fired.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import aggregate_version as av

CURRENT = 7


class VersionCase(unittest.TestCase):
    def refusal(self, expected_version: object = 7, current_version: object = CURRENT) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(av.VersionError) as caught:
            av.compare_expected_version(expected_version, current_version)
        return caught.exception.code

    def compare(
        self, expected_version: object, current_version: object = CURRENT
    ) -> av.VersionComparison:
        return av.compare_expected_version(expected_version, current_version)


class TestTheThreeOutcomes(VersionCase):
    def test_the_outcomes_are_exactly_these_three(self) -> None:
        """Membership, not only presence: a fourth outcome would invent a distinction."""
        self.assertEqual(av.OUTCOMES, ("match", "mismatch", "no_expectation"))

    def test_match_when_the_expectation_equals_the_current_version(self) -> None:
        result = self.compare(CURRENT)
        self.assertEqual(result.outcome, av.MATCH)
        self.assertTrue(result.expectation_supplied)

    def test_match_compares_by_value_not_identity(self) -> None:
        """`==`, never `is`. Two separately constructed equal ints, above CPython's cache.

        Small ints are cached only to 256, so every aggregate version above that is affected.
        A review found this pinned by nothing: the mutation `==` -> `is` left all 62 tests green
        because every other MATCH assertion passes one object twice.
        """
        left = int("2147483647")
        right = int("214748364" + "7")
        self.assertEqual(left, right)
        self.assertIsNot(left, right)
        result = av.compare_expected_version(left, right)
        self.assertEqual(result.outcome, av.MATCH)
        self.assertTrue(result.expectation_supplied)

    def test_the_accepted_bound_is_this_value_not_merely_this_symbol(self) -> None:
        """Pins the value, so drift from the two sibling slices' bound is detectable.

        Every other bound assertion here is written relative to `av.VERSION_MAX`, so widening the
        symbol left the suite green. The docstring claims equality with
        `command_envelope.EXPECTED_VERSION_MAX` and `tenancy_s0.EXPECTED_VERSION_MAX`; this is
        what makes that claim falsifiable from inside the lane.
        """
        self.assertEqual(av.VERSION_MAX, 2**31 - 1)

    def test_mismatch_when_the_expectation_differs(self) -> None:
        result = self.compare(CURRENT + 1)
        self.assertEqual(result.outcome, av.MISMATCH)
        self.assertTrue(result.expectation_supplied)

    def test_mismatch_is_not_subdivided_by_direction(self) -> None:
        """Below and above both MISMATCH: no pinned source distinguishes stale from ahead.

        Asserted as sameness rather than as two separate outcomes, so a later revision that
        invented a direction-specific outcome would fail here.
        """
        below = self.compare(CURRENT - 1)
        above = self.compare(CURRENT + 1)
        self.assertEqual(below.outcome, av.MISMATCH)
        self.assertEqual(above.outcome, av.MISMATCH)
        self.assertEqual(below.outcome, above.outcome)

    def test_no_expectation_when_none_is_supplied(self) -> None:
        """Reports the state; does not decide admissibility, which ADR-0002 leaves open."""
        result = self.compare(None)
        self.assertEqual(result.outcome, av.NO_EXPECTATION)
        self.assertFalse(result.expectation_supplied)

    def test_no_expectation_is_returned_rather_than_treated_as_a_match(self) -> None:
        """The open discrepancy must not be resolved by equating absence with agreement."""
        self.assertNotEqual(self.compare(None).outcome, av.MATCH)
        self.assertNotEqual(self.compare(None).outcome, av.MISMATCH)

    def test_expectation_supplied_tracks_the_outcome(self) -> None:
        self.assertTrue(self.compare(CURRENT).expectation_supplied)
        self.assertTrue(self.compare(CURRENT + 1).expectation_supplied)
        self.assertFalse(self.compare(None).expectation_supplied)


class TestFailClosed(VersionCase):
    def test_the_current_version_is_required_and_must_be_shape_valid(self) -> None:
        rejected: tuple[object, ...] = (None, True, False, 1.0, "7", -1,
                                        av.VERSION_MAX + 1, [7], {"v": 7})
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(current_version=value), "bad_current_version")

    def test_a_supplied_expectation_must_be_shape_valid(self) -> None:
        rejected: tuple[object, ...] = (True, False, 1.0, "7", -1,
                                        av.VERSION_MAX + 1, [7], {"v": 7})
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(expected_version=value), "bad_expected_version")

    def test_bool_is_refused_although_it_is_an_int_subclass(self) -> None:
        """`type(value) is int`, not `isinstance`: `True == 1` would otherwise compare equal."""
        self.assertEqual(self.refusal(expected_version=True, current_version=1),
                         "bad_expected_version")
        self.assertEqual(self.refusal(expected_version=1, current_version=True),
                         "bad_current_version")

    def test_the_current_version_is_checked_before_the_expectation(self) -> None:
        """Fail closed on order: an absent expectation does not excuse an invalid current version.

        Without this ordering a caller passing no expectation would get NO_EXPECTATION back
        while handing in a current version this module never validated.
        """
        self.assertEqual(self.refusal(expected_version=None, current_version=None),
                         "bad_current_version")
        self.assertEqual(self.refusal(expected_version=None, current_version="7"),
                         "bad_current_version")

    def test_the_accepted_range_ends_where_it_says(self) -> None:
        for value in (0, 1, av.VERSION_MAX):
            with self.subTest(value=value):
                self.assertEqual(self.compare(value, value).outcome, av.MATCH)

    def test_zero_is_a_real_version_not_an_absent_one(self) -> None:
        """`0` must not be conflated with `None`: D6.3's own pattern uses 0 for a first set."""
        result = self.compare(0, 0)
        self.assertEqual(result.outcome, av.MATCH)
        self.assertTrue(result.expectation_supplied)


class TestTheResult(VersionCase):
    def test_the_comparison_is_frozen(self) -> None:
        result = self.compare(CURRENT)
        with self.assertRaises(FrozenInstanceError):
            result.outcome = av.MISMATCH  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = 999999
        with self.assertRaises(av.VersionError) as caught:
            av.compare_expected_version(secret, "not-a-version")
        self.assertEqual(str(caught.exception), "invalid aggregate version comparison inputs")
        self.assertNotIn(str(secret), str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        candidates: tuple[object, ...] = (None, 0, CURRENT, CURRENT + 1, av.VERSION_MAX)
        for value in candidates:
            with self.subTest(value=value):
                self.assertIn(self.compare(value).outcome, av.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
