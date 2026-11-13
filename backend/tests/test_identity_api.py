"""MOD-007 IAM-01 identity API against a real PostgreSQL with row-level security in force.

The cryptography and the policy are covered by `test_identity_domain.py`, which needs no database.
What is checked here is the behaviour only the wired-up service can show.

**The `ReviewRegressionTests` class at the end is one test per finding from the independent
security review of the first version.** They are named for what an attacker did, because a test
named for the fix stops meaning anything once the fix is refactored. The first version's own
step-up test asserted the defect as correct behaviour -- it issued recovery codes and then never
presented one -- so these are written as attacks that must fail, not as features that must work.
"""

from __future__ import annotations

import base64
import os
import unittest
import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_identity_pool, make_platform_pool, make_tenant_pool
from app.identity import policy
from app.main import create_app

DSN = os.environ.get("VEYRO_DATABASE_URL", "")


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class IdentityTestCase(unittest.TestCase):
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
            "external_key": f"iam-{uuid.uuid4()}", "display_name": "Identity Gym",
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

    def register(self, tenant_id: str, **overrides):
        """`email` defaults to a fresh address; pass it as None to register without one."""
        body = {"display_name": "Staff Member", **self.correlation(),
                "email": f"user-{uuid.uuid4().hex[:10]}@acme.test", "password": self.PASSWORD}
        body.update(overrides)
        return self.client.post("/identities", json=body, headers=self.headers(tenant_id))

    def login(self, tenant_id: str, identifier: str, password: str | None = None, **overrides):
        body = {"identifier": identifier, "password": password or self.PASSWORD,
                **self.correlation(), "device_fingerprint": "device-a"}
        body.update(overrides)
        return self.client.post("/auth/login", json=body, headers=self.headers(tenant_id))

    def identity(self, tenant_id: str | None = None) -> tuple[str, str, str]:
        tenant_id = tenant_id or self.tenant()
        email = f"user-{uuid.uuid4().hex[:10]}@acme.test"
        created = self.register(tenant_id, email=email)
        self.assertEqual(created.status_code, 201, created.text)
        return tenant_id, created.json()["identity_id"], email

    def session(self, tenant_id: str, email: str, **overrides) -> str:
        response = self.login(tenant_id, email, **overrides)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["authenticated"], response.text)
        return str(response.json()["token"])

    def signed_in(self) -> tuple[str, str, str, str]:
        """A tenant, an identity, its email and a live session token."""
        tenant_id, identity_id, email = self.identity()
        return tenant_id, identity_id, email, self.session(tenant_id, email)

    def suspend(self, tenant_id: str, identity_id: str) -> None:
        """No route sets an identity's status yet, so the test writes it directly."""
        with self._identity_pool.connection() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            conn.execute("UPDATE iam.identities SET status = 'suspended' WHERE identity_id = %s",
                         (identity_id,))

    def codes(self, tenant_id: str, identity_id: str, token: str) -> list[str]:
        response = self.client.post(
            f"/identities/{identity_id}/recovery-codes",
            json={**self.correlation(), "current_password": self.PASSWORD},
            headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 201, response.text)
        return list(response.json()["codes"])


class RegistrationTests(IdentityTestCase):
    def test_an_identity_registers_and_can_authenticate(self):
        tenant_id, identity_id, email = self.identity()
        body = self.login(tenant_id, email).json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["identity_id"], identity_id)
        self.assertGreaterEqual(len(body["token"]), 43)

    def test_an_identity_needs_an_email_or_a_phone(self):
        response = self.register(self.tenant(), email=None, phone=None)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "identity_needs_an_email_or_phone")

    def test_an_identifier_is_unique_within_a_tenant_and_free_in_another(self):
        first, _, email = self.identity()
        self.assertEqual(self.register(first, email=email).status_code, 409)
        self.assertEqual(self.register(self.tenant(), email=email).status_code, 201)

    def test_a_malformed_email_phone_or_correlation_id_is_refused(self):
        tenant_id = self.tenant()
        self.assertEqual(self.register(tenant_id, email="not-an-email").status_code, 422)
        self.assertEqual(self.register(tenant_id, email=None, phone="12345").status_code, 422)
        self.assertEqual(self.register(tenant_id, correlation_id="not-a-uuid").status_code, 422)

    def test_an_email_is_normalised_so_case_does_not_create_a_second_identity(self):
        tenant_id, _, email = self.identity()
        self.assertEqual(self.register(tenant_id, email=email.upper()).status_code, 409)
        self.assertTrue(self.login(tenant_id, email.upper()).json()["authenticated"])

    def test_one_person_can_hold_identities_in_two_tenants(self):
        first, _, _ = self.identity()
        shared = self.register(first, email=f"o-{uuid.uuid4().hex[:8]}@acme.test"
                               ).json()["person_id"]
        linked = self.register(self.tenant(), person_id=shared)
        self.assertEqual(linked.status_code, 201, linked.text)
        self.assertEqual(linked.json()["person_id"], shared)


