"""MOD-008 IAM-03-R05: approval policies, and the separation of duties that makes them mean
something.

Pure functions over rows the caller has read.

An approval requirement that the requester can satisfy is not an approval requirement, so
separation of duties is enforced here rather than left to the surface. The database carries the
other half -- `UNIQUE (tenant_id, request_id, decided_by)` -- so "two approvals" cannot be one
person pressing a button twice even if this module were bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
EXPIRED = "expired"
WITHDRAWN = "withdrawn"


class ApprovalError(ValueError):
    """A decision that cannot be recorded. `code` is stable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ApprovalPolicy:
    action: str
    threshold_minor: int = 0
    required_permissions: frozenset[str] = frozenset()
    """**All** of them, not one of them. A single column had to choose between two policies
    naming different permissions at the same strictness, and every rule for choosing -- row
    order, or a sort -- is arbitrary and weaker than one of the two policies."""
    required_approvals: int = 1
    separation_of_duties: bool = True


@dataclass(frozen=True)
class Decision:
    decided_by: str
    decision: str


def policy_for(
    policies: list[ApprovalPolicy], action: str, amount_minor: int | None
) -> ApprovalPolicy | None:
    """The terms that apply: the **strictest of every applicable policy**, combined.

    Thresholds overlap on purpose -- refunds over 100 need one approval, over 10000 need two --
    so every policy the amount clears applies, and what governs is the hardest requirement among
    them: the most approvals any of them asks for, and separation of duties if any of them
    demands it.

    An earlier version took the policy with the highest threshold, which a docstring called "the
    strictest". Those are the same only until somebody writes a lenient policy above a strict one
    -- a review demonstrated a `threshold_minor = 1` policy with one approval and no separation of
    duties silently governing a million-unit refund that a `threshold_minor = 0` policy had
    required two signatures for. Combining rather than choosing removes the possibility instead
    of relying on nobody writing that row.
    """
    amount = amount_minor or 0
    applicable = [p for p in policies if p.action == action and amount >= p.threshold_minor]
    if not applicable:
        return None
    return ApprovalPolicy(
        action=action,
        threshold_minor=max(p.threshold_minor for p in applicable),
        # The union, so the result does not depend on which policy happened to come first. An
        # earlier version took this field from whichever policy had the most approvals, which on
        # a tie meant row order -- the exact dependence combining was meant to remove, surviving
        # in one field.
        required_permissions=frozenset().union(*(p.required_permissions for p in applicable)),
        required_approvals=max(p.required_approvals for p in applicable),
        separation_of_duties=any(p.separation_of_duties for p in applicable),
    )


def requires_approval(
    policies: list[ApprovalPolicy], action: str, amount_minor: int | None
) -> bool:
    return policy_for(policies, action, amount_minor) is not None


def check_decider(
    policy: ApprovalPolicy, *, requested_by: str, decided_by: str,
    decider_permissions: frozenset[str],
) -> None:
    """Whether this person may decide this request. Raises rather than returning False.

    Two conditions, both of which have been quietly dropped in real systems: the decider holds
    **every** permission the applicable policies name, and -- when separation of duties applies --
    the decider is not the requester. The second is the one that turns an approval queue into a
    formality.
    """
    missing = policy.required_permissions - decider_permissions
    if missing:
        raise ApprovalError("decider_lacks_permission",
                            "the decider does not hold every permission these policies require")
    if policy.separation_of_duties and decided_by == requested_by:
        raise ApprovalError("separation_of_duties",
                            "the requester may not decide their own request")


def resolve(
    *,
    required_approvals: int,
    decisions: list[Decision],
    expires_at: datetime,
    now: datetime,
) -> str:
    """The state a request is in, given the decisions recorded against it.

    A single rejection settles it: requiring two approvals and treating one rejection as a tie to
    be broken would mean a request could be approved over a recorded objection. Expiry is checked
    before approval so that a request which ran out of time does not become approved by a late
    decision.
    """
    if any(d.decision == REJECTED for d in decisions):
        return REJECTED
    if expires_at <= now:
        return EXPIRED
    approvals = {d.decided_by for d in decisions if d.decision == APPROVED}
    if len(approvals) >= required_approvals:
        return APPROVED
    return PENDING
