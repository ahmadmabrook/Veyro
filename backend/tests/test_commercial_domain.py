"""MOD-017's decisions, with no database.

The four modules under `app/commercial/` do no I/O, so these tests are the cheapest place to
pin the arithmetic that an invoice, a notice period and an access decision rest on. What is
here is deliberately the arithmetic and the state machines; the service's locks and atomicity
are HTTP tests, because those are properties of a transaction and not of a function.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime

from app.commercial import collections, entitlements, invoicing, lifecycle

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


if __name__ == "__main__":
    unittest.main()
