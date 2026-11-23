"""MOD-026 slice 1b over HTTP: the gate, the masking, and the route-ordering trap.

**MOD-014's review found that no test had ever called a `/people` route successfully**, so
the gate return, the permission resolution and the actor lookup were exercised by nothing and
four findings passed a green suite. These are the assertions that need the request path:
which permission each route charges, that the masking is decided by the gate rather than by
the caller, and that a literal segment declared after a path parameter is never reached --
which `/memberships/summary` was bitten by and which reasoning cannot settle.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.tasks import service as tasks
from tests.support import GatedApiTestCase

READ = ["tasks.queue.read", "tasks.calendar.read", "tasks.task.read", "tasks.case.read"]
WRITE = ["tasks.queue.write", "tasks.calendar.write", "tasks.task.write",
         "tasks.case.write"]


class TasksApiTestCase(GatedApiTestCase):
    def scoped(self, tenant_id: str, permissions: list[str]) -> dict[str, str]:
        """Headers for a session holding exactly these permissions, at AAL 1."""
        return self.headers(tenant_id, self.grant(tenant_id, permissions))

    def queue(self, tenant_id: str, **over: object) -> str:
        body: dict = {"queue_key": f"q{uuid.uuid4().hex[:8]}", "display_name": "Front desk"}
        body.update(over)
        made = self.client.post("/tasks/queues", json={**body, **self.correlation()},
                                headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return str(made.json()["queue_id"])

    def task(self, tenant_id: str, queue_id: str, **over: object) -> str:
        body: dict = {"queue_id": queue_id, "title": "Call about the card",
                      "subject_kind": "tenant", "source": "manual",
                      "idempotency_key": f"k{uuid.uuid4().hex[:10]}"}
        body.update(over)
        made = self.client.post("/tasks", json={**body, **self.correlation()},
                                headers=self.headers(tenant_id))
        self.assertEqual(made.status_code, 201, made.text)
        return str(made.json()["task_id"])


class RoutingTests(TasksApiTestCase):
    def test_the_literal_segments_are_reached_rather_than_the_path_parameter(self):
        """**FastAPI matches in declaration order**, so a literal behind a path parameter is
        never reached: `/memberships/summary` was answered by `/memberships/{id}` and replied
        422 `bad_membership_id`. Four of this module's reads sit under `/tasks`, so this is
        the assertion rather than a reading of the file."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        for path in ("/tasks/queues", "/tasks/cases"):
            with self.subTest(path=path):
                answer = self.client.get(path, headers=owner)
                self.assertEqual(answer.status_code, 200, f"{path}: {answer.text}")
        # The calendar takes a required query parameter, so a bare call is a 422 about
        # `location_id` -- not about a malformed task id, which is what the trap looks like.
        answer = self.client.get("/tasks/calendar", headers=owner)
        self.assertEqual(answer.status_code, 422, answer.text)
        self.assertNotIn("task_id", answer.text)

    def test_a_malformed_id_is_a_422_on_every_route_that_takes_one(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        cases = [
            ("post", "/tasks/queues/not-a-uuid/retire", {"reason": "x"}),
            ("post", "/tasks/calendar/not-a-uuid/withdraw", {"reason": "x"}),
            ("post", "/tasks/cases/not-a-uuid/settle",
             {"target": "closed", "resolution_reason": "x"}),
            ("post", "/tasks/not-a-uuid/status", {"target": "in_progress"}),
            ("get", "/tasks/not-a-uuid", None),
            ("get", "/tasks/cases/not-a-uuid", None),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                if method == "get":
                    answer = self.client.get(path, headers=owner)
                else:
                    assert body is not None
                    answer = self.client.post(
                        path, json={**body, **self.correlation()}, headers=owner)
                self.assertEqual(answer.status_code, 422, f"{path}: {answer.text}")


class GateTests(TasksApiTestCase):
    def test_a_read_permission_does_not_open_a_write_route(self):
        tenant_id = self.tenant()
        reader = self.scoped(tenant_id, READ)
        answer = self.client.post("/tasks/queues", json={
            "queue_key": "front", "display_name": "Front desk", **self.correlation()},
            headers=reader)
        self.assertEqual(answer.status_code, 403, answer.text)

    def test_a_queue_permission_does_not_open_the_task_list(self):
        """MOD-013's `GET /notifications/channels` finding: "see the templates" also read
        what every message cost the tenant. A queue reader is not a task reader."""
        tenant_id = self.tenant()
        narrow = self.scoped(tenant_id, ["tasks.queue.read"])
        self.assertEqual(
            self.client.get("/tasks/queues", headers=narrow).status_code, 200)
        self.assertEqual(
            self.client.get("/tasks", headers=narrow).status_code, 403)
        self.assertEqual(
            self.client.get("/tasks/cases", headers=narrow).status_code, 403)

    def test_a_session_holding_nothing_is_refused_every_route(self):
        tenant_id = self.tenant()
        nobody = self.scoped(tenant_id, [])
        for path in ("/tasks", "/tasks/queues", "/tasks/cases"):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path, headers=nobody).status_code, 403)


