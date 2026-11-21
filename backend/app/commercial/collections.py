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

from app.commercial import lifecycle

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


# ------------------------------------------------------------------ the scheme's dispute
#
# **COM-03-R06's other half, and the table MOD-017 shipped with no writer.**
# `plt01.fin_disputes` has existed since this module's migration -- with forced RLS, twelve
# constraints, an isolation check and four privacy declarations -- and nothing in `app/` read
# or wrote it. The module's own registry entry lists disputes among what works. It was found
# by building ADM-PAY-03, whose disputed state is "evidence deadline banner": a state the
# screen can never render is the vacuous branch this codebase has shipped four times in a UI
# and four times in a service, so the remedy is the writer rather than a caveat.
#
# **Nothing here is a Veyro decision, which is why it is one permission rather than two.**
# A refund is split across `finance.refund.request` and `finance.refund.approve` because
# somebody chooses to send money back and paragraph 1598 wants a second person on that
# choice. A dispute has no such moment: the scheme opens it, the tenant answers it, and the
# scheme decides. Every transition is recording what another party did or what was sent to
# them, so a separation of duties would be a ceremony over somebody else's decision.
#
# **The deadline is the scheme's and cannot be moved.** `respond_due_on` is required on the
# row for that reason, and it is the only date in this module that is not Veyro's to extend --
# which is what makes it worth a banner rather than a column.

#: The states a dispute holds, matching `fin_disputes_status`. `responded` is not an outcome:
#: evidence was submitted and the scheme has not answered, which is `unknown`'s shape one
#: table over and must not be read as either result.
DISPUTE_STATUSES = ("open", "responded", "won", "lost", "withdrawn")

#: The three that end it, matching `fin_disputes_closed_has_an_outcome`.
DISPUTE_OUTCOMES = ("won", "lost", "withdrawn")

#: **A dispute may be settled without a response**, which is the edge worth stating: a scheme
#: can withdraw an inquiry, or decide against a tenant that missed the deadline, and a machine
#: that required `responded` first would make a missed deadline unrecordable. Both closing
#: paths exist because both happen.
DISPUTE_EDGES: dict[str, tuple[str, ...]] = {
    "open": ("responded", "won", "lost", "withdrawn"),
    "responded": ("won", "lost", "withdrawn"),
    "won": (),
    "lost": (),
    "withdrawn": (),
}


class DisputeError(ValueError):
    """A dispute transition the scheme's own machine does not have."""


def check_dispute_transition(current: str, target: str) -> None:
    """Refuse a dispute move that is not in the machine.

    Shares no code with the payment or fiscal machines, for `check_fiscal_transition`'s
    reason: a helper that handled several is where somebody later makes one imply another.
    """
    if current not in DISPUTE_STATUSES:
        raise DisputeError(f"{current!r} is not a dispute status")
    if target not in DISPUTE_STATUSES:
        raise DisputeError(f"{target!r} is not a dispute status")
    if target not in DISPUTE_EDGES[current]:
        raise DisputeError(f"a dispute does not move from {current} to {target}")


def evidence_window(*, opened_on: date, respond_due_on: date, at: date) -> dict[str, object]:
    """What is left of the window to answer a dispute in, as a fact rather than a colour.

    Three numbers and no verdict about what to do, because the action is the tenant's: how
    many days remain, whether the deadline has passed, and how long the scheme gave in the
    first place -- the last because "three days left" means something different out of thirty
    than out of four.

    **A passed deadline is reported, not hidden.** A dispute whose window closed is the one a
    surface most needs to show: the response can no longer be sent, and the tenant's exposure
    is now the full amount. `days_remaining` goes negative rather than clamping at zero, for
    `days_late`'s reason one module over -- zero would say the deadline is today.
    """
    if respond_due_on < opened_on:
        raise DisputeError("a dispute's deadline is not before it was opened")
    return {
        "days_remaining": (respond_due_on - at).days,
        "window_has_closed": at > respond_due_on,
        "days_given": (respond_due_on - opened_on).days,
    }


# ---------------------------------------------------------------- the recovery workspace
#
# ADM-PAY-05. The design's own argument for the screen is that "the six are one decision, not
# six", and that is only true if the six have been *sorted* first: a batch whose recommended
# treatment is identical for every row is one decision, and a batch mixing a member who needs
# a new card with a member whose membership ended is six. So this is the function that sorts
# them, and the header line the design writes -- "All retries exhausted · no access blocked"
# -- is read off the set rather than typed.

