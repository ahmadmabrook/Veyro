"""MOD-006 PLT-03 domain: money, lifecycle and metering decisions, with no database.

The arithmetic is the part that has to be right. A tenant-isolation bug is caught by the suite in
tests/sql; a rounding bug is caught here or it is caught by a customer.
"""

import unittest
from datetime import UTC, date, datetime, timedelta

from app.billing import money, subscription, usage


class RoundHalfUpTests(unittest.TestCase):
    def test_halves_go_away_from_zero_in_both_directions(self):
        self.assertEqual(money.round_half_up(5, 2), 3)
        self.assertEqual(money.round_half_up(-5, 2), -3)
        self.assertEqual(money.round_half_up(3, 2), 2)
        self.assertEqual(money.round_half_up(-3, 2), -2)

    def test_a_credit_rounds_to_the_same_magnitude_as_its_charge(self):
        """The symmetry is the reason for this convention, so it is asserted directly."""
        for numerator in range(-50, 51):
            self.assertEqual(
                money.round_half_up(numerator, 7), -money.round_half_up(-numerator, 7)
            )

    def test_exact_division_is_untouched(self):
        self.assertEqual(money.round_half_up(10, 5), 2)
        self.assertEqual(money.round_half_up(0, 5), 0)

    def test_a_non_positive_denominator_is_refused(self):
        for denominator in (0, -1):
            with self.assertRaises(money.MoneyError):
                money.round_half_up(1, denominator)


class RateTests(unittest.TestCase):
    def test_boundary_rates(self):
        self.assertEqual(money.apply_rate_bp(29900, 0), 0)
        self.assertEqual(money.apply_rate_bp(29900, money.BASIS_POINTS), 29900)

    def test_a_realistic_vat_rate(self):
        self.assertEqual(money.apply_rate_bp(29900, 2400), 7176)

    def test_a_fractional_percentage_is_expressible(self):
        self.assertEqual(money.apply_rate_bp(100_000, 250), 2_500)

    def test_a_negative_rate_is_refused(self):
        with self.assertRaises(money.MoneyError):
            money.apply_rate_bp(100, -1)


class AllocateTests(unittest.TestCase):
    def test_the_parts_always_sum_to_the_total(self):
        for total in (0, 1, 7, 100, 999, -100, 12345):
            for weights in ([1, 1, 1], [1, 2, 3], [5], [0, 1, 0], [7, 7]):
                self.assertEqual(sum(money.allocate(total, weights)), total,
                                 (total, weights))

    def test_the_leftover_goes_to_the_largest_remainder(self):
        self.assertEqual(money.allocate(100, [1, 1, 1]), [34, 33, 33])

    def test_proportions_are_respected(self):
        self.assertEqual(money.allocate(1000, [1, 4]), [200, 800])

    def test_a_negative_total_splits_the_same_way(self):
        self.assertEqual(money.allocate(-100, [1, 1, 1]), [-34, -33, -33])

    def test_zero_weight_takes_nothing(self):
        self.assertEqual(money.allocate(90, [0, 1, 2]), [0, 30, 60])

    def test_a_non_zero_total_cannot_be_split_across_no_weight(self):
        self.assertEqual(money.allocate(0, [0, 0]), [0, 0])
        with self.assertRaises(money.MoneyError):
            money.allocate(5, [0, 0])

    def test_negative_weights_are_refused(self):
        with self.assertRaises(money.MoneyError):
            money.allocate(10, [1, -1])


NOV = date(2026, 11, 1)
DEC = date(2026, 12, 1)


