"""OPS-01-R06's publishing, and the effective dating paragraph 1841 makes a Critical Control.

**"All schedule changes are effective-dated and impact-assessed before publication."** Two
obligations in one sentence, and they are different:

  * **Effective-dated** means a change says when it starts applying, and instances before that
    date are left alone. A rota change made in March for April does not rewrite March.
  * **Impact-assessed before publication** means the assessment is computable *without*
    writing anything, and the publish takes it. So `assess` is pure and the service calls it
    first; a design that assessed as it published would have nothing to show a human.

**A draft and its published form are the same template at two versions, not two rows with a
flag.** Paragraph 4149 keeps the definition separate from the occurrences, and the version is
what an instance snapshots -- so an instance can always say which version of which template it
came from, which is the question after somebody edits a recurring class.

**The impact is counted in members, not in sessions.** Paragraph 1838 asks for a "member impact
preview", and "forty-one sessions change" is a number an operator cannot act on while "nine
members lose a booked place" is. This module cannot count members -- bookings are MOD-020's --
so it counts the sessions *that have holds* and reports the hold count, which is the nearest
true statement from inside the module boundary.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from app.scheduling.recurrence import ScheduleError

#: A template's lifecycle. `draft` is editable, `published` generates instances, `retired`
#: generates no more and leaves what it generated standing. **No `deleted`**: a template whose
#: instances exist is the only answer to "where did this class come from", and deleting it
#: would orphan every instance it made.
STATUSES: tuple[str, ...] = ("draft", "published", "retired")

#: Which moves are allowed. A published template is edited by publishing a new version, not by
#: going back to draft -- the demotion MOD-013's review found was a two-step rewrite of
#: already-approved content, and the same trick here would change a class members have booked.
EDGES: dict[str, tuple[str, ...]] = {
    "draft": ("published",),
    "published": ("retired",),
    "retired": (),
}

#: How a published instance can be affected by a change. Each is a different conversation with
#: the member, which is why they are counted separately rather than summed.
IMPACTS: tuple[str, ...] = ("unchanged", "moved", "cancelled", "added")


@dataclass(frozen=True)
class Instance:
    """A generated session, as the impact assessment needs it."""

    session_id: str
    starts_at: datetime
    ends_at: datetime
    #: The date in the session's own zone, which is what `effective_from` is compared against.
    #: Optional so a caller assessing a proposal it has not stored can leave it out; the UTC
    #: date is the fallback and differs from it by a few hours either side of midnight.
    local_date: date | None = None
    #: How many places are held on it. From this module's own hold rows, so it is a fact rather
    #: than a guess about MOD-020's tables.
    held: int = 0


@dataclass(frozen=True)
class Impact:
    """What publishing a change would do. The preview paragraph 1838 asks for."""

    effective_from: date
    unchanged: int
    moved: int
    cancelled: int
    added: int
    #: The places held on the instances that move or vanish. The number an operator weighs.
    places_affected: int
    #: The earliest affected session, so a preview can say "from Tuesday" rather than a count.
    first_affected_at: datetime | None


def _local_day(instance: Instance) -> date:
    """The date the member knows this session is on.

    `local_date` when the caller supplies it, and the UTC date otherwise. The session row
    carries both for paragraph 4150's reason, and scope has to be compared against the local
    one: `effective_from` is a date somebody typed, in the tenant's own terms.
    """
    return instance.local_date or instance.starts_at.date()


def check_transition(current: str, target: str) -> None:
    if current not in STATUSES:
        raise ScheduleError(f"{current!r} is not a schedule template status")
    if target not in STATUSES:
        raise ScheduleError(f"{target!r} is not a schedule template status")
    if target not in EDGES[current]:
        raise ScheduleError(f"a schedule template does not move from {current} to {target}")


def check_effective_from(effective_from: date, *, today: date) -> None:
    """Refuse an effective date that rewrites the past.

    **Not in the past, which is the whole of "effective-dated".** A change effective last
    Tuesday would move sessions members already attended, and no row afterwards could say what
    the schedule had been on the day. Today is allowed: a mistake found this morning is fixed
    this morning.
    """
    if effective_from < today:
        raise ScheduleError(
            f"a schedule change takes effect today or later; {effective_from.isoformat()} is "
            f"in the past and sessions before it have already happened")
    if (effective_from - today).days > 400:
        raise ScheduleError("a schedule change takes effect within a year")


def assess(
    existing: list[Instance], proposed: list[Instance], *, effective_from: date,
    today: date,
) -> Impact:
    """What publishing would do to the instances from `effective_from` onwards.

    **Matched on the start instant and the slot, because that is what a member knows.** A
    session that keeps its time is `unchanged` whatever else moved about it; one whose time
    changes is `moved`, counted once rather than as a cancellation and an addition, because
    telling a member their class moved is one conversation and telling them it was cancelled
    and another added is two.

    **Every existing instance is counted, including two at one instant.** The first version
    keyed a dict on `starts_at`, so a tenant running two classes at six o'clock in two studios
    had one of them silently dropped -- and *which* one depended on list order, because the
    later row overwrote the earlier. Three rooms over five days reported five cancellations and
    a third of the held places. With the empty studio listed last, a publish that cancelled
    both reported zero places affected, needed no acknowledgement under paragraph 1841 and
    raised no notification under 1838. A pure function that answers differently depending on
    the order of a list it does not control is wrong whatever builds the list. Found by review.

    **Scope is the local date**, not the UTC one: `effective_from` is a date an operator typed
    and the session carries the local date the member knows. At UTC+3 a session at 23:30Z on
    the 4th is half past two in the morning on the 5th, and comparing the UTC date put it out
    of scope for a change effective on the 5th.

    Instances before `effective_from` are not counted at all -- not as unchanged either, since
    the change does not reach them and including them would inflate the preview with sessions
    nobody is deciding about.
    """
    check_effective_from(effective_from, today=today)
    in_scope = [i for i in existing if _local_day(i) >= effective_from]
    proposed_in_scope = [i for i in proposed if _local_day(i) >= effective_from]
    #: **The slot is the instant and the span**, so a class whose duration changes is not
    #: "unchanged": `ends_at` is carried on `Instance` for no other purpose, and a sixty-minute
    #: class republished as fifteen minutes reported that nothing changed at all.
    def slot(instance: Instance) -> tuple[datetime, datetime]:
        return (instance.starts_at, instance.ends_at)

    before = Counter(slot(i) for i in in_scope)
    after = Counter(slot(i) for i in proposed_in_scope)
    unchanged_count = sum((before & after).values())
    gone_slots = before - after
    added_count = sum((after - before).values())
    gone_count = sum(gone_slots.values())
    # **A gone slot paired with an added one is a move**, and the pairing is by count: as many
    # moves as there are of each. That is what a weekly class shifting by an hour looks like,
    # and pairing them keeps the preview honest about how much is really changing.
    moved = min(gone_count, added_count)
    cancelled = gone_count - moved
    #: The instances behind the gone slots, all of them -- this is where the collapsed
    #: duplicate used to be lost, and `places_affected` is the number an operator weighs.
    remaining = Counter(gone_slots)
    affected = []
    for instance in in_scope:
        key = slot(instance)
        if remaining[key]:
            remaining[key] -= 1
            affected.append(instance)
    return Impact(
        effective_from=effective_from,
        unchanged=unchanged_count,
        moved=moved,
        cancelled=cancelled,
        added=added_count - moved,
        places_affected=sum(i.held for i in affected),
        first_affected_at=min((i.starts_at for i in affected), default=None),
    )


def needs_notification(impact: Impact) -> bool:
    """Whether publishing this change has to tell somebody.

    **Any held place on a session that moves or vanishes.** Paragraph 1838 asks for a
    "notification plan", and the plan is MOD-013's; what this decides is whether there is
    anything to notify about. A change that touches only empty sessions is a schedule edit, and
    mailing everybody about it is how a tenant trains its members to ignore the mail.
    """
    return impact.places_affected > 0


def describe(impact: Impact) -> str:
    """The impact as a sentence, for a preview and for the published event's summary."""
    parts = []
    if impact.moved:
        parts.append(f"{impact.moved} moved")
    if impact.cancelled:
        parts.append(f"{impact.cancelled} cancelled")
    if impact.added:
        parts.append(f"{impact.added} added")
    if not parts:
        return f"nothing changes from {impact.effective_from.isoformat()}"
    summary = ", ".join(parts)
    if impact.places_affected:
        summary += f"; {impact.places_affected} held place(s) affected"
    return f"from {impact.effective_from.isoformat()}: {summary}"
