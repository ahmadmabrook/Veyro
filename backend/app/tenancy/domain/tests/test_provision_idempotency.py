"""Unit tests for the ProvisionTenant idempotency decision.

These evidence the pure decisions `provision_idempotency` makes about four values handed to it.
They evidence no uniqueness constraint, no registry, no transaction, no idempotency enforcement,
no database behaviour, no tenant isolation and no integration. Every refusal is asserted by its
`code`, so no test can pass because an unrelated refusal fired.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import provision_idempotency as pi

KEY = "b2c3d4e5-f607-4819-aa2b-3c4d5e6f7081"
PAYLOAD = "tenant-alpha"
OTHER_PAYLOAD = "tenant-beta"


class IdempotencyCase(unittest.TestCase):
    def refusal(
        self,
        idempotency_key: object = KEY,
        external_key: object = PAYLOAD,
        registered_external_key: object = None,
        external_key_taken: object = False,
    ) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(pi.IdempotencyError) as caught:
            pi.decide_provision_idempotency(
                idempotency_key, external_key, registered_external_key, external_key_taken)
        return caught.exception.code

    def decide(
        self,
        registered_external_key: object = None,
        external_key_taken: object = False,
        external_key: object = PAYLOAD,
    ) -> pi.IdempotencyDecision:
        return pi.decide_provision_idempotency(
            KEY, external_key, registered_external_key, external_key_taken)


class TestTheFourD63Cases(IdempotencyCase):
    def test_the_outcomes_are_exactly_these_three(self) -> None:
        """Membership, not only presence: a fourth outcome would be an invented case."""
        self.assertEqual(pi.OUTCOMES, ("first", "replay", "payload_mismatch"))

    def test_first_call_when_the_key_is_unregistered_and_the_payload_is_free(self) -> None:
        decision = self.decide()
        self.assertEqual(decision.outcome, pi.FIRST)
        self.assertFalse(decision.replayed)

    def test_replay_when_this_key_holds_the_same_payload(self) -> None:
        decision = self.decide(registered_external_key=PAYLOAD)
        self.assertEqual(decision.outcome, pi.REPLAY)
        self.assertTrue(decision.replayed)

    def test_replay_compares_by_value_not_identity(self) -> None:
        """`==`, never `is`. This is the normal case in any real wiring, not an exotic one.

        The registered payload arrives from a registry row and the request's from the caller, so
        they are equal and never identical. D6.3 makes `replayed = true` the gate on which the
        caller skips all tenant-side writes, so an identity comparison would duplicate those
        writes on every replay. A review found this pinned by nothing: the mutation `==` -> `is`
        left the whole suite green because every other replay test passes one string object.
        """
        equal_but_distinct = "".join(["tenant-", "alpha"])
        self.assertEqual(equal_but_distinct, PAYLOAD)
        self.assertIsNot(equal_but_distinct, PAYLOAD)
        decision = self.decide(registered_external_key=equal_but_distinct)
        self.assertEqual(decision.outcome, pi.REPLAY)
        self.assertTrue(decision.replayed)

    def test_payload_mismatch_when_this_key_holds_a_different_payload(self) -> None:
        decision = self.decide(registered_external_key=OTHER_PAYLOAD)
        self.assertEqual(decision.outcome, pi.PAYLOAD_MISMATCH)
        self.assertFalse(decision.replayed)

    def test_payload_mismatch_when_the_payload_is_taken_under_another_key(self) -> None:
        """D6.3 gives this the same error as a differing payload under the same key."""
        decision = self.decide(external_key_taken=True)
        self.assertEqual(decision.outcome, pi.PAYLOAD_MISMATCH)
        self.assertFalse(decision.replayed)

    def test_replayed_is_true_only_for_replay(self) -> None:
        """`replayed` is D6.3's field and gates the caller skipping all tenant-side writes."""
        self.assertTrue(self.decide(registered_external_key=PAYLOAD).replayed)
        self.assertFalse(self.decide().replayed)
        self.assertFalse(self.decide(registered_external_key=OTHER_PAYLOAD).replayed)
        self.assertFalse(self.decide(external_key_taken=True).replayed)


