"""OPS-02-R04's appeal: a member disputes a sanction and somebody else decides.

Paragraph 1883 lists the appeal beside the fee, the credit loss, the warning and the strike,
which is the order they happen in: a sanction is recorded, the member says it is wrong, and a
decision is made by a person who is not them.

**Two acts and two parties, which is the whole of it.** MOD-016's review found a separation of
duties that no stricter check could rescue because there was only one insert to compare
against, and MOD-017 shipped the same shape in a contract publication. So an appeal is a row a
member's request creates and a *second* row's worth of columns that only a decision fills, the
decider is derived from the session rather than taken from a body, and the constraint beside
the table refuses a decider who is the subject.

**A sanction stands until the appeal is upheld.** Not suspended while it is open: an appeal
that paused the strike would make appealing free and automatic, and a tenant whose strikes
never bite has no policy. What an upheld appeal does is recorded here and acted on by the
module that owns the thing -- the fee is MOD-017's to credit, and the strike is this module's
to mark overturned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.booking.denial import BookingError

#: Where an appeal is. `withdrawn` is the member's own exit, which is separate from `rejected`
#: because one is their choice and the other is a decision against them.
APPEAL_STATES: tuple[str, ...] = ("open", "upheld", "rejected", "withdrawn")

EDGES: dict[str, tuple[str, ...]] = {
    "open": ("upheld", "rejected", "withdrawn"),
    # **A decision is final.** An appeal that could be reopened is a sanction nobody can rely
    # on, and a second look is a second appeal -- which is a new row with its own decider.
    "upheld": (),
    "rejected": (),
    "withdrawn": (),
}

#: What can be appealed. The fee and the credit are MOD-017's to reverse; the warning and the
#: strike are this module's own.
APPEALABLE: tuple[str, ...] = ("fee", "credit_forfeit", "warning", "strike")

#: The two whose remedy is a sanction no longer counting, which is a thing this module can do.
SANCTION_APPEALS: tuple[str, ...] = ("warning", "strike")

#: And the two whose remedy is money, which it cannot: MOD-017 charged the fee and MOD-017
#: credits it. An upheld one is recorded and says so rather than reporting a reversal.
MONEY_APPEALS: tuple[str, ...] = ("fee", "credit_forfeit")

#: How long a member has. Beyond a month the class is further away than anybody's memory of
#: it, and an appeal nobody can investigate is one a tenant decides by coin toss.
APPEAL_WINDOW_DAYS = 30


@dataclass(frozen=True)
class Appeal:
    """A disputed sanction, as the decisions need it."""

    appeal_id: str
    subject_person_id: str
    against: str
    state: str
    raised_at: datetime
    decided_by: str | None = None


def check_appeal(appeal: Appeal) -> None:
    if appeal.state not in APPEAL_STATES:
        raise BookingError(f"{appeal.state!r} is not an appeal state")
    if appeal.against not in APPEALABLE:
        raise BookingError(f"{appeal.against!r} is not something that can be appealed")
    if appeal.state == "open" and appeal.decided_by is not None:
        raise BookingError("an open appeal has no decider yet")
    if appeal.state in ("upheld", "rejected") and appeal.decided_by is None:
        raise BookingError(
            "a decided appeal names who decided it; the decision is the evidence")


def check_transition(current: str, target: str) -> None:
    if current not in APPEAL_STATES:
        raise BookingError(f"{current!r} is not an appeal state")
    if target not in APPEAL_STATES:
        raise BookingError(f"{target!r} is not an appeal state")
    if target not in EDGES[current]:
        raise BookingError(f"an appeal does not move from {current} to {target}")


def within_appeal_window(sanctioned_at: datetime, *, at: datetime) -> bool:
    return at <= sanctioned_at + timedelta(days=APPEAL_WINDOW_DAYS)


def check_decider(appeal: Appeal, *, decider_person_id: str | None) -> None:
    """Whether this person may decide this appeal, raising the reason if not.

    **A member does not decide their own appeal**, and the comparison is against the person the
    sanction is about rather than against a name on the request -- which is MOD-016's finding:
    a separation of duties compared against a field the caller supplies is not one. The service
    derives both sides, and the constraint beside the table says the same thing again so that a
    writer which is not the service cannot get round it.

    **A decider with no person record cannot decide.** The first version permitted
    `decider_person_id=None` on the grounds that a staff identity without one "is not the
    subject by definition" -- and that is false for the one human it matters for: the coach who
    is also a member with a strike, whose identity has no `ppl_identity_links` row. Nothing
    creates that link automatically and registration is open, so both layers of the separation
    of duties -- this and the CHECK beside the table, which also permits NULL -- failed on the
    same missing row rather than independently. Refusing is the fail-closed direction and the
    cost is small: linking the identity is one call, and deciding an appeal is a stepped-up
    financial act somebody does at a desk.
    """
    check_appeal(appeal)
    if decider_person_id is None:
        raise BookingError(
            "whoever decides an appeal needs a person record, so that the separation of "
            "duties can be checked against the member it is about")
    if decider_person_id == appeal.subject_person_id:
        raise BookingError(
            "a member does not decide their own appeal; somebody else reviews it")


def check_against(
    against: str, *, fee_due: bool, credit_forfeit: bool, sanction: str | None,
) -> None:
    """Whether the record carries the thing being appealed, raising the reason if not.

    **A stored `against` that nothing reads is a comment, not a parameter**, and a reviewer
    used it twice: once to appeal a strike on a record whose sanction was `none` and have it
    upheld, and once to appeal only a fee and have the member's sanction count silently wiped
    instead. The first is a decision about something that never happened; the second inverts
    the decider's intent, because `_no_show_count` reads the overturn marker and the member's
    next miss becomes their first again. MOD-019's rule: a field stored beside a decision and
    never read is not a parameter.

    A cancellation has no sanction, so `sanction` is None for one -- and `warning` and `strike`
    are then both refused, which is right: there is nothing of that kind to dispute.
    """
    if against not in APPEALABLE:
        raise BookingError(f"{against!r} is not something an appeal is against")
    if against == "fee" and not fee_due:
        raise BookingError("this record carries no fee to appeal")
    if against == "credit_forfeit" and not credit_forfeit:
        raise BookingError("this record forfeited no credit to appeal")
    if against in SANCTION_APPEALS and sanction != against:
        carried = "no sanction" if sanction in (None, "none") else sanction
        raise BookingError(
            f"this record carries {carried}, so there is no {against} to appeal")
