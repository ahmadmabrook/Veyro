"""MOD-014 PPL-01: the decision modules, with no database anywhere.

`dedup`, `lifecycle`, `merge`, `timeline`, `fields` and `visibility` decide and read nothing, so
these run in milliseconds and say what the module believes rather than what the schema permits.
"""

from __future__ import annotations

import unittest
from datetime import date

from app.people import dedup, fields, lifecycle, merge, timeline, visibility


class VisibilityTests(unittest.TestCase):
    """The masking MOD-008 computed for five modules before anything applied it."""

    def test_a_mask_replaces_rather_than_removes(self):
        """"You may not see this" and "there is none" lead to different next actions."""
        masked = visibility.apply({"legal_name": "A", "national_id": "X"}, ("national_id",))
        self.assertEqual(masked, {"legal_name": "A", "national_id": visibility.MASK})

    def test_a_mask_reaches_every_depth(self):
        """The 360 read is a dict of lists of dicts, and a top-level-only mask is walked around
        by looking one level down."""
        record = {
            "person": {"email": "a@b.c"},
            "contact_points": [{"kind": "email", "email": "a@b.c"},
                               {"kind": "phone", "phone": "+962700000000"}],
        }
        masked = visibility.apply(record, ("email", "phone"))
        self.assertEqual(masked["person"]["email"], visibility.MASK)
        self.assertEqual(
            [c.get("email", c.get("phone")) for c in masked["contact_points"]],
            [visibility.MASK, visibility.MASK])

    def test_an_empty_mask_returns_the_record_unchanged(self):
        record = {"a": 1}
        self.assertIs(visibility.apply(record, ()), record)

    def test_each_class_has_its_own_permission(self):
        """One permission for all five would make a national id as protected as an email."""
        opens = visibility.CLASS_PERMISSIONS
        self.assertEqual(len(set(opens.values()) - {""}), 4)
        self.assertNotEqual(opens["contact"], opens["identity"])
        self.assertNotEqual(opens["identity"], opens["financial"])

    def test_health_is_unreachable_in_this_build_and_says_so(self):
        """`member.health.read` is biometric_sensitive, which needs AAL 3, which needs a
        hardware authenticator MOD-007 cannot verify."""
        self.assertEqual(visibility.UNREACHABLE_CLASSES, ("health", "biometric"))
        readable = visibility.readable_classes({"member.health.read"})
        # The permission opens the class in this module's own terms; the gate is what refuses
        # to issue a session that can exercise it, which is where the dead end lives.
        self.assertIn("health", readable)

    def test_none_is_always_readable(self):
        self.assertEqual(visibility.readable_classes(set()), frozenset({"none"}))

    def test_a_redacted_record_still_exists(self):
        """Telling a coach a member has no health notes when they have three is worse than
        telling them there are three they cannot read."""
        notes = [{"note_id": "1", "visibility_class": "health", "body": "knee injury"},
                 {"note_id": "2", "visibility_class": "none", "body": "likes mornings"}]
        out = visibility.redact_classified(
            notes, class_field="visibility_class", body_fields=("body",),
            readable=frozenset({"none"}))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["body"], visibility.MASK)
        self.assertTrue(out[0]["redacted"])
        self.assertEqual(out[1]["body"], "likes mornings")
        self.assertNotIn("redacted", out[1])

    def test_an_unknown_class_is_refused(self):
        with self.assertRaises(visibility.VisibilityError):
            visibility.check_class("secret")

    def test_an_unknown_birth_date_is_not_a_minor(self):
        """The uncomfortable direction, and the right one: every undated lead would otherwise
        need a guardian before anybody could read their record."""
        self.assertFalse(visibility.is_minor(None))
        self.assertTrue(visibility.is_minor(17))
        self.assertFalse(visibility.is_minor(18))

    def test_a_minors_record_needs_guardianship_or_staff_permission(self):
        """Paragraph 1372, with the reason named so a refusal can say which was missing."""
        allowed, why = visibility.guardianship_satisfied(
            minor=True, actor_is_guardian=False, held_permissions=frozenset())
        self.assertFalse(allowed)
        self.assertIn("guardianship", why)
        self.assertTrue(visibility.guardianship_satisfied(
            minor=True, actor_is_guardian=True, held_permissions=frozenset())[0])
        self.assertTrue(visibility.guardianship_satisfied(
            minor=True, actor_is_guardian=False,
            held_permissions=frozenset({"member.profile.read"}))[0])
        self.assertTrue(visibility.guardianship_satisfied(
            minor=False, actor_is_guardian=False, held_permissions=frozenset())[0])


