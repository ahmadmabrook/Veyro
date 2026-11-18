"""MOD-022 (OPS-03) decision modules. No database, no network, no clock of their own.

Every test here is about a property the TSD states or a shape this codebase has been bitten by
before. Two of them are structural sweeps rather than cases, for the reason the rules file
gives: a per-name list has to be edited whenever somebody adds a name, and that edit is the
moment an unchecked one slips through.
"""

from __future__ import annotations

import pathlib
import re
import unittest
from datetime import UTC, datetime, timedelta

from app.access import credentials, occupancy, offline, passback, policy, zones
from app.access.zones import AccessError

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def a_policy(**overrides: object) -> policy.ZonePolicy:
    """A permissive policy, so a case fails for the one reason it is about."""
    fields: dict[str, object] = {
        "policy_id": "11111111-1111-4111-8111-111111111111",
        "version": 1,
        "opens_minute": None,
        "closes_minute": None,
        "requires_entitlement": False,
        "max_balance_minor": None,
        "min_age_years": None,
        "anti_passback_seconds": 0,
        "capacity": None,
    }
    fields.update(overrides)
    return policy.ZonePolicy(**fields)  # type: ignore[arg-type]


def a_subject(**overrides: object) -> policy.Subject:
    """A member in good standing, for the same reason."""
    fields: dict[str, object] = {
        "person_id": "22222222-2222-4222-8222-222222222222",
        "membership_state": "active",
        "has_entitlement": True,
        "entitlement_reason": None,
        "balance_minor": 0,
        "age_years": 30,
        "safety_hold": False,
    }
    fields.update(overrides)
    return policy.Subject(**fields)  # type: ignore[arg-type]


class ZoneTests(unittest.TestCase):
    def test_a_high_risk_zone_bounds_an_offline_authorization_harder(self):
        """Paragraph 4160: twelve hours standard, two for high risk."""
        self.assertEqual(zones.snapshot_ceiling("standard"), timedelta(hours=12))
        self.assertEqual(zones.snapshot_ceiling("high_risk"), timedelta(hours=2))

    def test_a_snapshot_longer_than_its_zone_admits_is_refused(self):
        zones.check_snapshot_ttl(timedelta(hours=2), risk="high_risk")
        with self.assertRaises(AccessError):
            zones.check_snapshot_ttl(timedelta(hours=3), risk="high_risk")
        # The same TTL is fine at a standard zone, which is the point of the class existing.
        zones.check_snapshot_ttl(timedelta(hours=3), risk="standard")

    def test_an_unknown_risk_class_is_refused_rather_than_defaulted(self):
        # Defaulting an unknown class to `standard` would make a typo buy ten extra hours of
        # offline authority, silently.
        with self.assertRaises(AccessError):
            zones.snapshot_ceiling("medium")
        with self.assertRaises(AccessError):
            zones.check_risk_class("")

    def test_an_exit_reader_decides_nothing(self):
        """Paragraph 4177: egress is never conditioned on software authorization.

        Stated as a function rather than as a policy that happens to allow leaving, because a
        policy can be edited and a missing code path cannot.
        """
        self.assertTrue(zones.decides_entry("entry"))
        self.assertTrue(zones.decides_entry("both"))
        self.assertFalse(zones.decides_entry("exit"))


