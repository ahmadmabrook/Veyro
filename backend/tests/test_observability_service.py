"""MOD-011 REL-02 service against a real database.

The properties worth a database are the ones a mock would assert into existence: that a bucket
accumulates rather than duplicating, that a probe result and the series it feeds commit
together, that a burn alert fires once per period and threshold, and that the events reach the
outbox in the same transaction as the thing they describe.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, date, datetime, timedelta

from app.db import tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.observability import catalog
from app.observability import metrics as obs_metrics
from app.observability import service as observability
from tests.support import GatedApiTestCase

ACTOR = "33333333-3333-4333-8333-333333333333"
#: An hour that has already happened, derived rather than hard-coded: the write path refuses a
#: bucket in the future, and a fixed timestamp makes this suite pass or fail by the date.
HOUR = (datetime.now(UTC) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


class ObservabilityTestCase(GatedApiTestCase):
    def correlate(self) -> str:
        return str(uuid.uuid4())

    def outbox(self, tenant_id: str, event_type: str) -> list[dict]:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            rows = conn.execute(
                "SELECT payload FROM plt01.evt_outbox WHERE event_type = %s", (event_type,)
            ).fetchall()
        return [r[0] for r in rows]

    def objective(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {
            "objective_key": f"k{uuid.uuid4().hex[:8]}", "kind": "slo",
            "metric_key": "ops.synthetic_success", "comparison": "at_least",
            "threshold": 0.99, "window_hours": 24, "aggregate_as": "mean",
            "owner": "platform-ops", "runbook_ref": "RB-REL-02#login",
            "dimensions": {"check_key": "login"},
        }
        body.update(kwargs)
        return observability.define_objective(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def invoice(self, tenant_id: str, *, subtotal: int, partner_share: int,
                tax: int = 240000) -> str:
        """An issued invoice, written directly because MOD-015's own path needs a plan."""
        invoice_id = str(uuid.uuid4())
        subscription_id = str(uuid.uuid4())
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            conn.execute(
                "INSERT INTO plt01.bil_subscriptions"
                " (tenant_id, subscription_id, plan_code, plan_version, terms, status,"
                "  currency, billing_interval, period_start, period_end, started_on)"
                " VALUES (%s, %s, 'core', 1, '{}'::jsonb, 'active', 'EUR', 'monthly',"
                "  DATE '2026-11-01', DATE '2026-12-01', DATE '2026-11-01')",
                (tenant_id, subscription_id),
            )
            conn.execute(
                "INSERT INTO plt01.bil_invoices"
                " (tenant_id, invoice_id, invoice_number, subscription_id, currency,"
                "  period_start, period_end, subtotal_minor, tax_minor, total_minor,"
                "  partner_code, revenue_share_minor, correlation_id)"
                " VALUES (%s, %s, %s, %s, 'EUR', DATE '2026-11-01', DATE '2026-11-30',"
                "  %s, %s, %s, 'gymchain', %s, %s)",
                (tenant_id, invoice_id, f"INV-{invoice_id[:8]}", subscription_id, subtotal,
                 tax, subtotal + tax, partner_share, ACTOR),
            )
        return invoice_id

    def credit(self, tenant_id: str, *, amount_minor: int) -> None:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            invoice_id = conn.execute(
                "SELECT invoice_id FROM plt01.bil_invoices LIMIT 1").fetchone()
            assert invoice_id is not None
            conn.execute(
                "INSERT INTO plt01.bil_credit_notes"
                " (tenant_id, credit_note_number, invoice_id, amount_minor, reason, actor_id,"
                "  correlation_id)"
                " VALUES (%s, %s, %s, %s, 'service credit', %s, %s)",
                (tenant_id, f"CN-{uuid.uuid4().hex[:8]}", invoice_id[0], amount_minor, ACTOR,
                 ACTOR),
            )

    def check(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {"check_key": f"probe.{uuid.uuid4().hex[:8]}",
                      "description": "Signs a synthetic member in", "workflow": "login",
                      "interval_seconds": 60}
        body.update(kwargs)
        return observability.register_check(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )


class MetricPointTests(ObservabilityTestCase):
    def test_a_second_point_in_one_bucket_accumulates_rather_than_duplicating(self):
        """The unique index is the accumulation. Without it a series doubles silently, which is
        the one failure mode a dashboard cannot show you."""
        tenant_id = self.tenant()
        for _ in range(3):
            obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                total=1.0, dimensions={"category": "finance"}, at=HOUR)
        read = obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                  window_hours=1, until=HOUR)
        self.assertEqual(len(read["buckets"]), 1)
        self.assertEqual(read["buckets"][0]["observations"], 3)
        self.assertEqual(read["buckets"][0]["total"], 3.0)

    def test_a_different_dimension_set_is_a_different_series(self):
        tenant_id = self.tenant()
        obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                            total=1.0, dimensions={"category": "finance"}, at=HOUR)
        obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                            total=1.0, dimensions={"category": "access"}, at=HOUR)
        whole = obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                   window_hours=1, until=HOUR)
        self.assertEqual(len(whole["buckets"]), 2)
        sliced = obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                    window_hours=1, until=HOUR,
                                    dimensions={"category": "access"})
        self.assertEqual(len(sliced["buckets"]), 1)

    def test_a_point_outside_the_window_is_not_in_the_series(self):
        tenant_id = self.tenant()
        obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                            total=1.0, dimensions={"category": "finance"},
                            at=HOUR - timedelta(hours=48))
        read = obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                  window_hours=24, until=HOUR)
        self.assertEqual(read["buckets"], [])

    def test_an_undeclared_dimension_never_reaches_the_table(self):
        tenant_id = self.tenant()
        with self.assertRaises(catalog.CatalogError):
            obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                total=1.0, dimensions={"category": "finance", "who": "me"},
                                at=HOUR)

    def test_a_point_rolls_back_with_the_transaction_it_was_written_in(self):
        """`observe_in` runs on the caller's connection, so a caller that rolls back loses the
        point. That is the whole difference from `observe`, and it is what makes the probe
        result and its series commit together."""
        tenant_id = self.tenant()
        try:
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                obs_metrics.observe_in(conn, tenant_id, metric_key="authz.denials", total=1.0,
                                       dimensions={"category": "finance"}, at=HOUR)
                raise RuntimeError("the business write failed")
        except RuntimeError:
            pass
        read = obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                  window_hours=1, until=HOUR)
        self.assertEqual(read["buckets"], [])


