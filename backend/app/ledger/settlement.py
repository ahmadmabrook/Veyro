"""COM-04-R04's provider settlement import and matching, and COM-04-R05's cash reconciliation.

**A settlement is what the provider says it paid out, and it rarely equals what this build
thinks it took.** The difference is fees, timing, chargebacks and the provider's own
corrections, and the whole point of importing one is to find out which. So a settlement line is
matched to a payment, a refund or a fee, and anything that does not match opens a case for a
human rather than being absorbed.

**Nothing is absorbed silently and nothing is written off automatically.** An unmatched line
opens a reconciliation case, which is where a question nobody has answered lives, and that is
better than a balance quietly folded into fees. Paragraph 1699's "reconciliation mismatch = 0
unresolved past SLA" is a target somebody has to work, not an invariant the code can assert.

**A fee and a payout are the two kinds that post rather than asking.** They have no
counterpart in this build by design -- the fee is the provider's charge and the payout is the
provider paying -- and nothing else relieves `provider_clearing`, which every card payment
debits. The first version of this module said unmatched lines posted to `suspense` and
`import_settlement` posted nothing at all; a reviewer imported a fee and a payout and watched
four balances stay at zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.ledger.accounts import LedgerError

#: What a settlement line claims to be. The provider's own vocabulary varies; these are the
#: kinds this build knows how to post, and an import maps onto them at the boundary.
LINE_KINDS: tuple[str, ...] = (
    "payment", "refund", "fee", "chargeback", "chargeback_reversal", "adjustment", "payout",
)

#: Which kinds are expected to match something this build already recorded. A `fee` and a
#: `payout` are the provider's own movements and match nothing here, which is why an unmatched
#: one is not a mismatch.
MATCHABLE: frozenset[str] = frozenset(
    {"payment", "refund", "chargeback", "chargeback_reversal"})

#: How a matched line is classified once compared. These are the values a reconciliation case
#: records, and a reader should be able to tell from the word alone whether somebody has to act.
MATCHED = "matched"
AMOUNT_MISMATCH = "amount_mismatch"
UNMATCHED = "unmatched"
DUPLICATE = "duplicate"
NOT_EXPECTED = "not_expected"


@dataclass(frozen=True)
class Line:
    """One line of a provider's settlement file, as the matcher needs it."""

    line_kind: str
    provider_ref: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class Recorded:
    """What this build has against that provider reference."""

    reference: str
    amount_minor: int
    currency: str
    #: How many rows carry this reference. More than one is the provider having reused it,
    #: which MOD-017 refuses on the way in -- so this is defence for an imported file.
    count: int = 1


@dataclass(frozen=True)
class Verdict:
    """What matching one line concluded, and whether a human has to look."""

    outcome: str
    reason: str

    @property
    def needs_a_case(self) -> bool:
        return self.outcome != MATCHED


def check_line(line: Line) -> None:
    if line.line_kind not in LINE_KINDS:
        raise LedgerError(f"{line.line_kind!r} is not a settlement line kind")
    if line.amount_minor == 0:
        raise LedgerError("a settlement line of nothing is not a line")
    if not line.provider_ref.strip():
        raise LedgerError("a settlement line cites the provider's own reference")
    # **The sign per kind is this module's convention, stated rather than assumed.** A fee is
    # a deduction from what the provider owes and a payout is an amount it paid out, so the
    # two posting kinds arrive with opposite signs -- and the posting takes the magnitude,
    # which would silently put a clawback (a negative payout) in the wrong direction by twice
    # its value. A provider whose file disagrees is a mapping problem for whatever reads the
    # file, and a refusal here is where that gets noticed.
    if line.line_kind == "fee" and line.amount_minor > 0:
        raise LedgerError(
            "a fee is a deduction from what the provider owes, so it is negative; a positive "
            "fee line is a credit nobody has named")
    if line.line_kind == "payout" and line.amount_minor < 0:
        raise LedgerError(
            "a payout is money the provider paid out, so it is positive; a negative payout "
            "is a clawback and this build has no posting for one")
    if len(line.currency) != 3 or not line.currency.isupper():
        raise LedgerError("a settlement line's currency is a three-letter code")


