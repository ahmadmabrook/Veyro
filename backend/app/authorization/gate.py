"""MOD-008: the one place that answers "may this session do this".

The review that approved MOD-007 named the shape that produced every blocking defect in it: a
capability granted in one place and bounded in another. Its closing note was that the capability
test was still written out by hand at two call sites, and that **a third hand-written copy is
where that pattern restarts** -- so authorization gets one function rather than a condition at
each surface.

`may` combines the two questions that have to be asked together and have no useful answer apart:

* **Is the caller authorized?** `app.authorization.decision.authorize`, default deny.
* **Is the session strong enough?** `app.identity.policy`, by the permission's action class.

Asking only the first lets a password-only session move money. Asking only the second lets anyone
with a second factor do anything. Asking them in two different places is how they drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.authorization import decision as authz
from app.authorization.catalog import CatalogError, action_class
from app.identity import policy as assurance


@dataclass(frozen=True)
class Gate:
    allowed: bool
    reason: str
    """`default_deny`, `unknown_action`, `step_up_required`, `unreachable_assurance`,
    `role:<key>` or `policy:<key>`."""
    step_up_required: bool = False
    required_action_class: str | None = None
    required_aal: int | None = None
    reachable: bool = True
    """False when the required level cannot be reached in this build at all -- a privileged
    action needs a hardware authenticator and MOD-007 cannot verify one."""
    masked_fields: tuple[str, ...] = ()
    decision: authz.Decision | None = None


def may(
    *,
    session_aal: int,
    request: authz.Request,
    assignments: list[authz.Assignment],
    policies: list[authz.Policy],
    now: datetime,
) -> Gate:
    """The single gate. Authorization first, then assurance.

    The action comes from `request` alone. An earlier signature took it twice -- as `action` and
    as `request.action` -- which agreed only because one constructor built both. One fact in two
    places is the shape that produced every defect the MOD-007 review found, so it is one
    parameter now, before a second constructor exists to disagree.

    Authorization is checked before assurance on purpose: a caller who is not authorized at all
    should be told that, not sent to step up for an action they would still be denied afterwards.
    Stepping up would also cost them a recovery code for nothing.
    """
    action = request.action
    decided = authz.authorize(request, assignments, policies, now=now)
    if not decided.allowed:
        return Gate(allowed=False, reason=decided.reason, decision=decided)

    try:
        needed_class = action_class(action)
        needed_aal = assurance.required_aal(needed_class)
    except (CatalogError, assurance.PolicyError):
        return Gate(allowed=False, reason="unknown_action", decision=decided)

    reachable = needed_aal <= assurance.assurance_for(["password", "recovery_code"])
    if session_aal < needed_aal:
        return Gate(
            allowed=False,
            reason="unreachable_assurance" if not reachable else "step_up_required",
            step_up_required=True, required_action_class=needed_class,
            required_aal=needed_aal, reachable=reachable, decision=decided,
        )
    return Gate(allowed=True, reason=decided.reason, required_action_class=needed_class,
                required_aal=needed_aal, reachable=reachable,
                masked_fields=decided.masked_fields, decision=decided)