#: The system will try again on its own. **Nothing for a person to do yet**, which is why this
#: is a treatment rather than an absence: a case waiting on an automatic retry that appeared in
#: a workspace headed "all retries exhausted" would be a row somebody chased twice.
TREATMENT_RETRY = "retry"
#: Ask the member. A payment link is exactly this, and in this build it is also the thing that
#: does not exist -- see `recovery_workspace`'s disclosure.
TREATMENT_LINK = "link"
#: A person looks before anything goes out.
TREATMENT_REVIEW = "review"

TREATMENTS = (TREATMENT_RETRY, TREATMENT_LINK, TREATMENT_REVIEW)

#: Why, from a closed set, because a surface decides what to offer from this value and a
#: free-text reason is a decision nobody can group by. MOD-020's `DENIAL_REASONS` is the
#: precedent, and its review's rule -- grep the writers, a declared value with none is a gap
#: or a defect -- is `test_every_treatment_and_reason_is_reachable`, which drives this
#: function over every code, budget and membership status and requires each declared value
#: to come back from something.
RECOVERY_REASONS = (
    # review
    "failure_is_permanent",
    "membership_ended",
    "membership_frozen",
    "no_membership_cited",
    "cause_unknown",
    # link
    "member_action_needed",
    "retries_exhausted",
    # retry
    "retries_remain",
)

# A membership that has ended is `lifecycle.TERMINAL`, imported rather than restated:
# collecting against one is a different conversation from collecting against a live
# membership, and a second list of which statuses those are is a second answer the day either
# moves. Same for the vocabulary itself -- `lifecycle` owns the states.


@dataclass(frozen=True)
class Treatment:
    """What a failed payment's recovery wants next, and why."""

    treatment: str
    reason: str
    #: Carried so a surface can say "the system will try again" without re-deriving it, and so
    #: the two can never disagree: this is `may_retry`'s answer, not a second opinion.
    may_retry: bool


def recovery_treatment(
    failure_code: str | None,
    *,
    attempts: int,
    membership_status: str | None,
    max_attempts: int = 4,
) -> Treatment:
    """What to do about one failed payment, given why it failed and where the member stands.

    The order of the checks is the whole content of the function:

    1. **A permanent failure is reviewed, never messaged.** `may_retry` puts permanence first
       because a budget of four attempts is not permission to present a stolen card four
       times; the same holds for a "pay here" link, which a scheme cares about for the same
       reason. So this check precedes every other one, including the membership ones.
    2. **A membership that has ended, or is frozen, is reviewed** -- before the member-action
       check, because asking somebody for a card to pay for a membership they cancelled is a
       worse message than no message. The design's two `review first` rows are exactly these:
       "frozen member" and "membership ended".
    3. **An invoice citing no membership is reviewed**, not skipped. `None` here means the
       debt has no membership behind it -- a retail sale, say -- so the ordinary dunning
       notice, which is a sentence about somebody's membership, is the wrong message. Skipping
       it instead would drop a real debt off the workspace.
    4. Then, and only then, the failure class decides: the member has to act, the system
       should try again, or the budget is spent and a link is the remaining move.

    `max_attempts` is `may_retry`'s own default and is passed through rather than re-stated,
    because two retry budgets in one repository drift and the day they disagree nobody can say
    which one is the policy.
    """
    if membership_status is not None and membership_status not in lifecycle.STATUSES:
        raise CollectionsError(f"{membership_status!r} is not a membership status")
    retryable = may_retry(failure_code, attempts=attempts, max_attempts=max_attempts)
    verdict = classify_failure(failure_code)
    if verdict == PERMANENT:
        return Treatment(TREATMENT_REVIEW, "failure_is_permanent", retryable)
    if membership_status is None:
        return Treatment(TREATMENT_REVIEW, "no_membership_cited", retryable)
    if membership_status in lifecycle.TERMINAL:
        return Treatment(TREATMENT_REVIEW, "membership_ended", retryable)
    if membership_status == "frozen":
        return Treatment(TREATMENT_REVIEW, "membership_frozen", retryable)
    if verdict == NEEDS_MEMBER_ACTION:
        return Treatment(TREATMENT_LINK, "member_action_needed", retryable)
    if retryable:
        return Treatment(TREATMENT_RETRY, "retries_remain", retryable)
    if verdict == RETRYABLE:
        return Treatment(TREATMENT_LINK, "retries_exhausted", retryable)
    return Treatment(TREATMENT_REVIEW, "cause_unknown", retryable)
