"""MOD-015 PLT-03 service: plan catalogue, subscriptions, entitlements, metering, invoices.

The decisions live in `app.billing.money`, `app.billing.subscription` and `app.billing.usage`.
This module reads rows, calls those, and writes what they return. No arithmetic and no transition
is decided here.

**It is the first module that touches both planes in one call.** `start_subscription` and
`change_plan` read the catalogue through the platform pool and write the subscription through the
tenant pool. The two database roles stay separate -- neither is a member of the other and neither
can reach the other's schema -- so the separation that matters is intact; what crosses is the
Python process, which is the same process that already serves both planes in `app.main`.

**The catalogue is read once and snapshotted.** A subscription stores `plan_code`,
`plan_version` and a `terms` document holding the price, the interval, the prices for metered
overage and the entitlement limits as they stood when it was sold. Every later invoice is built
from that snapshot, never from today's catalogue, so re-reading an old invoice gives the same
answer after the catalogue has moved on.

Not built, and said here rather than left to be discovered:

* **No payment provider and no stored payment methods.** Taking a card is a real external action
  with real money behind it, and the owner reserves real financial expenditure. The ledger this
  module writes is complete without it: `payment_failed` and `payment_recovered` are commands a
  provider integration would call, and they work today against synthetic input.
* **No tax engine.** Rates are jurisdictional and the sources state none, so `issue_invoice`
  takes a rate rather than deriving one. Inventing a rate table would be inventing owner policy.
* **No cost or gross-margin view** (PLT-03-R07). It needs cloud, AI, messaging and support cost
  feeds that do not exist in this repository; a margin computed from nothing is a number that
  reads as fact.
* **No outbox.** `saas.subscription.started`, `saas.subscription.changed`, `saas.usage.recorded`,
  `saas.quota.reached` and `saas.payment.failed` are named in the TSD and nothing consumes them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.billing import money
from app.billing import subscription as sub
from app.billing import usage as use
from app.db import Pool, platform_scope, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound


def _json(value: Any) -> Jsonb:
    return Jsonb(value)


# --------------------------------------------------------------------------- plan catalogue

def create_plan(
    pool: Pool,
    *,
    plan_code: str,
    plan_version: int,
    edition: str,
    currency: str,
    region: str,
    billing_interval: str,
    base_price_minor: int,
    trial_days: int = 0,
    contract_months: int | None = None,
    prices: list[dict[str, Any]] | None = None,
    entitlements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """CreateSaaSPlan (PLT-03-R01). Drafts a plan version with its prices and entitlement limits.

    Prices and entitlements can only be written now: neither table carries an UPDATE grant, so a
    plan version's commercial terms are fixed from this call onwards. Changing them means a new
    version, which is the behaviour that keeps old invoices reconstructible.
    """
    if base_price_minor < 0:
        raise InvalidRequest("price_must_not_be_negative")
    with platform_scope(pool) as conn:
        try:
            conn.execute(
                """
                INSERT INTO plt01_platform.saas_plans
                    (plan_code, plan_version, edition, currency, region, billing_interval,
                     contract_months, base_price_minor, trial_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (plan_code, plan_version, edition, currency, region, billing_interval,
                 contract_months, base_price_minor, trial_days),
            )
        except errors.UniqueViolation:
            raise Conflict("plan_version_exists") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_plan") from None

        for price in prices or []:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01_platform.saas_prices
                        (plan_code, plan_version, price_code, kind, meter_code, unit,
                         unit_price_minor, included_quantity)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (plan_code, plan_version, price["price_code"], price["kind"],
                     price.get("meter_code"), price.get("unit"),
                     int(price["unit_price_minor"]), int(price.get("included_quantity", 0))),
                )
            except errors.CheckViolation:
                raise InvalidRequest("bad_price") from None
            except errors.UniqueViolation:
                raise Conflict("duplicate_price_code") from None
            except KeyError:
                raise InvalidRequest("bad_price") from None

        for entitlement in entitlements or []:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01_platform.saas_plan_entitlements
                        (plan_code, plan_version, feature_code, limit_value, unlimited)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (plan_code, plan_version, entitlement["feature_code"],
                     entitlement.get("limit_value"), bool(entitlement.get("unlimited", False))),
                )
            except errors.CheckViolation:
                raise InvalidRequest("bad_entitlement") from None
            except errors.UniqueViolation:
                raise Conflict("duplicate_feature_code") from None
            except KeyError:
                raise InvalidRequest("bad_entitlement") from None
    return {"plan_code": plan_code, "plan_version": plan_version, "status": "draft"}


