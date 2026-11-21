"""OPS-01-R03: when a resource can be scheduled, and the travel buffer between locations.

**Availability is a window plus the things that remove time from it.** Working hours say a
coach is here on Mondays from 07:00 to 15:00; a break removes an hour of that; time off removes
whole days. Three kinds rather than one because they are edited by different people at different
times -- a rota is set once a season, a break is part of the rota, and time off is a request --
and because a time-off row has to outlive a change to the working hours it overlapped.

**A resource with no working hours at all is unconstrained; one with any is held to them.**
Declaring a rota is what makes the rota binding. The first version treated an empty window list
as "never available", which is the fail-closed reading and wrong in a way that made the module
unusable: a room, a court, a bike and a service have no working hours in any meaningful sense,
so nothing could be scheduled in a tenant until somebody had written a rota for every piece of
equipment -- and on the day a gym opens, no rota exists for anybody. Found by writing the HTTP
tests, which is the argument for writing them: every domain test passed, because each one
supplied the windows it was about.

What is *not* fail-open is the day-by-day reading. A coach whose rota says Monday and Wednesday
is refused on Friday, because the rota is a statement about the whole week. And a removal binds
whether or not a rota exists: time off on a resource with no declared hours still blocks, since
an absence is a statement about a specific day and needs no rota to be meaningful.

**Deciding availability is a different question from detecting a conflict.** Availability asks
"is this resource supposed to be working then"; the conflict detector asks "is it already doing
something else". A session outside a coach's hours and a session clashing with another class
are different problems with different remedies, and a module that answered both with one
boolean would make the remedy unguessable.

**The travel buffer is between locations, not between sessions.** Paragraph 1835 names
"cross-location travel buffers": back-to-back classes in one studio are fine, and the same two
at sites twenty minutes apart are not. So the buffer applies only when the locations differ,
which means the check needs each session's location and not just its times.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.scheduling.recurrence import ScheduleError

#: How a window removes time. `working` adds availability; the other two take it away, and they
#: are distinct because a break recurs with the rota while time off is a dated absence.
WINDOW_KINDS: tuple[str, ...] = ("working", "break", "time_off")

#: The longest travel buffer a tenant can set. Beyond an hour the two sites are not in one
#: person's day and the schedule is lying about who can cover what.
MAX_TRAVEL_MINUTES = 120


@dataclass(frozen=True)
class Window:
    """One availability window for one resource.

    `weekday` is set for a recurring window and `on_date` for a one-off: a rota is weekly and
    time off is dated, and a single nullable pair would make "every Tuesday" and "this Tuesday"
    the same row.
    """

    kind: str
    #: Local to the resource's location, for paragraph 4150's reason: a rota is written in local
    #: time and a clock change must not move somebody's shift.
    timezone: str
    starts_at: time
    ends_at: time
    weekday: int | None = None
    on_date: date | None = None


@dataclass(frozen=True)
class Placement:
    """A session as the availability and conflict checks need it."""

    starts_at: datetime
    ends_at: datetime
    location_id: str | None = None


def check_window(window: Window) -> None:
    if window.kind not in WINDOW_KINDS:
        raise ScheduleError(f"{window.kind!r} is not an availability window kind")
    if window.ends_at <= window.starts_at:
        raise ScheduleError(
            "an availability window ends after it starts; a window over midnight is two "
            "windows, because the day it belongs to is otherwise unanswerable")
    if (window.weekday is None) == (window.on_date is None):
        raise ScheduleError(
            "an availability window is weekly or dated, not both and not neither")
    if window.weekday is not None and window.weekday not in range(7):
        raise ScheduleError("a weekday is 0 (Monday) to 6 (Sunday)")


def _local_span(placement: Placement, timezone: str) -> tuple[date, time, time]:
    """A placement as a local date and a local start and end, **in the given zone**.

    Availability is written in local time and a session is stored as instants, so one of the
    two has to be converted and it has to be this one: converting the *window* would mean doing
    it per occurrence anyway, and the window has no date to convert against.

    **Called once per window, with that window's own zone.** It used to be called once with a
    zone the caller chose, and `Window.timezone` -- declared, stored, and written from the
    resource's own location -- was read by nothing. A coach based in London rostered for 09:00
    to 17:00 was reported available for an 09:00 class at a site in Amman, which is 06:00 their
    time, because the session's zone was used to decide the coach's rota. With a *dated*
    absence it was worse than mis-timed: the window is selected by comparing its date against
    a local date computed in the wrong zone, so a day off three hours away was never consulted
    at all. Found by review.
    """
    zone = ZoneInfo(timezone)
    start = placement.starts_at.astimezone(zone)
    end = placement.ends_at.astimezone(zone)
    if start.date() != end.date():
        raise ScheduleError(
            "a session that crosses local midnight cannot be checked against a day's "
            "availability; schedule it as two")
    return start.date(), start.time(), end.time()


def _applicable(
    placement: Placement, windows: list[Window], *, timezone: str,
) -> list[tuple[Window, tuple[date, time, time]]]:
    """The windows that apply to this placement, each with the span read in its own zone.

    **`timezone` is the fallback, not the authority.** A window that declares its own zone is
    read in that one, because a rota is written where the resource is: the session's zone
    decides when the class is and the resource's decides whether anybody is there to run it.
    The parameter survives for a window whose zone is blank, which the schema does not allow
    but a caller constructing one by hand can produce.
    """
    for window in windows:
        check_window(window)
    out = []
    for window in windows:
        span = _local_span(placement, window.timezone or timezone)
        day = span[0]
        if window.on_date == day or (
                window.weekday is not None and window.weekday == day.weekday()):
            out.append((window, span))
    return out


def _is_constrained(
    windows: list[Window],
    applicable: list[tuple[Window, tuple[date, time, time]]],
) -> bool:
    """Whether this resource's rota binds on the day this placement falls on.

    Three cases, and each of the first two was a bug in turn:

      * **No working hours anywhere: unconstrained.** A room, a court and a bike have no rota
        in any meaningful sense, and on the day a gym opens nobody has one -- the first version
        read an empty list as "never available", so nothing could be scheduled at all.
      * **A weekly working window: the whole week binds.** A coach rostered Monday and
        Wednesday is not available on Friday, because a weekly rota is a statement about the
        week. This is what stops the rule above from being fail-open.
      * **Only dated working windows: each binds its own date.** The second version asked
        whether *any* working window existed, so one "open specially this Sunday" closed the
        rest of the week -- fail-closed, and a surprise no operator would predict.
    """
    if any(w.kind == "working" and w.weekday is not None for w in windows):
        return True
    return any(w.kind == "working" for w, _ in applicable)


def available(placement: Placement, windows: list[Window], *, timezone: str) -> bool:
    """Whether the windows allow a session at that placement.

    **A working window has to contain the whole session, and no removal may touch it.** Partial
    cover is not availability: half a class inside a coach's hours is a class that ends with
    nobody there. And a removal overlapping any part of it is enough, because a break in the
    middle of a session is not a session with a gap.

    **An empty window list is unconstrained** -- the module docstring says why -- and so is a
    list with no `working` window anywhere in it. A list that *does* declare working hours
    binds on every day, including the days it leaves out.
    """
    applicable = _applicable(placement, windows, timezone=timezone)
    if _is_constrained(windows, applicable):
        if not any(w.starts_at <= start and end <= w.ends_at
                   for w, (_, start, end) in applicable if w.kind == "working"):
            return False
    return not any(w.starts_at < end and start < w.ends_at
                   for w, (_, start, end) in applicable
                   if w.kind in ("break", "time_off"))


def unavailable_reason(
    placement: Placement, windows: list[Window], *, timezone: str,
) -> str | None:
    """Why the windows refuse, in a sentence, or None when they do not.

    **Separate from `available` because a denial has to be explainable.** Paragraph 1892 makes
    that a Critical Control for booking, and a scheduler telling an operator "no" with nothing
    else is a scheduler they work around by overriding everything.
    """
    applicable = _applicable(placement, windows, timezone=timezone)
    #: Only a resource whose rota reaches this day is held to it. The reason text distinguishes
    #: the two cases a reader needs to tell apart: a rota that leaves this day out, and a rota
    #: that covers it at other times.
    if _is_constrained(windows, applicable):
        working = [(w, span) for w, span in applicable if w.kind == "working"]
        if not working:
            # **The placement's own day, in the session's zone.** There is no applicable window
            # to take one from -- that is what this branch is about -- and reading it off the
            # first one raised `IndexError` on the commonest refusal in the module.
            day, _, _ = _local_span(placement, timezone)
            return f"this resource has no working hours on {day.isoformat()}"
        day = working[0][1][0]
        if not any(w.starts_at <= start and end <= w.ends_at for w, (_, start, end) in working):
            hours = ", ".join(
                f"{w.starts_at.strftime('%H:%M')}-{w.ends_at.strftime('%H:%M')}"
                for w, _ in sorted(working, key=lambda pair: pair[0].starts_at))
            _, start, end = working[0][1]
            return (f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')} is outside the working "
                    f"hours on {day.isoformat()} ({hours})")
    for window, (_, start, end) in sorted(
            applicable, key=lambda pair: pair[0].starts_at):
        if (window.kind in ("break", "time_off")
                and window.starts_at < end and start < window.ends_at):
            label = "a break" if window.kind == "break" else "time off"
            return (f"{label} from {window.starts_at.strftime('%H:%M')} to "
                    f"{window.ends_at.strftime('%H:%M')} overlaps this session")
    return None


def travel_gap_minutes(first: Placement, second: Placement) -> int | None:
    """The minutes between two sessions, or None when they are at one location.

    None rather than a large number, because "no travel needed" and "plenty of time" are
    different answers and the caller should not have to know a sentinel.
    """
    if first.location_id is None or second.location_id is None:
        return None
    if first.location_id == second.location_id:
        return None
    earlier, later = sorted((first, second), key=lambda p: p.starts_at)
    gap = later.starts_at - earlier.ends_at
    return int(gap.total_seconds() // 60)


def check_travel(
    first: Placement, second: Placement, *, buffer_minutes: int,
) -> str | None:
    """Whether one resource can make both sessions, given the buffer. A sentence, or None.

    **Overlapping sessions are not this function's finding.** Two sessions at the same time are
    a conflict whatever the travel time, and reporting them here as "not enough travel time"
    would send an operator looking at a map instead of at the clash.
    """
    if buffer_minutes < 0:
        raise ScheduleError("a travel buffer is not negative")
    if buffer_minutes > MAX_TRAVEL_MINUTES:
        raise ScheduleError(
            f"a travel buffer is at most {MAX_TRAVEL_MINUTES} minutes; beyond that the two "
            f"sites are not in one person's day")
    gap = travel_gap_minutes(first, second)
    if gap is None:
        return None
    if gap < 0:
        return None
    if gap < buffer_minutes:
        earlier, later = sorted((first, second), key=lambda p: p.starts_at)
        return (f"{gap} minutes between {earlier.location_id} and {later.location_id}, and "
                f"the travel buffer is {buffer_minutes}")
    return None


# ------------------------------------------------- ADM-SCH-04: a week of a rota
#
# **The grid is the rota as a background with bookings drawn on top**, which is the canvas's
# own sentence and the reason these are separate functions from `available`: that one answers
# "may this session be placed", and a screen has to answer "what does this week look like"
# for a resource that may have no rota at all.
#
# Nothing here reads a session. `service.resource_week` composes the two and calls
# `unavailable_reason` per held session, so a booking inside a day off is **flagged rather
# than dropped** -- "reducing availability never deletes a booking ... because the member on
# the other end has already been told a time."


def week_from(any_day: date) -> tuple[date, ...]:
    """The seven local dates of the week containing `any_day`, **Sunday first**.

    The caller may hand in any day; the week is normalised so two readers asking about the
    same week get the same seven dates.

    **Sunday, not Monday, and that is the design's call rather than this module's.**
    ADM-SCH-04 draws its columns SUN-SAT and dates its sample week to a Sunday, which is the
    working week in this product's own market -- Sunday to Thursday. The first version started
    on Monday because `Window.weekday` is 0-Monday, which is MOD-019's storage convention and
    says nothing about how a week is read: the rota rows are keyed by weekday number either
    way, and only the order of the seven dates moves.

    What this is *not* is a declaration of which days are the working week.
    `GET /reports/attendance` refuses to label a day set "weekdays" because nothing in this
    build records one, and that still holds -- a column order is where the week begins, not
    which of its days anybody works.
    """
    # `date.weekday()` is 0-Monday, so Sunday is 6; `(weekday + 1) % 7` is days since Sunday.
    start = any_day - timedelta(days=(any_day.weekday() + 1) % 7)
    return tuple(start + timedelta(days=offset) for offset in range(7))


def windows_on(windows: list[Window], day: date) -> list[Window]:
    """The windows that bind on one local date, weekly and dated alike.

    Sorted by start so a grid can draw them in order without choosing an order of its own --
    a pure function that answered differently depending on row order is MOD-019's
    `publishing.assess` finding, and a rota read straight from a table has no order.
    """
    for window in windows:
        check_window(window)
    return sorted(
        (w for w in windows
         if w.on_date == day or (w.weekday is not None and w.weekday == day.weekday())),
        key=lambda w: (w.starts_at, w.ends_at, w.kind))


def _minutes(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


def _subtract(spans: list[tuple[time, time]], cut: tuple[time, time]) -> list[tuple[time, time]]:
    out: list[tuple[time, time]] = []
    for start, end in spans:
        if cut[1] <= start or end <= cut[0]:
            out.append((start, end))
            continue
        if start < cut[0]:
            out.append((start, cut[0]))
        if cut[1] < end:
            out.append((cut[1], end))
    return out


def _merge(spans: list[tuple[time, time]]) -> list[tuple[time, time]]:
    """Overlapping spans joined, so an hour covered twice is counted once.

    **Two working rows on one weekday are ordinary and were double-counted.** A rota entered
    as 09:00-13:00 and then widened by adding 11:00-15:00 -- rather than by editing the first
    row, which nothing in this module makes anybody do -- is six hours open and reported as
    eight. That figure is the denominator of the canvas's own "26 of 34 available hours
    booked", so inflating it makes somebody look less booked than they are. Found by the test
    written for it, which is the argument for writing the arithmetic one down.
    """
    out: list[tuple[time, time]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def open_spans_on(windows: list[Window], day: date) -> list[tuple[time, time]]:
    """The working time left on one day once breaks and time off are removed.

    **A resource with no working window that binds is not "zero hours open" -- it is
    unconstrained**, and this function returns an empty list for both. The caller has to tell
    them apart with `rota_binds_on`, because rendering "0 of 0 hours" for a room that has no
    rota in any meaningful sense is the confident wrong answer `_is_constrained` exists to
    prevent. A removal binds whether or not a rota exists, which is why time off on a
    rota-less resource still subtracts from nothing and the result is still empty.
    """
    today = windows_on(windows, day)
    spans = _merge([(w.starts_at, w.ends_at) for w in today if w.kind == "working"])
    for window in today:
        if window.kind in ("break", "time_off"):
            spans = _subtract(spans, (window.starts_at, window.ends_at))
    return sorted(spans)


def rota_binds_on(windows: list[Window], day: date) -> bool:
    """Whether this resource's rota is a statement about this day at all.

    The same three cases `_is_constrained` decides, asked about a date rather than about a
    placement: any weekly working window binds the whole week, a dated one binds its own date,
    and a resource with neither is unconstrained.
    """
    if any(w.kind == "working" and w.weekday is not None for w in windows):
        return True
    return any(w.kind == "working" for w in windows_on(windows, day))


def open_minutes_on(windows: list[Window], day: date) -> int | None:
    """Minutes this resource is open on one day, or `None` where no rota binds.

    `None` rather than a large number and rather than zero: "available all day because nobody
    wrote a rota" and "available for no minutes because the rota says so" are different facts
    with different remedies, and a figure that conflated them would be the denominator of the
    canvas's own "26 of 34 available hours booked".
    """
    if not rota_binds_on(windows, day):
        return None
    return sum(_minutes(start, end) for start, end in open_spans_on(windows, day))