def match(line: Line, recorded: Recorded | None) -> Verdict:
    """Compare one settlement line against what this build recorded.

    **The currency is compared before the amount**, because two minor-unit counts that are
    equal in different currencies are the comparison MOD-015's money discipline forbids and
    MOD-016 shipped once. A line in another currency is not a small discrepancy; it is a line
    about something else.
    """
    check_line(line)
    if line.line_kind not in MATCHABLE:
        return Verdict(
            NOT_EXPECTED,
            f"a {line.line_kind} is the provider's own movement and matches nothing here")
    if recorded is None:
        return Verdict(
            UNMATCHED,
            f"nothing here carries the provider reference {line.provider_ref}")
    if recorded.count > 1:
        return Verdict(
            DUPLICATE,
            f"{recorded.count} rows carry the provider reference {line.provider_ref}")
    if recorded.currency != line.currency:
        return Verdict(
            AMOUNT_MISMATCH,
            f"the provider settled {line.currency} and this build recorded "
            f"{recorded.currency}")
    # **A refund leaves and a payment arrives, so the signs are opposite.** The provider's file
    # states both as positive magnitudes in its own direction; what is compared is the
    # magnitude, and the direction is the line kind.
    if abs(line.amount_minor) != abs(recorded.amount_minor):
        return Verdict(
            AMOUNT_MISMATCH,
            f"the provider settled {abs(line.amount_minor)} and this build recorded "
            f"{abs(recorded.amount_minor)}")
    return Verdict(MATCHED, "the provider and this build agree")


def control_total(lines: list[Line]) -> dict[str, int]:
    """The net movement per currency a settlement file claims, for comparing against a payout.

    Returned per currency and never summed across them, for the reason above.
    """
    out: dict[str, int] = {}
    for line in lines:
        check_line(line)
        out[line.currency] = out.get(line.currency, 0) + line.amount_minor
    return out


def check_control_total(
    *, claimed_minor: int, computed_minor: int, currency: str,
) -> Verdict:
    """Whether the file's own stated total agrees with its lines. COM-04-R04.

    A file whose header disagrees with its body is a file that was truncated or edited in
    transit, and importing it would post half a day's takings as though it were all of them.
    """
    if claimed_minor == computed_minor:
        return Verdict(MATCHED, f"the file's {currency} total agrees with its lines")
    return Verdict(
        AMOUNT_MISMATCH,
        f"the file claims {claimed_minor} {currency} and its lines come to "
        f"{computed_minor}")


@dataclass(frozen=True)
class Count:
    """A till count at the close of a session. COM-04-R05."""

    expected_minor: int
    counted_minor: int
    currency: str


def variance(count: Count) -> int:
    """What the drawer was over or under. Positive is over: more money than the system expected.

    **The sign convention is stated because it decides what a report means.** Over is positive,
    so a column of variances sums to the net discrepancy rather than to nothing, and "we are
    down 30.00 this week" is a negative number rather than an argument about direction.
    """
    return count.counted_minor - count.expected_minor


#: How far a till may be out before somebody has to explain it. Not a policy this build can
#: state -- a tenant's tolerance is a commercial decision and the sources name none -- so the
#: threshold is a tenant setting and this is the floor: any variance at all is recorded, and a
#: non-zero one needs a written reason before the session closes.
def check_close(count: Count, *, reason: str | None) -> None:
    """Refuse a close that leaves a discrepancy unexplained.

    **An unexplained variance is the finding, not the money.** A till 2.00 down is noise; a
    till 2.00 down every evening with nothing written is a pattern, and the only way the
    pattern is visible later is if each close said something at the time.
    """
    if count.counted_minor < 0:
        raise LedgerError("a till cannot hold a negative amount")
    if variance(count) != 0 and not (reason or "").strip():
        raise LedgerError(
            f"this till is out by {variance(count)} and a close states why")
    # A clerk explaining a session that balanced is harmless and the note is worth keeping,
    # so there is deliberately no branch for it.


def deposit_matches(
    *, declared_minor: int, sessions_minor: int,
) -> Verdict:
    """Whether a bank deposit agrees with the till sessions it claims to bank. COM-04-R05."""
    if declared_minor == sessions_minor:
        return Verdict(MATCHED, "the deposit agrees with the sessions it banks")
    return Verdict(
        AMOUNT_MISMATCH,
        f"the deposit is {declared_minor} and the sessions it banks come to "
        f"{sessions_minor}")


def ageing(
    opened_on: date, *, at: date,
) -> int:
    """How many days a reconciliation case has been open. For the SLA paragraph 1699 names."""
    return max((at - opened_on).days, 0)
