"""MOD-017 COM-03: invoice arithmetic, the fiscal sequence and tax, as decisions with no I/O.

Four rules carry this module:

* **The arithmetic is integer minor units and `app.billing.money` owns it.** Imported, never
  reimplemented. MOD-015 chose half-away-from-zero rounding and largest-remainder allocation
  and wrote down why; MOD-016 shipped a second rounding rule once, on a float, and a reviewer
  found that it disagreed with the first on ordinary inputs.

* **Tax is computed per line and summed, never computed on the total.** The two differ by up to
  one minor unit per line, and the figure a tax authority reads is the sum of the lines -- so
  computing it on the total and then allocating back is the way to produce an invoice whose
  lines do not add up to its own total.

* **Payment state and fiscal state are separate machines.** Paragraph 1607. Neither transition
  implies the other, and `check_fiscal_transition` and `check_payment_transition` share no
  code deliberately: a helper that handled both would be the place somebody later made one
  imply the other.

* **`fiscal_complete` needs the authority's acknowledgement, not just a serial.** Paragraph
  1607 names the Jordan rule and it is the general shape: a server-allocated serial means the
  document is numbered, and numbering is not filing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.billing import money

#: The version of the rules here, stamped on nothing yet and kept for when a stored decision
#: needs to name which arithmetic produced it.
POLICY_VERSION = 1

#: COM-03-R05's payment states. `written_off` is terminal and deliberate: a debt nobody will
#: collect is a decision somebody made, not a status a timer reaches.
PAYMENT_STATUSES = (
    "unpaid", "part_paid", "paid", "overdue", "written_off", "credited",
)

#: The payment-state machine. `overdue` is reachable from the two unpaid states and goes back
#: to them when money arrives -- a member who pays late is not permanently overdue.
PAYMENT_EDGES: dict[str, tuple[str, ...]] = {
    "unpaid": ("part_paid", "paid", "overdue", "written_off", "credited"),
    "part_paid": ("part_paid", "paid", "overdue", "written_off", "credited"),
    "overdue": ("part_paid", "paid", "written_off", "credited"),
    # **A paid invoice comes back when the money does.** The first version admitted only
    # `credited` here, on the reasoning that applies to a write-off: a debt that could be
    # reopened would make the write-off a suggestion. That reasoning does not transfer. A
    # refund is a recorded money movement rather than a change of mind, and an invoice whose
    # payment went back is owed again -- a refund that is *meant* to leave no debt is a refund
    # plus a credit note, which is why `credited` stays on the list. Without these edges
    # `_apply_to_invoice` recomputed the right status, found no edge for it, and left the
    # invoice reading `paid` with the member's money back in their account.
    "paid": ("unpaid", "part_paid", "overdue", "written_off", "credited"),
    "written_off": (),
    "credited": (),
}

#: COM-03-R07's fiscal states. `not_required` is a real answer: a regime that does not
#: fiscalize is not a regime whose invoices are permanently pending.
FISCAL_STATUSES = (
    "pending", "submitted", "acknowledged", "fiscal_complete", "rejected", "not_required",
)

FISCAL_EDGES: dict[str, tuple[str, ...]] = {
    "pending": ("submitted", "not_required"),
    # A rejection goes back to submitted, because the ordinary response to a rejection is to
    # correct and resubmit.
    "submitted": ("acknowledged", "rejected"),
    "rejected": ("submitted",),
    "acknowledged": ("fiscal_complete",),
    "fiscal_complete": (),
    "not_required": (),
}


class InvoicingError(ValueError):
    """An invoicing input this module will not accept."""


@dataclass(frozen=True)
class LineInput:
    """What a caller asks to be charged for."""

    description: str
    quantity: int
    unit_net_minor: int
    tax_rate_bp: int
    variant_id: str | None = None
    price_resolution_id: str | None = None
    tax_category_id: str | None = None


@dataclass(frozen=True)
class Line:
    """One computed line, with its own arithmetic settled."""

    line_number: int
    description: str
    quantity: int
    unit_net_minor: int
    net_minor: int
    tax_rate_bp: int
    tax_minor: int
    gross_minor: int
    variant_id: str | None = None
    price_resolution_id: str | None = None
    tax_category_id: str | None = None


@dataclass(frozen=True)
class Totals:
    """An invoice's figures, and the per-jurisdiction tax behind them."""

    net_minor: int
    tax_minor: int
    gross_minor: int
    lines: tuple[Line, ...] = field(default_factory=tuple)
    #: Tax grouped by rate, which is the shape a return wants: one figure per rate per
    #: jurisdiction, not one per line.
    tax_by_rate: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)


