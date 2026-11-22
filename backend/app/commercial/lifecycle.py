"""MOD-017 COM-01: the membership lifecycle, as decisions with no I/O.

COM-01-R04 names eleven acts -- freeze, pause, medical hold, upgrade, downgrade, transfer,
renewal, cancellation, reinstatement, expiry and suspension -- and COM-01-R07 requires the whole
history to be reconstructible "as of" any instant. Three rules carry this module, and each
exists because the obvious version is wrong:

* **A decision and its effect are two different dates.** A cancellation decided today under a
  thirty-day notice period takes effect in thirty days, and both dates matter to the argument
  that follows. Every function here takes `decided_on` and returns an `effective_on`, and they
  are never assumed equal.

* **The state is derived from the history, never the other way round.** `status_as_of` replays
  the recorded changes; the column on `mem_memberships` is a cache of its answer. A function
  that read the cache to decide the next transition would make the history decorative, and a
  cache that disagreed with it would be unresolvable.

* **Membership state, billing state and access state are never conflated.** Paragraph 1496. A
  frozen membership is not an unpaid one, and nothing here reads an invoice. What a lifecycle
  change *costs* is disclosed and recorded; whether it was paid is COM-03's question.

Dates are `date`, not `datetime`: a membership starts on a day, and the instant it starts is a
question about the location's timezone that the caller answers, not this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.billing import money

#: The version of the rules in this module. Recorded on nothing yet -- there is no stored
#: lifecycle decision to stamp -- and kept so that when one exists it has something to name.
POLICY_VERSION = 1

#: The states a membership can hold. `grace` is COM-01-R05's grace period, which is a state and
#: not merely a date because the access policy differs inside it.
STATUSES = (
    "pending", "active", "frozen", "grace", "suspended", "cancelled", "expired",
    "transferred",
)

#: States from which nothing moves. A cancelled membership is not reinstated -- a reinstatement
#: creates a new agreement, because the terms have to be re-agreed.
TERMINAL = ("cancelled", "expired", "transferred")

#: COM-01-R04's acts, and the edges each one is allowed to walk. **Written as data rather than
#: as a chain of `if`s**, so a mutation sweep can read the table and a reviewer can see the
#: whole machine at once. An act missing from here cannot be performed at all, which is the
#: direction that fails closed.
EDGES: dict[str, tuple[tuple[str, str], ...]] = {
    "activation": (("pending", "active"),),
    "freeze": (("active", "frozen"),),
    "medical_hold": (("active", "frozen"), ("grace", "frozen")),
    # A resume comes back to `active` from a freeze, and from the grace period once the debt
    # that put it there is settled.
    "resume": (("frozen", "active"), ("grace", "active"), ("suspended", "active")),
    "grace_entry": (("active", "grace"),),
    "suspension": (("active", "suspended"), ("grace", "suspended"), ("frozen", "suspended")),
    # A renewal does not move the status. It extends the term, which is why it is the one act
    # whose from and to are the same and why `mem_lifecycle_changes_moves` admits it.
    "renewal": (("active", "active"), ("grace", "active")),
    "upgrade": (("active", "active"), ("frozen", "frozen")),
    "downgrade": (("active", "active"), ("frozen", "frozen")),
    "transfer": (("active", "transferred"), ("frozen", "transferred")),
    "cancellation": (
        ("pending", "cancelled"), ("active", "cancelled"), ("frozen", "cancelled"),
        ("grace", "cancelled"), ("suspended", "cancelled"),
    ),
    "expiry": (("active", "expired"), ("grace", "expired"), ("suspended", "expired")),
    # **Reinstatement comes back from suspension only.** A cancelled or expired membership is
    # re-sold rather than reinstated: the terms, the price and the contract version all have to
    # be re-agreed, and pretending otherwise would revive an agreement nobody signed. COM-01-R04
    # asks for reinstatement and this is the honest reading of which state it reinstates from.
    "reinstatement": (("suspended", "active"),),
}


class LifecycleError(ValueError):
    """A lifecycle input this module will not accept."""


@dataclass(frozen=True)
class Terms:
    """The contract terms a decision is measured against, as data.

    Copied from the contract version the agreement was signed under -- not re-read from
    whatever is current, which is the whole reason a signature means anything.
    """

    minimum_term_months: int = 0
    notice_days: int = 0
    renewal_mode: str = "manual"
    cancellation_mode: str = "end_of_term"
    freeze_days_per_year: int = 0
    grace_days: int = 0
    # **Whether the member may leave inside the minimum term, and what that costs.**
    #
    # `None` is "they may not", which is what every contract in this build said until now and
    # what `cancellation_effective_on` enforces by pushing the date out to the end of the
    # term. An integer is "they may, for this many months of the agreement amount" -- the
    # buy-out an ordinary gym contract offers, and what ADM-MSH-07 discloses: "his 12-month
    # commitment runs to March. Cancelling now triggers a two-month fee of JOD 80.00, and his
    # access ends on 7 September after the notice period."
    #
    # **Three states in one nullable field, because zero is a real term and not an absence.**
    # A contract that lets somebody walk away free inside the term is a different product
    # from one that holds them to it, and a boolean beside an integer would let the two
    # disagree. The sources name a "cancellation policy" and do not say what it is, so which
    # of the three a tenant sells is theirs to write on the contract version.
    early_termination_months: int | None = None


@dataclass(frozen=True)
class Change:
    """One recorded lifecycle change, as the history stores it."""

    change_kind: str
    from_status: str
    to_status: str
    effective_on: date


@dataclass(frozen=True)
class FreezeWindow:
    """One freeze, for the allowance arithmetic."""

    starts_on: date
    ends_on: date | None = None
    counts_against_allowance: bool = True
    extends_term: bool = True


@dataclass(frozen=True)
class Decision:
    """What a lifecycle command decided, and the reasoning behind it."""

    change_kind: str
    from_status: str
    to_status: str
    effective_on: date
    #: What the member is told this will cost, in minor units. `None` means no fee was
    #: calculated, which is different from zero -- COM-01-R06 requires the disclosure and a
    #: missing one is not a free change.
    fee_minor: int | None = None
    #: The new end date, where the act moves it.
    ends_on: date | None = None
    steps: tuple[str, ...] = field(default_factory=tuple)


def check_transition(change_kind: str, from_status: str, to_status: str) -> None:
    """Refuse an edge the machine does not have.

    **Unknown kinds refuse rather than pass.** A change kind this module does not evaluate is
    an act somebody wrote; admitting it would move a membership by a rule nobody checked, which
    is MOD-008's "an unknown attribute must not grant" applied to a state machine.
    """
    if from_status not in STATUSES:
        raise LifecycleError(f"{from_status!r} is not a membership status")
    if to_status not in STATUSES:
        raise LifecycleError(f"{to_status!r} is not a membership status")
    allowed = EDGES.get(change_kind)
    if allowed is None:
        raise LifecycleError(f"{change_kind!r} is not a lifecycle change this build performs")
    if (from_status, to_status) not in allowed:
        raise LifecycleError(
            f"a {change_kind} does not move a membership from {from_status} to {to_status}")


def status_as_of(created_status: str, changes: list[Change], moment: date) -> str:
    """The status this membership held on `moment`, replayed from the history.

    COM-01-R07's "as-of reconstruction". **Ordered totally**, by effective date and then by the
    kind, so two changes effective on the same day give the same answer on every machine -- a
    replay whose result depended on row order would be worse than no replay, because it would
    be wrong only sometimes.

    A change effective *after* `moment` is not applied, which is the point: a cancellation
    decided in January and effective in March leaves the membership active in February, and
    that is exactly the fact a dispute turns on.
    """
    status = created_status
    for change in sorted(changes, key=lambda c: (c.effective_on, c.change_kind)):
        if change.effective_on <= moment:
            status = change.to_status
    return status


def _add_months(start: date, months: int) -> date:
    """`start` plus `months`, clamped into the target month.

    Written out rather than imported because the stdlib has no month arithmetic and the
    alternative is a dependency for eleven lines. The clamp is the whole subtlety: a membership
    starting on the 31st of January and running one month ends on the 28th of February, not on
    a date that does not exist.
    """
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    last_day = (next_month_start - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))


def minimum_term_end(starts_on: date, terms: Terms) -> date | None:
    """When the member's commitment runs out, or None where there is none."""
    if terms.minimum_term_months <= 0:
        return None
    return _add_months(starts_on, terms.minimum_term_months)