class CredentialTests(unittest.TestCase):
    def test_nothing_here_can_store_a_credential_in_the_clear(self):
        digest = credentials.digest_of("CARD-0001")
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(digest, credentials.digest_of("  CARD-0001  "))
        with self.assertRaises(credentials.CredentialError):
            credentials.digest_of("   ")
        with self.assertRaises(credentials.CredentialError):
            credentials.check_digest("CARD-0001")

    def test_a_usable_credential_is_not_an_authorized_one(self):
        """The module's whole separation, as a test rather than as a docstring.

        A card belonging to a suspended member identifies that member perfectly well. The
        refusal is `policy.decide`'s, and a `is_usable` that consulted the membership would be
        a credential that authorizes.
        """
        binding = credentials.Binding(
            credential_id="c", person_id="p", kind="nfc_card", state="active",
            issued_at=NOW - timedelta(days=1), expires_at=None, revocation_epoch=0)
        self.assertTrue(credentials.is_usable(binding, at=NOW))
        # There is no `suspended` state at all: a suspension is a fact about the member.
        self.assertNotIn("suspended", credentials.CREDENTIAL_STATES)

    def test_an_expired_or_revoked_credential_stops_identifying(self):
        expired = credentials.Binding(
            credential_id="c", person_id="p", kind="nfc_card", state="active",
            issued_at=NOW - timedelta(days=2), expires_at=NOW, revocation_epoch=0)
        self.assertFalse(credentials.is_usable(expired, at=NOW))
        self.assertTrue(credentials.is_usable(expired, at=NOW - timedelta(seconds=1)))
        revoked = credentials.Binding(
            credential_id="c", person_id="p", kind="nfc_card", state="revoked",
            issued_at=NOW - timedelta(days=2), expires_at=None, revocation_epoch=1)
        self.assertFalse(credentials.is_usable(revoked, at=NOW))

    def test_a_bad_reader_clock_refuses_a_rotating_credential_and_not_a_card(self):
        """Paragraph 4162, and the asymmetry is the point.

        A card number does not expire in thirty seconds, so a reader with a bad clock can
        still match one. A rotating token's entire anti-replay protection *is* the window.
        """
        credentials.check_clock(timedelta(seconds=90), kind="nfc_card")
        credentials.check_clock(timedelta(seconds=59), kind="qr_rotating")
        with self.assertRaises(credentials.CredentialError):
            credentials.check_clock(timedelta(seconds=61), kind="qr_rotating")
        # Symmetric: a reader an hour *behind* is as blind as one an hour ahead.
        with self.assertRaises(credentials.CredentialError):
            credentials.check_clock(timedelta(seconds=-61), kind="qr_rotating")

    def test_a_rotating_token_without_its_window_is_refused(self):
        with self.assertRaises(credentials.CredentialError):
            credentials.check_presentation(
                credentials.Presented(digest="a" * 64, kind="qr_rotating", presented_at=NOW),
                at=NOW)

    def test_a_rotating_token_without_a_counter_or_nonce_is_refused(self):
        """Without them a replayed token is indistinguishable from a fresh one."""
        for counter, nonce in ((None, "n"), (1, ""), (1, "   ")):
            with self.assertRaises(credentials.CredentialError):
                credentials.check_presentation(
                    credentials.Presented(
                        digest="a" * 64, kind="qr_rotating", presented_at=NOW,
                        rotation_counter=counter, nonce=nonce,
                        issued_at=NOW, expires_at=NOW + timedelta(seconds=30)),
                    at=NOW)

    def test_a_token_minted_for_longer_than_the_lifetime_is_refused(self):
        """A screenshot somebody can still use. The reader does not get to extend it."""
        with self.assertRaises(credentials.CredentialError):
            credentials.check_presentation(
                credentials.Presented(
                    digest="a" * 64, kind="qr_rotating", presented_at=NOW,
                    rotation_counter=1, nonce="n", issued_at=NOW,
                    expires_at=NOW + timedelta(minutes=10)),
                at=NOW)

    def test_a_token_is_accepted_inside_the_reader_clock_tolerance_and_not_outside(self):
        def present(at: datetime) -> None:
            credentials.check_presentation(
                credentials.Presented(
                    digest="a" * 64, kind="qr_rotating", presented_at=at,
                    rotation_counter=1, nonce="n", issued_at=NOW,
                    expires_at=NOW + credentials.ROTATING_LIFETIME),
                at=at)

        present(NOW)
        present(NOW - credentials.READER_CLOCK_TOLERANCE + timedelta(seconds=1))
        present(NOW + credentials.ROTATING_LIFETIME + credentials.READER_CLOCK_TOLERANCE
                - timedelta(seconds=1))
        with self.assertRaises(credentials.CredentialError):
            present(NOW - credentials.READER_CLOCK_TOLERANCE - timedelta(seconds=1))
        with self.assertRaises(credentials.CredentialError):
            present(NOW + credentials.ROTATING_LIFETIME + credentials.READER_CLOCK_TOLERANCE)

    def test_a_non_rotating_credential_needs_no_window_at_all(self):
        for kind in ("nfc_card", "physical_card", "wallet_pass", "pin", "staff_assisted"):
            credentials.check_presentation(
                credentials.Presented(digest="a" * 64, kind=kind, presented_at=NOW), at=NOW)

    def test_the_replay_key_separates_tokens_that_must_not_collide(self):
        """Two members' tokens, two counters and two nonces are four different things."""
        def key(digest: str, counter: int, nonce: str) -> str:
            return credentials.replay_key(credentials.Presented(
                digest=digest, kind="qr_rotating", presented_at=NOW,
                rotation_counter=counter, nonce=nonce))

        base = key("a" * 64, 1, "n")
        self.assertNotEqual(base, key("b" * 64, 1, "n"))
        self.assertNotEqual(base, key("a" * 64, 2, "n"))
        self.assertNotEqual(base, key("a" * 64, 1, "m"))
        self.assertEqual(base, key("a" * 64, 1, "n"))

    def test_the_replay_window_is_measured_from_the_server_clock(self):
        """A device claiming an old expiry cannot evict its own replay evidence early."""
        presented = credentials.Presented(
            digest="a" * 64, kind="qr_rotating", presented_at=NOW, rotation_counter=1,
            nonce="n", issued_at=NOW - timedelta(days=1),
            expires_at=NOW - timedelta(days=1) + timedelta(seconds=30))
        self.assertEqual(
            credentials.replay_expiry(presented, at=NOW), NOW + credentials.REPLAY_WINDOW)

    def test_the_replay_window_covers_every_instant_a_reader_would_accept(self):
        """A token is replayable for exactly as long as somebody would still take it."""
        self.assertGreaterEqual(
            credentials.REPLAY_WINDOW,
            credentials.ROTATING_LIFETIME + credentials.READER_CLOCK_TOLERANCE * 2)


