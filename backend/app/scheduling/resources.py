"""OPS-01-R01's resource model: what a session needs before it can happen.

**One scheduling engine for every bookable thing**, which paragraph 1831 asks for in one
sentence: "classes, PT, consultations, assessments, facilities, rooms, courts and equipment".
The way to have one engine rather than seven is to make all of those the same shape -- a
resource with a kind -- and to put what differs in the *requirement*, not in the resource.

**A requirement names a kind and a count, or it names a resource.** "A studio" and "that
studio" are different bookings: the first can be satisfied by whichever room is free, and the
second cannot. Composite requirements (paragraph 1833) are then just a list: a spin class needs
one instructor, one studio and twenty bikes, and the conflict detector checks each.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.scheduling.recurrence import ScheduleError

#: What a resource is. **Seven kinds, from paragraph 1833 verbatim**, because a kind is a fact
#: about what this software schedules and a per-tenant list would let two tenants disagree about
#: whether a court is a space -- which the conflict detector has to know, since two things can
#: share a room and two bookings of one court cannot.
KINDS: dict[str, str] = {
    # People. Double-booking one is the conflict members notice first.
    "staff": "person",
    # Space. A room, a studio, a zone of the floor.
    "room": "space",
    "zone": "space",
    "court": "space",
    # Countable things. Twenty bikes is one resource with a capacity of twenty, not twenty rows:
    # the question a booking asks is "are there enough", never "which one".
    "equipment": "countable",
    # A service is what is being delivered rather than what delivers it -- a class format, a
    # consultation type. It carries the requirements and the capacity policy.
    "service": "offering",
    # A composite is a named bundle of requirements: "spin studio" meaning the room and its
    # bikes, so a schedule template names one thing and the engine expands it.
    "composite": "offering",
}

#: The kinds a conflict is possible on. A service and a composite are descriptions rather than
#: things that can be in two places, so they are not double-bookable: the resources they expand
#: to are.
EXCLUSIVE_KINDS: frozenset[str] = frozenset({"staff", "room", "zone", "court"})


@dataclass(frozen=True)
class Resource:
    """One bookable thing, as the decisions need it."""

    resource_id: str
    kind: str
    #: For `equipment`: how many there are. One for everything else, and the schema makes a
    #: capacity above one meaningless for an exclusive kind.
    quantity: int = 1
    #: Where it is. A room cannot move; a member of staff can, which is what the travel buffer
    #: in `availability` is about.
    location_id: str | None = None


@dataclass(frozen=True)
class Requirement:
    """What a session needs. Either a named resource or a count of a kind, never both."""

    kind: str
    quantity: int = 1
    #: Set to require *that* resource: the senior instructor, court three.
    resource_id: str | None = None


def check_resource(resource: Resource) -> None:
    if resource.kind not in KINDS:
        raise ScheduleError(f"{resource.kind!r} is not a resource kind")
    if resource.quantity < 1:
        raise ScheduleError("a resource exists at least once")
    if resource.quantity > 1 and resource.kind in EXCLUSIVE_KINDS:
        raise ScheduleError(
            f"a {resource.kind} is one thing; a quantity above one belongs to equipment")
    if resource.quantity > 10_000:
        raise ScheduleError("a resource quantity is at most 10000")


def check_requirement_shape(requirement: Requirement) -> None:
    """The part of a requirement that has to hold for anything to decide about it.

    **Split from `check_requirement` because the rest is an authoring rule.** "A named
    requirement is for one resource" is true of a *template's* requirements, which is what a
    person writes; it is not true of a requirement reconstructed from what a session already
    holds, where twenty bikes are one row with a quantity of twenty. `conflicts.detect` is
    handed both kinds, so it checks this and the authoring path checks both.
    """
    if requirement.kind not in KINDS:
        raise ScheduleError(f"{requirement.kind!r} is not a resource kind")
    if requirement.quantity < 1:
        raise ScheduleError("a requirement is for at least one")
    if requirement.quantity > 10_000:
        raise ScheduleError("a requirement is for at most 10000")


def check_requirement(requirement: Requirement) -> None:
    """A requirement as a template author writes it."""
    check_requirement_shape(requirement)
    if requirement.resource_id is not None and requirement.quantity != 1:
        raise ScheduleError(
            "a requirement naming a particular resource is for that one resource")
    if requirement.kind in ("service", "composite") and requirement.resource_id is None:
        raise ScheduleError(
            f"a {requirement.kind} requirement names which one, because the kind alone "
            f"describes nothing a session can hold")


def check_requirements(requirements: list[Requirement]) -> None:
    """A session's whole requirement list.

    **A kind appears once.** Two requirements for `room` are a composite that was not modelled:
    the engine would satisfy them independently and nothing would say the two rooms have to be
    different, or the same. Refusing is the honest answer until there is a case for either.
    """
    if not requirements:
        raise ScheduleError("a session requires something; otherwise it is a note in a diary")
    if len(requirements) > 20:
        raise ScheduleError("a session has at most twenty requirements")
    for requirement in requirements:
        check_requirement(requirement)
    named = [r.resource_id for r in requirements if r.resource_id is not None]
    if len(set(named)) != len(named):
        raise ScheduleError("a particular resource is required once")
    anonymous = [r.kind for r in requirements if r.resource_id is None]
    if len(set(anonymous)) != len(anonymous):
        raise ScheduleError(
            "a kind is required once; two requirements for one kind cannot say whether they "
            "mean the same resource or different ones")


def is_exclusive(kind: str) -> bool:
    """Whether two sessions holding this kind at once is a conflict.

    The one question the conflict detector asks of a kind, so it is answered here rather than
    by a membership test spelled out at each call site.
    """
    if kind not in KINDS:
        raise ScheduleError(f"{kind!r} is not a resource kind")
    return kind in EXCLUSIVE_KINDS
