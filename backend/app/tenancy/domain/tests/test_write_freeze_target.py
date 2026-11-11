"""Unit tests for the TSD paragraph 779 write-freeze-target decision.

These evidence the pure reading `write_freeze_target` makes of two values handed to it. They
evidence no write freeze, no relocation, no relocation stage, no placement resolution, no
maintenance window, no service-level objective, no database behaviour, no tenant isolation and no
integration. Every refusal assertion but one is made by its `code`, so no test can pass because an
unrelated refusal fired; the exception is `test_the_refusal_message_carries_no_raw_input`, which
asserts the message instead, and for whose inputs only `bad_minutes` can fire.

The citation convention of the module under test holds here too: TSD paragraph 779 is inside the
741-783 range both pinned baselines number, so every reference carries its `TSD` prefix.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import write_freeze_target as wft

UNDER = wft.STANDARD_TARGET_MINUTES - 1
AT = wft.STANDARD_TARGET_MINUTES
OVER = wft.STANDARD_TARGET_MINUTES + 1


class FreezeCase(unittest.TestCase):
    def refusal(
        self,
        tenant_class: object = wft.TenantClass.STANDARD,
        minutes: object = UNDER,
    ) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(wft.WriteFreezeError) as caught:
            wft.evaluate_write_freeze_target(tenant_class, minutes)
        return caught.exception.code

    def decide(
        self,
        tenant_class: object,
        minutes: object,
    ) -> wft.WriteFreezeDecision:
        return wft.evaluate_write_freeze_target(tenant_class, minutes)


class TestTheParagraph779Target(FreezeCase):
    def test_the_outcomes_are_exactly_these_three(self) -> None:
        """Membership, not only presence: a fourth outcome would invent a case."""
        self.assertEqual(wft.OUTCOMES, ("within_target", "beyond_target", "no_stated_target"))

    def test_the_stated_figure_is_fifteen_minutes(self) -> None:
        """A round trip to the source: TSD paragraph 779 states "<15 minutes"."""
        self.assertEqual(wft.STANDARD_TARGET_MINUTES, 15)

    def test_a_standard_tenant_under_the_figure_is_within_target(self) -> None:
        result = self.decide(wft.TenantClass.STANDARD, UNDER)
        self.assertEqual(result.outcome, wft.WITHIN_TARGET)
        self.assertFalse(result.target_exceeded)

    def test_a_standard_tenant_at_exactly_fifteen_minutes_is_beyond_target(self) -> None:
        """The boundary, pinned on its own: the source writes "<15", so equal is outside.

        This is the one case where a reader's intuition and the stated text can part, and it is
        the assertion that would fail first if the comparison were ever relaxed to `<=`.
        """
        result = self.decide(wft.TenantClass.STANDARD, AT)
        self.assertEqual(result.outcome, wft.BEYOND_TARGET)
        self.assertTrue(result.target_exceeded)

    def test_a_standard_tenant_over_the_figure_is_beyond_target(self) -> None:
        self.assertEqual(self.decide(wft.TenantClass.STANDARD, OVER).outcome, wft.BEYOND_TARGET)

    def test_a_zero_minute_freeze_is_within_target(self) -> None:
        """The source states an upper target and no lower bound, so zero is under it."""
        self.assertEqual(self.decide(wft.TenantClass.STANDARD, 0).outcome, wft.WITHIN_TARGET)

    def test_the_largest_admitted_figure_is_beyond_target(self) -> None:
        self.assertEqual(
            self.decide(wft.TenantClass.STANDARD, wft.MINUTES_MAX).outcome, wft.BEYOND_TARGET
        )

    def test_a_large_dedicated_tenant_has_no_stated_target_at_any_figure(self) -> None:
        """TSD paragraph 779 states a window to be agreed, not a figure, so nothing compares."""
        for minutes in (0, UNDER, AT, OVER, wft.MINUTES_MAX):
            with self.subTest(minutes=minutes):
                result = self.decide(wft.TenantClass.LARGE_DEDICATED, minutes)
                self.assertEqual(result.outcome, wft.NO_STATED_TARGET)
                self.assertFalse(result.target_exceeded)

    def test_the_class_is_what_separates_the_outcomes(self) -> None:
        """Hold the figure constant and change only the class: the outcome must change."""
        standard = self.decide(wft.TenantClass.STANDARD, UNDER)
        dedicated = self.decide(wft.TenantClass.LARGE_DEDICATED, UNDER)
        self.assertEqual(standard.outcome, wft.WITHIN_TARGET)
        self.assertEqual(dedicated.outcome, wft.NO_STATED_TARGET)
        self.assertNotEqual(standard.outcome, dedicated.outcome)

    def test_no_stated_target_is_not_reported_as_within_target(self) -> None:
        """The two false `target_exceeded` cases must stay distinguishable by `outcome`."""
        dedicated = self.decide(wft.TenantClass.LARGE_DEDICATED, AT)
        self.assertFalse(dedicated.target_exceeded)
        self.assertNotEqual(dedicated.outcome, wft.WITHIN_TARGET)

    def test_target_exceeded_is_true_only_for_beyond_target(self) -> None:
        self.assertTrue(self.decide(wft.TenantClass.STANDARD, AT).target_exceeded)
        self.assertFalse(self.decide(wft.TenantClass.STANDARD, UNDER).target_exceeded)
        self.assertFalse(self.decide(wft.TenantClass.LARGE_DEDICATED, AT).target_exceeded)

    def test_the_source_states_exactly_two_classes(self) -> None:
        """A third member would invent a class TSD paragraph 779 does not name."""
        self.assertEqual(
            tuple(member.value for member in wft.TenantClass), ("standard", "large_dedicated")
        )


class TestItFailsClosed(FreezeCase):
    def test_a_non_member_class_is_refused(self) -> None:
        for bad in ("standard", "large_dedicated", None, 0, True, wft.TenantClass):
            with self.subTest(tenant_class=bad):
                self.assertEqual(self.refusal(tenant_class=bad), "bad_tenant_class")

    def test_a_non_int_figure_is_refused(self) -> None:
        for bad in (None, "14", 14.0, (14,)):
            with self.subTest(minutes=bad):
                self.assertEqual(self.refusal(minutes=bad), "bad_minutes")

    def test_a_bool_figure_is_refused(self) -> None:
        """`bool` is an `int` subclass, so `True` would otherwise compare as 1 minute."""
        for bad in (True, False):
            with self.subTest(minutes=bad):
                self.assertEqual(self.refusal(minutes=bad), "bad_minutes")

    def test_a_negative_figure_is_refused(self) -> None:
        """Not a duration. The source's target has no meaning below zero."""
        self.assertEqual(self.refusal(minutes=-1), "bad_minutes")

    def test_a_figure_above_the_bound_is_refused(self) -> None:
        self.assertEqual(self.refusal(minutes=wft.MINUTES_MAX + 1), "bad_minutes")

    def test_the_class_is_validated_before_the_figure(self) -> None:
        """Both malformed: the class refusal must be the one reported."""
        self.assertEqual(self.refusal(tenant_class="standard", minutes=-1), "bad_tenant_class")

    def test_the_figure_is_validated_even_where_nothing_compares(self) -> None:
        """A large/dedicated tenant compares nothing, and still may not pass a malformed figure.

        This is the assertion that would fail if the `NO_STATED_TARGET` return were ever moved
        ahead of validation as a shortcut.
        """
        for bad in (-1, "14", True, None):
            with self.subTest(minutes=bad):
                self.assertEqual(
                    self.refusal(tenant_class=wft.TenantClass.LARGE_DEDICATED, minutes=bad),
                    "bad_minutes",
                )

    def test_the_decision_is_frozen(self) -> None:
        result = self.decide(wft.TenantClass.STANDARD, UNDER)
        with self.assertRaises(FrozenInstanceError):
            result.outcome = wft.BEYOND_TARGET  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = 987654
        with self.assertRaises(wft.WriteFreezeError) as caught:
            wft.evaluate_write_freeze_target(wft.TenantClass.STANDARD, secret * 10**12)
        self.assertEqual(str(caught.exception), "invalid write freeze target inputs")
        self.assertNotIn(str(secret), str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        cases: tuple[tuple[wft.TenantClass, int], ...] = (
            (wft.TenantClass.STANDARD, 0),
            (wft.TenantClass.STANDARD, UNDER),
            (wft.TenantClass.STANDARD, AT),
            (wft.TenantClass.STANDARD, OVER),
            (wft.TenantClass.LARGE_DEDICATED, 0),
            (wft.TenantClass.LARGE_DEDICATED, AT),
        )
        for tenant_class, minutes in cases:
            with self.subTest(tenant_class=tenant_class, minutes=minutes):
                self.assertIn(self.decide(tenant_class, minutes).outcome, wft.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
