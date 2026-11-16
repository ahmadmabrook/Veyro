"""Paragraph 3084: "Remote commands are scoped, signed, audited and bounded by device safety."

A Critical Control with four named properties, and each is a separate thing here:

  * **Scoped** -- a command names one device, and `check_issue` refuses an action the device's
  own declared capabilities cannot perform. A reboot sent to a receipt printer is a typo; an
  unlock sent to one is a command the vocabulary should not have accepted.
  * **Signed** -- the record carries a digest of exactly what was asked, computed here, and a
  `signature_ref` locating the signature somewhere this build cannot produce. There is no key
  vault, so the digest is what makes tampering detectable and the reference is what a gateway
  verifies; a column claiming to hold a signature this software never made would be the
  fabricated-evidence shape.
  * **Audited** -- insert-only, with the actor and the correlation on the row. MOD-008 audits
  denials rather than allowed acts and this module's role holds nothing in `iam`, so this row
  is the only record that somebody told a door to open.
  * **Bounded by device safety** -- `safety.check_command_safety`, which has no override.

**And a command expires.** A device offline when one is issued must not receive it three days
later and open a door for somebody who has long gone: an undelivered command past its deadline
is `expired` and is not delivered. That is the control the lifecycle exists for, and it is why
`ISSUE_WINDOW` is short for an actuation and longer for a diagnostic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.devices.capabilities import ACTUATING, DeviceError
from app.devices.safety import SafetyProfile, check_command_safety

#: What a remote command may ask, from paragraph 3080's "remote commands, staged rollout,
#: maintenance mode, diagnostics bundle and replacement workflow". The value is the action and
#: the capability is what a device must declare to receive it -- `None` meaning any device,
#: because every device can be told to reboot or to report.
COMMAND_ACTIONS: dict[str, str | None] = {
    #: A momentary release. **The only thing this software may do to a barrier**, and it is
    #: momentary by name: there is no `hold`, and `safety.HOLD_COMMANDS` is the list of words
    #: that are refused if somebody adds one.
    "unlock_momentary": ACTUATING,
    "reboot": None,
    "diagnostics": None,
    "sync_now": None,
    "update_firmware": None,
    "rotate_certificate": None,
    "set_maintenance": None,
    "clear_maintenance": None,
    #: Read the device's own peripheral inventory -- paragraph 3079's "peripherals".
    "report_peripherals": "telemetry",
}

#: What each action's `arguments` object may name, and nothing else. **The vocabulary
#: refusal is on the action, and a value carries anything** -- which is MOD-010's rule about
#: declared field *names*, and here the consequence is physical: a reviewer sent
#: `{"mode": "hold_open", "hold_seconds": 86400}` on an `unlock_momentary` and the row the
#: edge agent parameterises its relay from, and verifies by digest, carried hold-the-door
#: semantics that `safety.HOLD_COMMANDS` exists to make unreachable. So an undeclared key is
#: refused at the producer, exactly as MOD-010 refuses one in an event payload.
#:
#: **`unlock_momentary` takes no arguments at all.** It is momentary by name; a duration, a
#: mode or a relay selector is the whole of what a hold would need, and a door this software
#: can parameterise is a door it can hold. The same emptiness is why `reboot`, `diagnostics`,
#: `sync_now` and `report_peripherals` take none: each is a whole instruction already.
COMMAND_ARGUMENTS: dict[str, frozenset[str]] = {
    "unlock_momentary": frozenset(),
    "reboot": frozenset(),
    "diagnostics": frozenset(),
    "sync_now": frozenset(),
    "report_peripherals": frozenset(),
    "update_firmware": frozenset({"firmware_id"}),
    "rotate_certificate": frozenset({"certificate_id"}),
    #: A reason an operator types, which is why it is the one free-text argument -- and why
    #: `dev_commands.arguments` is declared in `SUBJECT_COLUMNS` as residue.
    "set_maintenance": frozenset({"reason"}),
    "clear_maintenance": frozenset(),
}

#: The longest any argument value may be. A command row is insert-only with no DELETE grant,
#: and `arguments` is `jsonb` a caller supplies: unbounded, it is a growth primitive on a
#: table nothing can clear.
MAX_ARGUMENT_LENGTH = 200


def check_arguments(action: str, arguments: dict[str, object]) -> None:
    """Refuse an argument this action does not declare, or a value out of shape."""
    check_action(action)
    allowed = COMMAND_ARGUMENTS[action]
    undeclared = sorted(set(arguments) - allowed)
    if undeclared:
        raise DeviceError(
            f"a {action} does not take {', '.join(undeclared)}; it takes "
            + (", ".join(sorted(allowed)) if allowed else "no arguments"))
    for name, value in arguments.items():
        if not isinstance(value, str):
            raise DeviceError(f"{name} is a string; a command carries no nested structure")
        if not value.strip():
            raise DeviceError(f"{name} is stated or left out, not sent blank")
        if len(value) > MAX_ARGUMENT_LENGTH:
            raise DeviceError(
                f"{name} is at most {MAX_ARGUMENT_LENGTH} characters; a command row is "
                f"insert-only and nothing clears it")


#: Where a command is. `issued` is written and not yet handed over; `delivered` means the
#: gateway has it; `acknowledged` means the device has it; then it completes, fails or expires.
COMMAND_STATES: tuple[str, ...] = (
    "issued", "delivered", "acknowledged", "completed", "failed", "expired",
)

EDGES: dict[str, tuple[str, ...]] = {
    "issued": ("delivered", "expired", "failed"),
    "delivered": ("acknowledged", "failed", "expired"),
    # **An acknowledged command cannot expire.** The device has it; whether it worked is the
    # device's to report, and timing it out here would record "expired" for an unlock that
    # opened the door.
    "acknowledged": ("completed", "failed"),
    "completed": (),
    "failed": (),
    "expired": (),
}

#: How long a command stays deliverable. **A minute for an actuation**, because a door opened
#: a minute after somebody asked is a door opened for whoever is standing there now; an hour
#: for everything else, which is long enough for a gateway on a bad link to collect a firmware
#: instruction and short enough that a stale one does not fire after a shift change.
ISSUE_WINDOW: dict[str, timedelta] = {
    "unlock_momentary": timedelta(seconds=60),
}
DEFAULT_ISSUE_WINDOW = timedelta(hours=1)

#: The longest a caller may ask for. Bounded because `expires_at` is otherwise a caller-chosen
#: deadline on a command that opens a door.
MAX_ISSUE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Command:
    """One command's facts, as the decisions need them."""

    action: str
    state: str
    issued_at: datetime
    expires_at: datetime