class ProrateTests(unittest.TestCase):
    def test_the_whole_period_is_the_whole_amount(self):
        self.assertEqual(money.prorate(3000, NOV, DEC, NOV), 3000)

    def test_the_last_day_is_one_day(self):
        self.assertEqual(money.prorate(3000, NOV, DEC, date(2026, 11, 30)), 100)

    def test_halfway_is_half(self):
        self.assertEqual(money.prorate(3000, NOV, DEC, date(2026, 11, 16)), 1500)

    def test_dates_outside_the_period_clamp(self):
        self.assertEqual(money.prorate(3000, NOV, DEC, date(2026, 10, 1)), 3000)
        self.assertEqual(money.prorate(3000, NOV, DEC, DEC), 0)
        self.assertEqual(money.prorate(3000, NOV, DEC, date(2027, 1, 1)), 0)

    def test_a_period_that_does_not_advance_is_refused(self):
        with self.assertRaises(money.MoneyError):
            money.prorate(100, NOV, NOV, NOV)

    def test_an_upgrade_charges_and_a_downgrade_credits(self):
        window = {"period_start": NOV, "period_end": DEC, "effective_on": date(2026, 11, 16)}
        self.assertEqual(money.plan_change_proration(2000, 6000, **window), 2000)
        self.assertEqual(money.plan_change_proration(6000, 2000, **window), -2000)

    def test_a_change_at_the_period_end_is_worth_nothing(self):
        self.assertEqual(
            money.plan_change_proration(2000, 9000, period_start=NOV, period_end=DEC,
                                        effective_on=DEC),
            0,
        )


class MoneyTypeTests(unittest.TestCase):
    def test_arithmetic_within_one_currency(self):
        a, b = money.Money(1000, "EUR"), money.Money(250, "EUR")
        self.assertEqual((a + b).minor, 1250)
        self.assertEqual((a - b).minor, 750)
        self.assertEqual(a.times(3).minor, 3000)
        self.assertEqual(a.rate(2400).minor, 240)

    def test_currencies_cannot_be_mixed(self):
        with self.assertRaises(money.MoneyError):
            money.Money(1, "EUR") + money.Money(1, "ISK")

    def test_a_malformed_currency_code_is_refused(self):
        for code in ("eur", "EURO", "EU", ""):
            with self.assertRaises(money.MoneyError):
                money.Money(1, code)


class InvoiceTotalsTests(unittest.TestCase):
    def test_total_is_subtotal_plus_tax(self):
        subtotal, tax, total = money.invoice_totals([29900], tax_rate_bp=2400)
        self.assertEqual((subtotal, tax, total), (29900, 7176, 37076))

    def test_no_rate_means_no_tax(self):
        self.assertEqual(money.invoice_totals([100, 200]), (300, 0, 300))

    def test_tax_is_taken_on_the_subtotal_not_line_by_line(self):
        """Three 1-unit lines at 50%: 1.5 rounds to 2, while per-line rounding would give 3."""
        self.assertEqual(money.invoice_totals([1, 1, 1], tax_rate_bp=5000)[1], 2)

    def test_a_discount_line_reduces_the_subtotal(self):
        self.assertEqual(money.invoice_totals([1000, -250])[0], 750)


class LifecycleTests(unittest.TestCase):
    def test_every_admitted_edge(self):
        for state, command, expected in (
            (subscription.TRIALING, subscription.CONVERT, subscription.ACTIVE),
            (subscription.TRIALING, subscription.CANCEL, subscription.CANCELLED),
            (subscription.ACTIVE, subscription.PAYMENT_FAILED, subscription.PAST_DUE),
            (subscription.ACTIVE, subscription.CANCEL, subscription.CANCELLED),
            (subscription.PAST_DUE, subscription.PAYMENT_RECOVERED, subscription.ACTIVE),
            (subscription.PAST_DUE, subscription.GRACE_EXPIRED, subscription.SUSPENDED),
            (subscription.PAST_DUE, subscription.CANCEL, subscription.CANCELLED),
            (subscription.SUSPENDED, subscription.REACTIVATE, subscription.ACTIVE),
            (subscription.SUSPENDED, subscription.CANCEL, subscription.CANCELLED),
        ):
            self.assertEqual(subscription.apply_command(state, command), expected)

    def test_reactivation_exists_here_because_plt_03_names_it(self):
        self.assertEqual(
            subscription.apply_command(subscription.SUSPENDED, subscription.REACTIVATE),
            subscription.ACTIVE,
        )

    def test_cancelled_is_terminal(self):
        self.assertEqual(subscription.admitted_commands(subscription.CANCELLED), [])
        for command in (subscription.REACTIVATE, subscription.CONVERT, subscription.CANCEL):
            with self.assertRaises(subscription.LifecycleError) as caught:
                subscription.apply_command(subscription.CANCELLED, command)
            self.assertEqual(caught.exception.code, "illegal_transition")

    def test_a_trial_cannot_skip_to_suspended_and_an_active_cannot_be_reactivated(self):
        for state, command in ((subscription.TRIALING, subscription.GRACE_EXPIRED),
                               (subscription.ACTIVE, subscription.REACTIVATE),
                               (subscription.SUSPENDED, subscription.PAYMENT_FAILED)):
            with self.assertRaises(subscription.LifecycleError):
                subscription.apply_command(state, command)

    def test_unknown_states_and_commands_fail_closed(self):
        with self.assertRaises(subscription.LifecycleError) as caught:
            subscription.apply_command("dormant", subscription.CANCEL)
        self.assertEqual(caught.exception.code, "unknown_state")
        with self.assertRaises(subscription.LifecycleError) as caught:
            subscription.apply_command(subscription.ACTIVE, "refund")
        self.assertEqual(caught.exception.code, "unknown_command")

    def test_admitted_commands_matches_the_table(self):
        self.assertEqual(subscription.admitted_commands(subscription.PAST_DUE),
                         ["cancel", "grace_expired", "payment_recovered"])

    def test_only_running_states_bill(self):
        self.assertTrue(subscription.is_billable(subscription.ACTIVE))
        self.assertTrue(subscription.is_billable(subscription.PAST_DUE))
        for state in (subscription.TRIALING, subscription.SUSPENDED, subscription.CANCELLED):
            self.assertFalse(subscription.is_billable(state), state)