class ObjectiveServiceTests(ObservabilityTestCase):
    def test_a_percentile_objective_is_refused_before_it_is_stored(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            self.objective(tenant_id, aggregate_as="p95")
        self.assertEqual(observability.list_objectives(self._tenant_pool, tenant_id), [])

    def test_two_live_objectives_cannot_share_a_key(self):
        tenant_id = self.tenant()
        first = self.objective(tenant_id)
        with self.assertRaises(Conflict):
            self.objective(tenant_id, objective_key=first["objective_key"])

    def test_a_retired_key_can_be_taken_again(self):
        """Retirement has to leave the key usable, or a corrected objective needs a new name
        and every dashboard pointing at the old one silently stops."""
        tenant_id = self.tenant()
        first = self.objective(tenant_id)
        observability.retire_objective(self._tenant_pool, tenant_id, first["objective_id"],
                                       actor_id=ACTOR, correlation_id=self.correlate())
        again = self.objective(tenant_id, objective_key=first["objective_key"])
        self.assertNotEqual(again["objective_id"], first["objective_id"])

    def test_a_retired_objective_is_not_evaluated(self):
        tenant_id = self.tenant()
        objective = self.objective(tenant_id)
        observability.retire_objective(self._tenant_pool, tenant_id, objective["objective_id"],
                                       actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            observability.evaluate_objective(
                self._tenant_pool, tenant_id, objective["objective_id"],
                correlation_id=self.correlate(),
            )

    def test_an_empty_window_does_not_publish_a_breach(self):
        """"The measurement is missing" and "the system is failing" are different alerts, and
        conflating them is how an alert channel gets muted."""
        tenant_id = self.tenant()
        objective = self.objective(tenant_id)
        verdict = observability.evaluate_objective(
            self._tenant_pool, tenant_id, objective["objective_id"],
            correlation_id=self.correlate(), until=HOUR,
        )
        self.assertFalse(verdict["met"])
        self.assertEqual(verdict["reason"], "no_data_in_window")
        self.assertEqual(self.outbox(tenant_id, "performance_budget.exceeded"), [])

    def test_a_breach_publishes_an_event_carrying_the_owner_and_the_runbook(self):
        tenant_id = self.tenant()
        objective = self.objective(tenant_id, window_hours=1)
        obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="ops.synthetic_success",
                            total=5.0, observations=10, dimensions={"check_key": "login"},
                            at=HOUR)
        verdict = observability.evaluate_objective(
            self._tenant_pool, tenant_id, objective["objective_id"],
            correlation_id=self.correlate(), until=HOUR,
        )
        self.assertFalse(verdict["met"])
        self.assertAlmostEqual(verdict["observed"], 0.5)
        published = self.outbox(tenant_id, "performance_budget.exceeded")
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["owner"], "platform-ops")
        self.assertEqual(published[0]["runbook_ref"], "RB-REL-02#login")

    def test_a_met_objective_publishes_nothing(self):
        tenant_id = self.tenant()
        objective = self.objective(tenant_id, window_hours=1)
        obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="ops.synthetic_success",
                            total=10.0, observations=10, dimensions={"check_key": "login"},
                            at=HOUR)
        verdict = observability.evaluate_objective(
            self._tenant_pool, tenant_id, objective["objective_id"],
            correlation_id=self.correlate(), until=HOUR,
        )
        self.assertTrue(verdict["met"])
        self.assertEqual(self.outbox(tenant_id, "performance_budget.exceeded"), [])