class AuthenticationTests(IdentityTestCase):
    def test_a_wrong_password_and_an_unknown_address_fail_identically(self):
        tenant_id, _, email = self.identity()
        wrong = self.login(tenant_id, email, "not-the-password")
        unknown = self.login(tenant_id, f"nobody-{uuid.uuid4().hex[:8]}@acme.test")
        self.assertEqual(wrong.status_code, unknown.status_code)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertEqual(wrong.json()["error"], "authentication_failed")

    def test_a_malformed_identifier_fails_the_same_way_too(self):
        tenant_id, _, _ = self.identity()
        response = self.login(tenant_id, "not-an-email-at-all")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "authentication_failed")

    def test_a_failed_login_against_an_unknown_address_names_no_identity(self):
        tenant_id, identity_id, email = self.identity()
        token = self.session(tenant_id, email)
        self.login(tenant_id, f"nobody-{uuid.uuid4().hex[:8]}@acme.test")
        events = self.client.get("/auth/events",
                                 headers=self.headers(tenant_id, token)).json()
        self.assertNotIn("unknown_identifier", [e["reason"] for e in events],
                         "an event with no identity belongs to nobody's own log")

    def test_a_successful_login_clears_the_failure_count(self):
        tenant_id, _, email = self.identity()
        for _ in range(policy.MAX_FAILED_ATTEMPTS - 1):
            self.login(tenant_id, email, "wrong")
        self.assertTrue(self.login(tenant_id, email).json()["authenticated"])
        for _ in range(policy.MAX_FAILED_ATTEMPTS - 1):
            self.login(tenant_id, email, "wrong")
        self.assertEqual(self.login(tenant_id, email).status_code, 200)

    def test_the_lock_is_recorded_so_the_owner_can_see_it_afterwards(self):
        tenant_id, identity_id, email = self.identity()
        token = self.session(tenant_id, email)
        for _ in range(policy.MAX_FAILED_ATTEMPTS):
            self.login(tenant_id, email, "wrong")
        kinds = [e["kind"] for e in
                 self.client.get("/auth/events",
                                 headers=self.headers(tenant_id, token)).json()]
        self.assertIn("identity.locked", kinds)


class SessionTests(IdentityTestCase):
    def test_a_session_resolves_and_never_hands_the_token_back(self):
        tenant_id, identity_id, _, token = self.signed_in()
        body = self.client.get("/auth/session",
                               headers=self.headers(tenant_id, token)).json()
        self.assertEqual(body["identity_id"], identity_id)
        self.assertNotIn("token", body)
        self.assertNotIn("token_hash", body)
        self.assertEqual(body["factors"], ["password"])

    def test_a_made_up_or_missing_token_is_refused(self):
        tenant_id, _, _ = self.identity()
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, "nope")).status_code,
                         401)
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id)).status_code, 422)

    def test_a_session_inventory_lists_sessions_without_any_secret(self):
        tenant_id, identity_id, email, token = self.signed_in()
        self.session(tenant_id, email)
        listed = self.client.get(f"/identities/{identity_id}/sessions",
                                 headers=self.headers(tenant_id, token)).json()
        self.assertEqual(len(listed), 2)
        for row in listed:
            self.assertFalse({"token", "token_hash"} & set(row))

    def test_revoking_a_session_stops_it_resolving(self):
        tenant_id, _, _, token = self.signed_in()
        head = self.headers(tenant_id, token)
        session_id = self.client.get("/auth/session", headers=head).json()["session_id"]
        revoked = self.client.post(f"/sessions/{session_id}/revoke",
                                   json=self.correlation(), headers=head)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 401)

    def test_rotation_issues_a_new_token_and_retires_the_old_one(self):
        tenant_id, _, _, first = self.signed_in()
        rotated = self.client.post("/auth/rotate", json=self.correlation(),
                                   headers=self.headers(tenant_id, first))
        self.assertEqual(rotated.status_code, 200, rotated.text)
        second = rotated.json()["token"]
        self.assertNotEqual(second, first)
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, second)).status_code,
                         200)
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, first)).status_code,
                         401)

    def test_reusing_a_rotated_token_burns_every_session_for_that_identity(self):
        tenant_id, identity_id, _, first = self.signed_in()
        second = self.client.post("/auth/rotate", json=self.correlation(),
                                  headers=self.headers(tenant_id, first)).json()["token"]
        replayed = self.client.post("/auth/rotate", json=self.correlation(),
                                    headers=self.headers(tenant_id, first))
        self.assertEqual(replayed.status_code, 401)
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, second)).status_code,
                         401, "the successor is revoked too, not just the replayed token")


