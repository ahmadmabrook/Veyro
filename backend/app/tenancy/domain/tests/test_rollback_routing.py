"""Unit tests for the TSD paragraph 779 rollback routing condition.

These evidence the pure reading `rollback_routing` makes of two claims handed to it. They evidence
no rollback, no routing switch, no reconciliation, no discard, no deletion decision, no placement
resolution, no database behaviour, no tenant isolation and no integration. A `CONDITION_MET`
outcome is not permission to switch routing: TSD paragraph 779 states a necessary condition, and
no routing exists to switch.

Every refusal assertion is made by its `code`, except the one that asserts the refusal message
carries no raw input; for that test's inputs only `bad_target_writes` can fire.

TSD paragraph 779 is inside the 741-783 range both pinned baselines number, so every citation
here carries its `TSD` prefix.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from enum import Enum

from .. import rollback_routing as rr


class ForeignState(Enum):
    """A different enum whose member value collides with a real one.

    It exists so that the exact-type check is load-bearing under test. Without a member of some
    other enum in the refusal list, relaxing `type(x) is not TargetWriteState` to
    `isinstance(x, Enum)` leaves the whole suite green while admitting this member -- which the
    shipped code refuses, but which no test would have noticed.
    """

    RECONCILED = "reconciled"


BEFORE_DELETION: dict[str, object] = {
    "before_source_deletion": True,
    "target_writes": rr.TargetWriteState.RECONCILED,
}


class RollbackCase(unittest.TestCase):
    def decide(self, **overrides: object) -> rr.RollbackRoutingDecision:
        claims: dict[str, object] = dict(BEFORE_DELETION)
        claims.update(overrides)
        return rr.evaluate_rollback_routing(**claims)

    def refusal(self, **overrides: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(rr.RollbackRoutingError) as caught:
            self.decide(**overrides)
        return caught.exception.code


class TestTheParagraph779RoutingCondition(RollbackCase):
    def test_the_outcomes_are_exactly_these_three(self) -> None:
        """Membership, not only presence: a fourth outcome would invent a case."""
        self.assertEqual(
            rr.OUTCOMES, ("condition_met", "writes_outstanding", "not_before_deletion")
        )

    def test_the_states_are_the_two_the_sentence_names_plus_neither(self) -> None:
        """A fourth member would invent a state; a partial one is a source gap, not a value."""
        self.assertEqual(
            tuple(member.value for member in rr.TargetWriteState),
            ("reconciled", "discarded", "outstanding"),
        )

    def test_exactly_two_states_satisfy_the_sentence(self) -> None:
        """The source's words are "reconciled or discarded", so OUTSTANDING is not among them."""
        self.assertEqual(
            rr.SATISFYING_STATES,
            (rr.TargetWriteState.RECONCILED, rr.TargetWriteState.DISCARDED),
        )
        self.assertNotIn(rr.TargetWriteState.OUTSTANDING, rr.SATISFYING_STATES)

    def test_reconciled_writes_before_deletion_meet_the_condition(self) -> None:
        result = self.decide(target_writes=rr.TargetWriteState.RECONCILED)
        self.assertEqual(result.outcome, rr.CONDITION_MET)
        self.assertTrue(result.condition_met)

    def test_discarded_writes_before_deletion_meet_the_condition(self) -> None:
        """The sentence's disjunction: discarded satisfies it exactly as reconciled does."""
        result = self.decide(target_writes=rr.TargetWriteState.DISCARDED)
        self.assertEqual(result.outcome, rr.CONDITION_MET)
        self.assertTrue(result.condition_met)

    def test_outstanding_writes_before_deletion_refuse_the_condition(self) -> None:
        result = self.decide(target_writes=rr.TargetWriteState.OUTSTANDING)
        self.assertEqual(result.outcome, rr.WRITES_OUTSTANDING)
        self.assertFalse(result.condition_met)

    def test_rollback_not_before_deletion_is_outside_the_sentence(self) -> None:
        """Including with reconciled writes: the ordering clause gates before the state is read."""
        for state in rr.TargetWriteState:
            with self.subTest(target_writes=state):
                result = self.decide(before_source_deletion=False, target_writes=state)
                self.assertEqual(result.outcome, rr.NOT_BEFORE_DELETION)
                self.assertFalse(result.condition_met)

    def test_the_ordering_claim_is_what_separates_met_from_outside(self) -> None:
        """Hold the state constant and flip only the ordering claim."""
        before = self.decide(before_source_deletion=True)
        after = self.decide(before_source_deletion=False)
        self.assertEqual(before.outcome, rr.CONDITION_MET)
        self.assertEqual(after.outcome, rr.NOT_BEFORE_DELETION)

    def test_the_two_refusing_outcomes_stay_distinguishable(self) -> None:
        """Both carry `condition_met` false for different reasons, so `outcome` must separate."""
        outstanding = self.decide(target_writes=rr.TargetWriteState.OUTSTANDING)
        outside = self.decide(before_source_deletion=False)
        self.assertFalse(outstanding.condition_met)
        self.assertFalse(outside.condition_met)
        self.assertNotEqual(outstanding.outcome, outside.outcome)

    def test_condition_met_is_true_only_for_condition_met(self) -> None:
        self.assertTrue(self.decide().condition_met)
        self.assertFalse(self.decide(target_writes=rr.TargetWriteState.OUTSTANDING).condition_met)
        self.assertFalse(self.decide(before_source_deletion=False).condition_met)


