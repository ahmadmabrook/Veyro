"""The worker runtime: the registry's own invariants, and the tick against a real database.

Six things are worth a database here and a mock would assert every one of them into existence:
that a job actually moves rows, that running it twice moves them once, that one tenant's
failure does not take the batch with it, that the row a job writes carries the worker's name,
that the route the operations board reads returns what it renders, and that the role a job
declares is the role it gets.

**The last of those is the only negative test in the file that can fail closed, and it does**:
the replay sweep under `veyro_cp_app` is refused by the privilege layer, which is the whole
reason a job declares a role instead of the process holding the union of both. If it ever
passes, the split has stopped meaning anything.

**And the route is tested over HTTP rather than through the service.** MOD-014's review found
four defects that passed a green suite because no test had ever called a `/people` route
successfully, and the three pieces a route adds -- the gate, the permission resolution, the
shape of what it returns -- are exercised by nothing else.
"""

from __future__ import annotations

import threading
import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.db import make_worker_pool, tenant_scope
from app.events import service as events
from app.observability import catalog as metric_catalog
from app.observability import metrics
from app.worker import names, registry, runner
from tests.support import DSN
from tests.test_access_api import AccessApiTestCase

ACTOR = "44444444-4444-4444-8444-444444444444"


class RegistryTests(unittest.TestCase):
    """What has to be true about the registry before anything runs. No database."""

    def test_the_registry_and_the_name_list_agree_in_both_directions(self):
        self.assertEqual(sorted(j.name for j in registry.JOBS), sorted(names.JOB_NAMES))

    def test_a_job_whose_name_is_undeclared_is_refused_at_import(self):
        """The check is only evidence if removing a name breaks it. A job with no declared
        name could not record a metric point at all, because `worker.job_success` declares its
        `job` dimension as a closed set -- so the job would run and be invisible."""
        original = registry.JOBS
        try:
            registry.JOBS = original + (
                registry.Job(name="nobody.declared_this", every=timedelta(seconds=1),
                             role="app", units="x", summary="x", run=lambda ctx: {}),)
            with self.assertRaises(ValueError) as caught:
                registry._check_registry()
            self.assertIn("nobody.declared_this", str(caught.exception))
        finally:
            registry.JOBS = original

    def test_every_job_name_is_a_value_the_metric_will_accept(self):
        """A job name that the metric catalogue does not carry is a point that raises at the
        moment the job finishes -- after the work, which `_record` then swallows. So the
        failure would be a job doing its work with no record that it ran."""
        for job in registry.JOBS:
            with self.subTest(job.name):
                metric_catalog.validate_dimensions("worker.job_success", {"job": job.name})

    def test_every_job_names_a_pool_and_a_cadence_and_a_unit(self):
        for job in registry.JOBS:
            with self.subTest(job.name):
                self.assertIn(job.role, ("app", "worker"))
                self.assertGreater(job.every, timedelta(0))
                self.assertTrue(job.units.strip())
                self.assertTrue(job.summary.strip())

    def test_the_worker_actor_is_stable_and_is_not_a_random_identity(self):
        """Three jobs attribute the rows they write to this. A random id per run would make
        every sweep anonymous; a borrowed operator's id would be a lie about who decided."""
        self.assertEqual(registry.WORKER_ACTOR, registry.WORKER_ACTOR)
        self.assertEqual(uuid.UUID(registry.WORKER_ACTOR).version, 5)


