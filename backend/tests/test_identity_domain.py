"""MOD-007 IAM-01: the cryptography and the policy, with no database.

The TOTP and HOTP cases are the RFC's own published vectors. An implementation that passes a
test written from the same reading as the implementation proves nothing; these numbers come from
outside this repository.
"""

import unittest
from datetime import UTC, datetime, timedelta

from app.identity import policy, secrets

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

# Cheap parameters: these tests exercise the logic, not the cost factor. The default cost is
# asserted separately in ScryptParameterTests.
FAST = {"n": 2**10, "r": 8, "p": 1, "dklen": 32}


class HashSecretTests(unittest.TestCase):
    def test_a_secret_verifies_and_a_wrong_one_does_not(self):
        stored = secrets.hash_secret("correct horse battery staple", params=FAST)
        self.assertTrue(secrets.verify_secret(stored, "correct horse battery staple"))
        self.assertFalse(secrets.verify_secret(stored, "correct horse battery stapl"))
        self.assertFalse(secrets.verify_secret(stored, ""))

    def test_the_same_secret_hashes_differently_every_time(self):
        """A per-credential salt is what stops one cracked hash from cracking every reuse."""
        first = secrets.hash_secret("same", params=FAST)
        second = secrets.hash_secret("same", params=FAST)
        self.assertNotEqual(first.salt, second.salt)
        self.assertNotEqual(first.digest, second.digest)
        self.assertTrue(secrets.verify_secret(first, "same"))
        self.assertTrue(secrets.verify_secret(second, "same"))

    def test_unicode_is_normalised_so_the_same_characters_match(self):
        composed = "café"          # é as one code point
        decomposed = "café"       # e followed by a combining acute
        self.assertNotEqual(composed, decomposed)
        stored = secrets.hash_secret(composed, params=FAST)
        self.assertTrue(secrets.verify_secret(stored, decomposed))

    def test_an_empty_secret_cannot_be_stored(self):
        with self.assertRaises(secrets.SecretError):
            secrets.hash_secret("")

    def test_a_corrupt_stored_row_raises_rather_than_reading_as_a_wrong_password(self):
        good = secrets.hash_secret("x", params=FAST)
        for broken in (
            secrets.HashedSecret("bcrypt", good.salt, good.digest, good.params),
            secrets.HashedSecret(secrets.SCRYPT, b"\x00", good.digest, good.params),
        ):
            with self.assertRaises(secrets.SecretError):
                secrets.verify_secret(broken, "x")

    def test_salt_and_digest_are_long_enough_to_mean_anything(self):
        stored = secrets.hash_secret("x", params=FAST)
        self.assertGreaterEqual(len(stored.salt), 16)
        self.assertEqual(len(stored.digest), 32)


class ScryptParameterTests(unittest.TestCase):
    def test_the_shipped_cost_is_not_accidentally_trivial(self):
        """A regression that lowered n would silently make every stored password cheap."""
        self.assertGreaterEqual(secrets.DEFAULT_SCRYPT_PARAMS["n"], 2**14)
        self.assertGreaterEqual(secrets.DEFAULT_SCRYPT_PARAMS["r"], 8)
        self.assertEqual(secrets.DEFAULT_SCRYPT_PARAMS["dklen"], 32)

    def test_a_hash_made_under_weaker_parameters_is_flagged_for_rehash(self):
        weak = secrets.hash_secret("x", params=FAST)
        self.assertTrue(secrets.needs_rehash(weak))
        strong = secrets.HashedSecret(secrets.SCRYPT, weak.salt, weak.digest,
                                      secrets.DEFAULT_SCRYPT_PARAMS)
        self.assertFalse(secrets.needs_rehash(strong))

    def test_only_the_declared_parameters_reach_the_column(self):
        self.assertEqual(
            secrets.serialize_params({"n": 2, "r": 8, "p": 1, "dklen": 32, "injected": 9}),
            {"n": 2, "r": 8, "p": 1, "dklen": 32},
        )


class SessionTokenTests(unittest.TestCase):
    def test_a_minted_token_matches_its_own_digest_and_nothing_else(self):
        minted = secrets.mint_session_token()
        self.assertEqual(len(minted.digest), 32)
        self.assertTrue(secrets.tokens_match(minted.token, minted.digest))
        self.assertFalse(secrets.tokens_match(minted.token + "x", minted.digest))

    def test_tokens_do_not_repeat(self):
        minted = {secrets.mint_session_token().token for _ in range(500)}
        self.assertEqual(len(minted), 500)

    def test_a_token_carries_enough_entropy_to_be_unguessable(self):
        """32 bytes through urlsafe base64 is 43 characters; anything shorter is a weaker token."""
        self.assertGreaterEqual(len(secrets.mint_session_token().token), 43)


