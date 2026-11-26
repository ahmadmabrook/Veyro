"""MOD-020 OPS-02 over HTTP, with the credentials a real caller would hold.

**Driven through the routes, not the service.** MOD-014's reviewers found four defects in its
request path that a green suite could not see, MOD-016 had no test that had ever called a
`/catalog` route successfully, and MOD-019's HTTP tests found five defects in a module whose
domain suite was green -- two of them design errors rather than bugs.

The tests that matter most are the ones about paragraph 4697's two invariants: that capacity
never falls below zero, and that a duplicate waitlist promotion cannot consume two seats.
Neither is enforced in this module -- both are MOD-019's -- so these are the tests that prove
the borrowing works.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tests.support import DSN, GatedApiTestCase
from tests.test_commercial_api import CommercialApiTestCase


#: **UTC, not the local clock.** Every service in this build takes its "today" from
#: `datetime.now(UTC)`, and a fixture using `date.today()` disagrees with it in any timezone
#: east of UTC for as long as the two dates differ -- three hours a night here. A journal
#: posted on the local date was then outside a trial balance read as of the UTC date, and
#: sixteen tests across MOD-017 and MOD-018 failed for a reason that had nothing to do with
#: either module. CI never saw it because CI runs in UTC, where the two agree. Found while
#: running the full suite at 02:00.
#:
#: **A function, not a constant.** Evaluated once at import it is *yesterday* for every
#: test that runs after UTC midnight, while the service computes today -- which only CI
#: sees, because only CI runs a twelve-minute suite at 23:55Z. `test_commercial_api`
#: carries the finding and its mirror, the local-clock version this replaced.
def today() -> date:
    """Today in UTC, now rather than at import."""
    return datetime.now(UTC).date()


def day(offset: int) -> str:
    return (today() + timedelta(days=offset)).isoformat()


class BookingApiTestCase(GatedApiTestCase):
    """Fixtures: a gym with a published session, and a booking policy over it."""

    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman") -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        created = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": timezone}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["location_id"])

    def resource(self, tenant_id: str, kind: str, code: str, **extra: Any) -> str:
        created = self.client.post("/scheduling/resources", json={
            "resource_code": code, "resource_kind": kind,
            "display_name": f"A {kind}", **extra, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["resource_id"])

    def person(self, tenant_id: str, name: str = "Jane Smith",
               born: str | None = None) -> str:
        body: dict[str, Any] = {"legal_name": name, "profile_kinds": ["member"]}
        if born is not None:
            body["date_of_birth"] = born
        created = self.client.post("/people", json={**body, **self.correlation()},
                                   headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["person_id"])

    def policy(self, tenant_id: str, **rules: Any) -> str:
        key = rules.pop("policy_key", f"STD{uuid.uuid4().hex[:6].upper()}")
        created = self.client.post("/booking/policies", json={
            "policy_key": key, "display_name": "Standard", **rules,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(key)

    def gym(self, *, capacity: int = 12, starts_in_days: int = 1,
            waitlist_capacity: int = 0, restrictions: list[dict[str, Any]] | None = None,
            **policy_rules: Any) -> dict[str, Any]:
        """A tenant with one published session and a booking policy over it."""
        return self.gym_for(self.tenant(), capacity=capacity,
                            starts_in_days=starts_in_days,
                            waitlist_capacity=waitlist_capacity,
                            restrictions=restrictions, **policy_rules)

    def gym_for(self, tenant_id: str, *, capacity: int = 12, starts_in_days: int = 1,
                waitlist_capacity: int = 0,
                restrictions: list[dict[str, Any]] | None = None,
                **policy_rules: Any) -> dict[str, Any]:
        """The same, over a tenant somebody else made -- which a test spanning two modules
        needs, because a membership and a session have to belong to one gym."""
        location_id = self.location(tenant_id)
        suffix = uuid.uuid4().hex[:6].upper()
        studio = self.resource(tenant_id, "room", f"STUDIO-{suffix}",
                               location_id=location_id)
        service = self.resource(tenant_id, "service", f"SPIN-{suffix}")
        owner = self.headers(tenant_id)
        # A daily rule, so a session exists on the day the test wants one.
        template = self.client.post("/scheduling/templates", json={
            "template_code": f"SPIN-{suffix}", "display_name": "Spin",
            "service_resource_id": service, "location_id": location_id,
            "rule": {"frequency": "daily", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(starts_in_days),
                     "until": day(starts_in_days + 20), "weekdays": []},
            "policy": {"capacity": capacity, "opens_hours_before": 8000,
                       "waitlist_capacity": waitlist_capacity},
            "requirements": [
                {"kind": "service", "resource_id": service},
                {"kind": "room", "resource_id": studio},
            ], "restrictions": restrictions or [], **self.correlation()},
            headers=owner)
        self.assertEqual(template.status_code, 201, template.text)
        template_id = template.json()["template_id"]
        published = self.client.post(
            f"/scheduling/templates/{template_id}/publish",
            json=self.correlation(), headers=owner)
        self.assertEqual(published.status_code, 200, published.text)
        generated = self.client.post(
            f"/scheduling/templates/{template_id}/sessions",
            json=self.correlation(), headers=owner)
        self.assertEqual(generated.status_code, 201, generated.text)
        self.assertGreater(generated.json()["created"], 0, generated.text)
        sessions = generated.json()["sessions"]
        return {
            "tenant_id": tenant_id, "location_id": location_id,
            "template_id": template_id, "studio": studio, "service": service,
            "session_id": str(sessions[0]["session_id"]),
            "starts_at": sessions[0]["starts_at"],
            "sessions": [str(s["session_id"]) for s in sessions],
            "policy_key": self.policy(tenant_id, **policy_rules),
        }

    def book(self, gym: dict[str, Any], person_id: str, *,
             session_id: str | None = None, **extra: Any) -> Any:
        return self.client.post(
            f"/booking/sessions/{session_id or gym['session_id']}/bookings",
            json={"person_id": person_id, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **extra,
                  **self.correlation()},
            headers=self.headers(gym["tenant_id"]))

    def booked(self, gym: dict[str, Any], person_id: str, **extra: Any) -> str:
        response = self.book(gym, person_id, **extra)
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["booking_id"])

    def linked_decider(self, tenant_id: str) -> str:
        """The owner identity, linked to a person record of its own.

        **Deciding an appeal needs one.** `check_decider` used to permit a decider with no
        person record on the grounds that such an identity "is not the subject by definition",
        which is false for the coach who is also a member with a strike -- and both layers of
        the separation of duties then failed on the same missing `ppl_identity_links` row
        rather than independently. So a decider has to be somebody, and this is what makes the
        owner into one.
        """
        decider = self.person(tenant_id, name="Duty Manager")
        linked = self.client.post(
            f"/people/{decider}/identity-links",
            json={"identity_id": self.owner_identity(tenant_id),
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(linked.status_code, 201, linked.text)
        return decider

    def settled_no_show(self, gym: dict[str, Any], person_id: str) -> dict[str, Any]:
        """A real no-show record, produced by the real settlement path."""
        from app.booking import service as booking_service
        booking_id = self.booked(gym, person_id)
        session = self.client.get(f"/booking/bookings/{booking_id}",
                                  headers=self.headers(gym["tenant_id"])).json()
        ends_at = datetime.fromisoformat(session["session"]["ends_at"])
        result = booking_service.settle_session_bookings(
            self._tenant_pool, gym["tenant_id"], gym["session_id"],
            actor_id="33333333-3333-4333-8333-333333333333",
            correlation_id=str(uuid.uuid4()),
            at=ends_at + timedelta(hours=2))
        self.assertEqual(result["settled"], 1, result)
        detail = self.client.get(f"/booking/bookings/{booking_id}",
                                 headers=self.headers(gym["tenant_id"])).json()
        self.assertEqual(detail["state"], "no_show", detail)
        return {"booking_id": booking_id, "no_show": detail["no_show"]}


class BookingTests(BookingApiTestCase):
    """OPS-02-R01, and paragraph 4142's atomic reservation."""

    def test_a_booking_takes_a_place_and_cites_it(self):
        gym = self.gym()
        person_id = self.person(gym["tenant_id"])
        response = self.book(gym, person_id)
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["state"], "booked")
        self.assertTrue(body["hold_id"])
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster",
            headers=self.headers(gym["tenant_id"])).json()
        self.assertEqual(roster["held"], 1)
        self.assertEqual(roster["free"], 11)
        self.assertEqual(
            [b["person_id"] for b in roster["bookings"]], [person_id])

    def test_a_repeated_booking_is_the_same_booking(self):
        gym = self.gym()
        person_id = self.person(gym["tenant_id"])
        key = str(uuid.uuid4())
        body = {"person_id": person_id, "policy_key": gym["policy_key"],
                "idempotency_key": key}
        owner = self.headers(gym["tenant_id"])
        first = self.client.post(
            f"/booking/sessions/{gym['session_id']}/bookings",
            json={**body, **self.correlation()}, headers=owner)
        again = self.client.post(
            f"/booking/sessions/{gym['session_id']}/bookings",
            json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(again.json()["booking_id"], first.json()["booking_id"])
        self.assertTrue(again.json()["repeated"])
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 1)

    def test_a_key_reused_for_a_different_request_is_refused(self):
        """MOD-019 shipped a key compared on one field and handed one member another's hold."""
        gym = self.gym()
        first = self.person(gym["tenant_id"], "First")
        second = self.person(gym["tenant_id"], "Second")
        key = str(uuid.uuid4())
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/sessions/{gym['session_id']}/bookings", json={
            "person_id": first, "policy_key": gym["policy_key"],
            "idempotency_key": key, **self.correlation()}, headers=owner)
        reused = self.client.post(
            f"/booking/sessions/{gym['session_id']}/bookings", json={
                "person_id": second, "policy_key": gym["policy_key"],
                "idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(reused.status_code, 409, reused.text)

    def test_one_member_holds_one_place_on_a_session(self):
        gym = self.gym()
        person_id = self.person(gym["tenant_id"])
        self.booked(gym, person_id)
        again = self.book(gym, person_id)
        self.assertEqual(again.status_code, 409, again.text)

    def test_a_full_session_is_refused_and_offers_the_waitlist(self):
        """Paragraph 4697's first invariant, kept by MOD-019 rather than by this module."""
        gym = self.gym(capacity=1)
        self.booked(gym, self.person(gym["tenant_id"], "First"))
        second = self.person(gym["tenant_id"], "Second")
        refused = self.book(gym, second)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("full", refused.text)
        asked = self.client.get(
            f"/booking/sessions/{gym['session_id']}/eligibility"
            f"?person_id={second}&policy_key={gym['policy_key']}",
            headers=self.headers(gym["tenant_id"])).json()
        self.assertFalse(asked["may_book"])
        self.assertEqual(asked["reason"], "full")
        self.assertTrue(asked["offer_waitlist"])

    def test_the_denial_is_the_same_both_times(self):
        """Paragraph 5032's stable denial, over HTTP."""
        gym = self.gym(capacity=1)
        self.booked(gym, self.person(gym["tenant_id"], "First"))
        person_id = self.person(gym["tenant_id"], "Second")
        url = (f"/booking/sessions/{gym['session_id']}/eligibility"
               f"?person_id={person_id}&policy_key={gym['policy_key']}")
        owner = self.headers(gym["tenant_id"])
        first = self.client.get(url, headers=owner).json()
        second = self.client.get(url, headers=owner).json()
        self.assertEqual(first["reason"], second["reason"])
        self.assertEqual(first["offer_waitlist"], second["offer_waitlist"])

    def test_a_concurrent_limit_refuses_the_next_booking(self):
        gym = self.gym(max_concurrent=2)
        person_id = self.person(gym["tenant_id"])
        for session_id in gym["sessions"][:2]:
            response = self.book(gym, person_id, session_id=session_id)
            self.assertEqual(response.status_code, 201, response.text)
        third = self.book(gym, person_id, session_id=gym["sessions"][2])
        self.assertEqual(third.status_code, 409, third.text)
        self.assertIn("quota_reached", third.text)

    def test_a_quota_refuses_the_next_booking_and_says_when_it_rolls_over(self):
        gym = self.gym(quota=1, quota_period="rolling_30_days")
        person_id = self.person(gym["tenant_id"])
        self.booked(gym, person_id)
        asked = self.client.get(
            f"/booking/sessions/{gym['sessions'][1]}/eligibility"
            f"?person_id={person_id}&policy_key={gym['policy_key']}",
            headers=self.headers(gym["tenant_id"])).json()
        self.assertFalse(asked["may_book"])
        self.assertEqual(asked["reason"], "quota_reached")
        self.assertIsNotNone(asked["retry_at"])

    def test_a_cancelled_session_takes_no_bookings(self):
        gym = self.gym()
        owner = self.headers(gym["tenant_id"])
        cancelled = self.client.post(
            f"/scheduling/sessions/{gym['session_id']}/cancel", json={
                "cancellation_reason": "weather", "reason": "snow",
                **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        refused = self.book(gym, self.person(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_a_malformed_id_is_refused_rather_than_crashing(self):
        gym = self.gym()
        response = self.client.get("/booking/bookings/not-a-uuid",
                                   headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 422, response.text)


class EntitlementTests(BookingApiTestCase):
    """The entitlement a booking draws on is MOD-017's and is found by key, never named."""

    def test_a_booking_citing_an_entitlement_nobody_holds_is_refused(self):
        """**The reason is from the closed set now, and the read is what explains it.**
        `no_entitlement` was declared in `DENIAL_REASONS` and never produced: the refusal came
        as free prose from a lookup that ran after `_evaluate`, so the eligibility read -- the
        surface paragraph 1888's understandable denial exists for -- answered `may_book: true`
        and the command then refused. A stable code at the command and the sentence at the
        read is the split `denial.py` argues for.
        """
        gym = self.gym()
        person_id = self.person(gym["tenant_id"])
        refused = self.book(gym, person_id, entitlement_key="CLASS-PASS")
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no_entitlement", refused.text)
        read = self.client.get(
            f"/booking/sessions/{gym['session_id']}/eligibility",
            params={"person_id": person_id, "policy_key": gym["policy_key"],
                    "entitlement_key": "CLASS-PASS"},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertFalse(read.json()["may_book"])
        self.assertEqual(read.json()["reason"], "no_entitlement")
        self.assertIn("CLASS-PASS", read.json()["detail"])

    def test_a_booking_without_an_entitlement_needs_none(self):
        gym = self.gym()
        self.booked(gym, self.person(gym["tenant_id"]))


class CancellationTests(BookingApiTestCase):
    """OPS-02-R04: the consequence the booking's own policy declares."""

    def test_cancelling_in_time_costs_nothing_and_gives_the_place_back(self):
        gym = self.gym(cancellation_hours=1)
        person_id = self.person(gym["tenant_id"])
        booking_id = self.booked(gym, person_id)
        owner = self.headers(gym["tenant_id"])
        cancelled = self.client.post(
            f"/booking/bookings/{booking_id}/cancel",
            json={"reason": "something came up", **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = cancelled.json()
        self.assertEqual(body["occasion"], "cancelled_in_time")
        self.assertFalse(body["fee_due"])
        self.assertFalse(body["charged"])
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 0)

    def test_cancelling_late_is_recorded_as_due_and_not_charged(self):
        """It decides; MOD-017 charges. A row saying "charged" with nothing having charged is
        the shape this codebase has been bitten by five times."""
        gym = self.gym(cancellation_hours=168)
        person_id = self.person(gym["tenant_id"])
        booking_id = self.booked(gym, person_id)
        owner = self.headers(gym["tenant_id"])
        cancelled = self.client.post(
            f"/booking/bookings/{booking_id}/cancel",
            json={"reason": "overslept", **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["occasion"], "cancelled_late")
        self.assertTrue(cancelled.json()["fee_due"])
        self.assertFalse(cancelled.json()["charged"])

    def test_a_booking_is_cancelled_once(self):
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        owner = self.headers(gym["tenant_id"])
        body = {"reason": "changed my mind"}
        first = self.client.post(f"/booking/bookings/{booking_id}/cancel",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 200, first.text)
        again = self.client.post(f"/booking/bookings/{booking_id}/cancel",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)

    def test_a_cancelled_place_can_be_taken_by_somebody_else(self):
        gym = self.gym(capacity=1)
        first = self.person(gym["tenant_id"], "First")
        booking_id = self.booked(gym, first)
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "no longer free", **self.correlation()},
                         headers=owner)
        second = self.person(gym["tenant_id"], "Second")
        response = self.book(gym, second)
        self.assertEqual(response.status_code, 201, response.text)

    def test_the_cancellation_reason_is_masked_for_a_reader(self):
        """MOD-019's finding one module over: a reason column is where a medical reason goes."""
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel", json={
            "reason": "I am having treatment on Tuesdays", **self.correlation()},
            headers=owner)
        reader = self.headers(gym["tenant_id"], self.grant(
            gym["tenant_id"], ["booking.booking.read"]))
        masked = self.client.get(f"/booking/bookings/{booking_id}",
                                 headers=reader).json()
        self.assertIsNone(masked["cancellation"]["reason"])
        self.assertTrue(masked["cancellation"]["reason_masked"])
        self.assertNotIn("treatment", str(masked))
        full = self.client.get(f"/booking/bookings/{booking_id}",
                               headers=owner).json()
        self.assertIn("treatment", str(full["cancellation"]["reason"]))


class WaitlistTests(BookingApiTestCase):
    """OPS-02-R03, and paragraph 4697's second invariant."""

    def full_session(self, **rules: Any) -> tuple[dict[str, Any], str]:
        gym = self.gym(capacity=1, **rules)
        holder = self.person(gym["tenant_id"], "Holder")
        booking_id = self.booked(gym, holder)
        return gym, booking_id

    def join(self, gym: dict[str, Any], person_id: str, **extra: Any) -> Any:
        return self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist",
            json={"person_id": person_id, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **extra,
                  **self.correlation()},
            headers=self.headers(gym["tenant_id"]))

    def test_a_session_with_room_has_no_waitlist(self):
        """Joining one that has room would promote a member into a place they could have taken
        directly, which reads to everybody else as jumping the queue."""
        gym = self.gym()
        refused = self.join(gym, self.person(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("book it", refused.text)

    def test_joining_a_full_session_gives_a_position(self):
        gym, _ = self.full_session()
        first = self.join(gym, self.person(gym["tenant_id"], "Waiter one"))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["position"], 1)
        second = self.join(gym, self.person(gym["tenant_id"], "Waiter two"))
        self.assertEqual(second.json()["position"], 2)

    def test_one_member_waits_once(self):
        gym, _ = self.full_session()
        person_id = self.person(gym["tenant_id"])
        self.assertEqual(self.join(gym, person_id).status_code, 201)
        again = self.join(gym, person_id)
        self.assertEqual(again.status_code, 409, again.text)

    def test_a_promotion_reserves_and_does_not_notify(self):
        """Paragraph 5031's order, and the response says which half happened."""
        gym, booking_id = self.full_session()
        waiter = self.person(gym["tenant_id"], "Waiter")
        self.join(gym, waiter)
        owner = self.headers(gym["tenant_id"])
        # The place has to come free first.
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot make it", **self.correlation()},
                         headers=owner)
        promoted = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist/promote",
            json=self.correlation(), headers=owner)
        self.assertEqual(promoted.status_code, 200, promoted.text)
        body = promoted.json()
        self.assertIsNotNone(body["promoted"])
        self.assertEqual(body["promoted"]["person_id"], waiter)
        self.assertTrue(body["promoted"]["hold_id"])
        self.assertFalse(body["notified"])
        # The place is held for them, so nobody else can book it.
        other = self.book(gym, self.person(gym["tenant_id"], "Opportunist"))
        self.assertEqual(other.status_code, 409, other.text)

    def test_promoting_twice_cannot_hand_out_two_places(self):
        """Paragraph 4144 and 4697: "a member cannot consume the same capacity twice", kept by
        MOD-019's one-live-hold index and by the queue refusing to advance past a live offer."""
        gym, booking_id = self.full_session()
        self.join(gym, self.person(gym["tenant_id"], "Waiter one"))
        self.join(gym, self.person(gym["tenant_id"], "Waiter two"))
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot make it", **self.correlation()},
                         headers=owner)
        first = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist/promote",
            json=self.correlation(), headers=owner)
        self.assertIsNotNone(first.json()["promoted"])
        again = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist/promote",
            json=self.correlation(), headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertIsNone(again.json()["promoted"], again.text)
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 1, roster)

    def test_confirming_an_offer_becomes_a_booking_on_the_place_already_held(self):
        gym, booking_id = self.full_session()
        waiter = self.person(gym["tenant_id"], "Waiter")
        entry_id = self.join(gym, waiter).json()["entry_id"]
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot make it", **self.correlation()},
                         headers=owner)
        self.client.post(f"/booking/sessions/{gym['session_id']}/waitlist/promote",
                         json=self.correlation(), headers=owner)
        confirmed = self.client.post(
            f"/booking/waitlist/{entry_id}/confirm",
            json={"idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=owner)
        self.assertEqual(confirmed.status_code, 201, confirmed.text)
        self.assertEqual(confirmed.json()["state"], "confirmed")
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 1, roster)
        self.assertEqual([b["person_id"] for b in roster["bookings"]], [waiter])

    def test_a_declined_offer_releases_the_place_and_ends_the_entry(self):
        gym, booking_id = self.full_session()
        entry_id = self.join(
            gym, self.person(gym["tenant_id"], "Waiter")).json()["entry_id"]
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot make it", **self.correlation()},
                         headers=owner)
        self.client.post(f"/booking/sessions/{gym['session_id']}/waitlist/promote",
                         json=self.correlation(), headers=owner)
        declined = self.client.post(
            f"/booking/waitlist/{entry_id}/settle",
            json={"declined": True, "reason": "cannot make it either",
                  **self.correlation()}, headers=owner)
        self.assertEqual(declined.status_code, 200, declined.text)
        self.assertEqual(declined.json()["state"], "declined")
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 0, roster)

    def test_an_offer_that_has_not_expired_cannot_be_swept(self):
        gym, booking_id = self.full_session(offer_minutes=600)
        entry_id = self.join(
            gym, self.person(gym["tenant_id"], "Waiter")).json()["entry_id"]
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot make it", **self.correlation()},
                         headers=owner)
        self.client.post(f"/booking/sessions/{gym['session_id']}/waitlist/promote",
                         json=self.correlation(), headers=owner)
        early = self.client.post(
            f"/booking/waitlist/{entry_id}/settle",
            json={"reason": "too soon", **self.correlation()}, headers=owner)
        self.assertEqual(early.status_code, 409, early.text)
        swept = self.client.post("/booking/waitlist/expire",
                                 json=self.correlation(), headers=owner)
        self.assertEqual(swept.json()["released"], 0, swept.text)

    def test_an_expired_offer_releases_the_place_and_keeps_its_position(self):
        """A member asleep at six did not decline."""
        gym, booking_id = self.full_session(offer_minutes=1)
        waiter = self.person(gym["tenant_id"], "Waiter")
        entry_id = self.join(gym, waiter).json()["entry_id"]
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot make it", **self.correlation()},
                         headers=owner)
        self.client.post(f"/booking/sessions/{gym['session_id']}/waitlist/promote",
                         json=self.correlation(), headers=owner)
        # The offer window is a minute; move the clock past it in the database rather than
        # sleeping, because a test that waits is a test nobody runs.
        self._expire_offer(gym["tenant_id"], entry_id)
        swept = self.client.post("/booking/waitlist/expire",
                                 json=self.correlation(), headers=owner)
        self.assertEqual(swept.status_code, 200, swept.text)
        self.assertEqual(swept.json()["released"], 1, swept.text)
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 0, roster)
        waiting = [e for e in roster["waitlist"] if e["entry_id"] == entry_id]
        self.assertEqual(waiting[0]["state"], "expired")
        self.assertEqual(waiting[0]["position"], 1)

    def _expire_offer(self, tenant_id: str, entry_id: str) -> None:
        """Move one offer's expiry into the past, as the migrator.

        Done in SQL because the alternative is sleeping, and the column carries an UPDATE grant
        for the service rather than a way to backdate one.
        """
        import psycopg
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            # **Both ends move.** `bkg_waitlist_entries_offer_ordered` requires the expiry
            # to be after the offer, and correctly refused backdating only one of them --
            # which is the constraint doing its job on the test.
            cur.execute(
                "UPDATE plt01.bkg_waitlist_entries"
                "   SET offered_at = now() - interval '10 minutes',"
                "       offer_expires_at = now() - interval '1 minute'"
                " WHERE entry_id = %s", (entry_id,))


