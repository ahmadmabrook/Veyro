"""MOD-018's decisions, with no database. COM-04.

**The arithmetic is the module**, so these are the tests that matter most: a double-entry
ledger that posts an unbalanced journal, a wallet that spends the refundable balance first, or
a recognition schedule that earns a year's revenue on day one are each wrong in a way no later
correction can find.
"""

from __future__ import annotations

import unittest
from datetime import date

from app.ledger import accounts, periods, recognition, settlement, wallet


class ChartTests(unittest.TestCase):
    def test_every_kind_names_one_of_the_five_classes(self):
        """Checked at import too; this is the test that says why it matters."""
        for kind in accounts.KINDS:
            self.assertIn(kind.account_class, accounts.CLASSES, kind.key)

    def test_the_chart_covers_what_paragraph_115_names(self):
        """"Cash/receivable/provider clearing, tax, wallet/service-credit liabilities,
        unearned revenue, earned revenue, contra revenue, COGS and FX gain/loss." A chart
        missing one of those is a module that cannot post something the sources require."""
        for required in ("cash", "receivable", "provider_clearing", "tax_payable",
                         "wallet_cash", "wallet_promotional", "unearned_revenue",
                         "revenue", "contra_revenue", "cogs", "fx_gain_loss"):
            self.assertIn(required, accounts.KIND_BY_KEY, required)

    def test_an_asset_increases_with_a_debit_and_a_liability_with_a_credit(self):
        """The whole of double-entry, and getting it wrong once makes every statement built
        from these entries wrong."""
        self.assertEqual(accounts.normal_side("cash"), accounts.DEBIT)
        self.assertEqual(accounts.normal_side("receivable"), accounts.DEBIT)
        self.assertEqual(accounts.normal_side("cogs"), accounts.DEBIT)
        self.assertEqual(accounts.normal_side("wallet_cash"), accounts.CREDIT)
        self.assertEqual(accounts.normal_side("revenue"), accounts.CREDIT)
        self.assertEqual(accounts.normal_side("unearned_revenue"), accounts.CREDIT)

    def test_a_signed_amount_reads_as_the_account_s_own_increase(self):
        """A liability credited by 500 has *increased* by 500, and a member asking what their
        wallet holds wants 500 rather than -500."""
        self.assertEqual(accounts.signed_increase("wallet_cash", -500), 500)
        self.assertEqual(accounts.signed_increase("cash", 500), 500)
        self.assertEqual(accounts.signed_increase("revenue", -1000), 1000)

    def test_a_posting_of_nothing_is_not_a_posting(self):
        with self.assertRaises(accounts.LedgerError):
            accounts.side_of(0)

    def test_an_unknown_account_kind_is_refused(self):
        with self.assertRaises(accounts.LedgerError):
            accounts.normal_side("piggy_bank")

    def test_a_journal_balances_or_it_is_refused(self):
        accounts.check_balanced([1000, -1000])
        accounts.check_balanced([1000, -600, -400])
        with self.assertRaises(accounts.LedgerError) as caught:
            accounts.check_balanced([1000, -900])
        self.assertIn("sum to 100", str(caught.exception))

    def test_a_journal_has_at_least_two_postings(self):
        """There is no such thing as half a transfer."""
        with self.assertRaises(accounts.LedgerError):
            accounts.check_balanced([0])
        with self.assertRaises(accounts.LedgerError):
            accounts.check_balanced([1000])

    def test_a_control_total_is_the_debits(self):
        self.assertEqual(accounts.control_total([1000, -600, -400]), 1000)
        self.assertEqual(accounts.control_total([600, 400, -1000]), 1000)


