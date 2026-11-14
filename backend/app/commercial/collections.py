"""MOD-017 COM-03-R04 and R06: recovering money, and what a provider's answer means.

Two things live here and they are kept apart on purpose.

**The dunning journey** is COM-03-R04: a retry schedule, a grace period, a communication, an
escalation and an access consequence. The stages are data, so the whole journey is readable at
once and a tenant's configuration is one table rather than a chain of conditions.

**The provider's answer** is COM-03-R06: idempotent commands, webhook verification and
payment-status reconciliation. Two rules here, both from paragraph 1609 ("fail consequence-
bearing writes closed on unknown provider/ledger state; persist PENDING explicitly"):

* **`unknown` is not `failed`.** A provider that times out has told us nothing, and treating
  silence as a decline is how a member is dunned for a payment that actually succeeded. It is
  a state a payment holds until something reconciles it, and no retry, no dunning stage and no
  access consequence may read it as either outcome.

* **A failure's *code* decides what happens next, never its text.** `insufficient_funds` is
  worth retrying tomorrow; `card_stolen` is not worth retrying at all and must not be. MOD-016
  shipped a control that branched on whether a prose reason contained one of four English
  words, and a reviewer defeated it with a promotion key. So the codes are a declared set and
  the provider's own sentence goes in a field nothing branches on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

#: What a failure means for a retry, by code. **Three classes and an explicit default**, which
#: is the part that matters: a code this build has not seen is `unknown_cause`, which retries
#: cautiously rather than either giving up on a recoverable card or hammering a dead one.
RETRYABLE = "retryable"
PERMANENT = "permanent"
NEEDS_MEMBER_ACTION = "needs_member_action"
UNKNOWN_CAUSE = "unknown_cause"

FAILURE_CLASSES: dict[str, str] = {
    # Money, not the card. Tomorrow may be different.
    "insufficient_funds": RETRYABLE,
    "issuer_unavailable": RETRYABLE,
    "processing_error": RETRYABLE,
    "rate_limited": RETRYABLE,
    # **Never retried.** Retrying a card the issuer reported stolen is a thing a scheme fines
    # an acquirer for, and retrying a revoked mandate is a thing a regulator asks about.
    "card_stolen": PERMANENT,
    "card_lost": PERMANENT,
    "do_not_honour_final": PERMANENT,
    "mandate_revoked": PERMANENT,
    "account_closed": PERMANENT,
    # The member has to do something: a new card, a 3DS challenge, a corrected address.
    "card_expired": NEEDS_MEMBER_ACTION,
    "authentication_required": NEEDS_MEMBER_ACTION,
    "incorrect_details": NEEDS_MEMBER_ACTION,
    "limit_exceeded": NEEDS_MEMBER_ACTION,
}

#: COM-03-R04's journey. One entry per stage: how long after the previous step, what to say,
#: and what the stage recommends be done about access.
#:
#: **The access column is a recommendation and nothing here applies it.** Paragraph 1496 --
#: billing state and access state are related and never conflated -- so suspending a membership
#: is a lifecycle change with its own recorded decision and its own permission. A dunning stage
#: that reached into the membership tables would make an unpaid invoice and a suspended
#: membership the same fact, and they are not: a disputed invoice is unpaid and the member is
#: entitled to train.
STAGES: tuple[tuple[int, int, str, str], ...] = (
    (1, 0, "payment_failed", "none"),
    (2, 3, "payment_retry_notice", "none"),
    (3, 7, "payment_overdue_warning", "warn"),
    (4, 14, "payment_final_notice", "restrict"),
    (5, 21, "account_suspension_notice", "suspend"),
)

#: How many stages there are, so a caller can tell "the journey is over" from "there is another
#: step" without knowing the table.
FINAL_STAGE = STAGES[-1][0]


class CollectionsError(ValueError):
    """A collections input this module will not accept."""


@dataclass(frozen=True)
class Stage:
    """One step of the dunning journey."""

    stage: int
    days_after_due: int
    notification_key: str
    access_recommendation: str


@dataclass(frozen=True)
class NextStep:
    """What the journey does next, and when."""

    stage: int
    due_on: date
    notification_key: str
    access_recommendation: str
    #: True when this was the last stage: the case ends rather than advancing again.
    is_final: bool


def stage(number: int) -> Stage:
    """One stage by number."""
    for n, days, key, access in STAGES:
        if n == number:
            return Stage(n, days, key, access)
    raise CollectionsError(f"{number} is not a dunning stage this build runs")


def classify_failure(failure_code: str | None) -> str:
    """What a provider's failure code means for a retry.

    `None` is `unknown_cause` rather than an error: a payment can be in `unknown` state with no
    code at all, which is precisely the case paragraph 1609 requires to be representable.
    """
    if failure_code is None:
        return UNKNOWN_CAUSE
    return FAILURE_CLASSES.get(failure_code, UNKNOWN_CAUSE)


def may_retry(failure_code: str | None, *, attempts: int, max_attempts: int = 4) -> bool:
    """Whether a failed payment should be attempted again.

    **A permanent failure is never retried, whatever the attempt count says**, and that is the
    check that comes first: a budget of four attempts is not permission to present a stolen
    card four times. `needs_member_action` is likewise not retried by the system -- there is
    nothing to retry until the member does something -- and the journey's job then is to ask
    them.
    """
    if attempts < 0:
        raise CollectionsError("an_attempt_count_is_not_negative")
    if max_attempts < 1 or max_attempts > 20:
        raise CollectionsError("a_retry_budget_is_between_one_and_twenty")
    verdict = classify_failure(failure_code)
    if verdict in (PERMANENT, NEEDS_MEMBER_ACTION):
        return False
    return attempts < max_attempts


def next_step(
    *, current_stage: int, due_on: date, grace_days: int = 0,
) -> NextStep | None:
    """The next step of the journey, or None when it is over.

    Stage days are counted from the invoice's due date and the account's grace period is added
    once, at the front -- so a corporate payer on thirty-day terms is not warned on day three.
    Counting the grace into every stage instead would stretch the whole journey, which is not
    what a grace period is.
    """
    if grace_days < 0 or grace_days > 180:
        raise CollectionsError("a_grace_period_is_between_zero_and_one_hundred_and_eighty_days")
    following = current_stage + 1
    if following > FINAL_STAGE:
        return None
    step = stage(following)
    return NextStep(
        stage=step.stage,
        due_on=due_on + timedelta(days=grace_days + step.days_after_due),
        notification_key=step.notification_key,
        access_recommendation=step.access_recommendation,
        is_final=step.stage == FINAL_STAGE)


def opening_step(*, due_on: date, grace_days: int = 0) -> NextStep:
    """The first step, taken when a case opens."""
    step = stage(1)
    return NextStep(
        stage=step.stage,
        due_on=due_on + timedelta(days=grace_days + step.days_after_due),
        notification_key=step.notification_key,
        access_recommendation=step.access_recommendation,
        is_final=step.stage == FINAL_STAGE)


def reconcile(
    *, recorded_status: str, provider_status: str | None,
) -> tuple[str, str]:
    """What a reconciliation makes of a payment whose state we are unsure about.

    Returns `(status, reason_code)`. COM-03-R06's "payment-status reconciliation", and the rule
    is the one paragraph 1609 states: **an absent provider answer leaves the payment unknown.**
    It does not resolve to failed, because a payment that actually succeeded and was then
    recorded as failed is money collected and not credited to the member -- the direction that
    produces a complaint and a chargeback rather than a retry.

    A provider answer that *contradicts* a settled record is reported rather than applied. Only
    the provider knows what it did, but only a human should decide what to do when the two
    records disagree about money, and silently overwriting a `succeeded` payment with `failed`
    would destroy the evidence of the disagreement.
    """
    if recorded_status not in (
        "pending", "requires_authentication", "succeeded", "failed", "cancelled", "unknown",
    ):
        raise CollectionsError(f"{recorded_status!r} is not a payment status")
    if provider_status is None:
        return "unknown", "provider_did_not_answer"
    if provider_status not in ("succeeded", "failed", "pending", "cancelled"):
        raise CollectionsError(f"{provider_status!r} is not a provider answer")
    if recorded_status in ("pending", "requires_authentication", "unknown"):
        if provider_status == "pending":
            return "unknown", "provider_still_deciding"
        return provider_status, "reconciled_from_provider"
    if recorded_status == provider_status:
        return recorded_status, "already_agreed"
    return recorded_status, "provider_disagrees_escalate"