class ScheduleTests(unittest.TestCase):
    """The in-memory due-times. No database, because there is no table -- that is the point."""

    def setUp(self) -> None:
        self.job = registry.JOBS[0]
        self.now = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

    def test_a_fresh_schedule_makes_everything_due(self):
        """Which is what a restart looks like, and why every job has to be idempotent."""
        self.assertTrue(runner.Schedule().due("t", self.job, self.now))

    def test_a_job_just_run_is_not_due_until_its_interval_has_passed(self):
        schedule = runner.Schedule()
        schedule.mark("t", self.job, self.now)
        self.assertFalse(schedule.due("t", self.job, self.now + self.job.every / 2))
        self.assertTrue(schedule.due("t", self.job, self.now + self.job.every))

    def test_a_tenant_that_is_no_longer_schedulable_stops_occupying_a_slot(self):
        """The one thing in the runner that would otherwise grow with the age of the
        deployment rather than with its size."""
        schedule = runner.Schedule()
        schedule.mark("gone", self.job, self.now)
        schedule.mark("here", self.job, self.now)
        schedule.prune(["here"])
        self.assertEqual(list(schedule.last_run), [("here", self.job.name)])


class WorkerTestCase(AccessApiTestCase):
    """A real tick over a real tenant. `AccessApiTestCase.floor` is reused for its fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._worker_pool = make_worker_pool(DSN)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._worker_pool.close()
        super().tearDownClass()

    def pools(self) -> runner.Pools:
        return runner.Pools(platform=self._platform_pool, app=self._tenant_pool,
                            worker=self._worker_pool)

    def pending_events(self, tenant_id: str) -> int:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            return int(conn.execute(
                "SELECT count(*) FROM plt01.evt_outbox WHERE status = 'pending'").fetchone()[0])

    def job(self, name: str) -> registry.Job:
        return next(j for j in registry.JOBS if j.name == name)

    def tick(self, tenant_id: str, *jobs: str, **kwargs: object) -> runner.TickReport:
        chosen = [self.job(n) for n in jobs] if jobs else list(registry.JOBS)
        return runner.run_tick(self.pools(), jobs=chosen, tenant_ids=[tenant_id],
                               **kwargs)  # type: ignore[arg-type]


class TenantSelectionTests(WorkerTestCase):
    def test_a_provisioned_tenant_is_scheduled_because_it_already_holds_rows(self):
        """The reading that excludes it is the obvious one and it is wrong in this build:
        nothing on the tenant plane checks the registry before a write, so a tenant
        accumulates outbox rows from its own bootstrap onwards."""
        tenant_id = self.tenant()
        self.assertIn(tenant_id, runner.schedulable_tenants(self._platform_pool))

    def test_a_suspended_tenant_gets_no_work_done_on_its_behalf(self):
        """Suspension is a customer being told they do not have the product. Publishing
        `device.offline` into one would be spending it on them anyway."""
        tenant_id = self.tenant()
        version = self.client.get(f"/platform/tenants/{tenant_id}").json()["version"]
        for action, expected in (("activate", version), ("suspend", version + 1)):
            response = self.client.post(
                f"/platform/tenants/{tenant_id}/{action}",
                json={"actor_id": ACTOR, "correlation_id": str(uuid.uuid4()),
                      "expected_version": expected})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(tenant_id, runner.schedulable_tenants(self._platform_pool))


class RelayJobTests(WorkerTestCase):
    def test_the_relay_dispatches_what_is_pending_and_counts_it(self):
        tenant_id = self.tenant()
        self.person(tenant_id)
        waiting = self.pending_events(tenant_id)
        self.assertGreater(waiting, 0, "the fixture should have published something")

        report = self.tick(tenant_id, "events.relay")

        self.assertEqual(report.failures, ())
        self.assertEqual(report.units, waiting)
        self.assertEqual(self.pending_events(tenant_id), 0)

    def test_a_second_tick_does_the_work_once(self):
        """The property that makes the in-memory schedule safe: a restart re-runs everything,
        so everything has to be free the second time."""
        tenant_id = self.tenant()
        self.person(tenant_id)
        first = self.tick(tenant_id, "events.relay")
        second = self.tick(tenant_id, "events.relay")
        self.assertGreater(first.units, 0)
        self.assertEqual(second.units, 0)

    def test_the_relay_creates_one_delivery_per_subscriber(self):
        tenant_id = self.tenant()
        events.subscribe(self._tenant_pool, tenant_id, consumer="a_consumer",
                         event_type="person.created", actor_id=ACTOR,
                         correlation_id=str(uuid.uuid4()))
        self.person(tenant_id)
        self.tick(tenant_id, "events.relay")
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            deliveries = int(conn.execute(
                "SELECT count(*) FROM plt01.evt_deliveries WHERE consumer = 'a_consumer'"
            ).fetchone()[0])
        self.assertEqual(deliveries, 1)

    def test_two_runners_over_one_tenant_do_not_dispatch_an_event_twice(self):
        """The docstring in `runner.py` says no lock is needed because the jobs coordinate
        themselves. `dispatch_pending` claims with `FOR UPDATE SKIP LOCKED`, so two relays
        take disjoint slices -- and if that were untrue the two would report more dispatches
        between them than there were events."""
        tenant_id = self.tenant()
        for _ in range(4):
            self.person(tenant_id)
        waiting = self.pending_events(tenant_id)

        reports: list[runner.TickReport] = []
        lock = threading.Lock()

        def go() -> None:
            report = self.tick(tenant_id, "events.relay")
            with lock:
                reports.append(report)

        threads = [threading.Thread(target=go) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sum(r.units for r in reports), waiting)
        self.assertEqual(self.pending_events(tenant_id), 0)


class TimelineJobTests(WorkerTestCase):
    def test_the_timeline_job_projects_what_the_relay_leaves_behind(self):
        """MOD-014's absence changed the product: a timeline nobody projects stays empty, so
        the Member 360 shows a member with no history."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        report = self.tick(tenant_id, "people.project_timeline")
        self.assertEqual(report.failures, ())
        self.assertGreater(report.units, 0)
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            entries = int(conn.execute(
                "SELECT count(*) FROM plt01.ppl_timeline_entries WHERE person_id = %s",
                (person_id,)).fetchone()[0])
        self.assertGreater(entries, 0)