class DecisionTests(unittest.TestCase):
    def test_a_member_in_good_standing_is_admitted(self):
        decided = policy.decide(
            subject=a_subject(), policy=a_policy(), local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=None)
        self.assertTrue(decided.granted)
        self.assertEqual(decided.code, "granted")
        self.assertFalse(decided.masked)

    def test_a_decision_cites_the_exact_policy_version(self):
        """Paragraph 1952. A decision re-derived against today's policy is a different one."""
        terms = a_policy(version=7)
        for decided in (
            policy.decide(subject=a_subject(), policy=terms, local_minute=600, at=NOW,
                          seconds_since_last_entry=None, occupancy=None),
            policy.decide(subject=a_subject(membership_state="suspended"), policy=terms,
                          local_minute=600, at=NOW, seconds_since_last_entry=None,
                          occupancy=None),
        ):
            self.assertEqual(decided.policy_id, terms.policy_id)
            self.assertEqual(decided.policy_version, 7)

    def test_a_restricted_reason_is_never_readable_off_a_turnstile(self):
        """Paragraph 1944, the Critical Control.

        Each of these is a fact about somebody's account that whoever is behind them in the
        queue must not learn, and each one's public half is the same single line -- four
        different polite messages would be four different facts.
        """
        cases = {
            "membership_inactive": a_subject(membership_state="suspended"),
            "no_entitlement": a_subject(has_entitlement=False),
            "outstanding_balance": a_subject(balance_minor=5_000),
            "age_restricted": a_subject(age_years=14),
            "safety_hold": a_subject(safety_hold=True),
        }
        terms = a_policy(requires_entitlement=True, max_balance_minor=0, min_age_years=18)
        for code, subject in cases.items():
            decided = policy.decide(
                subject=subject, policy=terms, local_minute=600, at=NOW,
                seconds_since_last_entry=None, occupancy=None)
            self.assertEqual(decided.code, code, code)
            self.assertFalse(decided.granted, code)
            self.assertTrue(decided.masked, code)
            self.assertEqual(decided.public_reason, policy.DISCREET, code)
            # And the private half still says something somebody at the desk can act on.
            self.assertNotEqual(decided.private_reason, policy.DISCREET, code)

    def test_a_caller_cannot_hand_a_restricted_code_a_public_reason(self):
        """The control is a property of the code, not of the call site.

        It is tempting to let one through "just this once" for a better member experience,
        and that is exactly how a Critical Control gets broken -- MOD-013's `priority:
        "critical"` and MOD-009's `guardian_subject_id` are the same shape.
        """
        refused = policy.refuse(
            "outstanding_balance", "owes 5000", public="your account is in arrears")
        self.assertEqual(refused.public_reason, policy.DISCREET)
        self.assertTrue(refused.masked)

    def test_a_public_code_keeps_the_public_reason_it_was_given(self):
        refused = policy.refuse("anti_passback", "used 10 seconds ago", public="too soon")
        self.assertEqual(refused.public_reason, "too soon")
        self.assertFalse(refused.masked)

    def test_an_unknown_reason_code_is_refused(self):
        """A free-text refusal is not a stable reason code. MOD-016 shipped a control that
        matched English words in a reason string and four of them were the enforcement."""
        with self.assertRaises(AccessError):
            policy.refuse("because_i_said_so", "no")

    def test_the_order_of_the_checks_is_the_order_of_the_explanation(self):
        """A member whose card is simply out of hours is told that, not sent to the desk.

        The restricted codes come last on purpose: evaluating an unpaid balance before an
        expired opening window means a lapsed member learns their account is in arrears from
        a door, in front of whoever is behind them.
        """
        decided = policy.decide(
            subject=a_subject(membership_state="suspended", balance_minor=99_999,
                              has_entitlement=False),
            policy=a_policy(opens_minute=6 * 60, closes_minute=23 * 60,
                            requires_entitlement=True, max_balance_minor=0),
            local_minute=2 * 60, at=NOW, seconds_since_last_entry=None, occupancy=None)
        self.assertEqual(decided.code, "outside_opening_hours")
        self.assertFalse(decided.masked)

    def test_a_night_shift_window_wraps_past_midnight(self):
        """22:00 to 06:00 is a 24-hour club, not 'never'."""
        overnight = a_policy(opens_minute=22 * 60, closes_minute=6 * 60)
        for minute in (22 * 60, 23 * 60 + 59, 0, 5 * 60 + 59):
            self.assertTrue(
                policy.decide(subject=a_subject(), policy=overnight, local_minute=minute,
                              at=NOW, seconds_since_last_entry=None,
                              occupancy=None).granted, minute)
        for minute in (6 * 60, 12 * 60, 21 * 60 + 59):
            self.assertEqual(
                policy.decide(subject=a_subject(), policy=overnight, local_minute=minute,
                              at=NOW, seconds_since_last_entry=None,
                              occupancy=None).code, "outside_opening_hours", minute)

    def test_an_ordinary_window_excludes_its_closing_minute(self):
        day = a_policy(opens_minute=6 * 60, closes_minute=23 * 60)
        self.assertTrue(policy.decide(
            subject=a_subject(), policy=day, local_minute=6 * 60, at=NOW,
            seconds_since_last_entry=None, occupancy=None).granted)
        self.assertEqual(policy.decide(
            subject=a_subject(), policy=day, local_minute=23 * 60, at=NOW,
            seconds_since_last_entry=None, occupancy=None).code, "outside_opening_hours")

    def test_an_unknown_date_of_birth_is_not_an_adult_at_a_door(self):
        """**The opposite default from MOD-014, deliberately.**

        MOD-014 treats an undated person as not a minor, because requiring a guardian before
        anybody could read the record of a member who never gave a birthday would block most
        leads. A door is the other way round: the harm is a child in a weights room, and the
        remedy is one question at the desk.
        """
        decided = policy.decide(
            subject=a_subject(age_years=None), policy=a_policy(min_age_years=18),
            local_minute=600, at=NOW, seconds_since_last_entry=None, occupancy=None)
        self.assertEqual(decided.code, "age_restricted")
        self.assertIn("not recorded", decided.private_reason)

    def test_a_zone_with_no_age_rule_admits_a_member_with_no_birthday(self):
        self.assertTrue(policy.decide(
            subject=a_subject(age_years=None), policy=a_policy(), local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=None).granted)

    def test_capacity_refuses_at_the_limit_rather_than_past_it(self):
        full = a_policy(capacity=10)
        self.assertEqual(policy.decide(
            subject=a_subject(), policy=full, local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=10).code, "zone_at_capacity")
        self.assertTrue(policy.decide(
            subject=a_subject(), policy=full, local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=9).granted)

    def test_an_unknown_occupancy_does_not_refuse(self):
        """A zone whose occupancy cannot be read is a zone whose capacity cannot be enforced,
        and refusing everybody because the number is missing shuts the club."""
        self.assertTrue(policy.decide(
            subject=a_subject(), policy=a_policy(capacity=1), local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=None).granted)

    def test_anti_passback_refuses_inside_the_window_and_admits_a_first_entry(self):
        guarded = a_policy(anti_passback_seconds=60)
        self.assertEqual(policy.decide(
            subject=a_subject(), policy=guarded, local_minute=600, at=NOW,
            seconds_since_last_entry=10, occupancy=None).code, "anti_passback")
        self.assertTrue(policy.decide(
            subject=a_subject(), policy=guarded, local_minute=600, at=NOW,
            seconds_since_last_entry=60, occupancy=None).granted)
        # `None` is never, not zero -- MOD-016's `by_subject` conflation one module over.
        self.assertTrue(policy.decide(
            subject=a_subject(), policy=guarded, local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=None).granted)

    def test_a_trialing_membership_is_admitted(self):
        self.assertTrue(policy.decide(
            subject=a_subject(membership_state="trialing"), policy=a_policy(),
            local_minute=600, at=NOW, seconds_since_last_entry=None, occupancy=None).granted)

    def test_a_subject_with_no_membership_at_all_is_not_refused_for_being_one(self):
        """A staff member or a visitor has no membership row, which is not a suspension.

        `membership_state is None` means "this module has nothing to say"; refusing on it
        would make every member of staff fail at their own back door.
        """
        self.assertTrue(policy.decide(
            subject=a_subject(membership_state=None), policy=a_policy(), local_minute=600,
            at=NOW, seconds_since_last_entry=None, occupancy=None).granted)

    def test_an_override_is_its_own_code_rather_than_a_flag_on_a_grant(self):
        """A decision reading `granted` when somebody waved a member through is the shape
        MOD-013's `bypass_policy_ref` was blocked for."""
        decided = policy.override(reason="her card is in the car, I know her")
        self.assertTrue(decided.granted)
        self.assertEqual(decided.code, "granted_by_override")
        self.assertNotEqual(decided.code, "granted")

    def test_an_override_states_why(self):
        for blank in ("", "   ", "\t", "\n"):
            with self.assertRaises(AccessError, msg=repr(blank)):
                policy.override(reason=blank)


