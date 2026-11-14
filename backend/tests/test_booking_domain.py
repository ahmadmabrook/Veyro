"""MOD-020 OPS-02's decision functions, with no database.

The cases that matter are the ones about the invariants paragraph 4697 names and the Critical
Controls paragraph 1888 and 1889 name: a stable denial, a queue a member can predict, a
missing fact refusing rather than passing, and the predictive score this build declines to
compute.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.booking import appeals, attendance, consequence, denial, policy, waitlist
from app.booking.denial import BookingError


def at(day: int, hour: int = 18) -> datetime:
    return datetime(2026, 6, day, hour, tzinfo=UTC)


class PolicyTests(unittest.TestCase):
    def test_a_sane_policy_is_accepted(self):
        policy.check_policy(policy.Policy())

    def test_a_strike_before_a_warning_is_refused(self):
        """A sanction with no notice is what an appeal exists to overturn."""
        with self.assertRaises(BookingError):
            policy.check_policy(policy.Policy(
                warn_after_no_shows=3, strike_after_no_shows=2))

    def test_a_cancellation_window_longer_than_a_week_is_refused(self):
        with self.assertRaises(BookingError):
            policy.check_policy(policy.Policy(cancellation_hours=200))

    def test_a_quota_of_zero_is_refused_and_an_absent_one_admits_everything(self):
        """`None` and `0` are different statements and only one of them is meant."""
        with self.assertRaises(BookingError):
            policy.check_policy(policy.Policy(quota=0))
        self.assertTrue(policy.within_quota(10_000, policy=policy.Policy(quota=None)))

    def test_a_rolling_quota_cannot_be_defeated_by_booking_order(self):
        """**The defect this replaces was reachable with no trick beyond request order.** The
        window ran backwards from the session, so a member on three a week booked the last
        class of the week first and every earlier booking saw an empty window: seven classes
        under a quota of three. The rule now is that no window of that length may hold more
        than the quota, which is the same answer whichever order they book in.
        """
        week = [at(16 + d) for d in range(7)]
        for order in (week, list(reversed(week)), [week[3], week[0], week[6], week[1],
                                                   week[5], week[2], week[4]]):
            booked: list[datetime] = []
            for session_at in order:
                if policy.quota_allows(session_at, booked,
                                       policy=policy.Policy(quota=3), timezone="UTC"):
                    booked.append(session_at)
            self.assertEqual(len(booked), 3, order)

    def test_two_sessions_at_the_same_instant_are_both_counted(self):
        """The old anchor sat on its own window's excluded closing edge, so five classes at six
        o'clock in five studios each saw nobody else -- no ordering needed at all."""
        booked: list[datetime] = []
        for _ in range(5):
            if policy.quota_allows(at(16), booked,
                                   policy=policy.Policy(quota=1), timezone="UTC"):
                booked.append(at(16))
        self.assertEqual(len(booked), 1)

    def test_a_quota_refuses_once_it_is_committed_and_admits_below_it(self):
        """Both directions, because `return used < quota` survived every mutation the suite
        had: a reviewer replaced the whole body with `return True` and nothing failed."""
        two = [at(16), at(17)]
        self.assertFalse(policy.quota_allows(at(18), two,
                                             policy=policy.Policy(quota=2),
                                             timezone="UTC"))
        self.assertTrue(policy.quota_allows(at(18), two,
                                            policy=policy.Policy(quota=3),
                                            timezone="UTC"))

    def test_a_quota_that_is_unset_admits_everything(self):
        self.assertTrue(policy.quota_allows(
            at(18), [at(d) for d in range(1, 29)],
            policy=policy.Policy(quota=None), timezone="UTC"))

    def test_a_rolling_window_is_the_period_it_names(self):
        start, end = policy.quota_span("rolling_7_days", at=at(15), timezone="UTC")
        self.assertEqual(end - start, timedelta(days=14))
        self.assertEqual(start, at(15) - timedelta(days=7))
        self.assertEqual(end, at(15) + timedelta(days=7))
        self.assertEqual(policy.rolling_days("rolling_30_days"), 30)

    def test_a_calendar_quota_is_counted_in_the_sessions_own_timezone(self):
        """**Four classes on one Sydney day under a quota of two a day.** The bucket was
        computed on whatever zone the instant carried, so in Sydney the allowance reset at
        eleven in the morning and a member took two before it and two after. The session
        carries its own zone precisely because neither fact is derivable from the other.
        """
        syd = ZoneInfo("Australia/Sydney")
        booked: list[datetime] = []
        for hour in (6, 9, 12, 18):
            moment = datetime(2026, 11, 16, hour, tzinfo=syd).astimezone(UTC)
            if policy.quota_allows(moment, booked,
                                   policy=policy.Policy(quota=2, quota_period="day"),
                                   timezone="Australia/Sydney"):
                booked.append(moment)
        self.assertEqual(len(booked), 2)

    def test_a_calendar_bucket_is_the_local_day_not_a_span_of_hours(self):
        start, end = policy.quota_bucket(
            "day", at=datetime(2026, 11, 16, 23, tzinfo=UTC), timezone="Asia/Amman")
        self.assertEqual(start.astimezone(ZoneInfo("Asia/Amman")).hour, 0)
        self.assertEqual(end - start, timedelta(days=1))

    def test_a_naive_instant_has_no_zone_to_convert_out_of(self):
        with self.assertRaises(BookingError):
            policy.quota_bucket("day", at=datetime(2026, 11, 16, 18), timezone="UTC")

    def test_a_bucket_refuses_an_unknown_zone_and_a_rolling_period(self):
        with self.assertRaises(BookingError):
            policy.quota_bucket("day", at=at(16), timezone="Mars/Olympus")
        with self.assertRaises(BookingError):
            policy.quota_bucket("rolling_7_days", at=at(16), timezone="UTC")
        with self.assertRaises(BookingError):
            policy.rolling_days("day")

    def test_a_calendar_week_starts_on_monday(self):
        start, end = policy.quota_bucket("week", at=at(17), timezone="UTC")
        self.assertEqual(start.weekday(), 0)
        self.assertEqual(end - start, timedelta(days=7))

    def test_cancelling_inside_the_window_is_late_and_after_the_start_is_too(self):
        """A member who cancels during the class has not attended it; treating that as an
        ordinary cancellation is how a no-show becomes free."""
        rules = policy.Policy(cancellation_hours=12)
        self.assertFalse(policy.cancellation_is_late(at(10), at=at(9, 0), policy=rules))
        self.assertTrue(policy.cancellation_is_late(at(10), at=at(10, 10), policy=rules))
        self.assertTrue(policy.cancellation_is_late(at(10), at=at(10, 23), policy=rules))

    def test_a_window_of_zero_hours_is_never_late(self):
        rules = policy.Policy(cancellation_hours=0)
        self.assertFalse(policy.cancellation_is_late(at(10), at=at(10, 23), policy=rules))

    def test_the_concurrent_limit_is_a_limit(self):
        rules = policy.Policy(max_concurrent=2)
        self.assertTrue(policy.within_concurrent_limit(1, policy=rules))
        self.assertFalse(policy.within_concurrent_limit(2, policy=rules))
        with self.assertRaises(BookingError):
            policy.within_concurrent_limit(-1, policy=rules)


