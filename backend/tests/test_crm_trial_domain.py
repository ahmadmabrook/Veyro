"""ADM-CRM-05's four figures, against the canvas's own worked example.

The canvas draws `DAY 6 OF 7`, `2 DAYS LEFT`, `4 VISITS`, `4 CLASSES`, `High ENGAGEMENT` and
"Her trial ends tomorrow" on one card -- so the first test pins all of them against one
window, because an exclusive count gets two of the three date figures right and a reader
would not notice which.
"""
from __future__ import annotations

import unittest
from datetime import date

from app.crm import trial


class CanvasTests(unittest.TestCase):
    def test_the_canvas_s_own_figures_agree_on_one_window(self) -> None:
        """A seven-day trial on its sixth day: two days left, ending tomorrow, read as high.

        **All five at once**, because the inclusive reading is the only one under which they
        agree -- and this is the arithmetic a receptionist reads out loud.
        """
        window = trial.Window(starts_on=date(2026, 8, 15), ends_on=date(2026, 8, 21))
        today = date(2026, 8, 20)
        self.assertEqual(window.days, 7)
        self.assertEqual(trial.day_of(window, today), 6)
        self.assertEqual(trial.days_left(window, today), 2)
        self.assertTrue(trial.ends_tomorrow(window, today))
        self.assertFalse(trial.has_lapsed(window, today))
        self.assertEqual(
            trial.engagement(visits=4, window=window, today=today), "high")


class WindowTests(unittest.TestCase):
    def test_a_trial_cannot_end_before_it_starts(self) -> None:
        with self.assertRaises(trial.TrialError):
            trial.Window(starts_on=date(2026, 8, 15), ends_on=date(2026, 8, 14))

    def test_one_day_is_a_trial(self) -> None:
        """A day pass is a one-day trial, and the inclusive count is what makes it one rather
        than zero days long."""
        window = trial.Window(starts_on=date(2026, 8, 15), ends_on=date(2026, 8, 15))
        self.assertEqual(window.days, 1)
        self.assertEqual(trial.day_of(window, date(2026, 8, 15)), 1)
        self.assertEqual(trial.days_left(window, date(2026, 8, 15)), 1)


class ClampTests(unittest.TestCase):
    """Both ends are clamped rather than refused, because the countdown says the rest."""

    def setUp(self) -> None:
        self.window = trial.Window(starts_on=date(2026, 8, 15), ends_on=date(2026, 8, 21))

    def test_before_it_starts_it_is_day_one_with_every_day_left(self) -> None:
        self.assertEqual(trial.day_of(self.window, date(2026, 8, 10)), 1)
        self.assertEqual(trial.days_left(self.window, date(2026, 8, 10)), 7)
        self.assertFalse(trial.has_lapsed(self.window, date(2026, 8, 10)))

    def test_after_it_ends_it_is_the_last_day_with_none_left(self) -> None:
        self.assertEqual(trial.day_of(self.window, date(2026, 8, 30)), 7)
        self.assertEqual(trial.days_left(self.window, date(2026, 8, 30)), 0)
        self.assertTrue(trial.has_lapsed(self.window, date(2026, 8, 30)))

    def test_the_last_day_is_not_lapsed_and_does_not_end_tomorrow(self) -> None:
        """The off-by-one that matters: on the final day the trial is still running."""
        last = date(2026, 8, 21)
        self.assertEqual(trial.days_left(self.window, last), 1)
        self.assertFalse(trial.has_lapsed(self.window, last))
        self.assertFalse(trial.ends_tomorrow(self.window, last))


class EngagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = trial.Window(starts_on=date(2026, 8, 15), ends_on=date(2026, 8, 21))

    def band(self, visits: int, day: int) -> str:
        return trial.engagement(
            visits=visits, window=self.window,
            today=date(2026, 8, 14 + day))

    def test_no_visits_is_its_own_band_rather_than_the_bottom_of_a_scale(self) -> None:
        """"Nobody has been in" is a different conversation from "they came once"."""
        self.assertEqual(self.band(0, 6), "none")
        self.assertEqual(self.band(1, 6), "light")

    def test_the_three_bands_are_at_the_stated_rates(self) -> None:
        # Day 4: high needs 2 visits (0.5), steady needs 1 (0.25).
        self.assertEqual(self.band(2, 4), "high")
        self.assertEqual(self.band(1, 4), "steady")
        # Day 5: one visit is 0.2, below steady.
        self.assertEqual(self.band(1, 5), "light")

    def test_it_is_measured_over_the_days_elapsed_not_the_whole_trial(self) -> None:
        """**A band measured against the whole trial improves as the trial runs out**, which
        is useless on the day it matters: two visits on day two is somebody who has come every
        day, and against seven days it would read as light."""
        self.assertEqual(self.band(2, 2), "high")
        self.assertEqual(trial.engagement(
            visits=2, window=self.window, today=date(2026, 8, 21)), "steady")

    def test_a_negative_visit_count_is_refused_rather_than_banded(self) -> None:
        with self.assertRaises(trial.TrialError):
            trial.engagement(visits=-1, window=self.window, today=date(2026, 8, 20))

    def test_every_band_is_in_the_closed_set(self) -> None:
        for visits in range(0, 12):
            for day in range(1, 8):
                self.assertIn(self.band(visits, day), trial.ENGAGEMENT)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