class WalletTests(unittest.TestCase):
    TODAY = date(2026, 11, 14)

    def live(self) -> list[wallet.Entry]:
        return [
            wallet.Entry("cash", 5000),
            wallet.Entry("promotional", 1000, date(2026, 12, 31)),
            wallet.Entry("referral", 500, date(2027, 6, 30)),
        ]

    def test_the_four_kinds_stay_distinct(self):
        """Paragraph 1686's Critical Control. One balance makes refundable and promotional
        value indistinguishable the moment either is spent."""
        held = wallet.balances(self.live(), at=self.TODAY)
        self.assertEqual(held["cash"], 5000)
        self.assertEqual(held["promotional"], 1000)
        self.assertEqual(held["referral"], 500)
        self.assertEqual(held["refund_credit"], 0)

    def test_only_what_the_member_paid_in_is_refundable(self):
        """6500 spendable and 5000 refundable: the tenant's giveaways are not the member's
        money to ask for back."""
        self.assertEqual(wallet.spendable(self.live(), at=self.TODAY), 6500)
        self.assertEqual(wallet.refundable(self.live(), at=self.TODAY), 5000)

    def test_a_debit_spends_promotional_value_first_and_cash_last(self):
        """**The order is the member's interest, not the tenant's.** Spending cash first would
        quietly convert a refundable balance into an unrefundable one every time the member
        bought anything."""
        plan = wallet.plan_debit(self.live(), amount_minor=1200, at=self.TODAY)
        self.assertEqual([(s.value_kind, s.amount_minor) for s in plan],
                         [("promotional", 1000), ("referral", 200)])
        self.assertEqual(sum(s.amount_minor for s in plan), 1200)

    def test_a_debit_crossing_every_kind_adds_up(self):
        plan = wallet.plan_debit(self.live(), amount_minor=6500, at=self.TODAY)
        self.assertEqual(sum(s.amount_minor for s in plan), 6500)
        self.assertEqual([s.value_kind for s in plan],
                         ["promotional", "referral", "cash"])

    def test_a_debit_beyond_the_balance_is_refused_rather_than_partial(self):
        """A sale half-paid is one the caller cannot tell from a success."""
        with self.assertRaises(accounts.LedgerError) as caught:
            wallet.plan_debit(self.live(), amount_minor=7000, at=self.TODAY)
        self.assertIn("6500", str(caught.exception))

    def test_lapsed_value_stops_counting_without_being_swept(self):
        """Nothing runs on a schedule here, so a balance that counted lapsed value until a
        worker removed it would be value a member could spend after it had gone."""
        later = date(2027, 1, 2)
        held = wallet.balances(self.live(), at=later)
        self.assertEqual(held["promotional"], 0)
        self.assertEqual(held["cash"], 5000)
        self.assertEqual(wallet.spendable(self.live(), at=later), 5500)

    def test_cash_value_does_not_expire(self):
        """It is money the member paid in, so an expiry on it would be the tenant keeping
        money it owes."""
        with self.assertRaises(accounts.LedgerError) as caught:
            wallet.check_credit(value_kind="cash", amount_minor=100,
                                expires_on=date(2027, 1, 1), at=self.TODAY)
        self.assertIn("money the member paid in", str(caught.exception))

    def test_promotional_value_may_expire_or_not(self):
        wallet.check_credit(value_kind="promotional", amount_minor=100,
                            expires_on=date(2027, 1, 1), at=self.TODAY)
        wallet.check_credit(value_kind="promotional", amount_minor=100,
                            expires_on=None, at=self.TODAY)

    def test_a_credit_cannot_expire_before_it_is_given(self):
        with self.assertRaises(accounts.LedgerError):
            wallet.check_credit(value_kind="promotional", amount_minor=100,
                                expires_on=date(2020, 1, 1), at=self.TODAY)

    def test_refundable_is_the_money_the_member_paid_in_and_nothing_else(self):
        """The figure a member is told they could get back. **There is no refund guard**: the
        one that was here guarded nobody, because nothing in this build pays money out."""
        self.assertEqual(wallet.refundable(self.live(), at=self.TODAY), 5000)
        self.assertEqual(wallet.spendable(self.live(), at=self.TODAY), 6500)
        self.assertFalse(hasattr(wallet, "check_refund"))

    def test_expired_value_that_was_already_spent_is_not_deducted_twice(self):
        """A member who *used* a promo code lost, on the day it would have expired, an amount
        of their own paid-in cash equal to the promo they had already spent."""
        entries = [
            wallet.Entry("cash", 5000),
            wallet.Entry("promotional", 1000, date(2026, 11, 20)),
            wallet.Entry("promotional", -1000),
        ]
        after = date(2026, 12, 1)
        self.assertEqual(wallet.balances(entries, at=after)["promotional"], 0)
        self.assertEqual(wallet.balances(entries, at=after)["cash"], 5000)
        self.assertEqual(wallet.spendable(entries, at=after), 5000)
        # Unspent, the same credit lapses in full and the cash is untouched.
        unspent = entries[:2]
        self.assertEqual(wallet.spendable(unspent, at=after), 5000)
        self.assertEqual(wallet.spendable(unspent, at=date(2026, 11, 15)), 6000)

    def test_the_expiry_warning_is_capped_at_what_is_actually_there(self):
        soon = date(2026, 11, 20)
        entries = [wallet.Entry("promotional", 1000, soon),
                   wallet.Entry("promotional", 1000, soon),
                   wallet.Entry("promotional", -1500)]
        self.assertEqual(
            wallet.expiring_before(entries, horizon=date(2026, 12, 31), at=self.TODAY), 500)

    def test_the_two_liability_accounts_are_what_the_kinds_post_to(self):
        """Refund credit is money owed; referral value was given away. That is what they are
        in accounting terms, and it is why there are two accounts rather than four."""
        self.assertEqual(wallet.LIABILITY_ACCOUNT["cash"], "wallet_cash")
        self.assertEqual(wallet.LIABILITY_ACCOUNT["refund_credit"], "wallet_cash")
        self.assertEqual(wallet.LIABILITY_ACCOUNT["promotional"], "wallet_promotional")
        self.assertEqual(wallet.LIABILITY_ACCOUNT["referral"], "wallet_promotional")

    def test_a_statement_s_running_balance_is_computed_from_the_entries(self):
        from datetime import UTC, datetime
        rows = [
            (datetime(2026, 1, 1, tzinfo=UTC), wallet.Entry("cash", 5000), "paid in"),
            (datetime(2026, 2, 1, tzinfo=UTC), wallet.Entry("cash", -2000), "a class"),
        ]
        lines = wallet.statement_lines(rows, at=self.TODAY)
        self.assertEqual([line["balance_after"] for line in lines], [5000, 3000])

    def test_an_unknown_value_kind_is_refused(self):
        with self.assertRaises(accounts.LedgerError):
            wallet.check_kind("loyalty_points")