class DenialTests(unittest.TestCase):
    def test_every_reason_is_declared(self):
        for reason in denial.DENIAL_REASONS:
            denial.check_reason(reason)
        with self.assertRaises(BookingError):
            denial.check_reason("because")

    def test_a_full_class_offers_the_waitlist_and_a_full_waitlist_does_not(self):
        """Two different offers, and a surface switching on the reason needs to tell them
        apart."""
        full = denial.Denial(reason="full", detail="x", offer_waitlist=True)
        closed = denial.Denial(reason="waitlist_full", detail="x")
        self.assertTrue(full.offer_waitlist)
        self.assertFalse(closed.offer_waitlist)
        self.assertFalse(denial.is_stable(full, closed))

    def test_two_denials_of_the_same_kind_are_stable(self):
        """Paragraph 5032, as something a test can assert."""
        first = denial.Denial(reason="full", detail="all held", offer_waitlist=True)
        second = denial.Denial(reason="full", detail="all held too", offer_waitlist=True)
        self.assertTrue(denial.is_stable(first, second))


class WaitlistTests(unittest.TestCase):
    def entry(self, n: int, **kw) -> waitlist.Entry:
        fields = {"entry_id": f"e{n}", "person_id": f"p{n}",
                  "joined_at": at(1, 9) + timedelta(minutes=n), "state": "waiting"}
        fields.update(kw)
        return waitlist.Entry(**fields)  # type: ignore[arg-type]

    def test_first_come_orders_by_when_somebody_joined(self):
        entries = [self.entry(3), self.entry(1), self.entry(2)]
        order = waitlist.ordered(entries, policy=policy.Policy())
        self.assertEqual([e.entry_id for e in order], ["e1", "e2", "e3"])

    def test_a_tier_rule_orders_by_tier_then_by_arrival(self):
        entries = [self.entry(1, tier=2), self.entry(2, tier=1), self.entry(3, tier=1)]
        rules = policy.Policy(priority_rule="membership_tier")
        order = waitlist.ordered(entries, policy=rules)
        self.assertEqual([e.entry_id for e in order], ["e2", "e3", "e1"])

    def test_the_order_is_deterministic_when_two_joined_at_once(self):
        """A member watching their position move for no reason is the complaint this
        prevents."""
        same = at(1, 9)
        entries = [self.entry(2, joined_at=same), self.entry(1, joined_at=same)]
        for attempt in range(3):
            order = waitlist.ordered(entries, policy=policy.Policy())
            self.assertEqual([e.entry_id for e in order], ["e1", "e2"], attempt)

    def test_a_position_counts_from_one(self):
        entries = [self.entry(1), self.entry(2)]
        self.assertEqual(
            waitlist.position_of(entries, "e2", policy=policy.Policy()), 2)
        self.assertIsNone(
            waitlist.position_of(entries, "nobody", policy=policy.Policy()))

    def test_a_live_offer_holds_one_place_not_the_whole_queue(self):
        """**One place, not a veto.** The first version returned nobody while *any* offer was
        outstanding, so five cancellations two hours before a class filled two seats and three
        waiting members did not get in. The guard against double-allocation is MOD-019's
        hold; this is arithmetic.
        """
        rules = policy.Policy()
        entries = [
            self.entry(1, state="offered", offered_at=at(1, 9),
                       offer_expires_at=at(1, 10)),
            self.entry(2),
            self.entry(3),
        ]
        # One place free and one offer live: nothing more to give.
        self.assertEqual(
            waitlist.next_to_offer(entries, policy=rules, at=at(1, 9), places=1), [])
        # Three free and one live: the next two.
        self.assertEqual(
            [e.entry_id for e in waitlist.next_to_offer(
                entries, policy=rules, at=at(1, 9), places=3)],
            ["e2", "e3"])
        # Once the offer lapses it stops counting against the free places, so the next
        # member is reachable -- but the lapsed entry is still `offered` until something
        # sweeps it, and `next_to_offer` will not hand its own place back before then. That
        # is the honest order: the sweep writes `expired`, and *then* it is a candidate at its
        # own position, which `ReviewRegressionTests` asserts.
        self.assertEqual(
            [e.entry_id for e in waitlist.next_to_offer(
                entries, policy=rules, at=at(1, 11), places=1)],
            ["e2"])
        # No free places offers nobody, whoever is waiting.
        self.assertEqual(
            waitlist.next_to_offer(entries, policy=rules, at=at(1, 11), places=0), [])

    def test_an_expired_offer_goes_back_to_waiting_and_a_decline_does_not(self):
        """A member asleep at six did not decline, and sending them to the back would make the
        waitlist a lottery about who is awake."""
        waitlist.check_transition("expired", "waiting")
        with self.assertRaises(BookingError):
            waitlist.check_transition("declined", "waiting")

    def test_an_offer_with_no_expiry_is_refused(self):
        with self.assertRaises(BookingError):
            waitlist.check_entry(self.entry(1, state="offered", offered_at=at(1, 9)))

    def test_only_a_live_offer_can_be_confirmed(self):
        waiting = self.entry(1)
        with self.assertRaises(BookingError):
            waitlist.may_confirm(waiting, at=at(1, 9))
        offered = self.entry(1, state="offered", offered_at=at(1, 9),
                             offer_expires_at=at(1, 10))
        waitlist.may_confirm(offered, at=at(1, 9, ))
        with self.assertRaises(BookingError):
            waitlist.may_confirm(offered, at=at(1, 11))

    def test_a_waiting_entry_has_not_expired(self):
        """Reporting True would make a sweep release a place nobody was holding."""
        self.assertFalse(waitlist.offer_has_expired(self.entry(1), at=at(9)))


