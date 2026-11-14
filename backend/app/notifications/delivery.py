"""MOD-013 ENG-02: delivery state, deduplication, retry and suppression.

Paragraph 2464 is the control this module exists for: **"the same logical notification cannot be
delivered repeatedly because of retries."** Two mechanisms carry it, and they answer different
questions.

* The **request** is deduplicated by `(tenant, idempotency_key)`, so a caller that asks twice --
  because its own retry fired, or because an event was redelivered under MOD-010's
  at-least-once contract -- authors one notification. That is the producer side.
* The **delivery** is one row per `(tenant, notification, channel)`, so a dispatcher that
  retries after a timeout settles the row it already holds rather than creating a second one.
  That is the transport side, and it is the one a provider's own retry defeats if the row is
  missing.

Neither is sufficient alone: the first stops two authorings, the second stops two sends of one
authoring, and a provider that accepted a message and then timed out needs the second.

**The backoff is MOD-010's, imported rather than copied** -- a third retry curve in one
repository would be a third thing to keep in step.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.events import dispatch

#: What a stored digest looks like, so a caller cannot pass an address where a digest belongs --
#: which would put a contact address in a column this module promises never to hold one in.
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

#: How long a claimed delivery is left alone before another dispatcher may take it.
#:
#: **The claim is a lease, not a lock** -- MOD-010's wording, and the same tradeoff. A
#: dispatcher slower than this can be joined by a second one, which is inside the
#: at-least-once contract; the `state = 'pending'` guard on the settling write is what stops
#: the late writer corrupting the row. Setting `next_attempt_at` forward is what makes the
#: claim a claim at all: leaving it NULL marked the delivery due immediately, so five calls
#: handed one message out five times.
CLAIM_LEASE = timedelta(minutes=5)

#: A delivery's life. `suppressed` is terminal and is not a failure: it records that the
#: notification was considered and deliberately not sent, which is the evidence a member's
#: complaint needs. `dead` is a failure that exhausted its budget.
DELIVERY_STATES = ("pending", "sent", "delivered", "failed", "dead", "suppressed")

#: What a provider can come back with. `bounced` and `complained` are not just failures: each
#: adds the address to the suppression list, which is paragraph 2460's requirement and the
#: reason the two are distinguished from an ordinary `failed`.
OUTCOMES = ("sent", "delivered", "failed", "bounced", "complained")

#: Why an address is suppressed. `unsubscribed` is the recipient's own act and is the only one
#: a tenant may release, because the other two are the channel's judgement about deliverability
#: and overriding them damages every other notification's chance of arriving.
SUPPRESSION_REASONS = ("bounced", "complained", "unsubscribed")
RELEASABLE_REASONS = ("unsubscribed",)


class DeliveryError(ValueError):
    """A delivery transition or input this module will not accept."""


_EDGES: dict[str, tuple[str, ...]] = {
    # `delivered` directly from `pending` as well as from `sent`: plenty of providers report
    # one webhook saying "delivered" and never a separate handoff, and a machine that demanded
    # the intermediate state would refuse the confirmation it most wants to record.
    "pending": ("sent", "delivered", "failed", "dead", "suppressed"),
    # A provider may confirm delivery after reporting it sent, or report a late bounce.
    "sent": ("delivered", "failed", "dead"),
    # Terminal: a delivered message cannot un-deliver, and a later complaint is a suppression
    # against the address rather than a change to this row.
    "delivered": (),
    "failed": ("sent", "delivered", "dead"),
    "dead": (),
    "suppressed": (),
}


def check_transition(current: str, target: str) -> None:
    if current not in _EDGES:
        raise DeliveryError(f"unknown_delivery_state_{current}")
    if target not in _EDGES[current]:
        raise DeliveryError(f"a_delivery_cannot_go_from_{current}_to_{target}")


def address_digest(channel: str, address: str) -> str:
    """The only form of a contact address this module ever stores.

    **ENG-02 holds no contact data.** Suppression, frequency capping and deduplication all work
    on a digest, so a bounce can be remembered and an address can be matched without this module
    keeping a second copy of everyone's email beside the one MOD-014 and MOD-007 own. MOD-009's
    whole objection to a shadow database is that the copies disagree and only one of them is
    reachable by an erasure; a digest is reachable by neither and needs to be.

    The channel is part of the input, so the same address on two channels produces two digests
    and a bounce on email does not suppress an SMS. Normalized first, because `A@B.com` and
    `a@b.com` are one mailbox and a suppression that missed the other casing would send to a
    complainant.
    """
    if channel not in ("email", "sms", "whatsapp", "push", "in_app"):
        raise DeliveryError(f"{channel!r} is not a channel")
    normalized = address.strip().lower()
    if not normalized:
        raise DeliveryError("an_address_cannot_be_blank")
    return hashlib.sha256(f"{channel}:{normalized}".encode()).hexdigest()


@dataclass(frozen=True)
class Verdict:
    """What happens to a delivery that just reported an outcome."""

    state: str
    attempts: int
    next_attempt_at: datetime | None
    #: Set when the outcome requires the address to be suppressed.
    suppress_reason: str | None = None


def outcome_verdict(
    *, outcome: str, attempts: int, max_attempts: int, now: datetime,
) -> Verdict:
    """RecordDeliveryOutcome, as a decision.

    A **bounce or a complaint is terminal on the first report** and never retried: the channel
    has told us the address is wrong or the recipient reported us as spam, and a retry in either
    case is the thing that gets a sending domain blocked. An ordinary `failed` is a transient
    refusal and gets the budget.
    """
    if outcome not in OUTCOMES:
        raise DeliveryError(f"{outcome!r} is not a delivery outcome")
    if attempts < 1:
        raise DeliveryError("an_outcome_follows_at_least_one_attempt")
    if max_attempts < 1:
        raise DeliveryError("max_attempts_must_be_positive")
    if outcome in ("sent", "delivered"):
        return Verdict(state=outcome, attempts=attempts, next_attempt_at=None)
    if outcome in ("bounced", "complained"):
        return Verdict(state="dead", attempts=attempts, next_attempt_at=None,
                       suppress_reason=outcome)
    if attempts >= max_attempts:
        return Verdict(state="dead", attempts=attempts, next_attempt_at=None)
    return Verdict(state="failed", attempts=attempts,
                   next_attempt_at=now + dispatch.backoff_seconds(attempts))


def check_release(reason: str) -> None:
    """Which suppressions a tenant may lift.

    An unsubscribe is the recipient's own decision and they may change it. A bounce or a
    complaint is the **channel's** judgement, and a tenant that could clear those would be
    choosing to keep sending to an address that rejected them -- which damages the deliverability
    of every other notification, including the transactional ones nobody opted out of.
    """
    if reason not in SUPPRESSION_REASONS:
        raise DeliveryError(f"{reason!r} is not a suppression reason")
    if reason not in RELEASABLE_REASONS:
        raise DeliveryError(
            f"a {reason} suppression is the channel's judgement and cannot be released here"
        )
