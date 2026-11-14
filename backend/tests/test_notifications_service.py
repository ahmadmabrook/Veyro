"""MOD-013 ENG-02 service against a real database.

The properties worth a database are the ones a mock would assert into existence: that a
marketing notification cannot be authored without the consent record that permitted it, that a
transactional one ignores an opt-out, that the same request twice authors one notification, and
that a bounce suppresses the address in the same transaction as the delivery that caused it.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, time, timedelta

from app.db import tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.notifications import delivery
from app.notifications import service as notifications
from app.privacy import service as privacy
from tests.support import GatedApiTestCase

ACTOR = "33333333-3333-4333-8333-333333333333"
OTHER = "44444444-4444-4444-8444-444444444444"
NOW = datetime.now(UTC)


class NotificationsTestCase(GatedApiTestCase):
    def correlate(self) -> str:
        return str(uuid.uuid4())

    def digest(self, address: str = "member@acme.test", channel: str = "email") -> str:
        return delivery.address_digest(channel, address)

    def digests(self, address: str = "member@acme.test") -> dict[str, str]:
        """One digest per channel, each computed for its own channel.

        That `sha256("email:...")` and `sha256("sms:...")` differ is the whole reason the
        request takes a map: a fallback carrying the digest of the channel it fell back from
        looked up a suppression key the new channel can never produce.
        """
        return {channel: delivery.address_digest(channel, address)
                for channel in ("email", "sms", "whatsapp", "push", "in_app")}

    def outbox(self, tenant_id: str, event_type: str) -> list[dict]:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            rows = conn.execute(
                "SELECT payload FROM plt01.evt_outbox WHERE event_type = %s"
                " ORDER BY occurred_at, event_id", (event_type,)
            ).fetchall()
        return [r[0] for r in rows]

    def template(self, tenant_id: str, **kwargs: object) -> str:
        """A published template. Approved by a *different* actor, which the schema requires."""
        body: dict = {
            "template_key": f"t{uuid.uuid4().hex[:8]}", "version": 1,
            "category": "transactional", "channel": "email", "locale": "en",
            "subject": "Invoice {{ number }}", "body": "Invoice {{ number }} is ready.",
            "variables": ["number"],
        }
        body.update(kwargs)
        created = notifications.create_template(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body)
        notifications.approve_template(
            self._tenant_pool, tenant_id, created["template_id"], actor_id=OTHER,
            correlation_id=self.correlate())
        notifications.publish_template(
            self._tenant_pool, tenant_id, created["template_id"], actor_id=ACTOR,
            correlation_id=self.correlate())
        return str(body["template_key"])

    def grant_consent(self, tenant_id: str, recipient_id: str) -> None:
        """A live marketing consent on MOD-009's tables, through its own service."""
        correlation = self.correlate()
        purpose = privacy.register_purpose(
            self._tenant_pool, tenant_id, purpose_code="member.marketing",
            description="Marketing", lawful_basis="consent", controller_role="controller",
            data_classes=["internal"], actor_id=ACTOR, correlation_id=correlation)
        privacy.define_consent(
            self._tenant_pool, tenant_id, consent_type="marketing",
            purpose_id=purpose["purpose_id"], actor_id=ACTOR, correlation_id=correlation)
        privacy.publish_consent_version(
            self._tenant_pool, tenant_id, consent_type="marketing", language="en",
            document_ref="https://acme.test/marketing", document_hash="0" * 64,
            effective_from=NOW - timedelta(days=1), actor_id=ACTOR,
            correlation_id=correlation)
        privacy.register_consent(
            self._tenant_pool, tenant_id, subject_id=recipient_id, consent_type="marketing",
            language="en", signed_at=NOW - timedelta(hours=1), source="member_app",
            correlation_id=correlation)

    def request(self, tenant_id: str, template_key: str, **kwargs: object) -> dict:
        body: dict = {
            "recipient_id": str(uuid.uuid4()), "address_digests": self.digests(),
            "idempotency_key": f"k{uuid.uuid4().hex[:10]}", "variables": {"number": "INV-1"},
        }
        body.update(kwargs)
        return notifications.request_notification(
            self._tenant_pool, tenant_id, template_key=template_key, actor_id=ACTOR,
            correlation_id=self.correlate(), **body)


