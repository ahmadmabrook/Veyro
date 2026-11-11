"""MOD-004: whether TSD paragraph 779's rollback routing condition is met, as a pure decision.

TSD paragraph 779, pinned baseline text, third sentence: "Rollback before source deletion switches
routing back only after target writes are reconciled or discarded." Its first two sentences are the
write-freeze target, which slice 13 (`write_freeze_target`) reads and which explicitly left this
sentence out as a different rule; this module is that rule.

Citations in this file carry an explicit `TSD` or `EIP` prefix wherever the number falls inside the
741-783 window both pinned baselines number, including in passing references, because hand-keeping
that convention has already failed twice in this lane -- slice 13's docstring claimed it while
breaking it five times, and slice 14 reintroduced two bare references one commit after they were
corrected. Nothing automated enforces it: `tools/module_docs/cite_check.py` exists for this defect,
reads a module document rather than a Python source, and CI never invokes it. The surrounding rows
are given because the number alone does not survive a renumbering: TSD paragraph 775 heads "7.5
Tenant Placement and Relocation Workflow", TSD paragraph 777 lists the twelve relocation stages,
and TSD paragraph 778's third sentence is the reconciliation precondition that slice 14 reads.

This module answers one question: for the two claims handed in, is TSD paragraph 779's condition on
switching routing back satisfied?

**The sentence governs rollback *before* source deletion, and says nothing about rollback after
it.** That is why there is a third outcome rather than a convenient answer. The source's subject is
"Rollback before source deletion"; a caller claiming rollback is not before source deletion is
outside the sentence, and this module declines rather than inferring what follows. Whether source
deletion may happen at all is a different question governed by TSD paragraph 778's reconciliation
precondition (slice 14) and by the retention gate, deletion approvers and quorum, which
`knowledge/03-Modules/MOD-004/MOD-004.md` lists as item 2 under "Unresolved owner-reserved choices
(not decided here)". None of those is decided here.

**"Only after" is a necessary condition, not a sufficient one, and the outcome names are chosen so
that reading them cannot suggest otherwise.** `CONDITION_MET` says that TSD paragraph 779's
condition on the routing switch is satisfied. It is not a routing switch, not permission to
perform one, and not a finding that a rollback should happen. No routing exists to switch:
`MOD-004.md` records "no owner or design exists for provisioning and relocation workflows", and
TSD paragraph 776's placement resolution is recorded there as "test-harness only" with transport,
caller authentication and authorization "deferred and OPEN".

**Reconciled or discarded, as a three-state claim rather than two flags.** The source offers two
ways to satisfy the condition and they are alternatives, so `TargetWriteState` has exactly the two
the sentence names plus `OUTSTANDING` for neither. Two booleans would admit a fourth combination --
both reconciled and discarded -- that the source does not describe and that this module would then
have to decide about. There is deliberately no member for "partly reconciled": the sentence says
"target writes are reconciled or discarded" of the writes as a whole, and splitting them would be
inventing a granularity the source does not state. A caller holding a partial state has a source
gap to raise, which is the MOD-004 RLS Rule's obligation 8, not a value to pass.

**The member values are module-chosen identifiers.** As in slice 13, no source states a canonical
spelling for these states -- "reconciled" and "discarded" appear as verbs in a sentence, not as
labels -- so an enum names them rather than a string closure admitting a spelling this module would
have had to invent.

Scope. The result is a reading of two caller claims against one stated sentence. It is **not** a
rollback, not a routing switch, not permission to perform either, not evidence that any target
write was reconciled or discarded, not a reconciliation, not a deletion decision and not a
placement resolution. It establishes no authenticated principal, no authorization of a real caller,
no tenant context and no tenant isolation; it is not a database constraint and not integration
evidence. This module performs no I/O, keeps no state, logs nothing and echoes no raw input.

Three outcomes, one of `OUTCOMES`:
    CONDITION_MET      rollback is before source deletion and target writes are reconciled or
                       discarded, so TSD paragraph 779's condition is satisfied. Necessary, not
                       sufficient; see above.
    WRITES_OUTSTANDING rollback is before source deletion but target writes are neither
                       reconciled nor discarded, so the condition refuses.
    NOT_BEFORE_DELETION the caller does not claim rollback before source deletion, so the
                       sentence has no subject and this module decides nothing. Not a finding
                       that rollback is barred, and not a finding that deletion has occurred.

Inputs, both caller claims:
    before_source_deletion   required exact `bool`; `1` and `0` are refused rather than read.
    target_writes            required exact `TargetWriteState` member.

Fail closed. Both shapes are validated before either is read, so a malformed state is refused even
when the rollback claim already puts the call outside the sentence. Each has its own refusal code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CONDITION_MET = "condition_met"
WRITES_OUTSTANDING = "writes_outstanding"
NOT_BEFORE_DELETION = "not_before_deletion"
OUTCOMES = (CONDITION_MET, WRITES_OUTSTANDING, NOT_BEFORE_DELETION)

_MESSAGE = "invalid rollback routing claims"


class TargetWriteState(Enum):
    """The two states TSD paragraph 779's third sentence names, plus neither of them.

    The member values are lower-case identifiers chosen for this module; the source uses
    "reconciled" and "discarded" as verbs in a sentence and states no canonical label, which is
    why this is an enum rather than a name closure.
    """

    RECONCILED = "reconciled"
    DISCARDED = "discarded"
    OUTSTANDING = "outstanding"


# The two members that satisfy the sentence's "reconciled or discarded".
SATISFYING_STATES = (TargetWriteState.RECONCILED, TargetWriteState.DISCARDED)


class RollbackRoutingError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class RollbackRoutingDecision:
    """Immutable decision.

    `condition_met` is true only for `CONDITION_MET`, and only about TSD paragraph 779's own
    sentence, which states a necessary condition on switching routing back. It is false for
    `NOT_BEFORE_DELETION` because no condition was evaluated there, which is not the same as the
    condition failing -- read `outcome`, not this flag, to tell those two apart.
    """

    outcome: str
    condition_met: bool


def evaluate_rollback_routing(
    *,
    before_source_deletion: object,
    target_writes: object,
) -> RollbackRoutingDecision:
    """Decide whether TSD paragraph 779's routing condition holds for these two claims."""
    if type(before_source_deletion) is not bool:
        raise RollbackRoutingError("bad_before_source_deletion")
    if type(target_writes) is not TargetWriteState:
        raise RollbackRoutingError("bad_target_writes")

    if not before_source_deletion:
        return RollbackRoutingDecision(outcome=NOT_BEFORE_DELETION, condition_met=False)
    if target_writes in SATISFYING_STATES:
        return RollbackRoutingDecision(outcome=CONDITION_MET, condition_met=True)
    return RollbackRoutingDecision(outcome=WRITES_OUTSTANDING, condition_met=False)
