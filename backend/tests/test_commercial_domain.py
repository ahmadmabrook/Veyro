"""MOD-017's decisions, with no database.

The four modules under `app/commercial/` do no I/O, so these tests are the cheapest place to
pin the arithmetic that an invoice, a notice period and an access decision rest on. What is
here is deliberately the arithmetic and the state machines; the service's locks and atomicity
are HTTP tests, because those are properties of a transaction and not of a function.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from app.commercial import collections, entitlements, invoicing, lifecycle, reporting

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class TransitionTests(unittest.TestCase):
    def test_the_machine_is_data_and_an_unknown_act_refuses(self):
        """A change kind this build does not evaluate is an act somebody wrote; admitting it
        would move a membership by a rule nobody checked."""
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_transition("teleport", "active", "frozen")

    def test_an_edge_the_machine_does_not_have_refuses(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_transition("freeze", "cancelled", "frozen")
        lifecycle.check_transition("freeze", "active", "frozen")

    def test_a_cancelled_membership_is_not_reinstated(self):
        """COM-01-R04 asks for reinstatement and this is the honest reading of which state it
        reinstates from: a cancelled or expired membership is re-sold, because the terms, the
        price and the contract version all have to be re-agreed."""
        lifecycle.check_transition("reinstatement", "suspended", "active")
        for dead in ("cancelled", "expired", "transferred"):
            with self.assertRaises(lifecycle.LifecycleError, msg=dead):
                lifecycle.check_transition("reinstatement", dead, "active")

    def test_a_renewal_does_not_move_the_status(self):
        """The one act whose from and to are the same, which is why the schema's
        `moves` constraint admits it."""
        lifecycle.check_transition("renewal", "active", "active")


class AsOfTests(unittest.TestCase):
    def changes(self):
        return [
            lifecycle.Change("activation", "pending", "active", date(2026, 1, 10)),
            lifecycle.Change("freeze", "active", "frozen", date(2026, 3, 1)),
            lifecycle.Change("resume", "frozen", "active", date(2026, 4, 1)),
            lifecycle.Change("cancellation", "active", "cancelled", date(2026, 7, 1)),
        ]

    def test_a_change_effective_later_does_not_apply_yet(self):
        """**The fact a dispute turns on.** A cancellation decided in January and effective in
        March leaves the membership active in February."""
        self.assertEqual(
            lifecycle.status_as_of("pending", self.changes(), date(2026, 6, 1)), "active")
        self.assertEqual(
            lifecycle.status_as_of("pending", self.changes(), date(2026, 7, 1)), "cancelled")

    def test_the_replay_answers_each_point_in_the_history(self):
        for moment, expected in (
            (date(2026, 1, 1), "pending"),
            (date(2026, 1, 10), "active"),
            (date(2026, 3, 15), "frozen"),
            (date(2026, 4, 1), "active"),
            (date(2026, 12, 31), "cancelled"),
        ):
            self.assertEqual(
                lifecycle.status_as_of("pending", self.changes(), moment), expected,
                moment.isoformat())

    def test_the_order_is_total_so_the_answer_is_the_same_every_run(self):
        """Two changes effective on the same day must give the same answer on every machine; a
        replay whose result depended on row order would be wrong only sometimes."""
        same_day = [
            lifecycle.Change("activation", "pending", "active", date(2026, 1, 1)),
            lifecycle.Change("freeze", "active", "frozen", date(2026, 1, 1)),
        ]
        first = lifecycle.status_as_of("pending", same_day, date(2026, 2, 1))
        second = lifecycle.status_as_of("pending", list(reversed(same_day)), date(2026, 2, 1))
        self.assertEqual(first, second)


class NoticeAndTermTests(unittest.TestCase):
    def test_the_minimum_term_wins_over_the_notice(self):
        """**What a minimum term is.** A member inside their commitment cannot cancel out of it
        by giving notice: the notice runs and the effective date is whichever is later."""
        terms = lifecycle.Terms(notice_days=30, cancellation_mode="end_of_notice")
        effective, steps = lifecycle.cancellation_effective_on(
            decided_on=date(2026, 1, 1), terms=terms, period_end=None,
            minimum_term_ends_on=date(2026, 9, 30))
        self.assertEqual(effective, date(2026, 9, 30))
        self.assertTrue(any("later" in step for step in steps))

    def test_immediate_notice_and_end_of_term_differ(self):
        decided = date(2026, 1, 15)
        period_end = date(2026, 1, 31)
        for mode, expected in (
            ("immediate", date(2026, 1, 15)),
            ("end_of_notice", date(2026, 1, 22)),
            ("end_of_term", date(2026, 1, 31)),
        ):
            effective, _ = lifecycle.cancellation_effective_on(
                decided_on=decided,
                terms=lifecycle.Terms(notice_days=7, cancellation_mode=mode),
                period_end=period_end, minimum_term_ends_on=None)
            self.assertEqual(effective, expected, mode)

    def test_an_unknown_cancellation_mode_refuses(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.cancellation_effective_on(
                decided_on=date(2026, 1, 1),
                terms=lifecycle.Terms(cancellation_mode="whenever"),
                period_end=None, minimum_term_ends_on=None)

    def test_the_month_arithmetic_clamps_into_the_target_month(self):
        """A membership starting on the 31st of January and running one month ends on the
        28th of February, not on a date that does not exist."""
        self.assertEqual(
            lifecycle.minimum_term_end(
                date(2026, 1, 31), lifecycle.Terms(minimum_term_months=1)),
            date(2026, 2, 28))
        self.assertEqual(
            lifecycle.minimum_term_end(
                date(2026, 1, 15), lifecycle.Terms(minimum_term_months=12)),
            date(2027, 1, 15))
        self.assertIsNone(
            lifecycle.minimum_term_end(date(2026, 1, 1), lifecycle.Terms()))


class EarlyTerminationTests(unittest.TestCase):
    """COM-01-R02's cancellation policy, in the form ADM-MSH-07 discloses it.

    **The canvas and the implementation disagreed about a money figure and nothing noticed**,
    because the fee had no reader anywhere in the product: "his 12-month commitment runs to
    March. Cancelling now triggers a two-month fee of JOD 80.00, and his access ends on
    7 September after the notice period" is a commitment bought out, and
    `cancellation_effective_on` pushed the date to March and charged nothing. These tests are
    the canvas's own case and the three states around it.
    """

    #: Tareq Odeh's contract, from ADM-MSH-07: Flex at 40.00 a month, a twelve-month
    #: commitment to March, thirty days' notice, and a two-month buy-out.
    BOUGHT_OUT = lifecycle.Terms(
        minimum_term_months=12, notice_days=30, cancellation_mode="end_of_notice",
        early_termination_months=2)
    HELD = lifecycle.Terms(
        minimum_term_months=12, notice_days=30, cancellation_mode="end_of_notice")

    def test_the_canvas_case_end_to_end(self):
        """8 August, access ends 7 September, and the buy-out is two months of 40.00."""
        effective, steps = lifecycle.cancellation_effective_on(
            decided_on=date(2026, 8, 8), terms=self.BOUGHT_OUT,
            period_end=date(2026, 8, 31), minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(effective, date(2026, 9, 7))
        self.assertTrue(any("bought out at 2 months" in step for step in steps))
        fee, parts, _ = lifecycle.cancellation_fee(
            effective_on=effective, terms=self.BOUGHT_OUT, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(parts["early_termination_minor"], 8000)
        self.assertEqual(fee, parts["period_minor"] + parts["early_termination_minor"])

    def test_a_contract_with_no_buy_out_still_holds_them_to_the_term(self):
        """**The behaviour every contract in this build had, unchanged.** `None` is not zero:
        the term wins, the date moves to it, and no buy-out arises."""
        effective, _ = lifecycle.cancellation_effective_on(
            decided_on=date(2026, 8, 8), terms=self.HELD,
            period_end=date(2026, 8, 31), minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(effective, date(2027, 3, 1))
        _, parts, steps = lifecycle.cancellation_fee(
            effective_on=effective, terms=self.HELD, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(parts["early_termination_minor"], 0)
        self.assertTrue(any("no buy-out" in step for step in steps))

    def test_a_free_early_exit_is_not_the_same_as_no_early_exit(self):
        """**Zero is a term and not an absence**, which is why the field is nullable. A
        contract that lets somebody walk away free moves the date to the notice and charges
        nothing; one with no buy-out at all moves the date to the term. Reading the first as
        the second would hold a member to a commitment their contract released them from."""
        free = lifecycle.Terms(
            minimum_term_months=12, notice_days=30, cancellation_mode="end_of_notice",
            early_termination_months=0)
        effective, _ = lifecycle.cancellation_effective_on(
            decided_on=date(2026, 8, 8), terms=free, period_end=date(2026, 8, 31),
            minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(effective, date(2026, 9, 7))
        _, parts, _ = lifecycle.cancellation_fee(
            effective_on=effective, terms=free, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(parts["early_termination_minor"], 0)

    def test_nothing_is_bought_out_once_the_term_has_been_served(self):
        """A member whose commitment has run out is not leaving it early, so the buy-out is
        not charged however the contract prices one."""
        for ends_on in (None, date(2026, 1, 1), date(2026, 9, 7)):
            _, parts, _ = lifecycle.cancellation_fee(
                effective_on=date(2026, 9, 7), terms=self.BOUGHT_OUT, amount_minor=4000,
                period_start=None, period_end=None, minimum_term_ends_on=ends_on)
            self.assertEqual(parts["early_termination_minor"], 0, ends_on)

    def test_the_buy_out_is_charged_on_the_last_day_before_the_term_ends(self):
        """**The boundary, from both sides.** `effective_on >= minimum_term_ends_on` is not
        leaving early, and one day earlier is -- a comparison written the other way round
        charges a member who served their whole term, or releases one who left a day short."""
        _, served, _ = lifecycle.cancellation_fee(
            effective_on=date(2027, 3, 1), terms=self.BOUGHT_OUT, amount_minor=4000,
            period_start=None, period_end=None, minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(served["early_termination_minor"], 0)
        _, early, _ = lifecycle.cancellation_fee(
            effective_on=date(2027, 2, 28), terms=self.BOUGHT_OUT, amount_minor=4000,
            period_start=None, period_end=None, minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(early["early_termination_minor"], 8000)

    def test_a_membership_with_no_period_has_no_period_part(self):
        """The two parts are independent: a membership that has never been billed owes
        nothing for a period and may still owe a buy-out."""
        fee, parts, steps = lifecycle.cancellation_fee(
            effective_on=date(2026, 9, 7), terms=self.BOUGHT_OUT, amount_minor=4000,
            period_start=None, period_end=None, minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(parts["period_minor"], 0)
        self.assertEqual(fee, 8000)
        self.assertTrue(any("no billing period" in step for step in steps))

    def test_the_period_part_is_what_was_used_and_not_what_is_left(self):
        """**The direction, which nothing asserted until a mutation flipped it.**

        `prorated_amount` returns the part of the period *on or after* the effective date, so
        the part the member has used is the amount minus that. Returning the remainder
        instead reads as a plausible fee and is the opposite one: a member cancelling on the
        16th of a 31-day month would be charged for the fifteen days they have not had
        rather than the sixteen they have. The sweep caught it uncaught, because every other
        case here asserts the total or the buy-out and the total is the same either way when
        the whole period has been consumed.
        """
        # Access ends after the period ends, so the whole of it has been used.
        _, whole, _ = lifecycle.cancellation_fee(
            effective_on=date(2026, 9, 7), terms=self.BOUGHT_OUT, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(whole["period_minor"], 4000)

        # Mid-period: sixteen of the thirty-one days fall on or after the 16th, so 4000
        # prorates to 2065 and the part used is the other 1935.
        _, part, _ = lifecycle.cancellation_fee(
            effective_on=date(2026, 8, 16), terms=self.HELD, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=None)
        self.assertEqual(part["period_minor"], 1935)

        # And a cancellation effective before the period starts has used none of it.
        _, none_used, _ = lifecycle.cancellation_fee(
            effective_on=date(2026, 8, 1), terms=self.HELD, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=None)
        self.assertEqual(none_used["period_minor"], 0)

    def test_a_negative_amount_or_a_negative_buy_out_refuses(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.cancellation_fee(
                effective_on=date(2026, 9, 7), terms=self.BOUGHT_OUT, amount_minor=-1,
                period_start=None, period_end=None, minimum_term_ends_on=None)
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.cancellation_fee(
                effective_on=date(2026, 9, 7),
                terms=lifecycle.Terms(early_termination_months=-2), amount_minor=4000,
                period_start=None, period_end=None,
                minimum_term_ends_on=date(2027, 3, 1))
        # **And on the path that would not have charged it either way**, which the branch-
        # local version of the guard let through as a zero: the term is served, so nothing is
        # bought out, and a contract carrying a negative buy-out is still a contract nobody
        # should be able to write.
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.cancellation_fee(
                effective_on=date(2027, 6, 1),
                terms=lifecycle.Terms(early_termination_months=-2), amount_minor=4000,
                period_start=None, period_end=None,
                minimum_term_ends_on=date(2027, 3, 1))

    def test_the_total_is_the_parts(self):
        """**The screen renders the total and never adds the parts itself**, so the invariant
        that makes that safe is asserted here rather than assumed there."""
        fee, parts, steps = lifecycle.cancellation_fee(
            effective_on=date(2026, 9, 7), terms=self.BOUGHT_OUT, amount_minor=4000,
            period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            minimum_term_ends_on=date(2027, 3, 1))
        self.assertEqual(fee, sum(parts.values()))
        self.assertIn(f"fee_due_minor: {fee}", steps)


class FreezeAllowanceTests(unittest.TestCase):
    def test_only_the_overlap_with_the_contract_year_counts(self):
        """A freeze that began in December and ran into February spends part of each contract
        year's allowance; attributing the whole of it to either is how a member loses days they
        never used or gets a second allowance by timing."""
        windows = [lifecycle.FreezeWindow(date(2025, 12, 20), date(2026, 2, 10))]
        used = lifecycle.freeze_days_used(windows, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(used, 41)

    def test_an_open_ended_freeze_is_counted_to_the_year_end(self):
        """The conservative direction: it is spending the allowance right now, and treating it
        as free until it closes would let a membership be held frozen indefinitely inside a
        thirty-day allowance."""
        windows = [lifecycle.FreezeWindow(date(2026, 12, 1), None)]
        used = lifecycle.freeze_days_used(windows, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(used, 31)

    def test_a_hold_that_does_not_count_is_not_counted(self):
        windows = [
            lifecycle.FreezeWindow(date(2026, 3, 1), date(2026, 3, 10)),
            lifecycle.FreezeWindow(date(2026, 4, 1), date(2026, 4, 30),
                                   counts_against_allowance=False),
        ]
        self.assertEqual(
            lifecycle.freeze_days_used(windows, date(2026, 1, 1), date(2026, 12, 31)), 10)

    def test_a_medical_hold_does_not_spend_the_allowance(self):
        self.assertTrue(lifecycle.counts_against_allowance("freeze"))
        self.assertTrue(lifecycle.counts_against_allowance("pause"))
        self.assertFalse(lifecycle.counts_against_allowance("medical_hold"))
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.counts_against_allowance("sabbatical")

    def test_a_freeze_past_the_allowance_refuses(self):
        terms = lifecycle.Terms(freeze_days_per_year=30)
        lifecycle.check_freeze(requested_days=10, terms=terms, already_used=20)
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_freeze(requested_days=11, terms=terms, already_used=20)

    def test_a_contract_allowing_no_freezing_refuses_any(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_freeze(
                requested_days=1, terms=lifecycle.Terms(), already_used=0)


class ProrationTests(unittest.TestCase):
    def test_a_period_is_inclusive_of_both_ends(self):
        """A one-day period is one day and not zero."""
        amount, _ = lifecycle.prorated_amount(
            full_amount_minor=100, period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 1), effective_on=date(2026, 1, 1))
        self.assertEqual(amount, 100)

    def test_the_part_on_or_after_the_effective_date_is_what_is_owed(self):
        amount, steps = lifecycle.prorated_amount(
            full_amount_minor=3100, period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31), effective_on=date(2026, 1, 21))
        self.assertEqual(amount, 1100)
        self.assertTrue(any("11 days" in step for step in steps))

    def test_outside_the_period_is_all_or_nothing(self):
        for effective, expected in (
            (date(2025, 12, 1), 3100),
            (date(2026, 2, 1), 0),
        ):
            amount, _ = lifecycle.prorated_amount(
                full_amount_minor=3100, period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31), effective_on=effective)
            self.assertEqual(amount, expected, effective.isoformat())

    def test_a_backwards_period_refuses(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.prorated_amount(
                full_amount_minor=100, period_start=date(2026, 2, 1),
                period_end=date(2026, 1, 1), effective_on=date(2026, 1, 15))

    def test_periods_tile_without_a_gap_or_an_overlap(self):
        """A day in both periods is a day a member is billed twice for; a day in neither is one
        they trained for free."""
        start, end = lifecycle.renewal_period(
            current_end=date(2026, 1, 31), billing_period="monthly")
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))
        following, _ = lifecycle.renewal_period(
            current_end=end, billing_period="monthly")
        self.assertEqual(following, date(2026, 3, 1))

    def test_an_unrenewable_period_refuses(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.renewal_period(
                current_end=date(2026, 1, 31), billing_period="one_off")


class EntitlementSignTests(unittest.TestCase):
    def test_every_kind_has_a_declared_sign_and_an_unknown_one_refuses(self):
        self.assertEqual(len(entitlements.SIGNS), 9)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("teleport", 1)

    def test_a_grant_adds_and_a_reserve_takes(self):
        entitlements.check_sign("grant", 10)
        entitlements.check_sign("reserve", -1)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("grant", -10)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("reserve", 1)

    def test_a_consumption_moves_nothing(self):
        """The quantity left the balance when it was held; taking it again is the double-count
        the schema's `consume_is_neutral` constraint exists to refuse."""
        entitlements.check_sign("consume", 0)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("consume", -1)

    def test_a_lapsed_hold_adds_and_a_lapsed_grant_takes(self):
        """**Two kinds, not one.** A single `expire` would be two opposite movements under one
        name: a lapsed hold gives the quantity back and a lapsed grant takes the balance away.
        One kind meant one sign constraint, and whichever sign it enforced was wrong for half
        the rows -- a member either losing credit when a booking flow was abandoned, or keeping
        it after the grant expired. Found while writing the constraints."""
        entitlements.check_sign("reservation_expired", 1)
        entitlements.check_sign("grant_expired", -5)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("reservation_expired", -1)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("grant_expired", 5)

    def test_an_adjustment_may_go_either_way_but_not_nowhere(self):
        entitlements.check_sign("adjustment", 3)
        entitlements.check_sign("adjustment", -3)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.check_sign("adjustment", 0)


