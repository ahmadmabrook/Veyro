"""Unit tests for the TSD paragraph 1228 hard-deletion bar.

These evidence the pure reading `hard_deletion_gates` makes of three claims handed to it. They
evidence no gate, no gate evaluation, no approval, no audit record, no deletion, no permission to
delete, no lifecycle history, no database behaviour, no tenant isolation and no integration. A
`NOT_BARRED` outcome is not permission: TSD paragraph 1231 separately requires approvals,
retention checks and an immutable audit record, and the approvers and quorum are owner-reserved.

Every refusal assertion is made by its `code`, except the one that asserts the refusal message
carries no raw input; for that test's inputs only `bad_retention` can fire.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import hard_deletion_gates as hdg

ALL_PASSED: dict[str, object] = {"legal": True, "billing": True, "retention": True}


class GateCase(unittest.TestCase):
    def decide(self, **overrides: object) -> hdg.HardDeletionDecision:
        claims: dict[str, object] = dict(ALL_PASSED)
        claims.update(overrides)
        return hdg.evaluate_hard_deletion_gates(**claims)

    def refusal(self, **overrides: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(hdg.HardDeletionGateError) as caught:
            self.decide(**overrides)
        return caught.exception.code


class TestTheParagraph1228Bar(GateCase):
    def test_the_outcomes_are_exactly_these_two(self) -> None:
        self.assertEqual(hdg.OUTCOMES, ("barred", "not_barred"))

    def test_the_gates_are_the_three_the_paragraph_names_in_its_order(self) -> None:
        """A round trip: the three names rebuild the clause's list verbatim."""
        self.assertEqual(hdg.DELETION_GATES, ("legal", "billing", "retention"))
        rebuilt = (
            "prevent hard deletion before "
            + ", ".join(hdg.DELETION_GATES[:2])
            + " and "
            + hdg.DELETION_GATES[2]
            + " gates pass."
        )
        self.assertEqual(
            rebuilt, "prevent hard deletion before legal, billing and retention gates pass."
        )

    def test_all_three_passed_means_this_bar_does_not_apply(self) -> None:
        result = self.decide()
        self.assertEqual(result.outcome, hdg.NOT_BARRED)
        self.assertFalse(result.barred)
        self.assertEqual(result.outstanding, ())

    def test_any_single_gate_outstanding_bars_deletion(self) -> None:
        """The paragraph names three and requires all; one is enough, and it must be named."""
        for gate in hdg.DELETION_GATES:
            with self.subTest(gate=gate):
                result = self.decide(**{gate: False})
                self.assertEqual(result.outcome, hdg.BARRED)
                self.assertTrue(result.barred)
                self.assertEqual(result.outstanding, (gate,))

    def test_all_three_outstanding_are_named_in_the_paragraph_s_order(self) -> None:
        result = self.decide(legal=False, billing=False, retention=False)
        self.assertEqual(result.outstanding, hdg.DELETION_GATES)

    def test_two_outstanding_keep_the_paragraph_s_order(self) -> None:
        """Passed last-then-first; the result must still read in the source's order."""
        result = self.decide(retention=False, legal=False)
        self.assertEqual(result.outstanding, ("legal", "retention"))

    def test_outstanding_is_empty_exactly_when_not_barred(self) -> None:
        self.assertEqual(self.decide().outstanding, ())
        self.assertNotEqual(self.decide(billing=False).outstanding, ())

    def test_outstanding_is_a_tuple(self) -> None:
        self.assertIsInstance(self.decide(legal=False).outstanding, tuple)

    def test_barred_is_true_only_for_barred(self) -> None:
        self.assertFalse(self.decide().barred)
        self.assertTrue(self.decide(retention=False).barred)


class TestItFailsClosed(GateCase):
    def test_a_non_bool_claim_is_refused_per_gate(self) -> None:
        """`1` and `0` are refused rather than read as a gate having passed."""
        for gate in hdg.DELETION_GATES:
            for bad in (1, 0, None, "passed", 1.0, ()):
                with self.subTest(gate=gate, claim=bad):
                    self.assertEqual(self.refusal(**{gate: bad}), f"bad_{gate}")

    def test_the_claims_are_validated_in_the_paragraph_s_order(self) -> None:
        """All three malformed: the first gate in the source's order must be reported."""
        self.assertEqual(self.refusal(legal=1, billing=1, retention=1), "bad_legal")

    def test_a_malformed_claim_is_refused_even_when_another_gate_is_outstanding(self) -> None:
        """The answer would have been BARRED anyway; it is still refused."""
        self.assertEqual(self.refusal(legal=False, retention=1), "bad_retention")

    def test_every_claim_is_required(self) -> None:
        """No default: one would invent a gate's result."""
        for omitted in ALL_PASSED:
            with self.subTest(omitted=omitted):
                claims = {k: v for k, v in ALL_PASSED.items() if k != omitted}
                with self.assertRaises(TypeError):
                    hdg.evaluate_hard_deletion_gates(**claims)

    def test_the_claims_are_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            hdg.evaluate_hard_deletion_gates(True, True, True)  # type: ignore

    def test_the_decision_is_frozen(self) -> None:
        result = self.decide()
        with self.assertRaises(FrozenInstanceError):
            result.outcome = hdg.BARRED  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "tenant-4417-retention-waiver"
        with self.assertRaises(hdg.HardDeletionGateError) as caught:
            self.decide(retention=secret)
        self.assertEqual(str(caught.exception), "invalid hard deletion gate claims")
        self.assertNotIn(secret, str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        self.assertIn(self.decide().outcome, hdg.OUTCOMES)
        for gate in hdg.DELETION_GATES:
            with self.subTest(gate=gate):
                self.assertIn(self.decide(**{gate: False}).outcome, hdg.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
