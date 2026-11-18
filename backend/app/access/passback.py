"""Anti-passback, and the claim it does not make while a device is offline.

Paragraph 4163 is unusually explicit about the limit: "Offline anti-passback is local to a
device/connected controller group. Cross-device global anti-passback is not claimed while
disconnected; reconciliation flags duplicates after reconnect." So this module has two
functions and the second one's whole job is to say what the first could not see.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.access.zones import AccessError

#: How anti-passback was decided, which is recorded on the decision because the two are
#: different guarantees and a report that conflated them would overstate the weaker one.
SCOPES: tuple[str, ...] = ("global", "controller_group")


@dataclass(frozen=True)
class Entry:
    """The last time this credential was seen going in, and where."""

    at: datetime
    zone_id: str
    point_id: str
    scope: str


def check_scope(scope: str) -> None:
    if scope not in SCOPES:
        raise AccessError(f"{scope!r} is not an anti-passback scope")


def seconds_since(previous: Entry | None, *, at: datetime) -> int | None:
    """How long ago this credential last entered, or `None` if it never has.

    **`None` is not zero.** MOD-016's `max_per_subject` was enforced only against callers who
    volunteered a subject, because `by_subject` read 0 both for "never used it" and for
    "nobody said who this is"; here the same conflation would let a first-ever entry be
    refused as a passback.
    """
    if previous is None:
        return None
    return int((at - previous.at).total_seconds())


def claim(*, online: bool) -> str:
    """What anti-passback actually covered for this decision.

    An online decision reads every entry in the tenant, so the claim is `global`. An offline
    one reads whatever its own controller group holds, which is the honest `controller_group`
    -- and the decision records which, so nobody later reports "anti-passback enforced" over
    a period when half of it was local.
    """
    return "global" if online else "controller_group"


def is_duplicate(
    first: Entry, second: Entry, *, window_seconds: int,
) -> bool:
    """Whether two reconciled entries are the same person twice inside the window.

    Used after a reconnect, where paragraph 4163 says duplicates are **flagged** rather than
    rewritten: both rows stay, because an offline event is evidence of what a device saw and
    deleting one would be rewriting history to make a report tidy.
    """
    if window_seconds <= 0:
        return False
    return abs((second.at - first.at).total_seconds()) < window_seconds