class DedupTests(unittest.TestCase):
    def signals(self, person_id: str, **kwargs: object) -> dedup.PersonSignals:
        body: dict = {"person_id": person_id, "legal_name_folded": "ahmad mabrouk"}
        body.update(kwargs)
        return dedup.PersonSignals(**body)  # type: ignore[arg-type]

    def test_a_verified_shared_email_is_the_strongest_signal(self):
        a = self.signals("a", emails=frozenset({"x@y.z"}),
                         verified_emails=frozenset({"x@y.z"}))
        b = self.signals("b", emails=frozenset({"x@y.z"}),
                         verified_emails=frozenset({"x@y.z"}))
        candidate = dedup.compare(a, b)
        self.assertIn("verified_email_match", candidate.signals)
        self.assertNotIn("email_match", candidate.signals)
        self.assertTrue(dedup.worth_reviewing(candidate))

    def test_the_combined_name_and_birth_signal_replaces_its_halves(self):
        """Scoring all three would count the same evidence twice."""
        born = date(1990, 5, 1)
        a = self.signals("a", date_of_birth=born)
        b = self.signals("b", date_of_birth=born)
        candidate = dedup.compare(a, b)
        self.assertEqual(candidate.signals, ("name_and_birth_date_match",))
        self.assertEqual(candidate.score, dedup.WEIGHTS["name_and_birth_date_match"])

    def test_a_shared_household_lowers_the_score(self):
        """Two real people who share an address are correctly represented by a household, so a
        household makes a duplicate less likely rather than more."""
        a = self.signals("a", emails=frozenset({"family@y.z"}),
                         household_ids=frozenset({"h1"}))
        b = self.signals("b", legal_name_folded="laila mabrouk",
                         emails=frozenset({"family@y.z"}), household_ids=frozenset({"h1"}))
        candidate = dedup.compare(a, b)
        self.assertIn("same_household", candidate.signals)
        self.assertEqual(candidate.score,
                         dedup.WEIGHTS["email_match"] + dedup.WEIGHTS["same_household"])
        self.assertFalse(dedup.worth_reviewing(candidate))

    def test_a_score_never_leaves_the_stored_range(self):
        a = self.signals("a", household_ids=frozenset({"h1"}))
        b = self.signals("b", legal_name_folded="someone else",
                         household_ids=frozenset({"h1"}))
        self.assertEqual(dedup.compare(a, b).score, 0)

    def test_a_pair_is_ordered_so_it_cannot_be_queued_twice(self):
        candidate = dedup.compare(self.signals("bbb"), self.signals("aaa"))
        self.assertEqual(candidate.ordered, ("aaa", "bbb"))

    def test_a_person_is_not_their_own_duplicate(self):
        with self.assertRaises(dedup.DedupError):
            dedup.compare(self.signals("a"), self.signals("a"))

    def test_there_is_no_auto_merge_threshold(self):
        """Paragraph 10200 requires a merge to be reviewable; a score high enough to merge
        without a human makes the review optional where the consequences are largest."""
        self.assertIsNone(dedup.AUTO_MERGE_THRESHOLD)

    def test_name_folding_is_not_fuzzy(self):
        self.assertEqual(dedup.fold_name("  Ahmad   Mabrouk "), "ahmad mabrouk")
        self.assertNotEqual(dedup.fold_name("Ahmed"), dedup.fold_name("Ahmad"))

    def test_the_rank_is_stable_between_runs(self):
        a = dedup.Candidate("a", "b", 60, ("email_match",))
        b = dedup.Candidate("c", "d", 60, ("phone_match",))
        self.assertEqual(dedup.rank([b, a]), dedup.rank([a, b]))


class LifecycleTests(unittest.TestCase):
    def test_nothing_returns_to_lead(self):
        """A person who became a member and left is a former member; the step back would lose
        the one fact the record is for."""
        for state in ("prospect", "active", "paused", "cancelled", "former"):
            self.assertNotIn("lead", lifecycle.MEMBER_EDGES[state])

    def test_a_walk_in_can_join_the_same_day(self):
        lifecycle.check_member_transition("lead", "active")

    def test_a_former_member_can_rejoin(self):
        lifecycle.check_member_transition("former", "active")

    def test_a_no_op_move_is_refused(self):
        """A retry that succeeded silently would record a second lifecycle event for a change
        that never happened."""
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_member_transition("active", "active")

    def test_an_unknown_state_is_refused_on_both_sides(self):
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_member_transition("member", "active")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_member_transition("active", "deleted")

    def test_employment_ends_once(self):
        self.assertEqual(lifecycle.STAFF_EDGES["ended"], ())
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_staff_transition("ended", "active")

    def test_the_moves_that_take_something_away_say_why(self):
        for state in ("paused", "cancelled", "former"):
            self.assertTrue(lifecycle.reason_required(state))
        for state in ("lead", "prospect", "active"):
            self.assertFalse(lifecycle.reason_required(state))

    def test_a_stale_version_is_refused(self):
        lifecycle.check_version(3, 3)
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_version(3, 4)