class ReasonCodeSweepTests(unittest.TestCase):
    """The two structural sweeps. Both are MOD-020's lesson: an enumeration is a claim about
    what the software does, so the question is not "is this reachable in principle" but
    "which line puts this value in the column"."""

    SOURCES = ("service.py", "policy.py")

    def _module_text(self) -> str:
        root = pathlib.Path(__file__).resolve().parents[1] / "app" / "access"
        return "\n".join((root / name).read_text() for name in self.SOURCES)

    def test_every_declared_reason_code_has_a_writer(self):
        """MOD-020 shipped four declared denial reasons nothing produced, and two declared
        states nothing wrote -- so every member of every cancelled class was recorded absent,
        permanently. A value with no writer is either a gap to disclose or a defect wearing a
        design decision's clothes."""
        text = self._module_text()
        unwritten = [
            code for code in policy.REASON_CODES
            if len(re.findall(rf'"{re.escape(code)}"', text)) < 2
        ]
        self.assertEqual(
            unwritten, [],
            "these reason codes are declared and nothing outside the declaration names "
            "them; grep the writers and either produce the code or remove it")

    def test_every_public_safe_code_is_a_declared_code(self):
        """A stale exemption is worse than none, because it exempts whatever the name
        becomes."""
        self.assertEqual(policy.PUBLIC_SAFE - set(policy.REASON_CODES), set())

    def test_no_code_about_the_person_is_public(self):
        """The five restricted codes are exactly the ones that say something about a member's
        account, and `PUBLIC_SAFE` is checked against that list rather than against itself --
        a sweep that compared the set with a copy of itself would pass forever."""
        about_the_person = {
            "membership_inactive", "no_entitlement", "outstanding_balance", "age_restricted",
            "safety_hold",
        }
        self.assertEqual(about_the_person & policy.PUBLIC_SAFE, set())
        # And everything else is public, so a new code is not restricted by forgetting it.
        self.assertEqual(
            set(policy.REASON_CODES) - about_the_person - policy.PUBLIC_SAFE, set())

    def test_the_discreet_line_is_the_same_string_in_both_halves(self):
        """`acc_decisions_masked_is_the_discreet_line` compares against a literal.

        The constraint cannot call Python and this module cannot read the schema, so the one
        string lives in two places. A service that reworded it would start writing rows the
        database refuses -- or, if the constraint were relaxed instead, rows that read as
        unmasked while the member was told nothing. The pin is what makes that a failed test
        rather than a discovery.
        """
        migration = (
            pathlib.Path(__file__).resolve().parents[1]
            / "migrations" / "tenant" / "0016_access.sql"
        ).read_text()
        self.assertIn(f"public_reason = '{policy.DISCREET}'", migration)

    def test_a_grant_is_not_masked_although_its_two_reasons_differ(self):
        """The case the first version of that constraint got wrong.

        A grant says "welcome" publicly and "every check passed" privately: two different
        strings carrying the same nothing. Read as `masked = (public <> private)` that made
        every successful entry a masked one, and the constraint refused the row -- so the
        module could not admit anybody.
        """
        decided = policy.decide(
            subject=a_subject(), policy=a_policy(), local_minute=600, at=NOW,
            seconds_since_last_entry=None, occupancy=None)
        self.assertNotEqual(decided.public_reason, decided.private_reason)
        self.assertFalse(decided.masked)
        self.assertNotEqual(decided.public_reason, policy.DISCREET)

    def test_masked_means_the_public_half_is_the_discreet_line(self):
        for code in policy.REASON_CODES:
            if code in policy.GRANTS:
                continue
            refused = policy.refuse(code, "a private reason somebody can act on")
            self.assertEqual(
                refused.masked, refused.public_reason == policy.DISCREET, code)

    def test_the_grant_codes_are_the_only_ones_that_open_a_door(self):
        self.assertEqual(policy.GRANTS, {"granted", "granted_by_override"})
        self.assertTrue(policy.GRANTS <= set(policy.REASON_CODES))