class RecoveryCodeTests(unittest.TestCase):
    def test_codes_are_unique_grouped_and_free_of_confusable_characters(self):
        codes = secrets.generate_recovery_codes(20)
        self.assertEqual(len(set(codes)), 20)
        for code in codes:
            groups = code.split("-")
            self.assertEqual(len(groups), 3)
            self.assertTrue(all(len(g) == 4 for g in groups))
            self.assertFalse(set(code) & set("01OIL"), code)

    def test_a_nonsensical_shape_is_refused(self):
        for kwargs in ({"count": 0}, {"groups": 0}, {"group_size": 0}):
            with self.assertRaises(secrets.SecretError):
                secrets.generate_recovery_codes(**kwargs)


class HotpRfc4226Tests(unittest.TestCase):
    """Appendix D of RFC 4226, verbatim."""

    SECRET = b"12345678901234567890"
    EXPECTED = ["755224", "287082", "359152", "969429", "338314",
                "254676", "287922", "162583", "399871", "520489"]

    def test_the_published_counter_sequence(self):
        for counter, expected in enumerate(self.EXPECTED):
            self.assertEqual(secrets.hotp(self.SECRET, counter), expected, counter)

    def test_a_negative_counter_is_refused(self):
        with self.assertRaises(secrets.SecretError):
            secrets.hotp(self.SECRET, -1)


class TotpRfc6238Tests(unittest.TestCase):
    """Appendix B of RFC 6238, all three algorithms, verbatim."""

    SHA1 = b"12345678901234567890"
    SHA256 = b"12345678901234567890123456789012"
    SHA512 = b"1234567890123456789012345678901234567890123456789012345678901234"

    VECTORS = [
        (59, "94287082", "46119246", "90693936"),
        (1111111109, "07081804", "68084774", "25091201"),
        (1111111111, "14050471", "67062674", "99943326"),
        (1234567890, "89005924", "91819424", "93441116"),
        (2000000000, "69279037", "90698825", "38618901"),
        (20000000000, "65353130", "77737706", "47863826"),
    ]

    def test_every_published_vector(self):
        for at, sha1, sha256, sha512 in self.VECTORS:
            self.assertEqual(secrets.totp(self.SHA1, at, digits=8), sha1, at)
            self.assertEqual(
                secrets.totp(self.SHA256, at, digits=8, algorithm="sha256"), sha256, at)
            self.assertEqual(
                secrets.totp(self.SHA512, at, digits=8, algorithm="sha512"), sha512, at)

    def test_a_code_is_accepted_inside_the_drift_window_and_not_outside_it(self):
        at = 1111111111
        code = secrets.totp(self.SHA1, at, digits=8)
        self.assertTrue(secrets.totp_matches(self.SHA1, at + 30, code, digits=8))
        self.assertTrue(secrets.totp_matches(self.SHA1, at - 30, code, digits=8))
        self.assertFalse(secrets.totp_matches(self.SHA1, at + 300, code, digits=8))

    def test_drift_can_be_turned_off_entirely(self):
        at = 1111111111
        code = secrets.totp(self.SHA1, at, digits=8)
        self.assertTrue(secrets.totp_matches(self.SHA1, at, code, digits=8, drift_steps=0))
        self.assertFalse(
            secrets.totp_matches(self.SHA1, at + 30, code, digits=8, drift_steps=0))

    def test_a_wrong_code_is_rejected_at_every_drift(self):
        self.assertFalse(secrets.totp_matches(self.SHA1, 1111111111, "00000000", digits=8))

    def test_nonsensical_parameters_are_refused(self):
        with self.assertRaises(secrets.SecretError):
            secrets.totp(self.SHA1, 1, step=0)
        with self.assertRaises(secrets.SecretError):
            secrets.totp_matches(self.SHA1, 1, "000000", drift_steps=-1)

    def test_the_base32_form_is_what_an_authenticator_app_expects(self):
        self.assertEqual(secrets.base32_secret(self.SHA1), "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")


