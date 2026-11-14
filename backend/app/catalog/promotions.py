"""MOD-016 COM-02-R04 and R05: which promotions apply, which do not, and why not.

COM-02-R04 names five ways a discount is reached -- an automatic promotion, a coupon, a
corporate rate, a member tier, a staff discount -- and COM-02-R05 names the conditions:
eligibility, stacking, usage limits, minimum spend, blackout dates and approval thresholds.

Three rules carry this module, and each exists because the obvious version is wrong:

* **A rejection is explained by name.** "Not eligible" is useless to the person at the counter
  being asked why the code did not work; "minimum spend of 50.00 not met, subtotal was 40.00" is
  an answer they can act on. Every rule returns its own reason, which is why eligibility is rows
  with named kinds rather than an expression language -- an expression that evaluated to false
  could not say which clause did it.

* **Stacking is decided before any arithmetic happens.** Within a stacking group exactly one
  promotion survives; across groups they combine. Doing it this way round means the resolver
  never has to un-apply a discount, and it means the choice of survivor is explainable on its
  own terms rather than as a consequence of the order of a loop.

* **An unknown rule kind refuses the promotion.** The opposite -- ignoring a rule this code does
  not recognise -- would make a condition somebody wrote turn into a discount nobody meant to
  give, which is MOD-008's "an unknown attribute must not grant" applied to money. A rule kind
  reaches this module only through a CHECK constraint, so the branch is unreachable today and
  is written the safe way regardless.

Nothing here reads a row. The caller loads the promotions and their rules and the redemption
counts, and this module decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.billing import money
from app.catalog.pricing import Step

#: What COM-02-R04 lists. The kinds differ in how a promotion is *reached*, not in what it does.
PROMOTION_KINDS = (
    "automatic", "coupon", "corporate_rate", "member_tier", "staff_discount", "manual",
)

#: COM-02-R05's conditions, as named kinds. Each carries exactly one operand, which the schema
#: enforces per kind so a rule with the wrong operand cannot be stored and read as vacuous.
RULE_KINDS = (
    "minimum_spend", "customer_segment", "product_type", "channel",
    "blackout_dates", "max_total_redemptions", "max_per_subject",
)


class PromotionError(ValueError):
    """A promotion input this module will not accept."""


@dataclass(frozen=True)
class Rule:
    kind: str
    amount_minor: int | None = None
    quantity: int | None = None
    text_value: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class Promotion:
    promotion_key: str
    kind: str
    percent_bp: int | None = None
    amount_minor: int | None = None
    currency: str | None = None
    stacking_group: str = "default"
    priority: int = 0
    approval_threshold_bp: int = 0
    status: str = "active"
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    rules: tuple[Rule, ...] = ()


@dataclass(frozen=True)
class Usage:
    """How often a promotion has been redeemed, counted from the redemption ledger.

    Counted rather than stored on the promotion: a `times_redeemed` column is a second copy of
    the truth that can disagree with the rows beside it, and it is what two concurrent
    redemptions would contend on.

    **`subject_known` says whether `by_subject` means anything.** A caller that supplies no
    subject gets `by_subject = 0`, which is indistinguishable from "this person has never used
    it" -- so a `max_per_subject` rule was satisfied by leaving a field out, and the control
    bound only the honest caller. A rule that cannot be evaluated must refuse, which is
    MOD-008's "an unknown attribute must not grant" applied to a rule's *input* rather than to
    its kind.
    """

    total: int = 0
    by_subject: int = 0
    subject_known: bool = False


#: Reason codes `check_eligibility` returns. The service decides what to do by code and never
#: by matching words in the prose, because the prose is written for the person at the counter
#: and is edited for their benefit. The first version of `redeem_coupon` tested
#: `any(word in reason for word in ("redeemed", "revoked", "ended", "not started"))`, which
#: meant four English words were the whole enforcement of every usage limit in the module: a
#: draft promotion reads "is draft, not active" and matched none of them, so a code on a
#: campaign nobody activated redeemed -- and a promotion keyed `extended.summer` contains
#: "ended", so a benign rejection naming it refused a legitimate redemption.
NOT_ACTIVE = "not_active"
NOT_STARTED = "not_started"
ENDED = "ended"
CURRENCY_MISMATCH = "currency_mismatch"
MINIMUM_SPEND_NOT_MET = "minimum_spend_not_met"
SEGMENT_MISMATCH = "segment_mismatch"
PRODUCT_TYPE_MISMATCH = "product_type_mismatch"
CHANNEL_MISMATCH = "channel_mismatch"
BLACKED_OUT = "blacked_out"
TOTAL_LIMIT_REACHED = "total_limit_reached"
SUBJECT_LIMIT_REACHED = "subject_limit_reached"
SUBJECT_REQUIRED = "subject_required"
RULE_INCOMPLETE = "rule_incomplete"
UNKNOWN_RULE_KIND = "unknown_rule_kind"
ELIGIBLE = "eligible"

#: The only codes a redemption may *skip*, and the list is deliberately the whole exception.
#: These four are the basket conditions, which a redemption does not have the basket to
#: re-evaluate -- they were evaluated against the real basket when the price was resolved.
#: Everything else is refused, so the default for a code nobody thought about is to refuse.
SKIPPABLE_AT_REDEMPTION = frozenset({
    MINIMUM_SPEND_NOT_MET, SEGMENT_MISMATCH, PRODUCT_TYPE_MISMATCH, CHANNEL_MISMATCH,
})

#: Rules that bound how often a promotion may be used, as opposed to what it may be used on.
#: A promotion carrying one of these is only as good as the ledger that counts it, which is
#: why `service.create_promotion` refuses one on a kind no redemption is ever written for.
USAGE_RULE_KINDS = frozenset({"max_total_redemptions", "max_per_subject"})


@dataclass(frozen=True)
class Failure:
    """One rule that did not pass, by code and in words."""

    code: str
    reason: str


@dataclass(frozen=True)
class Eligibility:
    """Every reason this promotion did not apply, not just the first one.

    **Every rule is evaluated.** Returning on the first failure made the answer depend on the
    order the rules came back in -- `_promotion_row` orders them by kind, and `blackout_dates`,
    `channel` and `customer_segment` all sort before `max_per_subject` and
    `max_total_redemptions` -- so a coupon carrying a channel rule *and* a one-use limit failed
    on the channel, produced a reason the redemption path did not recognise, and the limit was
    never reached at all. A single-use code was unlimited, and which rule you added decided it.
    """

    failures: tuple[Failure, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def code(self) -> str:
        return self.failures[0].code if self.failures else ELIGIBLE

    @property
    def reason(self) -> str:
        return "; ".join(f.reason for f in self.failures)

    def blocks_redemption(self) -> Failure | None:
        """The first failure a redemption may not skip, or None.

        Fail-closed by construction: the question asked is "is this code skippable", not "is
        this code one of the ones I remembered to refuse".
        """
        for failure in self.failures:
            if failure.code not in SKIPPABLE_AT_REDEMPTION:
                return failure
        return None


@dataclass(frozen=True)
class Verdict:
    promotion_key: str
    eligible: bool
    reason: str
    discount_minor: int = 0
    steps: tuple[Step, ...] = ()


def check_eligibility(
    promotion: Promotion, *, subtotal_minor: int, currency: str, channel: str,
    customer_segment: str, product_type: str, at: datetime, usage: Usage,
) -> Eligibility:
    """Every reason this promotion may not apply, by code and in words.

    The window and the status come first because they are the commonest reason a code fails and
    the cheapest to explain: "this promotion ended on the fourteenth" needs no further detail.
    They short-circuit -- a promotion that is not live has nothing to say about its rules -- and
    the rules themselves do not, so a caller can always see every condition that failed.
    """
    key = promotion.promotion_key
    if promotion.status != "active":
        return Eligibility((Failure(NOT_ACTIVE, f"{key} is {promotion.status}, not active"),))
    if promotion.effective_from is not None and promotion.effective_from > at:
        return Eligibility((Failure(NOT_STARTED, f"{key} has not started yet"),))
    if promotion.effective_to is not None and promotion.effective_to <= at:
        return Eligibility((Failure(ENDED, f"{key} has ended"),))
    if promotion.amount_minor is not None and promotion.currency != currency:
        return Eligibility((Failure(CURRENCY_MISMATCH, (
            f"{key} is a fixed {promotion.currency} discount and this sale is in {currency}"
        )),))

    failures: list[Failure] = []
    for rule in promotion.rules:
        if rule.kind == "minimum_spend":
            if rule.amount_minor is None:
                failures.append(Failure(
                    RULE_INCOMPLETE, f"{key} has a minimum spend with no amount"))
            elif subtotal_minor < rule.amount_minor:
                failures.append(Failure(MINIMUM_SPEND_NOT_MET, (
                    f"minimum spend of {rule.amount_minor} not met, subtotal was "
                    f"{subtotal_minor}")))
        elif rule.kind == "customer_segment":
            if rule.text_value != customer_segment:
                failures.append(Failure(SEGMENT_MISMATCH, (
                    f"{key} is for the {rule.text_value} segment and this sale is "
                    f"{customer_segment}")))
        elif rule.kind == "product_type":
            if rule.text_value != product_type:
                failures.append(Failure(PRODUCT_TYPE_MISMATCH, (
                    f"{key} applies to {rule.text_value} and this is a "
                    f"{product_type or 'unknown'} product")))
        elif rule.kind == "channel":
            if rule.text_value != channel:
                failures.append(Failure(CHANNEL_MISMATCH, (
                    f"{key} is for the {rule.text_value} channel and this sale is on "
                    f"{channel}")))
        elif rule.kind == "blackout_dates":
            if rule.date_from is None or rule.date_to is None:
                failures.append(Failure(
                    RULE_INCOMPLETE, f"{key} has an incomplete blackout window"))
            elif rule.date_from <= at.date() <= rule.date_to:
                failures.append(Failure(BLACKED_OUT, (
                    f"{key} is blacked out from {rule.date_from} to {rule.date_to}")))
        elif rule.kind == "max_total_redemptions":
            if rule.quantity is None:
                failures.append(Failure(
                    RULE_INCOMPLETE, f"{key} has a usage limit with no quantity"))
            elif usage.total >= rule.quantity:
                failures.append(Failure(TOTAL_LIMIT_REACHED, (
                    f"{key} has been redeemed {usage.total} times and allows "
                    f"{rule.quantity}")))
        elif rule.kind == "max_per_subject":
            if rule.quantity is None:
                failures.append(Failure(
                    RULE_INCOMPLETE, f"{key} has a per-person limit with no quantity"))
            elif not usage.subject_known:
                # **A rule whose input is missing refuses.** `by_subject` is 0 both for "this
                # person has never used it" and for "nobody said who this is", so accepting
                # the second reading meant a per-person limit was turned off by omitting a
                # field -- refusing the honest caller and waving through the other one.
                failures.append(Failure(SUBJECT_REQUIRED, (
                    f"{key} is limited per person and this request names nobody")))
            elif usage.by_subject >= rule.quantity:
                failures.append(Failure(SUBJECT_LIMIT_REACHED, (
                    f"this person has redeemed {key} {usage.by_subject} times and may redeem "
                    f"it {rule.quantity}")))
        else:
            # **Unreachable through the schema, and refused rather than ignored.** A rule kind
            # this code does not recognise is a condition somebody wrote; ignoring it would turn
            # it into a discount nobody meant to give, which is MOD-008's "an unknown attribute
            # must not grant" applied to money.
            failures.append(Failure(UNKNOWN_RULE_KIND, (
                f"{key} carries a rule of kind {rule.kind!r}, which this build does not "
                f"evaluate")))
    return Eligibility(tuple(failures))


def discount_for(promotion: Promotion, subtotal_minor: int) -> int:
    """What this promotion takes off the given subtotal, in minor units.

    A percentage applies to whatever is left when it is reached, so two percentages in different
    stacking groups compound rather than summing -- which is the ordinary commercial meaning and
    is why the resolver passes a running subtotal rather than the list price.
    """
    if promotion.percent_bp is not None:
        return money.apply_rate_bp(subtotal_minor, promotion.percent_bp)
    if promotion.amount_minor is not None:
        return promotion.amount_minor
    raise PromotionError(
        f"{promotion.promotion_key} is neither a percentage nor an amount")


def select(
    promotions: list[Promotion], *, subtotal_minor: int, currency: str, channel: str,
    customer_segment: str, product_type: str, at: datetime,
    usage: dict[str, Usage] | None = None,
) -> tuple[list[tuple[str, int, list[Step]]], list[Verdict]]:
    """Decide which promotions apply and in what order, and explain every one that does not.

    Returns `(applied, verdicts)` where `applied` is what `pricing.resolve` consumes --
    `(key, discount_minor, steps)` in application order -- and `verdicts` is the full account,
    eligible and not.

    **Within a stacking group exactly one survives.** The winner is the highest priority; ties
    break on the larger discount, then on the key. Priority first because a tenant sets it
    explicitly and honouring their configuration is the point; the discount as the tiebreak
    because between two promotions the tenant ranked equally, the member should get the better
    one. The key last because it is unique, so the answer is total and no planner gets a vote.

    **The discount each group's winner takes is computed against the list subtotal, not the
    running one, for the purpose of choosing between them.** Otherwise which promotion looked
    biggest would depend on which group happened to be evaluated first, and the choice would
    stop being explainable on its own terms.
    """
    counts = usage or {}
    verdicts: list[Verdict] = []
    eligible: list[tuple[Promotion, int]] = []

    for promotion in sorted(promotions, key=lambda p: p.promotion_key):
        verdict = check_eligibility(
            promotion, subtotal_minor=subtotal_minor, currency=currency, channel=channel,
            customer_segment=customer_segment, product_type=product_type, at=at,
            usage=counts.get(promotion.promotion_key, Usage()))
        if not verdict.ok:
            verdicts.append(Verdict(promotion.promotion_key, False, verdict.reason))
            continue
        amount = discount_for(promotion, subtotal_minor)
        eligible.append((promotion, amount))
        verdicts.append(Verdict(
            promotion.promotion_key, True, f"{promotion.promotion_key} is eligible", amount))

    # One per stacking group, chosen totally.
    by_group: dict[str, list[tuple[Promotion, int]]] = {}
    for promotion, amount in eligible:
        by_group.setdefault(promotion.stacking_group, []).append((promotion, amount))

    winners: list[tuple[Promotion, int]] = []
    for group in sorted(by_group):
        members = sorted(
            by_group[group],
            key=lambda pair: (-pair[0].priority, -pair[1], pair[0].promotion_key))
        winner, amount = members[0]
        winners.append((winner, amount))
        for loser, _ in members[1:]:
            verdicts = [
                Verdict(v.promotion_key, False,
                        f"{winner.promotion_key} took the {group} stacking group",
                        0, v.steps)
                if v.promotion_key == loser.promotion_key else v
                for v in verdicts
            ]

    # Across groups, in a total order, applied to the running subtotal by the resolver.
    winners.sort(key=lambda pair: (-pair[0].priority, pair[0].stacking_group,
                                   pair[0].promotion_key))
    applied: list[tuple[str, int, list[Step]]] = []
    running = subtotal_minor
    for promotion, _ in winners:
        amount = discount_for(promotion, running)
        applied.append((
            promotion.promotion_key,
            amount,
            [Step("promotion_eligible",
                  f"{promotion.promotion_key} ({promotion.kind}, group "
                  f"{promotion.stacking_group}, priority {promotion.priority})", amount)],
        ))
        running = max(0, running - amount)
    return applied, verdicts


def highest_threshold_bp(promotions: list[Promotion], applied: list[str]) -> int:
    """The strictest approval threshold among the promotions that actually applied.

    **The strictest, not the first.** A sale that triggered a campaign requiring approval above
    20% and another requiring it above 50% needs the 20% rule honoured; taking either the first
    or the highest number would let a looser policy sitting beside a stricter one turn the
    stricter one off -- which is MOD-008's own finding about combining policies, where picking
    the highest threshold was wrong for the same reason.
    """
    thresholds = [
        p.approval_threshold_bp for p in promotions
        if p.promotion_key in applied and p.approval_threshold_bp > 0
    ]
    return min(thresholds) if thresholds else 0