class PassbackTests(unittest.TestCase):
    def test_a_credential_never_seen_is_not_a_credential_seen_now(self):
        self.assertIsNone(passback.seconds_since(None, at=NOW))
        entry = passback.Entry(at=NOW - timedelta(seconds=30), zone_id="z", point_id="p",
                               scope="global")
        self.assertEqual(passback.seconds_since(entry, at=NOW), 30)

    def test_an_offline_decision_claims_only_what_it_could_see(self):
        """Paragraph 4163: cross-device global anti-passback is not claimed while
        disconnected. A report saying 'anti-passback enforced' over a period when half of it
        was local overstates the weaker guarantee."""
        self.assertEqual(passback.claim(online=True), "global")
        self.assertEqual(passback.claim(online=False), "controller_group")
        for scope in passback.SCOPES:
            passback.check_scope(scope)
        with self.assertRaises(AccessError):
            passback.check_scope("device")

    def test_two_entries_inside_the_window_are_flagged_as_duplicates(self):
        first = passback.Entry(at=NOW, zone_id="z", point_id="p", scope="controller_group")
        near = passback.Entry(at=NOW + timedelta(seconds=20), zone_id="z", point_id="q",
                              scope="controller_group")
        far = passback.Entry(at=NOW + timedelta(seconds=90), zone_id="z", point_id="q",
                             scope="controller_group")
        self.assertTrue(passback.is_duplicate(first, near, window_seconds=60))
        self.assertFalse(passback.is_duplicate(first, far, window_seconds=60))
        # A zero window is "no anti-passback", not "everything is a duplicate".
        self.assertFalse(passback.is_duplicate(first, near, window_seconds=0))


