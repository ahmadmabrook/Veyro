"""MOD-016 COM-02-R01 and R06: what a product is, and what may be said about it.

The eight product types are COM-02-R01's list exactly. They are **code, not rows**, for the
reason MOD-008 gives for permissions and MOD-010 for event types: a product type decides which
module fulfils the sale, so two tenants disagreeing about which types exist would be a
disagreement only the code could settle. A tenant's own taxonomy is what tags and custom fields
are for; this list is a fact about what the software can do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: COM-02-R01, in full.
PRODUCT_TYPES = (
    "membership", "service", "session_credit", "class_credit", "retail_sku",
    "subscription_addon", "event", "gift_card",
)

#: Which types a bundle item may promise to deliver, and how.
FULFILMENT_KINDS = (
    "entitlement_grant", "membership_agreement", "physical_goods", "digital_delivery",
    "booking_credit",
)

#: The types that grant something a member later consumes, so `entitlement_quantity` means
#: something on their variants. Stated rather than derived, because `event` is the one a reader
#: would guess wrongly either way: a ticket is consumed, and it is consumed by attending rather
#: than by spending a balance.
QUANTITATIVE_TYPES = ("session_credit", "class_credit", "gift_card")

KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,62}$")
VARIANT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")
LOCALE_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")

#: A product moves draft -> published -> retired and never back. Un-publishing a product that
#: has been sold would make the sale unexplainable; retiring it is the supported way to stop
#: selling it, and the sales already made keep resolving.
STATUSES = ("draft", "published", "retired")
STATUS_EDGES: dict[str, tuple[str, ...]] = {
    "draft": ("published", "retired"),
    "published": ("retired",),
    "retired": (),
}


class ProductError(ValueError):
    """A product definition this module will not accept."""


@dataclass(frozen=True)
class Variant:
    variant_key: str
    display_name: str
    entitlement_quantity: int | None = None
    term_days: int | None = None
    sku: str | None = None


def check_product(
    *, product_key: str, product_type: str, merchandising_rank: int = 1000,
) -> None:
    if not KEY_RE.fullmatch(product_key):
        raise ProductError(
            "a product key is lowercase, starts with a letter and holds letters, digits, "
            "underscores, dots or hyphens"
        )
    if product_type not in PRODUCT_TYPES:
        raise ProductError(f"{product_type!r} is not a product type")
    if not 0 <= merchandising_rank <= 1_000_000:
        raise ProductError("a merchandising rank is between 0 and 1000000")


def check_variant(variant: Variant, product_type: str) -> None:
    """Refuse a variant that cannot be fulfilled as the type it belongs to.

    **A quantitative product's variant says how many.** A ten-session pack whose
    `entitlement_quantity` is empty is a sale nothing can fulfil, and the module that would
    fulfil it -- COM-01 -- is not built, so nothing downstream would catch it either. Refusing
    here is the only place it can be caught at all.
    """
    if not VARIANT_KEY_RE.fullmatch(variant.variant_key):
        raise ProductError(
            "a variant key is lowercase and holds letters, digits, underscores, dots or "
            "hyphens"
        )
    if not variant.display_name.strip():
        raise ProductError("a variant has a display name")
    if variant.entitlement_quantity is not None and variant.entitlement_quantity <= 0:
        raise ProductError("an entitlement quantity is at least one")
    if variant.term_days is not None and variant.term_days <= 0:
        raise ProductError("a term is at least one day")
    if product_type in QUANTITATIVE_TYPES and variant.entitlement_quantity is None:
        raise ProductError(
            f"a {product_type} variant says how many units it grants, or nothing can fulfil it"
        )
    if product_type == "membership" and variant.term_days is None:
        raise ProductError(
            "a membership variant says how long it runs, or its end date is unknowable"
        )


def check_transition(current: str, target: str) -> None:
    """Refuse a status move the machine does not admit, naming both ends."""
    if current not in STATUSES:
        raise ProductError(f"{current!r} is not a product status")
    if target not in STATUSES:
        raise ProductError(f"{target!r} is not a product status")
    if target == current:
        raise ProductError(f"this product is already {current}")
    if target not in STATUS_EDGES[current]:
        raise ProductError(
            f"a product cannot go from {current} to {target}: un-publishing would make a sale "
            f"already made unexplainable, and retiring is how selling stops"
        )


def check_text(locale: str, display_name: str) -> None:
    """COM-02-R06's localized text. The locale is a tag, not free text.

    **No fallback chain**, which is MOD-013's decision for the same reason: quietly showing
    English to somebody who asked for Arabic is worse than saying the text is missing, and
    picking a chain is a product decision the sources do not state.
    """
    if not LOCALE_RE.fullmatch(locale):
        raise ProductError("a locale is a language tag such as `en` or `en-GB`")
    if not display_name.strip():
        raise ProductError("a localized product has a display name")


def listing_order(
    products: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """COM-02-R06's merchandising order: rank first, then the key.

    The key is the tiebreak so a listing is stable between runs -- two products a tenant gave
    the same rank would otherwise swap places depending on the planner, which looks like a bug
    to whoever is arranging the shop front.
    """
    return sorted(products, key=lambda pair: (pair[0], pair[1]))
