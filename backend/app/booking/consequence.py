"""OPS-02-R04: what a late cancellation or a no-show costs, and the score this build refuses.

Paragraph 1883: "No-show and late-cancel policy with fee, credit loss, warning, strike and
appeal." Paragraph 1884: "Predictive no-show score used for reminders and controlled
overbooking, never opaque denial." Paragraph 1889 makes it a Critical Control that predictive
scoring "may influence communication and capacity strategy but not discriminate unlawfully".

**This module decides and records; it charges nothing and revokes nothing.** A fee is MOD-017's
invoice and a lost credit is MOD-017's entitlement, and real financial expenditure is
owner-reserved. So the outcome here is a *decision* -- what is owed, which credit is forfeit,
whether this is a warning or a strike -- carried on an insert-only row, and the modules that
own money act on it. A module that wrote "fee charged" with nothing having charged anything
would be the fabricated-evidence shape this codebase has been bitten by five times.

**And there is no predictive no-show score.** Paragraph 1884 asks for one; this build computes
none, and the refusal is here rather than in a stub that returns 0.5:

  * There is no outcome data. A score needs a history of who missed what, and on the day a
    tenant starts there is none -- so the first weeks' scores would be noise presented as a
    judgement about a person.
  * Paragraph 1889's limit is not a thing a function can promise. A score built from
    attendance correlates with shift work, childcare and illness, and "does not discriminate
    unlawfully" is a claim about a population, not a property of an expression.
  * The two sanctioned uses are reminders and controlled overbooking, and both are reachable
    without a score: a reminder goes to everybody and `overbook_places` is a number a tenant
    sets. `no_show_count` below is the observable fact, and it is used for the warning and the
    strike the policy declares -- which is a rule a member can read, not a prediction about
    them.

That is MOD-011's refusal to fake a percentile, applied to people instead of metrics: an
objective stated as a percentile is refused at definition time rather than evaluated against a
mean, and a score with no data behind it is refused here rather than returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from app.booking.denial import BookingError
from app.booking.policy import Policy, check_policy

#: What happened, which decides what it costs. `session_cancelled` is in the list because the
#: answer for it is "nothing", and leaving it out would make a caller derive that.
OCCASIONS: tuple[str, ...] = (
    "cancelled_in_time", "cancelled_late", "no_show", "session_cancelled",
)

#: What a tenant may do about it. Each is a different act by a different module, which is why
#: they are separate flags rather than a severity: a fee is MOD-017's, a forfeit credit is
#: MOD-017's entitlement, and a warning and a strike are this module's own record.
SANCTIONS: tuple[str, ...] = ("none", "warning", "strike")


@dataclass(frozen=True)
class Outcome:
    """What a cancellation or a no-show costs, as a decision for other modules to act on.

    **`fee_due` is a flag and not an amount.** The amount is a price, and a price is MOD-016's
    catalogue and MOD-017's invoice; a number here would be a second authority on what a member
    owes. What this says is *that* a fee is due under the policy the booking was made under.
    """

    occasion: str
    fee_due: bool
    #: Whether the entitlement the booking drew on is forfeit. A member who books with a
    #: ten-class pass and misses one has used one, which is the ordinary reading of a pass --
    #: and it is the policy's choice, because a tenant that refunds the class instead is also
    #: ordinary.
    credit_forfeit: bool
    sanction: str
    #: The no-show count this decision was made against, so the row says why it was a strike
    #: rather than leaving a reader to recount.
    no_show_count: int
    detail: str


def decide(
    occasion: str, *, no_show_count: int, policy: Policy,
    entitlement_cited: bool = False,
) -> Outcome:
    """What this occasion costs under this policy.

    `no_show_count` is the member's own count *including* this one, counted by the caller from
    the insert-only records -- not stored on the member, for MOD-018's reason: a cached count is
    a second authority that can disagree with the rows it came from, and here it would decide a
    sanction.
    """
    check_policy(policy)
    if occasion not in OCCASIONS:
        raise BookingError(f"{occasion!r} is not a booking occasion")
    if no_show_count < 0:
        raise BookingError("a no-show count is not negative")
    if occasion in ("cancelled_in_time", "session_cancelled"):
        # **A session the tenant cancelled costs the member nothing**, and nor does cancelling
        # inside the window. Both are the ordinary case and both are stated rather than
        # defaulted, so a later reader can see that the answer was decided.
        return Outcome(
            occasion=occasion, fee_due=False, credit_forfeit=False, sanction="none",
            no_show_count=no_show_count,
            detail=("the gym cancelled this session" if occasion == "session_cancelled"
                    else "cancelled inside the policy's window"))
    sanction = "none"
    if no_show_count >= policy.strike_after_no_shows:
        sanction = "strike"
    elif no_show_count >= policy.warn_after_no_shows:
        sanction = "warning"
    if occasion == "cancelled_late":
        # **A late cancellation is not a no-show, and its sanction is not counted.** The member
        # told the gym; somebody else could have had the place. Charging the fee and forfeiting
        # the credit is the policy's business, but a strike is for not turning up -- and
        # counting late cancellations towards one is how a member who always calls ahead ends
        # up sanctioned for being considerate.
        return Outcome(
            occasion=occasion, fee_due=True, credit_forfeit=entitlement_cited,
            sanction="none", no_show_count=no_show_count,
            detail=(f"cancelled within {policy.cancellation_hours} hours of the start"))
    return Outcome(
        occasion=occasion, fee_due=True, credit_forfeit=entitlement_cited,
        sanction=sanction, no_show_count=no_show_count,
        detail=(f"no-show number {no_show_count}; this policy warns after "
                f"{policy.warn_after_no_shows} and strikes after "
                f"{policy.strike_after_no_shows}"))


def predicted_no_show_risk(*_args: object, **_kwargs: object) -> NoReturn:
    """**Refused.** Paragraph 1884's predictive score, and this build computes none.

    It exists as a function so the refusal is reachable and testable rather than an absence
    somebody fills in later with a stub returning 0.5.

    **`NoReturn`, not `float`.** A reviewer pointed out that the old annotation was the stub
    with extra steps: the signature told a caller type-checking against it that a number comes
    back, so code written to it could not run.

    **The durable reason is the middle one, and the other two are not.** Paragraph 1889's
    "must not discriminate unlawfully" is a property of a population under a model rather than
    of an expression, so no function can promise it -- the same argument MOD-011 used to refuse
    a percentile at definition time, and stronger here because the subject is a person. "There
    is no outcome history" was also offered and *expires on its own*: `bkg_no_shows` is
    insert-only and `_no_show_count` already reads it, so a tenant that has run a month has
    exactly the history that reason says does not exist. It is dropped rather than left,
    because a reason that stops being true reads as an invitation. The third -- that both
    sanctioned uses, reminders and controlled overbooking, are reachable without a score -- is
    checkable and true: `overbook_places` is a tenant integer and a reminder that goes to
    everybody needs no ranking.
    """
    raise BookingError(
        "this build computes no predictive no-show score: there is no outcome history to "
        "learn from, and a number attached to a member with nothing behind it is the opaque "
        "denial paragraph 1884 forbids. The observable count is on the no-show records")
