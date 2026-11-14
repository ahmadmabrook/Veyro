"""MOD-011 REL-02 decisions, tested without a database.

The three pure modules: what the metric catalogue refuses, what an objective can and cannot be
evaluated as, how a budget burns, and what the rate limiter admits.
"""

from __future__ import annotations

import unittest
from datetime import date

from app.observability import catalog, objectives, ratelimit


class CatalogTests(unittest.TestCase):
    def test_every_metric_has_a_producer_named_in_this_build(self) -> None:
        """A metric nothing emits is a series that reads as a measurement and is always zero.

        The modules named here are the ones with a producer wired in this change. The list is
        short on purpose and this test is what keeps it honest: adding a metric means adding
        something that emits it.
        """
        self.assertEqual({m.owner_module for m in catalog.METRICS.values()},
                         {"MOD-008", "MOD-010", "MOD-011"})

    def test_a_metric_that_duplicates_a_table_is_not_in_the_catalogue(self) -> None:
        """The four the first draft carried, every one a count over an existing table.

        Keeping them would have meant a dashboard and a `SELECT count(*)` able to answer the
        same question differently with nothing to settle it -- "logs are not a shadow database"
        applied to the metric store itself.
        """
        for duplicated in ("events.outbox_pending", "events.dead_letters",
                           "privacy.dsar_open", "privacy.dsar_overdue"):
            self.assertNotIn(duplicated, catalog.METRICS)

    def test_the_denial_counter_declares_every_category_a_permission_can_have(self) -> None:
        """`_count_denial` swallows its own failure, so a category outside the declared values
        would stop denial counting with nothing to notice. The swallow is right; this is what
        stops it hiding something."""
        from app.authorization.catalog import PERMISSIONS
        declared = {d.name: set(d.values)
                    for d in catalog.METRICS["authz.denials"].dimensions}
        self.assertLessEqual({p.category for p in PERMISSIONS.values()},
                             declared["category"])

    def test_a_restricted_field_cannot_be_a_dimension(self) -> None:
        with self.assertRaises(catalog.CatalogError) as caught:
            catalog._d("national_id", "a", "b")
        self.assertIn("must not be a metric dimension", str(caught.exception))

    def test_an_unbounded_dimension_needs_a_written_reason(self) -> None:
        with self.assertRaises(catalog.CatalogError):
            catalog._d("consumer")
        self.assertEqual(catalog._d("consumer", reason="bounded by the subscription table").name,
                         "consumer")

    def test_every_unbounded_dimension_in_the_catalogue_argues_for_itself(self) -> None:
        unbounded = catalog.unbounded_dimensions()
        self.assertTrue(unbounded)
        for _key, dimension in unbounded:
            self.assertTrue(dimension.reason.strip())

    def test_dimensions_are_validated_in_both_directions(self) -> None:
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_dimensions("authz.denials", {})
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_dimensions("authz.denials",
                                        {"category": "finance", "extra": "x"})
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_dimensions("authz.denials", {"category": "not_a_category"})
        catalog.validate_dimensions("authz.denials", {"category": "finance"})

    def test_an_unknown_metric_is_refused_where_it_is_written(self) -> None:
        with self.assertRaises(catalog.CatalogError):
            catalog.require_metric("authz.denial")

    def test_a_ratio_cannot_total_more_than_its_trials(self) -> None:
        """A duration passed into a ratio reads as 340% availability rather than as an error."""
        with self.assertRaises(catalog.CatalogError) as caught:
            catalog.validate_point("ops.synthetic_success", observations=1, total=812.0)
        self.assertIn("count of successes", str(caught.exception))
        catalog.validate_point("ops.synthetic_success", observations=10, total=7.0)

    def test_a_point_needs_a_positive_observation_count(self) -> None:
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_point("authz.denials", observations=0, total=0.0)


    def test_there_is_no_gauge_kind(self) -> None:
        """One was declared and the accumulating upsert could not honour it: a second level in
        an hour yields the sum of the two levels, and `last` returns that sum."""
        self.assertNotIn("gauge", catalog.KINDS)


