"""Unit tests for the TSD paragraph 1242 staleness-bar decision.

These evidence the pure reading `read_model_freshness` makes of three values handed to it. They
evidence no read model, no freshness measurement, no authorization, no database behaviour, no
tenant isolation and no integration. Every refusal is asserted by its `code`, so no test can pass
because an unrelated refusal fired.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import read_model_freshness as rmf

BUDGET = 30


class FreshnessCase(unittest.TestCase):
    def refusal(
        self,
        staleness: object = 10,
        budget: object = BUDGET,
        consequence_bearing: object = True,
    ) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(rmf.FreshnessError) as caught:
            rmf.evaluate_read_model_freshness(staleness, budget, consequence_bearing)
        return caught.exception.code

    def decide(
        self,
        staleness: object,
        consequence_bearing: object = True,
        budget: object = BUDGET,
    ) -> rmf.FreshnessDecision:
        return rmf.evaluate_read_model_freshness(staleness, budget, consequence_bearing)


class TestTheParagraph1242Bar(FreshnessCase):
    def test_the_outcomes_are_exactly_these_three(self) -> None:
        """Membership, not only presence: a fourth outcome would invent a case."""
        self.assertEqual(rmf.OUTCOMES,
                         ("refused", "within_budget", "not_consequence_bearing"))

    def test_beyond_budget_and_consequence_bearing_is_refused(self) -> None:
        result = self.decide(BUDGET + 1)
        self.assertEqual(result.outcome, rmf.REFUSED)
        self.assertTrue(result.bar_applies)

    def test_equal_to_budget_is_within_because_1242_says_beyond(self) -> None:
        """"beyond budget" excludes equality; this is the boundary the wording fixes."""
        result = self.decide(BUDGET)
        self.assertEqual(result.outcome, rmf.WITHIN_BUDGET)
        self.assertFalse(result.bar_applies)

    def test_under_budget_is_within(self) -> None:
        self.assertEqual(self.decide(0).outcome, rmf.WITHIN_BUDGET)
        self.assertEqual(self.decide(BUDGET - 1).outcome, rmf.WITHIN_BUDGET)

    def test_a_non_consequence_bearing_mutation_leaves_the_bar_no_subject(self) -> None:
        """Paragraph 1242 bars a consequence-bearing mutation, so this is not a freshness
        finding."""
        result = self.decide(BUDGET + 1000, consequence_bearing=False)
        self.assertEqual(result.outcome, rmf.NOT_CONSEQUENCE_BEARING)
        self.assertFalse(result.bar_applies)

    def test_the_consequence_flag_is_what_separates_refused_from_no_subject(self) -> None:
        """Hold staleness beyond budget and flip only the flag."""
        bearing = self.decide(BUDGET + 1, consequence_bearing=True)
        not_bearing = self.decide(BUDGET + 1, consequence_bearing=False)
        self.assertEqual(bearing.outcome, rmf.REFUSED)
        self.assertEqual(not_bearing.outcome, rmf.NOT_CONSEQUENCE_BEARING)
        self.assertNotEqual(bearing.outcome, not_bearing.outcome)

    def test_the_flag_cannot_turn_a_within_budget_reading_into_a_refusal(self) -> None:
        for bearing in (True, False):
            with self.subTest(consequence_bearing=bearing):
                self.assertNotEqual(self.decide(0, consequence_bearing=bearing).outcome,
                                    rmf.REFUSED)

    def test_bar_applies_is_true_only_for_refused(self) -> None:
        self.assertTrue(self.decide(BUDGET + 1).bar_applies)
        self.assertFalse(self.decide(BUDGET).bar_applies)
        self.assertFalse(self.decide(BUDGET + 1, consequence_bearing=False).bar_applies)

    def test_a_zero_budget_bars_any_staleness_above_zero(self) -> None:
        """Zero is a real budget, not an absent one; the module supplies no default."""
        self.assertEqual(self.decide(1, budget=0).outcome, rmf.REFUSED)
        self.assertEqual(self.decide(0, budget=0).outcome, rmf.WITHIN_BUDGET)


class TestFailClosed(FreshnessCase):
    def test_both_measures_must_be_shape_valid(self) -> None:
        rejected: tuple[object, ...] = (None, True, False, 1.0, "10", -1,
                                        rmf.MEASURE_MAX + 1, [10], {"s": 10})
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(staleness=value), "bad_staleness")
                self.assertEqual(self.refusal(budget=value), "bad_budget")

    def test_the_budget_has_no_default_and_must_be_supplied(self) -> None:
        """MOD-004.md records the budget value as undecided, so this module never invents one."""
        with self.assertRaises(TypeError):
            rmf.evaluate_read_model_freshness(10, True)  # type: ignore[call-arg]

    def test_the_consequence_flag_must_be_an_exact_bool(self) -> None:
        rejected: tuple[object, ...] = (None, 0, 1, "", "false", "true", [], {})
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(consequence_bearing=value),
                                 "bad_consequence_bearing")

    def test_bool_is_refused_as_a_measure_although_it_is_an_int_subclass(self) -> None:
        """`type(value) is int`, not `isinstance` alone: `True == 1` would otherwise compare."""
        self.assertEqual(self.refusal(staleness=True, budget=1), "bad_staleness")
        self.assertEqual(self.refusal(staleness=1, budget=True), "bad_budget")

    def test_an_int_subclass_cannot_reach_the_comparison(self) -> None:
        """The exact-type guard keeps a subclass's operators out of the `>` at the decision."""
        class Sneaky(int):
            def __gt__(self, other: object) -> bool:
                raise AssertionError("comparison reached a subclass")

        self.assertEqual(self.refusal(staleness=Sneaky(99)), "bad_staleness")
        self.assertEqual(self.refusal(budget=Sneaky(1)), "bad_budget")

    def test_all_three_shapes_are_checked_before_any_comparison(self) -> None:
        """Fail closed on order: a false flag must not pre-empt a shape refusal."""
        self.assertEqual(self.refusal(staleness="x", consequence_bearing=False), "bad_staleness")
        self.assertEqual(self.refusal(budget="x", consequence_bearing=False), "bad_budget")

    def test_the_accepted_bound_is_this_value_not_merely_this_symbol(self) -> None:
        """Pins the value, so drift from the sibling slices' bound is detectable."""
        self.assertEqual(rmf.MEASURE_MAX, 2**31 - 1)

    def test_the_range_ends_where_it_says(self) -> None:
        self.assertEqual(self.decide(rmf.MEASURE_MAX, budget=rmf.MEASURE_MAX).outcome,
                         rmf.WITHIN_BUDGET)
        self.assertEqual(self.decide(rmf.MEASURE_MAX, budget=0).outcome, rmf.REFUSED)