def freeze_days_used(windows: list[FreezeWindow], year_start: date, year_end: date) -> int:
    """How many allowance-counting freeze days fall inside the window.

    **Only the overlap counts.** A freeze that began in December and ran into February spends
    part of each contract year's allowance, and attributing the whole of it to either year is
    how a member either loses days they never used or gets a second allowance by timing.

    An open-ended freeze is counted to `year_end`, which is the conservative direction: it is
    spending the allowance right now, and treating it as free until it closes would let
    somebody hold a membership frozen indefinitely inside a thirty-day allowance.
    """
    used = 0
    for window in windows:
        if not window.counts_against_allowance:
            continue
        start = max(window.starts_on, year_start)
        end = min(window.ends_on or year_end, year_end)
        if end >= start:
            used += (end - start).days + 1
    return used


def check_freeze(
    *, requested_days: int, terms: Terms, already_used: int,
) -> None:
    """Refuse a freeze the contract does not allow.

    The allowance is what the member agreed to. A freeze beyond it is a commercial decision
    somebody has to make deliberately, which in this module means a different act with its own
    approval -- not a longer freeze that quietly exceeds the contract.
    """
    if requested_days <= 0:
        raise LifecycleError("a_freeze_lasts_at_least_one_day")
    if requested_days > 365:
        raise LifecycleError("a_freeze_lasts_at_most_a_year")
    if terms.freeze_days_per_year <= 0:
        raise LifecycleError("this_contract_allows_no_freezing")
    if already_used + requested_days > terms.freeze_days_per_year:
        raise LifecycleError(
            f"this contract allows {terms.freeze_days_per_year} freeze days a year and "
            f"{already_used} have been used; {requested_days} more would exceed it")


