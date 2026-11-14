"""MOD-011 REL-02: recording a measurement and reading a series back.

Separate from `service.py` for a mechanical reason worth stating, because it looks like an
arbitrary split: `app.events.service` is a producer of metrics, and `app.observability.service`
is a producer of events. Putting the recording primitives beside the objective and budget logic
would make those two modules import each other. This module imports the catalogue and nothing
else in the application, so either side can depend on it.

**A metric point deliberately does not have to be atomic with the business change it describes,
and that is the opposite call from MOD-010's.** `events.append_event` takes a connection rather
than a pool because a state change committing without its event means a consumer never learns
about something that happened. A metric point is not that: losing one leaves a gap in a chart,
and taking a business write down because the chart could not be updated is the worse failure by
a wide margin. So `observe` opens its own transaction, `observe_in` exists only to save a second
one when the caller already holds a connection, and neither is the "correct" one -- unlike
MOD-010, where the pool-taking wrapper is the bug.

**Accumulation is an upsert on one row per (tenant, metric, hour, dimensions), so concurrent
writers for one tenant contend on that row.** At this scale that is microseconds of row lock
per write and it is fine; at a rate where it is not, the fix is in-process aggregation with a
periodic flush, which needs the worker runtime MOD-007, MOD-009 and MOD-010 are each already
waiting on. Stated here because it is a ceiling somebody should find in this file rather than
in a latency graph.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.db import Pool, tenant_scope
from app.errors import InvalidRequest
from app.observability import catalog, objectives


def _now() -> datetime:
    return datetime.now(UTC)


#: How far ahead of now a caller may place an observation. A probe that finished moments ago
#: and a clock a little out of step are ordinary; an hour ahead is not.
_FUTURE_SKEW = timedelta(minutes=5)


def _bucket(at: datetime) -> datetime:
    """Which hourly bucket a moment belongs to.

    **A naive datetime is refused rather than assumed.** `astimezone` on a naive value reads it
    as the host's local time, so `2026-11-14T09:00:00` with no offset lands in a different
    bucket depending on which machine the process runs on -- and the probe result row, which
    stores the value as given, would then disagree with the series it feeds about which hour
    the run was in. That is the precise divergence `record_result` promises not to have.
    """
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise InvalidRequest("timestamp_needs_a_timezone")
    return at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _writable_bucket(at: datetime) -> datetime:
    """`_bucket`, and a moment in the future is refused.

    A write-side bound only. `observe_in` accumulates, so a caller able to choose the bucket can
    add successes into hours that have not happened yet and hold an availability objective green
    through an outage still to come; the permission to record is routine and AAL-1 by design,
    which is what makes the bound matter. **Reading up to a future moment is harmless** and is
    the ordinary way to ask for "the last 24 hours", so `series` does not inherit this.
    """
    bucket = _bucket(at)
    if at > _now() + _FUTURE_SKEW:
        raise InvalidRequest("timestamp_is_in_the_future")
    return bucket


# ------------------------------------------------------------------------- metric points

def observe_in(
    conn: Connection[Any], tenant_id: str, *, metric_key: str, total: float,
    observations: int = 1, dimensions: dict[str, str] | None = None,
    at: datetime | None = None,
) -> None:
    """Add one measurement to its hourly bucket, on the caller's connection.

    The upsert is the accumulation: the unique index on (tenant, metric, bucket, dimensions) is
    what makes `ON CONFLICT DO UPDATE` an increment rather than a race between two readers that
    both saw no row. The conflict target is named rather than left bare, because a bare
    `ON CONFLICT` stays valid SQL when the index is dropped and silently stops accumulating --
    which is how MOD-010's delivery deduplication was found to have no test behind it.
    """
    labels = dimensions or {}
    catalog.validate_dimensions(metric_key, labels)
    catalog.validate_point(metric_key, observations=observations, total=total)
    conn.execute(
        """
        INSERT INTO plt01.ops_metric_points
            (tenant_id, metric_key, bucket_start, dimensions, observations, total)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, metric_key, bucket_start, dimensions) DO UPDATE
        SET observations = plt01.ops_metric_points.observations + EXCLUDED.observations,
            total = plt01.ops_metric_points.total + EXCLUDED.total
        """,
        (tenant_id, metric_key, _writable_bucket(at or _now()), Jsonb(labels), observations,
         total),
    )


def observe(
    pool: Pool, tenant_id: str, *, metric_key: str, total: float, observations: int = 1,
    dimensions: dict[str, str] | None = None, at: datetime | None = None,
) -> None:
    """`observe_in` in a transaction of its own, for a producer that holds no connection."""
    with tenant_scope(pool, tenant_id) as conn:
        observe_in(conn, tenant_id, metric_key=metric_key, total=total,
                   observations=observations, dimensions=dimensions, at=at)


def series(
    pool: Pool, tenant_id: str, *, metric_key: str, window_hours: int,
    dimensions: dict[str, str] | None = None, until: datetime | None = None,
) -> dict[str, Any]:
    """One series over a window, optionally sliced by an exact dimension set.

    The slice is an equality on the whole `dimensions` object, not a containment test. A
    partial match would silently merge series that the catalogue declared distinct, and the
    merged number would read as a measurement of something nobody defined.
    """
    # A caller-supplied metric key reaches this from an HTTP path, so an unknown one is a
    # refusal rather than an exception: an empty series for a key nobody declared would read as
    # "this is quiet", which is the wrong answer in the one direction that matters.
    try:
        catalog.require_metric(metric_key)
        if dimensions is not None:
            catalog.validate_dimensions(metric_key, dimensions)
    except catalog.CatalogError as e:
        raise InvalidRequest(str(e)) from None
    # The same ceiling `ops_objectives_window_sane` puts on a stored window. Unbounded, the
    # `timedelta` below raises `OverflowError` before any query runs, which reaches the caller
    # as a 500 -- the class MOD-009's review named and every id in this module is checked for.
    if not 1 <= window_hours <= 8760:
        raise InvalidRequest("window_hours_out_of_range")
    end = _bucket(until or _now()) + timedelta(hours=1)
    start = end - timedelta(hours=window_hours)
    sql = ["SELECT bucket_start, observations, total FROM plt01.ops_metric_points",
           " WHERE metric_key = %s AND bucket_start >= %s AND bucket_start < %s"]
    args: list[Any] = [metric_key, start, end]
    if dimensions is not None:
        sql.append(" AND dimensions = %s")
        args.append(Jsonb(dimensions))
    sql.append(" ORDER BY bucket_start")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return {
        "metric_key": metric_key, "window_hours": window_hours,
        "from": start.isoformat(), "until": end.isoformat(),
        "buckets": [{"bucket_start": r[0].isoformat(), "observations": int(r[1]),
                     "total": float(r[2])} for r in rows],
    }


def _buckets_for(
    conn: Connection[Any], *, metric_key: str, window_hours: int, until: datetime,
    dimensions: dict[str, str],
) -> list[objectives.Bucket]:
    """The one series an objective is about, sliced by its exact dimension set.

    The slice is not optional. Without it an objective on a metric with a `consumer` or
    `check_key` dimension aggregates every one of them together, so a consumer sitting at zero
    is invisible behind nine healthy ones and never alerts -- and when a merged ratio does
    breach, the event names only the metric, leaving whoever is paged with no way to tell which
    one failed. Found by review; `series` had refused a *partial* dimension match from the
    start for exactly this reason, and the objective path did a total one.
    """
    end = _bucket(until) + timedelta(hours=1)
    rows = conn.execute(
        "SELECT observations, total FROM plt01.ops_metric_points"
        " WHERE metric_key = %s AND dimensions = %s"
        " AND bucket_start >= %s AND bucket_start < %s ORDER BY bucket_start",
        (metric_key, Jsonb(dimensions), end - timedelta(hours=window_hours), end),
    ).fetchall()
    return [objectives.Bucket(observations=int(r[0]), total=float(r[1])) for r in rows]