class MergeTests(unittest.TestCase):
    def ok(self, **kwargs: object) -> dict:
        body: dict = {"source_person_id": "a", "target_person_id": "b",
                      "source_status": "active", "target_status": "active",
                      "source_has_identity_link": False,
                      "target_has_identity_link": False, "reason": "same person"}
        body.update(kwargs)
        return body

    def test_a_clean_merge_is_permitted(self):
        merge.check_merge(**self.ok())

    def test_nothing_merges_into_itself(self):
        with self.assertRaises(merge.MergeError):
            merge.check_merge(**self.ok(target_person_id="a"))

    def test_neither_side_may_already_be_merged(self):
        """A chain means a reader following one pointer still lands on a dead record, and
        reversing the middle link would be ambiguous."""
        with self.assertRaises(merge.MergeError):
            merge.check_merge(**self.ok(source_status="merged"))
        with self.assertRaises(merge.MergeError):
            merge.check_merge(**self.ok(target_status="merged"))

    def test_two_sign_in_identities_cannot_become_one_person(self):
        """MOD-007 is a separate plane and this module cannot revoke a session there, so the
        merge would mean two people logging in as each other."""
        with self.assertRaises(merge.MergeError):
            merge.check_merge(**self.ok(source_has_identity_link=True,
                                        target_has_identity_link=True))
        merge.check_merge(**self.ok(source_has_identity_link=True))

    def test_a_merge_states_a_reason(self):
        with self.assertRaises(merge.MergeError):
            merge.check_merge(**self.ok(reason="   "))

    def test_a_reversal_happens_once(self):
        merge.check_reversal(reversed_at=None, source_status="merged", reason="wrong call")
        with self.assertRaises(merge.MergeError):
            merge.check_reversal(reversed_at="2026-11-14", source_status="merged",
                                 reason="again")
        with self.assertRaises(merge.MergeError):
            merge.check_reversal(reversed_at=None, source_status="active", reason="wrong call")
        with self.assertRaises(merge.MergeError):
            merge.check_reversal(reversed_at=None, source_status="merged", reason=" ")

    def test_two_member_profiles_do_not_combine_and_the_plan_says_so(self):
        retained = merge.plan_retentions(
            source_has_member_profile=True, target_has_member_profile=True,
            source_has_staff_profile=False, target_has_staff_profile=False,
            source_member_number="M-1")
        self.assertEqual(len(retained), 2)
        self.assertTrue(any("member profile" in r for r in retained))
        self.assertTrue(any("M-1" in r for r in retained))

    def test_nothing_is_retained_when_only_one_side_has_a_profile(self):
        self.assertEqual(
            merge.plan_retentions(
                source_has_member_profile=False, target_has_member_profile=True,
                source_has_staff_profile=False, target_has_staff_profile=True,
                source_member_number=None),
            ())

    def test_the_survivor_is_found_through_the_chain(self):
        chain = {"a": "b", "b": "c", "c": None}
        self.assertEqual(merge.survivor_of(chain, "a"), "c")
        self.assertEqual(merge.survivor_of(chain, "c"), "c")

    def test_a_cycle_is_an_error_rather_than_a_hang(self):
        """A cycle here is an infinite loop in a read path, and the invariant that forbids it
        is one this function cannot see."""
        with self.assertRaises(merge.MergeError):
            merge.survivor_of({"a": "b", "b": "a"}, "a")


