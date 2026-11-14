"""OPS-01-R07: instructor substitution, cancellation, relocation and attendance handoff.

**Four acts on a published session, and each leaves the session where it is.** A substitution
changes who teaches, a relocation changes where, a cancellation ends it, and the handoff is who
takes the attendance. None of them is an edit to the template -- paragraph 4149 keeps generated
instances stable -- so each is a record *against* the instance, and the instance's own row says
which record is in force.

**A substitution is a fact about one session, not a change to a rota.** A coach covering one
class on Tuesday has not had their working hours changed, so the substitute's availability is
checked for that session and nothing is written to their rota. The alternative -- editing
availability to make the cover legal -- would leave a rota nobody could read back.

**Every one of them states a reason.** They are the acts a member notices: their instructor
changed, their class moved rooms, their class is gone. "Why" is the first question and the row
is the only place the answer can live, because MOD-008 audits denials rather than allowed
actions and this module's role holds nothing in `iam`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.scheduling.recurrence import ScheduleError

#: What happened to a session after it was published. Four kinds, from paragraph 1839.
CHANGE_KINDS: tuple[str, ...] = ("substitution", "relocation", "cancellation", "handoff")

#: A session's own lifecycle. `scheduled` is the published state; the other three are terminal
#: in the sense that a cancelled session does not come back -- reinstating one would be a new
#: session, because the members told it was cancelled have been told.
SESSION_STATUSES: tuple[str, ...] = ("scheduled", "cancelled", "completed")

#: Why a session was cancelled. **Named rather than free text**, because the reason decides
#: what a member is owed: an instructor's illness is the tenant's fault and a weather closure
#: may not be, and MOD-017's entitlement is what gets returned either way. A fifth reason is a
#: decision about refunds, not a string.
CANCELLATION_REASONS: tuple[str, ...] = (
    "instructor_unavailable", "resource_unavailable", "insufficient_bookings",
    "facility_closed", "weather", "other",
)

#: The reasons that put a held place back in the member's hands. `insufficient_bookings` is the
#: tenant's commercial choice and so is included; `weather` is not the tenant's doing and is
#: *also* included, because the member did not get the session either way. What is excluded is
#: `other`, which has to be decided by whoever used it.
REFUNDABLE_REASONS: frozenset[str] = frozenset({
    "instructor_unavailable", "resource_unavailable", "insufficient_bookings",
    "facility_closed", "weather",
})


@dataclass(frozen=True)
class Change:
    """One recorded change against a published session."""

    kind: str
    reason: str
    #: For a substitution: who is covering. For a relocation: where it moves to.
    replacement_id: str | None = None
    cancellation_reason: str | None = None


def check_change(change: Change) -> None:
    if change.kind not in CHANGE_KINDS:
        raise ScheduleError(f"{change.kind!r} is not a session change kind")
    if not change.reason.strip():
        raise ScheduleError(
            "a change to a published session states why; it is the first thing a member asks")
    if change.kind in ("substitution", "relocation", "handoff"):
        if change.replacement_id is None:
            raise ScheduleError(f"a {change.kind} names what replaces what")
        if change.cancellation_reason is not None:
            raise ScheduleError(f"a {change.kind} is not a cancellation")
    else:
        if change.replacement_id is not None:
            raise ScheduleError("a cancellation replaces the session with nothing")
        if change.cancellation_reason is None:
            raise ScheduleError(
                "a cancellation names its reason from the declared set, because the reason "
                "decides what a member is owed")
        if change.cancellation_reason not in CANCELLATION_REASONS:
            raise ScheduleError(
                f"{change.cancellation_reason!r} is not a cancellation reason")


def check_session_transition(current: str, target: str) -> None:
    """Refuse a session lifecycle move the module does not admit.

    **A cancelled session does not come back.** Members have been told; reinstating it would
    leave them with a cancellation notice for a class that happened. A replacement session is a
    new one, which is also what makes "what did we actually run" answerable.
    """
    if current not in SESSION_STATUSES:
        raise ScheduleError(f"{current!r} is not a session status")
    if target not in SESSION_STATUSES:
        raise ScheduleError(f"{target!r} is not a session status")
    if current != "scheduled":
        raise ScheduleError(
            f"this session is {current} and a {current} session does not change again")
    if target == "scheduled":
        raise ScheduleError("a session is already scheduled")


def places_are_returned(change: Change) -> bool:
    """Whether a cancellation gives the held places back.

    **True for every declared reason except `other`.** The member did not get the session,
    whatever the cause -- so the default is to return the place and `other` is the one that
    needs somebody to decide, which is why it is a reason rather than a free-text field that
    would have made every cancellation ambiguous.
    """
    check_change(change)
    if change.kind != "cancellation":
        return False
    assert change.cancellation_reason is not None
    return change.cancellation_reason in REFUNDABLE_REASONS


def check_relocation(
    *, from_location_id: str | None, to_location_id: str, starts_at: datetime,
    at: datetime,
) -> None:
    """Refuse a relocation that cannot reach the members it affects.

    **Not after the session has started.** Moving a class while it is running tells the members
    already in the room to go somewhere else, and the ones who have not arrived get a notice
    for a session that is under way. The hour is a judgement -- it is how long a notification
    takes to be read in practice -- and it is stated here rather than configured because a
    tenant setting it to zero would be setting it to "nobody is told".
    """
    if not to_location_id.strip():
        raise ScheduleError("a relocation names where the session moves to")
    if from_location_id == to_location_id:
        raise ScheduleError("this session is already at that location")
    if at >= starts_at:
        raise ScheduleError(
            "a session that has started is not relocated; cancel it and schedule another")
    if (starts_at - at).total_seconds() < 3600:
        raise ScheduleError(
            "a relocation within an hour of the session cannot reach the members travelling "
            "to it; cancel it instead, which tells them something true")
