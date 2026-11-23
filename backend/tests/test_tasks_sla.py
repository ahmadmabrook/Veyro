"""MOD-026 · AUT-02-R06: the SLA arithmetic, with no database.

INV-AUT-02 says the calculation is "time-zone and business-calendar aware", and these are the
assertions that say whether it is. The clock-change cases are the ones worth reading: a local
`09:00-17:00` window is eight local hours on an ordinary day, **seven** on a spring-forward
day and **nine** on an autumn one, because those are the instants a member actually waited.
MOD-019 paid for the inverse of this -- a rota read in the wrong zone made a London coach
available at six in the morning.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.tasks import sla

AMMAN = "Asia/Amman"      # permanently UTC+3 since 2022: no clock change at all
LONDON = "Europe/London"  # the clock-change cases


def weekly(*days: int, opens: str = "09:00", closes: str = "17:00") -> tuple[sla.Window, ...]:
    return tuple(
        sla.Window("open", d, None, time.fromisoformat(opens), time.fromisoformat(closes))
        for d in days)


WEEKDAYS = weekly(0, 1, 2, 3, 4)


def at(zone: str, y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(zone)).astimezone(UTC)


class WindowShapeTests(unittest.TestCase):
    def test_a_window_is_anchored_to_exactly_one_of_a_weekday_and_a_date(self):
        with self.assertRaises(sla.SlaError):
            sla.Window("open", 1, date(2026, 1, 1), time(9), time(17))
        with self.assertRaises(sla.SlaError):
            sla.Window("open", None, None, time(9), time(17))

    def test_a_closed_window_states_no_hours(self):
        """**The schema refuses this and the type did not**, so a `Window` the database
        cannot hold was constructible. Found by a mutation that came back uncaught because
        the guard it removed -- a `kind == "open"` filter -- was subsumed only by accident:
        with the invariant missing, a closed window could carry hours and would have been
        counted as open time on a day the club was shut."""
        with self.assertRaises(sla.SlaError):
            sla.Window("closed", None, date(2026, 5, 1), time(9), time(17))

    def test_a_closed_window_is_dated(self):
        """"Closed every Tuesday" is the absence of a Tuesday open window, and two ways to
        say it would let them disagree."""
        with self.assertRaises(sla.SlaError):
            sla.Window("closed", 1, None, None, None)
        sla.Window("closed", None, date(2026, 5, 1), None, None)


class SpanTests(unittest.TestCase):
    def test_overlapping_windows_are_merged_rather_than_counted_twice(self):
        """MOD-019 shipped this defect: a rota widened by adding a second row rather than
        editing the first reported eight hours where six were open -- and that figure is the
        denominator of a utilisation report."""
        windows = (
            *weekly(0, opens="09:00", closes="13:00"),
            *weekly(0, opens="11:00", closes="15:00"),
        )
        self.assertEqual(
            sla.spans_on(windows, date(2026, 11, 23)),  # a Monday
            [(time(9), time(15))])

    def test_a_dated_row_replaces_the_weekly_pattern_rather_than_adding_to_it(self):
        """Otherwise a half-day before a holiday is unexpressible: you could lengthen a day
        and never shorten one."""
        half_day = (*WEEKDAYS,
                    sla.Window("open", None, date(2026, 11, 24), time(9), time(12)))
        self.assertEqual(sla.spans_on(half_day, date(2026, 11, 24)), [(time(9), time(12))])
        # And the rest of the week is untouched.
        self.assertEqual(sla.spans_on(half_day, date(2026, 11, 23)), [(time(9), time(17))])

    def test_a_dated_closed_row_empties_the_day_and_only_that_day(self):
        holiday = (*WEEKDAYS, sla.Window("closed", None, date(2026, 11, 25), None, None))
        self.assertEqual(sla.spans_on(holiday, date(2026, 11, 25)), [])
        self.assertEqual(sla.spans_on(holiday, date(2026, 11, 26)), [(time(9), time(17))])

    def test_no_calendar_is_not_closed_all_week(self):
        """**The distinction, and the direction that matters here.** MOD-019 read an empty
        rota as "never available" and nothing could be scheduled in a tenant at all. Here the
        consequence is worse in the other direction: a clock that never advances is a breach
        that never fires, so the absence is raised rather than returned as zero."""
        self.assertFalse(sla.has_hours(()))
        self.assertTrue(sla.has_hours(WEEKDAYS))
        with self.assertRaises(sla.SlaError) as caught:
            sla.open_seconds((), AMMAN, frm=at(AMMAN, 2026, 11, 23),
                             to=at(AMMAN, 2026, 11, 24))
        self.assertIn("falls back to elapsed time", str(caught.exception))


class OpenTimeTests(unittest.TestCase):
    def test_a_whole_working_day_is_eight_hours(self):
        got = sla.open_seconds(
            WEEKDAYS, AMMAN, frm=at(AMMAN, 2026, 11, 23), to=at(AMMAN, 2026, 11, 24))
        self.assertEqual(got, 8 * 3600)

    def test_a_weekend_counts_nothing(self):
        """Saturday and Sunday are absent from the pattern, which is how a week says so."""
        got = sla.open_seconds(
            WEEKDAYS, AMMAN, frm=at(AMMAN, 2026, 11, 28), to=at(AMMAN, 2026, 11, 30))
        self.assertEqual(got, 0)

    def test_time_outside_the_window_does_not_count(self):
        """Raised at eight in the evening, the clock starts next morning."""
        got = sla.open_seconds(
            WEEKDAYS, AMMAN, frm=at(AMMAN, 2026, 11, 23, 20),
            to=at(AMMAN, 2026, 11, 24, 11))
        self.assertEqual(got, 2 * 3600)

    def test_a_pause_is_subtracted_from_the_open_time_and_not_the_elapsed_time(self):
        """**A clock paused overnight was not running anyway.** Subtracting the whole pause
        rather than its overlap with the open spans is how a target silently doubles."""
        overnight = (at(AMMAN, 2026, 11, 23, 16), at(AMMAN, 2026, 11, 24, 10))
        got = sla.open_seconds(
            WEEKDAYS, AMMAN, frm=at(AMMAN, 2026, 11, 23), to=at(AMMAN, 2026, 11, 24, 17),
            paused=(overnight,))
        # Two full days is sixteen hours; the pause covers one hour of Monday and one of
        # Tuesday, and the fourteen hours of night in between were never open.
        self.assertEqual(got, 14 * 3600)

    def test_a_span_that_ends_before_it_starts_is_refused(self):
        with self.assertRaises(sla.SlaError):
            sla.open_seconds(WEEKDAYS, AMMAN, frm=at(AMMAN, 2026, 11, 24),
                             to=at(AMMAN, 2026, 11, 23))


class ClockChangeTests(unittest.TestCase):
    """The half of INV-AUT-02 that cannot be got right by accident."""

    def test_a_spring_forward_day_is_an_hour_shorter_in_real_time(self):
        """Britain's clocks go forward at 01:00 on 29 March 2026, which is inside nothing --
        so this is the control: the *day* is 23 hours and the 09:00-17:00 window is not
        affected. The window case is the next test."""
        windows = weekly(6, opens="00:00", closes="23:00")  # Sunday, spanning the change
        got = sla.open_seconds(
            windows, LONDON, frm=at(LONDON, 2026, 3, 29), to=at(LONDON, 2026, 3, 30))
        # 00:00 to 23:00 local across the gap is 22 real hours, not 23.
        self.assertEqual(got, 22 * 3600)

    def test_an_autumn_back_day_is_an_hour_longer_in_real_time(self):
        """Clocks go back at 02:00 on 25 October 2026, so the same local window is one real
        hour longer -- which is an hour the member actually waited."""
        windows = weekly(6, opens="00:00", closes="23:00")
        got = sla.open_seconds(
            windows, LONDON, frm=at(LONDON, 2026, 10, 25), to=at(LONDON, 2026, 10, 26))
        self.assertEqual(got, 24 * 3600)

    def test_an_ordinary_sunday_is_the_stated_length(self):
        """The control for both, so the two above are a difference rather than a number."""
        windows = weekly(6, opens="00:00", closes="23:00")
        got = sla.open_seconds(
            windows, LONDON, frm=at(LONDON, 2026, 11, 1), to=at(LONDON, 2026, 11, 2))
        self.assertEqual(got, 23 * 3600)

    def test_the_zone_is_the_locations_and_the_answer_moves_with_it(self):
        """The same instants against the same local window in two zones are different
        amounts of business time, which is the whole reason the zone is a parameter."""
        frm, to = datetime(2026, 11, 23, 6, tzinfo=UTC), datetime(2026, 11, 23, 14, tzinfo=UTC)
        amman = sla.open_seconds(WEEKDAYS, AMMAN, frm=frm, to=to)
        london = sla.open_seconds(WEEKDAYS, LONDON, frm=frm, to=to)
        self.assertNotEqual(amman, london)


class DueAtTests(unittest.TestCase):
    def test_a_target_lands_inside_the_next_open_window(self):
        due = sla.due_at(WEEKDAYS, AMMAN, started_at=at(AMMAN, 2026, 11, 23, 16),
                         target_seconds=2 * 3600)
        # One hour of Monday is left, so the second hour is Tuesday morning.
        self.assertEqual(due, at(AMMAN, 2026, 11, 24, 10))

    def test_a_target_started_out_of_hours_begins_at_the_next_opening(self):
        due = sla.due_at(WEEKDAYS, AMMAN, started_at=at(AMMAN, 2026, 11, 22, 23),
                         target_seconds=3600)
        self.assertEqual(due, at(AMMAN, 2026, 11, 23, 10))

    def test_a_target_steps_over_a_closed_day(self):
        holiday = (*WEEKDAYS, sla.Window("closed", None, date(2026, 11, 24), None, None))
        due = sla.due_at(holiday, AMMAN, started_at=at(AMMAN, 2026, 11, 23, 16),
                         target_seconds=2 * 3600)
        self.assertEqual(due, at(AMMAN, 2026, 11, 25, 10))

    def test_due_and_open_seconds_agree(self):
        """**Two expressions of one fact, asserted against each other.** MOD-018's "one
        module, two definitions of the same balance" is what this prevents: the time between
        the start and the due instant must be exactly the target."""
        started = at(AMMAN, 2026, 11, 23, 11)
        due = sla.due_at(WEEKDAYS, AMMAN, started_at=started, target_seconds=10 * 3600)
        self.assertEqual(
            sla.open_seconds(WEEKDAYS, AMMAN, frm=started, to=due), 10 * 3600)

    def test_an_unreachable_target_is_refused_rather_than_walked_for_ever(self):
        """MOD-019's year-9999 rule: a loop with no ceiling answers 500 on input somebody can
        send, after the write has already committed."""
        one_hour_a_week = weekly(0, opens="09:00", closes="10:00")
        with self.assertRaises(sla.SlaError) as caught:
            sla.due_at(one_hour_a_week, AMMAN, started_at=at(AMMAN, 2026, 1, 1),
                       target_seconds=5000 * 3600)
        self.assertIn("almost no open time", str(caught.exception))

    def test_a_target_of_zero_or_less_is_refused(self):
        for bad in (0, -1):
            with self.assertRaises(sla.SlaError):
                sla.due_at(WEEKDAYS, AMMAN, started_at=at(AMMAN, 2026, 11, 23),
                           target_seconds=bad)


class StateTests(unittest.TestCase):
    def test_a_breach_is_computed_rather_than_stored(self):
        due = at(AMMAN, 2026, 11, 24, 12)
        self.assertEqual(sla.state(due=due, now=due + timedelta(seconds=1)), "breached")
        self.assertEqual(sla.state(due=due, now=due - timedelta(hours=1)), "running")

    def test_a_warning_needs_the_start_and_says_running_without_it(self):
        """A fraction of what, is the question -- so with no start there is no warning
        threshold to be past, and saying `running` is the honest answer rather than
        guessing a window."""
        started = at(AMMAN, 2026, 11, 23, 10)
        due = at(AMMAN, 2026, 11, 23, 20)
        near = at(AMMAN, 2026, 11, 23, 19)
        self.assertEqual(sla.state(due=due, now=near), "running")
        self.assertEqual(sla.state(due=due, now=near, started_at=started), "warning")
        early = at(AMMAN, 2026, 11, 23, 11)
        self.assertEqual(sla.state(due=due, now=early, started_at=started), "running")

    def test_the_threshold_is_a_fraction(self):
        due = at(AMMAN, 2026, 11, 23, 20)
        for bad in (0.0, 1.0, -0.5, 2.0):
            with self.assertRaises(sla.SlaError):
                sla.state(due=due, now=due - timedelta(hours=1), warn_at_fraction=bad)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