class OccupancyTests(unittest.TestCase):
    def test_a_zone_with_one_reader_is_advisory(self):
        """A turnstile in and a push bar out counts everybody in and nobody out, so the
        number rises all day. That is a fact about the building, not a defect to reset."""
        self.assertEqual(
            occupancy.confidence(occupancy.Readers(True, True)), "measured")
        self.assertEqual(
            occupancy.confidence(occupancy.Readers(True, False)), "advisory")
        self.assertEqual(
            occupancy.confidence(occupancy.Readers(False, True)), "advisory")
        self.assertEqual(
            occupancy.confidence(occupancy.Readers(False, False)), "advisory")

    def test_the_count_is_floored_at_zero(self):
        readers = occupancy.Readers(True, False)
        self.assertEqual(occupancy.inside(10, 3, readers=readers), 7)
        self.assertEqual(occupancy.inside(3, 10, readers=readers), 0)
        with self.assertRaises(ValueError):
            occupancy.inside(-1, 0, readers=readers)

    def test_the_disclaimer_says_it_is_never_a_muster_source(self):
        """Paragraph 4180, in the module rather than in a comment, so every read carries it."""
        self.assertIn("never the sole", occupancy.NEVER_A_MUSTER)
        self.assertIn("life-safety muster", occupancy.NEVER_A_MUSTER)