class FailureIsolationTests(WorkerTestCase):
    def test_one_jobs_failure_does_not_stop_the_rest_and_is_reported(self):
        """MOD-010 shipped a relay whose failure handler raised, so the poison row aborted
        every healthy delivery behind it -- permanently, because it sorted first. The same
        shape is available here where the unit is a whole tenant."""
        tenant_id = self.tenant()
        self.person(tenant_id)

        def explode(_ctx: registry.JobContext) -> dict[str, object]:
            raise RuntimeError("this tenant's data is bad")

        poison = registry.Job(name="events.relay", every=timedelta(seconds=1), role="app",
                              units="x", summary="a job that raises", run=explode)
        with self.assertLogs("veyro.worker", level="ERROR") as logged:
            report = runner.run_tick(
                self.pools(), jobs=[poison, self.job("people.project_timeline")],
                tenant_ids=[tenant_id])
        self.assertEqual(len(logged.records), 1, "the failure is logged, once")

        self.assertEqual(len(report.outcomes), 2)
        failed, survived = report.outcomes
        self.assertFalse(failed.ok)
        self.assertIn("this tenant's data is bad", failed.error or "")
        self.assertTrue(survived.ok)
        self.assertGreater(survived.units, 0)
        self.assertEqual(report.summary()["failed"], 1)

    def test_one_tenants_failure_does_not_stop_the_next_tenant(self):
        first, second = self.tenant(), self.tenant()
        self.person(first)
        self.person(second)
        seen: list[str] = []

        def only_the_first_fails(ctx: registry.JobContext) -> dict[str, object]:
            seen.append(ctx.tenant_id)
            if ctx.tenant_id == first:
                raise RuntimeError("bad data")
            return {"projected": 1}

        job = registry.Job(name="people.project_timeline", every=timedelta(seconds=1),
                           role="app", units="projected", summary="x",
                           run=only_the_first_fails)
        with self.assertLogs("veyro.worker", level="ERROR"):
            report = runner.run_tick(self.pools(), jobs=[job], tenant_ids=[first, second])

        self.assertEqual(seen, [first, second])
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(report.units, 1)


