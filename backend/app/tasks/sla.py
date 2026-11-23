"""MOD-026 · AUT-02-R06: the SLA clock, as arithmetic with no I/O.

INV-AUT-02: *"SLA calculation is time-zone and business-calendar aware."* That sentence is
this module, and three decisions carry it.

**Nothing is stored.** A clock is its target, the calendar, and the pauses recorded against
it; the remaining time is a function of those and `now()`. A stored countdown is a second copy
of the truth that goes stale between writes, which is MOD-018's no-stored-balance, MOD-019's
no-`held_count` and MOD-016's derived `in_window` for the fourth time. The cost is a query per
read; the benefit is that a dashboard and a breach report cannot disagree.

**Every span is measured in the location's own zone, and the answer is real elapsed time.**
A window is a *local* `09:00-17:00`; its two ends are converted to instants and the difference
taken. That is what makes a clock-change day come out right without a special case: on a
spring-forward morning the local window is one real hour shorter, and on an autumn one it is
an hour longer, because those are the instants. MOD-019 paid for the inverse of this -- a rota
read in the session's zone rather than the resource's made a London coach available at 06:00
their time.

**A dated row replaces the weekly pattern for its date; it does not add to it.** Otherwise a
half-day before a holiday is unexpressible: you could lengthen a day and never shorten one.
A `closed` row is the same mechanism saying zero. MOD-019's rule that a dated window binds
only its own date is kept -- "open specially this Sunday" must not touch the rest of the week.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

#: How far forward `due_at` will walk before giving up. A target that cannot be met inside two
#: years of business hours is a calendar with almost no open time in it, and walking for ever
#: is how a request thread stops answering -- MOD-019's year-9999 rule, which walked `day +=
#: timedelta(days=1)` off the end of `date` and answered 500 with the draft already committed.
MAX_DAYS = 730


class SlaError(ValueError):
    """An input this module refuses rather than guessing at."""


@dataclass(frozen=True, slots=True)
class Window:
    """One row of `plt01.tsk_business_hours`, as the arithmetic needs it.

    `weekday` is 0-Monday, which is `date.weekday()`'s convention and the schema's. It is a
    *storage* convention and says nothing about which day a week starts on for a reader --
    MOD-019 learned that one separately, when a rota grid started on Monday because the
    storage did.
    """

    kind: str
    weekday: int | None
    on_date: date | None
    opens_at: time | None
    closes_at: time | None

    def __post_init__(self) -> None:
        if self.kind not in ("open", "closed"):
            raise SlaError(f"{self.kind!r} is not a calendar window kind")
        if (self.weekday is None) == (self.on_date is None):
            raise SlaError("a window is anchored to a weekday or a date, and to exactly one")
        if self.kind == "open" and (self.opens_at is None or self.closes_at is None):
            raise SlaError("an open window states its hours")
        if self.kind == "closed" and (self.opens_at is not None
                                      or self.closes_at is not None):
            # **Mirrors `tsk_business_hours_open_has_hours`, and it was missing.** The schema
            # refuses a closed window carrying hours and this did not, so a `Window` the
            # database cannot hold was constructible -- which is the "fixture encoding a
            # state the system cannot produce" shape, available in the production type.
            # Found by a mutation that came back uncaught because the guard it removed was
            # subsumed only by accident.
            raise SlaError("a closed window states no hours; it states a day")
        if self.kind == "closed" and self.on_date is None:
            raise SlaError(
                "a closed window is dated: 'closed every Tuesday' is the absence of a "
                "Tuesday open window, and two ways to say it would let them disagree")


def _merge(spans: list[tuple[time, time]]) -> list[tuple[time, time]]:
    """Overlapping windows merged, because otherwise their overlap is counted twice.

    MOD-019 shipped this defect and a test caught it: a rota widened by *adding* a second row
    rather than editing the first reported eight hours where six were open, and that figure is
    the denominator of a utilisation report. A calendar does the same thing -- "we also open
    11:00-15:00 on Tuesdays" is how somebody records a change.
    """
    out: list[tuple[time, time]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def spans_on(windows: tuple[Window, ...], day: date) -> list[tuple[time, time]]:
    """The open spans on one local date, merged.

    **A dated row replaces the weekly pattern**, and that includes a dated `closed`, which
    produces no spans at all. An empty answer here means "closed that day"; an empty *calendar*
    means something else entirely and is the caller's to distinguish -- see `has_hours`.
    """
    dated = [w for w in windows if w.on_date == day]
    if dated:
        # **No `kind == "open"` here, and that is deliberate.** With the invariant above, a
        # closed window has no hours and the `is not None` filter is the whole test -- so the
        # `kind` check was subsumed, which a mutation proved by removing it and changing
        # nothing. A subsumed guard is deleted rather than tested harder, which is the
        # judgement this build records for MOD-016's redundant kind domain.
        return _merge([
            (w.opens_at, w.closes_at) for w in dated
            if w.opens_at is not None and w.closes_at is not None])
    weekly = [
        w for w in windows
        if w.weekday == day.weekday() and w.kind == "open"
        and w.opens_at is not None and w.closes_at is not None]
    return _merge([(w.opens_at, w.closes_at) for w in weekly])  # type: ignore[misc]


def has_hours(windows: tuple[Window, ...]) -> bool:
    """Whether this calendar states any business hours at all.

    **"No calendar" is not "closed all week", and conflating them is a real defect.** MOD-019's
    first version read an empty rota as "never available" and nothing could be scheduled in a
    tenant at all. Here the consequence is the opposite and worse: a clock that never advances
    is a breach that never fires, so a caller with no calendar must fall back to elapsed
    wall-clock time rather than to zero.
    """
    return any(w.kind == "open" for w in windows)


def _day_spans_utc(
    windows: tuple[Window, ...], zone: ZoneInfo, day: date,
) -> list[tuple[datetime, datetime]]:
    """One local day's open spans, as instants.

    The conversion is per span and the difference is taken afterwards, which is what makes a
    clock change come out right with no special case: the local hours are what the calendar
    says and the elapsed time is what the member waited.
    """
    out = []
    for opens, closes in spans_on(windows, day):
        start = datetime.combine(day, opens, tzinfo=zone).astimezone(UTC)
        end = datetime.combine(day, closes, tzinfo=zone).astimezone(UTC)
        if end > start:
            out.append((start, end))
    return out


def _overlap(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> timedelta:
    low, high = max(a[0], b[0]), min(a[1], b[1])
    return high - low if high > low else timedelta(0)


def open_seconds(
    windows: tuple[Window, ...], timezone: str, *, frm: datetime, to: datetime,
    paused: tuple[tuple[datetime, datetime], ...] = (),
) -> int:
    """Business seconds between two instants, minus any paused spans.

    **A pause is subtracted from the open time and not from the elapsed time**, because a
    clock paused overnight was not running anyway -- subtracting it twice is how a target
    silently doubles. The pauses are intersected with the open spans for that reason.
    """
    if to < frm:
        raise SlaError("an SLA span ends after it starts")
    zone = ZoneInfo(timezone)
    if not has_hours(windows):
        # Stated rather than silently zero: see `has_hours`.
        raise SlaError(
            "this location states no business hours, so a business-hours clock cannot be "
            "computed against it; the caller falls back to elapsed time and says so")
    if (to - frm).days > MAX_DAYS:
        raise SlaError(f"an SLA span is at most {MAX_DAYS} days")
    total = timedelta(0)
    day = frm.astimezone(zone).date() - timedelta(days=1)
    last = to.astimezone(zone).date() + timedelta(days=1)
    while day <= last:
        for span in _day_spans_utc(windows, zone, day):
            inside = _overlap(span, (frm, to))
            if inside:
                total += inside
                for pause in paused:
                    total -= _overlap(span, (max(pause[0], frm), min(pause[1], to)))
        day += timedelta(days=1)
    return max(0, int(total.total_seconds()))


def due_at(
    windows: tuple[Window, ...], timezone: str, *, started_at: datetime,
    target_seconds: int,
) -> datetime:
    """When a target expires, walking forward through open time.

    Returned as an instant, because that is what a reader renders and a local time would
    have to be re-converted by every one of them -- the ambiguity the schedule board was
    bitten by.

    **This walks forward from whatever instant it is given, which is what makes it usable on
    a clock that has stopped.** Called with the start and the whole target it answers "when
    would this have been due had it never paused", which is not a question anybody asks of a
    paused clock; `service.read_clock` calls it with *now* and what is *left*, so a pause
    moves the date rather than being subtracted from a figure beside one that ignores it.
    """
    if target_seconds <= 0:
        raise SlaError("an SLA target is a positive number of seconds")
    zone = ZoneInfo(timezone)
    if not has_hours(windows):
        raise SlaError(
            "this location states no business hours, so a business-hours target has no due "
            "instant; the caller falls back to elapsed time and says so")
    remaining = timedelta(seconds=target_seconds)
    day = started_at.astimezone(zone).date()
    for _ in range(MAX_DAYS):
        for span in _day_spans_utc(windows, zone, day):
            start = max(span[0], started_at)
            if start >= span[1]:
                continue
            available = span[1] - start
            if available >= remaining:
                return start + remaining
            remaining -= available
        day += timedelta(days=1)
    raise SlaError(
        f"this target is not reachable within {MAX_DAYS} days of business hours, which "
        "means the calendar has almost no open time in it")


def state(
    *, consumed_seconds: int, target_seconds: int, warn_at_fraction: float = 0.8,
) -> str:
    """`running`, `warning` or `breached`, measured in the frame the target is stated in.

    **Two integers, because a state derived from a different pair of numbers than the
    remaining time can contradict it.** The first version compared `now` against a due
    instant walked forward from the start, and got two things wrong in one expression --
    neither of which this module's own tests could see, because both readers of that state
    did not exist yet.

    A pause was invisible to it: `due_at` knows nothing about `tsk_sla_pauses`, so a clock
    stopped for a week read `breached` beside a `remaining_seconds` well above zero, which
    makes the pause decorative on the one field anybody acts on -- MOD-019's "a field stored
    beside a decision and never read is not a parameter, it is a comment". And the warning
    was `(now - started) / (due - started)`, wall-clock over wall-clock, in the module whose
    entire subject is that those are not the same thing: a target opened at five on Friday
    is 80% of the way to a Monday deadline by Sunday evening with no business second spent.

    So the inputs are what `open_seconds` already answers and what the row already states,
    and the threshold is a fraction of the target rather than of an interval. The "a
    fraction of what" question the previous signature had to answer with `started_at`
    disappears, because the denominator is now the only number that was ever a promise.
    """
    if not 0 < warn_at_fraction < 1:
        raise SlaError("the warning threshold is a fraction between 0 and 1")
    if target_seconds <= 0:
        raise SlaError("an SLA target is a positive number of seconds")
    if consumed_seconds >= target_seconds:
        return "breached"
    return "warning" if consumed_seconds / target_seconds >= warn_at_fraction else "running"
