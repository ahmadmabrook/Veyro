"""MOD-011 REL-02 service: metric points, objectives, synthetic checks, capacity, cost and budgets.

The decisions live in `app.observability.catalog`, `objectives` and `ratelimit`. This module
reads rows, calls those, and writes what they return.

**A metric point deliberately does not have to be atomic with the business change it describes,
and that is the opposite call from MOD-010's.** `events.append_event` takes a connection rather
than a pool because a state change committing without its event means a consumer never learns
about something that happened. A metric point is not that: losing one leaves a gap in a chart,
and taking a business write down because the chart could not be updated is the worse failure by a
wide margin. So `observe` opens its own transaction, `observe_in` exists only to save a second
one when the caller already holds a connection, and neither is the "correct" one -- unlike
MOD-010, where the pool-taking wrapper is the bug.

**Cost is an input.** There is no cloud bill, AI invoice or messaging statement in this
repository, so `allocate_cost` records figures a caller supplies, exactly as
`billing.service.issue_invoice` takes a tax rate it cannot derive. The ledger, the budget, the
burn arithmetic and the alert are built; the feed is absent and is not simulated.

**Nothing here runs a synthetic probe.** `record_result` is written by whatever does, and a row
saying "passed" that no probe produced would be the fabricated-evidence shape this codebase has
been bitten by twice. The registry and the ledger are the halves that have to be right whatever
the prober turns out to be.
"""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from typing import Any

from psycopg import errors
from psycopg.types.json import Jsonb

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.observability import catalog, objectives
from app.observability.metrics import _buckets_for, _now, observe_in


def _check_name(exc: errors.CheckViolation) -> str:
    """The constraint that refused, so a client learns which rule it broke, not which table."""
    return getattr(exc.diag, "constraint_name", None) or "constraint_violated"


# ---------------------------------------------------------------------------- objectives

