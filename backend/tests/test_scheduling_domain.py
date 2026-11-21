"""MOD-019 OPS-01: the scheduling decisions, with no database.

These are the parts that can be wrong without any row existing: a recurring class that moves by
an hour when the clocks change, a conflict detector that reports the wrong resource, an
eligibility check that lets somebody in because a fact about them is missing, an impact preview
that counts a move as a cancellation and an addition.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.scheduling import (
    availability,
    capacity,
    conflicts,
    publishing,
    recurrence,
    resources,
    substitution,
)
from app.scheduling.recurrence import ScheduleError

LONDON = "Europe/London"
AMMAN = "Asia/Amman"


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class RecurrenceTests(unittest.TestCase):
    def weekly(self, **kwargs) -> recurrence.Rule:
        base = {"frequency": "weekly", "local_time": time(18, 0), "timezone": LONDON,
                "duration_minutes": 60, "starts_on": date(2026, 3, 2),
                "until": date(2026, 3, 30), "weekdays": (0,)}
        base.update(kwargs)
        return recurrence.Rule(**base)  # type: ignore[arg-type]

    def test_a_weekly_class_keeps_its_local_time_across_a_clock_change(self):
        """**Paragraph 4150, which is the whole reason the rule stores a local time.** Adding
        seven days to a UTC instant moves an 18:00 class to 17:00 twice a year, and the member
        who turns up at 18:00 finds the room occupied."""
        occurrences = recurrence.generate(self.weekly())
        local = [o.starts_at.astimezone(recurrence.ZoneInfo(LONDON)).strftime("%H:%M")
                 for o in occurrences]
        self.assertEqual(set(local), {"18:00"})
        # And the UTC instants really do differ across the transition, which is what makes the
        # local time constant a non-trivial claim.
        in_utc = {o.starts_at.strftime("%H:%M") for o in occurrences}
        self.assertEqual(in_utc, {"18:00", "17:00"})

    def test_a_local_time_that_does_not_exist_moves_forward_and_says_so(self):
        """One day a year in one zone, 01:30 is skipped. Refusing would silently drop a class
        and leave the members who booked it with nothing and no row explaining why."""
        rule = self.weekly(frequency="daily", local_time=time(1, 30), weekdays=(),
                           starts_on=date(2026, 3, 28), until=date(2026, 3, 30))
        occurrences = {o.local_date: o for o in recurrence.generate(rule)}
        self.assertFalse(occurrences[date(2026, 3, 28)].adjusted)
        self.assertTrue(occurrences[date(2026, 3, 29)].adjusted)
        self.assertEqual(occurrences[date(2026, 3, 29)].starts_at, utc(2026, 3, 29, 1, 30))

    def test_a_local_time_that_happens_twice_takes_the_first(self):
        """`fold=0`, decided rather than inherited: leaving it to the platform default is how
        two services disagree about which 01:30 a class was at."""
        rule = self.weekly(frequency="daily", local_time=time(1, 30), weekdays=(),
                           starts_on=date(2026, 10, 25), until=date(2026, 10, 25))
        occurrence = recurrence.generate(rule)[0]
        self.assertFalse(occurrence.adjusted)
        self.assertEqual(occurrence.starts_at, utc(2026, 10, 25, 0, 30))

    def test_a_monthly_rule_means_the_month_s_own_nth_weekday(self):
        rule = self.weekly(frequency="monthly_by_weekday", weekdays=(0,), week_of_month=1,
                           starts_on=date(2026, 1, 15), until=date(2026, 4, 30))
        days = [o.local_date for o in recurrence.generate(rule)]
        self.assertEqual(days, [date(2026, 2, 2), date(2026, 3, 2), date(2026, 4, 6)])

    def test_the_last_weekday_of_a_month_is_the_last_one(self):
        rule = self.weekly(frequency="monthly_by_weekday", weekdays=(4,), week_of_month=-1,
                           starts_on=date(2026, 1, 1), until=date(2026, 2, 28))
        days = [o.local_date for o in recurrence.generate(rule)]
        self.assertEqual(days, [date(2026, 1, 30), date(2026, 2, 27)])

    def test_an_excluded_date_produces_nothing_and_the_rule_still_says_why(self):
        """OPS-01-R02's exceptions. Kept on the rule rather than deleted from the instances, so
        "why is there no class that Monday" is answerable."""
        rule = self.weekly(excluded_dates=(date(2026, 3, 16),))
        days = [o.local_date for o in recurrence.generate(rule)]
        self.assertNotIn(date(2026, 3, 16), days)
        self.assertEqual(len(days), 4)

    def test_a_one_time_session_is_one_occurrence(self):
        rule = self.weekly(frequency="once", weekdays=(), starts_on=date(2026, 3, 4),
                           until=date(2026, 3, 4))
        self.assertEqual(len(recurrence.generate(rule)), 1)

    def test_an_unworkable_rule_is_refused_with_a_sentence(self):
        for kwargs, fragment in (
            ({"frequency": "fortnightly"}, "not a recurrence frequency"),
            ({"duration_minutes": 0}, "longer than no time"),
            ({"timezone": "Mars/Olympus"}, "not a timezone"),
            ({"until": date(2026, 1, 1)}, "does not end before it starts"),
            ({"weekdays": ()}, "names the days it runs on"),
            ({"weekdays": (0, 0)}, "named once"),
            ({"weekdays": (7,)}, "0 (Monday) to 6 (Sunday)"),
            ({"until": date(2028, 1, 1)}, "at most"),
        ):
            with self.assertRaises(ScheduleError, msg=str(kwargs)) as caught:
                recurrence.generate(self.weekly(**kwargs))
            self.assertIn(fragment, str(caught.exception), str(kwargs))

    def test_a_count_is_available_without_generating(self):
        """For the impact preview: the first thing anybody asks of a draft is how many
        sessions it is."""
        self.assertEqual(recurrence.occurrence_count(self.weekly()), 5)

    def test_a_daily_rule_for_a_year_is_allowed_and_one_beyond_the_horizon_is_not(self):
        """A facility open every day for a year is an ordinary schedule. **The horizon is the
        only bound**, because a rule carries one local time and so produces at most one
        occurrence a day -- a separate occurrence cap sat here and could not fire."""
        year = recurrence.generate(self.weekly(
            frequency="daily", weekdays=(), starts_on=date(2026, 1, 1),
            until=date(2026, 12, 31)))
        self.assertEqual(len(year), 365)
        with self.assertRaises(ScheduleError) as caught:
            recurrence.generate(self.weekly(
                frequency="daily", weekdays=(), starts_on=date(2026, 1, 1),
                until=date(2027, 6, 30)))
        self.assertIn("at most", str(caught.exception))


class ResourceTests(unittest.TestCase):
    def test_every_kind_has_a_class_and_the_exclusive_ones_are_the_singular_ones(self):
        self.assertEqual(set(resources.EXCLUSIVE_KINDS),
                         {"staff", "room", "zone", "court"})
        for kind in resources.EXCLUSIVE_KINDS:
            self.assertTrue(resources.is_exclusive(kind), kind)
        for kind in ("equipment", "service", "composite"):
            self.assertFalse(resources.is_exclusive(kind), kind)

    def test_a_countable_resource_carries_its_quantity_and_an_exclusive_one_cannot(self):
        resources.check_resource(resources.Resource("r", "equipment", quantity=20))
        with self.assertRaises(ScheduleError) as caught:
            resources.check_resource(resources.Resource("r", "room", quantity=2))
        self.assertIn("one thing", str(caught.exception))

    def test_a_requirement_names_a_kind_or_a_resource_and_never_a_count_of_one(self):
        resources.check_requirement(resources.Requirement("room"))
        resources.check_requirement(resources.Requirement("room", resource_id="studio-1"))
        with self.assertRaises(ScheduleError):
            resources.check_requirement(
                resources.Requirement("equipment", quantity=5, resource_id="bikes"))

    def test_a_kind_is_required_once_because_two_cannot_say_whether_they_differ(self):
        with self.assertRaises(ScheduleError) as caught:
            resources.check_requirements([
                resources.Requirement("room"), resources.Requirement("room")])
        self.assertIn("same resource or different ones", str(caught.exception))

    def test_a_service_or_composite_requirement_names_which_one(self):
        with self.assertRaises(ScheduleError):
            resources.check_requirements([resources.Requirement("service")])

    def test_a_session_requires_something(self):
        with self.assertRaises(ScheduleError) as caught:
            resources.check_requirements([])
        self.assertIn("note in a diary", str(caught.exception))


class AvailabilityTests(unittest.TestCase):
    MONDAY = availability.Placement(utc(2026, 3, 2, 10), utc(2026, 3, 2, 11))

    def working(self, **kwargs) -> availability.Window:
        base = {"kind": "working", "timezone": LONDON, "starts_at": time(9, 0),
                "ends_at": time(17, 0), "weekday": 0}
        base.update(kwargs)
        return availability.Window(**base)  # type: ignore[arg-type]

    def test_a_session_inside_the_working_hours_is_available(self):
        self.assertTrue(
            availability.available(self.MONDAY, [self.working()], timezone=LONDON))
        self.assertIsNone(
            availability.unavailable_reason(self.MONDAY, [self.working()], timezone=LONDON))

    def test_partial_cover_is_not_availability(self):
        """Half a class inside a coach's hours is a class that ends with nobody there."""
        late = self.working(starts_at=time(10, 30))
        self.assertFalse(availability.available(self.MONDAY, [late], timezone=LONDON))
        self.assertIn("outside the working hours",
                      availability.unavailable_reason(self.MONDAY, [late], timezone=LONDON))

    def test_a_break_overlapping_any_part_removes_the_time(self):
        windows = [self.working(),
                   self.working(kind="break", starts_at=time(10, 30), ends_at=time(11, 0))]
        self.assertFalse(availability.available(self.MONDAY, windows, timezone=LONDON))
        self.assertIn("a break",
                      availability.unavailable_reason(self.MONDAY, windows, timezone=LONDON))

    def test_dated_time_off_beats_the_weekly_rota(self):
        windows = [self.working(),
                   availability.Window("time_off", LONDON, time(0, 0), time(23, 59),
                                       on_date=date(2026, 3, 2))]
        self.assertFalse(availability.available(self.MONDAY, windows, timezone=LONDON))
        self.assertIn("time off",
                      availability.unavailable_reason(self.MONDAY, windows, timezone=LONDON))

    def test_a_resource_with_no_rota_at_all_is_unconstrained(self):
        """Declaring a rota is what makes it binding.

        The first version read an empty list as "never available", which meant nothing could be
        scheduled in a tenant until somebody had written working hours for every room, court and
        bike. Found by the HTTP tests; every domain test passed because each supplied the windows
        it was about.
        """
        self.assertTrue(availability.available(self.MONDAY, [], timezone=LONDON))
        self.assertIsNone(
            availability.unavailable_reason(self.MONDAY, [], timezone=LONDON))

    def test_a_rota_that_leaves_a_day_out_still_refuses_that_day(self):
        """The other half, and the reason this is not simply fail-open: a coach whose rota says
        Monday is not available on Tuesday, because the rota is a statement about the week."""
        tuesday = availability.Placement(
            datetime(2026, 3, 3, 10, 0, tzinfo=UTC), datetime(2026, 3, 3, 11, 0, tzinfo=UTC))
        self.assertFalse(availability.available(tuesday, [self.working()],
                                               timezone=LONDON))
        self.assertIn("no working hours",
                      availability.unavailable_reason(tuesday, [self.working()],
                                                      timezone=LONDON))

    def test_time_off_binds_a_resource_with_no_rota(self):
        """An absence is a statement about a specific day and needs no rota to mean something --
        which is what stops the rule above from being fail-open in the direction that matters."""
        off = availability.Window("time_off", LONDON, time(0, 0), time(23, 59),
                                  on_date=date(2026, 3, 2))
        self.assertFalse(availability.available(self.MONDAY, [off], timezone=LONDON))
        self.assertIn("time off",
                      availability.unavailable_reason(self.MONDAY, [off],
                                                      timezone=LONDON))

    def test_a_window_over_midnight_is_refused_as_two_windows(self):
        with self.assertRaises(ScheduleError):
            availability.check_window(
                self.working(starts_at=time(22, 0), ends_at=time(2, 0)))

    def test_a_window_is_weekly_or_dated_and_not_both(self):
        with self.assertRaises(ScheduleError):
            availability.check_window(self.working(on_date=date(2026, 3, 2)))
        with self.assertRaises(ScheduleError):
            availability.check_window(self.working(weekday=None))

    def test_a_travel_buffer_applies_only_between_locations(self):
        here = availability.Placement(utc(2026, 3, 2, 10), utc(2026, 3, 2, 11), "site-a")
        same = availability.Placement(utc(2026, 3, 2, 11), utc(2026, 3, 2, 12), "site-a")
        other = availability.Placement(utc(2026, 3, 2, 11), utc(2026, 3, 2, 12), "site-b")
        self.assertIsNone(availability.check_travel(here, same, buffer_minutes=20))
        self.assertIn("travel buffer is 20",
                      availability.check_travel(here, other, buffer_minutes=20))
        later = availability.Placement(utc(2026, 3, 2, 12), utc(2026, 3, 2, 13), "site-b")
        self.assertIsNone(availability.check_travel(here, later, buffer_minutes=20))

    def test_overlapping_sessions_are_not_reported_as_a_travel_problem(self):
        """Two sessions at the same time are a conflict whatever the travel time, and saying
        "not enough travel" would send an operator to look at a map instead of the clash."""
        here = availability.Placement(utc(2026, 3, 2, 10), utc(2026, 3, 2, 12), "site-a")
        clash = availability.Placement(utc(2026, 3, 2, 11), utc(2026, 3, 2, 13), "site-b")
        self.assertIsNone(availability.check_travel(here, clash, buffer_minutes=30))