def set_plan_status(
    pool: Pool, *, plan_code: str, plan_version: int, status: str
) -> dict[str, Any]:
    """Publish or retire a plan version. Only the lifecycle columns are grantable."""
    if status not in ("published", "retired"):
        raise InvalidRequest("bad_plan_status")
    with platform_scope(pool) as conn:
        current = conn.execute(
            "SELECT status FROM plt01_platform.saas_plans"
            " WHERE plan_code = %s AND plan_version = %s FOR UPDATE",
            (plan_code, plan_version),
        ).fetchone()
        if current is None:
            raise NotFound("plan_not_found")
        wanted_from = "draft" if status == "published" else "published"
        if current[0] != wanted_from:
            raise Conflict("illegal_plan_transition")
        conn.execute(
            """
            UPDATE plt01_platform.saas_plans
            SET status = %s,
                published_at = CASE WHEN %s = 'published' THEN now() ELSE published_at END,
                retired_at = CASE WHEN %s = 'retired' THEN now() ELSE retired_at END
            WHERE plan_code = %s AND plan_version = %s
            """,
            (status, status, status, plan_code, plan_version),
        )
    return {"plan_code": plan_code, "plan_version": plan_version, "status": status}


def _read_plan(conn: Connection[Any], plan_code: str, plan_version: int | None) -> dict[str, Any]:
    """The plan terms as a snapshot document. `plan_version` None takes the newest published."""
    if plan_version is None:
        row = conn.execute(
            "SELECT plan_version FROM plt01_platform.saas_plans"
            " WHERE plan_code = %s AND status = 'published'"
            " ORDER BY plan_version DESC LIMIT 1",
            (plan_code,),
        ).fetchone()
        if row is None:
            raise NotFound("no_published_plan_version")
        plan_version = int(row[0])

    plan = conn.execute(
        """
        SELECT edition, status, currency, region, billing_interval, contract_months,
               base_price_minor, trial_days
        FROM plt01_platform.saas_plans WHERE plan_code = %s AND plan_version = %s
        """,
        (plan_code, plan_version),
    ).fetchone()
    if plan is None:
        raise NotFound("plan_not_found")
    prices = conn.execute(
        "SELECT price_code, kind, meter_code, unit, unit_price_minor, included_quantity"
        " FROM plt01_platform.saas_prices WHERE plan_code = %s AND plan_version = %s"
        " ORDER BY price_code",
        (plan_code, plan_version),
    ).fetchall()
    entitlements = conn.execute(
        "SELECT feature_code, limit_value, unlimited"
        " FROM plt01_platform.saas_plan_entitlements"
        " WHERE plan_code = %s AND plan_version = %s ORDER BY feature_code",
        (plan_code, plan_version),
    ).fetchall()
    return {
        "plan_code": plan_code, "plan_version": int(plan_version), "edition": plan[0],
        "status": plan[1], "currency": plan[2], "region": plan[3],
        "billing_interval": plan[4],
        "contract_months": int(plan[5]) if plan[5] is not None else None,
        "base_price_minor": int(plan[6]), "trial_days": int(plan[7]),
        "prices": [
            {"price_code": p[0], "kind": p[1], "meter_code": p[2], "unit": p[3],
             "unit_price_minor": int(p[4]), "included_quantity": int(p[5])} for p in prices
        ],
        "entitlements": [
            {"feature_code": e[0],
             "limit_value": int(e[1]) if e[1] is not None else None,
             "unlimited": bool(e[2])} for e in entitlements
        ],
    }


def get_plan(pool: Pool, *, plan_code: str, plan_version: int | None = None) -> dict[str, Any]:
    with platform_scope(pool) as conn:
        return _read_plan(conn, plan_code, plan_version)


def list_plans(pool: Pool) -> list[dict[str, Any]]:
    with platform_scope(pool) as conn:
        rows = conn.execute(
            "SELECT plan_code, plan_version, edition, status, currency, region,"
            " billing_interval, base_price_minor, trial_days FROM plt01_platform.saas_plans"
            " ORDER BY plan_code, plan_version"
        ).fetchall()
    return [
        {"plan_code": r[0], "plan_version": int(r[1]), "edition": r[2], "status": r[3],
         "currency": r[4], "region": r[5], "billing_interval": r[6],
         "base_price_minor": int(r[7]), "trial_days": int(r[8])} for r in rows
    ]


# --------------------------------------------------------------------------- subscriptions

def _period_for(interval: str, start: date) -> tuple[date, date]:
    """The first billing period. Monthly and contract bill monthly; annual bills yearly.

    A month is taken as the same day of the next month, falling back to the last day that exists
    -- 31 January plus a month is 28 February. Subsequent periods roll by length rather than by
    calendar (`subscription.next_period`), so this choice only ever shapes the first one.
    """
    if interval == "annual":
        try:
            return start, start.replace(year=start.year + 1)
        except ValueError:  # 29 February
            return start, start.replace(year=start.year + 1, day=28)
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    day = start.day
    while day > 1:
        try:
            return start, date(year, month, day)
        except ValueError:
            day -= 1
    return start, date(year, month, 1)


def _live_subscription(conn: Connection[Any], *, lock: bool = False) -> dict[str, Any]:
    row = conn.execute(
        "SELECT subscription_id, plan_code, plan_version, terms, status, currency,"
        " billing_interval, period_start, period_end, trial_ends_on, started_on,"
        " partner_code, revenue_share_bp, version"
        " FROM plt01.bil_subscriptions WHERE status <> 'cancelled'"
        + (" FOR UPDATE" if lock else "")
    ).fetchone()
    if row is None:
        raise NotFound("no_live_subscription")
    return {
        "subscription_id": str(row[0]), "plan_code": row[1], "plan_version": int(row[2]),
        "terms": row[3], "status": row[4], "currency": row[5], "billing_interval": row[6],
        "period_start": row[7], "period_end": row[8], "trial_ends_on": row[9],
        "started_on": row[10], "partner_code": row[11],
        "revenue_share_bp": int(row[12]) if row[12] is not None else None,
        "version": int(row[13]),
    }