class BalanceTests(unittest.TestCase):
    def ledger(self):
        return [
            entitlements.Movement("grant", 10),
            entitlements.Movement("reserve", -2),
            entitlements.Movement("consume", 0),
            entitlements.Movement("reserve", -1),
            entitlements.Movement("release", 1),
        ]

    def test_the_balance_is_the_sum_of_the_movements(self):
        self.assertEqual(entitlements.balance_of(self.ledger()), 8)

    def test_the_sum_cannot_be_got_wrong_by_processing_rows_out_of_order(self):
        """Which is itself a reason to keep the balance as a sum rather than as a replay."""
        rows = self.ledger()
        self.assertEqual(
            entitlements.balance_of(rows),
            entitlements.balance_of(list(reversed(rows))))

    def test_what_is_held_comes_from_the_reservations_not_the_ledger(self):
        """**The first version walked the movements and got it wrong.** A `consume` carries a
        delta of zero by design -- the quantity left the balance when it was held -- so there
        is nothing in the ledger to say the *hold* ended, and a consumed reservation was
        counted as held for ever. A member who had used all ten classes was told all ten were
        still reserved for bookings they had already attended. The reservation row is the
        authority on whether a hold is live. Found by this module's own tests."""
        self.assertEqual(entitlements.held_quantity([2, 1]), 3)
        self.assertEqual(entitlements.held_quantity([]), 0)

    def test_a_live_hold_of_nothing_refuses(self):
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.held_quantity([1, 0])

    def test_a_lapsed_hold_returns_to_the_balance(self):
        rows = [
            entitlements.Movement("grant", 5),
            entitlements.Movement("reserve", -2),
            entitlements.Movement("reservation_expired", 2),
        ]
        self.assertEqual(entitlements.balance_of(rows), 5)


