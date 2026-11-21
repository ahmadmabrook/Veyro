"""ADM-STF-01 and ADM-STF-02 over HTTP: the staff list, and the two planes it composes with.

**Three reads on three planes, and that is the shape of the screen.** `ppl_staff_profiles` is
MOD-014's and under `veyro_cp_app`; `iam.role_assignments` is MOD-008's and `iam.sessions` is
MOD-007's, both under `veyro_iam_app`, which holds nothing in `plt01` and vice versa. So the
design's four columns cannot be one query and must not be one permission: a reader may hold
`people.person.read` and not `authz.role.read`, and "nobody has a role" is a different fact
from "you may not see who does".

These go over HTTP rather than calling the services, for `test_people_api.py`'s reason: the
gate, the permission resolution, the assurance filter and the mask all live on that path, and
four defects in it were invisible to a green suite that reached past it.
"""

from __future__ import annotations

import unittest
import uuid

from tests.support import GatedApiTestCase


class StaffApiTestCase(GatedApiTestCase):
    """A tenant with a site, two people on the team and one of them with a login."""

    def location(self, tenant_id: str, name: str = "Khalda") -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Clubs Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        self.assertEqual(org.status_code, 201, org.text)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "Nadi"},
            headers=owner)
        self.assertEqual(brand.status_code, 201, brand.text)
        made = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": name,
            "timezone": "Asia/Amman"}, headers=owner)
        self.assertEqual(made.status_code, 201, made.text)
        return str(made.json()["location_id"])

    def person(self, tenant_id: str, name: str) -> str:
        made = self.client.post("/people", json={
            "legal_name": name, **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return str(made.json()["person_id"])

    def staff(
        self, tenant_id: str, person_id: str, *, title: str, location_id: str | None = None,
        started_on: str = "2025-01-06",
    ) -> dict[str, object]:
        made = self.client.post(f"/people/{person_id}/staff-profile", json={
            "job_title": title, "location_id": location_id, "started_on": started_on,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return dict(made.json())

    def scoped(self, tenant_id: str, permissions: list[str]) -> dict[str, str]:
        """Headers for an AAL-1 session holding exactly these permissions."""
        return self.headers(tenant_id, self.grant(tenant_id, permissions))


class StaffListTests(StaffApiTestCase):
    """ADM-STF-01, which until now had no route behind it at all."""

    def test_the_team_can_be_listed_which_it_could_not_before(self):
        tenant_id = self.tenant()
        site = self.location(tenant_id)
        layla = self.person(tenant_id, "Layla Mansour")
        self.staff(tenant_id, layla, title="Reception", location_id=site)
        listed = self.client.get("/staff", headers=self.headers(tenant_id))
        self.assertEqual(listed.status_code, 200, listed.text)
        body = listed.json()
        self.assertEqual(body["matching"], 1)
        row = body["staff"][0]
        self.assertEqual(row["job_title"], "Reception")
        self.assertEqual(row["employment_state"], "active")
        self.assertEqual(row["location_name"], "Khalda")
        self.assertEqual(row["started_on"], "2025-01-06")

    def test_the_chips_count_the_tenant_and_not_the_page(self):
        """A surface that summed the rows it loaded would report the page as the team."""
        tenant_id = self.tenant()
        for index in range(3):
            self.staff(tenant_id, self.person(tenant_id, f"Coach {index}"), title="Coach")
        ended = self.person(tenant_id, "Departed Person")
        profile = self.staff(tenant_id, ended, title="Sales")
        closed = self.client.post(f"/people/{ended}/staff-profile/end", json={
            "expected_version": profile["version"], "ended_on": "2026-03-01",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(closed.status_code, 200, closed.text)

        listed = self.client.get("/staff?limit=1", headers=self.headers(tenant_id))
        body = listed.json()
        self.assertEqual(len(body["staff"]), 1)
        self.assertEqual(body["by_state"], {"active": 3, "ended": 1})
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["matching"], 4)

    def test_the_order_is_what_the_states_mean_rather_than_how_they_spell(self):
        """Alphabetically `active` < `ended` < `suspended`, which puts the leavers above the
        people who are suspended -- and a suspended employee is still on the team."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        here = self.person(tenant_id, "Still Here")
        self.staff(tenant_id, here, title="Reception", started_on="2020-01-01")
        gone = self.person(tenant_id, "Gone")
        profile = self.staff(tenant_id, gone, title="Sales", started_on="2021-01-01")
        closed = self.client.post(f"/people/{gone}/staff-profile/end", json={
            "expected_version": profile["version"], "ended_on": "2026-03-01",
            **self.correlation()}, headers=owner)
        self.assertEqual(closed.status_code, 200, closed.text)
        rows = self.client.get("/staff", headers=owner).json()["staff"]
        self.assertEqual([r["employment_state"] for r in rows], ["active", "ended"])

    def test_a_filter_outside_the_domain_refuses_rather_than_returning_nothing(self):
        """"Invited" is the design's third chip and is not a state of this table.

        An unknown filter answering 200 with an empty list says the tenant has no invited
        staff, which is a different and wrong fact from nothing being able to invite anybody.
        """
        tenant_id = self.tenant()
        refused = self.client.get("/staff?employment_state=invited",
                                  headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("unknown_employment_state", refused.text)

    def test_the_three_gaps_are_stated_rather_than_drawn(self):
        tenant_id = self.tenant()
        body = self.client.get("/staff", headers=self.headers(tenant_id)).json()
        self.assertIn("role", body["columns_this_module_cannot_answer"])
        self.assertIn("last_seen", body["columns_this_module_cannot_answer"])
        self.assertIn("invitation", body["invited_is_not_a_state_here"])
        self.assertIn("certification", body["certifications_are_not_recorded"])
        self.assertIn("tenant-wide", body["the_location_filter_is_not_a_boundary"])

    def test_a_name_is_masked_on_a_session_that_may_not_read_identity(self):
        """The members list's behaviour, on the staff list, for the same reason.

        `legal_name` is identity-classed, so a routine session gets the mask and the surface
        offers the step-up -- which is how the members list ended up with that offer, after an
        independent tester clicked the marker looking for a way through.
        """
        tenant_id = self.tenant()
        self.staff(tenant_id, self.person(tenant_id, "Layla Mansour"), title="Reception")
        weak = self.client.get("/staff", headers=self.scoped(tenant_id,
                                                             ["people.person.read"]))
        self.assertEqual(weak.status_code, 200, weak.text)
        self.assertEqual(weak.json()["staff"][0]["legal_name"], "***")
        # And the owner, stepped up, reads it.
        strong = self.client.get("/staff", headers=self.headers(tenant_id))
        self.assertEqual(strong.json()["staff"][0]["legal_name"], "Layla Mansour")

    def test_a_session_holding_nothing_is_refused(self):
        tenant_id = self.tenant()
        refused = self.client.get(
            "/staff", headers=self.headers(tenant_id, self.unprivileged(tenant_id)))
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_the_limit_is_bounded_on_the_server(self):
        tenant_id = self.tenant()
        self.assertEqual(
            self.client.get("/staff?limit=500", headers=self.headers(tenant_id)).status_code,
            422)

    def test_a_malformed_location_filter_answers_422_not_500(self):
        tenant_id = self.tenant()
        self.assertEqual(
            self.client.get("/staff?location_id=not-an-id",
                            headers=self.headers(tenant_id)).status_code, 422)


class StaffProfileTests(StaffApiTestCase):
    """ADM-STF-02's header half."""

    def test_one_profile_reads_back_with_its_site(self):
        tenant_id = self.tenant()
        site = self.location(tenant_id, "Abdoun")
        layla = self.person(tenant_id, "Layla Mansour")
        self.staff(tenant_id, layla, title="Reception", location_id=site)
        read = self.client.get(f"/staff/{layla}", headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        self.assertEqual(body["job_title"], "Reception")
        self.assertEqual(body["location_name"], "Abdoun")
        self.assertEqual(body["employment_state"], "active")
        self.assertEqual(body["version"], 1)

    def test_it_carries_no_name_so_there_is_one_place_the_mask_has_to_be_right(self):
        tenant_id = self.tenant()
        layla = self.person(tenant_id, "Layla Mansour")
        self.staff(tenant_id, layla, title="Reception")
        body = self.client.get(f"/staff/{layla}", headers=self.headers(tenant_id)).json()
        self.assertNotIn("legal_name", body)
        self.assertNotIn("preferred_name", body)
        self.assertNotIn("date_of_birth", body)
        self.assertNotIn("Layla", read_text := str(body))
        self.assertNotIn("Mansour", read_text)

    def test_a_person_with_no_staff_profile_is_not_found(self):
        tenant_id = self.tenant()
        member = self.person(tenant_id, "Just A Member")
        missing = self.client.get(f"/staff/{member}", headers=self.headers(tenant_id))
        self.assertEqual(missing.status_code, 404, missing.text)

    def test_a_malformed_id_answers_422_not_500(self):
        tenant_id = self.tenant()
        self.assertEqual(
            self.client.get("/staff/not-an-id", headers=self.headers(tenant_id)).status_code,
            422)


class AssignmentBatchTests(StaffApiTestCase):
    """The ROLE column: MOD-008's assignments, batched, with the attribution the design draws."""

    def test_several_identities_in_one_request(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        first, _ = self.fresh_identity(tenant_id, "First")
        second, _ = self.fresh_identity(tenant_id, "Second")
        role = self.client.post("/authz/roles", json={
            "role_key": "reception", "display_name": "Reception",
            "permissions": ["people.person.read"], **self.correlation()}, headers=owner)
        self.assertEqual(role.status_code, 201, role.text)
        for who in (first, second):
            assigned = self.client.post("/authz/assignments", json={
                "identity_id": who, "role_key": "reception", **self.correlation()},
                headers=owner)
            self.assertEqual(assigned.status_code, 201, assigned.text)

        corr = str(uuid.uuid4())
        batched = self.client.get(
            f"/authz/assignments?identity_id={first}&identity_id={second}"
            f"&correlation_id={corr}", headers=owner)
        self.assertEqual(batched.status_code, 200, batched.text)
        answer = batched.json()["assignments"]
        self.assertEqual(sorted(answer), sorted([first, second]))
        for who in (first, second):
            self.assertEqual([a["role_key"] for a in answer[who]], ["reception"])
            self.assertEqual(answer[who][0]["display_name"], "Reception")

    def test_the_batch_answers_exactly_what_the_single_read_answers(self):
        """Same semantics, batched. A batch that aggregated would be a second definition."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        who, _ = self.fresh_identity(tenant_id, "Solo")
        self.client.post("/authz/roles", json={
            "role_key": "coach", "display_name": "Coach",
            "permissions": ["people.person.read"], **self.correlation()}, headers=owner)
        self.client.post("/authz/assignments", json={
            "identity_id": who, "role_key": "coach", **self.correlation()}, headers=owner)
        corr = str(uuid.uuid4())
        single = self.client.get(
            f"/authz/assignments/{who}?correlation_id={corr}", headers=owner).json()
        batched = self.client.get(
            f"/authz/assignments?identity_id={who}&correlation_id={corr}",
            headers=owner).json()["assignments"][who]
        self.assertEqual(single, batched)

    def test_the_grant_carries_who_made_it_which_nothing_had_ever_read(self):
        """`granted_by` is what the schema calls "the whole delegation record".

        ADM-STF-02's line is "Granted by Ziad / 4 Mar 2026", and a grant with nobody's name on
        it answers nothing. It is an identity id rather than a name: resolving it needs
        `people.person.read` and the identity link, so the attribution degrades to the id for
        a reader who may not see names rather than leaking one under `authz.role.read`.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        granter = self.owner_identity(tenant_id)
        who, _ = self.fresh_identity(tenant_id, "Granted")
        self.client.post("/authz/roles", json={
            "role_key": "sales", "display_name": "Sales",
            "permissions": ["people.person.read"], **self.correlation()}, headers=owner)
        self.client.post("/authz/assignments", json={
            "identity_id": who, "role_key": "sales", **self.correlation()}, headers=owner)
        answer = self.client.get(
            f"/authz/assignments?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=owner).json()["assignments"][who][0]
        self.assertEqual(answer["granted_by"], granter)
        self.assertTrue(answer["live"])

    def test_live_is_derived_on_the_server(self):
        """An assignment stops working when it expires or is revoked, and only one of those
        writes a row.

        Three cases rather than one, because the comparison a reader gets wrong is the
        open-ended one: an assignment with **no** expiry is live, and one with an expiry still
        in the future is live too. `role_assignments_expiry` refuses an expiry at or before
        the grant, so an already-expired row cannot be created through this route at all --
        which is why revocation is the third case rather than a past date.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        for key in ("locum", "standing"):
            self.client.post("/authz/roles", json={
                "role_key": key, "display_name": key.title(),
                "permissions": ["people.person.read"], **self.correlation()}, headers=owner)

        open_ended, _ = self.fresh_identity(tenant_id, "Permanent")
        made = self.client.post("/authz/assignments", json={
            "identity_id": open_ended, "role_key": "standing", **self.correlation()},
            headers=owner)
        self.assertEqual(made.status_code, 201, made.text)

        dated, _ = self.fresh_identity(tenant_id, "Temporary")
        timed = self.client.post("/authz/assignments", json={
            "identity_id": dated, "role_key": "locum",
            "expires_at": "2099-01-01T00:00:00+00:00", **self.correlation()}, headers=owner)
        self.assertEqual(timed.status_code, 201, timed.text)

        gone, _ = self.fresh_identity(tenant_id, "Revoked")
        revocable = self.client.post("/authz/assignments", json={
            "identity_id": gone, "role_key": "standing", **self.correlation()}, headers=owner)
        self.assertEqual(revocable.status_code, 201, revocable.text)
        dropped = self.client.post(
            f"/authz/assignments/{revocable.json()['assignment_id']}/revoke",
            json={**self.correlation()}, headers=owner)
        self.assertEqual(dropped.status_code, 200, dropped.text)

        answer = self.client.get(
            f"/authz/assignments?identity_id={open_ended}&identity_id={dated}"
            f"&identity_id={gone}&correlation_id={uuid.uuid4()}",
            headers=owner).json()["assignments"]
        self.assertTrue(answer[open_ended][0]["live"])
        self.assertIsNone(answer[open_ended][0]["expires_at"])
        self.assertTrue(answer[dated][0]["live"], "a future expiry is still live")
        self.assertIsNotNone(answer[dated][0]["expires_at"])
        self.assertFalse(answer[gone][0]["live"])

    def test_an_identity_with_no_assignment_answers_an_empty_list_not_a_missing_key(self):
        """An absent key reads as "we did not ask"; an empty list reads as "nobody gave them
        anything", which is the fact."""
        tenant_id = self.tenant()
        who, _ = self.fresh_identity(tenant_id, "Roleless")
        answer = self.client.get(
            f"/authz/assignments?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id)).json()["assignments"]
        self.assertEqual(answer, {who: []})

    def test_an_oversized_batch_refuses(self):
        tenant_id = self.tenant()
        many = "&".join(f"identity_id={uuid.uuid4()}" for _ in range(201))
        refused = self.client.get(
            f"/authz/assignments?{many}&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_malformed_identity_answers_422_not_500(self):
        tenant_id = self.tenant()
        refused = self.client.get(
            f"/authz/assignments?identity_id=nope&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_reading_roles_does_not_buy_the_staff_list(self):
        """Two permissions, two planes. A reader may hold either."""
        tenant_id = self.tenant()
        self.staff(tenant_id, self.person(tenant_id, "On The Team"), title="Coach")
        roles_only = self.scoped(tenant_id, ["authz.role.read"])
        self.assertEqual(self.client.get("/staff", headers=roles_only).status_code, 403)
        people_only = self.scoped(tenant_id, ["people.person.read"])
        self.assertEqual(
            self.client.get(
                f"/authz/assignments?identity_id={uuid.uuid4()}"
                f"&correlation_id={uuid.uuid4()}", headers=people_only).status_code, 403)


class SimulatorScopeTests(StaffApiTestCase):
    """What ADM-STF-02's grants block rests on, asserted rather than reasoned about.

    **`/authz/simulate` answers about one scope**, and `permissions_of` lets a broad assignment
    cover a narrow scope and never the reverse. That is correct and it means "what may this
    person do" has no single answer: a caller who asks about the tenant-wide default sees none
    of a person's narrowly scoped grants. The surface asks once per scope because of this, so
    the behaviour it depends on is checked here -- the first version of that page asked once
    and I wrote the finding up from reading the code, which is the mistake this repository
    records as "a theory that explains a failure is not the cause of it".
    """

    def test_a_location_scoped_grant_is_invisible_at_the_tenant_default(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        site = self.location(tenant_id)
        who, _ = self.fresh_identity(tenant_id, "Narrow")
        self.client.post("/authz/roles", json={
            "role_key": "till", "display_name": "Till",
            "permissions": ["finance.wallet.credit"], **self.correlation()}, headers=owner)
        assigned = self.client.post("/authz/assignments", json={
            "identity_id": who, "role_key": "till", "scope_type": "location",
            "location_id": site, **self.correlation()}, headers=owner)
        self.assertEqual(assigned.status_code, 201, assigned.text)

        at_default = self.client.get(
            f"/authz/simulate?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=owner)
        self.assertEqual(at_default.status_code, 200, at_default.text)
        self.assertNotIn("finance.wallet.credit", at_default.json()["permissions"],
                         "a location-scoped grant must not appear at the tenant default")

        at_site = self.client.get(
            f"/authz/simulate?identity_id={who}&location_id={site}"
            f"&correlation_id={uuid.uuid4()}", headers=owner)
        self.assertEqual(at_site.status_code, 200, at_site.text)
        self.assertIn("finance.wallet.credit", at_site.json()["permissions"])

    def test_a_tenant_scoped_grant_is_visible_at_a_location(self):
        """The other direction, which is what makes "everywhere" the right word for it."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        site = self.location(tenant_id)
        who, _ = self.fresh_identity(tenant_id, "Wide")
        self.client.post("/authz/roles", json={
            "role_key": "regional", "display_name": "Regional",
            "permissions": ["finance.wallet.credit"], **self.correlation()}, headers=owner)
        self.client.post("/authz/assignments", json={
            "identity_id": who, "role_key": "regional", **self.correlation()}, headers=owner)
        for query in ("", f"&location_id={site}"):
            with self.subTest(query or "default"):
                answer = self.client.get(
                    f"/authz/simulate?identity_id={who}{query}"
                    f"&correlation_id={uuid.uuid4()}", headers=owner)
                self.assertIn("finance.wallet.credit", answer.json()["permissions"])


class LastSeenTests(StaffApiTestCase):
    """The LAST SEEN column, and the control the design says it is for."""

    def test_an_identity_that_has_signed_in_has_been_seen_and_has_a_live_session(self):
        tenant_id = self.tenant()
        who, _ = self.fresh_identity(tenant_id, "Active")
        answer = self.client.get(
            f"/identities/last-seen?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 200, answer.text)
        row = answer.json()["identities"][who]
        self.assertEqual(row["status"], "active")
        self.assertIsNotNone(row["last_seen_at"])
        self.assertEqual(row["live_sessions"], 1)

    def test_a_departed_employee_with_a_live_login_is_visible_which_is_the_point(self):
        """The design's own sentence: "Last seen exists so a departed employee with a live
        login is visible rather than discovered."

        The two halves are on two planes under two permissions, so the composition is the
        surface's -- and this is the read that makes it possible at all.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        departed = self.person(tenant_id, "Still Has A Key")
        who, _ = self.fresh_identity(tenant_id, "Departing")
        linked = self.client.post(f"/people/{departed}/identity-links", json={
            "identity_id": who, **self.correlation()}, headers=owner)
        self.assertEqual(linked.status_code, 201, linked.text)
        profile = self.staff(tenant_id, departed, title="Sales")
        ended = self.client.post(f"/people/{departed}/staff-profile/end", json={
            "expected_version": profile["version"], "ended_on": "2026-03-01",
            **self.correlation()}, headers=owner)
        self.assertEqual(ended.status_code, 200, ended.text)

        row = [r for r in self.client.get("/staff", headers=owner).json()["staff"]
               if r["person_id"] == departed][0]
        self.assertEqual(row["employment_state"], "ended")
        self.assertEqual(row["identity_id"], who)
        seen = self.client.get(
            f"/identities/last-seen?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=owner).json()["identities"][who]
        self.assertGreaterEqual(seen["live_sessions"], 1)

    def test_it_returns_no_device_and_no_address(self):
        """Strictly less than the session inventory. A column on a list must not buy the page
        describing every device somebody has signed in from."""
        tenant_id = self.tenant()
        who, _ = self.fresh_identity(tenant_id, "Private")
        row = self.client.get(
            f"/identities/last-seen?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id)).json()["identities"][who]
        for leaked in ("device_id", "factors", "aal", "token_hash", "session_id",
                       "email_normalized", "phone_normalized", "display_name"):
            self.assertNotIn(leaked, row)
        self.assertIn("identity.session.read", row["no_device_or_address_is_returned"])

    def test_an_unknown_identity_is_absent_rather_than_invented(self):
        tenant_id = self.tenant()
        ghost = str(uuid.uuid4())
        answer = self.client.get(
            f"/identities/last-seen?identity_id={ghost}&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id)).json()["identities"]
        self.assertEqual(answer, {})

    def test_another_tenants_identity_is_not_answered_for(self):
        """The isolation this whole build rests on, asserted at the new route."""
        first = self.tenant()
        second = self.tenant()
        theirs, _ = self.fresh_identity(second, "Elsewhere")
        answer = self.client.get(
            f"/identities/last-seen?identity_id={theirs}&correlation_id={uuid.uuid4()}",
            headers=self.headers(first)).json()["identities"]
        self.assertEqual(answer, {})

    def test_an_oversized_batch_refuses(self):
        tenant_id = self.tenant()
        many = "&".join(f"identity_id={uuid.uuid4()}" for _ in range(201))
        refused = self.client.get(
            f"/identities/last-seen?{many}&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_a_malformed_identity_answers_422_not_500(self):
        tenant_id = self.tenant()
        refused = self.client.get(
            f"/identities/last-seen?identity_id=nope&correlation_id={uuid.uuid4()}",
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_reading_a_last_seen_needs_its_own_permission(self):
        tenant_id = self.tenant()
        people_only = self.scoped(tenant_id, ["people.person.read"])
        refused = self.client.get(
            f"/identities/last-seen?identity_id={uuid.uuid4()}"
            f"&correlation_id={uuid.uuid4()}", headers=people_only)
        self.assertEqual(refused.status_code, 403, refused.text)


class IdentityStatusTests(StaffApiTestCase):
    """IAM-01's missing writer, found by building the screen that needed it.

    **Four controls read `iam.identities.status` and nothing could set it.** `authenticate`,
    the risk challenge, `recover_with_code` and `_session_by_token` each refuse an identity
    that is not `active`; the column admits three states and two of them were unreachable, so
    this product could not shut anybody out. ADM-STF-01 shows an owner that a departed
    employee can still sign in, which made a board naming a problem the product could not act
    on -- so the act exists now, with the evidence its `kind` needed a migration to name.
    """

    def actor(self, tenant_id: str) -> dict[str, str]:
        """A stepped-up session holding the write. `identity.identity.write` is financial."""
        return self.headers(
            tenant_id, self.stepped_grant(tenant_id, ["identity.identity.write"]))

    def test_suspending_stops_the_login_and_revokes_the_live_sessions(self):
        tenant_id = self.tenant()
        who, token = self.fresh_identity(tenant_id, "Leaving")
        # Their session works before.
        self.assertEqual(
            self.client.get("/auth/session", headers=self.headers(tenant_id, token))
            .status_code, 200)

        done = self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "left the company on 1 March",
            **self.correlation()}, headers=self.actor(tenant_id))
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertEqual(body["status"], "suspended")
        self.assertEqual(body["was"], "active")
        self.assertGreaterEqual(body["sessions_revoked"], 1)

        # And it does not afterwards. `_session_by_token` reads the status, so the bearer
        # token stops working whether or not the session row was revoked -- which is why
        # revoking it is about the evidence rather than about the control.
        self.assertEqual(
            self.client.get("/auth/session", headers=self.headers(tenant_id, token))
            .status_code, 401)

    def test_a_suspended_identity_cannot_sign_in_again(self):
        """The control the four readers were written for, now reachable."""
        tenant_id = self.tenant()
        owner = self.actor(tenant_id)
        made = self.client.post("/identities", json={
            "display_name": "Soon Gone", "email": f"gone-{uuid.uuid4().hex[:8]}@acme.test",
            "password": self.PASSWORD, **self.correlation()},
            headers={"X-Veyro-Tenant": tenant_id})
        self.assertEqual(made.status_code, 201, made.text)
        email = made.json()["email"]
        who = made.json()["identity_id"]

        self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "offboarded", **self.correlation()},
            headers=owner)
        refused = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD, **self.correlation()},
            headers={"X-Veyro-Tenant": tenant_id})
        # The same 401 everything else answers: a refusal must not say why. MOD-007's review
        # found a locked identity answering 423 in two milliseconds, which identified every
        # registered address in five requests.
        self.assertEqual(refused.status_code, 401, refused.text)

    def test_reinstating_lets_them_back_in(self):
        """An accidental suspension with no way back would be worse than the gap it closed."""
        tenant_id = self.tenant()
        owner = self.actor(tenant_id)
        made = self.client.post("/identities", json={
            "display_name": "Back Again", "email": f"back-{uuid.uuid4().hex[:8]}@acme.test",
            "password": self.PASSWORD, **self.correlation()},
            headers={"X-Veyro-Tenant": tenant_id})
        email, who = made.json()["email"], made.json()["identity_id"]
        self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "a mistake", **self.correlation()},
            headers=owner)
        back = self.client.post(f"/identities/{who}/status", json={
            "status": "active", "reason": "it was a mistake", **self.correlation()},
            headers=owner)
        self.assertEqual(back.status_code, 200, back.text)
        self.assertEqual(back.json()["was"], "suspended")
        self.assertEqual(back.json()["sessions_revoked"], 0)
        allowed = self.client.post("/auth/login", json={
            "identifier": email, "password": self.PASSWORD, **self.correlation()},
            headers={"X-Veyro-Tenant": tenant_id})
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_a_session_cannot_suspend_the_identity_it_is_using(self):
        """**This build has no way back from an owner locking itself out.**

        There is no platform identity and nothing reinstates an identity from outside the
        tenant, so a self-suspension would end the tenant's administration with no remedy
        anywhere in the product. The refusal is recoverable; the act would not be.
        """
        tenant_id = self.tenant()
        token = self.stepped_grant(tenant_id, ["identity.identity.write"])
        me = self.client.get("/auth/session",
                             headers=self.headers(tenant_id, token)).json()["identity_id"]
        refused = self.client.post(f"/identities/{me}/status", json={
            "status": "suspended", "reason": "no", **self.correlation()},
            headers=self.headers(tenant_id, token))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("cannot_change_your_own_status", refused.text)

    def test_a_repeat_is_answered_from_what_was_recorded(self):
        """MOD-017's rule, three times paid for: a client whose request timed out after the
        commit must not be told the work failed."""
        tenant_id = self.tenant()
        owner = self.actor(tenant_id)
        who, _ = self.fresh_identity(tenant_id, "Twice")
        first = self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "left", **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["repeated"])
        again = self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "left", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["sessions_revoked"], 0)

    def test_the_act_is_recorded_with_who_did_it(self):
        """Seven modules running: evidence with nobody's name on it answers nothing.

        `iam.auth_events` records the identity an event is *about* and has no column for the
        one that caused it, so the actor gets its own row under the same correlation id. The
        log is insert-only, so neither can be edited to disagree with the other.
        """
        tenant_id = self.tenant()
        token = self.stepped_grant(
            tenant_id, ["identity.identity.write", "identity.identity.read"])
        headers = self.headers(tenant_id, token)
        actor = self.client.get("/auth/session", headers=headers).json()["identity_id"]
        who, _ = self.fresh_identity(tenant_id, "Logged")
        correlation = str(uuid.uuid4())
        self.client.post(f"/identities/{who}/status", json={
            "status": "deactivated", "reason": "contract ended 30 June",
            "correlation_id": correlation}, headers=headers)
        with self._identity_pool.connection() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            rows = conn.execute(
                "SELECT identity_id, kind, reason FROM iam.auth_events"
                " WHERE correlation_id = %s ORDER BY identity_id",
                (correlation,)).fetchall()
        kinds = {str(r[0]): (r[1], r[2]) for r in rows}
        self.assertIn(who, kinds)
        self.assertIn(actor, kinds)
        self.assertEqual(kinds[who][0], "identity.deactivated")
        self.assertEqual(kinds[who][1], "contract ended 30 June")
        self.assertEqual(kinds[actor][1], f"acted_on:{who}")

    def test_a_status_outside_the_schemas_own_domain_refuses(self):
        tenant_id = self.tenant()
        who, _ = self.fresh_identity(tenant_id, "Odd")
        refused = self.client.post(f"/identities/{who}/status", json={
            "status": "deleted", "reason": "x", **self.correlation()},
            headers=self.actor(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("bad_status", refused.text)

    def test_a_blank_reason_refuses_because_the_row_is_the_only_record(self):
        tenant_id = self.tenant()
        who, _ = self.fresh_identity(tenant_id, "Unexplained")
        for reason in ("", "   ", "\t"):
            with self.subTest(repr(reason)):
                refused = self.client.post(f"/identities/{who}/status", json={
                    "status": "suspended", "reason": reason, **self.correlation()},
                    headers=self.actor(tenant_id))
                self.assertEqual(refused.status_code, 422, refused.text)

    def test_the_permission_alone_is_not_enough_because_it_is_financial(self):
        """Holding the permission on a password-only session does not buy the act."""
        tenant_id = self.tenant()
        who, _ = self.fresh_identity(tenant_id, "Target")
        weak = self.headers(tenant_id, self.grant(tenant_id, ["identity.identity.write"]))
        refused = self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "left", **self.correlation()}, headers=weak)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_another_tenants_identity_is_not_found(self):
        first = self.tenant()
        second = self.tenant()
        theirs, _ = self.fresh_identity(second, "Elsewhere")
        refused = self.client.post(f"/identities/{theirs}/status", json={
            "status": "suspended", "reason": "left", **self.correlation()},
            headers=self.actor(first))
        self.assertEqual(refused.status_code, 404, refused.text)

    def test_the_roles_are_left_alone_and_the_response_says_so(self):
        """Whether somebody may sign in and what they may do are different questions."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        who, _ = self.fresh_identity(tenant_id, "Roled")
        self.client.post("/authz/roles", json={
            "role_key": "frontdesk", "display_name": "Front desk",
            "permissions": ["people.person.read"], **self.correlation()}, headers=owner)
        self.client.post("/authz/assignments", json={
            "identity_id": who, "role_key": "frontdesk", **self.correlation()},
            headers=owner)
        done = self.client.post(f"/identities/{who}/status", json={
            "status": "suspended", "reason": "left", **self.correlation()},
            headers=self.actor(tenant_id))
        self.assertIn("revokes nothing in authorization", done.json()["roles_are_unchanged"])
        still = self.client.get(
            f"/authz/assignments?identity_id={who}&correlation_id={uuid.uuid4()}",
            headers=owner).json()["assignments"][who]
        self.assertTrue(still[0]["live"])


if __name__ == "__main__":
    unittest.main()
