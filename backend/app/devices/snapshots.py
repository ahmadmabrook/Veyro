"""The EdgePolicySnapshot: paragraph 1949's "signed authorization projection with bounded TTL".

**A snapshot is how a gateway keeps working when the cloud does not**, and its bound is what
stops that becoming an authorization nobody can withdraw. Paragraph 1951: "deny when
snapshot/clock/credential is outside risk bounds". Paragraph 3094: a stale read model "cannot
authorize a consequence-bearing mutation beyond budget". Paragraph 1953 puts revocation
propagation online under sixty seconds, which is the number the TTL has to be read against: a
snapshot valid for a week is a member revoked on Monday still training on Friday.

**What this module owns is the bound, not the content.** OPS-03 (MOD-022, unbuilt) decides who
may go through which door; this decides how long a gateway may answer that question without
asking again, what a snapshot must carry to be answerable at all, and what a stale one may not
be used for. The split is paragraph 1949's own: "Access authorization separates credential
identity from policy."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.devices.capabilities import DeviceError

#: The longest a snapshot may be honoured. **Twelve hours**, which is a judgement and is
#: stated as one: paragraph 1949 says "bounded" and names no number, and the two pressures are
#: paragraph 1953's sixty-second revocation target (which argues for minutes) and a club whose
#: link is down for an afternoon (which argues for hours). Twelve hours is one trading day, so
#: a gateway that lost its link at opening still runs to closing and a member revoked today is
#: refused tomorrow at the latest. **The revocation epoch below is what closes the gap** --
#: a gateway that can reach the cloud learns about a revocation in seconds and does not wait
#: for its snapshot to expire.
MAX_TTL = timedelta(hours=12)

#: The shortest. A snapshot good for a minute is one a gateway spends its whole life fetching.
MIN_TTL = timedelta(minutes=5)

#: How far a gateway's own clock may be out before its snapshot is not answerable. Paragraph
#: 4179's reader tolerance is ±30 seconds for a rotating token; a *snapshot* is coarser, and
#: five minutes of skew is the point past which "is this expired" stops having one answer.
MAX_CLOCK_SKEW = timedelta(minutes=5)

#: What a snapshot may be used for once it is stale. **Nothing with a consequence**, which is
#: paragraph 3094 read as a list rather than a sentence: a stale snapshot may still let a
#: gateway *report* and *refuse*, because both are safe, and may not let it open anything.
STALE_PERMITS: frozenset[str] = frozenset({"report", "deny"})


@dataclass(frozen=True)
class Snapshot:
    """One snapshot's facts.

    `revocation_epoch` is the counter paragraph 4179 names: a gateway holding an older epoch
    than the registry knows about has missed a revocation, which is a different failure from
    an expired snapshot and has to be reported as one.
    """

    issued_at: datetime
    expires_at: datetime
    revocation_epoch: int
    content_digest: str


def check_ttl(issued_at: datetime, expires_at: datetime) -> timedelta:
    """Refuse a snapshot whose life is outside the bound, returning the life."""
    if expires_at <= issued_at:
        raise DeviceError("a snapshot expires after it is issued")
    ttl = expires_at - issued_at
    if ttl < MIN_TTL:
        raise DeviceError(
            f"a snapshot lives at least {int(MIN_TTL.total_seconds() // 60)} minutes; a "
            f"shorter one is a gateway that spends its life fetching")
    if ttl > MAX_TTL:
        raise DeviceError(
            f"a snapshot lives at most {int(MAX_TTL.total_seconds() // 3600)} hours; longer "
            f"is a revocation nobody can deliver")
    return ttl


def is_stale(snapshot: Snapshot, *, at: datetime) -> bool:
    return at >= snapshot.expires_at


def check_fresh_enough(
    snapshot: Snapshot, *, at: datetime, purpose: str, current_epoch: int,
) -> None:
    """Refuse to use a snapshot that cannot answer, and say which bound it is outside.

    Three bounds, because paragraph 1951 names three: the snapshot (has it expired), the clock
    (is the device's idea of now believable) and the credential (has a revocation happened
    that this snapshot predates). A single "stale" verdict would collapse them, and an
    operator reading a denial needs to know whether to re-sync a gateway or to look at its
    clock.
    """
    if snapshot.issued_at - at > MAX_CLOCK_SKEW:
        raise DeviceError(
            "this snapshot is issued in the future by more than the tolerated skew; the "
            "gateway's clock or the registry's disagree and neither can be trusted to "
            "decide expiry")
    if snapshot.revocation_epoch < current_epoch:
        raise DeviceError(
            f"this snapshot predates revocation epoch {current_epoch} and has missed at "
            f"least one withdrawal; it may refuse but it may not admit")
    if is_stale(snapshot, at=at) and purpose not in STALE_PERMITS:
        raise DeviceError(
            f"this snapshot expired at {snapshot.expires_at.isoformat()}; a stale snapshot "
            f"may report and may deny, and may not {purpose}")


def next_epoch(current: int) -> int:
    """The epoch after a revocation. Monotonic, because a gateway compares it numerically.

    Bounded, so the column cannot be driven past `integer` into a 500 -- MOD-011's overflow
    finding, which four modules have now paid for.
    """
    if current < 0:
        raise DeviceError("a revocation epoch is not negative")
    if current >= 2_000_000_000:
        raise DeviceError("a revocation epoch is at most two billion")
    return current + 1