class UsableTests(unittest.TestCase):
    def grant(self, **kwargs):
        body = {
            "grant_id": "g1", "is_counted": True, "granted_quantity": 10,
            "valid_from": datetime(2026, 1, 1, tzinfo=UTC),
        }
        body.update(kwargs)
        return entitlements.Grant(**body)  # type: ignore[arg-type]

    def test_a_usable_grant_is_usable(self):
        verdict = entitlements.usable(self.grant(), at=NOW, balance=5)
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.code, entitlements.USABLE)

    def test_each_refusal_carries_its_own_code(self):
        cases = [
            (self.grant(status="revoked"), {}, entitlements.NOT_ACTIVE),
            (self.grant(valid_from=datetime(2027, 1, 1, tzinfo=UTC)), {},
             entitlements.NOT_YET_VALID),
            (self.grant(valid_to=datetime(2026, 1, 2, tzinfo=UTC)), {},
             entitlements.EXPIRED),
            (self.grant(location_id="elsewhere"), {"location_id": "here"},
             entitlements.WRONG_LOCATION),
            (self.grant(), {"balance": 0}, entitlements.INSUFFICIENT),
        ]
        for grant, extra, code in cases:
            body = {"balance": 5}
            body.update(extra)
            verdict = entitlements.usable(grant, at=NOW, **body)  # type: ignore[arg-type]
            self.assertEqual(verdict.code, code, code)
            self.assertFalse(verdict.ok)
            self.assertTrue(verdict.reason)

    def test_a_set_scope_must_match_and_an_unset_one_matches_anything(self):
        """The same asymmetry as MOD-016's price-book specificity: scoring the wide match would
        make a grant that specifies nothing narrower than one that specifies a location."""
        wide = self.grant()
        self.assertTrue(
            entitlements.usable(wide, at=NOW, balance=5, location_id="anywhere").ok)
        narrow = self.grant(location_id="here")
        self.assertTrue(
            entitlements.usable(narrow, at=NOW, balance=5, location_id="here").ok)
        self.assertFalse(
            entitlements.usable(narrow, at=NOW, balance=5, location_id="there").ok)

    def test_a_time_restricted_grant_with_no_local_time_refuses(self):
        """**MOD-016's `max_per_subject` finding in this module's clothes.** Treating a missing
        local time as "any time" would turn an off-peak membership into an unlimited one by
        omitting a field."""
        off_peak = self.grant(usable_from_minute=540, usable_to_minute=1020)
        refused = entitlements.usable(off_peak, at=NOW, balance=5)
        self.assertEqual(refused.code, entitlements.OUTSIDE_HOURS)
        self.assertIn("no local time", refused.reason)
        self.assertTrue(
            entitlements.usable(off_peak, at=NOW, balance=5, local_minute=600).ok)
        self.assertFalse(
            entitlements.usable(off_peak, at=NOW, balance=5, local_minute=1100).ok)

    def test_the_window_is_half_open_so_the_closing_minute_is_out(self):
        off_peak = self.grant(usable_from_minute=540, usable_to_minute=1020)
        self.assertTrue(
            entitlements.usable(off_peak, at=NOW, balance=5, local_minute=1019).ok)
        self.assertFalse(
            entitlements.usable(off_peak, at=NOW, balance=5, local_minute=1020).ok)

    def test_an_unlimited_grant_needs_no_balance_and_a_counted_one_does(self):
        unlimited = self.grant(is_counted=False, granted_quantity=None)
        self.assertTrue(entitlements.usable(unlimited, at=NOW).ok)
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.usable(self.grant(), at=NOW)

    def test_a_reservation_ttl_is_bounded(self):
        self.assertEqual(
            entitlements.reservation_expiry(held_at=NOW, ttl_seconds=900).isoformat(),
            "2026-06-01T12:15:00+00:00")
        for bad in (29, 86401):
            with self.assertRaises(entitlements.EntitlementError):
                entitlements.reservation_expiry(held_at=NOW, ttl_seconds=bad)


class CarryoverTests(unittest.TestCase):
    def test_nothing_carries_by_default(self):
        """Carryover is a cost the tenant is choosing to bear, and a default that carried
        everything forward would make every class pack unlimited by accident."""
        self.assertEqual(
            entitlements.carryover_quantity(
                unused=7, carryover_mode="none", carryover_limit=None), 0)

    def test_a_cap_caps_and_unlimited_does_not(self):
        self.assertEqual(
            entitlements.carryover_quantity(
                unused=7, carryover_mode="capped", carryover_limit=3), 3)
        self.assertEqual(
            entitlements.carryover_quantity(
                unused=2, carryover_mode="capped", carryover_limit=3), 2)
        self.assertEqual(
            entitlements.carryover_quantity(
                unused=7, carryover_mode="unlimited", carryover_limit=None), 7)

    def test_a_capped_mode_without_a_cap_refuses(self):
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.carryover_quantity(
                unused=7, carryover_mode="capped", carryover_limit=None)

    def test_an_unknown_mode_refuses(self):
        with self.assertRaises(entitlements.EntitlementError):
            entitlements.carryover_quantity(
                unused=7, carryover_mode="forever", carryover_limit=None)


