"""A tenant that can actually be used, for suites whose routes are behind the MOD-008 gate.

Every product route now requires a session holding a permission, so a test that wants to publish
a configuration value or issue an invoice needs an identity, a session, a role and -- for
anything classed `financial` -- a stepped-up session. Building that by hand in each of the three
product suites would be a hundred lines of fixture repeated three times and wrong in three
different ways.

`tenant()` returns a tenant that already has an owner, and `headers()` carries that owner's
token, so a suite written before the gate existed keeps working by changing its base class.

**The fixture goes through the service layer, not HTTP.** Setting a tenant up is not what these
suites are testing, and the HTTP path would spend a dozen scrypt hashes per tenant -- at 16 MiB
each that is most of the suite's wall-clock. The one thing it does not shortcut is the gate
itself: the owner gets its permissions from a real bootstrap and a real step-up, so a test that
passes is a test whose caller genuinely held what the route demanded.
"""

from __future__ import annotations

import os
import unittest
import uuid

from fastapi.testclient import TestClient

from app.authorization import service as authz
from app.config import Settings
from app.db import make_identity_pool, make_platform_pool, make_tenant_pool
from app.identity import service as identity
from app.main import create_app

DSN = os.environ.get("VEYRO_DATABASE_URL", "")


@unittest.skipUnless(DSN, "VEYRO_DATABASE_URL is not set")
class GatedApiTestCase(unittest.TestCase):
    """Base for product suites. `tenant()` hands back a tenant with a fully-privileged owner."""

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

    def setUp(self) -> None:
        self._owners: dict[str, str] = {}
        #: The owner's own identity id, for the tests that need an actor to *be* somebody --
        #: a separation-of-duties refusal cannot be written without it.
        self._owner_identities: dict[str, str] = {}

    # ------------------------------------------------------------------ fixtures

    def correlation(self) -> dict[str, str]:
        return {"correlation_id": str(uuid.uuid4())}

    def tenant(self, *, with_owner: bool = True) -> str:
        """A provisioned tenant. With an owner unless a test wants to see an ungated caller."""
        response = self.client.post("/platform/tenants", json={
            "external_key": f"t-{uuid.uuid4()}", "display_name": "Test Gym",
            "region": "eu-west", "actor_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.text)
        tenant_id = str(response.json()["tenant_id"])
        if with_owner:
            identity_id, token = self.make_owner(tenant_id)
            self._owners[tenant_id] = token
            self._owner_identities[tenant_id] = identity_id
        return tenant_id

    def make_owner(self, tenant_id: str) -> tuple[str, str]:
        """An identity holding every permission, on a stepped-up session.

        Two recovery codes rather than ten: the step-up needs one and each costs a scrypt hash.
        """
        correlation = str(uuid.uuid4())
        created = identity.register_identity(
            self._identity_pool, tenant_id, display_name="Owner",
            email=f"owner-{uuid.uuid4().hex[:10]}@acme.test", password=self.PASSWORD,
            correlation_id=correlation,
        )
        identity_id = str(created["identity_id"])
        session = identity.authenticate(
            self._identity_pool, tenant_id, identifier=str(created["email"]),
            password=self.PASSWORD, correlation_id=correlation,
            device_fingerprint=f"fixture-{uuid.uuid4().hex[:8]}",
        )
        authz.bootstrap(self._identity_pool, tenant_id, identity_id=identity_id,
                        role_key="tenant_admin", display_name="Tenant Administrator",
                        correlation_id=correlation)
        codes = identity.issue_recovery_codes(
            self._identity_pool, tenant_id, identity_id=identity_id,
            correlation_id=correlation, current_password=self.PASSWORD, count=2,
        )["codes"]
        asked = identity.require_assurance(
            self._identity_pool, tenant_id, token=str(session["token"]),
            action_class="financial",
        )
        stepped = identity.complete_step_up(
            self._identity_pool, tenant_id, token=str(session["token"]),
            challenge=str(asked["challenge"]), recovery_code=codes[0],
            correlation_id=correlation,
        )
        return identity_id, str(stepped["token"])

    def owner_token(self, tenant_id: str) -> str:
        return self._owners[tenant_id]

    def owner_identity(self, tenant_id: str) -> str:
        return self._owner_identities[tenant_id]

    def headers(self, tenant_id: str, token: str | None = None) -> dict[str, str]:
        """The tenant claim plus, by default, that tenant's owner session."""
        head = {"X-Veyro-Tenant": tenant_id}
        bearer = token if token is not None else self._owners.get(tenant_id)
        if bearer:
            head["Authorization"] = f"Bearer {bearer}"
        return head

    def fresh_identity(self, tenant_id: str, label: str = "Nobody") -> tuple[str, str]:
        """A registered, authenticated identity in this tenant, holding no role.

        Its session is AAL 1: a password only. A test that wants a stepped-up one goes through
        `make_owner`, which pays for a recovery code.
        """
        correlation = str(uuid.uuid4())
        created = identity.register_identity(
            self._identity_pool, tenant_id, display_name=label,
            email=f"{label.lower()}-{uuid.uuid4().hex[:10]}@acme.test", password=self.PASSWORD,
            correlation_id=correlation,
        )
        session = identity.authenticate(
            self._identity_pool, tenant_id, identifier=str(created["email"]),
            password=self.PASSWORD, correlation_id=correlation,
            device_fingerprint=f"{label.lower()}-{uuid.uuid4().hex[:8]}",
        )
        return str(created["identity_id"]), str(session["token"])

    def unprivileged(self, tenant_id: str) -> str:
        """A session in this tenant holding no role at all, for testing the gate itself."""
        return self.fresh_identity(tenant_id)[1]

    def grant(self, tenant_id: str, permissions: list[str]) -> str:
        """A session holding exactly these permissions, and nothing else.

        The role is created and assigned by the tenant's owner over HTTP, so the fixture itself
        passes through the same gate every other caller does -- a privilege the fixture could
        not obtain honestly is one these tests must not hand out.
        """
        owner = self.headers(tenant_id, self.owner_token(tenant_id))
        role_key = f"scoped_{uuid.uuid4().hex[:8]}"
        created = self.client.post("/authz/roles", json={
            "role_key": role_key, "display_name": "Scoped", "permissions": permissions,
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        identity_id, token = self.fresh_identity(tenant_id, "Scoped")
        assigned = self.client.post("/authz/assignments", json={
            "identity_id": identity_id, "role_key": role_key, **self.correlation()},
            headers=owner)
        self.assertEqual(assigned.status_code, 201, assigned.text)
        return token

    def stepped_grant(self, tenant_id: str, permissions: list[str]) -> str:
        """A session holding exactly these permissions, **stepped up to AAL 2**.

        `grant` returns an AAL 1 session, which is enough for a routine permission and refused
        for anything `catalog.action_class` marks `financial`. A separation of duties over a
        financial act needs two stepped-up identities and there can only be one owner --
        `authz.bootstrap` refuses once any assignment exists -- so the second one is built
        here: registered, granted its role by the owner over HTTP, and stepped up against a
        recovery code of its own.

        Two recovery codes rather than ten, for `make_owner`'s reason: each costs a scrypt.
        """
        owner = self.headers(tenant_id, self.owner_token(tenant_id))
        role_key = f"stepped_{uuid.uuid4().hex[:8]}"
        created = self.client.post("/authz/roles", json={
            "role_key": role_key, "display_name": "Stepped", "permissions": permissions,
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        identity_id, token = self.fresh_identity(tenant_id, "Stepped")
        assigned = self.client.post("/authz/assignments", json={
            "identity_id": identity_id, "role_key": role_key, **self.correlation()},
            headers=owner)
        self.assertEqual(assigned.status_code, 201, assigned.text)
        correlation = str(uuid.uuid4())
        codes = identity.issue_recovery_codes(
            self._identity_pool, tenant_id, identity_id=identity_id,
            correlation_id=correlation, current_password=self.PASSWORD, count=2,
        )["codes"]
        asked = identity.require_assurance(
            self._identity_pool, tenant_id, token=token, action_class="financial")
        stepped = identity.complete_step_up(
            self._identity_pool, tenant_id, token=token,
            challenge=str(asked["challenge"]), recovery_code=codes[0],
            correlation_id=correlation)
        return str(stepped["token"])