class DeviceTests(IdentityTestCase):
    def test_revoking_a_device_kills_its_sessions(self):
        tenant_id, _, email, token = self.signed_in()
        head = self.headers(tenant_id, token)
        device_id = self.client.get("/auth/session", headers=head).json()["device_id"]
        revoked = self.client.post(f"/devices/{device_id}/revoke",
                                   json={**self.correlation(), "reason": "lost phone"},
                                   headers=head)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertGreaterEqual(revoked.json()["sessions_revoked"], 1)
        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 401)

    def test_trusting_a_device_records_it(self):
        tenant_id, identity_id, _, token = self.signed_in()
        head = self.headers(tenant_id, token)
        device_id = self.client.get("/auth/session", headers=head).json()["device_id"]
        trusted = self.client.post(f"/devices/{device_id}/trust", json=self.correlation(),
                                   headers=head)
        self.assertEqual(trusted.status_code, 200, trusted.text)
        listed = self.client.get(f"/identities/{identity_id}/devices", headers=head).json()
        self.assertTrue(listed[0]["trusted"])


class StepUpTests(IdentityTestCase):
    def test_a_routine_action_needs_no_step_up_and_a_financial_one_does(self):
        tenant_id, _, _, token = self.signed_in()
        head = self.headers(tenant_id, token)
        self.assertFalse(self.client.get("/auth/require/routine",
                                         headers=head).json()["step_up_required"])
        financial = self.client.get("/auth/require/financial", headers=head).json()
        self.assertTrue(financial["step_up_required"])
        self.assertEqual(financial["required_aal"], 2)
        self.assertIn("challenge", financial)
        self.assertTrue(financial["reachable"])

    def test_an_unclassified_action_is_refused_rather_than_treated_as_routine(self):
        tenant_id, _, _, token = self.signed_in()
        response = self.client.get("/auth/require/whatever",
                                   headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "unknown_action_class")

    def test_a_step_up_with_a_real_recovery_code_raises_the_level(self):
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        head = self.headers(tenant_id, token)
        challenge = self.client.get("/auth/require/financial", headers=head).json()["challenge"]

        stepped = self.client.post("/auth/step-up", json={
            "challenge": challenge, "recovery_code": codes[0], **self.correlation()},
            headers=head)
        self.assertEqual(stepped.status_code, 200, stepped.text)
        self.assertEqual(stepped.json()["aal"], 2)
        self.assertEqual(stepped.json()["factors"], ["password", "recovery_code"])
        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 401)
        self.assertFalse(
            self.client.get("/auth/require/financial",
                            headers=self.headers(tenant_id, stepped.json()["token"])
                            ).json()["step_up_required"])

    def test_a_step_up_with_a_wrong_recovery_code_is_an_authentication_failure(self):
        """401, not 403: a wrong credential is a failed authentication, not a missing level.

        It also counts against the recovery budget, which 403 would not have conveyed.
        """
        tenant_id, identity_id, _, token = self.signed_in()
        self.codes(tenant_id, identity_id, token)
        head = self.headers(tenant_id, token)
        challenge = self.client.get("/auth/require/financial", headers=head).json()["challenge"]
        response = self.client.post("/auth/step-up", json={
            "challenge": challenge, "recovery_code": "AAAA-BBBB-CCCC", **self.correlation()},
            headers=head)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "authentication_failed")
        self.assertEqual(self.client.get("/auth/session", headers=head).json()["aal"], 1)

    def test_a_challenge_cannot_be_replayed(self):
        tenant_id, identity_id, _, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        head = self.headers(tenant_id, token)
        challenge = self.client.get("/auth/require/financial", headers=head).json()["challenge"]
        body = {"challenge": challenge, "recovery_code": codes[0], **self.correlation()}
        first = self.client.post("/auth/step-up", json=body, headers=head)
        self.assertEqual(first.status_code, 200, first.text)
        replay = self.client.post(
            "/auth/step-up", json={**body, "recovery_code": codes[1]},
            headers=self.headers(tenant_id, first.json()["token"]))
        self.assertEqual(replay.status_code, 401)

    def test_a_made_up_challenge_is_refused(self):
        tenant_id, identity_id, _, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        response = self.client.post("/auth/step-up", json={
            "challenge": "invented", "recovery_code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 401)


class RecoveryTests(IdentityTestCase):
    def test_a_recovery_code_works_once_and_clears_a_lockout(self):
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        for _ in range(policy.MAX_FAILED_ATTEMPTS):
            self.login(tenant_id, email, "wrong")
        self.assertEqual(self.login(tenant_id, email).status_code, 401)

        recovered = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertIn("token", recovered.json())
        self.assertTrue(self.login(tenant_id, email, device_fingerprint="device-a"
                                   ).json().get("authenticated"), "recovery cleared the lock")

        replay = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(replay.status_code, 401, "a recovery code is single use")

    def test_regenerating_recovery_codes_retires_the_previous_set(self):
        tenant_id, identity_id, email, token = self.signed_in()
        old = self.codes(tenant_id, identity_id, token)
        self.codes(tenant_id, identity_id, token)
        response = self.client.post("/auth/recover", json={
            "identifier": email, "code": old[0], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 401)

    def test_recovery_against_an_unknown_address_fails_like_everything_else(self):
        tenant_id, _, _ = self.identity()
        response = self.client.post("/auth/recover", json={
            "identifier": f"nobody-{uuid.uuid4().hex[:8]}@acme.test", "code": "AAAA-BBBB-CCCC",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 401)


class PasswordTests(IdentityTestCase):
    def test_changing_a_password_needs_the_old_one_and_logs_everything_out(self):
        tenant_id, identity_id, email, token = self.signed_in()
        other = self.session(tenant_id, email)
        head = self.headers(tenant_id, token)
        changed = self.client.post(f"/identities/{identity_id}/password", json={
            "password": "a-different-long-password", "current_password": self.PASSWORD,
            **self.correlation()}, headers=head)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.login(tenant_id, email).status_code, 401)
        self.assertTrue(self.login(tenant_id, email, "a-different-long-password"
                                   ).json()["authenticated"])
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, other)).status_code,
                         401, "a password change logs every session out")

    def test_a_short_password_is_refused_at_registration_and_at_change(self):
        tenant_id, identity_id, _, token = self.signed_in()
        self.assertEqual(self.register(self.tenant(), password="short").status_code, 422)
        response = self.client.post(f"/identities/{identity_id}/password", json={
            "password": "short", "current_password": self.PASSWORD, **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 422)


class PasskeyTests(IdentityTestCase):
    def enroll(self, tenant_id: str, identity_id: str, token: str, *, cred: str | None = None):
        return self.client.post(f"/identities/{identity_id}/passkeys", json={
            "webauthn_credential_id": cred or base64.b64encode(
                uuid.uuid4().bytes).decode("ascii"),
            "public_key": base64.b64encode(b"k" * 48).decode("ascii"),
            **self.correlation(), "label": "YubiKey"},
            headers=self.headers(tenant_id, token))

    def test_a_passkey_enrols_and_says_plainly_that_it_is_not_a_factor(self):
        tenant_id, identity_id, _, token = self.signed_in()
        response = self.enroll(tenant_id, identity_id, token)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertFalse(response.json()["verified"])
        self.assertIn("not an auth factor", response.json()["note"])

    def test_the_same_credential_cannot_be_enrolled_twice(self):
        tenant_id, identity_id, _, token = self.signed_in()
        cred = base64.b64encode(uuid.uuid4().bytes).decode("ascii")
        self.assertEqual(self.enroll(tenant_id, identity_id, token, cred=cred).status_code, 201)
        self.assertEqual(self.enroll(tenant_id, identity_id, token, cred=cred).status_code, 409)

    def test_short_passkey_material_is_refused(self):
        tenant_id, identity_id, _, token = self.signed_in()
        response = self.client.post(f"/identities/{identity_id}/passkeys", json={
            "webauthn_credential_id": base64.b64encode(b"short").decode("ascii"),
            "public_key": base64.b64encode(b"k" * 48).decode("ascii"), **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 422)

    def test_an_advancing_signature_counter_is_accepted(self):
        tenant_id, identity_id, _, token = self.signed_in()
        passkey_id = self.enroll(tenant_id, identity_id, token).json()["passkey_id"]
        for count in (1, 2, 9):
            response = self.client.post(f"/passkeys/{passkey_id}/assertion", json={
                "sign_count": count, **self.correlation()},
                headers=self.headers(tenant_id, token))
            self.assertEqual(response.status_code, 200, response.text)

    def test_a_repeated_signature_counter_revokes_the_passkey_and_every_session(self):
        tenant_id, identity_id, _, token = self.signed_in()
        head = self.headers(tenant_id, token)
        passkey_id = self.enroll(tenant_id, identity_id, token).json()["passkey_id"]
        body = {"sign_count": 5, **self.correlation()}
        self.client.post(f"/passkeys/{passkey_id}/assertion", json=body, headers=head)
        cloned = self.client.post(f"/passkeys/{passkey_id}/assertion",
                                  json={"sign_count": 5, **self.correlation()}, headers=head)
        self.assertEqual(cloned.status_code, 409)
        self.assertEqual(cloned.json()["error"], "passkey_clone_suspected")
        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 401)


class IsolationTests(IdentityTestCase):
    def test_an_identity_is_invisible_to_another_tenant(self):
        owner, identity_id, email, token = self.signed_in()
        other = self.tenant()
        self.assertEqual(self.login(other, email).status_code, 401)
        self.assertEqual(
            self.client.get(f"/identities/{identity_id}/sessions",
                            headers=self.headers(other, token)).status_code, 401)

    def test_a_session_from_one_tenant_does_not_resolve_in_another(self):
        owner, _, _, token = self.signed_in()
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(self.tenant(), token)).status_code,
                         401)

    def test_a_request_with_no_tenant_header_is_refused(self):
        self.assertEqual(self.client.get("/auth/events").status_code, 422)


