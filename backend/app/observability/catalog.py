"""MOD-011 REL-02: the metric catalogue, and what a dimension is allowed to carry.

**Metrics are declared in code**, as permissions are in MOD-008 and event types in MOD-010, and
for the same reason: a metric is a fact about what the software measures, so a per-tenant
registry would let two tenants disagree about what `authz.denials` counts with only the emitting
code able to settle it. A dashboard written against one tenant's idea of a series would be
quietly wrong against another's.

**A dimension is a label, never a payload.** TSD paragraph 3508 states the control as
"observability data is redacted and access-controlled; logs are not a shadow database", and the
mechanism here is narrow and checkable: a metric declares the dimension names it carries, every
emitted point is validated against that list, and a declared dimension may not be a field MOD-008
classifies as restricted. Metric points are the easiest place in a system to accumulate a second
copy of the data nobody audits, which is exactly what "not a shadow database" forbids.

**Cardinality is declared, not discovered.** Every dimension names the values it may take, or
says `unbounded` and takes a documented reason. An unbounded dimension on a counter is how a
metrics store turns into one row per subject -- the shadow database again, arriving by accident
rather than by design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.authorization.catalog import SENSITIVE_FIELDS
from app.privacy.classification import KIND_CLASS, PURPOSE_REQUIRED_AT

METRIC_KEY = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$", re.ASCII)
DIMENSION_NAME = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$", re.ASCII)

#: `counter` accumulates and is read as a sum or a rate. `duration_ms` is a count of
#: observations plus a total, so a mean is
#: available without storing a histogram -- which is the honest limit of what a relational store
#: should be asked to do here, and it is stated rather than implied: **there are no
#: percentiles.** A performance budget expressed as a p95 cannot be evaluated from these points,
#: and `objectives.py` refuses to pretend otherwise. `ratio` is the same two columns read as
#: successes over trials, which is the one shape that makes an availability SLO expressible --
#: TSD paragraph 3516 asks for 99.9%, and a success ratio is what that compares against.
#:
#: **There is no `gauge`.** One was declared and nothing used it, and it could not have worked:
#: `observe_in` accumulates with `total = total + EXCLUDED.total`, so a second level written in
#: the same hour yields the *sum* of the two levels and `last` returns that sum. A kind whose
#: documented contract the storage cannot honour is worse than an absent one, because the first
#: metric to use it would be silently wrong rather than refused. Adding it back means making the
#: upsert replace rather than add for that kind.
KINDS = ("counter", "duration_ms", "ratio")


class CatalogError(ValueError):
    """A metric, dimension or point this build does not define."""


@dataclass(frozen=True)
class Dimension:
    name: str
    values: tuple[str, ...] = ()
    """The closed set this dimension may take. Empty means unbounded, which needs `reason`."""
    reason: str = ""
    """Why an unbounded dimension is acceptable here. Required when `values` is empty."""

    @property
    def unbounded(self) -> bool:
        return not self.values


@dataclass(frozen=True)
class Metric:
    key: str
    kind: str
    unit: str
    owner_module: str
    description: str
    dimensions: tuple[Dimension, ...] = field(default_factory=tuple)

    @property
    def dimension_names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.dimensions)


def _d(name: str, *values: str, reason: str = "") -> Dimension:
    if not DIMENSION_NAME.fullmatch(name):
        raise CatalogError(f"{name!r} is not a dimension name")
    kind = SENSITIVE_FIELDS.get(name)
    if kind is not None and KIND_CLASS.get(kind) == PURPOSE_REQUIRED_AT:
        raise CatalogError(
            f"{name!r} is {kind} data and must not be a metric dimension; a metric store is the "
            f"easiest place in a system to accumulate a copy of the data nobody audits"
        )
    if not values and not reason:
        raise CatalogError(
            f"{name!r} declares no values and no reason; an unbounded dimension is how a "
            f"metrics store becomes one row per subject, so it has to be argued for"
        )
    if len(set(values)) != len(values):
        raise CatalogError(f"{name!r} declares a value twice")
    return Dimension(name=name, values=tuple(values), reason=reason)


def _m(key: str, kind: str, unit: str, owner_module: str, description: str,
       *dimensions: Dimension) -> tuple[str, Metric]:
    if not METRIC_KEY.fullmatch(key):
        raise CatalogError(f"{key!r} is not a dotted metric key")
    if kind not in KINDS:
        raise CatalogError(f"{kind!r} is not a metric kind")
    if not unit.strip():
        raise CatalogError(f"{key!r} declares no unit")
    names = [d.name for d in dimensions]
    if len(set(names)) != len(names):
        raise CatalogError(f"{key!r} declares a dimension twice")
    return key, Metric(key=key, kind=kind, unit=unit, owner_module=owner_module,
                       description=description, dimensions=tuple(dimensions))


#: Every metric this build emits. Short on purpose, and shorter than the first draft of it.
#:
#: **A metric that duplicates a table is a second copy of the truth that can disagree with it.**
#: The first version of this catalogue carried `events.outbox_pending`, `events.dead_letters`,
#: `privacy.dsar_open` and `privacy.dsar_overdue`. Every one of those is a count over a table
#: that already exists, under a role that can already read it, and storing it here would mean a
#: dashboard and a `SELECT count(*)` could answer the same question differently -- with nothing
#: able to say which was right. That is "logs are not a shadow database" (paragraph 3503) applied
#: to the metric store itself, and it is the reason this list is five entries rather than nine.
#:
#: What is left is what has no table of its own: how long work took, and how often it succeeded.
#: Each has a producer in this change, because a metric nothing emits is a series that reads as a
#: measurement and is always zero -- worse than an absent panel, since a zero looks like an answer.
METRICS: dict[str, Metric] = dict([
    # ---------------------------------------------------------------- MOD-008, the gate
    # **Denials only, and allows deliberately not.** Counting every allow means an upsert on one
    # row for every request that reaches a gated route, which both contends on that row and
    # couples the availability of every product route to the availability of the metric store --
    # observability taking the product down is the wrong trade for a chart. A denial is rare, it
    # already costs an audit write, and a spike in one is the signal somebody actually alerts on.
    # The consequence, stated rather than discovered: there is no denominator here, so this
    # series is a count and not a rate, and an objective expressed as "denials under 1% of
    # traffic" cannot be evaluated in this build.
    _m("authz.denials", "counter", "denial", "MOD-008",
       "Requests refused at the gate, by the category of the permission asked for",
       _d("category", "authentication", "data_access", "configuration", "finance", "access",
          "ai", "support")),
    # ---------------------------------------------------------------- MOD-010, the event plane
    _m("events.delivery_duration", "duration_ms", "millisecond", "MOD-010",
       "How long a consumer took to handle one delivery",
       _d("consumer", reason="a consumer name is tenant-chosen, so the set is not closeable; "
                             "it is bounded in practice by the subscription table")),
    _m("events.delivery_success", "ratio", "delivery", "MOD-010",
       "Deliveries handled without error, over deliveries attempted",
       _d("consumer", reason="as above; the same subscription table bounds it")),
    # ---------------------------------------------------------------- MOD-011, itself
    # The SLI paragraph 3496 asks for. The probe ledger holds each run; this holds the hourly
    # ratio an availability objective is evaluated against, which is a rollup of that ledger
    # rather than a second copy of it -- the distinction being that no question is answerable
    # from both.
    _m("ops.synthetic_success", "ratio", "run", "MOD-011",
       "Synthetic probe runs that passed, over runs attempted",
       _d("check_key", reason="tenant-defined; the check registry bounds it")),
    _m("ops.synthetic_latency", "duration_ms", "millisecond", "MOD-011",
       "How long a synthetic probe took",
       _d("check_key", reason="tenant-defined; the check registry bounds it")),
])


def validate_point(key: str, *, observations: int, total: float) -> None:
    """Refuse a point whose numbers cannot mean what its kind says they mean.

    The `ratio` case is the one that bites: a ratio is successes over trials, so a total above
    the observation count is not a high ratio -- it is a producer that passed a duration or a
    sum into the wrong metric, and the series it produces would read as 340% availability.
    """
    metric = require_metric(key)
    if observations <= 0:
        raise CatalogError(f"{key!r} needs a positive observation count")
    if metric.kind == "ratio" and not 0 <= total <= observations:
        raise CatalogError(
            f"{key!r} is a ratio, so its total is a count of successes between 0 and "
            f"{observations}; {total} is not"
        )
    if metric.kind == "duration_ms" and total < 0:
        raise CatalogError(f"{key!r} is a duration and cannot total less than zero")


def require_metric(key: str) -> Metric:
    """Look a metric up, refusing one this build does not define.

    An unknown metric key cannot be recorded. A typo in a producer therefore fails where it is
    written rather than creating a second series that looks like the first and disagrees with it
    -- which is the failure that makes a dashboard untrustworthy without ever looking broken.
    """
    try:
        return METRICS[key]
    except KeyError:
        raise CatalogError(f"{key!r} is not a metric this build defines") from None


def validate_dimensions(key: str, dimensions: dict[str, str]) -> None:
    """Refuse a point whose labels are not exactly the declared dimensions, with legal values.

    Both directions, as MOD-010 does for payloads. A missing dimension makes two points that
    should be distinguishable aggregate together; an extra one is a label nobody declared,
    travelling into every query and every retention decision made about this table.
    """
    metric = require_metric(key)
    supplied = set(dimensions)
    declared = set(metric.dimension_names)
    if supplied - declared:
        raise CatalogError(f"{key!r} does not declare {sorted(supplied - declared)}")
    if declared - supplied:
        raise CatalogError(f"{key!r} requires {sorted(declared - supplied)}")
    for dimension in metric.dimensions:
        value = dimensions[dimension.name]
        if not value.strip():
            raise CatalogError(f"{key!r} dimension {dimension.name!r} is blank")
        if not dimension.unbounded and value not in dimension.values:
            raise CatalogError(
                f"{key!r} dimension {dimension.name!r} does not take {value!r}; "
                f"declared values are {sorted(dimension.values)}"
            )


def unbounded_dimensions() -> tuple[tuple[str, Dimension], ...]:
    """Every dimension whose values are not a closed set, with the argument for it.

    The cardinality risk in one read. A dashboard that is slow, or a table that is larger than
    anybody expected, starts here.
    """
    return tuple((metric.key, d) for metric in METRICS.values()
                 for d in metric.dimensions if d.unbounded)


def metrics_of(owner_module: str) -> tuple[Metric, ...]:
    return tuple(m for m in METRICS.values() if m.owner_module == owner_module)