def counts_against_allowance(freeze_kind: str) -> bool:
    """Whether this kind of hold spends the contract's annual allowance.

    **A medical hold does not**, which is the ordinary commercial term and the reason the kind
    exists separately. It is derived here and *stored* on the row rather than re-derived later,
    because the contract may change and the decision made at the time has to stand.
    """
    if freeze_kind not in ("freeze", "pause", "medical_hold"):
        raise LifecycleError(f"{freeze_kind!r} is not a kind of hold")
    return freeze_kind != "medical_hold"


def cancellation_effective_on(
    *, decided_on: date, terms: Terms, period_end: date | None,
    minimum_term_ends_on: date | None,
) -> tuple[date, tuple[str, ...]]:
    """When a cancellation decided today takes effect, and why.

    COM-01-R02's notice and cancellation policy, as arithmetic. Three modes, and the reasoning
    is returned alongside the date because COM-01-R06 requires the member to understand the
    consequence before confirming -- a date with no explanation is the thing they dispute.

    **The minimum term wins.** A member inside their commitment cannot cancel out of it by
    giving notice: the notice runs, and the effective date is whichever is later. That is what
    a minimum term *is*, and computing it the other way round is the defect that shows up as a
    member who stopped paying four months early.
    """
    steps: list[str] = [f"decided_on: {decided_on.isoformat()}"]
    if terms.cancellation_mode == "immediate":
        candidate = decided_on
        steps.append("cancellation_mode: immediate")
    elif terms.cancellation_mode == "end_of_notice":
        candidate = decided_on + timedelta(days=terms.notice_days)
        steps.append(f"notice_days: {terms.notice_days}")
    elif terms.cancellation_mode == "end_of_term":
        after_notice = decided_on + timedelta(days=terms.notice_days)
        candidate = max(after_notice, period_end) if period_end else after_notice
        steps.append(f"notice_days: {terms.notice_days}")
        if period_end:
            steps.append(f"period_end: {period_end.isoformat()}")
    else:
        raise LifecycleError(
            f"{terms.cancellation_mode!r} is not a cancellation mode this build evaluates")
    if minimum_term_ends_on and minimum_term_ends_on > candidate:
        if terms.early_termination_months is None:
            steps.append(f"minimum_term_ends_on: {minimum_term_ends_on.isoformat()} (later)")
            candidate = minimum_term_ends_on
        else:
            # **The term still ends when it ends; what moves is the member's access.** A
            # contract offering a buy-out is one where notice is the date and the commitment
            # is the price, so the date stands and `cancellation_fee` charges for the rest.
            # Pushing the date out *and* charging the buy-out would make the member pay twice
            # for the same months, which is the direction nobody would defend.
            steps.append(
                f"minimum_term_ends_on: {minimum_term_ends_on.isoformat()} (bought out at "
                f"{terms.early_termination_months} months)")
    steps.append(f"effective_on: {candidate.isoformat()}")
    return candidate, tuple(steps)


