"""OPS-02-R03: the waitlist -- position, offer, expiry and idempotent promotion.

Paragraph 1882: "Waitlist position, automatic promotion, timed confirmation, fallback and
member preferences." Paragraph 4144: "Waitlist promotion is an idempotent workflow with
offer/expiry policy; a member cannot consume the same capacity twice." Paragraph 5031:
"waitlist promotion reserves before notifying."

**Reserve, then notify, then wait.** The order is the whole design and the reason is in
paragraph 5031: a promotion that notified first would tell a member they have a place and then
race another member for it, and the member who lost would have been told they had won. So a
promotion takes the MOD-019 hold *first*, inside the transaction that records the offer, and
the notification is MOD-013's and goes out afterwards. "Notification failure does not lose the
booking state" (paragraph 5032) follows: the place is already held, so a mail that never
arrives is a member who has to be told again, not a member who lost their place.

**The offer holds real capacity, which is the cost of doing it in that order.** A sixty-minute
offer is an hour in which nobody else can book that place, and if the member never answers it
is an hour wasted. That is the trade paragraph 5032's "expired promotion releases capacity"
describes, and the expiry is what bounds it.

**Position is a number a member can predict.** `first_come` orders by when somebody joined,
full stop. A tier rule exists because OPS-02-R02 names priority, and it is opt-in on the
policy: a member who cannot tell why somebody else was promoted ahead of them is the complaint
this module exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.booking.denial import BookingError
from app.booking.policy import Policy, check_policy

#: What a waitlist entry is doing. `offered` is the one that holds capacity; the others do not.
#:
#: `expired` and `declined` are different facts about the same outcome -- the member did not
#: take the place -- because one is their choice and the other is the clock, and a tenant
#: deciding who to promote first next time needs to tell them apart.
ENTRY_STATES: tuple[str, ...] = (
    "waiting", "offered", "confirmed", "declined", "expired", "withdrawn", "lapsed",
)

#: The states that are still in the queue. **`expired` is one of them**, which is the whole of
#: the `expired -> waiting` promise one paragraph down: an offer that lapsed overnight leaves
#: the member exactly where they were, holding their `joined_at`. The first version treated
#: only `waiting` and `offered` as live, and since both expiry paths write `expired` and
#: nothing in the build ever writes `waiting` back, a member asleep at six was not sent to the
#: back of the queue -- they were removed from it. `position_of` answered None, so their app
#: showed them as not on the waitlist at all, and `next_to_offer` could never reach them
#: again. Found by review, with three docstrings and the migration header claiming otherwise.
#:
#: **`bkg_waitlist_entries_one_live_per_person` covers the same three**, because a member with
#: an expired entry *and* a new waiting one would hold two places in the queue.
LIVE_STATES: tuple[str, ...] = ("waiting", "offered", "expired")

#: An entry can only move forward, and `lapsed` is where an entry goes when the session it was
#: for happened without them. Each edge is a thing the member is told.
EDGES: dict[str, tuple[str, ...]] = {
    "waiting": ("offered", "withdrawn", "lapsed"),
    "offered": ("confirmed", "declined", "expired"),
    # **An expired offer keeps its place and can be offered again.** A member asleep at six in
    # the morning did not decline, and sending them to the back would make the waitlist a
    # lottery about who is awake. A *declined* offer is a choice and does end it.
    #
    # **`offered` is in this set because the promoter writes it**, and leaving it out was worse
    # than the defect it was meant to prevent: `next_to_offer` draws from `waiting` and
    # `expired` alike, and an expired entry keeps its `joined_at` so it sorts first -- so from
    # the moment one member failed to answer, every promotion on that session picked their
    # entry and was refused by the trigger, and nobody was promoted again while places sat
    # free. `waiting` stays in the set as an explicit re-queue; nothing in the build writes it.
    "expired": ("offered", "waiting", "lapsed"),
    "confirmed": (),
    "declined": (),
    "withdrawn": (),
    "lapsed": (),
}

#: **`lapsed` has no writer in this build**, and that is a disclosed gap rather than an
#: oversight: it is where an entry goes when the session has started and the queue is moot,
#: which wants something sweeping closed sessions on a schedule -- the worker runtime this
#: build does not have. Said here because this is where somebody reads the state list; an
#: enumeration is a claim about what the software does, and a value with no writer is either a
#: gap to name or a defect wearing a design decision's clothes. MOD-020 shipped four of the
#: second kind, the worst of which recorded every member of a cancelled class as a no-show.
LAPSED_HAS_NO_WRITER = True


@dataclass(frozen=True)
class Entry:
    """One member waiting for one session, as the decisions need it."""

    entry_id: str
    person_id: str
    joined_at: datetime
    state: str = "waiting"
    #: The tier `membership_tier` orders by, where a tenant uses it. Lower sorts first, so a
    #: tenant with no tiers has every member at zero and the rule collapses to `first_come` --
    #: which is the right degenerate case rather than an error.
    tier: int = 0
    offered_at: datetime | None = None
    offer_expires_at: datetime | None = None


def check_entry(entry: Entry) -> None:
    if entry.state not in ENTRY_STATES:
        raise BookingError(f"{entry.state!r} is not a waitlist entry state")
    if entry.tier < 0:
        raise BookingError("a waitlist tier is not negative")
    if entry.state == "offered" and entry.offer_expires_at is None:
        raise BookingError(
            "an offer has an expiry; one that never expires holds capacity for ever")
    if (entry.offered_at is None) != (entry.offer_expires_at is None):
        raise BookingError("an offer has both a time and an expiry, or neither")


def check_transition(current: str, target: str) -> None:
    if current not in ENTRY_STATES:
        raise BookingError(f"{current!r} is not a waitlist entry state")
    if target not in ENTRY_STATES:
        raise BookingError(f"{target!r} is not a waitlist entry state")
    if target not in EDGES[current]:
        raise BookingError(f"a waitlist entry does not move from {current} to {target}")


def ordered(entries: list[Entry], *, policy: Policy) -> list[Entry]:
    """The queue, in the order the policy promotes from.

    **Deterministic to the last tiebreak.** Two members who joined in the same millisecond are
    ordered by their entry id, because leaving it to the planner would make the queue change
    between two reads of the same page -- and a member watching their position move for no
    reason is the complaint this ordering exists to prevent.
    """
    check_policy(policy)
    for entry in entries:
        check_entry(entry)
    live = [e for e in entries if e.state in LIVE_STATES]
    if policy.priority_rule == "membership_tier":
        return sorted(live, key=lambda e: (e.tier, e.joined_at, e.entry_id))
    return sorted(live, key=lambda e: (e.joined_at, e.entry_id))


def position_of(entries: list[Entry], entry_id: str, *, policy: Policy) -> int | None:
    """A member's place in the queue, counting from one, or None when they are not in it.

    One-based because it is shown to a member: "you are number 0" is not a thing anybody says.
    """
    queue = ordered(entries, policy=policy)
    for n, entry in enumerate(queue, 1):
        if entry.entry_id == entry_id:
            return n
    return None


def live_offers(entries: list[Entry], *, at: datetime) -> int:
    """How many offers are outstanding, which is how much of the free capacity is spoken for."""
    return sum(1 for e in entries
               if e.state == "offered" and not offer_has_expired(e, at=at))


def next_to_offer(
    entries: list[Entry], *, policy: Policy, at: datetime, places: int = 1,
) -> list[Entry]:
    """Who gets the free places, in order, or an empty list when nobody can take one.

    **A live offer holds one place, not the whole queue.** Somebody already holding an offer
    has a place counted against them, so they must not be counted twice -- but the first
    version returned nobody at all while *any* offer was outstanding, so a class with five
    cancellations two hours out filled at most two of the five seats and three members who
    were waiting did not get in. The docstring's justification ("promoting the next member as
    well would hand out two places for one seat") was true only when one place was free, which
    is `CLAUDE.md`'s companion check: read the other act and see whether the danger the module
    names is reachable at all. What actually guards against double-allocation is MOD-019's
    hold, which refuses at the ceiling.

    So the rule is arithmetic rather than a veto: offer as many as there are places, minus the
    offers already live. Found by review.
    """
    check_policy(policy)
    if places < 0:
        raise BookingError("a promotion is for no fewer than nothing")
    queue = ordered(entries, policy=policy)
    room = places - live_offers(entries, at=at)
    if room <= 0:
        return []
    return [e for e in queue if e.state in ("waiting", "expired")][:room]


def offer_expiry(*, at: datetime, policy: Policy) -> datetime:
    check_policy(policy)
    return at + timedelta(minutes=policy.offer_minutes)


def offer_has_expired(entry: Entry, *, at: datetime) -> bool:
    """Whether an offer's window has closed.

    An entry that is not `offered` has not expired -- it has no offer. Reporting True for a
    `waiting` entry would make a sweep release a place nobody was holding.
    """
    check_entry(entry)
    if entry.state != "offered" or entry.offer_expires_at is None:
        return False
    return at >= entry.offer_expires_at


def may_confirm(entry: Entry, *, at: datetime) -> None:
    """Whether this member may take the place they were offered, raising the reason if not.

    **The expiry is checked here and again where the booking is written.** This answers a
    surface asking whether to show the button; the write re-reads the clock in the transaction
    that takes the place, because "a control consulted once is a control with a window" and an
    offer window is an hour long.
    """
    check_entry(entry)
    if entry.state != "offered":
        raise BookingError(
            f"this entry is {entry.state} and has no offer to confirm")
    if offer_has_expired(entry, at=at):
        raise BookingError("this offer has expired; the place has gone back to the waitlist")