def check_action(action: str) -> None:
    if action not in COMMAND_ACTIONS:
        raise DeviceError(
            f"{action!r} is not a device command; this software can ask for "
            f"{', '.join(sorted(COMMAND_ACTIONS))}")


def window_for(action: str) -> timedelta:
    check_action(action)
    return ISSUE_WINDOW.get(action, DEFAULT_ISSUE_WINDOW)


def requested_window(action: str, expires_in: timedelta | None) -> timedelta:
    """The window this request asks for, bounded, with no device read.

    It exists so a repeat can be compared against what was stored without first resolving
    the device: `issue_command` needs the requested window *before* it knows whether this
    is a new command or a retry of one. `check_issue` returns the same value for the same
    input, which is what makes the comparison meaningful.
    """
    check_action(action)
    window = window_for(action) if expires_in is None else expires_in
    if window <= timedelta(0):
        raise DeviceError("a command's window is a positive length of time")
    ceiling = ISSUE_WINDOW.get(action, MAX_ISSUE_WINDOW)
    if window > ceiling:
        raise DeviceError(
            f"a {action} is deliverable for at most {int(ceiling.total_seconds())} seconds")
    return window


def check_issue(
    action: str, *, declared: frozenset[str], state: str,
    profile: SafetyProfile | None, arguments: dict[str, object],
    expires_in: timedelta | None = None,
) -> timedelta:
    """Refuse a command this device cannot perform, is not live for, or must not be sent.

    Returns the window the command is deliverable for, so the caller cannot check one deadline
    and store another.

    **Safety first, before the capability and the state.** A `lock_down` sent to a retired
    scanner is refused for being a lock-down rather than for being sent to a scanner: the
    message somebody reads has to name the reason that matters, and a reviewer probing the
    safety rule must not be told about a state instead.
    """
    check_command_safety(action, profile=profile)
    check_action(action)
    check_arguments(action, arguments)
    needs = COMMAND_ACTIONS[action]
    if needs is not None and needs not in declared:
        raise DeviceError(
            f"this device does not declare {needs}, so it cannot be asked to {action}")
    if state != "active":
        raise DeviceError(
            f"this device is {state}; a command goes to a device in service")
    if needs == ACTUATING and profile is None:
        raise DeviceError(
            "an access point is commissioned with a hardware safety profile before anything "
            "tells it to open")
    # **`is None`, not `or`.** A zero timedelta is falsy, so `expires_in or default`
    # silently replaced a caller's zero with the default window instead of refusing it --
    # which meant the bound below could never fire on the one value somebody would send by
    # accident. Found by the test that was written to prove the bound.
    window = window_for(action) if expires_in is None else expires_in
    if window <= timedelta(0):
        raise DeviceError("a command is deliverable for some length of time")
    if window > MAX_ISSUE_WINDOW:
        raise DeviceError("a command is deliverable for at most a day")
    if action == "unlock_momentary" and window > ISSUE_WINDOW[action]:
        raise DeviceError(
            "an unlock is deliverable for at most a minute; longer is a door opened for "
            "whoever is standing there when it arrives")
    return window


def check_transition(before: str, after: str) -> None:
    for state in (before, after):
        if state not in COMMAND_STATES:
            raise DeviceError(f"{state!r} is not a command state")
    if after not in EDGES[before]:
        raise DeviceError(f"a command does not move from {before} to {after}")


def has_expired(command: Command, *, at: datetime) -> bool:
    """Whether this command is past its deadline and must not be delivered.

    An `acknowledged` command is never expired by the clock -- the device has it, and what
    happened is the device's to report.
    """
    if command.state not in ("issued", "delivered"):
        return False
    return at >= command.expires_at


def may_deliver(command: Command, *, at: datetime) -> None:
    """Refuse to hand over a command whose moment has passed."""
    if command.state != "issued":
        raise DeviceError(f"this command is {command.state} and is not waiting to be sent")
    if has_expired(command, at=at):
        raise DeviceError(
            "this command expired before the device collected it; issue another if it is "
            "still wanted")


def digest(
    *, device_id: str, action: str, arguments: dict[str, object], issued_at: datetime,
    expires_at: datetime,
) -> str:
    """A digest of exactly what was asked, which is the "signed" half this build can do.

    **Sorted keys and an explicit instant format**, so the same command digests the same way
    twice: a digest that depended on dict ordering would make tamper detection depend on the
    Python version. The signature itself belongs to whatever holds the key, which is not this
    build -- `signature_ref` is where that lands, and it is a locator rather than a signature
    for MOD-012's reason.
    """
    payload = json.dumps(
        {"device_id": device_id, "action": action, "arguments": arguments,
         "issued_at": issued_at.isoformat(), "expires_at": expires_at.isoformat()},
        sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