class InvoiceArithmeticTests(unittest.TestCase):
    def line(self, **kwargs):
        body = {"description": "Membership", "quantity": 1, "unit_net_minor": 4500,
                "tax_rate_bp": 1600}
        body.update(kwargs)
        return invoicing.LineInput(**body)  # type: ignore[arg-type]

    def test_the_line_and_the_invoice_both_add_up(self):
        totals = invoicing.compute_totals([self.line()])
        self.assertEqual(totals.net_minor, 4500)
        self.assertEqual(totals.tax_minor, 720)
        self.assertEqual(totals.gross_minor, 5220)
        self.assertEqual(totals.lines[0].gross_minor, 5220)

    def test_tax_is_computed_per_line_and_summed_not_computed_on_the_total(self):
        """**They differ.** Three lines of 3 minor units at 16% are 0 each by half-away-from-
        zero rounding, so the invoice's tax is 0 -- while 16% of the 9-unit total is 1. The
        figure a tax authority reads is the sum of the lines, so computing it on the total
        would produce an invoice whose own lines do not add up to the total printed on it."""
        totals = invoicing.compute_totals([
            self.line(unit_net_minor=3, tax_rate_bp=1600) for _ in range(3)])
        self.assertEqual(totals.net_minor, 9)
        self.assertEqual(sum(line.tax_minor for line in totals.lines), totals.tax_minor)
        self.assertEqual(totals.tax_minor, 0)
        self.assertEqual(totals.gross_minor, 9)

    def test_tax_is_grouped_by_rate_for_the_return(self):
        """One figure per rate, which is the shape a return wants -- not one per line."""
        totals = invoicing.compute_totals([
            self.line(unit_net_minor=1000, tax_rate_bp=1600),
            self.line(unit_net_minor=2000, tax_rate_bp=1600),
            self.line(unit_net_minor=500, tax_rate_bp=0),
        ])
        self.assertEqual(totals.tax_by_rate, ((0, 500, 0), (1600, 3000, 480)))

    def test_quantity_multiplies_the_net_before_the_tax(self):
        totals = invoicing.compute_totals([self.line(quantity=3, unit_net_minor=1000)])
        self.assertEqual(totals.net_minor, 3000)
        self.assertEqual(totals.tax_minor, 480)

    def test_an_invoice_with_no_lines_refuses(self):
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.compute_totals([])

    def test_a_blank_description_refuses(self):
        """It is what the member reads on the invoice."""
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.compute_totals([self.line(description="   ")])

    def test_an_absurd_figure_refuses_rather_than_overflowing(self):
        """MOD-011 and MOD-012 each shipped an unbounded integer that reached psycopg as a
        `DataError` the handlers do not catch -- a 500 instead of a 422."""
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.compute_totals([self.line(unit_net_minor=10**13)])
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.compute_totals([
                self.line(quantity=1_000_000, unit_net_minor=10**9)])

    def test_a_rate_outside_the_range_refuses(self):
        for bad in (-1, 10_001):
            with self.assertRaises(invoicing.InvoicingError):
                invoicing.compute_totals([self.line(tax_rate_bp=bad)])


class DocumentNumberTests(unittest.TestCase):
    def test_the_number_sorts_lexically_as_it_sorts_numerically(self):
        """A property somebody will rely on in a spreadsheet whether or not it was promised."""
        numbers = [invoicing.document_number("INV", n) for n in (1, 2, 10, 100)]
        self.assertEqual(numbers, ["INV-000001", "INV-000002", "INV-000010", "INV-000100"])
        self.assertEqual(numbers, sorted(numbers))

    def test_a_serial_starts_at_one_and_is_bounded(self):
        for bad in (0, -1, 10**10):
            with self.assertRaises(invoicing.InvoicingError):
                invoicing.document_number("INV", bad)

    def test_a_blank_series_code_refuses(self):
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.document_number("  ", 1)


class StateMachineTests(unittest.TestCase):
    def test_the_two_machines_are_separate_and_neither_implies_the_other(self):
        """Paragraph 1607. An invoice can be paid and not fiscalized, or fiscalized and
        unpaid, and a single status column would have made one of those unrepresentable."""
        invoicing.check_payment_transition("unpaid", "paid")
        invoicing.check_fiscal_transition("pending", "submitted")
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.check_payment_transition("unpaid", "submitted")
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.check_fiscal_transition("pending", "paid")

    def test_a_written_off_debt_does_not_reopen(self):
        """It would make the write-off a suggestion."""
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.check_payment_transition("written_off", "paid")

    def test_a_rejection_goes_back_to_submitted(self):
        """The ordinary response to a rejection is to correct and resubmit."""
        invoicing.check_fiscal_transition("submitted", "rejected")
        invoicing.check_fiscal_transition("rejected", "submitted")

    def test_fiscal_completion_follows_acknowledgement_and_nothing_else(self):
        invoicing.check_fiscal_transition("acknowledged", "fiscal_complete")
        for other in ("pending", "submitted", "rejected"):
            with self.assertRaises(invoicing.InvoicingError, msg=other):
                invoicing.check_fiscal_transition(other, "fiscal_complete")

    def test_a_late_payer_is_not_permanently_overdue(self):
        invoicing.check_payment_transition("overdue", "paid")

    def test_the_payment_status_is_derived_from_the_money(self):
        """**Never asserted by a caller.** The commonest way an invoice comes to read `paid`
        while money is outstanding is a caller passing the status it expected."""
        cases = [
            (5220, 0, 0, date(2026, 1, 10), "unpaid"),
            (5220, 0, 0, date(2026, 2, 10), "overdue"),
            (5220, 1000, 0, date(2026, 1, 10), "part_paid"),
            (5220, 1000, 0, date(2026, 2, 10), "overdue"),
            (5220, 5220, 0, date(2026, 2, 10), "paid"),
            (5220, 6000, 0, date(2026, 1, 10), "paid"),
            (5220, 0, 5220, date(2026, 2, 10), "credited"),
        ]
        for gross, paid, credited, at, expected in cases:
            self.assertEqual(
                invoicing.payment_status_for(
                    gross_minor=gross, paid_minor=paid, credited_minor=credited,
                    due_on=date(2026, 1, 31), at=at),
                expected, f"{gross}/{paid}/{credited}@{at}")

    def test_a_credit_note_reduces_what_is_owed(self):
        """MOD-015 stores credits positive and always reads them as a reduction; that
        convention is adopted rather than re-chosen."""
        self.assertEqual(
            invoicing.payment_status_for(
                gross_minor=5220, paid_minor=2610, credited_minor=2610,
                due_on=date(2026, 1, 31), at=date(2026, 1, 10)),
            "paid")

    def test_a_negative_figure_refuses(self):
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.payment_status_for(
                gross_minor=-1, paid_minor=0, credited_minor=0,
                due_on=date(2026, 1, 31), at=date(2026, 1, 10))


class FailureClassTests(unittest.TestCase):
    def test_a_permanent_failure_is_never_retried_whatever_the_budget_says(self):
        """**A budget of four attempts is not permission to present a stolen card four
        times.** A scheme fines an acquirer for that, and a regulator asks about a revoked
        mandate re-presented."""
        for code in ("card_stolen", "card_lost", "mandate_revoked", "account_closed",
                     "do_not_honour_final"):
            self.assertEqual(collections.classify_failure(code), collections.PERMANENT, code)
            self.assertFalse(collections.may_retry(code, attempts=0), code)

    def test_a_retryable_failure_is_retried_up_to_the_budget(self):
        self.assertTrue(collections.may_retry("insufficient_funds", attempts=3))
        self.assertFalse(collections.may_retry("insufficient_funds", attempts=4))

    def test_a_failure_needing_the_member_is_not_retried_by_the_system(self):
        """There is nothing to retry until the member does something, and the journey's job is
        then to ask them."""
        self.assertFalse(collections.may_retry("card_expired", attempts=0))
        self.assertEqual(
            collections.classify_failure("authentication_required"),
            collections.NEEDS_MEMBER_ACTION)

    def test_an_unseen_code_is_unknown_and_retries_cautiously(self):
        """Neither giving up on a recoverable card nor hammering a dead one."""
        self.assertEqual(
            collections.classify_failure("something_new"), collections.UNKNOWN_CAUSE)
        self.assertTrue(collections.may_retry("something_new", attempts=0))
        self.assertFalse(collections.may_retry("something_new", attempts=4))

    def test_no_code_at_all_is_unknown_rather_than_an_error(self):
        """A payment can be in `unknown` state with no code, which is precisely the case
        paragraph 1609 requires to be representable."""
        self.assertEqual(collections.classify_failure(None), collections.UNKNOWN_CAUSE)


