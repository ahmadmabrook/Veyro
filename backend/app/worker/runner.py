"""The tick: which tenants, which jobs, and what happens when one of them raises.

**The runner owns three properties and nothing else.** It decides which tenants exist, which
jobs are due, and that one failure does not take the rest of the batch with it. Every decision
about *what* a job does lives in the service function the job calls, which is why this file is
short and has no SQL in it beyond the tenant list.

**A failure path inside a batch loop must not raise.** MOD-010 shipped a relay whose failure
handler raised `NotFound` for a delivery with no subscription: that propagated out of the loop,
so the failure counted no attempt, wrote no error, and aborted every healthy delivery behind it
-- permanently, because the poison row sorted first. The same shape is available here one level
up, where the unit is a whole tenant: a single tenant whose data trips a bug would otherwise
stop every tenant after it in the list, and the failure would be invisible because the process
would look like it was running. So every job runs inside its own `try`, the error is recorded
against that (tenant, job), and the loop continues.

**The schedule is in memory, and that is a decision rather than an omission.** A durable
schedule needs a table, and a table in `plt01` needs a migration, RLS, policies, grants,
isolation checks and a mutation sweep -- the full discipline, correctly. What it would buy is
the ability to *not* re-run a job after a restart, and every job in the registry is idempotent,
so re-running one is free. What it would cost beyond the work is a second place where "has this
run" is recorded, which can disagree with the effect the job had. The day a job appears that is
not idempotent, it needs durable state before it needs a schedule, and that is when to build
both.

**Two workers may run at once.** Nothing here coordinates them, because the jobs already do:
`dispatch_pending` claims with `FOR UPDATE SKIP LOCKED`, `project_timeline` is idempotent by a
unique index, `sweep_offline` filters on idempotency keys before it publishes, and the three
sweeps are UPDATE or DELETE statements whose predicate no longer matches the rows the other
worker took. An advisory lock around each job would make that invisible rather than true, and
the test that proves it is `test_two_runners_over_one_tenant_do_not_double_count`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

from app.db import Pool, platform_scope
from app.observability import metrics
from app.worker.registry import JOBS, WORKER_ACTOR, Job, JobContext

log = logging.getLogger("veyro.worker")


@dataclass(frozen=True)
class Pools:
    """The three pools a tick needs, each pinned to its own role."""

    platform: Pool
    app: Pool
    worker: Pool

    def for_role(self, role: str) -> Pool:
        if role == "app":
            return self.app
        if role == "worker":
            return self.worker
        raise ValueError(f"no pool for role {role!r}")


@dataclass(frozen=True)
class JobOutcome:
    tenant_id: str
    job: str
    ok: bool
    units: int
    duration_ms: float
    error: str | None = None
    detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class TickReport:
    started_at: datetime
    tenants: tuple[str, ...]
    outcomes: tuple[JobOutcome, ...]

    @property
    def failures(self) -> tuple[JobOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.ok)

    @property
    def units(self) -> int:
        return sum(o.units for o in self.outcomes)

    def summary(self) -> dict[str, Any]:
        """What `--once` prints, and what a test reads."""
        by_job: dict[str, dict[str, int]] = {}
        for outcome in self.outcomes:
            entry = by_job.setdefault(outcome.job, {"runs": 0, "failed": 0, "units": 0})
            entry["runs"] += 1
            entry["units"] += outcome.units
            if not outcome.ok:
                entry["failed"] += 1
        return {
            "started_at": self.started_at.isoformat(),
            "tenants": len(self.tenants),
            "runs": len(self.outcomes),
            "failed": len(self.failures),
            "units": self.units,
            "jobs": by_job,
            "errors": [{"tenant_id": o.tenant_id, "job": o.job, "error": o.error}
                       for o in self.failures],
        }


@dataclass
class Schedule:
    """When each (tenant, job) last ran, for as long as this process lives.

    Pruned every tick against the live tenant list, so a tenant that is archived or suspended
    stops occupying a slot here. Without that the map is the one thing in the runner that grows
    with the age of the deployment rather than with its size.
    """

    last_run: dict[tuple[str, str], datetime] = field(default_factory=dict)

    def due(self, tenant_id: str, job: Job, now: datetime) -> bool:
        last = self.last_run.get((tenant_id, job.name))
        return last is None or now - last >= job.every

    def mark(self, tenant_id: str, job: Job, now: datetime) -> None:
        self.last_run[(tenant_id, job.name)] = now

    def prune(self, tenants: Iterable[str]) -> None:
        live = set(tenants)
        for key in [k for k in self.last_run if k[0] not in live]:
            del self.last_run[key]


#: The two lifecycle states a scheduled job runs for.
#:
#: **Suspended is withheld on purpose and archived is finished**, so neither gets work done on
#: its behalf: publishing `device.offline` into a suspended tenant is spending the product on a
#: customer who is being told they do not have it.
#:
#: **Provisioned is included, which is the one worth arguing.** The obvious reading is that a
#: provisioned tenant has had nothing happen in it yet -- and in this build that is false.
#: Nothing on the tenant plane checks the registry before a write, so a tenant accumulates
#: outbox rows from its own bootstrap onwards, and every test fixture in this repository works
#: that way. Excluding it would mean a tenant's events sat undispatched until somebody ran the
#: activation, with the backlog reading exactly like a relay that had stopped.
SCHEDULABLE = ("provisioned", "active")


def schedulable_tenants(platform: Pool) -> tuple[str, ...]:
    """The tenants a job may run for.

    The registry is on the platform plane under `veyro_cp_platform`, which holds nothing in
    `plt01` -- so this read and the work it leads to are two connections as two roles, which is
    the same span the HTTP surface already makes and the reason `Pools` carries three.
    """
    with platform_scope(platform) as conn:
        rows = conn.execute(
            "SELECT tenant_id FROM plt01_platform.tenants WHERE status = ANY(%s)"
            " ORDER BY created_at, tenant_id", (list(SCHEDULABLE),)).fetchall()
    return tuple(str(row[0]) for row in rows)


def _record(pools: Pools, job: Job, outcome: JobOutcome) -> None:
    """Record the run in MOD-011's metric store, and never fail the job for it.

    The swallow is deliberate and is the same trade `permit` makes for `authz.denials`: the job
    has already done its work and committed it, so turning a metric failure into a job failure
    would report work that happened as work that did not -- which is the one direction that
    makes the report worse than having none. It is logged, so a metric store that has stopped
    accepting points is visible in the process log rather than silent.
    """
    try:
        pool = pools.for_role(job.role)
        metrics.observe(pool, outcome.tenant_id, metric_key="worker.job_duration",
                        total=outcome.duration_ms, observations=1,
                        dimensions={"job": job.name})
        metrics.observe(pool, outcome.tenant_id, metric_key="worker.job_success",
                        total=1.0 if outcome.ok else 0.0, observations=1,
                        dimensions={"job": job.name})
    except Exception as e:  # noqa: BLE001 -- observability must not decide whether work counted
        log.warning("worker: could not record %s for %s: %s", job.name, outcome.tenant_id, e)


def _units(job: Job, result: dict[str, Any]) -> int:
    """How much work the job reports, and never a reason to lose the work it did.

    The naive version was `int(result[job.units])` on the success path, which is outside the
    `except` that guards the call -- so a job whose count came back as a list would have raised
    *after* committing, aborted the whole tick, and reported a job that worked as a job that
    never ran. That is this file's own rule ("a failure path inside a batch loop must not
    raise") turned on the file itself, and it is why reading a number is wrapped rather than
    trusted.
    """
    value = result.get(job.units, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        log.warning("worker: %s reported %r as %s, which is not a count", job.name, value,
                    job.units)
        return 0


def run_job(pools: Pools, job: Job, tenant_id: str, *, at: datetime) -> JobOutcome:
    """One job for one tenant, with its own correlation id and its own failure.

    The correlation id is per run rather than per tick, so every row a single sweep wrote can
    be found together and two sweeps of the same job are distinguishable. That is what the
    column is for in every module that carries one.
    """
    ctx = JobContext(tenant_id=tenant_id, pool=pools.for_role(job.role),
                     actor_id=WORKER_ACTOR, correlation_id=str(uuid4()), at=at)
    started = monotonic()
    try:
        result = job.run(ctx)
    except Exception as e:  # noqa: BLE001 -- one tenant's failure is not the batch's
        duration = (monotonic() - started) * 1000
        log.exception("worker: %s failed for %s", job.name, tenant_id)
        outcome = JobOutcome(tenant_id=tenant_id, job=job.name, ok=False, units=0,
                             duration_ms=duration, error=f"{type(e).__name__}: {e}"[:500])
    else:
        duration = (monotonic() - started) * 1000
        units = _units(job, result)
        if units:
            log.info("worker: %s did %s for %s", job.name, units, tenant_id)
        outcome = JobOutcome(tenant_id=tenant_id, job=job.name, ok=True, units=units,
                             duration_ms=duration, detail=result)
    _record(pools, job, outcome)
    return outcome


def run_tick(
    pools: Pools, *, schedule: Schedule | None = None, jobs: Sequence[Job] = JOBS,
    now: datetime | None = None, tenant_ids: Sequence[str] | None = None,
) -> TickReport:
    """Run every due job for every schedulable tenant, once.

    With no `schedule` every job is due, which is what `--once` means and what a test wants: a
    run whose output depends on the wall clock is a run nobody can assert against.
    """
    moment = now or datetime.now(UTC)
    tenants = tuple(tenant_ids) if tenant_ids is not None else schedulable_tenants(pools.platform)
    if schedule is not None:
        schedule.prune(tenants)
    outcomes: list[JobOutcome] = []
    for tenant_id in tenants:
        for job in jobs:
            if schedule is not None and not schedule.due(tenant_id, job, moment):
                continue
            outcomes.append(run_job(pools, job, tenant_id, at=moment))
            if schedule is not None:
                schedule.mark(tenant_id, job, moment)
    return TickReport(started_at=moment, tenants=tenants, outcomes=tuple(outcomes))


def run_forever(
    pools: Pools, *, interval: timedelta,
    sleep: Callable[[float], None] | None = None,
    stop: Callable[[], bool] | None = None,
    jobs: Sequence[Job] = JOBS,
) -> None:
    """Tick until something says stop.

    `sleep` and `stop` are injectable so the loop itself can be tested without wall-clock time;
    in the process they are `time.sleep` and a flag set by SIGINT and SIGTERM. The tick's own
    exceptions are caught here too: a tenant list that cannot be read is a reason to wait and
    try again, not a reason for the process to exit and take every other tenant's schedule with
    it.
    """
    tick = sleep or time.sleep
    should_stop = stop or (lambda: False)
    schedule = Schedule()
    while not should_stop():
        try:
            report = run_tick(pools, schedule=schedule, jobs=jobs)
        except Exception as e:  # noqa: BLE001 -- a bad tick is not a reason to stop ticking
            log.exception("worker: the tick itself failed: %s", e)
        else:
            if report.failures:
                log.warning("worker: %s of %s runs failed", len(report.failures),
                            len(report.outcomes))
        # Slept in slices so a SIGTERM is answered in about a second rather than at the end of
        # the interval. PEP 475 resumes an interrupted sleep with the time remaining, so one
        # long sleep would make an ordinary shutdown look like a hang.
        remaining = interval.total_seconds()
        while remaining > 0 and not should_stop():
            tick(min(1.0, remaining))
            remaining -= 1.0