class EntitlementTests(unittest.TestCase):
    def limits(self, **features):
        return [subscription.EntitlementLimit(code, value) for code, value in features.items()]

    def test_usage_within_the_new_limits_is_not_a_breach(self):
        self.assertEqual(
            subscription.entitlement_breaches({"locations": 3}, self.limits(locations=5)), []
        )

    def test_usage_above_the_new_limit_is_reported_with_both_numbers(self):
        breaches = subscription.entitlement_breaches({"locations": 8}, self.limits(locations=5))
        self.assertEqual(len(breaches), 1)
        self.assertEqual(
            (breaches[0].feature_code, breaches[0].in_use, breaches[0].new_limit),
            ("locations", 8, 5),
        )

    def test_exactly_at_the_limit_is_allowed(self):
        self.assertEqual(
            subscription.entitlement_breaches({"locations": 5}, self.limits(locations=5)), []
        )

    def test_an_unlimited_entitlement_never_breaches(self):
        unlimited = [subscription.EntitlementLimit("locations", None, unlimited=True)]
        self.assertEqual(subscription.entitlement_breaches({"locations": 9999}, unlimited), [])

    def test_a_feature_the_new_plan_drops_entirely_is_a_breach_at_zero(self):
        breaches = subscription.entitlement_breaches({"white_label": 1}, self.limits(locations=5))
        self.assertEqual((breaches[0].feature_code, breaches[0].new_limit), ("white_label", 0))

    def test_a_dropped_feature_nobody_uses_is_not_a_breach(self):
        self.assertEqual(
            subscription.entitlement_breaches({"white_label": 0}, self.limits(locations=5)), []
        )

    def test_breaches_are_reported_in_a_stable_order(self):
        breaches = subscription.entitlement_breaches(
            {"storage": 9, "api": 9, "locations": 9}, self.limits(locations=1)
        )
        self.assertEqual([b.feature_code for b in breaches], ["api", "locations", "storage"])


class PlanChangeTests(unittest.TestCase):
    def test_change_kind_follows_the_price(self):
        self.assertEqual(subscription.change_kind(1000, 2000), "upgrade")
        self.assertEqual(subscription.change_kind(2000, 1000), "downgrade")
        self.assertEqual(subscription.change_kind(2000, 2000), "change")

    def test_a_period_rolls_forward_by_its_own_length(self):
        self.assertEqual(subscription.next_period(NOV, DEC), (DEC, date(2026, 12, 31)))

    def test_a_long_period_keeps_its_length(self):
        start, end = date(2026, 1, 31), date(2026, 3, 3)
        rolled = subscription.next_period(start, end)
        self.assertEqual(rolled[1] - rolled[0], end - start)

    def test_a_period_that_does_not_advance_is_refused(self):
        with self.assertRaises(subscription.LifecycleError):
            subscription.next_period(NOV, NOV)


