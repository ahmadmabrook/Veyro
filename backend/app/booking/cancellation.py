"""What the members of a cancelled class get. ADM-SCH-07, ADR-0016.

**The remedy is required, which is the whole screen.** The canvas's own last sentence: "Cannot
commit without choosing what the members get. A cancellation that notifies nobody is the most
damaging thing this screen could permit, so the notification is the action rather than a
follow-up." So there is no default here and no `None`: a caller that has not decided is refused
before anything is written.

**A move is not a new booking** (ADR-0016 D3). The member already held a place, so moving them
to a replacement class is not re-evaluated against their weekly quota or their concurrent-booking
limit -- doing that would refuse the members whose quota *the cancelled class itself* consumed,
which is the product punishing somebody for a class the gym called off. What is still evaluated
is the destination's own capacity, which is MOD-019's row lock, and the destination's own
eligibility, because it is a different session with its own restrictions and a fourteen-year-old
must not be moved onto an 18+ class.

**Earliest booking first, and the shortfall is disclosed rather than resolved** (D4). The canvas
states the arithmetic -- "6 places free · 12 would need to choose another" -- so the order is the
order the bookings were made, which is `settle_session_bookings`' own order and the waitlist's
position rule. Nobody who does not fit is quietly given a credit instead: the manager chose to
move them, and silently doing something else to two thirds of them would make the drawn message,
which says a place has been held, false for twelve of eighteen people.

**No message is composed here** (D10). "Sent in each member's language" is the canvas's
requirement and this process has no message catalogue, so what crosses the wire is the facts a
message is made of and the screen renders one preview in the reader's own language.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: What a manager may choose. There is no third value and no absence: see the module docstring.
REMEDIES = ("move", "credit")

#: Why a member was not moved, from a closed set, because a surface decides what to offer from
#: it and free prose would make that a string comparison -- MOD-016's finding, where four
#: English words were the whole enforcement of a usage limit.
NOT_MOVED = ("no_place", "already_booked", "ineligible")

#: "Usable on any class within 30 days", from the canvas. Stated here rather than configured
#: because the canvas states it and nothing in this build records a goodwill window.
CREDIT_DAYS = 30


class CancellationError(ValueError):
    """A remedy that is not one, or one that names the wrong things."""


@dataclass(frozen=True)
class Remedy:
    """What the members get, as the caller stated it.

    `to_session_id` belongs to a move and to nothing else. A credit names no session, because
    the policy it is granted against is derived from the tenant's own catalogue (D6) -- a
    caller naming one would be choosing which right they hand out.
    """

    kind: str
    to_session_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in REMEDIES:
            raise CancellationError(
                f"{self.kind!r} is not something the members can be given")
        if self.kind == "move" and not self.to_session_id:
            raise CancellationError("a move names the class they are moved to")
        if self.kind == "credit" and self.to_session_id:
            raise CancellationError("a credit is not a move to another class")


@dataclass(frozen=True)
class Candidate:
    """One open booking on the cancelled session, and what the destination says about it."""

    booking_id: str
    person_id: str
    #: Already holds a live booking on the destination -- the ordinary case of somebody who
    #: booked both classes. `bkg_bookings_one_live_per_person` would refuse the move, so the
    #: whole command would fail on a member doing nothing unusual (D5).
    already_there: bool = False
    #: The destination's own restrictions, from `scheduling.check_eligibility_on`.
    eligible: bool = True
    #: Which restriction refused them, for the report. Never a reason the member is told.
    ineligible_because: str | None = None


@dataclass(frozen=True)
class Placement:
    booking_id: str
    person_id: str
    moved: bool
    reason: str | None = None
    ineligible_because: str | None = None


@dataclass(frozen=True)
class Allocation:
    placements: tuple[Placement, ...]

    @property
    def moving(self) -> tuple[Placement, ...]:
        return tuple(p for p in self.placements if p.moved)

    @property
    def must_choose(self) -> tuple[Placement, ...]:
        return tuple(p for p in self.placements if not p.moved)

    @property
    def moved_count(self) -> int:
        return len(self.moving)

    @property
    def must_choose_count(self) -> int:
        return len(self.must_choose)


def plan_moves(candidates: list[Candidate], *, free_places: int) -> Allocation:
    """Who gets a place on the replacement class, in the order they booked the first one.

    **A member who is already there is not counted against the free places**, because they are
    not taking one: they booked the destination themselves and their own place stands. Counting
    them would shorten the list for everybody behind them on the strength of a place nobody
    took.

    **An ineligible member is skipped rather than refused**, which is the direction the canvas
    sets: the manager asked for a move and the report says who could not have one. Refusing the
    whole cancellation because one member of eighteen is too young for the replacement class
    would leave the class running with no coach.
    """
    if free_places < 0:
        raise CancellationError("a class cannot have fewer than no places free")
    left = free_places
    placements: list[Placement] = []
    for candidate in candidates:
        if candidate.already_there:
            placements.append(Placement(
                candidate.booking_id, candidate.person_id, False, "already_booked"))
            continue
        if not candidate.eligible:
            placements.append(Placement(
                candidate.booking_id, candidate.person_id, False, "ineligible",
                candidate.ineligible_because))
            continue
        if left <= 0:
            placements.append(Placement(
                candidate.booking_id, candidate.person_id, False, "no_place"))
            continue
        left -= 1
        placements.append(Placement(candidate.booking_id, candidate.person_id, True))
    return Allocation(tuple(placements))


def credit_expires(at: datetime, *, days: int = CREDIT_DAYS) -> datetime:
    """When a goodwill class credit lapses.

    From the moment the class was cancelled rather than from the class's own time, because the
    member learns about it now and "within 30 days" is what they are told.
    """
    if days < 1 or days > 365:
        raise CancellationError("a credit window is between a day and a year")
    return at + timedelta(days=days)
