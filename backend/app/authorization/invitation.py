"""What a staff invitation is, and when it stops being one. ADM-STF-03, ADR-0017.

**No state is stored** (D6). Pending is derived from three facts the row already carries --
not accepted, not revoked, and not past its window -- so "2d left" is arithmetic rather than a
counter something has to sweep, and there is no `expired` flag to be wrong in either
direction. MOD-026's SLA clock and MOD-018's balances make the same call for the same reason.

**The token is minted and digested by MOD-007** (`secrets.mint_session_token`), imported rather
than reimplemented: two token paths in one repository is two things to get right, and this one
is a bearer credential that creates an identity with a role.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: "The link expires in 7 days", from the canvas.
EXPIRY_DAYS = 7

#: The band. **The ceiling is the interesting half**: an invitation is a bearer credential
#: that creates an identity with a role, so a year-long one is a permanent back door with a
#: friendly name. The floor is a day, because an invitation that expires in an hour is one
#: somebody has to be standing next to their inbox for.
MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 30

#: What an invitation can be, derived in this order: a settled outcome outranks the clock,
#: because an accepted invitation does not become expired by being left alone.
STATES = ("accepted", "revoked", "expired", "pending")

#: The scopes an invitation may name, which are `role_assignments`' own three.
SCOPE_TYPES = ("tenant", "brand", "location")

#: How many clubs one invitation may name. The canvas draws two; the bound is here because an
#: invitation naming forty locations creates forty assignments in one transaction, and a list
#: a caller controls is a list a caller can make expensive.
MAX_SCOPES = 25


class InvitationError(ValueError):
    """An invitation that is not one: a bad window, a bad scope, or no club at all."""


@dataclass(frozen=True)
class Scope:
    """One club an invitation is for. The shape `role_assignments_scope_shape` admits."""

    scope_type: str
    brand_id: str | None = None
    location_id: str | None = None

    def __post_init__(self) -> None:
        if self.scope_type not in SCOPE_TYPES:
            raise InvitationError(f"{self.scope_type!r} is not a scope an invitation can name")
        if self.scope_type == "tenant" and (self.brand_id or self.location_id):
            raise InvitationError("a tenant-wide invitation names no club")
        if self.scope_type == "brand" and not self.brand_id:
            raise InvitationError("a brand-scoped invitation names its brand")
        if self.scope_type == "brand" and self.location_id:
            raise InvitationError("a brand-scoped invitation names no location")
        if self.scope_type == "location" and not self.location_id:
            raise InvitationError("a location-scoped invitation names its club")
        if self.scope_type == "location" and self.brand_id:
            raise InvitationError("a location-scoped invitation names no brand")

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        return (self.scope_type, self.brand_id, self.location_id)


def check_scopes(scopes: list[Scope]) -> None:
    """Refuse a list of clubs that is not one.

    **At least one**, because an invitation with no scope is an identity with a role nobody
    can use -- `permissions_of` lets a broad assignment cover a narrow scope and never the
    reverse, so "no scope" is not "everywhere", it is nothing.

    **No duplicates**, because the accept writes one assignment per row and
    `role_assignments` has a live-uniqueness rule of its own: a repeated club would make the
    second insert refuse an invitation the first had already half-accepted.
    """
    if not scopes:
        raise InvitationError("an invitation names at least one club or the whole tenant")
    if len(scopes) > MAX_SCOPES:
        raise InvitationError(f"an invitation names at most {MAX_SCOPES} clubs")
    seen: set[tuple[str, str | None, str | None]] = set()
    for scope in scopes:
        if scope.key in seen:
            raise InvitationError("a club is named twice on one invitation")
        seen.add(scope.key)
    # **A tenant-wide scope is not combined with a club.** The wider one already covers the
    # narrower, so the pair is a reader being told two things -- and the accept would write an
    # assignment that grants nothing beyond the one beside it.
    if any(scope.scope_type == "tenant" for scope in scopes) and len(scopes) > 1:
        raise InvitationError(
            "a tenant-wide invitation already covers every club; name one or the other")


def check_window(days: int) -> int:
    """How long the link lasts, bounded. Returns the figure so a caller can pass it on.

    **The band is the decision and the instant is the database's**, which is a distinction this
    slice had to learn: the first version computed `expires_at` in Python and bounded it in SQL
    against a `created_at` the database generates -- so the constraint compared two clocks, and
    at exactly thirty days they disagreed. The container's `now()` running a millisecond behind
    the host's was enough to refuse the ceiling this function admits. One clock decides both
    ends now: `invitations_window` is the rule and `now() + make_interval(...)` is the value.
    """
    if days < MIN_EXPIRY_DAYS or days > MAX_EXPIRY_DAYS:
        raise InvitationError(
            f"an invitation lasts between {MIN_EXPIRY_DAYS} and {MAX_EXPIRY_DAYS} days")
    return days


def state(
    *, accepted_at: datetime | None, revoked_at: datetime | None,
    expires_at: datetime, at: datetime,
) -> str:
    """What this invitation is now, derived rather than stored.

    **A settled outcome outranks the clock**, which is the order that matters: an invitation
    accepted on Monday is accepted for ever, and reporting it as expired a week later would
    make the pending list disagree with the identity that exists.
    """
    if accepted_at is not None:
        return "accepted"
    if revoked_at is not None:
        return "revoked"
    return "expired" if expires_at <= at else "pending"


def days_left(expires_at: datetime, at: datetime) -> int:
    """The canvas's "2d left", rounded **up** to whole days.

    Up rather than down, because an invitation with eighteen hours left is one somebody still
    has a day to use: rounding down reports "0d left" on a link that works, which is the
    direction that makes a reader resend something they did not need to.
    """
    seconds = (expires_at - at).total_seconds()
    if seconds <= 0:
        return 0
    return int(-(-seconds // 86_400))