class AssuranceTests(unittest.TestCase):
    def test_each_action_class_has_a_level(self):
        self.assertEqual(policy.required_aal("routine"), 1)
        self.assertEqual(policy.required_aal("financial"), 2)
        self.assertEqual(policy.required_aal("privileged"), 3)
        self.assertEqual(policy.required_aal("biometric_sensitive"), 3)

    def test_an_unclassified_action_fails_closed_rather_than_defaulting_to_routine(self):
        with self.assertRaises(policy.PolicyError) as caught:
            policy.required_aal("delete_everything")
        self.assertEqual(caught.exception.code, "unknown_action_class")

    def test_a_password_alone_never_reaches_level_two(self):
        self.assertEqual(policy.assurance_for(["password"]), 1)

    def test_two_independent_factors_reach_level_two(self):
        self.assertEqual(policy.assurance_for(["password", "totp"]), 2)
        self.assertEqual(policy.assurance_for(["password", "recovery_code"]), 2)

    def test_the_same_factor_twice_is_not_two_factors(self):
        self.assertEqual(policy.assurance_for(["password", "password"]), 1)

    def test_only_a_hardware_authenticator_reaches_level_three(self):
        self.assertEqual(policy.assurance_for(["passkey_synced"]), 2)
        self.assertEqual(policy.assurance_for(["passkey_hardware"]), 3)

    def test_no_factors_is_no_assurance(self):
        self.assertEqual(policy.assurance_for([]), 0)

    def test_an_unknown_factor_is_refused(self):
        with self.assertRaises(policy.PolicyError):
            policy.assurance_for(["telepathy"])

    def test_step_up_is_required_exactly_when_the_session_is_below_the_bar(self):
        self.assertFalse(policy.needs_step_up(1, "routine"))
        self.assertTrue(policy.needs_step_up(1, "financial"))
        self.assertTrue(policy.needs_step_up(2, "privileged"))
        self.assertFalse(policy.needs_step_up(3, "privileged"))


class SessionPolicyTests(unittest.TestCase):
    def test_higher_assurance_expires_sooner(self):
        lifetimes = [policy.session_expiry(NOW, aal) - NOW for aal in (1, 2, 3)]
        self.assertEqual(lifetimes, sorted(lifetimes, reverse=True))

    def test_an_unknown_level_has_no_lifetime(self):
        with self.assertRaises(policy.PolicyError):
            policy.session_expiry(NOW, 9)

    def test_an_active_session_is_usable(self):
        state = policy.SessionState(aal=1, expires_at=NOW + timedelta(hours=1))
        self.assertEqual(policy.session_usable(state, NOW), (True, "active"))

    def test_an_expired_session_is_not(self):
        state = policy.SessionState(aal=1, expires_at=NOW)
        self.assertEqual(policy.session_usable(state, NOW), (False, "expired"))

    def test_revocation_is_reported_ahead_of_expiry(self):
        state = policy.SessionState(aal=1, expires_at=NOW - timedelta(hours=1),
                                    revoked_at=NOW - timedelta(hours=2))
        self.assertEqual(policy.session_usable(state, NOW), (False, "revoked"))

    def test_a_revocation_scheduled_in_the_future_does_not_bite_yet(self):
        state = policy.SessionState(aal=1, expires_at=NOW + timedelta(hours=2),
                                    revoked_at=NOW + timedelta(hours=1))
        self.assertEqual(policy.session_usable(state, NOW), (True, "active"))


class LockoutTests(unittest.TestCase):
    def test_failures_accumulate_and_lock_at_the_threshold(self):
        state = policy.LockoutState(failed_attempts=0)
        for _ in range(policy.MAX_FAILED_ATTEMPTS - 1):
            state = policy.after_failure(state, NOW)
            self.assertFalse(policy.locked(state, NOW))
        state = policy.after_failure(state, NOW)
        self.assertTrue(policy.locked(state, NOW))

    def test_a_lock_expires_on_its_own(self):
        state = policy.LockoutState(failed_attempts=9, locked_until=NOW + timedelta(minutes=1))
        self.assertTrue(policy.locked(state, NOW))
        self.assertFalse(policy.locked(state, NOW + timedelta(minutes=2)))

    def test_attempts_against_a_locked_account_stay_visible(self):
        state = policy.LockoutState(failed_attempts=5, locked_until=NOW + timedelta(minutes=5))
        self.assertEqual(policy.after_failure(state, NOW).failed_attempts, 6)

    def test_success_clears_the_count_and_the_lock(self):
        cleared = policy.after_success(
            policy.LockoutState(failed_attempts=9, locked_until=NOW + timedelta(minutes=5))
        )
        self.assertEqual((cleared.failed_attempts, cleared.locked_until), (0, None))