class TimelineTests(unittest.TestCase):
    def test_the_projected_list_is_short_on_purpose(self):
        """A projection of every event would be a second copy of the event log with a different
        retention policy and no owner."""
        self.assertLessEqual(len(timeline.PROJECTED), 12)
        self.assertIn("person.created", timeline.PROJECTED)
        self.assertNotIn("notification.sent", timeline.PROJECTED)
        self.assertNotIn("feature_flag.evaluated", timeline.PROJECTED)

    def test_no_summary_reads_a_classified_field(self):
        """Enforced at import; this asserts the rule rather than re-running it."""
        timeline.check_summary_fields()

    def test_an_unprojected_event_is_skipped_rather_than_an_error(self):
        self.assertIsNone(timeline.project("notification.sent", {"notification_id": "x"}))

    def test_a_lifecycle_change_renders_both_ends(self):
        person, summary, klass = timeline.project(
            "member.lifecycle.changed",
            {"person_id": "p1", "from_state": "lead", "to_state": "active"})
        self.assertEqual(person, "p1")
        self.assertIn("lead", summary)
        self.assertIn("active", summary)
        self.assertEqual(klass, "none")

    def test_only_the_declared_fields_reach_the_renderer(self):
        """An event that grows a field does not grow the timeline, which is what makes
        "user-safe summary" a mechanism rather than an intention."""
        _, summary, _ = timeline.project(
            "person.created", {"person_id": "p1", "national_id": "9999999999"})
        self.assertNotIn("9999999999", summary)

    def test_a_projected_event_with_no_subject_is_an_error(self):
        """The producer stopped sending a declared field, which is the compatibility break
        MOD-010's catalogue exists to prevent -- failing loudly is how it gets noticed."""
        with self.assertRaises(timeline.TimelineError):
            timeline.project("person.created", {})

    def test_a_summary_is_bounded(self):
        _, summary, _ = timeline.project(
            "profile.updated",
            {"person_id": "p1", "changed_fields": [f"field_{i}" for i in range(200)]})
        self.assertLessEqual(len(summary), timeline.MAX_SUMMARY)


class FieldTests(unittest.TestCase):
    def definition(self, **kwargs: object) -> fields.Definition:
        body: dict = {"field_key": "locker", "display_name": "Locker", "value_type": "text"}
        body.update(kwargs)
        return fields.Definition(**body)  # type: ignore[arg-type]

    def test_there_is_no_secret_type(self):
        """MOD-012's refusal, for the same reason: a type that invites a tenant to paste an API
        key turns a column every list route reads into where credentials end up."""
        self.assertNotIn("secret", fields.VALUE_TYPES)
        self.assertNotIn("json", fields.VALUE_TYPES)
        with self.assertRaises(fields.FieldError):
            fields.check_definition(self.definition(value_type="secret"))

    def test_a_sensitivity_outside_mod_008s_classes_is_refused(self):
        """A class the masking has never heard of reads as unmasked."""
        with self.assertRaises(fields.FieldError):
            fields.check_definition(self.definition(sensitivity="secret"))

    def test_an_enum_declares_its_options_and_nothing_else_does(self):
        with self.assertRaises(fields.FieldError):
            fields.check_definition(self.definition(value_type="enum"))
        fields.check_definition(self.definition(value_type="enum", options=("a", "b")))
        with self.assertRaises(fields.FieldError):
            fields.check_definition(self.definition(options=("a",)))
        with self.assertRaises(fields.FieldError):
            fields.check_definition(self.definition(value_type="enum", options=("a", "a")))

    def test_a_value_is_canonical_rather_than_as_typed(self):
        """Three spellings of one boolean would make a segment query depend on who typed it."""
        definition = self.definition(value_type="boolean")
        self.assertEqual(fields.normalize_value(definition, "TRUE"), "true")
        self.assertEqual(fields.normalize_value(definition, " False "), "false")
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(definition, "yes")

    def test_a_number_cannot_overflow_on_parse(self):
        """`1e999` overflows and reaches a caller as a 500, which MOD-011 and MOD-012 each
        shipped once."""
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(self.definition(value_type="decimal"), "1e999")
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(self.definition(value_type="integer"), "9" * 40)
        self.assertEqual(
            fields.normalize_value(self.definition(value_type="integer"), "007"), "7")

    def test_a_date_is_iso(self):
        definition = self.definition(value_type="date")
        self.assertEqual(fields.normalize_value(definition, "2026-11-14"), "2026-11-14")
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(definition, "14/11/2026")

    def test_an_enum_value_is_one_of_the_options(self):
        definition = self.definition(value_type="enum", options=("gold", "silver"))
        self.assertEqual(fields.normalize_value(definition, "gold"), "gold")
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(definition, "bronze")

    def test_a_blank_value_is_refused(self):
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(self.definition(), "   ")

    def test_text_is_bounded(self):
        with self.assertRaises(fields.FieldError):
            fields.normalize_value(self.definition(), "x" * (fields.MAX_TEXT + 1))

    def test_a_tenants_own_field_gets_the_same_masking_as_a_catalogue_one(self):
        """MOD-008's catalogue is code and a custom field is a row, so the classification
        travels on the definition and becomes the same shape of answer."""
        definitions = [self.definition(field_key="locker"),
                       self.definition(field_key="passport", sensitivity="identity"),
                       self.definition(field_key="allergy", sensitivity="health")]
        self.assertEqual(
            fields.masked_field_names(definitions, frozenset({"none", "identity"})),
            ("allergy",))
        self.assertEqual(
            fields.masked_field_names(definitions, frozenset({"none"})),
            ("allergy", "passport"))


if __name__ == "__main__":
    unittest.main()