class ReviewRegressionTests(IdentityTestCase):
    """One test per finding from the independent review, written as the attack that must fail."""

    def test_finding_1_a_step_up_cannot_be_had_by_naming_a_factor(self):
        """`{"factors": ["passkey_hardware"]}` bought AAL-3 from a password session."""
        tenant_id, identity_id, _, token = self.signed_in()
        head = self.headers(tenant_id, token)
        challenge = self.client.get("/auth/require/privileged", headers=head).json()["challenge"]
        for claimed in ({"factors": ["passkey_hardware"]}, {"factors": ["totp"]},
                        {"factors": ["password", "totp"]}):
            response = self.client.post(
                "/auth/step-up", json={"challenge": challenge, **claimed, **self.correlation()},
                headers=head)
            self.assertIn(response.status_code, (403, 422), claimed)
        self.assertEqual(self.client.get("/auth/session", headers=head).json()["aal"], 1)

    def test_finding_1b_the_highest_level_is_not_reachable_without_hardware(self):
        """AAL-3 needs a verified hardware authenticator, and nothing can verify one yet."""
        tenant_id, identity_id, _, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        head = self.headers(tenant_id, token)
        asked = self.client.get("/auth/require/privileged", headers=head).json()
        self.assertTrue(asked["step_up_required"])
        self.assertFalse(asked["reachable"], "the API must say so rather than imply otherwise")
        response = self.client.post("/auth/step-up", json={
            "challenge": asked["challenge"], "recovery_code": codes[0], "password": self.PASSWORD,
            **self.correlation()}, headers=head)
        self.assertEqual(response.status_code, 403)

    def test_finding_2_identity_operations_need_a_session_for_that_identity(self):
        """Tenant UUID alone reached recovery codes, the password and the session list."""
        tenant_id, victim_id, victim_email, victim_token = self.signed_in()
        attacker_tenant, _, attacker_email = self.identity(tenant_id)
        attacker = self.session(tenant_id, attacker_email, device_fingerprint="device-b")

        unauthenticated = self.headers(tenant_id)
        stolen = self.headers(tenant_id, attacker)
        for method, path, body in (
            ("post", f"/identities/{victim_id}/recovery-codes", self.correlation()),
            ("post", f"/identities/{victim_id}/password",
             {"password": "attacker-chosen-password", **self.correlation()}),
            ("get", f"/identities/{victim_id}/sessions", None),
            ("get", f"/identities/{victim_id}/devices", None),
            ("get", f"/identities/{victim_id}/passkeys", None),
        ):
            call = getattr(self.client, method)
            kwargs = {"json": body} if body is not None else {}
            self.assertEqual(call(path, headers=unauthenticated, **kwargs).status_code, 422,
                             f"no token: {path}")
            self.assertEqual(call(path, headers=stolen, **kwargs).status_code, 404,
                             f"another identity's token: {path}")
        self.assertTrue(self.login(tenant_id, victim_email).json()["authenticated"],
                        "the victim's password is untouched")

    def test_finding_2b_the_auth_log_shows_only_the_callers_own_events(self):
        tenant_id, victim_id, victim_email, _ = self.signed_in()
        _, _, attacker_email = self.identity(tenant_id)
        attacker = self.session(tenant_id, attacker_email, device_fingerprint="device-b")
        events = self.client.get("/auth/events",
                                 headers=self.headers(tenant_id, attacker)).json()
        self.assertTrue(events)
        for event in events:
            self.assertNotEqual(event["identity_id"], victim_id)

    def test_finding_3_repeating_a_challenged_login_does_not_answer_the_challenge(self):
        """Sending the identical request twice used to skip the risk challenge entirely."""
        tenant_id, identity_id, email, token = self.signed_in()
        self.codes(tenant_id, identity_id, token)
        body = {"identifier": email, "password": self.PASSWORD,
                "device_fingerprint": "an-unknown-device", **self.correlation()}
        first = self.client.post("/auth/login", json=body, headers=self.headers(tenant_id))
        self.assertTrue(first.json()["challenge_required"], first.text)
        for _ in range(3):
            again = self.client.post("/auth/login", json={**body, **self.correlation()},
                                     headers=self.headers(tenant_id))
            self.assertTrue(again.json()["challenge_required"],
                            "the device must stay unconfirmed until the challenge is answered")

    def test_finding_3b_a_challenged_login_can_actually_be_answered(self):
        """There was no endpoint for this at all, so the control was unanswerable by design."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        challenged = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD,
            "device_fingerprint": "a-second-unknown-device", **self.correlation()},
            headers=self.headers(tenant_id)).json()
        self.assertTrue(challenged["challenge_required"])

        answered = self.client.post("/auth/challenge", json={
            "identifier": email, "challenge": challenged["challenge"],
            "recovery_code": codes[0], **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(answered.status_code, 200, answered.text)
        self.assertEqual(answered.json()["aal"], 2)
        self.assertEqual(
            self.client.post("/auth/login", json={
                "identifier": email, "password": self.PASSWORD,
                "device_fingerprint": "a-second-unknown-device", **self.correlation()},
                headers=self.headers(tenant_id)).json()["authenticated"],
            True, "the answered device is now confirmed")

    def test_finding_3c_a_challenged_login_does_not_clear_the_failure_counter(self):
        tenant_id, identity_id, email, token = self.signed_in()
        self.codes(tenant_id, identity_id, token)
        for _ in range(policy.MAX_FAILED_ATTEMPTS - 1):
            self.login(tenant_id, email, "wrong")
        challenged = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD,
            "device_fingerprint": "yet-another-device", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertTrue(challenged.json()["challenge_required"])
        self.assertEqual(self.login(tenant_id, email, "wrong").status_code, 401)
        self.assertEqual(self.login(tenant_id, email, "wrong").status_code, 401)
        locked = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD,
            "device_fingerprint": "device-a", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(locked.status_code, 401, "the counter was never reset")

    def test_finding_4_a_locked_identity_is_indistinguishable_from_a_wrong_password(self):
        """423 in 1.7 ms against 401 in 49 ms identified every registered address."""
        tenant_id, _, email = self.identity()
        for _ in range(policy.MAX_FAILED_ATTEMPTS):
            self.login(tenant_id, email, "wrong")
        locked = self.login(tenant_id, email)
        unknown = self.login(tenant_id, f"nobody-{uuid.uuid4().hex[:8]}@acme.test")
        self.assertEqual(locked.status_code, 401)
        self.assertEqual(locked.json(), unknown.json())

    def test_finding_5_recovery_is_bounded_by_a_budget_of_its_own(self):
        """Unlimited guesses at ten scrypt hashes each, with no lockout, is an oracle."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        for _ in range(policy.MAX_FAILED_ATTEMPTS):
            response = self.client.post("/auth/recover", json={
                "identifier": email, "code": "AAAA-BBBB-CCCC", **self.correlation()},
                headers=self.headers(tenant_id))
            self.assertEqual(response.status_code, 401)
        spent = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(spent.status_code, 401,
                         "a correct code is refused once the recovery budget is spent")

    def test_finding_5b_a_password_lockout_does_not_block_recovery(self):
        """Recovery exists for exactly this moment; honouring the password lock would trap you."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        for _ in range(policy.MAX_FAILED_ATTEMPTS):
            self.login(tenant_id, email, "wrong")
        self.assertEqual(self.login(tenant_id, email).status_code, 401)
        recovered = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(recovered.status_code, 200, recovered.text)

    def test_finding_7_an_ordinary_sign_out_is_not_a_token_reuse_incident(self):
        """Sign out on one device, refresh a stale token, and every session died."""
        tenant_id, identity_id, email, phone = self.signed_in()
        laptop = self.session(tenant_id, email)
        head = self.headers(tenant_id, phone)
        session_id = self.client.get("/auth/session", headers=head).json()["session_id"]
        self.client.post(f"/sessions/{session_id}/revoke", json=self.correlation(), headers=head)

        stale = self.client.post("/auth/rotate", json=self.correlation(), headers=head)
        self.assertEqual(stale.status_code, 401)
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, laptop)).status_code,
                         200, "the other device stays signed in")
        reasons = {row["revoke_reason"] for row in
                   self.client.get(f"/identities/{identity_id}/sessions",
                                   headers=self.headers(tenant_id, laptop)).json()}
        self.assertNotIn("token_reuse_detected", reasons,
                         "no fabricated security incident in the audit trail")

    def test_finding_9_a_revoked_device_cannot_log_in_again(self):
        """The stolen phone signed back in with the password it already knew."""
        tenant_id, _, email, token = self.signed_in()
        head = self.headers(tenant_id, token)
        device_id = self.client.get("/auth/session", headers=head).json()["device_id"]
        self.assertEqual(self.client.post(f"/devices/{device_id}/revoke",
                                          json=self.correlation(), headers=head).status_code, 200)
        refused = self.login(tenant_id, email)
        self.assertEqual(refused.status_code, 401)
        self.assertTrue(self.login(tenant_id, email, device_fingerprint="a-different-device"
                                   ).json().get("challenge_required", False)
                        or self.login(tenant_id, email,
                                      device_fingerprint="a-different-device"
                                      ).json().get("authenticated", False),
                        "another device is unaffected")

    def test_finding_9b_revoking_a_device_twice_is_not_an_error(self):
        tenant_id, _, email, token = self.signed_in()
        head = self.headers(tenant_id, token)
        device_id = self.client.get("/auth/session", headers=head).json()["device_id"]
        self.assertEqual(self.client.post(f"/devices/{device_id}/revoke",
                                          json=self.correlation(),
                                          headers=head).status_code, 200)
        # Revoking killed this session with the device, so prove idempotence from a live one on
        # another device rather than from the token that just died.
        other = self.session(tenant_id, email, device_fingerprint="device-b")
        again = self.client.post(f"/devices/{device_id}/revoke", json=self.correlation(),
                                 headers=self.headers(tenant_id, other))
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["already_revoked"])

    def test_round2_n1_answering_a_challenge_confirms_only_the_device_that_drew_it(self):
        """An attacker holding the password got whitelisted when the victim answered."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)

        def challenged(fingerprint: str):
            response = self.client.post("/auth/login", json={
                "identifier": email, "password": self.PASSWORD,
                "device_fingerprint": fingerprint, **self.correlation()},
                headers=self.headers(tenant_id))
            self.assertTrue(response.json()["challenge_required"], response.text)
            return response.json()["challenge"]

        victim_challenge = challenged("victim-laptop")
        challenged("attacker-box")  # seen more recently than the victim's

        answered = self.client.post("/auth/challenge", json={
            "identifier": email, "challenge": victim_challenge, "recovery_code": codes[0],
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(answered.status_code, 200, answered.text)

        devices = {d["label"] or d["device_id"]: d for d in
                   self.client.get(f"/identities/{identity_id}/devices",
                                   headers=self.headers(tenant_id, token)).json()}
        confirmed = {d["device_id"] for d in devices.values() if d["confirmed"]}
        self.assertIn(answered.json()["device_id"], confirmed)

        attacker = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD,
            "device_fingerprint": "attacker-box", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertTrue(attacker.json()["challenge_required"],
                        "the attacker's device was never confirmed by the victim's answer")

    def test_round2_n2_a_recovered_user_can_set_a_new_password(self):
        """Recovery existed but led nowhere: no old password, no step-up, codes burnt per try."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        recovered = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id)).json()
        self.assertEqual(recovered["aal"], 1)

        changed = self.client.post(f"/identities/{identity_id}/password", json={
            "password": "a-brand-new-long-password", **self.correlation()},
            headers=self.headers(tenant_id, recovered["token"]))
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertTrue(self.login(tenant_id, email, "a-brand-new-long-password"
                                   ).json()["authenticated"])

    def test_round2_n2b_a_refused_step_up_does_not_burn_the_code_it_verified(self):
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        recovered = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id)).json()["token"]
        head = self.headers(tenant_id, recovered)
        challenge = self.client.get("/auth/require/financial", headers=head).json()["challenge"]
        refused = self.client.post("/auth/step-up", json={
            "challenge": challenge, "recovery_code": codes[1], **self.correlation()},
            headers=head)
        self.assertEqual(refused.status_code, 403, "one kind of factor twice is still one kind")
        still_good = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[1], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(still_good.status_code, 200, "the code it verified was not consumed")

    def test_round2_n3_re_authentication_paths_count_their_failures(self):
        """A stolen session bought an unmetered password oracle at twenty guesses a second."""
        tenant_id, identity_id, email, token = self.signed_in()
        head = self.headers(tenant_id, token)
        for _ in range(policy.MAX_FAILED_ATTEMPTS):
            response = self.client.post(f"/identities/{identity_id}/password", json={
                "password": "a-long-enough-replacement", "current_password": "wrong",
                **self.correlation()}, headers=head)
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.login(tenant_id, email).status_code, 401,
                         "guessing through the change endpoint locks the identity too")

    def test_round2_n3b_a_failed_code_issue_leaves_an_audit_row(self):
        tenant_id, identity_id, email, token = self.signed_in()
        head = self.headers(tenant_id, token)
        before = len(self.client.get("/auth/events", headers=head).json())
        refused = self.client.post(f"/identities/{identity_id}/recovery-codes", json={
            **self.correlation(), "current_password": "wrong"}, headers=head)
        self.assertEqual(refused.status_code, 401)
        after = self.client.get("/auth/events", headers=head).json()
        self.assertGreater(len(after), before,
                           "a failed guess at the permanent-credential endpoint is recorded")

    def test_round2_n4_rotation_does_not_extend_an_elevated_window(self):
        """Rotating every twelve hours held level 2 forever without re-presenting anything."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        head = self.headers(tenant_id, token)
        challenge = self.client.get("/auth/require/financial", headers=head).json()["challenge"]
        stepped = self.client.post("/auth/step-up", json={
            "challenge": challenge, "recovery_code": codes[0], **self.correlation()},
            headers=head).json()
        deadline, rotating = stepped["expires_at"], stepped["token"]
        for _ in range(3):
            rotated = self.client.post("/auth/rotate", json=self.correlation(),
                                       headers=self.headers(tenant_id, rotating)).json()
            self.assertEqual(rotated["aal"], 2)
            self.assertEqual(rotated["expires_at"], deadline,
                             "the elevation keeps its original deadline")
            rotating = rotated["token"]

    def test_round2_n4b_a_routine_session_still_gets_a_fresh_window_on_rotation(self):
        tenant_id, _, _, token = self.signed_in()
        first = self.client.get("/auth/session",
                                headers=self.headers(tenant_id, token)).json()["expires_at"]
        rotated = self.client.post("/auth/rotate", json=self.correlation(),
                                   headers=self.headers(tenant_id, token)).json()
        self.assertEqual(rotated["aal"], 1)
        self.assertGreaterEqual(rotated["expires_at"], first)

    def test_round2_n5_suspending_an_identity_stops_its_live_sessions(self):
        """Suspension blocked new logins and left an existing token working for a fortnight."""
        tenant_id, identity_id, email, token = self.signed_in()
        head = self.headers(tenant_id, token)
        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 200)
        self.suspend(tenant_id, identity_id)
        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 401)
        self.assertEqual(self.login(tenant_id, email).status_code, 401)

    def test_round3_b1_a_recovery_session_cannot_mint_new_recovery_codes(self):
        """A stolen recovery session minted codes that survived the owner's own password reset."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        stolen = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id)).json()["token"]

        minted = self.client.post(f"/identities/{identity_id}/recovery-codes",
                                  json=self.correlation(),
                                  headers=self.headers(tenant_id, stolen))
        self.assertEqual(minted.status_code, 401,
                         "minting permanent credentials needs a real password")

    def test_round3_b1b_a_password_reset_actually_ends_the_attackers_access(self):
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        stolen = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id)).json()["token"]

        owner = self.session(tenant_id, email)
        reset = self.client.post(f"/identities/{identity_id}/password", json={
            "password": "the-owners-new-long-password", "current_password": self.PASSWORD,
            **self.correlation()}, headers=self.headers(tenant_id, owner))
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(self.client.get("/auth/session",
                                         headers=self.headers(tenant_id, stolen)).status_code,
                         401, "the reset revoked the stolen session")
        self.assertEqual(self.client.post(f"/identities/{identity_id}/recovery-codes",
                                          json=self.correlation(),
                                          headers=self.headers(tenant_id, stolen)).status_code,
                         401)

    def test_round3_b2_a_suspended_identity_cannot_rotate_or_step_up(self):
        """The status read was in one of three callers, so two paths kept the chain alive."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        head = self.headers(tenant_id, token)
        challenge = self.client.get("/auth/require/financial", headers=head).json()["challenge"]
        self.suspend(tenant_id, identity_id)

        self.assertEqual(self.client.get("/auth/session", headers=head).status_code, 401)
        self.assertEqual(self.client.post("/auth/rotate", json=self.correlation(),
                                          headers=head).status_code, 401)
        self.assertEqual(self.client.post("/auth/step-up", json={
            "challenge": challenge, "recovery_code": codes[0], **self.correlation()},
            headers=head).status_code, 401)

    def test_round3_b3_a_reset_capable_session_is_short_lived_and_does_not_renew(self):
        """It is level 1 but can reset a password, so it must not hold a fortnight-long window."""
        tenant_id, identity_id, email, token = self.signed_in()
        codes = self.codes(tenant_id, identity_id, token)
        # Read the ordinary window first: recovering revokes every existing session, this one
        # included, which is itself the behaviour B1b depends on.
        routine = self.client.get("/auth/session",
                                  headers=self.headers(tenant_id, token)).json()["expires_at"]
        recovered = self.client.post("/auth/recover", json={
            "identifier": email, "code": codes[0], **self.correlation()},
            headers=self.headers(tenant_id)).json()
        self.assertEqual(recovered["aal"], 1)
        self.assertLess(recovered["expires_at"], routine,
                        "a reset-capable session expires sooner than an ordinary one")

        rotating, deadline = recovered["token"], recovered["expires_at"]
        for _ in range(3):
            rotated = self.client.post("/auth/rotate", json=self.correlation(),
                                       headers=self.headers(tenant_id, rotating)).json()
            self.assertEqual(rotated["expires_at"], deadline,
                             "rotation must not renew a reset capability")
            rotating = rotated["token"]

    def test_finding_11_the_log_does_not_call_a_password_change_an_authentication(self):
        tenant_id, identity_id, email, token = self.signed_in()
        self.codes(tenant_id, identity_id, token)
        events = self.client.get("/auth/events",
                                 headers=self.headers(tenant_id, token)).json()
        kinds = [e["kind"] for e in events]
        self.assertIn("recovery.codes_issued", kinds)
        self.assertEqual(kinds.count("authentication.succeeded"), 1,
                         "only the login is an authentication")


if __name__ == "__main__":
    unittest.main()