class MaskingTests(TasksApiTestCase):
    def test_the_gate_decides_the_mask_and_not_the_caller(self):
        """**The reason is masked for a reader who could not have written it.** MOD-019's
        trade, and the request path is where it has to be proved: a service test passing
        `may_read_reasons=False` proves the service, not that the route computes it."""
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        settled = self.client.post(f"/tasks/{task_id}/status", json={
            "target": "done", "reason": "she is having chemotherapy on Tuesdays",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(settled.status_code, 200, settled.text)

        reader = self.scoped(tenant_id, ["tasks.task.read"])
        masked = self.client.get(f"/tasks/{task_id}", headers=reader)
        self.assertEqual(masked.status_code, 200, masked.text)
        self.assertEqual(masked.json()["settle_reason"], tasks.WITHHELD)
        self.assertTrue(masked.json()["reason_masked"])
        # And the task is still there: a redacted record still exists.
        self.assertEqual(masked.json()["title"], "Call about the card")

        writer = self.scoped(tenant_id, ["tasks.task.read", "tasks.task.write"])
        shown = self.client.get(f"/tasks/{task_id}", headers=writer)
        self.assertIn("chemotherapy", shown.json()["settle_reason"])
        self.assertFalse(shown.json()["reason_masked"])

    def test_the_listing_carries_no_name_address_or_birth_date(self):
        tenant_id = self.tenant()
        self.task(tenant_id, self.queue(tenant_id))
        body = self.client.get("/tasks", headers=self.headers(tenant_id)).text
        for leaked in ("legal_name", "date_of_birth", "email_normalized"):
            self.assertNotIn(leaked, body)


class LifecycleTests(TasksApiTestCase):
    def test_a_create_is_idempotent_over_http(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        key = f"k{uuid.uuid4().hex[:10]}"
        body = {"queue_id": queue_id, "title": "First", "subject_kind": "tenant",
                "source": "manual", "idempotency_key": key}
        owner = self.headers(tenant_id)
        first = self.client.post("/tasks", json={**body, **self.correlation()},
                                 headers=owner)
        again = self.client.post(
            "/tasks", json={**body, "title": "Second", **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        # **201 and `repeated`, not 409.** A caller told "conflict" cannot tell a duplicate
        # request from a real collision, which is MOD-017's finding in three commands.
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(first.json()["task_id"], again.json()["task_id"])
        self.assertEqual(again.json()["title"], "First")

    def test_a_settlement_without_a_reason_is_refused(self):
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        answer = self.client.post(f"/tasks/{task_id}/status", json={
            "target": "done", **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 422, answer.text)

    def test_a_status_outside_the_closed_set_is_a_422_and_not_a_500(self):
        """A `Literal` on the body is refused at the boundary rather than by a CHECK.

        **It does not name the field, and the first version of this test asserted it did.**
        This application replaced FastAPI's validation handler precisely because the default
        echoed the offending *input* into its own 422, which `json.dumps` then refused for a
        `NaN` the parser had accepted -- a 500 from inside a 422, on every route here. So the
        answer is `{"error": "invalid_request"}` and nothing more, which is the trade that
        was made: a caller learns the request was malformed and not which byte of it. Worth
        asserting the shape, because a reader of the route comment would otherwise expect a
        field name that is never coming.
        """
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.queue(tenant_id))
        answer = self.client.post(f"/tasks/{task_id}/status", json={
            "target": "finished", **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 422, answer.text)
        self.assertEqual(answer.json(), {"error": "invalid_request"})

    def test_a_case_carries_its_timeline_and_its_tasks(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        owner = self.headers(tenant_id)
        made = self.client.post("/tasks/cases", json={
            "case_number": f"C-{uuid.uuid4().hex[:6].upper()}", "title": "Card not working",
            "queue_id": queue_id, "subject_kind": "tenant", "source": "manual",
            "idempotency_key": f"k{uuid.uuid4().hex[:10]}", **self.correlation()},
            headers=owner)
        self.assertEqual(made.status_code, 201, made.text)
        case_id = made.json()["case_id"]
        self.task(tenant_id, queue_id, case_id=case_id)
        entry = self.client.post(f"/tasks/cases/{case_id}/entries", json={
            "entry_kind": "communication", "summary": "called her back",
            **self.correlation()}, headers=owner)
        self.assertEqual(entry.status_code, 201, entry.text)
        read = self.client.get(f"/tasks/cases/{case_id}", headers=owner)
        self.assertEqual(len(read.json()["timeline"]), 1)
        self.assertEqual(len(read.json()["tasks"]), 1)
        self.assertIn("no object store", read.json()["documents_are_references"])

    def test_a_calendar_time_that_is_not_hh_mm_is_a_422_not_a_500(self):
        tenant_id = self.tenant()
        answer = self.client.post("/tasks/calendar", json={
            "location_id": str(uuid.uuid4()), "kind": "open", "weekday": 1,
            "opens_at": "nine o'clock", "closes_at": "17:00", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 422, answer.text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ClockRouteTests(TasksApiTestCase):
    def club(self, tenant_id: str) -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        made = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": "Asia/Amman"}, headers=owner)
        self.assertEqual(made.status_code, 201, made.text)
        location_id = str(made.json()["location_id"])
        for weekday in range(5):
            hours = self.client.post("/tasks/calendar", json={
                "location_id": location_id, "kind": "open", "weekday": weekday,
                "opens_at": "09:00", "closes_at": "17:00", **self.correlation()},
                headers=owner)
            self.assertEqual(hours.status_code, 201, hours.text)
        return self.queue(tenant_id, location_id=location_id)

    def test_the_clock_routes_are_reached_rather_than_the_task_path_parameter(self):
        """`/tasks/clocks/{clock_id}` sits under the same prefix as `/tasks/{task_id}`, and
        FastAPI matches in declaration order -- the trap `/memberships/summary` was bitten
        by. A clock id read as a task id would answer 404 for a clock that exists."""
        tenant_id = self.tenant()
        queue_id = self.club(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        owner = self.headers(tenant_id)
        made = self.client.post("/tasks/clocks", json={
            "task_id": task_id, "target_seconds": 4 * 3600, **self.correlation()},
            headers=owner)
        self.assertEqual(made.status_code, 201, made.text)
        read = self.client.get(
            f"/tasks/clocks/{made.json()['clock_id']}", headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["measured_in"], "business_hours")
        self.assertIn("due_at", read.json())

    def test_the_sla_permission_is_its_own(self):
        """MOD-013's finding: a permission's name is a claim about what it is for. Somebody
        who works tasks is not necessarily who decides what the club promises."""
        tenant_id = self.tenant()
        queue_id = self.club(tenant_id)
        task_id = self.task(tenant_id, queue_id)
        worker = self.scoped(tenant_id, ["tasks.task.read", "tasks.task.write"])
        refused = self.client.post("/tasks/clocks", json={
            "task_id": task_id, "target_seconds": 3600, **self.correlation()},
            headers=worker)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_a_target_outside_its_bounds_is_refused_at_the_boundary(self):
        """Bounded on the body as well as in the schema, so an out-of-range integer is a
        refusal rather than a `DataError` the handlers do not catch -- MOD-011's and
        MOD-012's finding, which this build has now paid for three times."""
        tenant_id = self.tenant()
        task_id = self.task(tenant_id, self.club(tenant_id))
        for seconds in (1, 10**12):
            with self.subTest(seconds=seconds):
                answer = self.client.post("/tasks/clocks", json={
                    "task_id": task_id, "target_seconds": seconds, **self.correlation()},
                    headers=self.headers(tenant_id))
                self.assertEqual(answer.status_code, 422, answer.text)


class SweepRouteTests(TasksApiTestCase):
    def test_there_is_no_route_that_settles_breaches(self):
        """Deliberate, and this is the test that keeps it deliberate.

        `sweep_breaches` decides whether somebody failed to answer in time, and it reads its
        own clock: MOD-020's settlement takes no caller-supplied instant for the same reason,
        because a settlement time a caller chooses decides who is recorded as having failed.
        A route would be the other half of that -- a caller choosing *when* the judgement is
        made, which is the same thing said differently -- so the only caller is the worker,
        and there is no permission for it in the catalogue.

        The clock routes that do exist are the asserted other half: a target can be set,
        paused, resumed, read and settled **by a person who says why**, which is the ordinary
        path and is nothing like a sweep.
        """
        routes = {
            (method, getattr(route, "path", ""))
            for route in self.client.app.routes  # type: ignore[attr-defined]
            for method in getattr(route, "methods", set())
        }
        self.assertIn(("POST", "/tasks/clocks"), routes)
        self.assertIn(("POST", "/tasks/clocks/{clock_id}/settle"), routes)
        self.assertNotIn(("POST", "/tasks/clocks/sweep"), routes)
        self.assertFalse([r for r in routes if "breach" in r[1]])


class AttentionApiTests(TasksApiTestCase):
    """ADM-CC-06 and ADM-CC-07 over HTTP, which is the only layer that proves three things.

    MOD-014's review found four defects that passed a green suite because no test had ever
    called a `/people` route successfully: the gate return, the permission resolution that
    decides the mask, and the actor lookup are exercised by nothing else. All three are new
    here -- the sheet masks, and its state depends on a viewer the route derives.
    """

    def case(self, tenant_id: str, queue_id: str, headers: dict[str, str],
             **over: object) -> str:
        body: dict = {
            "case_number": f"C-{uuid.uuid4().hex[:6].upper()}", "title": "Card not working",
            "queue_id": queue_id, "subject_kind": "tenant", "source": "manual",
            "idempotency_key": f"k{uuid.uuid4().hex[:10]}"}
        body.update(over)
        made = self.client.post("/tasks/cases", json={**body, **self.correlation()},
                                headers=headers)
        self.assertEqual(made.status_code, 201, made.text)
        return str(made.json()["case_id"])

    def test_the_sheet_is_readable_and_its_reasons_are_masked_by_the_gate(self):
        """The read needs `tasks.case.read`; the prose needs `tasks.case.write`. A session
        holding only the read gets the row and the marker, which is the distinction -- an
        absent field reads as "there was nothing here", the one answer that is always wrong.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, owner)
        until = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        deferred = self.client.post(f"/tasks/cases/{case_id}/snooze", json={
            "snoozed_until": until, "reason": "waiting on the member",
            **self.correlation()}, headers=owner)
        self.assertEqual(deferred.status_code, 200, deferred.text)

        reader = self.scoped(tenant_id, ["tasks.case.read"])
        masked = self.client.get(f"/tasks/cases/{case_id}/attention", headers=reader)
        self.assertEqual(masked.status_code, 200, masked.text)
        self.assertEqual(masked.json()["snooze_reason"], "__withheld__")
        self.assertTrue(masked.json()["reason_masked"])
        self.assertEqual(masked.json()["state"], "snoozed")

        full = self.client.get(f"/tasks/cases/{case_id}/attention", headers=owner)
        self.assertIn("waiting on the member", full.json()["snooze_reason"])

    def test_the_sheet_refuses_a_session_holding_nothing(self):
        tenant_id = self.tenant()
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, self.headers(tenant_id))
        refused = self.client.get(f"/tasks/cases/{case_id}/attention",
                                  headers=self.scoped(tenant_id, []))
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_the_viewer_is_derived_and_no_route_accepts_one(self):
        """The sheet's states include "assigned to me", so the answer depends on who asks --
        and a `viewer_person_id` on the query string would let a reader ask as somebody else,
        which is MOD-020's four caller-supplied person ids in one route. An owner session
        with no `ppl_identity_links` row therefore reads an assigned case as somebody
        else's, which is true."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, owner)
        person = self.client.post("/people", json={
            "legal_name": "Nadia Suleiman", **self.correlation()}, headers=owner)
        self.assertEqual(person.status_code, 201, person.text)
        assigned = self.client.post(f"/tasks/cases/{case_id}/assign", json={
            "assignee_person_id": person.json()["person_id"], **self.correlation()},
            headers=owner)
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(assigned.json()["act"], "assigned")

        sheet = self.client.get(f"/tasks/cases/{case_id}/attention", headers=owner).json()
        self.assertEqual(sheet["state"], "someone_else")
        # ADM-CC-06: somebody else's item "keeps every action visible but read-only".
        self.assertFalse(sheet["actions_are_live"])
        # And the parameter does not exist: sending it changes nothing rather than being
        # honoured, because FastAPI does not bind an undeclared query field.
        spoofed = self.client.get(
            f"/tasks/cases/{case_id}/attention",
            params={"viewer_person_id": person.json()["person_id"]}, headers=owner)
        self.assertEqual(spoofed.json()["state"], "someone_else")

    def test_a_blank_deferral_reason_is_refused_at_the_boundary_and_names_no_field(self):
        """This application replaced FastAPI's validation handler, so a 422 here is
        `{"error": "invalid_request"}` and nothing more -- the default echoed the offending
        input and `json.dumps` then refused a `NaN` the parser had accepted."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, owner)
        refused = self.client.post(f"/tasks/cases/{case_id}/snooze", json={
            "snoozed_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "reason": "", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json(), {"error": "invalid_request"})

    def test_an_affected_record_is_added_and_withdrawn_over_http(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, owner)
        lead = str(uuid.uuid4())
        added = self.client.post(f"/tasks/cases/{case_id}/affected", json={
            "affected_kind": "lead", "affected_id": lead, **self.correlation()},
            headers=owner)
        self.assertEqual(added.status_code, 201, added.text)
        self.assertTrue(added.json()["subject_is_a_recorded_claim"])
        sheet = self.client.get(f"/tasks/cases/{case_id}/attention", headers=owner).json()
        self.assertEqual(sheet["affected_count"], 1)
        gone = self.client.post(f"/tasks/cases/{case_id}/affected/withdraw", json={
            "affected_kind": "lead", "affected_id": lead, "reason": "wrong lead",
            **self.correlation()}, headers=owner)
        self.assertEqual(gone.status_code, 200, gone.text)
        after = self.client.get(f"/tasks/cases/{case_id}/attention", headers=owner).json()
        self.assertEqual(after["affected_count"], 0)
        self.assertEqual(len(after["withdrawn"]), 1)

    def test_the_tenant_is_refused_as_an_affected_kind_at_the_boundary(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, owner)
        refused = self.client.post(f"/tasks/cases/{case_id}/affected", json={
            "affected_kind": "tenant", "affected_id": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_the_resolved_record_is_read_only_and_there_is_no_un_resolve_route(self):
        """ADM-CC-07: "Read-only for every role, including Owner. There is no un-resolve."
        This is the assertion that keeps it so -- MOD-018's `test_there_is_no_journal_listing
        _route` shape, where the absence is the control."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = self.case(tenant_id, queue_id, owner)
        settled = self.client.post(f"/tasks/cases/{case_id}/settle", json={
            "target": "resolved", "resolution_reason": "replaced the card",
            **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        read = self.client.get("/tasks/resolved", headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["resolved"], 1)
        self.assertIsNotNone(read.json()["median_seconds"])

        routes = {
            (method, getattr(route, "path", ""))
            for route in self.client.app.routes  # type: ignore[attr-defined]
            for method in getattr(route, "methods", set())
        }
        self.assertIn(("GET", "/tasks/resolved"), routes)
        self.assertFalse([r for r in routes if "un-resolve" in r[1] or "unresolve" in r[1]])

    def test_the_workload_answers_the_chips_and_carries_no_name(self):
        """`tasks.task.read` is routine, so a name here would be a lateral read path around
        `people.person.read` -- MOD-010's `events.event.read` finding. Asserted by field
        name rather than by a substring, because a short literal searched across a body is a
        coin flip against `gen_random_uuid()`."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        self.task(tenant_id, queue_id)
        read = self.client.get("/tasks/workload", headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        self.assertEqual(body["team"], 1)
        self.assertEqual(body["mine"], 0)
        self.assertEqual(body["overdue"], 0)
        forbidden = {"legal_name", "preferred_name", "display_name", "date_of_birth",
                     "email", "phone", "assignee_name"}
        seen: set[str] = set()

        def walk(node: object) -> None:
            if isinstance(node, dict):
                seen.update(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(body)
        self.assertEqual(seen & forbidden, set())


class DerivedViewerTests(TasksApiTestCase):
    """ADM-TSK-01's `Mine` chip and ADM-CC-06's "Assign to me" -- the two actions a browser
    cannot express, and the only layer that proves they are derived rather than accepted.

    A session carries an `identity_id`; the link to a person is MOD-014's through
    `ppl_identity_links`. So a client has no person id for the reader at all, and the two
    wrong answers are both available: accepting one from the query string would let a reader
    ask the question as somebody else (MOD-020's four caller-supplied person ids in one
    route), and falling back to the unfiltered answer would turn "mine" into "everybody's".
    """

    def linked_person(self, tenant_id: str, headers: dict[str, str]) -> str:
        """A person record linked to the owner's own identity, which is what makes the owner
        somebody rather than merely a permission holder."""
        person = self.client.post("/people", json={
            "legal_name": "Rania Haddad", **self.correlation()}, headers=headers)
        self.assertEqual(person.status_code, 201, person.text)
        person_id = str(person.json()["person_id"])
        linked = self.client.post(f"/people/{person_id}/identity-links", json={
            "identity_id": self.owner_identity(tenant_id), **self.correlation()},
            headers=headers)
        self.assertEqual(linked.status_code, 201, linked.text)
        return person_id

    def test_mine_is_empty_for_an_identity_with_no_person_record(self):
        """**And it is empty rather than everything**, which is the half worth asserting:
        staff hold permissions and do not have to be anybody in particular, so this is the
        ordinary state of an owner session -- and a fallback to the unfiltered list would have
        made the chip read as the whole queue's count."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        self.task(tenant_id, queue_id)
        everything = self.client.get("/tasks", headers=owner)
        self.assertEqual(len(everything.json()["tasks"]), 1, everything.text)

        mine = self.client.get("/tasks", params={"mine": "true"}, headers=owner)
        self.assertEqual(mine.status_code, 200, mine.text)
        self.assertEqual(mine.json()["tasks"], [])
        # And `/tasks/workload` says why, so the surface does not report an empty queue.
        workload = self.client.get("/tasks/workload", headers=owner).json()
        self.assertTrue(workload["mine_is_zero_without_a_person_record"])
        self.assertEqual(workload["mine"], 0)
        self.assertEqual(workload["team"], 1)

    def test_mine_returns_the_linked_persons_work_and_nobody_elses(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        me = self.linked_person(tenant_id, owner)
        somebody = self.client.post("/people", json={
            "legal_name": "Nadia Suleiman", **self.correlation()}, headers=owner)
        mine_id = self.task(tenant_id, queue_id, title="Mine", assignee_person_id=me)
        self.task(tenant_id, queue_id, title="Theirs",
                  assignee_person_id=str(somebody.json()["person_id"]))

        mine = self.client.get("/tasks", params={"mine": "true"}, headers=owner).json()
        self.assertEqual([row["task_id"] for row in mine["tasks"]], [mine_id])
        workload = self.client.get("/tasks/workload", headers=owner).json()
        self.assertFalse(workload["mine_is_zero_without_a_person_record"])
        self.assertEqual(workload["mine"], 1)
        self.assertEqual(workload["team"], 2)

    def test_overdue_is_the_servers_filter_and_excludes_a_task_finished_late(self):
        """**The chip's figure and the table's rows have to agree**, which is why this is a
        filter here rather than in the client: a client filtering the fifty rows it was given
        would report whichever of them were late, which is the members list's own finding.
        And a task that was *finished* late is not overdue work -- the filter restricts to the
        statuses still in hand, exactly as the chip's count does."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        late = self.task(tenant_id, queue_id, title="Late", due_at=past)
        ahead = self.task(
            tenant_id, queue_id, title="Ahead",
            due_at=(datetime.now(UTC) + timedelta(days=3)).isoformat())
        done = self.task(tenant_id, queue_id, title="Done late", due_at=past)
        settled = self.client.post(f"/tasks/{done}/status", json={
            "target": "done", "reason": "got there eventually", **self.correlation()},
            headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)

        overdue = self.client.get("/tasks", params={"overdue": "true"},
                                  headers=owner).json()
        self.assertEqual([row["task_id"] for row in overdue["tasks"]], [late])
        self.assertNotIn(ahead, [row["task_id"] for row in overdue["tasks"]])
        # The chip and the table agree, which is the point of the shared status tuple.
        self.assertEqual(self.client.get("/tasks/workload", headers=owner)
                         .json()["overdue"], 1)

    def test_assign_to_self_derives_the_person_and_refuses_both_fields(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        me = self.linked_person(tenant_id, owner)
        case_id = AttentionApiTests.case(self, tenant_id, queue_id, owner)

        taken = self.client.post(f"/tasks/cases/{case_id}/assign", json={
            "to_self": True, **self.correlation()}, headers=owner)
        self.assertEqual(taken.status_code, 200, taken.text)
        self.assertEqual(taken.json()["assignee_person_id"], me)
        # And the sheet now reads as this reader's own, which is the state the flag exists for.
        sheet = self.client.get(f"/tasks/cases/{case_id}/attention", headers=owner).json()
        self.assertEqual(sheet["state"], "mine")
        self.assertTrue(sheet["actions_are_live"])

        # **Both fields together is a caller that does not know which it meant.** Refused at
        # the boundary, so the answer is `{"error": "invalid_request"}` and nothing more.
        confused = self.client.post(f"/tasks/cases/{case_id}/assign", json={
            "to_self": True, "assignee_person_id": me, **self.correlation()}, headers=owner)
        self.assertEqual(confused.status_code, 422, confused.text)
        self.assertEqual(confused.json(), {"error": "invalid_request"})

    def test_assign_to_self_refuses_an_identity_that_is_nobody(self):
        """**Not a release, and not a null assignee.** Both alternatives silently do the
        opposite of what the reader pressed: a release hands the item back to the queue, and a
        null written as an assignment reads as a release in `tsk_cases` afterwards. The link
        is MOD-014's to make, so the refusal names that rather than the permission."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        queue_id = self.queue(tenant_id)
        case_id = AttentionApiTests.case(self, tenant_id, queue_id, owner)
        refused = self.client.post(f"/tasks/cases/{case_id}/assign", json={
            "to_self": True, **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"], "no_person_record_for_this_identity")
        # Unassigned, rather than assigned to nobody -- which the sheet reads differently.
        sheet = self.client.get(f"/tasks/cases/{case_id}/attention", headers=owner).json()
        self.assertEqual(sheet["state"], "unassigned")
        self.assertIsNone(sheet["assignee_person_id"])
