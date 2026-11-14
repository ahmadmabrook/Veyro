"""MOD-012 ECO-02: the connector lifecycle, decided without touching the database.

Paragraph 3025 names it: install, authorize, configure, validate, activate, monitor, rotate and
uninstall. Two small machines rather than one large one, because an install and a connection
genuinely move independently -- a tenant can hold an install with three connections, revoke one
and keep the others, and an install disabled for a billing reason is not the same thing as a
connection whose credential was revoked by the provider.

**`validated` means somebody recorded a validation, not that this build performed one.** There is
no provider in this repository, so nothing here can call one and see that it answers. The state
therefore carries an actor and a written piece of evidence, and the row says what it is: a claim
made by a named party at a time. A state that read as "verified" while nothing verified anything
is the fabricated-evidence shape MOD-011's synthetic results were built to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: An install: the tenant's decision to use a definition.
INSTALL_STATES = ("installed", "active", "disabled", "uninstalled")

#: A connection: one authorized link from an install to a provider account.
CONNECTION_STATES = ("pending", "authorized", "validated", "revoked")

_INSTALL_EDGES: dict[str, tuple[str, ...]] = {
    "installed": ("active", "uninstalled"),
    # Disabling and re-activating is the ordinary operational pair, so it goes both ways.
    "active": ("disabled", "uninstalled"),
    "disabled": ("active", "uninstalled"),
    # Terminal. An uninstall releases the tenant's data from the provider's reach, and a state
    # that could come back from it would mean an integration somebody removed is one a later
    # command can revive -- with the scopes it used to hold.
    "uninstalled": (),
}

_CONNECTION_EDGES: dict[str, tuple[str, ...]] = {
    "pending": ("authorized", "revoked"),
    "authorized": ("validated", "revoked"),
    # Re-validation is a transition to itself: a connection validated a year ago and a
    # connection validated this morning are different facts, and the second is worth recording.
    "validated": ("validated", "revoked"),
    "revoked": (),
}


class LifecycleError(ValueError):
    """A transition this module does not admit."""


def check_install_transition(current: str, target: str) -> None:
    if current not in _INSTALL_EDGES:
        raise LifecycleError(f"unknown_install_state_{current}")
    if target not in _INSTALL_EDGES[current]:
        raise LifecycleError(f"an_install_cannot_go_from_{current}_to_{target}")


def check_connection_transition(current: str, target: str) -> None:
    if current not in _CONNECTION_EDGES:
        raise LifecycleError(f"unknown_connection_state_{current}")
    if target not in _CONNECTION_EDGES[current]:
        raise LifecycleError(f"a_connection_cannot_go_from_{current}_to_{target}")


@dataclass(frozen=True)
class ActivationCheck:
    """What an install needs before it may carry traffic."""

    criticality: str
    has_fallback: bool
    has_reconciliation: bool
    has_exit_plan: bool
    validated_connections: int


def check_activation(check: ActivationCheck) -> None:
    """Paragraph 3033: a critical integration needs a fallback, reconciliation and an exit plan.

    **Enforced at activation rather than at install**, which is the only point where it bites:
    refusing the install would stop somebody exploring an integration before they have written
    an exit plan for it, and refusing at activation is the moment it starts carrying traffic
    the tenant will come to depend on. Written per install rather than per definition, because
    the fallback for a payment provider depends on what else that tenant has.

    An install with no validated connection is refused whatever its criticality: an active
    integration that cannot reach the provider is one whose failures read as the provider's.
    """
    if check.validated_connections < 1:
        raise LifecycleError("an_install_needs_a_validated_connection_to_activate")
    if check.criticality != "critical":
        return
    missing = [
        name for name, present in (
            ("fallback", check.has_fallback),
            ("reconciliation", check.has_reconciliation),
            ("exit_plan", check.has_exit_plan),
        ) if not present
    ]
    if missing:
        raise LifecycleError(
            "a critical integration cannot be activated without " + ", ".join(missing)
        )


#: How long before a credential expires somebody should be told. Two weeks is long enough to
#: raise a ticket with a provider whose rotation needs a human, and short enough that the
#: reminder is still about this credential rather than noise.
ROTATION_LEAD = timedelta(days=14)


@dataclass(frozen=True)
class RotationVerdict:
    due: bool
    expired: bool
    days_remaining: int | None
    """None when the credential reference declares no expiry."""


def rotation_due(
    *, expires_at: datetime | None, now: datetime, lead: timedelta = ROTATION_LEAD,
) -> RotationVerdict:
    """Paragraph 3027's rotation reminder, as a decision rather than a schedule.

    A credential with no declared expiry is **not** due: this build cannot see the provider's
    own policy, and inventing an expiry would produce a reminder about a date nobody set. The
    gap is that such a credential is never reminded about at all, which is a true statement
    about what is known rather than a guess dressed as one.

    Nothing calls this on a schedule. That is the same missing worker runtime MOD-007, MOD-009,
    MOD-010 and MOD-011 each name, and here it means `credential.expiring` is published when
    somebody asks rather than when the lead window opens.
    """
    if expires_at is None:
        return RotationVerdict(due=False, expired=False, days_remaining=None)
    remaining = expires_at - now
    return RotationVerdict(
        due=remaining <= lead,
        expired=remaining <= timedelta(0),
        days_remaining=remaining.days,
    )