def _record(rid, quantity, day, corrects=None):
    return usage.UsageRecord(record_id=rid, quantity=quantity,
                             occurred_at=datetime(2026, 11, day, 12, 0, tzinfo=UTC),
                             corrects_record_id=corrects)


WINDOW = {"start": datetime(2026, 11, 1, tzinfo=UTC), "end": datetime(2026, 12, 1, tzinfo=UTC)}


class AggregateTests(unittest.TestCase):
    def test_sum_max_and_last(self):
        records = [_record("a", 10, 2), _record("b", 40, 5), _record("c", 20, 9)]
        self.assertEqual(usage.aggregate(records, aggregation=usage.SUM, **WINDOW), 70)
        self.assertEqual(usage.aggregate(records, aggregation=usage.MAX, **WINDOW), 40)
        self.assertEqual(usage.aggregate(records, aggregation=usage.LAST, **WINDOW), 20)

    def test_nothing_in_the_window_is_zero(self):
        self.assertEqual(usage.aggregate([], **WINDOW), 0)

    def test_the_window_includes_its_start_and_excludes_its_end(self):
        at_start = usage.UsageRecord("a", 5, WINDOW["start"])
        at_end = usage.UsageRecord("b", 5, WINDOW["end"])
        self.assertEqual(usage.aggregate([at_start, at_end], **WINDOW), 5)

    def test_a_late_event_lands_in_the_period_it_happened_in(self):
        """Happened in November, recorded in December: it counts in November, not December."""
        november = [_record("a", 10, 2), _record("late", 7, 28)]
        self.assertEqual(usage.aggregate(november, **WINDOW), 17)
        december = {"start": datetime(2026, 12, 1, tzinfo=UTC),
                    "end": datetime(2027, 1, 1, tzinfo=UTC)}
        self.assertEqual(usage.aggregate(november, **december), 0)

    def test_an_unknown_aggregation_is_refused(self):
        with self.assertRaises(usage.UsageError):
            usage.aggregate([], aggregation="median", **WINDOW)


class CorrectionTests(unittest.TestCase):
    def test_a_correction_lowers_the_sum(self):
        records = [_record("a", 100, 2), _record("fix", -40, 20, corrects="a")]
        self.assertEqual(usage.aggregate(records, **WINDOW), 60)

    def test_a_correction_lowers_the_peak_rather_than_adding_a_trough(self):
        """The case that decides the rule: treating -500 as its own reading leaves 900 standing."""
        records = [_record("peak", 900, 5), _record("normal", 400, 6),
                   _record("fix", -500, 25, corrects="peak")]
        self.assertEqual(usage.aggregate(records, aggregation=usage.MAX, **WINDOW), 400)

    def test_a_correction_does_not_become_the_last_reading(self):
        records = [_record("a", 100, 2), _record("b", 30, 20), _record("fix", -10, 28,
                                                                       corrects="a")]
        self.assertEqual(usage.aggregate(records, aggregation=usage.LAST, **WINDOW), 30)

    def test_a_correction_lands_in_its_targets_period_not_its_own(self):
        november = [_record("a", 100, 2)]
        correction = usage.UsageRecord("fix", -40, datetime(2026, 12, 5, tzinfo=UTC),
                                       corrects_record_id="a")
        self.assertEqual(usage.aggregate([*november, correction], **WINDOW), 60)

    def test_a_correction_whose_target_is_absent_counts_for_nothing(self):
        orphan = usage.UsageRecord("fix", -40, datetime(2026, 11, 5, tzinfo=UTC),
                                   corrects_record_id="not-here")
        self.assertEqual(usage.aggregate([_record("a", 100, 2), orphan], **WINDOW), 100)

    def test_several_corrections_to_one_record_accumulate(self):
        records = [_record("a", 100, 2), _record("f1", -10, 3, corrects="a"),
                   _record("f2", -5, 4, corrects="a")]
        self.assertEqual(usage.aggregate(records, **WINDOW), 85)


