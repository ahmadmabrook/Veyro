"""The canonical capability vocabulary: what this software can ask a device to do.

**Code-resident, like MOD-008's permissions and MOD-010's event types, and for the same
reason.** Paragraph 3086's required outcome is that "hardware vendors can change without
rewriting gym workflows", which only holds if the *workflow* names a capability rather than a
vendor: a turnstile and a biometric terminal both read a credential, and a gym's check-in flow
asks for `credential.read` without knowing which it got. A per-tenant capability table would
let two tenants disagree about what `access.actuate` means, with only the code able to settle
it -- and a command bounded by a capability nobody can define consistently is not bounded.

**Seven, from paragraph 3075**, which names them: "credential read, access actuation, biometric
match, scan, print, payment and telemetry". Not an open set: a capability this software cannot
drive is a capability a tenant should not be able to declare, because declaring it would make a
device look able to do something no command here can ask for.
"""

from __future__ import annotations

from app.errors import InvalidRequest


class DeviceError(ValueError):
    """A device decision refused. `ValueError` so a service maps it like every sibling."""


#: Paragraph 3075's seven. The value is what a device type declares and what a command names;
#: the prose is what a fleet dashboard shows somebody who has to replace one.
CAPABILITIES: dict[str, str] = {
    "credential.read": "read a member credential presented at the device",
    "access.actuate": "release or hold a door, turnstile or barrier",
    "biometric.match": "match a presented biometric against an enrolled template",
    "scan": "scan a barcode, QR code or document",
    "print": "print a receipt, label or wristband",
    "payment": "take a card or contactless payment at the device",
    "telemetry": "report its own health, counters and peripherals",
}

#: The capability that can move a physical barrier, named once because three modules check it:
#: a command that actuates has to clear the safety profile, a device that actuates has to be
#: commissioned, and a snapshot that authorizes one has to be inside its TTL.
ACTUATING = "access.actuate"

#: The capabilities whose *input* is a person. A device declaring one of these is a device
#: whose telemetry and command history can identify somebody, which is why
#: `app/privacy/classification.py` declares the registry's subject columns and why a
#: diagnostics bundle is not a free read.
PERSONAL: frozenset[str] = frozenset({"credential.read", "biometric.match"})

#: The kinds of device ECO-03 names in paragraph 3073, plus the gateway the edge agent runs on.
#: A kind is what somebody buys; the capabilities are what it can do, and the two are separate
#: because one model of turnstile reads a credential and another is driven by a reader beside
#: it.
DEVICE_KINDS: tuple[str, ...] = (
    "turnstile",
    "door_controller",
    "biometric_terminal",
    "scanner",
    "kiosk",
    "pos",
    "equipment",
    "gateway",
)


def check_capability(name: str) -> None:
    """Refuse a capability this software cannot ask for."""
    if name not in CAPABILITIES:
        raise DeviceError(
            f"{name!r} is not a device capability; this software can ask for "
            f"{', '.join(sorted(CAPABILITIES))}")


def check_kind(kind: str) -> None:
    if kind not in DEVICE_KINDS:
        raise DeviceError(f"{kind!r} is not a kind of device")


def check_declared(kind: str, declared: frozenset[str]) -> None:
    """Refuse a device type whose declared capabilities do not make sense for what it is.

    **A gateway actuates nothing.** The edge agent runs on it and the agent drives the devices
    beside it; a gateway that declared `access.actuate` would be a door with no door, and the
    safety profile -- which is commissioned per *access point* -- would have nothing physical
    to describe. The other kinds are deliberately unconstrained: a kiosk that takes payment and
    prints a wristband is ordinary, and guessing which combinations a vendor sells is how a
    registry refuses real hardware.
    """
    check_kind(kind)
    if not declared:
        raise DeviceError("a device type declares at least one capability")
    for name in sorted(declared):
        check_capability(name)
    if kind == "gateway" and ACTUATING in declared:
        raise DeviceError(
            "a gateway runs the edge agent and drives the devices beside it; it is not "
            "itself a door")


#: What a caller-supplied `jsonb` object may be. **Both of them are insert-only or
#: tenant-written and neither has a DELETE grant**, so an unbounded object is a growth
#: primitive on a table nothing can clear -- a reviewer put 400 KB into each on a routine
#: permission. The bound is deliberately small: a peripheral inventory and a device config
#: are a handful of short facts, not a document.
MAX_OBJECT_KEYS = 64
MAX_OBJECT_VALUE = 500


def check_small_object(value: dict[str, object], what: str) -> None:
    """Refuse a caller-supplied object too large or too deep to belong in a column."""
    if len(value) > MAX_OBJECT_KEYS:
        raise DeviceError(
            f"{what} carries at most {MAX_OBJECT_KEYS} entries; this is a record of facts, "
            f"not a document")
    for name, item in value.items():
        if not isinstance(name, str) or not name.strip():
            raise DeviceError(f"every name in {what} is a non-blank string")
        if len(name) > 120:
            raise DeviceError(f"a name in {what} is at most 120 characters")
        if not isinstance(item, str | int | float | bool) or isinstance(item, bool) is None:
            raise DeviceError(
                f"{what} carries flat values; nothing nested, because nothing reads it")
        if isinstance(item, str) and len(item) > MAX_OBJECT_VALUE:
            raise DeviceError(
                f"a value in {what} is at most {MAX_OBJECT_VALUE} characters")


def require_name(value: str, what: str) -> str:
    """A non-blank identifier, trimmed. `InvalidRequest` because this is input shape."""
    trimmed = value.strip()
    if not trimmed:
        raise InvalidRequest(f"{what}_cannot_be_blank")
    return trimmed