class AttendanceTests(unittest.TestCase):
    def facts(self, **kw) -> attendance.Attendance:
        fields = {"booking_state": "booked", "session_starts_at": at(10, 18),
                  "session_ends_at": at(10, 19)}
        fields.update(kw)
        return attendance.Attendance(**fields)  # type: ignore[arg-type]

    def test_check_in_opens_an_hour_before_and_closes_after_the_grace(self):
        opens, closes = attendance.checkin_window(
            at(10, 18), policy=policy.Policy(checkin_grace_minutes=15))
        self.assertEqual(opens, at(10, 17))
        self.assertEqual(closes, at(10, 18) + timedelta(minutes=15))

    def test_checking_in_too_early_or_too_late_is_refused(self):
        rules = policy.Policy(checkin_grace_minutes=15)
        with self.assertRaises(BookingError):
            attendance.may_check_in(self.facts(), at=at(10, 16), policy=rules)
        with self.assertRaises(BookingError):
            attendance.may_check_in(
                self.facts(), at=at(10, 19), policy=rules)
        attendance.may_check_in(self.facts(), at=at(10, 18), policy=rules)

    def test_a_no_show_waits_for_both_the_window_and_the_session(self):
        """**Both, which is why `settle` is `or`.** A member inside the grace period has not
        missed the class and a class still running has not been missed either, so a booking is
        a no-show only once neither is true. The first version read the window alone and
        called a booking on a two-hour class a no-show sixteen minutes in.
        """
        rules = policy.Policy(checkin_grace_minutes=15)
        # Not yet: the window is open.
        self.assertFalse(attendance.is_no_show(
            self.facts(), at=at(10, 18), policy=rules))
        # Window shut, but the class is still running.
        long_class = self.facts(session_ends_at=at(10, 20))
        self.assertFalse(attendance.is_no_show(long_class, at=at(10, 19), policy=rules))
        # Both past, and nobody came.
        self.assertTrue(attendance.is_no_show(
            self.facts(), at=at(10, 20), policy=rules))
        # Somebody came.
        self.assertFalse(attendance.is_no_show(
            self.facts(checked_in_at=at(10, 18)), at=at(10, 20), policy=rules))
        # A cancelled booking is not a no-show.
        self.assertFalse(attendance.is_no_show(
            self.facts(booking_state="cancelled"), at=at(10, 23), policy=rules))

    def test_a_member_inside_the_grace_period_is_not_settled(self):
        """**The worst defect this module shipped**: the guard required *both* reasons, so a
        settlement went ahead as soon as the session ended even with the check-in window still
        open -- and a grace period longer than the class is inside `check_policy`'s bounds,
        which a thirty-minute slot with three-quarters of an hour of grace reaches without
        trying. A member who walked in ten minutes late was written to `no_show` the moment
        the class finished: no way back, the fee charged, the strike counted, and the front
        desk's later check-in refused because the state had moved.
        """
        rules = policy.Policy(checkin_grace_minutes=45)
        short = self.facts(session_ends_at=at(10, 18) + timedelta(minutes=30))
        for minutes in (31, 44):
            moment = at(10, 18) + timedelta(minutes=minutes)
            # They may still check in...
            attendance.may_check_in(short, at=moment, policy=rules)
            # ...so they are not settled.
            with self.assertRaises(BookingError):
                attendance.settle(short, at=moment, policy=rules)
        # Once the window shuts, both agree.
        late = at(10, 18) + timedelta(minutes=46)
        self.assertEqual(attendance.settle(short, at=late, policy=rules), "no_show")

    def test_settling_before_the_session_is_over_is_refused(self):
        """A settlement is final, so settling early makes a member on their way a no-show for
        ever."""
        rules = policy.Policy(checkin_grace_minutes=15)
        with self.assertRaises(BookingError):
            attendance.settle(self.facts(), at=at(10, 18), policy=rules)
        with self.assertRaises(BookingError):
            # The window has shut but the class has not finished.
            attendance.settle(self.facts(session_ends_at=at(10, 20)),
                              at=at(10, 19), policy=rules)
        self.assertEqual(
            attendance.settle(self.facts(), at=at(10, 20), policy=rules), "no_show")
        self.assertEqual(
            attendance.settle(self.facts(checked_in_at=at(10, 18)), at=at(10, 20),
                              policy=rules),
            "attended")

    def test_settle_and_is_no_show_cannot_disagree(self):
        """They answered differently on the same booking at the same instant, which is a trap
        for whoever wires up the one nothing calls. `settle` asks `is_no_show` now."""
        rules = policy.Policy(checkin_grace_minutes=45)
        short = self.facts(session_ends_at=at(10, 18) + timedelta(minutes=30))
        moment = at(10, 18) + timedelta(minutes=50)
        self.assertEqual(attendance.settle(short, at=moment, policy=rules), "no_show")
        self.assertTrue(attendance.is_no_show(short, at=moment, policy=rules))

    def test_the_check_in_window_honours_the_policys_grace(self):
        """A hard-coded fifteen passed every test the suite had."""
        for grace in (0, 15, 45, 240):
            _, closes = attendance.checkin_window(
                at(10, 18), policy=policy.Policy(checkin_grace_minutes=grace))
            self.assertEqual(closes, at(10, 18) + timedelta(minutes=grace))

    def test_a_grace_period_beyond_four_hours_is_refused(self):
        with self.assertRaises(BookingError):
            policy.check_policy(policy.Policy(checkin_grace_minutes=241))

    def test_a_settled_booking_does_not_move(self):
        for state in ("attended", "no_show", "cancelled", "released"):
            with self.assertRaises(BookingError):
                attendance.check_transition(state, "booked")


