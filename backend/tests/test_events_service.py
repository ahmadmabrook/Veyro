"""MOD-010 DAT-01 service against a real database.

The properties worth a database are the ones a mock would assert into existence: that an event
appended in a transaction that rolls back is not there, that a consumer seeing the same event
twice acts once, that a failure costs exactly one attempt, and that a replay into a consumer
which sends messages sends nothing.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.db import tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import catalog
from app.events import service as events
from tests.support import GatedApiTestCase

ACTOR = "33333333-3333-4333-8333-333333333333"


def _payload(name: str, version: int = 1) -> dict[str, object]:
    """A payload that satisfies the catalogue for this event type, whatever it declares."""
    return {field: f"v-{field}" for field in catalog.require_event(name, version).fields}


class EventsTestCase(GatedApiTestCase):
    def append(self, tenant_id: str, event_type: str = "tenant.provisioned",
               **kwargs: object) -> str:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            return events.append_event(
                conn, tenant_id, event_type=event_type,
                aggregate_type=kwargs.pop("aggregate_type", "tenant"),  # type: ignore[arg-type]
                aggregate_id=kwargs.pop("aggregate_id", tenant_id),  # type: ignore[arg-type]
                payload=kwargs.pop("payload", _payload(event_type)),  # type: ignore[arg-type]
                correlation_id=kwargs.pop("correlation_id", str(uuid.uuid4())),  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )

    def subscribe(self, tenant_id: str, consumer: str,
                  event_type: str = "tenant.provisioned", **kwargs: object) -> dict:
        return events.subscribe(
            self._tenant_pool, tenant_id, consumer=consumer, event_type=event_type,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()), **kwargs,  # type: ignore[arg-type]
        )


class AtomicAppendTests(EventsTestCase):
    """The one property the whole module exists for."""

    def test_an_event_appended_in_a_rolled_back_transaction_does_not_exist(self):
        """`append_event` takes a connection precisely so this is true. A version that took a
        pool would open its own transaction and the event would survive a business change that
        did not -- a consumer acting on something that never happened."""
        tenant_id = self.tenant()
        try:
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                events.append_event(
                    conn, tenant_id, event_type="tenant.provisioned",
                    aggregate_type="tenant", aggregate_id=tenant_id,
                    payload=_payload("tenant.provisioned"),
                    correlation_id=str(uuid.uuid4()),
                )
                raise RuntimeError("the business change failed after the append")
        except RuntimeError:
            pass
        self.assertEqual(events.outbox_health(self._tenant_pool, tenant_id)["pending_events"], 0)

    def test_an_event_appended_in_a_committed_transaction_is_pending(self):
        tenant_id = self.tenant()
        event_id = self.append(tenant_id)
        health = events.outbox_health(self._tenant_pool, tenant_id)
        self.assertEqual(health["pending_events"], 1)
        self.assertEqual(
            events.get_event(self._tenant_pool, tenant_id, event_id=event_id)["status"],
            "pending")

    def test_the_event_id_is_generated_and_cannot_be_supplied(self):
        """It is globally unique across tenants, so a caller able to choose it could probe for
        another tenant's events by watching which values collide."""
        tenant_id = self.tenant()
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            with self.assertRaises(TypeError):
                events.append_event(  # type: ignore[call-arg]
                    conn, tenant_id, event_id=str(uuid.uuid4()),
                    event_type="tenant.provisioned", aggregate_type="tenant",
                    aggregate_id=tenant_id, payload=_payload("tenant.provisioned"),
                    correlation_id=str(uuid.uuid4()))

    def test_an_unknown_event_type_cannot_be_appended(self):
        tenant_id = self.tenant()
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            with self.assertRaises(catalog.CatalogError):
                events.append_event(
                    conn, tenant_id, event_type="tenant.exploded", aggregate_type="tenant",
                    aggregate_id=tenant_id, payload={"a": 1},
                    correlation_id=str(uuid.uuid4()))

    def test_a_payload_carrying_an_undeclared_field_is_refused(self):
        """At the producer, which is the only place it is cheap. After the append it is in
        every consumer, the archive and every later replay."""
        tenant_id = self.tenant()
        payload = _payload("tenant.provisioned") | {"internal_note": "do not ship"}
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            with self.assertRaises(catalog.CatalogError):
                events.append_event(
                    conn, tenant_id, event_type="tenant.provisioned",
                    aggregate_type="tenant", aggregate_id=tenant_id, payload=payload,
                    correlation_id=str(uuid.uuid4()))

    def test_the_same_idempotency_key_twice_is_refused(self):
        """A command that may itself be retried appends with a key, and the second attempt is
        refused rather than silently duplicating the event."""
        tenant_id = self.tenant()
        key = f"k-{uuid.uuid4().hex[:8]}"
        self.append(tenant_id, idempotency_key=key)
        with self.assertRaises(Conflict):
            self.append(tenant_id, idempotency_key=key)

    def test_the_same_key_in_two_tenants_is_fine(self):
        """The producer's handle is tenant-scoped; only the generated id spans tenants."""
        first, second = self.tenant(), self.tenant()
        key = f"k-{uuid.uuid4().hex[:8]}"
        self.append(first, idempotency_key=key)
        self.append(second, idempotency_key=key)

    def test_a_blank_idempotency_key_is_refused(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            self.append(tenant_id, idempotency_key="   ")


class IsolationTests(EventsTestCase):
    def test_one_tenants_events_are_invisible_to_another(self):
        first, second = self.tenant(), self.tenant()
        self.append(first)
        self.assertEqual(
            events.outbox_health(self._tenant_pool, second)["pending_events"], 0)

    def test_an_event_cannot_be_read_from_the_wrong_tenant(self):
        first, second = self.tenant(), self.tenant()
        event_id = self.append(first)
        with self.assertRaises(NotFound):
            events.get_event(self._tenant_pool, second, event_id=event_id)


class DispatchTests(EventsTestCase):
    def test_dispatch_creates_one_delivery_per_active_subscriber(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe")
        self.subscribe(tenant_id, "analytics", replay_safety="safe")
        event_id = self.append(tenant_id)

        result = events.dispatch_pending(self._tenant_pool, tenant_id)
        self.assertEqual(result, {"events_dispatched": 1, "deliveries_created": 2})
        read = events.get_event(self._tenant_pool, tenant_id, event_id=event_id)
        self.assertEqual(read["status"], "dispatched")
        self.assertEqual({d["consumer"] for d in read["deliveries"]},
                         {"timeline", "analytics"})

    def test_dispatching_twice_creates_no_duplicate_deliveries(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe")
        self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        again = events.dispatch_pending(self._tenant_pool, tenant_id)
        self.assertEqual(again["events_dispatched"], 0)

    def test_an_event_with_no_subscriber_is_still_marked_dispatched(self):
        """Leaving it pending for ever in case somebody subscribes later means the pending set
        grows without bound and the claim index stops being selective. Replay is the tool for a
        consumer that arrived late."""
        tenant_id = self.tenant()
        event_id = self.append(tenant_id)
        self.assertEqual(
            events.dispatch_pending(self._tenant_pool, tenant_id),
            {"events_dispatched": 1, "deliveries_created": 0})
        self.assertEqual(
            events.get_event(self._tenant_pool, tenant_id, event_id=event_id)["status"],
            "dispatched")

    def test_an_inactive_subscription_receives_nothing(self):
        tenant_id = self.tenant()
        sub = self.subscribe(tenant_id, "timeline", replay_safety="safe")
        events.unsubscribe(self._tenant_pool, tenant_id,
                           subscription_id=sub["subscription_id"], actor_id=ACTOR,
                           correlation_id=str(uuid.uuid4()))
        self.append(tenant_id)
        self.assertEqual(
            events.dispatch_pending(self._tenant_pool, tenant_id)["deliveries_created"], 0)

    def test_a_consumer_cannot_subscribe_to_the_same_type_twice(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline")
        with self.assertRaises(Conflict):
            self.subscribe(tenant_id, "timeline")

    def test_a_subscription_to_an_unknown_event_type_is_refused(self):
        tenant_id = self.tenant()
        with self.assertRaises(catalog.CatalogError):
            self.subscribe(tenant_id, "timeline", event_type="tenant.exploded")


class DeliveryTests(EventsTestCase):
    def test_a_handler_runs_once_and_the_delivery_is_marked_handled(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe")
        event_id = self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)

        seen: list[str] = []
        result = events.deliver_pending(
            self._tenant_pool, tenant_id, consumer="timeline",
            handlers={"timeline": lambda e: seen.append(e["event_id"])})
        self.assertEqual(result["handled"], 1)
        self.assertEqual(seen, [event_id])

        read = events.get_event(self._tenant_pool, tenant_id, event_id=event_id)
        self.assertEqual(read["deliveries"][0]["status"], "handled")
        self.assertEqual(read["deliveries"][0]["attempts"], 1)

    def test_a_handled_delivery_is_never_run_again(self):
        """At-least-once means the consumer sees the event twice; the row saying `handled` is
        what makes the second time cost nothing."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe")
        self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        seen: list[str] = []
        handlers = {"timeline": lambda e: seen.append(e["event_id"])}
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="timeline",
                               handlers=handlers)
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="timeline",
                               handlers=handlers)
        self.assertEqual(len(seen), 1)

    def test_the_handler_receives_the_whole_envelope(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "consent.granted", event_type="consent.granted",
                       replay_safety="safe")
        correlation = str(uuid.uuid4())
        self.append(tenant_id, event_type="consent.granted", aggregate_type="subject",
                    aggregate_id=str(uuid.uuid4()), correlation_id=correlation)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        received: list[dict] = []
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="consent.granted",
                               handlers={"consent.granted": received.append})
        self.assertEqual(received[0]["event_type"], "consent.granted")
        self.assertEqual(received[0]["correlation_id"], correlation)
        self.assertEqual(set(received[0]["payload"]),
                         set(catalog.require_event("consent.granted", 1).fields))

    def test_one_handler_failing_does_not_undo_the_deliveries_that_worked(self):
        """Each delivery is its own transaction. A shared one would roll the successes back
        with the failure, and the attempt count of the failure with them."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe")
        first = self.append(tenant_id)
        second = self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)

        def flaky(event: dict) -> None:
            if event["event_id"] == second:
                raise RuntimeError("downstream is down")

        result = events.deliver_pending(self._tenant_pool, tenant_id, consumer="timeline",
                                        handlers={"timeline": flaky})
        self.assertEqual(result["handled"], 1)
        self.assertEqual(result["retrying"], 1)
        statuses = {
            d["consumer"]: d["status"]
            for event_id in (first, second)
            for d in events.get_event(self._tenant_pool, tenant_id,
                                      event_id=event_id)["deliveries"]
        }
        self.assertEqual(statuses["timeline"], "pending")  # the second one
        self.assertEqual(
            events.get_event(self._tenant_pool, tenant_id,
                             event_id=first)["deliveries"][0]["status"],
            "handled")

    def test_a_failure_costs_exactly_one_attempt_and_records_why(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe", max_attempts=3)
        event_id = self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)

        def boom(_: dict) -> None:
            raise ValueError("handler is unhappy")

        events.deliver_pending(self._tenant_pool, tenant_id, consumer="timeline",
                               handlers={"timeline": boom})
        delivery = events.get_event(self._tenant_pool, tenant_id,
                                    event_id=event_id)["deliveries"][0]
        self.assertEqual(delivery["attempts"], 1)
        self.assertEqual(delivery["status"], "pending")
        self.assertIn("handler is unhappy", delivery["last_error"])

    def test_no_handler_for_the_consumer_is_a_refusal_not_a_silent_skip(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            events.deliver_pending(self._tenant_pool, tenant_id, consumer="nobody",
                                   handlers={})


class DeadLetterTests(EventsTestCase):
    def _exhaust(self, tenant_id: str, max_attempts: int = 2) -> str:
        self.subscribe(tenant_id, "ledger", replay_safety="safe", max_attempts=max_attempts)
        event_id = self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)

        def boom(_: dict) -> None:
            raise ValueError("permanently broken")

        for _ in range(max_attempts):
            # Each pass has to clear the backoff the previous one set, or the delivery is not
            # due and the loop would exit having proved nothing.
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                conn.execute("UPDATE plt01.evt_deliveries SET available_at = now()"
                             " WHERE consumer = 'ledger'")
            events.deliver_pending(self._tenant_pool, tenant_id, consumer="ledger",
                                   handlers={"ledger": boom})
        return event_id

    def test_an_exhausted_delivery_is_quarantined_with_its_reason(self):
        tenant_id = self.tenant()
        event_id = self._exhaust(tenant_id)
        letters = events.list_dead_letters(self._tenant_pool, tenant_id)
        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0]["event_id"], event_id)
        self.assertEqual(letters[0]["consumer"], "ledger")
        self.assertEqual(letters[0]["attempts"], 2)
        self.assertIn("permanently broken", letters[0]["reason"])
        self.assertEqual(
            events.outbox_health(self._tenant_pool, tenant_id)["dead_letters"], 1)

    def test_a_dead_delivery_is_not_claimed_again(self):
        tenant_id = self.tenant()
        self._exhaust(tenant_id)
        seen: list[dict] = []
        result = events.deliver_pending(self._tenant_pool, tenant_id, consumer="ledger",
                                        handlers={"ledger": seen.append})
        self.assertEqual(result["handled"], 0)
        self.assertEqual(seen, [])

    def test_releasing_a_dead_letter_requeues_it_with_a_fresh_budget(self):
        """The operator is asserting that whatever failed has been fixed. A release that kept
        the exhausted count would dead-letter again on the first attempt."""
        tenant_id = self.tenant()
        self._exhaust(tenant_id)
        letter = events.list_dead_letters(self._tenant_pool, tenant_id)[0]
        released = events.release_dead_letter(
            self._tenant_pool, tenant_id, dead_letter_id=letter["dead_letter_id"],
            reason="downstream fixed", actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        self.assertTrue(released["requeued"])

        seen: list[dict] = []
        result = events.deliver_pending(self._tenant_pool, tenant_id, consumer="ledger",
                                        handlers={"ledger": seen.append})
        self.assertEqual(result["handled"], 1)
        self.assertEqual(len(seen), 1)

    def test_a_release_is_attributed_and_needs_a_reason(self):
        tenant_id = self.tenant()
        self._exhaust(tenant_id)
        letter = events.list_dead_letters(self._tenant_pool, tenant_id)[0]
        with self.assertRaises(InvalidRequest):
            events.release_dead_letter(
                self._tenant_pool, tenant_id, dead_letter_id=letter["dead_letter_id"],
                reason="   ", actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        events.release_dead_letter(
            self._tenant_pool, tenant_id, dead_letter_id=letter["dead_letter_id"],
            reason="fixed", actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        with self.assertRaises(NotFound):
            events.release_dead_letter(
                self._tenant_pool, tenant_id, dead_letter_id=letter["dead_letter_id"],
                reason="again", actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        history = events.list_dead_letters(self._tenant_pool, tenant_id,
                                           include_released=True)
        self.assertEqual(history[0]["released_by"], ACTOR)
        self.assertEqual(history[0]["release_reason"], "fixed")


class ReplayTests(EventsTestCase):
    def _window(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(hours=1), now + timedelta(hours=1)

    def test_a_replay_into_a_safe_consumer_queues_the_events(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "projection", replay_safety="safe")
        self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="projection",
                               handlers={"projection": lambda _: None})

        # A new consumer that arrived late is the ordinary case for replay.
        self.subscribe(tenant_id, "projection_v2", replay_safety="safe")
        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="projection_v2",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        result = events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        self.assertEqual(result["actions"], {"tenant.provisioned": "deliver"})
        self.assertEqual(result["events_queued"], 1)

        seen: list[dict] = []
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="projection_v2",
                               handlers={"projection_v2": seen.append})
        self.assertEqual(len(seen), 1)

    def test_a_replay_into_a_suppress_consumer_sends_nothing(self):
        """The case the feature exists for: replaying a month of events into a consumer that
        sends email. The delivery row says `suppressed`, so the evidence shows the event was
        considered and deliberately skipped rather than lost."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "messaging", replay_safety="suppress")
        self.append(tenant_id)
        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="messaging",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        result = events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        self.assertEqual(result["actions"], {"tenant.provisioned": "suppress"})
        self.assertEqual(result["events_suppressed"], 1)

        seen: list[dict] = []
        delivered = events.deliver_pending(self._tenant_pool, tenant_id, consumer="messaging",
                                           handlers={"messaging": seen.append})
        self.assertEqual(delivered["handled"], 0)
        self.assertEqual(seen, [], "a suppressed replay must not reach the handler")

    def test_allowing_side_effects_needs_a_written_reason(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "messaging", replay_safety="suppress")
        start, end = self._window()
        with self.assertRaises(InvalidRequest) as caught:
            events.request_replay(
                self._tenant_pool, tenant_id, consumer="messaging",
                event_types=["tenant.provisioned"], from_time=start, to_time=end,
                actor_id=ACTOR, correlation_id=str(uuid.uuid4()), side_effects="allow")
        self.assertEqual(caught.exception.code,
                         "allowing_side_effects_on_a_replay_needs_a_reason")

    def test_allow_overrides_the_consumers_caution_when_somebody_says_why(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "messaging", replay_safety="suppress")
        self.append(tenant_id)
        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="messaging",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()), side_effects="allow",
            side_effects_reason="the provider dropped the originals; confirmed with the owner")
        result = events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        self.assertEqual(result["actions"], {"tenant.provisioned": "deliver"})

    def test_a_replay_does_not_re_run_a_consumer_that_already_handled_the_event(self):
        """The deduplication is what makes a replay safe to run twice."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "projection", replay_safety="safe")
        self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        seen: list[dict] = []
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="projection",
                               handlers={"projection": seen.append})

        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="projection",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="projection",
                               handlers={"projection": seen.append})
        self.assertEqual(len(seen), 1, "the handled row is the deduplication")

    def test_a_job_runs_once(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "projection", replay_safety="safe")
        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="projection",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        with self.assertRaises(Conflict):
            events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))

    def test_a_replay_for_a_consumer_with_no_subscription_is_refused(self):
        tenant_id = self.tenant()
        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="ghost",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        with self.assertRaises(NotFound):
            events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))

    def test_a_backwards_or_empty_replay_is_refused_before_a_row_exists(self):
        tenant_id = self.tenant()
        start, end = self._window()
        with self.assertRaises(InvalidRequest):
            events.request_replay(
                self._tenant_pool, tenant_id, consumer="projection",
                event_types=["tenant.provisioned"], from_time=end, to_time=start,
                actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        with self.assertRaises(InvalidRequest):
            events.request_replay(
                self._tenant_pool, tenant_id, consumer="projection", event_types=[],
                from_time=start, to_time=end, actor_id=ACTOR,
                correlation_id=str(uuid.uuid4()))


class ReviewRegressionTests(EventsTestCase):
    """One test per defect an independent review of MOD-010 found, named for the attack.

    Three of the four blockers were one mistake: `run_replay` decided once for a job and then
    acted per event. Each of these passed the happy-path suite above.
    """

    def _window(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(hours=1), now + timedelta(hours=1)

    def test_listing_a_second_event_type_does_not_defeat_default_suppress(self):
        """A consumer `safe` for one type and `suppress` for another had its suppress-class
        events delivered under the default policy -- TSD paragraph 200 defeated by a caller who
        only had to name a second type, with `suppress` recorded on the job and no reason
        written anywhere."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "messaging", event_type="tenant.activated",
                       replay_safety="safe")
        self.subscribe(tenant_id, "messaging", event_type="tenant.provisioned",
                       replay_safety="suppress")
        self.append(tenant_id, event_type="tenant.activated")
        self.append(tenant_id, event_type="tenant.provisioned")

        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="messaging",
            event_types=["tenant.activated", "tenant.provisioned"],
            from_time=start, to_time=end, actor_id=ACTOR,
            correlation_id=str(uuid.uuid4()))
        result = events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        self.assertEqual(result["actions"], {"tenant.activated": "deliver",
                                             "tenant.provisioned": "suppress"})

        seen: list[dict] = []
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="messaging",
                               handlers={"messaging": seen.append})
        self.assertEqual([e["event_type"] for e in seen], ["tenant.activated"],
                         "the suppress-class event must not reach the handler")

    def test_the_other_ordering_does_not_suppress_the_type_the_operator_asked_for(self):
        """The same defect in its other direction, and the worse one: a `suppressed` delivery
        row is terminal and every later insert is ON CONFLICT DO NOTHING, so a wrongly
        suppressed replay could not be undone by anything in this module."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "messaging", event_type="tenant.provisioned",
                       replay_safety="suppress")
        self.subscribe(tenant_id, "messaging", event_type="tenant.activated",
                       replay_safety="safe")
        self.append(tenant_id, event_type="tenant.activated")

        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="messaging",
            event_types=["tenant.provisioned", "tenant.activated"],
            from_time=start, to_time=end, actor_id=ACTOR,
            correlation_id=str(uuid.uuid4()))
        events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        seen: list[dict] = []
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="messaging",
                               handlers={"messaging": seen.append})
        self.assertEqual([e["event_type"] for e in seen], ["tenant.activated"])

    def test_a_replay_cannot_route_an_event_type_the_consumer_never_subscribed_to(self):
        """`event_types` is caller-supplied over HTTP. The events query filtered on the job's
        list alone, so a holder of the replay permissions could route any event type in the
        tenant to any consumer name -- bypassing `evt_subscriptions`, the table that is supposed
        to be the routing authority."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "ledger", event_type="tenant.activated",
                       replay_safety="safe")
        self.append(tenant_id, event_type="tenant.activated")
        self.append(tenant_id, event_type="tenant.provisioned")

        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="ledger",
            event_types=["tenant.activated", "tenant.provisioned"],
            from_time=start, to_time=end, actor_id=ACTOR,
            correlation_id=str(uuid.uuid4()))
        events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        seen: list[dict] = []
        events.deliver_pending(self._tenant_pool, tenant_id, consumer="ledger",
                               handlers={"ledger": seen.append})
        self.assertEqual([e["event_type"] for e in seen], ["tenant.activated"],
                         "the unsubscribed type must not be routed at all")

    def test_a_delivery_with_no_subscription_quarantines_instead_of_stalling_the_relay(self):
        """`_record_failure` raised out of the relay's batch loop, so one such delivery counted
        no attempt, wrote no error, never dead-lettered, and aborted every healthy delivery
        behind it -- for ever, since the poison row sorts first. `outbox_health` then reported a
        growing backlog with zero dead letters, pointing an operator away from the cause."""
        tenant_id = self.tenant()
        sub = self.subscribe(tenant_id, "orphan", replay_safety="safe", max_attempts=3)
        self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        # Deactivating the subscription leaves a pending delivery with nothing routing it.
        events.unsubscribe(self._tenant_pool, tenant_id,
                           subscription_id=sub["subscription_id"], actor_id=ACTOR,
                           correlation_id=str(uuid.uuid4()))

        def boom(_: dict) -> None:
            raise ValueError("nothing routes this")

        result = events.deliver_pending(self._tenant_pool, tenant_id, consumer="orphan",
                                        handlers={"orphan": boom})
        self.assertEqual(result["dead_lettered"], 1, "it must quarantine, not raise")
        letters = events.list_dead_letters(self._tenant_pool, tenant_id)
        self.assertEqual(len(letters), 1)
        self.assertIn("no active subscription", letters[0]["reason"])
        self.assertEqual(events.outbox_health(self._tenant_pool, tenant_id)["dead_letters"], 1)

    def test_one_poisoned_delivery_does_not_stop_the_ones_behind_it(self):
        tenant_id = self.tenant()
        good = self.subscribe(tenant_id, "mixed", event_type="tenant.activated",
                              replay_safety="safe")
        self.subscribe(tenant_id, "mixed", event_type="tenant.provisioned",
                       replay_safety="safe")
        self.append(tenant_id, event_type="tenant.provisioned")
        self.append(tenant_id, event_type="tenant.activated")
        events.dispatch_pending(self._tenant_pool, tenant_id)
        events.unsubscribe(self._tenant_pool, tenant_id,
                           subscription_id=good["subscription_id"], actor_id=ACTOR,
                           correlation_id=str(uuid.uuid4()))

        seen: list[dict] = []

        def flaky(event: dict) -> None:
            if event["event_type"] == "tenant.activated":
                raise ValueError("orphaned")
            seen.append(event)

        result = events.deliver_pending(self._tenant_pool, tenant_id, consumer="mixed",
                                        handlers={"mixed": flaky})
        self.assertEqual(result["handled"], 1)
        self.assertEqual([e["event_type"] for e in seen], ["tenant.provisioned"])

    def test_a_late_success_cannot_overwrite_a_settled_delivery(self):
        """The claim is a lease, not a lock, so a handler slower than its lease can have its row
        settled by another relay. Without `AND status = 'pending'` on the success UPDATE, the
        late writer overwrote that settlement -- leaving a delivery reading `handled` beside a
        live quarantine row, and an attempt count past the subscription's budget."""
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "slow", replay_safety="safe", max_attempts=1)
        event_id = self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)

        def slow(_: dict) -> None:
            # Settle the row underneath this handler, the way a second relay would.
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                conn.execute(
                    "UPDATE plt01.evt_deliveries SET status = 'dead', handled_at = now(),"
                    " attempts = 1, last_error = 'settled by another relay'"
                    " WHERE consumer = 'slow' AND event_id = %s", (event_id,))
                conn.execute(
                    "INSERT INTO plt01.evt_dead_letters"
                    " (tenant_id, event_id, consumer, reason, attempts)"
                    " VALUES (%s, %s, 'slow', 'settled by another relay', 1)",
                    (tenant_id, event_id))

        events.deliver_pending(self._tenant_pool, tenant_id, consumer="slow",
                               handlers={"slow": slow})
        delivery = events.get_event(self._tenant_pool, tenant_id,
                                    event_id=event_id)["deliveries"][0]
        self.assertEqual(delivery["status"], "dead", "the settlement must stand")
        self.assertLessEqual(delivery["attempts"], 1,
                             "a one-attempt budget cannot record two attempts")

    def test_a_deactivated_consumer_can_be_subscribed_again(self):
        """The unique key spans active and inactive rows and nothing ever set `active = true`,
        so a consumer deactivated by mistake was permanently unroutable -- and the error said
        `consumer_already_subscribed_to_this_event_type`, the opposite of what was true."""
        tenant_id = self.tenant()
        sub = self.subscribe(tenant_id, "comeback", replay_safety="safe")
        events.unsubscribe(self._tenant_pool, tenant_id,
                           subscription_id=sub["subscription_id"], actor_id=ACTOR,
                           correlation_id=str(uuid.uuid4()))
        again = self.subscribe(tenant_id, "comeback", replay_safety="idempotent")
        self.assertTrue(again["reactivated"])
        self.assertEqual(again["subscription_id"], sub["subscription_id"])
        self.assertEqual(again["replay_safety"], "idempotent")

        self.append(tenant_id)
        self.assertEqual(
            events.dispatch_pending(self._tenant_pool, tenant_id)["deliveries_created"], 1)

    def test_events_replayed_counts_rows_written_not_rows_considered(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "projection", replay_safety="safe")
        self.append(tenant_id)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        start, end = self._window()
        job = events.request_replay(
            self._tenant_pool, tenant_id, consumer="projection",
            event_types=["tenant.provisioned"], from_time=start, to_time=end,
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        result = events.run_replay(self._tenant_pool, tenant_id, job_id=job["job_id"],
                                   actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        self.assertEqual(result["events_replayed"], 0,
                         "the delivery already existed; nothing was written")


class ExplorerTests(EventsTestCase):
    def test_a_correlation_id_answers_what_this_request_caused(self):
        tenant_id = self.tenant()
        correlation = str(uuid.uuid4())
        self.append(tenant_id, correlation_id=correlation)
        self.append(tenant_id, event_type="tenant.activated", correlation_id=correlation)
        self.append(tenant_id, event_type="tenant.activated")  # a different correlation

        traced = events.trace(self._tenant_pool, tenant_id, correlation_id=correlation)
        self.assertEqual([t["event_type"] for t in traced],
                         ["tenant.provisioned", "tenant.activated"])

    def test_an_aggregate_has_a_timeline(self):
        tenant_id = self.tenant()
        aggregate = str(uuid.uuid4())
        self.append(tenant_id, aggregate_type="brand", aggregate_id=aggregate,
                    event_type="brand.created")
        self.append(tenant_id, aggregate_type="brand", aggregate_id=aggregate,
                    event_type="organization.updated")
        history = events.aggregate_history(self._tenant_pool, tenant_id,
                                           aggregate_type="brand", aggregate_id=aggregate)
        self.assertEqual([h["event_type"] for h in history],
                         ["brand.created", "organization.updated"])
        self.assertTrue(all("payload" not in h for h in history),
                        "the timeline says what happened, not what each event carried")

    def test_health_reports_the_backlog_an_operator_asks_about(self):
        tenant_id = self.tenant()
        self.subscribe(tenant_id, "timeline", replay_safety="safe")
        self.append(tenant_id)
        self.assertEqual(
            events.outbox_health(self._tenant_pool, tenant_id)["pending_events"], 1)
        events.dispatch_pending(self._tenant_pool, tenant_id)
        health = events.outbox_health(self._tenant_pool, tenant_id)
        self.assertEqual(health["pending_events"], 0)
        self.assertEqual(health["pending_deliveries"], 1)
        self.assertIsNotNone(health["oldest_undelivered_at"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
