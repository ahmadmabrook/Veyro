"""OPS-02-R02: the booking policy -- windows, lead time, quotas and priority.

**A booking policy is the tenant's, and a session's capacity policy is MOD-019's.** The two are
different questions and keeping them apart is why there are two tables: MOD-019 decides when a
*session* opens for booking at all, because that is a property of the session, and this decides
what a *member* may do inside that window -- how many bookings they may hold, how late they may
cancel, how far ahead they may reach. A single policy would make a tenant's cancellation rule a
property of every class it is attached to.

**A snapshot, like MOD-012's install and MOD-017's agreement.** A booking records the policy
version it was made under, because the consequence of cancelling it late is decided months
later and must be decided on the terms the member agreed to. Changing the cancellation window
next week cannot change what somebody owes for a class they booked last week.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.booking.denial import BookingError

#: The periods a quota can be counted over. Not "per month": a calendar month makes a member's
#: allowance depend on which month they joined in, and a rolling window is what every tenant
#: describing a "ten classes a month" plan actually means.
QUOTA_PERIODS: tuple[str, ...] = ("day", "week", "rolling_7_days", "rolling_30_days")

#: How a member's place in the waitlist is decided. `first_come` is the default because it is
#: the only one a member can predict; `membership_tier` needs MOD-017 and is why `priority` is
#: on the policy rather than assumed.
PRIORITY_RULES: tuple[str, ...] = ("first_come", "membership_tier")

#: The longest a tenant can hold a member to a cancellation window. Beyond a week the class is
#: further away than the decision, and a policy that charges for cancelling a class eight days
#: out is one nobody can plan around.
MAX_CANCELLATION_HOURS = 168

#: The most bookings a policy can let one member hold at once. A bound rather than a judgement
#: about gyms: an unbounded one is a member who books every class in the horizon and attends
#: none, which is what the quota exists to stop.
MAX_CONCURRENT = 100


@dataclass(frozen=True)
class Policy:
    """A tenant's booking rules, as a booking snapshots them.

    Every field is a number or a declared value, deliberately: a policy a member is held to has
    to be readable back to them, and a rule expressed as prose is one nobody can evaluate.
    """

    #: Hours before the session start after which cancelling is "late" and carries the
    #: consequence `consequence.py` decides. Zero means a cancellation is never late.
    cancellation_hours: int = 12
    #: How many bookings one member may hold on sessions that have not happened yet.
    max_concurrent: int = 10
    #: The quota and the period it is counted over, or None for no quota.
    quota: int | None = None
    quota_period: str = "rolling_7_days"
    #: Minutes after the session's start within which a check-in still counts as attendance.
    #: Beyond it the booking is a no-show, which is what `attendance.py` decides.
    checkin_grace_minutes: int = 15
    #: How many no-shows before a warning, and before a strike. A strike is what a tenant acts
    #: on; a warning is what it tells the member first, because a sanction with no notice is
    #: the thing appeals exist to overturn.
    warn_after_no_shows: int = 2
    strike_after_no_shows: int = 3
    priority_rule: str = "first_come"
    #: Minutes a waitlist offer is held open. The place is reserved for this long -- paragraph
    #: 5031: "waitlist promotion reserves before notifying" -- so a long window is capacity
    #: nobody can book and a short one is an offer a member asleep at 06:00 cannot take.
    offer_minutes: int = 60


def check_policy(policy: Policy) -> None:
    """Refuse a policy that cannot be applied, with the reason in the message."""
    if policy.cancellation_hours < 0:
        raise BookingError("a cancellation window is measured backwards from the session")
    if policy.cancellation_hours > MAX_CANCELLATION_HOURS:
        raise BookingError(
            f"a cancellation window is at most {MAX_CANCELLATION_HOURS} hours; beyond that "
            f"the class is further away than the decision")
    if policy.max_concurrent < 1:
        raise BookingError("a member may hold at least one booking")
    if policy.max_concurrent > MAX_CONCURRENT:
        raise BookingError(f"a member holds at most {MAX_CONCURRENT} bookings at once")
    if policy.quota is not None and policy.quota < 1:
        raise BookingError("a quota of zero is a policy that books nothing; leave it unset")
    if policy.quota is not None and policy.quota > 10_000:
        raise BookingError("a quota is at most 10000")
    if policy.quota_period not in QUOTA_PERIODS:
        raise BookingError(f"{policy.quota_period!r} is not a quota period")
    if not 0 <= policy.checkin_grace_minutes <= 240:
        raise BookingError("a check-in grace period is between zero and four hours")
    if policy.warn_after_no_shows < 1 or policy.strike_after_no_shows < 1:
        raise BookingError("a warning and a strike are counted from at least one no-show")
    if policy.strike_after_no_shows < policy.warn_after_no_shows:
        raise BookingError(
            "a strike comes after a warning, not before it: a sanction with no notice is "
            "what an appeal exists to overturn")
    if policy.priority_rule not in PRIORITY_RULES:
        raise BookingError(f"{policy.priority_rule!r} is not a waitlist priority rule")
    if not 1 <= policy.offer_minutes <= 1440:
        raise BookingError(
            "a waitlist offer is held open between a minute and a day; longer is capacity "
            "nobody can book")


def _local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """Midnight at the start of `day` in `zone`, as an absolute instant.

    **Built from the date rather than by adding a day to a datetime.** Adding `timedelta` to an
    aware instant is absolute-time arithmetic, so a day added across a clock change lands at
    01:00 or 23:00 local and the bucket stops being the calendar day it is named after. Where
    local midnight does not exist at all -- Chile and Cuba shift at midnight, and
    America/Nuuk's gap is 23:00 to 23:59 -- `ZoneInfo` resolves it with the offset in force
    before the transition, which puts one hour of a 23-hour day in the previous bucket. That is
    the smaller error and it is stated rather than hidden.
    """
    return datetime.combine(day, time(0), tzinfo=zone)


def quota_bucket(period: str, *, at: datetime, timezone: str) -> tuple[datetime, datetime]:
    """The calendar bucket a `day` or `week` quota is counted over, as half-open instants.

    **In the session's own timezone, not in whatever the instant happens to carry.**
    `sch_sessions` stores a UTC instant *and* the zone it was converted from precisely because
    neither is derivable from the other, and a bucket computed on the UTC day is the wrong day
    for every tenant more than an hour out: a "two a day" policy in Sydney resets at eleven in
    the morning, so a member takes two before the reset and two after. Found by review, and it
    is MOD-017's `AT TIME ZONE` lesson one module later -- the correct value was already in the
    caller's hand.

    **A week starts on Monday**, stated here because it is a product assumption and not a fact:
    a tenant whose week starts on Saturday has its allowance reset on the wrong day, and
    closing that needs a field on the policy rather than a different constant.
    """
    if period not in ("day", "week"):
        raise BookingError(f"{period!r} is not a calendar quota period")
    if at.tzinfo is None or at.utcoffset() is None:
        raise BookingError(
            "a quota bucket is computed from an absolute instant; a naive one has no zone to "
            "convert out of")
    try:
        zone = ZoneInfo(timezone)
    except Exception as exc:
        raise BookingError(f"{timezone!r} is not a timezone") from exc
    local = at.astimezone(zone)
    if period == "day":
        day = local.date()
        return _local_midnight(day, zone), _local_midnight(day + timedelta(days=1), zone)
    monday = local.date() - timedelta(days=local.weekday())
    return _local_midnight(monday, zone), _local_midnight(monday + timedelta(days=7), zone)


def rolling_days(period: str) -> int:
    """How many days a rolling quota period spans."""
    if period == "rolling_7_days":
        return 7
    if period == "rolling_30_days":
        return 30
    raise BookingError(f"{period!r} is not a rolling quota period")


def quota_span(period: str, *, at: datetime, timezone: str) -> tuple[datetime, datetime]:
    """The span of a member's own sessions a quota decision has to read.

    Wider than the bucket for a rolling period, and deliberately: a rolling quota is a
    statement about *every* window containing the session, so a booking after it counts as much
    as one before. The first version returned `(at - days, at)` and looked only backwards,
    which a member defeats by booking the last class of the week first -- seven classes under a
    quota of three, in request order, with nothing adversarial about it. Two sessions at the
    same instant were worse still: `at` sat on the excluded closing edge, so five classes at
    six o'clock each saw an empty window. Found by review.
    """
    if period in ("day", "week"):
        return quota_bucket(period, at=at, timezone=timezone)
    days = timedelta(days=rolling_days(period))
    return at - days, at + days


def quota_allows(
    candidate: datetime, others: list[datetime], *, policy: Policy, timezone: str,
) -> bool:
    """Whether this session fits the member's quota, given their other sessions in the span.

    **Order-independent, which is the whole point.** A calendar period counts everything in the
    bucket the session falls in; a rolling period asks whether any window of that length would
    end up holding more than the quota, which is the only reading of "three a week" that cannot
    be rearranged. Both answers are the same whichever order the member books in.
    """
    check_policy(policy)
    if policy.quota is None:
        return True
    quota = policy.quota
    if policy.quota_period in ("day", "week"):
        start, end = quota_bucket(policy.quota_period, at=candidate, timezone=timezone)
        used = sum(1 for other in others if start <= other < end)
        return used < quota
    # No window of this length may hold more than the quota. Sorted, that is exactly: every
    # run of `quota + 1` consecutive sessions spans at least a whole window.
    window = timedelta(days=rolling_days(policy.quota_period))
    times = sorted([*others, candidate])
    return all(times[i + quota] - times[i] >= window for i in range(len(times) - quota))


def cancellation_is_late(
    starts_at: datetime, *, at: datetime, policy: Policy,
) -> bool:
    """Whether cancelling now carries the policy's consequence.

    **After the session has started is late, not "not a cancellation".** A member who cancels
    during the class has not attended it, and treating that as an ordinary cancellation is how
    a no-show becomes free. What the consequence *is* belongs to `consequence.py`.
    """
    check_policy(policy)
    if policy.cancellation_hours == 0:
        return False
    return at > starts_at - timedelta(hours=policy.cancellation_hours)


def within_concurrent_limit(held: int, *, policy: Policy) -> bool:
    """Whether a member holding `held` live bookings may take one more."""
    check_policy(policy)
    if held < 0:
        raise BookingError("a count of held bookings is not negative")
    return held < policy.max_concurrent


def within_quota(used: int, *, policy: Policy) -> bool:
    """Whether a member who has used `used` of their quota may book again.

    A policy with no quota admits everything, which is what `None` means -- and is why this
    takes the policy rather than the number: a caller that defaulted a missing quota to zero
    would refuse every booking in a tenant that set none.

    **This is the calendar half only.** A rolling period cannot be decided from a count,
    because which sessions fall in the window depends on the candidate: `quota_allows` is the
    entry point, and it is what the service calls.
    """
    check_policy(policy)
    if used < 0:
        raise BookingError("a count of used bookings is not negative")
    if policy.quota is None:
        return True
    return used < policy.quota
