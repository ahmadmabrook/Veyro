"""MOD-016 COM-02-R03: a bundle links a commercial sale to operational fulfilment.

"Linking" is the whole of what this module does, and the distinction matters: the modules that
*fulfil* -- COM-01's entitlement grants, OPS-01's bookings -- are not built in this repository.
So a bundle declares what a sale owes and `cat_bundle_fulfilments` records what somebody says
was delivered, with their name on the row.

**Nothing here delivers anything**, and that is stated rather than discovered. A module that
wrote "fulfilled" with nothing having fulfilled anything is the fabricated-evidence shape this
build has been bitten by five times -- MOD-011's synthetic results, MOD-012's connector runs,
MOD-013's deliveries, MOD-014's contact verification, and MOD-015's payment recovery. The ledger
is the honest half: it is what whatever does the work writes to.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.catalog.products import FULFILMENT_KINDS

#: What a fulfilment record may say happened. `reversed` subtracts, which is how a delivery
#: recorded in error is corrected without an UPDATE the table does not grant.
OUTCOMES = ("delivered", "failed", "cancelled", "reversed")


class BundleError(ValueError):
    """A bundle definition or fulfilment this module will not accept."""


@dataclass(frozen=True)
class Item:
    variant_id: str
    quantity: int
    fulfilment_kind: str


@dataclass(frozen=True)
class Outstanding:
    """What a sale of this bundle still owes."""

    variant_id: str
    fulfilment_kind: str
    owed: int
    delivered: int

    @property
    def remaining(self) -> int:
        return self.owed - self.delivered


def check_items(items: list[Item]) -> None:
    """Refuse a bundle that cannot be fulfilled or that owes the same thing twice.

    **A bundle with no items is a sale that owes nothing**, which is a product priced as a
    bundle for no reason -- and far more likely a composition somebody forgot to finish than a
    deliberate empty bundle. Refusing it here is the only place it can be caught, because the
    thing that would notice is a fulfilment run that never happens.
    """
    if not items:
        raise BundleError("a bundle has at least one item, or it owes nothing")
    seen: set[str] = set()
    for item in items:
        if item.variant_id in seen:
            raise BundleError(
                f"{item.variant_id} appears twice; one line with a quantity is the way to owe "
                f"two of something"
            )
        seen.add(item.variant_id)
        if item.quantity <= 0:
            raise BundleError("a bundle item owes at least one unit")
        if item.quantity > 1000:
            raise BundleError("a bundle item owes at most 1000 units")
        if item.fulfilment_kind not in FULFILMENT_KINDS:
            raise BundleError(f"{item.fulfilment_kind!r} is not a fulfilment kind")


def outstanding(
    items: list[Item], delivered: dict[str, int],
) -> list[Outstanding]:
    """What is still owed on one sale, per item.

    `delivered` is the net of the `delivered` rows less the `reversed` ones; a failed or
    cancelled one leaves the obligation standing, which is the direction that cannot silently
    lose a member something they paid for.
    """
    return [
        Outstanding(item.variant_id, item.fulfilment_kind, item.quantity,
                    delivered.get(item.variant_id, 0))
        for item in sorted(items, key=lambda i: i.variant_id)
    ]


def check_fulfilment(
    item: Item, *, already_delivered: int, quantity: int, outcome: str, detail: str | None,
) -> None:
    """Refuse a fulfilment record that could not be true.

    **Over-delivery is refused.** For an entitlement grant that is a member with more sessions
    than they bought, and nothing downstream would catch it: the grant module reads this ledger
    rather than auditing it.

    **A failure says why**, because a dead-lettered fulfilment with no reason is an obligation
    nobody can act on -- and the member is still owed whatever it was.

    **A mistaken delivery is reversed rather than edited**, and a reversal cannot take back
    more than was delivered -- which would leave the obligation reading as larger than the
    sale. The ledger has no UPDATE and no DELETE grant, so this is the only correction path
    there is; it is MOD-015's credit note applied to an obligation, and it is what makes
    recording a delivery a recoverable mistake rather than a permanent one.
    """
    if outcome not in OUTCOMES:
        raise BundleError(f"{outcome!r} is not a fulfilment outcome")
    if quantity <= 0:
        raise BundleError("a fulfilment delivers at least one unit")
    if outcome != "delivered" and not (detail or "").strip():
        raise BundleError(f"a {outcome} fulfilment states why")
    if outcome == "delivered" and already_delivered + quantity > item.quantity:
        raise BundleError(
            f"this sale owes {item.quantity} of {item.variant_id} and {already_delivered} "
            f"have been delivered; {quantity} more would over-deliver"
        )
    if outcome == "reversed" and quantity > already_delivered:
        raise BundleError(
            f"{already_delivered} of {item.variant_id} have been delivered on this sale; "
            f"{quantity} cannot be reversed"
        )