class PeriodTests(unittest.TestCase):
    def test_a_period_key_is_derived_from_the_date(self):
        self.assertEqual(periods.period_key_for(date(2026, 11, 14)), "2026-11")
        self.assertEqual(periods.period_key_for(date(2026, 1, 1)), "2026-01")

    def test_month_bounds_are_the_first_and_last_day(self):
        self.assertEqual(periods.month_bounds("2026-11"),
                         (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(periods.month_bounds("2026-12"),
                         (date(2026, 12, 1), date(2026, 12, 31)))
        self.assertEqual(periods.month_bounds("2028-02"),
                         (date(2028, 2, 1), date(2028, 2, 29)))

    def test_a_malformed_period_key_is_refused(self):
        for bad in ("2026-13", "26-11", "2026-00", "november"):
            with self.assertRaises(accounts.LedgerError, msg=bad):
                periods.month_bounds(bad)

    def test_a_closed_period_admits_nothing(self):
        """COM-04-R06. The correction for something found afterwards is a posting in the open
        period that references the original."""
        closed = periods.Period("2026-10", date(2026, 10, 1), date(2026, 10, 31), "closed")
        for purpose in periods.PURPOSES:
            with self.assertRaises(accounts.LedgerError, msg=purpose):
                periods.check_postable(closed, purpose)

    def test_a_closing_period_admits_the_close_s_own_work_and_no_trade(self):
        """Which is the whole point of the state: a period that admitted nothing could never
        be closed."""
        closing = periods.Period("2026-10", date(2026, 10, 1), date(2026, 10, 31),
                                 "closing")
        with self.assertRaises(accounts.LedgerError):
            periods.check_postable(closing, "trade")
        for purpose in ("correction", "recognition", "settlement", "close"):
            periods.check_postable(closing, purpose)

    def test_a_reopened_period_admits_corrections_only(self):
        reopened = periods.Period("2026-10", date(2026, 10, 1), date(2026, 10, 31),
                                  "reopened")
        periods.check_postable(reopened, "correction")
        for purpose in ("trade", "recognition", "settlement"):
            with self.assertRaises(accounts.LedgerError, msg=purpose):
                periods.check_postable(reopened, purpose)

    def test_a_closed_period_never_reopens_on_its_own_authority(self):
        """`reopened` is a distinct state with its own permission and its own written reason,
        so a statement can say "this month was reopened on the fourteenth"."""
        periods.check_transition("closed", "reopened")
        with self.assertRaises(accounts.LedgerError):
            periods.check_transition("closed", "open")
        with self.assertRaises(accounts.LedgerError):
            periods.check_transition("closed", "closing")

    def test_a_purpose_is_derived_from_where_the_journal_came_from(self):
        """**`purpose` decides whether a period under close admits the journal**, so a caller
        able to send it chose that: a reviewer posted the identical trade as `settlement`
        after it was refused as `trade`. Everything but `close` is derivable."""
        self.assertEqual(periods.PURPOSE_BY_SOURCE["correction"], "correction")
        self.assertEqual(periods.PURPOSE_BY_SOURCE["recognition"], "recognition")
        self.assertEqual(periods.PURPOSE_BY_SOURCE["settlement"], "settlement")
        for ordinary in ("invoice", "payment", "refund", "wallet", "manual", "deposit"):
            self.assertNotIn(ordinary, periods.PURPOSE_BY_SOURCE, ordinary)


class RecognitionTests(unittest.TestCase):
    YEAR = recognition.Schedule(
        basis="straight_line", total_minor=120000, currency="JOD",
        starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31))
    PACK = recognition.Schedule(
        basis="on_delivery", total_minor=10000, currency="JOD", units_total=3)
    JOINING_FEE = recognition.Schedule(
        basis="immediate", total_minor=5000, currency="JOD")

    def test_prepaid_cash_is_not_day_one_revenue(self):
        """Paragraph 1695, and the reason this module exists: a member who pays for a year in
        January has given the tenant cash and a claim on eleven months of service."""
        self.assertEqual(recognition.earned_by(self.YEAR, at=date(2026, 1, 1)), 329)
        self.assertEqual(recognition.earned_by(self.YEAR, at=date(2025, 12, 31)), 0)

    def test_a_straight_line_schedule_earns_exactly_its_total_by_the_end(self):
        """Largest-remainder allocation, so the last day earns the rounding rather than it
        being lost."""
        self.assertEqual(recognition.earned_by(self.YEAR, at=date(2026, 12, 31)), 120000)
        self.assertEqual(recognition.earned_by(self.YEAR, at=date(2027, 6, 1)), 120000)

    def test_a_class_pack_earns_on_delivery_and_not_by_time(self):
        """An unused class is still owed, so charging time against a pack would recognise
        revenue for sessions the member can still demand."""
        earned = [recognition.earned_by(self.PACK, at=date(2026, 6, 1),
                                        units_delivered=n) for n in range(4)]
        self.assertEqual(earned, [0, 3334, 6667, 10000])

    def test_a_joining_fee_earns_when_it_is_sold(self):
        self.assertEqual(
            recognition.earned_by(self.JOINING_FEE, at=date(2026, 1, 1)), 5000)

    def test_recognition_is_cumulative_so_running_it_twice_posts_once(self):
        """**The decision that makes it safe with no worker.** An incremental design would
        double-count the day it ran twice."""
        midyear = date(2026, 6, 30)
        first = recognition.to_recognise(self.YEAR, already_minor=0, at=midyear)
        self.assertEqual(first, 59549)
        second = recognition.to_recognise(self.YEAR, already_minor=first, at=midyear)
        self.assertEqual(second, 0)

    def test_nothing_earned_is_zero_rather_than_an_error(self):
        """The ordinary answer on most days, and a command that refused would make a sweep
        over every live schedule a sweep of mostly failures."""
        self.assertEqual(
            recognition.to_recognise(self.YEAR, already_minor=0,
                                     at=date(2025, 1, 1)), 0)

    def test_over_recognition_is_reported_and_never_posted(self):
        """A negative recognition would reverse earned revenue with nothing to show why."""
        early = date(2026, 1, 31)
        self.assertEqual(
            recognition.to_recognise(self.YEAR, already_minor=50000, at=early), 0)
        self.assertEqual(
            recognition.over_recognised(self.YEAR, already_minor=50000, at=early),
            50000 - recognition.earned_by(self.YEAR, at=early))

    def test_more_recognised_than_the_schedule_holds_is_refused(self):
        with self.assertRaises(accounts.LedgerError):
            recognition.to_recognise(self.YEAR, already_minor=130000,
                                     at=date(2026, 6, 1))

    def test_a_schedule_carrying_both_a_period_and_a_unit_count_is_refused(self):
        """`earned_by` would have to choose, and whichever it chose would be wrong half the
        time."""
        with self.assertRaises(accounts.LedgerError):
            recognition.check_schedule(recognition.Schedule(
                basis="straight_line", total_minor=1000, currency="JOD",
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                units_total=10))
        with self.assertRaises(accounts.LedgerError):
            recognition.check_schedule(recognition.Schedule(
                basis="on_delivery", total_minor=1000, currency="JOD", units_total=10,
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31)))

    def test_a_schedule_is_bounded_in_both_dimensions(self):
        """The allocation is linear in the day or unit count, so an unbounded one is a request
        that allocates a hundred million shares and answers 500."""
        with self.assertRaises(accounts.LedgerError):
            recognition.check_schedule(recognition.Schedule(
                basis="straight_line", total_minor=1000, currency="JOD",
                starts_on=date(2026, 1, 1), ends_on=date(2060, 1, 1)))
        with self.assertRaises(accounts.LedgerError):
            recognition.check_schedule(recognition.Schedule(
                basis="on_delivery", total_minor=1000, currency="JOD",
                units_total=200_000))

    def test_what_remains_is_the_total_less_what_was_recognised(self):
        self.assertEqual(
            recognition.remaining(self.YEAR, already_minor=20000), 100000)


