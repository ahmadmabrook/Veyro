"""MOD-008 IAM-03 authorization API against a real PostgreSQL with row-level security in force.

The decision logic is covered by `test_authorization_domain.py`, which needs no database. What is
checked here is what only the wired-up service can show: that the gate is actually on the routes,
that a denial reaches the audit log, that separation of duties survives a real second approver,
and that the hash chain notices somebody editing the log behind the application's back.
"""

from __future__ import annotations

import os
import unittest
import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_identity_pool, make_platform_pool, make_tenant_pool
from app.main import create_app

DSN = os.environ.get("VEYRO_DATABASE_URL", "")


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class AuthorizationTestCase(unittest.TestCase):
    client: TestClient
    PASSWORD = "a-long-enough-password"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tenant_pool = make_tenant_pool(DSN)
        cls._platform_pool = make_platform_pool(DSN)
        cls._identity_pool = make_identity_pool(DSN)
        app = create_app(
            Settings(environment="local", release="test", database_url=DSN),
            tenant_pool=cls._tenant_pool, platform_pool=cls._platform_pool,
            identity_pool=cls._identity_pool,
        )
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        cls._tenant_pool.close()
        cls._platform_pool.close()
        cls._identity_pool.close()

    # ------------------------------------------------------------------ helpers

    def correlation(self) -> dict[str, str]:
        return {"correlation_id": str(uuid.uuid4())}

    def tenant(self) -> str:
        response = self.client.post("/platform/tenants", json={
            "external_key": f"authz-{uuid.uuid4()}", "display_name": "Authz Gym",
            "region": "eu-west", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["tenant_id"])

    def headers(self, tenant_id: str, token: str | None = None) -> dict[str, str]:
        head = {"X-Veyro-Tenant": tenant_id}
        if token:
            head["Authorization"] = f"Bearer {token}"
        return head

    def person(self, tenant_id: str, *, fingerprint: str = "device-a") -> tuple[str, str, str]:
        """An identity in this tenant, its email and a live session token."""
        email = f"user-{uuid.uuid4().hex[:10]}@acme.test"
        created = self.client.post("/identities", json={
            "display_name": "Staff", "email": email, "password": self.PASSWORD,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        login = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD,
            "device_fingerprint": fingerprint, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertTrue(login.json().get("authenticated"), login.text)
        return created.json()["identity_id"], email, login.json()["token"]

    def elevated(self, tenant_id: str, identity_id: str, token: str) -> str:
        """Step a session up to level 2, which every administrative action needs."""
        codes = self.client.post(f"/identities/{identity_id}/recovery-codes", json={
            **self.correlation(), "current_password": self.PASSWORD},
            headers=self.headers(tenant_id, token)).json()["codes"]
        challenge = self.client.get("/auth/require/financial",
                                    headers=self.headers(tenant_id, token)
                                    ).json()["challenge"]
        stepped = self.client.post("/auth/step-up", json={
            "challenge": challenge, "recovery_code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(stepped.status_code, 200, stepped.text)
        return str(stepped.json()["token"])

    def admin(self, tenant_id: str | None = None) -> tuple[str, str, str]:
        """A bootstrapped administrator: tenant, identity id, elevated session token."""
        tenant_id = tenant_id or self.tenant()
        identity_id, _, token = self.person(tenant_id)
        boot = self.client.post("/authz/bootstrap", json=self.correlation(),
                                headers=self.headers(tenant_id, token))
        self.assertEqual(boot.status_code, 201, boot.text)
        return tenant_id, identity_id, self.elevated(tenant_id, identity_id, token)


class BootstrapTests(AuthorizationTestCase):
    def test_the_bootstrap_grants_everything_once_and_then_refuses(self):
        tenant_id = self.tenant()
        identity_id, _, token = self.person(tenant_id)
        first = self.client.post("/authz/bootstrap", json=self.correlation(),
                                 headers=self.headers(tenant_id, token))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertGreater(first.json()["permissions"], 30)

        second = self.client.post("/authz/bootstrap", json=self.correlation(),
                                  headers=self.headers(tenant_id, token))
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "already_bootstrapped")

    def test_the_bootstrap_needs_a_session(self):
        self.assertEqual(
            self.client.post("/authz/bootstrap", json=self.correlation(),
                             headers=self.headers(self.tenant())).status_code, 422)

    def test_a_second_identity_gets_nothing_from_the_first_bootstrap(self):
        tenant_id, _, _ = self.admin()
        _, _, other = self.person(tenant_id, fingerprint="device-b")
        checked = self.client.get("/authz/check", params={
            "action": "authz.role.write", **self.correlation()},
            headers=self.headers(tenant_id, other)).json()
        self.assertFalse(checked["allowed"])
        self.assertEqual(checked["reason"], "default_deny")


class GateTests(AuthorizationTestCase):
    def test_an_unauthorized_caller_cannot_create_a_role(self):
        tenant_id, _, _ = self.admin()
        _, _, outsider = self.person(tenant_id, fingerprint="device-b")
        refused = self.client.post("/authz/roles", json={
            "role_key": "sneaky", "display_name": "Sneaky", **self.correlation()},
            headers=self.headers(tenant_id, outsider))
        self.assertEqual(refused.status_code, 403)

    def test_an_administrator_can_create_a_role_and_grant_it(self):
        tenant_id, admin_id, token = self.admin()
        created = self.client.post("/authz/roles", json={
            "role_key": "front_desk", "display_name": "Front Desk",
            "permissions": ["member.profile.read"], **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["permissions"], ["member.profile.read"])

        staff_id, _, staff_token = self.person(tenant_id, fingerprint="device-b")
        granted = self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "front_desk", **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(granted.status_code, 201, granted.text)

        checked = self.client.get("/authz/check", params={
            "action": "member.profile.read", **self.correlation()},
            headers=self.headers(tenant_id, staff_token)).json()
        self.assertTrue(checked["allowed"])
        self.assertEqual(checked["reason"], "role:front_desk")

    def test_a_role_cannot_hold_a_permission_this_build_does_not_define(self):
        tenant_id, _, token = self.admin()
        refused = self.client.post("/authz/roles", json={
            "role_key": "invented", "display_name": "Invented",
            "permissions": ["member.profile.destroy"], **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(refused.status_code, 422)
        self.assertEqual(refused.json()["error"], "unknown_permission")

    def test_revoking_an_assignment_takes_the_permission_away(self):
        tenant_id, _, token = self.admin()
        self.client.post("/authz/roles", json={
            "role_key": "reader", "display_name": "Reader",
            "permissions": ["member.profile.read"], **self.correlation()},
            headers=self.headers(tenant_id, token))
        staff_id, _, staff_token = self.person(tenant_id, fingerprint="device-b")
        assignment = self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "reader", **self.correlation()},
            headers=self.headers(tenant_id, token)).json()["assignment_id"]

        def allowed():
            return self.client.get("/authz/check", params={
                "action": "member.profile.read", **self.correlation()},
                headers=self.headers(tenant_id, staff_token)).json()["allowed"]

        self.assertTrue(allowed())
        self.client.post(f"/authz/assignments/{assignment}/revoke", json=self.correlation(),
                         headers=self.headers(tenant_id, token))
        self.assertFalse(allowed())

    def test_a_financial_action_needs_an_elevated_session_even_with_the_permission(self):
        tenant_id, _, token = self.admin()
        self.client.post("/authz/roles", json={
            "role_key": "biller", "display_name": "Biller",
            "permissions": ["billing.invoice.issue"], **self.correlation()},
            headers=self.headers(tenant_id, token))
        staff_id, _, staff_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "biller", **self.correlation()},
            headers=self.headers(tenant_id, token))

        checked = self.client.get("/authz/check", params={
            "action": "billing.invoice.issue", **self.correlation()},
            headers=self.headers(tenant_id, staff_token)).json()
        self.assertFalse(checked["allowed"])
        self.assertTrue(checked["step_up_required"])
        self.assertEqual(checked["required_aal"], 2)

    def test_a_privileged_action_reports_that_it_cannot_be_reached_at_all(self):
        tenant_id, admin_id, token = self.admin()
        checked = self.client.get("/authz/check", params={
            "action": "support.session.start", **self.correlation()},
            headers=self.headers(tenant_id, token)).json()
        self.assertFalse(checked["allowed"])
        self.assertFalse(checked["reachable"])


class ScopeAndPolicyTests(AuthorizationTestCase):
    def brand(self, tenant_id: str, token: str) -> str:
        """Built through the hierarchy routes, which are themselves gated now."""
        head = self.headers(tenant_id, token)
        org = self.client.post("/organizations",
                               json={"legal_name": "Authz ehf", "country_code": "IS"},
                               headers=head)
        self.assertEqual(org.status_code, 201, org.text)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "Authz City"},
            headers=head)
        self.assertEqual(brand.status_code, 201, brand.text)
        return str(brand.json()["brand_id"])

    def test_a_brand_scoped_assignment_grants_only_at_that_brand(self):
        tenant_id, _, token = self.admin()
        brand_id = self.brand(tenant_id, token)
        self.client.post("/authz/roles", json={
            "role_key": "brand_reader", "display_name": "Brand Reader",
            "permissions": ["member.profile.read"], **self.correlation()},
            headers=self.headers(tenant_id, token))
        staff_id, _, staff_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "brand_reader", "scope_type": "brand",
            "brand_id": brand_id, **self.correlation()},
            headers=self.headers(tenant_id, token))

        head = self.headers(tenant_id, staff_token)
        at_brand = self.client.get("/authz/check", params={
            "action": "member.profile.read", "brand_id": brand_id,
            **self.correlation()}, headers=head).json()
        elsewhere = self.client.get("/authz/check", params={
            "action": "member.profile.read", "brand_id": str(uuid.uuid4()),
            **self.correlation()}, headers=head).json()
        self.assertTrue(at_brand["allowed"])
        self.assertFalse(elsewhere["allowed"])

    def test_a_deny_policy_beats_the_role_that_granted_it(self):
        tenant_id, admin_id, token = self.admin()
        head = self.headers(tenant_id, token)

        def allowed():
            return self.client.get("/authz/check", params={
                "action": "member.health.read", **self.correlation()},
                headers=head).json()

        # The administrator holds everything, but health reads also need level 3.
        self.assertFalse(allowed()["allowed"])

        self.client.post("/authz/policies", json={
            "policy_key": "no_health", "effect": "deny", "action": "member.health.read",
            **self.correlation()}, headers=head)
        denied = allowed()
        self.assertFalse(denied["allowed"])
        self.assertEqual(denied["reason"], "policy:no_health",
                         "the policy decides before assurance does")

    def test_a_mask_policy_comes_back_with_the_decision(self):
        tenant_id, _, token = self.admin()
        head = self.headers(tenant_id, token)
        self.client.post("/authz/policies", json={
            "policy_key": "mask_contact", "effect": "mask", "action": "member.profile.read",
            "masked_fields": ["email", "phone"], **self.correlation()}, headers=head)
        checked = self.client.get("/authz/check", params={
            "action": "member.profile.read", **self.correlation()}, headers=head).json()
        self.assertTrue(checked["allowed"])
        self.assertEqual(sorted(checked["masked_fields"]), ["email", "phone"])

    def test_a_mask_policy_must_name_fields(self):
        tenant_id, _, token = self.admin()
        refused = self.client.post("/authz/policies", json={
            "policy_key": "empty", "effect": "mask", "action": "member.profile.read",
            **self.correlation()}, headers=self.headers(tenant_id, token))
        self.assertEqual(refused.status_code, 422)

    def test_the_simulator_agrees_with_the_gate(self):
        tenant_id, admin_id, token = self.admin()
        head = self.headers(tenant_id, token)
        simulated = self.client.get("/authz/simulate", params={
            "identity_id": admin_id, **self.correlation()}, headers=head).json()
        self.assertIn("authz.role.write", simulated["permissions"])
        for action in ("authz.role.write", "member.profile.read"):
            checked = self.client.get("/authz/check", params={
                "action": action, **self.correlation()}, headers=head).json()
            self.assertEqual(checked["allowed"], action in simulated["permissions"], action)