def define_objective(
    pool: Pool, tenant_id: str, *, objective_key: str, kind: str, metric_key: str,
    comparison: str, threshold: float, window_hours: int, aggregate_as: str, owner: str,
    runbook_ref: str, actor_id: str, correlation_id: str,
    dimensions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """DefineSLI and SetSLO, which are one command because they are one row.

    The aggregate is refused here rather than at evaluation time. An objective stated as a p95
    is a legitimate thing to want and this store cannot answer it, so the refusal belongs where
    somebody is writing it down and can see why -- not months later in a dashboard that has
    been quietly comparing a mean against a percentile budget.
    """
    labels = dimensions or {}
    try:
        metric = catalog.require_metric(metric_key)
        # Every declared dimension, with a value. An objective that named only some of them --
        # or none -- would be evaluated against every series the metric has, merged; see the
        # column comment in the migration for what that hides.
        catalog.validate_dimensions(metric_key, labels)
    except catalog.CatalogError as e:
        raise InvalidRequest(str(e)) from None
    try:
        objectives.check_evaluable(kind=kind, comparison=comparison, aggregate_as=aggregate_as,
                                   metric_kind=metric.kind)
    except objectives.ObjectiveError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ops_objectives
                    (tenant_id, objective_key, kind, metric_key, comparison, threshold,
                     window_hours, aggregate_as, dimensions, owner, runbook_ref, set_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING objective_id, set_at
                """,
                (tenant_id, objective_key, kind, metric_key, comparison, threshold,
                 window_hours, aggregate_as, Jsonb(labels), owner, runbook_ref, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("objective_key_already_live") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"objective_id": str(row[0]), "objective_key": objective_key, "kind": kind,
            "metric_key": metric_key, "comparison": comparison, "threshold": float(threshold),
            "window_hours": window_hours, "aggregate_as": aggregate_as, "dimensions": labels,
            "owner": owner, "runbook_ref": runbook_ref, "set_at": row[1].isoformat(),
            "retired_at": None}


def retire_objective(
    pool: Pool, tenant_id: str, objective_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Retire, never delete. An objective that was in force when something breached it is the
    thing somebody will ask about afterwards, and a row that can vanish cannot answer."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE plt01.ops_objectives SET retired_at = now(), retired_by = %s,"
            " retire_correlation_id = %s"
            " WHERE objective_id = %s AND retired_at IS NULL RETURNING objective_key, retired_at",
            (actor_id, correlation_id, objective_id),
        ).fetchone()
        if row is None:
            raise NotFound("live_objective_not_found")
    return {"objective_id": objective_id, "objective_key": row[0],
            "retired_at": row[1].isoformat()}


def list_objectives(
    pool: Pool, tenant_id: str, *, include_retired: bool = False,
) -> list[dict[str, Any]]:
    sql = ("SELECT objective_id, objective_key, kind, metric_key, comparison, threshold,"
           " window_hours, aggregate_as, owner, runbook_ref, set_at, retired_at, dimensions"
           " FROM plt01.ops_objectives")
    if not include_retired:
        sql += " WHERE retired_at IS NULL"
    sql += " ORDER BY objective_key"
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(sql).fetchall()
    return [{"objective_id": str(r[0]), "objective_key": r[1], "kind": r[2], "metric_key": r[3],
             "comparison": r[4], "threshold": float(r[5]), "window_hours": r[6],
             "aggregate_as": r[7], "owner": r[8], "runbook_ref": r[9],
             "set_at": r[10].isoformat(),
             "retired_at": r[11].isoformat() if r[11] else None,
             "dimensions": r[12]} for r in rows]


def evaluate_objective(
    pool: Pool, tenant_id: str, objective_id: str, *, correlation_id: str,
    actor_id: str | None = None, until: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate one objective over its window, and publish a breach if it breached.

    A **retired** objective is refused rather than evaluated. Its threshold is whatever it was
    when somebody stopped standing behind it, and reporting a verdict against a rule nobody owns
    is the actionability failure paragraph 3504 names.

    An empty window returns `met: false` with reason `no_data_in_window`, and that is a
    deliberate verdict rather than an absence: a series with nothing in it is either a producer
    that stopped or an objective nobody wired up, and a dashboard that goes green during an
    outage is the failure this avoids. It does **not** publish a breach, because "the
    measurement is missing" and "the system is failing" are different alerts and conflating them
    is how an alert channel gets muted.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT objective_key, kind, metric_key, comparison, threshold, window_hours,"
            " aggregate_as, owner, runbook_ref, retired_at, dimensions"
            " FROM plt01.ops_objectives WHERE objective_id = %s",
            (objective_id,),
        ).fetchone()
        if row is None:
            raise NotFound("objective_not_found")
        if row[9] is not None:
            raise Conflict("objective_is_retired")
        buckets = _buckets_for(conn, metric_key=row[2], window_hours=row[5],
                               until=until or _now(), dimensions=row[10])
        try:
            verdict = objectives.evaluate(buckets, comparison=row[3], threshold=float(row[4]),
                                          aggregate_as=row[6], window_hours=row[5])
        except objectives.ObjectiveError as e:
            raise InvalidRequest(str(e)) from None
        if not verdict.met and verdict.buckets > 0:
            events.append_event(
                conn, tenant_id, event_type="performance_budget.exceeded",
                aggregate_type="objective", aggregate_id=objective_id,
                payload={"objective_id": objective_id, "objective_key": row[0], "kind": row[1],
                         "metric_key": row[2], "dimensions": row[10],
                         "observed": verdict.observed,
                         "threshold": float(row[4]), "comparison": row[3], "owner": row[7],
                         "runbook_ref": row[8]},
                correlation_id=correlation_id, actor_id=actor_id,
            )
    return {"objective_id": objective_id, "objective_key": row[0], "kind": row[1],
            "metric_key": row[2], "dimensions": row[10],
            "met": verdict.met, "observed": verdict.observed,
            "threshold": verdict.threshold, "comparison": verdict.comparison,
            "buckets": verdict.buckets, "reason": verdict.reason, "owner": row[7],
            "runbook_ref": row[8]}


# ---------------------------------------------------------------------- synthetic checks

def register_check(
    pool: Pool, tenant_id: str, *, check_key: str, description: str, workflow: str,
    interval_seconds: int, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ops_synthetic_checks
                    (tenant_id, check_key, description, workflow, interval_seconds,
                     registered_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING check_id, registered_at
                """,
                (tenant_id, check_key, description, workflow, interval_seconds, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("check_key_already_registered") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"check_id": str(row[0]), "check_key": check_key, "description": description,
            "workflow": workflow, "interval_seconds": interval_seconds, "enabled": True,
            "registered_at": row[1].isoformat(), "disabled_at": None}


def set_check_enabled(
    pool: Pool, tenant_id: str, check_id: str, *, enabled: bool, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Disable and re-enable, both attributed.

    Re-enabling clears the disablement columns, which the `ops_synthetic_enabled_consistent`
    constraint requires: a row reading `enabled` while still carrying a disablement is a check
    whose history says it is off and whose flag says it is on, and the two would be settled by
    whichever query somebody happened to write. MOD-010 shipped a subscription that could be
    deactivated and never reactivated; this is the same shape caught earlier.
    """
    with tenant_scope(pool, tenant_id) as conn:
        if enabled:
            row = conn.execute(
                "UPDATE plt01.ops_synthetic_checks SET enabled = true, disabled_at = NULL,"
                " disabled_by = NULL, disable_correlation_id = NULL"
                " WHERE check_id = %s AND NOT enabled RETURNING check_key",
                (check_id,),
            ).fetchone()
            if row is None:
                raise NotFound("disabled_check_not_found")
        else:
            row = conn.execute(
                "UPDATE plt01.ops_synthetic_checks SET enabled = false, disabled_at = now(),"
                " disabled_by = %s, disable_correlation_id = %s"
                " WHERE check_id = %s AND enabled RETURNING check_key",
                (actor_id, correlation_id, check_id),
            ).fetchone()
            if row is None:
                raise NotFound("enabled_check_not_found")
    return {"check_id": check_id, "check_key": row[0], "enabled": enabled}


def list_checks(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT check_id, check_key, description, workflow, interval_seconds, enabled,"
            " registered_at, disabled_at FROM plt01.ops_synthetic_checks ORDER BY check_key"
        ).fetchall()
    return [{"check_id": str(r[0]), "check_key": r[1], "description": r[2], "workflow": r[3],
             "interval_seconds": r[4], "enabled": r[5], "registered_at": r[6].isoformat(),
             "disabled_at": r[7].isoformat() if r[7] else None} for r in rows]


#: How much of a prober's failure detail is kept. Trimmed rather than refused, because a
#: constraint on length would throw away the evidence instead of shortening it -- and the
#: evidence is the whole reason a failed result carries a detail at all.
_DETAIL_LIMIT = 2000


def record_result(
    pool: Pool, tenant_id: str, *, check_id: str, outcome: str, duration_ms: int,
    actor_id: str, correlation_id: str, detail: str | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Record one probe run, roll it into the two series an SLO reads, and publish a failure.

    The result row, the two metric points and the event all commit together. That matters here
    in a way it does not for an ordinary metric: the series is what an availability objective is
    evaluated against, so a run recorded in the ledger but missing from the series would make
    the SLO disagree with the evidence underneath it, in the direction that hides failures.
    """
    if outcome not in ("passed", "failed"):
        raise InvalidRequest("unknown_outcome")
    at = observed_at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        check = conn.execute(
            "SELECT check_key, enabled FROM plt01.ops_synthetic_checks WHERE check_id = %s",
            (check_id,),
        ).fetchone()
        if check is None:
            raise NotFound("check_not_found")
        # **A disabled check does not report.** The first version selected `enabled` and never
        # looked at it, so disabling a probe -- which is what `set_check_enabled` exists for --
        # stopped nothing: results kept arriving from a prober that had no reason to notice,
        # kept feeding the series an availability objective is evaluated against, and kept
        # publishing `synthetic_check.failed`. Disabling the probe did not stop the paging that
        # disabling it is for. Found by review, with the ignored column still in the SELECT.
        if not check[1]:
            raise Conflict("check_is_disabled")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ops_synthetic_results
                    (tenant_id, check_id, outcome, duration_ms, detail, recorded_by,
                     correlation_id, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING result_id
                """,
                (tenant_id, check_id, outcome, duration_ms,
                 (detail or "")[:_DETAIL_LIMIT] or None, actor_id, correlation_id, at),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        labels = {"check_key": check[0]}
        observe_in(conn, tenant_id, metric_key="ops.synthetic_success",
                   total=1.0 if outcome == "passed" else 0.0, dimensions=labels, at=at)
        observe_in(conn, tenant_id, metric_key="ops.synthetic_latency",
                   total=float(duration_ms), dimensions=labels, at=at)
        if outcome == "failed":
            events.append_event(
                conn, tenant_id, event_type="synthetic_check.failed",
                aggregate_type="synthetic_check", aggregate_id=check_id,
                payload={"check_id": check_id, "check_key": check[0],
                         "duration_ms": duration_ms,
                         "detail": (detail or "")[:_DETAIL_LIMIT]},
                correlation_id=correlation_id,
            )
    assert row is not None
    return {"result_id": str(row[0]), "check_id": check_id, "check_key": check[0],
            "outcome": outcome, "duration_ms": duration_ms, "observed_at": at.isoformat()}


def list_results(
    pool: Pool, tenant_id: str, check_id: str, *, limit: int = 50,
) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT result_id, outcome, duration_ms, detail, observed_at"
            " FROM plt01.ops_synthetic_results WHERE check_id = %s"
            " ORDER BY observed_at DESC LIMIT %s",
            (check_id, max(1, min(limit, 500))),
        ).fetchall()
    return [{"result_id": str(r[0]), "outcome": r[1], "duration_ms": r[2], "detail": r[3],
             "observed_at": r[4].isoformat()} for r in rows]


# ------------------------------------------------------------------------------ capacity

#: Headroom below which a forecast is worth telling somebody about. 2000 basis points is twenty
#: per cent left, which is a fortnight of warning at ordinary growth and is a number somebody
#: should be able to argue with -- which is why it is named here rather than written into the
#: comparison.
CAPACITY_ALERT_BP = 2000


def record_forecast(
    pool: Pool, tenant_id: str, *, resource: str, horizon_days: int, current_value: float,
    projected_value: float, basis: str, actor_id: str, correlation_id: str,
    limit_value: float | None = None,
) -> dict[str, Any]:
    """RecordCapacityForecast, with the headroom derived rather than accepted.

    `limit_value` is the capacity the projection is measured against, and the headroom is
    computed from it. Taking a headroom from the caller would be accepting a conclusion rather
    than a measurement -- MOD-008's derive-don't-accept finding, applied to a number instead of
    a scope.
    """
    for name, number in (("current_value", current_value),
                         ("projected_value", projected_value)):
        if not isfinite(number):
            raise InvalidRequest(f"{name}_must_be_a_finite_number")
    headroom_bp: int | None = None
    if limit_value is not None:
        if not isfinite(limit_value):
            raise InvalidRequest("limit_value_must_be_a_finite_number")
        if limit_value <= 0:
            raise InvalidRequest("limit_must_be_positive")
        # Clamped into the column rather than left to overflow it. A projection far past the
        # limit produces a large negative figure, and an unbounded one reaches psycopg as a
        # `NumericValueOutOfRange` -- a 500 where a 422 is meant. -1000000 bp is a projection a
        # hundred times the limit, which is past every decision anybody would make from it.
        headroom_bp = max(-1000000, int((limit_value - projected_value) * 10000 // limit_value))
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ops_capacity_forecasts
                    (tenant_id, resource, horizon_days, current_value, projected_value,
                     limit_value, headroom_bp, basis, forecast_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING forecast_id, forecast_at
                """,
                (tenant_id, resource, horizon_days, current_value, projected_value,
                 limit_value, headroom_bp, basis, actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        if headroom_bp is not None and headroom_bp <= CAPACITY_ALERT_BP:
            events.append_event(
                conn, tenant_id, event_type="capacity.threshold.reached",
                aggregate_type="capacity_forecast", aggregate_id=str(row[0]),
                payload={"forecast_id": str(row[0]), "resource": resource,
                         "horizon_days": horizon_days, "headroom_bp": headroom_bp,
                         "projected_value": projected_value},
                correlation_id=correlation_id, actor_id=actor_id,
            )
    return {"forecast_id": str(row[0]), "resource": resource, "horizon_days": horizon_days,
            "current_value": current_value, "projected_value": projected_value,
            "limit_value": limit_value, "headroom_bp": headroom_bp, "basis": basis,
            "forecast_at": row[1].isoformat()}


def list_forecasts(
    pool: Pool, tenant_id: str, *, resource: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ("SELECT forecast_id, resource, horizon_days, current_value, projected_value,"
           " limit_value, headroom_bp, basis, forecast_at FROM plt01.ops_capacity_forecasts")
    args: list[Any] = []
    if resource is not None:
        sql += " WHERE resource = %s"
        args.append(resource)
    sql += " ORDER BY forecast_at DESC LIMIT %s"
    args.append(max(1, min(limit, 500)))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(sql, tuple(args)).fetchall()
    return [{"forecast_id": str(r[0]), "resource": r[1], "horizon_days": r[2],
             "current_value": float(r[3]), "projected_value": float(r[4]),
             "limit_value": float(r[5]) if r[5] is not None else None,
             "headroom_bp": r[6], "basis": r[7], "forecast_at": r[8].isoformat()}
            for r in rows]


# ------------------------------------------------------------------------ cost and budgets

def allocate_cost(
    pool: Pool, tenant_id: str, *, period_start: date, period_end: date, dimension: str,
    dimension_value: str, currency: str, amount_minor: int, source: str, actor_id: str,
    correlation_id: str, corrects_cost_record_id: str | None = None,
) -> dict[str, Any]:
    """AllocateCost. Insert-only, signed, and in minor units as an integer.

    A correction is a later row with the opposite sign rather than an edit, because a cost
    somebody can revise cannot be reconciled against the statement it came from. The amount is
    `bigint` and no part of this path is floating point, which is MOD-015's convention and
    applies to every amount in this repository.
    """
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise InvalidRequest("amount_must_be_an_integer_in_minor_units")
    with tenant_scope(pool, tenant_id) as conn:
        if corrects_cost_record_id is not None:
            # The foreign key proves the row exists, which is all it proves. A "correction"
            # that names a different currency, a different dimension or the same sign is not
            # one, and the docstring above claims the opposite-sign rule as a property -- a
            # claim nothing checked until review asked.
            target = conn.execute(
                "SELECT currency, dimension, dimension_value, amount_minor"
                " FROM plt01.ops_cost_records WHERE cost_record_id = %s",
                (corrects_cost_record_id,),
            ).fetchone()
            if target is None:
                raise NotFound("corrected_cost_record_not_found")
            if (target[0], target[1], target[2]) != (currency, dimension, dimension_value):
                raise InvalidRequest("a_correction_matches_the_record_it_corrects")
            if (amount_minor > 0) == (int(target[3]) > 0):
                raise InvalidRequest("a_correction_has_the_opposite_sign")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ops_cost_records
                    (tenant_id, period_start, period_end, dimension, dimension_value, currency,
                     amount_minor, source, corrects_cost_record_id, allocated_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING cost_record_id, allocated_at
                """,
                (tenant_id, period_start, period_end, dimension, dimension_value, currency,
                 amount_minor, source, corrects_cost_record_id, actor_id, correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("corrected_cost_record_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"cost_record_id": str(row[0]), "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(), "dimension": dimension,
            "dimension_value": dimension_value, "currency": currency,
            "amount_minor": amount_minor, "source": source,
            "corrects_cost_record_id": corrects_cost_record_id,
            "allocated_at": row[1].isoformat()}


def cost_summary(
    pool: Pool, tenant_id: str, *, period_start: date, period_end: date,
) -> dict[str, Any]:
    """Cost by dimension over a period, per currency.

    Per currency and never summed across them: a total that added euros to dinars would be a
    number with no unit, and this repository has no exchange rate and no source for one.
    """
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT currency, dimension, sum(amount_minor) FROM plt01.ops_cost_records"
            " WHERE period_start >= %s AND period_end <= %s"
            " GROUP BY currency, dimension ORDER BY currency, dimension",
            (period_start, period_end),
        ).fetchall()
    by_currency: dict[str, dict[str, Any]] = {}
    for currency, dimension, total in rows:
        entry = by_currency.setdefault(currency, {"currency": currency, "total_minor": 0,
                                                  "by_dimension": {}})
        entry["by_dimension"][dimension] = int(total)
        entry["total_minor"] += int(total)
    return {"period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "currencies": list(by_currency.values())}


def gross_margin(
    pool: Pool, tenant_id: str, *, period_start: date, period_end: date,
) -> dict[str, Any]:
    """Paragraph 3507: gross margin stays visible as usage and AI scale.

    Revenue is what MOD-015 actually invoiced in the period, **net of tax and of the partner's
    share** -- tax is collected on somebody else's behalf and a revenue share is not Veyro's
    money, so counting either as revenue would overstate the margin in exactly the direction
    nobody checks. Costs are what `allocate_cost` recorded.

    Currencies are kept apart. A currency with cost and no revenue is reported with a null
    margin and named rather than dropped, because a cost that silently does not appear is the
    FinOps failure worth guarding against.
    """
    with tenant_scope(pool, tenant_id) as conn:
        # Credit notes are subtracted in the same query, by the period of the invoice they
        # credit. MOD-015 has no invoice edit and no void -- "a correction is a credit note
        # rather than an edit", stored positive and always read as a reduction -- so a margin
        # that reads only `bil_invoices` is blind to the single mechanism by which revenue goes
        # down. Fully credit an invoice and the first version still reported a 50% margin on a
        # period that earned nothing, which is precisely the overstatement this function's
        # docstring says it exists to avoid. Attributed to the invoice's period rather than to
        # the credit's own date, so a correction lands against the revenue it corrects.
        revenue = dict(conn.execute(
            "SELECT i.currency,"
            " sum(i.subtotal_minor - i.revenue_share_minor - coalesce(c.credited, 0))"
            " FROM plt01.bil_invoices i"
            " LEFT JOIN LATERAL ("
            "   SELECT sum(amount_minor) AS credited FROM plt01.bil_credit_notes n"
            "   WHERE n.invoice_id = i.invoice_id) c ON true"
            " WHERE i.period_start >= %s AND i.period_end <= %s"
            " GROUP BY i.currency",
            (period_start, period_end),
        ).fetchall())
        costs = dict(conn.execute(
            "SELECT currency, sum(amount_minor) FROM plt01.ops_cost_records"
            " WHERE period_start >= %s AND period_end <= %s GROUP BY currency",
            (period_start, period_end),
        ).fetchall())
    lines = []
    for currency in sorted(set(revenue) | set(costs)):
        revenue_minor = int(revenue.get(currency, 0))
        cost_minor = int(costs.get(currency, 0))
        margin: int | None
        try:
            margin = objectives.margin_bp(revenue_minor=revenue_minor, cost_minor=cost_minor)
        except objectives.ObjectiveError:
            margin = None
        lines.append({"currency": currency, "revenue_minor": revenue_minor,
                      "cost_minor": cost_minor, "margin_bp": margin})
    return {"period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "lines": lines}


def set_budget(
    pool: Pool, tenant_id: str, *, budget_key: str, dimension: str, currency: str,
    amount_minor: int, period: str, owner: str, actor_id: str, correlation_id: str,
    dimension_value: str | None = None, warn_at_bp: int = 8000,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ops_budgets
                    (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
                     period, warn_at_bp, owner, set_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING budget_id, set_at
                """,
                (tenant_id, budget_key, dimension, dimension_value, currency, amount_minor,
                 period, warn_at_bp, owner, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("budget_key_already_live") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"budget_id": str(row[0]), "budget_key": budget_key, "dimension": dimension,
            "dimension_value": dimension_value, "currency": currency,
            "amount_minor": amount_minor, "period": period, "warn_at_bp": warn_at_bp,
            "owner": owner, "set_at": row[1].isoformat(), "retired_at": None}


def retire_budget(
    pool: Pool, tenant_id: str, budget_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE plt01.ops_budgets SET retired_at = now(), retired_by = %s,"
            " retire_correlation_id = %s"
            " WHERE budget_id = %s AND retired_at IS NULL RETURNING budget_key, retired_at",
            (actor_id, correlation_id, budget_id),
        ).fetchone()
        if row is None:
            raise NotFound("live_budget_not_found")
    return {"budget_id": budget_id, "budget_key": row[0], "retired_at": row[1].isoformat()}


def list_budgets(
    pool: Pool, tenant_id: str, *, include_retired: bool = False,
) -> list[dict[str, Any]]:
    sql = ("SELECT budget_id, budget_key, dimension, dimension_value, currency, amount_minor,"
           " period, warn_at_bp, owner, set_at, retired_at FROM plt01.ops_budgets")
    if not include_retired:
        sql += " WHERE retired_at IS NULL"
    sql += " ORDER BY budget_key"
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(sql).fetchall()
    return [{"budget_id": str(r[0]), "budget_key": r[1], "dimension": r[2],
             "dimension_value": r[3], "currency": r[4], "amount_minor": int(r[5]),
             "period": r[6], "warn_at_bp": r[7], "owner": r[8], "set_at": r[9].isoformat(),
             "retired_at": r[10].isoformat() if r[10] else None} for r in rows]


def evaluate_budget(
    pool: Pool, tenant_id: str, budget_id: str, *, period_start: date, correlation_id: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """AlertBudgetBurn: spend against budget for a period, and an alert per threshold crossed.

    Three things make this safe to run on a loop. The spend is summed from `ops_cost_records`
    at the moment of evaluation rather than carried on the budget. The alert row **snapshots**
    the owner, the budget and the spend that fired it, so it still says why somebody was told
    even after the budget is retired and replaced -- MOD-008's snapshot-your-terms finding. And
    the unique index on (budget, period, threshold) means a sweep running twice in an hour
    raises nothing the second time: an alert channel that repeats itself is one people mute,
    and a muted alert is worse than none.

    A **retired** budget is refused. Spending against a rule nobody stands behind is not an
    alert anybody can act on.
    """
    with tenant_scope(pool, tenant_id) as conn:
        budget = conn.execute(
            "SELECT budget_key, dimension, dimension_value, currency, amount_minor,"
            " warn_at_bp, owner, retired_at, period FROM plt01.ops_budgets"
            " WHERE budget_id = %s",
            (budget_id,),
        ).fetchone()
        if budget is None:
            raise NotFound("budget_not_found")
        if budget[7] is not None:
            raise Conflict("budget_is_retired")
        try:
            window_start, window_end = objectives.budget_window(budget[8], period_start)
        except objectives.ObjectiveError as e:
            raise InvalidRequest(str(e)) from None
        sql = ["SELECT coalesce(sum(amount_minor), 0) FROM plt01.ops_cost_records",
               " WHERE currency = %s AND period_start >= %s AND period_end < %s"]
        args: list[Any] = [budget[3], window_start, window_end]
        if budget[1] != "total":
            sql.append(" AND dimension = %s AND dimension_value = %s")
            args.extend([budget[1], budget[2]])
        spent_row = conn.execute("".join(sql), tuple(args)).fetchone()
        assert spent_row is not None
        spent = max(0, int(spent_row[0]))
        try:
            burn = objectives.burn(spent_minor=spent, budget_minor=int(budget[4]),
                                   warn_at_bp=budget[5])
        except objectives.ObjectiveError as e:
            raise InvalidRequest(str(e)) from None
        already = {r[0] for r in conn.execute(
            "SELECT threshold_bp FROM plt01.ops_budget_alerts"
            " WHERE budget_id = %s AND period_start = %s",
            (budget_id, window_start),
        ).fetchall()}
        raised = []
        for threshold in objectives.alerts_to_raise(burn, already):
            # `RETURNING`, and the event only when a row was actually written. The insert is
            # `DO NOTHING`, so two sweeps racing would otherwise both publish
            # `cost.anomaly.detected` and both report the alert while one row existed: the
            # unique index protects the table and not the alert channel, and the channel is
            # what people mute.
            written = conn.execute(
                """
                INSERT INTO plt01.ops_budget_alerts
                    (tenant_id, budget_id, period_start, threshold_bp, spent_minor,
                     budget_minor, currency, owner)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, budget_id, period_start, threshold_bp) DO NOTHING
                RETURNING alert_id
                """,
                (tenant_id, budget_id, window_start, threshold, spent, int(budget[4]),
                 budget[3], budget[6]),
            ).fetchone()
            if written is None:
                continue
            raised.append(threshold)
            events.append_event(
                conn, tenant_id, event_type="cost.anomaly.detected",
                aggregate_type="budget", aggregate_id=budget_id,
                payload={"budget_id": budget_id, "budget_key": budget[0],
                         "period_start": window_start.isoformat(), "threshold_bp": threshold,
                         "consumed_bp": burn.consumed_bp, "spent_minor": spent,
                         "budget_minor": int(budget[4]), "currency": budget[3],
                         "owner": budget[6]},
                correlation_id=correlation_id, actor_id=actor_id,
            )
    return {"budget_id": budget_id, "budget_key": budget[0],
            "period_start": window_start.isoformat(), "period_end": window_end.isoformat(),
            "currency": budget[3],
            "spent_minor": spent, "budget_minor": int(budget[4]),
            "consumed_bp": burn.consumed_bp, "over": burn.over,
            "thresholds_crossed": list(burn.crossed), "alerts_raised": raised}


def list_budget_alerts(pool: Pool, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT alert_id, budget_id, period_start, threshold_bp, spent_minor,"
            " budget_minor, currency, owner, raised_at FROM plt01.ops_budget_alerts"
            " ORDER BY raised_at DESC LIMIT %s",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [{"alert_id": str(r[0]), "budget_id": str(r[1]), "period_start": r[2].isoformat(),
             "threshold_bp": r[3], "spent_minor": int(r[4]), "budget_minor": int(r[5]),
             "currency": r[6], "owner": r[7], "raised_at": r[8].isoformat()} for r in rows]