class ConsequenceTests(unittest.TestCase):
    def test_a_cancellation_inside_the_window_costs_nothing(self):
        outcome = consequence.decide(
            "cancelled_in_time", no_show_count=5, policy=policy.Policy())
        self.assertFalse(outcome.fee_due)
        self.assertFalse(outcome.credit_forfeit)
        self.assertEqual(outcome.sanction, "none")

    def test_a_session_the_gym_cancelled_costs_nothing_whatever_the_count(self):
        outcome = consequence.decide(
            "session_cancelled", no_show_count=9, policy=policy.Policy())
        self.assertFalse(outcome.fee_due)
        self.assertEqual(outcome.sanction, "none")

    def test_a_late_cancellation_is_not_counted_towards_a_strike(self):
        """The member told the gym; somebody else could have had the place. Counting it would
        sanction a member for being considerate."""
        outcome = consequence.decide(
            "cancelled_late", no_show_count=9, policy=policy.Policy())
        self.assertTrue(outcome.fee_due)
        self.assertEqual(outcome.sanction, "none")

    def test_a_no_show_warns_then_strikes_where_the_policy_says(self):
        rules = policy.Policy(warn_after_no_shows=2, strike_after_no_shows=3)
        self.assertEqual(
            consequence.decide("no_show", no_show_count=1, policy=rules).sanction, "none")
        self.assertEqual(
            consequence.decide("no_show", no_show_count=2, policy=rules).sanction,
            "warning")
        self.assertEqual(
            consequence.decide("no_show", no_show_count=3, policy=rules).sanction,
            "strike")

    def test_a_credit_is_forfeit_only_when_one_was_cited(self):
        rules = policy.Policy()
        self.assertFalse(consequence.decide(
            "no_show", no_show_count=1, policy=rules,
            entitlement_cited=False).credit_forfeit)
        self.assertTrue(consequence.decide(
            "no_show", no_show_count=1, policy=rules,
            entitlement_cited=True).credit_forfeit)

    def test_an_unknown_occasion_is_refused(self):
        with self.assertRaises(BookingError):
            consequence.decide("forgot", no_show_count=1, policy=policy.Policy())

    def test_the_predictive_no_show_score_is_refused_rather_than_faked(self):
        """Paragraph 1884 asks for one and this build computes none.

        Reachable and tested rather than an absence somebody later fills with a stub returning
        0.5 -- MOD-011's refusal to evaluate a percentile against a mean, applied to people.
        """
        with self.assertRaises(BookingError) as caught:
            consequence.predicted_no_show_risk(person_id="p1")
        self.assertIn("no outcome history", str(caught.exception))


