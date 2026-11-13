"""MOD-006 PLT-03-R04: usage aggregation, late events, corrections, quotas and overage.

Pure functions over records the caller has already read. The database holds the control PLT-03
states -- records are idempotent, attributable and append-only, enforced by a unique key, two
NOT NULL columns and the absence of an UPDATE grant. What is decided here is what those records
*mean* when a period is billed.

**A correction adjusts the record it corrects. It is not a data point of its own.** That single
rule is what makes late corrections behave under all three aggregations:

* under `sum`, adjusting the target and summing is the same as summing the correction separately,
  so the obvious case stays obvious;
* under `max` and `last` it is the only reading that works at all. A correction saying "that peak
  of 900 was really 400" must lower the peak. Treating the correction as its own reading of -500
  would instead introduce a new minimum and leave the wrong peak standing.

The adjustment lands in the period the **corrected** record happened in, not the period the
correction arrived in. A correction to March filed in April belongs to March; that is what makes
it a correction rather than a new charge, and it is why `occurred_at` and `recorded_at` are
separate columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SUM = "sum"
MAX = "max"
LAST = "last"
AGGREGATIONS = (SUM, MAX, LAST)


class UsageError(ValueError):
    """An aggregation that does not exist, or a correction with no target."""


@dataclass(frozen=True)
class UsageRecord:
    record_id: str
    quantity: int
    occurred_at: datetime
    corrects_record_id: str | None = None


@dataclass(frozen=True)
class Quota:
    limit_quantity: int
    overage_allowed: bool = False
    hard_stop: bool = False


@dataclass(frozen=True)
class QuotaStatus:
    used: int
    limit: int
    remaining: int
    exceeded: bool
    overage_quantity: int
    permitted: bool
    """False only when the quota is exceeded and the quota says to stop rather than to bill."""


def effective_quantities(records: list[UsageRecord]) -> dict[str, tuple[int, datetime]]:
    """Fold corrections into the records they correct.

    Returns originals only, each with its adjusted quantity and its own `occurred_at`. A
    correction whose target is not in `records` is ignored rather than counted on its own: its
    target is outside the window the caller asked for, so applying it here would move usage
    between periods.
    """
    effective: dict[str, tuple[int, datetime]] = {
        record.record_id: (record.quantity, record.occurred_at)
        for record in records
        if record.corrects_record_id is None
    }
    for record in records:
        target = record.corrects_record_id
        if target is not None and target in effective:
            quantity, when = effective[target]
            effective[target] = (quantity + record.quantity, when)
    return effective


def aggregate(
    records: list[UsageRecord], *, start: datetime, end: datetime, aggregation: str = SUM
) -> int:
    """Aggregate usage over [start, end) by `occurred_at`, so late events land in their period."""
    if aggregation not in AGGREGATIONS:
        raise UsageError(f"{aggregation!r} is not a known aggregation")

    # Corrections are folded over every record handed in, then the window is applied: a
    # correction and its target may well have arrived in different calls to the recorder.
    folded = effective_quantities(records)
    in_window = [(when, quantity) for quantity, when in folded.values() if start <= when < end]
    if not in_window:
        return 0
    if aggregation == SUM:
        return sum(quantity for _, quantity in in_window)
    if aggregation == MAX:
        return max(quantity for _, quantity in in_window)
    return max(in_window, key=lambda pair: pair[0])[1]


def quota_status(used: int, quota: Quota | None) -> QuotaStatus:
    """Where a tenant stands against a quota, and whether the next call is permitted.

    With no quota configured, usage is unlimited and permitted -- an absent limit is not a limit
    of zero. PLT-03's outcome is that "tenants understand limits before reaching them", so
    `remaining` is reported even when the quota is not yet exceeded, and it never goes negative:
    the amount over is `overage_quantity`, which is a different number with a different meaning.
    """
    if quota is None:
        return QuotaStatus(used=used, limit=-1, remaining=-1, exceeded=False,
                           overage_quantity=0, permitted=True)
    over = max(0, used - quota.limit_quantity)
    exceeded = over > 0
    return QuotaStatus(
        used=used,
        limit=quota.limit_quantity,
        remaining=max(0, quota.limit_quantity - used),
        exceeded=exceeded,
        overage_quantity=over,
        permitted=not (exceeded and quota.hard_stop),
    )


def overage_charge(status: QuotaStatus, quota: Quota | None, unit_price_minor: int) -> int:
    """What the overage costs. Nothing unless the quota actually allows billing for it.

    A quota with neither `overage_allowed` nor `hard_stop` is a warning threshold: the tenant is
    told, the call goes through, and nobody is charged for crossing a line that was not priced.
    Charging there would be billing for a limit the plan never sold.
    """
    if quota is None or not quota.overage_allowed or not status.exceeded:
        return 0
    if unit_price_minor < 0:
        raise UsageError("overage price must not be negative")
    return status.overage_quantity * unit_price_minor