class ObjectiveTests(unittest.TestCase):
    def buckets(self, *pairs: tuple[int, float]) -> list[objectives.Bucket]:
        return [objectives.Bucket(observations=o, total=t) for o, t in pairs]

    def test_a_mean_weights_by_observations_not_by_buckets(self) -> None:
        """A quiet hour must not weigh as much as a busy one; dividing by the bucket count is
        the mistake that makes one slow request during the night look like an outage."""
        window = self.buckets((1000, 1000.0), (1, 500.0))
        self.assertAlmostEqual(objectives.aggregate(window, "mean", window_hours=2),
                               1500.0 / 1001)

    def test_a_rate_divides_by_the_window_not_by_the_buckets_present(self) -> None:
        window = self.buckets((1, 60.0), (1, 60.0))
        self.assertEqual(objectives.aggregate(window, "rate_per_hour", window_hours=24), 5.0)

    def test_a_percentile_objective_is_refused_at_definition_time(self) -> None:
        with self.assertRaises(objectives.ObjectiveError) as caught:
            objectives.check_evaluable(kind="performance_budget", comparison="at_most",
                                       aggregate_as="p95", metric_kind="duration_ms")
        self.assertIn("keeps no histogram", str(caught.exception))

    def test_an_aggregate_the_metric_s_kind_cannot_mean_is_refused(self) -> None:
        """A ratio summed instead of averaged is met during a total outage: one success in ten
        thousand attempts sums to 1.0, which clears an `at_least 0.999` threshold."""
        with self.assertRaises(objectives.ObjectiveError) as caught:
            objectives.check_evaluable(kind="slo", comparison="at_least",
                                       aggregate_as="sum", metric_kind="ratio")
        self.assertIn("cannot be read as", str(caught.exception))
        objectives.check_evaluable(kind="slo", comparison="at_least", aggregate_as="mean",
                                   metric_kind="ratio")

    def test_a_budget_window_is_derived_from_the_period_and_not_from_the_caller(self) -> None:
        self.assertEqual(objectives.budget_window("monthly", date(2026, 11, 1)),
                         (date(2026, 11, 1), date(2026, 12, 1)))
        self.assertEqual(objectives.budget_window("quarterly", date(2026, 10, 1)),
                         (date(2026, 10, 1), date(2027, 1, 1)))
        self.assertEqual(objectives.budget_window("annual", date(2026, 1, 1)),
                         (date(2026, 1, 1), date(2027, 1, 1)))

    def test_a_misaligned_period_start_is_refused(self) -> None:
        """A sweep passing today's date would otherwise raise every threshold again on every
        run, because the alert rows are unique per (budget, period_start, threshold)."""
        for period, start in (("monthly", date(2026, 11, 14)),
                              ("quarterly", date(2026, 11, 1)),
                              ("annual", date(2026, 2, 1))):
            with self.assertRaises(objectives.ObjectiveError):
                objectives.budget_window(period, start)

    def test_an_empty_window_is_not_a_pass(self) -> None:
        """A dashboard that goes green during an outage is the failure this avoids."""
        verdict = objectives.evaluate([], comparison="at_least", threshold=0.99,
                                      aggregate_as="mean", window_hours=24)
        self.assertFalse(verdict.met)
        self.assertEqual(verdict.reason, "no_data_in_window")
        self.assertEqual(verdict.buckets, 0)

    def test_both_comparisons_mean_what_they_say(self) -> None:
        window = self.buckets((100, 99.0))
        self.assertTrue(objectives.evaluate(window, comparison="at_least", threshold=0.98,
                                            aggregate_as="mean", window_hours=1).met)
        self.assertFalse(objectives.evaluate(window, comparison="at_most", threshold=0.98,
                                             aggregate_as="mean", window_hours=1).met)

    def test_burn_truncates_towards_one_alert_later_rather_than_one_too_early(self) -> None:
        burn = objectives.burn(spent_minor=7999, budget_minor=10000, warn_at_bp=8000)
        self.assertEqual(burn.consumed_bp, 7999)
        self.assertEqual(burn.crossed, ())
        self.assertFalse(burn.over)

    def test_the_standard_thresholds_ride_above_the_budget_s_own_warning(self) -> None:
        burn = objectives.burn(spent_minor=12500, budget_minor=10000, warn_at_bp=8000)
        self.assertEqual(burn.crossed, (8000, 10000, 12000))
        self.assertTrue(burn.over)

    def test_an_alert_already_raised_is_not_raised_again(self) -> None:
        burn = objectives.burn(spent_minor=12500, budget_minor=10000, warn_at_bp=8000)
        self.assertEqual(objectives.alerts_to_raise(burn, {8000, 10000}), (12000,))
        self.assertEqual(objectives.alerts_to_raise(burn, {8000, 10000, 12000}), ())

    def test_a_budget_of_zero_is_refused_rather_than_divided_by(self) -> None:
        with self.assertRaises(objectives.ObjectiveError):
            objectives.burn(spent_minor=1, budget_minor=0, warn_at_bp=8000)

    def test_margin_on_no_revenue_is_undefined_rather_than_zero(self) -> None:
        """Reporting 0 bp would read as "we break even"; the truth is "nothing to measure"."""
        with self.assertRaises(objectives.ObjectiveError):
            objectives.margin_bp(revenue_minor=0, cost_minor=500)

    def test_a_negative_margin_is_a_real_answer(self) -> None:
        self.assertEqual(objectives.margin_bp(revenue_minor=1000, cost_minor=1500), -5000)
        self.assertEqual(objectives.margin_bp(revenue_minor=1000, cost_minor=250), 7500)


