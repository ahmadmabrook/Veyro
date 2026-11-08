"""Unit tests for the TSD paragraph 778 epoch-rejection decision.

These evidence the pure reading `relocation_epoch` makes of three values handed to it. They
evidence no placement resolution, no route switch, no relocation state, no database behaviour, no
tenant isolation and no integration. Every refusal is asserted by its `code`, so no test can pass
because an unrelated refusal fired.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import relocation_epoch as re_

CURRENT_EPOCH = 4


class EpochCase(unittest.TestCase):
    def refusal(
        self,
        command_epoch: object = CURRENT_EPOCH,
        current_epoch: object = CURRENT_EPOCH,
        route_switched: object = True,
    ) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(re_.EpochError) as caught:
            re_.evaluate_relocation_epoch(command_epoch, current_epoch, route_switched)
        return caught.exception.code

    def decide(
        self,
        command_epoch: object,
        route_switched: object,
        current_epoch: object = CURRENT_EPOCH,
    ) -> re_.EpochDecision:
        return re_.evaluate_relocation_epoch(command_epoch, current_epoch, route_switched)


class TestTheParagraph778Rule(EpochCase):
    def test_the_outcomes_are_exactly_these_three(self) -> None:
        """Membership, not only presence: a fourth outcome would invent a case."""
        self.assertEqual(re_.OUTCOMES, ("reject", "current", "stale_before_switch"))

    def test_an_older_epoch_after_route_switch_is_rejected(self) -> None:
        """The rule as paragraph 778 states it: old epoch, after route switch."""
        result = self.decide(CURRENT_EPOCH - 1, True)
        self.assertEqual(result.outcome, re_.REJECT)
        self.assertTrue(result.rule_fires)

    def test_an_equal_epoch_is_current_and_the_rule_has_no_subject(self) -> None:
        result = self.decide(CURRENT_EPOCH, True)
        self.assertEqual(result.outcome, re_.CURRENT)
        self.assertFalse(result.rule_fires)

    def test_an_older_epoch_before_route_switch_does_not_fire_the_rule(self) -> None:
        """Paragraph 778 conditions rejection on "after route switch", so it does not fire."""
        result = self.decide(CURRENT_EPOCH - 1, False)
        self.assertEqual(result.outcome, re_.STALE_BEFORE_SWITCH)
        self.assertFalse(result.rule_fires)

    def test_the_switch_flag_is_what_separates_reject_from_stale(self) -> None:
        """Hold the epochs constant and flip only the flag: the outcome must change."""
        after = self.decide(CURRENT_EPOCH - 1, True)
        before = self.decide(CURRENT_EPOCH - 1, False)
        self.assertEqual(after.outcome, re_.REJECT)
        self.assertEqual(before.outcome, re_.STALE_BEFORE_SWITCH)
        self.assertNotEqual(after.outcome, before.outcome)

    def test_an_equal_epoch_is_current_regardless_of_the_switch(self) -> None:
        """The rule's subject is an old epoch, so the flag cannot make an equal one reject."""
        for switched in (True, False):
            with self.subTest(route_switched=switched):
                self.assertEqual(self.decide(CURRENT_EPOCH, switched).outcome, re_.CURRENT)

    def test_rule_fires_is_true_only_for_reject(self) -> None:
        self.assertTrue(self.decide(CURRENT_EPOCH - 1, True).rule_fires)
        self.assertFalse(self.decide(CURRENT_EPOCH, True).rule_fires)
        self.assertFalse(self.decide(CURRENT_EPOCH - 1, False).rule_fires)

    def test_a_much_older_epoch_is_still_only_older(self) -> None:
        """No gradation: paragraph 778 says "the old epoch", not how old."""
        self.assertEqual(self.decide(0, True).outcome, re_.REJECT)
        self.assertEqual(self.decide(CURRENT_EPOCH - 1, True).outcome, re_.REJECT)