class ConflictTests(unittest.TestCase):
    PLACE = availability.Placement(utc(2026, 3, 2, 18), utc(2026, 3, 2, 19), "site-a")

    def setUp(self) -> None:
        self.chart = {
            "coach-1": resources.Resource("coach-1", "staff", location_id="site-a"),
            "coach-2": resources.Resource("coach-2", "staff", location_id="site-a"),
            "studio-1": resources.Resource("studio-1", "room", location_id="site-a"),
            "bikes": resources.Resource("bikes", "equipment", quantity=20,
                                        location_id="site-a"),
        }

    def held(self, resource_id: str, kind: str, quantity: int = 1, *,
             label: str = "Spin", session: str = "s-other") -> conflicts.Held:
        return conflicts.Held(resource_id, kind, quantity, self.PLACE, session, label)

    def test_touching_sessions_do_not_conflict(self):
        """The half-open interval is what makes back-to-back scheduling possible at all."""
        before = availability.Placement(utc(2026, 3, 2, 17), utc(2026, 3, 2, 18))
        self.assertFalse(conflicts.overlaps(before, self.PLACE))

    def test_a_named_exclusive_resource_held_elsewhere_is_double_booked(self):
        found = conflicts.detect(
            self.PLACE, [resources.Requirement("staff", resource_id="coach-1")],
            self.chart, [self.held("coach-1", "staff")])
        self.assertEqual([c.kind for c in found], ["double_booked"])
        self.assertIn("already held by Spin", found[0].detail)
        self.assertEqual(found[0].with_session_id, "s-other")

    def test_a_kind_requirement_is_satisfied_by_a_free_one(self):
        found = conflicts.detect(
            self.PLACE, [resources.Requirement("staff")], self.chart,
            [self.held("coach-1", "staff")])
        self.assertEqual(found, [])

    def test_a_kind_requirement_conflicts_when_none_is_free(self):
        found = conflicts.detect(
            self.PLACE, [resources.Requirement("staff")], self.chart,
            [self.held("coach-1", "staff"), self.held("coach-2", "staff")])
        self.assertEqual([c.kind for c in found], ["double_booked"])
        self.assertIn("0 of 2 are free", found[0].detail)

    def test_countable_resources_conflict_on_the_total_rather_than_on_overlap(self):
        """Twenty-five bikes booked against twenty is a conflict even though neither session
        alone exceeds it."""
        found = conflicts.detect(
            self.PLACE, [resources.Requirement("equipment", quantity=10)], self.chart,
            [self.held("bikes", "equipment", 15)])
        self.assertEqual([c.kind for c in found], ["over_capacity"])
        self.assertIn("20 exist, 15 are held", found[0].detail)

    def test_a_session_does_not_conflict_with_itself(self):
        found = conflicts.detect(
            self.PLACE, [resources.Requirement("staff", resource_id="coach-1")],
            self.chart, [self.held("coach-1", "staff", session="s-mine")],
            session_id="s-mine")
        self.assertEqual(found, [])

    def test_a_requirement_for_a_kind_nobody_owns_says_so(self):
        found = conflicts.detect(
            self.PLACE, [resources.Requirement("court")], self.chart, [])
        self.assertEqual([c.kind for c in found], ["over_capacity"])
        self.assertIn("no court to schedule against", found[0].detail)

    def test_a_requirement_naming_a_resource_that_does_not_exist_is_refused(self):
        with self.assertRaises(ScheduleError):
            conflicts.detect(
                self.PLACE, [resources.Requirement("staff", resource_id="ghost")],
                self.chart, [])

    def test_any_conflict_needs_the_override_permission(self):
        """Paragraph 1842's Critical Control: the distinction between a serious clash and a
        trivial one is a judgement for whoever holds that permission, not a rule here."""
        self.assertFalse(conflicts.requires_override([]))
        self.assertTrue(conflicts.requires_override(
            [conflicts.Conflict("unavailable", None, "the rota says no")]))

    def test_the_summary_names_every_conflict_rather_than_the_first(self):
        found = [conflicts.Conflict("double_booked", "coach-1", "coach busy"),
                 conflicts.Conflict("over_capacity", "bikes", "not enough bikes")]
        summary = conflicts.summarise(found)
        self.assertIn("coach busy", summary)
        self.assertIn("not enough bikes", summary)