class DunningJourneyTests(unittest.TestCase):
    def test_the_journey_is_five_stages_and_escalates_access(self):
        recommendations = [collections.stage(n).access_recommendation
                           for n in range(1, collections.FINAL_STAGE + 1)]
        self.assertEqual(recommendations,
                         ["none", "none", "warn", "restrict", "suspend"])

    def test_the_grace_period_is_added_once_at_the_front(self):
        """Counting it into every stage would stretch the whole journey, which is not what a
        grace period is -- and a corporate payer on thirty-day terms is not warned on day
        three."""
        plain = collections.opening_step(due_on=date(2026, 1, 31))
        with_grace = collections.opening_step(due_on=date(2026, 1, 31), grace_days=30)
        self.assertEqual(plain.due_on, date(2026, 1, 31))
        self.assertEqual(with_grace.due_on, date(2026, 3, 2))
        third = collections.next_step(
            current_stage=2, due_on=date(2026, 1, 31), grace_days=30)
        assert third is not None
        self.assertEqual(third.due_on, date(2026, 3, 9))

    def test_the_journey_ends_rather_than_advancing_for_ever(self):
        last = collections.next_step(
            current_stage=collections.FINAL_STAGE - 1, due_on=date(2026, 1, 31))
        assert last is not None
        self.assertTrue(last.is_final)
        self.assertIsNone(collections.next_step(
            current_stage=collections.FINAL_STAGE, due_on=date(2026, 1, 31)))

    def test_an_unknown_stage_refuses(self):
        with self.assertRaises(collections.CollectionsError):
            collections.stage(99)


class ReconciliationTests(unittest.TestCase):
    def test_no_provider_answer_leaves_it_unknown(self):
        """**Paragraph 1609.** It does not resolve to failed, because a payment that actually
        succeeded and was recorded as failed is money collected and not credited to the
        member -- the direction that produces a chargeback rather than a retry."""
        status, reason = collections.reconcile(
            recorded_status="unknown", provider_status=None)
        self.assertEqual(status, "unknown")
        self.assertEqual(reason, "provider_did_not_answer")

    def test_a_provider_still_deciding_leaves_it_unknown(self):
        status, reason = collections.reconcile(
            recorded_status="pending", provider_status="pending")
        self.assertEqual(status, "unknown")
        self.assertEqual(reason, "provider_still_deciding")

    def test_an_unsettled_record_takes_the_provider_answer(self):
        for recorded in ("pending", "requires_authentication", "unknown"):
            status, reason = collections.reconcile(
                recorded_status=recorded, provider_status="succeeded")
            self.assertEqual(status, "succeeded", recorded)
            self.assertEqual(reason, "reconciled_from_provider")

    def test_a_contradiction_is_escalated_rather_than_applied(self):
        """**Only the provider knows what it did; only a human should decide what to do when
        the two records disagree about money.** Silently overwriting a `succeeded` payment with
        `failed` would destroy the evidence of the disagreement along with the member's
        credit."""
        status, reason = collections.reconcile(
            recorded_status="succeeded", provider_status="failed")
        self.assertEqual(status, "succeeded")
        self.assertEqual(reason, "provider_disagrees_escalate")

    def test_agreement_is_reported_as_agreement(self):
        status, reason = collections.reconcile(
            recorded_status="succeeded", provider_status="succeeded")
        self.assertEqual((status, reason), ("succeeded", "already_agreed"))

    def test_a_nonsense_status_refuses(self):
        with self.assertRaises(collections.CollectionsError):
            collections.reconcile(recorded_status="banana", provider_status="succeeded")
        with self.assertRaises(collections.CollectionsError):
            collections.reconcile(recorded_status="pending", provider_status="banana")


class DaysLateTests(unittest.TestCase):
    """ADM-PAY-03's header figure, which is the server's answer and not the reader's.

    `INV-20418 UNPAID · 2 DAYS LATE`. A date is not an instant, so a client subtracting a due
    date from its own clock answers differently in a different timezone for the same invoice.
    """

    def test_counts_the_days_past_due(self):
        self.assertEqual(
            invoicing.days_late(
                due_on=date(2026, 8, 17), at=date(2026, 8, 19),
                payment_status="unpaid"),
            2)

    def test_an_invoice_not_yet_due_is_none_rather_than_zero(self):
        """Zero would state a lateness that is not there."""
        self.assertIsNone(invoicing.days_late(
            due_on=date(2026, 8, 31), at=date(2026, 8, 19), payment_status="unpaid"))

    def test_due_today_is_none(self):
        """The edge: today is the last day, so nothing is late yet."""
        self.assertIsNone(invoicing.days_late(
            due_on=date(2026, 8, 19), at=date(2026, 8, 19), payment_status="unpaid"))

    def test_a_settled_invoice_has_no_lateness_however_late_it_was_paid(self):
        """It was late once; it is not late now, and a header saying so would be wrong."""
        for status in ("paid", "credited", "written_off"):
            with self.subTest(status=status):
                self.assertIsNone(invoicing.days_late(
                    due_on=date(2026, 8, 17), at=date(2026, 12, 1),
                    payment_status=status))

    def test_an_overdue_invoice_still_counts(self):
        self.assertEqual(
            invoicing.days_late(
                due_on=date(2026, 8, 17), at=date(2026, 8, 20),
                payment_status="overdue"),
            3)

    def test_a_status_outside_the_domain_refuses(self):
        with self.assertRaises(invoicing.InvoicingError):
            invoicing.days_late(
                due_on=date(2026, 8, 17), at=date(2026, 8, 19), payment_status="banana")


class DisputeMachineTests(unittest.TestCase):
    """The scheme's own state machine, for the table MOD-017 shipped with no writer."""

    def test_a_dispute_may_be_answered_then_decided(self):
        collections.check_dispute_transition("open", "responded")
        collections.check_dispute_transition("responded", "won")

    def test_a_dispute_may_be_decided_without_a_response(self):
        """A missed deadline has to be recordable, and it is the outcome that most matters.

        A machine that required `responded` first would make "we never answered and lost"
        unwritable, which is the one fact a tenant needs on the record.
        """
        for outcome in ("won", "lost", "withdrawn"):
            with self.subTest(outcome=outcome):
                collections.check_dispute_transition("open", outcome)

    def test_a_decided_dispute_is_terminal(self):
        for closed in ("won", "lost", "withdrawn"):
            with self.subTest(closed=closed):
                with self.assertRaises(collections.DisputeError):
                    collections.check_dispute_transition(closed, "responded")

    def test_responding_twice_is_not_a_transition(self):
        with self.assertRaises(collections.DisputeError):
            collections.check_dispute_transition("responded", "responded")

    def test_a_status_outside_the_domain_refuses_on_either_side(self):
        with self.assertRaises(collections.DisputeError):
            collections.check_dispute_transition("banana", "won")
        with self.assertRaises(collections.DisputeError):
            collections.check_dispute_transition("open", "banana")

    def test_the_machine_and_the_schema_agree_on_the_statuses(self):
        """`fin_disputes_status` is the authority and this tuple is read beside it."""
        self.assertEqual(
            sorted(collections.DISPUTE_STATUSES),
            ["lost", "open", "responded", "withdrawn", "won"])
        self.assertEqual(
            sorted(collections.DISPUTE_OUTCOMES), ["lost", "withdrawn", "won"])


