"""MOD-004: whether TSD paragraph 1242's staleness bar refuses a mutation, as a pure decision.

TSD paragraph 1242, pinned baseline text: "Failure/degraded behavior: Write commands fail
atomically; asynchronous effects retry idempotently; stale read models carry freshness and cannot
authorize a consequence-bearing mutation beyond budget." Paragraph 1238 is why a freshness figure
exists to compare: "every projection exposes freshness/version metadata when asynchronously
built."

Both are rows of §10.1 "PLT-01 - Tenant, Organization, Brand & Location Management": paragraph
1242 is its `Failure/degraded behavior` row and paragraph 1238 its `Queries/read models` row. The
row labels are given because the paragraph numbers alone do not survive a baseline renumbering
here. Paragraph 1242's sentence is cross-module boilerplate that recurs in 40 paragraphs of the
pinned TSD -- 57 sections carry a `Failure/degraded behavior` row -- so matching on its text
cannot identify which one is PLT-01's. The §10.1 heading occurs exactly once, and each of these
labels occurs exactly once inside that section, so heading plus label is a unique pair where the
number is not.

This module answers one question: does that bar refuse, for the three values handed in?

**It supplies no budget, and that is the point rather than an omission.**
`knowledge/03-Modules/MOD-004/MOD-004.md` records paragraph 1242 as OPEN with "no read model,
freshness field or budget exists; the budget value is undecided". So `budget` is a required
input with no default: a module that defaulted it would be inventing the undecided value, and a
module that made it optional would let a caller omit the only thing paragraph 1242 measures
against.

**It supplies no unit either.** Paragraph 1242 says "beyond budget" without one. `staleness` and
`budget` are compared directly, so they must already be in the same caller-chosen unit. This
module neither states nor checks what that unit is.

**It does not classify mutations.** Whether a mutation is consequence-bearing is a caller claim.
No pinned source defines the class, and inventing a definition is what the MOD-004 RLS Rule's
obligation 8 forbids.

Scope. The result is a reading of three caller claims. It is **not** a read model, not a freshness
measurement, not an authorization, and not evidence that the `staleness` handed in reflects any
real projection -- paragraph 1238's freshness metadata is the projection's to expose and no
projection exists. A WITHIN_BUDGET result is not permission to mutate: paragraph 1242 bars one
thing, and not being barred by it is not authority from anywhere else. This module performs no
I/O, keeps no state, logs nothing and echoes no raw input. It establishes no authenticated
principal, no authorization of a real caller, no tenant context and no tenant isolation.

Three outcomes, one of `OUTCOMES`:
    REFUSED                   the mutation is consequence-bearing and `staleness` exceeds
                              `budget`. Paragraph 1242's bar applies.
    WITHIN_BUDGET             `staleness` does not exceed `budget`, so the bar does not apply.
                              Equal is within: paragraph 1242 says "beyond budget".
    NOT_CONSEQUENCE_BEARING   the caller claims the mutation is not consequence-bearing, so
                              paragraph 1242's bar has no subject. This is not a finding that the
                              read model is fresh.

Inputs, all caller claims:
    staleness                     required int in 0..MEASURE_MAX inclusive, in the caller's unit.
    budget                        required int in the same range and unit. No default.
    consequence_bearing           required bool. Exact `bool` only; `0` and `1` are refused.

Fail closed. All three shapes are validated before any comparison, and any shape violation is
refused rather than resolved.
"""

from __future__ import annotations

from dataclasses import dataclass

MEASURE_MAX = 2**31 - 1
REFUSED = "refused"
WITHIN_BUDGET = "within_budget"
NOT_CONSEQUENCE_BEARING = "not_consequence_bearing"
OUTCOMES = (REFUSED, WITHIN_BUDGET, NOT_CONSEQUENCE_BEARING)

_MESSAGE = "invalid read model freshness inputs"


class FreshnessError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class FreshnessDecision:
    """Immutable decision. `bar_applies` is true only for the paragraph 1242 refusal."""

    outcome: str
    bar_applies: bool


def _measure_or_refuse(value: object, code: str) -> int:
    """Return `value` as an `int`, or refuse with `code`.

    The leading `isinstance` is what lets a type checker carry the narrowing out of this function,
    so a caller can compare the returned values with `>`; the `type(value) is not int` beside it
    is what refuses `bool` and every other `int` subclass, so no comparison downstream can reach a
    subclass's operators. Slice 4 learned this the hard way: a predicate returning `bool` keeps
    its narrowing to itself and leaves the caller comparing `object`.
    """
    if not isinstance(value, int) or type(value) is not int:
        raise FreshnessError(code)
    if not 0 <= value <= MEASURE_MAX:
        raise FreshnessError(code)
    return value


def evaluate_read_model_freshness(
    staleness: object,
    budget: object,
    consequence_bearing: object,
) -> FreshnessDecision:
    """Decide whether paragraph 1242's staleness bar refuses, for these three claims."""
    measured = _measure_or_refuse(staleness, "bad_staleness")
    allowed = _measure_or_refuse(budget, "bad_budget")
    if type(consequence_bearing) is not bool:
        raise FreshnessError("bad_consequence_bearing")

    if not consequence_bearing:
        return FreshnessDecision(outcome=NOT_CONSEQUENCE_BEARING, bar_applies=False)
    if measured > allowed:
        return FreshnessDecision(outcome=REFUSED, bar_applies=True)
    return FreshnessDecision(outcome=WITHIN_BUDGET, bar_applies=False)
