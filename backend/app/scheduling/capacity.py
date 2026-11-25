"""OPS-01-R04's capacity, setup and cleanup time, restrictions and entitlement checks.

**Capacity belongs to the schedule and reservations belong to booking.** Paragraph 4145 draws
the line: "Schedule owns published occurrences/resources/capacity. Booking owns member
reservation/waitlist/cancel/attendance intent." So this module decides how many a session can
take and who is eligible; MOD-020 decides whether a particular member gets one of the places.

**And the hold is on this side of the line, because the count has to be.** Paragraph 4146 wants
"optimistic concurrency or atomic reservation counters to prevent overbooking", and MOD-020
cannot read this module's tables to count what is taken ("no cross-domain write-table access").
So the schedule owns an atomic hold -- the same shape as MOD-017's entitlement reservation, for
the same reason -- and booking takes one. A stored `reserved_count` on the session would be the
cached total MOD-018 spent four reviews learning not to keep; the holds are the count.

**Setup and cleanup extend the window the resources are held for, not the session members see.**
A class from 18:00 to 19:00 with ten minutes of cleanup holds the studio until 19:10, and the
member's schedule still says 19:00. Conflating the two would either publish a class that runs
ten minutes longer than it does or let the next class walk into a room still being wiped down.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.scheduling.availability import Placement
from app.scheduling.recurrence import ScheduleError

#: What a session can refuse somebody for. **Four, each with a different remedy**: an age
#: restriction is a fact about the member, a skill one is about their record, an entitlement one
#: is about what they bought, and a capacity one is about the room. A booking denial has to say
#: which, because paragraph 1892 makes an understandable denial a Critical Control.
RESTRICTION_KINDS: tuple[str, ...] = ("min_age", "max_age", "skill", "entitlement")

#: The most a session can hold. A number above this is a typo, and the hold table would grow to
#: match it.
MAX_CAPACITY = 10_000

#: The most setup or cleanup a session can declare. Beyond an hour the gap is a second session.
MAX_MARGIN_MINUTES = 120


@dataclass(frozen=True)
class Policy:
    """A session's capacity policy. OPS-01-R04.

    `waitlist_capacity` is here rather than in MOD-020 because it is a property of the session
    -- how long a queue this class will hold -- while who is in the queue is booking's.
    """

    capacity: int
    setup_minutes: int = 0
    cleanup_minutes: int = 0
    waitlist_capacity: int = 0
    #: Overbooking, in places rather than a percentage: paragraph 1888 allows "controlled
    #: overbooking", and a percentage of a twelve-place class is a fraction somebody has to
    #: round. Zero is the default, because overbooking is a decision rather than a setting.
    #:
    #: **Named `overbook_places` rather than `overbook_by`**, because the privacy sweep's
    #: heuristic reads a `_by` suffix as an actor and flagged it -- and the right fix was the
    #: name rather than an exclusion. A sweep with one exception is a sweep that will grow a
    #: second, and the heuristic is what catches a real actor column nobody declared.
    overbook_places: int = 0


@dataclass(frozen=True)
class Restriction:
    """One eligibility rule on a session."""

    kind: str
    #: For `min_age` and `max_age`: years. For `skill` and `entitlement`: the key required.
    value: str


@dataclass(frozen=True)
class Candidate:
    """What is known about somebody being checked for eligibility.

    **Facts, not a verdict.** The caller supplies the member's age and what they hold, and this
    module decides -- which is the split that lets the same function answer a booking attempt
    and a "would this member be eligible" preview.
    """

    age_years: int | None = None
    skills: frozenset[str] = frozenset()
    entitlements: frozenset[str] = frozenset()


def check_policy(policy: Policy) -> None:
    if policy.capacity < 1:
        raise ScheduleError("a session holds at least one person")
    if policy.capacity > MAX_CAPACITY:
        raise ScheduleError(f"a session holds at most {MAX_CAPACITY}")
    for name, value in (("setup", policy.setup_minutes),
                        ("cleanup", policy.cleanup_minutes)):
        if value < 0:
            raise ScheduleError(f"{name} time is not negative")
        if value > MAX_MARGIN_MINUTES:
            raise ScheduleError(
                f"{name} time is at most {MAX_MARGIN_MINUTES} minutes; a longer gap is a "
                f"second session")
    if policy.waitlist_capacity < 0:
        raise ScheduleError("a waitlist holds nobody or somebody")
    if policy.waitlist_capacity > MAX_CAPACITY:
        raise ScheduleError(f"a waitlist holds at most {MAX_CAPACITY}")
    if policy.overbook_places < 0:
        raise ScheduleError(
            "overbooking is extra places, so it is not negative; fewer places is a smaller "
            "capacity")
    if policy.overbook_places > policy.capacity:
        raise ScheduleError(
            "overbooking beyond the capacity itself would make the room's own number "
            "meaningless")


@dataclass(frozen=True)
class Space:
    """A room, zone or court a template requires, and how many people it holds.

    `capacity` is `None` where the tenant has not stated one, which is the ordinary case for
    every resource registered before `0035` -- and it means this space does not bind rather
    than that it holds nobody. ADR-0018 D1.
    """

    resource_id: str
    resource_code: str
    capacity: int | None


@dataclass(frozen=True)
class PerAttendee:
    """Equipment a format takes per attendee, and how much of it is in the space.

    `available` is the sum of the `quantity` of the equipment rows *inside* the spaces the
    template requires -- which is the relation `0035` adds, because `location_id` is a club and
    a ceiling computed across clubs is a number about bikes nobody at this site can reach.

    `per_person` is the requirement's own quantity: two dumbbells each halves the room. The
    division is here rather than in the caller so the arithmetic has a test.
    """

    resource_code: str
    available: int
    per_person: int = 1

    def attendees(self) -> int:
        """How many people this equipment serves, rounded down."""
        if self.per_person < 1:
            raise ScheduleError("a per-attendee requirement is for at least one each")
        return self.available // self.per_person


@dataclass(frozen=True)
class Ceiling:
    """The most a class in these spaces with this equipment may offer, and what bound it.

    **The binding resource is part of the answer, not a lookup the caller repeats.** ADR-0018
    D6: "capacity 30 exceeds Studio 2, which holds 20" is actionable and "capacity too high"
    sends somebody to guess -- so the refusal and ADM-SCH-03's live check read the same two
    fields rather than each deciding how to word it.
    """

    #: `None` means nothing states a ceiling, which is not the same as a ceiling of zero: the
    #: canvas's sentence is about the rooms a tenant has described, and a tenant that has
    #: described none is unbound rather than unable to run a class.
    places: int | None
    #: The code of the space or the equipment that bound it, where one did.
    bound_by: str | None
    #: `space` or `equipment`, so a surface can word the two differently -- a room is rebuilt
    #: and a bike is bought, which are different remedies.
    bound_kind: str | None

    @property
    def binds(self) -> bool:
        return self.places is not None


def ceiling(
    spaces: list[Space], per_attendee: list[PerAttendee] | None = None,
) -> Ceiling:
    """The lowest ceiling these spaces and their per-attendee equipment impose. ADR-0018 D5.

    **ADM-SCH-06's sentence is the specification**: "capacity here is the ceiling every class
    inherits ... the constraint lives in one place, not in each scheduler's memory." So this is
    one function with two callers -- the capacity-policy write refuses a policy above it, and
    ADM-SCH-03's live check reports it before anybody saves. A figure a screen shows and a
    write then refuses is this build's one-module-two-definitions finding on the number a
    manager types.

    **A ceiling is not a default** (D2). This answers the most a class *may* offer; what it
    offers is its own policy's figure, which is what a session snapshots. Returning this as a
    capacity where a template states none would leave two columns able to disagree about how
    many places a session has.

    **The lowest wins, and ties go to the space.** Where a room holding twenty and twenty bikes
    both bind, the room is the one a reader can act on: a bike is bought and a wall is not
    moved, so naming the equipment first would send somebody to the cheaper remedy for a
    problem the room also has.
    """
    best: Ceiling = Ceiling(places=None, bound_by=None, bound_kind=None)
    for space in spaces:
        if space.capacity is None:
            continue
        if space.capacity < 1:
            raise ScheduleError("a space holds at least one person")
        if best.places is None or space.capacity < best.places:
            best = Ceiling(places=space.capacity, bound_by=space.resource_code,
                           bound_kind="space")
    for item in per_attendee or []:
        if item.available < 0:
            raise ScheduleError("equipment is not a negative quantity")
        serves = item.attendees()
        # **Strictly lower, so a tie leaves the space named**, which is the reading above.
        if best.places is None or serves < best.places:
            best = Ceiling(places=serves, bound_by=item.resource_code,
                           bound_kind="equipment")
    return best


def check_against_ceiling(policy: Policy, limit: Ceiling) -> None:
    """Refuse a policy that offers more places than the rooms and equipment allow.

    **The capacity, not the capacity plus overbooking.** Overbooking is a deliberate decision
    to admit more holds than places -- paragraph 1888's "controlled overbooking" -- and a
    ceiling that counted it would make the two settings fight: a tenant raising overbooking by
    two would find the class's own figure refused. What the room bounds is how many the class
    says it holds; whether the tenant then chooses to overbook it is theirs, and the honest
    place to say so is here rather than in a second ceiling.
    """
    check_policy(policy)
    if limit.places is not None and policy.capacity > limit.places:
        raise ScheduleError(
            f"a capacity of {policy.capacity} exceeds {limit.bound_by}, which allows "
            f"{limit.places}")


def check_restriction(restriction: Restriction) -> None:
    if restriction.kind not in RESTRICTION_KINDS:
        raise ScheduleError(f"{restriction.kind!r} is not a restriction kind")
    if not restriction.value.strip():
        raise ScheduleError("a restriction states what it requires")
    if restriction.kind in ("min_age", "max_age"):
        # **`isdecimal`, not `isdigit`.** `str.isdigit()` is true for Unicode superscripts and
        # other `No`-category digits that `int()` then refuses, so `'\u00b2'` passed this guard
        # and raised a bare `ValueError` two lines down -- which nothing in the request path
        # catches, so a template carrying it answered 500 instead of 422. `isdecimal` is the
        # predicate that matches what `int` accepts. Found by review.
        if not restriction.value.isdecimal():
            raise ScheduleError(f"{restriction.kind} is a number of years")
        if int(restriction.value) > 120:
            raise ScheduleError("an age restriction is at most 120 years")


def resource_window(placement: Placement, policy: Policy) -> Placement:
    """The window the resources are held for, which is the session plus its margins.

    Returned as a `Placement` so the conflict detector takes it unchanged: the detector should
    not have to know that setup time exists, and a caller that forgot to add it would publish a
    class that walks into the previous one's cleanup.
    """
    check_policy(policy)
    return Placement(
        starts_at=placement.starts_at - timedelta(minutes=policy.setup_minutes),
        ends_at=placement.ends_at + timedelta(minutes=policy.cleanup_minutes),
        location_id=placement.location_id)


def places(policy: Policy) -> int:
    """How many holds a session admits, including any overbooking."""
    check_policy(policy)
    return policy.capacity + policy.overbook_places


def check_hold(policy: Policy, *, held: int, wanted: int = 1) -> None:
    """Refuse a hold the session has no room for.

    `held` is counted from the hold rows by the caller, inside the transaction that is about to
    take the next one -- which is the whole of paragraph 4146: a count read outside the lock is
    a count two bookings can both read before either writes.
    """
    if wanted < 1:
        raise ScheduleError("a hold is for at least one place")
    if held < 0:
        raise ScheduleError("a session cannot hold a negative number of places")
    room = places(policy)
    if held + wanted > room:
        raise ScheduleError(
            f"this session has {room} places, {held} are held and {wanted} more was asked for")


def places_free(policy: Policy, *, held: int) -> int:
    """How many places are left, given what is held. The read half of `check_hold`.

    **One expression, because three callers had their own.** MOD-020 computed it inline in its
    eligibility path and again in its waitlist promotion, and ADM-SCH-07's cancellation needed
    it a third time -- which is this build's one-module-two-definitions finding waiting for the
    day somebody edits one of them. `held` is still the caller's, counted inside whatever
    transaction is about to act on the answer: the figure is only as fresh as the lock the
    caller holds, and that is `take_hold_on`'s business rather than this function's.

    **Never negative.** Overbooking can be *reduced* after the holds were taken, so a session
    can legitimately hold more places than it now has -- and a surface that printed a negative
    free count would be describing a mechanism this module does not have.
    """
    if held < 0:
        raise ScheduleError("a session cannot hold a negative number of places")
    return max(0, places(policy) - held)


def eligibility(
    restrictions: list[Restriction], candidate: Candidate,
) -> str | None:
    """Why this candidate cannot take a place, in a sentence, or None when they can.

    **A missing fact is a refusal, not a pass.** An age restriction on a session whose candidate
    has no date of birth cannot be evaluated, and treating "unknown" as "eligible" is how a
    twelve-year-old ends up in a class the insurer excluded. That is the asymmetry MOD-008's
    review established for deny policies, applied to a different question.
    """
    for restriction in restrictions:
        check_restriction(restriction)
    for restriction in sorted(restrictions, key=lambda r: r.kind):
        if restriction.kind == "min_age":
            if candidate.age_years is None:
                return (f"this session is for {restriction.value} and over, and this member's "
                        f"age is not recorded")
            if candidate.age_years < int(restriction.value):
                return f"this session is for {restriction.value} and over"
        elif restriction.kind == "max_age":
            if candidate.age_years is None:
                return (f"this session is for under {restriction.value}s, and this member's "
                        f"age is not recorded")
            if candidate.age_years > int(restriction.value):
                return f"this session is for under {restriction.value}s"
        elif restriction.kind == "skill":
            if restriction.value not in candidate.skills:
                return f"this session requires {restriction.value}"
        elif restriction.value not in candidate.entitlements:
            return f"this session requires the {restriction.value} entitlement"
    return None


def booking_window_open(
    placement: Placement, *, at: datetime, opens_hours_before: int,
    closes_minutes_before: int,
) -> str | None:
    """Whether the booking window is open, in a sentence when it is not.

    OPS-01-R04's lead time, decided here because the window is a property of the session rather
    than of the member -- MOD-020 adds the member's own eligibility on top.
    """
    if opens_hours_before < 0 or closes_minutes_before < 0:
        raise ScheduleError("a booking window is measured backwards from the session")
    if opens_hours_before > 24 * 365:
        raise ScheduleError("a booking window opens at most a year ahead")
    # **Both ends, because one bounded sibling is not a bound.** `closes_minutes_before` was
    # unbounded, and a large enough value overflows `timedelta` into an `OverflowError` --
    # which is not a `ValueError` and so not a `ScheduleError`, so it reaches a caller as a
    # 500. Unreachable through the route today because the column is bounded; a decision
    # function that relies on its caller's schema is not deciding.
    if closes_minutes_before > 60 * 24 * 365:
        raise ScheduleError("a booking window closes at most a year before")
    opens = placement.starts_at - timedelta(hours=opens_hours_before)
    closes = placement.starts_at - timedelta(minutes=closes_minutes_before)
    if at < opens:
        return f"booking opens at {opens.isoformat()}"
    if at > closes:
        return f"booking closed at {closes.isoformat()}"
    return None
