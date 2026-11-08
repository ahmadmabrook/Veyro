"""MOD-004: whether TSD paragraph 778's epoch-rejection rule fires, as a pure decision.

TSD paragraph 778, pinned baseline text: "The cutover uses a relocation_epoch included in
requests/events. Commands carrying the old epoch are rejected after route switch. ..." -- the
elided third sentence is about reconciliation before source deletion, a different subject.
Paragraph 777 places route switch eighth of twelve relocation stages.

This module answers one question: does that rule fire for the three values handed in? It decides
nothing else.

Scope. The result is a reading of three caller claims. It is **not** a placement resolution, not a
route switch, not a relocation state machine, and not evidence that the `current_epoch` or
`route_switched` handed in reflect any real control-plane record -- paragraph 776 makes placement
a control-plane record and paragraph 782 says domain code never assumes the tenant's placement
shape. A CURRENT result is not permission to execute a command. This module performs no I/O, keeps
no state, logs nothing and echoes no raw input. It establishes no authenticated principal, no
authorization of a real caller, no tenant context and no tenant isolation.

Three outcomes, one of `OUTCOMES`:
    REJECT                paragraph 778's rule fires: the command's epoch is older than the
                          current one and the route has switched.
    CURRENT               the command's epoch equals the current one, so the rule has no subject.
    STALE_BEFORE_SWITCH   the command's epoch is older and the route has not switched. Paragraph
                          778 conditions rejection on "after route switch", so the rule does not
                          fire.

`STALE_BEFORE_SWITCH` names the shape of the inputs, not a policy. Paragraph 778's "after route
switch" qualifier would be vacuous if the before-switch case did not exist, so the complementary
state is implied by the pinned text rather than coined -- but no pinned source states what a
caller should do in it, and this module does not supply one. An earlier revision rested this on an
ADR-0002 clause; a review established that the clause sits in a PROPOSED section, cross-references
a section the record lists as OPEN, and has no occurrence in the pinned extract, so the citation
is removed rather than qualified.

**An epoch ahead of the current one is refused, not decided.** No pinned source states a rule for
it: the sources speak only of "the old epoch" and "an older epoch". Returning any outcome would
invent a rule, so the module raises instead and the caller handles it explicitly. The refusal is
not a rejection ruling -- it reports that this module has no stated basis to decide.

Inputs, all caller claims:
    command_epoch   required int in 0..EPOCH_MAX inclusive.
    current_epoch   required int in the same range.
    route_switched  required bool. Exact `bool` only; `0` and `1` are refused.

Fail closed. Any shape violation is refused rather than resolved, and the shape of all three
inputs is checked before any comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

EPOCH_MAX = 2**31 - 1
REJECT = "reject"
CURRENT = "current"
STALE_BEFORE_SWITCH = "stale_before_switch"
OUTCOMES = (REJECT, CURRENT, STALE_BEFORE_SWITCH)

_MESSAGE = "invalid relocation epoch inputs"


class EpochError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class EpochDecision:
    """Immutable decision. `rule_fires` is true only for the paragraph 778 rejection."""

    outcome: str
    rule_fires: bool


def _epoch_ok(value: object) -> bool:
    return type(value) is int and 0 <= value <= EPOCH_MAX


def evaluate_relocation_epoch(
    command_epoch: object,
    current_epoch: object,
    route_switched: object,
) -> EpochDecision:
    """Decide whether paragraph 778's rejection rule fires for these three claims."""
    if not _epoch_ok(command_epoch):
        raise EpochError("bad_command_epoch")
    if not _epoch_ok(current_epoch):
        raise EpochError("bad_current_epoch")
    if type(route_switched) is not bool:
        raise EpochError("bad_route_switched")

    if command_epoch > current_epoch:
        raise EpochError("epoch_ahead_of_current")
    if command_epoch == current_epoch:
        return EpochDecision(outcome=CURRENT, rule_fires=False)
    if route_switched:
        return EpochDecision(outcome=REJECT, rule_fires=True)
    return EpochDecision(outcome=STALE_BEFORE_SWITCH, rule_fires=False)