def _record_change(
    conn: Connection[Any], tenant_id: str, subscription_id: str, **fields: Any
) -> None:
    conn.execute(
        """
        INSERT INTO plt01.bil_subscription_changes
            (tenant_id, subscription_id, change_kind, from_plan_code, from_plan_version,
             to_plan_code, to_plan_version, from_status, to_status, effective_on,
             proration_minor, reason, actor_id, correlation_id)
        VALUES (%(tenant_id)s, %(subscription_id)s, %(change_kind)s, %(from_plan_code)s,
                %(from_plan_version)s, %(to_plan_code)s, %(to_plan_version)s, %(from_status)s,
                %(to_status)s, %(effective_on)s, %(proration_minor)s, %(reason)s, %(actor_id)s,
                %(correlation_id)s)
        """,
        {
            "tenant_id": tenant_id, "subscription_id": subscription_id,
            "from_plan_code": None, "from_plan_version": None, "to_plan_code": None,
            "to_plan_version": None, "from_status": None, "to_status": None,
            "proration_minor": 0, "reason": None, **fields,
        },
    )


def start_subscription(
    tenant_pool: Pool,
    platform_pool: Pool,
    tenant_id: str,
    *,
    plan_code: str,
    actor_id: str,
    correlation_id: str,
    plan_version: int | None = None,
    start_on: date | None = None,
    partner_code: str | None = None,
    revenue_share_bp: int | None = None,
) -> dict[str, Any]:
    """StartTenantSubscription (PLT-03-R02). Snapshots the plan and grants its entitlements.

    A plan with a trial starts `trialing` and is not billed for that period; one without starts
    `active`. The trial length comes from the snapshot, so extending a trial in the catalogue does
    not extend trials already running.
    """
    with platform_scope(platform_pool) as conn:
        plan = _read_plan(conn, plan_code, plan_version)
    if plan["status"] != "published":
        raise Conflict("plan_not_published")

    started = start_on or datetime.now(UTC).date()
    period_start, period_end = _period_for(plan["billing_interval"], started)
    trialing = plan["trial_days"] > 0
    trial_ends_on = date.fromordinal(started.toordinal() + plan["trial_days"]) if trialing else None
    status = sub.TRIALING if trialing else sub.ACTIVE

    with tenant_scope(tenant_pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bil_subscriptions
                    (tenant_id, plan_code, plan_version, terms, status, currency,
                     billing_interval, period_start, period_end, trial_ends_on, started_on,
                     partner_code, revenue_share_bp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING subscription_id
                """,
                (tenant_id, plan["plan_code"], plan["plan_version"], _json(plan), status,
                 plan["currency"], plan["billing_interval"], period_start, period_end,
                 trial_ends_on, started, partner_code, revenue_share_bp),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("subscription_already_live") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_subscription") from None
        assert row is not None
        subscription_id = str(row[0])

        for entitlement in plan["entitlements"]:
            conn.execute(
                """
                INSERT INTO plt01.bil_entitlements
                    (tenant_id, subscription_id, feature_code, limit_value, unlimited, source)
                VALUES (%s, %s, %s, %s, %s, 'plan')
                """,
                (tenant_id, subscription_id, entitlement["feature_code"],
                 entitlement["limit_value"], entitlement["unlimited"]),
            )
        _record_change(
            conn, tenant_id, subscription_id, change_kind="start",
            to_plan_code=plan["plan_code"], to_plan_version=plan["plan_version"],
            to_status=status, effective_on=started, actor_id=actor_id,
            correlation_id=correlation_id,
        )
    return {
        "subscription_id": subscription_id, "plan_code": plan["plan_code"],
        "plan_version": plan["plan_version"], "status": status,
        "currency": plan["currency"], "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "trial_ends_on": trial_ends_on.isoformat() if trial_ends_on else None,
    }


def get_subscription(pool: Pool, tenant_id: str) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        live = _live_subscription(conn)
    return {
        **{k: v for k, v in live.items() if k != "terms"},
        "period_start": live["period_start"].isoformat(),
        "period_end": live["period_end"].isoformat(),
        "started_on": live["started_on"].isoformat(),
        "trial_ends_on": live["trial_ends_on"].isoformat() if live["trial_ends_on"] else None,
        "base_price_minor": int(live["terms"]["base_price_minor"]),
        "admitted_commands": sub.admitted_commands(live["status"]),
    }


def subscription_history(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT change_kind, from_plan_code, from_plan_version, to_plan_code,"
            " to_plan_version, from_status, to_status, effective_on, proration_minor, reason,"
            " occurred_at FROM plt01.bil_subscription_changes ORDER BY occurred_at, change_id"
        ).fetchall()
    return [
        {"change_kind": r[0], "from_plan_code": r[1],
         "from_plan_version": int(r[2]) if r[2] is not None else None,
         "to_plan_code": r[3], "to_plan_version": int(r[4]) if r[4] is not None else None,
         "from_status": r[5], "to_status": r[6], "effective_on": r[7].isoformat(),
         "proration_minor": int(r[8]), "reason": r[9], "occurred_at": r[10].isoformat()}
        for r in rows
    ]


def transition_subscription(
    pool: Pool, tenant_id: str, *, command: str, actor_id: str, correlation_id: str,
    reason: str | None = None, expected_version: int | None = None,
) -> dict[str, Any]:
    """Move a subscription along its lifecycle (PLT-03-R05, and SuspendForBilling).

    `grace_expired` is the suspension command; the decision about when a grace period has run out
    belongs to whatever schedules it, not to this function.
    """
    with tenant_scope(pool, tenant_id) as conn:
        live = _live_subscription(conn, lock=True)
        if expected_version is not None and expected_version != live["version"]:
            raise Conflict("version_mismatch")
        try:
            new_status = sub.apply_command(live["status"], command)
        except sub.LifecycleError as exc:
            raise (InvalidRequest(exc.code) if exc.code == "unknown_command"
                   else Conflict(exc.code)) from None
        today = datetime.now(UTC).date()
        conn.execute(
            """
            UPDATE plt01.bil_subscriptions
            SET status = %s,
                cancelled_on = CASE WHEN %s = 'cancelled' THEN %s ELSE cancelled_on END,
                version = version + 1
            WHERE subscription_id = %s
            """,
            (new_status, new_status, today, live["subscription_id"]),
        )
        _record_change(
            conn, tenant_id, live["subscription_id"],
            change_kind="cancel" if new_status == sub.CANCELLED else "status",
            from_status=live["status"], to_status=new_status, effective_on=today,
            reason=reason, actor_id=actor_id, correlation_id=correlation_id,
        )
    return {"subscription_id": live["subscription_id"], "from_status": live["status"],
            "status": new_status, "version": live["version"] + 1}


def change_plan(
    tenant_pool: Pool,
    platform_pool: Pool,
    tenant_id: str,
    *,
    plan_code: str,
    actor_id: str,
    correlation_id: str,
    plan_version: int | None = None,
    effective_on: date | None = None,
    in_use: dict[str, int] | None = None,
    acknowledge_reductions: bool = False,
) -> dict[str, Any]:
    """ChangeTenantPlan (PLT-03-R02), refusing a silent reduction (PLT-03's critical control).

    `in_use` is what the tenant currently consumes per feature. The caller supplies it because the
    modules that own those counts -- locations, staff, storage -- are not this one, and this
    module must not guess at their numbers. An empty mapping means nothing is claimed to be in
    use, and nothing can then breach.

    When a downgrade would put a feature over its new limit the change is refused and the breaches
    are listed. Passing `acknowledge_reductions` proceeds: the limits change, and **no data is
    touched** either way -- enforcing a lowered limit against existing rows is the owning module's
    decision, made in the open, not a side effect of a billing call.
    """
    with platform_scope(platform_pool) as conn:
        plan = _read_plan(conn, plan_code, plan_version)
    if plan["status"] != "published":
        raise Conflict("plan_not_published")

    with tenant_scope(tenant_pool, tenant_id) as conn:
        live = _live_subscription(conn, lock=True)
        if live["status"] == sub.CANCELLED:
            raise Conflict("subscription_cancelled")
        if live["currency"] != plan["currency"]:
            raise InvalidRequest("currency_change_not_supported")
        if (live["plan_code"], live["plan_version"]) == (plan["plan_code"], plan["plan_version"]):
            raise Conflict("already_on_this_plan")

        limits = [
            sub.EntitlementLimit(e["feature_code"], e["limit_value"], e["unlimited"])
            for e in plan["entitlements"]
        ]
        breaches = sub.entitlement_breaches(in_use or {}, limits)
        if breaches and not acknowledge_reductions:
            raise Conflict("entitlement_reduction_requires_acknowledgement")

        when = effective_on or datetime.now(UTC).date()
        old_price = int(live["terms"]["base_price_minor"])
        proration = money.plan_change_proration(
            old_price, plan["base_price_minor"],
            period_start=live["period_start"], period_end=live["period_end"], effective_on=when,
        )
        conn.execute(
            """
            UPDATE plt01.bil_subscriptions
            SET plan_code = %s, plan_version = %s, terms = %s, billing_interval = %s,
                version = version + 1
            WHERE subscription_id = %s
            """,
            (plan["plan_code"], plan["plan_version"], _json(plan), plan["billing_interval"],
             live["subscription_id"]),
        )
        # Entitlements follow the new plan. Rows are replaced in place rather than deleted and
        # re-inserted, because `veyro_cp_app` holds no DELETE here and because a feature's grant
        # history is worth more than a tidy table.
        for entitlement in plan["entitlements"]:
            conn.execute(
                """
                INSERT INTO plt01.bil_entitlements
                    (tenant_id, subscription_id, feature_code, limit_value, unlimited, source)
                VALUES (%s, %s, %s, %s, %s, 'plan')
                ON CONFLICT (tenant_id, subscription_id, feature_code) DO UPDATE
                SET limit_value = EXCLUDED.limit_value, unlimited = EXCLUDED.unlimited,
                    version = plt01.bil_entitlements.version + 1
                """,
                (tenant_id, live["subscription_id"], entitlement["feature_code"],
                 entitlement["limit_value"], entitlement["unlimited"]),
            )
        _record_change(
            conn, tenant_id, live["subscription_id"],
            change_kind=sub.change_kind(old_price, plan["base_price_minor"]),
            from_plan_code=live["plan_code"], from_plan_version=live["plan_version"],
            to_plan_code=plan["plan_code"], to_plan_version=plan["plan_version"],
            effective_on=when, proration_minor=proration, actor_id=actor_id,
            correlation_id=correlation_id,
        )
    return {
        "subscription_id": live["subscription_id"], "plan_code": plan["plan_code"],
        "plan_version": plan["plan_version"], "proration_minor": proration,
        "effective_on": when.isoformat(),
        "acknowledged_breaches": [
            {"feature_code": b.feature_code, "in_use": b.in_use, "new_limit": b.new_limit}
            for b in breaches
        ],
    }


# --------------------------------------------------------------------------- entitlements

def grant_entitlement(
    pool: Pool, tenant_id: str, *, feature_code: str, limit_value: int | None = None,
    unlimited: bool = False,
) -> dict[str, Any]:
    """GrantPlanEntitlement (PLT-03-R03): an entitlement outside the plan, marked as such."""
    if unlimited == (limit_value is not None):
        raise InvalidRequest("entitlement_needs_a_limit_or_unlimited")
    with tenant_scope(pool, tenant_id) as conn:
        live = _live_subscription(conn)
        conn.execute(
            """
            INSERT INTO plt01.bil_entitlements
                (tenant_id, subscription_id, feature_code, limit_value, unlimited, source)
            VALUES (%s, %s, %s, %s, %s, 'grant')
            ON CONFLICT (tenant_id, subscription_id, feature_code) DO UPDATE
            SET limit_value = EXCLUDED.limit_value, unlimited = EXCLUDED.unlimited,
                source = 'grant', version = plt01.bil_entitlements.version + 1
            """,
            (tenant_id, live["subscription_id"], feature_code, limit_value, unlimited),
        )
    return {"feature_code": feature_code, "limit_value": limit_value, "unlimited": unlimited,
            "source": "grant"}


def list_entitlements(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT feature_code, limit_value, unlimited, source, version"
            " FROM plt01.bil_entitlements ORDER BY feature_code"
        ).fetchall()
    return [
        {"feature_code": r[0], "limit_value": int(r[1]) if r[1] is not None else None,
         "unlimited": bool(r[2]), "source": r[3], "version": int(r[4])} for r in rows
    ]


def check_entitlement(
    pool: Pool, tenant_id: str, *, feature_code: str, quantity: int
) -> dict[str, Any]:
    """Whether a quantity is within the tenant's entitlement. An unknown feature is not granted."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT limit_value, unlimited FROM plt01.bil_entitlements WHERE feature_code = %s",
            (feature_code,),
        ).fetchone()
    if row is None:
        return {"feature_code": feature_code, "permitted": False, "limit_value": 0,
                "unlimited": False, "reason": "not_entitled"}
    limit = sub.EntitlementLimit(feature_code, int(row[0]) if row[0] is not None else None,
                                 bool(row[1]))
    return {"feature_code": feature_code, "permitted": limit.permits(quantity),
            "limit_value": limit.limit_value, "unlimited": limit.unlimited,
            "reason": "within_limit" if limit.permits(quantity) else "over_limit"}


# --------------------------------------------------------------------------- metering

def define_meter(
    pool: Pool, tenant_id: str, *, meter_code: str, unit: str, aggregation: str = use.SUM
) -> dict[str, Any]:
    if aggregation not in use.AGGREGATIONS:
        raise InvalidRequest("bad_aggregation")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO plt01.bil_usage_meters (tenant_id, meter_code, unit, aggregation)"
                " VALUES (%s, %s, %s, %s) RETURNING meter_id",
                (tenant_id, meter_code, unit, aggregation),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("meter_exists") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_meter_code") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        assert row is not None
    return {"meter_id": str(row[0]), "meter_code": meter_code, "unit": unit,
            "aggregation": aggregation}


def _meter(conn: Connection[Any], meter_code: str) -> tuple[Any, str]:
    row = conn.execute(
        "SELECT meter_id, aggregation FROM plt01.bil_usage_meters WHERE meter_code = %s",
        (meter_code,),
    ).fetchone()
    if row is None:
        raise NotFound("meter_not_found")
    return row[0], str(row[1])


def set_quota(
    pool: Pool, tenant_id: str, *, meter_code: str, period: str, limit_quantity: int,
    overage_allowed: bool = False, hard_stop: bool = False,
) -> dict[str, Any]:
    if overage_allowed and hard_stop:
        raise InvalidRequest("quota_cannot_both_bill_and_stop")
    with tenant_scope(pool, tenant_id) as conn:
        meter_id, _ = _meter(conn, meter_code)
        try:
            conn.execute(
                """
                INSERT INTO plt01.bil_quotas
                    (tenant_id, meter_id, period, limit_quantity, overage_allowed, hard_stop)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, meter_id, period) DO UPDATE
                SET limit_quantity = EXCLUDED.limit_quantity,
                    overage_allowed = EXCLUDED.overage_allowed,
                    hard_stop = EXCLUDED.hard_stop,
                    version = plt01.bil_quotas.version + 1
                """,
                (tenant_id, meter_id, period, limit_quantity, overage_allowed, hard_stop),
            )
        except errors.CheckViolation:
            raise InvalidRequest("bad_quota") from None
    return {"meter_code": meter_code, "period": period, "limit_quantity": limit_quantity,
            "overage_allowed": overage_allowed, "hard_stop": hard_stop}


def record_usage(
    pool: Pool,
    tenant_id: str,
    *,
    meter_code: str,
    quantity: int,
    idempotency_key: str,
    actor_id: str,
    correlation_id: str,
    occurred_at: datetime | None = None,
    corrects_record_id: str | None = None,
) -> dict[str, Any]:
    """RecordUsage (PLT-03-R04), idempotent on the key the emitter supplies.

    A replay returns the record that is already stored rather than an error: the emitter did
    nothing wrong, and making a retry fail would push every caller into writing its own
    deduplication. A key reused for a *different* quantity is still a replay by this definition --
    the key is the emitter's claim that this is the same event, and the stored row wins.
    """
    when = occurred_at or datetime.now(UTC)
    with tenant_scope(pool, tenant_id) as conn:
        meter_id, _ = _meter(conn, meter_code)
        existing = conn.execute(
            "SELECT record_id, quantity, occurred_at FROM plt01.bil_usage_records"
            " WHERE meter_id = %s AND idempotency_key = %s",
            (meter_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            return {"record_id": str(existing[0]), "meter_code": meter_code,
                    "quantity": int(existing[1]), "occurred_at": existing[2].isoformat(),
                    "recorded": False}
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bil_usage_records
                    (tenant_id, meter_id, idempotency_key, quantity, occurred_at,
                     corrects_record_id, actor_id, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING record_id
                """,
                (tenant_id, meter_id, idempotency_key, quantity, when, corrects_record_id,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation:
            raise InvalidRequest("negative_quantity_needs_a_correction_target") from None
        except errors.UniqueViolation:
            raise Conflict("usage_race") from None
        except errors.ForeignKeyViolation:
            raise NotFound("corrected_record_not_found") from None
        assert row is not None
    return {"record_id": str(row[0]), "meter_code": meter_code, "quantity": quantity,
            "occurred_at": when.isoformat(), "recorded": True}


def _usage_records(conn: Connection[Any], meter_id: Any) -> list[use.UsageRecord]:
    rows = conn.execute(
        "SELECT record_id, quantity, occurred_at, corrects_record_id"
        " FROM plt01.bil_usage_records WHERE meter_id = %s",
        (meter_id,),
    ).fetchall()
    return [
        use.UsageRecord(record_id=str(r[0]), quantity=int(r[1]), occurred_at=r[2],
                        corrects_record_id=str(r[3]) if r[3] else None)
        for r in rows
    ]


def _quota_for(conn: Connection[Any], meter_id: Any, period: str) -> use.Quota | None:
    row = conn.execute(
        "SELECT limit_quantity, overage_allowed, hard_stop FROM plt01.bil_quotas"
        " WHERE meter_id = %s AND period = %s",
        (meter_id, period),
    ).fetchone()
    if row is None:
        return None
    return use.Quota(limit_quantity=int(row[0]), overage_allowed=bool(row[1]),
                     hard_stop=bool(row[2]))


def usage_summary(
    pool: Pool, tenant_id: str, *, meter_code: str,
    start: datetime | None = None, end: datetime | None = None,
) -> dict[str, Any]:
    """Usage over a window with the quota position. Defaults to the current billing period."""
    with tenant_scope(pool, tenant_id) as conn:
        meter_id, aggregation = _meter(conn, meter_code)
        if start is None or end is None:
            live = _live_subscription(conn)
            start = datetime.combine(live["period_start"], datetime.min.time(), tzinfo=UTC)
            end = datetime.combine(live["period_end"], datetime.min.time(), tzinfo=UTC)
        used = use.aggregate(_usage_records(conn, meter_id), start=start, end=end,
                             aggregation=aggregation)
        quota = _quota_for(conn, meter_id, "billing_period")
    status = use.quota_status(used, quota)
    return {
        "meter_code": meter_code, "aggregation": aggregation,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "used": status.used, "limit": status.limit, "remaining": status.remaining,
        "exceeded": status.exceeded, "overage_quantity": status.overage_quantity,
        "permitted": status.permitted,
    }


# --------------------------------------------------------------------------- invoices

def _overage_lines(
    conn: Connection[Any], terms: dict[str, Any], period_start: date, period_end: date
) -> list[dict[str, Any]]:
    """One line per metered price whose quota was exceeded and whose quota allows billing."""
    start = datetime.combine(period_start, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(period_end, datetime.min.time(), tzinfo=UTC)
    lines = []
    for price in terms.get("prices", []):
        if price["kind"] != "overage" or not price.get("meter_code"):
            continue
        row = conn.execute(
            "SELECT meter_id, aggregation FROM plt01.bil_usage_meters WHERE meter_code = %s",
            (price["meter_code"],),
        ).fetchone()
        if row is None:
            continue
        meter_id, aggregation = row[0], str(row[1])
        used = use.aggregate(_usage_records(conn, meter_id), start=start, end=end,
                             aggregation=aggregation)
        quota = _quota_for(conn, meter_id, "billing_period")
        if quota is None:
            # The plan prices overage but no quota says where it begins; the included quantity on
            # the price is the next best statement of that line, and zero means everything bills.
            quota = use.Quota(limit_quantity=int(price.get("included_quantity", 0)),
                              overage_allowed=True)
        status = use.quota_status(used, quota)
        amount = use.overage_charge(status, quota, int(price["unit_price_minor"]))
        if amount:
            unit = price["unit"] or ""
            lines.append({
                "kind": "overage",
                "description": f"{price['meter_code']} over {status.limit} {unit}".strip(),
                "quantity": status.overage_quantity,
                "unit_price_minor": int(price["unit_price_minor"]),
                "amount_minor": amount,
                "meter_code": price["meter_code"],
            })
    return lines


def issue_invoice(
    pool: Pool,
    tenant_id: str,
    *,
    actor_id: str,
    correlation_id: str,
    tax_rate_bp: int | None = None,
) -> dict[str, Any]:
    """Issue the invoice for the current period and roll the subscription forward (R06).

    An invoice has no draft state: the row appears only when it is issued, and the ledger tables
    carry no UPDATE grant, so what is written here is final. A correction is a credit note.

    The lines are the base charge for a billable period, any metered overage, and the proration
    of every plan change whose effective date falls inside the period. Periods roll forward
    without overlapping, so each change contributes to exactly one invoice without needing a flag
    on the change row to say it has been billed.
    """
    with tenant_scope(pool, tenant_id) as conn:
        live = _live_subscription(conn, lock=True)
        if not sub.is_billable(live["status"]):
            raise Conflict("not_billable_in_this_status")

        terms = live["terms"]
        period_start, period_end = live["period_start"], live["period_end"]
        lines: list[dict[str, Any]] = [{
            "kind": "base",
            "description": f"{terms['plan_code']} {terms['billing_interval']}",
            "quantity": 1,
            "unit_price_minor": int(terms["base_price_minor"]),
            "amount_minor": int(terms["base_price_minor"]),
            "meter_code": None,
        }]
        lines.extend(_overage_lines(conn, terms, period_start, period_end))

        prorations = conn.execute(
            "SELECT change_kind, proration_minor FROM plt01.bil_subscription_changes"
            " WHERE proration_minor <> 0 AND effective_on >= %s AND effective_on < %s"
            " ORDER BY occurred_at",
            (period_start, period_end),
        ).fetchall()
        for change_kind, amount in prorations:
            lines.append({
                "kind": "proration",
                "description": f"{change_kind} proration",
                "quantity": 1,
                "unit_price_minor": int(amount),
                "amount_minor": int(amount),
                "meter_code": None,
            })

        subtotal, tax, total = money.invoice_totals(
            [int(line["amount_minor"]) for line in lines], tax_rate_bp=tax_rate_bp
        )
        share = (money.apply_rate_bp(subtotal, live["revenue_share_bp"])
                 if live["partner_code"] else 0)

        issued = conn.execute("SELECT count(*) FROM plt01.bil_invoices").fetchone()
        assert issued is not None
        number = f"INV-{period_start.isoformat()}-{int(issued[0]) + 1:04d}"
        try:
            invoice = conn.execute(
                """
                INSERT INTO plt01.bil_invoices
                    (tenant_id, invoice_number, subscription_id, currency, period_start,
                     period_end, subtotal_minor, tax_minor, tax_rate_bp, total_minor,
                     partner_code, revenue_share_minor, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING invoice_id, issued_at
                """,
                (tenant_id, number, live["subscription_id"], live["currency"], period_start,
                 period_end, subtotal, tax, tax_rate_bp, total, live["partner_code"], share,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("invoice_number_taken") from None
        except errors.CheckViolation:
            raise InvalidRequest("invoice_does_not_balance") from None
        assert invoice is not None
        invoice_id = str(invoice[0])

        for line_no, line in enumerate(lines, start=1):
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.bil_invoice_lines
                        (tenant_id, invoice_id, line_no, kind, description, quantity,
                         unit_price_minor, amount_minor, meter_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, invoice_id, line_no, line["kind"], line["description"],
                     line["quantity"], line["unit_price_minor"], line["amount_minor"],
                     line["meter_code"]),
                )
            except errors.CheckViolation:
                raise InvalidRequest("invoice_line_does_not_multiply_out") from None

        next_start, next_end = sub.next_period(period_start, period_end)
        conn.execute(
            "UPDATE plt01.bil_subscriptions SET period_start = %s, period_end = %s,"
            " version = version + 1 WHERE subscription_id = %s",
            (next_start, next_end, live["subscription_id"]),
        )
        _record_change(
            conn, tenant_id, live["subscription_id"], change_kind="renew",
            from_status=live["status"], to_status=live["status"], effective_on=next_start,
            actor_id=actor_id, correlation_id=correlation_id,
        )
    return {
        "invoice_id": invoice_id, "invoice_number": number, "currency": live["currency"],
        "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
        "subtotal_minor": subtotal, "tax_minor": tax, "total_minor": total,
        "revenue_share_minor": share, "lines": lines,
        "issued_at": invoice[1].isoformat(),
    }


def list_invoices(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT invoice_id, invoice_number, currency, period_start, period_end,"
            " subtotal_minor, tax_minor, total_minor, partner_code, revenue_share_minor,"
            " issued_at FROM plt01.bil_invoices ORDER BY issued_at, invoice_number"
        ).fetchall()
    return [
        {"invoice_id": str(r[0]), "invoice_number": r[1], "currency": r[2],
         "period_start": r[3].isoformat(), "period_end": r[4].isoformat(),
         "subtotal_minor": int(r[5]), "tax_minor": int(r[6]), "total_minor": int(r[7]),
         "partner_code": r[8], "revenue_share_minor": int(r[9]),
         "issued_at": r[10].isoformat()} for r in rows
    ]


def get_invoice(pool: Pool, tenant_id: str, invoice_id: str) -> dict[str, Any]:
    """An invoice with its lines and credits, and the balance after those credits."""
    with tenant_scope(pool, tenant_id) as conn:
        head = conn.execute(
            "SELECT invoice_number, currency, period_start, period_end, subtotal_minor,"
            " tax_minor, total_minor, issued_at FROM plt01.bil_invoices WHERE invoice_id = %s",
            (invoice_id,),
        ).fetchone()
        if head is None:
            raise NotFound("invoice_not_found")
        lines = conn.execute(
            "SELECT line_no, kind, description, quantity, unit_price_minor, amount_minor,"
            " meter_code FROM plt01.bil_invoice_lines WHERE invoice_id = %s ORDER BY line_no",
            (invoice_id,),
        ).fetchall()
        credits = conn.execute(
            "SELECT credit_note_number, amount_minor, reason, issued_at"
            " FROM plt01.bil_credit_notes WHERE invoice_id = %s ORDER BY issued_at",
            (invoice_id,),
        ).fetchall()
    credited = sum(int(c[1]) for c in credits)
    return {
        "invoice_id": invoice_id, "invoice_number": head[0], "currency": head[1],
        "period_start": head[2].isoformat(), "period_end": head[3].isoformat(),
        "subtotal_minor": int(head[4]), "tax_minor": int(head[5]),
        "total_minor": int(head[6]), "issued_at": head[7].isoformat(),
        "credited_minor": credited, "balance_minor": int(head[6]) - credited,
        "lines": [
            {"line_no": int(line[0]), "kind": line[1], "description": line[2],
             "quantity": int(line[3]), "unit_price_minor": int(line[4]),
             "amount_minor": int(line[5]), "meter_code": line[6]} for line in lines
        ],
        "credit_notes": [
            {"credit_note_number": c[0], "amount_minor": int(c[1]), "reason": c[2],
             "issued_at": c[3].isoformat()} for c in credits
        ],
    }


def issue_credit_note(
    pool: Pool, tenant_id: str, *, invoice_id: str, amount_minor: int, reason: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Credit an issued invoice. The only way to reduce what was charged.

    The total credited can never exceed the invoice, which is checked here against the credits
    already recorded. Over-crediting would turn an invoice into a payable, and this module has no
    concept of paying a tenant.
    """
    if amount_minor <= 0:
        raise InvalidRequest("credit_must_be_positive")
    if not reason.strip():
        raise InvalidRequest("credit_needs_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT total_minor FROM plt01.bil_invoices WHERE invoice_id = %s", (invoice_id,)
        ).fetchone()
        if row is None:
            raise NotFound("invoice_not_found")
        already = conn.execute(
            "SELECT coalesce(sum(amount_minor), 0) FROM plt01.bil_credit_notes"
            " WHERE invoice_id = %s",
            (invoice_id,),
        ).fetchone()
        assert already is not None
        if int(already[0]) + amount_minor > int(row[0]):
            raise Conflict("credit_exceeds_invoice")
        issued = conn.execute("SELECT count(*) FROM plt01.bil_credit_notes").fetchone()
        assert issued is not None
        number = f"CN-{int(issued[0]) + 1:04d}"
        try:
            note = conn.execute(
                """
                INSERT INTO plt01.bil_credit_notes
                    (tenant_id, credit_note_number, invoice_id, amount_minor, reason,
                     actor_id, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING credit_note_id, issued_at
                """,
                (tenant_id, number, invoice_id, amount_minor, reason, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("credit_note_number_taken") from None
        assert note is not None
    return {"credit_note_id": str(note[0]), "credit_note_number": number,
            "invoice_id": invoice_id, "amount_minor": amount_minor, "reason": reason,
            "issued_at": note[1].isoformat()}
