"""MOD-009 service tests against a real PostgreSQL across both planes.

The claim this module makes is that a deletion request erases what it says it erases and leaves
what it says it leaves. That is a claim about rows, so these are integration tests: a suite with
a mocked connection would pass while the UPDATE did nothing at all, which is precisely the defect
the registry exists to prevent.

The erasure test is the centre of the suite. It registers a real identity through MOD-007, runs a
deletion through MOD-009, and then reads the identity row back to check that the contact columns
are gone -- rather than trusting the evidence row that says they are.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.db import tenant_scope
from app.errors import Conflict, InvalidRequest
from app.identity import service as identity
from app.privacy import service as privacy
from tests.support import GatedApiTestCase

NOW = datetime.now(UTC)
#: A stand-in staff actor. These suites do not go through HTTP, so no session supplies
#: one; the routes pass `session["identity_id"]`.
ACTOR = "33333333-3333-4333-8333-333333333333"


class PrivacyServiceTestCase(GatedApiTestCase):
    """Service-level, so it does not pay for an HTTP round trip and a gate on every call."""

    def subject(self, tenant_id: str) -> str:
        created = identity.register_identity(
            self._identity_pool, tenant_id, display_name="Subject",
            email=f"subject-{uuid.uuid4().hex[:10]}@acme.test", password=self.PASSWORD,
            correlation_id=str(uuid.uuid4()),
        )
        return str(created["identity_id"])

    def purpose(self, tenant_id: str, code: str = "membership") -> str:
        return privacy.register_purpose(
            self._tenant_pool, tenant_id, purpose_code=code,
            description="Running the member's gym membership", lawful_basis="contract",
            controller_role="processor", data_classes=["confidential"],
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )["purpose_id"]

    def consent_type(self, tenant_id: str, kind: str = "marketing", **kw) -> str:
        definition = privacy.define_consent(
            self._tenant_pool, tenant_id, consent_type=kind,
            purpose_id=self.purpose(tenant_id, f"p.{uuid.uuid4().hex[:6]}"),
            actor_id=ACTOR, correlation_id=str(uuid.uuid4()), **kw,
        )
        privacy.publish_consent_version(
            self._tenant_pool, tenant_id, consent_type=kind, language="en",
            document_ref="s3://docs/v1", document_hash="b" * 64,
            effective_from=NOW - timedelta(days=10), actor_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
        )
        return str(definition["definition_id"])


class PurposeTests(PrivacyServiceTestCase):
    def test_a_purpose_records_its_basis_and_its_controller_role(self):
        tenant_id = self.tenant()
        registered = privacy.register_purpose(
            self._tenant_pool, tenant_id, purpose_code="security.monitoring",
            description="Detecting account takeover", lawful_basis="legitimate_interest",
            controller_role="controller", data_classes=["restricted"],
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        self.assertEqual(registered["controller_role"], "controller")

    def test_an_unknown_data_class_is_refused_before_the_insert(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            privacy.register_purpose(
                self._tenant_pool, tenant_id, purpose_code="x.y", description="d",
                lawful_basis="consent", controller_role="processor",
                data_classes=["top_secret"], actor_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
            )

    def test_an_invented_lawful_basis_is_refused_by_the_database(self):
        """The six are Jordan PDPL's, not GDPR's; a seventh would be inventing the law."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            privacy.register_purpose(
                self._tenant_pool, tenant_id, purpose_code="x.y", description="d",
                lawful_basis="because_we_want_to", controller_role="processor",
                data_classes=["internal"], actor_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
            )

    def test_a_retired_code_can_be_registered_again(self):
        """A new lawful basis for the same activity is a new purpose, and the old consent that
        cited the old one must still resolve."""
        tenant_id = self.tenant()
        first = self.purpose(tenant_id, "marketing.email")
        privacy.retire_purpose(self._tenant_pool, tenant_id, purpose_id=first,
                                 actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        second = self.purpose(tenant_id, "marketing.email")
        self.assertNotEqual(first, second)

    def test_a_live_code_cannot_be_registered_twice(self):
        tenant_id = self.tenant()
        self.purpose(tenant_id, "membership")
        with self.assertRaises(Conflict):
            self.purpose(tenant_id, "membership")


class ConsentTests(PrivacyServiceTestCase):
    def test_a_grant_binds_the_version_in_force(self):
        tenant_id = self.tenant()
        self.consent_type(tenant_id, "marketing")
        subject = str(uuid.uuid4())
        granted = privacy.register_consent(
            self._tenant_pool, tenant_id, subject_id=subject, consent_type="marketing",
            language="en", signed_at=NOW, source="member_app",
            correlation_id=str(uuid.uuid4()),
        )
        self.assertEqual(granted["action"], "granted")

        state = privacy.consent_state(self._tenant_pool, tenant_id, subject_id=subject)
        marketing = [c for c in state["consents"] if c["consent_type"] == "marketing"][0]
        self.assertTrue(marketing["granted"])
        self.assertFalse(marketing["stale"])

    def test_publishing_a_new_version_makes_an_existing_grant_stale_not_absent(self):
        tenant_id = self.tenant()
        self.consent_type(tenant_id, "privacy")
        subject = str(uuid.uuid4())
        privacy.register_consent(
            self._tenant_pool, tenant_id, subject_id=subject, consent_type="privacy",
            language="en", signed_at=NOW, source="web", correlation_id=str(uuid.uuid4()),
        )
        privacy.publish_consent_version(
            self._tenant_pool, tenant_id, consent_type="privacy", language="en",
            document_ref="s3://docs/v2", document_hash="c" * 64,
            effective_from=NOW - timedelta(minutes=1), actor_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
        )
        state = privacy.consent_state(self._tenant_pool, tenant_id, subject_id=subject)
        row = [c for c in state["consents"] if c["consent_type"] == "privacy"][0]
        self.assertTrue(row["granted"], "republishing does not erase a real agreement")
        self.assertTrue(row["stale"], "but it does not extend to the new document either")
        self.assertEqual([o["reason"] for o in state["outstanding"]], ["stale"])

    def test_a_withdrawal_is_a_new_row_and_the_grant_survives_in_the_history(self):
        tenant_id = self.tenant()
        self.consent_type(tenant_id, "marketing")
        subject = str(uuid.uuid4())
        privacy.register_consent(
            self._tenant_pool, tenant_id, subject_id=subject, consent_type="marketing",
            language="en", signed_at=NOW - timedelta(days=2), source="web",
            correlation_id=str(uuid.uuid4()),
        )
        privacy.withdraw_consent(
            self._tenant_pool, tenant_id, subject_id=subject, consent_type="marketing",
            signed_at=NOW, source="member_app", correlation_id=str(uuid.uuid4()),
        )
        history = privacy.consent_history(self._tenant_pool, tenant_id, subject_id=subject)
        self.assertEqual([h["action"] for h in history], ["granted", "withdrawn"])

        state = privacy.consent_state(self._tenant_pool, tenant_id, subject_id=subject)
        self.assertFalse([c for c in state["consents"]
                          if c["consent_type"] == "marketing"][0]["granted"])

    def test_a_consent_record_cannot_be_updated_or_deleted_by_the_runtime_role(self):
        """The grant is insert-only in the privilege layer, not only by convention."""
        tenant_id = self.tenant()
        self.consent_type(tenant_id, "marketing")
        subject = str(uuid.uuid4())
        privacy.register_consent(
            self._tenant_pool, tenant_id, subject_id=subject, consent_type="marketing",
            language="en", signed_at=NOW, source="web", correlation_id=str(uuid.uuid4()),
        )
        import psycopg

        for statement in ("UPDATE plt01.sec_consent_records SET action = 'withdrawn'",
                          "DELETE FROM plt01.sec_consent_records"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=statement):
                with tenant_scope(self._tenant_pool, tenant_id) as conn:
                    conn.execute(statement)

    def test_a_guardian_consent_without_a_guardian_is_refused(self):
        tenant_id = self.tenant()
        self.consent_type(tenant_id, "health", requires_guardian=True)
        with self.assertRaises(InvalidRequest) as raised:
            privacy.register_consent(
                self._tenant_pool, tenant_id, subject_id=str(uuid.uuid4()),
                consent_type="health", language="en", signed_at=NOW, source="staff_entry",
                correlation_id=str(uuid.uuid4()),
            )
        self.assertEqual(raised.exception.args[0], "guardian_required")

    def test_a_non_withdrawable_consent_refuses_withdrawal(self):
        tenant_id = self.tenant()
        self.consent_type(tenant_id, "terms", withdrawable=False)
        subject = str(uuid.uuid4())
        privacy.register_consent(
            self._tenant_pool, tenant_id, subject_id=subject, consent_type="terms",
            language="en", signed_at=NOW, source="web", correlation_id=str(uuid.uuid4()),
        )
        with self.assertRaises(Conflict):
            privacy.withdraw_consent(
                self._tenant_pool, tenant_id, subject_id=subject, consent_type="terms",
                signed_at=NOW, source="web", correlation_id=str(uuid.uuid4()),
            )

    def test_consent_does_not_leak_between_tenants(self):
        first, second = self.tenant(), self.tenant()
        self.consent_type(first, "marketing")
        subject = str(uuid.uuid4())
        privacy.register_consent(
            self._tenant_pool, first, subject_id=subject, consent_type="marketing",
            language="en", signed_at=NOW, source="web", correlation_id=str(uuid.uuid4()),
        )
        self.assertEqual(
            privacy.consent_history(self._tenant_pool, second, subject_id=subject), [],
            "the same subject id in another tenant must read nothing",
        )


class LegalHoldTests(PrivacyServiceTestCase):
    def test_a_hold_is_released_never_deleted(self):
        tenant_id = self.tenant()
        hold = privacy.place_legal_hold(
            self._tenant_pool, tenant_id, reason="litigation", reference="CASE-7",
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        privacy.release_legal_hold(self._tenant_pool, tenant_id, hold_id=hold["hold_id"],
                                   release_reason="matter closed", actor_id=ACTOR,
                                   correlation_id=str(uuid.uuid4()))
        everything = privacy.list_legal_holds(self._tenant_pool, tenant_id,
                                              include_released=True)
        self.assertEqual(len(everything), 1)
        self.assertIsNotNone(everything[0]["released_at"])
        self.assertEqual(everything[0]["release_reason"], "matter closed")

    def test_a_release_without_a_reason_is_refused(self):
        tenant_id = self.tenant()
        hold = privacy.place_legal_hold(
            self._tenant_pool, tenant_id, reason="r", reference="REF",
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        with self.assertRaises(InvalidRequest):
            privacy.release_legal_hold(self._tenant_pool, tenant_id,
                                       hold_id=hold["hold_id"], release_reason="   ",
                                       actor_id=ACTOR,
                                       correlation_id=str(uuid.uuid4()))

    def test_a_hold_cannot_be_deleted_by_the_runtime_role(self):
        tenant_id = self.tenant()
        privacy.place_legal_hold(
            self._tenant_pool, tenant_id, reason="r", reference="REF",
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        import psycopg

        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                conn.execute("DELETE FROM plt01.sec_legal_holds")


class DsarWorkflowTests(PrivacyServiceTestCase):
    def open_deletion(self, tenant_id: str, subject_id: str) -> str:
        opened = privacy.open_dsar(
            self._tenant_pool, tenant_id, subject_id=subject_id, request_type="deletion",
            response_days=30, actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        return str(opened["request_id"])

    def advance_to_ready(self, tenant_id: str, request_id: str) -> dict:
        privacy.start_dsar_identity_check(self._tenant_pool, tenant_id, request_id=request_id)
        privacy.verify_dsar_identity(self._tenant_pool, tenant_id, request_id=request_id,
                                     actor_id=str(uuid.uuid4()))
        return privacy.check_dsar_legal(self._tenant_pool, tenant_id, request_id=request_id,
                                        actor_id=str(uuid.uuid4()))

    def test_fulfilment_is_refused_until_both_gates_have_passed(self):
        tenant_id = self.tenant()
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        with self.assertRaises(Conflict):
            privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                identity_pool=self._identity_pool)

        privacy.start_dsar_identity_check(self._tenant_pool, tenant_id, request_id=request_id)
        privacy.verify_dsar_identity(self._tenant_pool, tenant_id, request_id=request_id,
                                     actor_id=str(uuid.uuid4()))
        with self.assertRaises(Conflict) as raised:
            privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                identity_pool=self._identity_pool)
        self.assertEqual(raised.exception.args[0], "legal_check_not_done")

    def test_identity_verification_comes_before_the_legal_check(self):
        tenant_id = self.tenant()
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        privacy.start_dsar_identity_check(self._tenant_pool, tenant_id, request_id=request_id)
        with self.assertRaises(Conflict):
            privacy.check_dsar_legal(self._tenant_pool, tenant_id, request_id=request_id,
                                     actor_id=str(uuid.uuid4()))

    def test_a_legal_hold_refuses_the_deletion_and_names_the_hold(self):
        """The uncomfortable case: erasure does not override a preservation order."""
        tenant_id = self.tenant()
        subject = self.subject(tenant_id)
        hold = privacy.place_legal_hold(
            self._tenant_pool, tenant_id, subject_id=subject, reason="litigation",
            reference="CASE-9", actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        request_id = self.open_deletion(tenant_id, subject)
        outcome = self.advance_to_ready(tenant_id, request_id)
        self.assertEqual(outcome["status"], "refused")
        self.assertEqual(outcome["reason"], "legal_hold")
        self.assertEqual(outcome["blocking_hold_ids"], [hold["hold_id"]])

        with self.assertRaises(Conflict):
            privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                identity_pool=self._identity_pool)

    def test_a_hold_on_another_subject_does_not_block_this_one(self):
        tenant_id = self.tenant()
        privacy.place_legal_hold(
            self._tenant_pool, tenant_id, subject_id=str(uuid.uuid4()), reason="other matter",
            reference="CASE-1", actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        self.assertEqual(self.advance_to_ready(tenant_id, request_id)["status"], "ready")

    def test_the_plan_discloses_what_will_survive_before_anything_runs(self):
        tenant_id = self.tenant()
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        plan = privacy.plan_dsar(self._tenant_pool, tenant_id, request_id=request_id)
        self.assertFalse(plan["erasure_is_complete"])
        blocked = [s for s in plan["steps"] if s["expected"] == "blocked"]
        self.assertTrue(blocked, "the plan must show the residue, not only the outcome")
        self.assertIn("plt01.bil_usage_records.actor_id", [s["target"] for s in blocked])

    # -------------------------------------------------------------- the erasure itself

    def test_a_deletion_actually_erases_the_identity_and_says_what_it_could_not(self):
        """The centre of the suite: the rows are read back rather than the evidence believed."""
        tenant_id = self.tenant()
        email = f"erase-{uuid.uuid4().hex[:10]}@acme.test"
        created = identity.register_identity(
            self._identity_pool, tenant_id, display_name="To Be Erased", email=email,
            password=self.PASSWORD, correlation_id=str(uuid.uuid4()),
        )
        subject = str(created["identity_id"])
        identity.authenticate(
            self._identity_pool, tenant_id, identifier=email, password=self.PASSWORD,
            correlation_id=str(uuid.uuid4()), device_fingerprint=f"d-{uuid.uuid4().hex[:8]}",
        )

        before = self.read_identity(tenant_id, subject)
        self.assertEqual(before["email_normalized"], email.lower())
        self.assertEqual(before["display_name"], "To Be Erased")

        request_id = self.open_deletion(tenant_id, subject)
        self.assertEqual(self.advance_to_ready(tenant_id, request_id)["status"], "ready")
        settled = privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                      identity_pool=self._identity_pool)

        self.assertEqual(settled["status"], "completed")
        self.assertTrue(settled["complete"])
        self.assertTrue(settled["has_residue"])
        self.assertIn("insert-only", str(settled["residue_note"]))

        after = self.read_identity(tenant_id, subject)
        self.assertTrue(str(after["email_normalized"]).startswith("erased:"),
                        "the real address must be gone, replaced by a per-row tombstone")
        self.assertNotIn("@", str(after["email_normalized"]))
        self.assertIsNone(after["phone_normalized"])
        self.assertEqual(after["display_name"], "erased")
        self.assertNotEqual(after["person_id"], before["person_id"],
                            "the cross-tenant link must be severed, not merely emptied")

        self.assertTrue(self.credential_digests(tenant_id, subject),
                        "the credential rows survive; it is their contents that must not")
        self.assertTrue(all(f.startswith("erased:")
                            for f in self.device_fingerprints(tenant_id, subject)))

    def test_the_erased_subject_can_no_longer_authenticate(self):
        """The erasure is not cosmetic: the credential it overwrote was a working one."""
        tenant_id = self.tenant()
        email = f"erase-{uuid.uuid4().hex[:10]}@acme.test"
        created = identity.register_identity(
            self._identity_pool, tenant_id, display_name="Gone", email=email,
            password=self.PASSWORD, correlation_id=str(uuid.uuid4()),
        )
        subject = str(created["identity_id"])
        request_id = self.open_deletion(tenant_id, subject)
        self.advance_to_ready(tenant_id, request_id)
        privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                            identity_pool=self._identity_pool)

        from app.identity.service import AuthenticationFailed

        with self.assertRaises(AuthenticationFailed):
            identity.authenticate(
                self._identity_pool, tenant_id, identifier=email, password=self.PASSWORD,
                correlation_id=str(uuid.uuid4()), device_fingerprint="after-erasure",
            )

    def test_every_target_leaves_one_evidence_row_including_the_blocked_ones(self):
        tenant_id = self.tenant()
        subject = self.subject(tenant_id)
        request_id = self.open_deletion(tenant_id, subject)
        self.advance_to_ready(tenant_id, request_id)
        privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                            identity_pool=self._identity_pool)

        read = privacy.get_dsar(self._tenant_pool, tenant_id, request_id=request_id)
        outcomes = {a["outcome"] for a in read["actions"]}
        self.assertEqual(outcomes, {"done", "blocked"})
        self.assertTrue(all(len(a["evidence_hash"]) == 64 for a in read["actions"]))
        self.assertEqual(read["status"], "completed")

    def test_without_the_identity_plane_nothing_is_written_at_all(self):
        """A target that was never attempted must not read as one that was -- and the request
        must stay where it was, not move to a state it cannot leave.

        This used to record a `failed` action per target and leave the request in `fulfilling`,
        whose only exits are `completed` and `refused`. A transient outage on the identity plane
        therefore made a valid erasure request permanently unanswerable. It now refuses before
        writing anything, so the caller fixes the outage and calls again.
        """
        tenant_id = self.tenant()
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        self.advance_to_ready(tenant_id, request_id)
        with self.assertRaises(InvalidRequest) as caught:
            privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                identity_pool=None)
        self.assertEqual(caught.exception.code, "identity_plane_not_available")

        read = privacy.get_dsar(self._tenant_pool, tenant_id, request_id=request_id)
        self.assertEqual(read["status"], "ready", "the request is still answerable")
        self.assertEqual(read["actions"], [], "nothing was recorded")

        # ...and the retry, once the plane is back, completes it.
        settled = privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                      identity_pool=self._identity_pool)
        self.assertEqual(settled["status"], "completed")

    def test_an_interrupted_run_can_be_resumed(self):
        """`fulfilling` used to be a dead end: the only transitions out are `completed` and
        `refused`, and a retry was refused because the status was not `ready`. Re-running is
        safe -- every clear expression is idempotent or writes a fresh tombstone over one
        already written -- and the evidence trail is insert-only, so both attempts stay visible.
        """
        tenant_id = self.tenant()
        subject_id = self.subject(tenant_id)
        request_id = self.open_deletion(tenant_id, subject_id)
        self.advance_to_ready(tenant_id, request_id)
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            conn.execute("UPDATE plt01.sec_dsar_requests SET status = 'fulfilling'"
                         " WHERE request_id = %s", (request_id,))

        settled = privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                                      identity_pool=self._identity_pool)
        self.assertEqual(settled["status"], "completed")

    def test_an_evidence_row_cannot_be_updated_or_deleted(self):
        tenant_id = self.tenant()
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        self.advance_to_ready(tenant_id, request_id)
        privacy.fulfil_dsar(self._tenant_pool, tenant_id, request_id=request_id,
                            identity_pool=self._identity_pool)
        import psycopg

        for statement in ("UPDATE plt01.sec_dsar_actions SET rows_affected = 0",
                          "DELETE FROM plt01.sec_dsar_actions"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=statement):
                with tenant_scope(self._tenant_pool, tenant_id) as conn:
                    conn.execute(statement)

    def test_a_request_type_and_subject_cannot_be_changed_after_it_is_opened(self):
        """The column-level UPDATE grant is what stops a deletion becoming an access request."""
        tenant_id = self.tenant()
        request_id = self.open_deletion(tenant_id, self.subject(tenant_id))
        import psycopg

        for statement in ("UPDATE plt01.sec_dsar_requests SET request_type = 'access'",
                          "UPDATE plt01.sec_dsar_requests SET subject_id = gen_random_uuid()",
                          "UPDATE plt01.sec_dsar_requests SET due_at = now()"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=statement):
                with tenant_scope(self._tenant_pool, tenant_id) as conn:
                    conn.execute(statement)
        self.assertEqual(
            privacy.get_dsar(self._tenant_pool, tenant_id,
                             request_id=request_id)["request_type"], "deletion")

    # ------------------------------------------------------------------------- helpers

    def read_identity(self, tenant_id: str, identity_id: str) -> dict:
        with tenant_scope(self._identity_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT email_normalized, phone_normalized, display_name, person_id"
                " FROM iam.identities WHERE identity_id = %s",
                (identity_id,),
            ).fetchone()
        assert row is not None
        return {"email_normalized": row[0], "phone_normalized": row[1],
                "display_name": row[2], "person_id": str(row[3])}

    def credential_digests(self, tenant_id: str, identity_id: str) -> set[str]:
        with tenant_scope(self._identity_pool, tenant_id) as conn:
            rows = conn.execute(
                "SELECT secret_hash FROM iam.credentials WHERE identity_id = %s",
                (identity_id,),
            ).fetchall()
        return {r[0] for r in rows}

    def device_fingerprints(self, tenant_id: str, identity_id: str) -> list[str]:
        with tenant_scope(self._identity_pool, tenant_id) as conn:
            rows = conn.execute(
                "SELECT fingerprint FROM iam.devices WHERE identity_id = %s",
                (identity_id,),
            ).fetchall()
        return [r[0] for r in rows]


