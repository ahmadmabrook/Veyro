"""MOD-004: whether TSD paragraph 1228's hard-deletion bar applies, as a pure decision.

TSD paragraph 1228, pinned baseline text: "Maintain tenant lifecycle history and prevent hard
deletion before legal, billing and retention gates pass." It is a row of §10.1's "Required
Capabilities Preserved" list, headed at TSD paragraph 1221. This module reads its second clause,
the bar on hard deletion. The first clause, maintaining lifecycle history, is a capability rather
than a decision and is not implemented here.

Slice 14 (`reconciliation_before_deletion`) reads TSD paragraph 778's reconciliation precondition
and routes the question of the gates here. This module is that question's stated rule, and only
its stated rule.

**It decides no gate.** `knowledge/03-Modules/MOD-004/MOD-004.md` records PLT-01-R07 against this
paragraph as OPEN with the reason beginning "Gate criteria and durations owner-reserved", and lists
"Lifecycle retention periods, legal/billing/retention gate criteria, deletion approvers and quorum"
as item 2 under "Unresolved owner-reserved choices (not decided here)". So whether a gate has
passed is a caller claim this module cannot evaluate, and the criteria by which it would be
evaluated do not exist. Each input is required with no default: a default would invent one of them.

**`NOT_BARRED` is not permission to delete.** It says the three gates this paragraph names are
claimed passed, so this paragraph's bar does not apply. TSD paragraph 1231, two rows below under
"Critical Controls", separately requires that "Destructive lifecycle actions require approvals,
retention checks and an immutable audit record", and the approvers and quorum are owner-reserved
and undecided. Nothing here satisfies any of that.

Scope. The result is a reading of three caller claims against one stated clause. It is **not** a
deletion, not permission to delete, not a gate, not an approval, not an audit record, not evidence
that any gate was evaluated, and not lifecycle history. It establishes no authenticated principal,
no authorization of a real caller, no tenant context and no tenant isolation; it is not a database
constraint and not integration evidence. This module performs no I/O, keeps no state, logs nothing
and echoes no raw input.

Two outcomes, one of `OUTCOMES`:
    BARRED      at least one named gate is not claimed passed, so the paragraph's bar applies.
                `outstanding` names which, in the paragraph's order.
    NOT_BARRED  all three are claimed passed, so this paragraph's bar does not apply. See above
                for what that is not.

Inputs, all three required, keyword-only, each an exact `bool`:
    legal, billing, retention.

Fail closed. All three are validated in the paragraph's order before any outcome is decided, so a
malformed claim is refused even when another gate is already outstanding. Each gate has its own
refusal code.
"""

from __future__ import annotations

from dataclasses import dataclass

# The three gates TSD paragraph 1228 names, in its order.
DELETION_GATES = ("legal", "billing", "retention")

BARRED = "barred"
NOT_BARRED = "not_barred"
OUTCOMES = (BARRED, NOT_BARRED)

_MESSAGE = "invalid hard deletion gate claims"


class HardDeletionGateError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class HardDeletionDecision:
    """Immutable decision.

    `barred` is true only for `BARRED`, and only about TSD paragraph 1228's own clause. False
    means this one bar does not apply, not that deletion is permitted. `outstanding` is empty
    exactly when `barred` is false.
    """

    outcome: str
    barred: bool
    outstanding: tuple[str, ...]


def evaluate_hard_deletion_gates(
    *,
    legal: object,
    billing: object,
    retention: object,
) -> HardDeletionDecision:
    """Decide whether TSD paragraph 1228's bar applies for these three claims."""
    claims = ((legal, "bad_legal"), (billing, "bad_billing"), (retention, "bad_retention"))
    for claim, code in claims:
        if type(claim) is not bool:
            raise HardDeletionGateError(code)

    outstanding = tuple(
        gate for gate, (claim, _) in zip(DELETION_GATES, claims, strict=True) if claim is not True
    )
    if outstanding:
        return HardDeletionDecision(outcome=BARRED, barred=True, outstanding=outstanding)
    return HardDeletionDecision(outcome=NOT_BARRED, barred=False, outstanding=())