class TestItFailsClosed(RollbackCase):
    def test_a_non_bool_ordering_claim_is_refused(self) -> None:
        """`1` and `0` are refused rather than read as the claim."""
        for bad in (1, 0, None, "true", 1.0, ()):
            with self.subTest(before_source_deletion=bad):
                self.assertEqual(
                    self.refusal(before_source_deletion=bad), "bad_before_source_deletion"
                )

    def test_a_non_member_state_is_refused(self) -> None:
        for bad in ("reconciled", "discarded", None, 0, True, rr.TargetWriteState):
            with self.subTest(target_writes=bad):
                self.assertEqual(self.refusal(target_writes=bad), "bad_target_writes")

    def test_a_member_of_another_enum_is_refused_even_at_the_same_value(self) -> None:
        """What makes the exact-type check load-bearing rather than decorative.

        `ForeignState.RECONCILED` is an `Enum` member, so relaxing the check to
        `isinstance(_, Enum)` admits it past validation. The module then reads it as
        `WRITES_OUTSTANDING`, not as a satisfying state: enum members compare by identity, so the
        shared value plays no part in that comparison. The collision earns its place against a
        second, independent relaxation -- comparing values rather than members in the membership
        test -- under which this member *is* read as satisfying. The shipped bytes refuse both.
        """
        self.assertEqual(ForeignState.RECONCILED.value, rr.TargetWriteState.RECONCILED.value)
        self.assertEqual(self.refusal(target_writes=ForeignState.RECONCILED), "bad_target_writes")

    def test_the_ordering_claim_is_validated_first(self) -> None:
        """Both malformed: the ordering refusal must be the one reported."""
        self.assertEqual(
            self.refusal(before_source_deletion=1, target_writes="reconciled"),
            "bad_before_source_deletion",
        )

    def test_the_state_is_validated_even_outside_the_sentence(self) -> None:
        """The answer would have been NOT_BEFORE_DELETION anyway; it is still refused.

        This is the assertion that fails if the `NOT_BEFORE_DELETION` return is ever moved ahead
        of validation as a shortcut.
        """
        for bad in ("reconciled", None, True, 0):
            with self.subTest(target_writes=bad):
                self.assertEqual(
                    self.refusal(before_source_deletion=False, target_writes=bad),
                    "bad_target_writes",
                )

    def test_both_claims_are_required(self) -> None:
        for omitted in BEFORE_DELETION:
            with self.subTest(omitted=omitted):
                claims = {k: v for k, v in BEFORE_DELETION.items() if k != omitted}
                with self.assertRaises(TypeError):
                    rr.evaluate_rollback_routing(**claims)

    def test_the_claims_are_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            rr.evaluate_rollback_routing(  # type: ignore
                True, rr.TargetWriteState.RECONCILED
            )

    def test_the_decision_is_frozen(self) -> None:
        result = self.decide()
        with self.assertRaises(FrozenInstanceError):
            result.outcome = rr.WRITES_OUTSTANDING  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "tenant-7731-target-writes"
        with self.assertRaises(rr.RollbackRoutingError) as caught:
            self.decide(target_writes=secret)
        self.assertEqual(str(caught.exception), "invalid rollback routing claims")
        self.assertNotIn(secret, str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        for before in (True, False):
            for state in rr.TargetWriteState:
                with self.subTest(before_source_deletion=before, target_writes=state):
                    result = self.decide(before_source_deletion=before, target_writes=state)
                    self.assertIn(result.outcome, rr.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