class IncidentTests(PrivacyServiceTestCase):
    def test_an_incident_records_whether_personal_data_was_involved(self):
        tenant_id = self.tenant()
        recorded = privacy.record_incident(
            self._tenant_pool, tenant_id, severity="high", category="credential_stuffing",
            summary="Repeated failed logins from one range", detected_at=NOW,
            personal_data_involved="unknown", actor_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
        )
        self.assertEqual(recorded["personal_data_involved"], "unknown")

    def test_a_correction_is_a_new_row_naming_the_earlier_one(self):
        tenant_id = self.tenant()
        first = privacy.record_incident(
            self._tenant_pool, tenant_id, severity="low", category="noise",
            summary="Probably nothing", detected_at=NOW, personal_data_involved="no",
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        )
        second = privacy.record_incident(
            self._tenant_pool, tenant_id, severity="critical", category="data_exposure",
            summary="It was something", detected_at=NOW, personal_data_involved="yes",
            actor_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
            supersedes_incident_id=first["incident_id"],
        )
        listed = privacy.list_incidents(self._tenant_pool, tenant_id)
        self.assertEqual(len(listed), 2, "the first record survives its own correction")
        superseding = [i for i in listed if i["incident_id"] == second["incident_id"]][0]
        self.assertEqual(superseding["supersedes_incident_id"], first["incident_id"])

    def test_an_incident_cannot_be_edited_by_the_party_responding_to_it(self):
        tenant_id = self.tenant()
        privacy.record_incident(
            self._tenant_pool, tenant_id, severity="low", category="noise", summary="s",
            detected_at=NOW, personal_data_involved="no", actor_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
        )
        import psycopg

        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with tenant_scope(self._tenant_pool, tenant_id) as conn:
                conn.execute("UPDATE plt01.sec_incidents SET severity = 'low'")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