class EvidenceWindowTests(unittest.TestCase):
    """ADM-PAY-03's disputed state is an evidence-deadline banner, and this is the deadline."""

    def test_reports_what_is_left_and_what_was_given(self):
        window = collections.evidence_window(
            opened_on=date(2026, 8, 17), respond_due_on=date(2026, 8, 31),
            at=date(2026, 8, 28))
        self.assertEqual(window["days_remaining"], 3)
        self.assertEqual(window["days_given"], 14)
        self.assertIs(window["window_has_closed"], False)

    def test_a_passed_deadline_goes_negative_rather_than_clamping(self):
        """Zero would say the deadline is today, which is a different and wrong sentence."""
        window = collections.evidence_window(
            opened_on=date(2026, 8, 17), respond_due_on=date(2026, 8, 31),
            at=date(2026, 9, 3))
        self.assertEqual(window["days_remaining"], -3)
        self.assertIs(window["window_has_closed"], True)

    def test_the_last_day_has_not_closed(self):
        window = collections.evidence_window(
            opened_on=date(2026, 8, 17), respond_due_on=date(2026, 8, 31),
            at=date(2026, 8, 31))
        self.assertEqual(window["days_remaining"], 0)
        self.assertIs(window["window_has_closed"], False)

    def test_a_deadline_before_the_opening_refuses(self):
        with self.assertRaises(collections.DisputeError):
            collections.evidence_window(
                opened_on=date(2026, 8, 17), respond_due_on=date(2026, 8, 1),
                at=date(2026, 8, 18))


