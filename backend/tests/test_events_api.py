"""MOD-010 over HTTP, and the proof that the producers actually produce.

An outbox nothing writes to is a table that reads as a control. These tests drive the *other*
modules' routes -- configuration, privacy, the organization hierarchy -- and then look in the
outbox, so "MOD-005 publishes configuration.changed" is a fact about the running system rather
than a sentence in a comment.

**What the producers cannot do, tested as explicitly as what they can.** The outbox lives in
`plt01` under `veyro_cp_app`. A write on another plane -- the tenant registry in
`plt01_platform`, anything in `iam` -- cannot share its transaction, because the roles hold
nothing in each other's schemas and are members of no role. So `tenant.provisioned`,
`identity.created`, `authentication.succeeded` and `role.assigned` are in the catalogue and have
no producer, and that is a property of the plane separation rather than an oversight.
`test_cross_plane_events_have_no_producer_and_the_catalogue_says_which` is the test that keeps
that honest.
"""

from __future__ import annotations

import unittest
import uuid

from app.events import catalog
from tests.test_privacy_api import PrivacyApiTestCase


class ProducerTests(PrivacyApiTestCase):
    """The modules that share the outbox's plane append in the same transaction as their write."""

    def outbox(self, tenant_id: str, event_type: str) -> list[dict]:
        """Every event of one type in this tenant, read back through the HTTP surface."""
        owner = self.headers(tenant_id)
        health = self.client.get("/events/health", headers=owner)
        self.assertEqual(health.status_code, 200, health.text)
        # There is no "list the outbox" route by design -- an unbounded read of every event is
        # not something a tenant surface should offer -- so the trace is the way in, which is
        # also the shape an operator uses during an incident.
        return [e for e in self._all_events(tenant_id) if e["event_type"] == event_type]

    def _all_events(self, tenant_id: str) -> list[dict]:
        from app.db import tenant_scope
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, aggregate_type, correlation_id, payload"
                " FROM plt01.evt_outbox ORDER BY occurred_at"
            ).fetchall()
        return [{"event_id": str(r[0]), "event_type": r[1], "aggregate_type": r[2],
                 "correlation_id": str(r[3]), "payload": r[4]} for r in rows]

    def test_publishing_a_configuration_value_appends_configuration_changed(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = f"pay.{uuid.uuid4().hex[:6]}"
        self.assertEqual(self.client.post("/config/definitions", headers=owner, json={
            "config_key": key, "value_type": "integer", "default_value": 1,
            "owner_module": "MOD-005"}).status_code, 201)
        correlation = str(uuid.uuid4())
        published = self.client.post("/config/values", headers=owner, json={
            "config_key": key, "value": 7, "published_by": str(uuid.uuid4()),
            "correlation_id": correlation})
        self.assertEqual(published.status_code, 201, published.text)

        appended = self.outbox(tenant_id, "configuration.changed")
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0]["payload"]["config_key"], key)
        self.assertEqual(appended[0]["payload"]["version"], 1)
        self.assertEqual(appended[0]["correlation_id"], correlation)

    def test_recording_consent_appends_consent_granted_with_the_same_correlation(self):
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        owner = self.headers(tenant_id)
        correlation = str(uuid.uuid4())
        subject = str(uuid.uuid4())
        recorded = self.client.post("/privacy/consent/records", headers=owner, json={
            "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "paper_import", "subject_id": subject,
            "correlation_id": correlation})
        self.assertEqual(recorded.status_code, 201, recorded.text)

        appended = self.outbox(tenant_id, "consent.granted")
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0]["payload"]["subject_id"], subject)
        self.assertEqual(appended[0]["payload"]["consent_type"], "waiver")
        self.assertEqual(appended[0]["correlation_id"], correlation)

    def test_withdrawing_consent_appends_consent_withdrawn(self):
        tenant_id = self.tenant()
        self.fixture(tenant_id, consent_type="marketing")
        owner = self.headers(tenant_id)
        subject = str(uuid.uuid4())
        self.client.post("/privacy/consent/records", headers=owner, json={
            "consent_type": "marketing", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "paper_import", "subject_id": subject, **self.correlation()})
        withdrew = self.client.post("/privacy/consent/withdrawals", headers=owner, json={
            "consent_type": "marketing", "signed_at": "2026-06-02T10:00:00+00:00",
            "source": "staff_entry", "subject_id": subject, **self.correlation()})
        self.assertEqual(withdrew.status_code, 201, withdrew.text)
        self.assertEqual(len(self.outbox(tenant_id, "consent.withdrawn")), 1)

    def test_a_dsar_appends_created_and_completed_around_the_work(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subject_id, _ = self.fresh_identity(tenant_id, "Eventful")
        request_id = self.walk_to_ready(tenant_id, subject_id)
        self.assertEqual(len(self.outbox(tenant_id, "data_subject_request.created")), 1)

        fulfilled = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=owner,
                                     json=self.correlation())
        self.assertEqual(fulfilled.status_code, 200, fulfilled.text)
        completed = self.outbox(tenant_id, "data_subject_request.completed")
        self.assertEqual(len(completed), 1)
        self.assertTrue(completed[0]["payload"]["has_residue"],
                        "the event carries the fact that erasure was incomplete")

    def test_recording_an_incident_appends_a_security_alert(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.post("/privacy/incidents", headers=owner, json={
            "severity": "high", "category": "access_anomaly", "summary": "s",
            "detected_at": "2026-06-01T10:00:00+00:00", "personal_data_involved": "unknown",
            **self.correlation()}).status_code, 201)
        appended = self.outbox(tenant_id, "security.alert.detected")
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0]["payload"]["severity"], "high")

    def test_creating_an_organization_appends_organization_updated(self):
        tenant_id = self.tenant()
        created = self.client.post("/organizations", headers=self.headers(tenant_id), json={
            "legal_name": "Acme ehf", "country_code": "IS"})
        self.assertEqual(created.status_code, 201, created.text)
        appended = self.outbox(tenant_id, "organization.updated")
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0]["payload"]["legal_name"], "Acme ehf")

    def test_a_command_refused_at_the_gate_appends_nothing(self):
        """The cheap half: the gate refuses before the service opens a transaction at all."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["privacy.consent.read"]))
        refused = self.client.post("/privacy/incidents", headers=head, json={
            "severity": "high", "category": "access_anomaly", "summary": "s",
            "detected_at": "2026-06-01T10:00:00+00:00", "personal_data_involved": "yes",
            **self.correlation()})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(self.outbox(tenant_id, "security.alert.detected"), [])

    def test_a_command_that_fails_after_appending_takes_the_event_with_it(self):
        """The half that actually exercises the rollback, which the gate-refusal test does not.

        A reviewer pointed out that refusing at the gate proves nothing about atomicity: the
        append never happened, so nothing rolled back. This appends an event and then fails the
        surrounding transaction the way a constraint violation or a crash would, and asserts the
        event is not there -- which is the whole reason `append_event` takes a connection.
        """
        from app.db import tenant_scope
        from app.events import service as events

        tenant_id = self.tenant()
        before = len(self._all_events(tenant_id))
        with self.assertRaises(RuntimeError):
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                conn.execute(
                    "INSERT INTO plt01.organizations (tenant_id, legal_name, country_code)"
                    " VALUES (%s, 'Doomed ehf', 'IS')", (tenant_id,))
                events.append_event(
                    conn, tenant_id, event_type="organization.updated",
                    aggregate_type="organization", aggregate_id=str(uuid.uuid4()),
                    payload={"organization_id": str(uuid.uuid4()),
                             "legal_name": "Doomed ehf", "country_code": "IS"},
                    correlation_id=str(uuid.uuid4()))
                raise RuntimeError("the rest of the command failed")
        self.assertEqual(len(self._all_events(tenant_id)), before,
                         "the event committed without the write it describes")
        listed = self.client.get("/organizations", headers=self.headers(tenant_id)).json()
        self.assertEqual([o for o in listed if o["legal_name"] == "Doomed ehf"], [],
                         "and the write itself is gone too, which is the point")

    def test_the_event_plane_is_not_a_second_way_to_read_another_modules_data(self):
        """`events.event.read` was a lateral read path around four modules' read permissions.

        A reviewer held exactly that one routine permission, was refused 403 by
        `/privacy/consent/history` and `/privacy/requests`, and then read the same facts -- who
        consented to what, who filed which data subject request -- out of `evt_outbox.payload`
        via `/events/aggregate`. The event plane routes and traces; what an event carried is the
        owning module's to disclose.
        """
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        owner = self.headers(tenant_id)
        subject = str(uuid.uuid4())
        self.client.post("/privacy/consent/records", headers=owner, json={
            "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "paper_import", "subject_id": subject, **self.correlation()})

        reader = self.headers(tenant_id, self.grant(tenant_id, ["events.event.read"]))
        self.assertEqual(self.client.get(
            "/privacy/consent/history", headers=reader,
            params={"subject_id": subject}).status_code, 403)

        timeline = self.client.get("/events/aggregate", headers=reader,
                                   params={"aggregate_type": "consent",
                                           "aggregate_id": subject})
        self.assertEqual(timeline.status_code, 200, timeline.text)
        self.assertEqual([e["event_type"] for e in timeline.json()], ["consent.granted"])
        for entry in timeline.json():
            self.assertNotIn("payload", entry,
                             "the timeline must not carry what the event said")

        event_id = timeline.json()[0]["event_id"]
        one = self.client.get(f"/events/{event_id}", headers=reader)
        self.assertEqual(one.status_code, 200, one.text)
        self.assertNotIn("payload", one.json())

    def test_an_exposure_event_carries_a_hash_and_not_the_caller_s_string(self):
        """`cfg_exposures.subject_id` is caller-chosen free text at AAL 1, so the name-based
        restricted-field rule cannot protect it -- a reviewer put an email address, a date of
        birth, a national id and a lab result in it. An event is the one store this build
        cannot erase from, so what travels is a hash."""
        import hashlib

        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = f"exp.{uuid.uuid4().hex[:8]}"
        self.assertEqual(self.client.post("/experiments", headers=owner, json={
            "experiment_key": key,
            "variants": [{"variant_key": "control", "weight": 1},
                         {"variant_key": "treatment", "weight": 1}]}).status_code, 201)
        self.assertEqual(self.client.post(f"/experiments/{key}/status", headers=owner,
                                          json={"status": "running"}).status_code, 200)
        leaky = "jane.doe@example.com dob=1979-04-02 nid=0204793429"
        allocated = self.client.post(f"/experiments/{key}/allocate", headers=owner,
                                     json={"subject_id": leaky, **self.correlation()})
        self.assertEqual(allocated.status_code, 200, allocated.text)

        appended = self.outbox(tenant_id, "experiment.exposed")
        self.assertEqual(len(appended), 1)
        payload = appended[0]["payload"]
        self.assertNotIn("subject_id", payload)
        self.assertEqual(payload["subject_hash"],
                         hashlib.sha256(leaky.encode()).hexdigest())
        self.assertNotIn("example.com", str(payload))


class CatalogueCoverageTests(PrivacyApiTestCase):
    def test_cross_plane_events_have_no_producer_and_the_plane_separation_is_why(self):
        """`tenant.provisioned` and the identity-plane events are declared and unproduced.

        Stated as a test rather than a comment so that the day somebody adds an outbox to the
        platform or identity plane, this fails and the gap note in CLAUDE.md gets deleted with
        it. The alternative -- appending them in a second transaction -- would mean a tenant
        that exists with no event, or an event for a tenant that does not, and either is worse
        than the honest absence.
        """
        tenant_id = self.tenant()
        self.fresh_identity(tenant_id, "Nobody")
        produced = {e["event_type"] for e in ProducerTests._all_events(self, tenant_id)}
        for cross_plane in ("tenant.provisioned", "identity.created",
                            "authentication.succeeded", "role.assigned",
                            "permission.denied"):
            self.assertIn((cross_plane, 1), catalog.EVENT_TYPES,
                          f"{cross_plane} should still be declared")
            self.assertNotIn(cross_plane, produced,
                             f"{cross_plane} now has a producer; update the gap note")


class EventApiTests(PrivacyApiTestCase):
    def test_the_whole_relay_loop_over_http(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subscribed = self.client.post("/events/subscriptions", headers=owner, json={
            "consumer": "timeline", "event_type": "organization.updated",
            "replay_safety": "safe", **self.correlation()})
        self.assertEqual(subscribed.status_code, 201, subscribed.text)

        self.client.post("/organizations", headers=owner,
                         json={"legal_name": "Acme ehf", "country_code": "IS"})
        health = self.client.get("/events/health", headers=owner).json()
        self.assertEqual(health["pending_events"], 1)

        dispatched = self.client.post("/events/dispatch", headers=owner,
                                      json=self.correlation())
        self.assertEqual(dispatched.json(),
                         {"events_dispatched": 1, "deliveries_created": 1})
        after = self.client.get("/events/health", headers=owner).json()
        self.assertEqual(after["pending_events"], 0)
        self.assertEqual(after["pending_deliveries"], 1)

    def test_a_trace_answers_what_one_request_caused(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        correlation = str(uuid.uuid4())
        key = f"pay.{uuid.uuid4().hex[:6]}"
        self.client.post("/config/definitions", headers=owner, json={
            "config_key": key, "value_type": "integer", "default_value": 1,
            "owner_module": "MOD-005"})
        self.client.post("/config/values", headers=owner, json={
            "config_key": key, "value": 7, "published_by": str(uuid.uuid4()),
            "correlation_id": correlation})
        traced = self.client.get("/events/trace", headers=owner,
                                 params={"correlation_id": correlation})
        self.assertEqual(traced.status_code, 200, traced.text)
        self.assertEqual([t["event_type"] for t in traced.json()], ["configuration.changed"])

    def test_a_replay_route_refuses_to_allow_side_effects_with_no_reason(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        self.client.post("/events/subscriptions", headers=owner, json={
            "consumer": "messaging", "event_type": "organization.updated",
            **self.correlation()})
        refused = self.client.post("/events/replays", headers=owner, json={
            "consumer": "messaging", "event_types": ["organization.updated"],
            "from_time": "2026-01-01T00:00:00+00:00", "to_time": "2027-01-01T00:00:00+00:00",
            "side_effects": "allow", **self.correlation()})
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"],
                         "allowing_side_effects_on_a_replay_needs_a_reason")

    def test_a_subscription_reader_cannot_route_an_event_type(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["events.subscription.read"]))
        self.assertEqual(
            self.client.get("/events/subscriptions/all", headers=head).status_code, 200)
        refused = self.client.post("/events/subscriptions", headers=head, json={
            "consumer": "sneaky", "event_type": "consent.granted", **self.correlation()})
        self.assertEqual(refused.status_code, 403)

    def test_a_relay_credential_cannot_request_a_replay(self):
        """`events.dispatch.run` is routine so a worker can loop on it. Replaying is not: it is
        a decision to send things again, and it is financial-class."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(
            tenant_id, ["events.dispatch.run", "events.event.read"]))
        self.assertEqual(
            self.client.post("/events/dispatch", headers=head,
                             json=self.correlation()).status_code, 200)
        refused = self.client.post("/events/replays", headers=head, json={
            "consumer": "timeline", "event_types": ["organization.updated"],
            "from_time": "2026-01-01T00:00:00+00:00", "to_time": "2027-01-01T00:00:00+00:00",
            **self.correlation()})
        self.assertEqual(refused.status_code, 403)

    def test_a_malformed_id_is_a_refusal_not_a_database_exception(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.get("/events/not-a-uuid",
                                         headers=owner).status_code, 422)
        self.assertEqual(self.client.get("/events/trace", headers=owner,
                                         params={"correlation_id": "nope"}).status_code, 422)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
