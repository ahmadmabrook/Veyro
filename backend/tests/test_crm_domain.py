"""MOD-027's pure decisions: the stage machine, the board column and the cold-lead rule.

No database. The canvases state their own figures -- "No contact 48h · 7", "NO CONTACT · 2
DAYS", "interested in classes and PT" -- so those are the assertions rather than a
restatement of the expressions, which would pass against any threshold.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.crm import pipeline

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


class StageMachineTests(unittest.TestCase):
    def test_the_machine_runs_forward_through_three_stages(self) -> None:
        pipeline.check_transition("new", "contacted")
        pipeline.check_transition("contacted", "toured")

    def test_it_does_not_run_backwards(self) -> None:
        """Stated in `EDGES`' own comment: "this lead has toured" is a fact about what
        happened, and un-reaching it would make the board's "Toured · 6" a count nobody can
        reconstruct. A tour that fell through is a touchpoint saying so."""
        for frm, to in (("contacted", "new"), ("toured", "contacted"), ("toured", "new")):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.check_transition(frm, to)

    def test_it_does_not_skip_a_stage(self) -> None:
        with self.assertRaises(pipeline.PipelineError):
            pipeline.check_transition("new", "toured")

    def test_it_does_not_stay_put(self) -> None:
        """A move to the stage a lead is already at is not a move, and admitting it would make
        `stage_changed_at` move for a write that changed nothing."""
        for stage in pipeline.STAGES:
            with self.assertRaises(pipeline.PipelineError):
                pipeline.check_transition(stage, stage)

    def test_a_stage_outside_the_vocabulary_is_refused_on_both_sides(self) -> None:
        for frm, to in (("lost", "contacted"), ("new", "lost"), ("on_trial", "toured")):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.check_transition(frm, to)

    def test_lost_and_the_derived_stages_are_not_stored_stages(self) -> None:
        """`lost` is slice 3's and a declared value nothing writes is this build's
        most-repeated finding; `on_trial` and `joined` are MOD-017's answer."""
        self.assertNotIn("lost", pipeline.STAGES)
        self.assertNotIn("on_trial", pipeline.STAGES)
        self.assertNotIn("joined", pipeline.STAGES)
        self.assertEqual(set(pipeline.EDGES), set(pipeline.STAGES))


class BoardColumnTests(unittest.TestCase):
    def test_the_board_draws_five_columns_and_stores_three(self) -> None:
        self.assertEqual(
            pipeline.BOARD_COLUMNS, ("new", "contacted", "toured", "on_trial", "joined"))

    def test_a_lead_with_no_membership_sits_at_its_sales_stage(self) -> None:
        for stage in pipeline.STAGES:
            self.assertEqual(pipeline.board_stage(stage, None), stage)

    def test_an_active_trial_is_on_trial_and_an_active_membership_is_joined(self) -> None:
        trial = pipeline.Membership(active=True, on_trial_product=True)
        member = pipeline.Membership(active=True, on_trial_product=False)
        self.assertEqual(pipeline.board_stage("new", trial), "on_trial")
        self.assertEqual(pipeline.board_stage("new", member), "joined")

    def test_a_membership_outranks_the_sales_stage(self) -> None:
        """The later fact wins: a lead whose stage still reads `contacted` because nobody moved
        it, and who has since bought a membership, is a member. The sales stage is what
        somebody typed; the membership is what happened."""
        member = pipeline.Membership(active=True, on_trial_product=False)
        self.assertEqual(pipeline.board_stage("contacted", member), "joined")

    def test_a_lapsed_membership_does_not_hold_a_lead_in_a_derived_column(self) -> None:
        """Which is the whole reason the column is derived rather than stored: a stored
        `on_trial` would still read `on_trial` the day after the trial lapsed."""
        lapsed = pipeline.Membership(active=False, on_trial_product=True)
        self.assertEqual(pipeline.board_stage("toured", lapsed), "toured")