class ReportingWindowTests(unittest.TestCase):
    """ADM-CC-01's "vs July · pace to 63.1k", which is three statements and not one sum."""

    def test_month_to_date_is_the_first_through_today(self):
        span = reporting.month_to_date(date(2026, 8, 19))
        self.assertEqual((span.first, span.last), (date(2026, 8, 1), date(2026, 8, 19)))
        self.assertEqual(span.days, 19)

    def test_the_comparison_is_the_same_point_in_the_previous_month(self):
        """The design's own figure: "41,280 against 44,770 ... the same point in July".

        Nineteen days against thirty-one would report a collapse on the 19th of every month,
        which is MOD-011's `evaluate_budget` finding with the bound on the other side.
        """
        span = reporting.comparable_previous_month(date(2026, 8, 19))
        self.assertEqual((span.first, span.last), (date(2026, 7, 1), date(2026, 7, 19)))
        self.assertEqual(span.days, 19)

    def test_the_comparison_clamps_to_a_shorter_previous_month(self):
        """31 March has no counterpart in February, so the span is three days shorter.

        The alternative -- the whole of February against 31 days of March -- is the
        one-sided comparison this module exists to avoid, in the other direction.
        """
        span = reporting.comparable_previous_month(date(2026, 3, 31))
        self.assertEqual((span.first, span.last), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(span.days, 28)

    def test_the_comparison_crosses_a_year(self):
        span = reporting.comparable_previous_month(date(2026, 1, 15))
        self.assertEqual((span.first, span.last), (date(2025, 12, 1), date(2025, 12, 15)))

    def test_a_leap_february_is_the_clamp_target_too(self):
        span = reporting.comparable_previous_month(date(2024, 3, 30))
        self.assertEqual(span.last, date(2024, 2, 29))

    def test_change_is_basis_points_and_no_baseline_is_not_zero(self):
        """`0` would read as "unchanged", which is the confident wrong answer.

        The first figure is the design's own pair -- 41,280 against 44,770 -- and -780 basis
        points is the "↓ 7.8%" it renders beside them.
        """
        self.assertEqual(reporting.change_bp(41_280_00, 44_770_00), -780)
        self.assertEqual(reporting.change_bp(100, 50), 10_000)
        self.assertIsNone(reporting.change_bp(5_000, 0))

    def test_pace_projects_the_month_from_the_part_that_happened(self):
        """19 days of 41,280 over a 31-day month, straight-line.

        **The design states no basis for its own figure** -- it renders "pace to 63.1k" from
        41,280 at the 19th, which a straight-line projection does not produce (67,348 does).
        No document in the folder gives a formula, so the method here is straight-line and
        the response names it; the discrepancy is recorded as an unresolved requirement
        rather than reverse-engineered from one illustrative number.
        """
        paced = reporting.pace(4_128_000, date(2026, 8, 19))
        self.assertEqual(paced, 6_735_158)  # 4_128_000 * 31 / 19, half away from zero

    def test_pace_on_the_last_day_of_the_month_is_what_was_collected(self):
        """Nothing is left to project, so a projection that moved the figure would be wrong."""
        self.assertEqual(reporting.pace(4_128_000, date(2026, 8, 31)), 4_128_000)

    def test_week_buckets_end_with_the_one_containing_as_of(self):
        """Saturday start, because the component source calls it a market token."""
        weeks = reporting.week_buckets(date(2026, 8, 19), 3)
        self.assertEqual(len(weeks), 3)
        # 19 August 2026 is a Wednesday; its Saturday-start week began on the 15th.
        self.assertEqual(weeks[-1].first, date(2026, 8, 15))
        self.assertEqual(weeks[-1].last, date(2026, 8, 21))
        self.assertEqual(weeks[0].first, date(2026, 8, 1))
        for span in weeks:
            self.assertEqual(span.days, 7)

    def test_the_week_start_is_a_parameter_and_moves_the_buckets(self):
        monday = reporting.week_buckets(date(2026, 8, 19), 1, week_start=0)
        self.assertEqual(monday[-1].first, date(2026, 8, 17))

    def test_only_the_bucket_containing_as_of_is_partial(self):
        """The design: the last bar is a partial week, marked and not extrapolated."""
        as_of = date(2026, 8, 19)
        weeks = reporting.week_buckets(as_of, 4)
        partials = [reporting.is_partial(span, as_of) for span in weeks]
        self.assertEqual(partials, [False, False, False, True])

    def test_a_week_that_ended_on_as_of_is_not_partial(self):
        """A Friday is the last day of a Saturday-start week, so nothing is outstanding."""
        as_of = date(2026, 8, 21)
        weeks = reporting.week_buckets(as_of, 1)
        self.assertEqual(weeks[0].last, as_of)
        self.assertFalse(reporting.is_partial(weeks[0], as_of))

    def test_the_bucket_count_and_the_week_start_are_bounded(self):
        with self.assertRaises(ValueError):
            reporting.week_buckets(date(2026, 8, 19), 0)
        with self.assertRaises(ValueError):
            reporting.week_buckets(date(2026, 8, 19), reporting.MAX_WEEKS + 1)
        with self.assertRaises(ValueError):
            reporting.week_buckets(date(2026, 8, 19), 4, week_start=7)


class RecoveryTreatmentTests(unittest.TestCase):
    """ADM-PAY-05's sort: which failed payments are one decision and which want a person.

    The design's six rows are the cases here, because "the six are one decision, not six" is
    only true once the set has been sorted -- a batch mixing a member who needs a new card
    with a member whose membership ended is six decisions wearing one button.
    """

    def test_a_card_that_expired_on_a_live_membership_wants_a_link(self) -> None:
        # The design's four `link ready` rows. `card_expired` is `needs_member_action`: there
        # is nothing for the system to retry until the member does something.
        got = collections.recovery_treatment(
            "card_expired", attempts=4, membership_status="active")
        self.assertEqual(got.treatment, collections.TREATMENT_LINK)
        self.assertEqual(got.reason, "member_action_needed")
        self.assertFalse(got.may_retry)

    def test_a_frozen_member_is_reviewed_first(self) -> None:
        # "Card expired · frozen member" -- the design's third row.
        got = collections.recovery_treatment(
            "card_expired", attempts=4, membership_status="frozen")
        self.assertEqual(got.treatment, collections.TREATMENT_REVIEW)
        self.assertEqual(got.reason, "membership_frozen")

    def test_an_ended_membership_is_reviewed_first(self) -> None:
        # "Card expired · membership ended" -- the design's fourth row. Every terminal status
        # answers the same way, which is why the check reads `lifecycle.TERMINAL` rather than
        # naming one of them.
        for status in lifecycle.TERMINAL:
            with self.subTest(status=status):
                got = collections.recovery_treatment(
                    "card_expired", attempts=4, membership_status=status)
                self.assertEqual(got.treatment, collections.TREATMENT_REVIEW)
                self.assertEqual(got.reason, "membership_ended")

    def test_the_membership_check_does_not_outrank_a_permanent_failure(self) -> None:
        """A stolen card on a live membership is reviewed, not messaged.

        This is the ordering the function is mostly about: `may_retry` refuses a permanent
        failure before it looks at the attempt budget, because four attempts is not permission
        to present a stolen card four times -- and a "pay here" link is the same act by
        another route. So permanence is asked before the membership, and a live membership
        does not turn it into a link.
        """
        got = collections.recovery_treatment(
            "card_stolen", attempts=0, membership_status="active")
        self.assertEqual(got.treatment, collections.TREATMENT_REVIEW)
        self.assertEqual(got.reason, "failure_is_permanent")

    def test_a_retryable_failure_with_budget_left_is_the_systems_move(self) -> None:
        """Nothing for a person to do yet, which is a treatment rather than an absence.

        A case still waiting on an automatic attempt that appeared in a workspace headed "all
        retries exhausted" is a row somebody chases twice.
        """
        got = collections.recovery_treatment(
            "insufficient_funds", attempts=1, membership_status="active")
        self.assertEqual(got.treatment, collections.TREATMENT_RETRY)
        self.assertEqual(got.reason, "retries_remain")
        self.assertTrue(got.may_retry)

    def test_a_retryable_failure_with_the_budget_spent_wants_a_link(self) -> None:
        # The design's two `Insufficient funds` rows sit in a batch headed "all retries
        # exhausted", so they are past their budget.
        got = collections.recovery_treatment(
            "insufficient_funds", attempts=4, membership_status="active")
        self.assertEqual(got.treatment, collections.TREATMENT_LINK)
        self.assertEqual(got.reason, "retries_exhausted")

    def test_an_unknown_cause_retries_cautiously_and_then_asks_a_person(self) -> None:
        """`classify_failure`'s own default, carried through to a treatment.

        An unknown cause with budget left is retried, which is the cautious direction; with
        the budget spent it is reviewed rather than messaged, because nobody can write a
        member a sentence explaining a failure this build has no code for.
        """
        soon = collections.recovery_treatment(
            "some_code_nobody_declared", attempts=0, membership_status="active")
        self.assertEqual(soon.treatment, collections.TREATMENT_RETRY)
        spent = collections.recovery_treatment(
            "some_code_nobody_declared", attempts=4, membership_status="active")
        self.assertEqual(spent.treatment, collections.TREATMENT_REVIEW)
        self.assertEqual(spent.reason, "cause_unknown")
        # And no code at all is the same answer, which is the `unknown` payment state
        # paragraph 1609 requires to be representable.
        none = collections.recovery_treatment(
            None, attempts=4, membership_status="active")
        self.assertEqual(none.reason, "cause_unknown")

    def test_an_invoice_citing_no_membership_is_reviewed_rather_than_skipped(self) -> None:
        """`None` means this build found nothing to collect against.

        Skipping it would drop a real debt off the workspace; treating it as live would send
        somebody the ordinary notice about a membership nobody can find.
        """
        got = collections.recovery_treatment(
            "card_expired", attempts=4, membership_status=None)
        self.assertEqual(got.treatment, collections.TREATMENT_REVIEW)
        self.assertEqual(got.reason, "no_membership_cited")

    def test_every_treatment_and_reason_is_reachable(self) -> None:
        """The enumeration is a claim about what the software does.

        MOD-020 shipped four declared states nothing wrote, so a declared treatment or reason
        with no input that produces it is either a gap to disclose or a defect wearing a
        design decision's clothes. This drives the function over the cross product and
        requires every declared value to come back from something.
        """
        seen_t: set[str] = set()
        seen_r: set[str] = set()
        codes = [None, "some_code_nobody_declared", *collections.FAILURE_CLASSES]
        for code in codes:
            for attempts in (0, 4):
                for status in (None, *lifecycle.STATUSES):
                    got = collections.recovery_treatment(
                        code, attempts=attempts, membership_status=status)
                    seen_t.add(got.treatment)
                    seen_r.add(got.reason)
        self.assertEqual(seen_t, set(collections.TREATMENTS))
        self.assertEqual(seen_r, set(collections.RECOVERY_REASONS))

    def test_a_membership_status_this_build_has_no_state_for_is_refused(self) -> None:
        with self.assertRaises(collections.CollectionsError):
            collections.recovery_treatment(
                "card_expired", attempts=1, membership_status="paused")


class PlanChangeTests(unittest.TestCase):
    """ADM-MSH-05's and ADM-MSH-06's arithmetic, and the direction nobody may declare.

    The canvas states its own figures -- "Club, 11 days remaining -20.17 / Club+, 11 days
    28.60 / Pay today JOD 8.43" -- so those are the assertions rather than a restatement of
    the formula, which would pass against any proration rule.
    """

    #: A thirty-day period with eleven days left, which is the shape the canvas's numbers come
    #: out of: 5500 * 11/30 rounds to 2017 and 7800 * 11/30 is exactly 2860.
    PERIOD = (date(2026, 8, 2), date(2026, 8, 31))
    DECIDED = date(2026, 8, 21)

    def test_the_canvas_figures_come_out_of_the_module(self) -> None:
        change, steps = lifecycle.plan_change(
            decided_on=self.DECIDED, period_start=self.PERIOD[0],
            period_end=self.PERIOD[1], from_amount_minor=5500, to_amount_minor=7800,
            billing_period="monthly")
        self.assertEqual(change.kind, "upgrade")
        self.assertEqual(change.credit_minor, 2017)
        self.assertEqual(change.charge_minor, 2860)
        self.assertEqual(change.due_minor, 843)
        # "From 1 Sep her monthly becomes JOD 78.00, up from 55.00."
        self.assertEqual(change.recurring_from, date(2026, 9, 1))
        self.assertEqual(change.to_amount_minor, 7800)
        self.assertEqual(change.effective_on, self.DECIDED)
        self.assertTrue(any("due today: 843" in s for s in steps))

    def test_an_upgrade_is_effective_immediately_and_a_downgrade_at_the_renewal(self) -> None:
        """The two acts differ in *both* of the things that matter, which is why the direction
        cannot be a caller's word."""
        up, _ = lifecycle.plan_change(
            decided_on=self.DECIDED, period_start=self.PERIOD[0],
            period_end=self.PERIOD[1], from_amount_minor=5500, to_amount_minor=7800,
            billing_period="monthly")
        down, _ = lifecycle.plan_change(
            decided_on=self.DECIDED, period_start=self.PERIOD[0],
            period_end=self.PERIOD[1], from_amount_minor=7800, to_amount_minor=5500,
            billing_period="monthly")
        self.assertEqual(up.effective_on, self.DECIDED)
        self.assertEqual(down.effective_on, date(2026, 9, 1))
        self.assertGreater(up.due_minor, 0)
        self.assertEqual(down.due_minor, 0)
        self.assertEqual((down.credit_minor, down.charge_minor), (0, 0))

    def test_the_direction_follows_the_price_in_both_directions(self) -> None:
        for frm, to, kind in ((100, 200, "upgrade"), (200, 100, "downgrade")):
            change, _ = lifecycle.plan_change(
                decided_on=self.DECIDED, period_start=self.PERIOD[0],
                period_end=self.PERIOD[1], from_amount_minor=frm, to_amount_minor=to,
                billing_period="monthly")
            self.assertEqual(change.kind, kind)

    def test_the_same_price_is_a_transfer_and_is_refused(self) -> None:
        """Neither act, and guessing either would be a different product: a downgrade delays a
        change the member asked for, an upgrade moves them today for nothing."""
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            lifecycle.plan_change(
                decided_on=self.DECIDED, period_start=self.PERIOD[0],
                period_end=self.PERIOD[1], from_amount_minor=5500, to_amount_minor=5500,
                billing_period="monthly")
        self.assertIn("transfer", str(caught.exception))

    def test_an_upgrade_outside_the_current_period_is_refused(self) -> None:
        """An upgrade is effective immediately, so "immediately" has to fall in the period
        being prorated -- outside it the two figures are the whole period or nothing, neither
        of which is what the sheet discloses."""
        for day in (date(2026, 8, 1), date(2026, 9, 1)):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.plan_change(
                    decided_on=day, period_start=self.PERIOD[0],
                    period_end=self.PERIOD[1], from_amount_minor=5500,
                    to_amount_minor=7800, billing_period="monthly")

    def test_a_downgrade_outside_the_period_is_not_refused(self) -> None:
        """The bound belongs to the upgrade alone: a downgrade prorates nothing, so the day it
        was decided on does not have to be inside the period it moves at the end of."""
        change, _ = lifecycle.plan_change(
            decided_on=date(2026, 7, 1), period_start=self.PERIOD[0],
            period_end=self.PERIOD[1], from_amount_minor=7800, to_amount_minor=5500,
            billing_period="monthly")
        self.assertEqual(change.effective_on, date(2026, 9, 1))

    def test_the_credit_and_the_charge_cover_the_same_days(self) -> None:
        """The two figures are the same proration on two amounts, which is what makes the
        difference the right number -- a credit over a different span would be arithmetic
        nobody can reconcile against the days they were told about."""
        change, _ = lifecycle.plan_change(
            decided_on=self.DECIDED, period_start=self.PERIOD[0],
            period_end=self.PERIOD[1], from_amount_minor=5500, to_amount_minor=7800,
            billing_period="monthly")
        days, _ = lifecycle.prorated_amount(
            full_amount_minor=3000, period_start=self.PERIOD[0],
            period_end=self.PERIOD[1], effective_on=self.DECIDED)
        self.assertEqual(days, 1100)  # 3000 * 11/30, so eleven days of thirty
        self.assertEqual(change.due_minor, change.charge_minor - change.credit_minor)

    def test_an_unrenewable_billing_period_is_refused(self) -> None:
        """A plan change needs to say when the new figure starts, and that is the next period
        -- so a billing period nothing renews cannot answer it."""
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.plan_change(
                decided_on=self.DECIDED, period_start=self.PERIOD[0],
                period_end=self.PERIOD[1], from_amount_minor=5500, to_amount_minor=7800,
                billing_period="one_off")

    def test_a_negative_amount_and_a_backwards_period_are_refused(self) -> None:
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.plan_change(
                decided_on=self.DECIDED, period_start=self.PERIOD[0],
                period_end=self.PERIOD[1], from_amount_minor=-1, to_amount_minor=7800,
                billing_period="monthly")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.plan_change(
                decided_on=self.DECIDED, period_start=self.PERIOD[1],
                period_end=self.PERIOD[0], from_amount_minor=5500, to_amount_minor=7800,
                billing_period="monthly")


class BillingAnchorTests(unittest.TestCase):
    """ADR-0011: which boundary a billing period falls on, and what the first one costs.

    **The canvas is the fixture.** ADM-CRM-06 draws "Club · monthly · JOD 55.00 / Pro-rata to
    31 Aug · JOD 21.29 / Then 55.00 from 1 Sep", so the first test asserts all four of those
    facts against one conversion rather than restating the expression -- which would pass
    against any arithmetic. 21.29 is 55.00 x 12/31, and there is no other reading: if the
    period were anchored on the day she converts the boundary would fall in September and the
    first charge would be the whole 55.00.
    """

    MONTHLY = 5500

    def test_the_canvas_s_own_conversion_in_full(self) -> None:
        amount, ends_on, next_start, steps = lifecycle.first_charge(
            full_amount_minor=self.MONTHLY, starts_on=date(2026, 8, 20),
            billing_period="monthly", anchor="calendar")
        self.assertEqual(amount, 2129)
        self.assertEqual(ends_on, date(2026, 8, 31))
        self.assertEqual(next_start, date(2026, 9, 1))
        # The denominator is the whole of August, which is what makes 12/31 rather than 12/12.
        self.assertIn("2026-08-01..2026-08-31", " ".join(steps))

    def test_the_periods_after_it_tile_on_calendar_months_with_no_second_rule(self) -> None:
        """ADR-0011 D2. `renewal_period` is untouched, so this is the property that makes the
        decision safe rather than a claim in the migration."""
        _, ends_on, _, _ = lifecycle.first_charge(
            full_amount_minor=self.MONTHLY, starts_on=date(2026, 8, 20),
            billing_period="monthly", anchor="calendar")
        seen = []
        for _ in range(3):
            start, ends_on = lifecycle.renewal_period(
                current_end=ends_on, billing_period="monthly")
            seen.append((start, ends_on))
        self.assertEqual(seen, [
            (date(2026, 9, 1), date(2026, 9, 30)),
            (date(2026, 10, 1), date(2026, 10, 31)),
            (date(2026, 11, 1), date(2026, 11, 30)),
        ])

    def test_the_default_anchor_is_what_this_build_already_did(self) -> None:
        """ADR-0011 D1. The whole reason the default is `agreement_start` is that a membership
        already sold keeps the periods it was sold on, so this is the regression that says
        adding the column changed nothing for anybody."""
        self.assertEqual(
            lifecycle.first_period(starts_on=date(2026, 8, 20), billing_period="monthly"),
            (date(2026, 8, 20), date(2026, 9, 19)))
        amount, ends_on, next_start, steps = lifecycle.first_charge(
            full_amount_minor=self.MONTHLY, starts_on=date(2026, 8, 20),
            billing_period="monthly")
        self.assertEqual(
            (amount, ends_on, next_start), (5500, date(2026, 9, 19), date(2026, 9, 20)))
        # And it says that it did not prorate, rather than leaving a reader to infer it from a
        # figure that happens to equal the recurring one.
        self.assertIn("nothing is prorated", " ".join(steps))

    def test_the_first_period_is_not_one_day_longer_than_every_later_one(self) -> None:
        """The off-by-one `activate_membership` paid for once: a monthly membership starting on
        1 January ran to 1 February, the next period opened on 2 February, and the drift
        compounded for the life of the membership."""
        start, end = lifecycle.first_period(
            starts_on=date(2026, 1, 1), billing_period="monthly")
        self.assertEqual((start, end), (date(2026, 1, 1), date(2026, 1, 31)))

    def test_joining_on_the_first_pays_the_whole_period_under_either_anchor(self) -> None:
        """A calendar anchor only differs mid-unit, which is the case worth pinning because it
        is the one a reader would assume the proration always applies to."""
        for anchor in ("agreement_start", "calendar"):
            amount, ends_on, _, _ = lifecycle.first_charge(
                full_amount_minor=self.MONTHLY, starts_on=date(2026, 9, 1),
                billing_period="monthly", anchor=anchor)
            self.assertEqual(amount, 5500, anchor)
            self.assertEqual(ends_on, date(2026, 9, 30), anchor)

    def test_a_quarter_and_a_year_have_calendar_boundaries_too(self) -> None:
        self.assertEqual(
            lifecycle.calendar_unit(day=date(2026, 8, 20), billing_period="quarterly"),
            (date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(
            lifecycle.calendar_unit(day=date(2026, 8, 20), billing_period="annual"),
            (date(2026, 1, 1), date(2026, 12, 31)))
        self.assertEqual(
            lifecycle.first_period(
                starts_on=date(2026, 8, 20), billing_period="quarterly", anchor="calendar"),
            (date(2026, 8, 20), date(2026, 9, 30)))

    def test_a_week_has_no_calendar_boundary_this_build_may_name(self) -> None:
        """ADR-0011 D3, which is ADM-RPT-04's refusal applied to money: nothing in this build
        records whether a week begins on Sunday or Monday, so anchoring a billing period on an
        invented week boundary would be inventing product where it decides a charge."""
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.calendar_unit(day=date(2026, 8, 20), billing_period="weekly")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.first_period(
                starts_on=date(2026, 8, 20), billing_period="weekly", anchor="calendar")

    def test_a_day_pass_has_a_period_of_one_day_and_no_calendar_anchor(self) -> None:
        self.assertEqual(
            lifecycle.first_period(starts_on=date(2026, 8, 20), billing_period="one_off"),
            (date(2026, 8, 20), date(2026, 8, 20)))
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.first_period(
                starts_on=date(2026, 8, 20), billing_period="one_off", anchor="calendar")

    def test_an_anchor_outside_the_declared_two_is_refused(self) -> None:
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.first_period(
                starts_on=date(2026, 8, 20), billing_period="monthly", anchor="quarterly")

    def test_a_short_february_and_a_long_january_each_price_their_own_days(self) -> None:
        """Actual days over actual days, so the same number of remaining days costs more in a
        shorter month -- which is the convention MOD-015 set and this adopts rather than
        re-chooses."""
        feb, _, _, _ = lifecycle.first_charge(
            full_amount_minor=self.MONTHLY, starts_on=date(2026, 2, 20),
            billing_period="monthly", anchor="calendar")
        jan, _, _, _ = lifecycle.first_charge(
            full_amount_minor=self.MONTHLY, starts_on=date(2026, 1, 20),
            billing_period="monthly", anchor="calendar")
        self.assertEqual(feb, 1768)   # 9 days of 28, at 55.00 x 9/28
        self.assertEqual(jan, 2129)   # 12 days of 31, at 55.00 x 12/31
        self.assertGreater(feb / 9, jan / 12)


if __name__ == "__main__":
    unittest.main()
