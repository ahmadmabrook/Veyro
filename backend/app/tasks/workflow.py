"""MOD-026 · AUT-02-R02 and R03: what a task and a case may become, and when.

Pure decisions, no I/O. The schema holds the same rules -- `tsk_tasks_status`,
`tsk_tasks_settlement_attributed` and the two one-way triggers in
`migrations/tenant/0019_tasks_and_cases.sql` -- and that duplication is deliberate and is the
one this repository argues for: the service answers a caller with a sentence naming the field,
and the database is the half that holds when the service is wrong. **What must not happen is
the two disagreeing**, so the transition tables here are compared against the schema's own
CHECK text by `test_tasks_domain.py` rather than trusted to stay in step.

MOD-020 shipped the counter-example: its waitlist state machine admitted an edge its trigger
refused, "both encodings agreed with each other and neither agreed with the service", and from
the moment one member failed to answer an offer nobody was promoted again while places sat
free.
"""

from __future__ import annotations

from typing import Final

TASK_STATUSES: Final[tuple[str, ...]] = (
    "open", "in_progress", "blocked", "done", "cancelled",
)
CASE_STATUSES: Final[tuple[str, ...]] = ("open", "resolved", "closed")

#: A task's settled states. Both carry an attribution trio, because "why was this not done" is
#: the question R07's outcome reporting exists to answer and a cancelled task with no reason
#: answers it with silence.
SETTLED: Final[frozenset[str]] = frozenset({"done", "cancelled"})

#: What a task may become from where it is.
#:
#: **`blocked` is reachable in both directions and the settled states are reachable from
#: anywhere unsettled**, because a task can be cancelled before anybody starts it -- which is
#: most cancellations. What is not here is any edge *out* of a settled state: a settled task
#: does not reopen, and the trigger says so as well.
TASK_EDGES: Final[dict[str, tuple[str, ...]]] = {
    "open": ("in_progress", "blocked", "done", "cancelled"),
    "in_progress": ("open", "blocked", "done", "cancelled"),
    "blocked": ("open", "in_progress", "cancelled"),
    "done": (),
    "cancelled": (),
}

#: A case moves forward only. A problem that returns is a new case citing the old through
#: `recurs_from_case_id`, which is this build's answer everywhere else -- MOD-016's credit
#: note, MOD-019's new rule version, MOD-014's merge pointer -- and the reason it is the answer
#: *here* is concrete: the resolution attribution CHECK requires an `open` case to carry no
#: resolution, so a reopen would erase the attribution the trigger exists to protect.
CASE_EDGES: Final[dict[str, tuple[str, ...]]] = {
    "open": ("resolved", "closed"),
    "resolved": ("closed",),
    "closed": (),
}


class WorkflowError(ValueError):
    """A transition or a rule this module refuses."""


def check_task_transition(current: str, target: str) -> None:
    """Refuse a task transition the schema would refuse.

    The error names *why* rather than restating the pair, because a caller reading
    "open -> done is not allowed" learns nothing it did not send.
    """
    if current not in TASK_STATUSES:
        raise WorkflowError(f"{current!r} is not a task status")
    if target not in TASK_STATUSES:
        raise WorkflowError(f"{target!r} is not a task status")
    if target == current:
        raise WorkflowError(
            f"this task is already {current}; a status change that changes nothing would "
            "write an attribution for a decision nobody made")
    if current in SETTLED:
        raise WorkflowError(
            f"this task was {current} and a settled task does not reopen; raise a new one "
            "and say why in its title")
    if target not in TASK_EDGES[current]:
        raise WorkflowError(
            f"a {current} task cannot become {target}: a blocked task is unblocked before it "
            "is finished, so that its dependency is either satisfied or removed on the record")


def check_case_transition(current: str, target: str) -> None:
    """Refuse a case transition the schema would refuse."""
    if current not in CASE_STATUSES:
        raise WorkflowError(f"{current!r} is not a case status")
    if target not in CASE_STATUSES:
        raise WorkflowError(f"{target!r} is not a case status")
    if target == current:
        raise WorkflowError(f"this case is already {current}")
    if target not in CASE_EDGES[current]:
        raise WorkflowError(
            f"a case moves open to resolved to closed and not back, so a {current} case "
            f"cannot become {target}; a problem that returns is a new case citing this one")


