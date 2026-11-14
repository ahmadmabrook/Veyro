"""OPS-01-R05's conflict detection, and the override paragraph 1842 makes a Critical Control.

**Every conflict is named, and the override is a permission rather than a flag.** Paragraph
1842: "Resource conflicts cannot be overridden without permission and reason." So this module
answers with a list of conflicts a human can read, and the service charges a distinct permission
and demands a written reason to publish over one. A boolean would make the override a body
field, which is the shape every review in this build has found.

**Detection is pure and takes what it compares.** The service reads the overlapping sessions
and hands them over; nothing here touches a connection. That is what makes a conflict check
usable as a *preview* -- paragraph 1838's "member impact preview" and paragraph 1841's
"impact-assessed before publication" both need the answer before anything is written, and a
detector that queried as it went could not be asked a hypothetical.

**An exclusive resource conflicts on overlap; a countable one conflicts on the total.** Two
classes cannot have the same coach, and twenty-five bikes booked against twenty is a conflict
even though neither session alone exceeds it. Those are different arithmetic, so the kind
decides which applies and `resources.is_exclusive` is the single place that says which is which.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.scheduling.availability import Placement
from app.scheduling.recurrence import ScheduleError
from app.scheduling.resources import (
    Requirement,
    Resource,
    check_requirement_shape,
    is_exclusive,
)

#: What kind of clash this is. Each is a different remedy, which is why they are not one
#: `conflict` with a message: `double_booked` means move one session, `over_capacity` means
#: reduce a requirement or find more equipment, `unavailable` means change the rota, and
#: `travel` means the two sites are too far apart for one person.
CONFLICT_KINDS: tuple[str, ...] = (
    "double_booked", "over_capacity", "unavailable", "travel", "closed",
    #: A resource that exists but is at another site. Its own kind, because the remedy is
    #: different from every other one here: nothing is busy and nothing is shut, somebody has
    #: required the wrong resource.
    "elsewhere",
)


@dataclass(frozen=True)
class Held:
    """A resource another session already holds over a window.

    `session_id` is carried so a conflict can name the session it clashes with: "the coach is
    teaching Spin at 18:00" is actionable and "the coach is busy" is not.
    """

    resource_id: str
    kind: str
    quantity: int
    placement: Placement
    session_id: str
    session_label: str


@dataclass(frozen=True)
class Conflict:
    """One reason a placement cannot happen, in terms somebody can act on."""

    kind: str
    resource_id: str | None
    detail: str
    #: The session this clashes with, where there is one. `unavailable` and `closed` have none.
    with_session_id: str | None = None


def overlaps(first: Placement, second: Placement) -> bool:
    """Whether two placements share any time.

    **Touching is not overlapping.** A class ending at 18:00 and the next starting at 18:00 do
    not clash: the half-open interval is what makes back-to-back scheduling possible at all,
    and the setup and cleanup minutes in `capacity` are how a tenant asks for a gap.
    """
    return first.starts_at < second.ends_at and second.starts_at < first.ends_at


def detect(
    placement: Placement,
    requirements: list[Requirement],
    resources: dict[str, Resource],
    held: list[Held],
    *,
    session_id: str | None = None,
) -> list[Conflict]:
    """Every conflict this placement has against what is already held.

    `session_id` is the session being moved, where one is: its own existing holds are excluded,
    because a session always clashes with itself and reporting that would make every change
    look impossible.
    """
    # **Every requirement is checked for shape**, which none were: `detect` is documented as
    # the authority on whether a placement works and accepted a requirement for zero or minus
    # five of something, reporting no conflict against a resource that was entirely held. The
    # schema refused the row later, which is not the same as this module deciding.
    #
    # The *shape* rather than the whole authoring rule: `detect_session_conflicts` rebuilds
    # requirements from what a session already holds, where twenty bikes are one named row with
    # a quantity of twenty -- which `check_requirement`'s "a named requirement is for one
    # resource" correctly refuses of a template and would wrongly refuse here.
    for requirement in requirements:
        check_requirement_shape(requirement)
    out: list[Conflict] = []
    others = [h for h in held if h.session_id != session_id and overlaps(h.placement, placement)]
    #: **A resource at another site does not satisfy a requirement here.** `Resource` and
    #: `Placement` have both carried a `location_id` from the start and nothing compared them,
    #: so a class could be published at one site holding a room and an instructor at another --
    #: two harms at once, because the schedule sends members to a room that is not there and
    #: the room is genuinely held, so the real class at the owning site is refused it. A
    #: resource with no location travels: a service format and a coach with no base are not
    #: tied to a building. Found by review.
    here = {
        rid: r for rid, r in resources.items()
        if placement.location_id is None or r.location_id is None
        or r.location_id == placement.location_id}
    for requirement in requirements:
        if requirement.resource_id is not None:
            resource = resources.get(requirement.resource_id)
            if resource is None:
                raise ScheduleError(
                    f"this session requires a resource that does not exist: "
                    f"{requirement.resource_id}")
            if requirement.resource_id not in here:
                out.append(Conflict(
                    kind="elsewhere", resource_id=resource.resource_id,
                    detail=(f"{resource.kind} {resource.resource_id} is at another site and "
                            f"this session is at {placement.location_id}")))
                continue
            out.extend(_for_named(requirement, resource, others))
        else:
            out.extend(_for_kind(requirement, here, others))
    return out


def _for_named(
    requirement: Requirement, resource: Resource, others: list[Held],
) -> list[Conflict]:
    """Conflicts for a requirement that names one resource."""
    clashing = [h for h in others if h.resource_id == resource.resource_id]
    if not clashing:
        return []
    if is_exclusive(resource.kind):
        # **Every clash, not the first.** An operator who frees the earliest one and republishes
        # met the next, which is the "sent round twice" failure `summarise`'s own docstring
        # argues against -- and it argued against it while this returned `clashing[0]`.
        return [Conflict(
            kind="double_booked", resource_id=resource.resource_id,
            detail=(f"{resource.kind} {resource.resource_id} is already held by "
                    f"{clash.session_label}"),
            with_session_id=clash.session_id) for clash in clashing]
    # Countable, and named: twenty of the gym's bikes are one resource row, so a named
    # requirement for it still competes with everything else holding it.
    taken = sum(h.quantity for h in clashing)
    if taken + requirement.quantity > resource.quantity:
        return [Conflict(
            kind="over_capacity", resource_id=resource.resource_id,
            detail=(f"{resource.resource_id} has {resource.quantity}, {taken} are held and "
                    f"this session needs {requirement.quantity}"),
            with_session_id=clashing[0].session_id)]
    return []


def _for_kind(
    requirement: Requirement, resources: dict[str, Resource], others: list[Held],
) -> list[Conflict]:
    """Conflicts for a requirement that names a kind and a count.

    **Satisfiable by any free one, so the conflict is "there are not enough".** Which resource
    a session ends up with is the service's choice when it assigns; what this reports is that
    no assignment exists, because reporting one candidate's clash would send an operator to
    free up a room that was never the only option.
    """
    candidates = [r for r in resources.values() if r.kind == requirement.kind]
    if not candidates:
        return [Conflict(
            kind="over_capacity", resource_id=None,
            detail=f"this tenant has no {requirement.kind} to schedule against")]
    if is_exclusive(requirement.kind):
        busy = {h.resource_id for h in others if h.kind == requirement.kind}
        free = [r for r in candidates if r.resource_id not in busy]
        if len(free) < requirement.quantity:
            return [Conflict(
                kind="double_booked", resource_id=None,
                detail=(f"{requirement.quantity} of {requirement.kind} needed and "
                        f"{len(free)} of {len(candidates)} are free"),
                with_session_id=next(
                    (h.session_id for h in others if h.kind == requirement.kind), None))]
        return []
    total = sum(r.quantity for r in candidates)
    taken = sum(h.quantity for h in others if h.kind == requirement.kind)
    if taken + requirement.quantity > total:
        return [Conflict(
            kind="over_capacity", resource_id=None,
            detail=(f"{requirement.kind}: {total} exist, {taken} are held and this session "
                    f"needs {requirement.quantity}"),
            with_session_id=next(
                (h.session_id for h in others if h.kind == requirement.kind), None))]
    return []


def requires_override(conflicts: list[Conflict]) -> bool:
    """Whether publishing over these needs the override permission.

    **Any conflict does**, including `unavailable`: a session outside a coach's hours is a
    change to somebody's working day, and "the rota says no" is exactly the refusal an operator
    would otherwise click past. The permission and the written reason are what paragraph 1842
    asks for, and the distinction between a serious clash and a trivial one is a judgement for
    the person holding that permission rather than a rule here.
    """
    for conflict in conflicts:
        if conflict.kind not in CONFLICT_KINDS:
            raise ScheduleError(f"{conflict.kind!r} is not a conflict kind")
    return bool(conflicts)


def summarise(conflicts: list[Conflict]) -> str:
    """The conflicts as one sentence, for a refusal a person reads.

    Every conflict, not the first: an operator who fixes the room clash and then discovers the
    coach clash has been sent round twice by a detector that knew both.
    """
    if not conflicts:
        return "no conflicts"
    return "; ".join(f"{c.kind}: {c.detail}" for c in conflicts)
