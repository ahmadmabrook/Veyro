"""MOD-027 slice 1 over HTTP: the gate, the mask, and the duplicate the design is built to stop.

**MOD-014's review found that no test had ever called a `/people` route successfully**, so the
gate return, the permission resolution and the actor lookup were exercised by nothing and four
findings passed a green suite. These are the assertions that need the request path.

The canvases state their own behaviour and those are what is asserted: "If this number already
existed, that record would open instead of a second one being created", "No contact 48h",
"interested in classes and PT", and "Age is the sortable column that matters".
"""

from __future__ import annotations

import pathlib
import re
import unittest
import uuid
from datetime import UTC, date, datetime, timedelta

from app.crm import pipeline
from app.crm import service as crm
from app.errors import InvalidRequest
from tests.support import GatedApiTestCase
from tests.test_access_api import AccessApiTestCase
from tests.test_commercial_api import TODAY, CommercialApiTestCase

READ = ["crm.lead.read", "crm.source.read"]
WRITE = ["crm.lead.write", "crm.touchpoint.write", "crm.source.write"]


class CrmApiTestCase(GatedApiTestCase):
    def scoped(self, tenant_id: str, permissions: list[str]) -> dict[str, str]:
        """Headers for a session holding exactly these permissions, at AAL 1."""
        return self.headers(tenant_id, self.grant(tenant_id, permissions))

    def person(self, tenant_id: str, name: str = "Rana Sabbagh") -> str:
        created = self.client.post("/people", json={
            "legal_name": name, "profile_kinds": ["lead"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["person_id"])

    def source(self, tenant_id: str, key: str = "") -> str:
        made = self.client.post("/crm/sources", json={
            "source_key": key or f"s{uuid.uuid4().hex[:8]}",
            "display_name": "Sweifieh open day", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return str(made.json()["source_id"])

    def lead(self, tenant_id: str, **over: object) -> dict:
        body: dict = {"person_id": self.person(tenant_id)}
        body.update(over)
        made = self.client.post("/crm/leads", json={**body, **self.correlation()},
                                headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return dict(made.json())

    def touch(self, tenant_id: str, lead_id: str, **over: object) -> dict:
        body: dict = {"kind": "call", "summary": "left a message"}
        body.update(over)
        made = self.client.post(
            f"/crm/leads/{lead_id}/touchpoints", json={**body, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return dict(made.json())


class RoutingTests(CrmApiTestCase):
    def test_the_board_is_reached_rather_than_the_lead_path_parameter(self):
        """**FastAPI matches in declaration order**, so a literal behind a path parameter is
        never reached: `/memberships/summary` was answered by `/memberships/{id}` and replied
        422. `/crm/board` sits beside `/crm/leads/{lead_id}`, so this is the assertion rather
        than a reading of the file."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        for path in ("/crm/board", "/crm/leads", "/crm/sources"):
            with self.subTest(path=path):
                answer = self.client.get(path, headers=owner)
                self.assertEqual(answer.status_code, 200, f"{path}: {answer.text}")


class LeadTests(CrmApiTestCase):
    def test_a_lead_opens_at_new_with_no_owner_and_no_next_action(self):
        """ADM-CRM-04: "Name and phone are enough. Everything else can wait." So an owner, a
        source and an interest are all optional and the board draws unclaimed leads."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        self.assertEqual(made["stage"], "new")
        self.assertFalse(made["existing"])
        read = self.client.get(
            f"/crm/leads/{made['lead_id']}", headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertIsNone(read.json()["owner_person_id"])
        self.assertIsNone(read.json()["next_action"])
        self.assertEqual(read.json()["interests"], [])

    def test_a_second_lead_for_one_person_returns_the_first(self):
        """**The duplicate the design is structured to stop.** ADM-CRM-04: "If this number
        already existed, that record would open instead of a second one being created." So
        there is no idempotency key -- the person is the key -- and a retried request, a second
        salesperson and a receptionist who did not look all get one record."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        first = self.lead(tenant_id, person_id=person_id)
        again = self.client.post("/crm/leads", json={
            "person_id": person_id, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["existing"])
        self.assertEqual(again.json()["lead_id"], first["lead_id"])

    def test_a_lead_for_a_person_nobody_created_is_refused(self):
        """`person_id` carries a foreign key, so an id nobody holds is 404 rather than a lead
        about nobody -- MOD-009's "a locator that exists is not a locator that matched"."""
        tenant_id = self.tenant()
        refused = self.client.post("/crm/leads", json={
            "person_id": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 404, refused.text)
        self.assertEqual(refused.json()["error"], "person_not_found")

    def test_the_lead_holds_no_name_number_or_address(self):
        """A lead is a `ppl_persons` row, so a name here would be the second copy MOD-013
        refuses to hold -- and it would be a copy a sales team edits. Asserted by field name
        rather than by value, because a field *called* `legal_name` is as much a leak as the
        name in it."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        read = self.client.get(
            f"/crm/leads/{made['lead_id']}", headers=self.headers(tenant_id)).json()
        for field in ("legal_name", "name", "phone", "email", "value_raw", "date_of_birth"):
            self.assertNotIn(field, read, f"{field} has no business in a lead")
        listed = self.client.get("/crm/leads", headers=self.headers(tenant_id)).json()
        self.assertIn("no_name_is_returned_here", listed)


class InterestTests(CrmApiTestCase):
    def test_a_set_is_recorded_and_read_back_in_the_vocabulary_order(self):
        """ADM-CRM-03 renders "interested in classes and PT", so the set is real."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id, interests=["pt", "classes"])
        self.assertEqual(made["interests"], ["classes", "pt"])
        read = self.client.get(
            f"/crm/leads/{made['lead_id']}", headers=self.headers(tenant_id)).json()
        self.assertEqual(read["interests"], ["classes", "pt"])

    def test_gym_only_is_not_combined_with_another_interest(self):
        tenant_id = self.tenant()
        refused = self.client.post("/crm/leads", json={
            "person_id": self.person(tenant_id), "interests": ["classes", "gym_only"],
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_the_pair_cannot_be_built_one_request_at_a_time(self):
        """**A control defeated by the order of two requests is not a control.** The second
        call is checked against what is already recorded, which is MOD-020's quota finding:
        a window that looks one way is defeated by the order of the requests."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id, interests=["gym_only"])
        refused = self.client.post(
            f"/crm/leads/{made['lead_id']}/interests",
            json={"interests": ["classes"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_adding_an_interest_twice_adds_nothing(self):
        tenant_id = self.tenant()
        made = self.lead(tenant_id, interests=["classes"])
        again = self.client.post(
            f"/crm/leads/{made['lead_id']}/interests",
            json={"interests": ["classes", "pt"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["added"], ["pt"])
        self.assertEqual(again.json()["interests"], ["classes", "pt"])


class StageTests(CrmApiTestCase):
    def test_a_call_moves_a_new_lead_to_contacted_in_one_transaction(self):
        """**The board counts what the timeline says.** A call that left the stage at `new`
        would make "Contacted · 9" a figure the profile contradicts."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        done = self.touch(tenant_id, made["lead_id"], kind="call")
        self.assertEqual(done["stage"], "contacted")
        self.assertTrue(done["stage_moved"])
        read = self.client.get(
            f"/crm/leads/{made['lead_id']}", headers=self.headers(tenant_id)).json()
        self.assertEqual(read["stage"], "contacted")
        self.assertEqual(read["touchpoint_count"], 1)

    def test_a_tour_reaches_toured_and_a_later_note_does_not_move_it_back(self):
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        self.assertEqual(self.touch(tenant_id, made["lead_id"], kind="tour")["stage"],
                         "toured")
        later = self.touch(tenant_id, made["lead_id"], kind="note", summary="left a voicemail")
        self.assertEqual(later["stage"], "toured")
        self.assertFalse(later["stage_moved"])

    def test_the_explicit_move_runs_forward_and_refuses_backwards(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        made = self.lead(tenant_id)
        forward = self.client.post(
            f"/crm/leads/{made['lead_id']}/stage",
            json={"to_stage": "contacted", **self.correlation()}, headers=owner)
        self.assertEqual(forward.status_code, 200, forward.text)
        back = self.client.post(
            f"/crm/leads/{made['lead_id']}/stage",
            json={"to_stage": "new", **self.correlation()}, headers=owner)
        self.assertEqual(back.status_code, 409, back.text)

    def test_a_stage_outside_the_vocabulary_is_refused_as_a_conflict_not_a_500(self):
        """`lost` is slice 3's and the derived columns are MOD-017's, so neither is a stage
        this command writes -- and the refusal is the pipeline's sentence rather than a CHECK
        violation leaking out as a 500."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        for stage in ("lost", "on_trial", "joined"):
            with self.subTest(stage=stage):
                refused = self.client.post(
                    f"/crm/leads/{made['lead_id']}/stage",
                    json={"to_stage": stage, **self.correlation()},
                    headers=self.headers(tenant_id))
                self.assertEqual(refused.status_code, 409, refused.text)

    def test_the_version_guards_a_concurrent_move(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        made = self.lead(tenant_id)
        read = self.client.get(f"/crm/leads/{made['lead_id']}", headers=owner).json()
        self.touch(tenant_id, made["lead_id"], kind="call")
        stale = self.client.post(
            f"/crm/leads/{made['lead_id']}/stage",
            json={"to_stage": "toured", "expected_version": read["version"],
                  **self.correlation()}, headers=owner)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["error"], "this_lead_changed_since_it_was_read")


class OwnershipTests(CrmApiTestCase):
    def test_claiming_a_lead_needs_a_person_record_and_says_so(self):
        """**Staff hold permissions and do not have to be anybody in particular.** The
        fixture's owner is nobody in this tenant, so `to_self` is refused with the reason
        rather than silently writing a null owner -- which would read as a release."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"to_self": True, **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"], "no_person_record_for_this_identity")

    def test_which_act_it_was_is_derived_from_what_the_column_held(self):
        """A caller cannot report a release and perform a handover -- MOD-026's rule, one
        module over."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        made = self.lead(tenant_id)
        yasmin = self.person(tenant_id, "Yasmin Khalil")
        nadia = self.person(tenant_id, "Nadia Faris")
        claimed = self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"owner_person_id": yasmin, **self.correlation()}, headers=owner)
        self.assertEqual(claimed.json()["act"], "claimed")
        handed = self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"owner_person_id": nadia, **self.correlation()}, headers=owner)
        self.assertEqual(handed.json()["act"], "handed_over")
        self.assertEqual(handed.json()["previous_owner_person_id"], yasmin)
        released = self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"release": True, **self.correlation()}, headers=owner)
        self.assertEqual(released.json()["act"], "released")
        self.assertIsNone(released.json()["owner_person_id"])

    def test_two_intents_at_once_are_refused(self):
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"owner_person_id": self.person(tenant_id), "release": True,
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_assigning_the_owner_it_already_has_is_refused(self):
        """A write that changes nothing would bump the version and read as a handover
        somebody made -- the "evidence with nobody's name on it" rule from the other side."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        made = self.lead(tenant_id)
        yasmin = self.person(tenant_id, "Yasmin Khalil")
        self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"owner_person_id": yasmin, **self.correlation()}, headers=owner)
        again = self.client.post(
            f"/crm/leads/{made['lead_id']}/assign",
            json={"owner_person_id": yasmin, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)


class NextActionTests(CrmApiTestCase):
    def test_both_halves_or_neither(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        made = self.lead(tenant_id)
        for body in ({"next_action": "call back"},
                     {"next_action_on": date.today().isoformat()}):
            with self.subTest(body=body):
                refused = self.client.post(
                    f"/crm/leads/{made['lead_id']}/next-action",
                    json={**body, **self.correlation()}, headers=owner)
                self.assertEqual(refused.status_code, 422, refused.text)

    def test_it_is_set_and_cleared(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        made = self.lead(tenant_id)
        when = (date.today() + timedelta(days=2)).isoformat()
        set_it = self.client.post(
            f"/crm/leads/{made['lead_id']}/next-action",
            json={"next_action": "call back about spin", "next_action_on": when,
                  **self.correlation()}, headers=owner)
        self.assertEqual(set_it.status_code, 200, set_it.text)
        self.assertEqual(set_it.json()["next_action_on"], when)
        cleared = self.client.post(
            f"/crm/leads/{made['lead_id']}/next-action",
            json={**self.correlation()}, headers=owner)
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["next_action"])


class ColdLeadTests(CrmApiTestCase):
    """The forty-eight-hour rule, asked from the future rather than written into the past.

    **No route takes an instant**, deliberately: a caller-supplied "now" would decide which
    leads a sales manager is told are going cold, which is MOD-011's unbounded `observed_at`
    finding one module over. And `crm_leads.created_at` is outside every runtime role's UPDATE
    grant -- age is the column ADM-CRM-02 says matters, and a lead whose age could be reset is
    a lead that never goes cold -- so the fixture cannot write it either.

    So these ask the service as of a later moment, which exercises the same expressions the
    route does, and the HTTP assertions below are the ones a request can make. MOD-020 split
    its settlement tests the same way and for the same reason.
    """

    def test_a_fresh_lead_is_warm_over_http_and_the_threshold_is_reported(self):
        tenant_id = self.tenant()
        self.lead(tenant_id)
        listed = self.client.get("/crm/leads", headers=self.headers(tenant_id)).json()
        self.assertFalse(listed["leads"][0]["going_cold"])
        self.assertEqual(listed["going_cold_after_hours"], 48)
        self.assertEqual(listed["leads"][0]["hours_since_contact"], 0)

    def test_an_untouched_lead_goes_cold_after_two_days(self):
        """The canvas's own example: "Rana Sabbagh NO CONTACT · 2 DAYS" beside "open day ·
        2d". Treating an untouched lead as warm would hide the ones the chip is for."""
        tenant_id = self.tenant()
        self.lead(tenant_id)
        soon = crm.list_leads(
            self._tenant_pool, tenant_id, at=datetime.now(UTC) + timedelta(hours=47))
        later = crm.list_leads(
            self._tenant_pool, tenant_id, at=datetime.now(UTC) + timedelta(hours=49))
        self.assertFalse(soon["leads"][0]["going_cold"])
        self.assertTrue(later["leads"][0]["going_cold"])

    def test_the_chip_filters_rather_than_flagging(self):
        """The same lead is in the filtered list after the threshold and not before it, which
        is the filter rather than the flag the test above asserts."""
        tenant_id = self.tenant()
        self.lead(tenant_id)
        before = crm.list_leads(
            self._tenant_pool, tenant_id, going_cold=True,
            at=datetime.now(UTC) + timedelta(hours=47))
        after = crm.list_leads(
            self._tenant_pool, tenant_id, going_cold=True,
            at=datetime.now(UTC) + timedelta(hours=49))
        self.assertEqual(before["leads"], [])
        self.assertEqual(len(after["leads"]), 1)

    def test_a_touchpoint_is_what_the_clock_reads_rather_than_the_created_date(self):
        """**The order has to disagree with the created order, or it proves nothing.**

        The lead touched here is the one created *first*, so by `created_at` it would come
        first and by last contact it comes last. The first version of this test touched the
        second lead, where the two sort keys agree -- and the mutation sweep reported the
        ordering as uncaught, which is exactly the "a case catches a weakening only if the
        weakened rule admits the row" rule applied to a sort.

        A touchpoint cannot be dated into the future -- the schema refuses it, because "no
        contact · 2 days" is counted from that column -- so this is the only way to separate
        the two clocks without waiting two days."""
        tenant_id = self.tenant()
        touched = self.lead(tenant_id)
        untouched = self.lead(tenant_id)
        self.touch(tenant_id, touched["lead_id"], kind="call")
        listed = self.client.get(
            "/crm/leads", headers=self.headers(tenant_id)).json()
        self.assertEqual(
            [r["lead_id"] for r in listed["leads"]],
            [untouched["lead_id"], touched["lead_id"]])
        self.assertIn("oldest contact first", listed["ordered_by"])
        by_id = {r["lead_id"]: r for r in listed["leads"]}
        self.assertIsNone(by_id[untouched["lead_id"]]["last_touch_at"])
        self.assertIsNotNone(by_id[touched["lead_id"]]["last_touch_at"])


class TouchpointTests(CrmApiTestCase):
    def test_a_touchpoint_in_the_future_is_refused(self):
        """"No contact · 2 days" is counted from `occurred_at`, so a touchpoint dated forward
        would make a cold lead read as warm. A bound against the server's clock rather than
        between two columns the same writer supplies -- MOD-021's finding."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{made['lead_id']}/touchpoints",
            json={"kind": "call", "summary": "spoke to her",
                  "occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_touchpoint_in_the_past_is_accepted(self):
        """A salesperson writes up Friday's open day on Monday."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        when = datetime.now(UTC) - timedelta(days=3)
        done = self.touch(
            tenant_id, made["lead_id"], kind="tour", occurred_at=when.isoformat())
        self.assertEqual(done["occurred_at"][:10], when.date().isoformat())

    def test_an_unknown_kind_is_refused(self):
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{made['lead_id']}/touchpoints",
            json={"kind": "carrier_pigeon", "summary": "sent a bird", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_the_timeline_is_newest_first(self):
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        self.touch(tenant_id, made["lead_id"], kind="note", summary="first",
                   occurred_at=(datetime.now(UTC) - timedelta(days=4)).isoformat())
        self.touch(tenant_id, made["lead_id"], kind="note", summary="second")
        read = self.client.get(
            f"/crm/leads/{made['lead_id']}", headers=self.headers(tenant_id)).json()
        self.assertEqual([t["summary"] for t in read["touchpoints"]], ["second", "first"])


class MaskTests(CrmApiTestCase):
    def test_a_summary_is_withheld_from_a_reader_who_cannot_write_one(self):
        """**A summary is where a health fact goes in practice**, which MOD-017 and MOD-019
        each paid for discovering. The mask is decided by the gate in the route, and it is
        worth something only because `crm.touchpoint.write` is separate from `crm.lead.read`:
        a mask keyed on the cheapest permission in a module masks nothing."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        self.touch(tenant_id, made["lead_id"], kind="note",
                   summary="she is having chemotherapy on Tuesdays")
        reader = self.scoped(tenant_id, ["crm.lead.read"])
        masked = self.client.get(f"/crm/leads/{made['lead_id']}", headers=reader).json()
        self.assertEqual(masked["touchpoints"][0]["summary"], "__withheld__")
        self.assertTrue(masked["touchpoints"][0]["summary_withheld"])
        # The entry stays visible: a timeline missing its rows reads as a lead nobody has
        # spoken to, which is the one reading that is always wrong here.
        self.assertEqual(masked["touchpoints"][0]["kind"], "note")

    def test_a_writer_reads_the_prose(self):
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        self.touch(tenant_id, made["lead_id"], kind="note", summary="asked twice about spin")
        writer = self.scoped(tenant_id, ["crm.lead.read", "crm.touchpoint.write"])
        read = self.client.get(f"/crm/leads/{made['lead_id']}", headers=writer).json()
        self.assertEqual(read["touchpoints"][0]["summary"], "asked twice about spin")
        self.assertFalse(read["touchpoints"][0]["summary_withheld"])


class SourceTests(CrmApiTestCase):
    def test_a_source_is_idempotent_on_its_key(self):
        tenant_id = self.tenant()
        first = self.client.post("/crm/sources", json={
            "source_key": "open_day", "display_name": "Sweifieh open day",
            **self.correlation()}, headers=self.headers(tenant_id))
        again = self.client.post("/crm/sources", json={
            "source_key": "open_day", "display_name": "Something else",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["source_id"], first.json()["source_id"])
        self.assertEqual(again.json()["display_name"], "Sweifieh open day")

    def test_a_retired_source_leaves_the_dropdown_and_keeps_its_leads(self):
        """Retired, not deleted: ADM-RPT-03 groups conversions by source and reads the
        history, so a club that ran one open day in March still ran it."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        source_id = self.source(tenant_id)
        made = self.lead(tenant_id, source_id=source_id)
        gone = self.client.post(f"/crm/sources/{source_id}/retire", json={
            "reason": "we do not run it any more", **self.correlation()}, headers=owner)
        self.assertEqual(gone.status_code, 200, gone.text)
        live = self.client.get("/crm/sources", headers=owner).json()
        self.assertEqual(live["sources"], [])
        all_of_them = self.client.get(
            "/crm/sources?include_retired=true", headers=owner).json()
        self.assertEqual(len(all_of_them["sources"]), 1)
        read = self.client.get(f"/crm/leads/{made['lead_id']}", headers=owner).json()
        self.assertEqual(read["source"], "Sweifieh open day")

    def test_retiring_twice_is_refused(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        source_id = self.source(tenant_id)
        body = {"reason": "no longer run", **self.correlation()}
        self.client.post(f"/crm/sources/{source_id}/retire", json=body, headers=owner)
        again = self.client.post(
            f"/crm/sources/{source_id}/retire", json=body, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)


class BoardTests(CrmApiTestCase):
    def test_the_board_draws_five_columns_and_counts_three(self):
        """ADM-CRM-01's five columns. The last two are derived from MOD-017 and are zero here
        because none of these leads has a membership -- `TrialColumnTests` below is where the
        derivation is exercised."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        new = self.lead(tenant_id)
        contacted = self.lead(tenant_id)
        self.touch(tenant_id, contacted["lead_id"], kind="call")
        toured = self.lead(tenant_id)
        self.touch(tenant_id, toured["lead_id"], kind="tour")
        board = self.client.get("/crm/board", headers=owner).json()
        counts = {c["stage"]: c["count"] for c in board["columns"]}
        self.assertEqual(
            list(counts), ["new", "contacted", "toured", "on_trial", "joined"])
        self.assertEqual((counts["new"], counts["contacted"], counts["toured"]), (1, 1, 1))
        self.assertEqual((counts["on_trial"], counts["joined"]), (0, 0))
        self.assertEqual(board["open_leads"], 3)
        self.assertIn("the_last_two_columns_are_derived", board)
        del new

    def test_mine_is_zero_without_a_person_record_and_says_so(self):
        tenant_id = self.tenant()
        self.lead(tenant_id)
        board = self.client.get("/crm/board?mine=true", headers=self.headers(tenant_id))
        self.assertEqual(board.status_code, 200, board.text)
        self.assertEqual(board.json()["open_leads"], 0)
        self.assertIn("mine_is_zero_without_a_person_record", board.json())
        listed = self.client.get("/crm/leads?mine=true", headers=self.headers(tenant_id))
        self.assertEqual(listed.json()["leads"], [])
        self.assertIn("mine_is_zero_without_a_person_record", listed.json())


class FilterTests(CrmApiTestCase):
    def test_a_stage_outside_the_vocabulary_is_refused_rather_than_answered_empty(self):
        """"This tenant has no toured leads" and "that is not a stage" are different answers,
        and a list that rendered both as an empty table is one nobody can trust."""
        tenant_id = self.tenant()
        refused = self.client.get(
            "/crm/leads?stage=lost", headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_unowned_and_one_owners_leads_are_not_asked_for_together(self):
        tenant_id = self.tenant()
        refused = self.client.get(
            f"/crm/leads?unowned=true&owner_person_id={uuid.uuid4()}",
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_the_page_is_bounded(self):
        tenant_id = self.tenant()
        refused = self.client.get("/crm/leads?limit=500", headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)


if __name__ == "__main__":
    unittest.main()


class TrialColumnTests(CrmApiTestCase, CommercialApiTestCase):
    """ADM-CRM-01's last two columns, which MOD-017 answers.

    **Two test cases joined rather than a helper copied.** Building a trial means a product, a
    price book, a published price, a contract version, membership terms, an agreement, a
    signature and an activation -- eight calls that `CommercialApiTestCase` already makes, and
    a second copy of them here would be two definitions of "a live membership". The MRO puts
    the CRM helpers first, so `person` is the lead-shaped one.
    """

    def board_counts(self, tenant_id: str) -> dict[str, int]:
        board = self.client.get("/crm/board", headers=self.headers(tenant_id)).json()
        return {c["stage"]: c["count"] for c in board["columns"]}

    def lead_for(self, tenant_id: str, person_id: str) -> dict:
        made = self.client.post("/crm/leads", json={
            "person_id": person_id, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return dict(made.json())

    def test_a_lead_on_a_trial_product_is_counted_on_trial(self):
        tenant_id = self.tenant()
        live = self.membership(
            tenant_id, starts_on=TODAY.isoformat(), terms_extra={"trial_days": 7})
        self.lead_for(tenant_id, live["person_id"])
        counts = self.board_counts(tenant_id)
        self.assertEqual(counts["on_trial"], 1)
        self.assertEqual(counts["joined"], 0)
        self.assertEqual(counts["new"], 0)

    def test_a_lead_with_an_ordinary_membership_is_counted_joined(self):
        """The other side of the same derivation, which an `on_trial`-only test cannot see: a
        rule that counted every active membership as a trial would pass that one."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, starts_on=TODAY.isoformat())
        self.lead_for(tenant_id, live["person_id"])
        counts = self.board_counts(tenant_id)
        self.assertEqual(counts["joined"], 1)
        self.assertEqual(counts["on_trial"], 0)

    def test_a_trial_that_has_run_out_is_in_neither_column(self):
        """**Live by the dates rather than the cached status**, which is MOD-022's own rule for
        a door: the membership still says `active` and its window has closed, so the lead is
        back in its sales stage. That is what ADM-CRM-07's "trial lapsed" is about, and a read
        that trusted the status cache would leave somebody on trial for ever."""
        tenant_id = self.tenant()
        live = self.membership(
            tenant_id, starts_on=(TODAY - timedelta(days=30)).isoformat(),
            terms_extra={"trial_days": 7})
        self.assertEqual(live["ends_on"], (TODAY - timedelta(days=24)).isoformat())
        self.lead_for(tenant_id, live["person_id"])
        counts = self.board_counts(tenant_id)
        self.assertEqual((counts["on_trial"], counts["joined"]), (0, 0))
        self.assertEqual(counts["new"], 1)

    def test_a_converted_trial_reads_as_joined_rather_than_on_trial(self):
        """**The chain, which is the whole reason this read walks it.**
        `mem_memberships.agreement_id` is the chain's root and immutable by grant, so a member
        who converted by superseding the trial's agreement still *points at* the trial -- and a
        read that stopped at the root would leave every converted member in the "On trial"
        column for ever. The successor is on an ordinary product, so the standing moves."""
        tenant_id = self.tenant()
        live = self.membership(
            tenant_id, starts_on=TODAY.isoformat(), terms_extra={"trial_days": 7})
        self.lead_for(tenant_id, live["person_id"])
        self.assertEqual(self.board_counts(tenant_id)["on_trial"], 1)
        # A successor on its own contract and its own product, which is what a conversion is.
        self.supersede(tenant_id, live, amount_minor=5500,
                       contract={"contract_key": f"c{uuid.uuid4().hex[:8]}"},
                       starts_on=TODAY.isoformat())
        counts = self.board_counts(tenant_id)
        self.assertEqual(counts["joined"], 1)
        self.assertEqual(counts["on_trial"], 0)

    def test_a_conversion_does_not_leave_the_membership_ending_at_the_trial(self):
        """**The defect a trial created and `change_membership_plan` did not know about.** The
        plan change writes a superseding agreement and moved no date, so a conversion left
        `ends_on` at the trial's end -- and MOD-022 reads the dates while
        `memberships.revoke_ended_grants` sweeps on that column, so the member's door would
        have stopped and their entitlements been revoked a few days after they paid. Asserted
        at a moment past the old end, which is the only place the bug is visible."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(
            tenant_id, starts_on=TODAY.isoformat(), terms_extra={"trial_days": 7})
        self.assertEqual(live["ends_on"], (TODAY + timedelta(days=6)).isoformat())
        self.lead_for(tenant_id, live["person_id"])
        # **Through `plan-change`, which is what a conversion is.** `supersede` alone writes
        # the agreement and records no lifecycle change, which is the other half of this and
        # the gap named below.
        target = self.supersede(
            tenant_id, live, amount_minor=9000, sign=False,
            contract={"contract_key": f"c{uuid.uuid4().hex[:8]}"},
            starts_on=TODAY.isoformat())
        quote = self.client.get(
            f"/memberships/{live['membership_id']}/plan-change-preview"
            f"?to_agreement_id={target}", headers=owner)
        self.assertEqual(quote.status_code, 200, quote.text)
        done = self.client.post(
            f"/memberships/{live['membership_id']}/plan-change", json={
                "to_agreement_id": target, "reason": "converting the trial",
                "signature_kind": "click_through",
                "signature_evidence_ref": "s3://signatures/convert",
                "acknowledged_due_minor": quote.json()["due_minor"],
                "idempotency_key": f"cv-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertIsNone(done.json()["ends_on"], done.text)
        self.assertFalse(done.json()["ends_on_follows_at_the_effective_date"])
        after = self.client.get(
            f"/memberships/{live['membership_id']}", headers=owner)
        self.assertEqual(after.status_code, 200, after.text)
        self.assertIsNone(after.json()["ends_on"], after.text)
        # And a month later they are still a member rather than nobody.
        board = crm.board(self._tenant_pool, tenant_id,
                          at=datetime.combine(TODAY + timedelta(days=30),
                                              datetime.min.time(), tzinfo=UTC))
        counts = {c["stage"]: c["count"] for c in board["columns"]}
        self.assertEqual(counts["joined"], 1)
        self.assertEqual(counts["on_trial"], 0)

    def test_the_table_and_the_board_agree_about_where_a_person_is(self):
        """**Two views of one list, and they disagreed.** The board derived "On trial" from
        MOD-017 and `list_leads` returned the stored sales stage, so ADM-CRM-02's STAGE column
        would have read "New" for somebody the board put in "On trial" -- MOD-018's
        one-module-two-definitions finding across two screens rather than two functions. The
        row carries both now: `stage` is what the filter takes and `board_stage` is where the
        person is."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(
            tenant_id, starts_on=TODAY.isoformat(), terms_extra={"trial_days": 7})
        self.lead_for(tenant_id, live["person_id"])
        listed = self.client.get("/crm/leads", headers=owner).json()
        self.assertEqual(len(listed["leads"]), 1, listed)
        row = listed["leads"][0]
        self.assertEqual(row["stage"], "new")
        self.assertEqual(row["board_stage"], "on_trial")
        self.assertEqual(self.board_counts(tenant_id)["on_trial"], 1)
        # And a member is not a lead going cold, which the board's own count already said.
        self.assertFalse(row["going_cold"])

    def test_a_superseding_agreement_alone_leaves_the_end_date_where_it_was(self):
        """**The gap, asserted rather than left to be found.** There are two ways to supersede:
        `plan-change`, which records a lifecycle change and moves `ends_on`, and
        `POST /memberships/agreements` with `supersedes_agreement_id`, which writes the
        agreement and nothing else. After the second the chain says one thing and the cached
        end date says another -- so the board follows the new product while the door still
        expires on the old one. Closing it means either a lifecycle change on that route or an
        `ends_on` the door derives, and both are decisions rather than fixes."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(
            tenant_id, starts_on=TODAY.isoformat(), terms_extra={"trial_days": 7})
        self.supersede(tenant_id, live, amount_minor=5500,
                       contract={"contract_key": f"c{uuid.uuid4().hex[:8]}"},
                       starts_on=TODAY.isoformat())
        after = self.client.get(
            f"/memberships/{live['membership_id']}", headers=owner)
        self.assertEqual(after.json()["ends_on"], (TODAY + timedelta(days=6)).isoformat())

    def test_a_membership_outranks_a_trial_where_somebody_has_both(self):
        """Having a real membership is the later and stronger fact, and the board's columns are
        stages rather than tags -- so one person is in one of them."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        self.membership_for(tenant_id, person_id, trial=True)
        self.membership_for(tenant_id, person_id, trial=False)
        self.lead_for(tenant_id, person_id)
        counts = self.board_counts(tenant_id)
        self.assertEqual(counts["joined"], 1)
        self.assertEqual(counts["on_trial"], 0)

    def test_a_trial_that_has_not_started_is_in_neither_column(self):
        """The other end of the window. A trial sold today to start next Monday is not one
        somebody is on, and a read bounded on one side only would put them on the board a week
        early -- which is the same one-sided bound this repository has found in a CHECK three
        times."""
        tenant_id = self.tenant()
        live = self.membership(
            tenant_id, starts_on=(TODAY + timedelta(days=7)).isoformat(),
            terms_extra={"trial_days": 7})
        self.lead_for(tenant_id, live["person_id"])
        counts = self.board_counts(tenant_id)
        self.assertEqual((counts["on_trial"], counts["joined"]), (0, 0))
        self.assertEqual(counts["new"], 1)

    def test_a_cancelled_membership_is_in_neither_column(self):
        """**The status half of "live", which the two date cases cannot see.** A membership
        cancelled with immediate effect is inside its own window and is not one anybody holds,
        so a read bounded only by the dates would keep showing them as joined."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(
            tenant_id, starts_on=(TODAY - timedelta(days=30)).isoformat(),
            contract={"notice_days": 0, "cancellation_mode": "immediate"})
        self.lead_for(tenant_id, live["person_id"])
        self.assertEqual(self.board_counts(tenant_id)["joined"], 1)
        cancelled = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "idempotency_key": "c-now",
                **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertTrue(cancelled.json()["takes_effect_immediately"])
        counts = self.board_counts(tenant_id)
        self.assertEqual((counts["on_trial"], counts["joined"]), (0, 0))

    def membership_for(self, tenant_id: str, person_id: str, *, trial: bool) -> str:
        """A live membership for a person who already exists, which `membership` cannot do."""
        owner = self.headers(tenant_id)
        contract_key = self.contract(tenant_id)
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, contract_key, product_id,
                              **({"trial_days": 7} if trial else {}))
        agreement = self.client.post("/memberships/agreements", json={
            "person_id": person_id, "membership_terms_id": terms_id,
            "variant_id": variant_id, "amount_minor": 4500, "currency": "JOD",
            "starts_on": TODAY.isoformat(), **self.correlation()}, headers=owner)
        self.assertEqual(agreement.status_code, 201, agreement.text)
        agreement_id = str(agreement.json()["agreement_id"])
        signed = self.client.post(
            f"/memberships/agreements/{agreement_id}/sign", json={
                "signature_kind": "click_through",
                "signature_evidence_ref": f"s3://signatures/{agreement_id}",
                "signed_by_person_id": person_id, **self.correlation()}, headers=owner)
        self.assertEqual(signed.status_code, 200, signed.text)
        active = self.client.post("/memberships", json={
            "agreement_id": agreement_id,
            "membership_number": f"M{uuid.uuid4().hex[:8].upper()}",
            "idempotency_key": f"act-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(active.status_code, 201, active.text)
        return str(active.json()["membership_id"])


class TrialCardTests(CrmApiTestCase, CommercialApiTestCase, AccessApiTestCase):
    """ADM-CRM-05's card, composed from three modules in one transaction.

    **Three test cases joined rather than three helpers copied.** A trial card needs a live
    trial membership (eight calls), an entry event (a location, a live device, a zone, a point,
    a policy and a credential) and an attended booking -- all of which already have fixtures,
    and a second copy of any of them would be a second definition of a live membership or of a
    visit. The MRO puts the CRM helpers first, so `person` is the lead-shaped one and `floor`
    builds its door around a person this class names.
    """

    def trialist(self, tenant_id: str, *, days: int = 7, back: int = 5) -> dict:
        """A lead who is on day `back + 1` of a `days`-day trial."""
        live = self.membership(
            tenant_id, starts_on=(TODAY - timedelta(days=back)).isoformat(),
            terms_extra={"trial_days": days})
        made = self.client.post("/crm/leads", json={
            "person_id": live["person_id"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return {**live, "lead_id": str(made.json()["lead_id"])}

    def door_for(self, tenant_id: str, person_id: str) -> dict:
        """A live door and a credential for a person who already exists.

        **`location` and `policy` are called unbound, because three of these harnesses define
        each name.** Joining test cases resolves a colliding helper by MRO, silently, to
        whichever base comes first -- and the two `location` helpers build different things
        while the two `publisher` helpers returned different *types*, so the first symptom was
        a 401 from a session created a line earlier. There is no type error to catch it: both
        are methods on `self` taking a tenant id.
        """
        location_id = AccessApiTestCase.location(self, tenant_id)
        device_id = self.live_device(tenant_id, location_id)
        zone_id = self.zone(tenant_id, location_id)
        point_id = self.point(tenant_id, zone_id, device_id)
        AccessApiTestCase.policy(self, tenant_id, zone_id)
        credential_id, value = self.credential(tenant_id, person_id)
        del credential_id
        return {"tenant_id": tenant_id, "point_id": point_id,
                "credential_value": value, "person_id": person_id}

    def entry(self, door: dict, *, when: datetime) -> None:
        """One entry event through that door.

        Inlined rather than inherited: `AccessApiTestCase`'s own `entry` is defined on a test
        class inside that module rather than on the harness, so it is not available here.
        """
        recorded = self.client.post("/access/events", json={
            "point_id": door["point_id"], "direction": "entry",
            "credential_value": door["credential_value"],
            "occurred_at": when.isoformat(), "source": "online",
            "idempotency_key": str(uuid.uuid4()), **self.correlation()},
            headers=self.headers(door["tenant_id"]))
        self.assertEqual(recorded.status_code, 201, recorded.text)

    def card(self, tenant_id: str, lead_id: str) -> dict:
        read = self.client.get(
            f"/crm/leads/{lead_id}/trial", headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        return dict(read.json())

    def test_the_canvas_s_figures_come_back_for_a_running_trial(self):
        """A seven-day trial on its sixth day: `DAY 6 OF 7`, `2 DAYS LEFT`, ending tomorrow.

        **All of them from one read**, because every figure is an arithmetic over today and a
        browser comparing dates against its own clock counts in the wrong frame -- which this
        build has three recorded defects from.
        """
        tenant_id = self.tenant()
        live = self.trialist(tenant_id, days=7, back=5)
        body = self.card(tenant_id, live["lead_id"])
        self.assertTrue(body["on_trial"])
        self.assertEqual(body["day_of"], 6)
        self.assertEqual(body["of_days"], 7)
        self.assertEqual(body["days_left"], 2)
        self.assertTrue(body["ends_tomorrow"])
        self.assertEqual(body["trial_days"], 7)
        self.assertEqual(body["membership_id"], live["membership_id"])

    def test_nobody_having_been_in_is_its_own_band_rather_than_zero(self):
        """"Nobody has been in" is a different conversation from "they came once", so the
        band is `none` and the counts are honest zeros."""
        tenant_id = self.tenant()
        live = self.trialist(tenant_id)
        body = self.card(tenant_id, live["lead_id"])
        self.assertEqual((body["visits"], body["classes"]), (0, 0))
        self.assertEqual(body["engagement"], "none")

    def test_a_visit_is_counted_and_reads_as_use_rather_than_a_prediction(self):
        """Four visits in six days is 0.67 a day, which is the canvas's `High ENGAGEMENT`.

        **And the response says it is use, not likelihood.** The prototype calls this cell
        conversion likelihood; the drawn canvas says ENGAGEMENT, and a prediction about a
        person is what MOD-020 refuses outright for the no-show score.
        """
        tenant_id = self.tenant()
        live = self.trialist(tenant_id, days=7, back=5)
        door = self.door_for(tenant_id, live["person_id"])
        for back in (0, 1, 3, 4):
            self.entry(door, when=datetime.now(UTC) - timedelta(days=back))
        body = self.card(tenant_id, live["lead_id"])
        self.assertEqual(body["visits"], 4, body)
        self.assertEqual(body["engagement"], "high", body)
        self.assertIn("engagement_is_use_not_a_prediction", body)

    def test_a_visit_before_the_trial_started_is_not_counted(self):
        """**The window is the trial's own**, which is what makes "4 VISITS" a figure about
        the trial rather than about the member: `entries_in_window` beside it is the habit and
        would count visits from before they ever took one."""
        tenant_id = self.tenant()
        live = self.trialist(tenant_id, days=7, back=2)
        door = self.door_for(tenant_id, live["person_id"])
        self.entry(door, when=datetime.now(UTC) - timedelta(days=1))
        self.entry(door, when=datetime.now(UTC) - timedelta(days=20))
        body = self.card(tenant_id, live["lead_id"])
        self.assertEqual(body["visits"], 1, body)

    def test_a_lead_with_no_trial_gets_a_reason_rather_than_four_zeros(self):
        """A lead with no trial is the ordinary case -- three of the five board columns -- so
        the read says so and the profile draws its own state. Four zeros would be MOD-014's
        "a confident wrong answer where a missing one would have been honest"."""
        tenant_id = self.tenant()
        made = self.lead(tenant_id)
        body = self.card(tenant_id, made["lead_id"])
        self.assertFalse(body["on_trial"])
        self.assertIn("not_on_a_trial", body)
        self.assertNotIn("day_of", body)

    def test_a_lapsed_trial_is_not_a_running_one(self):
        """The membership still says `active` and its window has closed, so the card is gone
        -- which is what ADM-CRM-07's "trial lapsed" is about."""
        tenant_id = self.tenant()
        live = self.trialist(tenant_id, days=7, back=30)
        body = self.card(tenant_id, live["lead_id"])
        self.assertFalse(body["on_trial"], body)

    ALL_FOUR = ["crm.lead.read", "access.decision.read", "booking.booking.read",
                "membership.record.read"]

    def test_the_card_charges_all_four_permissions(self):
        """**Four modules' facts, so four permissions.** A reader holding only the lead read
        would otherwise get MOD-022's visits, MOD-020's classes and MOD-017's membership window
        out of a CRM route, which is MOD-010's `events.event.read` finding.

        **This asserted three and `membership.record.read` was the one missing.** The card
        returns a membership id, a start, an end and the terms' `trial_days`, which is verbatim
        what that permission is described as granting -- so the route was a sales permission
        reaching a membership row, and the test said so was correct. Each subset here is every
        way to hold three of the four, so the case for each permission is its own.
        """
        tenant_id = self.tenant()
        live = self.trialist(tenant_id)
        for dropped in self.ALL_FOUR:
            held = [p for p in self.ALL_FOUR if p != dropped]
            with self.subTest(without=dropped):
                answer = self.client.get(
                    f"/crm/leads/{live['lead_id']}/trial",
                    headers=self.scoped(tenant_id, held))
                self.assertEqual(answer.status_code, 403, answer.text)
        allowed = self.client.get(
            f"/crm/leads/{live['lead_id']}/trial",
            headers=self.scoped(tenant_id, self.ALL_FOUR))
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_an_unknown_lead_is_a_404_and_a_malformed_id_is_a_422(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.get(
            f"/crm/leads/{uuid.uuid4()}/trial", headers=owner).status_code, 404)
        self.assertEqual(self.client.get(
            "/crm/leads/not-a-uuid/trial", headers=owner).status_code, 422)


class LostLeadTests(CrmApiTestCase):
    """ADM-CRM-07: why did this person not join, and what happens to the record.

    **The one thing every case here rests on is that the stage does not move** (ADR-0010 D8).
    A sixth stage value would need a backwards edge on reopen, which D3 rules out because it
    would make `Toured · 6` a count nobody can reconstruct.
    """

    def toured(self, tenant_id: str) -> dict:
        """A lead who has been contacted and toured, so the stage is worth preserving."""
        lead = self.lead(tenant_id)
        for stage in ("contacted", "toured"):
            moved = self.client.post(
                f"/crm/leads/{lead['lead_id']}/stage",
                json={"to_stage": stage, **self.correlation()},
                headers=self.headers(tenant_id))
            self.assertEqual(moved.status_code, 200, moved.text)
        return lead

    def lose(self, tenant_id: str, lead_id: str, **kwargs) -> dict:
        body = {"reason": "too_expensive", **self.correlation()}
        body.update(kwargs)
        answer = self.client.post(
            f"/crm/leads/{lead_id}/lost", json=body, headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 200, answer.text)
        return dict(answer.json())

    def test_the_stage_does_not_move_and_the_read_says_so(self) -> None:
        tenant_id = self.tenant()
        lead = self.toured(tenant_id)
        lost = self.lose(tenant_id, lead["lead_id"],
                         reason="joined_elsewhere",
                         detail="he joined the one on Mecca Street")
        self.assertEqual(lost["stage"], "toured")
        self.assertTrue(lost["stage_did_not_move"])
        read = self.client.get(
            f"/crm/leads/{lead['lead_id']}", headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        self.assertEqual(body["stage"], "toured")
        self.assertTrue(body["lost"])
        self.assertEqual(body["lost_reason"], "joined_elsewhere")
        self.assertEqual(body["lost_detail"], "he joined the one on Mecca Street")

    def test_the_loss_is_in_the_timeline_as_well_as_on_the_row(self) -> None:
        """ADR-0010 D4: "the history is the touchpoint timeline rather than a chain of
        records". The row keeps the latest loss; the timeline keeps that it happened, which is
        what makes a lead lost twice for two reasons answerable at all."""
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        before = self.client.get(
            f"/crm/leads/{lead['lead_id']}", headers=self.headers(tenant_id)).json()
        self.lose(tenant_id, lead["lead_id"], reason="location_or_hours")
        after = self.client.get(
            f"/crm/leads/{lead['lead_id']}", headers=self.headers(tenant_id)).json()
        self.assertEqual(after["touchpoint_count"], before["touchpoint_count"] + 1)
        self.assertIn("location_or_hours", after["touchpoints"][0]["summary"])

    def test_losing_a_lead_twice_is_refused_rather_than_re_dated(self) -> None:
        """The second call would move when they said no and drop the first reason from the row
        with nothing to say it had been there."""
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        self.lose(tenant_id, lead["lead_id"])
        again = self.client.post(
            f"/crm/leads/{lead['lead_id']}/lost",
            json={"reason": "no_longer_responding", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["error"], "this_lead_is_already_lost")

    def test_reopening_resumes_the_stage_and_is_not_gated_on_ninety_days(self) -> None:
        """ADR-0010 D10. A lead marked lost by mistake has to be correctable now, not in a
        quarter -- locking it would be MOD-013's rule on a routine permission."""
        tenant_id = self.tenant()
        lead = self.toured(tenant_id)
        self.lose(tenant_id, lead["lead_id"])
        reopened = self.client.post(
            f"/crm/leads/{lead['lead_id']}/reopen",
            json=self.correlation(), headers=self.headers(tenant_id))
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertFalse(reopened.json()["lost"])
        self.assertEqual(reopened.json()["stage"], "toured")
        self.assertEqual(reopened.json()["was_lost_for"], "too_expensive")
        read = self.client.get(
            f"/crm/leads/{lead['lead_id']}", headers=self.headers(tenant_id)).json()
        self.assertFalse(read["lost"])
        self.assertIsNone(read["lost_reason"])
        self.assertEqual(read["stage"], "toured")

    def test_reopening_a_live_lead_is_refused(self) -> None:
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{lead['lead_id']}/reopen",
            json=self.correlation(), headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["error"], "this_lead_is_not_lost")

    def test_a_lost_lead_is_off_the_board_and_out_of_the_default_list(self) -> None:
        """ADM-CRM-01 draws five columns and no sixth, and ADM-CRM-07 is a side sheet."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        lead = self.toured(tenant_id)
        before = self.client.get("/crm/board", headers=owner)
        self.assertEqual(before.status_code, 200, before.text)
        toured_before = next(c["count"] for c in before.json()["columns"]
                             if c["stage"] == "toured")
        self.lose(tenant_id, lead["lead_id"])

        # **The board answers counts, not cards** -- the cards are `/crm/leads`, which the
        # surface fetches alongside. So the assertion is the count for the column this lead
        # was in, before and after: a lost lead leaving the board is a chip going down by one.
        after = self.client.get("/crm/board", headers=owner)
        self.assertEqual(after.status_code, 200, after.text)
        toured_now = next(c["count"] for c in after.json()["columns"]
                          if c["stage"] == "toured")
        self.assertEqual(toured_now, toured_before - 1)

        live = self.client.get("/crm/leads", headers=owner)
        self.assertNotIn(lead["lead_id"], [r["lead_id"] for r in live.json()["leads"]])

        lost = self.client.get("/crm/leads", params={"lost": "true"}, headers=owner)
        self.assertEqual(lost.status_code, 200, lost.text)
        rows = {r["lead_id"]: r for r in lost.json()["leads"]}
        self.assertIn(lead["lead_id"], rows)
        self.assertEqual(rows[lead["lead_id"]]["lost_reason"], "too_expensive")
        self.assertEqual(rows[lead["lead_id"]]["stage"], "toured")

    def test_a_lost_lead_is_not_a_lead_going_cold(self) -> None:
        """Nobody has failed to ring them: they said no, and the reason is on the record.
        Counting them would put every refusal into the one chip that exists to surface a lead
        somebody has forgotten."""
        #
        # **Asked from a later moment, because a lead created a second ago is not cold
        # either.** The first version read the listing now and asserted `going_cold` is
        # false -- which it was, for the wrong reason, and the mutation that deletes the
        # guard came back uncaught. The pair is what makes it evidence: at the same age, a
        # live lead *is* cold.
        tenant_id = self.tenant()
        live = self.lead(tenant_id)
        lost = self.lead(tenant_id)
        self.lose(tenant_id, lost["lead_id"])
        later = datetime.now(UTC) + timedelta(hours=49)

        cold = crm.list_leads(self._tenant_pool, tenant_id, at=later)["leads"]
        self.assertTrue(
            next(r for r in cold if r["lead_id"] == live["lead_id"])["going_cold"])

        refused = crm.list_leads(
            self._tenant_pool, tenant_id, lost=True, at=later)["leads"]
        self.assertFalse(
            next(r for r in refused if r["lead_id"] == lost["lead_id"])["going_cold"])

    def test_an_unknown_reason_is_a_422_at_the_boundary(self) -> None:
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{lead['lead_id']}/lost",
            json={"reason": "changed_their_mind", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_the_four_reasons_agree_in_three_places(self) -> None:
        """**The Python set, the request body's `Literal` and the migration's CHECK.** MOD-026
        shipped a state machine whose two encodings agreed with each other and with neither
        the service nor the trigger; a regex over the migration is what makes that drift fail
        in CI rather than at the next sweep."""
        sql = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "tenant"
               / "0030_a_lost_lead_and_its_reason.sql").read_text()
        found = re.search(
            r"crm_leads_lost_reason\s*\n?\s*CHECK \(lost_reason IS NULL OR lost_reason IN \("
            r"(?P<body>.*?)\)\)", sql, re.S)
        self.assertIsNotNone(found, "the reason CHECK is not where this test looks")
        assert found is not None
        in_sql = tuple(sorted(re.findall(r"'([a-z_]+)'", found.group("body"))))
        self.assertEqual(in_sql, tuple(sorted(pipeline.LOST_REASONS)))

    def test_an_interest_can_be_withdrawn_and_asked_for_again(self) -> None:
        """ADR-0010 D11, which `0027` said slice 3 owed: until this existed, an interest
        recorded by mistake had no remedy anywhere in the product."""
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        owner = self.headers(tenant_id)
        recorded = self.client.post(
            f"/crm/leads/{lead['lead_id']}/interests",
            json={"interests": ["classes", "pt"], **self.correlation()}, headers=owner)
        self.assertEqual(recorded.status_code, 200, recorded.text)

        taken = self.client.post(
            f"/crm/leads/{lead['lead_id']}/interests/withdraw",
            json={"interest": "pt", **self.correlation()}, headers=owner)
        self.assertEqual(taken.status_code, 200, taken.text)
        self.assertTrue(taken.json()["withdrawn"])

        read = self.client.get(f"/crm/leads/{lead['lead_id']}", headers=owner).json()
        self.assertEqual(read["interests"], ["classes"])

        # **And it can be asked for again**, which the total key `0027` wrote would have
        # refused for ever: the uniqueness is partial on live rows.
        again = self.client.post(
            f"/crm/leads/{lead['lead_id']}/interests",
            json={"interests": ["classes", "pt"], **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        back = self.client.get(f"/crm/leads/{lead['lead_id']}", headers=owner).json()
        self.assertEqual(sorted(back["interests"]), ["classes", "pt"])

    def test_withdrawing_an_interest_nobody_holds_is_a_404(self) -> None:
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        refused = self.client.post(
            f"/crm/leads/{lead['lead_id']}/interests/withdraw",
            json={"interest": "gym_only", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 404, refused.text)

    def test_the_service_refuses_an_unknown_reason_as_well_as_the_route(self) -> None:
        """**The `Literal` is the boundary and `check_lost_reason` is the layer behind it.**
        The route refuses first, so this is the only thing that proves the service does too --
        and a service whose own vocabulary check is unreachable is a check nobody has tested,
        which is this build's recurring finding about defence in depth.
        """
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        # **The message, not the type.** With the service's own check gone the reason reaches
        # the CHECK, which raises `CheckViolation`, which the handler turns into the same
        # `InvalidRequest` -- so asserting the type proved nothing and the mutation that
        # disables the check came back uncaught. What differs is what the caller is told: the
        # four reasons, or the name of a constraint they cannot look up.
        with self.assertRaises(InvalidRequest) as refused:
            crm.mark_lead_lost(
                self._tenant_pool, tenant_id, lead["lead_id"],
                reason="changed_their_mind", detail=None,
                actor_id="33333333-3333-4333-8333-333333333333",
                correlation_id=str(uuid.uuid4()))
        self.assertIn("four reasons", str(refused.exception))

    def test_recontactable_turns_on_at_ninety_days_and_gates_nothing(self) -> None:
        """**Advisory**, so this is a service test: no route takes an instant, because a
        caller-supplied "now" would decide which lost leads a manager is told to try again."""
        tenant_id = self.tenant()
        lead = self.lead(tenant_id)
        self.lose(tenant_id, lead["lead_id"])
        for days, expected in ((89, False), (91, True)):
            with self.subTest(days=days):
                rows = crm.list_leads(
                    self._tenant_pool, tenant_id, lost=True,
                    at=datetime.now(UTC) + timedelta(days=days))["leads"]
                mine = next(r for r in rows if r["lead_id"] == lead["lead_id"])
                self.assertEqual(mine["recontactable"], expected)
