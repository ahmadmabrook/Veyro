"""MOD-012 ECO-02 service against a real database.

The properties worth a database are the ones a mock would assert into existence: that an install
carries the definition it was made against rather than today's, that an uninstall actually
revokes what it says it revokes, that a rotation leaves the old reference readable, and that a
run cannot start against a connection nobody validated.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

import psycopg

from app.db import platform_scope, tenant_scope
from app.errors import Conflict, InvalidRequest
from app.integrations import service as integrations
from tests.support import GatedApiTestCase

ACTOR = "33333333-3333-4333-8333-333333333333"
NOW = datetime.now(UTC)


class IntegrationsTestCase(GatedApiTestCase):
    def correlate(self) -> str:
        return str(uuid.uuid4())

    def outbox(self, tenant_id: str, event_type: str) -> list[dict]:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            # `ORDER BY occurred_at, event_id`: without it the order is whatever the planner
            # returns, and a test asserting a *sequence* of events passes or fails by luck.
            # It did exactly that in a full run after passing alone.
            rows = conn.execute(
                "SELECT payload FROM plt01.evt_outbox WHERE event_type = %s"
                " ORDER BY occurred_at, event_id", (event_type,)
            ).fetchall()
        return [r[0] for r in rows]

    def definition(self, **kwargs: object) -> str:
        """A published definition version. The key is unique per call so suites do not collide
        in the shared platform catalogue, which is not tenant-scoped."""
        key = str(kwargs.pop("definition_key", f"acme.p{uuid.uuid4().hex[:8]}"))
        body: dict = {
            "version": 1, "provider": "Acme", "display_name": "Acme Payments",
            "criticality": "critical", "support_owner": "platform-ops",
            "description": "Takes card payments", "capabilities": ["payments"],
            "scopes": ["payments.charge", "payments.refund"],
            "required_scopes": ["payments.charge"],
            "config_fields": [{"name": "merchant_id", "field_type": "reference",
                               "required": True}],
            "regions": ["eu-west"],
        }
        body.update(kwargs)
        integrations.register_definition(self._platform_pool, definition_key=key, **body)
        if body.get("publish", True):
            integrations.publish_definition(self._platform_pool, definition_key=key,
                                            version=int(body["version"]))
        return key

    def install(self, tenant_id: str, key: str | None = None, **kwargs: object) -> dict:
        definition_key = key or self.definition()
        return integrations.install_integration(
            self._tenant_pool, self._platform_pool, tenant_id,
            definition_key=definition_key, config={"merchant_id": "m-1"},
            actor_id=ACTOR, correlation_id=self.correlate(), **kwargs,
        )

    def connect(self, tenant_id: str, install_id: str, **kwargs: object) -> dict:
        body: dict = {"external_account_ref": f"acct_{uuid.uuid4().hex[:6]}",
                      "region": "eu-west", "granted_scopes": ["payments.charge"],
                      "vault_ref": "vault://acme/live-1"}
        body.update(kwargs)
        return integrations.authorize_connection(
            self._tenant_pool, tenant_id, install_id=install_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body,
        )

    def ready(self, tenant_id: str) -> tuple[str, str]:
        """An active install with a validated connection, which is what a run needs."""
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        integrations.validate_connection(
            self._tenant_pool, tenant_id, connection["connection_id"],
            evidence="test charge accepted", actor_id=ACTOR,
            correlation_id=self.correlate())
        integrations.configure_install(
            self._tenant_pool, tenant_id, installed["install_id"],
            fallback_plan="manual terminal", reconciliation_plan="daily settlement file",
            exit_plan="export and switch", actor_id=ACTOR, correlation_id=self.correlate())
        integrations.activate_install(
            self._tenant_pool, tenant_id, installed["install_id"], actor_id=ACTOR,
            correlation_id=self.correlate())
        return installed["install_id"], connection["connection_id"]


class DefinitionTests(IntegrationsTestCase):
    def test_a_draft_cannot_be_installed(self):
        tenant_id = self.tenant()
        key = f"acme.d{uuid.uuid4().hex[:8]}"
        integrations.register_definition(
            self._platform_pool, definition_key=key, version=1, provider="Acme",
            display_name="D", criticality="convenience", support_owner="ops",
            description="d", capabilities=["payments"], scopes=[], required_scopes=[])
        # The version is named: with none published, asking for "the current one" is a
        # NotFound about the catalogue rather than the refusal this test is about.
        with self.assertRaises(Conflict):
            integrations.install_integration(
                self._tenant_pool, self._platform_pool, tenant_id, definition_key=key,
                version=1, actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_retired_version_cannot_be_installed_and_existing_installs_keep_working(self):
        tenant_id = self.tenant()
        other = self.tenant()
        key = self.definition()
        self.install(tenant_id, key)
        integrations.retire_definition(self._platform_pool, definition_key=key, version=1)
        with self.assertRaises(Conflict):
            self.install(other, key, version=1)
        self.assertEqual(
            integrations.list_installs(self._tenant_pool, tenant_id)[0]["definition_key"], key)

    def test_a_successor_that_drops_a_capability_is_refused_at_registration(self):
        key = self.definition()
        with self.assertRaises(InvalidRequest):
            integrations.register_definition(
                self._platform_pool, definition_key=key, version=2, provider="Acme",
                display_name="D", criticality="critical", support_owner="ops",
                description="d", capabilities=["accounting"],
                scopes=["payments.charge"], required_scopes=["payments.charge"])

    def test_a_version_must_climb(self):
        key = self.definition()
        with self.assertRaises(Conflict):
            integrations.register_definition(
                self._platform_pool, definition_key=key, version=1, provider="Acme",
                display_name="D", criticality="critical", support_owner="ops",
                description="d", capabilities=["payments"], scopes=[], required_scopes=[])


class InstallTests(IntegrationsTestCase):
    def test_an_install_carries_the_definition_it_was_made_against(self):
        """Validating against today's catalogue would refuse a value correct for this install,
        or accept one that is not."""
        tenant_id = self.tenant()
        key = self.definition()
        installed = self.install(tenant_id, key)
        integrations.register_definition(
            self._platform_pool, definition_key=key, version=2, provider="Acme",
            display_name="D", criticality="critical", support_owner="ops", description="d",
            capabilities=["payments"], scopes=["payments.charge", "payments.refund"],
            required_scopes=["payments.charge"],
            config_fields=[{"name": "merchant_id", "field_type": "reference",
                            "required": True},
                           {"name": "label", "field_type": "string"}])
        integrations.publish_definition(self._platform_pool, definition_key=key, version=2)
        # `label` exists on v2 and not on the snapshot this install holds.
        with self.assertRaises(InvalidRequest):
            integrations.configure_install(
                self._tenant_pool, tenant_id, installed["install_id"],
                config={"label": "shop"}, actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_missing_required_configuration_is_refused_at_install(self):
        tenant_id = self.tenant()
        key = self.definition()
        with self.assertRaises(InvalidRequest):
            integrations.install_integration(
                self._tenant_pool, self._platform_pool, tenant_id, definition_key=key,
                config={}, actor_id=ACTOR, correlation_id=self.correlate())

    def test_one_live_install_per_definition(self):
        tenant_id = self.tenant()
        key = self.definition()
        self.install(tenant_id, key)
        with self.assertRaises(Conflict):
            self.install(tenant_id, key)

    def test_a_critical_integration_needs_its_obligations_before_activation(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        integrations.validate_connection(
            self._tenant_pool, tenant_id, connection["connection_id"], evidence="ok",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict) as caught:
            integrations.activate_install(
                self._tenant_pool, tenant_id, installed["install_id"], actor_id=ACTOR,
                correlation_id=self.correlate())
        self.assertIn("fallback", str(caught.exception.code))

    def test_nothing_activates_without_a_validated_connection(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        integrations.configure_install(
            self._tenant_pool, tenant_id, installed["install_id"], fallback_plan="f",
            reconciliation_plan="r", exit_plan="e", actor_id=ACTOR,
            correlation_id=self.correlate())
        self.connect(tenant_id, installed["install_id"])
        with self.assertRaises(Conflict):
            integrations.activate_install(
                self._tenant_pool, tenant_id, installed["install_id"], actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_an_uninstall_revokes_every_connection_and_retires_every_credential(self):
        """An uninstall that left one authorized would be a tenant believing a third party no
        longer has access while it does."""
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        self.connect(tenant_id, installed["install_id"], external_account_ref="acct_one")
        self.connect(tenant_id, installed["install_id"], external_account_ref="acct_two")
        result = integrations.uninstall_integration(
            self._tenant_pool, tenant_id, installed["install_id"], reason="switched provider",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(result["connections_revoked"], 2)
        self.assertEqual(
            integrations.list_connections(self._tenant_pool, tenant_id), [])
        self.assertEqual(
            integrations.list_credentials(self._tenant_pool, tenant_id), [])
        published = self.outbox(tenant_id, "integration.uninstalled")
        self.assertEqual(published[0]["connections_revoked"], 2)

    def test_an_uninstalled_integration_cannot_come_back(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        integrations.uninstall_integration(
            self._tenant_pool, tenant_id, installed["install_id"], reason="done",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.activate_install(
                self._tenant_pool, tenant_id, installed["install_id"], actor_id=ACTOR,
                correlation_id=self.correlate())


class ConnectionTests(IntegrationsTestCase):
    def test_a_scope_the_definition_never_declared_cannot_be_granted(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.connect(tenant_id, installed["install_id"],
                         granted_scopes=["payments.charge", "payments.settle"])

    def test_the_required_scopes_have_to_be_granted(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.connect(tenant_id, installed["install_id"],
                         granted_scopes=["payments.refund"])

    def test_a_region_the_definition_does_not_serve_is_refused(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.connect(tenant_id, installed["install_id"], region="us-east")

    def test_a_connection_and_its_credential_reference_arrive_together(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        credentials = integrations.list_credentials(self._tenant_pool, tenant_id)
        self.assertEqual(len(credentials), 1)
        self.assertEqual(credentials[0]["connection_id"], connection["connection_id"])

    def test_a_validation_records_what_was_seen(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        with self.assertRaises(InvalidRequest):
            integrations.validate_connection(
                self._tenant_pool, tenant_id, connection["connection_id"], evidence="   ",
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_revoking_retires_the_credential_with_it(self):
        """A revoked connection whose reference still reads as live is a secret nobody will
        think to rotate, pointing at an account the tenant believes is disconnected."""
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        integrations.revoke_connection(
            self._tenant_pool, tenant_id, connection["connection_id"], reason="compromised",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(integrations.list_credentials(self._tenant_pool, tenant_id), [])
        retired = integrations.list_credentials(self._tenant_pool, tenant_id,
                                                include_retired=True)
        self.assertIsNotNone(retired[0]["retired_at"])

    def test_the_connected_event_names_the_scopes_that_were_granted(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        self.connect(tenant_id, installed["install_id"])
        published = self.outbox(tenant_id, "integration.connected")
        self.assertEqual(published[0]["granted_scopes"], ["payments.charge"])


class CredentialTests(IntegrationsTestCase):
    def test_a_rotation_supersedes_and_leaves_the_old_reference_readable(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        rotated = integrations.rotate_credential(
            self._tenant_pool, tenant_id, connection["connection_id"],
            vault_ref="vault://acme/live-2", actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(rotated["supersedes"], connection["credential_ref_id"])
        live = integrations.list_credentials(self._tenant_pool, tenant_id)
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0]["vault_ref"], "vault://acme/live-2")
        history = integrations.list_credentials(self._tenant_pool, tenant_id,
                                                include_retired=True)
        self.assertEqual(len(history), 2)

    def test_a_rotation_cannot_widen_scopes(self):
        """A rotation is a new secret for the same access; more access is a new authorization
        with its own decision."""
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        with self.assertRaises(InvalidRequest):
            integrations.rotate_credential(
                self._tenant_pool, tenant_id, connection["connection_id"],
                vault_ref="vault://acme/live-2",
                scopes=["payments.charge", "payments.refund"], actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_a_rotation_may_narrow_them(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"],
                                  granted_scopes=["payments.charge", "payments.refund"])
        rotated = integrations.rotate_credential(
            self._tenant_pool, tenant_id, connection["connection_id"],
            vault_ref="vault://acme/live-2", scopes=["payments.charge"], actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(rotated["scopes"], ["payments.charge"])

    def test_only_a_credential_inside_its_window_is_announced(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        self.connect(tenant_id, installed["install_id"], external_account_ref="acct_far",
                     expires_at=NOW + timedelta(days=90))
        self.connect(tenant_id, installed["install_id"], external_account_ref="acct_soon",
                     expires_at=NOW + timedelta(days=2))
        self.connect(tenant_id, installed["install_id"], external_account_ref="acct_never")
        result = integrations.credentials_due(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(len(result["announced"]), 1)
        self.assertEqual(len(self.outbox(tenant_id, "credential.expiring")), 1)

    def test_a_revoked_connection_is_not_announced(self):
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"],
                                  expires_at=NOW + timedelta(days=2))
        integrations.revoke_connection(
            self._tenant_pool, tenant_id, connection["connection_id"], reason="done",
            actor_id=ACTOR, correlation_id=self.correlate())
        result = integrations.credentials_due(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(result["announced"], [])


class SyncServiceTests(IntegrationsTestCase):
    def test_a_run_needs_a_validated_connection_and_an_active_install(self):
        """A connector reaching a provider on behalf of an install nobody activated is the
        integration operating outside the decision that authorized it."""
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        connection = self.connect(tenant_id, installed["install_id"])
        with self.assertRaises(Conflict):
            integrations.start_run(
                self._tenant_pool, tenant_id, connection_id=connection["connection_id"],
                resource="settlements", actor_id=ACTOR, correlation_id=self.correlate())

    def test_one_resource_syncs_at_a_time(self):
        """A lock rather than a lease, deliberately: two concurrent syncs of one resource read
        the same window and both advance the same cursor, so one ends up having skipped records
        it never saw."""
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.start_run(
                self._tenant_pool, tenant_id, connection_id=connection_id,
                resource="settlements", actor_id=ACTOR, correlation_id=self.correlate())
        # A different resource on the same connection is unaffected.
        integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="members",
            actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_run_settles_once(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        integrations.finish_run(self._tenant_pool, tenant_id, run["run_id"], records_read=10,
                                records_written=9, actor_id=ACTOR,
                                correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.finish_run(self._tenant_pool, tenant_id, run["run_id"],
                                    records_read=1, records_written=1, actor_id=ACTOR,
                                    correlation_id=self.correlate())

    def test_a_failure_retries_until_the_budget_is_gone_then_quarantines(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate(), max_attempts=2)
        first = integrations.fail_run(
            self._tenant_pool, tenant_id, run["run_id"], error="provider refused",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(first["status"], "failed")
        integrations.retry_run(self._tenant_pool, tenant_id, run["run_id"], actor_id=ACTOR,
                               correlation_id=self.correlate(),
                               now=datetime.now(UTC) + timedelta(hours=1))
        second = integrations.fail_run(
            self._tenant_pool, tenant_id, run["run_id"], error="provider refused again",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(second["status"], "dead")
        published = self.outbox(tenant_id, "integration.sync.failed")
        self.assertEqual([p["status"] for p in published], ["failed", "dead"])

    def test_a_quarantined_run_is_released_with_a_reason_and_a_fresh_budget(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate(), max_attempts=1)
        integrations.fail_run(self._tenant_pool, tenant_id, run["run_id"], error="boom",
                              actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.retry_run(self._tenant_pool, tenant_id, run["run_id"],
                                   actor_id=ACTOR, correlation_id=self.correlate())
        released = integrations.release_run(
            self._tenant_pool, tenant_id, run["run_id"], reason="provider fixed their API",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(released["attempts"], 1)
        # The "with a reason" half of this test's name, which went unverified until review
        # pointed out that the reason was validated, returned and discarded.
        self.assertEqual(released["released_because"], "provider fixed their API")

    def test_a_cursor_cannot_be_advanced_by_an_older_observation(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        integrations.advance_cursor(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            position="cur-2", observed_at=NOW, actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.advance_cursor(
                self._tenant_pool, tenant_id, connection_id=connection_id,
                resource="settlements", position="cur-1", observed_at=NOW - timedelta(days=1),
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_reset_may_move_it_backwards_and_records_why(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        integrations.advance_cursor(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            position="cur-2", observed_at=NOW, actor_id=ACTOR,
            correlation_id=self.correlate())
        integrations.reset_cursor(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            position="cur-0", observed_at=NOW - timedelta(days=7), reason="backfill",
            actor_id=ACTOR, correlation_id=self.correlate())
        cursor = integrations.list_cursors(self._tenant_pool, tenant_id)[0]
        self.assertEqual(cursor["position"], "cur-0")
        self.assertIsNotNone(cursor["reset_at"])

    def test_a_cursor_on_a_revoked_connection_is_refused(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        integrations.revoke_connection(
            self._tenant_pool, tenant_id, connection_id, reason="done", actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.advance_cursor(
                self._tenant_pool, tenant_id, connection_id=connection_id,
                resource="settlements", position="cur-9", observed_at=NOW, actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_a_reconciliation_records_both_sides(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        found = integrations.record_reconciliation(
            self._tenant_pool, tenant_id, run["run_id"], local_count=10, provider_count=8,
            matched=8, actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual((found["local_only"], found["provider_only"]), (2, 0))
        self.assertFalse(found["reconciled"])

    def test_an_impossible_reconciliation_is_refused(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            integrations.record_reconciliation(
                self._tenant_pool, tenant_id, run["run_id"], local_count=3,
                provider_count=3, matched=5, actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_an_unknown_run_is_refused(self):
        tenant_id = self.tenant()
        with self.assertRaises(Conflict):
            integrations.record_reconciliation(
                self._tenant_pool, tenant_id, str(uuid.uuid4()), local_count=1,
                provider_count=1, matched=1, actor_id=ACTOR,
                correlation_id=self.correlate())


class ReviewRegressionTests(IntegrationsTestCase):
    """One per blocking finding from the MOD-012 review round."""

    def test_releasing_a_quarantined_run_records_who_and_why(self):
        """It puts a connector that burned its entire retry budget back in front of a
        third-party provider, and resets the attempt count -- so without the columns the row
        afterwards reads as a fresh run with no trace that a human decided anything."""
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate(), max_attempts=1)
        integrations.fail_run(self._tenant_pool, tenant_id, run["run_id"], error="boom",
                              actor_id=ACTOR, correlation_id=self.correlate())
        integrations.release_run(
            self._tenant_pool, tenant_id, run["run_id"], reason="provider fixed their API",
            actor_id=ACTOR, correlation_id=self.correlate())
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT released_by, release_reason, release_correlation_id"
                " FROM plt01.int_connector_runs WHERE run_id = %s", (run["run_id"],),
            ).fetchone()
        assert row is not None
        self.assertEqual(str(row[0]), ACTOR)
        self.assertEqual(row[1], "provider fixed their API")
        self.assertIsNotNone(row[2])

    def test_settling_a_run_records_who_claimed_it(self):
        """`integrations.sync.run` is routine and tenant-wide, so any holder can finish any
        running run. Without this the only name on a fabricated count is the name of the party
        that did not make the claim."""
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        other = "44444444-4444-4444-8444-444444444444"
        integrations.finish_run(self._tenant_pool, tenant_id, run["run_id"], records_read=4,
                                records_written=4, actor_id=other,
                                correlation_id=self.correlate())
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT started_by, settled_by FROM plt01.int_connector_runs"
                " WHERE run_id = %s", (run["run_id"],),
            ).fetchone()
        assert row is not None
        self.assertEqual(str(row[0]), ACTOR)
        self.assertEqual(str(row[1]), other)

    def test_a_failure_reported_twice_cannot_stall_the_quarantine(self):
        """`fail_run` does not increment the attempt count, so accepting an already-failed run
        froze `attempts` for ever: the run could never reach `dead`, and an operator reading
        the dead-letter board saw it clean while a connector failed continuously."""
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate(), max_attempts=2)
        integrations.fail_run(self._tenant_pool, tenant_id, run["run_id"], error="boom",
                              actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.fail_run(self._tenant_pool, tenant_id, run["run_id"], error="boom",
                                  actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_second_run_does_not_make_the_first_unretryable_with_a_500(self):
        """`start_run` looks at the connection and the install, not at other runs, so a second
        run for one resource is reachable while the first waits out its backoff -- and the
        retry then collides with the in-flight lock. A refusal, not a server error."""
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        first = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        integrations.fail_run(self._tenant_pool, tenant_id, first["run_id"], error="boom",
                              actor_id=ACTOR, correlation_id=self.correlate())
        integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.retry_run(
                self._tenant_pool, tenant_id, first["run_id"], actor_id=ACTOR,
                correlation_id=self.correlate(),
                now=datetime.now(UTC) + timedelta(hours=1))

    def test_a_live_critical_install_cannot_have_its_obligations_blanked(self):
        """`coalesce` replaces NULL and not the empty string, so three blank fields erased the
        fallback, the reconciliation procedure and the exit plan from an active install -- with
        the same permission that wrote them and no refusal anywhere."""
        tenant_id = self.tenant()
        install_id, _ = self.ready(tenant_id)
        for blanked in ({"fallback_plan": ""}, {"reconciliation_plan": "  "},
                        {"exit_plan": ""}):
            with self.assertRaises(InvalidRequest):
                integrations.configure_install(
                    self._tenant_pool, tenant_id, install_id, actor_id=ACTOR,
                    correlation_id=self.correlate(), **blanked)
        listed = integrations.list_installs(self._tenant_pool, tenant_id)[0]
        self.assertTrue(listed["has_fallback"])
        self.assertTrue(listed["has_exit_plan"])

    def test_a_reconciliation_is_recorded_once_with_its_totals_and_its_author(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        run = integrations.start_run(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            actor_id=ACTOR, correlation_id=self.correlate())
        integrations.record_reconciliation(
            self._tenant_pool, tenant_id, run["run_id"], local_count=10, provider_count=8,
            matched=8, actor_id=ACTOR, correlation_id=self.correlate())
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT reconciled_by, reconciled_local, reconciled_provider,"
                " reconciled_matched FROM plt01.int_connector_runs WHERE run_id = %s",
                (run["run_id"],),
            ).fetchone()
        assert row is not None
        self.assertEqual((str(row[0]), int(row[1]), int(row[2]), int(row[3])),
                         (ACTOR, 10, 8, 8))
        with self.assertRaises(Conflict):
            integrations.record_reconciliation(
                self._tenant_pool, tenant_id, run["run_id"], local_count=1, provider_count=1,
                matched=1, actor_id=ACTOR, correlation_id=self.correlate())

    def test_the_conflict_policy_is_settable_before_any_sync(self):
        """It is the tenant's decision, and it has to be reachable without letting a connector
        create the cursor first -- which is how the routine sync permission came to be the one
        choosing it."""
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        integrations.set_conflict_policy(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            policy="local_wins", actor_id=ACTOR, correlation_id=self.correlate())
        integrations.advance_cursor(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            position="cur-1", observed_at=NOW, actor_id=ACTOR,
            correlation_id=self.correlate())
        cursor = integrations.list_cursors(self._tenant_pool, tenant_id)[0]
        self.assertEqual(cursor["conflict_policy"], "local_wins")
        self.assertEqual(cursor["position"], "cur-1")

    def test_a_definition_cannot_declare_a_region_no_connection_could_use(self):
        """An upper-case region registered fine and then made the definition permanently
        unconnectable, because the connection's own shape constraint refuses it."""
        for bad in (["EU-WEST"], ["eu-west", "eu-west"], ["  "]):
            with self.assertRaises(InvalidRequest):
                integrations.register_definition(
                    self._platform_pool, definition_key=f"acme.r{uuid.uuid4().hex[:8]}",
                    version=1, provider="Acme", display_name="D", criticality="convenience",
                    support_owner="ops", description="d", capabilities=["payments"],
                    scopes=[], required_scopes=[], regions=bad)

    def test_a_published_version_cannot_gain_a_scope(self):
        """`GRANT SELECT, INSERT` plus a unique entry name stops re-declaring a name that
        exists and stops nothing else, so a published version's scope set was additive-mutable
        -- and a *required* scope could be added to it. Installs keep their snapshot, so the
        blast radius is new installs authorizing a wider set than the one that was reviewed."""
        key = self.definition()
        with platform_scope(self._platform_pool) as conn:
            with self.assertRaises(psycopg.errors.RestrictViolation):
                conn.execute(
                    "INSERT INTO plt01_platform.int_definition_versions"
                    " (definition_key, version, kind, name, required)"
                    " VALUES (%s, 1, 'scope', 'members.read_all', true)", (key,))

    def test_a_vault_reference_has_to_look_like_a_locator(self):
        """Non-blank text alone made a live API key a valid "vault reference", which made the
        absence of a secret column a naming convention rather than a control."""
        tenant_id = self.tenant()
        installed = self.install(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.connect(tenant_id, installed["install_id"],
                         vault_ref="raw-credential-material-not-a-locator")

    def test_a_cursor_on_a_revoked_connection_cannot_be_reset_or_repolicied(self):
        tenant_id = self.tenant()
        _, connection_id = self.ready(tenant_id)
        integrations.advance_cursor(
            self._tenant_pool, tenant_id, connection_id=connection_id, resource="settlements",
            position="cur-1", observed_at=NOW, actor_id=ACTOR,
            correlation_id=self.correlate())
        integrations.revoke_connection(
            self._tenant_pool, tenant_id, connection_id, reason="done", actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.reset_cursor(
                self._tenant_pool, tenant_id, connection_id=connection_id,
                resource="settlements", position="cur-0", observed_at=NOW - timedelta(days=1),
                reason="backfill", actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            integrations.set_conflict_policy(
                self._tenant_pool, tenant_id, connection_id=connection_id,
                resource="settlements", policy="local_wins", actor_id=ACTOR,
                correlation_id=self.correlate())


if __name__ == "__main__":
    unittest.main()
