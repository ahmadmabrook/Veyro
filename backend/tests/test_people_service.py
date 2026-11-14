"""MOD-014 PPL-01 service tests: people, profiles, merge, timeline and the masking.

The masking tests are the ones to read first. `Decision.mask` was computed on every allowed
decision from MOD-008 to MOD-013 and applied by nothing; these are the first assertions in the
build that a caller without a class's permission gets `***` rather than the value.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, date, datetime, timedelta

from app.authorization.service import Forbidden
from app.db import tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.people import service as people
from app.people import visibility
from tests.support import GatedApiTestCase

ACTOR = "33333333-3333-4333-8333-333333333333"
OTHER = "44444444-4444-4444-8444-444444444444"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)

#: What a caller holding every people permission can read. The 360 and profile reads take a
#: permission set, so a test that passed `set()` would be testing the masking rather than the
#: behaviour -- and one that passed everything would never see a mask at all.
STAFF = {"people.person.read", "people.person.write", "member.profile.read"}
STAFF_FULL = STAFF | {"member.identity.read", "member.finance.read"}


class PeopleTestCase(GatedApiTestCase):
    def correlate(self) -> str:
        return str(uuid.uuid4())

    def person(self, tenant_id: str, **kwargs: object) -> str:
        body: dict = {"legal_name": f"Person {uuid.uuid4().hex[:6]}"}
        body.update(kwargs)
        return str(people.create_person(
            self._tenant_pool, tenant_id, actor_id=ACTOR,
            correlation_id=self.correlate(), **body)["person_id"])

    def outbox(self, tenant_id: str, event_type: str) -> list[dict]:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            rows = conn.execute(
                "SELECT payload FROM plt01.evt_outbox WHERE event_type = %s"
                " ORDER BY occurred_at, event_id", (event_type,)
            ).fetchall()
        return [r[0] for r in rows]


class PersonTests(PeopleTestCase):
    def test_a_person_is_created_with_their_contact_points(self):
        """A person with no way to reach them is a record nobody can use, and two commands
        would leave a window where the detector sees somebody with no signals."""
        tenant_id = self.tenant()
        created = people.create_person(
            self._tenant_pool, tenant_id, legal_name="Ahmad Mabrouk",
            preferred_name="Ahmad", date_of_birth=date(1990, 5, 1),
            contacts=[{"kind": "email", "value": "Ahmad@Acme.test", "is_primary": True},
                      {"kind": "phone", "value": "+962 (79) 000-0000"}],
            actor_id=ACTOR, correlation_id=self.correlate())
        read = people.get_person(
            self._tenant_pool, tenant_id, created["person_id"],
            masked_fields=(), held_permissions=STAFF_FULL)
        self.assertEqual(read["preferred_name"], "Ahmad")
        values = {c["kind"]: c["value_normalized"] for c in read["contact_points"]}
        # Normalized by MOD-007's own functions, which is what makes a duplicate findable.
        self.assertEqual(values["email"], "ahmad@acme.test")
        self.assertEqual(values["phone"], "+962790000000")

    def test_a_birth_date_in_the_future_is_refused_before_the_constraint(self):
        """A 422 naming the field beats a 500 from a constraint naming a column."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            people.create_person(
                self._tenant_pool, tenant_id, legal_name="Time Traveller",
                date_of_birth=(NOW + timedelta(days=365)).date(),
                actor_id=ACTOR, correlation_id=self.correlate(), at=NOW)

    def test_the_same_contact_twice_in_one_command_is_refused(self):
        tenant_id = self.tenant()
        with self.assertRaises(Conflict):
            people.create_person(
                self._tenant_pool, tenant_id, legal_name="Twice",
                contacts=[{"kind": "email", "value": "a@b.c"},
                          {"kind": "email", "value": "A@B.C"}],
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_an_update_needs_the_version_it_read(self):
        """Two front-desk staff editing one profile is the ordinary case, and last-write-wins
        discards whichever finished first."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id, legal_name="Before")
        with self.assertRaises(Conflict):
            people.update_person(
                self._tenant_pool, tenant_id, person_id, expected_version=99,
                legal_name="After", actor_id=ACTOR, correlation_id=self.correlate())
        updated = people.update_person(
            self._tenant_pool, tenant_id, person_id, expected_version=1,
            legal_name="After", actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["changed_fields"], ["legal_name"])

    def test_an_update_that_changes_nothing_is_refused(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id, legal_name="Same")
        with self.assertRaises(InvalidRequest):
            people.update_person(
                self._tenant_pool, tenant_id, person_id, expected_version=1,
                legal_name="Same", actor_id=ACTOR, correlation_id=self.correlate())

    def test_the_updated_event_names_the_fields_and_not_the_values(self):
        """An event naming the new value would put a legal name and a birth date into
        `evt_outbox.payload`, the store MOD-009's registry declares unreachable."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id, legal_name="Before")
        people.update_person(
            self._tenant_pool, tenant_id, person_id, expected_version=1,
            legal_name="Jane Secret", actor_id=ACTOR, correlation_id=self.correlate())
        payloads = self.outbox(tenant_id, "profile.updated")
        self.assertTrue(payloads)
        for payload in payloads:
            self.assertNotIn("Jane Secret", str(payload))
        self.assertIn("legal_name", payloads[0]["changed_fields"])

    def test_one_identity_signs_in_as_one_person(self):
        """Two would mean a login resolving to two member records, and every permission
        decision afterwards would be about an arbitrary one."""
        tenant_id = self.tenant()
        first = self.person(tenant_id)
        second = self.person(tenant_id)
        identity_id = str(uuid.uuid4())
        people.link_identity(
            self._tenant_pool, tenant_id, first, identity_id=identity_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.link_identity(
                self._tenant_pool, tenant_id, second, identity_id=identity_id,
                actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(
            people.person_of_identity(self._tenant_pool, tenant_id, identity_id=identity_id),
            first)

    def test_a_person_from_another_tenant_is_not_found(self):
        a, b = self.tenant(), self.tenant()
        person_id = self.person(a)
        with self.assertRaises(NotFound):
            people.get_person(self._tenant_pool, b, person_id, masked_fields=(),
                              held_permissions=STAFF_FULL)


class MaskingTests(PeopleTestCase):
    """The first read path in the build that applies MOD-008's computed mask."""

    def test_a_masked_field_comes_back_starred_rather_than_missing(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id, legal_name="Ahmad",
                                date_of_birth=date(1990, 5, 1))
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id,
            masked_fields=("date_of_birth",), held_permissions=STAFF_FULL)
        self.assertEqual(read["date_of_birth"], visibility.MASK)
        self.assertIn("date_of_birth", read)

    def test_a_mask_reaches_a_nested_contact_point(self):
        """A mask applied only at the top level is one a reader walks around by looking one
        level down, which is the shape of mistake this module exists to stop making."""
        tenant_id = self.tenant()
        person_id = self.person(
            tenant_id, contacts=[{"kind": "email", "value": "secret@acme.test"}])
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id,
            masked_fields=("value_raw", "value_normalized"), held_permissions=STAFF_FULL)
        for contact in read["contact_points"]:
            self.assertEqual(contact["value_raw"], visibility.MASK)
            self.assertEqual(contact["value_normalized"], visibility.MASK)

    def test_a_sensitive_custom_field_is_masked_by_its_own_classification(self):
        """MOD-008's catalogue is code and a custom field is a row, so the classification
        travels on the definition."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.define_custom_field(
            self._tenant_pool, tenant_id, field_key="passport", display_name="Passport",
            value_type="text", sensitivity="identity", actor_id=ACTOR,
            correlation_id=self.correlate())
        people.set_custom_field_value(
            self._tenant_pool, tenant_id, person_id, field_key="passport",
            value="X1234567", actor_id=ACTOR, correlation_id=self.correlate())
        without = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF)
        self.assertEqual(without["custom_fields"][0]["value"], visibility.MASK)
        self.assertTrue(without["custom_fields"][0]["redacted"])
        with_permission = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(with_permission["custom_fields"][0]["value"], "X1234567")

    def test_a_health_note_is_redacted_and_still_counted(self):
        """Telling a coach a member has no health notes when they have one is worse than
        telling them there is one they cannot read."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.record_note(
            self._tenant_pool, tenant_id, person_id, body="Recovering from a knee injury",
            note_class="health", actor_id=ACTOR, correlation_id=self.correlate())
        notes = people.list_notes(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["body"], visibility.MASK)
        self.assertTrue(notes[0]["redacted"])
        self.assertIn("member.health.read", notes[0]["redacted_because"])

    def test_a_general_note_rides_with_the_profile_read(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.record_note(
            self._tenant_pool, tenant_id, person_id, body="Asked about a locker",
            actor_id=ACTOR, correlation_id=self.correlate())
        notes = people.list_notes(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF)
        self.assertEqual(notes[0]["body"], "Asked about a locker")

    def test_a_sensitive_note_needs_the_identity_permission(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.record_note(
            self._tenant_pool, tenant_id, person_id, body="Argued with reception",
            note_class="sensitive", actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(
            people.list_notes(self._tenant_pool, tenant_id, person_id, masked_fields=(),
                              held_permissions=STAFF)[0]["body"],
            visibility.MASK)
        self.assertEqual(
            people.list_notes(self._tenant_pool, tenant_id, person_id, masked_fields=(),
                              held_permissions=STAFF_FULL)[0]["body"],
            "Argued with reception")

    def test_a_note_body_cannot_be_edited_only_withdrawn(self):
        """A note that could be edited is a note nobody can rely on in the dispute it exists
        for, so a correction is a new note and a retraction is a withdrawal."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        note = people.record_note(
            self._tenant_pool, tenant_id, person_id, body="Wrong person entirely",
            actor_id=ACTOR, correlation_id=self.correlate())
        people.withdraw_note(
            self._tenant_pool, tenant_id, note["note_id"], reason="wrong person",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(
            people.list_notes(self._tenant_pool, tenant_id, person_id, masked_fields=(),
                              held_permissions=STAFF), [])
        kept = people.list_notes(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF,
            include_withdrawn=True)
        self.assertEqual(kept[0]["body"], "Wrong person entirely")
        self.assertEqual(kept[0]["withdraw_reason"], "wrong person")
        with self.assertRaises(Conflict):
            people.withdraw_note(
                self._tenant_pool, tenant_id, note["note_id"], reason="again",
                actor_id=ACTOR, correlation_id=self.correlate())


class MinorTests(PeopleTestCase):
    def test_a_minors_record_needs_guardianship_or_staff_permission(self):
        """Paragraph 1372: guardianship and consent must be validated before exposing minor
        data."""
        tenant_id = self.tenant()
        child = self.person(tenant_id, legal_name="Laila",
                            date_of_birth=date(2015, 3, 4))
        parent = self.person(tenant_id, legal_name="Ahmad")
        stranger = self.person(tenant_id, legal_name="Nobody")
        # A caller who is a person in this tenant but not a guardian, and holds nothing.
        # **A 403, not a 409**: every other authorization refusal in this build is 403, and a
        # 409 told the caller their request conflicted with something rather than that they may
        # not make it. Both reviewers raised it.
        with self.assertRaises(Forbidden):
            people.get_person(self._tenant_pool, tenant_id, child, masked_fields=(),
                              held_permissions=set(), actor_person_id=stranger)
        people.add_relationship(
            self._tenant_pool, tenant_id, kind="guardian_dependent",
            from_person_id=parent, to_person_id=child, actor_id=ACTOR,
            correlation_id=self.correlate())
        read = people.get_person(
            self._tenant_pool, tenant_id, child, masked_fields=(),
            held_permissions=set(), actor_person_id=parent)
        self.assertTrue(read["is_minor"])
        self.assertEqual(read["guardianship"], "actor_is_a_recorded_guardian")

    def test_staff_can_serve_a_minor_at_the_desk(self):
        """A gym's staff have to be able to serve a fourteen-year-old; the guardian path is
        what makes a member-app caller reach only their own dependents."""
        tenant_id = self.tenant()
        child = self.person(tenant_id, date_of_birth=date(2015, 3, 4))
        read = people.get_person(
            self._tenant_pool, tenant_id, child, masked_fields=(),
            held_permissions=STAFF)
        self.assertEqual(read["guardianship"], "staff_profile_read")

    def test_an_undated_person_is_not_treated_as_a_minor(self):
        """Every undated lead would otherwise need a guardian before anybody could read them."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=set())
        self.assertFalse(read["is_minor"])
        self.assertEqual(read["guardianship"], "not_a_minor")


class LifecycleServiceTests(PeopleTestCase):
    def test_a_member_moves_through_the_lifecycle_and_publishes_each_move(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        created = people.create_member_profile(
            self._tenant_pool, tenant_id, person_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(created["lifecycle_state"], "lead")
        moved = people.change_member_lifecycle(
            self._tenant_pool, tenant_id, person_id, to_state="active",
            expected_version=created["version"], actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual((moved["from_state"], moved["to_state"]), ("lead", "active"))
        states = [(p["from_state"], p["to_state"])
                  for p in self.outbox(tenant_id, "member.lifecycle.changed")]
        self.assertIn(("none", "lead"), states)
        self.assertIn(("lead", "active"), states)

    def test_a_move_the_machine_does_not_admit_is_refused(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        created = people.create_member_profile(
            self._tenant_pool, tenant_id, person_id, lifecycle_state="active",
            actor_id=ACTOR, correlation_id=self.correlate())
        people.change_member_lifecycle(
            self._tenant_pool, tenant_id, person_id, to_state="former",
            expected_version=created["version"], reason="moved abroad", actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.change_member_lifecycle(
                self._tenant_pool, tenant_id, person_id, to_state="lead",
                expected_version=created["version"] + 1, actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_the_moves_that_take_something_away_state_a_reason(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        created = people.create_member_profile(
            self._tenant_pool, tenant_id, person_id, lifecycle_state="active",
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            people.change_member_lifecycle(
                self._tenant_pool, tenant_id, person_id, to_state="cancelled",
                expected_version=created["version"], actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_employment_ends_once(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        staff = people.upsert_staff_profile(
            self._tenant_pool, tenant_id, person_id, job_title="Coach", actor_id=ACTOR,
            correlation_id=self.correlate())
        people.end_staff_employment(
            self._tenant_pool, tenant_id, person_id, expected_version=staff["version"],
            ended_on=date(2026, 11, 1), actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.end_staff_employment(
                self._tenant_pool, tenant_id, person_id,
                expected_version=staff["version"] + 1, ended_on=date(2026, 12, 1),
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_one_member_number_belongs_to_one_member(self):
        tenant_id = self.tenant()
        first, second = self.person(tenant_id), self.person(tenant_id)
        people.create_member_profile(
            self._tenant_pool, tenant_id, first, member_number="M-1", actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.create_member_profile(
                self._tenant_pool, tenant_id, second, member_number="M-1", actor_id=ACTOR,
                correlation_id=self.correlate())


class RelationshipTests(PeopleTestCase):
    def test_a_relationship_ends_rather_than_being_deleted(self):
        """"Who was this member's coach in March" has to stay answerable, which is why the
        row is time-bounded rather than removed."""
        tenant_id = self.tenant()
        coach, client = self.person(tenant_id), self.person(tenant_id)
        created = people.add_relationship(
            self._tenant_pool, tenant_id, kind="coach_client", from_person_id=coach,
            to_person_id=client, actor_id=ACTOR, correlation_id=self.correlate())
        people.end_relationship(
            self._tenant_pool, tenant_id, created["relationship_id"],
            reason="client changed coach", actor_id=ACTOR, correlation_id=self.correlate())
        read = people.get_person(
            self._tenant_pool, tenant_id, coach, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(read["relationships"], [])
        with self.assertRaises(Conflict):
            people.end_relationship(
                self._tenant_pool, tenant_id, created["relationship_id"], reason="again",
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_one_live_relationship_of_a_kind_between_two_people(self):
        tenant_id = self.tenant()
        coach, client = self.person(tenant_id), self.person(tenant_id)
        people.add_relationship(
            self._tenant_pool, tenant_id, kind="coach_client", from_person_id=coach,
            to_person_id=client, actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.add_relationship(
                self._tenant_pool, tenant_id, kind="coach_client", from_person_id=coach,
                to_person_id=client, actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_relationship_publishes_its_creation(self):
        tenant_id = self.tenant()
        coach, client = self.person(tenant_id), self.person(tenant_id)
        people.add_relationship(
            self._tenant_pool, tenant_id, kind="coach_client", from_person_id=coach,
            to_person_id=client, actor_id=ACTOR, correlation_id=self.correlate())
        payloads = self.outbox(tenant_id, "relationship.created")
        self.assertEqual(payloads[0]["kind"], "coach_client")


class DedupServiceTests(PeopleTestCase):
    def test_a_shared_email_queues_a_candidate_with_its_reasons(self):
        tenant_id = self.tenant()
        first = self.person(tenant_id, legal_name="Ahmad Mabrouk",
                            contacts=[{"kind": "email", "value": "ahmad@acme.test"}])
        self.person(tenant_id, legal_name="A. Mabrouk",
                    contacts=[{"kind": "email", "value": "Ahmad@Acme.test"}])
        found = people.find_duplicates(
            self._tenant_pool, tenant_id, first, actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(len(found), 1)
        self.assertIn("email_match", found[0]["signals"])
        queued = people.list_duplicate_candidates(self._tenant_pool, tenant_id)
        self.assertEqual(len(queued), 1)
        self.assertEqual(sorted(queued[0]["signals"]), ["email_match"])

    def test_running_the_detector_twice_queues_one_candidate(self):
        tenant_id = self.tenant()
        # The same name *and* the same birth date, which is the combined signal worth 45 --
        # a shared name alone is worth 10 and is deliberately below the review threshold,
        # because a father and son share one.
        first = self.person(tenant_id, legal_name="Same Name",
                            date_of_birth=date(1988, 2, 2))
        self.person(tenant_id, legal_name="Same Name", date_of_birth=date(1988, 2, 2))
        for _ in range(2):
            people.find_duplicates(
                self._tenant_pool, tenant_id, first, actor_id=ACTOR,
                correlation_id=self.correlate())
        self.assertEqual(len(people.list_duplicate_candidates(self._tenant_pool, tenant_id)), 1)

    def test_a_dismissal_states_a_reason_and_keeps_it_out_of_the_queue(self):
        tenant_id = self.tenant()
        first = self.person(tenant_id, legal_name="Same Name",
                            date_of_birth=date(1988, 2, 2))
        self.person(tenant_id, legal_name="Same Name", date_of_birth=date(1988, 2, 2))
        people.find_duplicates(
            self._tenant_pool, tenant_id, first, actor_id=ACTOR,
            correlation_id=self.correlate())
        candidate = people.list_duplicate_candidates(self._tenant_pool, tenant_id)[0]
        with self.assertRaises(InvalidRequest):
            people.dismiss_duplicate_candidate(
                self._tenant_pool, tenant_id, candidate["candidate_id"], reason="  ",
                actor_id=ACTOR, correlation_id=self.correlate())
        people.dismiss_duplicate_candidate(
            self._tenant_pool, tenant_id, candidate["candidate_id"],
            reason="father and son", actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(people.list_duplicate_candidates(self._tenant_pool, tenant_id), [])
        self.assertEqual(
            people.list_duplicate_candidates(
                self._tenant_pool, tenant_id, status="dismissed")[0]["decision_reason"],
            "father and son")

    def test_a_weak_pair_is_not_queued(self):
        """A queue full of single weak signals is a queue nobody reads, and an unread queue is
        worse than none because it looks like the control is running."""
        tenant_id = self.tenant()
        first = self.person(tenant_id, legal_name="Unique Name One")
        self.person(tenant_id, legal_name="Unique Name Two",
                    date_of_birth=date(1990, 1, 1))
        found = people.find_duplicates(
            self._tenant_pool, tenant_id, first, actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(found, [])


class MergeServiceTests(PeopleTestCase):
    def pair(self, tenant_id: str) -> tuple[str, str]:
        source = self.person(
            tenant_id, legal_name="Dup Record",
            contacts=[{"kind": "email", "value": "dup@acme.test"}])
        target = self.person(tenant_id, legal_name="Real Record")
        return source, target

    def test_a_merge_moves_what_this_module_owns_and_deletes_nothing(self):
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        people.record_note(
            self._tenant_pool, tenant_id, source, body="Called about a refund",
            actor_id=ACTOR, correlation_id=self.correlate())
        merged = people.merge_persons(
            self._tenant_pool, tenant_id, source_person_id=source,
            target_person_id=target, reason="same person", actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(merged["moved"]["contact_points"], 1)
        self.assertEqual(merged["moved"]["notes"], 1)
        # Nothing is deleted: the losing record keeps its row and points at the survivor.
        source_read = people.get_person(
            self._tenant_pool, tenant_id, source, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(source_read["merge_status"], "merged")
        self.assertEqual(source_read["merged_into_person_id"], target)
        target_read = people.get_person(
            self._tenant_pool, tenant_id, target, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(
            [c["value_normalized"] for c in target_read["contact_points"]],
            ["dup@acme.test"])
        self.assertEqual(
            len(people.list_notes(self._tenant_pool, tenant_id, target, masked_fields=(),
                                  held_permissions=STAFF)), 1)

    def test_the_plan_says_what_a_merge_would_leave_behind(self):
        """Two member profiles do not combine, and an operator is entitled to know that before
        agreeing rather than afterwards."""
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        for person_id, number in ((source, "M-100"), (target, "M-200")):
            people.create_member_profile(
                self._tenant_pool, tenant_id, person_id, member_number=number,
                actor_id=ACTOR, correlation_id=self.correlate())
        plan = people.plan_merge(
            self._tenant_pool, tenant_id, source_person_id=source, target_person_id=target)
        self.assertEqual(plan["contact_points"], 1)
        self.assertTrue(any("member profile" in r for r in plan["retained"]))
        self.assertTrue(any("M-100" in r for r in plan["retained"]))

    def test_an_already_merged_person_cannot_be_merged_again(self):
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        third = self.person(tenant_id)
        people.merge_persons(
            self._tenant_pool, tenant_id, source_person_id=source,
            target_person_id=target, reason="same person", actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.merge_persons(
                self._tenant_pool, tenant_id, source_person_id=source,
                target_person_id=third, reason="again", actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_two_sign_in_identities_cannot_become_one_person(self):
        """This module cannot revoke a session in `iam`, so the merge would mean two people
        logging in as each other."""
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        for person_id in (source, target):
            people.link_identity(
                self._tenant_pool, tenant_id, person_id, identity_id=str(uuid.uuid4()),
                actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.merge_persons(
                self._tenant_pool, tenant_id, source_person_id=source,
                target_person_id=target, reason="same person", actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_a_merge_publishes_and_the_payload_carries_no_name(self):
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        people.merge_persons(
            self._tenant_pool, tenant_id, source_person_id=source,
            target_person_id=target, reason="same person", actor_id=ACTOR,
            correlation_id=self.correlate())
        payload = self.outbox(tenant_id, "person.merged")[0]
        self.assertEqual(payload["source_person_id"], source)
        self.assertNotIn("Dup Record", str(payload))

    def test_a_reversal_restores_the_person_and_says_what_does_not_come_back(self):
        """"Reversible where feasible" is the honest part of paragraph 10200, and this is where
        the limit is."""
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        merged = people.merge_persons(
            self._tenant_pool, tenant_id, source_person_id=source,
            target_person_id=target, reason="same person", actor_id=ACTOR,
            correlation_id=self.correlate())
        reversed_ = people.reverse_merge(
            self._tenant_pool, tenant_id, merged["merge_id"], reason="wrong call",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(reversed_["not_restored"]["contact_points"], 1)
        self.assertIn("custom_fields", reversed_["not_restored"])
        # "Copied", not "re-pointed": the merge inserts on the survivor and the source keeps
        # its own rows, which is what the grants allow and what an operator has to be told.
        self.assertIn("copied these rows", reversed_["not_restored"]["why"])
        restored = people.get_person(
            self._tenant_pool, tenant_id, source, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(restored["merge_status"], "active")
        with self.assertRaises(Conflict):
            people.reverse_merge(
                self._tenant_pool, tenant_id, merged["merge_id"], reason="again",
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_merged_person_cannot_be_updated(self):
        tenant_id = self.tenant()
        source, target = self.pair(tenant_id)
        people.merge_persons(
            self._tenant_pool, tenant_id, source_person_id=source,
            target_person_id=target, reason="same person", actor_id=ACTOR,
            correlation_id=self.correlate())
        with self.assertRaises(Conflict):
            people.update_person(
                self._tenant_pool, tenant_id, source, expected_version=2,
                legal_name="Edited after merge", actor_id=ACTOR,
                correlation_id=self.correlate())


class TimelineServiceTests(PeopleTestCase):
    def test_the_projection_is_idempotent(self):
        """Paragraph 4225: the projection can be rebuilt from retained events, so a second pass
        has to be free rather than doubling every member's history."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        first = people.project_timeline(self._tenant_pool, tenant_id)
        self.assertGreaterEqual(first["projected"], 1)
        second = people.project_timeline(self._tenant_pool, tenant_id)
        self.assertEqual(second["projected"], 0)
        entries = people.read_timeline(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF)
        self.assertEqual(len([e for e in entries if e["event_type"] == "person.created"]), 1)

    def test_an_entry_references_the_event_and_carries_no_payload(self):
        """Paragraph 4021: user-safe summaries, not raw event payloads."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id, legal_name="Jane Secret")
        people.project_timeline(self._tenant_pool, tenant_id)
        entries = people.read_timeline(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF)
        self.assertTrue(entries)
        for entry in entries:
            self.assertNotIn("Jane Secret", str(entry))
            self.assertNotIn("payload", entry)
            self.assertTrue(entry["event_id"])
            self.assertTrue(entry["aggregate_type"])

    def test_an_event_about_a_subject_who_is_not_a_person_here_is_skipped(self):
        """MOD-009's consent subjects are identity ids rather than person ids, so an entry
        inserted against one would be a dangling reference."""
        tenant_id = self.tenant()
        self.person(tenant_id)
        result = people.project_timeline(self._tenant_pool, tenant_id)
        self.assertGreaterEqual(result["considered"], result["projected"])

    def test_a_lifecycle_change_reaches_the_timeline(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        created = people.create_member_profile(
            self._tenant_pool, tenant_id, person_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        people.change_member_lifecycle(
            self._tenant_pool, tenant_id, person_id, to_state="active",
            expected_version=created["version"], actor_id=ACTOR,
            correlation_id=self.correlate())
        people.project_timeline(self._tenant_pool, tenant_id)
        summaries = [e["summary"] for e in people.read_timeline(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF)]
        self.assertTrue(any("lead" in s and "active" in s for s in summaries))


class Member360Tests(PeopleTestCase):
    def test_every_section_names_its_source_and_the_absent_ones_say_why(self):
        """Returning an empty list for a module that does not exist would read as "none", which
        is the difference between "no outstanding balance" and "nothing here knows"."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        view = people.member_360(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertIn("this module", view["sections"]["identity"])
        self.assertIn("unavailable", view["sections"]["membership"])
        self.assertIn("COM-04", view["sections"]["finance"])
        self.assertNotIn("membership", view)

    def test_the_360_composes_the_parts_that_exist(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.create_member_profile(
            self._tenant_pool, tenant_id, person_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        people.upsert_staff_profile(
            self._tenant_pool, tenant_id, person_id, job_title="Coach", actor_id=ACTOR,
            correlation_id=self.correlate())
        people.record_note(
            self._tenant_pool, tenant_id, person_id, body="Prefers mornings",
            actor_id=ACTOR, correlation_id=self.correlate())
        people.project_timeline(self._tenant_pool, tenant_id)
        view = people.member_360(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(view["member_profile"]["lifecycle_state"], "lead")
        self.assertEqual(view["staff_profile"]["job_title"], "Coach")
        self.assertEqual(len(view["notes"]), 1)
        self.assertTrue(view["timeline"])

    def test_the_360_is_masked_too(self):
        tenant_id = self.tenant()
        person_id = self.person(
            tenant_id, date_of_birth=date(1990, 5, 1),
            contacts=[{"kind": "email", "value": "secret@acme.test"}])
        view = people.member_360(
            self._tenant_pool, tenant_id, person_id,
            masked_fields=("date_of_birth", "value_normalized"),
            held_permissions=STAFF_FULL)
        self.assertEqual(view["person"]["date_of_birth"], visibility.MASK)
        self.assertEqual(
            view["person"]["contact_points"][0]["value_normalized"], visibility.MASK)


class CustomFieldServiceTests(PeopleTestCase):
    def test_a_value_is_refused_unless_it_parses_as_the_declared_type(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.define_custom_field(
            self._tenant_pool, tenant_id, field_key="visits", display_name="Visits",
            value_type="integer", actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            people.set_custom_field_value(
                self._tenant_pool, tenant_id, person_id, field_key="visits",
                value="many", actor_id=ACTOR, correlation_id=self.correlate())
        stored = people.set_custom_field_value(
            self._tenant_pool, tenant_id, person_id, field_key="visits", value="007",
            actor_id=ACTOR, correlation_id=self.correlate())
        self.assertEqual(stored["value"], "7")

    def test_an_enum_value_is_one_of_the_options(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        people.define_custom_field(
            self._tenant_pool, tenant_id, field_key="tier", display_name="Tier",
            value_type="enum", options=[{"value": "gold"}, {"value": "silver"}],
            actor_id=ACTOR, correlation_id=self.correlate())
        with self.assertRaises(InvalidRequest):
            people.set_custom_field_value(
                self._tenant_pool, tenant_id, person_id, field_key="tier", value="bronze",
                actor_id=ACTOR, correlation_id=self.correlate())
        people.set_custom_field_value(
            self._tenant_pool, tenant_id, person_id, field_key="tier", value="gold",
            actor_id=ACTOR, correlation_id=self.correlate())

    def test_a_secret_typed_field_cannot_be_declared(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            people.define_custom_field(
                self._tenant_pool, tenant_id, field_key="api_key",
                display_name="API key", value_type="secret", actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_a_value_for_an_unknown_field_is_a_404(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        with self.assertRaises(NotFound):
            people.set_custom_field_value(
                self._tenant_pool, tenant_id, person_id, field_key="nothing", value="x",
                actor_id=ACTOR, correlation_id=self.correlate())


class TagServiceTests(PeopleTestCase):
    def test_a_tag_is_applied_and_removed_without_losing_who_applied_it(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        tag = people.create_tag(
            self._tenant_pool, tenant_id, tag_key="vip", display_name="VIP",
            actor_id=ACTOR, correlation_id=self.correlate())
        people.apply_tag(
            self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"], actor_id=ACTOR,
            correlation_id=self.correlate())
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual([t["tag_key"] for t in read["tags"]], ["vip"])
        people.remove_tag(
            self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"], actor_id=OTHER)
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual(read["tags"], [])
        with self.assertRaises(Conflict):
            people.remove_tag(
                self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"],
                actor_id=OTHER)

    def test_a_removed_tag_can_be_re_applied(self):
        """The row is keyed on (person, tag) for ever, so `DO NOTHING` against a removed row
        left the tag off the person while the response said `applied: True`."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        tag = people.create_tag(
            self._tenant_pool, tenant_id, tag_key="vip", display_name="VIP",
            actor_id=ACTOR, correlation_id=self.correlate())
        people.apply_tag(
            self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"], actor_id=ACTOR,
            correlation_id=self.correlate())
        people.remove_tag(
            self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"], actor_id=OTHER)
        again = people.apply_tag(
            self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"], actor_id=OTHER,
            correlation_id=self.correlate())
        self.assertTrue(again["reapplied"])
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        self.assertEqual([t["tag_key"] for t in read["tags"]], ["vip"])

    def test_applying_a_tag_twice_is_free(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        tag = people.create_tag(
            self._tenant_pool, tenant_id, tag_key="vip", display_name="VIP",
            actor_id=ACTOR, correlation_id=self.correlate())
        for _ in range(2):
            people.apply_tag(
                self._tenant_pool, tenant_id, person_id, tag_id=tag["tag_id"],
                actor_id=ACTOR, correlation_id=self.correlate())

    def test_an_unknown_tag_is_a_404(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        with self.assertRaises(NotFound):
            people.apply_tag(
                self._tenant_pool, tenant_id, person_id, tag_id=str(uuid.uuid4()),
                actor_id=ACTOR, correlation_id=self.correlate())


class ContactPointTests(PeopleTestCase):
    def test_a_new_primary_demotes_the_old_one(self):
        """"You already have a primary email" is not a useful answer to "make this the primary
        email"."""
        tenant_id = self.tenant()
        person_id = self.person(
            tenant_id, contacts=[{"kind": "email", "value": "old@acme.test",
                                  "is_primary": True}])
        people.add_contact_point(
            self._tenant_pool, tenant_id, person_id, kind="email", value="new@acme.test",
            is_primary=True, actor_id=ACTOR, correlation_id=self.correlate())
        read = people.get_person(
            self._tenant_pool, tenant_id, person_id, masked_fields=(),
            held_permissions=STAFF_FULL)
        primaries = [c["value_normalized"] for c in read["contact_points"] if c["is_primary"]]
        self.assertEqual(primaries, ["new@acme.test"])

    def test_a_verification_is_recorded_as_an_assertion(self):
        """Nothing here sends a code or reads a reply, so the row says a named actor asserted
        it at a time -- not that this build verified anything."""
        tenant_id = self.tenant()
        created = people.create_person(
            self._tenant_pool, tenant_id, legal_name="Verify Me",
            contacts=[{"kind": "email", "value": "v@acme.test"}],
            actor_id=ACTOR, correlation_id=self.correlate())
        read = people.get_person(
            self._tenant_pool, tenant_id, created["person_id"], masked_fields=(),
            held_permissions=STAFF_FULL)
        contact_id = read["contact_points"][0]["contact_point_id"]
        result = people.verify_contact_point(
            self._tenant_pool, tenant_id, contact_id, actor_id=ACTOR,
            correlation_id=self.correlate())
        self.assertEqual(result["asserted_by"], ACTOR)
        with self.assertRaises(Conflict):
            people.verify_contact_point(
                self._tenant_pool, tenant_id, contact_id, actor_id=ACTOR,
                correlation_id=self.correlate())

    def test_a_malformed_email_is_refused(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        with self.assertRaises(InvalidRequest):
            people.add_contact_point(
                self._tenant_pool, tenant_id, person_id, kind="email", value="not-an-email",
                actor_id=ACTOR, correlation_id=self.correlate())


if __name__ == "__main__":
    unittest.main()
