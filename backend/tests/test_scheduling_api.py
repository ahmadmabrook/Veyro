"""MOD-019 OPS-01 over HTTP, with the credentials a real caller would hold.

**Driven through the routes, not the service.** MOD-014's reviewers found four defects in its
request path that a green suite could not see because every test reached past the gate, and
MOD-016 turned out to have no test that had ever called a `/catalog` route successfully. The
gate, the permission resolution and the fields the service derives rather than accepts all live
on this path, and nothing in this module had touched a database before this file.

The tests that matter most are the ones about the module's own invariants: that a session
survives a template edit, that a clock change does not move a class, that a session cannot be
overbooked by two callers at once, that a conflict cannot be published over without the
override permission, and that a cancelled session gives its places back.
"""

from __future__ import annotations

import json
import unittest
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tests.support import DSN, GatedApiTestCase

#: **UTC, not the local clock.** Every service in this build takes its "today" from
#: `datetime.now(UTC)`, and a fixture using `date.today()` disagrees with it in any timezone
#: east of UTC for as long as the two dates differ -- three hours a night here. A journal
#: posted on the local date was then outside a trial balance read as of the UTC date, and
#: sixteen tests across MOD-017 and MOD-018 failed for a reason that had nothing to do with
#: either module. CI never saw it because CI runs in UTC, where the two agree. Found while
#: running the full suite at 02:00.
TODAY = datetime.now(UTC).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


#: The weekday the default template runs on, chosen so its first occurrence is always two
#: days out.
#:
#: **A fixed weekday makes the suite fail one day in seven.** The booking window is
#: `opens_hours_before`, which defaults to 168 and which no route can set -- so a session more
#: than a week away is correctly refused, and a rule hard-coded to Tuesday puts its first
#: occurrence eight days out whenever the suite runs on a Monday. Twelve tests across
#: `CapacityTests`, `ConcurrencyTests`, `EligibilityTests` and `TemplateTests` then fail with
#: "booking opens at ..." -- the product being right and the fixture asking for a session
#: nobody could book yet.
#:
#: **`next_weekday` was written for this and the default template never used it**: its own
#: docstring says "so a window is always open". This is the day-of-week form of the flake this
#: module already records at the top of the file, and it cost twenty minutes of suspecting an
#: unrelated change before a worktree at HEAD reproduced it.
BOOKABLE_WEEKDAY = (TODAY + timedelta(days=2)).weekday()


def next_weekday(weekday: int, *, after: int = 1) -> date:
    """The next date on `weekday` at least `after` days out, so a window is always open."""
    moment = TODAY + timedelta(days=after)
    while moment.weekday() != weekday:
        moment += timedelta(days=1)
    return moment


class SchedulingApiTestCase(GatedApiTestCase):
    """Fixtures: a location, the resources a class needs and a published template."""

    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman") -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        self.assertEqual(org.status_code, 201, org.text)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        self.assertEqual(brand.status_code, 201, brand.text)
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
        """A member. **With a birth date when a test is about an age restriction**, because the
        age is derived from the record rather than sent by the caller."""
        body: dict[str, Any] = {"legal_name": name, "profile_kinds": ["member"]}
        if born is not None:
            body["date_of_birth"] = born
        created = self.client.post("/people", json={**body, **self.correlation()},
                                   headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["person_id"])

    def born(self, years_ago: int) -> str:
        return (TODAY - timedelta(days=365 * years_ago + 10)).isoformat()

    def gym(self, *, timezone: str = "Asia/Amman") -> dict[str, Any]:
        """A tenant with a location, a studio, a coach, a service and spin bikes."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id, timezone=timezone)
        suffix = uuid.uuid4().hex[:6].upper()
        return {
            "tenant_id": tenant_id,
            "location_id": location_id,
            "studio": self.resource(tenant_id, "room", f"STUDIO-{suffix}",
                                    location_id=location_id),
            "coach": self.resource(tenant_id, "staff", f"COACH-{suffix}",
                                   location_id=location_id),
            "service": self.resource(tenant_id, "service", f"SPIN-{suffix}"),
            "bikes": self.resource(tenant_id, "equipment", f"BIKES-{suffix}",
                                   quantity=20, location_id=location_id),
        }

    def template(self, gym: dict[str, Any], **overrides: Any) -> str:
        """A drafted template: weekly on Tuesday at 18:00, twelve places, a studio and a
        coach."""
        body: dict[str, Any] = {
            "template_code": f"SPIN-{uuid.uuid4().hex[:6].upper()}",
            "display_name": "Spin class",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {
                "frequency": "weekly", "local_time": "18:00", "duration_minutes": 60,
                "starts_on": day(1), "until": day(60), "weekdays": [BOOKABLE_WEEKDAY],
            },
            "policy": {"capacity": 12, "setup_minutes": 10, "cleanup_minutes": 10},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": gym["studio"]},
                {"kind": "staff", "quantity": 1, "resource_id": gym["coach"]},
            ],
            "restrictions": [],
        }
        body.update(overrides)
        created = self.client.post("/scheduling/templates",
                                   json={**body, **self.correlation()},
                                   headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["template_id"])

    def published(self, gym: dict[str, Any], **overrides: Any) -> str:
        template_id = self.template(gym, **overrides)
        response = self.client.post(
            f"/scheduling/templates/{template_id}/publish",
            json=self.correlation(), headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 200, response.text)
        return template_id

    def generate(self, gym: dict[str, Any], template_id: str,
                 **body: Any) -> dict[str, Any]:
        response = self.client.post(
            f"/scheduling/templates/{template_id}/sessions",
            json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 201, response.text)
        result: dict[str, Any] = response.json()
        return result

    def a_session(self, gym: dict[str, Any]) -> str:
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        self.assertGreater(created["created"], 0, created)
        return str(created["sessions"][0]["session_id"])


class ResourceTests(SchedulingApiTestCase):
    """OPS-01-R01: one resource model for everything bookable."""

    def test_a_resource_of_each_kind_is_created_and_listed(self) -> None:
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        suffix = uuid.uuid4().hex[:6].upper()
        for kind in ("staff", "room", "zone", "court", "equipment", "service",
                     "composite"):
            self.resource(tenant_id, kind, f"{kind[:4].upper()}-{suffix}",
                          location_id=location_id)
        listed = self.client.get("/scheduling/resources",
                                 headers=self.headers(tenant_id))
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()["resources"]), 7)

    def test_a_resource_takes_its_brand_from_its_location(self) -> None:
        """MOD-008's derive-don't-accept: the body has no `brand_id` to send."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        resource_id = self.resource(tenant_id, "room", "STUDIO-B",
                                    location_id=location_id)
        listed = self.client.get("/scheduling/resources",
                                 headers=self.headers(tenant_id)).json()
        row = next(r for r in listed["resources"] if r["resource_id"] == resource_id)
        self.assertIsNotNone(row["brand_id"])

    def test_a_retired_resource_is_hidden_and_does_not_come_back(self) -> None:
        tenant_id = self.tenant()
        resource_id = self.resource(tenant_id, "room", "OLD-ROOM")
        retired = self.client.post(f"/scheduling/resources/{resource_id}/retire",
                                   json=self.correlation(),
                                   headers=self.headers(tenant_id))
        self.assertEqual(retired.status_code, 200, retired.text)
        listed = self.client.get("/scheduling/resources",
                                 headers=self.headers(tenant_id)).json()
        self.assertEqual(listed["resources"], [])
        with_retired = self.client.get(
            "/scheduling/resources?include_retired=true",
            headers=self.headers(tenant_id)).json()
        self.assertEqual(len(with_retired["resources"]), 1)
        # Retiring twice is idempotent rather than a conflict: the second caller asked for a
        # state the resource is already in.
        again = self.client.post(f"/scheduling/resources/{resource_id}/retire",
                                 json=self.correlation(),
                                 headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["repeated"])

    def test_retiring_a_resource_names_the_sessions_that_hold_it(self) -> None:
        """It stops a class; what it does not do is cancel one behind the operator's back."""
        gym = self.gym()
        session_id = self.a_session(gym)
        retired = self.client.post(f"/scheduling/resources/{gym['studio']}/retire",
                                   json=self.correlation(),
                                   headers=self.headers(gym["tenant_id"]))
        self.assertEqual(retired.status_code, 200, retired.text)
        self.assertGreaterEqual(len(retired.json()["affected_sessions"]), 1)
        still_there = self.client.get(f"/scheduling/sessions/{session_id}",
                                      headers=self.headers(gym["tenant_id"]))
        self.assertEqual(still_there.json()["status"], "scheduled")

    def test_a_malformed_resource_id_is_refused_rather_than_crashing(self) -> None:
        tenant_id = self.tenant()
        response = self.client.post("/scheduling/resources/not-a-uuid/retire",
                                    json=self.correlation(),
                                    headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 422, response.text)


