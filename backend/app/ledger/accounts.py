"""COM-04's chart of accounts: the account kinds this software posts to, and what they mean.

**The kinds are in code and the accounts are rows.** This is the same division MOD-008 makes
for permissions, MOD-010 for event types and MOD-011 for metrics, and the reason is the same: a
kind is a fact about what the software does, so two tenants disagreeing about whether
`unearned_revenue` is a liability would be a disagreement only the code could settle. The
*accounts* are per tenant and per location -- one cash account per till is the ordinary
arrangement -- so those are rows.

**Normal balance is the whole of double-entry.** An asset and an expense increase with a debit;
a liability, equity and revenue increase with a credit. Everything else in this module is
arithmetic over that one table, and getting it wrong once means every statement built from
these entries is wrong in a way no later correction can find. Paragraph 115 names the accounts
this build needs: "cash/receivable/provider clearing, tax, wallet/service-credit liabilities,
unearned revenue, earned revenue, contra revenue, COGS and FX gain/loss."

**Signs, not sides.** A posting carries a signed `amount_minor` and the side is derived: a
positive amount is a debit and a negative one is a credit. One column cannot disagree with
itself, and `sum(amount_minor) = 0` is then exactly "the journal balances" -- which is the
constraint the database enforces per journal rather than a property the service promises.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What a positive posting does to each class of account. `debit` means a positive amount
#: increases the account; `credit` means a positive amount decreases it. The pair is what makes
#: a balance readable without knowing which side it was posted from.
DEBIT = "debit"
CREDIT = "credit"

#: The account classes, with the side that increases them. Five classes, because that is what
#: double-entry has; a sixth would be a modelling error wearing a name.
CLASSES: dict[str, str] = {
    "asset": DEBIT,
    "liability": CREDIT,
    "equity": CREDIT,
    "revenue": CREDIT,
    "expense": DEBIT,
}


@dataclass(frozen=True)
class AccountKind:
    """One account kind: its class, whether a tenant may have more than one, and why."""

    key: str
    account_class: str
    description: str
    #: Whether this kind is scoped to a location. A till is; a tax liability is not.
    per_location: bool = False


#: The chart paragraph 115 names. Each entry says what it is *for*, because an account whose
#: purpose is not written down is one somebody posts the wrong thing to.
KINDS: tuple[AccountKind, ...] = (
    AccountKind("cash", "asset", "money in a till or a safe", per_location=True),
    AccountKind("bank", "asset", "money in a bank account"),
    AccountKind("receivable", "asset", "money a member owes on an issued invoice"),
    AccountKind(
        "provider_clearing", "asset",
        "money a payment provider has taken and not yet settled to the bank"),
    AccountKind(
        "tax_payable", "liability",
        "tax collected on somebody else's behalf, owed to an authority"),
    AccountKind(
        "wallet_cash", "liability",
        "refundable wallet value a member has paid for and not yet spent"),
    AccountKind(
        "wallet_promotional", "liability",
        "wallet value the tenant gave away: spendable, never refundable"),
    AccountKind(
        "unearned_revenue", "liability",
        "money taken for service not yet delivered -- a prepaid term or a class pack"),
    AccountKind("revenue", "revenue", "service delivered and earned"),
    AccountKind(
        "contra_revenue", "revenue",
        "revenue given back: a discount, a credit note or a goodwill reduction"),
    AccountKind("cogs", "expense", "the cost of goods sold"),
    AccountKind(
        "provider_fee", "expense", "what a payment provider charged for taking the money"),
    AccountKind("fx_gain_loss", "revenue", "the difference a rate moved between two postings"),
    AccountKind(
        "suspense", "asset",
        "money whose home is not yet known -- an unmatched settlement line, pending a human"),
)

KIND_BY_KEY: dict[str, AccountKind] = {k.key: k for k in KINDS}


class LedgerError(ValueError):
    """A ledger input this module will not accept."""


def _check_chart() -> None:
    """Run at import. A kind whose class is not one of the five is a modelling error."""
    for kind in KINDS:
        if kind.account_class not in CLASSES:
            raise LedgerError(
                f"{kind.key!r} names account class {kind.account_class!r}, which is not one "
                f"of {sorted(CLASSES)}")
    if len(KIND_BY_KEY) != len(KINDS):
        raise LedgerError("two account kinds share a key")


_check_chart()


def normal_side(account_kind: str) -> str:
    """Which side increases this kind of account. `debit` or `credit`."""
    kind = KIND_BY_KEY.get(account_kind)
    if kind is None:
        raise LedgerError(f"{account_kind!r} is not an account kind this build posts to")
    return CLASSES[kind.account_class]


def side_of(amount_minor: int) -> str:
    """The side a signed posting amount represents. Positive is a debit."""
    if amount_minor == 0:
        raise LedgerError("a posting of nothing is not a posting")
    return DEBIT if amount_minor > 0 else CREDIT


def signed_increase(account_kind: str, amount_minor: int) -> int:
    """What `amount_minor` does to the account's own balance, in its own direction.

    A liability credited by 500 has *increased* by 500, and a reader asking "how much wallet
    value does this member hold" wants 500 rather than -500. The ledger stores the signed
    posting; this is the one place that turns it into the account's own language.
    """
    if normal_side(account_kind) == DEBIT:
        return amount_minor
    return -amount_minor


def check_balanced(amounts: list[int]) -> None:
    """Refuse a journal whose postings do not sum to zero.

    **Checked here and by a deferred constraint trigger on the table.** The decision function
    gives a readable refusal before any row is written; the trigger makes it true of rows
    written by anything else, which is the half that still holds when a later service forgets.
    A journal with one posting is also refused: there is no such thing as half a transfer.
    """
    if len(amounts) < 2:
        raise LedgerError("a journal has at least two postings")
    if any(a == 0 for a in amounts):
        raise LedgerError("a posting of nothing is not a posting")
    total = sum(amounts)
    if total != 0:
        raise LedgerError(
            f"this journal's postings sum to {total} rather than zero; "
            f"debits are {sum(a for a in amounts if a > 0)} and credits are "
            f"{-sum(a for a in amounts if a < 0)}")


def control_total(amounts: list[int]) -> int:
    """The sum of the debits, which is what a control total means for a balanced journal.

    Stored on the journal so a reconciliation can compare a figure against the postings
    without re-summing them, and so a journal whose postings were tampered with disagrees with
    its own header. Both halves are insert-only, which is what makes the disagreement evidence
    rather than a stale cache.
    """
    return sum(a for a in amounts if a > 0)