class SettlementTests(unittest.TestCase):
    def line(self, **kwargs: object) -> settlement.Line:
        base = {"line_kind": "payment", "provider_ref": "ch_1",
                "amount_minor": 1000, "currency": "JOD"}
        base.update(kwargs)
        return settlement.Line(**base)  # type: ignore[arg-type]

    def test_a_line_that_agrees_is_matched(self):
        verdict = settlement.match(
            self.line(),
            settlement.Recorded("pay-1", 1000, "JOD"))
        self.assertEqual(verdict.outcome, settlement.MATCHED)
        self.assertFalse(verdict.needs_a_case)

    def test_a_line_with_nothing_behind_it_is_unmatched(self):
        verdict = settlement.match(self.line(), None)
        self.assertEqual(verdict.outcome, settlement.UNMATCHED)
        self.assertTrue(verdict.needs_a_case)

    def test_a_fee_matches_nothing_here_and_opens_no_case(self):
        """It is the provider's own movement; a case for each would bury the lines that
        actually need somebody."""
        # Negative, because a fee is a deduction from what the provider owes: the sign per
        # kind is this module's stated convention, since the posting takes the magnitude.
        verdict = settlement.match(
            self.line(line_kind="fee", amount_minor=-1000), None)
        self.assertEqual(verdict.outcome, settlement.NOT_EXPECTED)

    def test_the_currency_is_compared_before_the_amount(self):
        """Two minor-unit counts that are equal in different currencies are the comparison
        MOD-015's money discipline forbids."""
        verdict = settlement.match(
            self.line(), settlement.Recorded("pay-1", 1000, "USD"))
        self.assertEqual(verdict.outcome, settlement.AMOUNT_MISMATCH)
        self.assertIn("USD", verdict.reason)

    def test_two_rows_sharing_a_reference_are_a_duplicate_not_a_pick(self):
        verdict = settlement.match(
            self.line(), settlement.Recorded("pay-1", 1000, "JOD", count=2))
        self.assertEqual(verdict.outcome, settlement.DUPLICATE)

    def test_a_refund_is_compared_by_magnitude_because_the_signs_oppose(self):
        verdict = settlement.match(
            self.line(line_kind="refund", amount_minor=-500),
            settlement.Recorded("ref-1", 500, "JOD"))
        self.assertEqual(verdict.outcome, settlement.MATCHED)

    def test_a_control_total_that_disagrees_with_its_lines_is_a_case(self):
        """A file whose header disagrees with its body was truncated or edited in transit."""
        lines = [self.line(), self.line(line_kind="fee", amount_minor=-50)]
        self.assertEqual(settlement.control_total(lines), {"JOD": 950})
        agreed = settlement.check_control_total(
            claimed_minor=950, computed_minor=950, currency="JOD")
        self.assertFalse(agreed.needs_a_case)
        off = settlement.check_control_total(
            claimed_minor=1000, computed_minor=950, currency="JOD")
        self.assertTrue(off.needs_a_case)

    def test_a_total_is_never_summed_across_currencies(self):
        lines = [self.line(), self.line(provider_ref="ch_2", currency="USD")]
        self.assertEqual(settlement.control_total(lines), {"JOD": 1000, "USD": 1000})

    def test_a_malformed_line_is_refused(self):
        for bad in ({"line_kind": "mystery"}, {"amount_minor": 0},
                    {"provider_ref": "  "}, {"currency": "jod"}):
            with self.assertRaises(accounts.LedgerError, msg=str(bad)):
                settlement.check_line(self.line(**bad))


