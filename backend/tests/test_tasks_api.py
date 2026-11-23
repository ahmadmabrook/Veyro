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
                      "subject_kind": "tenant",
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
                "idempotency_key": key}
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
            "queue_id": queue_id, "subject_kind": "tenant",
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