class TestFailClosed(EpochCase):
    def test_an_epoch_ahead_of_current_is_refused_not_decided(self) -> None:
        """No pinned source states a rule for it, so no outcome is returned.

        Verified by searching the pinned extract: "newer epoch", "future epoch", "ahead",
        "greater epoch" and "higher epoch" do not occur. The sources speak only of "the old
        epoch" and "an older epoch".
        """
        self.assertEqual(self.refusal(command_epoch=CURRENT_EPOCH + 1),
                         "epoch_ahead_of_current")
        self.assertEqual(self.refusal(command_epoch=re_.EPOCH_MAX, current_epoch=0),
                         "epoch_ahead_of_current")

    def test_the_refusal_for_an_ahead_epoch_does_not_depend_on_the_switch(self) -> None:
        for switched in (True, False):
            with self.subTest(route_switched=switched):
                self.assertEqual(
                    self.refusal(command_epoch=CURRENT_EPOCH + 1, route_switched=switched),
                    "epoch_ahead_of_current")

    def test_both_epochs_must_be_shape_valid(self) -> None:
        rejected: tuple[object, ...] = (None, True, False, 1.0, "4", -1,
                                        re_.EPOCH_MAX + 1, [4], {"e": 4})
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(command_epoch=value), "bad_command_epoch")
                self.assertEqual(self.refusal(current_epoch=value), "bad_current_epoch")

    def test_the_switch_flag_must_be_an_exact_bool(self) -> None:
        rejected: tuple[object, ...] = (None, 0, 1, "", "false", "true", [], {})
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(route_switched=value), "bad_route_switched")

    def test_bool_is_refused_as_an_epoch_although_it_is_an_int_subclass(self) -> None:
        """`type(value) is int`, not `isinstance`: `True == 1` would otherwise compare."""
        self.assertEqual(self.refusal(command_epoch=True, current_epoch=1),
                         "bad_command_epoch")
        self.assertEqual(self.refusal(command_epoch=1, current_epoch=True),
                         "bad_current_epoch")

    def test_all_three_shapes_are_checked_before_any_comparison(self) -> None:
        """Fail closed on order: an ahead epoch must not pre-empt a shape refusal.

        Without this ordering a caller could get `epoch_ahead_of_current` while handing in a
        `route_switched` this module never validated.
        """
        self.assertEqual(self.refusal(command_epoch=CURRENT_EPOCH + 1, route_switched="yes"),
                         "bad_route_switched")
        self.assertEqual(self.refusal(command_epoch=CURRENT_EPOCH + 1, current_epoch="4"),
                         "bad_current_epoch")

    def test_the_accepted_bound_is_this_value_not_merely_this_symbol(self) -> None:
        """Pins the value, so drift from the sibling slices' bound is detectable."""
        self.assertEqual(re_.EPOCH_MAX, 2**31 - 1)

    def test_the_range_ends_where_it_says(self) -> None:
        for value in (0, 1, re_.EPOCH_MAX):
            with self.subTest(value=value):
                self.assertEqual(self.decide(value, True, current_epoch=value).outcome,
                                 re_.CURRENT)


class TestTheResult(EpochCase):
    def test_comparison_is_by_value_not_identity(self) -> None:
        """`==` and `>`, never `is`. Two separately constructed equal ints above the int cache."""
        left = int("2147483647")
        right = int("214748364" + "7")
        self.assertEqual(left, right)
        self.assertIsNot(left, right)
        result = re_.evaluate_relocation_epoch(left, right, True)
        self.assertEqual(result.outcome, re_.CURRENT)

    def test_the_decision_is_frozen(self) -> None:
        result = self.decide(CURRENT_EPOCH, True)
        with self.assertRaises(FrozenInstanceError):
            result.outcome = re_.REJECT  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = 123456
        with self.assertRaises(re_.EpochError) as caught:
            re_.evaluate_relocation_epoch(secret, "not-an-epoch", True)
        self.assertEqual(str(caught.exception), "invalid relocation epoch inputs")
        self.assertNotIn(str(secret), str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        cases: tuple[tuple[int, bool], ...] = ((CURRENT_EPOCH, True), (CURRENT_EPOCH, False),
                                               (CURRENT_EPOCH - 1, True),
                                               (CURRENT_EPOCH - 1, False), (0, True))
        for epoch, switched in cases:
            with self.subTest(epoch=epoch, switched=switched):
                self.assertIn(self.decide(epoch, switched).outcome, re_.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
