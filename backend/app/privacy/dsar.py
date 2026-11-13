"""MOD-009 SEC-01-R07: the data subject request workflow, decided without touching the database.

TSD paragraph 4384: the workflow "handles access, correction, portability, restriction and
deletion with identity verification, legal hold and subprocessor propagation". The order in that
sentence is the order enforced here, and the ordering is the substance of the module.

**Identity is verified before the legal check, and both before anything is done.** Each step
exists to stop a different attack. Verifying identity first stops the request that is itself the
attack -- "delete everything belonging to this member", sent by someone who is not that member,
is a denial-of-service with no undo, and an access request from an impostor is a data breach
performed by the controller's own compliance process. Checking legal holds second stops a
lawfully-made request from destroying evidence somebody is required to preserve. Doing neither
until both have passed is what stops a half-finished erasure.

**No deadline is defaulted.** The TSD refers to a "DSAR SLA" (paragraph 4414) and never states
one, and the statutory period under Jordan PDPL No. 24 of 2023 is a legal fact this repository's
sources do not contain. `open_request` therefore requires `response_days` from the caller and
refuses to invent one, exactly as `app.billing.service.issue_invoice` requires a tax rate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol


class Target(Protocol):
    """What `plan` needs of a `classification.Reachability`, named so this module keeps no
    dependency on the registry it describes."""

    @property
    def schema(self) -> str: ...
    @property
    def table(self) -> str: ...
    @property
    def column(self) -> str: ...
    @property
    def mechanism(self) -> str: ...

REQUEST_TYPES = ("access", "correction", "portability", "restriction", "deletion")

#: The request types this build can actually carry out. Separate from REQUEST_TYPES because a
#: request of any of the five may be opened, verified and legal-checked -- refusing to accept an
#: access request would be refusing the commonest DSAR there is -- while only a deletion has an
#: executor behind it. `fulfil_dsar` checks this before it writes anything, so an unexecutable
#: request stays where it was instead of being stranded in `fulfilling`.
EXECUTABLE_REQUEST_TYPES = ("deletion",)

# The states a request moves through, and the only moves allowed between them. Written as a map
# rather than as a chain of `if`s so that the whole machine is readable at once, and so that a
# state nobody can leave shows up as an empty tuple rather than as a missing branch.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "received": ("identity_pending", "refused"),
    "identity_pending": ("legal_pending", "refused"),
    "legal_pending": ("ready", "refused"),
    "ready": ("fulfilling", "refused"),
    "fulfilling": ("completed", "refused"),
    "completed": (),
    "refused": (),
}

# Which mechanism each request type uses when it acts on a store. `access` and `portability` both
# read; they differ in the shape of what comes back, not in what they touch.
#
# `plan` no longer reads this -- a plan names each target's own mechanism, because deriving it
# from the request type made the plan advertise `delete` for rows the executor anonymized. It
# stays because it is the mapping a future executor for the other four types will need, and it
# is the only written statement of what each request type is supposed to do to a store.
MECHANISM_FOR: dict[str, str] = {
    "access": "export",
    "portability": "export",
    "correction": "anonymize",
    "restriction": "restrict",
    "deletion": "delete",
}


class DsarError(ValueError):
    """A request that cannot be moved as asked."""


@dataclass(frozen=True)
class Request:
    request_id: str
    subject_id: str
    request_type: str
    status: str
    received_at: datetime
    due_at: datetime
    identity_verified_at: datetime | None = None
    legal_checked_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class Action:
    """One thing done to one target, and the evidence that it was done."""

    store: str
    target: str
    mechanism: str
    outcome: str
    rows_affected: int
    detail: dict[str, object] = field(default_factory=dict)


def open_request(
    *, request_type: str, received_at: datetime, response_days: int, now: datetime,
) -> dict[str, object]:
    """Validate a new request and compute its deadline. Raises rather than guessing.

    `response_days` has no default on purpose -- see the module docstring. A caller that does not
    know its own statutory deadline should find out rather than inherit one from this file.

    `received_at` is bounded too, which it was not. The deadline is computed from it, so a
    caller that can set it freely can set the regulator-facing deadline and the `overdue` flag:
    a request dated into the future is never late, and one backdated far enough arrives already
    overdue. A paper request logged a few days after it arrived is the legitimate case, so the
    past is allowed and the future is not -- the same shape as `consent.check_grant`.
    """
    if request_type not in REQUEST_TYPES:
        raise DsarError("unknown_request_type")
    if received_at > now:
        raise DsarError("received_in_the_future")
    if response_days <= 0:
        raise DsarError("response_days_must_be_positive")
    if response_days > 365:
        # Not a legal limit, a typo guard: a deadline a year out is almost certainly days and
        # months transposed, and the resulting request would never appear overdue.
        raise DsarError("response_days_implausible")
    return {
        "request_type": request_type,
        "status": "received",
        "received_at": received_at,
        "due_at": received_at + timedelta(days=response_days),
    }


def check_transition(current: str, target: str) -> None:
    """Refuse a move the machine does not allow."""
    if current not in TRANSITIONS:
        raise DsarError("unknown_status")
    if target not in TRANSITIONS:
        raise DsarError("unknown_target_status")
    if target not in TRANSITIONS[current]:
        raise DsarError(f"cannot_move_from_{current}_to_{target}")


def check_ready_to_fulfil(request: Request) -> None:
    """The gate in front of every irreversible step.

    Re-checked here rather than trusted from the status alone. The status is one column that one
    UPDATE moves; these are the two facts that status is supposed to summarise, and a summary
    that can be set without the facts behind it is how a request gets fulfilled for an
    unverified requester.

    `fulfilling` is accepted as well as `ready`, which is what makes an interrupted run
    resumable. A transient failure on the identity plane used to leave a valid request in
    `fulfilling` for ever: the only transitions out are `completed` and `refused`, and a retry
    was refused here. Re-running is safe because every expression in `service._CLEAR_SQL` is
    either idempotent or writes a fresh tombstone over one already written, and the evidence
    trail is insert-only, so both attempts remain visible.
    """
    if request.identity_verified_at is None:
        raise DsarError("identity_not_verified")
    if request.legal_checked_at is None:
        raise DsarError("legal_check_not_done")
    if request.status not in ("ready", "fulfilling"):
        raise DsarError("request_is_not_ready")


def overdue(request: Request, now: datetime) -> bool:
    return request.status not in ("completed", "refused") and now > request.due_at


def plan(request_type: str, reachable: Sequence[Target],
         unreachable: Sequence[Target]) -> list[dict[str, object]]:
    """What a request will do, and what it cannot do, before it does anything.

    Both lists carry the registry's own entries, and each planned step names **that target's**
    mechanism rather than one derived from the request type. It did derive it, and the plan
    therefore advertised `delete` for all seven reachable targets while the executor anonymized
    every one of them. The plan is the artefact somebody reviewing an erasure reads before
    approving it; a plan that misdescribes what will happen to every row it names is worse than
    no plan.

    Returning the unreachable targets as planned-but-blocked, rather than filtering them out, is
    what makes the residue visible before the run and not only in the outcome.
    """
    rows: list[dict[str, object]] = []
    for entry in reachable:
        rows.append({"store": "postgresql",
                     "target": f"{entry.schema}.{entry.table}.{entry.column}",
                     "mechanism": entry.mechanism, "expected": "done"})
    for entry in unreachable:
        rows.append({"store": "postgresql",
                     "target": f"{entry.schema}.{entry.table}.{entry.column}",
                     "mechanism": "pseudonymize", "expected": "blocked"})
    return rows


def settle(request_type: str, actions: list[Action]) -> dict[str, object]:
    """The outcome of a fulfilled request: what was done, what was not, and whether to say
    "completed".

    A request completes when every action that could be attempted was attempted. It completes
    *with residue* when some target was blocked, and the residue is named rather than summarised
    away: a subject told their data was erased, when rows naming them remain in a ledger that
    cannot be rewritten, has been told something false. A controller that cannot fully erase owes
    an explanation of what survived and why, and this is the structure that explanation is built
    from.

    A failed action is different from a blocked one and does not complete the request. Blocked
    means the system is working as designed and the data stays by decision; failed means
    something broke, and reporting a broken erasure as finished is how backup residue becomes a
    surprise years later.
    """
    failed = [a for a in actions if a.outcome == "failed"]
    blocked = [a for a in actions if a.outcome == "blocked"]
    done = [a for a in actions if a.outcome == "done"]
    return {
        "request_type": request_type,
        "status": "fulfilling" if failed else "completed",
        "complete": not failed,
        "has_residue": bool(blocked),
        "rows_affected": sum(a.rows_affected for a in done),
        "targets_done": [a.target for a in done],
        "targets_blocked": [a.target for a in blocked],
        "targets_failed": [a.target for a in failed],
        "residue_note": (
            "Rows naming this subject remain in insert-only stores that no runtime role may "
            "modify: the financial ledger, the audit chain and the authentication log. They are "
            "retained because the integrity of those records is itself a legal and security "
            "requirement, and erasing them is barred rather than merely unimplemented."
        ) if blocked else None,
    }