class OfflineTests(unittest.TestCase):
    def posture(self, **overrides: object) -> offline.Posture:
        fields: dict[str, object] = {
            "mode": "offline",
            "snapshot_issued_at": NOW - timedelta(hours=1),
            "snapshot_expires_at": NOW + timedelta(hours=1),
            "snapshot_epoch": 5,
            "device_epoch": 5,
            "clock_skew": timedelta(0),
            "snapshot_id": "s",
        }
        fields.update(overrides)
        return offline.Posture(**fields)  # type: ignore[arg-type]

    def test_the_mode_is_derived_from_facts_the_server_can_see(self):
        """**A device that reports its own mode reports the mode it would like to be in.**"""
        self.assertEqual(offline.mode_for(
            clock_skew=timedelta(0), last_sync_at=NOW - timedelta(minutes=1), at=NOW),
            "online")
        self.assertEqual(offline.mode_for(
            clock_skew=timedelta(0), last_sync_at=NOW - timedelta(minutes=30), at=NOW),
            "offline")
        self.assertEqual(offline.mode_for(
            clock_skew=timedelta(0), last_sync_at=None, at=NOW), "offline")
        # A clock too far out outranks everything, including a sync a second ago.
        self.assertEqual(offline.mode_for(
            clock_skew=timedelta(seconds=120), last_sync_at=NOW, at=NOW), "supervised")

    def test_a_reader_with_no_snapshot_decides_nothing(self):
        with self.assertRaises(AccessError):
            offline.check_snapshot_usable(
                self.posture(snapshot_issued_at=None, snapshot_expires_at=None), at=NOW,
                risk="standard")

    def test_an_expired_snapshot_decides_nothing(self):
        with self.assertRaises(AccessError):
            offline.check_snapshot_usable(
                self.posture(snapshot_expires_at=NOW), at=NOW, risk="standard")

    def test_a_snapshot_behind_the_revocation_epoch_decides_nothing(self):
        """It has already missed a withdrawal. MOD-021's rule, at the point of use."""
        with self.assertRaises(AccessError):
            offline.check_snapshot_usable(
                self.posture(snapshot_epoch=4, device_epoch=5), at=NOW, risk="standard")
        with self.assertRaises(AccessError):
            offline.check_snapshot_usable(
                self.posture(snapshot_epoch=None), at=NOW, risk="standard")

    def test_a_snapshot_outliving_its_zones_risk_decides_nothing_there(self):
        long_lived = self.posture(
            snapshot_issued_at=NOW - timedelta(hours=1),
            snapshot_expires_at=NOW + timedelta(hours=5))
        offline.check_snapshot_usable(long_lived, at=NOW, risk="standard")
        with self.assertRaises(AccessError):
            offline.check_snapshot_usable(long_lived, at=NOW, risk="high_risk")

    def test_a_supervised_device_decides_nothing_even_with_a_good_snapshot(self):
        """Its snapshot is fine and its clock is not, which is a different refusal."""
        good = self.posture(mode="supervised")
        offline.check_snapshot_usable(good, at=NOW, risk="standard")
        self.assertFalse(offline.may_decide_offline(good, at=NOW, risk="standard"))
        self.assertTrue(
            offline.may_decide_offline(self.posture(mode="offline"), at=NOW, risk="standard"))

    def test_a_reconciliation_outcome_comes_from_the_closed_set(self):
        for outcome in offline.OUTCOMES:
            offline.check_outcome(outcome)
        with self.assertRaises(AccessError):
            offline.check_outcome("rewritten")

    def test_nothing_in_the_outcome_vocabulary_rewrites_history(self):
        """Paragraph 4168: reconnect reconciliation deduplicates and flags policy conflicts
        rather than rewriting history. The absence is the control, so the test is the absence."""
        for forbidden in ("rewritten", "deleted", "reversed", "corrected", "removed"):
            self.assertNotIn(forbidden, offline.OUTCOMES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
