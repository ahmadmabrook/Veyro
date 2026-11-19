"""Access points and the zones they stand on, and what a zone's risk buys.

**A zone is where the risk is declared**, not a label. TSD paragraph 4160: a standard access
snapshot's authorization TTL is twelve hours, and a high-risk zone defaults to two and may be
configured shorter. That is the only place in this build where an authorization's *lifetime*
depends on what it opens, so it is the reason zones exist as rows rather than as a string on
a door.
"""

from __future__ import annotations

from datetime import timedelta


class AccessError(ValueError):
    """What this module refuses. Carried to the service as a `Conflict` or an `InvalidRequest`."""


#: How risky a zone is, which bounds how long an offline authorization for it may live.
#: Paragraph 4160 names the two; a third would need a stated TTL nobody has written down.
RISK_CLASSES: tuple[str, ...] = ("standard", "high_risk")

#: The ceiling per risk class. **A ceiling, not a default**: a tenant may configure shorter and
#: may not configure longer, because the number is what bounds the damage of a stolen snapshot.
SNAPSHOT_CEILING: dict[str, timedelta] = {
    "standard": timedelta(hours=12),
    "high_risk": timedelta(hours=2),
}

#: Which way a reader faces. **`exit` is not the mirror of `entry`**, and the difference is
#: paragraph 4177: egress is never conditioned on Veyro membership, cloud reachability or
#: software authorization. An exit reader *records* that somebody left; it never decides.
DIRECTIONS: tuple[str, ...] = ("entry", "exit", "both")


def check_risk_class(risk: str) -> None:
    if risk not in RISK_CLASSES:
        raise AccessError(
            f"{risk!r} is not a zone risk class; this software knows "
            f"{', '.join(RISK_CLASSES)}")


def check_direction(direction: str) -> None:
    if direction not in DIRECTIONS:
        raise AccessError(
            f"{direction!r} is not a reader direction; this software knows "
            f"{', '.join(DIRECTIONS)}")


def snapshot_ceiling(risk: str) -> timedelta:
    """The longest an offline authorization for this zone may be honoured."""
    check_risk_class(risk)
    return SNAPSHOT_CEILING[risk]


def check_snapshot_ttl(ttl: timedelta, *, risk: str) -> None:
    """Refuse a snapshot that outlives what its zone's risk admits.

    **The ceiling is per zone and the floor is MOD-021's.** `snapshots.check_ttl` already
    refuses anything over twelve hours or under five minutes, for every device; this narrows
    it where the zone says so. A high-risk zone issued a twelve-hour snapshot is an
    authorization that outlives the risk assessment that was made about it.
    """
    ceiling = snapshot_ceiling(risk)
    if ttl > ceiling:
        raise AccessError(
            f"a {risk} zone's offline authorization lives at most "
            f"{int(ceiling.total_seconds() // 3600)} hours; this one asks for "
            f"{ttl.total_seconds() / 3600:.1f}")


def decides_entry(direction: str) -> bool:
    """Whether a reader facing this way can make an access decision at all.

    **An exit reader never does.** Paragraph 4177 puts egress outside the Veyro application
    path entirely. A `both` reader *can*, on the way in -- which is why `decides_for` below
    exists and why this predicate is not enough on its own.
    """
    check_direction(direction)
    return direction in ("entry", "both")


def decides_for(point_direction: str, reported_direction: str) -> bool:
    """Whether a presentation at this reader, going this way, is a decision at all.

    **This function is the fix for a paragraph 4177 violation a tenant reached by wiring the
    ordinary hardware.** `both` is one lane that reads in each direction -- the arrangement
    that makes a zone's occupancy `measured` and therefore the one a tenant is pushed toward
    -- and `evaluate_access` took no direction, so every presentation at a `both` lane was
    evaluated as an entry and could be refused. A reviewer walked a member in, then presented
    the same card on the way out and got `anti_passback`: the member was inside and the
    software would not let them out. Any restricted code reaches the same place, so a member
    whose card lapsed while they were in the building could not leave by the lane they came
    in by.

    The docstring above it claimed at the time that this module "has no code path that can
    refuse somebody leaving -- not a policy that happens to allow it, not a configuration that
    happens to be set". The configuration existed, was admitted by the schema and by
    `commission_point`, and was the tempting one.

    **The reported direction is the reader's, and lying about it buys nothing**, which is what
    makes taking it safe: a presentation claiming `exit` is not a decision, so it issues no
    unlock. The only thing a false `exit` achieves is not opening the door.
    """
    check_direction(point_direction)
    check_direction(reported_direction)
    if reported_direction == "exit":
        return False
    return decides_entry(point_direction)
