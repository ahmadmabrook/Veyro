"""The access decision: stable reason codes, ordered, and a public half that reveals nothing.

Paragraph 4157: "Every decision returns stable reason codes suitable for member/front-desk
explanation and stores policy/entitlement version references." Paragraph 1944 is the Critical
Control beside it: "Access denial never reveals sensitive financial or health information
publicly." Those two pull in opposite directions -- a useful reason and a safe one -- and the
answer is that a decision carries **two** reasons: one for the screen above a turnstile and
one for the evidence and the front desk.

**The order of the checks is the order of the explanation**, which is MOD-017's rule for
`entitlements.usable` and the same argument: the reason a member is given should be the most
useful one rather than whichever check happened to run first. Here it is also a privacy
control, because an unpaid balance evaluated before an expired card means a lapsed member
learns their account is in arrears from a door.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.access.zones import AccessError

#: Every reason this module can give, and the only ones. A free-text refusal is not a stable
#: reason code, and a surface that has to parse prose to decide what to show the member is a
#: surface that will show the wrong thing -- MOD-016 shipped a control that matched English
#: words in a reason string and four of them were the whole enforcement.
REASON_CODES: tuple[str, ...] = (
    "granted",
    "granted_by_override",
    #: The credential itself.
    "credential_unknown",
    "credential_revoked",
    "credential_expired",
    "credential_replayed",
    "credential_window",
    "reader_clock_unreliable",
    #: Where and when.
    "wrong_zone",
    "outside_opening_hours",
    "zone_closed",
    #: Who they are to the club. **The three below are the restricted ones.**
    "membership_inactive",
    "no_entitlement",
    "outstanding_balance",
    "age_restricted",
    "safety_hold",
    #: What just happened.
    "anti_passback",
    "zone_at_capacity",
    #: What the door itself is.
    "device_untrusted",
    "point_not_an_entry",
)

#: **`snapshot_stale` used to be here and is deliberately gone.**
#:
#: It was the refusal for a decision made on an offline snapshot outside its bounds, and
#: nothing in this build can produce one: `evaluate_access` is a server decision and needs no
#: snapshot, and a reader that decided on its own authority reports an *event*, which
#: `reconcile_offline_access` flags as `stale_snapshot` rather than deciding again. A declared
#: value with no writer is MOD-020's defect -- four denial reasons nothing produced, and two
#: states nothing wrote that recorded every member of every cancelled class as absent -- so it
#: is removed rather than kept against a route that does not exist. The day there is a route
#: for a reader to report a decision it made offline, this is the code it needs.

#: **The codes whose detail may be read off a screen in a public place.** Everything outside
#: this set gets a fixed line that says to see the front desk: paragraph 1944 forbids a denial
#: revealing sensitive financial or health information publicly, and "your membership is
#: frozen", "you have no sessions left" and "there is a safety hold on your account" are each
#: one of those said out loud to whoever is standing behind the member.
#:
#: `membership_inactive` is in neither list by accident -- it is the one a product owner will
#: want to move, and moving it tells a queue that somebody has stopped paying.
PUBLIC_SAFE: frozenset[str] = frozenset({
    "granted", "granted_by_override", "credential_unknown", "credential_revoked",
    "credential_expired", "credential_replayed", "credential_window",
    "reader_clock_unreliable", "wrong_zone", "outside_opening_hours", "zone_closed",
    "anti_passback", "zone_at_capacity", "device_untrusted", "point_not_an_entry",
})

#: What a member sees when the real reason is not safe to show. **One line for all of them**,
#: because four different polite messages are four different facts about somebody's account
#: readable by whoever is behind them in the queue.
DISCREET = "please see the front desk"

#: The codes that mean the door opens.
GRANTS: frozenset[str] = frozenset({"granted", "granted_by_override"})


@dataclass(frozen=True)
class Subject:
    """What the modules that own a person say about them, at this instant.

    **Every field is read from its owning module**, never from the credential: the membership
    state is MOD-017's, the entitlement verdict is MOD-017's `entitlements.usable`, the date
    of birth is MOD-014's. A credential that carried any of them would be a credential that
    authorizes, which is the sentence this module exists to make unwritable.
    """

    person_id: str
    membership_state: str | None
    has_entitlement: bool
    entitlement_reason: str | None
    balance_minor: int
    age_years: int | None
    safety_hold: bool


@dataclass(frozen=True)
class ZonePolicy:
    """The published policy version a decision is made against, and its identity.

    `policy_id` and `version` are on the row because paragraph 1952 requires the decision to
    reference the exact policy version: a decision re-derived a year later against today's
    policy is not the decision that was made.
    """

    policy_id: str
    version: int
    opens_minute: int | None
    closes_minute: int | None
    requires_entitlement: bool
    max_balance_minor: int | None
    min_age_years: int | None
    anti_passback_seconds: int
    capacity: int | None


@dataclass(frozen=True)
class Decision:
    """What was decided, why, and what may be said about it out loud."""

    granted: bool
    code: str
    public_reason: str
    private_reason: str
    policy_id: str | None = None
    policy_version: int | None = None
    masked: bool = False
    facts: dict[str, str] = field(default_factory=dict)


def check_code(code: str) -> None:
    if code not in REASON_CODES:
        raise AccessError(f"{code!r} is not an access reason code")


def refuse(code: str, private: str, *, public: str | None = None,
           policy: ZonePolicy | None = None) -> Decision:
    """A denial, with its public half chosen by the code rather than by the caller.

    **The caller cannot pass a public reason for a restricted code.** It is tempting to let
    one through "just this once" for a better member experience, and that is exactly how
    paragraph 1944 gets broken: the control has to be a property of the code, so adding a
    restricted reason later cannot forget it.
    """
    check_code(code)
    safe = code in PUBLIC_SAFE
    return Decision(
        granted=False, code=code,
        public_reason=(public or private) if safe else DISCREET,
        private_reason=private, masked=not safe,
        policy_id=None if policy is None else policy.policy_id,
        policy_version=None if policy is None else policy.version)


def decide(
    *, subject: Subject, policy: ZonePolicy, local_minute: int, at: datetime,
    seconds_since_last_entry: int | None, occupancy: int | None,
) -> Decision:
    """The policy half, with the credential already resolved and already checked.

    **This function cannot see a credential**, deliberately: it takes a `Subject`, and a
    subject is what a credential resolved *to*. The separation is paragraph 4155's, and making
    it a signature rather than a convention is what stops the next person adding a
    `credential_says_ok` parameter.

    The order is cheapest and most final first, and the restricted codes come last so that a
    member whose card is simply expired is told that rather than being sent to the desk.
    """
    if policy.opens_minute is not None and policy.closes_minute is not None:
        if not _within(local_minute, policy.opens_minute, policy.closes_minute):
            return refuse(
                "outside_opening_hours",
                f"this zone is open "
                f"{policy.opens_minute // 60:02d}:{policy.opens_minute % 60:02d}"
                f"-{policy.closes_minute // 60:02d}:{policy.closes_minute % 60:02d}",
                policy=policy)
    if policy.capacity is not None and occupancy is not None and occupancy >= policy.capacity:
        return refuse(
            "zone_at_capacity",
            f"this zone holds {policy.capacity} and {occupancy} are inside", policy=policy)
    if (policy.anti_passback_seconds > 0 and seconds_since_last_entry is not None
            and seconds_since_last_entry < policy.anti_passback_seconds):
        return refuse(
            "anti_passback",
            f"this credential was used to enter {seconds_since_last_entry} seconds ago and "
            f"this zone admits one entry every {policy.anti_passback_seconds}",
            policy=policy)
    # --- from here down the reasons are about the person, and none of them is public ------
    if subject.membership_state is not None and subject.membership_state not in (
            "active", "trialing"):
        return refuse("membership_inactive",
                      f"this membership is {subject.membership_state}", policy=policy)
    if policy.min_age_years is not None:
        if subject.age_years is None:
            # **An unknown age is not an adult.** MOD-014 takes the opposite default for
            # *reading a record*, with a stated reason: treating every undated person as a
            # minor would make a guardian mandatory before anybody could read the record of a
            # member who never gave a birthday. A door is the other way round -- the harm is
            # a child in a weights room, and the remedy is one question at the desk.
            return refuse("age_restricted",
                          f"this zone is {policy.min_age_years}+ and this member's date of "
                          f"birth is not recorded", policy=policy)
        if subject.age_years < policy.min_age_years:
            return refuse("age_restricted",
                          f"this zone is {policy.min_age_years}+", policy=policy)
    if subject.safety_hold:
        return refuse("safety_hold",
                      "there is a safety hold on this member's record", policy=policy)
    if policy.max_balance_minor is not None and subject.balance_minor > policy.max_balance_minor:
        return refuse("outstanding_balance",
                      f"this member owes {subject.balance_minor} in minor units, over the "
                      f"{policy.max_balance_minor} this zone admits", policy=policy)
    if policy.requires_entitlement and not subject.has_entitlement:
        return refuse(
            "no_entitlement",
            subject.entitlement_reason or "this member has nothing that admits them here",
            policy=policy)
    return Decision(granted=True, code="granted", public_reason="welcome",
                    private_reason="every check passed", policy_id=policy.policy_id,
                    policy_version=policy.version)


def override(*, reason: str, policy: ZonePolicy | None = None) -> Decision:
    """A staff override, which is a decision in its own right rather than a flag on one.

    Paragraph 1938 asks for "configurable grace and exception policies with staff override,
    reason and approval". The override is a different reason code and a different permission,
    so a report of how often a door was opened against the policy is one query -- and a
    decision that reads as `granted` when somebody waved a member through is the shape
    MOD-013's `bypass_policy_ref` was blocked for.
    """
    if not reason.strip():
        raise AccessError("an override states why")
    return Decision(
        granted=True, code="granted_by_override", public_reason="welcome",
        private_reason=reason.strip(),
        policy_id=None if policy is None else policy.policy_id,
        policy_version=None if policy is None else policy.version)


def _within(minute: int, opens: int, closes: int) -> bool:
    """Whether a local minute is inside an opening window, wrapping past midnight.

    A gym that opens at 06:00 and closes at 23:00 is the ordinary case; one that opens at
    22:00 and closes at 06:00 is a 24-hour club's night shift, and reading that as "never" is
    how a door stops working at ten at night.
    """
    if opens <= closes:
        return opens <= minute < closes
    return minute >= opens or minute < closes
