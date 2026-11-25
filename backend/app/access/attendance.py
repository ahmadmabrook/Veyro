"""Which hour of the day a club is busiest, and the one claim this build will not make.

ADM-RPT-04 draws a bar per hour and then writes the conclusion underneath it in words. The
canvas gives its own reason, and it is the requirement rather than a styling note: "A manager
should not have to interpret a heat strip to find the actionable hour." So the actionable hour
is derived here, where it can be tested, rather than left to whoever reads the chart.

**The claim this module refuses is the canvas's own percentage of floor capacity.** The canvas
writes "18:00-20:00 runs at 94% of floor capacity", and a capacity figure does exist -- it is
`acc_policies.capacity`, the number `policy.evaluate` refuses a presentation against. It is
not the denominator for this chart, for two independent reasons and either would be enough:

  * **Entries in an hour are not people inside at a moment.** A hundred arrivals between six
    and seven is a floor holding a hundred if everybody stays an hour and fifty if everybody
    stays half of one. A capacity bounds simultaneous presence, so dividing an arrival count
    by it answers a question nobody asked and reads as the one they did.
  * **Occupancy here is advisory unless a zone reads both directions**, which is
    `occupancy.confidence` and paragraph 4180 behind it. A concurrency figure summed over four
    weeks at an entry-only turnstile climbs all month, so the honest version of this
    comparison is unavailable at exactly the zones most clubs have.

What is left is still the whole of the canvas's point, because every figure on that chart is
*relative*: the bars are heights against the busiest hour and the three colours are tiers of
the same ratio. So the conclusion is written against the peak rather than against a capacity,
which needs no denominator this build would have to invent -- and `NO_CAPACITY_PERCENTAGE`
says so on the response, because a reader who assumed the percentages were capacity would be
making a staffing decision on the wrong number.

Nothing here does I/O. `service.visits_by_hour` fetches the buckets and calls these.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.access.zones import AccessError

#: Hours in a local day. Every read returns all of them, including the empty ones -- see
#: `OPENING_HOURS_ARE_NOT_RECORDED`.
HOURS: tuple[int, ...] = tuple(range(24))

#: Days of the week, 0 Monday to 6 Sunday.
#:
#: **MOD-019's convention, imported rather than chosen.** `sch_availability_windows.weekday`
#: is 0 (Monday) to 6 (Sunday) and `availability.check_window` says so in as many words; a
#: second weekday convention in one repository is MOD-012's two retry curves, and the day they
#: disagree nobody can say which one is the policy. Postgres offers `isodow` (1-7) and `dow`
#: (0 = Sunday), so the query converts rather than letting either leak out.
WEEKDAYS: tuple[int, ...] = tuple(range(7))

#: The window a caller may ask for, in weeks of complete local days.
MIN_WEEKS = 1
MAX_WEEKS = 26

#: Where the three heat tiers divide, as a share of the busiest hour in basis points.
#:
#: Read off the canvas rather than picked: it paints 41% and 42% in the quiet tone, 52% and
#: 74% in the middle one, and 88% and 100% in the warning one. So the boundaries sit at a half
#: and at 85%, which is the only pair of round numbers that reproduces all six.
BUSY_FROM_BP = 5_000
PEAK_FROM_BP = 8_500

#: The tiers, quietest first. The surface maps these to tokens; nothing here knows a colour.
TIERS: tuple[str, ...] = ("quiet", "busy", "peak")

#: Said on every read, because the canvas's own sentence is a percentage of capacity.
NO_CAPACITY_PERCENTAGE = (
    "every share on this chart is a share of the busiest hour, never of a zone's capacity. "
    "Entries in an hour are arrivals, not people inside at a moment, and occupancy derived "
    "from access events is advisory unless a zone reads both directions"
)

#: Said on every read, because the quietest hour is the figure a manager acts on.
#:
#: **Its first clause used to say "nothing in this build records when a club is open", and that
#: has been false since MOD-026's third slice.** `plt01.tsk_business_hours` holds a location's
#: weekly pattern and its dated overrides with a withdrawal trail, and `/tasks/business-hours`
#: sets, withdraws and reads it -- a table, a writer and a route. MOD-026's own note says it
#: built that calendar *because* nothing recorded when a club is open and cited this refusal
#: for it, so the sentence outlived its reason by a module. It was returned to the caller on
#: every read and rendered on ADM-RPT-04, which means the product was telling a manager it
#: cannot know its own opening hours while a table held them.
#:
#: **What is still true is that this read does not consult them**, and that is a smaller and
#: honest claim: the hours are gated on `tasks.calendar.read`, which an access reader does not
#: hold, so consulting them is a composed second read whose availability depends on the
#: reader -- and a club's opening hours being a *tasks* fact is the architecture question
#: behind that, which ADM-SET-02 is the screen for. Until that is decided this read returns all
#: twenty-four hours, and says why in terms that are true.
OPENING_HOURS_ARE_NOT_RECORDED = (
    "this read does not consult a club's opening hours, so all 24 hours are returned and the "
    "quietest hour is the quietest one that saw anybody at all. Its share of the peak is "
    "returned beside it: an hour at a few per cent of the busiest one is a stray entry "
    "outside opening hours rather than a gap worth filling. The hours themselves are recorded "
    "per location in this build -- MOD-026's business calendar holds a weekly pattern and its "
    "dated overrides -- and composing them here is work rather than a missing fact"
)


@dataclass(frozen=True)
class Bucket:
    """One local hour and the entries recorded in it across the whole window."""

    hour: int
    entries: int

    def __post_init__(self) -> None:
        if self.hour not in HOURS:
            raise AccessError("an hour is 0 to 23")
        if self.entries < 0:
            raise AccessError("an entry count is not negative")


def check_weekdays(days: object) -> tuple[int, ...]:
    """The days this report is about, normalised -- and there is no default.

    **A weekend is jurisdictional and the sources state none.** The canvas scopes its chart to
    "WEEKDAYS", which is Monday to Friday in some markets and Sunday to Thursday in the one
    this product is built for, and no table, configuration key or constant in this repository
    declares which. So the set is required of the caller, which is MOD-009's precedent for a
    DSAR deadline and MOD-015's for a tax rate: a defaulted value here would be this module
    quietly deciding a market convention and then reporting a chart about the wrong days.
    """
    if not isinstance(days, (list, tuple, set, frozenset)):
        raise AccessError("the days are a list of weekdays, 0 (Monday) to 6 (Sunday)")
    seen: set[int] = set()
    for day in days:
        if isinstance(day, bool) or not isinstance(day, int):
            raise AccessError("a weekday is an integer, 0 (Monday) to 6 (Sunday)")
        if day not in WEEKDAYS:
            raise AccessError("a weekday is 0 (Monday) to 6 (Sunday)")
        seen.add(day)
    if not seen:
        raise AccessError("a report about no days is not a report")
    return tuple(sorted(seen))


def check_weeks(weeks: object) -> int:
    """How far back to look, in weeks of complete local days."""
    if isinstance(weeks, bool) or not isinstance(weeks, int):
        raise AccessError("the window is a whole number of weeks")
    if weeks < MIN_WEEKS or weeks > MAX_WEEKS:
        raise AccessError(f"the window is {MIN_WEEKS} to {MAX_WEEKS} weeks")
    return weeks


def peak_entries(buckets: tuple[Bucket, ...]) -> int:
    """The busiest hour's count, which is the denominator for everything else."""
    return max((b.entries for b in buckets), default=0)


