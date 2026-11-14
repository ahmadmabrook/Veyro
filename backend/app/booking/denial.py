"""A booking denial a member can act on. OPS-02's first Critical Control.

Paragraph 1888: "Booking decisions return an understandable eligibility or denial explanation."
Paragraph 5032 adds that a capacity conflict returns a *stable* denial -- the same input gives
the same answer, so a member who tries again gets the same sentence rather than a different
guess.

**A denial is a declared reason plus a sentence, not a sentence alone.** The reason is what a
surface switches on -- a full class offers the waitlist, a closed window offers the opening
time, an ineligible member offers nothing and says why -- and prose alone would make every
caller parse English to decide what to show. MOD-019's `conflicts.Conflict` is the same shape
for the same reason.

**No denial here is a score.** Paragraph 1884 allows a predictive no-show score to influence
communication and capacity strategy, and paragraph 1889 forbids it discriminating unlawfully;
`consequence.py` records why this build computes none at all. Nothing in this module refuses a
member because of a prediction about them.
"""

from __future__ import annotations

from dataclasses import dataclass


class BookingError(ValueError):
    """A booking decision that cannot be made, with the reason in the message.

    `ValueError` for the reason every other decision module in this build subclasses it: the
    service layer maps it to the five service errors and nothing else has to know.
    """


#: Why a booking was refused. The set is closed because a surface switches on it, and an
#: unknown member of it would be a surface that cannot decide what to offer.
#:
#: `full` and `waitlist_full` are different offers: the first is an invitation to wait, the
#: second is the end of the conversation.
DENIAL_REASONS: tuple[str, ...] = (
    "session_not_bookable",
    "window_not_open",
    "window_closed",
    "full",
    "waitlist_full",
    "already_booked",
    "ineligible",
    "no_entitlement",
    "quota_reached",
    "suspended",
)


@dataclass(frozen=True)
class Denial:
    """One reason a booking cannot be made, and what to do about it.

    `offer_waitlist` is separate from the reason because it is the *action* a surface takes,
    and deriving it from the reason in every caller is how two surfaces come to disagree about
    whether a full class has a waitlist.
    """

    reason: str
    detail: str
    offer_waitlist: bool = False
    #: When the refusal stops applying, where that is knowable: the moment a booking window
    #: opens, or a quota period rolls over. None means "not from waiting".
    retry_at: str | None = None


def check_reason(reason: str) -> None:
    if reason not in DENIAL_REASONS:
        raise BookingError(f"{reason!r} is not a booking denial reason")


def is_stable(first: Denial, second: Denial) -> bool:
    """Whether two denials of the same request say the same thing.

    Paragraph 5032's "stable denial", as something a test can assert rather than a promise in
    prose: a member who taps *book* twice on a full class must not be told "full" and then
    "you are not eligible". The service makes it true by evaluating in a fixed order; this is
    how that is checked.
    """
    return (first.reason == second.reason
            and first.offer_waitlist == second.offer_waitlist)