class CapacityTests(unittest.TestCase):
    PLACE = availability.Placement(utc(2026, 3, 2, 18), utc(2026, 3, 2, 19))

    def test_setup_and_cleanup_extend_the_resource_window_and_not_the_session(self):
        """A class from 18:00 to 19:00 with ten minutes of cleanup holds the studio until
        19:10, and the member's schedule still says 19:00."""
        window = capacity.resource_window(
            self.PLACE, capacity.Policy(capacity=12, setup_minutes=5, cleanup_minutes=10))
        self.assertEqual(window.starts_at, utc(2026, 3, 2, 17, 55))
        self.assertEqual(window.ends_at, utc(2026, 3, 2, 19, 10))
        self.assertEqual(self.PLACE.ends_at, utc(2026, 3, 2, 19))

    def test_places_include_the_overbooking_and_a_hold_beyond_them_is_refused(self):
        policy = capacity.Policy(capacity=12, overbook_places=2)
        self.assertEqual(capacity.places(policy), 14)
        capacity.check_hold(policy, held=13)
        with self.assertRaises(ScheduleError) as caught:
            capacity.check_hold(policy, held=14)
        self.assertIn("14 places, 14 are held", str(caught.exception))

    def test_overbooking_beyond_the_capacity_itself_is_refused(self):
        with self.assertRaises(ScheduleError):
            capacity.check_policy(capacity.Policy(capacity=10, overbook_places=11))

    def test_an_age_restriction_refuses_a_member_whose_age_is_unknown(self):
        """**A missing fact is a refusal, not a pass.** Treating unknown as eligible is how a
        twelve-year-old ends up in a class the insurer excluded."""
        adults = [capacity.Restriction("min_age", "18")]
        self.assertIsNone(
            capacity.eligibility(adults, capacity.Candidate(age_years=30)))
        self.assertIn("age is not recorded",
                      capacity.eligibility(adults, capacity.Candidate()))
        self.assertIn("18 and over",
                      capacity.eligibility(adults, capacity.Candidate(age_years=12)))

    def test_a_skill_or_entitlement_restriction_names_what_is_missing(self):
        self.assertIn(
            "requires level-2",
            capacity.eligibility([capacity.Restriction("skill", "level-2")],
                                 capacity.Candidate(age_years=30)))
        self.assertIsNone(
            capacity.eligibility([capacity.Restriction("skill", "level-2")],
                                 capacity.Candidate(age_years=30,
                                                    skills=frozenset({"level-2"}))))
        self.assertIn(
            "pt-pack entitlement",
            capacity.eligibility([capacity.Restriction("entitlement", "pt-pack")],
                                 capacity.Candidate(age_years=30)))

    def test_an_age_restriction_that_is_not_a_number_is_refused_at_declaration(self):
        with self.assertRaises(ScheduleError):
            capacity.check_restriction(capacity.Restriction("min_age", "grown up"))

    def test_the_booking_window_opens_and_closes_before_the_session(self):
        early = utc(2026, 2, 20, 10)
        inside = utc(2026, 3, 1, 10)
        late = utc(2026, 3, 2, 17, 55)
        self.assertIn("booking opens at", capacity.booking_window_open(
            self.PLACE, at=early, opens_hours_before=72, closes_minutes_before=30))
        self.assertIsNone(capacity.booking_window_open(
            self.PLACE, at=inside, opens_hours_before=72, closes_minutes_before=30))
        self.assertIn("booking closed at", capacity.booking_window_open(
            self.PLACE, at=late, opens_hours_before=72, closes_minutes_before=30))