def share_of_peak_bp(entries: int, peak: int) -> int | None:
    """`entries` as a share of the busiest hour, in basis points.

    `None` where the peak is zero, which is a window in which nobody came in at all. Returning
    0 there would read as "this hour is quiet" for a club that was shut, and the two are
    different facts -- MOD-011's "an empty window is not a pass" in a report.
    """
    if entries < 0 or peak < 0:
        raise AccessError("a count is not negative")
    if peak == 0:
        return None
    return round(entries * 10_000 / peak)


def tier(entries: int, peak: int) -> str:
    """Which of the canvas's three tones this hour is painted in.

    An hour that saw nobody is `quiet` rather than a fourth tone: the canvas has three, and an
    hour at zero and an hour at 4% of the peak are the same advice.
    """
    share = share_of_peak_bp(entries, peak)
    if share is None or share < BUSY_FROM_BP:
        return "quiet"
    if share < PEAK_FROM_BP:
        return "busy"
    return "peak"


def busiest_window(buckets: tuple[Bucket, ...]) -> dict[str, object] | None:
    """The run of hours around the busiest one, and any peak hour outside it.

    The canvas writes "18:00-20:00", which is the two peak-tier bars at 18:00 and 19:00 read
    as a span: `to_hour` is therefore the hour the last bar *ends*, which is what a reader
    means by "until eight".

    **The run is the contiguous one containing the single busiest hour, and the peak-tier
    hours outside it are returned separately.** A club with a morning rush and an evening one
    has two peaks, and one span covering both would claim the middle of the day is busy. The
    busiest hour ties to the earliest, so the answer does not depend on the order the rows
    arrived in -- which is MOD-019's `publishing.assess` finding, where a dict keyed on a
    start time dropped a session and which one depended on the query planner.
    """
    peak = peak_entries(buckets)
    if peak == 0:
        return None
    by_hour = {b.hour: b.entries for b in buckets}
    top = min((h for h in by_hour if by_hour[h] == peak), default=None)
    if top is None:
        return None
    in_tier = {h for h, n in by_hour.items() if tier(n, peak) == "peak"}
    first = top
    while first - 1 in in_tier:
        first -= 1
    last = top
    while last + 1 in in_tier:
        last += 1
    outside = tuple(sorted(h for h in in_tier if h < first or h > last))
    return {
        "from_hour": first,
        # The hour the span ends, so 18:00 and 19:00 read as "18:00 to 20:00".
        "to_hour": last + 1,
        "busiest_hour": top,
        "entries": peak,
        "other_peak_hours": outside,
    }


def quietest_attended_hour(buckets: tuple[Bucket, ...]) -> dict[str, object] | None:
    """The hour with the fewest entries among those that saw anybody.

    `None` where nobody came in at all. Hours at zero are excluded because nothing here
    records opening hours -- see `OPENING_HOURS_ARE_NOT_RECORDED` -- so "the quietest hour"
    taken over all 24 is four in the morning in every club in the world, and the one thing
    this chart exists to produce would be useless.
    """
    attended = [b for b in buckets if b.entries > 0]
    if not attended:
        return None
    fewest = min(b.entries for b in attended)
    hour = min(b.hour for b in attended if b.entries == fewest)
    return {
        "hour": hour,
        "entries": fewest,
        "share_of_peak_bp": share_of_peak_bp(fewest, peak_entries(buckets)),
    }


def days_in_window(first_day: date, last_day: date, weekdays: tuple[int, ...]) -> int:
    """How many days of the chosen set fall in the window, inclusive of both ends.

    The same for every hour, so it is one figure on the response rather than one per bucket --
    and it is what tells a reader the bars are a sum over twenty weekdays rather than one.
    """
    if last_day < first_day:
        raise AccessError("a window ends on or after it starts")
    wanted = set(check_weekdays(weekdays))
    days = 0
    day = first_day
    while day <= last_day:
        if day.weekday() in wanted:
            days += 1
        day += timedelta(days=1)
    return days
