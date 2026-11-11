"""MOD-004: whether TSD paragraph 778's reconciliation precondition is met, as a pure decision.

TSD paragraph 778, pinned baseline text, third sentence: "All copied row counts, ledger control
totals, outbox high-water marks, object references and search/read projections are reconciled
before source deletion." Its first two sentences are the relocation_epoch rule, which slice 4
(`relocation_epoch`) already reads; this module reads only the third.

Citations in this file carry an explicit `TSD` or `EIP` prefix wherever the number falls inside the
741-783 window both pinned baselines number, because there the two documents are unrelated: TSD
paragraph 778 is this reconciliation sentence, while EIP paragraph 778 is the single word "Code",
a header cell of the scenario-category table whose next two cells are "Scenario category" and
"Required deepening question". Nothing automated enforces the convention here --
`tools/module_docs/cite_check.py` exists for the defect but reads a module document and CI never
invokes it -- so this file keeps it by hand. The surrounding rows are given because the number
alone does not survive a renumbering: TSD paragraph 775 heads "7.5 Tenant Placement and Relocation
Workflow", TSD paragraph 777 lists the twelve relocation stages, ending "source quarantine →
source deletion after retention gate", and TSD paragraph 779 states the write-freeze target that
slice 13 reads.

This module answers one question: for the five claims handed in, is TSD paragraph 778's
reconciliation precondition satisfied?

**Satisfying it is not permission to delete, and this is the module's most important limit.**
TSD paragraph 778 states one necessary condition. TSD paragraph 777's own stage list puts source
deletion "after retention gate", and `knowledge/03-Modules/MOD-004/MOD-004.md` records
PLT-01-R07 -- "Tenant lifecycle history; no hard deletion before legal, billing and retention gates
pass" -- as OPEN, its reason beginning "Gate criteria and durations owner-reserved", and lists
"Lifecycle retention periods, legal/billing/retention gate criteria, deletion approvers and
quorum" as item 2 under "Unresolved owner-reserved choices (not decided here)". So the retention
gate, the approvers and the quorum are undecided and owner-reserved, this module decides none of
them, and a `RECONCILED` result leaves every one of them outstanding. A caller treating it as
clearance to delete a tenant's source data would be acting on one condition out of several, and on
the only one of them that is merely stated rather than decided.

**The five claims describe a process that does not exist.** `MOD-004.md` records "RB-PLT-01 and
RUNBOOK.md: **OPEN** (reconciliation owner and workflow orchestration undesigned)" and, for durable
workflow orchestration, "no owner or design exists for provisioning and relocation workflows". No
reconciliation runs anywhere in this repository. Each input is therefore a caller claim that some
reconciliation happened, and this module can neither perform one nor check that one did. It reads
the five claims and nothing else.

**All five, with no default.** Every parameter is required and keyword-only. A default of `True`
would invent a reconciliation the source requires evidence of; a default of `False` would answer
`OUTSTANDING` for a subject the caller never spoke about, which reads like a finding and is not
one. Keyword-only because five same-typed claims in a row are the kind of signature a caller
silently transposes, and a transposition here would move an outstanding subject onto a reconciled
one without any error.

**The subject names are the source's own.** Unlike TSD paragraph 779's tenant classes, these five
are spelled canonically inside a single sentence, so `RECONCILIATION_SUBJECTS` quotes them in that
sentence's order, solidus and hyphen included. The parameter names are the same five in the
spelling Python requires, which is the only place this module rewrites them.

Scope. The result is a reading of five caller claims against one stated sentence. It is **not** a
reconciliation, not evidence that any reconciliation ran, not a row count, not a ledger control
total, not a retention gate, not a deletion approval and not authority to delete anything. It
establishes no authenticated principal, no authorization of a real caller, no tenant context and
no tenant isolation; it is not a database constraint and not integration evidence. This module
performs no I/O, keeps no state, logs nothing and echoes no raw input.

Two outcomes, one of `OUTCOMES`:
    RECONCILED    all five subjects are claimed reconciled, so TSD paragraph 778's precondition is
                  met. Not a deletion decision; see above.
    OUTSTANDING   at least one is not. `outstanding` names which, in the sentence's order.

Inputs, all five required, keyword-only, each an exact `bool` -- so `1`, `0`, `"yes"` and every
other truthy or falsy stand-in is refused rather than read as a claim:
    copied_row_counts, ledger_control_totals, outbox_high_water_marks, object_references,
    search_read_projections.

Fail closed. All five are validated in the sentence's order before any outcome is decided, so a
malformed claim is refused even when another subject is already outstanding and the answer would
have been `OUTSTANDING` anyway. Each subject has its own refusal code, so a caller can tell which
claim was malformed without the refusal carrying the value.
"""

from __future__ import annotations

from dataclasses import dataclass

# The five subjects TSD paragraph 778's third sentence names, in its order and its spelling.
RECONCILIATION_SUBJECTS = (
    "copied row counts",
    "ledger control totals",
    "outbox high-water marks",
    "object references",
    "search/read projections",
)

RECONCILED = "reconciled"
OUTSTANDING = "outstanding"
OUTCOMES = (RECONCILED, OUTSTANDING)

_MESSAGE = "invalid reconciliation claims"


class ReconciliationError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    """Immutable decision.

    `precondition_met` is true only for `RECONCILED`, and only about TSD paragraph 778's own
    sentence. It says nothing about the retention gate, the deletion approvers or the quorum,
    which are owner-reserved and undecided, so it is not a deletion decision in either state.
    `outstanding` is empty exactly when `precondition_met` is true.
    """

    outcome: str
    precondition_met: bool
    outstanding: tuple[str, ...]


def evaluate_reconciliation_before_source_deletion(
    *,
    copied_row_counts: object,
    ledger_control_totals: object,
    outbox_high_water_marks: object,
    object_references: object,
    search_read_projections: object,
) -> ReconciliationDecision:
    """Decide whether TSD paragraph 778's precondition is met for these five claims."""
    claims = (
        (copied_row_counts, "bad_copied_row_counts"),
        (ledger_control_totals, "bad_ledger_control_totals"),
        (outbox_high_water_marks, "bad_outbox_high_water_marks"),
        (object_references, "bad_object_references"),
        (search_read_projections, "bad_search_read_projections"),
    )
    for claim, code in claims:
        if type(claim) is not bool:
            raise ReconciliationError(code)

    # strict=True so that a future edit adding a subject to one sequence and not the other raises
    # rather than silently truncating, which would drop a subject from `outstanding`.
    outstanding = tuple(
        subject
        for subject, (claim, _) in zip(RECONCILIATION_SUBJECTS, claims, strict=True)
        if claim is not True
    )
    if outstanding:
        return ReconciliationDecision(
            outcome=OUTSTANDING, precondition_met=False, outstanding=outstanding
        )
    return ReconciliationDecision(outcome=RECONCILED, precondition_met=True, outstanding=())
