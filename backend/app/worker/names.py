"""The names of the scheduled jobs, and nothing else.

This module imports nothing, deliberately. The job *names* are needed in two places that
cannot import each other: `app.worker.registry`, which holds the functions, imports every
module whose work it drives -- and `app.observability.catalog`, which declares the two metrics
a job run records, is imported by most of those. Declaring the names in the registry and
importing them into the catalogue would close that loop.

So the names live in a leaf, and `registry` asserts at import that the two agree in **both**
directions: every registered job's name is declared here, and every name declared here has a
job behind it. A name with no job would be a metric dimension value nothing can ever emit --
a series that reads as a measurement and is always absent -- and a job with no name could not
record a thing.
"""

from __future__ import annotations

#: Every scheduled job this build runs, as a closed set.
#:
#: Closed because a job is a fact about what the software does, which is the same argument
#: MOD-008 makes for permissions, MOD-010 for event types and MOD-011 for metrics. It is what
#: lets `worker.job_success` declare its `job` dimension with values rather than a reason:
#: MOD-011's rule is that cardinality is declared, not discovered, and here it genuinely can be.
JOB_NAMES: tuple[str, ...] = (
    "access.replay_sweep",
    "booking.expire_offers",
    "devices.expire_commands",
    "devices.sweep_offline",
    "events.relay",
    "observability.evaluate_objectives",
    "notifications.close_digests",
    "people.project_timeline",
)