class SyntheticCheckTests(ObservabilityTestCase):
    def test_a_result_and_the_series_it_feeds_commit_together(self):
        """A run in the ledger but missing from the series makes an SLO disagree with the
        evidence underneath it, in the direction that hides failures."""
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        observability.record_result(
            self._tenant_pool, tenant_id, check_id=check["check_id"], outcome="passed",
            duration_ms=120, observed_at=HOUR, actor_id=ACTOR,
            correlation_id=self.correlate(),
        )
        success = obs_metrics.series(self._tenant_pool, tenant_id,
                                     metric_key="ops.synthetic_success", window_hours=1,
                                     until=HOUR)
        latency = obs_metrics.series(self._tenant_pool, tenant_id,
                                     metric_key="ops.synthetic_latency", window_hours=1,
                                     until=HOUR)
        self.assertEqual(success["buckets"][0]["total"], 1.0)
        self.assertEqual(latency["buckets"][0]["total"], 120.0)

    def test_a_failure_publishes_and_a_pass_does_not(self):
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        observability.record_result(
            self._tenant_pool, tenant_id, check_id=check["check_id"], outcome="passed",
            duration_ms=10, observed_at=HOUR, actor_id=ACTOR,
            correlation_id=self.correlate(),
        )
        self.assertEqual(self.outbox(tenant_id, "synthetic_check.failed"), [])
        observability.record_result(
            self._tenant_pool, tenant_id, check_id=check["check_id"], outcome="failed",
            duration_ms=812, detail="timed out at the token step", observed_at=HOUR,
            actor_id=ACTOR, correlation_id=self.correlate(),
        )
        published = self.outbox(tenant_id, "synthetic_check.failed")
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["check_key"], check["check_key"])

    def test_a_failure_with_no_detail_is_refused(self):
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        with self.assertRaises(InvalidRequest):
            observability.record_result(
                self._tenant_pool, tenant_id, check_id=check["check_id"], outcome="failed",
                duration_ms=1, observed_at=HOUR, actor_id=ACTOR,
                correlation_id=self.correlate(),
            )

    def test_a_result_against_an_unknown_check_is_not_found(self):
        tenant_id = self.tenant()
        with self.assertRaises(NotFound):
            observability.record_result(
                self._tenant_pool, tenant_id, check_id=str(uuid.uuid4()), outcome="passed",
                duration_ms=1, observed_at=HOUR, actor_id=ACTOR,
                correlation_id=self.correlate(),
            )

    def test_a_check_can_be_disabled_and_enabled_again(self):
        """MOD-010 shipped a subscription that could be deactivated and never reactivated; this
        is the same shape, caught before it shipped."""
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        observability.set_check_enabled(self._tenant_pool, tenant_id, check["check_id"],
                                        enabled=False, actor_id=ACTOR,
                                        correlation_id=self.correlate())
        self.assertFalse(observability.list_checks(self._tenant_pool, tenant_id)[0]["enabled"])
        observability.set_check_enabled(self._tenant_pool, tenant_id, check["check_id"],
                                        enabled=True, actor_id=ACTOR,
                                        correlation_id=self.correlate())
        live = observability.list_checks(self._tenant_pool, tenant_id)[0]
        self.assertTrue(live["enabled"])
        self.assertIsNone(live["disabled_at"])

    def test_disabling_twice_is_refused_rather_than_silently_repeated(self):
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        observability.set_check_enabled(self._tenant_pool, tenant_id, check["check_id"],
                                        enabled=False, actor_id=ACTOR,
                                        correlation_id=self.correlate())
        with self.assertRaises(NotFound):
            observability.set_check_enabled(self._tenant_pool, tenant_id, check["check_id"],
                                            enabled=False, actor_id=ACTOR,
                                            correlation_id=self.correlate())


