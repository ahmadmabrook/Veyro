"""Signing in with a passkey, against a real PostgreSQL and a real signature.

**This is the end of MOD-007's longest-standing deliberate gap**, and what makes it a test
rather than a demonstration is that the private key lives in the test: every assertion here is
signed by a key the browser would hold, so a server that accepted anything less would pass
nothing below.

`test_webauthn.py` proves the verifier against every way to break an assertion and needs no
database. What this file proves is the half only the wired-up service can show: the challenge
is single-use and bound to the identity it was issued for, the sign-count clone check is the
one MOD-007 already had, a verified assertion opens a session at the level its factor reaches,
and **AAL 3 is reachable at last** -- which five modules' worth of `reachable: false` said it
was not.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest
import uuid

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_identity_pool, make_platform_pool, make_tenant_pool
from app.main import create_app

DSN = os.environ.get("VEYRO_DATABASE_URL", "")
RP_ID = "veyro.test"
ORIGIN = "https://veyro.test"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class Authenticator:
    """A P-256 authenticator: a key pair, a credential id and a counter that goes up."""

    def __init__(self) -> None:
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0

    @property
    def spki(self) -> bytes:
        return self.private.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def assert_(
        self, challenge: str, *, rp_id: str = RP_ID, origin: str = ORIGIN,
        uv: bool = True, be: bool = False, kind: str = "webauthn.get",
        sign_count: int | None = None,
    ) -> dict[str, str]:
        """One assertion, signed. `sign_count` defaults to one more than the last."""
        self.sign_count = self.sign_count + 1 if sign_count is None else sign_count
        client = json.dumps({"type": kind, "challenge": challenge, "origin": origin}).encode()
        flags = 0x01 | (0x04 if uv else 0) | (0x08 if be else 0)
        authenticator = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags])
                         + self.sign_count.to_bytes(4, "big"))
        signature = self.private.sign(
            authenticator + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "credential_id": b64url(self.credential_id),
            "client_data_json": b64url(client),
            "authenticator_data": b64url(authenticator),
            "signature": b64url(bytes(signature)),
        }


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class PasskeyLoginTests(unittest.TestCase):
    PASSWORD = "a-long-enough-password"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tenant_pool = make_tenant_pool(DSN)
        cls._platform_pool = make_platform_pool(DSN)
        cls._identity_pool = make_identity_pool(DSN)
        cls._app = create_app(
            Settings(environment="local", release="test", database_url=DSN,
                     webauthn_rp_id=RP_ID, webauthn_origins=(ORIGIN,)),
            tenant_pool=cls._tenant_pool, platform_pool=cls._platform_pool,
            identity_pool=cls._identity_pool)
        cls._client_cm = TestClient(cls._app)
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

    def headers(self, tenant_id: str, token: str | None = None) -> dict[str, str]:
        head = {"X-Veyro-Tenant": tenant_id}
        if token:
            head["Authorization"] = f"Bearer {token}"
        return head

    def tenant(self) -> str:
        response = self.client.post("/platform/tenants", json={
            "external_key": f"passkey-{uuid.uuid4()}", "display_name": "Passkey Gym",
            "region": "eu-west", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["tenant_id"])

    def enrolled(self, *, be: bool = False) -> tuple[str, str, str, Authenticator]:
        """A tenant, an identity, its email and an authenticator enrolled against it."""
        tenant_id = self.tenant()
        email = f"user-{uuid.uuid4().hex[:10]}@acme.test"
        created = self.client.post("/identities", json={
            "display_name": "Staff Member", "email": email, "password": self.PASSWORD,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        identity_id = created.json()["identity_id"]

        signed_in = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD, "device_fingerprint": "device-a",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        token = signed_in.json()["token"]

        key = Authenticator()
        enrolment = self.client.post(
            f"/identities/{identity_id}/passkeys",
            json={"webauthn_credential_id": b64url(key.credential_id),
                  "public_key": b64url(key.spki), "backed_up": be, **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(enrolment.status_code, 201, enrolment.text)
        self.assertTrue(enrolment.json()["verifiable"])
        self.assertEqual(enrolment.json()["cose_algorithm"], -7)
        return tenant_id, identity_id, email, key

    def challenge(self, tenant_id: str, identifier: str) -> str:
        response = self.client.post("/auth/passkey/challenge",
                                    json={"identifier": identifier, **self.correlation()},
                                    headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        return str(response.json()["challenge"])

    def sign_in(self, tenant_id: str, identifier: str, assertion: dict[str, str],
                challenge: str, **extra):
        return self.client.post("/auth/passkey/login", json={
            "identifier": identifier, "challenge": challenge, **assertion,
            "device_fingerprint": "device-a", **self.correlation(), **extra},
            headers=self.headers(tenant_id))

    # ------------------------------------------------------------------ the happy path

    def test_a_device_bound_passkey_opens_a_level_three_session(self) -> None:
        # **The assertion this whole piece of work exists for.** For five modules
        # `/auth/require/*` answered that level 3 was unreachable by anybody, because it needs
        # a hardware authenticator and nothing verified a signature. This is what changed.
        tenant_id, identity_id, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        response = self.sign_in(tenant_id, email, key.assert_(challenge), challenge)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["aal"], 3)
        self.assertEqual(body["factors"], ["passkey_hardware"])
        self.assertEqual(body["identity_id"], identity_id)

    def test_a_synced_passkey_stops_at_level_two(self) -> None:
        # The `BE` flag the authenticator signed over decides it, and a caller cannot ask for
        # the other answer: a key that may leave its authenticator is a strong factor and not
        # a hardware-bound one.
        tenant_id, _, email, key = self.enrolled(be=True)
        challenge = self.challenge(tenant_id, email)
        response = self.sign_in(tenant_id, email, key.assert_(challenge, be=True), challenge)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["aal"], 2)
        self.assertEqual(response.json()["factors"], ["passkey_synced"])

    def test_a_level_three_session_reaches_a_privileged_action(self) -> None:
        # `require_assurance` is what MOD-008 asks before a `privileged` action, and its own
        # docstring said the bar could not be met today. It can.
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        token = self.sign_in(tenant_id, email, key.assert_(challenge), challenge).json()["token"]
        gate = self.client.get("/auth/require/privileged",
                               headers=self.headers(tenant_id, token))
        self.assertEqual(gate.status_code, 200, gate.text)
        self.assertFalse(gate.json()["step_up_required"], gate.text)
        self.assertEqual(gate.json()["required_aal"], 3)
        self.assertTrue(gate.json()["reachable"])

    def test_the_counter_advances_and_a_second_sign_in_works(self) -> None:
        tenant_id, _, email, key = self.enrolled()
        for _ in range(3):
            challenge = self.challenge(tenant_id, email)
            response = self.sign_in(tenant_id, email, key.assert_(challenge), challenge)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(key.sign_count, 3)

    # ------------------------------------------------------------------ the refusals

    def refused(self, response) -> None:
        """Every refusal is the same 401 with the same body. That is the control."""
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["error"], "authentication_failed")

    def test_a_challenge_is_single_use(self) -> None:
        # Replaying an assertion is the attack a nonce exists to stop, and the nonce is
        # consumed on *any* attempt rather than only on a successful one.
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        assertion = key.assert_(challenge)
        self.assertEqual(self.sign_in(tenant_id, email, assertion, challenge).status_code, 200)
        self.refused(self.sign_in(tenant_id, email, assertion, challenge))

    def test_a_failed_attempt_spends_the_challenge_too(self) -> None:
        # **The opposite of "verify, decide, then consume"**, deliberately: that rule is about
        # not destroying a credential the owner cannot replace. A challenge that survived a
        # failed attempt is a replay window, and a new one costs a round trip.
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        bad = key.assert_(challenge)
        bad["signature"] = b64url(b64url_bytes(bad["signature"])[:-1] + b"\x00")
        self.refused(self.sign_in(tenant_id, email, bad, challenge))
        # And the good assertion over the same challenge is refused now.
        self.refused(self.sign_in(tenant_id, email, key.assert_(challenge), challenge))

    def test_another_identity_cannot_spend_this_challenge(self) -> None:
        # `_pending_challenge` filters on identity, nonce and kind together, which is what
        # stops one identity's nonce being presented with another's identifier.
        tenant_id, _, email, key = self.enrolled()
        other = f"user-{uuid.uuid4().hex[:10]}@acme.test"
        self.client.post("/identities", json={
            "display_name": "Other", "email": other, "password": self.PASSWORD,
            **self.correlation()}, headers=self.headers(tenant_id))
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(tenant_id, other, key.assert_(challenge), challenge))

    def test_an_assertion_for_another_relying_party_is_refused(self) -> None:
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(
            tenant_id, email, key.assert_(challenge, rp_id="evil.test"), challenge))

    def test_an_assertion_from_another_origin_is_refused(self) -> None:
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(
            tenant_id, email, key.assert_(challenge, origin="https://veyro.test.evil.com"),
            challenge))

    def test_an_unverified_user_is_refused(self) -> None:
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(tenant_id, email, key.assert_(challenge, uv=False), challenge))

    def test_a_registration_ceremony_does_not_open_a_session(self) -> None:
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(
            tenant_id, email, key.assert_(challenge, kind="webauthn.create"), challenge))

    def test_another_authenticator_cannot_sign_for_this_credential(self) -> None:
        # The credential id is looked up and the stored public key is what verifies, so holding
        # somebody's credential id buys nothing.
        tenant_id, _, email, key = self.enrolled()
        impostor = Authenticator()
        impostor.credential_id = key.credential_id
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(tenant_id, email, impostor.assert_(challenge), challenge))

    def test_an_unenrolled_credential_is_refused(self) -> None:
        tenant_id, _, email, _ = self.enrolled()
        stranger = Authenticator()
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(tenant_id, email, stranger.assert_(challenge), challenge))

    def test_a_repeated_sign_count_revokes_the_passkey_and_every_session(self) -> None:
        # MOD-007's clone check, reached through the verified path -- one implementation, so
        # two counters cannot drift. The passkey is revoked on sight and the identity's live
        # sessions go with it.
        tenant_id, identity_id, email, key = self.enrolled()
        first = self.challenge(tenant_id, email)
        token = self.sign_in(tenant_id, email, key.assert_(first), first).json()["token"]
        second = self.challenge(tenant_id, email)
        self.refused(self.sign_in(
            tenant_id, email, key.assert_(second, sign_count=1), second))
        # The session opened a moment ago is gone.
        self.assertEqual(
            self.client.get(f"/identities/{identity_id}/sessions",
                            headers=self.headers(tenant_id, token)).status_code, 401)
        # And the passkey cannot be used again.
        third = self.challenge(tenant_id, email)
        self.refused(self.sign_in(tenant_id, email, key.assert_(third), third))

    def test_a_suspended_identity_cannot_sign_in_with_a_passkey(self) -> None:
        # Four independent controls read `iam.identities.status`; this is the fifth path and it
        # reads it too, because a control consulted on one path and not its sibling is the
        # shape this repository records in four modules.
        tenant_id, identity_id, email, key = self.enrolled()
        with self._identity_pool.connection() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            conn.execute("UPDATE iam.identities SET status = 'suspended'"
                         " WHERE identity_id = %s", (identity_id,))
        challenge = self.challenge(tenant_id, email)
        self.refused(self.sign_in(tenant_id, email, key.assert_(challenge), challenge))

    # ------------------------------------------------------------------ the ceremony itself

    def test_the_challenge_route_answers_the_same_for_an_unknown_identifier(self) -> None:
        # **The anti-enumeration property.** A ceremony that said "no passkey is enrolled
        # here" would be a directory of which addresses exist, which is the oracle MOD-007
        # paid a blocking defect for once already.
        tenant_id, _, email, _ = self.enrolled()
        known = self.client.post("/auth/passkey/challenge", json={
            "identifier": email, **self.correlation()}, headers=self.headers(tenant_id))
        unknown = self.client.post("/auth/passkey/challenge", json={
            "identifier": f"nobody-{uuid.uuid4().hex[:8]}@acme.test", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(sorted(known.json()), sorted(unknown.json()))
        self.assertNotEqual(known.json()["challenge"], unknown.json()["challenge"])

    def test_an_assertion_against_an_unissued_challenge_is_refused(self) -> None:
        # Which is what makes the uniform challenge response safe: the nonce for an identity
        # that does not exist was never stored, so signing it proves nothing.
        tenant_id, _, email, key = self.enrolled()
        unknown = self.client.post("/auth/passkey/challenge", json={
            "identifier": f"nobody-{uuid.uuid4().hex[:8]}@acme.test", **self.correlation()},
            headers=self.headers(tenant_id)).json()["challenge"]
        self.refused(self.sign_in(tenant_id, email, key.assert_(unknown), unknown))

    def test_a_standard_base64_field_is_a_422_rather_than_a_different_signature(self) -> None:
        # Every WebAuthn field is base64url and `_b64url` is strict about it: the two alphabets
        # agree on most byte strings and differ on the rest, so accepting either would mean one
        # value decoding two ways.
        tenant_id, _, email, key = self.enrolled()
        challenge = self.challenge(tenant_id, email)
        assertion = key.assert_(challenge)
        assertion["signature"] = base64.b64encode(
            b"\xfb\xff" + b64url_bytes(assertion["signature"])).decode()
        response = self.sign_in(tenant_id, email, assertion, challenge)
        self.assertEqual(response.status_code, 422, response.text)

    def test_an_unparseable_public_key_is_refused_at_enrolment(self) -> None:
        # Where somebody can read the reason, rather than at the moment they are signing in.
        tenant_id = self.tenant()
        email = f"user-{uuid.uuid4().hex[:10]}@acme.test"
        created = self.client.post("/identities", json={
            "display_name": "Staff", "email": email, "password": self.PASSWORD,
            **self.correlation()}, headers=self.headers(tenant_id))
        identity_id = created.json()["identity_id"]
        token = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD, **self.correlation()},
            headers=self.headers(tenant_id)).json()["token"]
        response = self.client.post(
            f"/identities/{identity_id}/passkeys",
            json={"webauthn_credential_id": b64url(os.urandom(32)),
                  "public_key": b64url(b"\x30" + b"\x01" * 48), **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["error"], "public_key_unusable")


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class NoRelyingPartyTests(unittest.TestCase):
    """A build that has not stated its relying party refuses, and says which thing is missing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tenant_pool = make_tenant_pool(DSN)
        cls._platform_pool = make_platform_pool(DSN)
        cls._identity_pool = make_identity_pool(DSN)
        app = create_app(
            Settings(environment="local", release="test", database_url=DSN),
            tenant_pool=cls._tenant_pool, platform_pool=cls._platform_pool,
            identity_pool=cls._identity_pool)
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        cls._tenant_pool.close()
        cls._platform_pool.close()
        cls._identity_pool.close()

    def test_a_passkey_login_is_a_422_naming_the_configuration(self) -> None:
        # **Not a 401.** "Wrong credential" is what a 401 says, and the one person who could
        # fix an unconfigured relying party would read it as their own mistake.
        tenant = self.client.post("/platform/tenants", json={
            "external_key": f"passkey-{uuid.uuid4()}", "display_name": "No RP",
            "region": "eu-west", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4()),
        }).json()["tenant_id"]
        response = self.client.post("/auth/passkey/login", json={
            "identifier": "someone@acme.test", "challenge": b64url(os.urandom(32)),
            "credential_id": b64url(os.urandom(32)),
            "client_data_json": b64url(b"{}"), "authenticator_data": b64url(b"\x00" * 37),
            "signature": b64url(b"\x00" * 64), "correlation_id": str(uuid.uuid4()),
        }, headers={"X-Veyro-Tenant": tenant})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["error"], "webauthn_not_configured")


if __name__ == "__main__":
    unittest.main()
