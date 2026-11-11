"""Unit tests for the TSD paragraph 778 reconciliation precondition.

These evidence the pure reading `reconciliation_before_deletion` makes of five claims handed to
it. They evidence no reconciliation, no row count, no ledger control total, no retention gate, no
deletion approval, no database behaviour, no tenant isolation and no integration. Nothing here is
evidence that any reconciliation ran, and a `RECONCILED` outcome is not a deletion decision: the
retention gate, the approvers and the quorum are owner-reserved and undecided.

Every refusal assertion is made by its `code`, except the one that asserts the refusal message
carries no raw input; for that test's inputs only `bad_object_references` can fire.

TSD paragraph 778 is inside the 741-783 range both pinned baselines number, so every citation
here carries its `TSD` prefix.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import reconciliation_before_deletion as rbd

ALL_RECONCILED: dict[str, object] = {
    "copied_row_counts": True,
    "ledger_control_totals": True,
    "outbox_high_water_marks": True,
    "object_references": True,
    "search_read_projections": True,
}
# Parameter name paired with the subject name TSD paragraph 778 spells, in the sentence's order.
PAIRS = (
    ("copied_row_counts", "copied row counts"),
    ("ledger_control_totals", "ledger control totals"),
    ("outbox_high_water_marks", "outbox high-water marks"),
    ("object_references", "object references"),
    ("search_read_projections", "search/read projections"),
)


class ReconciliationCase(unittest.TestCase):
    def decide(self, **overrides: object) -> rbd.ReconciliationDecision:
        claims = dict(ALL_RECONCILED)
        claims.update(overrides)
        return rbd.evaluate_reconciliation_before_source_deletion(**claims)

    def refusal(self, **overrides: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(rbd.ReconciliationError) as caught:
            self.decide(**overrides)
        return caught.exception.code


class TestTheParagraph778Precondition(ReconciliationCase):
    def test_the_outcomes_are_exactly_these_two(self) -> None:
        """Membership, not only presence: a third outcome would invent a case."""
        self.assertEqual(rbd.OUTCOMES, ("reconciled", "outstanding"))

    def test_the_five_subjects_are_the_sentence_s_own_words_in_its_order(self) -> None:
        """A round trip to the source: the five names rebuild the sentence verbatim.

        This is the pin the name closures over table columns cannot have. These five sit in one
        sentence, so joining them in order must reproduce it exactly -- which fails if a name is
        reworded, a solidus or hyphen is lost, or the order drifts.
        """
        self.assertEqual(rbd.RECONCILIATION_SUBJECTS, tuple(name for _, name in PAIRS))
        rebuilt = (
            "All "
            + ", ".join(rbd.RECONCILIATION_SUBJECTS[:4])
            + " and "
            + rbd.RECONCILIATION_SUBJECTS[4]
            + " are reconciled before source deletion."
        )
        self.assertEqual(
            rebuilt,
            "All copied row counts, ledger control totals, outbox high-water marks, object "
            "references and search/read projections are reconciled before source deletion.",
        )

    def test_all_five_reconciled_meets_the_precondition(self) -> None:
        result = self.decide()
        self.assertEqual(result.outcome, rbd.RECONCILED)
        self.assertTrue(result.precondition_met)
        self.assertEqual(result.outstanding, ())

    def test_any_single_subject_outstanding_fails_the_precondition(self) -> None:
        """The sentence's word is "All", so one is enough, and the right one must be named."""
        for parameter, subject in PAIRS:
            with self.subTest(subject=subject):
                result = self.decide(**{parameter: False})
                self.assertEqual(result.outcome, rbd.OUTSTANDING)
                self.assertFalse(result.precondition_met)
                self.assertEqual(result.outstanding, (subject,))

    def test_all_five_outstanding_are_named_in_the_sentence_s_order(self) -> None:
        result = self.decide(**{parameter: False for parameter, _ in PAIRS})
        self.assertEqual(result.outstanding, rbd.RECONCILIATION_SUBJECTS)

    def test_two_outstanding_keep_the_sentence_s_order_not_the_call_s(self) -> None:
        """Passed last-then-first; the result must still read in the source's order.

        Half of this is guaranteed by the language rather than by the code: the signature is
        keyword-only, so the call's ordering never reaches the function at all. What the test
        genuinely pins is that `outstanding` follows the sentence's order, which fails if the
        subject tuple is reordered.
        """
        result = self.decide(search_read_projections=False, copied_row_counts=False)
        self.assertEqual(result.outstanding, ("copied row counts", "search/read projections"))

    def test_outstanding_is_empty_exactly_when_the_precondition_is_met(self) -> None:
        for parameter, _ in PAIRS:
            with self.subTest(parameter=parameter):
                met = self.decide(**{parameter: True})
                unmet = self.decide(**{parameter: False})
                self.assertEqual(met.precondition_met, met.outstanding == ())
                self.assertEqual(unmet.precondition_met, unmet.outstanding == ())

    def test_outstanding_is_a_tuple(self) -> None:
        """A mutable sequence would let a caller edit a decision after the fact."""
        self.assertIsInstance(self.decide(object_references=False).outstanding, tuple)

    def test_precondition_met_is_true_only_for_reconciled(self) -> None:
        self.assertTrue(self.decide().precondition_met)
        self.assertFalse(self.decide(ledger_control_totals=False).precondition_met)