def cancellation_fee(
    *, effective_on: date, terms: Terms, amount_minor: int, period_start: date | None,
    period_end: date | None, minimum_term_ends_on: date | None,
) -> tuple[int, dict[str, int], tuple[str, ...]]:
    """What a cancellation costs, in parts. COM-01-R06's disclosure, as arithmetic.

    **Two components, named separately, because they answer different questions** and a
    member disputing one should not have to take the other on trust. The period part is what
    they owe for the part of the current period they will have used by the time access ends;
    the buy-out is what the contract charges for leaving the commitment early. ADM-MSH-07
    draws one headline figure and this returns the headline *and* its parts, which is more
    than the canvas asks for and is what makes the headline checkable.

    **The parts are kept apart rather than summed early** for the reason MOD-018 keeps four
    wallet balances rather than one: a total that has lost its components cannot be
    reconciled against anything, and the first question about a fee is always which half of
    it is which.

    A buy-out is charged only where the contract offers one and the member is actually
    leaving inside the term. `early_termination_months = 0` is a contract that lets them
    leave free, and it produces a step saying so -- a zero that means "no charge" and a zero
    that means "no early exit at all" must not read alike, which is the whole reason
    `Terms.early_termination_months` is nullable.
    """
    if amount_minor < 0:
        raise LifecycleError("an_agreement_amount_is_not_negative")
    steps: list[str] = []
    parts: dict[str, int] = {"period_minor": 0, "early_termination_minor": 0}

    if period_start is not None and period_end is not None:
        remaining, prorate_steps = prorated_amount(
            full_amount_minor=amount_minor, period_start=period_start,
            period_end=period_end, effective_on=effective_on)
        parts["period_minor"] = amount_minor - remaining
        steps.extend(prorate_steps)
        steps.append(f"period_minor: {parts['period_minor']} (the part already used)")
    else:
        steps.append("period_minor: 0 (this membership has no billing period)")

    months = terms.early_termination_months
    # **Validated before the branches, not inside one.** The first version checked this in
    # the branch that charges a buy-out, so a negative one on a contract whose term had
    # already been served was reported as zero rather than refused -- a guard with a window,
    # which is the shape this build has found in nine modules. The database forbids the value
    # outright; this is the half that holds for a caller who is not the database.
    if months is not None and months < 0:
        raise LifecycleError("a_buy_out_is_not_negative")
    if months is None:
        steps.append("early_termination_minor: 0 (this contract has no buy-out)")
    elif minimum_term_ends_on is None or effective_on >= minimum_term_ends_on:
        steps.append(
            "early_termination_minor: 0 (access ends on or after the minimum term, so "
            "nothing is being left early)")
    else:
        parts["early_termination_minor"] = months * amount_minor
        steps.append(
            f"early_termination_minor: {months} x {amount_minor} = "
            f"{parts['early_termination_minor']} (leaving before "
            f"{minimum_term_ends_on.isoformat()})")

    total = parts["period_minor"] + parts["early_termination_minor"]
    steps.append(f"fee_due_minor: {total}")
    return total, parts, tuple(steps)


def prorated_amount(
    *, full_amount_minor: int, period_start: date, period_end: date, effective_on: date,
) -> tuple[int, tuple[str, ...]]:
    """COM-01-R05's proration: the part of a period that falls on or after `effective_on`.

    **Actual days over actual days**, which is MOD-015's convention and is adopted rather than
    re-chosen -- two proration rules in one build is a pair of numbers that disagree on an
    invoice, and MOD-016 shipped a second rounding rule once and a reviewer found it.

    The period is inclusive of both ends, so a one-day period is one day and not zero. An
    `effective_on` before the period is the whole period; after it, nothing.
    """
    if period_end < period_start:
        raise LifecycleError("a_period_does_not_end_before_it_starts")
    if full_amount_minor < 0:
        raise LifecycleError("a_period_amount_is_not_negative")
    total_days = (period_end - period_start).days + 1
    if effective_on <= period_start:
        remaining = total_days
    elif effective_on > period_end:
        remaining = 0
    else:
        remaining = (period_end - effective_on).days + 1
    amount = money.round_half_up(full_amount_minor * remaining, total_days)
    return amount, (
        f"period: {period_start.isoformat()}..{period_end.isoformat()} ({total_days} days)",
        f"remaining: {remaining} days from {effective_on.isoformat()}",
        f"prorated: {amount} of {full_amount_minor} minor units",
    )


def grace_ends_on(*, entered_on: date, terms: Terms) -> date:
    """When the grace period runs out.

    Zero grace days means the grace period ends the day it starts, which is a real contract
    term and not a mistake: some contracts suspend access the moment a payment fails.
    """
    if terms.grace_days < 0:
        raise LifecycleError("a_grace_period_is_not_negative")
    return entered_on + timedelta(days=terms.grace_days)


def renewal_period(
    *, current_end: date, billing_period: str,
) -> tuple[date, date]:
    """The next period a renewal opens, as `(start, end)`.

    The new period starts the day after the old one ends, so periods tile without a gap and
    without an overlap -- a day in both periods is a day a member is billed twice for, and a
    day in neither is one they trained for free.
    """
    start = current_end + timedelta(days=1)
    if billing_period == "weekly":
        end = start + timedelta(days=6)
    elif billing_period == "monthly":
        end = _add_months(start, 1) - timedelta(days=1)
    elif billing_period == "quarterly":
        end = _add_months(start, 3) - timedelta(days=1)
    elif billing_period == "annual":
        end = _add_months(start, 12) - timedelta(days=1)
    else:
        raise LifecycleError(f"{billing_period!r} is not a renewable billing period")
    return start, end