def compute_totals(inputs: list[LineInput]) -> Totals:
    """Turn charge requests into lines and totals, with the tax computed per line.

    **Per line, then summed.** Computing tax on the net total and allocating it back across the
    lines gives a different answer by up to one minor unit per line, and the invoice would then
    be one whose own lines do not add up to the total printed on it -- which is the version a
    member notices and an auditor asks about.
    """
    if not inputs:
        raise InvoicingError("an_invoice_has_at_least_one_line")
    if len(inputs) > 500:
        raise InvoicingError("an_invoice_has_at_most_500_lines")
    lines: list[Line] = []
    for number, item in enumerate(inputs, start=1):
        if not item.description.strip():
            raise InvoicingError("an_invoice_line_describes_what_it_is_for")
        if item.quantity <= 0 or item.quantity > 1_000_000:
            raise InvoicingError("an_invoice_line_quantity_is_between_one_and_a_million")
        if item.unit_net_minor < 0:
            raise InvoicingError("an_invoice_line_is_not_negative")
        if item.unit_net_minor > 1_000_000_000_000:
            raise InvoicingError("an_invoice_line_exceeds_the_sane_bound")
        if not 0 <= item.tax_rate_bp <= money.BASIS_POINTS:
            raise InvoicingError("a_tax_rate_is_between_zero_and_one_hundred_percent")
        net = item.unit_net_minor * item.quantity
        if net > 1_000_000_000_000:
            raise InvoicingError("an_invoice_line_exceeds_the_sane_bound")
        tax = money.apply_rate_bp(net, item.tax_rate_bp)
        lines.append(Line(
            line_number=number, description=item.description.strip(),
            quantity=item.quantity, unit_net_minor=item.unit_net_minor, net_minor=net,
            tax_rate_bp=item.tax_rate_bp, tax_minor=tax, gross_minor=net + tax,
            variant_id=item.variant_id, price_resolution_id=item.price_resolution_id,
            tax_category_id=item.tax_category_id))
    net_total = sum(line.net_minor for line in lines)
    tax_total = sum(line.tax_minor for line in lines)
    if net_total + tax_total > 1_000_000_000_000:
        raise InvoicingError("an_invoice_exceeds_the_sane_bound")
    by_rate: dict[int, tuple[int, int]] = {}
    for line in lines:
        taxable, taxed = by_rate.get(line.tax_rate_bp, (0, 0))
        by_rate[line.tax_rate_bp] = (taxable + line.net_minor, taxed + line.tax_minor)
    return Totals(
        net_minor=net_total, tax_minor=tax_total, gross_minor=net_total + tax_total,
        lines=tuple(lines),
        tax_by_rate=tuple(
            (rate, taxable, taxed) for rate, (taxable, taxed) in sorted(by_rate.items())))


def document_number(series_code: str, serial: int) -> str:
    """The printed number, built from the series and the serial.

    One format, here, so every document in a series looks the same and a human can tell at a
    glance which series a number belongs to. Zero-padded to six digits, which is enough for any
    series this build would see and keeps numbers sorting lexically as they sort numerically --
    a property somebody will rely on in a spreadsheet whether or not it was promised.
    """
    if not series_code.strip():
        raise InvoicingError("a_fiscal_series_has_a_code")
    if serial < 1:
        raise InvoicingError("a_fiscal_serial_starts_at_one")
    if serial > 999_999_999:
        raise InvoicingError("a_fiscal_serial_exceeds_the_sane_bound")
    return f"{series_code.strip().upper()}-{serial:06d}"


def check_payment_transition(current: str, target: str) -> None:
    """Refuse a payment-state move the machine does not have."""
    if current not in PAYMENT_STATUSES:
        raise InvoicingError(f"{current!r} is not a payment status")
    if target not in PAYMENT_STATUSES:
        raise InvoicingError(f"{target!r} is not a payment status")
    if target not in PAYMENT_EDGES[current]:
        raise InvoicingError(f"an invoice does not move from {current} to {target}")


def check_fiscal_transition(current: str, target: str) -> None:
    """Refuse a fiscal-state move the machine does not have.

    Deliberately shares no code with the payment machine. A helper that handled both would be
    the place somebody later made one imply the other, which is the exact conflation paragraph
    1607 forbids.
    """
    if current not in FISCAL_STATUSES:
        raise InvoicingError(f"{current!r} is not a fiscal status")
    if target not in FISCAL_STATUSES:
        raise InvoicingError(f"{target!r} is not a fiscal status")
    if target not in FISCAL_EDGES[current]:
        raise InvoicingError(f"an invoice does not move from {current} to {target} fiscally")


def payment_status_for(
    *, gross_minor: int, paid_minor: int, credited_minor: int, due_on: date, at: date,
) -> str:
    """What an invoice's payment status should be, given what has arrived.

    **Derived from the money, not asserted by a caller.** The commonest way an invoice comes to
    read `paid` while money is outstanding is a caller passing the status it expected; this
    takes the figures and decides.

    A credit note reduces what is owed, which is why `credited_minor` subtracts: MOD-015 stores
    credits positive and always reads them as a reduction, and that convention is adopted here
    rather than re-chosen.
    """
    if gross_minor < 0 or paid_minor < 0 or credited_minor < 0:
        raise InvoicingError("an_invoice_figure_is_not_negative")
    owed = gross_minor - credited_minor
    if owed <= 0:
        return "credited"
    if paid_minor >= owed:
        return "paid"
    if paid_minor > 0:
        return "part_paid" if at <= due_on else "overdue"
    return "unpaid" if at <= due_on else "overdue"