class AttendanceTests(BookingApiTestCase):
    """Check-in, no-shows and the sanctions that follow."""

    def session_now(self) -> dict[str, Any]:
        """A gym whose first session starts today, so check-in is reachable."""
        return self.gym(starts_in_days=0)

    def test_checking_in_too_early_is_refused(self):
        gym = self.gym(starts_in_days=5)
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        response = self.client.post(
            f"/booking/bookings/{booking_id}/check-in",
            json=self.correlation(), headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("has not started", response.text)

    def test_an_attendance_intent_is_recorded_and_a_change_of_mind_is_a_new_row(self):
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        owner = self.headers(gym["tenant_id"])
        for intent in ("attending", "not_attending"):
            response = self.client.post(
                f"/booking/bookings/{booking_id}/intent",
                json={"intent": intent, "idempotency_key": str(uuid.uuid4()),
                      **self.correlation()}, headers=owner)
            self.assertEqual(response.status_code, 201, response.text)
        detail = self.client.get(f"/booking/bookings/{booking_id}",
                                 headers=owner).json()
        self.assertEqual([i["intent"] for i in detail["intents"]],
                         ["not_attending", "attending"])

    def test_settling_a_session_that_is_not_over_is_refused(self):
        gym = self.gym(starts_in_days=5)
        self.booked(gym, self.person(gym["tenant_id"]))
        response = self.client.post(
            f"/booking/sessions/{gym['session_id']}/settle",
            json=self.correlation(), headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("not over", response.text)


class AppealTests(BookingApiTestCase):
    """OPS-02-R04's appeal: two acts, two parties."""

    def test_an_appeal_about_a_record_that_is_not_the_subject_s_is_refused(self):
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"], "Member"))
        owner = self.headers(gym["tenant_id"])
        cancelled = self.client.post(
            f"/booking/bookings/{booking_id}/cancel",
            json={"reason": "late", **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        detail = self.client.get(f"/booking/bookings/{booking_id}",
                                 headers=owner).json()
        other = self.person(gym["tenant_id"], "Somebody else")
        refused = self.client.post("/booking/appeals", json={
            "subject_person_id": other, "against": "fee",
            "grounds": "it was not me", "cancellation_id": detail["booking_id"],
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=owner)
        # The cancellation id is not the booking id, so this is a missing record either way --
        # what matters is that it is refused rather than accepted.
        self.assertIn(refused.status_code, (404, 409), refused.text)

    def test_an_appeal_needs_exactly_one_record(self):
        gym = self.gym()
        owner = self.headers(gym["tenant_id"])
        neither = self.client.post("/booking/appeals", json={
            "subject_person_id": self.person(gym["tenant_id"]), "against": "strike",
            "grounds": "about nothing", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(neither.status_code, 422, neither.text)

    def test_the_appeal_list_is_behind_the_deciding_permission(self):
        """The grounds are the member's own words about why a sanction is wrong."""
        gym = self.gym()
        reader = self.headers(gym["tenant_id"], self.grant(
            gym["tenant_id"], ["booking.booking.read"]))
        refused = self.client.get("/booking/appeals", headers=reader)
        self.assertEqual(refused.status_code, 403, refused.text)


class IsolationTests(BookingApiTestCase):
    """One tenant's bookings are not another's, through the routes."""

    def test_another_tenant_cannot_read_a_booking(self):
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        other = self.gym()
        response = self.client.get(f"/booking/bookings/{booking_id}",
                                   headers=self.headers(other["tenant_id"]))
        self.assertEqual(response.status_code, 404, response.text)

    def test_another_tenant_cannot_book_a_session(self):
        gym = self.gym()
        other = self.gym()
        response = self.client.post(
            f"/booking/sessions/{gym['session_id']}/bookings", json={
                "person_id": self.person(other["tenant_id"]),
                "policy_key": other["policy_key"],
                "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(other["tenant_id"]))
        self.assertEqual(response.status_code, 404, response.text)


class EventTests(BookingApiTestCase):
    """The six events, appended in the transaction that caused them."""

    def events_for(self, tenant_id: str, aggregate_type: str,
                   aggregate_id: str) -> set[str]:
        response = self.client.get(
            f"/events/aggregate?aggregate_type={aggregate_type}"
            f"&aggregate_id={aggregate_id}", headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        return {row["event_type"] for row in response.json()}

    def test_booking_and_cancelling_publish_their_events(self):
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot come", **self.correlation()},
                         headers=owner)
        kinds = self.events_for(gym["tenant_id"], "booking", booking_id)
        self.assertIn("booking.created", kinds)
        self.assertIn("booking.cancelled", kinds)

    def test_joining_and_being_promoted_publish_their_events(self):
        gym = self.gym(capacity=1)
        holder = self.person(gym["tenant_id"], "Holder")
        booking_id = self.booked(gym, holder)
        owner = self.headers(gym["tenant_id"])
        entry = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist", json={
                "person_id": self.person(gym["tenant_id"], "Waiter"),
                "policy_key": gym["policy_key"],
                "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=owner)
        self.assertEqual(entry.status_code, 201, entry.text)
        entry_id = entry.json()["entry_id"]
        self.client.post(f"/booking/bookings/{booking_id}/cancel",
                         json={"reason": "cannot come", **self.correlation()},
                         headers=owner)
        self.client.post(f"/booking/sessions/{gym['session_id']}/waitlist/promote",
                         json=self.correlation(), headers=owner)
        kinds = self.events_for(gym["tenant_id"], "waitlist_entry", entry_id)
        self.assertIn("waitlist.joined", kinds)
        self.assertIn("waitlist.promoted", kinds)

    def test_no_free_text_reaches_the_outbox(self):
        """`evt_outbox.payload` is the one store no erasure in this build can reach, and three
        modules have shipped a value carrying a subject into it."""
        gym = self.gym()
        booking_id = self.booked(gym, self.person(gym["tenant_id"]))
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/booking/bookings/{booking_id}/cancel", json={
            "reason": "jane@example.com, DOB 1990-04-02, having chemotherapy",
            **self.correlation()}, headers=owner)
        import psycopg
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)",
                        (gym["tenant_id"],))
            cur.execute(
                "SELECT payload::text FROM plt01.evt_outbox"
                " WHERE event_type LIKE 'booking.%'")
            payloads = " ".join(r[0] for r in cur.fetchall())
        for leaked in ("jane@example.com", "1990-04-02", "chemotherapy"):
            self.assertNotIn(leaked, payloads)


class ConcurrencyTests(BookingApiTestCase):
    """Paragraph 4697's first invariant, against several bookers at once."""

    def test_racing_bookers_cannot_overfill_a_session(self):
        """**MOD-019's lock is what makes this true**, and this module counts nothing -- so
        this test is the proof that the borrowing works through two modules' service layers."""
        import threading
        gym = self.gym(capacity=2)
        people = [self.person(gym["tenant_id"], f"Racer {n}") for n in range(6)]
        owner = self.headers(gym["tenant_id"])
        codes: list[int] = []
        lock = threading.Lock()

        def book(person_id: str) -> None:
            response = self.client.post(
                f"/booking/sessions/{gym['session_id']}/bookings", json={
                    "person_id": person_id, "policy_key": gym["policy_key"],
                    "idempotency_key": str(uuid.uuid4()), **self.correlation()},
                headers=owner)
            with lock:
                codes.append(response.status_code)

        threads = [threading.Thread(target=book, args=(p,)) for p in people]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(codes), [201, 201, 409, 409, 409, 409], codes)
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.assertEqual(roster["held"], 2, roster)


if __name__ == "__main__":
    unittest.main()


class ReviewRegressionApiTests(BookingApiTestCase):
    """One test per defect the request-path review found, named for the attack.

    **This class is also the answer to the evidence gap that let them ship.** No HTTP test in
    this file had ever recorded a no-show or decided an appeal against one, and four of the
    nine blocking findings lived in exactly that untested half -- which is MOD-014's "no test
    ever called a `/people` route successfully", one module on.

    **A no-show needs a session that has finished**, and no route takes an instant: a
    caller-supplied settlement time would be MOD-011's unbounded `observed_at` finding in a
    place where it decides whether somebody is recorded absent. So the sessions that must be
    over are settled through the service with an explicit `at`, and everything decided
    *afterwards* -- the appeal, its idempotency, its remedy -- goes over HTTP.
    """

    # ------------------------------------------- a class the gym cancelled

    def test_a_cancelled_session_releases_its_bookings_rather_than_blaming_anybody(self):
        """**The worst defect this module shipped.** `released` and `session_cancelled` were
        both declared, both documented as existing so that "somebody does not get a strike for
        a class the gym called off", and nothing wrote either -- so settling a cancelled
        session ran the ordinary no-show path and recorded every member of it as absent, with
        a fee, a forfeited credit and a warning or a strike. `bkg_bookings.state` is one-way
        by trigger and `bkg_no_shows` has no DELETE grant, so it was permanent.
        """
        gym = self.gym(capacity=5, warn_after_no_shows=1)
        owner = self.headers(gym["tenant_id"])
        people = [self.person(gym["tenant_id"], name=f"Member {n}") for n in range(3)]
        bookings = [self.booked(gym, person_id) for person_id in people]
        cancelled = self.client.post(
            f"/scheduling/sessions/{gym['session_id']}/cancel",
            json={"cancellation_reason": "instructor_unavailable",
                  "reason": "the instructor is ill", **self.correlation()},
            headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["places_released"], 3)
        settled = self.client.post(
            f"/booking/sessions/{gym['session_id']}/settle",
            json=self.correlation(), headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertEqual(settled.json()["settled"], 3, settled.text)
        for row in settled.json()["bookings"]:
            self.assertEqual(row["state"], "released", row)
            self.assertEqual(row["occasion"], "session_cancelled", row)
            self.assertFalse(row["fee_due"], row)
            self.assertFalse(row["credit_forfeit"], row)
            self.assertEqual(row["sanction"], "none", row)
        for booking_id, person_id in zip(bookings, people, strict=True):
            detail = self.client.get(f"/booking/bookings/{booking_id}",
                                     headers=owner).json()
            self.assertEqual(detail["state"], "released", detail)
            self.assertIsNone(detail["no_show"], detail)
            mine = self.client.get(f"/booking/members/{person_id}/bookings",
                                   headers=owner).json()
            self.assertEqual(mine["no_shows_counting"], 0, mine)

    # ------------------------------------------- what an appeal is against

    def test_an_appeal_against_a_sanction_the_record_does_not_carry_is_refused(self):
        """A strike that never happened was appealed and upheld, because `against` was stored
        beside the decision and never read."""
        gym = self.gym(warn_after_no_shows=5, strike_after_no_shows=9)
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        record = self.settled_no_show(gym, person_id)
        self.assertEqual(record["no_show"]["sanction"], "none", record)
        refused = self.client.post("/booking/appeals", json={
            "subject_person_id": person_id, "against": "strike",
            "grounds": "there was no strike to appeal",
            "no_show_id": record["no_show"]["no_show_id"],
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no strike to appeal", refused.text)

    def test_upholding_a_fee_appeal_does_not_wipe_the_sanction_count(self):
        """**The remedy was inverted in both directions.** A decider waiving a fee also
        stopped the miss counting, so the member's next one was their "first" again under the
        strike policy; a decider lifting a strike was told nothing about the fee."""
        gym = self.gym(warn_after_no_shows=1, strike_after_no_shows=1)
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        self.linked_decider(gym["tenant_id"])
        record = self.settled_no_show(gym, person_id)
        before = self.client.get(f"/booking/members/{person_id}/bookings",
                                 headers=owner).json()["no_shows_counting"]
        self.assertEqual(before, 1)
        raised = self.client.post("/booking/appeals", json={
            "subject_person_id": person_id, "against": "fee",
            "grounds": "I dispute only the fee",
            "no_show_id": record["no_show"]["no_show_id"],
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(raised.status_code, 201, raised.text)
        decided = self.client.post(
            f"/booking/appeals/{raised.json()['appeal_id']}/decide",
            json={"uphold": True, "note": "waiving the fee only",
                  **self.correlation()}, headers=owner)
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertEqual(decided.json()["state"], "upheld")
        # The money remedy is MOD-017's and this says so rather than claiming one.
        self.assertFalse(decided.json()["overturned"], decided.text)
        self.assertFalse(decided.json()["fee_reversed"], decided.text)
        self.assertIn("about money", decided.json()["note"])
        after = self.client.get(f"/booking/members/{person_id}/bookings",
                                headers=owner).json()["no_shows_counting"]
        self.assertEqual(after, 1, "a fee decision must not reset the strike policy")

    def test_upholding_a_strike_appeal_stops_it_counting(self):
        gym = self.gym(warn_after_no_shows=1, strike_after_no_shows=1)
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        self.linked_decider(gym["tenant_id"])
        record = self.settled_no_show(gym, person_id)
        self.assertEqual(record["no_show"]["sanction"], "strike", record)
        raised = self.client.post("/booking/appeals", json={
            "subject_person_id": person_id, "against": "strike",
            "grounds": "I was in hospital",
            "no_show_id": record["no_show"]["no_show_id"],
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(raised.status_code, 201, raised.text)
        decided = self.client.post(
            f"/booking/appeals/{raised.json()['appeal_id']}/decide",
            json={"uphold": True, "note": "the evidence stands", **self.correlation()},
            headers=owner)
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertTrue(decided.json()["overturned"], decided.text)
        after = self.client.get(f"/booking/members/{person_id}/bookings",
                                headers=owner).json()["no_shows_counting"]
        self.assertEqual(after, 0)

    def test_an_appeal_key_reused_for_another_sanction_is_refused(self):
        """**It landed on the one remedy a sanction has.** The key was compared against
        nothing, so a member with two strikes reusing a per-shift counter was handed the first
        appeal back with 201 -- their second strike had no appeal, nobody saw one in the queue,
        and they were told theirs had been heard and rejected."""
        gym = self.gym(warn_after_no_shows=1, strike_after_no_shows=1)
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        self.linked_decider(gym["tenant_id"])
        first = self.settled_no_show(gym, person_id)
        key = "appeal-counter-1"
        raised = self.client.post("/booking/appeals", json={
            "subject_person_id": person_id, "against": "strike",
            "grounds": "I was in hospital",
            "no_show_id": first["no_show"]["no_show_id"],
            "idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(raised.status_code, 201, raised.text)
        self.client.post(f"/booking/appeals/{raised.json()['appeal_id']}/decide",
                         json={"uphold": False, "note": "no evidence",
                               **self.correlation()}, headers=owner)
        # A second no-show on another session, appealed under the same key.
        second_gym = dict(gym, session_id=gym["sessions"][1])
        second = self.settled_no_show(second_gym, person_id)
        reused = self.client.post("/booking/appeals", json={
            "subject_person_id": person_id, "against": "strike",
            "grounds": "different class, I was at a funeral",
            "no_show_id": second["no_show"]["no_show_id"],
            "idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(reused.status_code, 409, reused.text)
        self.assertIn("different_request", reused.text)

    # ------------------------------------------- acting for somebody else

    def test_a_member_cannot_act_on_another_members_booking(self):
        """**Any member could cancel any other member's class** -- releasing their seat and
        recording a late fee and a forfeited credit against them in an insert-only table --
        book in their name against their quota, declare their attendance and appeal as them.
        `booking.booking.write` is held by every member's own app, and nothing related the
        request to the caller."""
        gym = self.gym(cancellation_hours=48)
        owner = self.headers(gym["tenant_id"])
        victim = self.person(gym["tenant_id"], name="Victim")
        booking_id = self.booked(gym, victim)
        token = self.grant(gym["tenant_id"],
                           ["booking.booking.write", "booking.booking.read"])
        member = self.headers(gym["tenant_id"], token)
        cancelled = self.client.post(
            f"/booking/bookings/{booking_id}/cancel",
            json={"reason": "not coming", **self.correlation()}, headers=member)
        self.assertEqual(cancelled.status_code, 403, cancelled.text)
        intent = self.client.post(
            f"/booking/bookings/{booking_id}/intent",
            json={"intent": "not_attending", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=member)
        self.assertEqual(intent.status_code, 403, intent.text)
        booked = self.client.post(
            f"/booking/sessions/{gym['sessions'][1]}/bookings",
            json={"person_id": victim, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=member)
        self.assertEqual(booked.status_code, 403, booked.text)
        # The booking is untouched, which is the half that matters.
        detail = self.client.get(f"/booking/bookings/{booking_id}",
                                 headers=owner).json()
        self.assertEqual(detail["state"], "booked", detail)

    def test_a_front_desk_may_act_for_a_member(self):
        """The other direction: the act is bounded by who holds the permission, not by how
        hard it was to get. A front desk books for a member who phoned in."""
        gym = self.gym()
        person_id = self.person(gym["tenant_id"])
        token = self.grant(gym["tenant_id"], [
            "booking.booking.write", "booking.booking.read",
            "booking.booking.act_for_another"])
        desk = self.headers(gym["tenant_id"], token)
        booked = self.client.post(
            f"/booking/sessions/{gym['session_id']}/bookings",
            json={"person_id": person_id, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=desk)
        self.assertEqual(booked.status_code, 201, booked.text)

    # ------------------------------------------- the cancellation reason

    def test_a_cancellation_reason_is_not_readable_with_the_permission_every_member_holds(
            self):
        """**Every member in the tenant held the key to every other member's cancellation
        prose**, in a build where `member.health.read` is unreachable by anybody and
        `/people/{id}` refuses the same caller. A reviewer read "I am having chemotherapy on
        Tuesdays" with it. The quantifier was the defect: anybody who could write *a* reason
        read *every* reason."""
        gym = self.gym(cancellation_hours=1)
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        booking_id = self.booked(gym, person_id)
        cancelled = self.client.post(
            f"/booking/bookings/{booking_id}/cancel",
            json={"reason": "I am having chemotherapy on Tuesdays",
                  **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        token = self.grant(gym["tenant_id"],
                           ["booking.booking.read", "booking.booking.write"])
        member = self.headers(gym["tenant_id"], token)
        masked = self.client.get(f"/booking/bookings/{booking_id}", headers=member)
        self.assertEqual(masked.status_code, 200, masked.text)
        self.assertIsNone(masked.json()["cancellation"]["reason"], masked.text)
        self.assertNotIn("chemotherapy", masked.text)
        # Staff see it.
        staff_token = self.grant(gym["tenant_id"], [
            "booking.booking.read", "booking.booking.act_for_another"])
        staff = self.client.get(f"/booking/bookings/{booking_id}",
                                headers=self.headers(gym["tenant_id"], staff_token))
        self.assertEqual(staff.json()["cancellation"]["reason"],
                         "I am having chemotherapy on Tuesdays")

    # ------------------------------------------- the read and the command agree

    def test_the_eligibility_read_refuses_what_the_command_refuses(self):
        """`may_book: true` for a fourteen-year-old on an 18+ class, and the command then
        refused -- the two refusals that matter most, on the surface that exists to explain
        them."""
        gym = self.gym(restrictions=[{"kind": "min_age", "value": "18"}])
        owner = self.headers(gym["tenant_id"])
        child = self.person(gym["tenant_id"], name="Young Member",
                            born=day(-14 * 365))
        read = self.client.get(
            f"/booking/sessions/{gym['session_id']}/eligibility",
            params={"person_id": child, "policy_key": gym["policy_key"]},
            headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertFalse(read.json()["may_book"], read.text)
        self.assertEqual(read.json()["reason"], "ineligible", read.text)
        refused = self.book(gym, child)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("ineligible", refused.text)

    # ------------------------------------------- the waitlist

    def test_a_declared_waitlist_capacity_is_enforced(self):
        """It was declared on MOD-019's policy and read by nothing, so a capacity-one policy
        with a waitlist of one took five joins -- and `waitlist_full`, which `denial.py` makes
        a design point against `full`, was an outcome nothing could produce."""
        gym = self.gym(capacity=1, waitlist_capacity=1)
        owner = self.headers(gym["tenant_id"])
        self.booked(gym, self.person(gym["tenant_id"], name="Holder"))
        joined, refused = 0, 0
        for n in range(4):
            response = self.client.post(
                f"/booking/sessions/{gym['session_id']}/waitlist",
                json={"person_id": self.person(gym["tenant_id"], name=f"Waiter {n}"),
                      "policy_key": gym["policy_key"],
                      "idempotency_key": str(uuid.uuid4()), **self.correlation()},
                headers=owner)
            if response.status_code == 201:
                joined += 1
            elif "waitlist_full" in response.text:
                refused += 1
        self.assertEqual(joined, 1, f"{joined} joined, {refused} refused")
        self.assertEqual(refused, 3, f"{joined} joined, {refused} refused")

    def test_a_member_can_leave_a_waitlist(self):
        """`withdrawn` was a declared state nothing wrote, so a member could not leave a queue
        at all -- and was auto-promoted into a seat they no longer wanted."""
        gym = self.gym(capacity=1)
        owner = self.headers(gym["tenant_id"])
        self.booked(gym, self.person(gym["tenant_id"], name="Holder"))
        waiter = self.person(gym["tenant_id"], name="Waiter")
        joined = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist",
            json={"person_id": waiter, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=owner)
        self.assertEqual(joined.status_code, 201, joined.text)
        left = self.client.post(
            f"/booking/waitlist/{joined.json()['entry_id']}/leave",
            json={"reason": "I found another class", **self.correlation()},
            headers=owner)
        self.assertEqual(left.status_code, 200, left.text)
        self.assertEqual(left.json()["state"], "withdrawn", left.text)

    def test_a_till_counter_reused_between_booking_and_confirming_is_not_a_collision(self):
        """`confirm_offer` wrote into `create_booking`'s key namespace, so a till reusing one
        counter had its confirmation refused as "already confirmed" -- which was the opposite
        of true: the offer was never confirmed, the member could not confirm it, and the seat
        stayed held until an expiry nothing drives."""
        gym = self.gym(capacity=1)
        owner = self.headers(gym["tenant_id"])
        holder = self.person(gym["tenant_id"], name="Holder")
        key = "till-0001"
        booked = self.client.post(
            f"/booking/sessions/{gym['session_id']}/bookings",
            json={"person_id": holder, "policy_key": gym["policy_key"],
                  "idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(booked.status_code, 201, booked.text)
        waiter = self.person(gym["tenant_id"], name="Waiter")
        joined = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist",
            json={"person_id": waiter, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=owner)
        self.assertEqual(joined.status_code, 201, joined.text)
        self.client.post(f"/booking/bookings/{booked.json()['booking_id']}/cancel",
                         json={"reason": "cannot come", **self.correlation()},
                         headers=owner)
        promoted = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist/promote",
            json=self.correlation(), headers=owner)
        self.assertEqual(promoted.status_code, 200, promoted.text)
        self.assertIsNotNone(promoted.json()["promoted"], promoted.text)
        confirmed = self.client.post(
            f"/booking/waitlist/{joined.json()['entry_id']}/confirm",
            json={"idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(confirmed.status_code, 201, confirmed.text)
        self.assertFalse(confirmed.json()["repeated"], confirmed.text)
        # And the retry is answered from what was recorded.
        again = self.client.post(
            f"/booking/waitlist/{joined.json()['entry_id']}/confirm",
            json={"idempotency_key": key, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"], again.text)
        self.assertEqual(again.json()["booking_id"], confirmed.json()["booking_id"])

    def test_an_intent_key_reused_for_another_booking_is_refused(self):
        """201 for a write that did not happen, against the wrong booking and reporting the
        wrong intent."""
        gym = self.gym()
        owner = self.headers(gym["tenant_id"])
        first = self.booked(gym, self.person(gym["tenant_id"], name="One"))
        second = self.booked(gym, self.person(gym["tenant_id"], name="Two"))
        key = "shift-counter-7"
        one = self.client.post(
            f"/booking/bookings/{first}/intent",
            json={"intent": "not_attending", "idempotency_key": key,
                  **self.correlation()}, headers=owner)
        self.assertEqual(one.status_code, 201, one.text)
        two = self.client.post(
            f"/booking/bookings/{second}/intent",
            json={"intent": "attending", "idempotency_key": key,
                  **self.correlation()}, headers=owner)
        self.assertEqual(two.status_code, 409, two.text)
        detail = self.client.get(f"/booking/bookings/{second}", headers=owner).json()
        self.assertEqual(detail["intents"], [], detail)

    # ------------------------------------------- the quota

    def test_a_quota_cannot_be_defeated_by_booking_the_last_class_first(self):
        """Seven classes under a quota of three, in request order, with nothing adversarial."""
        gym = self.gym(capacity=20, quota=3, quota_period="rolling_7_days")
        person_id = self.person(gym["tenant_id"])
        taken = 0
        # Six consecutive days, all inside the default week-long booking window, booked from
        # the furthest back -- which is the order the old window could not see.
        for session_id in reversed(gym["sessions"][:6]):
            response = self.book(gym, person_id, session_id=session_id)
            if response.status_code == 201:
                taken += 1
            else:
                self.assertEqual(response.status_code, 409, response.text)
                self.assertIn("quota_reached", response.text)
        self.assertEqual(taken, 3)

    def test_a_policy_can_be_retired_and_nothing_new_is_sold_on_it(self):
        """**The writer the grant was waiting for.** `status`, `retired_at`, `retired_by` and
        `retire_reason` carried an UPDATE grant and two `write_once` privacy declarations, and
        nothing retired a policy -- so `create_booking`'s own "this policy is retired" refusal
        was unreachable, because `_live_policy` filters on `status = 'active'` and nothing
        could leave it. MOD-012's "a column implying a control nobody implemented"."""
        gym = self.gym()
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        self.booked(gym, person_id)
        retired = self.client.post(
            f"/booking/policies/{gym['policy_key']}/retire",
            json={"reason": "superseded by the 2027 terms", **self.correlation()},
            headers=owner)
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertEqual(retired.json()["status"], "retired")
        refused = self.book(gym, self.person(gym["tenant_id"], name="Later"),
                            session_id=gym["sessions"][1])
        self.assertEqual(refused.status_code, 404, refused.text)
        # Retiring it twice is refused rather than silently repeated.
        again = self.client.post(
            f"/booking/policies/{gym['policy_key']}/retire",
            json={"reason": "again", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 404, again.text)


class SuspensionTests(BookingApiTestCase, CommercialApiTestCase):
    """The one declared denial reason that was a product hole rather than an unbuilt feature.

    **Both fixtures, because the control spans two modules.** A membership needs MOD-017's
    whole chain -- a contract, membership terms, an agreement, a signature and an activation --
    and the booking needs MOD-019's published session, so the test inherits both suites'
    helpers rather than rebuilding either.
    """

    def test_a_suspended_membership_does_not_book(self):
        """`suspended` was declared in `DENIAL_REASONS` and produced by nothing, while
        MOD-017 suspends a membership for non-payment and `mem_memberships` is on this plane
        under this role -- so the member carried on booking classes. An enumeration is a claim
        about what the software does.

        **Nothing suspends a membership over HTTP**, because MOD-017's `suspension` transition
        is a declared edge with no writer of its own (dunning drives it and nothing drives
        dunning). So the status is moved directly, which is the most this build can reach; the
        read under test is the booking side, and it is closed before MOD-017's writer arrives.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        person_id = str(live["person_id"])
        gym = self.gym_for(tenant_id)
        # Bookable while the membership is live.
        self.booked(gym, person_id)
        with self._tenant_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            moved = conn.execute(
                "UPDATE plt01.mem_memberships SET status = 'suspended'"
                " WHERE person_id = %s AND status = 'active'",
                (person_id,)).rowcount
        self.assertEqual(moved, 1, "the fixture's membership was not active")
        refused = self.book(gym, person_id, session_id=gym["sessions"][1])
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("suspended", refused.text)
        read = self.client.get(
            f"/booking/sessions/{gym['sessions'][1]}/eligibility",
            params={"person_id": person_id, "policy_key": gym["policy_key"]},
            headers=self.headers(tenant_id))
        self.assertEqual(read.json()["reason"], "suspended", read.text)



class RosterContextTests(BookingApiTestCase):
    """FD-06 draws a prior-no-show count beside each name, and the canvas says what it is for.

    > "Hala's two prior no-shows are shown without judgement -- it is context for the coach,
    > not a flag on her."

    `settled_no_show` produces one through the real settlement path -- a hand-written row
    would be testing a record this module cannot actually write. **It moved to the base class
    for this**, because subclassing the review tests to borrow a fixture helper re-runs all
    fifteen of them under a second name.

    Two properties matter and only one is obvious. The count has to be the **same** figure
    `consequence` is given when it decides a sanction, or a roster and a strike disagree
    about how many there were; and it has to come back for the whole roster in one query,
    because eighteen rows asking separately is the round-trip problem the staff list paid
    for once.
    """

    def test_the_roster_carries_each_member_s_prior_no_shows(self):
        gym = self.gym(capacity=5, warn_after_no_shows=5, strike_after_no_shows=9)
        person_id = self.person(gym["tenant_id"])
        for session_id in gym["sessions"][1:3]:
            self.settled_no_show(dict(gym, session_id=session_id), person_id)

        self.booked(gym, person_id)
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster",
            headers=self.headers(gym["tenant_id"])).json()
        row = next(b for b in roster["bookings"] if b["person_id"] == person_id)
        self.assertEqual(row["prior_no_shows"], 2, roster)

    def test_a_member_with_none_reads_nought_rather_than_being_absent(self):
        """An absent field reads as "no data" and a surface would render a blank cell, which
        is the one reading that is always wrong about a count."""
        gym = self.gym(capacity=5)
        person_id = self.person(gym["tenant_id"])
        self.booked(gym, person_id)
        roster = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster",
            headers=self.headers(gym["tenant_id"])).json()
        self.assertEqual(roster["bookings"][0]["prior_no_shows"], 0, roster)

    def test_an_overturned_no_show_stops_counting(self):
        """**The same predicate the sanction uses.** An upheld appeal sets `overturned_at`,
        which takes the record out of the count without unsaying that they missed the class
        -- so a roster that counted it would show a coach a figure the module has already
        decided against.
        """
        gym = self.gym(capacity=5, warn_after_no_shows=1, strike_after_no_shows=1)
        owner = self.headers(gym["tenant_id"])
        person_id = self.person(gym["tenant_id"])
        self.linked_decider(gym["tenant_id"])
        settled = self.settled_no_show(gym, person_id)

        raised = self.client.post("/booking/appeals", json={
            "subject_person_id": person_id, "against": "strike",
            "grounds": "She was in the building; the reader was down.",
            "no_show_id": settled["no_show"]["no_show_id"],
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(raised.status_code, 201, raised.text)
        decided = self.client.post(
            f"/booking/appeals/{raised.json()['appeal_id']}/decide",
            json={"uphold": True, "note": "Confirmed by the door log.",
                  **self.correlation()}, headers=owner)
        self.assertEqual(decided.status_code, 200, decided.text)

        later = dict(gym, session_id=gym["sessions"][3])
        self.booked(later, person_id, session_id=later["session_id"])
        roster = self.client.get(
            f"/booking/sessions/{later['session_id']}/roster",
            headers=self.headers(gym["tenant_id"])).json()
        row = next(b for b in roster["bookings"] if b["person_id"] == person_id)
        self.assertEqual(row["prior_no_shows"], 0, roster)


class CancellationRemedyApiTests(BookingApiTestCase):
    """ADM-SCH-07 over HTTP. ADR-0016.

    **The layer that matters**, which is MOD-014's finding: a service test passing a remedy
    object proves the service and not that the route reads the body, charges the right
    permissions and turns a bad id into a 422.
    """

    def _credit_policy(self, tenant_id: str, **kwargs: Any) -> str:
        body: dict[str, Any] = {
            "policy_key": f"p{uuid.uuid4().hex[:8]}", "display_name": "Class credit",
            "entitlement_type": "class_credit", **self.correlation()}
        body.update(kwargs)
        created = self.client.post(
            "/member-entitlements/policies", json=body,
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["policy_id"])

    def _cancel(self, gym: dict[str, Any], **body: Any) -> Any:
        return self.client.post(
            f"/scheduling/sessions/{gym['session_id']}/cancel-with-remedy",
            json={"cancellation_reason": "instructor_unavailable",
                  "reason": "no coach available", **body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))

    def _preview(self, gym: dict[str, Any], **body: Any) -> Any:
        return self.client.post(
            f"/scheduling/sessions/{gym['session_id']}/cancel-preview",
            json={"cancellation_reason": "instructor_unavailable",
                  "reason": "no coach available", **body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))

    # ----------------------------------------------------------------- the disclosure

    def test_the_preview_writes_nothing_and_counts_who_is_affected(self) -> None:
        gym = self.gym(capacity=12, waitlist_capacity=3)
        for n in range(3):
            self.booked(gym, self.person(gym["tenant_id"], f"Member {n}"))
        self._credit_policy(gym["tenant_id"])
        seen = self._preview(gym, remedy="credit")
        self.assertEqual(seen.status_code, 200, seen.text)
        body = seen.json()
        self.assertEqual(body["booked"], 3)
        self.assertEqual(body["to_notify"], 3)
        self.assertTrue(body["wrote_nothing"])
        self.assertEqual(body["credit"]["days"], 30)
        # And the class is still running, which is the point of a preview.
        still = self.client.get(f"/scheduling/sessions/{gym['session_id']}",
                                headers=self.headers(gym["tenant_id"]))
        self.assertEqual(still.json()["status"], "scheduled", still.text)

    def test_the_preview_discloses_the_shortfall_the_canvas_names(self) -> None:
        """"6 places free · 12 would need to choose another" -- the figure that makes the
        screen honest, at the smaller scale a test can seed."""
        gym = self.gym(capacity=4)
        people = [self.person(gym["tenant_id"], f"Member {n}") for n in range(4)]
        for person_id in people:
            self.booked(gym, person_id)
        elsewhere = gym["sessions"][1]
        # Two of the destination's four places are already taken, so two of the four
        # cancelled members fit and two do not.
        for person_id in people[:2]:
            self.booked(gym, person_id, session_id=elsewhere)
        seen = self._preview(gym, remedy="move", to_session_id=elsewhere)
        self.assertEqual(seen.status_code, 200, seen.text)
        body = seen.json()
        self.assertEqual(body["destination"]["places_free"], 2)
        # The two who booked both classes are already there; the other two take the places.
        self.assertEqual(body["moved_count"], 2)
        self.assertEqual(
            [m["reason"] for m in body["must_choose"]],
            ["already_booked", "already_booked"])

    # -------------------------------------------------------------------- the credit

    def test_a_credit_is_granted_to_every_member_in_one_act(self) -> None:
        gym = self.gym(capacity=12)
        people = [self.person(gym["tenant_id"], f"Member {n}") for n in range(3)]
        for person_id in people:
            self.booked(gym, person_id)
        self._credit_policy(gym["tenant_id"])
        done = self._cancel(gym, remedy="credit")
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual(body["status"], "cancelled")
        self.assertEqual(body["released"], 3)
        self.assertEqual(len(body["credited"]), 3)
        self.assertFalse(body["notified"])
        owner = self.headers(gym["tenant_id"])
        for person_id in people:
            held = self.client.get(
                f"/member-entitlements?person_id={person_id}", headers=owner)
            self.assertEqual(held.status_code, 200, held.text)
            kinds = [g["source_kind"] for g in held.json()["grants"]]
            self.assertIn("goodwill", kinds, held.text)

    def test_a_credit_needs_a_policy_the_tenant_declared(self) -> None:
        """A remedy granted against a policy nobody declared is a right nothing can draw, so
        the refusal names it rather than inventing a policy."""
        gym = self.gym(capacity=12)
        self.booked(gym, self.person(gym["tenant_id"]))
        refused = self._cancel(gym, remedy="credit")
        self.assertEqual(refused.status_code, 409, refused.text)
        # **The whole code**, because the surface tells this refusal from the next one by its
        # prefix: a rename here would leave the screen showing the generic conflict sentence
        # instead of "declare a class credit", which is the one next step a reader can take.
        self.assertEqual(
            refused.json()["error"],
            "this_tenant_has_declared_no_class_credit_entitlement")

    def test_two_class_credit_policies_are_refused_with_both_named(self) -> None:
        """MOD-027's trial-plan precedent: picking between two would be choosing which right
        the members get on the strength of whichever row sorted first."""
        gym = self.gym(capacity=12)
        self.booked(gym, self.person(gym["tenant_id"]))
        first = self._credit_policy(gym["tenant_id"], policy_key="credit.a")
        second = self._credit_policy(gym["tenant_id"], policy_key="credit.b")
        self.assertNotEqual(first, second)
        refused = self._cancel(gym, remedy="credit")
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertTrue(
            refused.json()["error"].startswith(
                "this_tenant_has_more_than_one_class_credit_entitlement"),
            refused.text)
        self.assertIn("credit.a", refused.json()["error"])
        self.assertIn("credit.b", refused.json()["error"])

    # ---------------------------------------------------------------------- the move

    def test_a_move_books_the_members_onto_the_replacement_class(self) -> None:
        gym = self.gym(capacity=12)
        people = [self.person(gym["tenant_id"], f"Member {n}") for n in range(2)]
        was = {person_id: self.booked(gym, person_id) for person_id in people}
        elsewhere = gym["sessions"][1]
        done = self._cancel(gym, remedy="move", to_session_id=elsewhere)
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual(len(body["moved"]), 2, body)
        self.assertEqual(body["must_choose"], [])
        owner = self.headers(gym["tenant_id"])
        for entry in body["moved"]:
            detail = self.client.get(f"/booking/bookings/{entry['booking_id']}",
                                     headers=owner)
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["session_id"], elsewhere, detail.text)
            self.assertEqual(entry["moved_from_booking_id"], was[entry["person_id"]])
            # And the place they came off is released rather than cancelled by them.
            before = self.client.get(f"/booking/bookings/{was[entry['person_id']]}",
                                     headers=owner)
            self.assertEqual(before.json()["state"], "released", before.text)

    def test_a_full_replacement_class_moves_nobody_and_says_who(self) -> None:
        gym = self.gym(capacity=2)
        people = [self.person(gym["tenant_id"], f"Member {n}") for n in range(2)]
        for person_id in people:
            self.booked(gym, person_id)
        elsewhere = gym["sessions"][1]
        others = [self.person(gym["tenant_id"], f"Other {n}") for n in range(2)]
        for person_id in others:
            self.booked(gym, person_id, session_id=elsewhere)
        done = self._cancel(gym, remedy="move", to_session_id=elsewhere)
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual(body["moved"], [])
        self.assertEqual([m["reason"] for m in body["must_choose"]],
                         ["no_place", "no_place"])
        # The cancellation still happened: a remedy that reaches nobody is not a refusal.
        self.assertEqual(body["status"], "cancelled")
        self.assertEqual(body["released"], 2)

    def test_a_class_cannot_be_moved_to_itself(self) -> None:
        gym = self.gym(capacity=4)
        self.booked(gym, self.person(gym["tenant_id"]))
        refused = self._cancel(
            gym, remedy="move", to_session_id=gym["session_id"])
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_move_names_a_class_and_a_credit_does_not(self) -> None:
        gym = self.gym(capacity=4)
        self.assertEqual(self._preview(gym, remedy="move").status_code, 422)
        self.assertEqual(
            self._preview(gym, remedy="credit",
                          to_session_id=gym["sessions"][1]).status_code, 422)

    def test_a_malformed_destination_is_refused_at_the_boundary(self) -> None:
        """MOD-009's finding: an id shape-checked nowhere answers 500 from psycopg."""
        gym = self.gym(capacity=4)
        refused = self._cancel(gym, remedy="move", to_session_id="not-a-uuid")
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_cancelled_replacement_class_is_refused(self) -> None:
        gym = self.gym(capacity=4)
        self.booked(gym, self.person(gym["tenant_id"]))
        elsewhere = gym["sessions"][1]
        gone = self.client.post(
            f"/scheduling/sessions/{elsewhere}/cancel",
            json={"cancellation_reason": "weather", "reason": "storm",
                  **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(gone.status_code, 200, gone.text)
        refused = self._cancel(gym, remedy="move", to_session_id=elsewhere)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("cancelled", refused.json()["error"])

    # ------------------------------------------------------------------ the waitlist

    def test_the_waitlist_lapses_with_the_class(self) -> None:
        """ADR-0016 D9, and `lapsed`'s first writer. Leaving three people `waiting` for a
        class that will never run is this build's declared-state-nothing-writes shape."""
        gym = self.gym(capacity=1, waitlist_capacity=3)
        self.booked(gym, self.person(gym["tenant_id"], "In the class"))
        waiting = self.person(gym["tenant_id"], "Waiting")
        joined = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist",
            json={"person_id": waiting, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(joined.status_code, 201, joined.text)
        self._credit_policy(gym["tenant_id"])
        done = self._cancel(gym, remedy="credit")
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["waitlist_lapsed"], 1, done.text)
        self.assertEqual(done.json()["to_notify"], 2, done.text)
        # **Read through the pool, because MOD-020 has no waitlist listing route.** `3 on the
        # waitlist` is what ADM-SCH-07 needs and the preview answers it; a general queue read
        # is another screen's. Named rather than worked around.
        with self._tenant_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)",
                         (gym["tenant_id"],))
            states = [str(r[0]) for r in conn.execute(
                "SELECT state FROM plt01.bkg_waitlist_entries WHERE session_id = %s",
                (gym["session_id"],)).fetchall()]
        self.assertEqual(states, ["lapsed"])

    # --------------------------------------------------------------------- the retry

    def test_the_same_request_twice_is_answered_from_what_was_recorded(self) -> None:
        """MOD-017's review found three commands answering 409 to their own success. Here the
        report is rebuilt from the rows, which is why it needs no column."""
        gym = self.gym(capacity=12)
        people = [self.person(gym["tenant_id"], f"Member {n}") for n in range(2)]
        for person_id in people:
            self.booked(gym, person_id)
        self._credit_policy(gym["tenant_id"])
        correlation = str(uuid.uuid4())
        body = {"cancellation_reason": "instructor_unavailable",
                "reason": "no coach available", "remedy": "credit",
                "correlation_id": correlation}
        url = f"/scheduling/sessions/{gym['session_id']}/cancel-with-remedy"
        owner = self.headers(gym["tenant_id"])
        first = self.client.post(url, json=body, headers=owner)
        self.assertEqual(first.status_code, 200, first.text)
        again = self.client.post(url, json=body, headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(len(again.json()["credited"]), 2, again.text)
        # And nothing was granted twice, which is what the partial unique index is for.
        for person_id in people:
            held = self.client.get(
                f"/member-entitlements?person_id={person_id}", headers=owner)
            goodwill = [g for g in held.json()["grants"]
                        if g["source_kind"] == "goodwill"]
            self.assertEqual(len(goodwill), 1, held.text)

    def test_a_different_request_on_a_cancelled_class_is_refused(self) -> None:
        gym = self.gym(capacity=12)
        self.booked(gym, self.person(gym["tenant_id"]))
        self._credit_policy(gym["tenant_id"])
        self.assertEqual(self._cancel(gym, remedy="credit").status_code, 200)
        refused = self._cancel(gym, remedy="credit")
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_a_member_the_replacement_class_refuses_is_named_not_moved(self) -> None:
        """D3. A fourteen-year-old moved onto an 18+ class is a booking MOD-019's own hold
        trigger refuses -- and refusing the whole cancellation because one member of eighteen
        is too young would leave a class running with no coach.

        **`ineligible` is read from the verdict's own key**, not from `eligible`: that one
        folds in the room being full and the booking window being shut, so reading it made
        every member of a full destination ineligible and `free_places` decoration.
        """
        tenant_id = self.tenant()
        gym = self.gym_for(tenant_id, capacity=4)
        grown_ups = self.gym_for(
            tenant_id, capacity=4,
            restrictions=[{"kind": "min_age", "value": "18"}])
        child = self.person(tenant_id, "Young Member", born=day(-365 * 14))
        adult = self.person(tenant_id, "Older Member", born=day(-365 * 40))
        self.booked(gym, child)
        self.booked(gym, adult)
        done = self._cancel(
            gym, remedy="move", to_session_id=grown_ups["session_id"])
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual([m["person_id"] for m in body["moved"]], [adult], body)
        self.assertEqual(len(body["must_choose"]), 1, body)
        self.assertEqual(body["must_choose"][0]["person_id"], child)
        self.assertEqual(body["must_choose"][0]["reason"], "ineligible")
        self.assertIsNotNone(body["must_choose"][0]["ineligible_because"])

    def test_the_earliest_bookings_take_the_places_that_are_left(self) -> None:
        """D4, through the routes: the order is the order they booked, which is what makes
        the `ORDER BY booked_at` in the candidate read observable at all."""
        gym = self.gym(capacity=4)
        people = [self.person(gym["tenant_id"], f"Member {n}") for n in range(4)]
        for person_id in people:
            self.booked(gym, person_id)
        elsewhere = gym["sessions"][1]
        filler = [self.person(gym["tenant_id"], f"Filler {n}") for n in range(2)]
        for person_id in filler:
            self.booked(gym, person_id, session_id=elsewhere)
        done = self._cancel(gym, remedy="move", to_session_id=elsewhere)
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual([m["person_id"] for m in body["moved"]], people[:2], body)
        self.assertEqual([m["person_id"] for m in body["must_choose"]], people[2:], body)

    def test_an_offered_place_lapses_with_the_class(self) -> None:
        """The one entry that *has* a place was the one entry the state machine could not
        settle: `offered -> lapsed` was not an admitted edge, so the queue had to be settled
        before the cancellation released the hold -- and both halves are what this proves."""
        gym = self.gym(capacity=1, waitlist_capacity=3)
        self.booked(gym, self.person(gym["tenant_id"], "In the class"))
        waiting = self.person(gym["tenant_id"], "Waiting")
        owner = self.headers(gym["tenant_id"])
        joined = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist",
            json={"person_id": waiting, "policy_key": gym["policy_key"],
                  "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=owner)
        self.assertEqual(joined.status_code, 201, joined.text)
        # A place frees, so the entry is offered one and holds it.
        booked_out = self.client.get(
            f"/booking/sessions/{gym['session_id']}/roster", headers=owner).json()
        self.client.post(
            f"/booking/bookings/{booked_out['bookings'][0]['booking_id']}/cancel",
            json={"reason": "cannot make it", **self.correlation()}, headers=owner)
        promoted = self.client.post(
            f"/booking/sessions/{gym['session_id']}/waitlist/promote",
            json=self.correlation(), headers=owner)
        self.assertEqual(promoted.status_code, 200, promoted.text)
        with self._tenant_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)",
                         (gym["tenant_id"],))
            state = conn.execute(
                "SELECT state FROM plt01.bkg_waitlist_entries WHERE session_id = %s",
                (gym["session_id"],)).fetchone()
        self.assertEqual(str(state[0]), "offered")
        self._credit_policy(gym["tenant_id"])
        done = self._cancel(gym, remedy="credit")
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json()["waitlist_lapsed"], 1, done.text)
        with self._tenant_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)",
                         (gym["tenant_id"],))
            row = conn.execute(
                "SELECT state, hold_id, settle_reason FROM plt01.bkg_waitlist_entries"
                " WHERE session_id = %s", (gym["session_id"],)).fetchone()
        self.assertEqual(str(row[0]), "lapsed")
        self.assertIsNone(row[1], "the place goes back with the cancellation")
        self.assertIn("cancelled", str(row[2]))

    def test_a_moved_booking_keeps_the_entitlement_the_member_already_spent(self) -> None:
        """D3. The member paid once: drawing a second grant for a class the gym moved would
        charge them for the gym's own change of plan."""
        tenant_id = self.tenant()
        gym = self.gym_for(tenant_id, capacity=4)
        person_id = self.person(tenant_id, "Pass Holder")
        policy_id = self._credit_policy(tenant_id, policy_key="passes")
        granted = self.client.post("/member-entitlements/grants", json={
            "person_id": person_id, "policy_id": policy_id, "source_kind": "goodwill",
            "quantity": 4, "valid_from": datetime.now(UTC).isoformat(),
            "reason": "a book of passes", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(granted.status_code, 201, granted.text)
        was = self.booked(gym, person_id, entitlement_key="passes")
        owner = self.headers(tenant_id)
        before = self.client.get(f"/booking/bookings/{was}", headers=owner).json()
        self.assertIsNotNone(before["entitlement_grant_id"], before)
        done = self._cancel(
            gym, remedy="move", to_session_id=gym["sessions"][1])
        self.assertEqual(done.status_code, 200, done.text)
        moved = done.json()["moved"][0]["booking_id"]
        after = self.client.get(f"/booking/bookings/{moved}", headers=owner).json()
        self.assertEqual(after["entitlement_grant_id"],
                         before["entitlement_grant_id"], after)

    def test_the_preview_refuses_a_cancelled_replacement_class(self) -> None:
        """**The reader the guard is actually for.** On the write path MOD-019's own hold
        refuses a cancelled session, so the service's check is subsumed there -- the mutation
        sweep said so by coming back uncaught. The preview takes no hold at all, so without
        the check it would report a cancelled class as having places free, which is a figure
        the screen puts in front of a manager."""
        gym = self.gym(capacity=4)
        self.booked(gym, self.person(gym["tenant_id"]))
        elsewhere = gym["sessions"][1]
        gone = self.client.post(
            f"/scheduling/sessions/{elsewhere}/cancel",
            json={"cancellation_reason": "weather", "reason": "storm",
                  **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(gone.status_code, 200, gone.text)
        refused = self._preview(gym, remedy="move", to_session_id=elsewhere)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("cancelled", refused.json()["error"])