class PublishingTests(unittest.TestCase):
    TODAY = date(2026, 3, 1)

    def instance(self, hour: int, day: int = 2, held: int = 0) -> publishing.Instance:
        return publishing.Instance(
            session_id=f"s-{day}-{hour}", starts_at=utc(2026, 3, day, hour),
            ends_at=utc(2026, 3, day, hour + 1), held=held)

    def test_a_change_takes_effect_today_or_later_and_never_in_the_past(self):
        publishing.check_effective_from(self.TODAY, today=self.TODAY)
        with self.assertRaises(ScheduleError) as caught:
            publishing.check_effective_from(date(2026, 2, 20), today=self.TODAY)
        self.assertIn("already happened", str(caught.exception))

    def test_instances_before_the_effective_date_are_not_counted_at_all(self):
        """Including them would inflate the preview with sessions nobody is deciding about."""
        existing = [self.instance(18, day=2), self.instance(18, day=10)]
        proposed = [self.instance(18, day=2), self.instance(19, day=10)]
        impact = publishing.assess(existing, proposed, effective_from=date(2026, 3, 5),
                                   today=self.TODAY)
        self.assertEqual(impact.unchanged, 0)
        self.assertEqual(impact.moved, 1)
        self.assertEqual(impact.cancelled, 0)
        self.assertEqual(impact.added, 0)

    def test_a_session_that_moves_is_counted_once_rather_than_twice(self):
        """Telling a member their class moved is one conversation; telling them it was
        cancelled and another added is two."""
        impact = publishing.assess(
            [self.instance(18, held=4)], [self.instance(19)],
            effective_from=self.TODAY, today=self.TODAY)
        self.assertEqual((impact.moved, impact.cancelled, impact.added), (1, 0, 0))
        self.assertEqual(impact.places_affected, 4)
        self.assertEqual(impact.first_affected_at, utc(2026, 3, 2, 18))

    def test_a_cancellation_and_an_addition_are_distinguished_from_a_move(self):
        impact = publishing.assess(
            [self.instance(18), self.instance(20)],
            [self.instance(18), self.instance(21), self.instance(22)],
            effective_from=self.TODAY, today=self.TODAY)
        self.assertEqual((impact.unchanged, impact.moved, impact.cancelled, impact.added),
                         (1, 1, 0, 1))

    def test_a_change_touching_only_empty_sessions_needs_no_notification(self):
        """Mailing everybody about a schedule edit is how a tenant trains its members to
        ignore the mail."""
        quiet = publishing.assess([self.instance(18)], [self.instance(19)],
                                  effective_from=self.TODAY, today=self.TODAY)
        self.assertFalse(publishing.needs_notification(quiet))
        loud = publishing.assess([self.instance(18, held=1)], [self.instance(19)],
                                 effective_from=self.TODAY, today=self.TODAY)
        self.assertTrue(publishing.needs_notification(loud))

    def test_a_published_template_is_not_demoted_to_draft(self):
        """MOD-013's finding: a demotion is a two-step rewrite of already-approved content, and
        here it would change a class members have booked."""
        publishing.check_transition("draft", "published")
        publishing.check_transition("published", "retired")
        for current, target in (("published", "draft"), ("retired", "published"),
                                ("draft", "retired")):
            with self.assertRaises(ScheduleError, msg=f"{current}->{target}"):
                publishing.check_transition(current, target)

    def test_the_description_says_what_changes_and_what_it_costs(self):
        impact = publishing.assess([self.instance(18, held=3)], [self.instance(19)],
                                   effective_from=self.TODAY, today=self.TODAY)
        said = publishing.describe(impact)
        self.assertIn("1 moved", said)
        self.assertIn("3 held place(s) affected", said)


