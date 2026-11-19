"""What the scheduled jobs are, what each one calls, and how often it is worth calling.

**Fourteen module entries in `CLAUDE.md` end with some version of "nothing drives this on a
schedule".** Each of those is a decision function that is written, tested and reachable from a
route, waiting for something to call it without a person asking. This registry is that
something, and the shape of it matters more than the list:

  * **A job is an adapter, not a new implementation.** Every entry below calls a service
    function that already exists, with arguments it already takes. A worker that re-implemented
    a sweep would be a second copy of the rule, and the day the two disagreed nobody could say
    which was the policy -- the argument MOD-012 makes for importing MOD-010's backoff rather
    than copying it.
  * **A job declares the role it needs.** `veyro_cp_worker` differs from `veyro_cp_app` in one
    direction only: it holds DELETE on the configuration registry and on the access replay
    cache, and `veyro_cp_app` holds DELETE nowhere. So a worker process holding the union of
    both would be able to delete a tenant's feature flags in order to sweep a replay cache, and
    the only thing that can refuse that is the connection the job runs on.
  * **Every job is idempotent, and that is what makes the schedule disposable.** The runner
    keeps due-times in memory, so a restart makes everything due at once. That is safe here
    because a second pass is free by construction -- a unique index, an idempotency key, or a
    predicate that no longer matches -- and it is why this change adds no table. A durable
    schedule is a thing to build when a job appears that cannot say the same.
  * **A job returns a count of what it did.** `units` names the field, the runner reads it, and
    the number is the only honest answer to "is the worker working": a job that runs every
    minute and moves nothing is indistinguishable from one that is not running at all, unless
    somebody is counting.

**What is deliberately not here.** MOD-007's challenge sweep, which wants a DELETE grant on
`iam.challenges` that no role holds by design -- a job that ran and deleted nothing would be
activity with no effect, which is worse than the gap it claims to close. MOD-010's
`deliver_pending`, because this process registers no handlers and the function refuses a
consumer that has none; a relay that drove an empty registry would read as a control and do
nothing. MOD-009's retention sweep, MOD-011's objective evaluation, MOD-013's digest close and
MOD-018's revenue recognition, each of which needs a decision this registry would have to
invent -- which deadline, which objective, which period -- and inventing product is the one
thing the delegation does not cover.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.access import service as access
from app.booking import service as booking
from app.db import Pool
from app.devices import service as devices
from app.events import service as events
from app.people import service as people
from app.worker.names import JOB_NAMES

#: The actor every attributed job writes into the rows it moves.
#:
#: Three of the six jobs take an `actor_id` because the row they write is evidence and this
#: codebase's standing rule is that evidence with nobody's name on it answers nothing. The
#: worker is not a person, so the honest name is a fixed identifier that is obviously not one:
#: derived from a URL in the reserved `.invalid` domain, stable across restarts and across
#: deployments, and never issued to an identity by MOD-007 -- whose identifiers are random
#: version-4 UUIDs. A row attributed here says "the scheduled worker did this", which is a
#: true and useful sentence; a random id per run would say nothing, and a borrowed operator's
#: id would be a lie about who decided.
WORKER_ACTOR = str(uuid5(NAMESPACE_URL, "https://veyro.invalid/actors/scheduled-worker"))

#: Which pool a job wants. `app` is `veyro_cp_app`, the role the HTTP surface uses; `worker` is
#: `veyro_cp_worker`, which holds the DELETE grants.
Role = str


@dataclass(frozen=True)
class JobContext:
    """Everything a job is given. One of these per (tenant, job, tick)."""

    tenant_id: str
    pool: Pool
    actor_id: str
    correlation_id: str
    at: datetime


@dataclass(frozen=True)
class Job:
    name: str
    every: timedelta
    role: Role
    units: str
    summary: str
    run: Callable[[JobContext], dict[str, Any]]


# --------------------------------------------------------------------------- the adapters
#
# Module-level functions rather than lambdas, so a traceback from inside one names the job.


def _events_relay(ctx: JobContext) -> dict[str, Any]:
    return events.dispatch_pending(ctx.pool, ctx.tenant_id, limit=500)


def _people_project_timeline(ctx: JobContext) -> dict[str, Any]:
    return people.project_timeline(ctx.pool, ctx.tenant_id, limit=500)


def _devices_sweep_offline(ctx: JobContext) -> dict[str, Any]:
    return devices.sweep_offline(ctx.pool, ctx.tenant_id, actor_id=ctx.actor_id,
                                 correlation_id=ctx.correlation_id, at=ctx.at)


def _devices_expire_commands(ctx: JobContext) -> dict[str, Any]:
    return devices.expire_commands(ctx.pool, ctx.tenant_id, actor_id=ctx.actor_id,
                                   correlation_id=ctx.correlation_id, at=ctx.at, limit=500)


def _booking_expire_offers(ctx: JobContext) -> dict[str, Any]:
    return booking.expire_offers(ctx.pool, ctx.tenant_id, actor_id=ctx.actor_id,
                                 correlation_id=ctx.correlation_id, at=ctx.at, limit=200)


def _access_replay_sweep(ctx: JobContext) -> dict[str, Any]:
    return access.sweep_replay_tokens(ctx.pool, ctx.tenant_id, at=ctx.at, limit=5000)


JOBS: tuple[Job, ...] = (
    # MOD-010. The shortest cadence in the registry, because this is the one job whose delay a
    # member can feel: an event sits in the outbox until it is fanned out, and every consumer
    # that will ever exist reads its deliveries. Fifteen seconds is latency a product can live
    # with and a claim query -- `FOR UPDATE SKIP LOCKED` over a partial index -- can absorb.
    Job(name="events.relay", every=timedelta(seconds=15), role="app",
        units="events_dispatched",
        summary="Fan pending outbox events out to their subscribers",
        run=_events_relay),
    # MOD-014. The absence changed the product: a timeline nobody projects stays empty, and the
    # Member 360 shows a member with no history.
    Job(name="people.project_timeline", every=timedelta(seconds=60), role="app",
        units="projected",
        summary="Project outbox events into member timelines",
        run=_people_project_timeline),
    # MOD-021. `deliver_command` refuses a stale command whether or not this runs, so this is
    # tidying rather than the control -- but an unlock nobody expires reads as a door waiting
    # to open, and a queue full of those is how an operator stops trusting the queue.
    Job(name="devices.expire_commands", every=timedelta(seconds=60), role="app",
        units="expired",
        summary="Settle commands nothing collected before their deadline",
        run=_devices_expire_commands),
    # MOD-021. `fleet.OFFLINE_AFTER` is half an hour, so five minutes of sweep latency is six
    # per cent of the signal and nobody notices. A shorter cadence would buy nothing and cost a
    # scan of the device table per tenant per tick.
    Job(name="devices.sweep_offline", every=timedelta(minutes=5), role="app",
        units="offline",
        summary="Publish device.offline for devices in service that have gone quiet",
        run=_devices_sweep_offline),
    # MOD-020. A member is waiting for this one: an unanswered offer holds a place that the
    # next person in the queue cannot be offered until it is released.
    Job(name="booking.expire_offers", every=timedelta(seconds=60), role="app",
        units="released",
        summary="Release places held by waitlist offers nobody answered",
        run=_booking_expire_offers),
    # MOD-022, and the one job that needs the other role. A replay token expires in ninety
    # seconds and nothing depends on the row being *gone* -- the window is what refuses the
    # second presentation -- so this is bounding a table that would otherwise grow with every
    # rotating-credential presentation in the building.
    Job(name="access.replay_sweep", every=timedelta(minutes=5), role="worker",
        units="deleted",
        summary="Delete replay-cache rows whose window has closed",
        run=_access_replay_sweep),
)


def _check_registry() -> None:
    """Refuse a registry that disagrees with `app.worker.names`, in both directions.

    A job whose name is undeclared cannot record a metric point, because `worker.job_success`
    declares its `job` dimension as a closed set -- so the failure would be a job that runs and
    is invisible. A declared name with no job is the opposite: a dimension value nothing can
    emit, which reads on a dashboard as a measurement that is always missing. Both are checked
    where somebody is writing the change, which is MOD-010's argument for checking event
    compatibility at import rather than at a registration endpoint.
    """
    registered = [job.name for job in JOBS]
    if len(set(registered)) != len(registered):
        raise ValueError("a job name is registered twice")
    if set(registered) != set(JOB_NAMES):
        missing = sorted(set(JOB_NAMES) - set(registered))
        extra = sorted(set(registered) - set(JOB_NAMES))
        raise ValueError(
            f"the registry and app.worker.names disagree: declared with no job {missing}, "
            f"registered with no name {extra}")
    for job in JOBS:
        if job.role not in ("app", "worker"):
            raise ValueError(f"{job.name!r} names no pool this runner has")
        if job.every <= timedelta(0):
            raise ValueError(f"{job.name!r} would run every tick for ever")
        if not job.units.strip() or not job.summary.strip():
            raise ValueError(f"{job.name!r} says nothing about what it does")


_check_registry()