class ApprovalTests(AuthorizationTestCase):
    def requester(self, tenant_id: str, admin_head: dict[str, str],
                  fingerprint: str) -> tuple[str, str]:
        """Somebody who may perform the action, and therefore may ask for approval of it.

        Approval gates an action a person is authorized for but which exceeds a threshold. It is
        not a way in for somebody who is not authorized at all, so the requester holds the
        permission -- what they lack is the amount, not the right.
        """
        self.client.put("/authz/roles/refunder/permissions", json={
            "permissions": ["billing.refund.issue"], **self.correlation()},
            headers=admin_head)
        identity_id, _, token = self.person(tenant_id, fingerprint=fingerprint)
        self.client.post("/authz/assignments", json={
            "identity_id": identity_id, "role_key": "refunder", **self.correlation()},
            headers=admin_head)
        return identity_id, token


    def test_two_approvals_must_come_from_two_people(self):
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "refunder", "display_name": "Refunder", **self.correlation()},
            headers=head)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 2, **self.correlation()}, headers=head)

        requester_id, requester_token = self.requester(tenant_id, head, "device-b")
        request = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            "amount_minor": 50_000, "currency": "EUR", **self.correlation()},
            headers=self.headers(tenant_id, requester_token))
        self.assertEqual(request.status_code, 201, request.text)
        request_id = request.json()["request_id"]
        self.assertEqual(request.json()["required_approvals"], 2)

        own = self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "approved", **self.correlation()},
            headers=self.headers(tenant_id, requester_token))
        self.assertEqual(own.status_code, 403, "the requester may not decide their own request")

        first = self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "approved", **self.correlation()}, headers=head)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["state"], "pending", "one of two is not enough")

        again = self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "approved", **self.correlation()}, headers=head)
        self.assertEqual(again.status_code, 409, "the same approver cannot count twice")

    def test_a_second_approver_completes_it(self):
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "refunder", "display_name": "Refunder", **self.correlation()},
            headers=head)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 2, **self.correlation()}, headers=head)
        self.client.post("/authz/roles", json={
            "role_key": "approver", "display_name": "Approver",
            "permissions": ["billing.refund.approve", "authz.approval.decide"],
            **self.correlation()}, headers=head)
        second_id, _, second_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": second_id, "role_key": "approver", **self.correlation()},
            headers=head)
        second_elevated = self.elevated(tenant_id, second_id, second_token)

        requester_id, requester_token = self.requester(tenant_id, head, "device-c")
        request_id = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            "amount_minor": 50_000, "currency": "EUR", **self.correlation()},
            headers=self.headers(tenant_id, requester_token)).json()["request_id"]

        self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "approved", **self.correlation()}, headers=head)
        completed = self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "approved", **self.correlation()},
            headers=self.headers(tenant_id, second_elevated))
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["state"], "approved")

    def test_a_rejection_settles_a_request_whatever_else_was_recorded(self):
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "refunder", "display_name": "Refunder", **self.correlation()},
            headers=head)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 1, **self.correlation()}, headers=head)
        requester_id, requester_token = self.requester(tenant_id, head, "device-b")
        request_id = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            **self.correlation()},
            headers=self.headers(tenant_id, requester_token)).json()["request_id"]
        rejected = self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "rejected", "reason": "no", **self.correlation()}, headers=head)
        self.assertEqual(rejected.json()["state"], "rejected")
        self.assertEqual(
            self.client.post(f"/authz/approvals/{request_id}/decide", json={
                "decision": "approved", **self.correlation()}, headers=head).status_code, 409)

    def test_an_action_with_no_policy_cannot_be_sent_for_approval(self):
        tenant_id, _, token = self.admin()
        refused = self.client.post("/authz/approvals", json={
            "action": "config.flag.write", "resource_type": "flag", **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["error"], "no_approval_policy_applies")


class AuditTests(AuthorizationTestCase):
    def test_every_administrative_write_appends_to_the_chain(self):
        tenant_id, _, token = self.admin()
        head = self.headers(tenant_id, token)
        before = len(self.client.get("/authz/audit", params=self.correlation(),
                                     headers=head).json())
        self.client.post("/authz/roles", json={
            "role_key": "audited", "display_name": "Audited", **self.correlation()},
            headers=head)
        after = self.client.get("/authz/audit", params=self.correlation(), headers=head).json()
        self.assertGreater(len(after), before)
        self.assertEqual(after[0]["action"], "role.created")

    def test_a_denial_is_recorded_without_the_caller_having_to_remember(self):
        tenant_id, _, token = self.admin()
        outsider_id, _, outsider = self.person(tenant_id, fingerprint="device-c")
        self.client.post("/authz/roles", json={
            "role_key": "nope", "display_name": "Nope", **self.correlation()},
            headers=self.headers(tenant_id, outsider))
        entries = self.client.get("/authz/audit", params=self.correlation(),
                                  headers=self.headers(tenant_id, token)).json()
        denials = [e for e in entries if e["outcome"] == "denied"]
        self.assertTrue(denials)
        self.assertEqual(denials[0]["action"], "authz.role.write")

    def test_the_chain_verifies_and_is_contiguous(self):
        tenant_id, _, token = self.admin()
        head = self.headers(tenant_id, token)
        for n in range(3):
            self.client.post("/authz/roles", json={
                "role_key": f"role_{n}", "display_name": f"Role {n}", **self.correlation()},
                headers=head)
        verified = self.client.get("/authz/audit/verify", params=self.correlation(),
                                   headers=head).json()
        self.assertTrue(verified["verified"], verified)
        entries = self.client.get("/authz/audit", params=self.correlation(),
                                  headers=head).json()
        sequences = sorted(e["sequence"] for e in entries)
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    def test_editing_an_entry_behind_the_application_is_detected(self):
        """The application cannot do this at all; somebody with database access can."""
        tenant_id, _, token = self.admin()
        head = self.headers(tenant_id, token)
        self.assertTrue(self.client.get("/authz/audit/verify", params=self.correlation(),
                                        headers=head).json()["verified"])
        with self._identity_pool.connection() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            conn.execute("SET LOCAL ROLE postgres")
            conn.execute(
                "UPDATE iam.audit_events SET action = 'role.revoked'"
                " WHERE tenant_id = %s AND sequence = 1", (tenant_id,))
        verified = self.client.get("/authz/audit/verify", params=self.correlation(),
                                   headers=head).json()
        self.assertFalse(verified["verified"])
        self.assertEqual(verified["problem"], "content_changed")
        self.assertEqual(verified["at"], 1)

    def test_reading_the_audit_log_needs_the_permission(self):
        tenant_id, _, _ = self.admin()
        _, _, outsider = self.person(tenant_id, fingerprint="device-b")
        self.assertEqual(
            self.client.get("/authz/audit", params=self.correlation(),
                            headers=self.headers(tenant_id, outsider)).status_code, 403)


class AccessReviewTests(AuthorizationTestCase):
    def test_a_review_snapshots_live_assignments_and_can_revoke_them(self):
        tenant_id, admin_id, token = self.admin()
        head = self.headers(tenant_id, token)
        opened = self.client.post("/authz/access-reviews", json={
            "title": "Quarterly", **self.correlation()}, headers=head)
        self.assertEqual(opened.status_code, 201, opened.text)
        self.assertGreaterEqual(opened.json()["items"], 1,
                                "the bootstrap grant is the first thing worth reviewing")
        review_id = opened.json()["review_id"]

        early = self.client.post(f"/authz/access-reviews/{review_id}/complete",
                                 json=self.correlation(), headers=head)
        self.assertEqual(early.status_code, 409, "a review with undecided items cannot close")


class ReviewRegressionTests(AuthorizationTestCase):
    """One test per finding from the independent review, as the attack that must fail."""

    def hierarchy(self, tenant_id: str, token: str) -> tuple[str, str, str]:
        """Two brands and a location under the second one, built through the gated routes."""
        head = self.headers(tenant_id, token)
        org = self.client.post("/organizations",
                               json={"legal_name": "Two Brands ehf", "country_code": "IS"},
                               headers=head).json()["organization_id"]
        first = self.client.post("/brands", json={
            "organization_id": org, "brand_name": f"A-{uuid.uuid4().hex[:6]}"},
            headers=head).json()["brand_id"]
        second = self.client.post("/brands", json={
            "organization_id": org, "brand_name": f"B-{uuid.uuid4().hex[:6]}"},
            headers=head).json()["brand_id"]
        location = self.client.post("/locations", json={
            "brand_id": second, "location_name": "B Gym",
            "timezone": "Atlantic/Reykjavik"}, headers=head).json()["location_id"]
        return first, second, location

    def test_b2_a_brand_scoped_principal_cannot_reach_another_brands_location(self):
        """Sending your own brand id beside somebody else's location used to work."""
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        brand_a, brand_b, location_of_b = self.hierarchy(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "brand_mgr", "display_name": "Brand Manager",
            "permissions": ["member.profile.read"], **self.correlation()}, headers=head)
        staff_id, _, staff_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "brand_mgr", "scope_type": "brand",
            "brand_id": brand_a, **self.correlation()}, headers=head)
        staff_head = self.headers(tenant_id, staff_token)

        honest = self.client.get("/authz/check", params={
            "action": "member.profile.read", "location_id": location_of_b,
            **self.correlation()}, headers=staff_head).json()
        cheat = self.client.get("/authz/check", params={
            "action": "member.profile.read", "location_id": location_of_b,
            "brand_id": brand_a, **self.correlation()}, headers=staff_head).json()
        self.assertFalse(honest["allowed"])
        self.assertFalse(cheat["allowed"],
                         "the brand is resolved from the location, not taken from the caller")

        simulated = self.client.get("/authz/simulate", params={
            "identity_id": staff_id, "location_id": location_of_b, "brand_id": brand_a,
            **self.correlation()}, headers=head).json()
        self.assertEqual(simulated["permissions"], [],
                         "the simulator must expose the escalation, not confirm it")

    def test_b2b_a_brand_scope_still_reaches_its_own_locations(self):
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        _, brand_b, location_of_b = self.hierarchy(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "own_brand", "display_name": "Own Brand",
            "permissions": ["member.profile.read"], **self.correlation()}, headers=head)
        staff_id, _, staff_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "own_brand", "scope_type": "brand",
            "brand_id": brand_b, **self.correlation()}, headers=head)
        allowed = self.client.get("/authz/check", params={
            "action": "member.profile.read", "location_id": location_of_b,
            **self.correlation()}, headers=self.headers(tenant_id, staff_token)).json()
        self.assertTrue(allowed["allowed"])

    def test_b4_a_grantor_cannot_grant_what_they_do_not_hold(self):
        """A clerk holding only assignment.write granted itself everything."""
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "clerk", "display_name": "Clerk",
            "permissions": ["authz.assignment.write"], **self.correlation()}, headers=head)
        clerk_id, _, clerk_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": clerk_id, "role_key": "clerk", **self.correlation()}, headers=head)
        clerk_elevated = self.elevated(tenant_id, clerk_id, clerk_token)

        grab = self.client.post("/authz/assignments", json={
            "identity_id": clerk_id, "role_key": "tenant_admin", **self.correlation()},
            headers=self.headers(tenant_id, clerk_elevated))
        self.assertEqual(grab.status_code, 403)
        self.assertEqual(grab.json()["error"], "cannot_grant_what_you_do_not_hold")

        simulated = self.client.get("/authz/simulate", params={
            "identity_id": clerk_id, **self.correlation()}, headers=head).json()
        self.assertEqual(simulated["permissions"], ["authz.assignment.write"])

    def test_b4b_a_grantor_may_grant_a_subset_of_what_they_hold(self):
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "reader_role", "display_name": "Reader",
            "permissions": ["member.profile.read"], **self.correlation()}, headers=head)
        staff_id, _, _ = self.person(tenant_id, fingerprint="device-b")
        granted = self.client.post("/authz/assignments", json={
            "identity_id": staff_id, "role_key": "reader_role", **self.correlation()},
            headers=head)
        self.assertEqual(granted.status_code, 201, granted.text)

    def test_b6_requesting_approval_needs_the_permission_for_the_action(self):
        """An identity with no roles filled the audit log with requests it could never act on."""
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 1, **self.correlation()}, headers=head)
        _, _, outsider = self.person(tenant_id, fingerprint="device-b")
        refused = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            **self.correlation()}, headers=self.headers(tenant_id, outsider))
        self.assertEqual(refused.status_code, 403)

    def test_b3_separation_of_duties_cannot_be_switched_off_mid_flight(self):
        """Writing a lenient policy after the request used to let the requester approve it."""
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "refunder", "display_name": "Refunder",
            "permissions": ["billing.refund.issue", "billing.refund.approve",
                            "authz.approval.decide"], **self.correlation()}, headers=head)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 2, "separation_of_duties": True, **self.correlation()},
            headers=head)
        requester_id, _, requester_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": requester_id, "role_key": "refunder", **self.correlation()},
            headers=head)
        requester_elevated = self.elevated(tenant_id, requester_id, requester_token)
        request_id = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            "amount_minor": 1_000_000, "currency": "EUR", **self.correlation()},
            headers=self.headers(tenant_id, requester_elevated)).json()["request_id"]

        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "threshold_minor": 1, "required_approvals": 1, "separation_of_duties": False,
            **self.correlation()}, headers=head)
        own = self.client.post(f"/authz/approvals/{request_id}/decide", json={
            "decision": "approved", **self.correlation()},
            headers=self.headers(tenant_id, requester_elevated))
        self.assertEqual(own.status_code, 403,
                         "the request's own snapshot governs, not today's policies")