class TestItFailsClosed(ReconciliationCase):
    def test_a_non_bool_claim_is_refused_per_subject(self) -> None:
        """Each subject has its own code, and `1`/`0` are refused rather than read."""
        for parameter, subject in PAIRS:
            for bad in (1, 0, None, "true", 1.0, ()):
                with self.subTest(subject=subject, claim=bad):
                    self.assertEqual(self.refusal(**{parameter: bad}), f"bad_{parameter}")

    def test_the_claims_are_validated_in_the_sentence_s_order(self) -> None:
        """All five malformed: the first subject in the source's order must be reported."""
        self.assertEqual(
            self.refusal(**{parameter: 1 for parameter, _ in PAIRS}), "bad_copied_row_counts"
        )

    def test_a_malformed_claim_is_refused_even_when_another_is_outstanding(self) -> None:
        """The answer would have been OUTSTANDING anyway; it is still refused.

        This is the assertion that fails if validation is ever folded into the outstanding
        comprehension as a shortcut.
        """
        self.assertEqual(
            self.refusal(copied_row_counts=False, search_read_projections=1),
            "bad_search_read_projections",
        )

    def test_every_claim_is_required(self) -> None:
        """No default: `True` would invent a reconciliation, `False` would invent a finding."""
        for parameter, _ in PAIRS:
            with self.subTest(omitted=parameter):
                claims = {k: v for k, v in ALL_RECONCILED.items() if k != parameter}
                with self.assertRaises(TypeError):
                    rbd.evaluate_reconciliation_before_source_deletion(**claims)

    def test_the_claims_are_keyword_only(self) -> None:
        """Five same-typed claims in a row are what a caller silently transposes."""
        with self.assertRaises(TypeError):
            rbd.evaluate_reconciliation_before_source_deletion(  # type: ignore
                True, True, True, True, True
            )

    def test_the_decision_is_frozen(self) -> None:
        result = self.decide()
        with self.assertRaises(FrozenInstanceError):
            result.outcome = rbd.OUTSTANDING  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "reconciled-by-tenant-9931"
        with self.assertRaises(rbd.ReconciliationError) as caught:
            self.decide(object_references=secret)
        self.assertEqual(str(caught.exception), "invalid reconciliation claims")
        self.assertNotIn(secret, str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        self.assertIn(self.decide().outcome, rbd.OUTCOMES)
        for parameter, _ in PAIRS:
            with self.subTest(parameter=parameter):
                self.assertIn(self.decide(**{parameter: False}).outcome, rbd.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
