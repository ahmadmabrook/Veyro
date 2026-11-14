"""The product surfaces are behind MOD-008's gate. These are the tests that say so.

Every other product suite runs as a fully-privileged owner, which proves the routes still work
and proves nothing about whether they are guarded. This one approaches them the way an attacker
would: with no session, with a session holding nothing, and with a session holding the read
permission when the route wants the write one.

IAM-03's control is that default deny is mandatory. A catalogue nothing checks is a list, so the
thing worth testing is the refusal.
"""

from __future__ import annotations

import ast
import pathlib
import unittest
import uuid

from app.authorization import service as authz
from tests.support import GatedApiTestCase

# Ids that exist nowhere. The gate refuses before any lookup, so a route that answers 404
# rather than 403 to these is a route whose guard runs after its work.
_ID = "00000000-0000-4000-8000-000000000001"
_SUBJECT = "00000000-0000-4000-8000-000000000002"
_WHEN = "2026-11-01T00:00:00+00:00"
_CORR = {"correlation_id": "00000000-0000-4000-8000-000000000003"}

# A behavioural sweep of the gated product routes, with a body that would otherwise succeed. A
# route added without a `permit` call shows up here as a 2xx -- and `GateCoverageTests` below
# is what stops a route being added without appearing here at all.
READ_ROUTES = [
    ("get", "/organizations", None),
    ("get", "/locations", None),
    ("get", "/config/definitions", None),
    ("get", "/config/resolved", None),
    ("get", "/invoices", None),
    ("get", "/entitlements", None),
    ("get", "/privacy/purposes", None),
    ("get", "/privacy/retention", None),
    ("get", "/privacy/legal-holds", None),
    ("get", "/privacy/requests", None),
    ("get", "/privacy/incidents", None),
    # Query parameters are part of the path here on purpose: FastAPI validates them alongside
    # the session dependency, so a route swept without its required query would answer 422 for
    # a missing parameter and be read as a refusal it did not make.
    ("get", f"/privacy/consent/state?subject_id={_SUBJECT}", None),
    ("get", f"/privacy/consent/history?subject_id={_SUBJECT}", None),
    ("get", f"/privacy/requests/{_ID}", None),
    ("get", f"/privacy/requests/{_ID}/plan", None),
    ("get", "/events/health", None),
    ("get", f"/events/trace?correlation_id={_CORR['correlation_id']}", None),
    ("get", f"/events/aggregate?aggregate_type=tenant&aggregate_id={_ID}", None),
    ("get", f"/events/{_ID}", None),
    ("get", "/events/subscriptions/all", None),
    ("get", "/events/dead-letters/all", None),
    ("get", "/ops/metrics/authz.denials", None),
    ("get", "/ops/objectives", None),
    ("get", "/ops/synthetic-checks", None),
    ("get", f"/ops/synthetic-checks/{_ID}/results", None),
    ("get", "/ops/capacity", None),
    ("get", "/ops/costs?period_start=2026-11-01&period_end=2026-11-30", None),
    ("get", "/ops/margin?period_start=2026-11-01&period_end=2026-11-30", None),
    ("get", "/ops/budgets", None),
    ("get", "/ops/budget-alerts", None),
]

