"""COM-04-R06's financial periods and the lock that makes a closed one mean something.

**A period is closed so that a figure already reported cannot change.** Once finance has told
an authority what a month was, a posting dated into that month makes the statement and the
filing disagree with no trace of which is current. So a closed period refuses postings, and the
correction for something discovered afterwards is a posting in the *open* period that references
the original -- which is the same answer this build gives everywhere an insert-only table is
asked to change its mind.

**The lock is enforced by a trigger, not by this function alone.** A period's status is a fact
about another row, so a CHECK cannot see it; and the service's choice of SQL is not the writer
the control exists for. This module gives the readable refusal and the state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.ledger.accounts import LedgerError

#: A period's states. `closing` exists because closing is work -- recognition to post,
#: settlements to match, variances to explain -- and a period mid-close must stop accepting
#: ordinary postings while still admitting the entries the close itself produces.
STATUSES: tuple[str, ...] = ("open", "closing", "closed", "reopened")

#: Which moves are allowed. **A closed period never reopens on its own authority**: that is
#: `reopened`, a distinct state with its own permission and its own written reason, so a
#: statement can say "this month was reopened on the fourteenth" rather than silently differ
#: from the one filed.
EDGES: dict[str, tuple[str, ...]] = {
    "open": ("closing",),
    "closing": ("closed", "open"),
    "closed": ("reopened",),
    "reopened": ("closing",),
}

#: What may be posted into a period in each state. The `closing` case is the point of the
#: state: the close's own work continues while ordinary trade stops.
POSTABLE: dict[str, tuple[str, ...]] = {
    "open": ("trade", "correction", "recognition", "settlement", "close"),
    "closing": ("correction", "recognition", "settlement", "close"),
    "closed": (),
    "reopened": ("correction", "close"),
}

#: The reasons a journal can be posted for. `trade` is the ordinary sale or payment;
#: `correction` is a compensating entry; the rest are the close's own machinery.
PURPOSES: tuple[str, ...] = ("trade", "correction", "recognition", "settlement", "close")

#: **Which purpose a journal has, derived from where it came from.** `purpose` decides whether
#: a period under close admits the journal, so a caller able to send it chose that -- a
#: reviewer posted the identical journal as `settlement` after it was refused as `trade`, which
#: is COM-04-R06's lock defeated by one word. Anything not named here is `trade`; `close` is
#: the one purpose that is not derivable, because it is the accountant's own accrual, and the
#: route charges `finance.period.close` for it rather than taking it on trust.
PURPOSE_BY_SOURCE: dict[str, str] = {
    "correction": "correction",
    "recognition": "recognition",
    "settlement": "settlement",
}


@dataclass(frozen=True)
class Period:
    """One financial period, as the decisions need it."""

    period_key: str
    starts_on: date
    ends_on: date
    status: str


def check_transition(current: str, target: str) -> None:
    if current not in STATUSES:
        raise LedgerError(f"{current!r} is not a period status")
    if target not in STATUSES:
        raise LedgerError(f"{target!r} is not a period status")
    if target not in EDGES[current]:
        raise LedgerError(f"a financial period does not move from {current} to {target}")


def check_postable(period: Period, purpose: str) -> None:
    """Refuse a posting the period's state does not admit."""
    if purpose not in PURPOSES:
        raise LedgerError(f"{purpose!r} is not a reason to post a journal")
    if period.status not in POSTABLE:
        raise LedgerError(f"{period.status!r} is not a period status")
    if purpose not in POSTABLE[period.status]:
        raise LedgerError(
            f"the period {period.period_key} is {period.status} and admits no "
            f"{purpose} postings")


def period_key_for(moment: date) -> str:
    """The monthly key a date belongs to. `2026-11`.

    **Monthly, because paragraph 1663 says "monthly partitions where volume warrants"** and a
    period shorter than the shortest filing cycle is a close nobody asked for. The key is
    derived rather than chosen, so two callers cannot disagree about which period a date is in.
    """
    return f"{moment.year:04d}-{moment.month:02d}"


def month_bounds(period_key: str) -> tuple[date, date]:
    """The first and last day of a monthly period key."""
    try:
        year_text, month_text = period_key.split("-")
        year, month = int(year_text), int(month_text)
    except ValueError:
        raise LedgerError(f"{period_key!r} is not a monthly period key") from None
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        raise LedgerError(f"{period_key!r} is not a monthly period key")
    starts = date(year, month, 1)
    if month == 12:
        ends = date(year, 12, 31)
    else:
        ends = date.fromordinal(date(year, month + 1, 1).toordinal() - 1)
    return starts, ends
