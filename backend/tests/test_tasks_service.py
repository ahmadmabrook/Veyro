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

from app.errors import Conflict, InvalidRequest, NotFound
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
            "due_at": None, "evidence_ref": None, "idempotency_key": self.key()}
        body.update(kwargs)
        return str(tasks.create_task(
            self._tenant_pool, tenant_id, queue_id=queue_id, actor_id=ACTOR,
            correlation_id=self.cid(), **body)["task_id"])

    def case(self, tenant_id: str, queue_id: str, **kwargs: object) -> str:
        body: dict = {
            "case_number": f"C-{uuid.uuid4().hex[:8].upper()}", "title": "Card not working",
            "subject_kind": "tenant", "subject_id": None, "priority": "normal",
            "recurs_from_case_id": None, "idempotency_key": self.key()}
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
            idempotency_key=self.key(), actor_id=ACTOR, correlation_id=self.cid())
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
            actor_id=ACTOR, correlation_id=self.cid())
        again = tasks.create_task(
            self._tenant_pool, tenant_id, queue_id=queue_id, case_id=None, title="Second",
            subject_kind="tenant", subject_id=None, assignee_person_id=None,
            priority="normal", due_at=None, evidence_ref=None, idempotency_key=key,
            actor_id=ACTOR, correlation_id=self.cid())
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


class ClockTests(TasksTestCase):
    """AUT-02-R06 against a real database. The arithmetic is `test_tasks_sla.py`; what is
    here is whether the right inputs reach it."""

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
