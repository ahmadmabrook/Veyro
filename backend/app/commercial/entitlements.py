"""MOD-017 COM-01-R03: what a member may use, and the arithmetic that decides it.

Paragraph 1506 in one line: **MemberEntitlementGrant is the fulfilment authority.** This module
is the decision half of that -- it answers "may this member do this now, and what does the
balance become" with no I/O, and the service holds the lock that makes the answer safe.

Three rules, each because the obvious version is wrong:

* **The balance is a sum of movements, never a stored number.** `balance_of` takes the ledger
  rows. A `remaining` column is what two concurrent bookings race on, and a stored balance that
  disagreed with the movements beside it would be unresolvable -- MOD-011's argument against a
  metric that duplicates a table, applied to the number that decides whether somebody gets
  through a turnstile.

* **A reservation holds quantity; a consumption moves nothing.** The quantity left the balance
  when it was held, so settling must not take it again. That is why `consume` is constrained to
  a delta of zero in the schema: the invariant lives in both places because it is the one a
  double-count would quietly break.

* **An unusable grant is refused with the reason, not merely refused.** A member told "not
  eligible" at a turnstile cannot act on it; "your off-peak membership is usable from 09:00 and
  it is 07:40" is something they can. Every refusal here carries a code and a sentence, by the
  shape MOD-016's review arrived at: **the service branches on the code and never on the
  words**, because a decision made by matching prose is one anybody can change by editing a
  string.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: COM-01-R03's nine kinds of right.
ENTITLEMENT_TYPES = (
    "location_access", "schedule_access", "zone_access", "class_credit",
    "facility_access", "service_credit", "guest_pass", "discount", "digital_content",
)

#: Movement kinds, and the sign each one must carry. The schema enforces the same table one
#: constraint per kind; it is stated twice because a balance with a wrong sign in it is the
#: defect nobody notices until a member is refused at a turnstile, and because the two places
#: are checked by different things -- a mutation sweep and a unit test.
#:
#: `reservation_expired` and `grant_expired` are deliberately separate kinds. A single `expire`
#: would be two opposite movements under one name: a lapsed hold gives quantity *back*, and a
#: lapsed grant takes the remaining balance *away*.
SIGNS: dict[str, str] = {
    "grant": "positive",
    "carryover": "positive",
    "release": "positive",
    "reservation_expired": "positive",
    "reserve": "negative",
    "revoke": "negative",
    "grant_expired": "negative",
    "consume": "zero",
    "adjustment": "either",
}

#: Refusal codes. The service compares against these; nothing compares against the prose.
NOT_ACTIVE = "grant_not_active"
NOT_YET_VALID = "grant_not_yet_valid"
EXPIRED = "grant_expired"
OUTSIDE_HOURS = "outside_usable_hours"
WRONG_LOCATION = "outside_granted_scope"
INSUFFICIENT = "insufficient_balance"
USABLE = "usable"


class EntitlementError(ValueError):
    """An entitlement input this module will not accept."""


@dataclass(frozen=True)
class Movement:
    """One ledger row, for the balance arithmetic."""

    movement_kind: str
    delta: int


@dataclass(frozen=True)
class Grant:
    """A grant's own facts, as the decision layer needs them."""

    grant_id: str
    is_counted: bool
    granted_quantity: int | None
    valid_from: datetime
    valid_to: datetime | None = None
    status: str = "active"
    brand_id: str | None = None
    location_id: str | None = None
    usable_from_minute: int | None = None
    usable_to_minute: int | None = None


@dataclass(frozen=True)
class Verdict:
    """Whether a grant may be drawn on, by code and in words."""

    code: str
    reason: str

    @property
    def ok(self) -> bool:
        return self.code == USABLE


def check_sign(movement_kind: str, delta: int) -> None:
    """Refuse a movement whose sign contradicts its kind."""
    expected = SIGNS.get(movement_kind)
    if expected is None:
        raise EntitlementError(f"{movement_kind!r} is not a movement this build records")
    if expected == "positive" and delta <= 0:
        raise EntitlementError(f"a {movement_kind} adds to the balance")
    if expected == "negative" and delta >= 0:
        raise EntitlementError(f"a {movement_kind} takes from the balance")
    if expected == "zero" and delta != 0:
        raise EntitlementError(
            f"a {movement_kind} moves nothing: the quantity left the balance when it was held")
    if expected == "either" and delta == 0:
        raise EntitlementError(f"a {movement_kind} of nothing is a row with no meaning")


def balance_of(movements: list[Movement]) -> int:
    """What is left on a counted grant: the sum of its movements.

    No ordering is needed and none is imposed, because addition commutes -- which is itself a
    reason to keep the balance as a sum rather than as a replay: a sum cannot be got wrong by
    processing rows in the wrong order, and a replay can.
    """
    return sum(m.delta for m in movements)


