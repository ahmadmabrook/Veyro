"""MOD-017 reporting windows: the arithmetic behind a month-to-date figure and its comparison.

ADM-CC-01 states four metrics and two charts, and three of them are not a `sum()` over a
month -- they are a span, a *comparable* span, and a projection, each of which can be wrong in
a way nobody checks:

    COLLECTED · MONTH TO DATE
    JOD 41,280.00   ↓ 7.8%   vs July · pace to 63.1k

So the decisions live here, with no I/O, and `service.py` runs the sums the spans describe.
Three of them are worth stating before the code:

* **"vs July" is the same *point* in July, not the whole of it.** The design's own figure says
  so -- "Collections are JOD 3,490 below the same point in July -- 41,280 against 44,770" --
  and comparing nineteen days against thirty-one would report a collapse on the 19th of every
  month. MOD-011 shipped the one-sided version of exactly this: `evaluate_budget` bounded spend
  with `period_start >= %s` and nothing above it, and a monthly budget 45% consumed reported
  143%.

* **A projection is labelled a projection, and its basis is stated.** `pace` is what the month
  reaches if the rest of it looks like the part that has happened -- a different kind of
  statement from the 41,280 beside it. It is returned under its own name and the response says
  so; a figure a manager could quote as collections is the one thing this must not produce.
  **The design gives no formula.** It renders "pace to 63.1k" against 41,280 at the 19th of a
  31-day month, and a straight-line projection gives 67,348, so the drawn figure comes from a
  basis no document in the folder states. Straight-line is what is implemented, the response
  names it, and the discrepancy is recorded as an unresolved design requirement rather than
  reverse-engineered from one illustrative number.

* **A partial bucket is marked, never extrapolated.** "The last bar is a partial week and is
  marked, not extrapolated." A chart that scaled the final bar up to a notional full week would
  put a number on the screen that no payment produced.

**Week start is a market token, not a default.** The component source says "Week starts
Saturday -- a market setting, not a default", so it is a parameter here. Nothing in MOD-005's
configuration registry declares the key yet, so the caller passes it and the default is the
market the design is drawn for.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

from app.billing import money

#: Saturday, in `date.weekday()` terms where Monday is 0. The market the design is drawn for.
SATURDAY = 5

#: The most weekly buckets a chart read will produce. Twelve is what the design draws; the
#: bound exists because the span is caller-supplied and a chart is not a bulk export.
MAX_WEEKS = 52


@dataclass(frozen=True)
class Span:
    """An inclusive date range. Both ends are dates, because a collections figure is daily."""

    first: date
    last: date

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1


def month_to_date(as_of: date) -> Span:
    """The first of `as_of`'s month through `as_of` itself."""
    return Span(as_of.replace(day=1), as_of)


def comparable_previous_month(as_of: date) -> Span:
    """The same number of days into the previous month, which is what "vs July" means.

    **Clamped to the previous month's own length**, which is the case that makes this a
    function rather than a subtraction: the 31st of March has no counterpart in February, so
    the comparison runs to the 28th and the span is three days shorter. Reporting the whole of
    February against 31 days of March would be the one-sided comparison this module exists to
    avoid, in the other direction.
    """
    first_of_this = as_of.replace(day=1)
    last_of_previous = first_of_this - timedelta(days=1)
    first_of_previous = last_of_previous.replace(day=1)
    through = min(as_of.day, last_of_previous.day)
    return Span(first_of_previous, first_of_previous.replace(day=through))


def change_bp(now_minor: int, before_minor: int) -> int | None:
    """The change from `before` to `now`, in basis points. `None` when there is no baseline.

    Basis points rather than a float, for MOD-015's reason: every figure in this build is an
    integer and a percentage rendered from a float is the second rounding rule MOD-016 shipped
    and a reviewer found. A caller renders this as a percentage by dividing by 100.

    **`None` is not zero.** A month with no collections behind it cannot say whether this one
    is up or down, and `0` would read as "unchanged" -- which is the confident wrong answer.
    """
    if before_minor == 0:
        return None
    return money.round_half_up((now_minor - before_minor) * 10_000, before_minor)


def pace(collected_minor: int, as_of: date) -> int:
    """What the month reaches if the remainder looks like the part that has happened.

    A projection, returned under its own name. The caller is responsible for saying so; this
    function will not produce a figure that reads as money already collected.
    """
    span = month_to_date(as_of)
    days_in_month = monthrange(as_of.year, as_of.month)[1]
    return money.round_half_up(collected_minor * days_in_month, span.days)


def week_buckets(as_of: date, weeks: int, *, week_start: int = SATURDAY) -> list[Span]:
    """`weeks` consecutive week-long spans ending with the one containing `as_of`, oldest first.

    The last is partial whenever `as_of` is not its final day, which `is_partial` answers
    rather than the caller deriving it from two dates -- MOD-018's `admits_trade` rule, where
    the implication is the fact.
    """
    if weeks < 1 or weeks > MAX_WEEKS:
        raise ValueError("bad_weeks")
    if week_start < 0 or week_start > 6:
        raise ValueError("bad_week_start")
    # How far back the current week began. `weekday()` is Monday-0; this is the offset from
    # `as_of` to the most recent `week_start`.
    into_week = (as_of.weekday() - week_start) % 7
    current_first = as_of - timedelta(days=into_week)
    return [
        Span(current_first - timedelta(days=7 * back), current_first - timedelta(days=7 * back - 6))
        for back in range(weeks - 1, -1, -1)
    ]


def is_partial(span: Span, as_of: date) -> bool:
    """Whether `as_of` falls inside `span` without reaching its end."""
    return span.first <= as_of < span.last
