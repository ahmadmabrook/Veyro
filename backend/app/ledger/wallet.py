"""COM-04-R02's member wallet: four kinds of value, each with its own rules.

**Promotional, refundable and cash-equivalent balances remain distinct** -- paragraph 1686, a
Critical Control, and the whole reason this is four balances rather than one number. A member
holding 50.00 of cash they paid in and 10.00 the tenant gave away holds two different things:
the first is money the tenant owes them and must refund on request, the second is a marketing
expense already incurred that no refund can reach. A single balance makes the two
indistinguishable the moment either is spent, and the tenant then either refuses a refund it
owes or pays out money it never took.

**A balance is the sum of the entries and is stored nowhere.** COM-04-R07: "statements and
balances reconstructed from entries rather than mutable totals." A cached total is a second
authority that can disagree with the first, and the disagreement surfaces as a member who
cannot spend value the statement says they have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.ledger.accounts import LedgerError

#: The four kinds COM-04-R02 names, in the order a debit spends them.
#:
#: **The order is a decision and it is the member's interest, not the tenant's.** Promotional
#: value first because it expires soonest and is worth nothing to the member if it lapses;
#: then referral and refund credit, which are given value with no cash behind them; cash last,
#: because cash is the only kind a member can ask for back. Spending cash first would let a
#: tenant quietly convert a refundable balance into an unrefundable one every time the member
#: bought anything.
SPEND_ORDER: tuple[str, ...] = ("promotional", "referral", "refund_credit", "cash")

#: Which kinds a refund may reach. Only the money the member actually paid in.
REFUNDABLE: frozenset[str] = frozenset({"cash", "refund_credit"})

#: The ledger account each wallet kind is a liability in. `refund_credit` and `referral` sit in
#: the same two accounts as cash and promotional value respectively, because that is what they
#: are in accounting terms: one is money owed, the other is value given away.
LIABILITY_ACCOUNT: dict[str, str] = {
    "cash": "wallet_cash",
    "refund_credit": "wallet_cash",
    "promotional": "wallet_promotional",
    "referral": "wallet_promotional",
}


@dataclass(frozen=True)
class Entry:
    """One wallet movement, for the balance arithmetic."""

    value_kind: str
    amount_minor: int
    expires_on: date | None = None


@dataclass(frozen=True)
class Spend:
    """What a debit takes from one kind of value."""

    value_kind: str
    amount_minor: int


def check_kind(value_kind: str) -> None:
    if value_kind not in SPEND_ORDER:
        raise LedgerError(f"{value_kind!r} is not a kind of wallet value")


def balances(entries: list[Entry], *, at: date) -> dict[str, int]:
    """The spendable balance per kind, as of a date, with lapsed value excluded.

    **Expiry is evaluated rather than swept.** Nothing in this build runs on a schedule, so a
    balance that counted lapsed value until a worker removed it would be a balance a member
    could spend after it expired. The entry stays -- it is the record of what was given -- and
    the arithmetic stops counting it, which is also what makes "what did I have in March"
    answerable.

    **What lapses is the value that was not spent, and that is the whole of this function.**
    The first version dropped an expired credit and kept every debit, and a debit carries no
    expiry -- so a member who *used* a promo code lost, on the day the promo would have
    expired, an amount of their own paid-in cash equal to the promo they had already spent:
    the kind went negative and `spendable` sums across kinds. Their statement said 40.00 while
    they held 50.00, and the till refused the 50.00 purchase. It compounded with every expired
    credit they had used.

    So per kind: the balance is the sum of everything, less whatever expired *beyond* what has
    already been drawn against that kind. Spending is ordered by `SPEND_ORDER` and promotional
    value goes first precisely because it expires, so charging the spend against the expiring
    credits first is also the order the member benefits from. The result is never negative,
    because the lapse can never exceed what is left.
    """
    total = {kind: 0 for kind in SPEND_ORDER}
    expiring = {kind: 0 for kind in SPEND_ORDER}
    spent = {kind: 0 for kind in SPEND_ORDER}
    for entry in entries:
        check_kind(entry.value_kind)
        total[entry.value_kind] += entry.amount_minor
        if entry.amount_minor > 0:
            if entry.expires_on is not None and entry.expires_on < at:
                expiring[entry.value_kind] += entry.amount_minor
        else:
            spent[entry.value_kind] += -entry.amount_minor
    return {
        kind: total[kind] - max(0, expiring[kind] - spent[kind])
        for kind in SPEND_ORDER
    }


def spendable(entries: list[Entry], *, at: date) -> int:
    """What the member can spend in total, now."""
    return sum(balances(entries, at=at).values())


def refundable(entries: list[Entry], *, at: date) -> int:
    """What the member could ask for in money. Promotional value is not in here."""
    held = balances(entries, at=at)
    return sum(amount for kind, amount in held.items() if kind in REFUNDABLE)


def plan_debit(
    entries: list[Entry], *, amount_minor: int, at: date,
) -> tuple[Spend, ...]:
    """How a debit of `amount_minor` is taken, kind by kind, in `SPEND_ORDER`.

    Refuses rather than partially spending: a wallet debit that took what it could and left the
    rest would be a sale half-paid, and the caller cannot tell from a success whether the member
    was charged. The refusal names what is there.
    """
    if amount_minor <= 0:
        raise LedgerError("a wallet debit is for a positive amount")
    held = balances(entries, at=at)
    total = sum(held.values())
    if total < amount_minor:
        raise LedgerError(
            f"this wallet holds {total} and {amount_minor} was asked for")
    plan: list[Spend] = []
    left = amount_minor
    for kind in SPEND_ORDER:
        if left == 0:
            break
        take = min(held[kind], left)
        if take > 0:
            plan.append(Spend(kind, take))
            left -= take
    assert left == 0
    return tuple(plan)


def check_credit(
    *, value_kind: str, amount_minor: int, expires_on: date | None, at: date,
) -> None:
    """Refuse a credit this module will not accept.

    **Cash value does not expire**, and that is the one asymmetry worth stating: it is money the
    member paid in, so an expiry on it would be the tenant keeping money it owes. Promotional
    value is the tenant's to time-limit, and a promotional credit with no expiry is accepted --
    an unbounded giveaway is a commercial decision rather than a defect.
    """
    check_kind(value_kind)
    if amount_minor <= 0:
        raise LedgerError("a wallet credit is for a positive amount")
    if amount_minor > 10**12:
        raise LedgerError("a wallet credit past the sane bound")
    if value_kind == "cash" and expires_on is not None:
        raise LedgerError("cash wallet value does not expire: it is money the member paid in")
    if expires_on is not None and expires_on < at:
        raise LedgerError("a credit cannot expire before it is given")


# **There is no `check_refund`, and `refundable` is a read rather than a guard.** A refund
# guard existed here with nothing calling it, because nothing in this build refunds a wallet --
# paying money out is the owner-reserved half of COM-04-R02 and needs the provider MOD-017 does
# not have either. `refundable` stays, because telling a member how much of their balance they
# could get back is worth saying and is what makes the four kinds visible to them; a function
# reading as a control that nothing calls is what MOD-008's `Decision.mask` cost five modules.


def expiring_before(
    entries: list[Entry], *, horizon: date, at: date,
) -> int:
    """How much live value lapses before `horizon`. For telling a member, not for sweeping.

    **Capped per kind at what is actually there.** The first version compared each credit
    against the kind's whole balance independently, so two 1000 credits expiring on the same
    day with 1500 already spent reported 1000 about to lapse against a live balance of 500.
    A warning that overstates what the member is about to lose is a warning they learn to
    ignore.
    """
    live = balances(entries, at=at)
    out = 0
    for kind in SPEND_ORDER:
        lapsing = sum(
            entry.amount_minor for entry in entries
            if entry.value_kind == kind and entry.amount_minor > 0
            and entry.expires_on is not None and at <= entry.expires_on < horizon)
        out += min(lapsing, max(live[kind], 0))
    return out


def statement_lines(
    entries: list[tuple[datetime, Entry, str]], *, at: date,
) -> list[dict[str, object]]:
    """A running statement, built from the entries in order.

    COM-04-R07 asks for statements reconstructed from entries. The running balance is computed
    here rather than stored, so a statement and a balance cannot disagree: they are the same
    sum read to different depths.
    """
    running = 0
    lines: list[dict[str, object]] = []
    for moment, entry, reason in sorted(entries, key=lambda row: row[0]):
        check_kind(entry.value_kind)
        running += entry.amount_minor
        lines.append({
            "at": moment.isoformat(),
            "value_kind": entry.value_kind,
            "amount_minor": entry.amount_minor,
            "balance_after": running,
            "expires_on": entry.expires_on.isoformat() if entry.expires_on else None,
            "lapsed": bool(entry.expires_on and entry.expires_on < at),
            "reason": reason,
        })
    return lines
