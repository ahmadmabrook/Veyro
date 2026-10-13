"""Financial-invariant test harness placeholder — GOV-01-R02, SCN-MOD001-133.

A placeholder double-entry-invariant fixture over synthetic ledger rows,
asserting total debits equal total credits. This proves the
financial-invariant test harness itself is live; it is not real
payment/ledger business logic, which belongs to whichever module
eventually claims `backend/app/modules/ledger/` (see that domain's own
scaffold-live placeholder, SCN-MOD001-132).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.contract._execution_suppression_guard import assert_execution_not_suppressed

_SELF_CHECK_NAMES = frozenset(
    {
        "test_all_match_assertions_are_anchored",
        "test_match_assertions_use_only_the_shared_constants",
        "test_error_codes_are_mutually_disjoint",
        "test_critical_negative_tests_are_not_suppressed",
    }
)
_REQUIRED_NEGATIVE_CASE_NAMES = frozenset(
    {
        "test_unbalanced_synthetic_entry_fails_closed",
        "test_unmatched_credit_fails_closed",
        "test_precision_loss_fails_closed",
        "test_precision_boundary_within_context_still_compares_exactly",
    }
)

# R15-1/R15-2/R15-4: this call is ordinary module-level Python, executed
# once, unconditionally, when pytest imports this file for collection —
# before any per-test skip/xfail/redefinition/rebind or module-level
# `pytestmark` has a chance to prevent a *test* from running. Suppressing
# any one of the eight watched names (the four self-checks, including the
# thin pytest-visible wrapper below, plus the four negative-case tests)
# fails collection for the whole file. See `_execution_suppression_guard`'s
# own module docstring and BUG-050's round-15 remediation section for why
# this mechanism — not a fifth per-shape patch, not the full
# `pytest_sessionfinish`-based execution witness round 15 §12 named — was
# chosen.
assert_execution_not_suppressed(Path(__file__), _SELF_CHECK_NAMES | _REQUIRED_NEGATIVE_CASE_NAMES)


class Side(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass(frozen=True)
class SyntheticLedgerLeg:
    """One leg of a double-entry posting: a single account, side, and a
    strictly positive amount. A real posting pairs a debit leg with a
    credit leg of the same amount on a different account; this scaffold
    only asserts the aggregate invariant, not pairing."""

    entry_id: UUID
    account: str
    side: Side
    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.side, Side):
            raise TypeError(f"leg side must be a Side member, got {self.side!r}")
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"leg amount must be a Decimal, got {self.amount!r}")
        if not self.amount.is_finite():
            raise ValueError(f"leg amount must be finite, got {self.amount!r}")
        if self.amount <= Decimal(0):
            raise ValueError(f"leg amount must be strictly positive, got {self.amount}")


class FinancialInvariantViolation(AssertionError):
    """Raised with the specific invariant that failed, never a bare assert."""


# OBS-4 (rounds 6/7): the two routes' `match=` literals are centralized here
# rather than inlined at each `pytest.raises` call site. This is the
# structural fix, not a convenience: every call site shares one constant per
# route, so there is exactly one place to un-anchor by accident instead of
# four, and `test_all_match_assertions_are_anchored` below pins both.
_COMPARISON_MATCH = r"^DEBITS_NE_CREDITS"
_PRECISION_MATCH = r"^DEBITS_CREDITS_UNEVALUABLE_PRECISION"


def assert_debits_equal_credits(legs: list[SyntheticLedgerLeg]) -> None:
    """The one invariant this placeholder harness checks: total debit-side
    amounts must equal total credit-side amounts across the synthetic leg
    set.

    Summation traps `Inexact` (NR3-1): the default decimal context rounds
    to 28 significant digits, which can silently absorb a small leg into a
    much larger one and report a false-clean balance. Trapping makes that
    rounding a named failure instead of a hidden one.

    The trap applies independently to *each* side's sum (not just one),
    so an unevaluable-precision leg on either the debit or the credit side
    is caught (NR4-1). That condition is raised under its own code,
    `DEBITS_CREDITS_UNEVALUABLE_PRECISION` — a set that cannot be summed
    at this precision has not been shown to be out of balance, only to be
    unevaluable (NR4-3). This message intentionally does NOT name the
    comparison code `DEBITS_NE_CREDITS` anywhere in its text (NR5-1): an
    earlier version did, as an explanatory aside, and `pytest.raises`'
    `match=` performs an unanchored `re.search` over the whole message, so
    that aside made every `match="DEBITS_NE_CREDITS"` assertion accept
    this message too — the two *codes* were distinct substrings, but the
    two *messages* were not disjoint under that search. The contrast
    between the two codes belongs only in this docstring, never echoed
    into either raised string.
    """
    with localcontext() as ctx:
        ctx.traps[Inexact] = True
        try:
            total_debits = sum(
                (leg.amount for leg in legs if leg.side is Side.DEBIT), start=Decimal(0)
            )
            total_credits = sum(
                (leg.amount for leg in legs if leg.side is Side.CREDIT), start=Decimal(0)
            )
        except Inexact as exc:
            raise FinancialInvariantViolation(
                "DEBITS_CREDITS_UNEVALUABLE_PRECISION: leg amounts could not be summed without"
                " rounding at the decimal context's 28-significant-digit precision, so this"
                " invariant could not be evaluated"
            ) from exc
    if total_debits != total_credits:
        raise FinancialInvariantViolation(
            f"DEBITS_NE_CREDITS: total debits {total_debits} != total credits {total_credits}"
            f" across {len(legs)} leg(s)"
        )


def _posting(debit_account: str, credit_account: str, amount: Decimal) -> list[SyntheticLedgerLeg]:
    """A balanced double-entry posting: one debit leg, one credit leg, equal amount."""
    return [
        SyntheticLedgerLeg(uuid4(), debit_account, Side.DEBIT, amount),
        SyntheticLedgerLeg(uuid4(), credit_account, Side.CREDIT, amount),
    ]


def _balanced_synthetic_set() -> list[SyntheticLedgerLeg]:
    return [
        *_posting("synthetic:cash", "synthetic:revenue", Decimal("100.00")),
        *_posting("synthetic:deferred", "synthetic:cash", Decimal("25.50")),
    ]


def test_balanced_synthetic_entries_pass() -> None:
    balanced = _balanced_synthetic_set()
    assert balanced, "fixture must be non-empty; an empty set passes vacuously (not a proof)"
    assert_debits_equal_credits(balanced)


def test_unbalanced_synthetic_entry_fails_closed() -> None:
    """Negative case (SCN-MOD001-133): a debit with no matching credit must
    fail the harness, citing the specific invariant violated — not a
    rubber-stamp pass."""
    unmatched_debit = SyntheticLedgerLeg(uuid4(), "synthetic:cash", Side.DEBIT, Decimal("10.00"))
    unbalanced = [*_balanced_synthetic_set(), unmatched_debit]

    with pytest.raises(FinancialInvariantViolation, match=_COMPARISON_MATCH):
        assert_debits_equal_credits(unbalanced)


def test_unmatched_credit_fails_closed() -> None:
    """Regression for reviewer mutant M4: a one-directional check
    (debits > credits only) would miss a lone unmatched credit."""
    unmatched_credit = SyntheticLedgerLeg(
        uuid4(), "synthetic:revenue", Side.CREDIT, Decimal("5.00")
    )
    unbalanced = [*_balanced_synthetic_set(), unmatched_credit]

    with pytest.raises(FinancialInvariantViolation, match=_COMPARISON_MATCH):
        assert_debits_equal_credits(unbalanced)


@pytest.mark.parametrize(
    "side,amount",
    [
        (Side.DEBIT, Decimal(0)),  # regression for mutant M6 (<= changed to <)
        (Side.DEBIT, Decimal(-10)),
        (Side.DEBIT, Decimal("NaN")),
        (Side.DEBIT, Decimal("Infinity")),  # regression for NF-1(a)
        (Side.DEBIT, Decimal("-Infinity")),
        ("debit", Decimal(10)),  # regression for NF-1(b): str, not Side
        (None, Decimal(10)),
        (object(), Decimal(10)),
        (Side.DEBIT, 10.0),  # regression for mutant M14 (NR3-2): non-Decimal amount
        (Side.DEBIT, 10),
    ],
)
def test_invalid_leg_rejected_at_construction(side: object, amount: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        SyntheticLedgerLeg(uuid4(), "synthetic:cash", side, amount)  # type: ignore[arg-type]


def test_bug_050_counterexample_rejected_at_construction() -> None:
    """Regression for mutant M2/BUG-050: Dr10 + Dr-10 must not construct, so
    it can never again report a false-clean balance."""
    with pytest.raises(ValueError):
        SyntheticLedgerLeg(uuid4(), "synthetic:cash", Side.DEBIT, Decimal(-10))


@pytest.mark.parametrize(
    "legs",
    [
        # NR3-1: a huge leg absorbs a small unmatched leg at 28-digit precision
        # (excess on the DEBIT side).
        [
            SyntheticLedgerLeg(uuid4(), "a", Side.DEBIT, Decimal("1E+30")),
            SyntheticLedgerLeg(uuid4(), "b", Side.DEBIT, Decimal("0.01")),
            SyntheticLedgerLeg(uuid4(), "c", Side.CREDIT, Decimal("1E+30")),
        ],
        # NR3-1: two legs differing only past the 28th significant digit.
        [
            SyntheticLedgerLeg(uuid4(), "a", Side.DEBIT, Decimal("1.0000000000000000000000000001")),
            SyntheticLedgerLeg(uuid4(), "b", Side.CREDIT, Decimal(1)),
        ],
        # NR4-1: the same excess, but on the CREDIT side. Round 3's fix only
        # regression-locked the debit-side sum; a mutant that applies the
        # Inexact trap to the debit sum only (and leaves the credit sum
        # outside localcontext()) survived the suite until this row existed.
        [
            SyntheticLedgerLeg(uuid4(), "a", Side.DEBIT, Decimal("1E+30")),
            SyntheticLedgerLeg(uuid4(), "b", Side.CREDIT, Decimal("1E+30")),
            SyntheticLedgerLeg(uuid4(), "c", Side.CREDIT, Decimal("0.01")),
        ],
        # NR4-1: a magnitude separation no fixed-precision bump (e.g.
        # replacing the trap with ctx.prec = 60) can absorb, pinning the
        # guard's actual mechanism rather than one specific magnitude.
        [
            SyntheticLedgerLeg(uuid4(), "a", Side.DEBIT, Decimal("1E+70")),
            SyntheticLedgerLeg(uuid4(), "b", Side.DEBIT, Decimal("0.01")),
            SyntheticLedgerLeg(uuid4(), "c", Side.CREDIT, Decimal("1E+70")),
        ],
    ],
)
def test_precision_loss_fails_closed(legs: list[SyntheticLedgerLeg]) -> None:
    """Regression for NR3-1/NR4-1: summation must never silently round away
    an imbalance at the decimal context's precision boundary, on either
    side of the posting, at any magnitude a fixed precision bump could be
    mistaken for handling. This must raise the dedicated
    `DEBITS_CREDITS_UNEVALUABLE_PRECISION` code, not `DEBITS_NE_CREDITS` —
    the two totals were never evaluated, so they cannot be asserted unequal.
    The match is anchored (NR6-1): this is the file's fourth `match=`
    assertion and was the only one round 5 left unanchored, which let a
    regression that re-embeds `DEBITS_NE_CREDITS` as an aside in this
    message (re-admitting NR4-3 undetected) pass silently."""
    with pytest.raises(FinancialInvariantViolation, match=_PRECISION_MATCH):
        assert_debits_equal_credits(legs)


def test_precision_boundary_within_context_still_compares_exactly() -> None:
    """A sum that fits exactly within the 28-digit context precision must
    still be compared normally via DEBITS_NE_CREDITS, never
    DEBITS_CREDITS_UNEVALUABLE_PRECISION. The match is anchored to the
    start of the message (NR5-1): an unanchored search would also accept
    the precision-trap message if that message ever mentioned
    "DEBITS_NE_CREDITS" in passing, as an earlier version did, which let
    mutant T6 (ctx.prec = 27 alongside the trap) survive undetected. With
    the anchor, and with the precision message no longer naming the
    comparison code at all, only a real DEBITS_NE_CREDITS-prefixed message
    can satisfy this assertion."""
    legs = [
        SyntheticLedgerLeg(uuid4(), "a", Side.DEBIT, Decimal("1E+27")),
        SyntheticLedgerLeg(uuid4(), "b", Side.DEBIT, Decimal(1)),
        SyntheticLedgerLeg(uuid4(), "c", Side.CREDIT, Decimal("1E+27")),
    ]
    with pytest.raises(FinancialInvariantViolation, match=_COMPARISON_MATCH):
        assert_debits_equal_credits(legs)


def test_all_match_assertions_are_anchored() -> None:
    """OBS-4 (rounds 6/7): both route-match patterns this file's four
    `pytest.raises(..., match=...)` call sites share must be anchored to
    the start of the message. An unanchored `match=` is the exact
    structural gap NR5-1 and NR6-1 each exploited, in opposite directions,
    three rounds apart (see BUG-050).

    **Corrected 2026-10-03, round 11 (NR11-1/R11b-1):** this test
    previously asserted only `.startswith("^")` and claimed that, because
    every call site uses one of the two constants, pinning the constants
    pins every call site at once. Both halves were overclaims: pinning
    only the anchor prefix left each constant's remaining text
    unverified (truncating `_COMPARISON_MATCH` to `r"^D"` still passed
    this assertion and, composed with mutant T6, produced a fully green
    suite — no decoy call site needed), and pinning the constants alone
    never verified *which* constant belongs at *which* call site
    (swapping the two constants at one call site also still passed this
    assertion and, composed with T6, was likewise fully green). This test
    now pins each constant's exact value, closing the truncation gap
    outright; `test_match_assertions_use_only_the_shared_constants` below
    now also pins call-site-to-specific-constant correspondence, closing
    the swap gap. Together these two tests verify both halves this
    docstring previously only asserted — see BUG-050's round-11 section
    for the composed-mutant evidence for both gaps."""
    assert _COMPARISON_MATCH == r"^DEBITS_NE_CREDITS"
    assert _PRECISION_MATCH == r"^DEBITS_CREDITS_UNEVALUABLE_PRECISION"


def test_error_codes_are_mutually_disjoint() -> None:
    """OBS-4 (rounds 6/7): neither route's raised message may contain the
    other route's error code as a substring. This is the structural half
    of the same defect class NR5-1 and NR6-1 exploited: a future edit that
    re-embeds one code's name in the other route's message (as both an
    earlier precision-route message and mutant T11's regression did) must
    fail here directly, without needing a `match=` assertion or a mutant
    to expose it."""
    with pytest.raises(FinancialInvariantViolation) as comparison_exc:
        assert_debits_equal_credits(
            [SyntheticLedgerLeg(uuid4(), "synthetic:cash", Side.DEBIT, Decimal("10.00"))]
        )
    with pytest.raises(FinancialInvariantViolation) as precision_exc:
        assert_debits_equal_credits(
            [
                SyntheticLedgerLeg(uuid4(), "a", Side.DEBIT, Decimal("1E+30")),
                SyntheticLedgerLeg(uuid4(), "b", Side.DEBIT, Decimal("0.01")),
                SyntheticLedgerLeg(uuid4(), "c", Side.CREDIT, Decimal("1E+30")),
            ]
        )
    comparison_message = str(comparison_exc.value)
    precision_message = str(precision_exc.value)
    assert "DEBITS_CREDITS_UNEVALUABLE_PRECISION" not in comparison_message
    assert "DEBITS_NE_CREDITS" not in precision_message


def test_match_assertions_use_only_the_shared_constants() -> None:
    """OBS-6 (round 8), corrected round 9 (NR9-2/NR9-3), scope narrowed
    round 10 (NR10-1): `test_all_match_assertions_are_anchored` pins the
    two constants, not that every call site actually uses them. The
    original regex-based version of this check only matched one exact
    source formatting (single-line, double-quoted literal) — round 9
    showed it was both under- and over-sensitive: four of five
    adversarial variants (single-quoted literal, a multi-line call, an
    identifier missing its leading underscore, an f-string) escaped
    undetected, and a benign multi-line reformat of an existing call
    site (produced by the project's own blocking `ruff format` gate once
    a line exceeds `line-length = 100`) could fail it for no real
    reason. Parsing the AST instead of the source text is
    formatting-immune by construction for the one call shape this check
    actually walks — a direct `pytest.raises(..., match=...)` attribute
    call with `match` passed as a plain keyword argument: within that
    shape, line wrapping and quote style no longer matter, and the
    `match` argument must resolve to a bare `Name` node referencing one
    of the two shared constants.

    This is narrower than "every match= call site" (round 10, NR10-1):
    the check does not resolve name bindings (a local variable rebound
    to one of the two constant identifiers still passes), does not see
    a call written via `from pytest import raises` (only the
    `pytest.raises` attribute form is walked), does not see `match`
    passed through `**kwargs` unpacking (only a literal `match=` keyword
    is inspected), and does not see a call reached through a module
    alias such as `import pytest as pt; pt.raises(...)` (only the
    literal name `pytest` is matched; disclosed 2026-10-03, round 12,
    R12-3).

    **Extended 2026-10-03, round 11 (NR11-1/R11b-1):** this check also
    asserts, per enclosing test function, that the `match` value is the
    *specific* constant that function's own negative case expects, not
    merely one of the two — closing a correspondence gap the original
    version left open.

    **Partially described here, corrected 2026-10-04, round 14 (R14-2):**
    this paragraph previously said the per-gap decoy mechanism was
    "deliberately not described" and that this docstring "stops at the
    four-gap enumeration above" — both false: the parenthetical two
    sentences below is itself a mechanism description, and round 14
    independently re-verified it is correct (`G1c` alone is green with
    no decoy; `G2`/`G3`/`G4` are each green only with a decoy co-located
    in the same enclosing test function). Round 13's actual intent —
    stop writing a sixth full description and point at re-runnable
    evidence instead of one more prose attempt — was sound; the "stops
    at" sentence simply overstated how much text had been removed. See
    `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-050-financial-invariant-placeholder-false-clean.md`'s
    round-13 section for the exact reproduction table (shape, decoy
    placement, observed pass/fail) a reader can re-run rather than
    trust, and that file's round-14 section for the independent
    re-confirmation. Every surviving escape among these four still
    requires editing this test file itself — none is reachable from
    product code, and `assert_debits_equal_credits` has been fuzz-clean
    and byte-stable since round 4 — so these four remain deliberately
    open per round 10-13's own scoping judgment, not chased further
    here.

    **A fifth, categorically different gap class, round 14 (R14-1),
    mechanism elevated round 15 (R15-1/R15-2/R15-4):** the four gaps
    above are all *walker-blindness* shapes — the call site exists and
    executes, but the AST walker cannot see it. Round 14 found the
    inverse was unchecked: nothing verified that a validated call site
    actually **ran**, closed by a new per-test check
    (`test_critical_negative_tests_are_not_suppressed`) against four
    shapes (skip/xfail/redefinition/rebind of a negative-case test).
    Round 15 found that check was itself exactly as suppressible as what
    it watched (R15-1: skip/redefine/rebind *the check*, fully green),
    that its marker match was alias-blind (R15-2: `from pytest import
    mark` / `import pytest as pt` both escaped it), and that a
    module-level `pytestmark` suppressed every test in the file
    including the check itself, catching nothing (R15-4). All three are
    now closed by `assert_execution_not_suppressed` (see
    `_execution_suppression_guard.py`), called **eagerly at this file's
    module level** rather than only from inside a collected test — the
    one change that makes the check itself immune to every suppression
    shape that defeats a *test*, since it is no longer only reachable as
    one.

    **Corrected round 16 (§9): the paragraph this replaces overstated
    what remains open, carrying forward round 14's framing unrevised
    after round 15 changed the mechanism it described.** Tested
    directly (a throwaway stand-in package, `pytest -k`/`-m`/
    `--collect-only`, and a `pytest_collection_modifyitems` conftest
    hook, each against an eager-import-time assertion standing in for
    this file's own call), not merely asserted:
    - **`-k`/`-m` deselection is NOT a gap.** Deselection filters
      *after* collection, and collection already imports the module —
      the eager call has already fired by the time any filter applies.
      This was true of round 14's mechanism (a collected, deselectable
      test); it stopped being true the moment round 15 moved the check
      to module import time, and no record caught that the claim needed
      revising.
    - **A `conftest.py`-level skip is only half a gap.** A
      `pytest_collection_modifyitems` hook that adds a skip marker to
      every item runs *after* import too, so it does not evade this
      check either. Only the shape that prevents the file from being
      collected at all (`collect_ignore`, `--ignore`, or simply
      invoking pytest against a narrower path) is real — and that is
      not really "a skip," it is a different, single, genuinely
      irreducible residue (see below).
    - **An in-body `pytest.skip()` call is a real, closable gap**, not
      invisible "in principle": it is a plain `Call` node inside the
      watched function's body, in the same file this check already
      parses for decorators/`pytestmark`/redefinition/rebind. Closing
      it is a small, optional addition to the existing walker, not a
      new mechanism — not built here, since neither SCN-MOD001-132 nor
      SCN-MOD001-133 asks for tamper-resistance against an editor
      willing to add a line inside a test body (see BUG-050's round-16
      section for the full reasoning).

    **The one genuinely irreducible residue is therefore narrower than
    previously stated: the watched file is never collected at all**
    (`collect_ignore`/`--ignore`/a narrowed invocation path). No
    in-repository mechanism — including a `pytest_sessionfinish`
    execution witness — closes this: such a hook has to live somewhere,
    and whatever prevents the watched file from being collected equally
    prevents a hook living in that file from registering; moving the
    hook to a `conftest.py` only relocates the same question one level
    up. This residue is controlled by the reviewed CI invocation being a
    reviewed diff in its own right, not by any mechanism inside this
    file. See BUG-050's round-14, round-15, and round-16 sections for
    the full reproduction evidence and reasoning."""
    tree = ast.parse(Path(__file__).read_text())
    expected_constant_by_function = {
        "test_unbalanced_synthetic_entry_fails_closed": "_COMPARISON_MATCH",
        "test_unmatched_credit_fails_closed": "_COMPARISON_MATCH",
        "test_precision_loss_fails_closed": "_PRECISION_MATCH",
        "test_precision_boundary_within_context_still_compares_exactly": "_COMPARISON_MATCH",
    }
    match_args: list[ast.expr] = []
    found_by_function: dict[str, list[ast.expr]] = {}
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "raises"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "pytest"):
                continue
            for keyword in node.keywords:
                if keyword.arg == "match":
                    match_args.append(keyword.value)
                    found_by_function.setdefault(function.name, []).append(keyword.value)

    assert len(match_args) == 4, (
        f"expected 4 pytest.raises(..., match=...) call sites, found {len(match_args)}"
    )
    for value in match_args:
        assert isinstance(value, ast.Name) and value.id in (
            "_COMPARISON_MATCH",
            "_PRECISION_MATCH",
        ), f"match= call site is {ast.dump(value)!r}, not a bare reference to a shared constant"

    assert set(found_by_function) == set(expected_constant_by_function), (
        "match= call sites were not found in exactly the expected test functions: "
        f"found {sorted(found_by_function)}, expected {sorted(expected_constant_by_function)}"
    )
    for function_name, expected_constant in expected_constant_by_function.items():
        [value] = found_by_function[function_name]
        assert isinstance(value, ast.Name) and value.id == expected_constant, (
            f"{function_name} uses {ast.dump(value)!r}, expected a bare reference to"
            f" {expected_constant}"
        )


def test_critical_negative_tests_are_not_suppressed() -> None:
    """R14-1 (round 14), elevated round 15 (R15-1/R15-2/R15-4): this test
    is now a thin, pytest-visible wrapper — kept under its original name
    for reporting and for the durable records that already reference it
    by name — around the real check, which round 15 moved to module level
    in this file (see the `assert_execution_not_suppressed(...)` call near
    the top) specifically so the check itself cannot be defeated by the
    same suppression shapes it watches for.

    Round 14's own version of this check ran only as a collected pytest
    item, which round 15 (R15-1) showed was the exact same defect class
    one level up: skipping, redefining, or rebinding *this test itself*
    reopened all four of round 14's shapes, fully green, `ruff`/`mypy
    --strict` both clean. Its suppressing-marker match was also shape-
    bound to the literal `pytest.mark.*` attribute chain (R15-2):
    `from pytest import mark` plus `@mark.skip(...)`, and `import pytest
    as pt` plus `@pt.mark.skip(...)`, each escaped it the same way,
    equally fully green and lint-clean. A module-level `pytestmark`
    assignment (R15-4) skipped every test in the file at once —
    including this one — so no per-function check, however written,
    could have caught it from inside a test body.

    The module-level call this test now wraps runs unconditionally at
    import time, before pytest's skip/xfail/redefinition/rebind/
    `pytestmark` machinery has any effect, closing all three routes in
    one mechanism rather than one more per-shape patch. This wrapper
    calling the same already-run check is intentionally redundant with
    that eager call; it exists only so a reader scanning test names, or
    a tool that greps collected test IDs, still sees this protection
    named explicitly. See `_execution_suppression_guard.py`'s own module
    docstring for the full mechanism and BUG-050's round-15 remediation
    section for the reproduction evidence."""
    assert_execution_not_suppressed(
        Path(__file__), _SELF_CHECK_NAMES | _REQUIRED_NEGATIVE_CASE_NAMES
    )
