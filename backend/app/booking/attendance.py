"""OPS-02's attendance half: check-in, no-show and the AttendanceIntent entity.

Paragraph 1885: "Calendar synchronization, reminders, check-in linkage and attendance
completion." Paragraph 4189 keeps session completion and credit consumption as separate
coordinated events, and this is the booking side of that.

**A check-in is recorded, not performed.** Nothing here reads a turnstile: MOD-021 is the
hardware bridge and MOD-022 is check-in and access, neither of which exists. So
`CheckInBooking` records that a named actor marked a member present at a time, which is what a
front desk does and what a reader will do later -- the same shape as MOD-012's `validated`
install and MOD-014's contact verification, and said out loud for the same reason.

**A no-show is a decision about a booking whose session has finished.** Not a status somebody
sets: the facts are the session's end, the grace period and whether a check-in exists, and
deriving it means two tenants cannot disagree about what a no-show is. What it *costs* is
`consequence.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.booking.denial import BookingError
from app.booking.policy import Policy, check_policy

#: What a booking is doing. `attended` and `no_show` are both settled and are the two answers
#: a session's end produces; `cancelled` is the member's own act before it.
BOOKING_STATES: tuple[str, ...] = (
    "booked", "attended", "no_show", "cancelled", "released",
)

#: `released` is where a booking goes when the *session* was cancelled rather than the member
#: cancelling: the member owes nothing and the place came back, and conflating it with their
#: own cancellation is how somebody gets a strike for a class the gym called off.
EDGES: dict[str, tuple[str, ...]] = {
    "booked": ("attended", "no_show", "cancelled", "released"),
    "attended": (),
    "no_show": (),
    "cancelled": (),
    "released": (),
}

#: How somebody came to be marked present. Declared rather than free text, because a report of
#: who was in a class has to separate a reader from a person at a desk -- and because
#: `device` is what MOD-022 will write and nothing in this build can.
CHECKIN_SOURCES: tuple[str, ...] = ("front_desk", "self_service", "device", "migration")


@dataclass(frozen=True)
class Attendance:
    """What is known about whether a member turned up."""

    booking_state: str
    session_starts_at: datetime
    session_ends_at: datetime
    checked_in_at: datetime | None = None


def check_source(source: str) -> None:
    if source not in CHECKIN_SOURCES:
        raise BookingError(f"{source!r} is not a check-in source")


def check_transition(current: str, target: str) -> None:
    if current not in BOOKING_STATES:
        raise BookingError(f"{current!r} is not a booking state")
    if target not in BOOKING_STATES:
        raise BookingError(f"{target!r} is not a booking state")
    if target not in EDGES[current]:
        raise BookingError(f"a booking does not move from {current} to {target}")


def checkin_window(
    starts_at: datetime, *, policy: Policy,
) -> tuple[datetime, datetime]:
    """When a check-in counts, as half-open instants.

    **It opens an hour before the session and closes after the grace period.** The early edge
    is not configurable and the late one is: arriving early is universal, and how long a gym
    waits before calling somebody a no-show is exactly the judgement a tenant makes.
    """
    check_policy(policy)
    return (starts_at - timedelta(hours=1),
            starts_at + timedelta(minutes=policy.checkin_grace_minutes))


def may_check_in(
    attendance: Attendance, *, at: datetime, policy: Policy,
) -> None:
    """Whether a member may be marked present now, raising the reason if not."""
    if attendance.booking_state not in BOOKING_STATES:
        raise BookingError(f"{attendance.booking_state!r} is not a booking state")
    if attendance.booking_state != "booked":
        raise BookingError(
            f"this booking is {attendance.booking_state} and cannot be checked in")
    opens, closes = checkin_window(attendance.session_starts_at, policy=policy)
    if at < opens:
        raise BookingError(
            f"check-in opens at {opens.isoformat()}; this session has not started")
    if at > closes:
        raise BookingError(
            f"check-in closed at {closes.isoformat()}; this booking is a no-show")


def is_no_show(attendance: Attendance, *, at: datetime, policy: Policy) -> bool:
    """Whether this booking is a no-show, as of now.

    **Three facts and no judgement**: the booking is still `booked`, nobody checked in, and the
    check-in window has closed. A booking whose session has not finished is not a no-show yet,
    which is why this takes the clock -- a sweep that ran early would mark a whole day's
    bookings as missed.
    """
    check_policy(policy)
    if attendance.booking_state != "booked":
        return False
    if attendance.checked_in_at is not None:
        return False
    _, closes = checkin_window(attendance.session_starts_at, policy=policy)
    # **Both, for the reason `settle` is `or`.** A member inside the grace period has not
    # missed the class, and a class still running has not been missed either -- so a booking
    # is a no-show only once neither is true. The first version read the window alone and so
    # called a booking on a two-hour class a no-show sixteen minutes in.
    return at > closes and at > attendance.session_ends_at


def settle(attendance: Attendance, *, at: datetime, policy: Policy) -> str:
    """What this booking becomes when its session is over: `attended` or `no_show`.

    Raises rather than guessing when the session is not over, because a settlement is final --
    `EDGES` gives `attended` and `no_show` no way out -- and settling early would make a member
    who is on their way a no-show for ever.
    """
    check_policy(policy)
    if attendance.booking_state != "booked":
        raise BookingError(
            f"this booking is already {attendance.booking_state}")
    # **Either reason is enough to refuse, which is why this is `or`.** The first version
    # required both, so a settlement went ahead as soon as the *session* ended even with the
    # check-in window still open -- and a grace period longer than the class is inside
    # `check_policy`'s bounds, which a thirty-minute personal-training slot with
    # three-quarters of an hour of grace reaches without trying. A member who walked in ten
    # minutes late then had their booking written to `no_show` the moment the class finished:
    # `EDGES` gives that state no way out, `consequence.decide` charges the fee and counts it
    # towards a strike, and the front desk's later check-in is refused because the state has
    # moved. They attended, were charged and were struck. Found by review; the refusal's own
    # message had said the session was not over while not refusing.
    _, closes = checkin_window(attendance.session_starts_at, policy=policy)
    if at <= closes or at <= attendance.session_ends_at:
        raise BookingError(
            "this session is not over, or its check-in window is still open, so its bookings "
            "are not settled yet")
    # **Asked of `is_no_show`, not decided again.** Two functions answering the same question
    # from the same facts are two answers that can disagree, and a reviewer found them
    # disagreeing at the same instant on the same booking.
    return "no_show" if is_no_show(attendance, at=at, policy=policy) else "attended"
