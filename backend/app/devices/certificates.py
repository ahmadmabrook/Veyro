"""Paragraph 3083: "Devices authenticate with rotating certificates; default credentials are
forbidden." A Critical Control, and both halves are here.

**No column anywhere holds a private key, and there is no type one could be stored in.** A
certificate record carries a fingerprint, the window it is valid for, and a `vault_ref`
locating the material somewhere this build cannot read -- MOD-012's shape, for MOD-012's
reason: there is no key vault here, so the honest table is one that *cannot* hold a key rather
than one that holds it carefully. The migration pins the column list for exactly this, because
the control is an absence and an absence is what a later migration adds back.

**Rotation overlaps.** A device that had its certificate replaced at the instant the new one
was issued would be locked out for as long as it took to receive the new one, which for a
gateway on a flaky link is long enough to shut a club. So the outgoing certificate stays valid
until its own expiry and is marked superseded; what rotation changes is which one is *current*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.devices.capabilities import DeviceError

#: Where a certificate is. `pending` exists because issuing one is an act somebody records
#: before the device has it; `active` is in use; `superseded` was rotated out and is still
#: honoured until it expires; `revoked` is refused from the moment it is written.
CERTIFICATE_STATES: tuple[str, ...] = ("pending", "active", "superseded", "revoked")

#: The longest a device certificate may be valid for. **A year**, because paragraph 3083's
#: word is "rotating" and a certificate valid for a decade is not rotating -- and because the
#: revocation path is the only way to withdraw one early, which means a long life is a long
#: window in which a stolen gateway keeps working.
MAX_LIFETIME = timedelta(days=366)

#: The shortest. A certificate valid for an hour is one a device on a slow link cannot finish
#: installing, which is the same outage rotation exists to avoid.
MIN_LIFETIME = timedelta(hours=24)

#: How long before expiry a certificate is due for rotation. A quarter of its life, so a
#: year-long certificate is announced three months out and a day-long one six hours out
#: rather than both getting the same fixed warning.
ROTATION_FRACTION = 0.25

#: The shortest repeating block a placeholder fingerprint is built from. **This replaced a
#: list of exact strings, which was the wrong shape entirely**: the list held
#: `deadbeef` repeated to 32 characters, and a reviewer's `DE:AD:BE:EF:` repeated eight times
#: normalises to 64 -- the same placeholder at a different length, and it walked straight
#: through. A vendor default is not a particular string, it is a *pattern somebody typed*, so
#: what is checked is whether the whole fingerprint is one short block repeated.
MAX_PLACEHOLDER_PERIOD = 16


def _is_a_repeated_block(folded: str) -> bool:
    """Whether this fingerprint is one short block typed over and over.

    A real digest has no short period -- the probability that a SHA-256 output is, say,
    `abcd` repeated sixteen times is nil -- so a value with one is a placeholder whatever
    block somebody chose. That catches `00...`, `ff...`, `deadbeef...` and the next one
    nobody thought of, at any length, which an exact list cannot.
    """
    for period in range(1, min(MAX_PLACEHOLDER_PERIOD, len(folded) // 2) + 1):
        if len(folded) % period:
            continue
        if folded == folded[:period] * (len(folded) // period):
            return True
    return False


#: And the words somebody types instead of a digest. These never reach
#: `_is_a_repeated_block` because `normalise_fingerprint` requires hexadecimal, so they are
#: here for the message rather than for the check.
FORBIDDEN_FINGERPRINTS: frozenset[str] = frozenset({
    "default", "changeme", "insecure", "testkey", "vendordefault",
})


@dataclass(frozen=True)
class Certificate:
    """One certificate's facts, as a decision needs them."""

    fingerprint: str
    state: str
    not_before: datetime
    not_after: datetime


def normalise_fingerprint(value: str) -> str:
    """Lowercase, with separators removed, which is how a fingerprint is compared.

    **Normalised before it is checked against the forbidden list**, because the vendor default
    a reviewer would paste is `DE:AD:BE:EF:...` and a list of bare hex would miss it. The same
    normalisation is what the unique index sees, so two spellings of one fingerprint cannot be
    two rows.
    """
    folded = value.strip().lower().replace(":", "").replace("-", "").replace(" ", "")
    if not folded:
        raise DeviceError("a certificate has a fingerprint")
    if len(folded) < 32:
        raise DeviceError(
            "a certificate fingerprint is at least 32 characters; a shorter one is not a "
            "digest of anything")
    if len(folded) > 128:
        raise DeviceError("a certificate fingerprint is at most 128 characters")
    if any(c not in "0123456789abcdef" for c in folded):
        raise DeviceError("a certificate fingerprint is hexadecimal")
    return folded


def check_issue(
    fingerprint: str, *, not_before: datetime, not_after: datetime,
) -> str:
    """Refuse a certificate that is a default, or whose window is not a rotation.

    Returns the normalised fingerprint, so a caller cannot check one spelling and store
    another -- which is the derive-don't-accept shape five modules of this build have paid for.
    """
    folded = normalise_fingerprint(fingerprint)
    if folded in FORBIDDEN_FINGERPRINTS or _is_a_repeated_block(folded):
        raise DeviceError(
            "this is a vendor default credential, and a device that authenticates with one "
            "authenticates as every other unit of its model")
    if not_after <= not_before:
        raise DeviceError("a certificate expires after it begins")
    life = not_after - not_before
    if life < MIN_LIFETIME:
        raise DeviceError(
            "a certificate valid for less than a day is one a device on a slow link cannot "
            "finish installing")
    if life > MAX_LIFETIME:
        raise DeviceError(
            "a certificate is valid for at most a year; paragraph 3083's word is rotating")
    return folded


def is_usable(certificate: Certificate, *, at: datetime) -> bool:
    """Whether a device presenting this certificate authenticates, as of now.

    `superseded` is still usable until it expires, which is the overlap rotation needs.
    `revoked` never is, from the moment it is written -- that is the difference between the
    two and the reason both states exist.
    """
    if certificate.state not in ("active", "superseded"):
        return False
    return certificate.not_before <= at < certificate.not_after


def due_for_rotation(certificate: Certificate, *, at: datetime) -> bool:
    """Whether this certificate is inside its rotation window."""
    if certificate.state != "active":
        return False
    life = certificate.not_after - certificate.not_before
    return at >= certificate.not_after - life * ROTATION_FRACTION


def check_may_activate(certificates: list[Certificate], *, at: datetime) -> None:
    """Refuse to bring a device live with no usable certificate.

    The other half of `safety.may_go_live`: that one asks whether the *door* is safe and this
    asks whether the *device* can prove who it is. A device live with no certificate is one
    whose commands nothing authenticates, which is paragraph 3083 with the word "rotating"
    removed.
    """
    if not any(is_usable(c, at=at) for c in certificates):
        raise DeviceError(
            "this device has no usable certificate; a device authenticates before it "
            "operates")