class TestFailClosed(IdempotencyCase):
    def test_the_same_payload_under_two_keys_is_refused_as_impossible(self) -> None:
        """One external_key on two registry rows contradicts D6.3's unique constraint on it.

        Narrow by design: only the SAME payload. A review proved an earlier revision refused the
        wider condition and swallowed the legal state pinned by the next test.
        """
        self.assertEqual(
            self.refusal(registered_external_key=PAYLOAD, external_key_taken=True),
            "contradictory_registry_state")

    def test_this_key_holding_another_payload_is_a_mismatch_even_if_ours_is_taken(self) -> None:
        """A legal state D6.3 answers twice, and an earlier revision refused.

        This key holds Q and the request's P is registered under a different key: the registry
        holds each payload once, so both unique constraints are satisfied. D6.3 gives both "same
        idempotency key, different payload" and "a different idempotency key with an
        already-registered external_key" the same error, so the outcome is PAYLOAD_MISMATCH.
        """
        decision = self.decide(registered_external_key=OTHER_PAYLOAD, external_key_taken=True)
        self.assertEqual(decision.outcome, pi.PAYLOAD_MISMATCH)
        self.assertFalse(decision.replayed)

    def test_the_taken_flag_alone_does_not_change_a_mismatch_into_a_refusal(self) -> None:
        """The control the review used: flip only `external_key_taken` and the outcome holds."""
        for taken in (False, True):
            with self.subTest(external_key_taken=taken):
                decision = self.decide(registered_external_key=OTHER_PAYLOAD,
                                       external_key_taken=taken)
                self.assertEqual(decision.outcome, pi.PAYLOAD_MISMATCH)

    def test_the_idempotency_key_must_be_a_shape_valid_uuid(self) -> None:
        for value in (None, 1, True, "not-a-uuid", KEY + "x",
                      "00000000-0000-0000-0000-000000000000", KEY.replace("-", "")):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(idempotency_key=value), "bad_idempotency_key")

    def test_the_uuid_version_and_variant_nibbles_are_checked_separately(self) -> None:
        """Each alone, because the nil UUID trips both at once and hid a coverage gap.

        A review's mutations relaxing the version class or the variant class individually both
        left the suite green, since no case had one bad nibble and one good one.
        """
        bad_version = "b2c3d4e5-f607-0819-aa2b-3c4d5e6f7081"
        bad_variant = "b2c3d4e5-f607-4819-2a2b-3c4d5e6f7081"
        for value in (bad_version, bad_variant):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(idempotency_key=value), "bad_idempotency_key")

    def test_upper_case_hex_in_the_key_is_accepted(self) -> None:
        """Shape, not canonicalization: this module normalizes nothing and returns no key."""
        decision = pi.decide_provision_idempotency(KEY.upper(), PAYLOAD, None, False)
        self.assertEqual(decision.outcome, pi.FIRST)

    def test_the_external_key_must_satisfy_the_s0_policy(self) -> None:
        for value in (None, 1, True, "", " lead", "-lead", "a" * 129, "nul\x00", "nonascii-é"):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(external_key=value), "bad_external_key")

    def test_the_taken_flag_must_be_an_exact_bool(self) -> None:
        for value in (None, 0, 1, "", "false", "true", []):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(external_key_taken=value), "bad_external_key_taken")

    def test_a_registered_payload_must_itself_be_shape_valid(self) -> None:
        for value in (1, True, "", " lead", "a" * 129):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(registered_external_key=value),
                                 "bad_registered_external_key")

    def test_none_means_unregistered_and_is_not_a_shape_violation(self) -> None:
        self.assertEqual(self.decide(registered_external_key=None).outcome, pi.FIRST)

    def test_a_str_subclass_cannot_pass_the_exact_type_guards(self) -> None:
        """`type(value) is str`, not `isinstance`: an overridden method must not reach a
        decision."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return 0

        self.assertEqual(self.refusal(external_key=Sneaky(PAYLOAD)), "bad_external_key")
        self.assertEqual(self.refusal(registered_external_key=Sneaky(PAYLOAD)),
                         "bad_registered_external_key")


class TestTheResult(IdempotencyCase):
    def test_the_decision_is_frozen(self) -> None:
        decision = self.decide()
        with self.assertRaises(FrozenInstanceError):
            decision.outcome = pi.REPLAY  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "tenant-secret-value"
        with self.assertRaises(pi.IdempotencyError) as caught:
            pi.decide_provision_idempotency(KEY, secret + "!", None, False)
        self.assertEqual(str(caught.exception), "invalid ProvisionTenant idempotency inputs")
        self.assertNotIn(secret, str(caught.exception))

    def test_every_returned_outcome_is_in_the_declared_set(self) -> None:
        for registered, taken in ((None, False), (PAYLOAD, False), (OTHER_PAYLOAD, False),
                                  (None, True)):
            with self.subTest(registered=registered, taken=taken):
                self.assertIn(self.decide(registered, taken).outcome, pi.OUTCOMES)


if __name__ == "__main__":
    unittest.main()