def settlement_needs_a_reason(target: str) -> bool:
    """Does moving to `target` require the attribution trio.

    Returned rather than assumed, because the route decides whether `reason` is a required
    field from this and a route that required it always would refuse an ordinary
    `open -> in_progress`.
    """
    if target not in TASK_STATUSES:
        raise WorkflowError(f"{target!r} is not a task status")
    return target in SETTLED


def blocking(dependencies: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    """Which of a task's dependencies are still in the way.

    `dependencies` is `(task_id, status)` for each task this one depends on, read by the
    caller. A dependency is in the way until it is **settled**, which includes `cancelled`:
    work that was called off no longer blocks, and treating it as blocking would leave every
    downstream task permanently stuck with no way to clear it -- MOD-016's bundle-fulfilment
    finding, where a transient failure made an obligation unsatisfiable for ever.

    Returns the blockers in the order given, so a surface can name them rather than print a
    count. A count is what a reader cannot act on -- MOD-005's "a rule id is not a reason".
    """
    out: list[str] = []
    for task_id, status in dependencies:
        if status not in TASK_STATUSES:
            raise WorkflowError(f"{status!r} is not a task status")
        if status not in SETTLED:
            out.append(task_id)
    return tuple(out)


def check_no_cycle(
    task_id: str, depends_on: str, edges: tuple[tuple[str, str], ...],
) -> None:
    """Refuse a dependency that would close a cycle.

    **The schema refuses a self-reference and cannot see a longer cycle**, because that spans
    rows -- so this is the half that has to hold, and the migration says so rather than
    implying the CHECK covers it.

    `edges` is every `(task_id, depends_on_task_id)` already recorded in the tenant, read by
    the caller inside the transaction that will write the new one. A cycle leaves every task
    in it `blocked` with nothing able to unblock any of them, which is a declared state the
    product cannot leave -- the shape MOD-020's expired-offer edge had, where places sat free
    because the only exit was refused.
    """
    if task_id == depends_on:
        raise WorkflowError("a task cannot depend on itself")
    # Walk forward from the proposed dependency: if it reaches back to `task_id`, the new edge
    # closes a loop. Iterative rather than recursive, so a long chain cannot exhaust the stack
    # on caller-supplied data.
    ahead: dict[str, list[str]] = {}
    for a, b in edges:
        ahead.setdefault(a, []).append(b)
    seen: set[str] = set()
    frontier = [depends_on]
    while frontier:
        here = frontier.pop()
        if here == task_id:
            raise WorkflowError(
                "this dependency would close a cycle, and every task in a cycle is blocked "
                "with nothing able to unblock it")
        if here in seen:
            continue
        seen.add(here)
        frontier.extend(ahead.get(here, ()))


def _check_edges_are_well_formed() -> None:
    """Every edge names a declared status, and no settled state has an exit. At import.

    MOD-010's argument: a catalogue is checked where it is declared rather than at a
    registration endpoint, because that is where somebody is writing the change. Both
    directions, so a status with no entry in the table fails as loudly as an edge naming a
    status that does not exist -- which is the one-directional-check lesson this repository
    records for the message catalogue, the id sweep and the worker's job names.
    """
    for name, statuses, table in (
        ("task", TASK_STATUSES, TASK_EDGES), ("case", CASE_STATUSES, CASE_EDGES),
    ):
        missing = set(statuses) - set(table)
        if missing:
            raise AssertionError(f"{name} statuses with no edge list: {sorted(missing)}")
        extra = set(table) - set(statuses)
        if extra:
            raise AssertionError(f"{name} edge lists for unknown statuses: {sorted(extra)}")
        for origin, targets in table.items():
            unknown = set(targets) - set(statuses)
            if unknown:
                raise AssertionError(
                    f"{name} {origin} points at unknown statuses: {sorted(unknown)}")
            if origin in targets:
                raise AssertionError(f"{name} {origin} points at itself")
    for state in SETTLED:
        if TASK_EDGES[state]:
            raise AssertionError(
                f"{state} is settled and has an exit, which would make the one-way trigger "
                f"and this table disagree: {TASK_EDGES[state]}")
    if CASE_EDGES["closed"]:
        raise AssertionError("a closed case has an exit here and not in the trigger")


_check_edges_are_well_formed()
