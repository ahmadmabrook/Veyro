"""How many people are inside, and the reason that number has a disclaimer on it.

Paragraph 4180: "Occupancy derived from access events is operational/advisory unless both
entry and exit are reliably measured. It is never the sole life-safety muster source."

**So there is no occupancy table.** A stored count is a second copy of the truth that can
disagree with the events it was derived from -- MOD-018's argument for computing every balance
-- and here a count that drifts is a count somebody might use to decide whether a room has
been evacuated. The number is a sum over `acc_events`, and whether it may be relied on is a
property of the zone's own readers rather than a flag anybody sets.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What the number is worth. `measured` needs both directions wired; `advisory` is everything
#: else, and the word is paragraph 4180's own.
CONFIDENCE: tuple[str, ...] = ("measured", "advisory")

#: Said on every read, because a number without it is the one somebody counts heads against.
NEVER_A_MUSTER = (
    "occupancy is derived from access events and is operational only; it is never the sole "
    "life-safety muster source"
)


@dataclass(frozen=True)
class Readers:
    """What a zone can actually see."""

    has_entry_reader: bool
    has_exit_reader: bool


def confidence(readers: Readers) -> str:
    """`measured` only when both directions are read.

    A zone with a turnstile in and a push bar out counts everybody in and nobody out, so its
    occupancy rises all day and is wrong by closing time. That is not a defect to fix with a
    nightly reset -- it is a fact about the building, and the honest answer is to say the
    number is advisory.
    """
    return "measured" if (readers.has_entry_reader and readers.has_exit_reader) else "advisory"


def inside(entries: int, exits: int, *, readers: Readers) -> int:
    """The count, floored at zero.

    **Floored, and that is a disclosure rather than a repair.** An advisory zone can report
    more exits than entries -- somebody held a door, somebody left by the fire escape -- and a
    negative occupancy would be obviously wrong in a way that makes the whole number look
    broken. Zero is the honest floor; `confidence` is what says not to trust it.
    """
    if entries < 0 or exits < 0:
        raise ValueError("an occupancy count is built from non-negative tallies")
    return max(0, entries - exits)