class AppealTests(unittest.TestCase):
    def appeal(self, **kw) -> appeals.Appeal:
        fields = {"appeal_id": "a1", "subject_person_id": "p1", "against": "strike",
                  "state": "open", "raised_at": at(10)}
        fields.update(kw)
        return appeals.Appeal(**fields)  # type: ignore[arg-type]

    def test_a_member_does_not_decide_their_own_appeal(self):
        with self.assertRaises(BookingError):
            appeals.check_decider(self.appeal(), decider_person_id="p1")
        appeals.check_decider(self.appeal(), decider_person_id="p2")

    def test_a_decider_with_no_person_record_cannot_decide(self):
        """**The grounds for permitting this were false.** "A staff identity with no person
        record is not the subject by definition" fails for the one human it matters for: the
        coach who is also a member with a strike, whose identity has no `ppl_identity_links`
        row. Nothing creates that link automatically, so both layers of the separation of
        duties failed on the same missing row rather than independently.
        """
        with self.assertRaises(BookingError):
            appeals.check_decider(self.appeal(), decider_person_id=None)

    def test_a_decided_appeal_is_final(self):
        for state in ("upheld", "rejected", "withdrawn"):
            with self.assertRaises(BookingError):
                appeals.check_transition(state, "open")

    def test_a_decided_appeal_names_its_decider(self):
        with self.assertRaises(BookingError):
            appeals.check_appeal(self.appeal(state="upheld"))
        appeals.check_appeal(self.appeal(state="upheld", decided_by="i2"))

    def test_an_open_appeal_has_no_decider(self):
        with self.assertRaises(BookingError):
            appeals.check_appeal(self.appeal(decided_by="i2"))

    def test_an_appeal_is_raised_within_a_month(self):
        self.assertTrue(appeals.within_appeal_window(at(1), at=at(20)))
        self.assertFalse(
            appeals.within_appeal_window(at(1), at=at(1) + timedelta(days=31)))

    def test_only_a_declared_thing_can_be_appealed(self):
        with self.assertRaises(BookingError):
            appeals.check_appeal(self.appeal(against="the weather"))