def held_quantity(live_reservation_quantities: list[int]) -> int:
    """How much of the balance is currently held by live reservations.

    **Summed from the reservations in `held` status, not reconstructed from the ledger.** The
    first version walked the movements -- reserves less the returns -- and got it wrong, because
    a `consume` carries a delta of zero by design: the quantity already left the balance when
    it was held, so there is nothing in the ledger to say the *hold* ended. A consumed
    reservation was therefore counted as held for ever, and a member who had used all ten
    classes was told all ten were still reserved for bookings they had already attended.

    The reservation row is the authority on whether a hold is live, and reconstructing that
    from a ledger whose language is deliberately about *balance* rather than *holds* was the
    mistake. Reported separately from the balance because "you have two classes left" and "two
    of your classes are held for a booking you have not attended" are different answers.

    Found by this module's own tests.
    """
    if any(q <= 0 for q in live_reservation_quantities):
        raise EntitlementError("a_live_reservation_holds_at_least_one_unit")
    return sum(live_reservation_quantities)


def usable(
    grant: Grant, *, at: datetime, quantity: int = 1, balance: int | None = None,
    location_id: str | None = None, brand_id: str | None = None,
    local_minute: int | None = None,
) -> Verdict:
    """Whether this grant may be drawn on for `quantity`, now, here.

    **The order of the checks is the order of the explanation.** Status, then window, then
    scope, then hours, then balance -- cheapest and most final first, so the reason a member is
    given is the most useful one rather than whichever check happened to run.

    `local_minute` is minutes since midnight *in the location's own timezone*, and the service
    derives it from the location rather than taking it from a caller: it was a request field,
    and an off-peak grant was then drawn on at seven in the evening by sending `600`. This
    module still will not guess a timezone -- an off-peak membership refused because the server
    is in UTC is the defect that only shows up in one country -- which is why the conversion
    happens in SQL, against the zone database PostgreSQL has and this process does not.
    """
    if quantity <= 0:
        raise EntitlementError("a_draw_is_at_least_one_unit")
    if grant.status != "active":
        return Verdict(NOT_ACTIVE, f"this entitlement is {grant.status}")
    if at < grant.valid_from:
        return Verdict(NOT_YET_VALID,
                       f"this entitlement is usable from {grant.valid_from.isoformat()}")
    if grant.valid_to is not None and at >= grant.valid_to:
        return Verdict(EXPIRED, f"this entitlement expired on {grant.valid_to.isoformat()}")
    # **A set scope must match; an unset one matches anything.** The same asymmetry as
    # MOD-016's price-book specificity, and for the same reason: scoring the wide match would
    # make a grant that specifies nothing narrower than one that specifies a location.
    if grant.brand_id is not None and grant.brand_id != brand_id:
        return Verdict(WRONG_LOCATION, "this entitlement is for another brand")
    if grant.location_id is not None and grant.location_id != location_id:
        return Verdict(WRONG_LOCATION, "this entitlement is for another location")
    if grant.usable_from_minute is not None:
        if local_minute is None:
            # **A window that cannot be evaluated refuses.** The caller did not say what time
            # it is locally, and treating that as "any time" would turn an off-peak membership
            # into an unlimited one by omitting a field -- MOD-016's `max_per_subject` finding,
            # in this module's clothes.
            return Verdict(
                OUTSIDE_HOURS,
                "this entitlement is restricted by time of day and no local time was given")
        assert grant.usable_to_minute is not None
        if not (grant.usable_from_minute <= local_minute < grant.usable_to_minute):
            return Verdict(OUTSIDE_HOURS, (
                f"this entitlement is usable between "
                f"{grant.usable_from_minute // 60:02d}:{grant.usable_from_minute % 60:02d} "
                f"and {grant.usable_to_minute // 60:02d}:{grant.usable_to_minute % 60:02d}"))
    if grant.is_counted:
        if balance is None:
            raise EntitlementError("a_counted_grant_needs_its_balance")
        if balance < quantity:
            return Verdict(INSUFFICIENT,
                           f"{balance} left and {quantity} needed")
    return Verdict(USABLE, "usable")


def reservation_expiry(*, held_at: datetime, ttl_seconds: int) -> datetime:
    """When a hold lapses.

    Computed at reservation time from the policy's TTL and *stored*, so a later policy change
    neither extends nor expires a live hold. A hold whose expiry moved under it is the one a
    member loses a booking to.
    """
    if ttl_seconds < 30 or ttl_seconds > 86400:
        raise EntitlementError("a_reservation_ttl_is_between_30_seconds_and_a_day")
    return held_at + timedelta(seconds=ttl_seconds)


def carryover_quantity(
    *, unused: int, carryover_mode: str, carryover_limit: int | None,
) -> int:
    """COM-01-R05's credit carryover: how much unconsumed quantity survives the period.

    **Nothing is the default and `none` is the commonest mode**, because carryover is a cost the
    tenant is choosing to bear and a default that carried everything forward would make every
    class pack unlimited by accident.
    """
    if unused < 0:
        raise EntitlementError("an_unused_quantity_is_not_negative")
    if carryover_mode == "none":
        return 0
    if carryover_mode == "unlimited":
        return unused
    if carryover_mode == "capped":
        if carryover_limit is None:
            raise EntitlementError("a_capped_carryover_states_its_cap")
        return min(unused, carryover_limit)
    raise EntitlementError(f"{carryover_mode!r} is not a carryover mode this build evaluates")