class CapacityTests(ObservabilityTestCase):
    def forecast(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {"resource": "database_connections", "horizon_days": 90,
                      "current_value": 120.0, "projected_value": 430.0,
                      "basis": "linear fit over 60 days of peak concurrency"}
        body.update(kwargs)
        return observability.record_forecast(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def test_headroom_is_derived_from_the_limit_not_accepted_from_the_caller(self):
        tenant_id = self.tenant()
        recorded = self.forecast(tenant_id, projected_value=800.0, limit_value=1000.0)
        self.assertEqual(recorded["headroom_bp"], 2000)

    def test_a_forecast_with_no_limit_computes_no_headroom_and_alerts_nobody(self):
        tenant_id = self.tenant()
        recorded = self.forecast(tenant_id)
        self.assertIsNone(recorded["headroom_bp"])
        self.assertEqual(self.outbox(tenant_id, "capacity.threshold.reached"), [])

    def test_thin_headroom_publishes(self):
        tenant_id = self.tenant()
        self.forecast(tenant_id, projected_value=950.0, limit_value=1000.0)
        published = self.outbox(tenant_id, "capacity.threshold.reached")
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["headroom_bp"], 500)

    def test_ample_headroom_publishes_nothing(self):
        tenant_id = self.tenant()
        self.forecast(tenant_id, projected_value=100.0, limit_value=1000.0)
        self.assertEqual(self.outbox(tenant_id, "capacity.threshold.reached"), [])

    def test_a_projection_past_the_limit_is_recorded_with_negative_headroom(self):
        """Refusing it would mean the one forecast somebody most needs to record cannot be."""
        tenant_id = self.tenant()
        recorded = self.forecast(tenant_id, projected_value=1500.0, limit_value=1000.0)
        self.assertLess(recorded["headroom_bp"], 0)


class CostAndBudgetTests(ObservabilityTestCase):
    def cost(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {"period_start": date(2026, 11, 1), "period_end": date(2026, 11, 30),
                      "dimension": "ai_model", "dimension_value": "claude-opus",
                      "currency": "EUR", "amount_minor": 412000,
                      "source": "vendor statement 2026-11"}
        body.update(kwargs)
        return observability.allocate_cost(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def budget(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {"budget_key": f"b{uuid.uuid4().hex[:8]}", "dimension": "ai_model",
                      "dimension_value": "claude-opus", "currency": "EUR",
                      "amount_minor": 500000, "period": "monthly", "owner": "platform-ops"}
        body.update(kwargs)
        return observability.set_budget(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def test_a_correction_is_a_later_row_with_the_opposite_sign(self):
        tenant_id = self.tenant()
        original = self.cost(tenant_id)
        self.cost(tenant_id, amount_minor=-12000, source="correction to statement 2026-11",
                  corrects_cost_record_id=original["cost_record_id"])
        summary = observability.cost_summary(self._tenant_pool, tenant_id,
                                             period_start=date(2026, 11, 1),
                                             period_end=date(2026, 11, 30))
        self.assertEqual(summary["currencies"][0]["total_minor"], 400000)

    def test_currencies_are_summed_apart(self):
        tenant_id = self.tenant()
        self.cost(tenant_id, currency="EUR", amount_minor=100)
        self.cost(tenant_id, currency="USD", amount_minor=200)
        summary = observability.cost_summary(self._tenant_pool, tenant_id,
                                             period_start=date(2026, 11, 1),
                                             period_end=date(2026, 11, 30))
        totals = {line["currency"]: line["total_minor"] for line in summary["currencies"]}
        self.assertEqual(totals, {"EUR": 100, "USD": 200})

    def test_a_float_amount_is_refused_rather_than_truncated(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            self.cost(tenant_id, amount_minor=412000.5)

    def test_correcting_a_record_that_does_not_exist_is_not_found(self):
        tenant_id = self.tenant()
        with self.assertRaises(NotFound):
            self.cost(tenant_id, amount_minor=-1,
                      corrects_cost_record_id=str(uuid.uuid4()))

    def test_a_burn_alert_fires_once_per_period_and_threshold(self):
        """A sweep running twice in an hour must not raise the same alert twice: an alert
        channel that repeats itself is one people mute."""
        tenant_id = self.tenant()
        budget = self.budget(tenant_id)
        self.cost(tenant_id, amount_minor=450000)
        first = observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 11, 1), correlation_id=self.correlate(),
        )
        self.assertEqual(first["alerts_raised"], [8000])
        second = observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 11, 1), correlation_id=self.correlate(),
        )
        self.assertEqual(second["alerts_raised"], [])
        self.assertEqual(len(self.outbox(tenant_id, "cost.anomaly.detected")), 1)

    def test_a_budget_only_counts_costs_in_its_own_dimension(self):
        tenant_id = self.tenant()
        budget = self.budget(tenant_id)
        self.cost(tenant_id, amount_minor=450000, dimension="storage",
                  dimension_value="objects")
        burn = observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 11, 1), correlation_id=self.correlate(),
        )
        self.assertEqual(burn["spent_minor"], 0)
        self.assertEqual(burn["alerts_raised"], [])

    def test_a_total_budget_counts_every_dimension(self):
        tenant_id = self.tenant()
        budget = self.budget(tenant_id, dimension="total", dimension_value=None)
        self.cost(tenant_id, amount_minor=300000, dimension="storage",
                  dimension_value="objects")
        self.cost(tenant_id, amount_minor=200000, dimension="ai_model",
                  dimension_value="claude-opus")
        burn = observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 11, 1), correlation_id=self.correlate(),
        )
        self.assertEqual(burn["spent_minor"], 500000)

    def test_an_alert_snapshots_the_owner_that_was_told(self):
        """Retiring the budget afterwards must not rewrite why somebody was alerted."""
        tenant_id = self.tenant()
        budget = self.budget(tenant_id, owner="platform-ops")
        self.cost(tenant_id, amount_minor=450000)
        observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 11, 1), correlation_id=self.correlate(),
        )
        observability.retire_budget(self._tenant_pool, tenant_id, budget["budget_id"],
                                    actor_id=ACTOR, correlation_id=self.correlate())
        alerts = observability.list_budget_alerts(self._tenant_pool, tenant_id)
        self.assertEqual(alerts[0]["owner"], "platform-ops")
        self.assertEqual(alerts[0]["budget_minor"], 500000)

    def test_a_retired_budget_is_not_evaluated(self):
        tenant_id = self.tenant()
        budget = self.budget(tenant_id)
        observability.retire_budget(self._tenant_pool, tenant_id, budget["budget_id"],
                                    actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            observability.evaluate_budget(
                self._tenant_pool, tenant_id, budget["budget_id"],
                period_start=date(2026, 11, 1), correlation_id=self.correlate(),
            )

    def test_margin_is_net_of_tax_and_of_the_partner_share(self):
        """Counting either as revenue overstates the margin in the direction nobody checks."""
        tenant_id = self.tenant()
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            conn.execute(
                "INSERT INTO plt01.bil_subscriptions"
                " (tenant_id, subscription_id, plan_code, plan_version, terms, status,"
                "  currency, billing_interval, period_start, period_end, started_on)"
                " VALUES (%s, %s, 'core', 1, '{}'::jsonb, 'active', 'EUR', 'monthly',"
                "  DATE '2026-11-01', DATE '2026-12-01', DATE '2026-11-01')",
                (tenant_id, "00000000-0000-4000-8000-00000000c0de"),
            )
            conn.execute(
                "INSERT INTO plt01.bil_invoices"
                " (tenant_id, invoice_number, subscription_id, currency, period_start,"
                "  period_end, subtotal_minor, tax_minor, total_minor, partner_code,"
                "  revenue_share_minor, correlation_id)"
                " VALUES (%s, 'INV-1', %s, 'EUR', DATE '2026-11-01', DATE '2026-11-30',"
                "  1000000, 240000, 1240000, 'gymchain', 100000, %s)",
                (tenant_id, "00000000-0000-4000-8000-00000000c0de", ACTOR),
            )
        self.cost(tenant_id, amount_minor=450000)
        margin = observability.gross_margin(self._tenant_pool, tenant_id,
                                            period_start=date(2026, 11, 1),
                                            period_end=date(2026, 11, 30))
        line = margin["lines"][0]
        self.assertEqual(line["revenue_minor"], 900000)
        self.assertEqual(line["cost_minor"], 450000)
        self.assertEqual(line["margin_bp"], 5000)

    def test_a_currency_with_cost_and_no_revenue_is_named_rather_than_dropped(self):
        """A cost that silently does not appear is the FinOps failure worth guarding against."""
        tenant_id = self.tenant()
        self.cost(tenant_id, currency="ISK", amount_minor=9000)
        margin = observability.gross_margin(self._tenant_pool, tenant_id,
                                            period_start=date(2026, 11, 1),
                                            period_end=date(2026, 11, 30))
        line = next(line for line in margin["lines"] if line["currency"] == "ISK")
        self.assertEqual(line["cost_minor"], 9000)
        self.assertIsNone(line["margin_bp"])


class ReviewRegressionTests(ObservabilityTestCase):
    """One per blocking finding from the MOD-011 review round.

    Named for what an attacker or an unlucky operator would do, not for the fix: a test named
    after a fix passes once the fix is there and stops meaning anything afterwards.
    """

    def cost(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {"period_start": date(2026, 11, 1), "period_end": date(2026, 11, 30),
                      "dimension": "ai_model", "dimension_value": "claude-opus",
                      "currency": "EUR", "amount_minor": 100000, "source": "statement"}
        body.update(kwargs)
        return observability.allocate_cost(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def budget(self, tenant_id: str, **kwargs: object) -> dict:
        body: dict = {"budget_key": f"b{uuid.uuid4().hex[:8]}", "dimension": "ai_model",
                      "dimension_value": "claude-opus", "currency": "EUR",
                      "amount_minor": 1000000, "period": "monthly", "owner": "platform-ops"}
        body.update(kwargs)
        return observability.set_budget(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def test_a_month_s_burn_counts_that_month_and_not_the_rest_of_the_year(self):
        """The spend query had a lower bound and no upper one, and took the date from the
        caller. A January budget 45% consumed reported 143% -- the whole year -- raised every
        threshold, and wrote the fabricated figure into insert-only alert rows."""
        tenant_id = self.tenant()
        budget = self.budget(tenant_id)
        for month, amount in ((1, 450000), (2, 480000), (12, 500000)):
            end = date(2026, month, 28)
            self.cost(tenant_id, period_start=date(2026, month, 1), period_end=end,
                      amount_minor=amount)
        burn = observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 1, 1), correlation_id=self.correlate(),
        )
        self.assertEqual(burn["spent_minor"], 450000)
        self.assertEqual(burn["consumed_bp"], 4500)
        self.assertFalse(burn["over"])
        self.assertEqual(burn["alerts_raised"], [])

    def test_a_sweep_passing_an_unaligned_date_is_refused_rather_than_re_alerting(self):
        """A loop passing today's date would otherwise raise every threshold again on every
        run, each time with a bigger number, because the lower bound moved while the sum grew."""
        tenant_id = self.tenant()
        budget = self.budget(tenant_id)
        with self.assertRaises(InvalidRequest):
            observability.evaluate_budget(
                self._tenant_pool, tenant_id, budget["budget_id"],
                period_start=date(2026, 11, 14), correlation_id=self.correlate(),
            )

    def test_a_quarterly_budget_counts_its_quarter(self):
        tenant_id = self.tenant()
        budget = self.budget(tenant_id, period="quarterly")
        self.cost(tenant_id, period_start=date(2026, 11, 1), period_end=date(2026, 11, 30),
                  amount_minor=300000)
        self.cost(tenant_id, period_start=date(2027, 2, 1), period_end=date(2027, 2, 28),
                  amount_minor=900000)
        burn = observability.evaluate_budget(
            self._tenant_pool, tenant_id, budget["budget_id"],
            period_start=date(2026, 10, 1), correlation_id=self.correlate(),
        )
        self.assertEqual(burn["spent_minor"], 300000)

    def test_a_credit_note_reduces_the_margin_it_credits(self):
        """MOD-015 has no invoice edit and no void -- a correction is a credit note -- so a
        margin blind to that table is blind to the only way revenue goes down."""
        tenant_id = self.tenant()
        self.invoice(tenant_id, subtotal=1000000, partner_share=100000)
        self.cost(tenant_id, amount_minor=450000)
        before = observability.gross_margin(self._tenant_pool, tenant_id,
                                            period_start=date(2026, 11, 1),
                                            period_end=date(2026, 11, 30))
        self.assertEqual(before["lines"][0]["margin_bp"], 5000)
        self.credit(tenant_id, amount_minor=900000)
        after = observability.gross_margin(self._tenant_pool, tenant_id,
                                           period_start=date(2026, 11, 1),
                                           period_end=date(2026, 11, 30))
        self.assertEqual(after["lines"][0]["revenue_minor"], 0)
        self.assertIsNone(after["lines"][0]["margin_bp"])

    def test_one_dead_consumer_is_not_hidden_behind_nine_healthy_ones(self):
        """An objective applied no dimension filter, so a consumer at zero never alerted."""
        tenant_id = self.tenant()
        objective = self.objective(tenant_id, metric_key="events.delivery_success",
                                   window_hours=1, dimensions={"consumer": "webhook"})
        obs_metrics.observe(self._tenant_pool, tenant_id,
                            metric_key="events.delivery_success", total=10000.0,
                            observations=10000, dimensions={"consumer": "projector"}, at=HOUR)
        obs_metrics.observe(self._tenant_pool, tenant_id,
                            metric_key="events.delivery_success", total=0.0, observations=5,
                            dimensions={"consumer": "webhook"}, at=HOUR)
        verdict = observability.evaluate_objective(
            self._tenant_pool, tenant_id, objective["objective_id"],
            correlation_id=self.correlate(), until=HOUR,
        )
        self.assertFalse(verdict["met"])
        self.assertEqual(verdict["observed"], 0.0)
        published = self.outbox(tenant_id, "performance_budget.exceeded")
        self.assertEqual(published[0]["dimensions"], {"consumer": "webhook"})

    def test_a_ratio_cannot_be_stored_as_a_sum(self):
        """`aggregate_as=sum` on a ratio reads as a 99.9% availability SLO and is met during a
        total outage: one success in ten thousand attempts sums to 1.0."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest) as caught:
            self.objective(tenant_id, aggregate_as="sum")
        self.assertIn("cannot be read as", str(caught.exception.code))

    def test_an_objective_names_every_dimension_its_metric_declares(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            self.objective(tenant_id, dimensions={})

    def test_a_disabled_check_does_not_report(self):
        """Disabling a probe has to stop the paging that disabling it is for."""
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        observability.set_check_enabled(self._tenant_pool, tenant_id, check["check_id"],
                                        enabled=False, actor_id=ACTOR,
                                        correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            observability.record_result(
                self._tenant_pool, tenant_id, check_id=check["check_id"], outcome="failed",
                duration_ms=1, detail="still probing", observed_at=HOUR, actor_id=ACTOR,
                correlation_id=self.correlate(),
            )
        self.assertEqual(self.outbox(tenant_id, "synthetic_check.failed"), [])

    def test_a_probe_result_records_who_submitted_it(self):
        """The row is insert-only and MOD-008 does not audit an allowed action, so this column
        is the only possible answer to who wrote a `passed` nobody can account for."""
        tenant_id = self.tenant()
        check = self.check(tenant_id)
        observability.record_result(
            self._tenant_pool, tenant_id, check_id=check["check_id"], outcome="passed",
            duration_ms=10, observed_at=HOUR, actor_id=ACTOR,
            correlation_id=self.correlate(),
        )
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT recorded_by, correlation_id FROM plt01.ops_synthetic_results"
            ).fetchone()
        assert row is not None
        self.assertEqual(str(row[0]), ACTOR)
        self.assertIsNotNone(row[1])

    def test_a_measurement_cannot_be_placed_in_an_hour_that_has_not_happened(self):
        """`observe_in` accumulates, so a future bucket holds an objective green through an
        outage still to come -- under a routine, AAL-1 permission."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                total=1.0, dimensions={"category": "finance"},
                                at=HOUR + timedelta(days=2))

    def test_a_naive_timestamp_is_refused_rather_than_read_as_local_time(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            obs_metrics.observe(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                total=1.0, dimensions={"category": "finance"},
                                at=HOUR.replace(tzinfo=None))

    def test_reading_up_to_a_future_moment_is_allowed(self):
        """The bound is on writes. "The last 24 hours" is the ordinary read."""
        tenant_id = self.tenant()
        read = obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                                  window_hours=24, until=HOUR + timedelta(days=1))
        self.assertEqual(read["buckets"], [])

    def test_a_window_of_a_billion_hours_is_refused_and_not_an_overflow(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            obs_metrics.series(self._tenant_pool, tenant_id, metric_key="authz.denials",
                               window_hours=10 ** 9)

    def test_a_correction_has_to_match_what_it_corrects(self):
        tenant_id = self.tenant()
        original = self.cost(tenant_id)
        for wrong in ({"currency": "USD", "amount_minor": -50000},
                      {"dimension_value": "claude-haiku", "amount_minor": -50000},
                      # The same sign as the thing it claims to correct.
                      {"amount_minor": 50000}):
            with self.assertRaises(InvalidRequest):
                self.cost(tenant_id,
                          corrects_cost_record_id=original["cost_record_id"], **wrong)
        self.cost(tenant_id, amount_minor=-50000,
                  corrects_cost_record_id=original["cost_record_id"])

    def test_a_forecast_far_past_its_limit_is_recorded_and_not_an_overflow(self):
        tenant_id = self.tenant()
        recorded = observability.record_forecast(
            self._tenant_pool, tenant_id, resource="cpu", horizon_days=30,
            current_value=1.0, projected_value=1e9, limit_value=1000.0,
            basis="runaway projection", actor_id=ACTOR, correlation_id=self.correlate(),
        )
        self.assertEqual(recorded["headroom_bp"], -1000000)

    def test_a_non_finite_number_never_reaches_the_arithmetic(self):
        tenant_id = self.tenant()
        for bad in ({"projected_value": float("nan")}, {"limit_value": float("inf")},
                    {"current_value": float("inf")}):
            body = {"resource": "cpu", "horizon_days": 30, "current_value": 1.0,
                    "projected_value": 2.0, "basis": "b", **bad}
            with self.assertRaises(InvalidRequest):
                observability.record_forecast(
                    self._tenant_pool, tenant_id, actor_id=ACTOR,
                    correlation_id=self.correlate(), **body,
                )

    def test_the_limit_a_headroom_was_derived_from_is_kept(self):
        """A derived number whose input is thrown away cannot be re-checked from the row."""
        tenant_id = self.tenant()
        observability.record_forecast(
            self._tenant_pool, tenant_id, resource="cpu", horizon_days=30,
            current_value=1.0, projected_value=800.0, limit_value=1000.0, basis="b",
            actor_id=ACTOR, correlation_id=self.correlate(),
        )
        listed = observability.list_forecasts(self._tenant_pool, tenant_id)[0]
        self.assertEqual(listed["limit_value"], 1000.0)
        self.assertEqual(listed["headroom_bp"], 2000)


if __name__ == "__main__":
    unittest.main()
