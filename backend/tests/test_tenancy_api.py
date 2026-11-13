"""MOD-004 tenancy API tests against a real PostgreSQL with row-level security in force.

These are integration tests on purpose. The isolation they check is a property of the database,
not of the Python, so a suite with a mocked connection would assert nothing: every cross-tenant
case here would pass against a mock while the real policy was missing.

The database must already carry the migrations -- backend/scripts/verify_db.sh applies them, and
CI runs it before this suite. Each test provisions its own tenants with unique external keys, so
no test depends on another's rows and nothing needs tearing down.
"""

from __future__ import annotations

import unittest
import uuid

from tests.support import GatedApiTestCase


def _envelope(external_key: str, **overrides: object) -> dict[str, object]:
    body = {
        "external_key": external_key,
        "display_name": "Test Gym",
        "region": "eu-west",
        "actor_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
    }
    body.update(overrides)
    return body


class TenancyApiTests(GatedApiTestCase):
    """Platform-plane routes are ungated (see the module docstring in app/main.py), but the
    hierarchy routes under them are not, so this suite still needs an owner."""

    def provision(self, **overrides: object) -> dict[str, object]:
        response = self.client.post(
            "/platform/tenants", json=_envelope(f"t-{uuid.uuid4().hex}", **overrides)
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def active_tenant(self) -> str:
        """An active tenant with an owner, since the hierarchy routes are gated now."""
        tenant = self.provision()
        tenant_id = str(tenant["tenant_id"])
        response = self.client.post(
            f"/platform/tenants/{tenant_id}/activate",
            json={"actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self._owners[tenant_id] = self.make_owner(tenant_id)[1]
        return tenant_id

    # ------------------------------------------------------------------ lifecycle

    def test_provision_creates_a_provisioned_tenant(self) -> None:
        tenant = self.provision()
        self.assertEqual(tenant["status"], "provisioned")
        self.assertEqual(tenant["version"], 1)

    def test_provision_is_idempotent_on_the_idempotency_key(self) -> None:
        body = _envelope(f"t-{uuid.uuid4().hex}")
        first = self.client.post("/platform/tenants", json=body)
        second = self.client.post("/platform/tenants", json=body)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200, "a replay must not create a second tenant")
        self.assertEqual(first.json()["tenant_id"], second.json()["tenant_id"])
        history = self.client.get(f"/platform/tenants/{first.json()['tenant_id']}/history")
        self.assertEqual(len(history.json()), 1, "a replay must not write a second history row")

    def test_same_external_key_under_a_new_key_is_a_conflict(self) -> None:
        shared = f"t-{uuid.uuid4().hex}"
        self.assertEqual(
            self.client.post("/platform/tenants", json=_envelope(shared)).status_code, 201
        )
        clash = self.client.post("/platform/tenants", json=_envelope(shared))
        self.assertEqual(clash.status_code, 409)
        self.assertEqual(clash.json()["error"], "external_key_exists")

    def test_malformed_envelope_is_rejected(self) -> None:
        response = self.client.post(
            "/platform/tenants", json=_envelope("t-bad", actor_id="not-a-uuid")
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "bad_actor_id")

    def test_full_lifecycle_is_recorded(self) -> None:
        tenant_id = str(self.provision()["tenant_id"])
        for action, expected in (
            ("activate", "active"),
            ("suspend", "suspended"),
            ("archive", "archived"),
        ):
            response = self.client.post(
                f"/platform/tenants/{tenant_id}/{action}",
                json={"actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], expected)

        history = self.client.get(f"/platform/tenants/{tenant_id}/history").json()
        self.assertEqual(
            [row["to_status"] for row in history],
            ["provisioned", "active", "suspended", "archived"],
        )

    def test_illegal_transition_is_refused(self) -> None:
        tenant_id = str(self.provision()["tenant_id"])
        response = self.client.post(
            f"/platform/tenants/{tenant_id}/archive",
            json={"actor_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 409, "archive is not reachable from provisioned")
        self.assertEqual(
            self.client.get(f"/platform/tenants/{tenant_id}").json()["status"], "provisioned"
        )

    def test_version_mismatch_is_refused(self) -> None:
        tenant_id = str(self.provision()["tenant_id"])
        response = self.client.post(
            f"/platform/tenants/{tenant_id}/activate",
            json={
                "actor_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4()),
                "expected_version": 99,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "version_mismatch")

    def test_hard_deletion_is_gated(self) -> None:
        tenant_id = str(self.provision()["tenant_id"])
        response = self.client.delete(f"/platform/tenants/{tenant_id}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "hard_deletion_gated")
        self.assertEqual(self.client.get(f"/platform/tenants/{tenant_id}").status_code, 200)

    def test_unknown_tenant_is_not_found(self) -> None:
        response = self.client.get(f"/platform/tenants/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------ isolation

    def test_a_tenant_reads_only_its_own_hierarchy(self) -> None:
        first, second = self.active_tenant(), self.active_tenant()
        created = self.client.post(
            "/organizations",
            headers=self.headers(first),
            json={"legal_name": "First ehf", "country_code": "IS"},
        )
        self.assertEqual(created.status_code, 201, created.text)

        mine = self.client.get("/organizations", headers=self.headers(first)).json()
        theirs = self.client.get("/organizations", headers=self.headers(second)).json()
        self.assertEqual(len(mine), 1)
        self.assertEqual(theirs, [], "a second tenant must not see the first tenant's rows")

    def test_a_brand_cannot_be_parented_to_another_tenants_organization(self) -> None:
        first, second = self.active_tenant(), self.active_tenant()
        organization = self.client.post(
            "/organizations",
            headers=self.headers(first),
            json={"legal_name": "First ehf", "country_code": "IS"},
        ).json()
        stolen = self.client.post(
            "/brands",
            headers=self.headers(second),
            json={"organization_id": organization["organization_id"], "brand_name": "Stolen"},
        )
        self.assertEqual(stolen.status_code, 404, "the composite foreign key must refuse this")

    def test_hierarchy_round_trips_within_one_tenant(self) -> None:
        tenant_id = self.active_tenant()
        headers = self.headers(tenant_id)
        organization = self.client.post(
            "/organizations", headers=headers,
            json={"legal_name": "Acme ehf", "country_code": "IS"},
        ).json()
        brand = self.client.post(
            "/brands", headers=headers,
            json={"organization_id": organization["organization_id"], "brand_name": "Acme City"},
        ).json()
        location = self.client.post(
            "/locations", headers=headers,
            json={
                "brand_id": brand["brand_id"],
                "location_name": "Laugavegur",
                "timezone": "Atlantic/Reykjavik",
            },
        )
        self.assertEqual(location.status_code, 201, location.text)
        listed = self.client.get("/locations", headers=headers).json()
        self.assertEqual([row["location_name"] for row in listed], ["Laugavegur"])

    def test_a_missing_or_malformed_tenant_header_is_refused(self) -> None:
        self.assertEqual(self.client.get("/organizations").status_code, 422)
        self.assertEqual(
            self.client.get("/organizations", headers={"X-Veyro-Tenant": "nope"}).status_code, 422
        )

    def test_an_unknown_tenant_is_refused_before_it_reaches_the_database(self) -> None:
        """Since MOD-008 the hierarchy routes are gated, so this is refused earlier.

        It used to assert a 404 from the composite foreign key. There is now no session for a
        tenant nobody has bootstrapped, so there is nobody to authorize and the request stops at
        the gate. The foreign key still refuses the write -- isolation check 7 proves it against
        the database directly -- but no HTTP caller can get far enough to find out.
        """
        ghost = str(uuid.uuid4())
        for call in (
            lambda: self.client.post(
                "/organizations", headers={"X-Veyro-Tenant": ghost},
                json={"legal_name": "Ghost ehf", "country_code": "IS"}),
            lambda: self.client.get("/organizations", headers={"X-Veyro-Tenant": ghost}),
        ):
            self.assertEqual(call().status_code, 422)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