class SettlementSignTests(unittest.TestCase):
    """**The posting takes the magnitude**, so the sign per kind has to be the convention
    rather than an assumption: a clawback sent as a negative payout would otherwise post in
    the wrong direction by twice its value."""

    def line(self, kind: str, amount: int) -> settlement.Line:
        return settlement.Line(line_kind=kind, provider_ref="r", amount_minor=amount,
                               currency="JOD")

    def test_a_fee_is_negative_and_a_payout_is_positive(self):
        settlement.check_line(self.line("fee", -1000))
        settlement.check_line(self.line("payout", 10000))

    def test_the_other_direction_is_refused_with_a_sentence(self):
        with self.assertRaises(accounts.LedgerError) as caught:
            settlement.check_line(self.line("fee", 1000))
        self.assertIn("a credit nobody has named", str(caught.exception))
        with self.assertRaises(accounts.LedgerError) as caught:
            settlement.check_line(self.line("payout", -10000))
        self.assertIn("clawback", str(caught.exception))

    def test_a_payment_or_a_refund_carries_either_sign(self):
        """Those two are matched rather than posted, so their sign is the provider's own
        statement about direction and nothing here depends on it."""
        for kind in ("payment", "refund", "chargeback", "adjustment"):
            settlement.check_line(self.line(kind, 500))
            settlement.check_line(self.line(kind, -500))


