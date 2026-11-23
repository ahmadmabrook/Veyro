"""MOD-026 slice 1b service tests: queues, the calendar, cases and tasks.

Against a real database, because what is being tested is mostly what the schema and the
service agree about -- an idempotent create answering from the row it already wrote, a
forward-only case, a settlement that demands a reason, and two prose columns masked unless
the caller may write them.

**The masking tests pass an explicit `may_read_reasons`, both ways.** A suite that always
passed `True` would never see a mask, and one that always passed `False` would be testing the
mask rather than the behaviour -- which is the trap `test_people_service.py` names for its own
permission sets.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, time, timedelta

from psycopg import errors as pg

from app.db import tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.people import service as people
from app.tasks import service as tasks
from app.tasks import subjects, workflow
from tests.support import GatedApiTestCase

ACTOR = "33333333-3333-4333-8333-333333333333"


class TasksTestCase(GatedApiTestCase):
    def cid(self) -> str:
        return str(uuid.uuid4())

    def key(self) -> str:
        return f"k-{uuid.uuid4().hex[:12]}"

    def queue(self, tenant_id: str, **kwargs: object) -> str:
        body: dict = {"queue_key": f"q{uuid.uuid4().hex[:8]}",
                      "display_name": "Front desk", "location_id": None}
        body.update(kwargs)
        return str(tasks.create_queue(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=self.cid(),
            **body)["queue_id"])

    def task(self, tenant_id: str, queue_id: str, **kwargs: object) -> str:
        body: dict = {
            "case_id": None, "title": "Call about the card", "subject_kind": "tenant",
            "subject_id": None, "assignee_person_id": None, "priority": "normal",
            "due_at": None, "evidence_ref": None, "idempotency_key": self.key(),
            # `0024`: required with no default, because ADM-TSK-01's own line is "the source
            # is always named -- a task nobody can account for gets ignored".
            "source": "manual"}
        body.update(kwargs)
        return str(tasks.create_task(
            self._tenant_pool, tenant_id, queue_id=queue_id, actor_id=ACTOR,
            correlation_id=self.cid(), **body)["task_id"])

    def case(self, tenant_id: str, queue_id: str, **kwargs: object) -> str:
        body: dict = {
            "case_number": f"C-{uuid.uuid4().hex[:8].upper()}", "title": "Card not working",
            "subject_kind": "tenant", "subject_id": None, "priority": "normal",
            "recurs_from_case_id": None, "idempotency_key": self.key(),
            "source": "manual"}
        body.update(kwargs)
        return str(tasks.open_case(
            self._tenant_pool, tenant_id, queue_id=queue_id, actor_id=ACTOR,
            correlation_id=self.cid(), **body)["case_id"])


class QueueTests(TasksTestCase):
    def test_a_queue_is_idempotent_on_its_key(self):
        tenant_id = self.tenant()
        key = f"q{uuid.uuid4().hex[:8]}"
        first = tasks.create_queue(
            self._tenant_pool, tenant_id, queue_key=key, display_name="Front desk",
            location_id=None, actor_id=ACTOR, correlation_id=self.cid())
        again = tasks.create_queue(
            self._tenant_pool, tenant_id, queue_key=key, display_name="Something else",
            location_id=None, actor_id=ACTOR, correlation_id=self.cid())
        self.assertFalse(first["repeated"])
        self.assertTrue(again["repeated"])
        self.assertEqual(first["queue_id"], again["queue_id"])
        # **Answered from the row already written, not from the retry.** MOD-017's finding:
        # a repeat echoing the caller's own figures back is the disclosure check bypassed by
        # retrying with the values you wanted.
        self.assertEqual(again["display_name"], "Front desk")

    def test_retiring_a_queue_counts_the_work_left_in_it_rather_than_refusing(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        self.task(tenant_id, queue_id)
        self.task(tenant_id, queue_id)
        out = tasks.retire_queue(
            self._tenant_pool, tenant_id, queue_id, reason="merged into the main desk",
            actor_id=ACTOR, correlation_id=self.cid())
        self.assertEqual(out["open_tasks"], 2)
        self.assertEqual(out["status"], "retired")

    def test_a_retired_queue_takes_no_new_work(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        tasks.retire_queue(self._tenant_pool, tenant_id, queue_id, reason="merged",
                           actor_id=ACTOR, correlation_id=self.cid())
        with self.assertRaises(Conflict):
            self.task(tenant_id, queue_id)

    def test_a_retired_queue_is_absent_unless_asked_for(self):
        """A retired queue is a state a surface has to be able to show. MOD-009's board
        shipped a branch nothing could reach because its client never passed the flag."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        tasks.retire_queue(self._tenant_pool, tenant_id, queue_id, reason="merged",
                           actor_id=ACTOR, correlation_id=self.cid())
        live = tasks.list_queues(self._tenant_pool, tenant_id)
        self.assertEqual(live["queues"], [])
        all_of_them = tasks.list_queues(self._tenant_pool, tenant_id, include_retired=True)
        self.assertEqual(len(all_of_them["queues"]), 1)
        self.assertEqual(all_of_them["queues"][0]["retire_reason"], "merged")

    def test_a_listing_is_bounded(self):
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            tasks.list_queues(self._tenant_pool, tenant_id, limit=tasks.PAGE + 1)
        with self.assertRaises(InvalidRequest):
            tasks.list_queues(self._tenant_pool, tenant_id, limit=0)


class CalendarTests(TasksTestCase):
    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman") -> str:
        """Through the HTTP surface, as every other suite's location helper does: the
        hierarchy writes are stepped-up financial permissions and `GatedApiTestCase` is what
        holds a session that has them."""
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        self.assertEqual(org.status_code, 201, org.text)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        created = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": timezone}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["location_id"])

    def test_a_location_with_no_windows_has_no_calendar_rather_than_being_closed(self):
        """**MOD-019's first version read an empty rota as "never available" and nothing
        could be scheduled in a tenant at all.** The distinction is returned rather than left
        to a reader."""
        tenant_id = self.tenant()
        out = tasks.read_business_hours(
            self._tenant_pool, tenant_id, location_id=self.location(tenant_id))
        self.assertFalse(out["has_a_calendar"])
        self.assertEqual(out["windows"], [])
        self.assertIn("not the same", out["no_calendar_is_not_closed"])

    def test_a_window_is_withdrawn_and_not_deleted(self):
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        made = tasks.set_business_hours(
            self._tenant_pool, tenant_id, location_id=location_id, kind="open", weekday=1,
            on_date=None, opens_at=time(9, 0), closes_at=time(17, 0), note=None,
            actor_id=ACTOR, correlation_id=self.cid())
        tasks.withdraw_business_hours(
            self._tenant_pool, tenant_id, made["window_id"], reason="typed the wrong day",
            actor_id=ACTOR, correlation_id=self.cid())
        live = tasks.read_business_hours(
            self._tenant_pool, tenant_id, location_id=location_id)
        self.assertFalse(live["has_a_calendar"])
        kept = tasks.read_business_hours(
            self._tenant_pool, tenant_id, location_id=location_id, include_withdrawn=True)
        self.assertEqual(len(kept["windows"]), 1)
        self.assertEqual(kept["windows"][0]["withdraw_reason"], "typed the wrong day")

    def test_the_read_names_the_zone_every_window_is_in(self):
        """An instant without a zone is the schedule board's own hard-won lesson."""
        tenant_id = self.tenant()
        out = tasks.read_business_hours(
            self._tenant_pool, tenant_id, location_id=self.location(tenant_id))
        self.assertTrue(out["timezone"])

    def test_a_window_for_a_location_that_does_not_exist_is_refused(self):
        tenant_id = self.tenant()
        with self.assertRaises(NotFound):
            tasks.set_business_hours(
                self._tenant_pool, tenant_id, location_id=str(uuid.uuid4()), kind="closed",
                weekday=None, on_date=datetime.now(UTC).date(), opens_at=None,
                closes_at=None, note=None, actor_id=ACTOR, correlation_id=self.cid())