class RateLimitTests(unittest.TestCase):
    def test_a_budget_of_n_admits_the_nth_and_refuses_the_next(self) -> None:
        limit = ratelimit.BUDGETS["auth.recover"]
        self.assertTrue(ratelimit.decide(limit_key="auth.recover", used=limit,
                                         now_epoch=100.0).allowed)
        refused = ratelimit.decide(limit_key="auth.recover", used=limit + 1, now_epoch=100.0)
        self.assertFalse(refused.allowed)
        self.assertGreater(refused.retry_after_seconds, 0)

    def test_an_undeclared_limit_is_refused_rather_than_defaulted(self) -> None:
        with self.assertRaises(ratelimit.RateLimitError):
            ratelimit.decide(limit_key="auth.invented", used=1, now_epoch=100.0)

    def test_the_window_turns_over(self) -> None:
        limiter = ratelimit.Limiter(window_seconds=60)
        for _ in range(ratelimit.BUDGETS["auth.recover"] + 1):
            last = limiter.check(tenant_id="t", limit_key="auth.recover", subject="s",
                                 now_epoch=100.0)
        self.assertFalse(last.allowed)
        self.assertTrue(limiter.check(tenant_id="t", limit_key="auth.recover", subject="s",
                                      now_epoch=200.0).allowed)

    def test_one_tenant_cannot_spend_another_s_budget(self) -> None:
        """The whole of the noisy-neighbour requirement a per-process limiter can satisfy."""
        limiter = ratelimit.Limiter()
        for _ in range(ratelimit.BUDGETS["auth.login"] + 1):
            limiter.check(tenant_id="a", limit_key="auth.login", subject="s", now_epoch=100.0)
        self.assertTrue(limiter.check(tenant_id="b", limit_key="auth.login", subject="s",
                                      now_epoch=100.0).allowed)

    def test_two_subjects_are_counted_apart(self) -> None:
        limiter = ratelimit.Limiter()
        for _ in range(ratelimit.BUDGETS["auth.login"] + 1):
            limiter.check(tenant_id="a", limit_key="auth.login", subject="one",
                          now_epoch=100.0)
        self.assertTrue(limiter.check(tenant_id="a", limit_key="auth.login", subject="two",
                                      now_epoch=100.0).allowed)

    def test_the_tracked_set_is_bounded(self) -> None:
        """An unauthenticated caller choosing the subject is why the cap exists at all."""
        limiter = ratelimit.Limiter(max_tracked=50)
        for i in range(500):
            limiter.check(tenant_id="a", limit_key="auth.login", subject=f"s{i}",
                          now_epoch=100.0)
        self.assertLessEqual(limiter.tracked(), 50)

    def test_an_old_window_is_evicted_before_a_live_one(self) -> None:
        limiter = ratelimit.Limiter(window_seconds=60, max_tracked=2)
        limiter.check(tenant_id="a", limit_key="auth.login", subject="old", now_epoch=100.0)
        limiter.check(tenant_id="a", limit_key="auth.login", subject="live", now_epoch=200.0)
        limiter.check(tenant_id="a", limit_key="auth.login", subject="live2", now_epoch=200.0)
        verdict = limiter.check(tenant_id="a", limit_key="auth.login", subject="live",
                                now_epoch=200.0)
        self.assertEqual(verdict.used, 2)


if __name__ == "__main__":
    unittest.main()
