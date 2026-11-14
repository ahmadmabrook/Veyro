"""MOD-016 COM-02: resolving a price, deterministically, with the reasoning kept.

Paragraph 10220 states the control in one sentence: **"pricing resolution is deterministic and
returns an explanation."** Both halves are load-bearing and both are easy to lose.

**Deterministic** means the same inputs against the same rows give the same answer, every time,
on any machine. That is not free: the obvious implementation picks "the matching price book"
and "the applicable promotions" from query results, and a query without a total sort returns
rows in whatever order the planner chose today. So every ordering here is total -- down to the
key, which is unique -- and nothing depends on the order the caller supplied either.

**An explanation** means the reasoning, not the number. A resolver that returned `4500` and
nothing else would be impossible to dispute at a counter, which is exactly where these numbers
are read out loud: a member asking "why is it that much" is asking which price book, which
promotion, and which promotion did *not* apply and why not. So `resolve` names every step,
including the rejections -- "minimum spend of 50.00 not met, subtotal was 40.00" is an answer
and "not eligible" is not.

**Everything is an integer count of minor units.** `app.billing.money` owns the arithmetic and
is imported rather than reimplemented: MOD-015 already chose half-away-from-zero rounding and
largest-remainder allocation and wrote down why, and a second rounding rule in one build is a
pair of numbers that disagree on a receipt.

`POLICY_VERSION` is recorded on every stored resolution. When the rules below change, it
changes, so a different answer to the same question is visible as a different policy rather than
as an unexplained difference in the number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.billing import money

#: The version of the rules in this module. **Bump it whenever a rule here changes**, because
#: `cat_price_resolutions.policy_version` is the only thing that lets somebody comparing two
#: resolutions tell "the catalogue changed" from "the resolver changed".
POLICY_VERSION = 1

#: The sales channels a price book may be scoped to. `any` is the wildcard, and it is a value
#: rather than NULL so the specificity ordering below has something total to sort on.
CHANNELS = ("any", "pos", "member_app", "admin_web", "crm", "kiosk", "web")


class PricingError(ValueError):
    """A pricing input this module will not accept."""


@dataclass(frozen=True)
class Request:
    """What is being priced, and for whom.

    Every field the resolver reads is here: a resolution that consulted something not in this
    dataclass could not be reproduced from the stored snapshot, which is the property the
    snapshot exists to have.
    """

    variant_id: str
    currency: str
    at: datetime
    quantity: int = 1
    channel: str = "any"
    customer_segment: str = "any"
    brand_id: str | None = None
    location_id: str | None = None
    #: The product type of the variant being priced, which some eligibility rules match on.
    product_type: str = ""
    subject_id: str | None = None


@dataclass(frozen=True)
class PriceBook:
    """A price book's matching dimensions. COM-02-R02's seven, as data."""

    price_book_id: str
    price_book_key: str
    currency: str
    effective_from: datetime
    effective_to: datetime | None = None
    brand_id: str | None = None
    location_id: str | None = None
    channel: str = "any"
    customer_segment: str = "any"
    priority: int = 0
    status: str = "active"


@dataclass(frozen=True)
class Price:
    """One price in one book for one variant, over one window."""

    price_id: str
    price_book_id: str
    variant_id: str
    amount_minor: int
    currency: str
    effective_from: datetime
    effective_to: datetime | None = None
    superseded_by: str | None = None


@dataclass(frozen=True)
class Step:
    """One line of the explanation: what happened, to what, and why."""

    code: str
    detail: str
    amount_minor: int = 0

    def render(self) -> str:
        return f"{self.code}: {self.detail}" if not self.amount_minor else (
            f"{self.code}: {self.detail} ({self.amount_minor} minor units)"
        )


@dataclass(frozen=True)
class Resolution:
    """What a price resolved to, and the whole reasoning behind it."""

    variant_id: str
    price_book_id: str
    price_id: str
    currency: str
    list_amount_minor: int
    discount_minor: int
    final_amount_minor: int
    applied_promotions: tuple[str, ...] = ()
    rejected_promotions: tuple[str, ...] = ()
    steps: tuple[Step, ...] = ()
    policy_version: int = POLICY_VERSION
    #: The total discount as a share of the list, which is what an approval threshold is
    #: measured against. Derived rather than stored twice.
    discount_bp: int = 0
    explanation: tuple[str, ...] = field(default_factory=tuple)


def book_specificity(book: PriceBook, request: Request) -> int | None:
    """How well this book matches, or `None` when it does not match at all.

    **A dimension set on the book must equal the request's; a dimension left wide matches
    anything and scores nothing.** That asymmetry is the whole rule: a book for the `pos`
    channel is not a candidate for a `member_app` sale, and a book with `channel = 'any'` is a
    candidate for both. Scoring the wide match would make a book that specifies nothing beat one
    that specifies a brand, which is backwards.

    The four dimensions score equally, so a tie is possible by design -- that is what `priority`
    is for, and after priority the key breaks the tie so the answer is total.
    """
    if book.status != "active":
        return None
    if book.currency != request.currency:
        return None
    if book.effective_from > request.at:
        return None
    if book.effective_to is not None and book.effective_to <= request.at:
        return None

    score = 0
    for book_value, request_value in (
        (book.brand_id, request.brand_id),
        (book.location_id, request.location_id),
    ):
        if book_value is not None:
            if book_value != request_value:
                return None
            score += 1
    for book_value, request_value in (
        (book.channel, request.channel),
        (book.customer_segment, request.customer_segment),
    ):
        if book_value != "any":
            if book_value != request_value:
                return None
            score += 1
    return score


def choose_book(
    books: list[PriceBook], request: Request, prices: list[Price] | None = None,
) -> tuple[PriceBook, list[Step]]:
    """The one book this sale prices from, with the reason it won and the others lost.

    **Total ordering, three keys deep.** Most specific, then highest priority, then the key --
    which is unique, so there is never a tie the planner gets to break. A resolver whose answer
    depended on row order would fail the requirement in the way nobody notices until two tills
    disagree.

    **A book that does not price this variant is not a candidate**, and that is not an
    optimisation. The first version chose the best-matching book and *then* looked for a price
    in it, so a tenant with two equally-matching books -- the ordinary result of adding a
    seasonal book beside a standing one -- got `no_price_is_in_force` for a variant that was
    priced in the other one, decided by whichever key sorted first. Found by this module's own
    tests before review saw it.
    """
    scored: list[tuple[int, PriceBook]] = []
    steps: list[Step] = []
    matched_but_unpriced = False
    for book in sorted(books, key=lambda b: b.price_book_key):
        score = book_specificity(book, request)
        if score is None:
            steps.append(Step("price_book_skipped",
                              f"{book.price_book_key} does not match this sale"))
            continue
        if prices is not None and not _has_live_price(prices, book, request):
            matched_but_unpriced = True
            steps.append(Step(
                "price_book_has_no_price",
                f"{book.price_book_key} matches this sale but does not price this variant"))
            continue
        scored.append((score, book))
    if not scored:
        # Two different problems, and the caller can act on only one of them: "no book applies
        # to this channel" is a configuration gap, and "the books that apply do not price this
        # variant" is a missing price. Collapsing them into one message would send whoever
        # reads it to the wrong screen.
        raise PricingError(
            "no_price_is_in_force_for_this_variant" if matched_but_unpriced
            else "no_price_book_matches_this_sale")
    scored.sort(key=lambda pair: (-pair[0], -pair[1].priority, pair[1].price_book_key))
    best_score, chosen = scored[0]
    steps.append(Step(
        "price_book_chosen",
        f"{chosen.price_book_key} matched on {best_score} of four dimensions "
        f"at priority {chosen.priority}"))
    for score, book in scored[1:]:
        steps.append(Step(
            "price_book_not_chosen",
            f"{book.price_book_key} matched on {score} at priority {book.priority}"))
    return chosen, steps


def _live_prices(
    prices: list[Price], book: PriceBook, request: Request,
) -> list[Price]:
    """The prices in force in this book for this variant at this instant."""
    return [
        price for price in prices
        if price.price_book_id == book.price_book_id
        and price.variant_id == request.variant_id
        and price.superseded_by is None
        and price.effective_from <= request.at
        and (price.effective_to is None or price.effective_to > request.at)
    ]


def _has_live_price(prices: list[Price], book: PriceBook, request: Request) -> bool:
    return bool(_live_prices(prices, book, request))


def choose_price(prices: list[Price], book: PriceBook, request: Request) -> Price:
    """The price in force in this book for this variant at this instant.

    **The latest `effective_from` at or before the moment wins**, which is what makes
    COM-02-R07 work: re-pricing writes a new row rather than editing the old one, so an order
    resolved last March re-derives by asking this question with March's timestamp.

    A superseded price is skipped even if its window is still open, because supersession is how
    a price written in error is withdrawn before it ever applies.
    """
    live = _live_prices(prices, book, request)
    if not live:
        raise PricingError("no_price_is_in_force_for_this_variant")
    # Total: the newest start, then the id, which is unique.
    live.sort(key=lambda p: (p.effective_from, p.price_id), reverse=True)
    chosen = live[0]
    if chosen.currency != request.currency:
        raise PricingError("the_price_in_force_is_in_another_currency")
    return chosen


def resolve(
    *,
    request: Request,
    books: list[PriceBook],
    prices: list[Price],
    discounts: list[tuple[str, int, list[Step]]] | None = None,
) -> Resolution:
    """Price one line, and say how.

    `discounts` is what `promotions.select` decided: a list of
    `(promotion_key, discount_minor, steps)` already ordered and already reduced to one per
    stacking group. Keeping the eligibility and stacking rules in `promotions` and the
    arithmetic here means neither module has to know how the other decides, and both are
    testable without a database.

    **The discount is clamped at the line total and the clamp is explained.** Two promotions
    that between them exceed the price is a real configuration, and silently returning a
    negative amount -- or, worse, a negative that a later sum turns into a refund -- is the kind
    of arithmetic failure an invoice is one unit away from being wrong about.
    """
    if request.quantity <= 0:
        raise PricingError("a_quantity_is_at_least_one")
    if request.channel not in CHANNELS:
        raise PricingError(f"{request.channel!r} is not a sales channel")

    book, steps = choose_book(books, request, prices)
    price = choose_price(prices, book, request)
    unit = price.amount_minor
    list_total = unit * request.quantity
    steps.append(Step("list_price", f"{request.quantity} x unit price", list_total))

    applied: list[str] = []
    rejected: list[str] = []
    running = list_total
    total_discount = 0
    for key, amount, promotion_steps in (discounts or []):
        steps.extend(promotion_steps)
        if amount <= 0:
            rejected.append(key)
            continue
        taken = min(amount, running)
        if taken < amount:
            steps.append(Step(
                "discount_clamped",
                f"{key} would have taken more than the remaining line total", taken))
        else:
            steps.append(Step("discount_applied", key, taken))
        running -= taken
        total_discount += taken
        applied.append(key)

    final = list_total - total_discount
    # The share of the list that was discounted, which is what an approval threshold is
    # measured against. Zero-priced lines cannot be discounted, so the ratio is defined.
    discount_bp = (
        0 if list_total == 0
        else money.round_half_up(total_discount * money.BASIS_POINTS, list_total)
    )
    steps.append(Step("final_amount", f"{list_total} less {total_discount}", final))
    return Resolution(
        variant_id=request.variant_id,
        price_book_id=book.price_book_id,
        price_id=price.price_id,
        currency=price.currency,
        list_amount_minor=list_total,
        discount_minor=total_discount,
        final_amount_minor=final,
        applied_promotions=tuple(applied),
        rejected_promotions=tuple(rejected),
        steps=tuple(steps),
        discount_bp=discount_bp,
        explanation=tuple(step.render() for step in steps),
    )


def override(
    resolution: Resolution, *, override_amount_minor: int, reason: str,
) -> Resolution:
    """Replace the resolved amount with one a human chose, keeping the whole explanation.

    **This is not a discount and it does not pretend to be one.** It is somebody deciding the
    price, which paragraph 10220 says needs explicit permission and audit -- so the service will
    not call this without a recorded approval, and the resolution it returns carries the
    override as its own step rather than folding it into the promotion list. Folding it in would
    make a manual decision indistinguishable from a campaign on the receipt, which is precisely
    what the audit requirement exists to prevent.

    An override **up** is refused -- and **up means above what this resolution already
    arrived at**, not above the list price. Bounding it against the list let a manager raise
    the price past a promotion the member had already earned: a 50.00 line discounted to 40.00
    could be "overridden" to 45.00, which is a 5.00 surcharge wearing a discount's name, and
    `needs_approval` scored it as a discount because the figure was still under the list.
    Charging more than the catalogue says is a different act with different consequences, and
    nothing in COM-02 asks for it.

    **The explanation is rebuilt, not appended to.** `resolve` has already written its
    `final_amount` step by the time this runs, so keeping the step list whole left the one
    artefact paragraph 10220 requires stating a final amount that is not the one in the row's
    own column -- on the single table in this module with no UPDATE grant. The prior
    `final_amount` step is dropped and re-emitted from the figures this function actually
    returns.
    """
    if override_amount_minor < 0:
        raise PricingError("an_override_is_not_negative")
    if override_amount_minor > resolution.final_amount_minor:
        raise PricingError("an_override_cannot_raise_the_resolved_price")
    if not reason.strip():
        raise PricingError("an_override_states_a_reason")
    discount = resolution.list_amount_minor - override_amount_minor
    kept = tuple(
        step for step in resolution.steps if step.code != "final_amount")
    steps = (
        *kept,
        Step("manual_override", reason.strip(), override_amount_minor),
        Step("final_amount", f"{resolution.list_amount_minor} less {discount}",
             override_amount_minor),
    )
    discount_bp = (
        0 if resolution.list_amount_minor == 0
        else money.round_half_up(
            discount * money.BASIS_POINTS, resolution.list_amount_minor)
    )
    return Resolution(
        variant_id=resolution.variant_id,
        price_book_id=resolution.price_book_id,
        price_id=resolution.price_id,
        currency=resolution.currency,
        list_amount_minor=resolution.list_amount_minor,
        discount_minor=discount,
        final_amount_minor=override_amount_minor,
        applied_promotions=resolution.applied_promotions,
        rejected_promotions=resolution.rejected_promotions,
        steps=steps,
        discount_bp=discount_bp,
        explanation=tuple(step.render() for step in steps),
    )


def needs_approval(resolution: Resolution, threshold_bp: int) -> bool:
    """Whether this resolution's discount reaches the threshold that requires an approval.

    `0` means never, which is the default and is why the comparison is `>=` on a positive
    threshold rather than on zero: a threshold of zero with `>=` would demand an approval for
    every undiscounted sale in the tenant.
    """
    if threshold_bp <= 0:
        return False
    return resolution.discount_bp >= threshold_bp
