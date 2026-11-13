"""MOD-015 PLT-03-R02/R05: the subscription lifecycle and what a plan change is allowed to do.

Pure functions. The service persists what these admit, so there is one transition table in the
codebase rather than one per call site.

**The transitions here are better grounded than MOD-004's were, and the difference is worth
stating.** `app.tenancy.domain.lifecycle` records that no source gives a tenant transition order
at all, so every edge it admits is the author's reading. PLT-03-R05 names its own verbs --
"trial conversion, dunning, grace periods, suspension, **reactivation** and offboarding
coordination" -- so each edge below answers to a named capability. What is still a reading is the
*shape*: that dunning is a `past_due` state rather than a flag, and that grace expiry is what
moves a subscription to `suspended`. A baseline that states otherwise changes `_EDGES` and
nothing else.

Reactivation lives here by the sources' own placement. MOD-004's tenant lifecycle deliberately
has no `suspended -> active` edge and says so: TSD section 10.3 is PLT-03, and this is it.

`cancelled` is terminal. What happens afterwards -- export, retention, erasure -- is LIF-03's
work, and inventing an edge out of it here would put a second, disagreeing lifecycle in the
product.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

TRIALING = "trialing"
ACTIVE = "active"
PAST_DUE = "past_due"
SUSPENDED = "suspended"
CANCELLED = "cancelled"

STATES = (TRIALING, ACTIVE, PAST_DUE, SUSPENDED, CANCELLED)

CONVERT = "convert"
PAYMENT_FAILED = "payment_failed"
PAYMENT_RECOVERED = "payment_recovered"
GRACE_EXPIRED = "grace_expired"
REACTIVATE = "reactivate"
CANCEL = "cancel"

_EDGES: dict[tuple[str, str], str] = {
    (TRIALING, CONVERT): ACTIVE,
    (TRIALING, CANCEL): CANCELLED,
    (ACTIVE, PAYMENT_FAILED): PAST_DUE,
    (ACTIVE, CANCEL): CANCELLED,
    (PAST_DUE, PAYMENT_RECOVERED): ACTIVE,
    (PAST_DUE, GRACE_EXPIRED): SUSPENDED,
    (PAST_DUE, CANCEL): CANCELLED,
    (SUSPENDED, REACTIVATE): ACTIVE,
    (SUSPENDED, CANCEL): CANCELLED,
}


class LifecycleError(ValueError):
    """A command was issued from a state that does not admit it. `code` is stable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def apply_command(current_status: str, command: str) -> str:
    """The status after `command`, or raise. Unknown states and commands fail closed."""
    if current_status not in STATES:
        raise LifecycleError("unknown_state", f"{current_status!r} is not a subscription state")
    if command not in {c for _, c in _EDGES}:
        raise LifecycleError("unknown_command", f"{command!r} is not a subscription command")
    try:
        return _EDGES[(current_status, command)]
    except KeyError:
        raise LifecycleError(
            "illegal_transition", f"{command} is not admitted from {current_status}"
        ) from None


def admitted_commands(current_status: str) -> list[str]:
    """What a surface may offer from here, so a console need not hard-code the table."""
    return sorted(command for state, command in _EDGES if state == current_status)


def is_billable(status: str) -> bool:
    """Whether a period in this status produces a charge.

    A trial does not, by definition. A suspended subscription does not: suspension exists to stop
    the service, and billing for a service that was withheld is the kind of charge that ends in a
    chargeback. `past_due` does bill -- the service is still running and the debt is the point.
    """
    return status in (ACTIVE, PAST_DUE)


# --------------------------------------------------------------------------- plan changes

@dataclass(frozen=True)
class EntitlementLimit:
    feature_code: str
    limit_value: int | None
    unlimited: bool = False

    def permits(self, quantity: int) -> bool:
        return self.unlimited or (self.limit_value is not None and quantity <= self.limit_value)


@dataclass(frozen=True)
class Breach:
    feature_code: str
    in_use: int
    new_limit: int


def entitlement_breaches(
    in_use: dict[str, int], new_limits: list[EntitlementLimit]
) -> list[Breach]:
    """Which features a plan change would put over their new limit.

    PLT-03's second critical control is that "a plan change may never silently remove
    operationally critical tenant data". The word doing the work is *silently*: a tenant with
    eight locations may move to a five-location plan, but nothing in this module may decide on
    their behalf which three locations stop existing. So a downgrade that breaches a limit is
    reported here, the service refuses it unless the caller acknowledges the list, and no row
    outside this module is ever touched either way.

    A feature in use but absent from the new plan is a breach with a limit of zero -- losing a
    capability entirely is a larger change than having less of it, not a smaller one.
    """
    limits = {limit.feature_code: limit for limit in new_limits}
    breaches = []
    for feature_code, quantity in sorted(in_use.items()):
        limit = limits.get(feature_code)
        if limit is None:
            if quantity > 0:
                breaches.append(Breach(feature_code, quantity, 0))
        elif not limit.permits(quantity):
            assert limit.limit_value is not None  # permits() is True whenever unlimited
            breaches.append(Breach(feature_code, quantity, limit.limit_value))
    return breaches


def change_kind(old_price_minor: int, new_price_minor: int) -> str:
    """An upgrade costs more, a downgrade less, and a same-price move is neither.

    Moving between two plans that cost the same -- a different region, a different feature mix --
    is recorded as `change`. Calling it an upgrade would put a word in the history that the
    numbers do not support, and the history is what someone reads a year later.
    """
    if new_price_minor > old_price_minor:
        return "upgrade"
    if new_price_minor < old_price_minor:
        return "downgrade"
    return "change"


def next_period(period_start: date, period_end: date) -> tuple[date, date]:
    """Roll a billing period forward by its own length.

    Keeping the length rather than adding a calendar month is what makes renewals total: a
    subscription starting on the 31st has no 31st to land on in the following month, and every
    rule for picking a substitute day either drifts or needs a special case. The length is
    already a number the period carries.
    """
    span = period_end - period_start
    if span <= timedelta(0):
        raise LifecycleError("bad_period", "period must end after it starts")
    return period_end, period_end + span
