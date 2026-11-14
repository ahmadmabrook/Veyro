"""Revenue recognition: why prepaid cash is not day-one revenue.

Paragraph 1695 is the whole of this module in one sentence: "Unearned revenue and
RevenueRecognitionSchedule prevent prepaid membership cash from becoming day-one revenue."

**A member who pays for a year in January has not given the tenant a year's revenue in
January.** They have given it cash and taken on a claim: eleven months of service the tenant
still owes. Posting the whole amount as revenue on the day makes January look like the best
month the business ever had and every month after it look like a collapse, and it overstates
the tax owed on a period in which the service was not delivered. So the cash lands in
`unearned_revenue`, a liability, and a schedule moves it to `revenue` as the service is
delivered.

**Two bases, because two things are being sold.** A term membership earns by *time* -- a day of
access delivered is a day of revenue earned, whether or not the member turned up. A class pack
earns by *delivery* -- ten classes bought earn nothing until a class is taken, because an
unused class is still owed. Charging time against a class pack would recognise revenue for
sessions the member can still demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.billing import money
from app.ledger.accounts import LedgerError

#: How a schedule earns. `straight_line` is by day over a period; `on_delivery` is per unit
#: consumed; `immediate` is for what is earned when it is sold -- a joining fee, a retail sale.
BASES: tuple[str, ...] = ("straight_line", "on_delivery", "immediate")


@dataclass(frozen=True)
class Schedule:
    """One recognition schedule, as the decisions need it."""

    basis: str
    total_minor: int
    currency: str
    #: For `straight_line`. Inclusive at both ends, like every other period in this build.
    starts_on: date | None = None
    ends_on: date | None = None
    #: For `on_delivery`. How many units the money bought.
    units_total: int | None = None


def check_schedule(schedule: Schedule) -> None:
    """Refuse a schedule that cannot be earned."""
    if schedule.basis not in BASES:
        raise LedgerError(f"{schedule.basis!r} is not a recognition basis")
    if schedule.total_minor <= 0:
        raise LedgerError("a recognition schedule is for a positive amount")
    if schedule.total_minor > 10**12:
        raise LedgerError("a recognition schedule past the sane bound")
    # `isascii` as well, because `money.Money` requires it and two currency checks that
    # disagree is one of them passing a value the other refuses.
    if (len(schedule.currency) != 3 or not schedule.currency.isupper()
            or not schedule.currency.isascii()):
        raise LedgerError("a recognition schedule's currency is a three-letter code")
    if schedule.basis == "straight_line":
        if schedule.starts_on is None or schedule.ends_on is None:
            raise LedgerError("a straight-line schedule earns over a period")
        if schedule.ends_on < schedule.starts_on:
            raise LedgerError("a schedule cannot end before it starts")
        # **Bounded, because the allocation builds a list per day.** Ten years is longer than
        # any prepaid term this product sells and the arithmetic below is linear in the day
        # count -- an unbounded period is a request that allocates a hundred million shares
        # and answers 500, which is MOD-011's forecast overflow in different clothes.
        if (schedule.ends_on - schedule.starts_on).days > 3650:
            raise LedgerError("a straight-line schedule earns over at most ten years")
        if schedule.units_total is not None:
            raise LedgerError("a straight-line schedule earns by time, not by unit")
    elif schedule.basis == "on_delivery":
        if schedule.units_total is None or schedule.units_total <= 0:
            raise LedgerError("an on-delivery schedule earns over a number of units")
        if schedule.units_total > 100_000:
            raise LedgerError("an on-delivery schedule earns over at most 100,000 units")
        if schedule.starts_on is not None or schedule.ends_on is not None:
            raise LedgerError("an on-delivery schedule earns by unit, not by time")
    else:
        if schedule.starts_on is not None or schedule.units_total is not None:
            raise LedgerError("an immediate schedule earns when it is sold")


def earned_by(schedule: Schedule, *, at: date, units_delivered: int = 0) -> int:
    """How much of the schedule is earned, cumulatively, as of now.

    **Cumulative rather than incremental**, which is the decision that makes this safe to run
    twice: a sweep that posted "one more day" would double-count the day it ran twice, and
    there is no worker here to guarantee it runs once. What is posted is the difference between
    this figure and what has already been recognised, so running it ten times in one day posts
    once and then posts nothing.
    """
    check_schedule(schedule)
    if schedule.basis == "immediate":
        return schedule.total_minor
    if schedule.basis == "on_delivery":
        assert schedule.units_total is not None
        if units_delivered < 0:
            raise LedgerError("units delivered cannot be negative")
        if units_delivered >= schedule.units_total:
            return schedule.total_minor
        # Largest-remainder allocation, so the units each earn a whole share and the last
        # delivery earns the remainder rather than the rounding being lost.
        shares = money.allocate(schedule.total_minor, [1] * schedule.units_total)
        return sum(shares[:units_delivered])
    assert schedule.starts_on is not None and schedule.ends_on is not None
    if at < schedule.starts_on:
        return 0
    if at >= schedule.ends_on:
        return schedule.total_minor
    total_days = (schedule.ends_on - schedule.starts_on).days + 1
    elapsed = (at - schedule.starts_on).days + 1
    shares = money.allocate(schedule.total_minor, [1] * total_days)
    return sum(shares[:elapsed])


def to_recognise(
    schedule: Schedule, *, already_minor: int, at: date, units_delivered: int = 0,
) -> int:
    """What a recognition posting should move now. Zero is the ordinary answer.

    **Never negative.** A schedule whose basis says less is earned than has already been
    recognised -- a class pack whose delivery count was corrected downwards, say -- is a
    correction somebody has to make deliberately, with a reason, in the open period. Quietly
    posting a negative recognition would reverse earned revenue with nothing to show why.
    """
    earned = earned_by(schedule, at=at, units_delivered=units_delivered)
    if already_minor < 0:
        raise LedgerError("what has already been recognised cannot be negative")
    if already_minor > schedule.total_minor:
        raise LedgerError(
            f"{already_minor} has been recognised against a schedule of "
            f"{schedule.total_minor}")
    return max(earned - already_minor, 0)


def over_recognised(schedule: Schedule, *, already_minor: int, at: date,
                    units_delivered: int = 0) -> int:
    """How much more has been recognised than is earned. For reporting, not for posting.

    This is the figure `to_recognise` refuses to act on, returned so a close can list the
    schedules that need a human. Zero whenever the ordinary case holds.
    """
    earned = earned_by(schedule, at=at, units_delivered=units_delivered)
    return max(already_minor - earned, 0)


def remaining(schedule: Schedule, *, already_minor: int) -> int:
    """What is still sitting in unearned revenue for this schedule."""
    check_schedule(schedule)
    return schedule.total_minor - already_minor
