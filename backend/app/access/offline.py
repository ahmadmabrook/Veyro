"""Bounded offline operation, degraded mode, and what reconciliation may and may not do.

Paragraph 1947's required outcome is that "the club continues operating during temporary
connectivity loss", and paragraph 1955 bounds it: "Use bounded signed offline policy snapshot;
deny when snapshot/clock/credential is outside risk bounds; egress/emergency safety remains
hardware-controlled."

**The deny is the part that is easy to lose.** An offline door that falls back to letting
everybody in is a club that operates during an outage in the sense that nothing stops anybody,
and a door that falls back to letting nobody in is a club that does not operate at all. The
rule here is the middle one the paragraph actually states: a snapshot inside its bounds is
honoured, and outside them the answer is a refusal with a reason somebody can act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.access.credentials import MAX_DEVICE_CLOCK_SKEW
from app.access.zones import AccessError, snapshot_ceiling

#: How a device is running. `supervised` is paragraph 4162's: the clock is too far out to
#: trust a rotating credential, so a human is in the loop until it is fixed.
MODES: tuple[str, ...] = ("online", "offline", "supervised")

#: Paragraph 4160: an online device requests deltas at least every five minutes, and
#: immediately on a pushed revocation epoch. Past this without a sync, a device that believes
#: it is online is wrong about it.
SYNC_INTERVAL = timedelta(minutes=5)

#: What a reconciled offline batch may be. **Nothing here rewrites**: paragraph 4168 says
#: reconnect reconciliation deduplicates and flags policy conflicts "rather than rewriting
#: history", so a conflicting decision is recorded beside the original, never over it.
OUTCOMES: tuple[str, ...] = ("accepted", "duplicate", "policy_conflict", "stale_snapshot")


@dataclass(frozen=True)
class Posture:
    """What a device's own situation allows it to decide."""

    mode: str
    snapshot_issued_at: datetime | None
    snapshot_expires_at: datetime | None
    snapshot_epoch: int | None
    device_epoch: int
    clock_skew: timedelta
    #: Which snapshot, so the decision can cite it. Paragraph 1952: "decision references
    #: exact snapshot/policy version", and a decision that names the policy and not the
    #: snapshot is half a citation on the half that was offline.
    snapshot_id: str | None = None


def check_mode(mode: str) -> None:
    if mode not in MODES:
        raise AccessError(f"{mode!r} is not a device mode")


def check_outcome(outcome: str) -> None:
    if outcome not in OUTCOMES:
        raise AccessError(f"{outcome!r} is not a reconciliation outcome")


def mode_for(*, clock_skew: timedelta, last_sync_at: datetime | None,
             at: datetime) -> str:
    """Derive the posture rather than taking it from the device.

    **A device that reports its own mode reports the mode it would like to be in.** The three
    inputs are facts the server can see -- how far out the clock is against the server's own
    instant, and when this device last synced -- so a unit cannot claim `online` to have its
    decisions trusted more.
    """
    if abs(clock_skew) > MAX_DEVICE_CLOCK_SKEW:
        return "supervised"
    if last_sync_at is None or at - last_sync_at > SYNC_INTERVAL:
        return "offline"
    return "online"


def check_snapshot_usable(posture: Posture, *, at: datetime, risk: str) -> None:
    """Refuse an offline decision made on a snapshot outside its risk bounds.

    Four refusals, each one of paragraph 1955's "snapshot/clock/credential outside risk
    bounds":

      * there is no snapshot at all, so nothing authorized this device to decide anything;
      * the snapshot has expired, which is what a bounded TTL is *for*;
      * it was minted below the device's revocation epoch, so it has already missed a
        withdrawal -- MOD-021's rule, applied at the point of use rather than at issue;
      * it outlives what this zone's risk class admits, which is `zones.snapshot_ceiling`.
    """
    if posture.snapshot_expires_at is None or posture.snapshot_issued_at is None:
        raise AccessError(
            "this reader holds no authorization snapshot, so it decides nothing offline")
    if at >= posture.snapshot_expires_at:
        raise AccessError(
            "this reader's authorization snapshot expired "
            f"{posture.snapshot_expires_at.isoformat()}; it decides nothing until it syncs")
    if posture.snapshot_epoch is None or posture.snapshot_epoch < posture.device_epoch:
        raise AccessError(
            "this reader's snapshot was built before a credential was withdrawn; it decides "
            "nothing until it syncs")
    ceiling = snapshot_ceiling(risk)
    if posture.snapshot_expires_at - posture.snapshot_issued_at > ceiling:
        raise AccessError(
            f"this reader's snapshot outlives what a {risk} zone admits")


def may_decide_offline(posture: Posture, *, at: datetime, risk: str) -> bool:
    """Whether this device may decide at all without the cloud. A convenience over the above."""
    try:
        check_snapshot_usable(posture, at=at, risk=risk)
    except AccessError:
        return False
    return posture.mode != "supervised"
