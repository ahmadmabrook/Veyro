"""MOD-014 PPL-01: the member and staff lifecycle states, and which moves are legal.

**This is the person's standing with the tenant, not a membership agreement.** COM-01's
`app.membership` is the agreement and paragraph 9979 calls it "lifecycle source of truth" for
that; this module is about whether somebody is a lead, a member, a paused member or a former
one, which exists before the first agreement and after the last. Collapsing the two would make
"is this person a member" depend on a module that is not built yet.

The states are the ones a gym actually works with, and the transitions are the ones that are
real rather than the ones that are drawable. Three refusals carry the design:

* **Nothing returns to `lead`.** A person who became a member and left is a `former` member, and
  a former member who comes back is `active` again. Allowing the step back would lose the fact
  that they were ever a member, which is the one thing the record is for.
* **`cancelled` and `former` are different.** Cancelled is the member's decision this time
  round; former is the tenant's record that the relationship has ended. Both can go back to
  `active` -- people rejoin -- and neither can go to `lead`.
* **Staff employment ends once.** `ended` is terminal. Re-hiring somebody is a new employment
  period, and a row that could be un-ended would make "who was employed in March" unanswerable.
"""

from __future__ import annotations

#: PPL-01's member states. `lead` is the entry point because somebody who walks in and gives a
#: phone number is a lead before anybody has decided anything else about them.
MEMBER_STATES = ("lead", "prospect", "active", "paused", "cancelled", "former")

#: Who may go where. Read it as "from this state, these are reachable".
MEMBER_EDGES: dict[str, tuple[str, ...]] = {
    # A lead can be qualified, can join outright (the walk-in who signs the same day), or can go
    # cold -- which is `former`, not a deletion, because the attribution is the point.
    "lead": ("prospect", "active", "former"),
    "prospect": ("active", "former"),
    # The ordinary member. Pausing is a product feature (travel, injury); cancelling is theirs.
    "active": ("paused", "cancelled", "former"),
    "paused": ("active", "cancelled", "former"),
    # Both ends of the relationship can be picked up again. Neither goes back to `lead`.
    "cancelled": ("active", "former"),
    "former": ("active",),
}

#: Staff employment. Three states, and the end is final.
STAFF_STATES = ("active", "suspended", "ended")
STAFF_EDGES: dict[str, tuple[str, ...]] = {
    "active": ("suspended", "ended"),
    "suspended": ("active", "ended"),
    "ended": (),
}

#: The member states that mean somebody is currently entitled to walk in, before any entitlement
#: check. Named here so a surface asking "is this person a member" has one answer -- `paused` is
#: deliberately not in it, and `cancelled` is deliberately not either: a cancellation that is
#: still inside its notice period is COM-01's problem, not this module's.
PRESENT_STATES = ("active",)


class LifecycleError(ValueError):
    """A lifecycle move this module will not make."""


def check_member_transition(current: str, target: str) -> None:
    """Refuse a move the machine does not admit, naming both ends.

    A no-op move -- `active` to `active` -- is refused rather than ignored. The caller asking
    for it either has a stale read or is retrying a request that already landed, and both want
    to know; silently succeeding would let a retry record a second `member.lifecycle.changed`
    event for a change that never happened.
    """
    if current not in MEMBER_STATES:
        raise LifecycleError(f"{current!r} is not a member lifecycle state")
    if target not in MEMBER_STATES:
        raise LifecycleError(f"{target!r} is not a member lifecycle state")
    if target == current:
        raise LifecycleError(f"this member is already {current}")
    if target not in MEMBER_EDGES[current]:
        raise LifecycleError(f"a member cannot go from {current} to {target}")


def check_staff_transition(current: str, target: str) -> None:
    if current not in STAFF_STATES:
        raise LifecycleError(f"{current!r} is not a staff employment state")
    if target not in STAFF_STATES:
        raise LifecycleError(f"{target!r} is not a staff employment state")
    if target == current:
        raise LifecycleError(f"this employment is already {current}")
    if target not in STAFF_EDGES[current]:
        raise LifecycleError(f"employment cannot go from {current} to {target}")


def reason_required(target: str) -> bool:
    """Which moves have to say why.

    The ones that take something away. A member being paused, cancelled or written off is
    something they may ask about months later, and "it says `cancelled` and nobody wrote down
    why" is the answer that ends up in a complaint. Becoming `active` needs no excuse.
    """
    return target in ("paused", "cancelled", "former")


def check_version(expected: int, actual: int) -> None:
    """Optimistic concurrency, which paragraph 1331 asks for by name.

    Two front-desk staff editing one profile is the ordinary case, not a race worth ignoring:
    last-write-wins silently discards one of them, and the one discarded is whichever finished
    first, which is nobody's intent. The caller sends the version it read and a mismatch is a
    refusal it can act on by re-reading.
    """
    if expected != actual:
        raise LifecycleError(
            f"this record has changed since it was read (expected version {expected}, "
            f"found {actual})"
        )