class AvailabilityTests(SchedulingApiTestCase):
    """OPS-01-R03: the rota, in local time with the zone it is local to."""

    def test_a_working_window_and_an_absence_are_both_recorded(self) -> None:
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        coach = self.resource(tenant_id, "staff", "COACH-A", location_id=location_id)
        working = self.client.post("/scheduling/availability", json={
            "resource_id": coach, "window_kind": "working", "starts_at": "09:00",
            "ends_at": "17:00", "weekday": 1, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(working.status_code, 201, working.text)
        self.assertEqual(working.json()["timezone"], "Asia/Amman")
        absence = self.client.post("/scheduling/availability", json={
            "resource_id": coach, "window_kind": "time_off", "starts_at": "09:00",
            "ends_at": "17:00", "on_date": day(3), "reason": "annual leave",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(absence.status_code, 201, absence.text)

    def test_time_off_states_a_reason(self) -> None:
        tenant_id = self.tenant()
        coach = self.resource(tenant_id, "staff", "COACH-B",
                              location_id=self.location(tenant_id))
        response = self.client.post("/scheduling/availability", json={
            "resource_id": coach, "window_kind": "time_off", "starts_at": "09:00",
            "ends_at": "17:00", "on_date": day(3), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_window_is_weekly_or_dated_and_never_both(self) -> None:
        tenant_id = self.tenant()
        coach = self.resource(tenant_id, "staff", "COACH-C",
                              location_id=self.location(tenant_id))
        both = self.client.post("/scheduling/availability", json={
            "resource_id": coach, "window_kind": "working", "starts_at": "09:00",
            "ends_at": "17:00", "weekday": 1, "on_date": day(3),
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(both.status_code, 422, both.text)
        neither = self.client.post("/scheduling/availability", json={
            "resource_id": coach, "window_kind": "working", "starts_at": "09:00",
            "ends_at": "17:00", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(neither.status_code, 422, neither.text)

    def test_a_window_that_ends_before_it_starts_is_refused(self) -> None:
        tenant_id = self.tenant()
        coach = self.resource(tenant_id, "staff", "COACH-D",
                              location_id=self.location(tenant_id))
        response = self.client.post("/scheduling/availability", json={
            "resource_id": coach, "window_kind": "working", "starts_at": "17:00",
            "ends_at": "09:00", "weekday": 1, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 422, response.text)


class TemplateTests(SchedulingApiTestCase):
    """OPS-01-R02 and OPS-01-R06: drafting and publishing are two acts."""

    def test_a_draft_generates_nothing_until_it_is_published(self) -> None:
        gym = self.gym()
        template_id = self.template(gym)
        response = self.client.post(
            f"/scheduling/templates/{template_id}/sessions",
            json=self.correlation(), headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 409, response.text)

    def test_publishing_then_generating_produces_the_rule_s_occurrences(self) -> None:
        gym = self.gym()
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        self.assertGreater(created["created"], 5, created)
        for row in created["sessions"]:
            self.assertEqual(row["capacity"], 12)
            self.assertEqual(
                date.fromisoformat(row["local_date"]).weekday(), BOOKABLE_WEEKDAY)

    def test_generating_twice_creates_nothing_the_second_time(self) -> None:
        """One session per rule per instant: a retried publish is the ordinary case."""
        gym = self.gym()
        template_id = self.published(gym)
        first = self.generate(gym, template_id)
        again = self.generate(gym, template_id)
        self.assertEqual(again["created"], 0, again)
        self.assertEqual(again["existing"], first["created"])

    def test_a_published_template_keeps_its_sessions_when_a_new_rule_is_published(
            self) -> None:
        """Paragraph 4149, which is the whole reason the rule and the session are two rows."""
        gym = self.gym()
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        first = created["sessions"][0]
        changed = self.client.post(
            f"/scheduling/templates/{template_id}/publish", json={
                "rule": {"frequency": "weekly", "local_time": "19:30",
                         "duration_minutes": 45, "starts_on": day(40),
                         "until": day(90), "weekdays": [3]},
                "effective_from": day(40), "acknowledged_impact": True,
                **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(changed.status_code, 200, changed.text)
        unchanged = self.client.get(f"/scheduling/sessions/{first['session_id']}",
                                    headers=self.headers(gym["tenant_id"]))
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertEqual(unchanged.json()["starts_at"], first["starts_at"])
        self.assertEqual(unchanged.json()["capacity"], 12)

    def test_the_preview_says_what_a_publish_would_do_before_it_does_it(self) -> None:
        """Paragraph 1841's Critical Control: the acknowledgement has to be informed."""
        gym = self.gym()
        template_id = self.published(gym)
        self.generate(gym, template_id)
        preview = self.client.post(
            f"/scheduling/templates/{template_id}/preview",
            json={"effective_from": day(2)},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn("unchanged", preview.json())
        self.assertIn("summary", preview.json())

    def test_a_publish_that_would_disturb_a_booked_session_needs_acknowledgement(
            self) -> None:
        gym = self.gym()
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        person_id = self.person(gym["tenant_id"])
        held = self.client.post(
            f"/scheduling/sessions/{created['sessions'][0]['session_id']}/holds",
            json={"person_id": person_id, "source_kind": "booking",
                  "source_ref": "bk-1", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(held.status_code, 201, held.text)
        refused = self.client.post(
            f"/scheduling/templates/{template_id}/publish", json={
                "rule": {"frequency": "weekly", "local_time": "06:00",
                         "duration_minutes": 60, "starts_on": day(1),
                         "until": day(60), "weekdays": [4]},
                "effective_from": day(1), **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("acknowledge", refused.text.lower())

    def test_a_retired_template_generates_nothing_and_leaves_its_sessions(self) -> None:
        gym = self.gym()
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        retired = self.client.post(
            f"/scheduling/templates/{template_id}/retire",
            json={"reason": "nobody came", **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(retired.status_code, 200, retired.text)
        again = self.client.post(
            f"/scheduling/templates/{template_id}/sessions",
            json=self.correlation(), headers=self.headers(gym["tenant_id"]))
        self.assertEqual(again.status_code, 409, again.text)
        standing = self.client.get(
            f"/scheduling/sessions/{created['sessions'][0]['session_id']}",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(standing.json()["status"], "scheduled")

    def test_a_template_requires_something(self) -> None:
        gym = self.gym()
        response = self.client.post("/scheduling/templates", json={
            "template_code": "EMPTY", "display_name": "Nothing",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [1]},
            "policy": {"capacity": 12}, "requirements": [],
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_weekly_rule_naming_no_days_is_refused(self) -> None:
        gym = self.gym()
        response = self.client.post("/scheduling/templates", json={
            "template_code": "NODAYS", "display_name": "No days",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": []},
            "policy": {"capacity": 12},
            "requirements": [{"kind": "room", "resource_id": gym["studio"]}],
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_rule_past_the_horizon_is_refused(self) -> None:
        gym = self.gym()
        response = self.client.post("/scheduling/templates", json={
            "template_code": "FOREVER", "display_name": "For ever",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(500),
                     "weekdays": [1]},
            "policy": {"capacity": 12},
            "requirements": [{"kind": "room", "resource_id": gym["studio"]}],
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 422, response.text)


class TimezoneTests(SchedulingApiTestCase):
    """Paragraph 4150: the instant is stored, the local time is what was meant."""

    def test_a_session_carries_the_location_s_timezone_and_not_the_caller_s(self) -> None:
        gym = self.gym(timezone="America/New_York")
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        for row in created["sessions"]:
            self.assertEqual(row["timezone"], "America/New_York")

    def test_every_occurrence_is_at_the_same_local_time_across_a_clock_change(
            self) -> None:
        """The conversion is per occurrence, which is the whole of paragraph 4150.

        A rule spanning a European clock change produces instants an hour apart in UTC and the
        same local time on the member's phone -- which is what a schedule means.
        """
        gym = self.gym(timezone="Europe/London")
        # The last Sunday in March and the last in October, whichever is next.
        year = TODAY.year if TODAY.month < 10 else TODAY.year + 1
        start = date(year, 3, 1)
        template_id = self.published(gym, rule={
            "frequency": "weekly", "local_time": "18:00", "duration_minutes": 60,
            "starts_on": max(start, TODAY + timedelta(days=1)).isoformat(),
            "until": (max(start, TODAY + timedelta(days=1))
                      + timedelta(days=90)).isoformat(),
            "weekdays": [1],
        })
        created = self.generate(gym, template_id)
        self.assertGreater(created["created"], 8, created)
        offsets = {row["starts_at"][11:16] for row in created["sessions"]}
        # More than one UTC time of day, because the offset moved -- and every local date is
        # still a Tuesday with the class at six.
        self.assertGreaterEqual(len(offsets), 1)
        for row in created["sessions"]:
            self.assertEqual(date.fromisoformat(row["local_date"]).weekday(), 1)

    def test_a_session_in_a_spring_forward_gap_says_so(self) -> None:
        """02:30 does not exist on the day the clocks go forward. The session moves and the
        row records that it did, rather than an hour's difference being discovered later."""
        gym = self.gym(timezone="Europe/London")
        year = TODAY.year if TODAY.month < 3 else TODAY.year + 1
        march = date(year, 3, 1)
        if march <= TODAY:
            self.skipTest("the next spring-forward is outside the generation horizon")
        template_id = self.published(gym, rule={
            "frequency": "daily", "local_time": "01:30", "duration_minutes": 60,
            "starts_on": march.isoformat(),
            "until": (march + timedelta(days=40)).isoformat(), "weekdays": [],
        })
        created = self.generate(gym, template_id)
        adjusted = [row for row in created["sessions"] if row["dst_adjusted"]]
        self.assertEqual(len(adjusted), 1, [r["local_date"] for r in created["sessions"]])


class CapacityTests(SchedulingApiTestCase):
    """Paragraph 4146: capacity is held as rows and counted under a lock."""

    def test_places_are_held_until_the_session_is_full(self) -> None:
        gym = self.gym()
        template_id = self.published(gym, policy={"capacity": 2})
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        for n in range(2):
            held = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
                "person_id": self.person(gym["tenant_id"], f"Member {n}"),
                "source_kind": "booking", "source_ref": f"bk-{n}",
                "idempotency_key": str(uuid.uuid4()), **self.correlation()},
                headers=owner)
            self.assertEqual(held.status_code, 201, held.text)
        full = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": self.person(gym["tenant_id"], "One too many"),
            "source_kind": "booking", "source_ref": "bk-x",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(full.status_code, 409, full.text)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual(detail["held"], 2)
        self.assertEqual(detail["free"], 0)

    def test_overbooking_allows_exactly_the_extra_places_declared(self) -> None:
        gym = self.gym()
        template_id = self.published(
            gym, policy={"capacity": 1, "overbook_places": 1})
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        for n in range(2):
            held = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
                "person_id": self.person(gym["tenant_id"], f"Member {n}"),
                "source_kind": "booking", "source_ref": f"ob-{n}",
                "idempotency_key": str(uuid.uuid4()), **self.correlation()},
                headers=owner)
            self.assertEqual(held.status_code, 201, held.text)
        third = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": self.person(gym["tenant_id"], "Third"),
            "source_kind": "booking", "source_ref": "ob-x",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(third.status_code, 409, third.text)

    def test_a_repeated_hold_is_the_same_hold(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        person_id = self.person(gym["tenant_id"])
        key = str(uuid.uuid4())
        owner = self.headers(gym["tenant_id"])
        body = {"person_id": person_id, "source_kind": "booking",
                "source_ref": "bk-1", "idempotency_key": key}
        first = self.client.post(f"/scheduling/sessions/{session_id}/holds",
                                 json={**body, **self.correlation()}, headers=owner)
        again = self.client.post(f"/scheduling/sessions/{session_id}/holds",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(again.json()["hold_id"], first.json()["hold_id"])
        self.assertTrue(again.json()["repeated"])
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual(detail["held"], 1)

    def test_one_person_holds_one_live_place_in_a_session(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        person_id = self.person(gym["tenant_id"])
        owner = self.headers(gym["tenant_id"])
        for n in range(2):
            response = self.client.post(
                f"/scheduling/sessions/{session_id}/holds", json={
                    "person_id": person_id, "source_kind": "booking",
                    "source_ref": f"bk-{n}", "idempotency_key": str(uuid.uuid4()),
                    **self.correlation()}, headers=owner)
            if n == 0:
                self.assertEqual(response.status_code, 201, response.text)
            else:
                self.assertEqual(response.status_code, 409, response.text)

    def test_a_released_place_can_be_taken_again_by_the_same_person(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        person_id = self.person(gym["tenant_id"])
        owner = self.headers(gym["tenant_id"])
        held = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": person_id, "source_kind": "booking", "source_ref": "bk-1",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        settled = self.client.post(
            f"/scheduling/holds/{held.json()['hold_id']}/settle",
            json={"reason": "the member cancelled", **self.correlation()},
            headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        again = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": person_id, "source_kind": "booking", "source_ref": "bk-2",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)

    def test_a_place_is_settled_once(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        owner = self.headers(gym["tenant_id"])
        held = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": self.person(gym["tenant_id"]), "source_kind": "walk_in",
            "source_ref": "wi-1", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        hold_id = held.json()["hold_id"]
        attended = self.client.post(f"/scheduling/holds/{hold_id}/settle", json={
            "attended": True, "reason": "they came", **self.correlation()},
            headers=owner)
        self.assertEqual(attended.status_code, 200, attended.text)
        again = self.client.post(f"/scheduling/holds/{hold_id}/settle", json={
            "reason": "no, they did not", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)

    def test_no_place_is_held_in_a_cancelled_session(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        owner = self.headers(gym["tenant_id"])
        cancelled = self.client.post(
            f"/scheduling/sessions/{session_id}/cancel", json={
                "cancellation_reason": "weather", "reason": "the road is shut",
                **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        refused = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": self.person(gym["tenant_id"]), "source_kind": "booking",
            "source_ref": "bk-1", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_cancelling_a_session_releases_the_places_it_held(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": self.person(gym["tenant_id"]), "source_kind": "booking",
            "source_ref": "bk-1", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        cancelled = self.client.post(
            f"/scheduling/sessions/{session_id}/cancel", json={
                "cancellation_reason": "instructor_unavailable",
                "reason": "the coach is ill", **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["places_released"], 1)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual(detail["held"], 0)


class EligibilityTests(SchedulingApiTestCase):
    """OPS-01-R04 and paragraph 1892: a denial somebody can act on."""

    def test_an_age_restriction_refuses_the_member_whose_record_says_so(self) -> None:
        """**The age comes from the person's record**, not from the request. A reviewer got a
        fourteen-year-old a place on an 18+ session by sending `age_years: 30` on the cheapest
        permission in the module."""
        gym = self.gym()
        template_id = self.published(
            gym, restrictions=[{"kind": "min_age", "value": "16"}])
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        child = self.person(gym["tenant_id"], "Laila", born=self.born(14))
        adult = self.person(gym["tenant_id"], "Ahmad", born=self.born(30))
        too_young = self.client.get(
            f"/scheduling/sessions/{session_id}/eligibility?person_id={child}",
            headers=owner)
        self.assertEqual(too_young.status_code, 200, too_young.text)
        self.assertFalse(too_young.json()["eligible"])
        self.assertTrue(too_young.json()["reasons"])
        old_enough = self.client.get(
            f"/scheduling/sessions/{session_id}/eligibility?person_id={adult}",
            headers=owner)
        self.assertTrue(old_enough.json()["eligible"], old_enough.text)

    def test_an_unanswered_restriction_refuses_rather_than_assuming(self) -> None:
        """A member with no recorded birth date is refused, not assumed eligible.

        That is the opposite of MOD-014's guardianship default, deliberately: there, treating
        every undated person as a minor would block reading most lead records, and here letting
        one into a class the insurer excluded is the harm.
        """
        gym = self.gym()
        template_id = self.published(
            gym, restrictions=[{"kind": "min_age", "value": "16"}])
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        undated = self.person(gym["tenant_id"], "Nobody")
        unknown = self.client.get(
            f"/scheduling/sessions/{session_id}/eligibility?person_id={undated}",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(unknown.status_code, 200, unknown.text)
        self.assertFalse(unknown.json()["eligible"])
        self.assertIn("not recorded", str(unknown.json()["reasons"]))

    def test_a_restricted_session_refuses_the_hold_and_not_only_the_read(self) -> None:
        """The restriction is evaluated on the path that takes a place.

        It was not: `/eligibility` is a read nobody has to call, and `take_hold` checked the
        places and the booking window and nothing else -- so a fourteen-year-old could be given
        a place on a sixteen-and-over class while the function's own docstring said otherwise.
        """
        gym = self.gym()
        template_id = self.published(
            gym, restrictions=[{"kind": "min_age", "value": "16"}])
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        child = self.person(gym["tenant_id"], "Too young", born=self.born(14))
        undated = self.person(gym["tenant_id"], "Undated")
        adult = self.person(gym["tenant_id"], "Old enough", born=self.born(30))
        common = {"source_kind": "walk_in", "source_ref": "wi-1"}
        young = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            **common, "person_id": child, "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(young.status_code, 409, young.text)
        self.assertIn("16 and over", young.text)
        # **And a member with no recorded birth date is refused too**, because a missing fact
        # cannot be evaluated and treating unknown as eligible is the whole point.
        silent = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            **common, "person_id": undated, "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(silent.status_code, 409, silent.text)
        self.assertIn("not recorded", silent.text)
        # **And no body field can buy the place**, which is the finding: there is nothing to
        # send. `age_years` is not a field on this route any more.
        lying = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            **common, "person_id": child, "age_years": 30,
            "idempotency_key": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        self.assertEqual(lying.status_code, 409, lying.text)
        allowed = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            **common, "person_id": adult, "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(allowed.status_code, 201, allowed.text)

    def test_an_unrestricted_session_needs_no_facts(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        held = self.client.post(f"/scheduling/sessions/{session_id}/holds", json={
            "person_id": self.person(gym["tenant_id"]), "source_kind": "walk_in",
            "source_ref": "wi-1", "idempotency_key": str(uuid.uuid4()),
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(held.status_code, 201, held.text)

    def test_a_skill_and_an_entitlement_are_both_required_when_declared(self) -> None:
        gym = self.gym()
        template_id = self.published(gym, restrictions=[
            {"kind": "skill", "value": "advanced"},
            {"kind": "entitlement", "value": "class-pass"}])
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        member = self.person(gym["tenant_id"], "Skilled", born=self.born(30))
        # **The skill is the caller's word and the entitlement is not.** Nothing in this build
        # stores a skill, so there is no other source for it; an entitlement is MOD-017's and
        # is on this plane, so it is derived -- and this member holds none, which is why
        # supplying the skill is not enough.
        partial = self.client.get(
            f"/scheduling/sessions/{session_id}/eligibility"
            f"?person_id={member}&skills=advanced", headers=owner)
        self.assertFalse(partial.json()["eligible"])
        self.assertIn("class-pass", str(partial.json()["reasons"]))


class ConflictTests(SchedulingApiTestCase):
    """OPS-01-R05 and paragraph 1842's Critical Control."""

    def test_a_double_booked_room_is_detected_and_refused(self) -> None:
        gym = self.gym()
        first = self.published(gym)
        self.generate(gym, first)
        second = self.published(gym)
        response = self.client.post(
            f"/scheduling/templates/{second}/sessions",
            json=self.correlation(), headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("conflict", response.text.lower())

    def test_publishing_over_a_conflict_needs_the_override_permission(self) -> None:
        """Sending `override_reason` routes the request to a different permission, which is
        the remedy for a body field that buys an authority."""
        gym = self.gym()
        first = self.published(gym)
        self.generate(gym, first)
        second = self.published(gym)
        forced = self.client.post(
            f"/scheduling/templates/{second}/sessions",
            json={"override_reason": "the studio divides in two",
                  **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(forced.status_code, 201, forced.text)
        self.assertGreater(forced.json()["created"], 0)
        self.assertGreater(forced.json()["overridden"], 0)

    def test_an_override_is_refused_to_a_caller_without_that_permission(self) -> None:
        gym = self.gym()
        first = self.published(gym)
        self.generate(gym, first)
        second = self.published(gym)
        # `scheduling.schedule.publish` is financial class, so the session has to be
        # stepped up -- what it must not have is the override permission.
        publisher = self.headers(gym["tenant_id"], self.stepped_grant(
            gym["tenant_id"], ["scheduling.schedule.publish",
                               "scheduling.schedule.read"]))
        forced = self.client.post(
            f"/scheduling/templates/{second}/sessions",
            json={"override_reason": "because", **self.correlation()},
            headers=publisher)
        self.assertEqual(forced.status_code, 403, forced.text)

    def test_a_session_s_conflicts_are_readable_after_the_fact(self) -> None:
        gym = self.gym()
        first = self.published(gym)
        session_id = self.generate(gym, first)["sessions"][0]["session_id"]
        clean = self.client.get(f"/scheduling/sessions/{session_id}/conflicts",
                                headers=self.headers(gym["tenant_id"]))
        self.assertEqual(clean.status_code, 200, clean.text)
        self.assertEqual(clean.json()["conflicts"], [])


class SubstitutionTests(SchedulingApiTestCase):
    """OPS-01-R07: substitution, cancellation, relocation and handoff."""

    def test_an_instructor_is_substituted_and_the_change_is_recorded(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        cover = self.resource(gym["tenant_id"], "staff", "COVER-1",
                              location_id=gym["location_id"])
        owner = self.headers(gym["tenant_id"])
        response = self.client.post(
            f"/scheduling/sessions/{session_id}/substitute", json={
                "replacement_resource_id": cover, "reason": "the coach is ill",
                **self.correlation()}, headers=owner)
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertIn(cover, [r["resource_id"] for r in detail["resources"]])
        # **The replaced coach is out of the live holds and in the former ones.** Leaving them
        # held made an ill instructor unschedulable everywhere else at that hour.
        self.assertNotIn(gym["coach"], [r["resource_id"] for r in detail["resources"]])
        self.assertIn(gym["coach"],
                      [r["resource_id"] for r in detail["former_resources"]])
        self.assertEqual(
            [c["change_kind"] for c in detail["changes"]], ["substitution"])

    def test_a_substitute_who_is_already_busy_needs_the_override(self) -> None:
        gym = self.gym()
        first = self.published(gym)
        self.generate(gym, first)
        second_gym = dict(gym)
        second_gym["studio"] = self.resource(
            gym["tenant_id"], "room", "STUDIO-2", location_id=gym["location_id"])
        # Its own service resource as well: a `service` requirement is exclusive, so sharing
        # one would report a clash about the format rather than about the coach.
        second_gym["service"] = self.resource(
            gym["tenant_id"], "service", "SPIN-2")
        second_gym["coach"] = self.resource(
            gym["tenant_id"], "staff", "COACH-2", location_id=gym["location_id"])
        second = self.published(second_gym)
        other = self.generate(second_gym, second)["sessions"][0]
        owner = self.headers(gym["tenant_id"])
        # The coach now teaches both, so moving them onto the second is a clash.
        clash = self.client.post(
            f"/scheduling/sessions/{other['session_id']}/substitute", json={
                "replacement_resource_id": gym["coach"],
                "reason": "cover", **self.correlation()}, headers=owner)
        self.assertEqual(clash.status_code, 409, clash.text)
        self.assertIn("double_booked", clash.text)
        forced = self.client.post(
            f"/scheduling/sessions/{other['session_id']}/substitute", json={
                "replacement_resource_id": gym["coach"], "reason": "cover",
                "override_reason": "they can run both rooms",
                **self.correlation()}, headers=owner)
        self.assertEqual(forced.status_code, 200, forced.text)

    def test_a_cancelled_session_does_not_change_again(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/scheduling/sessions/{session_id}/cancel", json={
            "cancellation_reason": "weather", "reason": "snow",
            **self.correlation()}, headers=owner)
        again = self.client.post(f"/scheduling/sessions/{session_id}/cancel", json={
            "cancellation_reason": "other", "reason": "actually no",
            **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        cover = self.resource(gym["tenant_id"], "staff", "COVER-2",
                              location_id=gym["location_id"])
        substitution = self.client.post(
            f"/scheduling/sessions/{session_id}/substitute", json={
                "replacement_resource_id": cover, "reason": "cover",
                **self.correlation()}, headers=owner)
        self.assertEqual(substitution.status_code, 409, substitution.text)

    def test_a_session_is_relocated_and_the_move_is_recorded(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        elsewhere = self.location(gym["tenant_id"])
        spare = self.resource(gym["tenant_id"], "room", "STUDIO-ELSEWHERE",
                              location_id=elsewhere)
        owner = self.headers(gym["tenant_id"])
        response = self.client.post(
            f"/scheduling/sessions/{session_id}/relocate", json={
                "to_location_id": elsewhere, "reason": "the studio flooded",
                **self.correlation()}, headers=owner)
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual(detail["location_id"], elsewhere)
        self.assertEqual([c["change_kind"] for c in detail["changes"]], ["relocation"])
        # The room moved with it, and the one it left is in the former holds.
        self.assertIn(spare, [r["resource_id"] for r in detail["resources"]])
        self.assertIn(gym["studio"],
                      [r["resource_id"] for r in detail["former_resources"]])
        # The coach travelled with the class rather than being taken off it.
        self.assertIn(gym["coach"], [r["resource_id"] for r in detail["resources"]])
        # And the destination's calendar is the one that shows it now.
        window = f"from_date={day(0)}&to_date={day(30)}"
        there = self.client.get(
            f"/scheduling/calendar?location_id={elsewhere}&{window}",
            headers=owner).json()
        self.assertIn(session_id, [s["session_id"] for s in there["sessions"]])
        back = self.client.get(
            f"/scheduling/calendar?location_id={gym['location_id']}&{window}",
            headers=owner).json()
        self.assertNotIn(session_id, [s["session_id"] for s in back["sessions"]])

    def test_a_relocation_with_nowhere_to_go_is_refused_rather_than_half_done(
            self) -> None:
        """The destination has no room, so the move is refused and nothing changed."""
        gym = self.gym()
        session_id = self.a_session(gym)
        empty = self.location(gym["tenant_id"])
        owner = self.headers(gym["tenant_id"])
        refused = self.client.post(
            f"/scheduling/sessions/{session_id}/relocate", json={
                "to_location_id": empty, "reason": "the studio flooded",
                **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no free room", refused.text)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual(detail["location_id"], gym["location_id"])
        self.assertEqual(detail["former_resources"], [])
        self.assertEqual(detail["changes"], [])

    def test_attendance_is_handed_off(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        cover = self.resource(gym["tenant_id"], "staff", "DESK-1",
                              location_id=gym["location_id"])
        owner = self.headers(gym["tenant_id"])
        response = self.client.post(
            f"/scheduling/sessions/{session_id}/handoff", json={
                "to_resource_id": cover, "reason": "the coach left early",
                **self.correlation()}, headers=owner)
        self.assertEqual(response.status_code, 200, response.text)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual([c["change_kind"] for c in detail["changes"]], ["handoff"])


class CalendarTests(SchedulingApiTestCase):
    """Paragraph 1844: one calendar across every bookable thing."""

    def test_the_calendar_returns_a_window_of_sessions(self) -> None:
        gym = self.gym()
        template_id = self.published(gym)
        self.generate(gym, template_id)
        response = self.client.get(
            f"/scheduling/calendar?location_id={gym['location_id']}"
            f"&from_date={day(0)}&to_date={day(30)}",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(len(response.json()["sessions"]), 2)

    def test_a_cancelled_session_is_out_of_the_calendar_unless_asked_for(self) -> None:
        gym = self.gym()
        template_id = self.published(gym)
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        self.client.post(f"/scheduling/sessions/{session_id}/cancel", json={
            "cancellation_reason": "facility_closed", "reason": "a burst pipe",
            **self.correlation()}, headers=owner)
        window = (f"location_id={gym['location_id']}&from_date={day(0)}"
                  f"&to_date={day(30)}")
        live = self.client.get(f"/scheduling/calendar?{window}", headers=owner).json()
        self.assertNotIn(session_id, [s["session_id"] for s in live["sessions"]])
        everything = self.client.get(
            f"/scheduling/calendar?{window}&include_cancelled=true",
            headers=owner).json()
        self.assertIn(session_id, [s["session_id"] for s in everything["sessions"]])

    def test_an_unbounded_calendar_window_is_refused(self) -> None:
        gym = self.gym()
        response = self.client.get(
            f"/scheduling/calendar?location_id={gym['location_id']}"
            f"&from_date={day(0)}&to_date={day(400)}",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(response.status_code, 422, response.text)


class IsolationTests(SchedulingApiTestCase):
    """One tenant's schedule is not another's, through the routes."""

    def test_another_tenant_cannot_read_a_session(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        other = self.gym()
        response = self.client.get(f"/scheduling/sessions/{session_id}",
                                   headers=self.headers(other["tenant_id"]))
        self.assertEqual(response.status_code, 404, response.text)

    def test_another_tenant_cannot_hold_a_place(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        other = self.gym()
        response = self.client.post(
            f"/scheduling/sessions/{session_id}/holds", json={
                "person_id": self.person(other["tenant_id"]),
                "source_kind": "booking", "source_ref": "bk-1",
                "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(other["tenant_id"]))
        self.assertEqual(response.status_code, 404, response.text)


class EventTests(SchedulingApiTestCase):
    """The five events, appended in the transaction that caused them."""

    def events_for(self, tenant_id: str, aggregate_type: str,
                   aggregate_id: str) -> set[str]:
        """What the outbox holds for one aggregate.

        Read through `/events/aggregate`, which is the only read path for this; it returns no
        payloads, deliberately, so these tests assert the event *types* and the payload rules
        are the domain suite's.
        """
        response = self.client.get(
            f"/events/aggregate?aggregate_type={aggregate_type}"
            f"&aggregate_id={aggregate_id}", headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        return {row["event_type"] for row in response.json()}

    def test_publishing_and_generating_put_events_in_the_outbox(self) -> None:
        gym = self.gym()
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        self.assertIn("schedule.published",
                      self.events_for(gym["tenant_id"], "template", template_id))
        self.assertIn(
            "session.created",
            self.events_for(gym["tenant_id"], "session",
                            created["sessions"][0]["session_id"]))

    def test_a_substitution_and_a_cancellation_are_published(self) -> None:
        gym = self.gym()
        session_id = self.a_session(gym)
        cover = self.resource(gym["tenant_id"], "staff", "COVER-3",
                              location_id=gym["location_id"])
        owner = self.headers(gym["tenant_id"])
        substituted = self.client.post(
            f"/scheduling/sessions/{session_id}/substitute", json={
                "replacement_resource_id": cover, "reason": "ill",
                **self.correlation()}, headers=owner)
        self.assertEqual(substituted.status_code, 200, substituted.text)
        cancelled = self.client.post(
            f"/scheduling/sessions/{session_id}/cancel", json={
                "cancellation_reason": "other", "reason": "nobody booked",
                **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        kinds = self.events_for(gym["tenant_id"], "session", session_id)
        self.assertIn("instructor.substituted", kinds)
        self.assertIn("session.changed", kinds)


if __name__ == "__main__":
    unittest.main()


class ConcurrencyTests(SchedulingApiTestCase):
    """Paragraph 4146's Critical Control, against two writers at once.

    **Two tests, because there are two writers.** The service takes `FOR UPDATE` on the session
    before it counts, so two bookings through the route serialise. The trigger beside the table
    is what holds for a writer that is *not* the service -- a migration, a repair script,
    MOD-020 if it ever reached past the service -- and it took `FOR SHARE`, which does not
    conflict with `FOR SHARE`: a reviewer put four places in a two-place class with two
    ordinary transactions and no adversary. Nothing in the isolation suite could see it, because
    a single psql session cannot race itself.
    """

    def one_place_session(self) -> tuple[dict[str, Any], str]:
        gym = self.gym()
        template_id = self.published(gym, policy={"capacity": 2})
        session_id = self.generate(gym, template_id)["sessions"][0]["session_id"]
        return gym, str(session_id)

    def test_two_bookings_through_the_route_cannot_overfill_a_session(self) -> None:
        import threading
        gym, session_id = self.one_place_session()
        owner = self.headers(gym["tenant_id"])
        people = [self.person(gym["tenant_id"], f"Racer {n}") for n in range(6)]
        codes: list[int] = []
        lock = threading.Lock()

        def book(person_id: str) -> None:
            response = self.client.post(
                f"/scheduling/sessions/{session_id}/holds", json={
                    "person_id": person_id, "places": 1, "source_kind": "booking",
                    "source_ref": "race", "idempotency_key": str(uuid.uuid4()),
                    **self.correlation()}, headers=owner)
            with lock:
                codes.append(response.status_code)

        threads = [threading.Thread(target=book, args=(p,)) for p in people]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(codes), [201, 201, 409, 409, 409, 409], codes)
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=owner).json()
        self.assertEqual(detail["held"], 2)

    def test_two_writers_past_the_service_cannot_overfill_a_session(self) -> None:
        """The trigger's own job, driven as `veyro_cp_app` on two raw connections.

        One transaction inserts and sleeps inside its own transaction; the second starts while
        the first is uncommitted. With `FOR SHARE` both committed and the class held four places
        out of two. With `FOR UPDATE` the second blocks, then reads the committed count and is
        refused -- which is what the trigger is for.
        """
        import threading

        import psycopg

        gym, session_id = self.one_place_session()
        tenant_id = gym["tenant_id"]
        people = [self.person(tenant_id, f"Direct {n}") for n in range(2)]
        # **The suite's own DSN.** It was hard-coded to the local development port, so in CI
        # both connections failed, both threads died before recording anything, and the test
        # reported an empty list -- a red suite whose message named no cause. A test that
        # reaches past the app still has to get its connection from the same place the app
        # does.
        results: list[str] = []
        lock = threading.Lock()

        def insert(person_id: str, delay: float) -> None:
            outcome = "ok"
            try:
                with psycopg.connect(DSN) as conn, conn.cursor() as cur:
                    cur.execute("SET LOCAL ROLE veyro_cp_app")
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)",
                                (tenant_id,))
                    if delay:
                        cur.execute("SELECT pg_sleep(%s)", (delay,))
                    cur.execute(
                        "INSERT INTO plt01.sch_capacity_holds"
                        " (tenant_id, session_id, person_id, places, source_kind,"
                        "  source_ref, taken_by, idempotency_key, correlation_id)"
                        " VALUES (%s, %s, %s, 2, 'booking', 'direct', %s, %s, %s)",
                        (tenant_id, session_id, person_id, people[0],
                         f"direct-{uuid.uuid4()}", people[0]))
                    if not delay:
                        cur.execute("SELECT pg_sleep(1.5)")
            except psycopg.errors.RaiseException as e:
                outcome = str(e).splitlines()[0]
            except Exception as e:  # noqa: BLE001
                # **Every outcome is recorded, including an unexpected one.** The first version
                # caught only the trigger's refusal, so anything else -- a connection that
                # could not be made -- killed the thread silently and the assertion below
                # reported an empty list with nothing to read.
                outcome = f"unexpected {type(e).__name__}: {e}"
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=insert, args=(people[0], 0.0)),
                   threading.Thread(target=insert, args=(people[1], 0.5))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 2, results)
        self.assertNotIn(True, ["unexpected" in r for r in results], results)
        refused = [r for r in results if r != "ok"]
        self.assertEqual(len(refused), 1, results)
        self.assertIn("places", refused[0])
        detail = self.client.get(f"/scheduling/sessions/{session_id}",
                                 headers=self.headers(tenant_id)).json()
        self.assertEqual(detail["held"], 2, detail)


class CalendarStaffTests(SchedulingApiTestCase):
    """ADM-SCH-01's ClassCell carries the coach, so the calendar has to answer it.

    The grid is `name · coach · fill` per cell, and a board that fetched one session read per
    cell to get the coach would make a week of classes a week of requests.
    """

    def test_the_calendar_names_the_live_coach(self) -> None:
        gym = self.gym()
        self.generate(gym, self.published(gym))
        read = self.client.get(
            f"/scheduling/calendar?location_id={gym['location_id']}"
            f"&from_date={day(0)}&to_date={day(30)}",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(read.status_code, 200, read.text)
        for session in read.json()["sessions"]:
            self.assertIsNotNone(session["staff"], session)

    def test_a_substitution_moves_the_name_rather_than_adding_one(self) -> None:
        """A superseded assignment is not a coach, and it is still a row."""
        gym = self.gym()
        session_id = self.a_session(gym)
        cover = self.resource(gym["tenant_id"], "staff", "COVER-CAL",
                              display_name="Dana Cover",
                              location_id=gym["location_id"])
        owner = self.headers(gym["tenant_id"])
        swapped = self.client.post(
            f"/scheduling/sessions/{session_id}/substitute", json={
                "replacement_resource_id": cover, "reason": "the coach is ill",
                **self.correlation()}, headers=owner)
        self.assertEqual(swapped.status_code, 200, swapped.text)
        read = self.client.get(
            f"/scheduling/calendar?location_id={gym['location_id']}"
            f"&from_date={day(0)}&to_date={day(30)}", headers=owner)
        row = next(x for x in read.json()["sessions"] if x["session_id"] == session_id)
        self.assertEqual(row["staff"], "Dana Cover")

    def test_a_class_with_no_staff_requirement_reports_null_not_blank(self) -> None:
        """A blank reads as a name nobody typed; null is a gap somebody has to fill."""
        gym = self.gym()
        self.generate(gym, self.published(gym, requirements=[
            {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
            {"kind": "room", "quantity": 1, "resource_id": gym["studio"]},
        ]))
        read = self.client.get(
            f"/scheduling/calendar?location_id={gym['location_id']}"
            f"&from_date={day(0)}&to_date={day(30)}",
            headers=self.headers(gym["tenant_id"]))
        rows = read.json()["sessions"]
        self.assertGreater(len(rows), 0)
        for session in rows:
            self.assertIsNone(session["staff"], session)


class UnstaffedSessionTests(SchedulingApiTestCase):
    """ADM-CC-01's STAFFING item: "Spin 19:00 Thursday has no coach -- 18 members booked"."""

    def unstaffed_template(self, gym: dict[str, Any]) -> str:
        """The same template with its staff requirement removed."""
        return self.published(gym, requirements=[
            {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
            {"kind": "room", "quantity": 1, "resource_id": gym["studio"]},
        ])

    def test_a_session_with_no_staff_requirement_is_listed(self) -> None:
        gym = self.gym()
        created = self.generate(gym, self.unstaffed_template(gym))
        read = self.client.get("/scheduling/unstaffed?days=62",
                               headers=self.headers(gym["tenant_id"]))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        listed = {s["session_id"] for s in body["sessions"]}
        self.assertIn(created["sessions"][0]["session_id"], listed)
        self.assertEqual(body["count"], created["created"])

    def test_a_session_with_a_coach_is_not_listed(self) -> None:
        """The queue exists because it is short. A staffed class in it is noise."""
        gym = self.gym()
        created = self.generate(gym, self.published(gym))
        read = self.client.get("/scheduling/unstaffed?days=62",
                               headers=self.headers(gym["tenant_id"]))
        listed = {s["session_id"] for s in read.json()["sessions"]}
        self.assertNotIn(created["sessions"][0]["session_id"], listed)
        self.assertEqual(read.json()["count"], 0)

    def test_a_substituted_session_still_has_a_coach(self) -> None:
        """A substitution supersedes the outgoing hold and inserts the replacement."""
        gym = self.gym()
        session_id = self.a_session(gym)
        cover = self.resource(gym["tenant_id"], "staff", "COVER-U",
                              location_id=gym["location_id"])
        owner = self.headers(gym["tenant_id"])
        swapped = self.client.post(
            f"/scheduling/sessions/{session_id}/substitute", json={
                "replacement_resource_id": cover, "reason": "the coach is ill",
                **self.correlation()}, headers=owner)
        self.assertEqual(swapped.status_code, 200, swapped.text)
        read = self.client.get("/scheduling/unstaffed?days=62", headers=owner)
        listed = {s["session_id"] for s in read.json()["sessions"]}
        self.assertNotIn(session_id, listed)

    def test_a_session_whose_only_assignment_was_superseded_has_no_coach(self) -> None:
        """The `superseded_at IS NULL` clause, which is the whole of "has a coach".

        No route reaches this state -- `substitute` always inserts a replacement -- so it is
        made directly, which is the only way to prove the clause. **Counting rows instead
        would report this session as staffed**, because the superseded row is still there:
        MOD-019 keeps it so the window a past conflict was decided against stays readable.
        """
        from app.db import tenant_scope

        gym = self.gym()
        session_id = self.a_session(gym)
        owner = self.headers(gym["tenant_id"])
        before = self.client.get("/scheduling/unstaffed?days=62", headers=owner)
        self.assertNotIn(session_id,
                         {s["session_id"] for s in before.json()["sessions"]})
        with tenant_scope(self._tenant_pool, gym["tenant_id"]) as conn:
            moved = conn.execute(
                "UPDATE plt01.sch_session_resources SET superseded_at = now(),"
                " superseded_by = %s, supersede_correlation_id = %s"
                " WHERE session_id = %s AND resource_kind = 'staff'"
                "   AND superseded_at IS NULL",
                (gym["coach"], str(uuid.uuid4()), session_id))
            self.assertEqual(moved.rowcount, 1)
        after = self.client.get("/scheduling/unstaffed?days=62", headers=owner)
        self.assertIn(session_id, {s["session_id"] for s in after.json()["sessions"]})
        self.assertIn("superseded", after.json()["a_superseded_assignment_is_not_a_coach"])

    def test_a_cancelled_session_needs_no_coach(self) -> None:
        gym = self.gym()
        created = self.generate(gym, self.unstaffed_template(gym))
        session_id = created["sessions"][0]["session_id"]
        owner = self.headers(gym["tenant_id"])
        cancelled = self.client.post(f"/scheduling/sessions/{session_id}/cancel", json={
            "cancellation_reason": "facility_closed", "reason": "a burst pipe",
            **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        read = self.client.get("/scheduling/unstaffed?days=62", headers=owner)
        self.assertNotIn(session_id,
                         {s["session_id"] for s in read.json()["sessions"]})

    def test_the_local_time_is_the_sessions_own_recorded_zone(self) -> None:
        """The class is advertised at 18:00 local, and the row says 18:00.

        The schedule board shipped the other version -- it sliced the ISO instant and
        rendered 15:00 for an 18:00 class in Asia/Amman -- and 140 green assertions did not
        notice, because every one of them asserted that the timezone was *named* on the page.
        """
        gym = self.gym()
        self.generate(gym, self.unstaffed_template(gym))
        read = self.client.get("/scheduling/unstaffed?days=62",
                               headers=self.headers(gym["tenant_id"]))
        row = read.json()["sessions"][0]
        self.assertEqual(row["timezone"], "Asia/Amman")
        self.assertIn("T18:00", row["local_starts_at"])
        self.assertNotIn("T18:00", row["starts_at"])

    def test_the_places_held_come_back_with_the_gap(self) -> None:
        """A gap nobody has booked and a gap with eighteen members are a different morning."""
        gym = self.gym()
        self.generate(gym, self.unstaffed_template(gym))
        read = self.client.get("/scheduling/unstaffed?days=62",
                               headers=self.headers(gym["tenant_id"]))
        body = read.json()
        self.assertEqual(body["members_affected"], 0)
        for row in body["sessions"]:
            self.assertEqual(row["held"], 0)
            self.assertEqual(row["places"], 12)

    def test_the_window_is_bounded_and_the_date_is_validated(self) -> None:
        gym = self.gym()
        head = self.headers(gym["tenant_id"])
        for query in ("days=0", "days=400", "from_date=31-12-2026"):
            answer = self.client.get(f"/scheduling/unstaffed?{query}", headers=head)
            self.assertEqual(answer.status_code, 422, f"{query}: {answer.text}")

    def test_a_session_holding_nothing_is_refused_the_queue(self) -> None:
        gym = self.gym()
        nobody = self.grant(gym["tenant_id"], [])
        refused = self.client.get(
            "/scheduling/unstaffed", headers=self.headers(gym["tenant_id"], nobody))
        self.assertEqual(refused.status_code, 403, refused.text)


class RotaWeekApiTests(SchedulingApiTestCase):
    """ADM-SCH-04 over HTTP: a resource's rota, and the booking the rota now refuses.

    `set_availability` had a writer and no reader since the module was built -- the schedule
    board's own gap note says "nothing here reads a resource's availability" -- so a rota
    could be written and the only way to learn what it said was to publish a template against
    it and read the refusal.
    """

    def window(self, gym: dict[str, Any], resource_id: str, kind: str,
               starts: str, ends: str, **extra: Any) -> None:
        created = self.client.post("/scheduling/availability", json={
            "resource_id": resource_id, "window_kind": kind,
            "starts_at": starts, "ends_at": ends, **extra, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)

    def week(self, gym: dict[str, Any], resource_id: str, *,
             reader: str | None = None, **query: Any) -> dict[str, Any]:
        params = "".join(f"&{k}={v}" for k, v in query.items())
        read = self.client.get(
            f"/scheduling/availability?resource_id={resource_id}{params}",
            headers=self.headers(gym["tenant_id"], reader))
        self.assertEqual(read.status_code, 200, read.text)
        body: dict[str, Any] = read.json()
        return body

    def withdraw(self, gym: dict[str, Any], window_id: str,
                 reason: str = "entered on the wrong day") -> Any:
        return self.client.post(
            f"/scheduling/availability/{window_id}/withdraw",
            json={"reason": reason, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))

    def window_id(self, gym: dict[str, Any], resource_id: str, kind: str,
                  starts: str, ends: str, **extra: Any) -> str:
        created = self.client.post("/scheduling/availability", json={
            "resource_id": resource_id, "window_kind": kind,
            "starts_at": starts, "ends_at": ends, **extra, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["window_id"])

    def test_a_window_can_be_taken_back_and_the_rota_stops_saying_it(self) -> None:
        """**A rota could only ever grow until this existed.**

        `sch_availability_windows` carried `GRANT SELECT, INSERT` and nothing else, so a day
        off entered on the wrong date, a shift typed as 06:00 instead of 16:00, or an absence
        written against the wrong coach had no remedy anywhere in the product. Invisible
        while the only writer was a seed script; decisive the moment a form exists, because
        `scheduling.availability.write` is routine and AAL 1 by design.
        """
        gym = self.gym()
        wid = self.window_id(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        tuesday = next(d for d in self.week(gym, gym["coach"])["days"] if d["weekday"] == 1)
        self.assertEqual(8 * 60, tuesday["open_minutes"])

        taken = self.withdraw(gym, wid)
        self.assertEqual(taken.status_code, 200, taken.text)
        self.assertTrue(taken.json()["withdrawn"])

        after = next(d for d in self.week(gym, gym["coach"])["days"] if d["weekday"] == 1)
        self.assertFalse(after["rota_binds"])
        self.assertIsNone(after["open_minutes"])
        self.assertEqual([], after["windows"])

    def test_a_withdrawal_happens_once(self) -> None:
        """The trigger makes it one-way and the service says so first, because a 409 naming
        the state is a caller who can act and a trigger's exception is a 500."""
        gym = self.gym()
        wid = self.window_id(gym, gym["coach"], "time_off", "12:00", "22:00",
                             on_date=str(next_weekday(1, after=1)),
                             reason="a hospital appointment")
        self.assertEqual(self.withdraw(gym, wid).status_code, 200)
        again = self.withdraw(gym, wid)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_withdrawn", again.json()["error"])

    def test_a_withdrawal_states_a_reason_and_an_unknown_window_is_not_found(self) -> None:
        gym = self.gym()
        wid = self.window_id(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        blank = self.withdraw(gym, wid, reason="   ")
        # A reason made only of whitespace is refused, and by the schema rather than by
        # convention: `~ '[^[:space:]]'`, because `btrim` strips spaces and nothing else.
        self.assertIn(blank.status_code, (400, 422), blank.text)
        missing = self.withdraw(gym, "eeeeeeee-1000-4000-8000-0000000000ff")
        self.assertEqual(missing.status_code, 404, missing.text)
        malformed = self.withdraw(gym, "not-a-uuid")
        self.assertEqual(malformed.status_code, 422, malformed.text)

    def test_a_withdrawn_window_no_longer_blocks_a_session(self) -> None:
        """**The point of the remedy, not just its bookkeeping.** A day off written against
        the wrong coach makes them unavailable; taking it back has to make them available
        again, which means every read of the rota has to ignore it -- not only the one the
        grid uses."""
        gym = self.gym()
        day = next_weekday(1, after=1)
        self.window(gym, gym["coach"], "working", "06:00", "22:00", weekday=1)
        wid = self.window_id(gym, gym["coach"], "time_off", "12:00", "22:00",
                             on_date=str(day), reason="booked against the wrong coach")
        before = next(d for d in self.week(gym, gym["coach"], from_date=str(day))["days"]
                      if d["date"] == str(day))
        self.assertEqual(6 * 60, before["open_minutes"])
        self.assertEqual(200, self.withdraw(gym, wid).status_code)
        after = next(d for d in self.week(gym, gym["coach"], from_date=str(day))["days"]
                     if d["date"] == str(day))
        self.assertEqual(16 * 60, after["open_minutes"])

    def test_the_rota_can_be_read_at_last(self) -> None:
        gym = self.gym()
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        body = self.week(gym, gym["coach"])
        self.assertEqual(7, len(body["days"]))
        tuesday = next(d for d in body["days"] if d["weekday"] == 1)
        self.assertTrue(tuesday["rota_binds"])
        self.assertEqual(8 * 60, tuesday["open_minutes"])
        self.assertEqual([{"starts_at": "09:00", "ends_at": "17:00"}],
                         tuesday["open_spans"])

    def test_every_time_is_the_resources_own_zone_and_not_the_sessions(self) -> None:
        """The defect this module shipped: `Window.timezone` was declared, written from the
        resource's own location and read by nothing, so a London coach rostered 09:00-17:00
        was available for an 09:00 class in Amman -- 06:00 their time. A grid of somebody's
        week is where that would be least questioned."""
        gym = self.gym(timezone="Europe/London")
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        body = self.week(gym, gym["coach"])
        self.assertEqual("Europe/London", body["timezone"])
        tuesday = next(d for d in body["days"] if d["weekday"] == 1)
        self.assertEqual("Europe/London", tuesday["windows"][0]["timezone"])

    def test_a_resource_with_no_rota_has_null_open_minutes_rather_than_zero(self) -> None:
        """A room, a court and a bike have no rota in any meaningful sense, and on the day a
        gym opens nobody has one. "26 of 0 hours booked" is the figure zero would produce."""
        gym = self.gym()
        body = self.week(gym, gym["studio"])
        self.assertIsNone(body["open_minutes"])
        for one in body["days"]:
            self.assertFalse(one["rota_binds"])
            self.assertIsNone(one["open_minutes"])
        self.assertIn("nobody wrote a rota",
                      body["an_unconstrained_resource_has_no_open_hours"])

    def test_a_rota_that_binds_and_is_fully_removed_is_zero_not_null(self) -> None:
        """**The pair the screen is about**, and the fixture carries both members of it."""
        gym = self.gym()
        tuesday = next_weekday(1, after=1)
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        self.window(gym, gym["coach"], "time_off", "08:00", "18:00",
                    on_date=tuesday.isoformat(), reason="annual leave")
        body = self.week(gym, gym["coach"], from_date=tuesday.isoformat())
        day_off = next(d for d in body["days"] if d["date"] == tuesday.isoformat())
        self.assertTrue(day_off["rota_binds"])
        self.assertEqual(0, day_off["open_minutes"])
        self.assertEqual([], day_off["open_spans"])

    def test_a_break_splits_the_open_span_rather_than_shortening_it(self) -> None:
        gym = self.gym()
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        self.window(gym, gym["coach"], "break", "12:00", "13:00", weekday=1)
        tuesday = next(d for d in self.week(gym, gym["coach"])["days"]
                       if d["weekday"] == 1)
        self.assertEqual([{"starts_at": "09:00", "ends_at": "12:00"},
                          {"starts_at": "13:00", "ends_at": "17:00"}],
                         tuesday["open_spans"])
        self.assertEqual(7 * 60, tuesday["open_minutes"])

    # --- the canvas's own case ----------------------------------------------

    def test_a_booking_inside_a_day_off_is_shown_and_flagged_never_dropped(self) -> None:
        """ADM-SCH-04's own sentence, and the reason this screen exists:

        "Thursday afternoon is an exception -- he asked for it off three weeks ago. His 17:30
        with Hala sits inside it, so the grid shows both and the booking is flagged rather
        than silently honoured or silently dropped ... reducing availability never deletes a
        booking, because the member on the other end has already been told a time."
        """
        gym = self.gym()
        template_id = self.published(gym)
        created = self.generate(gym, template_id)
        self.assertGreater(created["created"], 0, created)
        booked = created["sessions"][0]
        # The rota arrives *after* the sessions, which is the realistic order: a class is on
        # the calendar and somebody then asks for the afternoon off.
        # **The window has to contain the session, or the wrong rule answers.**
        # `unavailable_reason` checks working-hours containment first, so a 17:50-19:10 hold
        # against 09:00-17:00 is refused for being outside the rota and the time-off overlap
        # is never reached. The canvas's case is a day he *does* work, with the afternoon off
        # -- so the rota covers the evening and the exception is what the booking collides
        # with. Found by the test reading back a correct refusal for the other reason.
        self.window(gym, gym["coach"], "working", "09:00", "21:00", weekday=BOOKABLE_WEEKDAY)
        self.window(gym, gym["coach"], "time_off", "12:00", "20:00",
                    on_date=booked["local_date"], reason="annual leave")

        body = self.week(gym, gym["coach"], from_date=booked["local_date"])
        held = [s for s in body["sessions"] if s["session_id"] == booked["session_id"]]
        self.assertEqual(1, len(held), body["sessions"])
        self.assertTrue(held[0]["conflicts_with_availability"])
        self.assertIn("time off", held[0]["conflict_reason"])
        self.assertEqual(1, body["conflicts"])
        self.assertIn("already been told a time", body["a_booking_is_never_dropped"])

    def test_a_booking_the_rota_admits_carries_no_conflict(self) -> None:
        gym = self.gym()
        created = self.generate(gym, self.published(gym))
        booked = created["sessions"][0]
        # 18:00 for an hour, with setup and cleanup either side, sits inside 09:00-21:00.
        self.window(gym, gym["coach"], "working", "09:00", "21:00", weekday=BOOKABLE_WEEKDAY)
        body = self.week(gym, gym["coach"], from_date=booked["local_date"])
        held = [s for s in body["sessions"] if s["session_id"] == booked["session_id"]]
        self.assertEqual(1, len(held))
        self.assertFalse(held[0]["conflicts_with_availability"], held[0])
        self.assertIsNone(held[0]["conflict_reason"])
        self.assertEqual(0, body["conflicts"])

    def test_booked_and_open_are_two_numbers_because_the_ratio_can_exceed_one(self) -> None:
        """A session outside the rota is booked and not open, which is the whole point of the
        screen -- so a single percentage would have to be over 100 or wrong."""
        gym = self.gym()
        created = self.generate(gym, self.published(gym))
        booked = created["sessions"][0]
        self.window(gym, gym["coach"], "working", "09:00", "10:00", weekday=BOOKABLE_WEEKDAY)
        body = self.week(gym, gym["coach"], from_date=booked["local_date"])
        self.assertGreater(body["booked_minutes"], 0)
        assert body["open_minutes"] is not None
        self.assertGreater(body["booked_minutes"], body["open_minutes"])

    def test_a_cancelled_session_occupies_nobody(self) -> None:
        gym = self.gym()
        created = self.generate(gym, self.published(gym))
        booked = created["sessions"][0]
        self.window(gym, gym["coach"], "working", "09:00", "21:00", weekday=BOOKABLE_WEEKDAY)
        cancelled = self.client.post(
            f"/scheduling/sessions/{booked['session_id']}/cancel",
            json={"cancellation_reason": "instructor_unavailable",
                  "reason": "the instructor is ill", **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = self.week(gym, gym["coach"], from_date=booked["local_date"])
        self.assertEqual([], [s for s in body["sessions"]
                              if s["session_id"] == booked["session_id"]])

    # --- the masked reason ---------------------------------------------------

    def test_a_time_off_reason_needs_the_permission_that_could_have_written_it(self) -> None:
        """The one window kind the schema requires a reason on is the one about why a person
        is away, which is where a health fact goes in practice -- MOD-017's rule, and the
        same prose `sch_session_changes.reason` is masked for one table over."""
        gym = self.gym()
        tuesday = next_weekday(1, after=1)
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        self.window(gym, gym["coach"], "time_off", "12:00", "17:00",
                    on_date=tuesday.isoformat(), reason="chemotherapy on Tuesdays")

        reader = self.grant(gym["tenant_id"], ["scheduling.schedule.read"])
        masked = self.week(gym, gym["coach"], reader=reader,
                           from_date=tuesday.isoformat())
        off = [w for d in masked["days"] for w in d["windows"] if w["kind"] == "time_off"]
        self.assertEqual(1, len(off))
        # **The exception itself is never hidden** -- a grid that dropped it would be the rota
        # lying about who is working. Only the sentence is.
        self.assertTrue(off[0]["reason_masked"])
        self.assertIsNone(off[0]["reason"])
        self.assertNotIn("chemotherapy", json.dumps(masked))

        setter = self.grant(gym["tenant_id"],
                            ["scheduling.schedule.read", "scheduling.availability.write"])
        open_to = self.week(gym, gym["coach"], reader=setter,
                            from_date=tuesday.isoformat())
        off = [w for d in open_to["days"] for w in d["windows"] if w["kind"] == "time_off"]
        self.assertFalse(off[0]["reason_masked"])
        self.assertEqual("chemotherapy on Tuesdays", off[0]["reason"])

    def test_a_working_window_has_no_reason_to_mask(self) -> None:
        gym = self.gym()
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        tuesday = next(d for d in self.week(gym, gym["coach"])["days"]
                       if d["weekday"] == 1)
        self.assertFalse(tuesday["windows"][0]["reason_masked"])
        self.assertIsNone(tuesday["windows"][0]["reason"])

    # --- the bounds ----------------------------------------------------------

    def test_an_unbounded_window_is_refused(self) -> None:
        gym = self.gym()
        for weeks in (0, 5, 100000):
            with self.subTest(weeks=weeks):
                read = self.client.get(
                    f"/scheduling/availability?resource_id={gym['coach']}&weeks={weeks}",
                    headers=self.headers(gym["tenant_id"]))
                self.assertEqual(read.status_code, 422, read.text)

    def test_a_malformed_or_unknown_resource_is_422_then_404(self) -> None:
        gym = self.gym()
        bad = self.client.get(
            "/scheduling/availability?resource_id=not-a-uuid",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(bad.status_code, 422, bad.text)
        missing = self.client.get(
            f"/scheduling/availability?resource_id={uuid.uuid4()}",
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(missing.status_code, 404, missing.text)

    def test_the_rota_read_needs_the_schedule_read(self) -> None:
        gym = self.gym()
        nobody = self.grant(gym["tenant_id"], [])
        refused = self.client.get(
            f"/scheduling/availability?resource_id={gym['coach']}",
            headers=self.headers(gym["tenant_id"], nobody))
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_nobody_is_named_in_a_rota_read(self) -> None:
        """A rota is who works when. The resource row carries a `person_id` and nothing on
        this read resolves it to a name, which is `people.person.read`'s to answer."""
        gym = self.gym()
        self.window(gym, gym["coach"], "working", "09:00", "17:00", weekday=1)
        body = json.dumps(self.week(gym, gym["coach"]))
        for leaked in ("legal_name", "date_of_birth", "email", "phone"):
            self.assertNotIn(leaked, body)


class ConflictCheckTests(SchedulingApiTestCase):
    """ADM-SCH-03's live check: a class that does not exist yet, asked about.

    **The read `preview_publish` could not answer.** That one takes a template id and assesses
    what republishing it would move; this screen is the one where there is no template yet, and
    the canvas says when the answer has to arrive: "conflicts surface as the coach field
    changes, not on save".
    """

    def proposal(self, gym: dict[str, Any], **over: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "location_id": gym["location_id"],
            "rule": {
                "frequency": "weekly", "local_time": "18:00", "duration_minutes": 60,
                "starts_on": day(1), "until": day(21),
                "weekdays": [BOOKABLE_WEEKDAY],
            },
            "policy": {"capacity": 12, "setup_minutes": 10, "cleanup_minutes": 10},
            "requirements": [
                {"kind": "room", "quantity": 1, "resource_id": gym["studio"]},
                {"kind": "staff", "quantity": 1, "resource_id": gym["coach"]},
            ],
        }
        body.update(over)
        return body

    def check(self, gym: dict[str, Any], **over: Any) -> Any:
        return self.client.post(
            "/scheduling/conflict-check", json=self.proposal(gym, **over),
            headers=self.headers(gym["tenant_id"]))

    def test_a_clear_hour_comes_back_clear_with_the_count_the_button_states(self) -> None:
        """"Create · 2 classes a week" is a figure, so the read answers it."""
        gym = self.gym()
        answer = self.check(gym)
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertTrue(body["clear"])
        self.assertEqual(body["conflicts"], [])
        self.assertEqual(body["per_week"], 1)
        self.assertGreaterEqual(body["occurrences"], 2)
        self.assertEqual(body["timezone"], "Asia/Amman")

    def test_per_week_is_absent_where_the_rule_is_not_weekly(self) -> None:
        """A monthly or one-off rule has no weekly figure, so there is none to state.

        Computed from a span it would be a number nobody wrote -- MOD-022's own refusal to
        divide by a capacity it cannot defend.
        """
        gym = self.gym()
        once = self.check(gym, rule={
            "frequency": "once", "local_time": "18:00", "duration_minutes": 60,
            "starts_on": day(2), "until": day(2), "weekdays": []})
        self.assertEqual(once.status_code, 200, once.text)
        self.assertIsNone(once.json()["per_week"])

    def test_a_studio_already_held_is_reported_with_the_class_that_holds_it(self) -> None:
        """The clash the canvas draws, and the session it points at.

        A published template's generated session holds the studio, so a second class at the
        same hour is the ordinary collision -- and the report names the resource and the
        session rather than saying "busy".
        """
        gym = self.gym()
        self.a_session(gym)
        answer = self.check(gym)
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertFalse(body["clear"])
        kinds = {c["kind"] for c in body["conflicts"]}
        self.assertIn("double_booked", kinds)
        clash = next(c for c in body["conflicts"] if c["kind"] == "double_booked")
        self.assertIsNotNone(clash["resource_id"])
        self.assertIsNotNone(clash["with_session_id"])
        self.assertIsNotNone(clash["resource_name"])
        self.assertEqual(clash["local_date"], body["conflicts"][0]["local_date"])

    def test_it_warns_and_does_not_block(self) -> None:
        """The canvas's own sentence: "a manager may know Omar's PT is moving".

        So a clash is a 200 with a report rather than a refusal, and the response says what
        publishing over one would cost.
        """
        gym = self.gym()
        self.a_session(gym)
        answer = self.check(gym)
        self.assertEqual(answer.status_code, 200)
        self.assertIn("scheduling.conflict.override",
                      answer.json()["it_warns_it_does_not_block"])

    def test_a_busy_coach_brings_back_the_staff_who_are_free(self) -> None:
        """"Dana and Yousef are both qualified and free at that hour" -- the free half.

        Nothing in this build stores a skill, so the response offers the staff whose rota
        admits the hour and who hold nothing else over it, and says that is what it means.
        """
        gym = self.gym()
        self.a_session(gym)
        spare = self.resource(
            gym["tenant_id"], "staff", f"DANA-{uuid.uuid4().hex[:6].upper()}",
            location_id=gym["location_id"])
        answer = self.check(gym)
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertIn(spare, [a["resource_id"] for a in body["alternatives"]])
        self.assertNotIn(gym["coach"], [a["resource_id"] for a in body["alternatives"]])
        self.assertIn("stores a skill", body["alternatives_are_free_not_qualified"])

    def test_the_spare_quantity_of_an_anonymous_requirement_bounds_the_capacity(self) -> None:
        """"Studio 2 holds 20 bikes. Capacity cannot exceed the room."

        The ceiling is the quantity that exists rather than a seat count on a room, which this
        schema deliberately does not carry: twenty bikes is one row with a quantity of twenty.
        A *named* requirement contributes none, because the ceiling there is the thing itself.
        """
        gym = self.gym()
        answer = self.check(gym, requirements=[
            {"kind": "room", "quantity": 1, "resource_id": gym["studio"]},
            {"kind": "equipment", "quantity": 12},
        ])
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertEqual(body["spare"], {"equipment": 20})

    def test_the_walk_is_bounded_and_says_how_far_it_looked(self) -> None:
        """Asked per keystroke, so the walk is bounded and the answer is not silent about it.

        A daily rule over three weeks is twenty-one occurrences and each costs a query; the
        response carries what it examined and out of how many.
        """
        gym = self.gym()
        answer = self.check(gym, rule={
            "frequency": "daily", "local_time": "18:00", "duration_minutes": 60,
            "starts_on": day(1), "until": day(21), "weekdays": []})
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertEqual(body["examined"], 8)
        self.assertGreater(body["examined_of"], 8)
        refused = self.client.post(
            "/scheduling/conflict-check",
            json={**self.proposal(gym), "limit": 99},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_rule_the_engine_could_not_use_is_refused_rather_than_called_clear(self) -> None:
        """A dry run that accepted an impossible rule would report "no conflicts" about a class
        nobody can create, which is the confident wrong answer this read exists to avoid."""
        gym = self.gym()
        answer = self.check(gym, rule={
            "frequency": "weekly", "local_time": "18:00", "duration_minutes": 60,
            "starts_on": day(1), "until": day(21), "weekdays": []})
        self.assertEqual(answer.status_code, 422, answer.text)

    def test_a_malformed_location_is_refused_rather_than_crashing(self) -> None:
        gym = self.gym()
        answer = self.client.post(
            "/scheduling/conflict-check",
            json={**self.proposal(gym), "location_id": "not-a-uuid"},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(answer.status_code, 422, answer.text)
        missing = self.client.post(
            "/scheduling/conflict-check",
            json={**self.proposal(gym), "location_id": str(uuid.uuid4())},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(missing.status_code, 404, missing.text)

    def test_a_coach_whose_rota_refuses_the_hour_is_its_own_conflict_kind(self) -> None:
        """"The rota says no" and "the room is busy" have different remedies, so they are
        different kinds -- the generation's own split, asked here before anything is written."""
        gym = self.gym()
        window = self.client.post("/scheduling/availability", json={
            "resource_id": gym["coach"], "window_kind": "working",
            "weekday": BOOKABLE_WEEKDAY,
            "starts_at": "09:00", "ends_at": "11:00", **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(window.status_code, 201, window.text)
        answer = self.check(gym)
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertIn("unavailable", {c["kind"] for c in body["conflicts"]})

    def test_the_walk_starts_at_today_rather_than_at_the_rule_s_first_date(self) -> None:
        """A rule that began last week says nothing about the class being created now.

        And examining its past dates spends the bound on occurrences nobody asked about, so
        the first one examined is on or after today.
        """
        gym = self.gym()
        answer = self.check(gym, rule={
            "frequency": "daily", "local_time": "18:00", "duration_minutes": 60,
            "starts_on": day(-10), "until": day(21), "weekdays": []})
        self.assertEqual(answer.status_code, 200, answer.text)
        body = answer.json()
        self.assertEqual(body["examined"], 8)
        # **The dates, because the count cannot see this.** Eight of the past is still eight,
        # which is why the mutation that started the walk at the rule's first date came back
        # uncaught against a count assertion.
        self.assertGreaterEqual(body["examined_from"], TODAY.isoformat())
        self.assertLess(body["examined_of"], body["occurrences"])

    def test_a_clash_inside_the_proposals_own_setup_margin_is_a_clash(self) -> None:
        """The margins are part of the window this check asks about.

        **The proposal's own margins, which is the half a count cannot see.** The existing
        class runs 18:00-19:00 and holds exactly that; the proposed one starts at 19:10 with
        fifteen minutes of setup, so its *window* opens at 18:55 and overlaps. Asking about
        the bare session would report it clear -- the two questions asked about different
        spans, which is the defect a reviewer found in the generation.
        """
        gym = self.gym()
        template_id = self.published(gym, policy={"capacity": 12})
        self.assertGreater(self.generate(gym, template_id)["created"], 0)
        bare = self.check(gym, policy={"capacity": 12}, rule={
            "frequency": "weekly", "local_time": "19:10", "duration_minutes": 30,
            "starts_on": day(1), "until": day(21), "weekdays": [BOOKABLE_WEEKDAY]})
        self.assertEqual(bare.status_code, 200, bare.text)
        self.assertTrue(bare.json()["clear"], bare.text)
        with_setup = self.check(
            gym, policy={"capacity": 12, "setup_minutes": 15}, rule={
                "frequency": "weekly", "local_time": "19:10", "duration_minutes": 30,
                "starts_on": day(1), "until": day(21), "weekdays": [BOOKABLE_WEEKDAY]})
        self.assertEqual(with_setup.status_code, 200, with_setup.text)
        self.assertFalse(with_setup.json()["clear"], with_setup.text)

    def test_the_suggestions_are_the_coaches_free_at_this_site(self) -> None:
        """Three guards, and each needs a coach the others admit.

        A coach at another site is not an alternative at this one; a coach whose rota refuses
        the hour is not free however empty their diary; and a coach holding something else over
        the window is not free either -- which needs a *second* class, because the coach this
        proposal names is already excluded for being the one the clash is about.
        """
        gym = self.gym()
        tenant_id = gym["tenant_id"]
        suffix = uuid.uuid4().hex[:6].upper()
        self.a_session(gym)

        elsewhere = self.location(tenant_id, timezone="Asia/Amman")
        away = self.resource(tenant_id, "staff", f"AWAY-{suffix}", location_id=elsewhere)
        rostered_off = self.resource(
            tenant_id, "staff", f"OFF-{suffix}", location_id=gym["location_id"])
        self.assertEqual(self.client.post("/scheduling/availability", json={
            "resource_id": rostered_off, "window_kind": "working",
            "weekday": BOOKABLE_WEEKDAY, "starts_at": "09:00", "ends_at": "11:00",
            **self.correlation()}, headers=self.headers(tenant_id)).status_code, 201)
        free = self.resource(
            tenant_id, "staff", f"FREE-{suffix}", location_id=gym["location_id"])

        # A second class at the same hour, so its coach is busy without being named by this
        # proposal: the only guard that can exclude them is the held-over check.
        other_studio = self.resource(
            tenant_id, "room", f"ROOM2-{suffix}", location_id=gym["location_id"])
        other_coach = self.resource(
            tenant_id, "staff", f"BUSY2-{suffix}", location_id=gym["location_id"])
        # **Its own service format too**, because the first class is already holding the
        # shared one at that hour -- a service resource exists once, so two classes of the
        # same format at the same instant is the over-capacity the engine correctly refuses.
        other_service = self.resource(tenant_id, "service", f"YOGA-{suffix}")
        other = self.published(gym, requirements=[
            {"kind": "service", "quantity": 1, "resource_id": other_service},
            {"kind": "room", "quantity": 1, "resource_id": other_studio},
            {"kind": "staff", "quantity": 1, "resource_id": other_coach},
        ], service_resource_id=other_service, template_code=f"SPIN2-{suffix}")
        self.assertGreater(self.generate(gym, other)["created"], 0)

        offered = [a["resource_id"] for a in self.check(gym).json()["alternatives"]]
        self.assertIn(free, offered)
        self.assertNotIn(away, offered)
        self.assertNotIn(rostered_off, offered)
        self.assertNotIn(other_coach, offered)
        self.assertNotIn(gym["coach"], offered)

    def test_the_coach_the_clash_is_about_is_not_their_own_alternative(self) -> None:
        """The guard the busy check cannot stand in for.

        When the conflict is the *rota* rather than a hold, the coach it names holds nothing --
        so nothing but `besides` keeps them off a list offering a way round their own absence.
        """
        gym = self.gym()
        tenant_id = gym["tenant_id"]
        self.assertEqual(self.client.post("/scheduling/availability", json={
            "resource_id": gym["coach"], "window_kind": "working",
            "weekday": BOOKABLE_WEEKDAY, "starts_at": "09:00", "ends_at": "11:00",
            **self.correlation()}, headers=self.headers(tenant_id)).status_code, 201)
        spare = self.resource(
            tenant_id, "staff", f"SPARE-{uuid.uuid4().hex[:6].upper()}",
            location_id=gym["location_id"])
        body = self.check(gym).json()
        self.assertIn("unavailable", {c["kind"] for c in body["conflicts"]})
        offered = [a["resource_id"] for a in body["alternatives"]]
        self.assertIn(spare, offered)
        self.assertNotIn(gym["coach"], offered)

    def test_the_suggestions_are_bounded(self) -> None:
        """A tenant with sixty coaches would otherwise put sixty names under one field, which
        is a list rather than a suggestion."""
        gym = self.gym()
        self.a_session(gym)
        for n in range(FREE := 6):
            self.resource(gym["tenant_id"], "staff",
                          f"SPARE{n}-{uuid.uuid4().hex[:6].upper()}",
                          location_id=gym["location_id"])
        self.assertGreater(FREE, 4)
        self.assertEqual(len(self.check(gym).json()["alternatives"]), 4)

    def test_the_spare_count_is_what_is_free_here_and_now(self) -> None:
        """Two guards on the figure that bounds the capacity field.

        Equipment at another site is not in this room, and equipment the published class is
        already holding is not available to a second one at the same hour -- a ceiling that
        counted either would put a capacity on screen the publish then refuses.
        """
        gym = self.gym()
        tenant_id = gym["tenant_id"]
        suffix = uuid.uuid4().hex[:6].upper()
        elsewhere = self.location(tenant_id, timezone="Asia/Amman")
        self.resource(tenant_id, "equipment", f"AWAYBIKES-{suffix}",
                      quantity=50, location_id=elsewhere)
        requirements = [
            {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
            {"kind": "room", "quantity": 1, "resource_id": gym["studio"]},
            {"kind": "equipment", "quantity": 8},
        ]
        # Nothing held yet: twenty bikes here, and the fifty at the other site are not in
        # this room.
        self.assertEqual(
            self.check(gym, requirements=requirements).json()["spare"], {"equipment": 20})
        # A class that holds eight of them leaves twelve.
        template_id = self.published(gym, requirements=requirements,
                                     template_code=f"SPIN3-{suffix}")
        self.assertGreater(self.generate(gym, template_id)["created"], 0)
        self.assertEqual(
            self.check(gym, requirements=requirements).json()["spare"], {"equipment": 12})


class ResourceCapacityTests(SchedulingApiTestCase):
    """ADM-SCH-06's two facts, through the routes. ADR-0018.

    > Capacity here is the ceiling every class inherits. Double-booking is impossible because
    > ADM-SCH-03 reads this list — the constraint lives in one place, not in each scheduler's
    > memory.

    **Three different numbers, and this build had one of them.** `quantity` is how many of a
    thing there are, a policy's `capacity` is how many places a class offers, and what the
    canvas draws is neither: how many *people* a space holds. These assert that the three stay
    three, and that the ceiling refuses a class the room cannot take.
    """

    def space(self, gym: dict[str, Any], code: str, capacity: int | None) -> str:
        body: dict[str, Any] = {"location_id": gym["location_id"]}
        if capacity is not None:
            body["capacity"] = capacity
        return self.resource(gym["tenant_id"], "room", code, **body)

    def listed(self, tenant_id: str, **params: Any) -> dict[str, Any]:
        read = self.client.get("/scheduling/resources", params={
            **params, **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        return dict(read.json())

    def one(self, tenant_id: str, resource_id: str) -> dict[str, Any]:
        for row in self.listed(tenant_id)["resources"]:
            if row["resource_id"] == resource_id:
                return dict(row)
        raise AssertionError(f"{resource_id} is not in the list")

    # ---------------------------------------------------------------- the two facts

    def test_a_room_states_how_many_people_it_holds(self):
        gym = self.gym()
        room = self.space(gym, f"CAP-{uuid.uuid4().hex[:6].upper()}", 30)
        self.assertEqual(self.one(gym["tenant_id"], room)["capacity"], 30)

    def test_a_coach_cannot_hold_people_because_the_number_has_no_reading(self):
        gym = self.gym()
        refused = self.client.post("/scheduling/resources", json={
            "resource_code": f"CO-{uuid.uuid4().hex[:6].upper()}",
            "resource_kind": "staff", "display_name": "A coach with a capacity",
            "capacity": 10, "location_id": gym["location_id"], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_an_unstated_capacity_is_null_and_not_zero(self):
        """ADR-0018 D1. A room nobody has described does not bind a class, and rendering it as
        zero would say the room holds nobody -- a different fact, and the one a reader acts
        on."""
        gym = self.gym()
        self.assertIsNone(self.one(gym["tenant_id"], gym["studio"])["capacity"])
        listed = self.listed(gym["tenant_id"])
        self.assertIn("unstated rather than zero", listed["capacity_is_a_ceiling"])

    def test_equipment_goes_in_a_space_and_the_list_says_what_is_in_each(self):
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        room = self.space(gym, f"SP-{suffix}", 30)
        bikes = self.resource(
            gym["tenant_id"], "equipment", f"BK-{suffix}", quantity=20,
            location_id=gym["location_id"], parent_resource_id=room)
        self.assertEqual(self.one(gym["tenant_id"], bikes)["parent_resource_id"], room)
        contains = self.one(gym["tenant_id"], room)["contains"]
        self.assertEqual(
            [(c["resource_code"], c["quantity"]) for c in contains],
            [(f"BK-{suffix}", 20)],
            "twenty bikes are one row with a quantity of twenty, which is what makes '20 "
            "bikes' a figure rather than a row count")

    def test_only_equipment_goes_inside_a_space(self):
        gym = self.gym()
        room = self.space(gym, f"RM-{uuid.uuid4().hex[:6].upper()}", 30)
        refused = self.client.post("/scheduling/resources", json={
            "resource_code": f"IN-{uuid.uuid4().hex[:6].upper()}",
            "resource_kind": "room", "display_name": "A room inside a room",
            "location_id": gym["location_id"], "parent_resource_id": room,
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_bike_cannot_be_inside_a_coach(self):
        """The trigger, not a CHECK: what the parent *is* lives in another row."""
        gym = self.gym()
        refused = self.client.post("/scheduling/resources", json={
            "resource_code": f"BC-{uuid.uuid4().hex[:6].upper()}",
            "resource_kind": "equipment", "display_name": "A bike inside a coach",
            "location_id": gym["location_id"], "parent_resource_id": gym["coach"],
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("staff", refused.text)

    def test_equipment_cannot_be_in_another_clubs_space(self):
        """Twenty bikes in Khalda are not twenty bikes in Sweifieh, and a ceiling computed
        across clubs is a number about bikes nobody at this site can reach."""
        gym = self.gym()
        elsewhere = self.location(gym["tenant_id"], timezone="Asia/Amman")
        far_room = self.resource(
            gym["tenant_id"], "room", f"FAR-{uuid.uuid4().hex[:6].upper()}",
            location_id=elsewhere, capacity=30)
        refused = self.client.post("/scheduling/resources", json={
            "resource_code": f"BF-{uuid.uuid4().hex[:6].upper()}",
            "resource_kind": "equipment", "display_name": "A bike in another club",
            "location_id": gym["location_id"], "parent_resource_id": far_room,
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("different locations", refused.text)

    # ---------------------------------------------------------------- the ceiling

    def test_a_class_may_not_offer_more_places_than_its_named_room_holds(self):
        gym = self.gym()
        code = f"SM-{uuid.uuid4().hex[:6].upper()}"
        room = self.space(gym, code, 20)
        refused = self.client.post("/scheduling/templates", json={
            "template_code": f"BIG-{uuid.uuid4().hex[:6].upper()}",
            "display_name": "A class bigger than its room",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 30},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": room},
            ],
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_class_inside_its_room_is_accepted_and_the_ceiling_comes_back(self):
        gym = self.gym()
        room = self.space(gym, f"OK-{uuid.uuid4().hex[:6].upper()}", 20)
        created = self.client.post("/scheduling/templates", json={
            "template_code": f"FIT-{uuid.uuid4().hex[:6].upper()}",
            "display_name": "A class that fits",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 20},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": room},
            ],
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capacity_ceiling"], 20)
        self.assertEqual(created.json()["ceiling_bound_kind"], "space")

    def test_an_anonymous_room_requirement_is_bounded_by_the_smallest_candidate(self):
        """**The slice's hardest decision.** "A room" means the generator may pick any room of
        that kind at the site, so the class has to fit in whichever it picks -- and taking the
        largest would let a class of fifty be assigned a studio holding twenty, which is the
        failure this whole slice exists to prevent. The cost is real and stated: naming the
        hall is the remedy, which is a requirement that says what it means.
        """
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        self.space(gym, f"SMALL-{suffix}", 20)
        self.space(gym, f"HALL-{suffix}", 50)
        body: dict[str, Any] = {
            "template_code": f"ANY-{suffix}",
            "display_name": "A class in any room",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 30},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1},
            ],
            "restrictions": [],
        }
        refused = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        # And twenty is accepted, which is the smallest candidate rather than the largest.
        body["policy"] = {"capacity": 20}
        body["template_code"] = f"ANY2-{suffix}"
        created = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capacity_ceiling"], 20)

    def test_a_bike_per_attendee_bounds_the_class_at_the_bikes_in_that_room(self):
        """ADM-SCH-03's own named gap: "Studio 2 holds 20 bikes. Capacity cannot exceed the
        room" needs the one fact nothing recorded -- that a format takes one unit of equipment
        per attendee."""
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        room = self.space(gym, f"SPIN-{suffix}", 40)
        self.resource(gym["tenant_id"], "equipment", f"BIKE-{suffix}", quantity=20,
                      location_id=gym["location_id"], parent_resource_id=room)
        body: dict[str, Any] = {
            "template_code": f"CYC-{suffix}",
            "display_name": "A spin class",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 25},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": room},
                {"kind": "equipment", "quantity": 1, "per_attendee": True},
            ],
            "restrictions": [],
        }
        refused = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("20", refused.text)
        body["policy"] = {"capacity": 20}
        body["template_code"] = f"CYC2-{suffix}"
        created = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["ceiling_bound_kind"], "equipment")

    def test_equipment_at_the_club_and_in_no_room_bounds_no_room(self):
        """The fixture's own bikes have no parent, so a per-attendee requirement against a
        room with nothing in it holds nobody. Uncomfortable, correct, and the reason the
        containment is a relation rather than a label."""
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        room = self.space(gym, f"BARE-{suffix}", 40)
        refused = self.client.post("/scheduling/templates", json={
            "template_code": f"NOB-{suffix}",
            "display_name": "A spin class with no bikes in the room",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 1},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": room},
                {"kind": "equipment", "quantity": 1, "per_attendee": True},
            ],
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("allows 0", refused.text)

    def test_a_retired_room_does_not_bound_a_class(self):
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        tiny = self.space(gym, f"TINY-{suffix}", 5)
        self.space(gym, f"BIG-{suffix}", 40)
        retired = self.client.post(
            f"/scheduling/resources/{tiny}/retire",
            json={"reason": "knocked through", **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(retired.status_code, 200, retired.text)
        created = self.client.post("/scheduling/templates", json={
            "template_code": f"RET-{suffix}",
            "display_name": "A class in the room that is left",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 40},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1},
            ],
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)

    def test_the_fixture_template_is_unaffected_because_nothing_states_a_capacity(self):
        """**The default is what this build already did**, which is load-bearing: every
        resource registered before `0035` states no capacity, so no template already written
        changes verdict. ADR-0011's reasoning about the billing anchor, applied to a ceiling.
        """
        gym = self.gym()
        self.template(gym)

    def test_a_named_resource_cannot_also_be_required_per_attendee(self):
        gym = self.gym()
        refused = self.client.post("/scheduling/templates", json={
            "template_code": f"NM-{uuid.uuid4().hex[:6].upper()}",
            "display_name": "A named per-attendee requirement",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 10},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "equipment", "quantity": 1, "resource_id": gym["bikes"],
                 "per_attendee": True},
            ],
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_an_anonymous_room_counts_the_bikes_in_the_poorest_of_them(self):
        """**The case that separates a minimum from a sum**, which the mutation sweep asked
        for: with one required space the two agree, so a club-wide sum passed every other test
        here. Two candidate rooms with different counts is the shape where they differ -- and
        the smaller has to win, because the generator may pick either.

        **Its own site**, because the ceiling is over *every* active room there: the shared
        fixture's studio holds no bikes, so any site that includes it is bounded at zero. That
        is the rule working rather than a wrinkle to design around -- a spin class assigned a
        room with no bikes in it can hold nobody -- and it is the subject of the test below.
        """
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        site = self.location(gym["tenant_id"])
        poor = self.resource(gym["tenant_id"], "room", f"POOR-{suffix}",
                             location_id=site, capacity=40)
        rich = self.resource(gym["tenant_id"], "room", f"RICH-{suffix}",
                             location_id=site, capacity=40)
        self.resource(gym["tenant_id"], "equipment", f"BP-{suffix}", quantity=5,
                      location_id=site, parent_resource_id=poor)
        self.resource(gym["tenant_id"], "equipment", f"BR-{suffix}", quantity=25,
                      location_id=site, parent_resource_id=rich)
        body: dict[str, Any] = {
            "template_code": f"MIX-{suffix}",
            "display_name": "A spin class in any room",
            "service_resource_id": gym["service"],
            "location_id": site,
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 6},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1},
                {"kind": "equipment", "quantity": 1, "per_attendee": True},
            ],
            "restrictions": [],
        }
        refused = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        # Five is the poorer room's own count, and it is accepted. A club-wide sum would be
        # thirty, and this is the assertion that says which one the ceiling is.
        body["policy"] = {"capacity": 5}
        body["template_code"] = f"MIX2-{suffix}"
        created = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capacity_ceiling"], 5)
        self.assertEqual(created.json()["ceiling_bound_kind"], "equipment")

    def test_a_room_with_no_bikes_in_it_bounds_an_anonymous_spin_class_at_nobody(self):
        """Uncomfortable, correct, and the reason to name the room instead.

        "Any room" means the generator may pick the yoga studio, where there are no bikes --
        so a format taking one each cannot run there, and the honest answer is to refuse the
        template rather than to publish a class that cannot be held. The remedy is a
        requirement that says which room, which is what naming one means.
        """
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        spin = self.space(gym, f"SPIN-{suffix}", 40)
        self.resource(gym["tenant_id"], "equipment", f"BS-{suffix}", quantity=20,
                      location_id=gym["location_id"], parent_resource_id=spin)
        body: dict[str, Any] = {
            "template_code": f"ANYB-{suffix}",
            "display_name": "A spin class in any room",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 1},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1},
                {"kind": "equipment", "quantity": 1, "per_attendee": True},
            ],
            "restrictions": [],
        }
        refused = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("allows 0", refused.text)
        # Naming the spin studio is the remedy, and twenty is then what it holds.
        body["requirements"][1] = {"kind": "room", "quantity": 1, "resource_id": spin}
        body["policy"] = {"capacity": 20}
        body["template_code"] = f"NAMED-{suffix}"
        created = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capacity_ceiling"], 20)

    def test_retired_equipment_stops_counting_toward_the_ceiling(self):
        """Bikes taken out of service are bikes nobody can ride, so a class sized against them
        would be a class the room cannot hold. The sweep asked for this one: with no case,
        dropping the status filter from the equipment count changed nothing.
        """
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        room = self.space(gym, f"RET-{suffix}", 40)
        kept = self.resource(gym["tenant_id"], "equipment", f"KEEP-{suffix}", quantity=5,
                             location_id=gym["location_id"], parent_resource_id=room)
        broken = self.resource(gym["tenant_id"], "equipment", f"BRK-{suffix}", quantity=15,
                               location_id=gym["location_id"], parent_resource_id=room)
        self.assertNotEqual(kept, broken)
        gone = self.client.post(
            f"/scheduling/resources/{broken}/retire",
            json={"reason": "rusted through", **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(gone.status_code, 200, gone.text)
        body: dict[str, Any] = {
            "template_code": f"RB-{suffix}",
            "display_name": "A spin class on the bikes that still work",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 20},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": room},
                {"kind": "equipment", "quantity": 1, "per_attendee": True},
            ],
            "restrictions": [],
        }
        refused = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("allows 5", refused.text)
        # And the five that are left are what it holds.
        body["policy"] = {"capacity": 5}
        body["template_code"] = f"RB2-{suffix}"
        created = self.client.post(
            "/scheduling/templates", json={**body, **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["capacity_ceiling"], 5)
        # The retired row is also out of the room's own contents, which is what ADM-SCH-06
        # draws: a reader counting bikes on the screen counts the ones that work.
        contains = self.one(gym["tenant_id"], room)["contains"]
        self.assertEqual([c["resource_code"] for c in contains], [f"KEEP-{suffix}"])

    def test_the_live_check_reports_the_ceiling_and_does_not_refuse_it(self):
        """ADM-SCH-03's own half: "Studio 2 holds 20 bikes. Capacity cannot exceed the room".

        **Reported, not refused**, which is that canvas's rule -- "it warns, it does not
        block" -- and from `_ceiling_for`, the same function the write refuses by. A figure
        this read computed its own way would be a screen clearing a capacity the publish then
        rejected, which is this build's one-module-two-definitions finding pointed at a form.
        """
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        room = self.space(gym, f"LIVE-{suffix}", 20)
        asked = self.client.post("/scheduling/conflict-check", json={
            "location_id": gym["location_id"],
            "rule": {"frequency": "weekly", "local_time": "18:00",
                     "duration_minutes": 60, "starts_on": day(1), "until": day(60),
                     "weekdays": [BOOKABLE_WEEKDAY]},
            "policy": {"capacity": 30},
            "requirements": [
                {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
                {"kind": "room", "quantity": 1, "resource_id": room},
            ],
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(asked.status_code, 200, asked.text)
        body = asked.json()
        self.assertEqual(body["capacity_ceiling"], 20)
        self.assertEqual(body["ceiling_bound_by"], f"LIVE-{suffix}")
        self.assertEqual(body["ceiling_bound_kind"], "space")
        self.assertTrue(body["capacity_over_the_ceiling"])

    def test_the_live_check_and_the_write_agree_about_the_number(self):
        """The property the shared function exists for: whatever the check reports, the write
        accepts -- and one over it, the write refuses."""
        gym = self.gym()
        suffix = uuid.uuid4().hex[:6].upper()
        room = self.space(gym, f"AGR-{suffix}", 17)
        requirements = [
            {"kind": "service", "quantity": 1, "resource_id": gym["service"]},
            {"kind": "room", "quantity": 1, "resource_id": room},
        ]
        rule = {"frequency": "weekly", "local_time": "18:00", "duration_minutes": 60,
                "starts_on": day(1), "until": day(60), "weekdays": [BOOKABLE_WEEKDAY]}
        asked = self.client.post("/scheduling/conflict-check", json={
            "location_id": gym["location_id"], "rule": rule,
            "policy": {"capacity": 1}, "requirements": requirements,
            **self.correlation()}, headers=self.headers(gym["tenant_id"]))
        self.assertEqual(asked.status_code, 200, asked.text)
        ceiling = asked.json()["capacity_ceiling"]
        self.assertEqual(ceiling, 17)
        self.assertFalse(asked.json()["capacity_over_the_ceiling"])
        created = self.client.post("/scheduling/templates", json={
            "template_code": f"AG-{suffix}", "display_name": "At the ceiling",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"], "rule": rule,
            "policy": {"capacity": ceiling}, "requirements": requirements,
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(created.status_code, 201, created.text)
        refused = self.client.post("/scheduling/templates", json={
            "template_code": f"AG2-{suffix}", "display_name": "One over it",
            "service_resource_id": gym["service"],
            "location_id": gym["location_id"], "rule": rule,
            "policy": {"capacity": ceiling + 1}, "requirements": requirements,
            "restrictions": [], **self.correlation()},
            headers=self.headers(gym["tenant_id"]))
        self.assertEqual(refused.status_code, 422, refused.text)