class SubjectTests(TasksTestCase):
    def test_a_resolvable_subject_that_does_not_exist_is_refused(self):
        """**MOD-009's erasure recorded `done / 0` and completed** because `subject_id`
        carried no foreign key and nothing resolved it. A task about an invoice nobody issued
        is work about nothing."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        with self.assertRaises(NotFound):
            self.task(tenant_id, queue_id, subject_kind="member",
                      subject_id=str(uuid.uuid4()))

    def test_a_claim_kind_is_recorded_and_the_answer_says_so(self):
        """A lead is MOD-027's and there is nothing to resolve against. Presenting that as a
        verified reference is MOD-012's `validated` shape, so the write says which it was."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        out = tasks.create_task(
            self._tenant_pool, tenant_id, queue_id=queue_id, case_id=None,
            title="Chase the lead", subject_kind="lead", subject_id=str(uuid.uuid4()),
            assignee_person_id=None, priority="normal", due_at=None, evidence_ref=None,
            idempotency_key=self.key(), source="manual", actor_id=ACTOR,
            correlation_id=self.cid())
        self.assertTrue(out["subject_is_a_recorded_claim"])
        read = tasks.read_task(self._tenant_pool, tenant_id, out["task_id"],
                               may_read_reasons=True)
        self.assertTrue(read["subject_is_a_recorded_claim"])

    def test_a_tenant_subject_carries_no_id_in_either_direction(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        with self.assertRaises(subjects.SubjectError):
            self.task(tenant_id, queue_id, subject_kind="tenant",
                      subject_id=str(uuid.uuid4()))
        with self.assertRaises(subjects.SubjectError):
            self.task(tenant_id, queue_id, subject_kind="member", subject_id=None)


class TaskLifecycleTests(TasksTestCase):
    def test_a_task_is_idempotent_on_its_key(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        key = self.key()
        first = tasks.create_task(
            self._tenant_pool, tenant_id, queue_id=queue_id, case_id=None, title="First",
            subject_kind="tenant", subject_id=None, assignee_person_id=None,
            priority="normal", due_at=None, evidence_ref=None, idempotency_key=key,
            source="manual", actor_id=ACTOR, correlation_id=self.cid())
        again = tasks.create_task(
            self._tenant_pool, tenant_id, queue_id=queue_id, case_id=None, title="Second",
            subject_kind="tenant", subject_id=None, assignee_person_id=None,
            priority="normal", due_at=None, evidence_ref=None, idempotency_key=key,
            source="manual", actor_id=ACTOR, correlation_id=self.cid())
        self.assertEqual(first["task_id"], again["task_id"])
        self.assertTrue(again["repeated"])
        self.assertEqual(again["title"], "First")

    def test_a_settlement_states_why_and_an_ordinary_move_does_not(self):
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        tasks.change_task_status(self._tenant_pool, tenant_id, task_id,
                                 target="in_progress", reason=None, actor_id=ACTOR,
                                 correlation_id=self.cid())
        with self.assertRaises(InvalidRequest):
            tasks.change_task_status(self._tenant_pool, tenant_id, task_id, target="done",
                                     reason="   ", actor_id=ACTOR,
                                     correlation_id=self.cid())
        tasks.change_task_status(self._tenant_pool, tenant_id, task_id, target="done",
                                 reason="spoke to her", actor_id=ACTOR,
                                 correlation_id=self.cid())

    def test_a_settled_task_does_not_reopen_or_move_again(self):
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        tasks.change_task_status(self._tenant_pool, tenant_id, task_id, target="cancelled",
                                 reason="raised twice", actor_id=ACTOR,
                                 correlation_id=self.cid())
        with self.assertRaises(workflow.WorkflowError):
            tasks.change_task_status(self._tenant_pool, tenant_id, task_id, target="open",
                                     reason=None, actor_id=ACTOR,
                                     correlation_id=self.cid())

    def test_a_status_change_that_changes_nothing_is_a_repeat_not_a_write(self):
        """It would otherwise write an attribution for a decision nobody made."""
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        out = tasks.change_task_status(
            self._tenant_pool, tenant_id, task_id, target="open", reason=None,
            actor_id=ACTOR, correlation_id=self.cid())
        self.assertTrue(out["repeated"])

    def test_a_settled_task_is_not_reassigned(self):
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        tasks.change_task_status(self._tenant_pool, tenant_id, task_id, target="done",
                                 reason="done", actor_id=ACTOR, correlation_id=self.cid())
        with self.assertRaises(Conflict):
            tasks.assign_task(self._tenant_pool, tenant_id, task_id,
                              assignee_person_id=None)


class DependencyTests(TasksTestCase):
    def test_a_blocker_is_named_and_stops_the_task_starting(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        first, second = self.task(tenant_id, queue_id), self.task(tenant_id, queue_id)
        tasks.add_dependency(self._tenant_pool, tenant_id, second,
                             depends_on_task_id=first, actor_id=ACTOR,
                             correlation_id=self.cid())
        read = tasks.read_task(self._tenant_pool, tenant_id, second, may_read_reasons=True)
        self.assertEqual(read["blocked_by"], [first])
        with self.assertRaises(Conflict):
            tasks.change_task_status(self._tenant_pool, tenant_id, second,
                                     target="in_progress", reason=None, actor_id=ACTOR,
                                     correlation_id=self.cid())

    def test_a_cancelled_blocker_stops_blocking(self):
        """**The direction that matters.** Treating called-off work as blocking leaves every
        downstream task stuck with no way to clear it -- MOD-016's bundle fulfilment."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        first, second = self.task(tenant_id, queue_id), self.task(tenant_id, queue_id)
        tasks.add_dependency(self._tenant_pool, tenant_id, second,
                             depends_on_task_id=first, actor_id=ACTOR,
                             correlation_id=self.cid())
        tasks.change_task_status(self._tenant_pool, tenant_id, first, target="cancelled",
                                 reason="not needed", actor_id=ACTOR,
                                 correlation_id=self.cid())
        read = tasks.read_task(self._tenant_pool, tenant_id, second, may_read_reasons=True)
        self.assertEqual(read["blocked_by"], [])
        tasks.change_task_status(self._tenant_pool, tenant_id, second, target="in_progress",
                                 reason=None, actor_id=ACTOR, correlation_id=self.cid())

    def test_a_cycle_is_refused_and_the_schema_cannot_see_it(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        a, b = self.task(tenant_id, queue_id), self.task(tenant_id, queue_id)
        tasks.add_dependency(self._tenant_pool, tenant_id, b, depends_on_task_id=a,
                             actor_id=ACTOR, correlation_id=self.cid())
        with self.assertRaises(workflow.WorkflowError):
            tasks.add_dependency(self._tenant_pool, tenant_id, a, depends_on_task_id=b,
                                 actor_id=ACTOR, correlation_id=self.cid())


class CaseTests(TasksTestCase):
    def test_a_case_moves_forward_only_and_keeps_its_first_attribution(self):
        tenant_id = self.tenant()
        case_id = self.case(tenant_id, self.queue(tenant_id))
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                          resolution_reason="replaced the card", actor_id=ACTOR,
                          correlation_id=self.cid())
        resolved = tasks.read_case(self._tenant_pool, tenant_id, case_id,
                                   may_read_reasons=True)
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="closed",
                          resolution_reason="filed", actor_id=ACTOR,
                          correlation_id=self.cid())
        closed = tasks.read_case(self._tenant_pool, tenant_id, case_id,
                                 may_read_reasons=True)
        # Closing moves the status and does not rewrite who resolved it, when, or why.
        self.assertEqual(closed["resolved_at"], resolved["resolved_at"])
        self.assertEqual(closed["resolution_reason"], "replaced the card")
        with self.assertRaises(workflow.WorkflowError):
            tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                              resolution_reason="again", actor_id=ACTOR,
                              correlation_id=self.cid())

    def test_a_closed_case_takes_no_entries_and_no_tasks(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="closed",
                          resolution_reason="filed", actor_id=ACTOR,
                          correlation_id=self.cid())
        with self.assertRaises(Conflict):
            tasks.add_case_entry(self._tenant_pool, tenant_id, case_id, entry_kind="note",
                                 summary="one more thing", document_ref=None,
                                 occurred_at=None, actor_id=ACTOR,
                                 correlation_id=self.cid())

    def test_a_task_under_a_case_must_share_its_queue(self):
        """The correspondence trigger: the same work counted in two backlogs makes "whose
        backlog is this" unanswerable."""
        tenant_id = self.tenant()
        case_id = self.case(tenant_id, self.queue(tenant_id))
        other_queue = self.queue(tenant_id)
        # **The named exception and the sentence**, not a blind `Exception`: a bare assertion
        # passes if anything at all goes wrong, which is "assert the sentence, not the class"
        # in Python -- and here a sibling could plausibly answer, since the trigger also
        # refuses a closed case.
        with self.assertRaises(pg.RaiseException) as caught:
            self.task(tenant_id, other_queue, case_id=case_id)
        self.assertIn("different queue from its case", str(caught.exception))

    def test_the_timeline_says_a_document_is_a_reference(self):
        tenant_id = self.tenant()
        case_id = self.case(tenant_id, self.queue(tenant_id))
        tasks.add_case_entry(
            self._tenant_pool, tenant_id, case_id, entry_kind="document",
            summary="the signed form", document_ref="s3://cases/form.pdf",
            occurred_at=None, actor_id=ACTOR, correlation_id=self.cid())
        read = tasks.read_case(self._tenant_pool, tenant_id, case_id, may_read_reasons=True)
        self.assertEqual(len(read["timeline"]), 1)
        self.assertIn("no object store", read["documents_are_references"])

    def test_an_entry_cannot_be_dated_in_the_future(self):
        """MOD-011's unbounded `observed_at` in a dispute record. Late is legitimate --
        somebody writes up Friday's call on Monday -- so only the future is bounded."""
        tenant_id = self.tenant()
        case_id = self.case(tenant_id, self.queue(tenant_id))
        with self.assertRaises(pg.CheckViolation) as caught:
            tasks.add_case_entry(
                self._tenant_pool, tenant_id, case_id, entry_kind="note", summary="later",
                document_ref=None, occurred_at=datetime.now(UTC) + timedelta(days=2),
                actor_id=ACTOR, correlation_id=self.cid())
        # Which constraint refused it: `check_violation` is the same exception for every
        # CHECK on a table, so counting it proves whichever fires first.
        self.assertEqual(
            caught.exception.diag.constraint_name, "tsk_case_entries_not_in_the_future")


class MaskingTests(TasksTestCase):
    def test_a_settle_reason_is_withheld_from_a_caller_who_may_not_write(self):
        """MOD-019 masks a session change's reason for this reason, after a reviewer read a
        diagnosis out of one. The entry stays visible: a redacted record still exists."""
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        tasks.change_task_status(
            self._tenant_pool, tenant_id, task_id, target="done",
            reason="she is having chemotherapy on Tuesdays", actor_id=ACTOR,
            correlation_id=self.cid())
        open_read = tasks.read_task(self._tenant_pool, tenant_id, task_id,
                                    may_read_reasons=True)
        self.assertIn("chemotherapy", open_read["settle_reason"])
        self.assertFalse(open_read["reason_masked"])
        masked = tasks.read_task(self._tenant_pool, tenant_id, task_id,
                                 may_read_reasons=False)
        self.assertEqual(masked["settle_reason"], tasks.WITHHELD)
        self.assertTrue(masked["reason_masked"])
        # The task itself is not hidden, and the title is not masked -- a queue whose titles
        # are withheld cannot be worked at all.
        self.assertEqual(masked["title"], open_read["title"])

    def test_a_resolution_reason_is_withheld_the_same_way(self):
        tenant_id = self.tenant()
        case_id = self.case(tenant_id, self.queue(tenant_id))
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                          resolution_reason="he is in hospital", actor_id=ACTOR,
                          correlation_id=self.cid())
        masked = tasks.list_cases(self._tenant_pool, tenant_id, may_read_reasons=False)
        self.assertEqual(masked["cases"][0]["resolution_reason"], tasks.WITHHELD)
        shown = tasks.list_cases(self._tenant_pool, tenant_id, may_read_reasons=True)
        self.assertIn("hospital", shown["cases"][0]["resolution_reason"])

    def test_an_absent_reason_is_absent_rather_than_withheld(self):
        """**A null and a mask are different facts.** An unsettled task has no reason, and
        rendering the withheld marker for one would say something was hidden that is not
        there -- the inverse of MOD-014's rule that a redacted record still exists."""
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        masked = tasks.read_task(self._tenant_pool, tenant_id, task_id,
                                 may_read_reasons=False)
        self.assertIsNone(masked["settle_reason"])

    def test_a_filter_value_outside_its_domain_refuses(self):
        """"No tasks" and "that is not a status" are different answers, and a list rendering
        both as an empty table is a surface nobody can trust."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            tasks.list_tasks(self._tenant_pool, tenant_id, may_read_reasons=True,
                             status="finished")
        with self.assertRaises(InvalidRequest):
            tasks.list_cases(self._tenant_pool, tenant_id, may_read_reasons=True,
                             status="shut")

    def test_a_listing_carries_no_name_address_or_birth_date(self):
        """`tasks.task.read` is routine, so a listing carrying the assignee's legal name
        would be a lateral read path around `people.person.read` -- MOD-010's
        `events.event.read` finding. Asserted by field name, not by inspection."""
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        row = tasks.read_task(self._tenant_pool, tenant_id, task_id, may_read_reasons=True)
        for leaked in ("legal_name", "display_name", "email", "phone", "date_of_birth"):
            self.assertNotIn(leaked, row)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ClockFixture:
    """A club with a calendar, shared by the two clock suites.

    A mixin rather than a base class, because `BreachSweepTests` inheriting `ClockTests`
    would silently re-run every one of its cases under a second name -- twice the wall-clock
    for no second assertion, and a count that reads as more evidence than there is.
    """

    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman") -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        created = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": timezone}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["location_id"])

    def club(self, tenant_id: str, *, with_hours: bool = True) -> tuple[str, str]:
        """A location and a queue in it, optionally with a weekday calendar."""
        location_id = self.location(tenant_id)
        if with_hours:
            for weekday in range(5):
                tasks.set_business_hours(
                    self._tenant_pool, tenant_id, location_id=location_id, kind="open",
                    weekday=weekday, on_date=None, opens_at=time(9, 0),
                    closes_at=time(17, 0), note=None, actor_id=ACTOR,
                    correlation_id=self.cid())
        return location_id, self.queue(tenant_id, location_id=location_id)

    def clock(self, tenant_id: str, task_id: str, **over: object) -> str:
        body: dict = {"case_id": None, "target_seconds": 4 * 3600,
                      "escalate_to_queue_id": None, "warn_at_basis_points": 8000}
        body.update(over)
        return str(tasks.start_clock(
            self._tenant_pool, tenant_id, task_id=task_id, actor_id=ACTOR,
            correlation_id=self.cid(), **body)["clock_id"])

class ClockTests(ClockFixture, TasksTestCase):
    """AUT-02-R06 against a real database. The arithmetic is `test_tasks_sla.py`; what is
    here is whether the right inputs reach it."""

    def test_the_location_comes_from_the_queue_and_not_the_caller(self):
        """A caller able to name one could measure a promise against a calendar the work is
        not done in -- MOD-017's `brand_id` finding, where an off-peak grant was drawn on at
        seven in the evening because the caller sent the minute."""
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        out = tasks.start_clock(
            self._tenant_pool, tenant_id, task_id=task_id, case_id=None,
            target_seconds=3600, escalate_to_queue_id=None, warn_at_basis_points=8000,
            actor_id=ACTOR, correlation_id=self.cid())
        self.assertEqual(out["location_id"], location_id)

    def test_a_clock_is_about_one_subject_and_exactly_one(self):
        tenant_id = self.tenant()
        _, queue_id = self.club(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        case_id = self.case(tenant_id, queue_id)
        for task, case in ((None, None), (task_id, case_id)):
            with self.subTest(task=task, case=case):
                with self.assertRaises(InvalidRequest):
                    tasks.start_clock(
                        self._tenant_pool, tenant_id, task_id=task, case_id=case,
                        target_seconds=3600, escalate_to_queue_id=None,
                        warn_at_basis_points=8000, actor_id=ACTOR,
                        correlation_id=self.cid())

    def test_one_running_clock_per_subject(self):
        """Two targets on one task is two promises, and which one a breach report counts
        would be the planner's choice."""
        tenant_id = self.tenant()
        _, queue_id = self.club(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        self.clock(tenant_id, task_id)
        with self.assertRaises(pg.UniqueViolation):
            self.clock(tenant_id, task_id)

    def test_a_queue_with_no_club_has_no_calendar_to_measure_against(self):
        """Refused at the boundary with a sentence naming the remedy, rather than reaching
        the schema's NOT NULL as a 500."""
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        with self.assertRaises(InvalidRequest) as caught:
            self.clock(tenant_id, task_id)
        self.assertIn("give the queue a location", str(caught.exception))

    def test_an_escalation_to_a_retired_queue_is_refused(self):
        """An alarm wired to a bell nobody answers -- MOD-021's "a lookup that proves
        something exists does not authorise what you do next"."""
        tenant_id = self.tenant()
        _, queue_id = self.club(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        dead = self.queue(tenant_id)
        tasks.retire_queue(self._tenant_pool, tenant_id, dead, reason="merged",
                           actor_id=ACTOR, correlation_id=self.cid())
        with self.assertRaises(pg.RaiseException) as caught:
            self.clock(tenant_id, task_id, escalate_to_queue_id=dead)
        self.assertIn("bell nobody answers", str(caught.exception))

    def test_a_pause_states_why_and_resuming_closes_it(self):
        tenant_id = self.tenant()
        _, queue_id = self.club(tenant_id)
        clock_id = self.clock(tenant_id, self.task(tenant_id, queue_id))
        first = tasks.pause_clock(self._tenant_pool, tenant_id, clock_id,
                                  reason="waiting on the member", actor_id=ACTOR,
                                  correlation_id=self.cid())
        again = tasks.pause_clock(self._tenant_pool, tenant_id, clock_id,
                                  reason="again", actor_id=ACTOR,
                                  correlation_id=self.cid())
        self.assertTrue(again["repeated"])
        self.assertEqual(first["pause_id"], again["pause_id"])
        read = tasks.read_clock(self._tenant_pool, tenant_id, clock_id)
        self.assertTrue(read["is_paused"])
        self.assertEqual(read["paused"][0]["reason"], "waiting on the member")
        tasks.resume_clock(self._tenant_pool, tenant_id, clock_id, actor_id=ACTOR,
                           correlation_id=self.cid())
        self.assertFalse(
            tasks.read_clock(self._tenant_pool, tenant_id, clock_id)["is_paused"])
        with self.assertRaises(Conflict):
            tasks.resume_clock(self._tenant_pool, tenant_id, clock_id, actor_id=ACTOR,
                               correlation_id=self.cid())

    def test_a_target_is_judged_once(self):
        tenant_id = self.tenant()
        _, queue_id = self.club(tenant_id)
        clock_id = self.clock(tenant_id, self.task(tenant_id, queue_id))
        tasks.settle_clock(self._tenant_pool, tenant_id, clock_id, status="met",
                           reason="answered in an hour", actor_id=ACTOR,
                           correlation_id=self.cid())
        again = tasks.settle_clock(self._tenant_pool, tenant_id, clock_id,
                                   status="breached", reason="changed my mind",
                                   actor_id=ACTOR, correlation_id=self.cid())
        self.assertTrue(again["repeated"])
        self.assertEqual(again["status"], "met")

    def test_the_read_computes_the_state_rather_than_storing_it(self):
        tenant_id = self.tenant()
        _, queue_id = self.club(tenant_id)
        clock_id = self.clock(tenant_id, self.task(tenant_id, queue_id))
        read = tasks.read_clock(self._tenant_pool, tenant_id, clock_id)
        self.assertEqual(read["measured_in"], "business_hours")
        self.assertIn(read["state"], ("running", "warning", "breached"))
        self.assertIn("due_at", read)
        self.assertEqual(read["timezone"], "Asia/Amman")
        self.assertEqual(
            read["remaining_seconds"],
            max(0, read["target_seconds"] - read["consumed_seconds"]))

    def test_a_club_with_no_calendar_falls_back_to_elapsed_time_and_says_so(self):
        """**MOD-019's "no rota is not never available", in the direction that matters
        here**: a business-hours clock against an empty calendar never advances, which is a
        breach that never fires."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        queue_id = self.queue(tenant_id, location_id=location_id)
        clock_id = self.clock(tenant_id, self.task(tenant_id, queue_id))
        read = tasks.read_clock(self._tenant_pool, tenant_id, clock_id)
        self.assertEqual(read["measured_in"], "elapsed_time")
        self.assertIn("never advance", read["no_calendar"])
        self.assertNotIn("due_at", read)


class BreachSweepTests(ClockFixture, TasksTestCase):
    """AUT-02-R06's other half: a breach is computed, so until something looks, a missed
    promise stays `running` for ever and `escalate_to_queue_id` is a column implying a
    control nobody implemented.

    **The clocks here are aged by inserting the row, not by passing an instant.** MOD-020's
    settlement takes no caller-supplied `now` because a settlement time a caller chooses
    decides who is recorded as having failed, and this judgement is the same shape -- so the
    sweep reads its own clock and a test builds the state that waiting would have built.

    **Two weeks and not two days, because a green that depends on the hour is not a green.**
    The first version aged by 48 hours against a Monday-to-Friday 09:00-17:00 calendar, and
    it was written at 08:45 on a Monday: from Saturday to that moment the club had been open
    for zero seconds, so four cases reported nothing breached and read as a defect in the
    sweep. Fourteen days spans at least ten working days in any week and from any hour, which
    is this repository's own rule about a fixture whose answer moves with the clock.
    """

    def aged(
        self, tenant_id: str, *, location_id: str, hours_ago: int = 24 * 14,
        target_seconds: int = 3600, escalate_to: str | None = None,
        task_id: str | None = None, case_id: str | None = None,
    ) -> str:
        location = location_id
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            made = conn.execute(
                "INSERT INTO plt01.tsk_sla_clocks"
                " (tenant_id, task_id, case_id, location_id, target_seconds,"
                "  warn_at_basis_points, started_at, escalate_to_queue_id, created_by,"
                "  create_correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, 8000, now() - %s * interval '1 hour', %s,"
                "         %s, %s) RETURNING clock_id",
                (tenant_id, task_id, case_id, location, target_seconds, hours_ago,
                 escalate_to, ACTOR, self.cid()),
            ).fetchone()
        assert made is not None
        return str(made[0])

    def sweep(self, tenant_id: str) -> dict:
        return tasks.sweep_breaches(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=self.cid())

    def escalations(self, tenant_id: str, queue_id: str) -> list[dict]:
        return list(tasks.list_tasks(
            self._tenant_pool, tenant_id, queue_id=queue_id, status=None,
            assignee_person_id=None, may_read_reasons=True)["tasks"])

    def test_a_missed_target_is_judged_and_the_judgement_names_the_worker(self):
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id,
                             task_id=self.task(tenant_id, queue_id))
        out = self.sweep(tenant_id)
        self.assertEqual(out["breached"], 1)
        read = tasks.read_clock(self._tenant_pool, tenant_id, clock_id)
        self.assertEqual(read["status"], "breached")
        self.assertEqual(read["state"], "breached")
        self.assertIn("business hours", read["settle_reason"])

    def test_a_target_still_inside_its_time_is_left_alone(self):
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id, hours_ago=0,
                             target_seconds=4 * 3600,
                             task_id=self.task(tenant_id, queue_id))
        self.assertEqual(self.sweep(tenant_id)["breached"], 0)
        self.assertEqual(
            tasks.read_clock(self._tenant_pool, tenant_id, clock_id)["status"], "running")

    def pause(self, tenant_id: str, clock_id: str, *, from_start: bool) -> None:
        """An open pause, optionally reaching back to just after the clock started.

        Inserted rather than taken through `pause_clock`, which stamps `now()`: what is
        being tested is a clock that was stopped almost as soon as it started, which is the
        state the product reaches by somebody pausing it and a fortnight passing.
        """
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            conn.execute(
                "INSERT INTO plt01.tsk_sla_pauses"
                " (tenant_id, clock_id, paused_at, reason, paused_by, pause_correlation_id)"
                " SELECT %s, clock_id,"
                "        CASE WHEN %s THEN started_at + interval '1 minute' ELSE now() END,"
                "        'waiting on the member', %s, %s"
                "   FROM plt01.tsk_sla_clocks WHERE clock_id = %s",
                (tenant_id, from_start, ACTOR, self.cid(), clock_id))

    def test_a_pause_that_keeps_a_clock_under_its_target_keeps_it_out_of_the_sweep(self):
        """The arithmetic is the whole rule: `_consumed` subtracts the pause, so a clock
        stopped before its time ran out has not spent it."""
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id,
                             task_id=self.task(tenant_id, queue_id))
        self.pause(tenant_id, clock_id, from_start=True)
        self.assertEqual(self.sweep(tenant_id)["breached"], 0)
        self.assertEqual(
            tasks.read_clock(self._tenant_pool, tenant_id, clock_id)["status"], "running")

    def test_pausing_a_clock_whose_target_has_already_gone_does_not_un_break_it(self):
        """The first version of the sweep returned early for any open pause, which read as
        "a stopped clock is not spending its target" -- true, and already handled by
        `_consumed`. What the guard actually added was an escape: a missed promise could be
        kept out of the sweep for ever by pausing it afterwards. Two rules for one question,
        and the one written as a guard was the wrong one."""
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id,
                             task_id=self.task(tenant_id, queue_id))
        self.pause(tenant_id, clock_id, from_start=False)
        self.assertEqual(self.sweep(tenant_id)["breached"], 1)
        self.assertEqual(
            tasks.read_clock(self._tenant_pool, tenant_id, clock_id)["status"], "breached")

    def test_a_second_pass_settles_nothing_and_raises_nothing(self):
        """What makes the schedule disposable: the runner keeps due-times in memory, so a
        restart makes every job due at once."""
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        escalation = self.queue(tenant_id)
        self.aged(tenant_id, location_id=location_id, escalate_to=escalation,
                  task_id=self.task(tenant_id, queue_id))
        first = self.sweep(tenant_id)
        second = self.sweep(tenant_id)
        self.assertEqual((first["breached"], first["escalated"]), (1, 1))
        self.assertEqual((second["breached"], second["escalated"]), (0, 0))
        self.assertEqual(len(self.escalations(tenant_id, escalation)), 1)

    def test_the_escalation_carries_the_subject_and_points_at_the_clock(self):
        """**It does not cite the case**, and the schema decided that: a task filed under a
        different queue from its case is refused, "so the same work would not be counted in
        two backlogs" -- and an escalation is by definition filed somewhere else. What
        travels is who the missed promise was to."""
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        # A `lead` rather than a member: it is a recorded claim, so no MOD-014
        # row is needed and what the test is about -- that the subject travels --
        # is unchanged.
        person = str(uuid.uuid4())
        case_id = self.case(tenant_id, queue_id, subject_kind="lead",
                            subject_id=person, title="Card not working")
        escalation = self.queue(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id, escalate_to=escalation,
                             case_id=case_id)
        self.sweep(tenant_id)
        raised = self.escalations(tenant_id, escalation)
        self.assertEqual(len(raised), 1)
        self.assertEqual(raised[0]["subject_kind"], "lead")
        self.assertEqual(raised[0]["subject_id"], person)
        self.assertEqual(raised[0]["priority"], "high")
        self.assertIn("Card not working", raised[0]["title"])
        self.assertEqual(raised[0]["evidence_ref"], f"veyro://sla-clocks/{clock_id}")
        self.assertIsNone(raised[0]["case_id"])

    def test_a_clock_with_no_route_is_judged_and_nothing_is_raised(self):
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        self.aged(tenant_id, location_id=location_id, task_id=self.task(tenant_id, queue_id))
        out = self.sweep(tenant_id)
        self.assertEqual((out["breached"], out["escalated"], out["skipped"]), (1, 0, []))

    def test_a_route_retired_after_the_clock_started_is_reported_rather_than_rung(self):
        """**A route checked once is a route with a window.** The write-time trigger refuses
        an escalation to a retired queue and nothing stops the queue being retired
        afterwards. The breach stands -- it is true whatever the route says."""
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        escalation = self.queue(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id, escalate_to=escalation,
                             task_id=self.task(tenant_id, queue_id))
        tasks.retire_queue(self._tenant_pool, tenant_id, escalation, reason="team merged",
                           actor_id=ACTOR, correlation_id=self.cid())
        out = self.sweep(tenant_id)
        self.assertEqual((out["breached"], out["escalated"]), (1, 0))
        self.assertIn("retired", out["skipped"][0]["why"])
        self.assertEqual(out["skipped"][0]["clock_id"], clock_id)
        self.assertEqual(self.escalations(tenant_id, escalation), [])

    def test_retiring_the_route_does_not_freeze_the_clock_it_pointed_at(self):
        """`0022`. The escalation trigger is `BEFORE INSERT OR UPDATE` and re-judged the
        route on every write, so retiring a queue refused **every** later update to every
        clock pointing at it -- the settlement included. A target whose escalation team was
        merged into another could never be judged: it stayed `running` for ever and R07
        counted it as still in hand.

        A guard that admits a state nothing can leave is worse than no guard. Setting or
        moving a route to a retired queue is still refused, which the sibling case above
        this one proves.
        """
        tenant_id = self.tenant()
        location_id, queue_id = self.club(tenant_id)
        escalation = self.queue(tenant_id)
        clock_id = self.aged(tenant_id, location_id=location_id, escalate_to=escalation,
                             hours_ago=0, target_seconds=4 * 3600,
                             task_id=self.task(tenant_id, queue_id))
        tasks.retire_queue(self._tenant_pool, tenant_id, escalation, reason="team merged",
                           actor_id=ACTOR, correlation_id=self.cid())
        out = tasks.settle_clock(
            self._tenant_pool, tenant_id, clock_id, status="met",
            reason="answered the member the same morning", actor_id=ACTOR,
            correlation_id=self.cid())
        self.assertEqual(out["status"], "met")

    def test_a_club_with_no_calendar_is_judged_on_elapsed_time(self):
        """The fallback is the same one the read states, because both go through
        `_consumed`: a business-hours clock against an empty calendar never advances, which
        is a breach that never fires."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        queue_id = self.queue(tenant_id, location_id=location_id)
        clock_id = self.aged(tenant_id, location_id=location_id,
                             task_id=self.task(tenant_id, queue_id))
        self.assertEqual(self.sweep(tenant_id)["breached"], 1)
        self.assertIn(
            "elapsed time",
            tasks.read_clock(self._tenant_pool, tenant_id, clock_id)["settle_reason"])


class CaseResolutionTests(TasksTestCase):
    def test_a_task_naming_a_case_that_does_not_exist_is_refused_with_a_reason(self):
        """`0023` deleted the trigger branch that duplicated the composite foreign key, and
        this application has no handler for a psycopg error at all -- only
        `RequestValidationError` and `ServiceError` -- so an unknown `case_id` answered 500
        whether the key or the trigger spoke. An id shape-checked and never resolved is
        MOD-009's finding; the queue and the assignee beside it were already looked up."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        with self.assertRaises(NotFound) as caught:
            self.task(tenant_id, queue_id, case_id=str(uuid.uuid4()))
        self.assertEqual(str(caught.exception), "case_not_found")


class AttentionItemTests(TasksTestCase):
    """ADM-CC-06 and ADM-CC-07 against a real database: `0024`'s four fields and the sheet.

    The decisions are `test_tasks_attention.py`; what is here is whether the right inputs
    reach them and whether the writes the sheet's actions make land where they say.
    """

    def person(self, tenant_id: str, name: str = "Hala Barakat") -> str:
        return str(people.create_person(
            self._tenant_pool, tenant_id, legal_name=name, actor_id=ACTOR,
            correlation_id=self.cid())["person_id"])

    def sheet(self, tenant_id: str, case_id: str, *, viewer: str | None = None,
              reasons: bool = True) -> dict:
        return tasks.read_attention_item(
            self._tenant_pool, tenant_id, case_id, viewer_person_id=viewer,
            may_read_reasons=reasons)

    def entries(self, sheet: dict, kind: str) -> list[dict]:
        return [e for e in sheet["entries"] if e["entry_kind"] == kind]

    # ---- the owner, and ADM-CC-06's four assignment states

    def test_the_four_assignment_states_the_canvas_draws(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        me, them = self.person(tenant_id), self.person(tenant_id, "Nadia Suleiman")

        self.assertEqual(self.sheet(tenant_id, case_id, viewer=me)["state"], "unassigned")
        tasks.assign_case(self._tenant_pool, tenant_id, case_id, assignee_person_id=me,
                          actor_id=ACTOR, correlation_id=self.cid())
        self.assertEqual(self.sheet(tenant_id, case_id, viewer=me)["state"], "mine")
        self.assertEqual(
            self.sheet(tenant_id, case_id, viewer=them)["state"], "someone_else")
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                          resolution_reason="replaced the card", actor_id=ACTOR,
                          correlation_id=self.cid())
        self.assertEqual(self.sheet(tenant_id, case_id, viewer=me)["state"], "resolved")

    def test_which_assignment_act_it_was_is_derived_rather_than_declared(self):
        """One route sets the column and the entry says which act it was, so a caller cannot
        report a release and perform a handover."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        me, them = self.person(tenant_id), self.person(tenant_id, "Nadia Suleiman")

        first = tasks.assign_case(self._tenant_pool, tenant_id, case_id,
                                  assignee_person_id=me, actor_id=ACTOR,
                                  correlation_id=self.cid())
        self.assertEqual(first["act"], "assigned")
        over = tasks.assign_case(self._tenant_pool, tenant_id, case_id,
                                 assignee_person_id=them, actor_id=ACTOR,
                                 correlation_id=self.cid())
        self.assertEqual(over["act"], "handed_over")
        released = tasks.assign_case(self._tenant_pool, tenant_id, case_id,
                                     assignee_person_id=None, actor_id=ACTOR,
                                     correlation_id=self.cid())
        self.assertEqual(released["act"], "released")
        # **The handover is on the timeline, which is where the history lives.** The column
        # answers "who has it"; an entry answers "who handed it over and to whom".
        kinds = self.entries(self.sheet(tenant_id, case_id), "assignment")
        self.assertEqual(len(kinds), 3)
        self.assertIn(them, kinds[1]["summary"])
        self.assertIn(me, kinds[1]["summary"])

    def test_assigning_to_who_already_has_it_writes_no_second_entry(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        me = self.person(tenant_id)
        for _ in range(2):
            out = tasks.assign_case(self._tenant_pool, tenant_id, case_id,
                                    assignee_person_id=me, actor_id=ACTOR,
                                    correlation_id=self.cid())
        self.assertTrue(out["repeated"])
        self.assertEqual(len(self.entries(self.sheet(tenant_id, case_id), "assignment")), 1)

    def test_an_unknown_assignee_and_a_closed_case_are_both_refused(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        with self.assertRaises(NotFound):
            tasks.assign_case(self._tenant_pool, tenant_id, case_id,
                              assignee_person_id=str(uuid.uuid4()), actor_id=ACTOR,
                              correlation_id=self.cid())
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                          resolution_reason="done", actor_id=ACTOR,
                          correlation_id=self.cid())
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="closed",
                          resolution_reason=None, actor_id=ACTOR,
                          correlation_id=self.cid())
        with self.assertRaises(Conflict):
            tasks.assign_case(self._tenant_pool, tenant_id, case_id,
                              assignee_person_id=self.person(tenant_id), actor_id=ACTOR,
                              correlation_id=self.cid())

    # ---- the deferral, which the canvas says cannot be a dismissal

    def test_a_deferral_carries_a_date_and_an_account_of_why(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        until = datetime.now(UTC) + timedelta(days=3)
        out = tasks.snooze_case(self._tenant_pool, tenant_id, case_id, until=until,
                                reason="waiting on the member", actor_id=ACTOR,
                                correlation_id=self.cid())
        self.assertEqual(out["state"], "snoozed")
        sheet = self.sheet(tenant_id, case_id)
        self.assertEqual(sheet["state"], "snoozed")
        self.assertIsNotNone(sheet["snoozed_at"])
        self.assertIn("waiting on the member", sheet["snooze_reason"])
        self.assertEqual(len(self.entries(sheet, "deferral")), 1)

    def test_a_date_that_is_past_or_beyond_a_year_and_a_blank_reason_are_refused(self):
        """The schema bounds the far end at a year from the deferral and the service bounds
        the near one, because `snoozed_until <= now()` is a deferral that is over before it
        starts -- `item_state` reads it as open and the caller is told it worked."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        now = datetime.now(UTC)
        for until, reason in ((now - timedelta(minutes=1), "fine"),
                              (now, "fine"),
                              (now + timedelta(days=400), "fine"),
                              (now + timedelta(days=3), "\t")):
            with self.assertRaises(InvalidRequest):
                tasks.snooze_case(self._tenant_pool, tenant_id, case_id, until=until,
                                  reason=reason, actor_id=ACTOR,
                                  correlation_id=self.cid())

    def test_a_settled_case_has_nothing_to_defer(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                          resolution_reason="replaced the card", actor_id=ACTOR,
                          correlation_id=self.cid())
        with self.assertRaises(Conflict):
            tasks.snooze_case(self._tenant_pool, tenant_id, case_id,
                              until=datetime.now(UTC) + timedelta(days=1),
                              reason="later", actor_id=ACTOR, correlation_id=self.cid())

    def test_a_deferral_can_be_ended_early_and_the_account_survives_on_the_timeline(self):
        """The remedy a routine act needs: a return date typed as next year would otherwise
        hide an exception for eleven months. Clearing the columns takes the reason with
        them, which is why every deferral writes an entry."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        until = datetime.now(UTC) + timedelta(days=300)
        tasks.snooze_case(self._tenant_pool, tenant_id, case_id, until=until,
                          reason="mistyped the year", actor_id=ACTOR,
                          correlation_id=self.cid())
        back = tasks.return_case_to_queue(
            self._tenant_pool, tenant_id, case_id, reason="brought forward",
            actor_id=ACTOR, correlation_id=self.cid())
        self.assertEqual(back["state"], "open")
        sheet = self.sheet(tenant_id, case_id)
        self.assertEqual(sheet["state"], "unassigned")
        self.assertIsNone(sheet["snoozed_until"])
        self.assertIsNone(sheet["snooze_reason"])
        deferrals = self.entries(sheet, "deferral")
        self.assertEqual(len(deferrals), 2)
        self.assertIn("mistyped the year", deferrals[0]["summary"])
        self.assertIn("brought forward", deferrals[1]["summary"])

    def test_a_case_that_is_not_deferred_cannot_be_brought_back(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        with self.assertRaises(Conflict):
            tasks.return_case_to_queue(self._tenant_pool, tenant_id, case_id,
                                       reason="why", actor_id=ACTOR,
                                       correlation_id=self.cid())
        with self.assertRaises(InvalidRequest):
            tasks.return_case_to_queue(self._tenant_pool, tenant_id, case_id,
                                       reason="  ", actor_id=ACTOR,
                                       correlation_id=self.cid())

    # ---- the records an exception is about, which a single subject cannot hold

    def test_an_exception_is_about_many_records_and_the_count_cannot_be_inflated(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        hala = self.person(tenant_id)
        first = tasks.add_affected(self._tenant_pool, tenant_id, case_id,
                                   affected_kind="member", affected_id=hala,
                                   actor_id=ACTOR, correlation_id=self.cid())
        self.assertFalse(first["repeated"])
        self.assertFalse(first["subject_is_a_recorded_claim"])
        again = tasks.add_affected(self._tenant_pool, tenant_id, case_id,
                                   affected_kind="member", affected_id=hala,
                                   actor_id=ACTOR, correlation_id=self.cid())
        self.assertTrue(again["repeated"])
        self.assertEqual(self.sheet(tenant_id, case_id)["affected_count"], 1)

    def test_an_affected_record_of_a_resolvable_kind_has_to_exist(self):
        """`_resolve_subject` is the same function the case's own subject goes through, so an
        exception cannot be about an invoice nobody issued."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        with self.assertRaises(NotFound):
            tasks.add_affected(self._tenant_pool, tenant_id, case_id,
                               affected_kind="member", affected_id=str(uuid.uuid4()),
                               actor_id=ACTOR, correlation_id=self.cid())
        # A lead is a recorded claim -- MOD-027's, with nothing here to resolve against --
        # and the answer says which it was rather than presenting it as verified.
        claim = tasks.add_affected(self._tenant_pool, tenant_id, case_id,
                                   affected_kind="lead", affected_id=str(uuid.uuid4()),
                                   actor_id=ACTOR, correlation_id=self.cid())
        self.assertTrue(claim["subject_is_a_recorded_claim"])

    def test_the_tenant_is_not_an_affected_record(self):
        """An affected record names a specific thing, and a case about the tenant is about
        the row's own `tenant_id`, which RLS already bounds."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        with self.assertRaises(InvalidRequest):
            tasks.add_affected(self._tenant_pool, tenant_id, case_id,
                               affected_kind="tenant", affected_id=str(uuid.uuid4()),
                               actor_id=ACTOR, correlation_id=self.cid())

    def test_a_record_is_withdrawn_rather_than_deleted_and_only_once(self):
        """"Was this member ever on this exception, and who said so" is asked precisely
        when somebody was contacted by mistake."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        hala = self.person(tenant_id)
        tasks.add_affected(self._tenant_pool, tenant_id, case_id, affected_kind="member",
                           affected_id=hala, actor_id=ACTOR, correlation_id=self.cid())
        with self.assertRaises(InvalidRequest):
            tasks.withdraw_affected(self._tenant_pool, tenant_id, case_id,
                                    affected_kind="member", affected_id=hala, reason="\t",
                                    actor_id=ACTOR, correlation_id=self.cid())
        tasks.withdraw_affected(self._tenant_pool, tenant_id, case_id,
                                affected_kind="member", affected_id=hala,
                                reason="wrong member", actor_id=ACTOR,
                                correlation_id=self.cid())
        sheet = self.sheet(tenant_id, case_id)
        self.assertEqual(sheet["affected_count"], 0)
        self.assertEqual(len(sheet["withdrawn"]), 1)
        self.assertIn("wrong member", sheet["withdrawn"][0]["withdraw_reason"])
        # The row recedes rather than disappearing, so the second attempt finds nothing live.
        with self.assertRaises(NotFound):
            tasks.withdraw_affected(self._tenant_pool, tenant_id, case_id,
                                    affected_kind="member", affected_id=hala,
                                    reason="again", actor_id=ACTOR,
                                    correlation_id=self.cid())

    def test_a_withdrawal_reason_is_masked_like_every_other_reason_here(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        hala = self.person(tenant_id)
        tasks.add_affected(self._tenant_pool, tenant_id, case_id, affected_kind="member",
                           affected_id=hala, actor_id=ACTOR, correlation_id=self.cid())
        tasks.withdraw_affected(self._tenant_pool, tenant_id, case_id,
                                affected_kind="member", affected_id=hala,
                                reason="she is not on the policy", actor_id=ACTOR,
                                correlation_id=self.cid())
        masked = self.sheet(tenant_id, case_id, reasons=False)
        self.assertEqual(masked["withdrawn"][0]["withdraw_reason"], tasks.WITHHELD)

    # ---- ADM-CC-07, and R07's five questions

    def test_the_resolved_record_carries_the_median_and_no_un_resolve(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        for n in range(3):
            case_id = self.case(tenant_id, queue_id, case_number=f"R-{n}0000")
            tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                              resolution_reason=f"handled {n}", actor_id=ACTOR,
                              correlation_id=self.cid())
        out = tasks.list_resolved(self._tenant_pool, tenant_id, may_read_reasons=True)
        self.assertEqual(out["resolved"], 3)
        self.assertEqual(out["window_hours"], tasks.RESOLVED_WINDOW_HOURS)
        self.assertIsNotNone(out["median_seconds"])
        self.assertIn("appears in this list as a new row", out["no_un_resolve"])
        self.assertTrue(all(c["took_seconds"] is not None for c in out["cases"]))
        self.assertTrue(all(c["source"] == "manual" for c in out["cases"]))

    def test_an_empty_window_has_no_median_rather_than_a_median_of_zero(self):
        """MOD-011's rule: a dashboard reporting a median of zero reads as a team resolving
        everything instantly."""
        tenant_id = self.tenant()
        out = tasks.list_resolved(self._tenant_pool, tenant_id, may_read_reasons=True)
        self.assertEqual(out["resolved"], 0)
        self.assertIsNone(out["median_seconds"])

    def test_the_outcome_is_masked_like_every_other_reason_here(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id)
        tasks.settle_case(self._tenant_pool, tenant_id, case_id, target="resolved",
                          resolution_reason="she is having chemotherapy on Tuesdays",
                          actor_id=ACTOR, correlation_id=self.cid())
        masked = tasks.list_resolved(self._tenant_pool, tenant_id, may_read_reasons=False)
        self.assertEqual(masked["cases"][0]["outcome"], tasks.WITHHELD)
        self.assertTrue(masked["cases"][0]["reason_masked"])
        # And the row is still there: an absent row says nothing was resolved, which is a
        # different and wrong fact.
        self.assertEqual(masked["resolved"], 1)

    def test_a_window_outside_its_bounds_is_refused_rather_than_clamped(self):
        tenant_id = self.tenant()
        for bad in (0, 24 * 91):
            with self.assertRaises(InvalidRequest):
                tasks.list_resolved(self._tenant_pool, tenant_id, window_hours=bad,
                                    may_read_reasons=True)

    def test_the_workload_answers_the_three_chips_the_canvas_draws(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        me = self.person(tenant_id)
        mine = self.task(tenant_id, queue_id)
        # `assign_task` takes no actor, unlike `assign_case`: a task has no timeline to
        # write a handover to, which is a gap the module records rather than one this test
        # works around.
        tasks.assign_task(self._tenant_pool, tenant_id, mine, assignee_person_id=me)
        self.task(tenant_id, queue_id)
        self.task(tenant_id, queue_id,
                  due_at=datetime.now(UTC) - timedelta(days=1))
        out = tasks.workload(self._tenant_pool, tenant_id, viewer_person_id=me)
        self.assertEqual(out["mine"], 1)
        self.assertEqual(out["team"], 3)
        self.assertEqual(out["overdue"], 1)
        self.assertFalse(out["mine_is_zero_without_a_person_record"])

    def test_mine_is_zero_without_a_person_record_rather_than_everybodys_work(self):
        """Staff hold permissions and do not have to be anybody in particular, so an
        unlinked identity is not an error -- but it is also not the team count, which is
        what a fallback would have made it."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        self.task(tenant_id, queue_id)
        out = tasks.workload(self._tenant_pool, tenant_id, viewer_person_id=None)
        self.assertEqual(out["mine"], 0)
        self.assertEqual(out["team"], 1)
        self.assertTrue(out["mine_is_zero_without_a_person_record"])

    def test_the_bottleneck_names_the_blockers_rather_than_counting_blocked_work(self):
        """MOD-005's "a rule id is not a reason" one level up: a count of blocked tasks is
        what a reader cannot act on, and the blocker is where somebody should look."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        blocker = self.task(tenant_id, queue_id)
        for _ in range(2):
            waiting = self.task(tenant_id, queue_id)
            tasks.add_dependency(self._tenant_pool, tenant_id, task_id=waiting,
                                 depends_on_task_id=blocker, actor_id=ACTOR,
                                 correlation_id=self.cid())
        out = tasks.workload(self._tenant_pool, tenant_id, viewer_person_id=None)
        self.assertEqual(out["bottleneck"], [{"task_id": blocker, "blocking": 2}])

    def test_a_settled_blocker_blocks_nothing(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        blocker = self.task(tenant_id, queue_id)
        waiting = self.task(tenant_id, queue_id)
        tasks.add_dependency(self._tenant_pool, tenant_id, task_id=waiting,
                             depends_on_task_id=blocker, actor_id=ACTOR,
                             correlation_id=self.cid())
        tasks.change_task_status(self._tenant_pool, tenant_id, blocker, target="done",
                                 reason="finished", actor_id=ACTOR,
                                 correlation_id=self.cid())
        out = tasks.workload(self._tenant_pool, tenant_id, viewer_person_id=None)
        self.assertEqual(out["bottleneck"], [])

    def test_compliance_has_no_share_until_something_has_been_judged(self):
        """MOD-011's rule again: a window in which nothing was judged is a window with no
        measurement, not one in which nothing was kept."""
        tenant_id = self.tenant()
        out = tasks.workload(self._tenant_pool, tenant_id, viewer_person_id=None)
        self.assertEqual(out["compliance"]["met"], 0)
        self.assertEqual(out["compliance"]["breached"], 0)
        self.assertIsNone(out["compliance"]["met_basis_points"])

    def test_the_aging_buckets_are_the_declared_ones(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        self.task(tenant_id, queue_id)
        out = tasks.workload(self._tenant_pool, tenant_id, viewer_person_id=None)
        self.assertEqual(out["aging"]["bucket_days"], list(tasks.AGING_DAYS))
        self.assertEqual(out["aging"]["under_a_day"], 1)
        self.assertEqual(out["aging"]["older"], 0)
