"""MOD-006 PLT-03 billing API against a real PostgreSQL with row-level security in force.

The arithmetic is covered by `test_billing_domain.py`, which needs no database. What is checked
here is what only the database can answer: that an issued invoice cannot be rewritten, that a
replayed usage key does not double-count, that a plan change refuses to shrink an entitlement
silently, and that one tenant's ledger is invisible to another.
"""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_platform_pool, make_tenant_pool
from app.main import create_app

DSN = os.environ.get("VEYRO_DATABASE_URL", "")


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class BillingApiTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls._tenant_pool = make_tenant_pool(DSN)
        cls._platform_pool = make_platform_pool(DSN)
        app = create_app(
            Settings(environment="local", release="test", database_url=DSN),
            tenant_pool=cls._tenant_pool,
            platform_pool=cls._platform_pool,
        )
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        cls._tenant_pool.close()
        cls._platform_pool.close()

    # ------------------------------------------------------------------ helpers

    def tenant(self) -> str:
        response = self.client.post("/platform/tenants", json={
            "external_key": f"bil-{uuid.uuid4()}", "display_name": "Billing Gym",
            "region": "eu-west", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["tenant_id"])

    def headers(self, tenant_id: str) -> dict[str, str]:
        return {"X-Veyro-Tenant": tenant_id}

    def plan(self, *, price: int = 29900, trial_days: int = 0, entitlements=None, prices=None,
             code: str | None = None, publish: bool = True) -> str:
        plan_code = code or f"plan-{uuid.uuid4().hex[:12]}"
        created = self.client.post("/platform/plans", json={
            "plan_code": plan_code, "plan_version": 1, "edition": "growth", "currency": "EUR",
            "region": "eu-west", "billing_interval": "monthly", "base_price_minor": price,
            "trial_days": trial_days,
            "entitlements": entitlements if entitlements is not None else
                            [{"feature_code": "locations", "limit_value": 5}],
            "prices": prices or [],
        })
        self.assertEqual(created.status_code, 201, created.text)
        if publish:
            published = self.client.post(f"/platform/plans/{plan_code}/1/status",
                                         json={"status": "published"})
            self.assertEqual(published.status_code, 200, published.text)
        return plan_code

    def start(self, tenant_id: str, plan_code: str, **overrides):
        body = {"plan_code": plan_code, "actor_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4()), "start_on": date(2026, 11, 1).isoformat()}
        body.update(overrides)
        return self.client.post("/subscription", json=body, headers=self.headers(tenant_id))

    def subscribed(self, **plan_kwargs) -> tuple[str, str]:
        tenant_id = self.tenant()
        plan_code = self.plan(**plan_kwargs)
        response = self.start(tenant_id, plan_code)
        self.assertEqual(response.status_code, 201, response.text)
        return tenant_id, plan_code

    # ------------------------------------------------------------------ catalogue

    def test_a_plan_version_is_unique_and_must_be_published_before_sale(self):
        plan_code = self.plan(publish=False)
        again = self.client.post("/platform/plans", json={
            "plan_code": plan_code, "plan_version": 1, "edition": "growth", "currency": "EUR",
            "region": "eu-west", "billing_interval": "monthly", "base_price_minor": 100,
        })
        self.assertEqual(again.status_code, 409)

        tenant_id = self.tenant()
        # Asking for the plan by code finds no published version at all...
        unversioned = self.start(tenant_id, plan_code)
        self.assertEqual(unversioned.status_code, 404)
        self.assertEqual(unversioned.json()["error"], "no_published_plan_version")
        # ...while naming the draft version explicitly finds it and refuses to sell it.
        explicit = self.start(tenant_id, plan_code, plan_version=1)
        self.assertEqual(explicit.status_code, 409)
        self.assertEqual(explicit.json()["error"], "plan_not_published")

    def test_a_plan_cannot_be_published_twice_or_retired_from_draft(self):
        plan_code = self.plan(publish=False)
        self.assertEqual(
            self.client.post(f"/platform/plans/{plan_code}/1/status",
                             json={"status": "retired"}).status_code, 409)
        self.client.post(f"/platform/plans/{plan_code}/1/status", json={"status": "published"})
        self.assertEqual(
            self.client.post(f"/platform/plans/{plan_code}/1/status",
                             json={"status": "published"}).status_code, 409)

    def test_a_negative_price_is_refused(self):
        response = self.client.post("/platform/plans", json={
            "plan_code": f"plan-{uuid.uuid4().hex[:12]}", "plan_version": 1, "edition": "x",
            "currency": "EUR", "region": "eu-west", "billing_interval": "monthly",
            "base_price_minor": -1,
        })
        self.assertEqual(response.status_code, 422)

    def test_a_contract_interval_needs_a_term(self):
        response = self.client.post("/platform/plans", json={
            "plan_code": f"plan-{uuid.uuid4().hex[:12]}", "plan_version": 1, "edition": "x",
            "currency": "EUR", "region": "eu-west", "billing_interval": "contract",
            "base_price_minor": 100,
        })
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------ subscriptions

    def test_starting_a_subscription_snapshots_the_plan_and_grants_entitlements(self):
        tenant_id, plan_code = self.subscribed()
        live = self.client.get("/subscription", headers=self.headers(tenant_id)).json()
        self.assertEqual((live["plan_code"], live["status"], live["base_price_minor"]),
                         (plan_code, "active", 29900))
        entitlements = self.client.get("/entitlements", headers=self.headers(tenant_id)).json()
        self.assertEqual([(e["feature_code"], e["limit_value"]) for e in entitlements],
                         [("locations", 5)])

    def test_a_trial_plan_starts_trialing_and_is_not_billable(self):
        tenant_id, _ = self.subscribed(trial_days=14)
        live = self.client.get("/subscription", headers=self.headers(tenant_id)).json()
        self.assertEqual(live["status"], "trialing")
        self.assertEqual(live["trial_ends_on"], "2026-11-15")
        invoice = self.client.post("/invoices", json={
            "actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())},
            headers=self.headers(tenant_id))
        self.assertEqual(invoice.status_code, 409)
        self.assertEqual(invoice.json()["error"], "not_billable_in_this_status")

    def test_a_tenant_cannot_hold_two_live_subscriptions(self):
        tenant_id, _ = self.subscribed()
        second = self.start(tenant_id, self.plan())
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "subscription_already_live")

    def test_the_catalogue_can_move_without_changing_what_was_sold(self):
        """The subscription keeps its snapshot; a later plan version is a different product."""
        tenant_id, plan_code = self.subscribed()
        self.client.post("/platform/plans", json={
            "plan_code": plan_code, "plan_version": 2, "edition": "growth", "currency": "EUR",
            "region": "eu-west", "billing_interval": "monthly", "base_price_minor": 99900,
        })
        self.client.post(f"/platform/plans/{plan_code}/2/status", json={"status": "published"})
        live = self.client.get("/subscription", headers=self.headers(tenant_id)).json()
        self.assertEqual((live["plan_version"], live["base_price_minor"]), (1, 29900))

    # ------------------------------------------------------------------ lifecycle

    def transition(self, tenant_id: str, command: str, **overrides):
        body = {"command": command, "actor_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4())}
        body.update(overrides)
        return self.client.post("/subscription/transition", json=body,
                                headers=self.headers(tenant_id))

    def test_the_dunning_path_runs_and_a_suspended_tenant_can_be_reactivated(self):
        tenant_id, _ = self.subscribed()
        self.assertEqual(self.transition(tenant_id, "payment_failed").json()["status"],
                         "past_due")
        self.assertEqual(self.transition(tenant_id, "grace_expired").json()["status"],
                         "suspended")
        self.assertEqual(self.transition(tenant_id, "reactivate").json()["status"], "active")

    def test_a_recovered_payment_returns_to_active_without_suspension(self):
        tenant_id, _ = self.subscribed()
        self.transition(tenant_id, "payment_failed")
        self.assertEqual(self.transition(tenant_id, "payment_recovered").json()["status"],
                         "active")

    def test_an_illegal_transition_is_refused(self):
        tenant_id, _ = self.subscribed()
        refused = self.transition(tenant_id, "reactivate")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["error"], "illegal_transition")

    def test_an_unknown_command_is_a_422(self):
        tenant_id, _ = self.subscribed()
        self.assertEqual(self.transition(tenant_id, "refund").status_code, 422)

    def test_a_cancelled_subscription_leaves_no_live_one(self):
        tenant_id, _ = self.subscribed()
        self.assertEqual(self.transition(tenant_id, "cancel").json()["status"], "cancelled")
        self.assertEqual(
            self.client.get("/subscription", headers=self.headers(tenant_id)).status_code, 404)
        self.assertEqual(self.start(tenant_id, self.plan()).status_code, 201,
                         "a cancelled subscription frees the tenant to start a new one")

    def test_expected_version_refuses_a_stale_transition(self):
        tenant_id, _ = self.subscribed()
        stale = self.transition(tenant_id, "payment_failed", expected_version=99)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"], "version_mismatch")

    def test_the_history_records_every_move(self):
        tenant_id, _ = self.subscribed()
        self.transition(tenant_id, "payment_failed")
        self.transition(tenant_id, "payment_recovered")
        history = self.client.get("/subscription/history",
                                  headers=self.headers(tenant_id)).json()
        self.assertEqual([row["change_kind"] for row in history], ["start", "status", "status"])
        self.assertEqual([row["to_status"] for row in history],
                         ["active", "past_due", "active"])

    # ------------------------------------------------------------------ plan changes

    def change(self, tenant_id: str, plan_code: str, **overrides):
        body = {"plan_code": plan_code, "actor_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4()),
                "effective_on": date(2026, 11, 16).isoformat()}
        body.update(overrides)
        return self.client.post("/subscription/plan", json=body,
                                headers=self.headers(tenant_id))

    def test_an_upgrade_prorates_a_charge_and_a_downgrade_prorates_a_credit(self):
        tenant_id, _ = self.subscribed(price=2000)
        up = self.change(tenant_id, self.plan(price=6000))
        self.assertEqual(up.status_code, 200, up.text)
        self.assertEqual(up.json()["proration_minor"], 2000)

        down = self.change(tenant_id, self.plan(price=2000))
        self.assertEqual(down.json()["proration_minor"], -2000)

    def test_a_downgrade_that_would_breach_an_entitlement_is_refused_until_acknowledged(self):
        tenant_id, _ = self.subscribed(
            entitlements=[{"feature_code": "locations", "limit_value": 10}])
        smaller = self.plan(price=900,
                            entitlements=[{"feature_code": "locations", "limit_value": 3}])

        refused = self.change(tenant_id, smaller, in_use={"locations": 8})
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["error"],
                         "entitlement_reduction_requires_acknowledgement")

        accepted = self.change(tenant_id, smaller, in_use={"locations": 8},
                               acknowledge_reductions=True)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["acknowledged_breaches"],
                         [{"feature_code": "locations", "in_use": 8, "new_limit": 3}])

    def test_a_downgrade_within_the_new_limits_needs_no_acknowledgement(self):
        tenant_id, _ = self.subscribed(
            entitlements=[{"feature_code": "locations", "limit_value": 10}])
        smaller = self.plan(price=900,
                            entitlements=[{"feature_code": "locations", "limit_value": 3}])
        self.assertEqual(self.change(tenant_id, smaller, in_use={"locations": 2}).status_code,
                         200)

    def test_a_plan_change_moves_the_entitlement_limits(self):
        tenant_id, _ = self.subscribed(
            entitlements=[{"feature_code": "locations", "limit_value": 5}])
        bigger = self.plan(price=59900,
                           entitlements=[{"feature_code": "locations", "limit_value": 25}])
        self.change(tenant_id, bigger)
        entitlements = self.client.get("/entitlements", headers=self.headers(tenant_id)).json()
        self.assertEqual(entitlements[0]["limit_value"], 25)

    def test_moving_to_the_same_plan_is_refused(self):
        tenant_id, plan_code = self.subscribed()
        response = self.change(tenant_id, plan_code)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "already_on_this_plan")

    # ------------------------------------------------------------------ entitlements

    def test_an_entitlement_check_answers_within_over_and_unknown(self):
        tenant_id, _ = self.subscribed(
            entitlements=[{"feature_code": "locations", "limit_value": 5}])
        head = self.headers(tenant_id)

        def check(feature, quantity):
            return self.client.get(f"/entitlements/{feature}/check",
                                   params={"quantity": quantity}, headers=head).json()

        self.assertTrue(check("locations", 5)["permitted"])
        self.assertFalse(check("locations", 6)["permitted"])
        self.assertEqual(check("white_label", 1)["reason"], "not_entitled")

    def test_a_granted_entitlement_overrides_the_plan_and_is_marked_as_a_grant(self):
        tenant_id, _ = self.subscribed(
            entitlements=[{"feature_code": "locations", "limit_value": 5}])
        head = self.headers(tenant_id)
        self.client.post("/entitlements", json={"feature_code": "locations",
                                                "limit_value": 50}, headers=head)
        entitlements = self.client.get("/entitlements", headers=head).json()
        self.assertEqual((entitlements[0]["limit_value"], entitlements[0]["source"]),
                         (50, "grant"))

    def test_an_unlimited_grant_permits_anything(self):
        tenant_id, _ = self.subscribed()
        head = self.headers(tenant_id)
        self.client.post("/entitlements", json={"feature_code": "api", "unlimited": True},
                         headers=head)
        check = self.client.get("/entitlements/api/check", params={"quantity": 10_000_000},
                                headers=head).json()
        self.assertTrue(check["permitted"])

    def test_an_entitlement_needs_exactly_one_of_a_limit_or_unlimited(self):
        tenant_id, _ = self.subscribed()
        head = self.headers(tenant_id)
        for body in ({"feature_code": "api"},
                     {"feature_code": "api", "limit_value": 5, "unlimited": True}):
            self.assertEqual(
                self.client.post("/entitlements", json=body, headers=head).status_code, 422)

    # ------------------------------------------------------------------ metering

    def meter(self, tenant_id: str, code: str = "messaging.sms", aggregation: str = "sum"):
        return self.client.post("/meters", json={"meter_code": code, "unit": "message",
                                                 "aggregation": aggregation},
                                headers=self.headers(tenant_id))

    def record(self, tenant_id: str, quantity: int, *, key: str | None = None,
               occurred: datetime | None = None, code: str = "messaging.sms", corrects=None):
        body = {"meter_code": code, "quantity": quantity,
                "idempotency_key": key or str(uuid.uuid4()),
                "actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
                "occurred_at": (occurred or datetime(2026, 11, 5, tzinfo=UTC)).isoformat()}
        if corrects:
            body["corrects_record_id"] = corrects
        return self.client.post("/usage", json=body, headers=self.headers(tenant_id))

    def test_a_replayed_idempotency_key_does_not_double_count(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        first = self.record(tenant_id, 120, key="emitter-1")
        self.assertEqual(first.status_code, 201, first.text)
        self.assertTrue(first.json()["recorded"])

        replay = self.record(tenant_id, 120, key="emitter-1")
        self.assertFalse(replay.json()["recorded"])
        self.assertEqual(replay.json()["record_id"], first.json()["record_id"])

        summary = self.client.get("/usage/messaging.sms",
                                  headers=self.headers(tenant_id)).json()
        self.assertEqual(summary["used"], 120)

    def test_a_key_reused_for_a_different_quantity_keeps_the_stored_row(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        self.record(tenant_id, 100, key="same")
        replay = self.record(tenant_id, 999, key="same")
        self.assertEqual(replay.json()["quantity"], 100)

    def test_a_correction_lowers_the_total_and_an_uncorrecting_negative_is_refused(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        original = self.record(tenant_id, 500).json()["record_id"]
        self.assertEqual(self.record(tenant_id, -200).status_code, 422)
        fix = self.record(tenant_id, -200, corrects=original)
        self.assertEqual(fix.status_code, 201, fix.text)
        summary = self.client.get("/usage/messaging.sms",
                                  headers=self.headers(tenant_id)).json()
        self.assertEqual(summary["used"], 300)

    def test_a_late_event_lands_in_the_period_it_happened_in(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        self.record(tenant_id, 50, occurred=datetime(2026, 11, 30, 23, 0, tzinfo=UTC))
        self.record(tenant_id, 70, occurred=datetime(2026, 12, 2, tzinfo=UTC))
        summary = self.client.get("/usage/messaging.sms",
                                  headers=self.headers(tenant_id)).json()
        self.assertEqual(summary["used"], 50, "December usage is not in November's period")

    def test_a_quota_reports_remaining_then_overage(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        head = self.headers(tenant_id)
        self.client.post("/meters/messaging.sms/quota",
                         json={"period": "billing_period", "limit_quantity": 1000,
                               "overage_allowed": True}, headers=head)
        self.record(tenant_id, 400)
        before = self.client.get("/usage/messaging.sms", headers=head).json()
        self.assertEqual((before["remaining"], before["exceeded"]), (600, False))
        self.record(tenant_id, 900)
        after = self.client.get("/usage/messaging.sms", headers=head).json()
        self.assertEqual((after["remaining"], after["overage_quantity"], after["permitted"]),
                         (0, 300, True))

    def test_a_hard_stop_quota_stops_permitting(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        head = self.headers(tenant_id)
        self.client.post("/meters/messaging.sms/quota",
                         json={"period": "billing_period", "limit_quantity": 10,
                               "hard_stop": True}, headers=head)
        self.record(tenant_id, 11)
        self.assertFalse(self.client.get("/usage/messaging.sms", headers=head).json()["permitted"])

    def test_a_quota_cannot_both_bill_and_stop(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id)
        response = self.client.post(
            "/meters/messaging.sms/quota",
            json={"period": "billing_period", "limit_quantity": 10, "overage_allowed": True,
                  "hard_stop": True}, headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 422)

    def test_a_meter_code_is_unique_per_tenant(self):
        tenant_id, _ = self.subscribed()
        self.assertEqual(self.meter(tenant_id).status_code, 201)
        self.assertEqual(self.meter(tenant_id).status_code, 409)

    def test_a_max_meter_takes_the_peak(self):
        tenant_id, _ = self.subscribed()
        self.meter(tenant_id, code="staff.seats", aggregation="max")
        for quantity, day in ((4, 3), (9, 7), (6, 11)):
            self.record(tenant_id, quantity, code="staff.seats",
                        occurred=datetime(2026, 11, day, tzinfo=UTC))
        summary = self.client.get("/usage/staff.seats",
                                  headers=self.headers(tenant_id)).json()
        self.assertEqual(summary["used"], 9)

    # ------------------------------------------------------------------ invoices

    def invoice(self, tenant_id: str, **overrides):
        body = {"actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
        body.update(overrides)
        return self.client.post("/invoices", json=body, headers=self.headers(tenant_id))

    def test_an_invoice_carries_the_base_charge_and_balances(self):
        tenant_id, _ = self.subscribed()
        response = self.invoice(tenant_id, tax_rate_bp=2400)
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual((body["subtotal_minor"], body["tax_minor"], body["total_minor"]),
                         (29900, 7176, 37076))
        self.assertEqual(body["total_minor"], body["subtotal_minor"] + body["tax_minor"])
        self.assertEqual([line["kind"] for line in body["lines"]], ["base"])

    def test_issuing_rolls_the_period_forward_without_a_gap(self):
        tenant_id, _ = self.subscribed()
        first = self.invoice(tenant_id).json()
        live = self.client.get("/subscription", headers=self.headers(tenant_id)).json()
        self.assertEqual(live["period_start"], first["period_end"])
        second = self.invoice(tenant_id).json()
        self.assertEqual(second["period_start"], first["period_end"])
        self.assertNotEqual(second["invoice_number"], first["invoice_number"])

    def test_overage_is_billed_once_the_quota_is_passed(self):
        tenant_id, _ = self.subscribed(prices=[{
            "price_code": "sms-overage", "kind": "overage", "meter_code": "messaging.sms",
            "unit": "message", "unit_price_minor": 4, "included_quantity": 0,
        }])
        self.meter(tenant_id)
        head = self.headers(tenant_id)
        self.client.post("/meters/messaging.sms/quota",
                         json={"period": "billing_period", "limit_quantity": 1000,
                               "overage_allowed": True}, headers=head)
        self.record(tenant_id, 1250)
        body = self.invoice(tenant_id).json()
        overage = [line for line in body["lines"] if line["kind"] == "overage"]
        self.assertEqual(len(overage), 1)
        self.assertEqual((overage[0]["quantity"], overage[0]["amount_minor"]), (250, 1000))
        self.assertEqual(body["subtotal_minor"], 29900 + 1000)

    def test_a_warning_quota_bills_nothing(self):
        tenant_id, _ = self.subscribed(prices=[{
            "price_code": "sms-overage", "kind": "overage", "meter_code": "messaging.sms",
            "unit": "message", "unit_price_minor": 4,
        }])
        self.meter(tenant_id)
        self.client.post("/meters/messaging.sms/quota",
                         json={"period": "billing_period", "limit_quantity": 100},
                         headers=self.headers(tenant_id))
        self.record(tenant_id, 900)
        body = self.invoice(tenant_id).json()
        self.assertEqual([line["kind"] for line in body["lines"]], ["base"])

    def test_a_mid_period_upgrade_appears_as_a_proration_line(self):
        tenant_id, _ = self.subscribed(price=2000)
        self.change(tenant_id, self.plan(price=6000))
        body = self.invoice(tenant_id).json()
        prorations = [line for line in body["lines"] if line["kind"] == "proration"]
        self.assertEqual(len(prorations), 1)
        self.assertEqual(prorations[0]["amount_minor"], 2000)
        self.assertEqual(body["subtotal_minor"], 6000 + 2000)

    def test_a_downgrade_credit_is_a_negative_line_and_still_balances(self):
        tenant_id, _ = self.subscribed(price=6000)
        self.change(tenant_id, self.plan(price=2000))
        body = self.invoice(tenant_id).json()
        self.assertEqual(body["subtotal_minor"], 2000 - 2000)
        self.assertEqual(body["total_minor"], body["subtotal_minor"] + body["tax_minor"])

    def test_a_partner_subscription_records_the_revenue_share(self):
        tenant_id = self.tenant()
        plan_code = self.plan(price=10_000)
        self.start(tenant_id, plan_code, partner_code="reseller-a", revenue_share_bp=1500)
        body = self.invoice(tenant_id).json()
        self.assertEqual(body["revenue_share_minor"], 1500)

    def test_an_issued_invoice_reads_back_with_its_lines(self):
        tenant_id, _ = self.subscribed()
        invoice_id = self.invoice(tenant_id, tax_rate_bp=2400).json()["invoice_id"]
        body = self.client.get(f"/invoices/{invoice_id}",
                               headers=self.headers(tenant_id)).json()
        self.assertEqual(sum(line["amount_minor"] for line in body["lines"]),
                         body["subtotal_minor"])
        self.assertEqual(body["balance_minor"], body["total_minor"])

    def test_a_credit_note_reduces_the_balance_without_touching_the_invoice(self):
        tenant_id, _ = self.subscribed()
        issued = self.invoice(tenant_id).json()
        head = self.headers(tenant_id)
        credit = self.client.post(f"/invoices/{issued['invoice_id']}/credit-notes", json={
            "amount_minor": 900, "reason": "goodwill", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4())}, headers=head)
        self.assertEqual(credit.status_code, 201, credit.text)
        body = self.client.get(f"/invoices/{issued['invoice_id']}", headers=head).json()
        self.assertEqual(body["total_minor"], issued["total_minor"],
                         "the invoice itself is untouched")
        self.assertEqual((body["credited_minor"], body["balance_minor"]),
                         (900, issued["total_minor"] - 900))

    def test_credits_cannot_exceed_the_invoice(self):
        tenant_id, _ = self.subscribed(price=1000)
        issued = self.invoice(tenant_id).json()
        head = self.headers(tenant_id)

        def credit(amount):
            return self.client.post(f"/invoices/{issued['invoice_id']}/credit-notes", json={
                "amount_minor": amount, "reason": "x", "actor_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4())}, headers=head)

        self.assertEqual(credit(600).status_code, 201)
        over = credit(600)
        self.assertEqual(over.status_code, 409)
        self.assertEqual(over.json()["error"], "credit_exceeds_invoice")
        self.assertEqual(credit(400).status_code, 201)

    def test_a_credit_needs_a_positive_amount_and_a_reason(self):
        tenant_id, _ = self.subscribed()
        issued = self.invoice(tenant_id).json()
        head = self.headers(tenant_id)
        for body in ({"amount_minor": 0, "reason": "x"}, {"amount_minor": 10, "reason": "  "}):
            response = self.client.post(
                f"/invoices/{issued['invoice_id']}/credit-notes",
                json={**body, "actor_id": str(uuid.uuid4()),
                      "correlation_id": str(uuid.uuid4())}, headers=head)
            self.assertEqual(response.status_code, 422, body)

    # ------------------------------------------------------------------ isolation

    def test_one_tenants_ledger_is_invisible_to_another(self):
        owner, _ = self.subscribed()
        self.invoice(owner)
        other = self.tenant()
        self.assertEqual(
            self.client.get("/invoices", headers=self.headers(other)).json(), [])
        self.assertEqual(
            self.client.get("/subscription", headers=self.headers(other)).status_code, 404)

    def test_another_tenants_invoice_cannot_be_read_or_credited(self):
        owner, _ = self.subscribed()
        invoice_id = self.invoice(owner).json()["invoice_id"]
        other = self.tenant()
        head = self.headers(other)
        self.assertEqual(self.client.get(f"/invoices/{invoice_id}", headers=head).status_code,
                         404)
        credited = self.client.post(f"/invoices/{invoice_id}/credit-notes", json={
            "amount_minor": 1, "reason": "theft", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4())}, headers=head)
        self.assertEqual(credited.status_code, 404)

    def test_usage_cannot_be_recorded_against_another_tenants_meter(self):
        owner, _ = self.subscribed()
        self.meter(owner)
        other = self.tenant()
        self.assertEqual(self.record(other, 10).status_code, 404)

    def test_two_tenants_keep_separate_totals_on_the_same_meter_code(self):
        first, _ = self.subscribed()
        second, _ = self.subscribed()
        for tenant_id, quantity in ((first, 100), (second, 7)):
            self.meter(tenant_id)
            self.record(tenant_id, quantity)
        for tenant_id, expected in ((first, 100), (second, 7)):
            summary = self.client.get("/usage/messaging.sms",
                                      headers=self.headers(tenant_id)).json()
            self.assertEqual(summary["used"], expected)

    def test_a_request_with_no_tenant_header_is_refused(self):
        for path in ("/subscription", "/entitlements", "/invoices"):
            self.assertEqual(self.client.get(path).status_code, 422, path)

    def test_a_long_running_subscription_invoices_every_period_without_drift(self):
        tenant_id, _ = self.subscribed(price=1000)
        periods = []
        for _ in range(6):
            issued = self.invoice(tenant_id).json()
            periods.append((issued["period_start"], issued["period_end"]))
        for (_, end), (start, _) in zip(periods, periods[1:], strict=False):
            self.assertEqual(end, start, "periods must abut, leaving nothing unbilled")
        first_span = date.fromisoformat(periods[0][1]) - date.fromisoformat(periods[0][0])
        self.assertEqual(first_span, timedelta(days=30))


if __name__ == "__main__":
    unittest.main()
