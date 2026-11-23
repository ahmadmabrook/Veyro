"""MOD-026 slice 4: what an attention item is, with no database.

ADM-CC-06's five states, ADM-CC-07's TOOK column and its median headline. Each is a figure a
screen prints, and each is here rather than in a client for the reason MOD-018 records: two
expressions for one number agree until somebody edits one of them.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.tasks import attention

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
ME = "aaaaaaaa-0000-4000-8000-00000000000a"
THEM = "bbbbbbbb-0000-4000-8000-00000000000b"


def state(**over: object) -> str:
    body: dict = {"status": "open", "snoozed_until": None, "now": NOW,
                  "assignee_person_id": None, "viewer_person_id": ME}
    body.update(over)
    return attention.item_state(**body)  # type: ignore[arg-type]


class StateTests(unittest.TestCase):
    def test_the_five_states_the_canvas_draws(self):
        self.assertEqual(state(), "unassigned")
        self.assertEqual(state(assignee_person_id=ME), "mine")
        self.assertEqual(state(assignee_person_id=THEM), "someone_else")
        self.assertEqual(state(status="resolved"), "resolved")
        self.assertEqual(state(status="closed"), "resolved")
        self.assertEqual(
            state(snoozed_until=NOW + timedelta(days=1)), "snoozed")

    def test_lifecycle_beats_assignment(self):
        """The sheet's *actions* differ by lifecycle and only its labels differ by
        assignment, so reading it the other way round puts a Release button on a case
        nobody has to look at until Monday."""
        self.assertEqual(
            state(status="resolved", assignee_person_id=ME), "resolved")
        self.assertEqual(
            state(snoozed_until=NOW + timedelta(days=1), assignee_person_id=ME), "snoozed")

    def test_a_return_date_that_has_passed_is_not_a_state(self):
        """The item is back in the queue and the columns stay, because "this was deferred to
        Monday and nobody looked" is exactly what a manager asks on Tuesday. Nothing sweeps
        them, which is why the comparison is in the function."""
        self.assertEqual(state(snoozed_until=NOW - timedelta(minutes=1)), "unassigned")
        self.assertEqual(
            state(snoozed_until=NOW - timedelta(minutes=1), assignee_person_id=ME), "mine")

    def test_the_boundary_is_strict_so_a_deferral_ends_when_it_says(self):
        self.assertEqual(state(snoozed_until=NOW), "unassigned")

    def test_a_reader_with_no_person_record_sees_an_assigned_item_as_somebody_elses(self):
        self.assertEqual(
            state(assignee_person_id=THEM, viewer_person_id=None), "someone_else")
        # And not as theirs, which a None-equals-None comparison would have produced.
        self.assertEqual(
            state(assignee_person_id=None, viewer_person_id=None), "unassigned")


class ActionTests(unittest.TestCase):
    def test_only_an_unassigned_or_own_item_has_live_actions(self):
        self.assertTrue(attention.may_act("unassigned"))
        self.assertTrue(attention.may_act("mine"))
        self.assertFalse(attention.may_act("someone_else"))
        self.assertFalse(attention.may_act("resolved"))
        self.assertFalse(attention.may_act("snoozed"))

    def test_a_state_outside_the_five_is_refused_rather_than_read_as_no(self):
        """Returning False for an unknown state would make a typo look like a permission
        answer, which is the shape MOD-022's undeclared rate-limit budget had."""
        with self.assertRaises(attention.AttentionError):
            attention.may_act("assigned")


class TookTests(unittest.TestCase):
    def test_wall_clock_and_not_business_hours(self):
        """An SLA target is measured against what a club said it would be open for; this is
        how long the member waited. Measuring it in business hours would make an overnight
        exception read as handled instantly."""
        opened = datetime(2026, 11, 22, 20, 0, tzinfo=UTC)
        self.assertEqual(
            attention.took_seconds(opened_at=opened,
                                   resolved_at=opened + timedelta(minutes=41)), 2460)

    def test_an_open_case_has_taken_no_length_of_time_yet(self):
        self.assertIsNone(attention.took_seconds(opened_at=NOW, resolved_at=None))
        # And zero is a different fact: resolved the instant it was raised.
        self.assertEqual(attention.took_seconds(opened_at=NOW, resolved_at=NOW), 0)

    def test_resolved_before_opened_is_refused(self):
        with self.assertRaises(attention.AttentionError):
            attention.took_seconds(opened_at=NOW, resolved_at=NOW - timedelta(seconds=1))


class MedianTests(unittest.TestCase):
    def test_the_odd_count_takes_the_middle(self):
        self.assertEqual(attention.median_seconds((10, 2460, 90)), 90)

    def test_the_even_count_takes_the_mean_of_the_two_middles(self):
        """Stated rather than left implicit: the alternative (the lower middle) differs by up
        to a second, and somebody would eventually notice two readings disagree."""
        self.assertEqual(attention.median_seconds((10, 20, 30, 41)), 25)
        self.assertEqual(attention.median_seconds((10, 21)), 15)

    def test_an_empty_window_has_no_median_rather_than_a_median_of_zero(self):
        """MOD-011's rule: nothing resolved is not a median of zero, and a dashboard
        reporting one would read as a team resolving everything instantly."""
        self.assertIsNone(attention.median_seconds(()))

    def test_the_order_of_the_input_does_not_matter(self):
        self.assertEqual(attention.median_seconds((41, 10, 30, 20)),
                         attention.median_seconds((10, 20, 30, 41)))

    def test_a_negative_duration_is_refused(self):
        with self.assertRaises(attention.AttentionError):
            attention.median_seconds((10, -1))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
