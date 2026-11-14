"""MOD-011 REL-02 over HTTP: the surface, the step-up classes and the rate limiter.

The service suite proves the behaviour. This one proves the things only the HTTP layer decides:
which permission each route charges, that a malformed id is a 422 rather than a 500, and that
the limiter wired into the request path actually refuses.
"""

from __future__ import annotations

import unittest
import uuid

from app.observability import ratelimit
from tests.support import GatedApiTestCase


class ObservabilityApiTests(GatedApiTestCase):
    def correlation(self) -> dict[str, str]:
        return {"correlation_id": str(uuid.uuid4())}

    def objective_body(self, **kwargs: object) -> dict:
        body: dict = {"objective_key": f"k{uuid.uuid4().hex[:8]}", "kind": "slo",
                      "metric_key": "ops.synthetic_success", "comparison": "at_least",
                      "threshold": 0.99, "window_hours": 24, "aggregate_as": "mean",
                      "owner": "platform-ops", "runbook_ref": "RB-REL-02",
                      "dimensions": {"check_key": "login"}, **self.correlation()}
        body.update(kwargs)
        return body

    def test_an_objective_is_defined_read_and_retired(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        created = self.client.post("/ops/objectives", headers=head,
                                   json=self.objective_body())
        self.assertEqual(created.status_code, 201, created.text)
        objective_id = created.json()["objective_id"]
        listed = self.client.get("/ops/objectives", headers=head)
        self.assertEqual([o["objective_id"] for o in listed.json()], [objective_id])
        retired = self.client.post(f"/ops/objectives/{objective_id}/retire", headers=head,
                                   json=self.correlation())
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(self.client.get("/ops/objectives", headers=head).json(), [])

    def test_a_percentile_objective_is_a_422_with_a_reason(self):
        tenant_id = self.tenant()
        response = self.client.post("/ops/objectives", headers=self.headers(tenant_id),
                                    json=self.objective_body(aggregate_as="p95"))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("histogram", response.json()["error"])

    def test_a_malformed_id_is_a_422_and_not_a_database_exception(self):
        """MOD-009's finding: eight of eight id-bearing routes answered 500 with a psycopg
        error until every id was shape-checked at the boundary."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        for path, body in (
            ("/ops/objectives/not-a-uuid/retire", self.correlation()),
            ("/ops/objectives/not-a-uuid/evaluate", self.correlation()),
            ("/ops/synthetic-checks/not-a-uuid/enabled",
             {"enabled": False, **self.correlation()}),
            ("/ops/synthetic-checks/not-a-uuid/results",
             {"outcome": "passed", "duration_ms": 1, **self.correlation()}),
            ("/ops/budgets/not-a-uuid/retire", self.correlation()),
            ("/ops/budgets/not-a-uuid/burn",
             {"period_start": "2026-11-01", **self.correlation()}),
        ):
            response = self.client.post(path, headers=head, json=body)
            self.assertEqual(response.status_code, 422, f"{path}: {response.text}")
        self.assertEqual(
            self.client.get("/ops/synthetic-checks/not-a-uuid/results",
                            headers=head).status_code, 422)

    def test_an_unknown_metric_key_is_refused_rather_than_returning_an_empty_series(self):
        """An empty series for a key nobody declared reads as "this is quiet"."""
        tenant_id = self.tenant()
        response = self.client.get("/ops/metrics/authz.denial",
                                   headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_probe_result_is_recorded_and_read_back(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        check = self.client.post("/ops/synthetic-checks", headers=head, json={
            "check_key": "login.probe", "description": "Signs a synthetic member in",
            "workflow": "login", "interval_seconds": 60, **self.correlation()})
        self.assertEqual(check.status_code, 201, check.text)
        check_id = check.json()["check_id"]
        recorded = self.client.post(f"/ops/synthetic-checks/{check_id}/results", headers=head,
                                    json={"outcome": "failed", "duration_ms": 812,
                                          "detail": "timed out", **self.correlation()})
        self.assertEqual(recorded.status_code, 201, recorded.text)
        results = self.client.get(f"/ops/synthetic-checks/{check_id}/results", headers=head)
        self.assertEqual(len(results.json()), 1)
        self.assertEqual(results.json()[0]["outcome"], "failed")
        series = self.client.get("/ops/metrics/ops.synthetic_success?window_hours=1",
                                 headers=head)
        self.assertEqual(series.json()["buckets"][0]["total"], 0.0)

    def test_an_unknown_workflow_is_refused_by_the_closed_set(self):
        tenant_id = self.tenant()
        response = self.client.post("/ops/synthetic-checks", headers=self.headers(tenant_id),
                                    json={"check_key": "x.probe", "description": "d",
                                          "workflow": "teleport", "interval_seconds": 60,
                                          **self.correlation()})
        self.assertEqual(response.status_code, 422, response.text)

    # ----------------------------------------------------------------- permissions

    def test_a_read_permission_does_not_open_a_write_route(self):
        tenant_id = self.tenant()
        reader = self.headers(tenant_id, self.grant(tenant_id, ["ops.objective.read"]))
        self.assertEqual(self.client.get("/ops/objectives", headers=reader).status_code, 200)
        self.assertEqual(
            self.client.post("/ops/objectives", headers=reader,
                             json=self.objective_body()).status_code, 403)

    def test_money_is_behind_the_money_permissions(self):
        """`ops.cost.read` is `finance`-category and does not come with the metric read."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["ops.metric.read"]))
        self.assertEqual(
            self.client.get("/ops/costs?period_start=2026-11-01&period_end=2026-11-30",
                            headers=head).status_code, 403)
        self.assertEqual(
            self.client.get("/ops/margin?period_start=2026-11-01&period_end=2026-11-30",
                            headers=head).status_code, 403)

    def test_recording_a_probe_result_does_not_need_a_stepped_up_session(self):
        """Routine on purpose: a prober runs on a loop, and a step-up requirement would mean
        no probe ever reports. Its reach is bounded by the table being insert-only."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        check_id = self.client.post("/ops/synthetic-checks", headers=head, json={
            "check_key": "login.probe", "description": "d", "workflow": "login",
            "interval_seconds": 60, **self.correlation()}).json()["check_id"]
        prober = self.headers(tenant_id, self.grant(tenant_id, ["ops.metric.record"]))
        response = self.client.post(f"/ops/synthetic-checks/{check_id}/results",
                                    headers=prober,
                                    json={"outcome": "passed", "duration_ms": 10,
                                          **self.correlation()})
        self.assertEqual(response.status_code, 201, response.text)

    def test_a_cost_write_needs_a_stepped_up_session(self):
        """`ops.cost.write` is `financial`, so holding the permission on an AAL-1 session is
        not enough -- the same rule every other money write in this build follows."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["ops.cost.write"]))
        response = self.client.post("/ops/costs", headers=head, json={
            "period_start": "2026-11-01", "period_end": "2026-11-30", "dimension": "compute",
            "dimension_value": "api", "currency": "EUR", "amount_minor": 1, "source": "s",
            **self.correlation()})
        self.assertEqual(response.status_code, 403, response.text)

    def test_a_window_of_a_billion_hours_is_a_422(self):
        """Unbounded, the timedelta raises OverflowError before any query and the caller gets
        a 500 -- the class every id in this module is shape-checked to avoid."""
        tenant_id = self.tenant()
        response = self.client.get("/ops/metrics/authz.denials?window_hours=1000000000",
                                   headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_non_finite_number_is_refused_at_the_boundary(self):
        """`json.loads` accepts the non-standard NaN and Infinity literals, and pydantic passes
        them to a float. A NaN threshold makes every comparison False, so the objective breaches
        on every evaluation and its event payload carries a value jsonb refuses."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        response = self.client.post(
            "/ops/objectives", headers={**head, "Content-Type": "application/json"},
            content=b'{"objective_key": "k", "kind": "slo", "metric_key":'
                    b' "ops.synthetic_success", "comparison": "at_least", "threshold": NaN,'
                    b' "window_hours": 24, "aggregate_as": "mean", "owner": "o",'
                    b' "runbook_ref": "r", "dimensions": {"check_key": "login"},'
                    b' "correlation_id": "00000000-0000-4000-8000-000000000003"}')
        self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post(
            "/ops/capacity", headers={**head, "Content-Type": "application/json"},
            content=b'{"resource": "cpu", "horizon_days": 30, "current_value": 1.0,'
                    b' "projected_value": Infinity, "basis": "b",'
                    b' "correlation_id": "00000000-0000-4000-8000-000000000003"}')
        self.assertEqual(response.status_code, 422, response.text)


class RateLimitRegressionTests(GatedApiTestCase):
    """The blocking finding from the request-path review, and the backoff that goes with it."""

    def body(self, identifier: str) -> dict:
        return {"identifier": identifier, "password": "wrong-but-long-enough",
                "correlation_id": str(uuid.uuid4())}

    def test_respelling_a_phone_number_does_not_buy_a_fresh_budget(self):
        """`normalize_phone` strips whitespace, parentheses and hyphens from anywhere in the
        string, so one number has unlimited spellings that resolve to one identity. The limiter
        keyed on the raw value handed each spelling its own 30 a minute, and every attempt still
        cost the server a scrypt -- which is the volume MOD-007's gap was about."""
        tenant_id = self.tenant()
        head = {"X-Veyro-Tenant": tenant_id}
        spellings = ["+3545551234", "+354 5551234", "+354-555-1234", "+354(555)1234",
                     "+3 545551234", "+35 45551234", "+354555 1234", "+354555-1234"]
        statuses = []
        for i in range(ratelimit.BUDGETS["auth.login"] + 4):
            statuses.append(self.client.post(
                "/auth/login", headers=head,
                json=self.body(spellings[i % len(spellings)])).status_code)
        self.assertIn(429, statuses)

    def test_the_refusal_says_how_long_to_wait(self):
        """Computing a backoff and not sending it makes choosing 429 over 403 decorative."""
        tenant_id = self.tenant()
        head = {"X-Veyro-Tenant": tenant_id}
        for _ in range(ratelimit.BUDGETS["auth.login"] + 1):
            last = self.client.post("/auth/login", headers=head,
                                    json=self.body("ghost@acme.test"))
        self.assertEqual(last.status_code, 429)
        self.assertIn("retry-after", {k.lower() for k in last.headers})
        self.assertGreaterEqual(int(last.headers["retry-after"]), 1)

    def test_an_unparseable_identifier_still_gets_a_stable_key(self):
        """A limiter that refused to count what it could not parse is one an attacker turns off
        by sending nonsense."""
        tenant_id = self.tenant()
        head = {"X-Veyro-Tenant": tenant_id}
        statuses = [self.client.post("/auth/login", headers=head,
                                     json=self.body("not an identifier at all")).status_code
                    for _ in range(ratelimit.BUDGETS["auth.login"] + 2)]
        self.assertIn(429, statuses)


class RateLimitApiTests(GatedApiTestCase):
    """The limiter in the request path, which closes MOD-007's named gap."""

    def test_login_volume_is_bounded_even_for_an_address_that_does_not_exist(self):
        """Lockout bounds guessing against one identity and sees nothing at all when the
        address is not registered. This is the half that was missing."""
        tenant_id = self.tenant()
        head = {"X-Veyro-Tenant": tenant_id}
        body = {"identifier": "nobody@acme.test", "password": "wrong-but-long-enough",
                "correlation_id": str(uuid.uuid4())}
        statuses = [self.client.post("/auth/login", headers=head, json=body).status_code
                    for _ in range(ratelimit.BUDGETS["auth.login"] + 2)]
        self.assertIn(429, statuses)
        self.assertEqual(statuses[0], 401)

    def test_one_tenant_s_flood_does_not_refuse_another_tenant(self):
        tenant_a = self.tenant()
        tenant_b = self.tenant()
        body = {"identifier": "nobody@acme.test", "password": "wrong-but-long-enough",
                "correlation_id": str(uuid.uuid4())}
        for _ in range(ratelimit.BUDGETS["auth.login"] + 2):
            self.client.post("/auth/login", headers={"X-Veyro-Tenant": tenant_a}, json=body)
        response = self.client.post("/auth/login", headers={"X-Veyro-Tenant": tenant_b},
                                    json=body)
        self.assertNotEqual(response.status_code, 429)

    def test_the_refusal_is_a_429_with_a_fixed_code(self):
        """429 rather than 403: a client that reads 403 stops, one that reads 429 backs off.
        The code is a fixed identifier, so nothing from the request travels back out."""
        tenant_id = self.tenant()
        head = {"X-Veyro-Tenant": tenant_id}
        wrong = {"identifier": "ghost@acme.test", "password": "wrong-but-long-enough",
                 "correlation_id": str(uuid.uuid4())}
        for _ in range(ratelimit.BUDGETS["auth.login"] + 1):
            self.client.post("/auth/login", headers=head, json=wrong)
        refused = self.client.post("/auth/login", headers=head, json=wrong)
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.json()["error"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