class TestTheResult(FreshnessCase):
    def test_comparison_is_by_value_not_identity(self) -> None:
        """Two separately constructed equal ints above CPython's small-int cache."""
        left = int("2147483647")
        right = int("214748364" + "7")
        self.assertEqual(left, right)
        self.assertIsNot(left, right)
        result = rmf.evaluate_read_model_freshness(left, right, True)
        self.assertEqual(result.outcome, rmf.WITHIN_BUDGET)

    def test_the_decision_is_frozen(self) -> None:
        result = self.decide(0)
        with self.assertRaises(FrozenInstanceError):
            result.outcome = rmf.REFUSED  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = 987654
        with self.assertRaises(rmf.FreshnessError) as caught:
            rmf.evaluate_read_model_freshness(secret, "not-a-budget", True)
        self.assertEqual(str(caught.exception), "invalid read model freshness inputs")
        self.assertNotIn(str(secret), str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        cases: tuple[tuple[int, bool], ...] = ((0, True), (BUDGET, True), (BUDGET + 1, True),
                                               (0, False), (BUDGET + 1, False))
        for staleness, bearing in cases:
            with self.subTest(staleness=staleness, bearing=bearing):
                self.assertIn(self.decide(staleness, consequence_bearing=bearing).outcome,
                              rmf.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
