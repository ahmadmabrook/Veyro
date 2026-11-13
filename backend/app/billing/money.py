"""MOD-015 PLT-03: money arithmetic, in integers, with the conventions written down.

**Every amount is an integer count of minor units** -- cents, aurar, pence. Nothing here takes or
returns a float. That is not fussiness: `0.1 + 0.2 != 0.3` in binary floating point, and an
invoice that is one unit out is a defect whoever caused it. `Decimal` would be exact as well, but
minor units also remove the unit ambiguity at every boundary -- `1250` in a JSON body cannot be
misread as twelve and a half of anything -- and they match what payment providers expect.

Two conventions have to be chosen rather than derived, because the sources state neither. Both
are stated here so a reader can disagree with the choice rather than reverse-engineer it:

* **Rounding is half away from zero.** 2.5 units rounds to 3, -2.5 to -3. It is what invoice
  readers expect, it is symmetric so a credit and the charge it reverses round to the same
  magnitude, and it is computed in integers so there is no floating-point tie-breaking to argue
  about. Banker's rounding would be defensible for statistics and is wrong here, because a
  customer comparing two lines that differ only in sign would see different magnitudes.
* **Proration is actual days over actual days in the period.** A change effective on day 10 of a
  30-day period is charged 20/30 of the new price and credited 20/30 of the old, counting from
  the effective date inclusive to the period end exclusive. A 30/360 convention would be equally
  defensible and would produce different numbers in February; `prorate` is the one function to
  change if a baseline ever states one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

BASIS_POINTS = 10_000
"""A rate of 10000 bp is 100%. Rates are integers for the same reason amounts are."""


class MoneyError(ValueError):
    """Two amounts in different currencies met, or a rate was out of range."""


def round_half_up(numerator: int, denominator: int) -> int:
    """Divide, rounding halves away from zero. Integers only, so no tie-breaking surprises."""
    if denominator <= 0:
        raise MoneyError("denominator must be positive")
    quotient, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    return quotient if numerator >= 0 else -quotient


def apply_rate_bp(amount_minor: int, rate_bp: int) -> int:
    """Apply a basis-point rate: tax, a revenue share, a percentage discount."""
    if rate_bp < 0:
        raise MoneyError("rate must not be negative")
    return round_half_up(amount_minor * rate_bp, BASIS_POINTS)


def allocate(total_minor: int, weights: list[int]) -> list[int]:
    """Split a total by weights so that the parts sum to exactly the total.

    Proportional division loses or gains units to rounding -- three ways of 100 is 33, 33, 33 and
    one unit has vanished. The largest-remainder method hands the leftover units to the parts
    with the biggest fractional claim, so the sum is exact by construction. Used wherever one
    amount has to be spread across lines, such as a discount over several charges.
    """
    if any(w < 0 for w in weights):
        raise MoneyError("weights must not be negative")
    total_weight = sum(weights)
    if total_weight == 0:
        if total_minor != 0:
            raise MoneyError("cannot allocate a non-zero total across zero weight")
        return [0] * len(weights)

    sign = -1 if total_minor < 0 else 1
    magnitude = abs(total_minor)
    shares = [magnitude * w // total_weight for w in weights]
    remainders = [(magnitude * w) % total_weight for w in weights]
    leftover = magnitude - sum(shares)
    # Biggest remainder first; ties go to the earlier position so the result is deterministic.
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        shares[i] += 1
    return [sign * s for s in shares]


def prorate(amount_minor: int, period_start: date, period_end: date, effective_on: date) -> int:
    """The part of `amount_minor` that covers `effective_on` to `period_end`.

    Counting is inclusive of the effective date and exclusive of the period end, so a change on
    the first day of the period prorates to the whole amount and a change on the last day
    prorates to one day. An effective date outside the period clamps to the nearer end rather
    than producing a negative or an over-full share.
    """
    total_days = (period_end - period_start).days
    if total_days <= 0:
        raise MoneyError("period must end after it starts")
    remaining = (period_end - effective_on).days
    remaining = max(0, min(remaining, total_days))
    return round_half_up(amount_minor * remaining, total_days)


def plan_change_proration(
    old_price_minor: int,
    new_price_minor: int,
    *,
    period_start: date,
    period_end: date,
    effective_on: date,
) -> int:
    """What a mid-period plan change is worth: positive charges, negative credits.

    The unused remainder of the old plan is credited and the same remainder of the new plan is
    charged. An upgrade therefore produces a charge, a downgrade a credit, and a change effective
    exactly at the period end produces zero rather than a rounding artefact.
    """
    window = {"period_start": period_start, "period_end": period_end,
              "effective_on": effective_on}
    return prorate(new_price_minor, **window) - prorate(old_price_minor, **window)


@dataclass(frozen=True)
class Money:
    """An amount and the currency it is in, so the two cannot drift apart in a call chain."""

    minor: int
    currency: str

    def __post_init__(self) -> None:
        if not (len(self.currency) == 3 and self.currency.isascii()
                and self.currency.isupper()):
            raise MoneyError(f"{self.currency!r} is not an ISO 4217 code")

    def _same(self, other: Money) -> None:
        if self.currency != other.currency:
            raise MoneyError(f"cannot combine {self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.minor - other.minor, self.currency)

    def times(self, quantity: int) -> Money:
        return Money(self.minor * quantity, self.currency)

    def rate(self, rate_bp: int) -> Money:
        return Money(apply_rate_bp(self.minor, rate_bp), self.currency)


def invoice_totals(
    line_amounts_minor: list[int], *, tax_rate_bp: int | None = None
) -> tuple[int, int, int]:
    """Subtotal, tax and total for a set of line amounts.

    Tax is computed on the subtotal rather than per line and then summed. Per-line tax followed by
    a sum can differ from the headline figure by a unit or two once each line is rounded, and the
    number a customer checks is the one on the bottom of the page.
    """
    subtotal = sum(line_amounts_minor)
    # A subtotal that has gone negative -- a mid-period downgrade crediting more than the new
    # plan charges -- carries no tax. Taxing it would produce a negative tax figure, which is a
    # refund of tax and a matter for the credit note and the jurisdiction, not for this sum.
    tax = 0 if tax_rate_bp is None or subtotal <= 0 else apply_rate_bp(subtotal, tax_rate_bp)
    return subtotal, tax, subtotal + tax