class LoopTests(WorkerTestCase):
    """`run_forever`, which is the only part of the runner a process actually calls."""

    def test_the_loop_sleeps_in_slices_so_a_shutdown_is_not_a_hang(self):
        """PEP 475 resumes an interrupted sleep with the time remaining, so one long sleep
        would answer a SIGTERM at the end of the interval rather than at the signal -- which
        reads as a process that will not die."""
        slept: list[float] = []
        runner.run_forever(self.pools(), interval=timedelta(seconds=3), jobs=[],
                           sleep=slept.append, stop=lambda: len(slept) >= 3)
        self.assertEqual(slept, [1.0, 1.0, 1.0])

    def test_a_tick_that_cannot_even_list_the_tenants_is_logged_and_retried(self):
        """**A bad tick is not a reason to stop ticking.** A tenant list that cannot be read
        is a reason to wait and try again; exiting would take every other tenant's schedule
        with it, and a process manager restarting into the same outage gains nothing.

        The pool is closed rather than stubbed, so what fails is the real failure: a pool that
        cannot hand out a connection, which is what a database outage looks like from here.
        """
        broken = make_worker_pool(DSN)
        broken.close()
        pools = runner.Pools(platform=broken, app=self._tenant_pool, worker=self._worker_pool)
        # One sleep per tick at this interval, so the nap count is the tick count.
        naps: list[float] = []

        with self.assertLogs("veyro.worker", level="ERROR") as logged:
            runner.run_forever(pools, interval=timedelta(seconds=1), jobs=[],
                               sleep=naps.append, stop=lambda: len(naps) >= 2)
        self.assertEqual(len(naps), 2)
        self.assertEqual(len(logged.records), 2, "one per attempted tick, and it kept going")