class QuotaTests(unittest.TestCase):
    def test_no_quota_means_unlimited_and_permitted(self):
        status = usage.quota_status(10_000, None)
        self.assertTrue(status.permitted)
        self.assertFalse(status.exceeded)
        self.assertEqual(status.overage_quantity, 0)

    def test_remaining_is_reported_before_the_limit_is_reached(self):
        status = usage.quota_status(300, usage.Quota(limit_quantity=1000))
        self.assertEqual((status.remaining, status.exceeded, status.overage_quantity),
                         (700, False, 0))

    def test_exactly_at_the_limit_is_not_exceeded(self):
        status = usage.quota_status(1000, usage.Quota(limit_quantity=1000))
        self.assertEqual((status.remaining, status.exceeded), (0, False))

    def test_over_the_limit_reports_the_overage_and_never_a_negative_remaining(self):
        status = usage.quota_status(1250, usage.Quota(limit_quantity=1000))
        self.assertEqual((status.remaining, status.exceeded, status.overage_quantity),
                         (0, True, 250))

    def test_a_hard_stop_refuses_once_exceeded(self):
        quota = usage.Quota(limit_quantity=100, hard_stop=True)
        self.assertTrue(usage.quota_status(100, quota).permitted)
        self.assertFalse(usage.quota_status(101, quota).permitted)

    def test_an_overage_quota_keeps_permitting(self):
        quota = usage.Quota(limit_quantity=100, overage_allowed=True)
        self.assertTrue(usage.quota_status(5_000, quota).permitted)


class OverageChargeTests(unittest.TestCase):
    def test_overage_is_charged_at_the_unit_price(self):
        quota = usage.Quota(limit_quantity=1000, overage_allowed=True)
        status = usage.quota_status(1250, quota)
        self.assertEqual(usage.overage_charge(status, quota, 4), 1000)

    def test_a_warning_threshold_charges_nothing(self):
        """Neither overage_allowed nor hard_stop: the tenant is told, nobody is billed."""
        quota = usage.Quota(limit_quantity=1000)
        self.assertEqual(usage.overage_charge(usage.quota_status(1250, quota), quota, 4), 0)

    def test_staying_inside_the_quota_charges_nothing(self):
        quota = usage.Quota(limit_quantity=1000, overage_allowed=True)
        self.assertEqual(usage.overage_charge(usage.quota_status(900, quota), quota, 4), 0)

    def test_no_quota_charges_nothing(self):
        self.assertEqual(usage.overage_charge(usage.quota_status(900, None), None, 4), 0)

    def test_a_negative_overage_price_is_refused(self):
        quota = usage.Quota(limit_quantity=10, overage_allowed=True)
        with self.assertRaises(usage.UsageError):
            usage.overage_charge(usage.quota_status(20, quota), quota, -1)


class PeriodArithmeticTests(unittest.TestCase):
    def test_a_month_of_daily_usage_sums_exactly(self):
        records = [_record(f"d{day}", day, day) for day in range(1, 31)]
        self.assertEqual(usage.aggregate(records, **WINDOW), sum(range(1, 31)))

    def test_prorating_a_year_never_exceeds_the_year(self):
        start, end = date(2026, 1, 1), date(2027, 1, 1)
        for offset in range(0, 365, 7):
            share = money.prorate(119_900, start, end, start + timedelta(days=offset))
            self.assertTrue(0 <= share <= 119_900, (offset, share))


if __name__ == "__main__":
    unittest.main()


class NegativeSubtotalTests(unittest.TestCase):
    """A big downgrade credit can take an invoice below zero; the arithmetic must still close."""

    def test_a_negative_subtotal_carries_no_tax(self):
        subtotal, tax, total = money.invoice_totals([1000, -4000], tax_rate_bp=2400)
        self.assertEqual((subtotal, tax, total), (-3000, 0, -3000))

    def test_a_zero_subtotal_carries_no_tax(self):
        self.assertEqual(money.invoice_totals([1000, -1000], tax_rate_bp=2400), (0, 0, 0))

    def test_total_is_always_subtotal_plus_tax(self):
        for lines in ([100], [100, -50], [-100], [0], [333, 333, 334]):
            subtotal, tax, total = money.invoice_totals(lines, tax_rate_bp=2400)
            self.assertEqual(total, subtotal + tax, lines)
