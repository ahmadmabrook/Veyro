"""MOD-009 over HTTP: the privacy surface driven the way a caller drives it.

Two things are tested here that the service suites cannot see.

**The gate's own decisions.** `tests/test_gating.py` sweeps every privacy route with no session
and with a session holding nothing, which proves each one is guarded. It does not prove each one
is guarded by the *right* permission -- a route guarded by the wrong one reads exactly like a
guarded route from outside. The tests here ask what the weakest credential that satisfies each
route can actually do, which is the only way to tell them apart. That distinction is what an
independent review of MOD-008's gate found four times over.

**The workflow end to end.** `open -> identity -> legal -> fulfil` is an ordering, and an
ordering is a property of the sequence rather than of any one call. Driving it over HTTP is also
the only place the route wiring is exercised: a body field spelled wrong in `main.py` passes
every unit test in `app/privacy/` and fails here.
"""

from __future__ import annotations

import unittest
import uuid

from tests.support import GatedApiTestCase


class PrivacyApiTestCase(GatedApiTestCase):
    """A tenant with a processing purpose, a waiver consent kind and one published document."""

    def fixture(self, tenant_id: str, *, consent_type: str = "waiver",
                requires_guardian: bool = False) -> dict[str, str]:
        owner = self.headers(tenant_id)
        purpose = self.client.post("/privacy/purposes", headers=owner, json={
            "purpose_code": f"member.training{uuid.uuid4().hex[:6]}",
            "description": "Deliver training sessions", "lawful_basis": "contract",
            "controller_role": "processor", "data_classes": ["confidential"],
            **self.correlation()})
        self.assertEqual(purpose.status_code, 201, purpose.text)
        definition = self.client.post("/privacy/consent/definitions", headers=owner, json={
            "consent_type": consent_type, "purpose_id": purpose.json()["purpose_id"],
            "requires_guardian": requires_guardian, **self.correlation()})
        self.assertEqual(definition.status_code, 201, definition.text)
        version = self.client.post("/privacy/consent/versions", headers=owner, json={
            "consent_type": consent_type, "language": "en",
            "document_ref": f"{consent_type}/v1",
            "document_hash": "ab" * 32, "effective_from": "2026-01-01T00:00:00+00:00",
            **self.correlation()})
        self.assertEqual(version.status_code, 201, version.text)
        return {"purpose_id": purpose.json()["purpose_id"],
                "consent_version_id": version.json()["consent_version_id"]}

    def walk_to_ready(self, tenant_id: str, subject_id: str, *,
                      request_type: str = "deletion") -> str:
        """Open a request and move it through both gates, as the owner."""
        owner = self.headers(tenant_id)
        opened = self.client.post("/privacy/requests", headers=owner, json={
            "subject_id": subject_id, "request_type": request_type, "response_days": 30,
            **self.correlation()})
        self.assertEqual(opened.status_code, 201, opened.text)
        request_id = str(opened.json()["request_id"])
        for step in ("identity-check", "verify-identity", "legal-check"):
            moved = self.client.post(f"/privacy/requests/{request_id}/{step}", headers=owner,
                                     json=self.correlation())
            self.assertEqual(moved.status_code, 200, f"{step}: {moved.text}")
        return request_id