if __name__ == "__main__":
    unittest.main()


class ReviewRegressionTests(unittest.TestCase):
    """One case per defect three independent reviewers found, named for the attack.

    **The cause of all of them was the same**: 24 of 67 single-clause mutations survived a
    green 41-test suite, so the logic could be deleted or inverted with nothing failing. Each
    case below is written so that the clause it names is the only thing that makes it pass.
    """

    # --------------------------------------------------- the queue a member can predict

    def test_an_expired_offer_keeps_its_place_in_the_queue(self):
        """**A member asleep at six was not sent to the back of the queue -- they were taken
        out of it.** Both expiry paths write `expired`, nothing in the build ever writes
        `waiting` back, and `ordered` treated only `waiting` and `offered` as live. So
        `position_of` answered None, their app showed them as not on the waitlist at all, and
        `next_to_offer` could never reach them again -- while three docstrings and the
        migration header said they kept their place.
        """
        rules = policy.Policy()
        asleep = waitlist.Entry("asleep-at-six", "p1", at(15, 6), state="expired")
        later = waitlist.Entry("joined-later", "p2", at(15, 8))
        entries = [asleep, later]
        self.assertEqual([e.entry_id for e in waitlist.ordered(entries, policy=rules)],
                         ["asleep-at-six", "joined-later"])
        self.assertEqual(waitlist.position_of(entries, "asleep-at-six", policy=rules), 1)
        self.assertEqual(
            [e.entry_id for e in waitlist.next_to_offer(
                entries, policy=rules, at=at(15, 9), places=1)],
            ["asleep-at-six"])

    def test_a_settled_entry_is_out_of_the_queue(self):
        """The other direction: `confirmed`, `declined`, `withdrawn` and `lapsed` are resolved,
        and an ordering that kept them would have withdrawn members occupying positions."""
        rules = policy.Policy()
        live = waitlist.Entry("live", "p1", at(15, 8))
        settled = [waitlist.Entry(state, "p2", at(15, 6), state=state)
                   for state in ("confirmed", "declined", "withdrawn", "lapsed")]
        self.assertEqual(
            [e.entry_id for e in waitlist.ordered([*settled, live], policy=rules)],
            ["live"])

    def test_the_tier_rule_still_orders_by_when_they_joined(self):
        """A tier rule that ignored `joined_at` ordered members of one tier arbitrarily, which
        is the complaint the deterministic ordering exists to prevent."""
        rules = policy.Policy(priority_rule="membership_tier")
        first = waitlist.Entry("first", "p1", at(15, 6), tier=1)
        second = waitlist.Entry("second", "p2", at(15, 8), tier=1)
        self.assertEqual(
            [e.entry_id for e in waitlist.ordered([second, first], policy=rules)],
            ["first", "second"])

    def test_an_offer_with_neither_a_time_nor_an_expiry_is_refused(self):
        """**The isolating row.** The suite's case built an `offered` entry with a time and no
        expiry, which two checks refuse -- so either could be deleted and the test still
        passed. An offer that never expires is the row only the first one refuses.
        """
        with self.assertRaises(BookingError):
            waitlist.check_entry(waitlist.Entry(
                "e", "p", at(15, 6), state="offered"))

    def test_an_offer_expires_exactly_when_it_says(self):
        rules = policy.Policy(offer_minutes=60)
        expiry = waitlist.offer_expiry(at=at(15, 6), policy=rules)
        self.assertEqual(expiry, at(15, 7))
        entry = waitlist.Entry("e", "p", at(15, 5), state="offered",
                               offered_at=at(15, 6), offer_expires_at=expiry)
        self.assertFalse(waitlist.offer_has_expired(entry, at=expiry - timedelta(
            seconds=1)))
        self.assertTrue(waitlist.offer_has_expired(entry, at=expiry))

    def test_an_offer_window_honours_the_policy(self):
        """A hard-coded sixty passed every test the suite had."""
        for minutes in (1, 30, 1440):
            self.assertEqual(
                waitlist.offer_expiry(at=at(15, 6),
                                      policy=policy.Policy(offer_minutes=minutes)),
                at(15, 6) + timedelta(minutes=minutes))

    def test_an_offer_window_outside_a_minute_to_a_day_is_refused(self):
        for minutes in (0, 1441):
            with self.assertRaises(BookingError):
                policy.check_policy(policy.Policy(offer_minutes=minutes))

    def test_a_negative_tier_is_refused(self):
        with self.assertRaises(BookingError):
            waitlist.check_entry(waitlist.Entry("e", "p", at(15, 6), tier=-1))

    # --------------------------------------------------- the denial a member is given

    def test_a_denial_is_stable_in_both_of_its_clauses(self):
        """Paragraph 5032's Critical Control, and the suite's only unequal pair differed in
        *both* fields -- so each single-clause mutation kept it green. These two pairs differ
        in one field each.
        """
        full = denial.Denial(reason="full", detail="x", offer_waitlist=True)
        self.assertTrue(denial.is_stable(full, denial.Denial(
            reason="full", detail="different prose", offer_waitlist=True)))
        # Same reason, different offer.
        self.assertFalse(denial.is_stable(full, denial.Denial(
            reason="full", detail="x", offer_waitlist=False)))
        # Same offer, different reason.
        self.assertFalse(denial.is_stable(full, denial.Denial(
            reason="waitlist_full", detail="x", offer_waitlist=True)))

    # --------------------------------------------------- what a no-show costs

    def test_a_no_show_carries_the_fee_its_policy_declares(self):
        """`fee_due=True` was unconditional and no test asserted it, so the fee decision was
        deletable."""
        outcome = consequence.decide(
            "no_show", no_show_count=1, policy=policy.Policy())
        self.assertTrue(outcome.fee_due)

    def test_a_free_occasion_cannot_be_made_to_cost_anything(self):
        """`entitlement_cited` is about a *forfeit*, and a cancellation in time or a session
        the gym cancelled costs nothing whatever it says."""
        for occasion in ("cancelled_in_time", "session_cancelled"):
            outcome = consequence.decide(
                occasion, no_show_count=3, policy=policy.Policy(),
                entitlement_cited=True)
            self.assertFalse(outcome.fee_due, occasion)
            self.assertFalse(outcome.credit_forfeit, occasion)
            self.assertEqual(outcome.sanction, "none", occasion)

    def test_a_negative_no_show_count_is_refused(self):
        with self.assertRaises(BookingError):
            consequence.decide("no_show", no_show_count=-1, policy=policy.Policy())

    def test_a_cancellation_is_late_from_the_hour_the_policy_names(self):
        """The boundary in both directions: `>` against `>=` survived the suite."""
        rules = policy.Policy(cancellation_hours=12)
        start = at(16, 18)
        self.assertFalse(policy.cancellation_is_late(
            start, at=start - timedelta(hours=12), policy=rules))
        self.assertTrue(policy.cancellation_is_late(
            start, at=start - timedelta(hours=12) + timedelta(seconds=1), policy=rules))

    def test_an_appeal_window_includes_its_last_day(self):
        recorded = at(1)
        self.assertTrue(appeals.within_appeal_window(
            recorded, at=recorded + timedelta(days=appeals.APPEAL_WINDOW_DAYS)))
        self.assertFalse(appeals.within_appeal_window(
            recorded,
            at=recorded + timedelta(days=appeals.APPEAL_WINDOW_DAYS, seconds=1)))

    # --------------------------------------------------- what an appeal is against

    def test_an_appeal_must_be_against_something_the_record_carries(self):
        """**A strike that does not exist was appealed and upheld.** `against` was stored
        beside the decision and never read, which MOD-019's rule calls a comment rather than a
        parameter.
        """
        with self.assertRaises(BookingError):
            appeals.check_against("strike", fee_due=True, credit_forfeit=False,
                                  sanction="none")
        with self.assertRaises(BookingError):
            appeals.check_against("warning", fee_due=True, credit_forfeit=False,
                                  sanction="strike")
        with self.assertRaises(BookingError):
            appeals.check_against("fee", fee_due=False, credit_forfeit=False,
                                  sanction="strike")
        with self.assertRaises(BookingError):
            appeals.check_against("credit_forfeit", fee_due=True, credit_forfeit=False,
                                  sanction="strike")
        # And a cancellation, which has no sanction at all.
        with self.assertRaises(BookingError):
            appeals.check_against("strike", fee_due=True, credit_forfeit=False,
                                  sanction=None)
        appeals.check_against("fee", fee_due=True, credit_forfeit=False, sanction=None)
        appeals.check_against("strike", fee_due=True, credit_forfeit=False,
                              sanction="strike")

    def test_a_money_appeal_and_a_sanction_appeal_are_different_remedies(self):
        """Upholding a fee appeal wiped the member's no-show out of the sanction count, so a
        decision about money silently reset the strike policy. The two sets are what the
        service routes on."""
        self.assertEqual(set(appeals.SANCTION_APPEALS) | set(appeals.MONEY_APPEALS),
                         set(appeals.APPEALABLE))
        self.assertFalse(set(appeals.SANCTION_APPEALS) & set(appeals.MONEY_APPEALS))

    def test_an_unknown_appeal_subject_is_refused(self):
        with self.assertRaises(BookingError):
            appeals.check_against("suspension", fee_due=True, credit_forfeit=True,
                                  sanction="strike")

    # --------------------------------------------------- the policy's own bounds

    def test_every_policy_bound_bites(self):
        """Four of these were unproven, so the bound could be removed with the suite green."""
        for kw in ({"max_concurrent": 0}, {"max_concurrent": 101},
                   {"quota": 10_001}, {"checkin_grace_minutes": -1},
                   {"cancellation_hours": -1}, {"warn_after_no_shows": 0},
                   {"strike_after_no_shows": 0}, {"quota_period": "fortnight"},
                   {"priority_rule": "whoever_asks"}):
            with self.assertRaises(BookingError, msg=kw):
                policy.check_policy(policy.Policy(**kw))  # type: ignore[arg-type]
        policy.check_policy(policy.Policy(max_concurrent=100, quota=10_000,
                                          checkin_grace_minutes=240,
                                          cancellation_hours=168))

    def test_the_predicted_no_show_score_refuses_rather_than_guessing(self):
        """Paragraph 1884 asks for a score and this build computes none. Annotated `NoReturn`
        now, because `-> float` told a caller that type-checks against the signature that a
        number comes back."""
        with self.assertRaises(BookingError):
            consequence.predicted_no_show_risk(no_show_count=5, bookings=10)
