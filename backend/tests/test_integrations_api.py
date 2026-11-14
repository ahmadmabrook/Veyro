"""MOD-012 ECO-02 over HTTP: the surface, the permission split and the id boundary.

The service suite proves the behaviour. This one proves what only the HTTP layer decides: which
permission each route charges, that authorizing a connection is a separate grant from
configuring an install, and that a malformed id is a 422 rather than a 500.
"""

from __future__ import annotations

import unittest
import uuid

from tests.support import GatedApiTestCase


class IntegrationsApiTests(GatedApiTestCase):
    def correlation(self) -> dict[str, str]:
        return {"correlation_id": str(uuid.uuid4())}

    def definition(self, **kwargs: object) -> str:
        key = str(kwargs.pop("definition_key", f"acme.a{uuid.uuid4().hex[:8]}"))
        body: dict = {
            "definition_key": key, "version": 1, "provider": "Acme", "display_name": "Acme",
            "criticality": "convenience", "support_owner": "ops", "description": "d",
            "capabilities": ["payments"], "scopes": ["payments.charge"],
            "required_scopes": ["payments.charge"],
            "config_fields": [{"name": "merchant_id", "field_type": "reference",
                               "required": True}],
            "regions": ["eu-west"],
        }
        body.update(kwargs)
        created = self.client.post("/platform/integrations", json=body)
        self.assertEqual(created.status_code, 201, created.text)
        published = self.client.post(f"/platform/integrations/{key}/1/publish")
        self.assertEqual(published.status_code, 200, published.text)
        return key

    def install(self, tenant_id: str, key: str | None = None) -> str:
        created = self.client.post("/integrations", headers=self.headers(tenant_id), json={
            "definition_key": key or self.definition(), "config": {"merchant_id": "m-1"},
            **self.correlation()})
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()["install_id"]

    def test_an_integration_is_installed_connected_and_uninstalled(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        install_id = self.install(tenant_id)
        connected = self.client.post("/integrations/connections", headers=head, json={
            "install_id": install_id, "external_account_ref": "acct_1", "region": "eu-west",
            "granted_scopes": ["payments.charge"], "vault_ref": "vault://acme/1",
            **self.correlation()})
        self.assertEqual(connected.status_code, 201, connected.text)
        listed = self.client.get("/integrations/connections", headers=head)
        self.assertEqual(len(listed.json()), 1)
        removed = self.client.post(f"/integrations/{install_id}/uninstall", headers=head,
                                   json={"reason": "switched", **self.correlation()})
        self.assertEqual(removed.json()["connections_revoked"], 1)
        self.assertEqual(self.client.get("/integrations/connections", headers=head).json(), [])

    def test_a_definition_declaring_a_secret_field_is_refused(self):
        """There is no vault here, so a config value is never a place for a credential."""
        response = self.client.post("/platform/integrations", json={
            "definition_key": "acme.leaky", "version": 1, "provider": "Acme",
            "display_name": "D", "criticality": "convenience", "support_owner": "ops",
            "description": "d", "capabilities": ["payments"], "scopes": [],
            "required_scopes": [],
            "config_fields": [{"name": "api_key", "field_type": "secret", "required": True}]})
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_malformed_id_is_a_422_and_not_a_database_exception(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        for path, body in (
            ("/integrations/not-a-uuid/configure", self.correlation()),
            ("/integrations/not-a-uuid/activate", self.correlation()),
            ("/integrations/not-a-uuid/disable", self.correlation()),
            ("/integrations/not-a-uuid/uninstall", {"reason": "x", **self.correlation()}),
            ("/integrations/connections/not-a-uuid/validate",
             {"evidence": "x", **self.correlation()}),
            ("/integrations/connections/not-a-uuid/revoke",
             {"reason": "x", **self.correlation()}),
            ("/integrations/connections/not-a-uuid/rotate",
             {"vault_ref": "v", **self.correlation()}),
            ("/integrations/runs/not-a-uuid/finish",
             {"records_read": 1, "records_written": 1, **self.correlation()}),
            ("/integrations/runs/not-a-uuid/fail", {"error": "x", **self.correlation()}),
            ("/integrations/runs/not-a-uuid/retry", self.correlation()),
            ("/integrations/runs/not-a-uuid/release", {"reason": "x", **self.correlation()}),
            ("/integrations/runs/not-a-uuid/reconciliation",
             {"local_count": 1, "provider_count": 1, "matched": 1, **self.correlation()}),
        ):
            response = self.client.post(path, headers=head, json=body)
            self.assertEqual(response.status_code, 422, f"{path}: {response.text}")
        self.assertEqual(
            self.client.get("/integrations/connections?install_id=not-a-uuid",
                            headers=head).status_code, 422)

    def test_configuring_an_integration_does_not_let_you_connect_it(self):
        """The one command that hands a third party reach is a separate grant, so a role can
        configure an integration without being able to widen who it talks to."""
        tenant_id = self.tenant()
        install_id = self.install(tenant_id)
        configurer = self.headers(tenant_id, self.grant(
            tenant_id, ["integrations.install.read", "integrations.install.write"]))
        self.assertEqual(
            self.client.get("/integrations", headers=configurer).status_code, 200)
        response = self.client.post("/integrations/connections", headers=configurer, json={
            "install_id": install_id, "external_account_ref": "acct_x", "region": "eu-west",
            "granted_scopes": ["payments.charge"], "vault_ref": "vault://x",
            **self.correlation()})
        self.assertEqual(response.status_code, 403, response.text)

    def test_uninstalling_is_a_separate_grant_from_configuring(self):
        tenant_id = self.tenant()
        install_id = self.install(tenant_id)
        configurer = self.headers(tenant_id,
                                  self.grant(tenant_id, ["integrations.install.write"]))
        response = self.client.post(f"/integrations/{install_id}/uninstall",
                                    headers=configurer,
                                    json={"reason": "x", **self.correlation()})
        self.assertEqual(response.status_code, 403, response.text)

    def test_reading_credentials_returns_metadata_and_no_secret(self):
        """There is no secret in this module to return. The reference names one kept elsewhere,
        and the response is the whole row."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id)
        install_id = self.install(tenant_id)
        self.client.post("/integrations/connections", headers=head, json={
            "install_id": install_id, "external_account_ref": "acct_1", "region": "eu-west",
            "granted_scopes": ["payments.charge"], "vault_ref": "vault://acme/1",
            **self.correlation()})
        listed = self.client.get("/integrations/credentials", headers=head)
        self.assertEqual(listed.status_code, 200, listed.text)
        row = listed.json()[0]
        self.assertEqual(row["vault_ref"], "vault://acme/1")
        self.assertEqual(
            set(row), {"credential_ref_id", "connection_id", "vault_ref", "scopes",
                       "issued_at", "expires_at", "retired_at", "supersedes"})

    def test_a_sync_run_is_routine_and_a_cursor_reset_is_not(self):
        """A connector runs on a loop, so starting one needs no step-up. Moving a cursor
        backwards costs whatever the provider charges to re-read, so it does."""
        tenant_id = self.tenant()
        runner = self.headers(tenant_id, self.grant(tenant_id, ["integrations.sync.run"]))
        started = self.client.post("/integrations/runs", headers=runner, json={
            "connection_id": str(uuid.uuid4()), "resource": "members", **self.correlation()})
        # Routine: the gate lets it through and the service refuses the unknown connection.
        self.assertEqual(started.status_code, 404, started.text)
        resetter = self.headers(tenant_id, self.grant(tenant_id, ["integrations.sync.reset"]))
        reset = self.client.post("/integrations/cursors/reset", headers=resetter, json={
            "connection_id": str(uuid.uuid4()), "resource": "members", "position": "p",
            "observed_at": "2026-11-01T00:00:00+00:00", "reason": "backfill",
            **self.correlation()})
        self.assertEqual(reset.status_code, 403, reset.text)

    def test_the_definition_catalogue_is_readable_and_versioned(self):
        key = self.definition()
        listed = self.client.get("/platform/integrations?status=published")
        self.assertIn(key, [d["definition_key"] for d in listed.json()])
        detail = self.client.get(f"/platform/integrations/{key}")
        self.assertEqual(detail.json()["required_scopes"], ["payments.charge"])
        self.assertNotIn("_declared", detail.json())


if __name__ == "__main__":
    unittest.main()