class ConsentSubjectTests(PrivacyApiTestCase):
    """Whose consent a record claims to be is derived from the session, not taken on trust."""

    def test_a_subject_may_record_their_own_consent_on_an_ordinary_session(self):
        """The ordinary case has to work from a phone at AAL 1, or consent is uncollectable."""
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        token = self.grant(tenant_id, ["privacy.consent.record", "privacy.consent.read"])
        head = self.headers(tenant_id, token)
        recorded = self.client.post("/privacy/consent/records", headers=head, json={
            "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "member_app", **self.correlation()})
        self.assertEqual(recorded.status_code, 201, recorded.text)

    def test_the_subject_recorded_is_the_session_and_not_what_the_caller_asked_for(self):
        """A caller holding only `privacy.consent.record` cannot file consent for anyone else.

        This is the shape MOD-008's review found twice: a request field that names the thing
        the permission is about, accepted as given. A consent record is insert-only, so a
        fabricated one -- "this named person signed a liability waiver" -- cannot be removed
        afterwards by anybody, which is what makes believing the caller here expensive.
        """
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        token = self.grant(tenant_id, ["privacy.consent.record", "privacy.consent.read"])
        head = self.headers(tenant_id, token)
        someone_else = str(uuid.uuid4())
        refused = self.client.post("/privacy/consent/records", headers=head, json={
            "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "staff_entry", "subject_id": someone_else, **self.correlation()})
        self.assertEqual(refused.status_code, 403, refused.text)

        owner = self.headers(tenant_id)
        history = self.client.get("/privacy/consent/history", headers=owner,
                                  params={"subject_id": someone_else})
        self.assertEqual(history.json(), [], "the refusal must leave no record behind")

    def test_recording_for_somebody_else_needs_a_stepped_up_session_as_well(self):
        """`privacy.consent.record_on_behalf` is financial-class, so AAL 1 is not enough."""
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        token = self.grant(tenant_id, ["privacy.consent.record_on_behalf"])
        refused = self.client.post(
            "/privacy/consent/records", headers=self.headers(tenant_id, token), json={
                "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
                "source": "paper_import", "subject_id": str(uuid.uuid4()),
                **self.correlation()})
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_a_stepped_up_holder_may_record_for_somebody_else(self):
        """Staff importing a paper waiver is the case the second permission exists for."""
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        owner = self.headers(tenant_id)
        subject = str(uuid.uuid4())
        recorded = self.client.post("/privacy/consent/records", headers=owner, json={
            "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "paper_import", "subject_id": subject, **self.correlation()})
        self.assertEqual(recorded.status_code, 201, recorded.text)
        state = self.client.get("/privacy/consent/state", headers=owner,
                                params={"subject_id": subject})
        self.assertEqual(state.status_code, 200, state.text)
        waiver = next(c for c in state.json()["consents"] if c["consent_type"] == "waiver")
        self.assertTrue(waiver["granted"])
        self.assertFalse(waiver["stale"], "it was signed against the version in force")


class ReviewRegressionTests(PrivacyApiTestCase):
    """One test per defect an independent review of MOD-009 found, named for the attack.

    Three reviewers worked this change in parallel, and two of them found the legal-hold defect
    below independently. Every one of these passed a route-is-guarded check and a happy-path
    test before the review: each is a case where the control existed and did not cover the input
    that mattered.
    """

    def test_a_member_cannot_mint_a_guardian_for_their_own_minor_consent(self):
        """`requires_guardian` is the control that makes a minor's health consent valid.

        `consent_subject` charged the stronger permission for naming another *subject* and said
        nothing about naming another *guardian* -- which is the same kind of claim about a
        person who is not present, and the one that the guardian requirement rests on. There is
        no foreign key (the guardian is an identity in another plane) and the row is insert-only,
        so a 15-year-old satisfying it by typing a UUID could never be corrected.
        """
        tenant_id = self.tenant()
        self.fixture(tenant_id, consent_type="health", requires_guardian=True)
        head = self.headers(tenant_id, self.grant(tenant_id, ["privacy.consent.record"]))
        refused = self.client.post("/privacy/consent/records", headers=head, json={
            "consent_type": "health", "signed_at": "2026-06-01T10:00:00+00:00",
            "source": "member_app", "guardian_subject_id": str(uuid.uuid4()),
            **self.correlation()})
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_a_self_service_session_cannot_claim_a_paper_waiver(self):
        """`staff_entry` and `paper_import` assert that a signed document exists off-system and
        somebody keyed it in. With an `evidence_ref` of the caller's choosing, a member-app
        session wrote a row that reads as a scanned waiver nobody scanned."""
        tenant_id = self.tenant()
        self.fixture(tenant_id)
        head = self.headers(tenant_id, self.grant(tenant_id, ["privacy.consent.record"]))
        for source in ("staff_entry", "paper_import"):
            refused = self.client.post("/privacy/consent/records", headers=head, json={
                "consent_type": "waiver", "signed_at": "2026-06-01T10:00:00+00:00",
                "source": source, "evidence_ref": "scan/forged.pdf", **self.correlation()})
            self.assertEqual(refused.status_code, 403, f"{source}: {refused.text}")

    def test_a_hold_placed_after_the_legal_check_still_stops_the_erasure(self):
        """The one both reviewers found, and the one the whole module exists to prevent.

        Holds were consulted once, at the legal check. `ready` is durable with no expiry, so the
        window is however long an operator waits -- and litigation ordinarily starts *after* a
        request is queued. A correctly-placed preservation order was ignored and the erasure
        reported `completed`.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subject_id, _ = self.fresh_identity(tenant_id, "Late")
        request_id = self.walk_to_ready(tenant_id, subject_id)

        hold = self.client.post("/privacy/legal-holds", headers=owner, json={
            "subject_id": subject_id, "reason": "preservation order served after the check",
            "reference": "CASE-LATE", **self.correlation()})
        self.assertEqual(hold.status_code, 201, hold.text)

        refused = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=owner,
                                   json=self.correlation())
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["error"],
                         f"legal_hold:{hold.json()['hold_id']}")

        read = self.client.get(f"/privacy/requests/{request_id}", headers=owner)
        self.assertEqual(read.json()["status"], "ready", "the request is still answerable")
        self.assertEqual(read.json()["actions"], [], "and nothing was destroyed")

    def test_an_erasure_of_nobody_is_refused_rather_than_reported_complete(self):
        """`subject_id` has no foreign key -- it cannot, the planes are separate -- so an
        unresolvable id matched zero rows on every target, recorded `done / 0` for each, and
        completed. The realistic case is a caller supplying a `person_id` where an `identity_id`
        was meant: the controller then tells a live member their data is gone while every row
        stands. The `locate_by` defect one layer up.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        stranger = str(uuid.uuid4())
        request_id = self.walk_to_ready(tenant_id, stranger)

        refused = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=owner,
                                   json=self.correlation())
        self.assertEqual(refused.status_code, 404, refused.text)
        self.assertEqual(refused.json()["error"], "subject_not_found_in_the_identity_plane")
        read = self.client.get(f"/privacy/requests/{request_id}", headers=owner)
        self.assertEqual(read.json()["actions"], [])

    def test_an_access_request_is_refused_without_being_wedged(self):
        """Only a deletion has an executor. That refusal used to happen *after* the status was
        committed to `fulfilling`, whose only exits are `completed` and `refused` -- so trying
        to answer the commonest DSAR there is made it permanently unanswerable. A control that
        commits anything before it refuses is not a control.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subject_id, _ = self.fresh_identity(tenant_id, "Asker")
        request_id = self.walk_to_ready(tenant_id, subject_id, request_type="access")

        refused = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=owner,
                                   json=self.correlation())
        self.assertEqual(refused.status_code, 422, refused.text)
        read = self.client.get(f"/privacy/requests/{request_id}", headers=owner)
        self.assertEqual(read.json()["status"], "ready",
                         "the request stays where a human can still act on it")

    def test_a_malformed_id_is_a_refusal_not_a_database_exception(self):
        """Every id was a bare `str`, so a malformed one reached psycopg and came back as an
        uncaught `InvalidTextRepresentation` -- a 500 carrying a database error."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.get(
            "/privacy/consent/history", headers=owner,
            params={"subject_id": "not-a-uuid"}).status_code, 422)
        self.assertEqual(self.client.get(
            "/privacy/requests/not-a-uuid", headers=owner).status_code, 422)
        self.assertEqual(self.client.post(
            "/privacy/legal-holds", headers=owner,
            json={"subject_id": "not-a-uuid", "reason": "r", "reference": "R",
                  **self.correlation()}).status_code, 422)

    def test_releasing_a_hold_records_who_did_it(self):
        """The single act that un-blocks destruction of preserved evidence, and it recorded no
        actor anywhere in the system: `veyro_cp_app` holds nothing in `iam`, so MOD-008's audit
        chain is out of reach and the row was the only possible record."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        hold = self.client.post("/privacy/legal-holds", headers=owner, json={
            "reason": "investigation", "reference": "CASE-X", **self.correlation()})
        released = self.client.post(
            f"/privacy/legal-holds/{hold.json()['hold_id']}/release", headers=owner,
            json={"release_reason": "closed", **self.correlation()})
        self.assertEqual(released.status_code, 200, released.text)
        listed = self.client.get("/privacy/legal-holds", headers=owner,
                                 params={"include_released": True}).json()
        self.assertEqual(listed[0]["released_by"], released.json()["released_by"])
        self.assertTrue(listed[0]["released_by"])

    def test_the_plan_names_the_mechanism_the_executor_will_use(self):
        """The plan is the artefact somebody reads before approving an erasure. It derived the
        mechanism from the request type, so it advertised `delete` for all seven reachable
        targets while the executor anonymized every one."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subject_id, _ = self.fresh_identity(tenant_id, "Planned")
        request_id = self.walk_to_ready(tenant_id, subject_id)
        steps = self.client.get(f"/privacy/requests/{request_id}/plan",
                                headers=owner).json()["steps"]
        done = {s["mechanism"] for s in steps if s["expected"] == "done"}
        self.assertNotIn("delete", done,
                         "nothing in this build deletes; every reachable target is anonymized")
        self.assertTrue(done <= {"anonymize", "covered"}, done)


class PrivacyLeastPrivilegeTests(PrivacyApiTestCase):
    def test_a_consent_reader_cannot_place_a_legal_hold(self):
        """A hold suspends deletion across the tenant; reading consent must not reach it."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["privacy.consent.read"]))
        refused = self.client.post("/privacy/legal-holds", headers=head, json={
            "reason": "none", "reference": "X", **self.correlation()})
        self.assertEqual(refused.status_code, 403)

    def test_opening_a_request_does_not_confer_fulfilling_one(self):
        """Opening is routine -- a member asks. Fulfilling destroys data and is not."""
        tenant_id = self.tenant()
        subject = str(uuid.uuid4())
        head = self.headers(tenant_id, self.grant(
            tenant_id, ["privacy.dsar.open", "privacy.dsar.read"]))
        opened = self.client.post("/privacy/requests", headers=head, json={
            "subject_id": subject, "request_type": "access", "response_days": 30,
            **self.correlation()})
        self.assertEqual(opened.status_code, 201, opened.text)
        request_id = opened.json()["request_id"]
        refused = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=head,
                                   json=self.correlation())
        self.assertEqual(refused.status_code, 403)

    def test_a_retention_reader_cannot_shorten_a_retention_period(self):
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["privacy.retention.read"]))
        self.assertEqual(self.client.get("/privacy/retention", headers=head).status_code, 200)
        refused = self.client.post("/privacy/retention", headers=head, json={
            "resource_type": "consent_record", "data_class": "confidential",
            "retention_days": 0, "legal_basis": "none", "region": "eu-west",
            **self.correlation()})
        self.assertEqual(refused.status_code, 403)

    def test_recording_an_incident_works_without_a_step_up(self):
        """Deliberate: the incident may be that authentication is unavailable."""
        tenant_id = self.tenant()
        head = self.headers(tenant_id, self.grant(tenant_id, ["privacy.incident.record"]))
        recorded = self.client.post("/privacy/incidents", headers=head, json={
            "severity": "high", "category": "access_anomaly",
            "summary": "Repeated failed logins", "detected_at": "2026-06-01T10:00:00+00:00",
            "personal_data_involved": "unknown", **self.correlation()})
        self.assertEqual(recorded.status_code, 201, recorded.text)


class DsarWorkflowOverHttpTests(PrivacyApiTestCase):
    def test_the_whole_deletion_workflow_in_order(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subject_id, _ = self.fresh_identity(tenant_id, "Subject")

        opened = self.client.post("/privacy/requests", headers=owner, json={
            "subject_id": subject_id, "request_type": "deletion", "response_days": 30,
            **self.correlation()})
        self.assertEqual(opened.status_code, 201, opened.text)
        request_id = opened.json()["request_id"]
        self.assertEqual(opened.json()["status"], "received")

        # Fulfilling before either gate is refused, and refused for the first missing gate.
        early = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=owner,
                                 json=self.correlation())
        self.assertEqual(early.status_code, 409, early.text)
        self.assertEqual(early.json()["error"], "identity_not_verified")

        for step, expected in (("identity-check", "identity_pending"),
                               ("verify-identity", "legal_pending"),
                               ("legal-check", "ready")):
            moved = self.client.post(f"/privacy/requests/{request_id}/{step}", headers=owner,
                                     json=self.correlation())
            self.assertEqual(moved.status_code, 200, moved.text)
            self.assertEqual(moved.json()["status"], expected)

        planned = self.client.get(f"/privacy/requests/{request_id}/plan", headers=owner)
        self.assertEqual(planned.status_code, 200, planned.text)
        self.assertFalse(planned.json()["erasure_is_complete"],
                         "the plan must say up front what this build cannot erase")
        self.assertTrue([s for s in planned.json()["steps"] if s["expected"] == "blocked"])

        fulfilled = self.client.post(f"/privacy/requests/{request_id}/fulfil", headers=owner,
                                     json=self.correlation())
        self.assertEqual(fulfilled.status_code, 200, fulfilled.text)
        body = fulfilled.json()
        self.assertEqual(body["status"], "completed")
        self.assertTrue(body["has_residue"])
        self.assertTrue(body["targets_blocked"])
        self.assertIsNotNone(body["residue_note"])

        read = self.client.get(f"/privacy/requests/{request_id}", headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["status"], "completed")
        self.assertTrue(read.json()["actions"], "the evidence trail is part of the request")

    def test_a_legal_hold_refuses_the_deletion_and_names_itself(self):
        """Erasure does not override a preservation order, and says which one stopped it."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        subject_id, _ = self.fresh_identity(tenant_id, "Held")

        hold = self.client.post("/privacy/legal-holds", headers=owner, json={
            "subject_id": subject_id, "reason": "injury claim under investigation",
            "reference": "CASE-2026-11", **self.correlation()})
        self.assertEqual(hold.status_code, 201, hold.text)

        opened = self.client.post("/privacy/requests", headers=owner, json={
            "subject_id": subject_id, "request_type": "deletion", "response_days": 30,
            **self.correlation()})
        request_id = opened.json()["request_id"]
        self.client.post(f"/privacy/requests/{request_id}/identity-check", headers=owner,
                         json=self.correlation())
        self.client.post(f"/privacy/requests/{request_id}/verify-identity", headers=owner,
                         json=self.correlation())
        checked = self.client.post(f"/privacy/requests/{request_id}/legal-check", headers=owner,
                                   json=self.correlation())
        self.assertEqual(checked.status_code, 200, checked.text)
        self.assertEqual(checked.json()["status"], "refused")
        self.assertEqual(checked.json()["blocking_hold_ids"], [hold.json()["hold_id"]])

        # Released, the same subject's next request proceeds -- and the hold is still on file.
        released = self.client.post(
            f"/privacy/legal-holds/{hold.json()['hold_id']}/release", headers=owner,
            json={"release_reason": "claim settled", **self.correlation()})
        self.assertEqual(released.status_code, 200, released.text)
        holds = self.client.get("/privacy/legal-holds", headers=owner,
                                params={"include_released": True})
        self.assertEqual([h["hold_id"] for h in holds.json()], [hold.json()["hold_id"]])
        self.assertEqual(holds.json()[0]["release_reason"], "claim settled")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
