"""The device lifecycle: paragraph 3077's enrollment, assignment, revoke and replacement.

**A device moves one way through states a person can name**, because the fleet dashboard
paragraph 3079 asks for is a list of these and an operator deciding whether to drive to a club
is reading them. The edges are the ones the sources name -- enrollment, provisioning,
activation, maintenance mode, quarantine and replacement -- and nothing else.
"""

from __future__ import annotations

from app.devices.capabilities import DeviceError

#: Where a device is. `registered` is a row with no agent behind it yet; `provisioned` has a
#: certificate and has never been brought live; `active` is in service; `maintenance` is out
#: of service on purpose and `quarantined` is out of service because something is wrong.
DEVICE_STATES: tuple[str, ...] = (
    "registered", "provisioned", "active", "maintenance", "quarantined", "retired",
)

EDGES: dict[str, tuple[str, ...]] = {
    # Provisioning is what gives it a certificate; a device cannot go live without one,
    # which is `certificates.check_may_activate`'s half of the same rule.
    "registered": ("provisioned", "retired"),
    "provisioned": ("active", "quarantined", "retired"),
    # **Maintenance is reversible and quarantine is too**, because paragraph 3080's
    # replacement workflow is a swap rather than a scrapping: the old unit is quarantined,
    # the new one enrolled, and the old one may come back from the bench.
    "active": ("maintenance", "quarantined", "retired"),
    "maintenance": ("active", "quarantined", "retired"),
    "quarantined": ("active", "maintenance", "retired"),
    # **Retirement is final.** A retired device's certificate is revoked and its commands are
    # history; bringing the same row back would make "what was driving that door in March"
    # unanswerable, and enrolling the physical unit again is a new row.
    "retired": (),
}

#: The states in which a device may be sent a command or answer one. A quarantined device is
#: deliberately not one of them -- that is what quarantine is for -- and neither is a
#: `provisioned` one, because it has not been commissioned.
OPERABLE: frozenset[str] = frozenset({"active"})


def check_state(state: str) -> None:
    if state not in DEVICE_STATES:
        raise DeviceError(f"{state!r} is not a device state")


def check_transition(before: str, after: str) -> None:
    check_state(before)
    check_state(after)
    if before == after:
        raise DeviceError(f"this device is already {before}")
    if after not in EDGES[before]:
        raise DeviceError(f"a device does not move from {before} to {after}")


def is_operable(state: str) -> bool:
    check_state(state)
    return state in OPERABLE
