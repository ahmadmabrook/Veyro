"""OPS-01-R02's recurring schedules, and the timezone correctness paragraph 4150 requires.

**The rule and the occurrences it generates are different things, and that is the whole
design.** Paragraph 4149: "Recurring schedule definition is separate from generated occurrences
so historical instances remain stable after template edits." So a template says "Mondays and
Wednesdays at 18:00 local for sixty minutes" and generating materialises rows -- and editing the
template afterwards leaves every instance already generated exactly as it was. A design that
computed occurrences from the rule at read time would rewrite history every time somebody fixed
a typo in next month's schedule.

**A local time of day plus a timezone, never a UTC time of day.** Paragraph 4150: "store UTC
instants and source local timezone/recurrence rule for correct DST behavior." An 18:00 class is
at 18:00 for the member whatever the clocks did, so the rule carries 18:00 and a timezone and
each occurrence is converted separately. Storing one UTC instant and adding seven days moves
the class by an hour twice a year, in the direction that makes a 06:00 session land at 05:00 on
the morning nobody expected.

**The two clock-change edges are decided here rather than discovered.** A local time can be
skipped (the hour that does not exist when clocks go forward) or repeated (the hour that happens
twice when they go back):

  * **Skipped: the occurrence moves forward out of the gap**, and `Occurrence.adjusted` says so.
    Refusing would silently drop a class from the schedule on one day a year, which is worse: the
    members who booked it get nothing and no row explains why. Moving it keeps the class and
    makes the shift visible.
  * **Repeated: the first of the two is used**, which is `fold=0`. Either is defensible and the
    reason to decide is that leaving it to the platform's default is how two services disagree
    about which 01:30 a class was at. The earlier one is also the one a member reading "01:30"
    on the day the clocks go back will arrive for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ScheduleError(ValueError):
    """A scheduling decision refused. The service turns these into 409s and 422s."""


#: The recurrence frequencies this build generates. **Four, not a general iCalendar RRULE**:
#: every pattern OPS-01-R02 names -- one-time, weekly classes, a fortnightly PT slot, a monthly
#: assessment -- is expressible with these, and a full RRULE parser is a surface with its own
#: edge cases (BYSETPOS, BYYEARDAY, leap-week rules) that nothing here would exercise. A fifth
#: frequency is a decision to make when a tenant needs it, not a parser to inherit.
FREQUENCIES: tuple[str, ...] = ("once", "daily", "weekly", "monthly_by_weekday")

#: How far ahead a rule reaches. Beyond this a schedule is a plan rather than a booking surface,
#: and the instances would be rows nobody reads for months.
#:
#: **This is the only bound, because it subsumes a count.** A rule carries one local time, so
#: it produces at most one occurrence a day and the horizon bounds the row count at 401. A
#: separate `MAX_OCCURRENCES` sat here and could not fire -- an unreachable check with no
#: isolating case, which is what the rules file says to delete rather than test harder. The day
#: a rule carries several times of day, the count comes back with a case of its own.
MAX_HORIZON_DAYS = 400

#: The years a schedule can be in. Not a style bound: `date` arithmetic overflows a few days
#: past 9999 and the generator walks day by day, so the far edge has to be refused before the
#: walk rather than caught after it. The near edge is a typo bound -- a class in 1970 is a
#: wrong year, not a plan.
MIN_YEAR = 2000
MAX_YEAR = 2100


@dataclass(frozen=True)
class Rule:
    """A recurrence, in the terms the template stores it.

    `weekdays` is Monday=0 .. Sunday=6, which is `date.weekday()`'s own numbering, so nothing
    here converts between two conventions -- a conversion is where an off-by-one lands a class
    on the wrong day.
    """

    frequency: str
    #: The local time of day the occurrence starts at, in `timezone`.
    local_time: time
    #: The location's timezone. **Not the tenant's and not the server's**: paragraph 4150 makes
    #: this location-specific, because a tenant with sites in two zones has two schedules.
    timezone: str
    duration_minutes: int
    starts_on: date
    #: Inclusive. A template with no end is a template nobody can audit the extent of.
    until: date
    #: For `weekly` and `monthly_by_weekday`. Empty for `once` and `daily`.
    weekdays: tuple[int, ...] = ()
    #: For `monthly_by_weekday`: which occurrence of the weekday in the month, 1-based, or -1
    #: for the last. "The first Monday" and "the last Friday" are the two forms a gym uses.
    week_of_month: int | None = None
    #: Local dates the rule skips. OPS-01-R02's exceptions and seasonality: a public holiday, a
    #: shutdown week. Kept on the rule rather than deleted from the instances, so "why is there
    #: no class that Monday" is answerable.
    excluded_dates: tuple[date, ...] = ()


@dataclass(frozen=True)
class Occurrence:
    """One generated session, as instants plus the local facts it came from.

    Both the UTC instant and the local date are stored, because the first is what orders a
    schedule and the second is what a member recognises -- and after a clock change the two
    cannot be derived from each other without the timezone, which is why the rule carries it.
    """

    starts_at: datetime
    ends_at: datetime
    local_date: date
    #: True when the local time did not exist on that date and the occurrence moved forward out
    #: of the gap. One day a year, in one timezone, and the row says so.
    adjusted: bool = False


def check_rule(rule: Rule) -> None:
    """Refuse a rule that cannot generate a sane schedule."""
    if rule.frequency not in FREQUENCIES:
        raise ScheduleError(f"{rule.frequency!r} is not a recurrence frequency")
    if rule.duration_minutes <= 0:
        raise ScheduleError("a session lasts longer than no time at all")
    if rule.duration_minutes > 24 * 60:
        raise ScheduleError("a session shorter than a day; a longer one is a programme")
    try:
        ZoneInfo(rule.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError(f"{rule.timezone!r} is not a timezone") from None
    if rule.until < rule.starts_on:
        raise ScheduleError("a schedule does not end before it starts")
    if (rule.until - rule.starts_on).days > MAX_HORIZON_DAYS:
        raise ScheduleError(
            f"a schedule runs for at most {MAX_HORIZON_DAYS} days; beyond that it is a plan "
            f"rather than a booking surface")
    # **The epoch, as well as the span.** Only the span was bounded, so a thirty-day rule in
    # year 9999 passed validation and then walked `day += timedelta(days=1)` off the end of
    # `date` with an `OverflowError` -- which is not a `ValueError`, so not a `ScheduleError`,
    # so a 500. A reviewer typed one wrong year and the draft committed anyway, permanently
    # taking that template code: the table has a unique index on it, no DELETE grant, and a
    # draft cannot be retired.
    if not (MIN_YEAR <= rule.starts_on.year <= MAX_YEAR) or rule.until.year > MAX_YEAR:
        raise ScheduleError(
            f"a schedule runs between {MIN_YEAR} and {MAX_YEAR}; {rule.starts_on.year} is a "
            f"year nobody is booking classes in")
    if rule.frequency == "once" and rule.until != rule.starts_on:
        raise ScheduleError("a one-time session starts and ends on the same day")
    if rule.frequency in ("weekly", "monthly_by_weekday") and not rule.weekdays:
        raise ScheduleError(f"a {rule.frequency} schedule names the days it runs on")
    if rule.frequency not in ("weekly", "monthly_by_weekday") and rule.weekdays:
        raise ScheduleError(f"a {rule.frequency} schedule does not name weekdays")
    if any(day not in range(7) for day in rule.weekdays):
        raise ScheduleError("a weekday is 0 (Monday) to 6 (Sunday)")
    if len(set(rule.weekdays)) != len(rule.weekdays):
        raise ScheduleError("a weekday is named once")
    if rule.frequency == "monthly_by_weekday":
        if rule.week_of_month is None:
            raise ScheduleError(
                "a monthly schedule says which occurrence of the weekday it means")
        if rule.week_of_month not in (1, 2, 3, 4, -1):
            raise ScheduleError(
                "the occurrence of a weekday in a month is 1 to 4, or -1 for the last")
    elif rule.week_of_month is not None:
        raise ScheduleError(
            f"a {rule.frequency} schedule does not take an occurrence of the month")


def _local_dates(rule: Rule) -> list[date]:
    """The local dates the rule falls on, before any timezone arithmetic.

    Separate from the instant conversion because the two are different kinds of mistake: a
    wrong date is a wrong day of the week, and a wrong instant is the right day at the wrong
    hour. Keeping them apart means a test can pin either.
    """
    out: list[date] = []
    if rule.frequency == "once":
        out = [rule.starts_on]
    elif rule.frequency == "daily":
        day = rule.starts_on
        while day <= rule.until:
            out.append(day)
            day += timedelta(days=1)
    elif rule.frequency == "weekly":
        day = rule.starts_on
        while day <= rule.until:
            if day.weekday() in rule.weekdays:
                out.append(day)
            day += timedelta(days=1)
    else:
        # `monthly_by_weekday`: the nth (or last) named weekday of each month in range.
        # Counted within the month rather than from the start date, because "the first Monday"
        # means the month's first Monday whatever day the template was written on.
        day = rule.starts_on
        while day <= rule.until:
            if day.weekday() in rule.weekdays and _is_nth_weekday(day, rule.week_of_month):
                out.append(day)
            day += timedelta(days=1)
    excluded = set(rule.excluded_dates)
    return [day for day in out if day not in excluded]


def _round_trip(local: datetime, zone: ZoneInfo) -> datetime:
    """The wall time `local` names, after a trip through UTC and back.

    For an ordinary local time this is `local` itself. For one inside a spring-forward gap it
    is an hour later, because the instant `ZoneInfo` chose for the gap wall time belongs to a
    different wall time once the offset that actually applies is used.
    """
    return local.astimezone(UTC).astimezone(zone).replace(tzinfo=None)


def _is_nth_weekday(day: date, which: int | None) -> bool:
    """Whether `day` is the `which`th occurrence of its weekday in its month."""
    if which is None:
        return True
    if which == -1:
        return (day + timedelta(days=7)).month != day.month
    return (day.day - 1) // 7 + 1 == which


def generate(rule: Rule) -> list[Occurrence]:
    """The occurrences a rule produces, as UTC instants.

    **Each local date is converted on its own**, which is the whole of paragraph 4150: adding
    seven days to a UTC instant moves an 18:00 class to 17:00 or 19:00 across a clock change,
    and the member who turns up at 18:00 finds the room empty or occupied.
    """
    check_rule(rule)
    zone = ZoneInfo(rule.timezone)
    dates = _local_dates(rule)
    out: list[Occurrence] = []
    for day in dates:
        naive = datetime.combine(day, rule.local_time)
        local = naive.replace(tzinfo=zone)
        adjusted = False
        # **The hour that does not exist.** When clocks go forward, a local wall time inside the
        # gap names no instant, and `ZoneInfo` resolves it with the pre-transition offset
        # rather than refusing -- so the only way to notice is to go out to UTC and come back
        # and see whether the wall time survived.
        #
        # **Through UTC, not to the same zone.** `local.astimezone(zone)` where `local` is
        # already in `zone` is a no-op that returns the same wall time, so a round trip written
        # that way can never detect anything: it reported every skipped hour as fine, which the
        # first run of this module's own check showed.
        #: **Stepped until it lands on a real instant, not nudged once.** One hour is enough
        #: for every zone that shifts by an hour, and Antarctica/Troll moves by two -- asking
        #: for 01:30 there landed on 04:30 local, three hours late, because `naive + 1h` was
        #: still a wall time that does not exist and `replace(tzinfo=...)` resolved it with the
        #: pre-transition offset. Bounded at four steps because no zone has ever skipped more.
        steps = 0
        while _round_trip(local, zone) != naive and steps < 4:
            steps += 1
            naive += timedelta(hours=1)
            local = naive.replace(tzinfo=zone)
            adjusted = True
        if _round_trip(local, zone) != naive:
            raise ScheduleError(
                f"{rule.local_time.isoformat()} does not exist on {day.isoformat()} in "
                f"{rule.timezone} and no nearby hour does either")
        starts_at = local.astimezone(UTC)
        out.append(Occurrence(
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=rule.duration_minutes),
            #: **Re-derived, because the adjustment can cross midnight.** The gap is 23:00 to
            #: 23:59 in America/Nuuk, so a 23:30 rule moves onto the next local day -- and
            #: storing the day it was asked for left the two facts this row keeps separately
            #: contradicting each other.
            local_date=starts_at.astimezone(zone).date(),
            adjusted=adjusted))
    return out


def occurrence_count(rule: Rule) -> int:
    """How many occurrences a rule would produce, without building them.

    For the impact preview paragraph 1841 requires: "all schedule changes are effective-dated
    and impact-assessed before publication", and the first thing anybody wants to know about a
    draft is how many sessions it is.
    """
    check_rule(rule)
    return len(_local_dates(rule))