class SubstitutionTests(unittest.TestCase):
    STARTS = utc(2026, 3, 2, 18)

    def test_a_substitution_names_who_covers_and_why(self):
        substitution.check_change(substitution.Change(
            "substitution", "Sam is unwell", replacement_id="coach-2"))
        with self.assertRaises(ScheduleError):
            substitution.check_change(substitution.Change("substitution", "because"))
        with self.assertRaises(ScheduleError) as caught:
            substitution.check_change(substitution.Change(
                "substitution", "   ", replacement_id="coach-2"))
        self.assertIn("states why", str(caught.exception))

    def test_a_cancellation_names_a_declared_reason_rather_than_prose(self):
        """The reason decides what a member is owed, so it is a declared value and not a
        sentence somebody has to interpret."""
        substitution.check_change(substitution.Change(
            "cancellation", "nobody booked", cancellation_reason="insufficient_bookings"))
        with self.assertRaises(ScheduleError) as caught:
            substitution.check_change(substitution.Change("cancellation", "nobody booked"))
        self.assertIn("decides what a member is owed", str(caught.exception))
        with self.assertRaises(ScheduleError):
            substitution.check_change(substitution.Change(
                "cancellation", "x", cancellation_reason="felt like it"))

    def test_every_declared_reason_but_other_returns_the_held_places(self):
        for reason in substitution.CANCELLATION_REASONS:
            change = substitution.Change("cancellation", "because",
                                         cancellation_reason=reason)
            self.assertEqual(substitution.places_are_returned(change),
                             reason != "other", reason)

    def test_a_cancelled_session_does_not_come_back(self):
        substitution.check_session_transition("scheduled", "cancelled")
        with self.assertRaises(ScheduleError) as caught:
            substitution.check_session_transition("cancelled", "scheduled")
        self.assertIn("does not change again", str(caught.exception))

    def test_a_relocation_within_an_hour_is_refused_in_favour_of_a_cancellation(self):
        """A notice that cannot reach the members travelling to a class is worse than a
        cancellation, which tells them something true."""
        substitution.check_relocation(
            from_location_id="site-a", to_location_id="site-b", starts_at=self.STARTS,
            at=utc(2026, 3, 2, 10))
        with self.assertRaises(ScheduleError) as caught:
            substitution.check_relocation(
                from_location_id="site-a", to_location_id="site-b", starts_at=self.STARTS,
                at=utc(2026, 3, 2, 17, 30))
        self.assertIn("cancel it instead", str(caught.exception))

    def test_a_session_already_under_way_is_not_relocated(self):
        with self.assertRaises(ScheduleError) as caught:
            substitution.check_relocation(
                from_location_id="site-a", to_location_id="site-b", starts_at=self.STARTS,
                at=self.STARTS + timedelta(minutes=5))
        self.assertIn("has started", str(caught.exception))

    def test_a_relocation_to_where_it_already_is_is_refused(self):
        with self.assertRaises(ScheduleError):
            substitution.check_relocation(
                from_location_id="site-a", to_location_id="site-a", starts_at=self.STARTS,
                at=utc(2026, 3, 2, 10))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ReviewRegressionTests(unittest.TestCase):
    """The cases three independent reviews earned, named for the attacks and not the fixes.

    Four of these exist because a reviewer ran 51 single-clause mutations against this file and
    **four survived**: the code was right and the evidence was not there. The rest are the
    blocking findings.
    """

    LONDON = "Europe/London"
    AMMAN = "Asia/Amman"

    def working(self, **kw: object) -> availability.Window:
        fields: dict = {"kind": "working", "timezone": self.LONDON,
                        "starts_at": time(9, 0), "ends_at": time(17, 0), "weekday": 0}
        fields.update(kw)
        return availability.Window(**fields)  # type: ignore[arg-type]

    def placement(self, start: datetime, minutes: int = 60,
                  location_id: str | None = None) -> availability.Placement:
        return availability.Placement(
            starts_at=start, ends_at=start + timedelta(minutes=minutes),
            location_id=location_id)

    # ------------------------------------------------ the four surviving mutations

    def test_partial_cover_is_refused_at_the_end_as_well_as_the_start(self):
        """The containment has two halves and only one had a case.

        A reviewer weakened `w.starts_at <= start and end <= w.ends_at` to its first conjunct
        and all 58 tests passed: the existing case used a session starting *before* the rota,
        which the weakened predicate refuses anyway. The docstring describes the other side --
        "a class that ends with nobody there" -- and that is this case.
        """
        late = self.placement(datetime(2026, 3, 2, 16, 0, tzinfo=UTC), minutes=120)
        self.assertFalse(availability.available(
            late, [self.working()], timezone=self.LONDON))
        self.assertIn("outside the working hours", availability.unavailable_reason(
            late, [self.working()], timezone=self.LONDON))

    def test_a_named_countable_resource_conflicts_on_its_own_total(self):
        """`_for_named`'s arithmetic had no case, and it is the only path production takes.

        `detect_session_conflicts` builds every requirement with `resource_id` set, so the
        named branch is what runs; the existing countable case named a *kind* and exercised
        `_for_kind` instead. A reviewer weakened the named branch to ignore what this session
        asks for and all 58 tests passed.
        """
        window = self.placement(datetime(2026, 3, 2, 18, 0, tzinfo=UTC))
        bikes = resources.Resource("bikes", "equipment", quantity=20)
        held = [conflicts.Held("bikes", "equipment", 15, window, "other", "Spin")]
        found = conflicts.detect(
            window, [resources.Requirement("equipment", quantity=10, resource_id="bikes")],
            {"bikes": bikes}, held)
        self.assertEqual([c.kind for c in found], ["over_capacity"])
        self.assertIn("20", found[0].detail)
        # And exactly enough is not a conflict.
        self.assertEqual(conflicts.detect(
            window, [resources.Requirement("equipment", quantity=5, resource_id="bikes")],
            {"bikes": bikes}, held), [])

    def test_max_age_refuses_an_unknown_age(self):
        """`max_age` appeared nowhere in this file: a reviewer made it pass on an unknown age
        and all 58 tests passed. It is the children's-class direction, so the untested half was
        an adult with no recorded age joining a minors' session."""
        refused = capacity.eligibility(
            [capacity.Restriction("max_age", "12")], capacity.Candidate(age_years=None))
        self.assertIsNotNone(refused)
        self.assertIn("not recorded", refused or "")
        self.assertIsNotNone(capacity.eligibility(
            [capacity.Restriction("max_age", "12")], capacity.Candidate(age_years=30)))
        self.assertIsNone(capacity.eligibility(
            [capacity.Restriction("max_age", "12")], capacity.Candidate(age_years=9)))

    def test_an_occurrence_ends_after_its_duration(self):
        """`ends_at` was never asserted, so `duration_minutes` was validated and its effect
        was not: a reviewer set `ends_at = starts_at` and all 58 tests passed."""
        rule = recurrence.Rule(
            frequency="once", local_time=time(18, 0), timezone=self.AMMAN,
            duration_minutes=45, starts_on=date(2026, 6, 1), until=date(2026, 6, 1),
            weekdays=())
        occurrence = recurrence.generate(rule)[0]
        self.assertEqual(
            occurrence.ends_at - occurrence.starts_at, timedelta(minutes=45))

    # ------------------------------------------------ the blocking findings

    def test_a_rota_is_read_in_the_resource_s_own_zone(self):
        """`Window.timezone` was stored, written from the resource's location and read by
        nothing, so a coach's rota was evaluated in the *session's* zone.

        A London coach rostered 09:00-17:00 was reported available for an 09:00 class at an
        Amman site, which is 06:00 their time.
        """
        amman_nine = datetime(2026, 3, 2, 9, 0, tzinfo=ZoneInfo(self.AMMAN))
        place = self.placement(amman_nine.astimezone(UTC))
        rota = [self.working()]
        self.assertFalse(availability.available(place, rota, timezone=self.AMMAN))
        self.assertIn("outside the working hours",
                      availability.unavailable_reason(place, rota, timezone=self.AMMAN))

    def test_a_dated_absence_in_another_zone_is_still_consulted(self):
        """The worse half: the window is *selected* by comparing its date against a local date,
        so an absence a few hours away was never looked at."""
        off = availability.Window(
            "time_off", "America/Los_Angeles", time(0, 0), time(23, 59),
            on_date=date(2026, 3, 2))
        amman_nine = datetime(2026, 3, 3, 9, 0, tzinfo=ZoneInfo(self.AMMAN))
        place = self.placement(amman_nine.astimezone(UTC))
        self.assertFalse(availability.available(place, [off], timezone=self.AMMAN))

    def test_a_resource_at_another_site_does_not_satisfy_a_requirement(self):
        """`Resource.location_id` and `Placement.location_id` were both carried and neither
        was compared, so a class could be published at one site holding a room at another --
        and the room was genuinely held, which refused it to the real class there."""
        chart = {
            "studio-london": resources.Resource(
                "studio-london", "room", location_id="site-london"),
            "coach-london": resources.Resource(
                "coach-london", "staff", location_id="site-london"),
        }
        place = self.placement(
            datetime(2026, 3, 2, 18, 0, tzinfo=UTC), location_id="site-amman")
        found = conflicts.detect(
            place, [resources.Requirement("room"), resources.Requirement("staff")],
            chart, [])
        self.assertEqual([c.kind for c in found], ["over_capacity", "over_capacity"])
        self.assertTrue(conflicts.requires_override(found))
        # Named, rather than by kind, reports which resource is in the wrong place.
        named = conflicts.detect(
            place, [resources.Requirement("room", resource_id="studio-london")],
            chart, [])
        self.assertEqual([c.kind for c in named], ["elsewhere"])

    def test_a_resource_tied_to_no_site_travels(self):
        """The other direction, so the guard is not simply "refuse everything": a service
        format and a coach with no base are not bolted to a building."""
        chart = {"spin": resources.Resource("spin", "service"),
                 "coach": resources.Resource("coach", "staff")}
        place = self.placement(
            datetime(2026, 3, 2, 18, 0, tzinfo=UTC), location_id="site-amman")
        self.assertEqual(conflicts.detect(
            place, [resources.Requirement("service", resource_id="spin"),
                    resources.Requirement("staff", resource_id="coach")], chart, []), [])

    def test_two_sessions_at_one_instant_are_both_assessed(self):
        """`assess` keyed a dict on `starts_at`, so a tenant running two classes at six in two
        studios had one silently dropped -- and *which* one depended on list order, because the
        later row overwrote the earlier. With the empty studio last, a publish that cancelled
        both reported zero places affected and needed no acknowledgement."""
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        end = start + timedelta(hours=1)
        a = publishing.Instance("studio-a", start, end, held=12)
        b = publishing.Instance("studio-b", start, end, held=18)
        for order in ([a, b], [b, a]):
            impact = publishing.assess(
                order, [], effective_from=date(2026, 6, 1), today=date(2026, 6, 1))
            self.assertEqual(impact.cancelled, 2, order)
            self.assertEqual(impact.places_affected, 30, order)
            self.assertTrue(publishing.needs_notification(impact))

    def test_a_duration_change_is_not_nothing_changing(self):
        """`Instance.ends_at` was carried and never compared, so a sixty-minute class
        republished as fifteen minutes reported that nothing changed at all."""
        start = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        before = [publishing.Instance("s", start, start + timedelta(hours=1), held=5)]
        after = [publishing.Instance("s", start, start + timedelta(minutes=15), held=5)]
        impact = publishing.assess(
            before, after, effective_from=date(2026, 6, 1), today=date(2026, 6, 1))
        self.assertEqual(impact.unchanged, 0)
        self.assertTrue(publishing.needs_notification(impact))
        self.assertNotIn("nothing changes", publishing.describe(impact))

    def test_scope_is_the_local_date_and_not_the_utc_one(self):
        """`effective_from` is a date an operator typed, and the session knows its local date.
        At UTC+3 a session at 23:30Z on the 4th is half past two on the 5th."""
        start = datetime(2026, 6, 4, 23, 30, tzinfo=UTC)
        instance = publishing.Instance(
            "s", start, start + timedelta(hours=1), local_date=date(2026, 6, 5), held=25)
        impact = publishing.assess(
            [instance], [], effective_from=date(2026, 6, 5), today=date(2026, 6, 1))
        self.assertEqual(impact.cancelled, 1)
        self.assertEqual(impact.places_affected, 25)

    def test_an_age_value_int_refuses_is_refused_here(self):
        """`str.isdigit()` is true for Unicode superscripts that `int()` rejects, so this guard
        passed a value that raised a bare `ValueError` two lines later -- which nothing in the
        request path catches, so the route answered 500 rather than 422."""
        with self.assertRaises(ScheduleError):
            capacity.check_restriction(capacity.Restriction("min_age", "²"))
        with self.assertRaises(ScheduleError):
            capacity.eligibility(
                [capacity.Restriction("min_age", "²")],
                capacity.Candidate(age_years=30))

    def test_both_ends_of_the_booking_window_are_bounded(self):
        """One bounded sibling is not a bound: the closing end overflowed `timedelta` into an
        `OverflowError`, which is not a `ScheduleError` and so reaches a caller as a 500."""
        place = self.placement(datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        with self.assertRaises(ScheduleError):
            capacity.booking_window_open(
                place, at=datetime(2026, 5, 1, tzinfo=UTC), opens_hours_before=168,
                closes_minutes_before=10 ** 13)

    def test_a_dated_working_window_does_not_close_the_rest_of_the_week(self):
        """"Open specially this Sunday" closed Monday to Saturday, because the rule asked
        whether *any* working window existed rather than whether the rota reaches this day."""
        sunday = availability.Window(
            "working", self.LONDON, time(10, 0), time(14, 0), on_date=date(2026, 3, 8))
        monday = self.placement(datetime(2026, 3, 2, 12, 0, tzinfo=UTC))
        self.assertTrue(availability.available(monday, [sunday], timezone=self.LONDON))
        # And it does bind on its own date.
        early = self.placement(datetime(2026, 3, 8, 8, 0, tzinfo=UTC))
        self.assertFalse(availability.available(early, [sunday], timezone=self.LONDON))

    def test_a_weekly_rota_still_binds_every_day(self):
        """The half that stops the rule above being fail-open."""
        friday = self.placement(datetime(2026, 3, 6, 12, 0, tzinfo=UTC))
        self.assertFalse(availability.available(
            friday, [self.working()], timezone=self.LONDON))

    def test_a_two_hour_clock_change_is_stepped_until_the_hour_exists(self):
        """Antarctica/Troll moves by two hours, so `naive + 1h` was still a wall time that does
        not exist and `replace(tzinfo=...)` resolved it with the pre-transition offset -- three
        hours late."""
        zone = ZoneInfo("Antarctica/Troll")
        rule = recurrence.Rule(
            frequency="once", local_time=time(1, 30), timezone="Antarctica/Troll",
            duration_minutes=60, starts_on=date(2027, 3, 28), until=date(2027, 3, 28),
            weekdays=())
        occurrence = recurrence.generate(rule)[0]
        self.assertTrue(occurrence.adjusted)
        self.assertEqual(
            occurrence.starts_at.astimezone(zone).time(), time(3, 30))

    def test_an_adjustment_across_midnight_re_derives_the_local_date(self):
        """America/Nuuk's gap is 23:00 to 23:59, so a 23:30 rule moves onto the next local day
        -- and storing the day it was asked for left the two facts this row keeps separately
        contradicting each other."""
        zone = ZoneInfo("America/Nuuk")
        rule = recurrence.Rule(
            frequency="once", local_time=time(23, 30), timezone="America/Nuuk",
            duration_minutes=60, starts_on=date(2027, 3, 27), until=date(2027, 3, 27),
            weekdays=())
        occurrence = recurrence.generate(rule)[0]
        self.assertEqual(
            occurrence.local_date, occurrence.starts_at.astimezone(zone).date())

    def test_a_rule_outside_the_bookable_epoch_is_refused(self):
        """Only the *span* was bounded, so a thirty-day rule in year 9999 passed validation and
        walked off the end of `date` with an `OverflowError` -- not a `ValueError`, so not a
        `ScheduleError`, so a 500 with the draft already committed."""
        with self.assertRaises(ScheduleError):
            recurrence.check_rule(recurrence.Rule(
                frequency="weekly", local_time=time(18, 0), timezone=self.AMMAN,
                duration_minutes=60, starts_on=date(9999, 12, 1),
                until=date(9999, 12, 31), weekdays=(1,)))

    def test_an_exclusive_clash_reports_every_session_it_clashes_with(self):
        """It reported `clashing[0]`, so an operator who freed the earliest met the next --
        which is the failure `summarise`'s own docstring argues against."""
        window = self.placement(datetime(2026, 3, 2, 18, 0, tzinfo=UTC))
        coach = resources.Resource("coach", "staff")
        held = [conflicts.Held("coach", "staff", 1, window, "s-1", "Spin"),
                conflicts.Held("coach", "staff", 1, window, "s-2", "Yoga")]
        found = conflicts.detect(
            window, [resources.Requirement("staff", resource_id="coach")],
            {"coach": coach}, held)
        self.assertEqual(len(found), 2)
        self.assertEqual({c.with_session_id for c in found}, {"s-1", "s-2"})

    def test_detect_refuses_a_requirement_it_cannot_evaluate(self):
        """`detect` is documented as the authority on whether a placement works and never
        called `check_requirements`, so a requirement for zero or minus five of something
        reported no conflict against a resource that was entirely held."""
        window = self.placement(datetime(2026, 3, 2, 18, 0, tzinfo=UTC))
        chart = {"coach": resources.Resource("coach", "staff")}
        held = [conflicts.Held("coach", "staff", 1, window, "s-1", "Spin")]
        with self.assertRaises(ScheduleError):
            conflicts.detect(
                window, [resources.Requirement("staff", quantity=0)], chart, held)


class RotaWeekTests(unittest.TestCase):
    """ADM-SCH-04's grid: the rota as a background, with the three cases that bit before.

    Every figure on that screen comes from here, and the one worth the most care is the
    denominator: "26 of 34 available hours booked" is meaningless for a room that has no rota,
    so `None` and `0` have to stay apart.
    """

    @staticmethod
    def window(kind: str, start: str, end: str, *, weekday: int | None = None,
               on_date: date | None = None, tz: str = "Asia/Amman") -> availability.Window:
        return availability.Window(
            kind=kind, timezone=tz,
            starts_at=time.fromisoformat(start), ends_at=time.fromisoformat(end),
            weekday=weekday, on_date=on_date)

    # --- the week ------------------------------------------------------------

    def test_a_week_is_normalised_to_its_sunday_whichever_day_is_asked_for(self):
        """Two readers asking about the same week get the same seven dates."""
        sunday = date(2026, 8, 16)
        for offset in range(7):
            self.assertEqual(
                availability.week_from(sunday + timedelta(days=offset))[0], sunday)
        self.assertEqual(7, len(availability.week_from(sunday)))

    def test_the_week_runs_sunday_first_which_is_what_the_design_draws(self):
        # ADM-SCH-04's columns are SUN-SAT and its sample week is dated to a Sunday, which is
        # the working week in this product's own market. `Window.weekday` is 0-Monday and that
        # is a storage convention: the rota rows are keyed by weekday number whichever day the
        # grid starts on, so only the order of the seven dates moves.
        week = availability.week_from(date(2026, 8, 19))
        self.assertEqual([6, 0, 1, 2, 3, 4, 5], [d.weekday() for d in week])
        self.assertEqual(date(2026, 8, 16), week[0])
        self.assertEqual(date(2026, 8, 22), week[6])

    # --- which windows bind --------------------------------------------------

    def test_a_weekly_window_binds_its_weekday_and_a_dated_one_its_date(self):
        weekly = self.window("working", "09:00", "17:00", weekday=0)
        dated = self.window("working", "10:00", "12:00", on_date=date(2026, 8, 19))
        monday, wednesday = date(2026, 8, 17), date(2026, 8, 19)
        self.assertEqual([weekly], availability.windows_on([weekly, dated], monday))
        self.assertEqual([dated], availability.windows_on([weekly, dated], wednesday))

    def test_the_windows_come_back_in_a_deterministic_order(self):
        """A pure function that answers differently depending on row order is wrong whatever
        builds the list -- `publishing.assess` keyed a dict on a start time and dropped a
        session, and which one depended on the query planner. A rota read straight from a
        table has no order at all."""
        early = self.window("working", "07:00", "11:00", weekday=0)
        late = self.window("working", "17:00", "20:00", weekday=0)
        monday = date(2026, 8, 17)
        self.assertEqual(
            availability.windows_on([early, late], monday),
            availability.windows_on([late, early], monday))
        self.assertEqual("07:00:00", availability.windows_on(
            [late, early], monday)[0].starts_at.isoformat())

    # --- what is open --------------------------------------------------------

    def test_a_break_in_the_middle_splits_the_day_into_two_open_spans(self):
        windows = [self.window("working", "09:00", "17:00", weekday=0),
                   self.window("break", "12:00", "13:00", weekday=0)]
        spans = availability.open_spans_on(windows, date(2026, 8, 17))
        self.assertEqual(
            [("09:00:00", "12:00:00"), ("13:00:00", "17:00:00")],
            [(s.isoformat(), e.isoformat()) for s, e in spans])
        self.assertEqual(7 * 60, availability.open_minutes_on(windows, date(2026, 8, 17)))

    def test_time_off_over_the_whole_shift_leaves_a_day_that_binds_and_is_shut(self):
        """**The pair this screen is about.** A rota that binds and is fully removed is zero
        open minutes; a resource with no rota is `None`. Rendering both as 0 would read as
        "never available" for a room nobody wrote a rota for."""
        day = date(2026, 8, 20)
        windows = [self.window("working", "09:00", "17:00", weekday=3),
                   self.window("time_off", "08:00", "18:00", on_date=day)]
        self.assertTrue(availability.rota_binds_on(windows, day))
        self.assertEqual([], availability.open_spans_on(windows, day))
        self.assertEqual(0, availability.open_minutes_on(windows, day))

    def test_a_resource_with_no_rota_has_no_open_hours_rather_than_none_of_them(self):
        day = date(2026, 8, 17)
        self.assertFalse(availability.rota_binds_on([], day))
        self.assertIsNone(availability.open_minutes_on([], day))
        # And a removal on a rota-less resource still binds, which is the module's own rule --
        # it subtracts from nothing, so the answer is still "nobody wrote a rota".
        off = [self.window("time_off", "08:00", "18:00", on_date=day)]
        self.assertFalse(availability.rota_binds_on(off, day))
        self.assertIsNone(availability.open_minutes_on(off, day))

    def test_a_weekly_rota_binds_every_day_including_the_ones_it_leaves_out(self):
        """A coach rostered Monday is not available on Friday: a weekly rota is a statement
        about the week. This is what stops the rule above from being fail-open."""
        windows = [self.window("working", "09:00", "17:00", weekday=0)]
        self.assertTrue(availability.rota_binds_on(windows, date(2026, 8, 21)))
        self.assertEqual(0, availability.open_minutes_on(windows, date(2026, 8, 21)))

    def test_only_dated_working_windows_bind_only_their_own_dates(self):
        """"Open specially this Sunday" must not close the rest of the week."""
        sunday = date(2026, 8, 23)
        windows = [self.window("working", "10:00", "14:00", on_date=sunday)]
        self.assertTrue(availability.rota_binds_on(windows, sunday))
        self.assertEqual(4 * 60, availability.open_minutes_on(windows, sunday))
        self.assertFalse(availability.rota_binds_on(windows, date(2026, 8, 17)))
        self.assertIsNone(availability.open_minutes_on(windows, date(2026, 8, 17)))

    def test_two_overlapping_working_windows_do_not_double_count_their_overlap(self):
        windows = [self.window("working", "09:00", "13:00", weekday=0),
                   self.window("working", "11:00", "15:00", weekday=0)]
        # Two rows covering 09:00-15:00 with a two-hour overlap is six hours open, not eight.
        # The first version reported eight: the overlap was counted twice, and that figure is
        # the denominator of the canvas's own "N of M available hours booked".
        spans = availability.open_spans_on(windows, date(2026, 8, 17))
        self.assertEqual([("09:00:00", "15:00:00")],
                         [(s.isoformat(), e.isoformat()) for s, e in spans])
        self.assertEqual(6 * 60, availability.open_minutes_on(windows, date(2026, 8, 17)))

    def test_a_malformed_window_is_refused_rather_than_drawn(self):
        for bad in (self.window("sabbatical", "09:00", "17:00", weekday=0),
                    self.window("working", "17:00", "09:00", weekday=0),
                    availability.Window(kind="working", timezone="Asia/Amman",
                                        starts_at=time(9), ends_at=time(17))):
            with self.assertRaises(ScheduleError):
                availability.windows_on([bad], date(2026, 8, 17))