WRITE_ROUTES = [
    ("post", "/organizations", {"legal_name": "X ehf", "country_code": "IS"}),
    ("post", "/config/definitions", {"config_key": "a.b", "value_type": "integer",
                                     "default_value": 1, "owner_module": "MOD-005"}),
    ("put", "/flags/pay.test", {"enabled": True, "default_variant": "off", "rules": []}),
    ("post", "/meters", {"meter_code": "m.sms", "unit": "message", "aggregation": "sum"}),
    ("post", "/privacy/purposes", {"purpose_code": "member.x", "description": "d",
                                   "lawful_basis": "consent", "controller_role": "controller",
                                   "data_classes": ["internal"], **_CORR}),
    ("post", f"/privacy/purposes/{_ID}/retire", _CORR),
    ("post", "/privacy/consent/definitions", {"consent_type": "marketing",
                                              "purpose_id": _ID, **_CORR}),
    ("post", "/privacy/consent/versions", {"consent_type": "marketing", "language": "en",
                                           "document_ref": "r", "document_hash": "0" * 64,
                                           "effective_from": _WHEN, **_CORR}),
    ("post", "/privacy/consent/records", {"consent_type": "marketing", "signed_at": _WHEN,
                                          "source": "web", **_CORR}),
    ("post", "/privacy/consent/withdrawals", {"consent_type": "marketing", "signed_at": _WHEN,
                                              "source": "web", **_CORR}),
    ("post", "/privacy/retention", {"resource_type": "x", "data_class": "internal",
                                    "retention_days": 30, "legal_basis": "b",
                                    "region": "eu-west", **_CORR}),
    ("post", "/privacy/legal-holds", {"reason": "r", "reference": "CASE-1", **_CORR}),
    ("post", f"/privacy/legal-holds/{_ID}/release", {"release_reason": "done", **_CORR}),
    ("post", "/privacy/requests", {"subject_id": _SUBJECT, "request_type": "access",
                                   "response_days": 30, **_CORR}),
    ("post", f"/privacy/requests/{_ID}/identity-check", _CORR),
    ("post", f"/privacy/requests/{_ID}/verify-identity", _CORR),
    ("post", f"/privacy/requests/{_ID}/legal-check", _CORR),
    ("post", f"/privacy/requests/{_ID}/fulfil", _CORR),
    ("post", f"/privacy/requests/{_ID}/refuse", {"reason": "not a subject", **_CORR}),
    ("post", "/privacy/incidents", {"severity": "low", "category": "access_anomaly",
                                    "summary": "s", "detected_at": _WHEN,
                                    "personal_data_involved": "unknown", **_CORR}),
    ("post", "/events/subscriptions", {"consumer": "timeline",
                                       "event_type": "tenant.provisioned", **_CORR}),
    ("post", f"/events/subscriptions/{_ID}/deactivate", _CORR),
    ("post", "/events/dispatch", _CORR),
    ("post", f"/events/dead-letters/{_ID}/release", {"reason": "fixed", **_CORR}),
    ("post", "/events/replays", {"consumer": "timeline",
                                 "event_types": ["tenant.provisioned"],
                                 "from_time": _WHEN, "to_time": "2026-12-01T00:00:00+00:00",
                                 **_CORR}),
    ("post", f"/events/replays/{_ID}/run", _CORR),
    ("post", "/ops/objectives", {"objective_key": "login.availability", "kind": "slo",
                                 "metric_key": "ops.synthetic_success",
                                 "comparison": "at_least", "threshold": 0.99,
                                 "window_hours": 24, "aggregate_as": "mean",
                                 "owner": "platform-ops", "runbook_ref": "RB-REL-02", **_CORR}),
    ("post", f"/ops/objectives/{_ID}/retire", _CORR),
    ("post", f"/ops/objectives/{_ID}/evaluate", _CORR),
    ("post", "/ops/synthetic-checks", {"check_key": "login.probe", "description": "d",
                                       "workflow": "login", "interval_seconds": 60, **_CORR}),
    ("post", f"/ops/synthetic-checks/{_ID}/enabled", {"enabled": False, **_CORR}),
    ("post", f"/ops/synthetic-checks/{_ID}/results", {"outcome": "passed", "duration_ms": 10,
                                                      **_CORR}),
    ("post", "/ops/capacity", {"resource": "db_connections", "horizon_days": 30,
                               "current_value": 1, "projected_value": 2, "basis": "b",
                               **_CORR}),
    ("post", "/ops/costs", {"period_start": "2026-11-01", "period_end": "2026-11-30",
                            "dimension": "compute", "dimension_value": "api",
                            "currency": "EUR", "amount_minor": 1, "source": "s", **_CORR}),
    ("post", "/ops/budgets", {"budget_key": "ai.monthly", "dimension": "total",
                              "currency": "EUR", "amount_minor": 1000, "period": "monthly",
                              "owner": "platform-ops", **_CORR}),
    ("post", f"/ops/budgets/{_ID}/retire", _CORR),
    ("post", f"/ops/budgets/{_ID}/burn", {"period_start": "2026-11-01", **_CORR}),
]