class AttributionTests(WorkerTestCase):
    """The worker writes evidence, so the evidence has to say it was the worker."""

    def test_a_command_the_worker_expired_names_the_worker(self):
        """**Evidence with nobody's name on it answers nothing**, and three of the six jobs
        write a row that is evidence. A random actor per run would make every sweep anonymous
        and a borrowed operator's id would be a lie about who decided, so the actor is a fixed
        version-5 UUID that MOD-007 could never issue -- and this is the test that it reaches
        the column rather than being asserted in a docstring."""
        floor = self.floor()
        tenant_id = str(floor["tenant_id"])
        issued = self.client.post(
            f"/fleet/{floor['device_id']}/commands",
            json={"action": "unlock_momentary", "idempotency_key": str(uuid.uuid4()),
                  **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(issued.status_code, 201, issued.text)
        command_id = issued.json()["command_id"]

        # An unlock lives for a minute, so the sweep has to be looking from after that.
        report = self.tick(tenant_id, "devices.expire_commands",
                           now=datetime.now(UTC) + timedelta(minutes=2))
        self.assertEqual(report.failures, ())
        self.assertGreaterEqual(report.units, 1)

        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            state, settled_by, correlation = conn.execute(
                "SELECT state, settled_by, settle_correlation_id FROM plt01.dev_commands"
                " WHERE command_id = %s", (command_id,)).fetchone()
        self.assertEqual(state, "expired")
        self.assertEqual(str(settled_by), registry.WORKER_ACTOR)
        # And a correlation id per run, so one sweep's rows can be found together.
        self.assertIsNotNone(correlation)


class MetricTests(WorkerTestCase):
    def one_bucket(self, tenant_id: str, metric_key: str,
                   job: str = "events.relay") -> dict[str, object]:
        """The only bucket in the window, since a tick happens in one hour."""
        series = metrics.series(self._tenant_pool, tenant_id, metric_key=metric_key,
                                window_hours=1, dimensions={"job": job})
        self.assertEqual(len(series["buckets"]), 1, series)
        return dict(series["buckets"][0])

    def test_a_tick_records_how_long_each_job_took_and_whether_it_worked(self):
        tenant_id = self.tenant()
        self.person(tenant_id)
        self.tick(tenant_id, "events.relay")

        success = self.one_bucket(tenant_id, "worker.job_success")
        duration = self.one_bucket(tenant_id, "worker.job_duration")
        self.assertEqual(success["observations"], 1)
        self.assertEqual(success["total"], 1.0)
        self.assertEqual(duration["observations"], 1)
        self.assertGreater(duration["total"], 0.0)

    def test_a_failed_run_is_recorded_as_a_failure_rather_than_as_nothing(self):
        """A job that raised and recorded no point is indistinguishable from a job that never
        ran, which is the one reading an operator must not be given."""
        tenant_id = self.tenant()

        def explode(_ctx: registry.JobContext) -> dict[str, object]:
            raise RuntimeError("no")

        job = registry.Job(name="events.relay", every=timedelta(seconds=1), role="app",
                           units="x", summary="x", run=explode)
        with self.assertLogs("veyro.worker", level="ERROR"):
            runner.run_tick(self.pools(), jobs=[job], tenant_ids=[tenant_id])

        success = self.one_bucket(tenant_id, "worker.job_success")
        self.assertEqual(success["observations"], 1)
        self.assertEqual(success["total"], 0.0)


class UnitsTests(unittest.TestCase):
    """Reading the count a job reports, which must never cost the work it did."""

    def test_a_count_that_is_not_a_number_is_zero_rather_than_an_exception(self):
        """The naive version read the count outside the `except` that guards the call, so a
        job whose count came back as a list would have raised *after* committing -- aborting
        the tick and reporting a job that worked as a job that never ran."""
        job = registry.JOBS[0]
        with self.assertLogs("veyro.worker", level="WARNING"):
            self.assertEqual(runner._units(job, {job.units: ["not", "a", "count"]}), 0)
        self.assertEqual(runner._units(job, {}), 0)
        self.assertEqual(runner._units(job, {job.units: 7}), 7)


class WorkerRouteTests(WorkerTestCase):
    """`GET /ops/worker`, driven over HTTP.

    MOD-014's review found four defects that passed a green suite because no test had ever
    called a `/people` route successfully. This is the route the operations board reads, and
    the thing it has to get right is the zero: a job with no runs is a worker that is not
    running, so a route that omitted the row or reported it as absent would make the board's
    one real verdict unreachable.
    """

    def test_a_tenant_whose_worker_never_ran_reports_every_job_with_no_runs(self):
        tenant_id = self.tenant()
        response = self.client.get("/ops/worker", headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["jobs"]), len(registry.JOBS))
        for job in body["jobs"]:
            with self.subTest(job["job"]):
                self.assertEqual(job["runs"], 0)
                self.assertEqual(job["failed"], 0)
                self.assertIsNone(job["mean_duration_ms"])
                # **And no expected-run count.** The arithmetic is trivial and every reading
                # of it is wrong unless the worker was up for the whole window, which is the
                # thing being tested: a worker started ten minutes ago would report 40 runs
                # against an expected 5,760 and read as broken.
                self.assertNotIn("expected_at_least", job)

    def test_a_tick_shows_up_on_the_route_the_board_reads(self):
        tenant_id = self.tenant()
        self.person(tenant_id)
        self.tick(tenant_id)
        body = self.client.get("/ops/worker", headers=self.headers(tenant_id)).json()
        by_name = {job["job"]: job for job in body["jobs"]}
        self.assertEqual(by_name["events.relay"]["runs"], 1)
        self.assertEqual(by_name["events.relay"]["failed"], 0)
        self.assertIsNotNone(by_name["events.relay"]["mean_duration_ms"])
        self.assertEqual(by_name["access.replay_sweep"]["role"], "worker")

    def test_the_route_says_what_a_run_does_not_prove(self):
        """A run is recorded by the worker itself. A board that rendered the count with no
        such line would let a reader take it as proof the job's effect reached something
        outside the database, which no row here can establish."""
        tenant_id = self.tenant()
        body = self.client.get("/ops/worker", headers=self.headers(tenant_id)).json()
        self.assertTrue(any("recorded by the worker itself" in gap
                            for gap in body["worker_gaps"]))

    def test_the_route_needs_the_metric_read_permission(self):
        tenant_id = self.tenant()
        refused = self.client.get("/ops/worker", headers=self.headers(tenant_id, token=""))
        self.assertIn(refused.status_code, (403, 422), refused.text)


class ReplaySweepTests(WorkerTestCase):
    """MOD-022's replay cache: the one job that needs the other role."""

    def seed_token(self, floor: dict[str, object], *, seen: datetime,
                   lifetime: timedelta) -> str:
        key = uuid.uuid4().hex + uuid.uuid4().hex
        with tenant_scope(self._tenant_pool, str(floor["tenant_id"])) as conn:
            conn.execute(
                "INSERT INTO plt01.acc_replay_tokens (tenant_id, token_key, credential_id,"
                " point_id, seen_at, expires_at, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (floor["tenant_id"], key, floor["credential_id"], floor["point_id"],
                 seen, seen + lifetime, str(uuid.uuid4())))
        return key

    def tokens(self, tenant_id: str) -> set[str]:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            return {str(r[0]) for r in conn.execute(
                "SELECT token_key FROM plt01.acc_replay_tokens").fetchall()}

    def test_the_sweep_takes_the_expired_rows_and_leaves_the_live_ones(self):
        """Deleting an unexpired row would re-open the replay window the table exists to
        close, so the predicate is the expiry and nothing else."""
        floor = self.floor()
        tenant_id = str(floor["tenant_id"])
        now = datetime.now(UTC)
        stale = self.seed_token(floor, seen=now - timedelta(minutes=2),
                                lifetime=timedelta(seconds=30))
        live = self.seed_token(floor, seen=now, lifetime=timedelta(seconds=60))

        report = self.tick(tenant_id, "access.replay_sweep")

        self.assertEqual(report.failures, ())
        self.assertEqual(report.units, 1)
        self.assertEqual(self.tokens(tenant_id), {live})
        self.assertNotIn(stale, self.tokens(tenant_id))

    def test_a_job_on_the_worker_pool_still_records_its_run(self):
        """`_record` swallows its own failure, deliberately -- so a role that could not write
        a metric point would be invisible, and the only job that runs as `veyro_cp_worker`
        would be the one job with no evidence that it ran."""
        floor = self.floor()
        tenant_id = str(floor["tenant_id"])
        self.tick(tenant_id, "access.replay_sweep")
        series = metrics.series(self._worker_pool, tenant_id,
                                metric_key="worker.job_success", window_hours=1,
                                dimensions={"job": "access.replay_sweep"})
        self.assertEqual(len(series["buckets"]), 1, series)
        self.assertEqual(series["buckets"][0]["total"], 1.0)

    def test_the_sweep_is_refused_to_the_role_the_product_runs_as(self):
        """The negative test that makes the per-job role real rather than decorative.
        `veyro_cp_app` holds DELETE nowhere in this build, and `veyro_cp_worker` holds it on
        the configuration registry as well as here -- so a worker process running everything
        as one role would be able to delete a tenant's feature flags in order to sweep a
        replay cache. If this ever passes, the split has stopped meaning anything."""
        from app.access import service as access

        floor = self.floor()
        tenant_id = str(floor["tenant_id"])
        self.seed_token(floor, seen=datetime.now(UTC) - timedelta(minutes=2),
                        lifetime=timedelta(seconds=30))
        with self.assertRaises(Exception) as caught:
            access.sweep_replay_tokens(self._tenant_pool, tenant_id)
        self.assertIn("permission denied", str(caught.exception).lower())


if __name__ == "__main__":
    unittest.main()