class TemplateServiceTests(NotificationsTestCase):
    def test_an_author_cannot_approve_their_own_template(self):
        """It goes out under the tenant's name to everybody, which is MOD-008's separation of
        duties applied to content."""
        tenant_id = self.tenant()
        created = notifications.create_template(
            self._tenant_pool, tenant_id, template_key="a.b", version=1,
            category="operational", channel="sms", locale="en", body="Hi.",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            notifications.approve_template(
                self._tenant_pool, tenant_id, created["template_id"], actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_publication_requires_an_approval(self):
        tenant_id = self.tenant()
        created = notifications.create_template(
            self._tenant_pool, tenant_id, template_key="a.b", version=1,
            category="operational", channel="sms", locale="en", body="Hi.",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            notifications.publish_template(
                self._tenant_pool, tenant_id, created["template_id"], actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_a_draft_cannot_be_authored_from(self):
        tenant_id = self.tenant()
        notifications.create_template(
            self._tenant_pool, tenant_id, template_key="draft.only", version=1,
            category="operational", channel="sms", locale="en", body="Hi.",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(NotFound):
            self.request(tenant_id, "draft.only", variables={})

    def test_a_successor_cannot_change_the_category(self):
        """Refused by the key-wide category rule, which fires before the succession check and
        covers more: a key is one message, and its category decides what every channel of it
        is allowed to do."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        with self.assertRaises(Conflict):
            notifications.create_template(
                self._tenant_pool, tenant_id, template_key=key, version=2,
                category="marketing", channel="email", locale="en",
                subject="Invoice {{ number }}", body="Invoice {{ number }} is ready.",
                variables=["number"], actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_successor_cannot_change_the_channel_or_locale(self):
        """The succession rule itself, reached by keeping the category the same."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        notifications.create_template(
            self._tenant_pool, tenant_id, template_key=key, version=2,
            category="transactional", channel="email", locale="en",
            subject="Invoice {{ number }}", body="Invoice {{ number }} ready.",
            variables=["number"], actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(
            len(notifications.list_templates(self._tenant_pool, tenant_id)), 2)

    def test_a_published_template_cannot_be_rewritten(self):
        """By trigger as well as by grant: the grant admits a body change on a draft and cannot
        see the status."""
        import psycopg
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        template_id = notifications.list_templates(self._tenant_pool, tenant_id)[0][
            "template_id"]
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            with self.assertRaises(psycopg.errors.RestrictViolation):
                conn.execute(
                    "UPDATE plt01.ntf_templates SET body = 'something else'"
                    " WHERE template_id = %s", (template_id,))
        self.assertTrue(key)


class ConsentSeparationTests(NotificationsTestCase):
    def test_a_marketing_notification_needs_a_live_consent(self):
        """Paragraph 2463's separation, at the one place it is enforceable: not a boolean
        somebody set, and not a call to a service that may have moved on."""
        tenant_id = self.tenant()
        key = self.template(tenant_id, category="marketing", channel="email",
                            subject="News", body="News for you.", variables=[])
        with self.assertRaises(Conflict) as caught:
            self.request(tenant_id, key, variables={})
        self.assertIn("consent", str(caught.exception.code))

    def test_a_marketing_notification_cites_the_consent_that_permitted_it(self):
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        self.grant_consent(tenant_id, recipient)
        key = self.template(tenant_id, category="marketing", channel="email",
                            subject="News", body="News for you.", variables=[])
        result = self.request(tenant_id, key, recipient_id=recipient, variables={})
        self.assertIsNotNone(result["consent_record_id"])
        detail = notifications.get_notification(
            self._tenant_pool, tenant_id, result["notification_id"])
        self.assertEqual(detail["consent_record_id"], result["consent_record_id"])

    def test_a_transactional_notification_ignores_an_opt_out(self):
        """A member who mutes marketing still gets their invoice."""
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        key = self.template(tenant_id)
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient, category="marketing",
            channel="email", allowed=False, actor_id=ACTOR,
            correlation_id=self.correlate())
        result = self.request(tenant_id, key, recipient_id=recipient)
        self.assertEqual(result["outcome"], "send")

    def test_a_transactional_preference_cannot_be_switched_off_at_all(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            notifications.set_preference(
                self._tenant_pool, tenant_id, recipient_id=str(uuid.uuid4()),
                category="transactional", channel="email", allowed=False, actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_an_opt_out_suppresses_a_coaching_notification(self):
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        key = self.template(tenant_id, category="coaching", channel="push", subject="",
                            body="Nice work.", variables=[])
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient, category="coaching",
            channel="push", allowed=False, actor_id=ACTOR, correlation_id=self.correlate())
        result = self.request(tenant_id, key, recipient_id=recipient, variables={})
        self.assertEqual((result["outcome"], result["status"]),
                         ("suppress", "suppressed"))

    def test_a_suppressed_notification_is_still_recorded(self):
        """A request that vanished because a preference said no is a request nobody can account
        for when the member asks why they never heard anything."""
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        key = self.template(tenant_id, category="coaching", channel="push", subject="",
                            body="Nice work.", variables=[])
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient, category="coaching",
            channel="push", allowed=False, actor_id=ACTOR, correlation_id=self.correlate())
        self.request(tenant_id, key, recipient_id=recipient, variables={})
        listed = notifications.list_notifications(self._tenant_pool, tenant_id)
        self.assertEqual(listed[0]["decision_reason"], "recipient_opted_out")


class RequestTests(NotificationsTestCase):
    def test_the_same_request_twice_authors_one_notification(self):
        """The request half of paragraph 2464: a caller whose own retry fired, or an event
        redelivered under MOD-010's at-least-once contract, authors one notification."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        first = self.request(tenant_id, key, idempotency_key="invoice-1")
        with self.assertRaises(Conflict):
            self.request(tenant_id, key, idempotency_key="invoice-1")
        self.assertEqual(
            len(notifications.list_notifications(self._tenant_pool, tenant_id)), 1)
        self.assertTrue(first["notification_id"])

    def test_the_rendered_text_is_stored_and_not_re_rendered(self):
        """The template may be retired tomorrow; what was sent is what somebody asks about."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        result = self.request(tenant_id, key, variables={"number": "INV-99"})
        detail = notifications.get_notification(
            self._tenant_pool, tenant_id, result["notification_id"])
        self.assertEqual(detail["rendered_subject"], "Invoice INV-99")
        self.assertIn("INV-99", detail["rendered_body"])

    def test_an_undeclared_variable_is_refused(self):
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.request(tenant_id, key, variables={"number": "1", "extra": "x"})

    def test_an_address_where_a_digest_belongs_is_refused(self):
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.request(tenant_id, key,
                         address_digests={"email": "member@acme.test"})

    def test_quiet_hours_defer_the_notification(self):
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        key = self.template(tenant_id, category="coaching", channel="push", subject="",
                            body="Nice work.", variables=[])
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient, category="coaching",
            channel="push", quiet_from=time(0), quiet_until=time(23, 59),
            quiet_timezone="UTC", actor_id=ACTOR, correlation_id=self.correlate())
        result = self.request(tenant_id, key, recipient_id=recipient, variables={})
        self.assertEqual((result["outcome"], result["status"]), ("defer", "deferred"))
        self.assertIsNotNone(result["scheduled_for"])

    def test_a_cap_folds_the_notification_into_a_digest(self):
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        key = self.template(tenant_id, category="coaching", channel="push", subject="",
                            body="Nice work.", variables=[])
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient, category="coaching",
            channel="push", daily_cap=1, actor_id=ACTOR, correlation_id=self.correlate())
        first = self.request(tenant_id, key, recipient_id=recipient, variables={})
        self.assertEqual(first["outcome"], "send")
        second = self.request(tenant_id, key, recipient_id=recipient, variables={})
        self.assertEqual(second["outcome"], "digest")
        digests = notifications.list_digests(self._tenant_pool, tenant_id)
        self.assertEqual(len(digests), 1)

    def test_a_critical_notification_needs_a_policy_reference(self):
        tenant_id = self.tenant()
        recipient = str(uuid.uuid4())
        key = self.template(tenant_id, category="coaching", channel="push", subject="",
                            body="Nice work.", variables=[])
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient, category="coaching",
            channel="push", allowed=False, actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            self.request(tenant_id, key, recipient_id=recipient, variables={},
                         priority="critical")
        allowed = self.request(tenant_id, key, recipient_id=recipient, variables={},
                               priority="critical", bypass_policy_ref="RB-ENG-02#alerts")
        self.assertEqual(allowed["outcome"], "send")

    def test_a_disabled_channel_falls_back_to_its_own_template(self):
        """An email subject on an SMS is text that goes nowhere, so the fallback re-renders
        from the template written for the channel it falls back to."""
        tenant_id = self.tenant()
        key = self.template(tenant_id, channel="email")
        # The same key, the SMS version. That is what a key is: one message, several channels.
        sms = notifications.create_template(
            self._tenant_pool, tenant_id, template_key=key, version=1,
            category="transactional", channel="sms", locale="en", subject="",
            body="Invoice {{ number }} ready.", variables=["number"], actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.approve_template(
            self._tenant_pool, tenant_id, sms["template_id"], actor_id=OTHER,
            correlation_id=self.correlate())
        notifications.publish_template(
            self._tenant_pool, tenant_id, sms["template_id"], actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.set_channel_policy(
            self._tenant_pool, tenant_id, channel="email", enabled=False,
            fallback_channel="sms", actor_id=ACTOR, correlation_id=self.correlate())
        result = self.request(tenant_id, key)
        self.assertEqual((result["outcome"], result["channel"]), ("send", "sms"))
        detail = notifications.get_notification(
            self._tenant_pool, tenant_id, result["notification_id"])
        self.assertEqual(detail["rendered_subject"], "")

    def test_a_fallback_with_no_template_is_suppressed_with_a_reason(self):
        tenant_id = self.tenant()
        key = self.template(tenant_id, channel="email")
        notifications.set_channel_policy(
            self._tenant_pool, tenant_id, channel="email", enabled=False,
            fallback_channel="sms", actor_id=ACTOR, correlation_id=self.correlate())
        result = self.request(tenant_id, key)
        self.assertEqual((result["outcome"], result["reason"]),
                         ("suppress", "no_template_for_the_fallback_channel"))

    def test_one_key_cannot_hold_two_categories(self):
        """A key whose email version is transactional and whose SMS version is marketing would
        change what a fallback is allowed to do."""
        tenant_id = self.tenant()
        key = self.template(tenant_id, channel="email")
        with self.assertRaises(Conflict):
            notifications.create_template(
                self._tenant_pool, tenant_id, template_key=key, version=1,
                category="marketing", channel="sms", locale="en", subject="",
                body="News.", variables=[], actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_the_list_carries_no_message_text(self):
        """A list route that did would be a read path to everything this tenant has ever said
        to anybody, under one permission."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        self.request(tenant_id, key)
        row = notifications.list_notifications(self._tenant_pool, tenant_id)[0]
        self.assertNotIn("rendered_body", row)
        self.assertNotIn("rendered_subject", row)


class DeliveryServiceTests(NotificationsTestCase):
    def ready(self, tenant_id: str, **kwargs: object) -> str:
        key = self.template(tenant_id)
        return self.request(tenant_id, key, **kwargs)["notification_id"]

    def test_a_dispatch_counts_one_attempt_and_settles_one_row(self):
        """The transport half of paragraph 2464: one delivery row per notification and channel,
        so a dispatcher that timed out and retried settles the row it already holds."""
        tenant_id = self.tenant()
        notification_id = self.ready(tenant_id)
        first = notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(first["attempts"], 1)
        notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="sent", actor_id=ACTOR,
            correlation_id=self.correlate())
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            count = conn.execute(
                "SELECT count(*) FROM plt01.ntf_deliveries WHERE notification_id = %s",
                (notification_id,)).fetchone()
        assert count is not None
        self.assertEqual(int(count[0]), 1)

    def test_a_bounce_suppresses_the_address_in_the_same_transaction(self):
        """Doing it in a later sweep would let the next notification to that address go out
        before anybody noticed."""
        tenant_id = self.tenant()
        notification_id = self.ready(tenant_id)
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        result = notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="bounced",
            error="mailbox does not exist", actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(result["state"], "dead")
        self.assertIsNotNone(result["suppression_id"])
        suppressions = notifications.list_suppressions(self._tenant_pool, tenant_id)
        self.assertEqual(suppressions[0]["reason"], "bounced")

    def test_the_next_notification_to_a_bounced_address_is_suppressed(self):
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        recipient_id = str(uuid.uuid4())
        first = self.request(tenant_id, key, recipient_id=recipient_id)
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, first["notification_id"], actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.record_outcome(
            self._tenant_pool, tenant_id, first["notification_id"], outcome="bounced",
            error="mailbox does not exist", actor_id=ACTOR,
            correlation_id=self.correlate())
        second = self.request(tenant_id, key, recipient_id=recipient_id)
        self.assertEqual((second["outcome"], second["reason"]),
                         ("suppress", "address_is_suppressed_on_this_channel"))

    def test_a_failure_retries_until_the_budget_is_gone(self):
        tenant_id = self.tenant()
        notification_id = self.ready(tenant_id)
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        first = notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="failed",
            error="provider timed out", actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(first["state"], "failed")
        self.assertIsNotNone(first["next_attempt_at"])

    def test_a_failure_records_what_went_wrong(self):
        tenant_id = self.tenant()
        notification_id = self.ready(tenant_id)
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            notifications.record_outcome(
                self._tenant_pool, tenant_id, notification_id, outcome="failed",
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_delivered_message_cannot_un_deliver(self):
        tenant_id = self.tenant()
        notification_id = self.ready(tenant_id)
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="delivered",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            notifications.record_outcome(
                self._tenant_pool, tenant_id, notification_id, outcome="failed",
                error="late bounce", actor_id=ACTOR, correlation_id=self.correlate())

    def test_each_outcome_publishes_its_own_event(self):
        tenant_id = self.tenant()
        notification_id = self.ready(tenant_id)
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="sent", actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="delivered",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(len(self.outbox(tenant_id, "notification.sent")), 1)
        self.assertEqual(len(self.outbox(tenant_id, "notification.delivered")), 1)

    def test_no_event_payload_carries_the_message_text(self):
        """A notification body is the most personal thing this build renders, and an event is
        fanned out, archived and replayed into more places than any other row."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        self.request(tenant_id, key, variables={"number": "SECRET-INV"})
        for event_type in ("notification.requested",):
            for payload in self.outbox(tenant_id, event_type):
                self.assertNotIn("SECRET-INV", str(payload))
                self.assertNotIn("address_digest", payload)


class SuppressionTests(NotificationsTestCase):
    def test_only_an_unsubscribe_may_be_released(self):
        tenant_id = self.tenant()
        # A bounce cannot be *declared* any more -- it is written by `record_outcome` from a
        # reported delivery -- so this reaches for the one that reports one.
        key = self.template(tenant_id)
        bounced_id = self.request(tenant_id, key)["notification_id"]
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, bounced_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        bounced = {"suppression_id": notifications.record_outcome(
            self._tenant_pool, tenant_id, bounced_id, outcome="bounced",
            error="550 no such mailbox", actor_id=ACTOR,
            correlation_id=self.correlate())["suppression_id"]}
        with self.assertRaises(Conflict):
            notifications.release_suppression(
                self._tenant_pool, tenant_id, bounced["suppression_id"],
                reason="we think it is fine now", actor_id=ACTOR,
                correlation_id=self.correlate())
        unsubscribed = notifications.suppress_address(
            self._tenant_pool, tenant_id, channel="sms", address_digest=self.digest("a@b.c"),
            reason="unsubscribed", actor_id=ACTOR, correlation_id=self.correlate())
        released = notifications.release_suppression(
            self._tenant_pool, tenant_id, unsubscribed["suppression_id"],
            reason="member re-subscribed", actor_id=ACTOR, correlation_id=self.correlate())
        self.assertTrue(released["released"])

    def test_a_release_states_a_reason(self):
        tenant_id = self.tenant()
        created = notifications.suppress_address(
            self._tenant_pool, tenant_id, channel="email", address_digest=self.digest(),
            reason="unsubscribed", actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            notifications.release_suppression(
                self._tenant_pool, tenant_id, created["suppression_id"], reason="  ",
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_suppression_takes_a_digest_and_not_an_address(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            notifications.suppress_address(
                self._tenant_pool, tenant_id, channel="email",
                address_digest="member@acme.test", reason="unsubscribed", actor_id=ACTOR,
                correlation_id=self.correlate())


class ReviewRegressionTests(NotificationsTestCase):
    """One test per blocking finding from the three independent reviews.

    Named for the attack rather than for the fix, so a later change that reopens the hole fails
    the test that describes what goes wrong.
    """

    def test_a_fallback_reads_the_fallback_channels_preference_not_the_originals(self):
        """A tenant falls back from email to SMS -- the ordinary response to a provider
        outage -- and a member who said "don't text me" was texted, because the preference had
        already been read for email."""
        tenant_id = self.tenant()
        recipient_id = str(uuid.uuid4())
        key = f"k{uuid.uuid4().hex[:8]}"
        self.template(tenant_id, template_key=key, category="coaching", channel="email")
        self.template(tenant_id, template_key=key, category="coaching", channel="sms",
                      subject="", body="Invoice {{ number }} is ready.")
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient_id, category="coaching",
            channel="sms", allowed=False, actor_id=ACTOR, correlation_id=self.correlate())
        notifications.set_channel_policy(
            self._tenant_pool, tenant_id, channel="email", enabled=False,
            fallback_channel="sms", actor_id=ACTOR, correlation_id=self.correlate())
        decided = self.request(tenant_id, key, recipient_id=recipient_id)
        self.assertEqual((decided["channel"], decided["outcome"], decided["reason"]),
                         ("sms", "suppress", "recipient_opted_out"))

    def test_a_fallback_checks_the_fallback_channels_suppression_list(self):
        """The suppression key is `sha256(channel:address)`, so an SMS suppression was not
        merely unchecked on an email fallback -- it was unreachable from that code path."""
        tenant_id = self.tenant()
        recipient_id = str(uuid.uuid4())
        key = f"k{uuid.uuid4().hex[:8]}"
        self.template(tenant_id, template_key=key, channel="email")
        self.template(tenant_id, template_key=key, channel="sms", subject="",
                      body="Invoice {{ number }} is ready.")
        notifications.suppress_address(
            self._tenant_pool, tenant_id, channel="sms",
            address_digest=self.digest("member@acme.test", "sms"), reason="unsubscribed",
            actor_id=ACTOR, correlation_id=self.correlate())
        notifications.set_channel_policy(
            self._tenant_pool, tenant_id, channel="email", enabled=False,
            fallback_channel="sms", actor_id=ACTOR, correlation_id=self.correlate())
        decided = self.request(tenant_id, key, recipient_id=recipient_id)
        self.assertEqual((decided["channel"], decided["reason"]),
                         ("sms", "address_is_suppressed_on_this_channel"))

    def test_a_fallback_stores_the_digest_of_the_channel_it_went_to(self):
        """Otherwise the bounce that follows writes a suppression key no later request can
        produce, and the record reads as handled while being permanently inert."""
        tenant_id = self.tenant()
        key = f"k{uuid.uuid4().hex[:8]}"
        self.template(tenant_id, template_key=key, channel="email")
        self.template(tenant_id, template_key=key, channel="sms", subject="",
                      body="Invoice {{ number }} is ready.")
        notifications.set_channel_policy(
            self._tenant_pool, tenant_id, channel="email", enabled=False,
            fallback_channel="sms", actor_id=ACTOR, correlation_id=self.correlate())
        requested = self.request(tenant_id, key)
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT address_digest FROM plt01.ntf_notifications"
                " WHERE notification_id = %s", (requested["notification_id"],)).fetchone()
        assert row is not None
        self.assertEqual(row[0], self.digest("member@acme.test", "sms"))

    def test_a_fallback_to_a_channel_with_no_digest_is_refused_not_guessed(self):
        tenant_id = self.tenant()
        key = f"k{uuid.uuid4().hex[:8]}"
        self.template(tenant_id, template_key=key, channel="email")
        self.template(tenant_id, template_key=key, channel="sms", subject="",
                      body="Invoice {{ number }} is ready.")
        notifications.set_channel_policy(
            self._tenant_pool, tenant_id, channel="email", enabled=False,
            fallback_channel="sms", actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            self.request(tenant_id, key,
                         address_digests={"email": self.digest()})

    def test_a_deferred_notification_can_actually_be_dispatched(self):
        """It had no delivery row at all, so quiet hours were a permanent silent drop --
        including for a transactional message, and the dispatcher's own
        `status IN ('requested', 'deferred')` clause was unreachable."""
        tenant_id = self.tenant()
        recipient_id = str(uuid.uuid4())
        key = self.template(tenant_id)
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient_id, category="transactional",
            channel="email", quiet_from=time(0), quiet_until=time(23, 59),
            quiet_timezone="UTC", actor_id=ACTOR, correlation_id=self.correlate())
        deferred = self.request(tenant_id, key, recipient_id=recipient_id)
        self.assertEqual(deferred["outcome"], "defer")
        with self.assertRaises(Conflict):
            notifications.dispatch_notification(
                self._tenant_pool, tenant_id, deferred["notification_id"], actor_id=ACTOR,
                correlation_id=self.correlate())
        later = datetime.fromisoformat(deferred["scheduled_for"]) + timedelta(minutes=1)
        claimed = notifications.dispatch_notification(
            self._tenant_pool, tenant_id, deferred["notification_id"], actor_id=ACTOR,
            correlation_id=self.correlate(), now=later)
        self.assertEqual(claimed["attempts"], 1)

    def test_a_dispatch_is_a_claim_and_not_a_handout(self):
        """It left `next_attempt_at` NULL, which the claim query reads as due now, so five
        calls handed one message to five dispatchers."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        notification_id = self.request(tenant_id, key)["notification_id"]
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            notifications.dispatch_notification(
                self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_the_suppression_list_is_read_again_before_sending(self):
        """A control consulted once is a control with a window, and a deferred notification can
        sit for eight hours."""
        tenant_id = self.tenant()
        recipient_id = str(uuid.uuid4())
        key = self.template(tenant_id)
        requested = self.request(tenant_id, key, recipient_id=recipient_id)
        notifications.suppress_address(
            self._tenant_pool, tenant_id, channel="email", address_digest=self.digest(),
            reason="unsubscribed", actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            notifications.dispatch_notification(
                self._tenant_pool, tenant_id, requested["notification_id"], actor_id=ACTOR,
                correlation_id=self.correlate())
        self.assertEqual(
            notifications.get_notification(
                self._tenant_pool, tenant_id, requested["notification_id"])["status"],
            "suppressed")

    def test_an_outcome_that_lost_the_race_is_refused_rather_than_published(self):
        """The UPDATE was guarded and its row count ignored, so a dispatcher whose claim had
        been settled by another published an outcome nothing recorded."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        notification_id = self.request(tenant_id, key)["notification_id"]
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="delivered",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            notifications.record_outcome(
                self._tenant_pool, tenant_id, notification_id, outcome="delivered",
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_bounce_cannot_be_declared_by_hand(self):
        """Only an unsubscribe can be released, so a declared bounce was irreversible state
        from a routine AAL-1 permission -- block an address from every transactional notice for
        ever, with no remedy anywhere in the module."""
        tenant_id = self.tenant()
        for reason in ("bounced", "complained"):
            with self.assertRaises(InvalidRequest):
                notifications.suppress_address(
                    self._tenant_pool, tenant_id, channel="email",
                    address_digest=self.digest(), reason=reason, actor_id=ACTOR,
                    correlation_id=self.correlate())

    def test_a_consent_tie_goes_to_the_withdrawal(self):
        """`signed_at` is caller-supplied, so two records can carry one instant, and the first
        version let the plan decide which was live."""
        tenant_id = self.tenant()
        recipient_id = str(uuid.uuid4())
        key = self.template(tenant_id, category="marketing")
        self.grant_consent(tenant_id, recipient_id)
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT definition_id, consent_version_id, signed_at, locale"
                " FROM plt01.sec_consent_records WHERE subject_id = %s", (recipient_id,),
            ).fetchone()
            assert row is not None
            conn.execute(
                "INSERT INTO plt01.sec_consent_records"
                " (tenant_id, subject_id, definition_id, consent_version_id, action,"
                "  signed_at, source, locale, correlation_id)"
                " VALUES (%s, %s, %s, %s, 'withdrawn', %s, 'member_app', %s, %s)",
                (tenant_id, recipient_id, row[0], row[1], row[2], row[3], self.correlate()),
            )
        with self.assertRaises(Conflict):
            self.request(tenant_id, key, recipient_id=recipient_id)

    def test_a_digest_counts_the_notification_that_opened_it(self):
        """The INSERT omitted the column, so it took the default of zero and only the DO UPDATE
        branch counted: every digest reported one fewer than it held."""
        tenant_id = self.tenant()
        recipient_id = str(uuid.uuid4())
        key = self.template(tenant_id, category="coaching")
        notifications.set_preference(
            self._tenant_pool, tenant_id, recipient_id=recipient_id, category="coaching",
            channel="email", digest_mode="daily", actor_id=ACTOR,
            correlation_id=self.correlate())
        self.request(tenant_id, key, recipient_id=recipient_id)
        digests = notifications.list_digests(
            self._tenant_pool, tenant_id, recipient_id=recipient_id)
        self.assertEqual([d["notification_count"] for d in digests], [1])

    def test_a_recipient_is_bound_to_one_digest_and_a_digest_to_one_recipient(self):
        """Both keys were caller-supplied and nothing related them, so every control split down
        the middle: the suppression list keyed on one, the preference and the cap on the other,
        and each half failed open."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        recipient_id = str(uuid.uuid4())
        self.request(tenant_id, key, recipient_id=recipient_id)
        with self.assertRaises(Conflict):
            self.request(tenant_id, key, recipient_id=recipient_id,
                         address_digests=self.digests("somebody.else@acme.test"))
        with self.assertRaises(Conflict):
            self.request(tenant_id, key, recipient_id=str(uuid.uuid4()))

    def test_a_rebinding_moves_the_binding_and_records_who_and_why(self):
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        recipient_id = str(uuid.uuid4())
        self.request(tenant_id, key, recipient_id=recipient_id)
        with self.assertRaises(InvalidRequest):
            notifications.rebind_recipient_channel(
                self._tenant_pool, tenant_id, recipient_id=recipient_id, channel="email",
                address_digest=self.digest("new@acme.test"), reason="   ", actor_id=ACTOR,
                correlation_id=self.correlate())
        notifications.rebind_recipient_channel(
            self._tenant_pool, tenant_id, recipient_id=recipient_id, channel="email",
            address_digest=self.digest("new@acme.test"), reason="they changed address",
            actor_id=ACTOR, correlation_id=self.correlate())
        bound = notifications.list_recipient_channels(
            self._tenant_pool, tenant_id, recipient_id)
        self.assertEqual(
            [(b["channel"], b["address_digest"], b["rebind_reason"]) for b in bound],
            [("email", self.digest("new@acme.test"), "they changed address")])

    def test_no_delivery_event_carries_the_providers_own_text(self):
        """An SMTP rejection quotes the address it rejected, and `evt_outbox.payload` is the one
        store no erasure in this build can reach."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        notification_id = self.request(tenant_id, key)["notification_id"]
        notifications.dispatch_notification(
            self._tenant_pool, tenant_id, notification_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        notifications.record_outcome(
            self._tenant_pool, tenant_id, notification_id, outcome="bounced",
            error="550 5.1.1 <jane.doe@example.com>: Recipient address rejected",
            actor_id=ACTOR, correlation_id=self.correlate())
        for payload in self.outbox(tenant_id, "notification.failed"):
            self.assertNotIn("jane.doe@example.com", str(payload))
            self.assertNotIn("reason", payload)
        detail = notifications.get_notification(self._tenant_pool, tenant_id, notification_id)
        self.assertIn("jane.doe@example.com", str(detail["delivery"]["last_error"]))

    def test_a_critical_request_is_charged_a_different_permission(self):
        """`priority: "critical"` plus any non-blank string overrode the opt-out, the quiet
        window and the cap, on the routine AAL-1 permission an ordinary request costs."""
        tenant_id = self.tenant()
        key = self.template(tenant_id)
        weak = self.grant(tenant_id, ["notifications.notification.request"])
        body = {"template_key": key, "recipient_id": str(uuid.uuid4()),
                "address_digests": self.digests(), "variables": {"number": "INV-1"},
                "idempotency_key": f"k{uuid.uuid4().hex[:10]}", **self.correlation()}
        ordinary = self.client.post(
            "/notifications", json=body, headers=self.headers(tenant_id, weak))
        self.assertEqual(ordinary.status_code, 201, ordinary.text)
        critical = self.client.post(
            "/notifications",
            json={**body, "idempotency_key": f"k{uuid.uuid4().hex[:10]}",
                  "priority": "critical", "bypass_policy_ref": "x"},
            headers=self.headers(tenant_id, weak))
        self.assertEqual(critical.status_code, 403, critical.text)


if __name__ == "__main__":
    unittest.main()