class NoSessionTests(GatedApiTestCase):
    def test_every_product_route_refuses_a_caller_with_no_session(self):
        """The tenant header is an unauthenticated claim; on its own it now opens nothing."""
        tenant_id = self.tenant()
        bare = {"X-Veyro-Tenant": tenant_id}
        for method, path, body in READ_ROUTES + WRITE_ROUTES:
            call = getattr(self.client, method)
            kwargs = {"json": body} if body is not None else {}
            response = call(path, headers=bare, **kwargs)
            self.assertEqual(response.status_code, 422, f"{method.upper()} {path}")

    def test_a_garbage_token_is_refused(self):
        tenant_id = self.tenant()
        head = {"X-Veyro-Tenant": tenant_id, "Authorization": "Bearer nonsense"}
        self.assertEqual(self.client.get("/organizations", headers=head).status_code, 401)

    def test_platform_routes_stay_open_deliberately(self):
        """The control plane is not behind MOD-008; see the gap note in CLAUDE.md."""
        response = self.client.post("/platform/tenants", json={
            "external_key": f"open-{uuid.uuid4()}", "display_name": "Open", "region": "eu-west",
            "actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
            "idempotency_key": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 201)


class UnprivilegedSessionTests(GatedApiTestCase):
    def test_a_session_holding_nothing_is_refused_everywhere(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.unprivileged(tenant_id))
        for method, path, body in READ_ROUTES + WRITE_ROUTES:
            call = getattr(self.client, method)
            kwargs = {"json": body} if body is not None else {}
            response = call(path, headers=head, **kwargs)
            self.assertEqual(response.status_code, 403, f"{method.upper()} {path}")

    def test_the_refusal_reaches_the_audit_log(self):
        """`require` writes the denial itself, so a route cannot forget to record it."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.unprivileged(tenant_id))
        self.client.get("/organizations", headers=head)
        entries = authz.read_audit(self._identity_pool, tenant_id, limit=500)
        denials = [e for e in entries
                   if e["outcome"] == "denied" and e["action"] == "tenancy.organization.read"]
        self.assertTrue(denials, "a denied product call is an access event worth recording")


class LeastPrivilegeTests(GatedApiTestCase):
    def test_a_read_permission_does_not_confer_the_write(self):
        tenant_id = self.tenant()
        token = self.grant(tenant_id, ["tenancy.organization.read"])
        head = self.headers(tenant_id, token)
        self.assertEqual(self.client.get("/organizations", headers=head).status_code, 200)
        refused = self.client.post("/organizations", headers=head,
                                   json={"legal_name": "X ehf", "country_code": "IS"})
        self.assertEqual(refused.status_code, 403)

    def test_a_configuration_permission_does_not_reach_billing(self):
        tenant_id = self.tenant()
        token = self.grant(tenant_id, ["config.definition.read", "config.flag.read"])
        head = self.headers(tenant_id, token)
        self.assertEqual(self.client.get("/config/definitions", headers=head).status_code, 200)
        self.assertEqual(self.client.get("/invoices", headers=head).status_code, 403)

    def test_a_financial_write_needs_a_stepped_up_session_as_well_as_the_permission(self):
        """`config.flag.write` is `financial` per TSD paragraph 1020's change control."""
        tenant_id = self.tenant()
        token = self.grant(tenant_id, ["config.flag.write", "config.flag.read"])
        head = self.headers(tenant_id, token)
        refused = self.client.put("/flags/pay.test", headers=head, json={
            "enabled": True, "default_variant": "off", "rules": []})
        self.assertEqual(refused.status_code, 403,
                         "holding the permission on an AAL-1 session is not enough")
        allowed = self.client.put("/flags/pay.test", headers=self.headers(tenant_id), json={
            "enabled": True, "default_variant": "off", "rules": []})
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_a_routine_read_works_on_an_unstepped_session(self):
        tenant_id = self.tenant()
        token = self.grant(tenant_id, ["config.flag.read"])
        response = self.client.get("/flags", params={"subject_id": "member-1"},
                                   headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 200, response.text)


class CrossTenantTests(GatedApiTestCase):
    def test_an_owner_of_one_tenant_authorizes_nothing_in_another(self):
        first, second = self.tenant(), self.tenant()
        borrowed = self.headers(second, self.owner_token(first))
        self.assertEqual(self.client.get("/organizations", headers=borrowed).status_code, 401,
                         "the session does not resolve under another tenant at all")


class ReviewRegressionTests(GatedApiTestCase):
    """One test per defect an independent review of the gate found, named for the attack.

    Each of these passed as a route-is-guarded check before the review and still let the caller
    through, because the permission the route named was not the permission the route needed. A
    route guarded by the wrong permission reads exactly like a guarded route from the outside;
    only asking what the weakest credential that satisfies it can do tells them apart.
    """

    def test_a_flag_reader_cannot_write_an_experiment_exposure(self):
        """`/experiments/{key}/allocate` was guarded by `config.flag.read`: "See feature flags".

        It inserts into `cfg_exposures`, which carries no UPDATE or DELETE grant, so what a
        read-only kiosk credential wrote there was permanent and became the basis of the
        experiment's analysis -- including exposures for subjects that do not exist.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = f"exp.{uuid.uuid4().hex[:8]}"
        created = self.client.post("/experiments", headers=owner, json={
            "experiment_key": key,
            "variants": [{"variant_key": "control", "weight": 1},
                         {"variant_key": "treatment", "weight": 1}]})
        self.assertEqual(created.status_code, 201, created.text)
        # A draft experiment assigns nobody, so it would refuse the write for the wrong reason.
        self.assertEqual(self.client.post(f"/experiments/{key}/status", headers=owner,
                                          json={"status": "running"}).status_code, 200)

        reader = self.headers(tenant_id, self.grant(tenant_id, ["config.flag.read"]))
        refused = self.client.post(f"/experiments/{key}/allocate", headers=reader,
                                   json={"subject_id": "ghost-1"})
        self.assertEqual(refused.status_code, 403, "reading flags must not write an exposure")

        exposures = self.client.get(f"/experiments/{key}/exposures", headers=owner)
        self.assertEqual(exposures.json(), [], "the refusal must leave nothing behind")

        allowed = self.client.post(f"/experiments/{key}/allocate", headers=owner,
                                   json={"subject_id": "member-1"})
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertTrue(allowed.json()["newly_exposed"])
        self.assertEqual(
            [e["subject_id"] for e in self.client.get(f"/experiments/{key}/exposures",
                                                      headers=owner).json()],
            ["member-1"], "a permitted allocation still writes one")

    def test_a_usage_emitter_cannot_define_a_meter_or_move_its_quota(self):
        """`/meters` and `/meters/{code}/quota` were guarded by `billing.usage.record`.

        That is the one finance permission deliberately left `routine`, because recording a
        measurement is telemetry a device does continuously. Defining what is measured, and
        setting the limit at which usage starts costing money or stops being allowed, are
        decisions that spend the measurement -- so the credential being metered could raise its
        own ceiling and switch its own hard stop off.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        code = f"m.{uuid.uuid4().hex[:6]}"
        self.assertEqual(self.client.post("/meters", headers=owner, json={
            "meter_code": code, "unit": "message", "aggregation": "sum"}).status_code, 201)
        self.assertEqual(self.client.post(f"/meters/{code}/quota", headers=owner, json={
            "period": "billing_period", "limit_quantity": 100, "hard_stop": True}).status_code, 200)

        emitter = self.headers(tenant_id, self.grant(tenant_id, ["billing.usage.record"]))
        self.assertEqual(self.client.post("/meters", headers=emitter, json={
            "meter_code": f"m.{uuid.uuid4().hex[:6]}", "unit": "message"}).status_code, 403)
        raised = self.client.post(f"/meters/{code}/quota", headers=emitter, json={
            "period": "billing_period", "limit_quantity": 100_000_000,
            "overage_allowed": True, "hard_stop": False})
        self.assertEqual(raised.status_code, 403, "the metered credential must not move its cap")

        # ...and the permission still does the job it was granted for.
        recorded = self.client.post("/usage", headers=emitter, json={
            "meter_code": code, "quantity": 1, "idempotency_key": str(uuid.uuid4()),
            "actor_id": str(uuid.uuid4()), **self.correlation()})
        self.assertEqual(recorded.status_code, 201, recorded.text)

    def test_defining_a_meter_needs_a_stepped_up_session(self):
        """The new permissions are `financial`, so holding one on an AAL-1 session is not enough."""
        tenant_id = self.tenant()
        scoped = self.headers(
            tenant_id, self.grant(tenant_id, ["billing.meter.write", "billing.quota.write"]))
        refused = self.client.post("/meters", headers=scoped, json={
            "meter_code": f"m.{uuid.uuid4().hex[:6]}", "unit": "message"})
        self.assertEqual(refused.status_code, 403)

    def test_the_gate_records_the_correlation_id_the_caller_sent(self):
        """The refusal and the request that caused it have to be joinable.

        Eight routes took a `correlation_id` in the body and did not hand it to the gate, so the
        gate minted its own: the denial was recorded under an id the caller had never seen and
        could not search for. Only denials are written -- an allow leaves its evidence in the
        business record the call goes on to make -- so a denial is what this looks for.
        """
        tenant_id = self.tenant()
        correlation = str(uuid.uuid4())
        onlooker = self.headers(tenant_id, self.grant(tenant_id, ["billing.subscription.read"]))
        refused = self.client.post("/subscription", headers=onlooker, json={
            "plan_code": "starter", "plan_version": 1,
            "actor_id": str(uuid.uuid4()), "correlation_id": correlation})
        self.assertEqual(refused.status_code, 403, refused.text)

        entries = authz.read_audit(self._identity_pool, tenant_id, limit=500)
        matched = [e for e in entries
                   if e["correlation_id"] == correlation
                   and e["action"] == "billing.subscription.write"
                   and e["outcome"] == "denied"]
        self.assertTrue(matched, "the gate must record the caller's own correlation id")


class GateCoverageTests(unittest.TestCase):
    """Every route either asks the gate or is listed here as deliberately not asking.

    The sweeps above are a sample, and a sample cannot prove a negative: a route added without
    a `permit` call is invisible to them, because they never call it. This reads `main.py`
    instead and requires each route to do one of three things -- call `permit`, scope itself to
    the caller's own identity, or appear in `UNGATED` with a reason somebody wrote down.

    It needs no database, which is the point: it is the check that still runs when the suite
    that exercises the routes is skipped.
    """

    #: Routes that deliberately do not ask MOD-008, and why. A new entry here is a decision to
    #: leave something open and should be hard to add without noticing.
    UNGATED = {
        ("GET", "/healthz"): "liveness, no tenant and no data",
        # The platform plane is unauthenticated by design and that is the largest open gap in
        # this build: these five routes provision tenants and move them through their
        # lifecycle, so reaching them is enough to suspend a live customer. See CLAUDE.md.
        ("POST", "/platform/tenants"): "the platform plane is not authenticated",
        ("GET", "/platform/tenants/{tenant_id}"): "the platform plane is not authenticated",
        ("DELETE", "/platform/tenants/{tenant_id}"): "the platform plane is not authenticated",
        ("GET", "/platform/tenants/{tenant_id}/history"):
            "the platform plane is not authenticated",
        ("POST", "/platform/tenants/{tenant_id}/{action}"):
            "the platform plane is not authenticated",
        ("POST", "/platform/plans"): "the platform plane is not authenticated",
        ("GET", "/platform/plans"): "the platform plane is not authenticated",
        ("GET", "/platform/plans/{plan_code}"): "the platform plane is not authenticated",
        ("POST", "/platform/plans/{plan_code}/{plan_version}/status"):
            "the platform plane is not authenticated",
        # How a caller gets a session in the first place. A gate in front of these would mean
        # needing a session to get a session.
        ("POST", "/auth/login"): "authentication",
        ("POST", "/auth/challenge"): "authentication",
        ("POST", "/auth/rotate"): "authentication",
        ("POST", "/auth/step-up"): "authentication",
        ("POST", "/auth/recover"): "authentication",
        ("GET", "/auth/session"): "reads the caller's own session",
        ("GET", "/auth/events"): "reads the caller's own authentication log",
        ("GET", "/auth/require/{action_class}"): "states what an action class needs, of nobody",
        ("POST", "/passkeys/{passkey_id}/assertion"): "authentication",
        ("POST", "/identities"): "registration is open; see the gap note in CLAUDE.md",
        ("POST", "/authz/bootstrap"):
            "the one-time grant that makes a tenant administrable; refuses once any assignment "
            "exists",
        ("GET", "/authz/check"): "asks the gate about the caller's own session",
        ("POST", "/authz/approvals"):
            "the service checks the requester holds the action's own permission",
        # Scoped to the caller in the service rather than by a permission: each passes the
        # session's own identity_id into a WHERE clause, so another identity's device or
        # session is not found rather than refused.
        ("POST", "/devices/{device_id}/revoke"): "scoped to the caller's own device",
        ("POST", "/devices/{device_id}/trust"): "scoped to the caller's own device",
        ("POST", "/sessions/{session_id}/revoke"): "scoped to the caller's own session",
    }

    #: Calling any of these counts as asking. `owned` refuses a path identity that is not the
    #: session's; `consent_subject` charges a stronger permission when the subject is not self.
    GUARDS = {"permit", "owned", "consent_subject"}

    #: The decorators that make a function a route. Anything else on `app` -- an exception
    #: handler, middleware -- is not a caller-facing path and has nothing to gate.
    HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

    def _routes(self):
        source = pathlib.Path(__file__).resolve().parents[1] / "app" / "main.py"
        tree = ast.parse(source.read_text())
        create_app = next(n for n in tree.body
                          if isinstance(n, ast.FunctionDef) and n.name == "create_app")
        # Both kinds, because `async def` is FastAPI's ordinary idiom and `create_app` already
        # contains one. The filter saw only `ast.FunctionDef`, so an async route was neither
        # required to call a guard nor required to appear in UNGATED -- it was simply absent,
        # and all three tests below passed. A checker with a blind spot in the shape the next
        # route will be written is worse than no checker, because the sweeps are allowed to be
        # a sample on the strength of this one.
        #
        # Still a top-level walk of `create_app.body`: a route defined inside an `if`, a `with`
        # or a loop is invisible here too. Nothing in this file does that, and the day
        # something does, this comment is where to start.
        routes = (ast.FunctionDef, ast.AsyncFunctionDef)
        for node in create_app.body:
            if not isinstance(node, routes):
                continue
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and isinstance(dec.func.value, ast.Name)
                        and dec.func.value.id == "app"
                        # `app.<verb>("/path")` and nothing else. Including async routes also
                        # brought in `@app.exception_handler(ServiceError)`, whose argument is a
                        # name rather than a path -- it is not a route and has no caller to gate.
                        and dec.func.attr.upper() in self.HTTP_METHODS
                        and dec.args and isinstance(dec.args[0], ast.Constant)
                        and isinstance(dec.args[0].value, str)):
                    called = {c.func.id for c in ast.walk(node)
                              if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
                    yield dec.func.attr.upper(), dec.args[0].value, called

    def test_every_route_asks_the_gate_or_is_a_named_exception(self):
        unguarded = [(method, path) for method, path, called in self._routes()
                     if not (self.GUARDS & called)
                     and (method, path) not in self.UNGATED]
        self.assertEqual(
            unguarded, [],
            "these routes neither ask MOD-008 nor scope themselves to the caller. Add the "
            "`permit` call, or add the route to GateCoverageTests.UNGATED with the reason it "
            "is open -- deliberately, in writing, where a reviewer will see it",
        )

    def test_the_exception_list_names_no_route_that_is_gone(self):
        """A stale exemption would silently excuse a path somebody reuses later."""
        live = {(method, path) for method, path, _ in self._routes()}
        self.assertEqual(sorted(set(self.UNGATED) - live), [],
                         "these exemptions name routes this build no longer has")

    def test_the_exception_list_names_no_route_that_does_ask(self):
        """An exemption on a gated route reads as a gap that is not there."""
        guarded = {(method, path) for method, path, called in self._routes()
                   if self.GUARDS & called}
        self.assertEqual(sorted(set(self.UNGATED) & guarded), [],
                         "these routes do ask the gate and should not be listed as open")

    #: Modules whose whole HTTP surface the behavioural sweeps cover, rather than sampling.
    #: A new one is added here when its routes are added to READ_ROUTES and WRITE_ROUTES.
    FULLY_SWEPT_PREFIXES = ("/privacy", "/events", "/ops")

    def test_every_route_of_a_fully_swept_module_is_in_the_behavioural_sweep(self):
        """The sweeps are a sample elsewhere; for these modules they are the whole surface.

        Without this, a route added to one of them is caught by the gate-coverage test above
        (it must call `permit`) but never actually called with a weak credential, so a wrong
        permission on it would go unnoticed -- and a wrong permission reads exactly like a
        right one from outside.
        """
        swept = {(method.upper(), path.split("?")[0])
                 for method, path, _ in READ_ROUTES + WRITE_ROUTES}
        swept = {(method, path.replace(_ID, "{id}").replace(_SUBJECT, "{id}"))
                 for method, path in swept}
        swept = {(method, "/ops/metrics/{metric_key}" if path.startswith("/ops/metrics/")
                  else path) for method, path in swept}
        live = set()
        for method, path, _ in self._routes():
            # `path == prefix or path.startswith(prefix + "/")`, not a bare prefix match: a
            # collection route registered at exactly `/events` -- the natural shape for a
            # listing -- slipped past a `startswith("/events/")` test silently, and a silent
            # escape in the test that licenses the sweeps to be a sample is the worst kind.
            if not any(path == prefix or path.startswith(prefix + "/")
                       for prefix in self.FULLY_SWEPT_PREFIXES):
                continue
            for name in ("purpose_id", "hold_id", "request_id", "event_id", "job_id",
                         "subscription_id", "dead_letter_id", "objective_id", "check_id",
                         "budget_id"):
                path = path.replace("{" + name + "}", "{id}")
            live.add((method, path))
        self.assertEqual(sorted(live - swept), [],
                         "these routes are never called by the gating sweep")


if __name__ == "__main__":
    unittest.main()
