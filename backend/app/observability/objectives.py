"""MOD-011 REL-02: objective evaluation and budget burn, decided without touching the database.

Three things live here: whether a series meets an objective over a window, how much of a budget
a period has consumed, and whether that crossing is one somebody should be told about.

**There are no percentiles, and this module refuses to fake one.** `ops_metric_points` stores an
observation count and a total per hourly bucket, so a mean is available and a p95 is not.
`evaluate` therefore takes an aggregate it can actually compute and `check_evaluable` refuses an
objective whose threshold is stated as a percentile -- because comparing a mean against a p95
budget produces a number that looks like a verdict, passes when it should fail, and is worse than
an empty panel. TSD paragraph 3502 does ask for percentile budgets; closing that needs a
histogram the store does not keep, and the gap is recorded rather than papered over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

COMPARISONS = ("at_least", "at_most")
KINDS = ("slo", "performance_budget")

#: Aggregates computable from (observations, total) alone.
AGGREGATES = ("sum", "rate_per_hour", "mean", "last")

#: Which aggregates are *meaningful* for each metric kind, which is a narrower question than
#: which are computable. A `ratio` holds successes over trials, so its mean is the success rate
#: and its sum is a count of successes wearing a ratio's clothes: review found
#: `kind=slo, metric=ops.synthetic_success, at_least 0.999, aggregate_as=sum` accepted and
#: stored, reading to anybody listing it as a 99.9% availability SLO -- and **met during a total
#: outage**, because one success in ten thousand attempts sums to 1.0. The catalogue already
#: knew the kind; nothing asked it. Refusing a percentile and then admitting that was stopping
#: one step short of the check that mattered.
AGGREGATES_BY_KIND: dict[str, tuple[str, ...]] = {
    "counter": ("sum", "rate_per_hour"),
    "duration_ms": ("mean",),
    "ratio": ("mean",),
}

#: How long a budget period runs, as the number of months after its start.
PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


class ObjectiveError(ValueError):
    """An objective that cannot be evaluated as stated."""


@dataclass(frozen=True)
class Bucket:
    """One hourly point of a series, as the store holds it."""

    observations: int
    total: float


@dataclass(frozen=True)
class Verdict:
    met: bool
    observed: float
    threshold: float
    comparison: str
    buckets: int
    """How many buckets the window actually had data in. Zero is not a pass."""
    reason: str


def aggregate(buckets: list[Bucket], how: str, *, window_hours: int) -> float:
    """Reduce a window of buckets to the one number an objective compares against."""
    if how not in AGGREGATES:
        raise ObjectiveError(f"unknown_aggregate_{how}")
    if window_hours <= 0:
        raise ObjectiveError("window_must_be_positive")
    if not buckets:
        raise ObjectiveError("no_data_in_window")
    total = sum(b.total for b in buckets)
    observations = sum(b.observations for b in buckets)
    if how == "sum":
        return float(total)
    if how == "rate_per_hour":
        return float(total) / window_hours
    if how == "mean":
        # Observations rather than buckets: a bucket with 1000 observations should weigh a
        # thousand times a bucket with one, and dividing by the bucket count is the mistake that
        # makes a quiet hour look as important as a busy one.
        if observations == 0:
            raise ObjectiveError("no_observations_in_window")
        return float(total) / observations
    return float(buckets[-1].total)


def check_evaluable(*, kind: str, comparison: str, aggregate_as: str,
                    metric_kind: str) -> None:
    """Refuse an objective this store cannot answer, or cannot answer *meaningfully*.

    Two refusals, and the second was missing. The percentile case is the obvious one: an
    objective asking for a p95 is a legitimate thing to want -- paragraph 3516 asks for it --
    and this store cannot produce one, so it is refused at definition time where somebody can
    see why, rather than evaluated against a mean and reported as a verdict months later.

    The second is the aggregate the metric's own kind does not support. That one is worse,
    because it produces a number rather than an error: a ratio summed instead of averaged is
    met during an outage and can never breach.
    """
    if kind not in KINDS:
        raise ObjectiveError(f"unknown_kind_{kind}")
    if comparison not in COMPARISONS:
        raise ObjectiveError(f"unknown_comparison_{comparison}")
    if aggregate_as not in AGGREGATES:
        raise ObjectiveError(
            f"{aggregate_as!r} is not computable from an observation count and a total; this "
            f"store keeps no histogram, so a percentile objective cannot be evaluated here"
        )
    allowed = AGGREGATES_BY_KIND.get(metric_kind, ())
    if aggregate_as not in allowed:
        raise ObjectiveError(
            f"a {metric_kind} metric cannot be read as {aggregate_as!r}; it is meaningful as "
            f"{' or '.join(allowed) or 'nothing this build evaluates'}"
        )


def evaluate(
    buckets: list[Bucket], *, comparison: str, threshold: float, aggregate_as: str,
    window_hours: int,
) -> Verdict:
    """Does this window meet the objective?

    **An empty window is not a pass.** A series with no data in it is either a producer that
    stopped or an objective nobody wired up, and both are things to look at; reporting "met"
    because nothing contradicted the threshold is how a dashboard goes green during an outage.
    """
    if comparison not in COMPARISONS:
        raise ObjectiveError(f"unknown_comparison_{comparison}")
    if not buckets:
        return Verdict(met=False, observed=0.0, threshold=threshold, comparison=comparison,
                       buckets=0, reason="no_data_in_window")
    observed = aggregate(buckets, aggregate_as, window_hours=window_hours)
    met = observed >= threshold if comparison == "at_least" else observed <= threshold
    return Verdict(met=met, observed=observed, threshold=threshold, comparison=comparison,
                   buckets=len(buckets), reason="met" if met else "breached")


# --------------------------------------------------------------------------------- budget burn

@dataclass(frozen=True)
class Burn:
    spent_minor: int
    budget_minor: int
    consumed_bp: int
    """Basis points of the budget consumed. 10000 is exactly the budget; above that is overspend."""
    over: bool
    crossed: tuple[int, ...]
    """Which notification thresholds this figure has passed, lowest first."""


#: Where a burn alert fires beyond the budget's own warning point. 10000 is the budget itself and
#: 12000 is twenty per cent over -- a second alert, because "you are over" and "you are well
#: over" are different conversations.
STANDARD_THRESHOLDS = (10000, 12000)


def burn(*, spent_minor: int, budget_minor: int, warn_at_bp: int) -> Burn:
    """How much of a budget a period has used, and which thresholds that crosses.

    Integer basis points throughout, because every amount in this repository is an integer in
    minor units and a float percentage would reintroduce the rounding MOD-015's conventions
    exist to avoid. The division truncates, so 7999.9 bp reads as 7999 and does not trip an
    8000 bp warning -- erring towards one alert later rather than one alert too early, which is
    the right direction for something whose failure mode is being muted.
    """
    if budget_minor <= 0:
        raise ObjectiveError("budget_must_be_positive")
    if spent_minor < 0:
        raise ObjectiveError("spend_cannot_be_negative")
    if not 1 <= warn_at_bp <= 10000:
        raise ObjectiveError("warn_at_bp_out_of_range")
    consumed = spent_minor * 10000 // budget_minor
    thresholds = tuple(sorted({warn_at_bp, *STANDARD_THRESHOLDS}))
    return Burn(
        spent_minor=spent_minor, budget_minor=budget_minor, consumed_bp=consumed,
        over=consumed > 10000,
        crossed=tuple(t for t in thresholds if consumed >= t),
    )


def alerts_to_raise(current: Burn, already_raised: set[int]) -> tuple[int, ...]:
    """Which thresholds need an alert that has not had one in this period.

    The set comes from the rows already written, not from a flag on the budget: a sweep that ran
    twice in an hour must not raise the same alert twice, and the unique index on
    `ops_budget_alerts` is the backstop if this is ever wrong. An alert channel that repeats
    itself is one people mute, and a muted alert is worse than none.
    """
    return tuple(t for t in current.crossed if t not in already_raised)


def budget_window(period: str, period_start: date) -> tuple[date, date]:
    """The half-open window a budget period covers, derived from the budget's own `period`.

    **Returned rather than accepted, because a period with only a start is not a period.** The
    first version of `evaluate_budget` bounded spend with `period_start >= %s` and nothing
    above it, and took that date from the caller. A monthly budget 45% consumed in January then
    reported 143% -- the sum of the whole year -- published three anomaly events, and wrote
    three insert-only alert rows snapshotting a figure that was never anybody's January spend.
    `ops_budgets.period` was written by `set_budget` and read by nothing.

    The start is checked for alignment too. A misaligned start is a window that overlaps two
    periods, and since the alert rows are unique per `(budget, period_start, threshold)`, a
    sweep passing an unaligned or moving date raises every threshold again on every run -- each
    time with a bigger number, because the lower bound moves while the sum keeps growing.
    """
    months = PERIOD_MONTHS.get(period)
    if months is None:
        raise ObjectiveError(f"unknown_budget_period_{period}")
    if period_start.day != 1:
        raise ObjectiveError("period_start_must_be_the_first_of_a_month")
    if months == 3 and period_start.month not in (1, 4, 7, 10):
        raise ObjectiveError("a_quarter_starts_in_january_april_july_or_october")
    if months == 12 and period_start.month != 1:
        raise ObjectiveError("a_year_starts_in_january")
    end_month = period_start.month - 1 + months
    return period_start, date(period_start.year + end_month // 12, end_month % 12 + 1, 1)


def margin_bp(*, revenue_minor: int, cost_minor: int) -> int:
    """Gross margin in basis points, which is what paragraph 3512 asks to stay visible.

    Refuses zero revenue rather than returning zero: a margin on no revenue is undefined, and
    reporting 0 bp would read as "we break even" when the truth is "there is nothing to measure".
    Negative margin is a real answer and is returned as one.
    """
    if revenue_minor <= 0:
        raise ObjectiveError("margin_needs_revenue")
    if cost_minor < 0:
        raise ObjectiveError("cost_cannot_be_negative")
    return (revenue_minor - cost_minor) * 10000 // revenue_minor