class SignCountTests(unittest.TestCase):
    def test_a_counter_that_advances_is_accepted(self):
        self.assertTrue(policy.sign_count_acceptable(7, 8))

    def test_a_repeated_or_reversed_counter_means_a_clone(self):
        self.assertFalse(policy.sign_count_acceptable(7, 7))
        self.assertFalse(policy.sign_count_acceptable(7, 6))

    def test_an_authenticator_without_a_counter_reports_zero_forever(self):
        self.assertTrue(policy.sign_count_acceptable(0, 0))

    def test_a_counter_that_drops_back_to_zero_is_still_a_clone(self):
        self.assertFalse(policy.sign_count_acceptable(5, 0))

    def test_a_negative_counter_is_refused(self):
        with self.assertRaises(policy.PolicyError):
            policy.sign_count_acceptable(-1, 1)


class ChallengeTests(unittest.TestCase):
    def test_a_fresh_challenge_is_pending(self):
        self.assertEqual(
            policy.challenge_usable(NOW + timedelta(minutes=1), None, NOW), (True, "pending"))

    def test_an_expired_challenge_is_refused(self):
        self.assertEqual(
            policy.challenge_usable(NOW, None, NOW), (False, "expired"))

    def test_a_consumed_challenge_cannot_be_replayed_even_before_it_expires(self):
        self.assertEqual(
            policy.challenge_usable(NOW + timedelta(minutes=1), NOW, NOW),
            (False, "already_used"),
        )

    def test_the_lifetime_is_short(self):
        self.assertLessEqual(policy.challenge_expiry(NOW) - NOW, timedelta(minutes=10))


class RiskTests(unittest.TestCase):
    def test_a_known_device_with_a_clean_history_needs_no_challenge(self):
        signals = policy.RiskSignals(known_device=True, recent_failures=0)
        self.assertEqual(policy.risk_requires_challenge(signals), (False, "no_signal"))

    def test_an_unknown_device_is_challenged(self):
        signals = policy.RiskSignals(known_device=False, recent_failures=0)
        self.assertEqual(policy.risk_requires_challenge(signals), (True, "unknown_device"))

    def test_impossible_travel_outranks_every_other_signal(self):
        signals = policy.RiskSignals(known_device=True, recent_failures=0,
                                     impossible_travel=True)
        self.assertEqual(policy.risk_requires_challenge(signals), (True, "impossible_travel"))

    def test_recent_failures_on_a_known_device_are_still_a_signal(self):
        signals = policy.RiskSignals(known_device=True, recent_failures=3)
        self.assertEqual(policy.risk_requires_challenge(signals), (True, "recent_failures"))

    def test_a_new_country_on_a_new_device_is_named_as_such(self):
        signals = policy.RiskSignals(known_device=False, recent_failures=0, new_country=True)
        self.assertEqual(policy.risk_requires_challenge(signals),
                         (True, "new_country_new_device"))


if __name__ == "__main__":
    unittest.main()


class CapabilityLifetimeTests(unittest.TestCase):
    """A session's window follows what it can do, not only the level it was scored at."""

    def test_a_recovery_session_expires_on_the_elevated_schedule(self):
        routine = policy.session_expiry(NOW, policy.AAL_ROUTINE, ["password"])
        reset_capable = policy.session_expiry(NOW, policy.AAL_ROUTINE, ["recovery_code"])
        self.assertLess(reset_capable, routine)
        self.assertEqual(reset_capable - NOW, policy.SESSION_LIFETIME[policy.AAL_ELEVATED])

    def test_an_elevated_session_is_not_lengthened_by_carrying_a_recovery_factor(self):
        self.assertEqual(
            policy.session_expiry(NOW, policy.AAL_HARDWARE, ["recovery_code"]) - NOW,
            policy.SESSION_LIFETIME[policy.AAL_HARDWARE],
        )

    def test_a_fixed_window_covers_every_elevated_or_reset_capable_session(self):
        self.assertFalse(policy.window_is_fixed(policy.AAL_ROUTINE, ["password"]))
        self.assertTrue(policy.window_is_fixed(policy.AAL_ROUTINE, ["recovery_code"]))
        self.assertTrue(policy.window_is_fixed(policy.AAL_ELEVATED, ["password", "totp"]))

    def test_the_default_is_unchanged_when_no_factors_are_given(self):
        self.assertEqual(policy.session_expiry(NOW, policy.AAL_ROUTINE) - NOW,
                         policy.SESSION_LIFETIME[policy.AAL_ROUTINE])