class CashTests(unittest.TestCase):
    def test_over_is_positive_so_a_column_of_variances_sums_to_the_net(self):
        """Stated because it decides what a report means: "we are down 30.00 this week" is a
        negative number rather than an argument about direction."""
        self.assertEqual(
            settlement.variance(settlement.Count(5000, 5200, "JOD")), 200)
        self.assertEqual(
            settlement.variance(settlement.Count(5000, 4800, "JOD")), -200)

    def test_an_unexplained_variance_refuses_the_close(self):
        """A till 2.00 down every evening with nothing written is a pattern, and the only way
        it is visible later is if each close said something at the time."""
        settlement.check_close(settlement.Count(5000, 5000, "JOD"), reason=None)
        with self.assertRaises(accounts.LedgerError) as caught:
            settlement.check_close(settlement.Count(5000, 4800, "JOD"), reason=None)
        self.assertIn("-200", str(caught.exception))
        settlement.check_close(settlement.Count(5000, 4800, "JOD"),
                               reason="a member was given change twice")

    def test_a_blank_reason_is_not_an_explanation(self):
        with self.assertRaises(accounts.LedgerError):
            settlement.check_close(settlement.Count(5000, 4800, "JOD"), reason="   ")

    def test_a_till_cannot_hold_a_negative_amount(self):
        with self.assertRaises(accounts.LedgerError):
            settlement.check_close(settlement.Count(5000, -1, "JOD"), reason="odd")

    def test_a_deposit_that_disagrees_with_its_sessions_is_a_case(self):
        self.assertFalse(settlement.deposit_matches(
            declared_minor=5000, sessions_minor=5000).needs_a_case)
        self.assertTrue(settlement.deposit_matches(
            declared_minor=5000, sessions_minor=4900).needs_a_case)

    def test_a_case_s_age_is_counted_in_days_and_never_negative(self):
        self.assertEqual(
            settlement.ageing(date(2026, 11, 1), at=date(2026, 11, 14)), 13)
        self.assertEqual(
            settlement.ageing(date(2026, 11, 20), at=date(2026, 11, 14)), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