class GoingColdTests(unittest.TestCase):
    def test_forty_eight_hours_is_the_threshold_the_canvas_states(self) -> None:
        self.assertEqual(pipeline.GOING_COLD_AFTER, timedelta(hours=48))

    def test_a_lead_touched_an_hour_ago_is_warm_and_three_days_ago_is_cold(self) -> None:
        warm = pipeline.is_going_cold(
            last_touch_at=NOW - timedelta(hours=1), created_at=NOW - timedelta(days=9),
            now=NOW)
        cold = pipeline.is_going_cold(
            last_touch_at=NOW - timedelta(days=3), created_at=NOW - timedelta(days=9),
            now=NOW)
        self.assertFalse(warm)
        self.assertTrue(cold)

    def test_an_untouched_lead_is_counted_from_when_it_was_created(self) -> None:
        """The canvas's own example: "Rana Sabbagh NO CONTACT · 2 DAYS" beside "open day ·
        2d". Treating an untouched lead as warm would hide exactly the ones the chip is for."""
        self.assertTrue(pipeline.is_going_cold(
            last_touch_at=None, created_at=NOW - timedelta(days=2), now=NOW))
        self.assertFalse(pipeline.is_going_cold(
            last_touch_at=None, created_at=NOW - timedelta(hours=4), now=NOW))

    def test_the_boundary_is_inclusive(self) -> None:
        self.assertTrue(pipeline.is_going_cold(
            last_touch_at=NOW - timedelta(hours=48), created_at=NOW, now=NOW))
        self.assertFalse(pipeline.is_going_cold(
            last_touch_at=NOW - timedelta(hours=47, minutes=59), created_at=NOW, now=NOW))

    def test_the_hours_are_whole_and_never_negative(self) -> None:
        """The card draws "4h" and "2d", and this app has one number path that throws for a
        fraction -- which cost a 500 on a rendered page once."""
        self.assertEqual(pipeline.hours_since_contact(
            last_touch_at=NOW - timedelta(hours=4, minutes=50), created_at=NOW, now=NOW), 4)
        self.assertEqual(pipeline.hours_since_contact(
            last_touch_at=NOW + timedelta(hours=2), created_at=NOW, now=NOW), 0)


class InterestTests(unittest.TestCase):
    def test_the_three_the_canvas_offers(self) -> None:
        self.assertEqual(pipeline.INTERESTS, ("classes", "pt", "gym_only"))

    def test_a_set_is_de_duplicated_and_ordered_by_the_vocabulary(self) -> None:
        """ADM-CRM-03 renders "interested in classes and PT", so the order is the
        vocabulary's rather than whatever order the form submitted."""
        self.assertEqual(
            pipeline.check_interests(("pt", "classes", "pt")), ("classes", "pt"))

    def test_gym_only_is_not_combined_with_another_interest(self) -> None:
        """The words say it: a lead interested in classes is not interested in the gym
        *only*. Refused rather than silently dropped, because a form that discarded a tick
        would be lying about what it recorded."""
        with self.assertRaises(pipeline.PipelineError):
            pipeline.check_interests(("classes", "gym_only"))
        self.assertEqual(pipeline.check_interests(("gym_only",)), ("gym_only",))

    def test_an_unknown_interest_is_refused(self) -> None:
        with self.assertRaises(pipeline.PipelineError):
            pipeline.check_interests(("nutrition",))

    def test_no_interests_is_allowed_because_the_field_is_optional(self) -> None:
        self.assertEqual(pipeline.check_interests(()), ())


class TouchpointStageTests(unittest.TestCase):
    def test_a_call_contacts_a_new_lead_and_a_tour_tours_it(self) -> None:
        self.assertEqual(pipeline.stage_from_touchpoint("new", "call"), "contacted")
        self.assertEqual(pipeline.stage_from_touchpoint("new", "tour"), "toured")

    def test_a_touchpoint_never_moves_a_lead_back(self) -> None:
        """Otherwise this function would be the one writer that defeats `EDGES`: a note on a
        toured lead would put it back to `contacted`."""
        self.assertEqual(pipeline.stage_from_touchpoint("toured", "note"), "toured")
        self.assertEqual(pipeline.stage_from_touchpoint("toured", "call"), "toured")
        self.assertEqual(pipeline.stage_from_touchpoint("contacted", "email"), "contacted")

    def test_every_kind_resolves_to_a_stage_in_the_vocabulary(self) -> None:
        for kind in pipeline.TOUCHPOINT_KINDS:
            for stage in pipeline.STAGES:
                self.assertIn(pipeline.stage_from_touchpoint(stage, kind), pipeline.STAGES)

    def test_an_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(pipeline.PipelineError):
            pipeline.stage_from_touchpoint("new", "carrier_pigeon")


if __name__ == "__main__":
    unittest.main()