class Round2RegressionTests(AuthorizationTestCase):
    """Round two of the review: role editing, and refusals that erased their own evidence."""

    def audit_count(self, tenant_id: str, admin_head: dict[str, str]) -> int:
        return len(self.client.get("/authz/audit", params={"limit": 500, **self.correlation()},
                                   headers=admin_head).json())

    def editor(self, tenant_id: str, admin_head: dict[str, str]) -> tuple[str, str]:
        """Somebody holding `authz.role.write` and nothing else."""
        self.client.post("/authz/roles", json={
            "role_key": "role_editor", "display_name": "Role Editor",
            "permissions": ["authz.role.write"], **self.correlation()}, headers=admin_head)
        identity_id, _, token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": identity_id, "role_key": "role_editor", **self.correlation()},
            headers=admin_head)
        return identity_id, self.elevated(tenant_id, identity_id, token)

    def test_c1_editing_a_role_cannot_add_a_permission_the_editor_lacks(self):
        """Holding only role.write, rewriting a role you hold used to gain you anything."""
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        editor_id, editor_token = self.editor(tenant_id, head)
        editor_head = self.headers(tenant_id, editor_token)

        grab = self.client.put("/authz/roles/role_editor/permissions", json={
            "permissions": ["authz.role.write", "billing.refund.issue",
                            "identity.session.revoke"], **self.correlation()},
            headers=editor_head)
        self.assertEqual(grab.status_code, 403)
        self.assertEqual(grab.json()["error"], "cannot_grant_what_you_do_not_hold")

        simulated = self.client.get("/authz/simulate", params={
            "identity_id": editor_id, **self.correlation()}, headers=head).json()
        self.assertEqual(simulated["permissions"], ["authz.role.write"])

    def test_c1b_creating_a_role_cannot_contain_a_permission_the_author_lacks(self):
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        _, editor_token = self.editor(tenant_id, head)
        refused = self.client.post("/authz/roles", json={
            "role_key": "trojan", "display_name": "Trojan",
            "permissions": ["billing.refund.issue"], **self.correlation()},
            headers=self.headers(tenant_id, editor_token))
        self.assertEqual(refused.status_code, 403)

    def test_c1c_an_editor_may_still_write_a_role_within_what_it_holds(self):
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        _, editor_token = self.editor(tenant_id, head)
        allowed = self.client.post("/authz/roles", json={
            "role_key": "lesser_editor", "display_name": "Lesser",
            "permissions": ["authz.role.write"], **self.correlation()},
            headers=self.headers(tenant_id, editor_token))
        self.assertEqual(allowed.status_code, 201, allowed.text)

    def test_c2_an_escalation_refusal_leaves_an_audit_row(self):
        """All three refusals wrote their evidence and then rolled it back with the raise."""
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        _, editor_token = self.editor(tenant_id, head)
        before = self.audit_count(tenant_id, head)
        self.client.post("/authz/assignments", json={
            "identity_id": self.person(tenant_id, fingerprint="device-c")[0],
            "role_key": "tenant_admin", **self.correlation()},
            headers=self.headers(tenant_id, editor_token))
        self.assertGreater(self.audit_count(tenant_id, head), before)

    def test_c2b_a_refused_approval_request_leaves_an_audit_row(self):
        tenant_id, _, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 1, **self.correlation()}, headers=head)
        _, _, outsider = self.person(tenant_id, fingerprint="device-b")
        before = self.audit_count(tenant_id, head)
        refused = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            **self.correlation()}, headers=self.headers(tenant_id, outsider))
        self.assertEqual(refused.status_code, 403)
        self.assertGreater(self.audit_count(tenant_id, head), before)

    def test_c2c_repeated_self_approval_attempts_are_all_recorded(self):
        tenant_id, admin_id, admin_token = self.admin()
        head = self.headers(tenant_id, admin_token)
        self.client.post("/authz/roles", json={
            "role_key": "refunder", "display_name": "Refunder",
            "permissions": ["billing.refund.issue", "billing.refund.approve",
                            "authz.approval.decide"], **self.correlation()}, headers=head)
        self.client.post("/authz/approval-policies", json={
            "action": "billing.refund.issue", "required_permission": "billing.refund.approve",
            "required_approvals": 2, **self.correlation()}, headers=head)
        requester_id, _, requester_token = self.person(tenant_id, fingerprint="device-b")
        self.client.post("/authz/assignments", json={
            "identity_id": requester_id, "role_key": "refunder", **self.correlation()},
            headers=head)
        elevated = self.elevated(tenant_id, requester_id, requester_token)
        request_id = self.client.post("/authz/approvals", json={
            "action": "billing.refund.issue", "resource_type": "invoice",
            **self.correlation()},
            headers=self.headers(tenant_id, elevated)).json()["request_id"]

        before = self.audit_count(tenant_id, head)
        for _ in range(3):
            self.assertEqual(self.client.post(f"/authz/approvals/{request_id}/decide", json={
                "decision": "approved", **self.correlation()},
                headers=self.headers(tenant_id, elevated)).status_code, 403)
        denials = [e for e in self.client.get("/authz/audit", params={
            "limit": 500, **self.correlation()}, headers=head).json()
            if e["action"] == "approval.denied"]
        self.assertEqual(len(denials), 3,
                         "every attempt to approve one's own request is on the record")
        self.assertGreater(self.audit_count(tenant_id, head), before)


class IsolationTests(AuthorizationTestCase):
    def test_one_tenants_roles_and_audit_are_invisible_to_another(self):
        first, _, first_token = self.admin()
        second, _, second_token = self.admin()
        self.client.post("/authz/roles", json={
            "role_key": "secret_role", "display_name": "Secret", **self.correlation()},
            headers=self.headers(first, first_token))
        keys = [r["role_key"] for r in self.client.get(
            "/authz/roles", params=self.correlation(),
            headers=self.headers(second, second_token)).json()]
        self.assertNotIn("secret_role", keys)

    def test_a_session_from_one_tenant_authorizes_nothing_in_another(self):
        first, _, token = self.admin()
        second = self.tenant()
        self.assertEqual(
            self.client.get("/authz/roles", params=self.correlation(),
                            headers=self.headers(second, token)).status_code, 401)


if __name__ == "__main__":
    unittest.main()
