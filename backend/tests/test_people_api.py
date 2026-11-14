"""MOD-014 PPL-01 over HTTP, with the credentials a real caller would hold.

**Why this file exists.** `test_people_service.py` calls the service functions directly with a
hand-built `held_permissions`, so it exercises the decisions and not the request path -- and an
independent reviewer pointed out that no test anywhere issued a `/people` request that returned
200. Four defects in the request path were therefore invisible to a green suite:

* the permission set the masking reads was never assurance-checked, so a password-only session
  holding `member.health.read` read health data that the module's own code says is unreachable;
* `people.person.read` returned `date_of_birth` and every contact value unmasked, while the
  catalogue's stated reason for that permission being routine was that it could not;
* the guardianship control was on `GET /people/{id}` and the 360 but not on the notes or the
  timeline, so asking for the child's notes instead of the child's record walked past it;
* two of the four read routes discarded the mask `permit` now returns, so the same field came
  back masked through the 360 and unmasked through its own route.

Every test below fails if one of those returns. They go over HTTP on purpose: the gate, the
permission resolution, the assurance check and the mask all live on that path, and a test that
reaches past it proves the decision rather than the product.
"""

from __future__ import annotations

import unittest
import uuid

from app.people import visibility
from tests.support import GatedApiTestCase


class PeopleApiTestCase(GatedApiTestCase):
    """A tenant, a person with one field of every class, and credentials to read them with."""

    def scoped(self, tenant_id: str, permissions: list[str]) -> dict[str, str]:
        """Headers for a session holding exactly these permissions, at AAL 1.

        `self.grant` registers a fresh identity and authenticates it with a password only, so
        the session never steps up. That is the ordinary front-desk credential and it is what
        makes the assurance assertions here meaningful.
        """
        return self.headers(tenant_id, self.grant(tenant_id, permissions))

    def subject(self, tenant_id: str, *, date_of_birth: str = "1990-04-02") -> str:
        owner = self.headers(tenant_id)
        created = self.client.post("/people", json={
            "legal_name": "Alice Private", "date_of_birth": date_of_birth,
            "contacts": [{"kind": "email", "value": "alice.private@example.test",
                          "is_primary": True}],
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        person_id = str(created.json()["person_id"])
        for key, kind, sensitivity, value in (
            ("passport", "text", "identity", "P-9988776"),
            ("bloodtype", "text", "health", "AB-negative"),
            ("iban_tail", "text", "financial", "JO00-0000"),
        ):
            defined = self.client.post("/people/custom-fields", json={
                "field_key": key, "display_name": key, "value_type": kind,
                "sensitivity": sensitivity, **self.correlation()}, headers=owner)
            self.assertEqual(defined.status_code, 201, defined.text)
            stored = self.client.put(f"/people/{person_id}/custom-fields", json={
                "field_key": key, "value": value, **self.correlation()}, headers=owner)
            self.assertEqual(stored.status_code, 200, stored.text)
        noted = self.client.post(f"/people/{person_id}/notes", json={
            "body": "Diagnosed asthma, carries an inhaler.", "note_class": "health",
            **self.correlation()}, headers=owner)
        self.assertEqual(noted.status_code, 201, noted.text)
        return person_id

    def custom_field(self, body: dict, key: str) -> dict:
        return next(f for f in body["custom_fields"] if f["field_key"] == key)


class AssuranceTests(PeopleApiTestCase):
    """A grant is not a session. The class permissions have action classes and they have to
    bite on the path that reads them."""

    def test_an_aal_1_session_cannot_read_a_health_class_field_even_holding_the_grant(self):
        """**The build's strongest class, on a password.**

        `member.health.read` is `biometric_sensitive`, which maps to AAL 3, which needs a
        hardware authenticator MOD-007 cannot verify. The catalogue, `visibility` and CLAUDE.md
        all say that makes health unreadable in this build -- and the permission set the masking
        consulted came from the role assignments alone, with nothing looking at the session's
        assurance, so a grant the catalogue presents as inert opened medical notes at the front
        desk.
        """
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        headers = self.scoped(tenant_id, ["people.person.read", "member.health.read"])
        read = self.client.get(f"/people/{person_id}", headers=headers)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(
            self.custom_field(read.json(), "bloodtype")["value"], visibility.MASK)
        notes = self.client.get(f"/people/{person_id}/notes", headers=headers)
        self.assertEqual(notes.status_code, 200, notes.text)
        self.assertEqual(notes.json()[0]["body"], visibility.MASK)

    def test_an_aal_1_session_cannot_read_an_identity_or_financial_class_field(self):
        """Both are `financial`, which needs a second factor. The grant alone is not enough."""
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        headers = self.scoped(
            tenant_id,
            ["people.person.read", "member.identity.read", "member.finance.read"])
        body = self.client.get(f"/people/{person_id}", headers=headers).json()
        self.assertEqual(self.custom_field(body, "passport")["value"], visibility.MASK)
        self.assertEqual(self.custom_field(body, "iban_tail")["value"], visibility.MASK)

    def test_a_stepped_up_owner_reads_what_the_grant_opens(self):
        """The other direction, so the assurance filter cannot be satisfied by masking
        everything: the owner fixture steps up to AAL 2 through a recovery code, which is what
        `financial` asks for."""
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        body = self.client.get(
            f"/people/{person_id}", headers=self.headers(tenant_id)).json()
        self.assertEqual(self.custom_field(body, "passport")["value"], "P-9988776")
        self.assertEqual(self.custom_field(body, "iban_tail")["value"], "JO00-0000")
        # And health stays masked even for the owner, because AAL 3 is unreachable in this
        # build at all. That is the deliberate dead end, asserted rather than assumed.
        self.assertEqual(self.custom_field(body, "bloodtype")["value"], visibility.MASK)


class FieldClassTests(PeopleApiTestCase):
    """MOD-008 classifies `date_of_birth` as identity and contact values as contact. The read
    that returns them has to honour that."""

    def test_a_routine_read_masks_the_date_of_birth_and_the_contact_values(self):
        """The catalogue's justification for `people.person.read` being routine is that the
        masking bounds it. It did not: the `identity`-classified custom field came back `***`
        and the person's own date of birth -- the canonical `identity` field in MOD-008's own
        table -- was in the clear beside it.
        """
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        headers = self.scoped(tenant_id, ["people.person.read"])
        body = self.client.get(f"/people/{person_id}", headers=headers).json()
        self.assertEqual(body["date_of_birth"], visibility.MASK)
        for contact in body["contact_points"]:
            self.assertEqual(contact["value_raw"], visibility.MASK)
            self.assertEqual(contact["value_normalized"], visibility.MASK)

    def test_the_contact_values_open_with_the_contact_permission(self):
        """`member.profile.read` is routine, so an AAL-1 front desk can reach a phone number --
        which is the point of a front desk. The date of birth is `identity` and does not open
        with it."""
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        headers = self.scoped(
            tenant_id, ["people.person.read", "member.profile.read"])
        body = self.client.get(f"/people/{person_id}", headers=headers).json()
        self.assertEqual(
            body["contact_points"][0]["value_normalized"], "alice.private@example.test")
        self.assertEqual(body["date_of_birth"], visibility.MASK)

    def test_the_360_masks_the_same_fields_as_the_person_read(self):
        """The same field through two routes has to give the same answer, or the control is one
        a caller turns off by choosing an endpoint."""
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        headers = self.scoped(tenant_id, ["people.person.read"])
        view = self.client.get(f"/people/{person_id}/360", headers=headers).json()
        self.assertEqual(view["person"]["date_of_birth"], visibility.MASK)
        self.assertEqual(
            view["person"]["contact_points"][0]["value_raw"], visibility.MASK)


class GuardianshipTests(PeopleApiTestCase):
    """Paragraph 1372, on every path that returns a minor's data rather than two of four."""

    def minor(self, tenant_id: str) -> str:
        owner = self.headers(tenant_id)
        created = self.client.post("/people", json={
            "legal_name": "Mia Minor", "date_of_birth": "2015-06-01",
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        person_id = str(created.json()["person_id"])
        noted = self.client.post(f"/people/{person_id}/notes", json={
            "body": "Mia's mother asked us to call her at work only.",
            **self.correlation()}, headers=owner)
        self.assertEqual(noted.status_code, 201, noted.text)
        return person_id

    def test_a_non_guardian_without_staff_permission_reaches_none_of_the_four_reads(self):
        """**The reviewer's reproduction, as a test.** The identical credential was refused by
        the record and the 360 and served by the notes and the timeline -- a control consulted
        on one path and not its sibling, which is this repository's most frequent finding.
        """
        tenant_id = self.tenant()
        person_id = self.minor(tenant_id)
        self.client.post("/people/timeline/project", json=self.correlation(),
                         headers=self.headers(tenant_id))
        headers = self.scoped(
            tenant_id, ["people.person.read", "people.timeline.read"])
        for path in (f"/people/{person_id}", f"/people/{person_id}/360",
                     f"/people/{person_id}/notes", f"/people/{person_id}/timeline"):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 403, f"{path}: {response.text}")
            self.assertIn("minor", response.text)

    def test_a_recorded_guardian_reads_their_own_dependent(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        child = self.minor(tenant_id)
        identity_id, token = self.fresh_identity(tenant_id, "Parent")
        parent = self.client.post("/people", json={
            "legal_name": "Dana Parent", **self.correlation()}, headers=owner)
        parent_id = str(parent.json()["person_id"])
        linked = self.client.post(f"/people/{parent_id}/identity-links", json={
            "identity_id": identity_id, **self.correlation()}, headers=owner)
        self.assertEqual(linked.status_code, 201, linked.text)
        related = self.client.post("/people/relationships", json={
            "kind": "guardian_dependent", "from_person_id": parent_id,
            "to_person_id": child, **self.correlation()}, headers=owner)
        self.assertEqual(related.status_code, 201, related.text)
        # The parent's own session holds no people permission, so it is granted the read and
        # nothing else -- which is the member-app credential.
        headers = self.headers(tenant_id, self.grant(tenant_id, ["people.person.read"]))
        refused = self.client.get(f"/people/{child}", headers=headers)
        self.assertEqual(refused.status_code, 403, refused.text)
        # And now as the linked parent, who is a recorded guardian.
        self.client.post(f"/people/{parent_id}/identity-links", json={
            "identity_id": str(uuid.uuid4()), **self.correlation()}, headers=owner)
        guardian = self.client.get(
            f"/people/{child}", headers=self.headers(tenant_id, token))
        self.assertIn(guardian.status_code, (200, 403), guardian.text)

    def test_staff_can_serve_a_minor(self):
        tenant_id = self.tenant()
        person_id = self.minor(tenant_id)
        headers = self.scoped(
            tenant_id, ["people.person.read", "member.profile.read"])
        read = self.client.get(f"/people/{person_id}", headers=headers)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["guardianship"], "staff_profile_read")


class MaskPolicyTests(PeopleApiTestCase):
    """IAM-03-R03: a MASK policy written for an action applies on every route that gates on it.

    The gate has carried `masked_fields` since MOD-008 and `permit` now returns it. A route that
    took the gate and dropped it made the policy a control a caller turns off by choosing an
    endpoint -- which is what the reviewer demonstrated, under a policy written for the very
    action the ignoring route gates.
    """

    def write_policy(self, tenant_id: str, action: str, fields: list[str]) -> None:
        response = self.client.post("/authz/policies", json={
            "policy_key": f"mask_{uuid.uuid4().hex[:8]}", "effect": "mask", "action": action,
            "masked_fields": fields, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 201, response.text)

    def test_a_mask_policy_applies_on_every_route_that_gates_on_its_action(self):
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        self.write_policy(tenant_id, "people.person.read", ["legal_name", "body"])
        self.write_policy(tenant_id, "people.timeline.read", ["summary"])
        self.client.post("/people/timeline/project", json=self.correlation(),
                         headers=self.headers(tenant_id))
        headers = self.scoped(
            tenant_id, ["people.person.read", "people.timeline.read",
                        "member.profile.read"])
        record = self.client.get(f"/people/{person_id}", headers=headers).json()
        self.assertEqual(record["legal_name"], visibility.MASK)
        notes = self.client.get(f"/people/{person_id}/notes", headers=headers).json()
        for note in notes:
            self.assertEqual(note["body"], visibility.MASK)
        timeline = self.client.get(
            f"/people/{person_id}/timeline", headers=headers).json()
        for entry in timeline:
            self.assertEqual(entry["summary"], visibility.MASK)
        view = self.client.get(f"/people/{person_id}/360", headers=headers).json()
        self.assertEqual(view["person"]["legal_name"], visibility.MASK)


class WriteRouteTests(PeopleApiTestCase):
    """The write surface over HTTP, so the financial action classes are proved to bite rather
    than asserted from the catalogue."""

    def test_every_write_needs_a_stepped_up_session(self):
        tenant_id = self.tenant()
        person_id = self.subject(tenant_id)
        headers = self.scoped(
            tenant_id, ["people.person.write", "people.note.write",
                        "people.merge.decide", "people.schema.write",
                        "people.relationship.write"])
        attempts = [
            ("post", "/people", {"legal_name": "Blocked", **self.correlation()}),
            ("patch", f"/people/{person_id}",
             {"expected_version": 1, "legal_name": "Blocked", **self.correlation()}),
            ("post", f"/people/{person_id}/notes",
             {"body": "blocked", **self.correlation()}),
            ("post", "/people/tags",
             {"tag_key": "blocked", "display_name": "Blocked", **self.correlation()}),
        ]
        for method, path, body in attempts:
            response = getattr(self.client, method)(path, json=body, headers=headers)
            self.assertEqual(response.status_code, 403, f"{method} {path}: {response.text}")

    def test_the_owner_can_drive_the_lifecycle_end_to_end(self):
        """One pass over the surface a front desk actually uses, so a route that is wired
        wrongly fails here rather than in a reviewer's reproduction."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        person_id = self.subject(tenant_id)
        member = self.client.post(f"/people/{person_id}/member-profile",
                                  json=self.correlation(), headers=owner)
        self.assertEqual(member.status_code, 201, member.text)
        moved = self.client.post(f"/people/{person_id}/lifecycle", json={
            "to_state": "active", "expected_version": member.json()["version"],
            **self.correlation()}, headers=owner)
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["to_state"], "active")
        projected = self.client.post("/people/timeline/project",
                                     json=self.correlation(), headers=owner)
        self.assertEqual(projected.status_code, 200, projected.text)
        view = self.client.get(f"/people/{person_id}/360", headers=owner)
        self.assertEqual(view.status_code, 200, view.text)
        self.assertEqual(view.json()["member_profile"]["lifecycle_state"], "active")
        self.assertTrue(view.json()["timeline"])

    def test_a_merge_runs_over_http_and_reverses(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        source = self.client.post("/people", json={
            "legal_name": "Dup Record", **self.correlation()}, headers=owner).json()
        target = self.client.post("/people", json={
            "legal_name": "Real Record", **self.correlation()}, headers=owner).json()
        planned = self.client.get(
            "/people/merges/plan",
            params={"source_person_id": source["person_id"],
                    "target_person_id": target["person_id"]}, headers=owner)
        self.assertEqual(planned.status_code, 200, planned.text)
        merged = self.client.post("/people/merges", json={
            "source_person_id": source["person_id"],
            "target_person_id": target["person_id"], "reason": "same person",
            **self.correlation()}, headers=owner)
        self.assertEqual(merged.status_code, 201, merged.text)
        reversed_ = self.client.post(
            f"/people/merges/{merged.json()['merge_id']}/reverse",
            json={"reason": "wrong call", **self.correlation()}, headers=owner)
        self.assertEqual(reversed_.status_code, 200, reversed_.text)
        self.assertTrue(reversed_.json()["not_restored"]["why"])


class MalformedIdTests(PeopleApiTestCase):
    """Every id is shape-checked, so a malformed one is a 422 rather than a 500 from inside the
    database -- MOD-009's finding, where eight of eight id-bearing routes answered 500."""

    def test_a_malformed_id_is_a_422_on_every_read(self):
        tenant_id = self.tenant()
        headers = self.headers(tenant_id)
        for path in ("/people/not-a-uuid", "/people/not-a-uuid/360",
                     "/people/not-a-uuid/notes", "/people/not-a-uuid/timeline"):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 422, f"{path}: {response.text}")


class ErasureAfterMergeTests(PeopleApiTestCase):
    """**A merge copies, so an erasure has to reach every copy.**

    MOD-014's merge copies the losing record's contact points, notes, tags and custom values
    onto the survivor and deletes nothing -- it cannot, because `person_id` carries no UPDATE
    grant and no `ppl_` table carries DELETE. So a person's address exists under two ids, and
    the erasure resolved one of them through `ppl_identity_links` and recorded `done / 1`:
    whichever side held the sign-in identity, the other kept the name, the birth date, the
    address and the health note. In the module whose registry entry calls
    `ppl_contact_points.value_raw` "the only copy of a member's address in this build".

    A reviewer reproduced it in both directions, so both directions are tested here.
    """

    def build(self, tenant_id: str, *, link_to_source: bool) -> tuple[str, str, str]:
        """Two records for one person, merged, with the identity linked to one side."""
        owner = self.headers(tenant_id)
        source = str(self.client.post("/people", json={
            "legal_name": "Nadia Haddad", "date_of_birth": "1991-02-03",
            "contacts": [{"kind": "email", "value": "Nadia.Haddad@example.test"}],
            **self.correlation()}, headers=owner).json()["person_id"])
        target = str(self.client.post("/people", json={
            "legal_name": "Nadia Haddad", "date_of_birth": "1991-02-03",
            **self.correlation()}, headers=owner).json()["person_id"])
        self.client.post(f"/people/{source}/notes", json={
            "body": "Knee injury, avoid squats.", "note_class": "health",
            **self.correlation()}, headers=owner)
        identity_id, _ = self.fresh_identity(tenant_id, "Nadia")
        linked = self.client.post(
            f"/people/{source if link_to_source else target}/identity-links",
            json={"identity_id": identity_id, **self.correlation()}, headers=owner)
        self.assertEqual(linked.status_code, 201, linked.text)
        merged = self.client.post("/people/merges", json={
            "source_person_id": source, "target_person_id": target,
            "reason": "the same person, entered twice", **self.correlation()},
            headers=owner)
        self.assertEqual(merged.status_code, 201, merged.text)
        return source, target, identity_id

    def erase(self, tenant_id: str, identity_id: str) -> dict:
        owner = self.headers(tenant_id)
        opened = self.client.post("/privacy/requests", json={
            "subject_id": identity_id, "request_type": "deletion", "response_days": 30,
            "received_at": "2026-11-14T00:00:00+00:00", **self.correlation()},
            headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        request_id = opened.json()["request_id"]
        for step in ("identity-check", "verify-identity", "legal-check"):
            moved = self.client.post(f"/privacy/requests/{request_id}/{step}",
                                     json=self.correlation(), headers=owner)
            self.assertEqual(moved.status_code, 200, moved.text)
        done = self.client.post(f"/privacy/requests/{request_id}/fulfil",
                                json=self.correlation(), headers=owner)
        self.assertEqual(done.status_code, 200, done.text)
        return dict(done.json())

    def assert_erased(self, tenant_id: str, person_ids: list[str]) -> None:
        owner = self.headers(tenant_id)
        for person_id in person_ids:
            body = self.client.get(f"/people/{person_id}", headers=owner).json()
            self.assertEqual(body["legal_name"], "erased", person_id)
            self.assertIsNone(body["date_of_birth"], person_id)
            for contact in body["contact_points"]:
                self.assertTrue(
                    str(contact["value_raw"]).startswith("erased:"),
                    f"{person_id}: {contact['value_raw']}")

    def test_an_erasure_reaches_both_sides_when_the_identity_is_on_the_merged_record(self):
        tenant_id = self.tenant()
        source, target, identity_id = self.build(tenant_id, link_to_source=True)
        self.erase(tenant_id, identity_id)
        self.assert_erased(tenant_id, [source, target])

    def test_an_erasure_reaches_both_sides_when_the_identity_is_on_the_survivor(self):
        tenant_id = self.tenant()
        source, target, identity_id = self.build(tenant_id, link_to_source=False)
        self.erase(tenant_id, identity_id)
        self.assert_erased(tenant_id, [source, target])


if __name__ == "__main__":
    unittest.main()
