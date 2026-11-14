"""MOD-016 COM-02 service: the catalog, its price books, its promotions and its resolutions.

The decisions live in `app.catalog.products`, `pricing`, `promotions` and `bundles`. This module
reads rows, calls those, and writes what they return.

**Two controls from paragraph 10220 are enforced here rather than described.**

*Pricing resolution is deterministic and returns an explanation.* `resolve_price` loads the
books, the prices and the promotions, hands them to the pure resolver, and writes the whole
explanation to `cat_price_resolutions` -- insert-only, so the receipt cannot be rewritten
afterwards. Every ordering the resolver uses is total, so two tills asking the same question at
the same instant get the same answer and the same reasoning.

*Manual price overrides and high discounts require explicit permission and audit.* An override
is a separate command with its own permission, and `resolve_price` **refuses** to store a
resolution whose discount reaches the applicable threshold without an approval id that resolves
to a real approval for the same variant and amount. A discount field on the resolution request
would have been that authority bought with a body field, which is the shape MOD-009's
`consent_subject`, MOD-013's `priority: "critical"` and MOD-014's guardian field each shipped
once.

**What this module cannot do, stated here rather than discovered later.**

* **It does not compute tax.** `cat_tax_categories` names a regime and holds no rate, because
  paragraph 4077 puts rates in regional configuration or a provider and the sources state none.
  MOD-015 refused identically; a rate column nobody sourced would end up on an invoice.
* **It does not create orders.** COM-01 owns the order and the invoice line; this module
  resolves a price and records how. `order_reference` is free text for that reason.
* **It does not fulfil a bundle.** It records what somebody says was delivered.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection, errors

from app.billing import money
from app.catalog import bundles, pricing, products, promotions
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, aggregate_type: str,
    aggregate_id: str, payload: dict[str, Any], *, correlation_id: str, actor_id: str,
) -> None:
    """Append an event in the caller's transaction, which is MOD-010's whole design."""
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, correlation_id=correlation_id,
        actor_id=actor_id,
    )


# ------------------------------------------------------------------------ tax categories

def register_tax_category(
    pool: Pool, tenant_id: str, *, category_key: str, display_name: str, actor_id: str,
    correlation_id: str, jurisdiction_note: str | None = None,
) -> dict[str, Any]:
    """Name a tax regime. **It holds no rate**, and that is paragraph 4077's requirement."""
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_tax_categories
                    (tenant_id, category_key, display_name, jurisdiction_note, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING tax_category_id
                """,
                (tenant_id, category_key, display_name, jurisdiction_note, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_tax_category_key_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"tax_category_id": str(row[0]), "category_key": category_key,
            "rate_note": "this build holds no tax rates; paragraph 4077 puts them in "
                         "regional configuration or a provider"}


# ------------------------------------------------------------------------------ products

def create_product(
    pool: Pool, tenant_id: str, *, product_key: str, product_type: str, actor_id: str,
    correlation_id: str, tax_category_id: str | None = None, brand_id: str | None = None,
    merchandising_rank: int = 1000, texts: list[dict[str, str]] | None = None,
    variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """CreateProduct, with its localized text and its variants in the same command.

    One command because a product with no variant cannot be priced and a product with no text
    cannot be displayed, so three commands would leave two windows in which the catalogue holds
    something unsellable. The same reasoning as MOD-014's person and their contact points.
    """
    try:
        products.check_product(
            product_key=product_key, product_type=product_type,
            merchandising_rank=merchandising_rank)
    except products.ProductError as e:
        raise InvalidRequest(str(e)) from None
    prepared: list[products.Variant] = []
    for entry in variants or []:
        variant = products.Variant(
            variant_key=str(entry.get("variant_key", "")),
            display_name=str(entry.get("display_name", "")),
            entitlement_quantity=entry.get("entitlement_quantity"),
            term_days=entry.get("term_days"),
            sku=entry.get("sku"))
        try:
            products.check_variant(variant, product_type)
        except products.ProductError as e:
            raise InvalidRequest(str(e)) from None
        prepared.append(variant)
    for text in texts or []:
        try:
            products.check_text(str(text.get("locale", "")),
                               str(text.get("display_name", "")))
        except products.ProductError as e:
            raise InvalidRequest(str(e)) from None

    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_products
                    (tenant_id, product_key, product_type, tax_category_id, brand_id,
                     merchandising_rank, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING product_id, version
                """,
                (tenant_id, product_key, product_type, tax_category_id, brand_id,
                 merchandising_rank, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_product_key_already_exists") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tax_category_or_brand_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        product_id = str(row[0])
        for text in texts or []:
            conn.execute(
                """
                INSERT INTO plt01.cat_product_texts
                    (tenant_id, product_id, locale, display_name, description, terms,
                     updated_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, product_id, locale) DO NOTHING
                """,
                (tenant_id, product_id, text.get("locale"), text.get("display_name"),
                 text.get("description"), text.get("terms"), actor_id, correlation_id),
            )
        created_variants: list[dict[str, Any]] = []
        for variant in prepared:
            try:
                created = conn.execute(
                    """
                    INSERT INTO plt01.cat_variants
                        (tenant_id, product_id, variant_key, display_name,
                         entitlement_quantity, term_days, sku, created_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING variant_id
                    """,
                    (tenant_id, product_id, variant.variant_key, variant.display_name,
                     variant.entitlement_quantity, variant.term_days, variant.sku, actor_id,
                     correlation_id),
                ).fetchone()
            except errors.UniqueViolation:
                raise Conflict("this_variant_key_or_sku_is_already_taken") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            assert created is not None
            created_variants.append(
                {"variant_id": str(created[0]), "variant_key": variant.variant_key})
    return {"product_id": product_id, "product_key": product_key,
            "product_type": product_type, "version": int(row[1]),
            "variants": created_variants}


def publish_product(
    pool: Pool, tenant_id: str, product_id: str, *, expected_version: int, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """PublishCatalog, for one product, and publish `product.published`.

    **A product with no price in any book is refused.** Publishing is what makes something
    sellable on every channel, and a sellable thing nobody can price is a till that stops
    working in front of a customer. The check is here rather than at the till because the till
    has no way to recover.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, version, product_key, product_type FROM plt01.cat_products"
            " WHERE product_id = %s",
            (product_id,),
        ).fetchone()
        if row is None:
            raise NotFound("product_not_found")
        try:
            products.check_transition(str(row[0]), "published")
        except products.ProductError as e:
            raise Conflict(str(e)) from None
        if int(row[1]) != expected_version:
            raise Conflict("this_product_changed_since_it_was_read")
        # **A price in a live book over a live window**, not any row at all. Counting every
        # non-superseded price meant a draft or retired book, or a window that had expired or
        # had not yet opened, satisfied the check -- so the till this exists to protect could
        # still stop working in front of a customer, which is the whole of its reason.
        priced = conn.execute(
            "SELECT count(*) FROM plt01.cat_prices p"
            " JOIN plt01.cat_variants v ON v.variant_id = p.variant_id"
            " JOIN plt01.cat_price_books b ON b.price_book_id = p.price_book_id"
            " WHERE v.product_id = %s AND p.superseded_by IS NULL"
            "   AND b.status = 'active'"
            "   AND b.effective_from <= now()"
            "   AND (b.effective_to IS NULL OR b.effective_to > now())"
            "   AND p.effective_from <= now()"
            "   AND (p.effective_to IS NULL OR p.effective_to > now())",
            (product_id,),
        ).fetchone()
        if priced is None or int(priced[0]) == 0:
            raise Conflict("this_product_has_no_live_price_in_any_active_book")
        updated = conn.execute(
            "UPDATE plt01.cat_products SET status = 'published', published_at = now(),"
            " published_by = %s, version = version + 1, updated_at = now()"
            " WHERE product_id = %s AND version = %s AND status = 'draft'",
            (actor_id, product_id, expected_version),
        ).rowcount
        if updated == 0:
            raise Conflict("this_product_changed_while_being_published")
        _append(conn, tenant_id, "product.published", "product", product_id,
                {"product_id": product_id, "product_key": str(row[2]),
                 "product_type": str(row[3])},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"product_id": product_id, "status": "published",
            "version": expected_version + 1}


def retire_product(
    pool: Pool, tenant_id: str, product_id: str, *, expected_version: int, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Stop selling a product, and publish `product.retired`.

    Sales already made keep resolving, which is COM-02-R07; a *new* sale is refused by
    `resolve_price`, which is what makes this act mean anything.

    Attributed and published, because publication is both: a retirement that recorded nobody
    and announced nothing was the withdrawal half of a pair whose other half does both.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, version, product_key FROM plt01.cat_products"
            " WHERE product_id = %s",
            (product_id,),
        ).fetchone()
        if row is None:
            raise NotFound("product_not_found")
        try:
            products.check_transition(str(row[0]), "retired")
        except products.ProductError as e:
            raise Conflict(str(e)) from None
        updated = conn.execute(
            "UPDATE plt01.cat_products SET status = 'retired', retired_at = now(),"
            " retired_by = %s, retire_correlation_id = %s,"
            " version = version + 1, updated_at = now()"
            " WHERE product_id = %s AND version = %s",
            (actor_id, correlation_id, product_id, expected_version),
        ).rowcount
        if updated == 0:
            raise Conflict("this_product_changed_while_being_retired")
        _append(conn, tenant_id, "product.retired", "product", product_id,
                {"product_id": product_id, "product_key": str(row[2])},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"product_id": product_id, "status": "retired", "version": expected_version + 1}


def list_products(
    pool: Pool, tenant_id: str, *, status: str | None = None, locale: str = "en",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """The catalogue listing, in COM-02-R06's merchandising order.

    The text is joined for the requested locale and **not** fallen back to another one: a
    missing translation shows as missing, which is MOD-013's decision and the same reasoning.
    """
    sql = ["SELECT p.product_id, p.product_key, p.product_type, p.status,"
           " p.merchandising_rank, t.display_name, t.description"
           " FROM plt01.cat_products p"
           " LEFT JOIN plt01.cat_product_texts t"
           "   ON t.product_id = p.product_id AND t.locale = %s"]
    args: list[Any] = [locale]
    if status is not None:
        sql.append(" WHERE p.status = %s")
        args.append(status)
    sql.append(" ORDER BY p.merchandising_rank, p.product_key LIMIT %s")
    args.append(max(1, min(limit, 500)))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"product_id": str(r[0]), "product_key": r[1], "product_type": r[2],
             "status": r[3], "merchandising_rank": int(r[4]),
             "display_name": r[5], "description": r[6],
             "text_locale": locale if r[5] is not None else None} for r in rows]


# -------------------------------------------------------------------- price books and prices

def create_price_book(
    pool: Pool, tenant_id: str, *, price_book_key: str, display_name: str, currency: str,
    effective_from: datetime, actor_id: str, correlation_id: str,
    brand_id: str | None = None, location_id: str | None = None, channel: str = "any",
    customer_segment: str = "any", tax_category_id: str | None = None,
    effective_to: datetime | None = None, priority: int = 0,
) -> dict[str, Any]:
    """COM-02-R02's seven dimensions, as a row."""
    if channel not in pricing.CHANNELS:
        raise InvalidRequest(f"unknown_channel_{channel}")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_price_books
                    (tenant_id, price_book_key, display_name, currency, brand_id, location_id,
                     channel, customer_segment, tax_category_id, effective_from, effective_to,
                     priority, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING price_book_id
                """,
                (tenant_id, price_book_key, display_name, currency.upper(), brand_id,
                 location_id, channel, customer_segment, tax_category_id, effective_from,
                 effective_to, priority, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_price_book_key_already_exists") from None
        except errors.ForeignKeyViolation:
            raise NotFound("brand_location_or_tax_category_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"price_book_id": str(row[0]), "price_book_key": price_book_key,
            "currency": currency.upper(), "status": "draft"}


def activate_price_book(
    pool: Pool, tenant_id: str, price_book_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Make a draft book live, and record who did it.

    **This is the act that switches a tenant's prices on**, and the first version took
    `actor_id` and `correlation_id` and wrote neither -- the table had no activation columns at
    all, while every sibling act in the module is attributed (`cat_products.published_by`,
    `cat_promotions.activated_by`, `cat_coupons.revoked_by`). MOD-008 audits denials and not
    allowed actions, and `veyro_cp_app` holds nothing in `iam`, so the row was the only record
    there could be. Fourth module to ship this shape; see CLAUDE.md.
    """
    with tenant_scope(pool, tenant_id) as conn:
        updated = conn.execute(
            "UPDATE plt01.cat_price_books SET status = 'active', activated_at = now(),"
            " activated_by = %s, activate_correlation_id = %s"
            " WHERE price_book_id = %s AND status = 'draft'",
            (actor_id, correlation_id, price_book_id),
        ).rowcount
        if updated == 0:
            raise Conflict("this_price_book_is_unknown_or_not_a_draft")
    return {"price_book_id": price_book_id, "status": "active"}


def create_price(
    pool: Pool, tenant_id: str, *, price_book_id: str, variant_id: str, amount_minor: int,
    effective_from: datetime, actor_id: str, correlation_id: str,
    effective_to: datetime | None = None,
) -> dict[str, Any]:
    """CreatePrice, and publish `price.changed`.

    **A new row, never an edit.** COM-02-R07: "versioned price changes that do not rewrite
    historical transactions". The table carries no UPDATE grant on the amount at all, so the
    only way to re-price is this command with a later `effective_from` -- and the superseded row
    keeps its window, which is what lets an order resolved last March re-derive.

    The currency comes from the book rather than the caller. A price in a currency its book does
    not use is a row the resolver would refuse at read time, and refusing it at write time means
    the catalogue never holds one.
    """
    with tenant_scope(pool, tenant_id) as conn:
        book = conn.execute(
            "SELECT currency, price_book_key FROM plt01.cat_price_books"
            " WHERE price_book_id = %s",
            (price_book_id,),
        ).fetchone()
        if book is None:
            raise NotFound("price_book_not_found")
        variant = conn.execute(
            "SELECT variant_key, product_id FROM plt01.cat_variants WHERE variant_id = %s",
            (variant_id,),
        ).fetchone()
        if variant is None:
            raise NotFound("variant_not_found")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_prices
                    (tenant_id, price_book_id, variant_id, amount_minor, currency,
                     effective_from, effective_to, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING price_id
                """,
                (tenant_id, price_book_id, variant_id, amount_minor, str(book[0]),
                 effective_from, effective_to, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_book_already_prices_this_variant_from_that_moment") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        _append(conn, tenant_id, "price.changed", "price", str(row[0]),
                {"price_id": str(row[0]), "price_book_id": price_book_id,
                 "variant_id": variant_id, "currency": str(book[0]),
                 "effective_from": effective_from.isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"price_id": str(row[0]), "price_book_id": price_book_id,
            "variant_id": variant_id, "amount_minor": amount_minor,
            "currency": str(book[0])}


def supersede_price(
    pool: Pool, tenant_id: str, price_id: str, *, replacement_price_id: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Withdraw a price in favour of another, without editing either.

    The one column on `cat_prices` that moves. Used for a price written in error: the row stays
    so a resolution that already cited it still explains, and the resolver skips it from now on.
    """
    if price_id == replacement_price_id:
        raise InvalidRequest("a_price_cannot_supersede_itself")
    with tenant_scope(pool, tenant_id) as conn:
        replacement = conn.execute(
            "SELECT price_book_id, variant_id FROM plt01.cat_prices WHERE price_id = %s",
            (replacement_price_id,),
        ).fetchone()
        if replacement is None:
            raise NotFound("replacement_price_not_found")
        original = conn.execute(
            "SELECT price_book_id, variant_id, superseded_by FROM plt01.cat_prices"
            " WHERE price_id = %s",
            (price_id,),
        ).fetchone()
        if original is None:
            raise NotFound("price_not_found")
        if original[2] is not None:
            raise Conflict("this_price_has_already_been_superseded")
        # **The replacement has to price the same thing.** Pointing a withdrawn price at an
        # unrelated row would make the supersession chain meaningless to anybody auditing why a
        # price stopped applying.
        if (str(original[0]), str(original[1])) != (str(replacement[0]),
                                                    str(replacement[1])):
            raise Conflict("a_replacement_prices_the_same_variant_in_the_same_book")
        updated = conn.execute(
            "UPDATE plt01.cat_prices SET superseded_by = %s, superseded_at = now(),"
            " superseded_by_actor = %s, supersede_correlation_id = %s"
            " WHERE price_id = %s AND superseded_by IS NULL",
            (replacement_price_id, actor_id, correlation_id, price_id),
        ).rowcount
        if updated == 0:
            raise Conflict("this_price_was_superseded_by_somebody_else")
        # Withdrawing a price *is* a price change, and a consumer of `price.changed` that only
        # saw the replacement appear would never see the withdrawal.
        _append(conn, tenant_id, "price.withdrawn", "price", price_id,
                {"price_id": price_id, "price_book_id": str(original[0]),
                 "variant_id": str(original[1]),
                 "replacement_price_id": replacement_price_id},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"price_id": price_id, "superseded_by": replacement_price_id}


# ---------------------------------------------------------------- promotions and coupons

def create_promotion(
    pool: Pool, tenant_id: str, *, promotion_key: str, display_name: str,
    promotion_kind: str, effective_from: datetime, actor_id: str, correlation_id: str,
    percent_bp: int | None = None, amount_minor: int | None = None,
    currency: str | None = None, stacking_group: str = "default", priority: int = 0,
    approval_threshold_bp: int = 0, effective_to: datetime | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """CreatePromotion, with its eligibility rules in the same command.

    The rules come together because a promotion whose conditions arrive a moment later is a
    promotion that is briefly unconditional -- and `cat_eligibility_rules` is insert-only, so
    there is no way to tighten one afterwards either.
    """
    if promotion_kind not in promotions.PROMOTION_KINDS:
        raise InvalidRequest(f"unknown_promotion_kind_{promotion_kind}")
    kinds = {str(rule.get("rule_kind")) for rule in rules or []}
    for kind in sorted(kinds):
        if kind not in promotions.RULE_KINDS:
            raise InvalidRequest(f"unknown_rule_kind_{kind}")
    # **A usage limit is only as real as the ledger that counts it, and only a coupon has
    # one.** `_usage` counts `cat_coupon_redemptions`, and a redemption is written only for a
    # promotion reached by presenting a code -- so `max_total_redemptions` on an automatic
    # promotion was evaluated against a count that is permanently zero and could never bite.
    # The API accepted the rule, stored it, evaluated it and it did nothing, which is "a rule
    # the evaluator reads as vacuous ... the direction that silently grants a discount nobody
    # meant to give" -- this module's own words about the operand constraint. Refused at the
    # write, because there is nowhere else to say it.
    if promotion_kind != "coupon" and kinds & promotions.USAGE_RULE_KINDS:
        raise InvalidRequest("only_a_coupon_promotion_can_carry_a_usage_limit")
    # **A promotion reached without a code and targeted at nobody applies to every sale.** A
    # reviewer activated a `staff_discount` at 5000bp with no rules and halved the price for
    # every customer in the tenant. `automatic` means exactly that and is the one kind for
    # which it is the intent; `corporate_rate`, `member_tier` and `staff_discount` each name a
    # group, so one of them with no condition is a configuration mistake with a bill attached.
    if promotion_kind in ("corporate_rate", "member_tier", "staff_discount") and not kinds:
        raise InvalidRequest(f"a_{promotion_kind}_promotion_needs_at_least_one_rule")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_promotions
                    (tenant_id, promotion_key, display_name, promotion_kind, percent_bp,
                     amount_minor, currency, stacking_group, priority,
                     approval_threshold_bp, effective_from, effective_to, created_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING promotion_id
                """,
                (tenant_id, promotion_key, display_name, promotion_kind, percent_bp,
                 amount_minor, (currency.upper() if currency else None), stacking_group,
                 priority, approval_threshold_bp, effective_from, effective_to, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_promotion_key_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        promotion_id = str(row[0])
        for rule in rules or []:
            try:
                conn.execute(
                    """
                    INSERT INTO plt01.cat_eligibility_rules
                        (tenant_id, promotion_id, rule_kind, amount_minor, quantity,
                         text_value, date_from, date_to, created_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, promotion_id, rule.get("rule_kind"),
                     rule.get("amount_minor"), rule.get("quantity"), rule.get("text_value"),
                     rule.get("date_from"), rule.get("date_to"), actor_id, correlation_id),
                )
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
    return {"promotion_id": promotion_id, "promotion_key": promotion_key,
            "status": "draft", "rules": len(rules or [])}


def activate_promotion(
    pool: Pool, tenant_id: str, promotion_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Make a promotion live, and publish `promotion.activated`."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT promotion_key, status FROM plt01.cat_promotions WHERE promotion_id = %s",
            (promotion_id,),
        ).fetchone()
        if row is None:
            raise NotFound("promotion_not_found")
        updated = conn.execute(
            "UPDATE plt01.cat_promotions SET status = 'active', activated_at = now(),"
            " activated_by = %s WHERE promotion_id = %s AND status = 'draft'",
            (actor_id, promotion_id),
        ).rowcount
        if updated == 0:
            raise Conflict("this_promotion_is_not_a_draft")
        _append(conn, tenant_id, "promotion.activated", "promotion", promotion_id,
                {"promotion_id": promotion_id, "promotion_key": str(row[0])},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"promotion_id": promotion_id, "status": "active"}


def issue_coupon(
    pool: Pool, tenant_id: str, *, promotion_id: str, code: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """A code that reaches a promotion.

    **Stored uppercase and matched uppercase**, so `SAVE10` and `save10` are one code. A code
    that depended on how somebody typed it would be a support call per campaign.
    """
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_coupons
                    (tenant_id, promotion_id, code, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING coupon_id
                """,
                (tenant_id, promotion_id, code.strip().upper(), actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_coupon_code_already_exists") from None
        except errors.ForeignKeyViolation:
            raise NotFound("promotion_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"coupon_id": str(row[0]), "code": code.strip().upper()}


def revoke_coupon(
    pool: Pool, tenant_id: str, coupon_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Stop a code working without ending the campaign it reaches.

    A leaked code is the ordinary reason, and ending the promotion instead would punish every
    other code issued under it.
    """
    if not reason.strip():
        raise InvalidRequest("revoking_a_coupon_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            updated = conn.execute(
                "UPDATE plt01.cat_coupons SET status = 'revoked', revoked_at = now(),"
                " revoked_by = %s, revoke_reason = %s"
                " WHERE coupon_id = %s AND status = 'active'",
                (actor_id, reason, coupon_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated == 0:
            raise Conflict("this_coupon_is_unknown_or_already_revoked")
    return {"coupon_id": coupon_id, "status": "revoked"}


def validate_promotion(
    pool: Pool, tenant_id: str, *, code: str, subtotal_minor: int, currency: str,
    channel: str = "any", customer_segment: str = "any", product_type: str = "",
    subject_id: str | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """ValidatePromotion: would this code work, and if not, why not?

    **A read, with no side effect**, so a till can tell somebody the answer before taking their
    money. The reason is the point -- "minimum spend of 50.00 not met, subtotal was 40.00" is
    something they can act on and "invalid code" is not.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        found = _coupon_by_code(conn, code)
        if found is None:
            return {"code": code.strip().upper(), "eligible": False,
                    "reason": "no coupon with this code"}
        coupon_id, promotion_id, status = found
        if status != "active":
            return {"code": code.strip().upper(), "eligible": False,
                    "reason": "this coupon has been revoked"}
        promotion = _promotion(conn, promotion_id)
        usage = _usage(conn, promotion_id, subject_id)
        verdict = promotions.check_eligibility(
            promotion, subtotal_minor=subtotal_minor, currency=currency.upper(),
            channel=channel, customer_segment=_segment_of(conn, subject_id),
            product_type=product_type, at=moment, usage=usage)
        discount = (
            promotions.discount_for(promotion, subtotal_minor) if verdict.ok else 0)
    return {"code": code.strip().upper(), "coupon_id": coupon_id,
            "promotion_key": promotion.promotion_key, "eligible": verdict.ok,
            "reason": verdict.reason or f"{promotion.promotion_key} is eligible",
            "reason_code": verdict.code, "discount_minor": discount}


# ---------------------------------------------------------------------- price resolution

def resolve_price(
    pool: Pool, tenant_id: str, *, variant_id: str, currency: str, actor_id: str,
    correlation_id: str, quantity: int = 1, channel: str = "any",
    location_id: str | None = None, subject_id: str | None = None,
    coupon_code: str | None = None, idempotency_key: str | None = None,
    at: datetime | None = None,
    override_amount_minor: int | None = None, override_reason: str | None = None,
    approval_id: str | None = None, store: bool = True,
) -> dict[str, Any]:
    """ResolvePrice: the number, and the whole reasoning, recorded.

    **The approval is checked against the database, not believed.** An override or a discount
    reaching the applicable threshold needs an `approval_id` that resolves to a real approval
    for *this variant* at *this list amount* -- so a caller cannot buy the authority by sending
    a uuid, which is the shape MOD-009's `consent_subject`, MOD-013's `bypass_policy_ref` and
    MOD-014's guardian field each shipped once. Paragraph 10220 asks for permission *and* audit;
    the permission is MOD-008's and this is the audit.

    **The dimensions that choose the price book are derived, not accepted.** `customer_segment`
    comes from the subject's tags and `brand_id` from the location -- see `_segment_of`, and the
    lookup below. Only `channel` is still the caller's word; it is bounded to `pricing.CHANNELS`
    and the gap is recorded in CLAUDE.md.

    **A coupon is redeemed in the same transaction as the resolution it discounts**, and that
    is the whole of this module's money correctness. The first version applied a coupon's
    discount here and wrote the redemption ledger on a *separate* route the caller was free
    never to call -- so the count every usage limit is measured against was never moved by the
    act the limit exists to bound, and a single-use 90% code priced six sales on a routine
    permission. It is MOD-010's `append_event` lesson, which takes a connection rather than a
    pool for exactly this reason: a control and the state it bounds commit together or the
    control is decoration. So storing a resolution that applies a coupon requires an
    `idempotency_key`, and the redemption is inserted beside the resolution carrying the
    discount this function actually computed.
    """
    moment = at or _now()

    with tenant_scope(pool, tenant_id) as conn:
        variant = conn.execute(
            "SELECT v.variant_key, p.product_type, p.status FROM plt01.cat_variants v"
            " JOIN plt01.cat_products p ON p.product_id = v.product_id"
            " WHERE v.variant_id = %s",
            (variant_id,),
        ).fetchone()
        if variant is None:
            raise NotFound("variant_not_found")
        # **Publication is what makes a thing sellable, and retirement is what stops it.** The
        # first version selected this status and never read it, so a product nobody had ever
        # published sold and a product explicitly retired went on selling -- which left
        # `catalog.product.publish` gating a flag and an event while buying nothing on the
        # sales path, and left retirement, the module's only stated way to withdraw something,
        # with no effect at all. COM-02-R07's "sales already made keep resolving" is about
        # re-deriving a historical resolution, not about opening a new sale of a withdrawn
        # product. The unused `p.status` select was the trace of the check that was intended.
        if str(variant[2]) != "published":
            raise Conflict(f"this_product_is_{variant[2]}_and_cannot_be_sold")

        customer_segment = _segment_of(conn, subject_id)
        brand_id: str | None = None
        if location_id is not None:
            # The hierarchy is MOD-004's fact and it is on this plane under this role, so it is
            # read here rather than taken from the caller beside the location -- MOD-008's
            # finding, where a brand-scoped manager reached another brand's location by sending
            # their own brand id next to it. Read on this connection rather than through
            # `tenancy.brand_of_location`, which opens a scope of its own and so could not be
            # part of this transaction.
            found_brand = conn.execute(
                "SELECT brand_id FROM plt01.locations WHERE location_id = %s",
                (location_id,),
            ).fetchone()
            if found_brand is None:
                raise NotFound("location_not_found")
            brand_id = str(found_brand[0])

        request = pricing.Request(
            variant_id=variant_id, currency=currency.upper(), at=moment, quantity=quantity,
            channel=channel, customer_segment=customer_segment, brand_id=brand_id,
            location_id=location_id, product_type=str(variant[1]), subject_id=subject_id)

        books = _price_books(conn)
        prices = _prices_for(conn, variant_id)
        candidates, presented_coupon = _applicable_promotions(conn, moment, coupon_code)
        if store and presented_coupon is not None and not (idempotency_key or "").strip():
            raise InvalidRequest("applying_a_coupon_needs_an_idempotency_key")
        # The subtotal promotions are measured against is the list total, which needs the price
        # first -- so the resolver runs twice: once to find the list, once with the discounts.
        try:
            baseline = pricing.resolve(request=request, books=books, prices=prices)
        except pricing.PricingError as e:
            raise Conflict(str(e)) from None
        usage = {
            promotion.promotion_key: _usage(conn, promotion_id, subject_id)
            for promotion_id, promotion in candidates
        }
        applied, verdicts = promotions.select(
            [promotion for _, promotion in candidates],
            subtotal_minor=baseline.list_amount_minor, currency=request.currency,
            channel=channel, customer_segment=customer_segment,
            product_type=str(variant[1]), at=moment, usage=usage)
        try:
            resolution = pricing.resolve(
                request=request, books=books, prices=prices, discounts=applied)
        except pricing.PricingError as e:
            raise Conflict(str(e)) from None

        if override_amount_minor is not None:
            try:
                resolution = pricing.override(
                    resolution, override_amount_minor=override_amount_minor,
                    reason=override_reason or "")
            except pricing.PricingError as e:
                raise InvalidRequest(str(e)) from None

        # What the presented code itself took, read from the applied list rather than from
        # the resolution's total. A coupon whose own verdict blocks a redemption is refused
        # outright: presenting a spent single-use code has to fail rather than quietly price
        # the sale without it.
        coupon_discount = 0
        if presented_coupon is not None:
            coupon_key = next(
                (p.promotion_key for pid, p in candidates
                 if pid == presented_coupon[1]), None)
            blocking = next(
                (v for v in verdicts
                 if v.promotion_key == coupon_key and not v.eligible), None)
            if blocking is not None:
                raise Conflict(blocking.reason)
            coupon_discount = next(
                (amount for key, amount, _ in applied if key == coupon_key), 0)

        threshold = promotions.highest_threshold_bp(
            [p for _, p in candidates], list(resolution.applied_promotions))
        needs = (override_amount_minor is not None
                 or pricing.needs_approval(resolution, threshold))
        if needs:
            if approval_id is None:
                raise Conflict(
                    "this_discount_needs_a_recorded_approval"
                    if override_amount_minor is None
                    else "a_manual_override_needs_a_recorded_approval")
            _check_approval(conn, approval_id, variant_id=variant_id,
                            list_amount_minor=resolution.list_amount_minor,
                            final_amount_minor=resolution.final_amount_minor,
                            currency=resolution.currency, at=moment)
        elif approval_id is not None:
            # **An approval nobody needed is not stored.** The first version validated the id
            # only inside the branch above and inserted it either way, so a resolution that
            # needed no approval at all could cite an unrelated one -- the foreign key asks
            # only that it exist in this tenant -- and the single table that *is* the audit
            # then read as though an approval had authorised a price it has nothing to do with.
            raise InvalidRequest("this_resolution_needs_no_approval")

        resolution_id: str | None = None
        if store:
            try:
                row = conn.execute(
                    """
                    INSERT INTO plt01.cat_price_resolutions
                        (tenant_id, variant_id, price_book_id, price_id, channel,
                         customer_segment, quantity, subject_id, resolved_at,
                         list_amount_minor, discount_minor, final_amount_minor, currency,
                         applied_promotions, rejected_promotions, explanation,
                         policy_version, approval_id, requested_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s)
                    RETURNING resolution_id
                    """,
                    (tenant_id, variant_id, resolution.price_book_id, resolution.price_id,
                     channel, customer_segment, quantity, subject_id, moment,
                     resolution.list_amount_minor, resolution.discount_minor,
                     resolution.final_amount_minor, resolution.currency,
                     list(resolution.applied_promotions),
                     list(resolution.rejected_promotions), list(resolution.explanation),
                     resolution.policy_version, approval_id, actor_id, correlation_id),
                ).fetchone()
            except errors.UniqueViolation:
                # `cat_price_resolutions_one_per_approval`. **An approval is spendable once**,
                # and the uniqueness lives on the citing side because this module's approval
                # table has no UPDATE grant and so cannot be marked consumed. Without it a
                # one-off goodwill decision was a standing authority to sell that variant at
                # that price for ever, exercisable by the cheapest permission in the module.
                raise Conflict("this_approval_has_already_been_used") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            assert row is not None
            resolution_id = str(row[0])
            if presented_coupon is not None and coupon_discount > 0:
                # **The coupon's own contribution, not the resolution's total.** Another
                # promotion may have taken part of the line, and the clamp may have reduced
                # what this one took -- the ledger records what this code was worth on this
                # sale, which is also what a reversal would have to give back.
                _record_redemption(
                    conn, tenant_id,
                    coupon_id=presented_coupon[0], promotion_id=presented_coupon[1],
                    subject_id=subject_id,
                    idempotency_key=(idempotency_key or "").strip(),
                    discount_minor=coupon_discount,
                    currency=resolution.currency, resolution_id=resolution_id,
                    actor_id=actor_id, correlation_id=correlation_id)
    return {
        "resolution_id": resolution_id,
        "variant_id": variant_id,
        "price_book_id": resolution.price_book_id,
        "price_id": resolution.price_id,
        "currency": resolution.currency,
        "list_amount_minor": resolution.list_amount_minor,
        "discount_minor": resolution.discount_minor,
        "final_amount_minor": resolution.final_amount_minor,
        "discount_bp": resolution.discount_bp,
        "applied_promotions": list(resolution.applied_promotions),
        "rejected_promotions": list(resolution.rejected_promotions),
        "explanation": list(resolution.explanation),
        "verdicts": [{"promotion_key": v.promotion_key, "eligible": v.eligible,
                      "reason": v.reason} for v in verdicts],
        "policy_version": resolution.policy_version,
    }


#: How long an approval stays spendable. Paragraph 10220 states no window, so this is a
#: judgement rather than a sourced fact -- and *some* window is required, because the
#: alternative is a standing authority. Twelve hours covers a shift, which is the unit of time
#: a till decision belongs to.
APPROVAL_VALID_FOR = timedelta(hours=12)


def request_discount(
    pool: Pool, tenant_id: str, *, variant_id: str, list_amount_minor: int,
    override_amount_minor: int, currency: str, reason: str, requester_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Ask for an override or a deep discount. The requester is the caller, derived.

    **This route exists because the separation of duties needs two acts.** The first version
    had one insert taking `requested_by` from the request body, with a CHECK comparing it to
    the approver -- and nothing relating it to any identity, session or request, because there
    was no request. So the control was satisfied by typing a uuid: three reviewers independently
    demonstrated one person approving their own 99.99% override and spending it in the same
    session, naming a requester who does not exist. MOD-008 does this correctly with
    `iam.approval_requests`: one identity creates the request, another decides it, and both rows
    are stored. Collapsing the two acts made the control unverifiable in principle rather than
    merely unverified.
    """
    if not reason.strip():
        raise InvalidRequest("a_request_states_a_reason")
    if list_amount_minor <= 0:
        raise InvalidRequest("a_request_measures_against_a_positive_list_price")
    if not 0 <= override_amount_minor <= list_amount_minor:
        raise InvalidRequest("an_override_is_between_zero_and_the_list_price")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_discount_requests
                    (tenant_id, variant_id, list_amount_minor, override_amount_minor,
                     currency, reason, requested_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING request_id
                """,
                (tenant_id, variant_id, list_amount_minor, override_amount_minor,
                 currency.upper(), reason, requester_id, correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("variant_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"request_id": str(row[0]), "variant_id": variant_id,
            "requested_by": requester_id}


def approve_discount(
    pool: Pool, tenant_id: str, *, request_id: str, reason: str, approver_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Approve a recorded request. Every figure comes from the request row.

    **Nothing here is taken from the body except the reason for the decision.** The variant,
    the list amount, the override and the currency are read from the request, so an approval
    cannot be issued for terms nobody asked for -- which is also what makes `requested_by`
    trustworthy, since it was derived from the requester's own session when the request was
    made. The schema's `approved_by <> requested_by` now compares two derived identities
    rather than one derived and one typed.

    The basis-point figure goes through `money.round_half_up`. The first version used
    `round(... * 10_000 / list)`, which is Python's banker's rounding on a float: it disagreed
    with the resolver's figure on ordinary inputs (list 20000, off 5 stored 2 where the
    resolver computes 3, and off 1 stored 0, which the route then refused as "no actual
    discount" for a real discount), and at the top of the allowed range the product exceeds
    float's exact-integer limit. `pricing.py` says `app.billing.money` is imported rather than
    reimplemented because a second rounding rule in one build is a pair of numbers that
    disagree on a receipt; this was that second rule.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("an_approval_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        asked = conn.execute(
            "SELECT variant_id, list_amount_minor, override_amount_minor, currency,"
            " requested_by FROM plt01.cat_discount_requests WHERE request_id = %s",
            (request_id,),
        ).fetchone()
        if asked is None:
            raise NotFound("request_not_found")
        variant_id = str(asked[0])
        list_amount_minor = int(asked[1])
        override_amount_minor = int(asked[2])
        currency = str(asked[3])
        requested_by = str(asked[4])
        discount_bp = money.round_half_up(
            (list_amount_minor - override_amount_minor) * money.BASIS_POINTS,
            list_amount_minor)
        if discount_bp <= 0:
            raise InvalidRequest("an_approval_covers_an_actual_discount")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_discount_approvals
                    (tenant_id, request_id, variant_id, list_amount_minor,
                     override_amount_minor, discount_bp, currency, reason, approved_by,
                     requested_by, expires_at, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING approval_id
                """,
                (tenant_id, request_id, variant_id, list_amount_minor,
                 override_amount_minor, discount_bp, currency, reason, approver_id,
                 requested_by, moment + APPROVAL_VALID_FOR, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_request_has_already_been_decided") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"approval_id": str(row[0]), "request_id": request_id,
            "variant_id": variant_id, "discount_bp": discount_bp,
            "approved_by": approver_id, "requested_by": requested_by,
            "expires_at": (moment + APPROVAL_VALID_FOR).isoformat()}


def _record_redemption(
    conn: Connection[Any], tenant_id: str, *, coupon_id: str, promotion_id: str,
    subject_id: str | None, idempotency_key: str, discount_minor: int, currency: str,
    resolution_id: str | None, actor_id: str, correlation_id: str,
    order_reference: str | None = None,
) -> tuple[str, bool]:
    """Insert one redemption, idempotently. Returns `(redemption_id, repeated)`.

    **`DO NOTHING` and then re-read, rather than catching the unique violation.** A caught
    `UniqueViolation` leaves the transaction aborted, so the SELECT that followed it raised
    `InFailedSqlTransaction` and a retried till request got a 500 instead of the idempotent
    answer. MOD-013's `_suppress` learned this the same way; found here by this module's own
    tests before review saw it.

    **The re-read is scoped to this coupon.** The key is unique per tenant, so a key reused
    across two different codes returned the *first* redemption with `repeated: True` -- telling
    the caller the second coupon had been redeemed when it had not, with another coupon's id
    beside the requested promotion key. A key that belongs to a different coupon is a conflict,
    not a repeat.
    """
    row = conn.execute(
        """
        INSERT INTO plt01.cat_coupon_redemptions
            (tenant_id, coupon_id, promotion_id, subject_id, order_reference,
             idempotency_key, discount_minor, currency, resolution_id, redeemed_by,
             correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        RETURNING redemption_id
        """,
        (tenant_id, coupon_id, promotion_id, subject_id, order_reference, idempotency_key,
         discount_minor, currency, resolution_id, actor_id, correlation_id),
    ).fetchone()
    if row is not None:
        return str(row[0]), False
    existing = conn.execute(
        "SELECT redemption_id, coupon_id FROM plt01.cat_coupon_redemptions"
        " WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    assert existing is not None
    if str(existing[1]) != coupon_id:
        raise Conflict("this_idempotency_key_belongs_to_another_coupon")
    return str(existing[0]), True


def redeem_coupon(
    pool: Pool, tenant_id: str, *, code: str, subtotal_minor: int, currency: str,
    idempotency_key: str, actor_id: str, correlation_id: str,
    subject_id: str | None = None, order_reference: str | None = None,
    channel: str = "any", at: datetime | None = None,
) -> dict[str, Any]:
    """RedeemCoupon, and publish `coupon.redeemed`.

    For a sale that does not go through `resolve_price` -- which redeems the coupon it applies
    in the same transaction as the resolution. Use that one wherever the price comes from this
    module; this exists for a caller that has its own subtotal and wants the code consumed.

    **The discount is computed here, never supplied.** The first version took
    `discount_minor` from the request body, so the ledger the module calls authoritative
    recorded whatever figure the caller typed -- a reviewer put 9,999,999,999.99 against a 5%
    coupon -- in a table with no UPDATE grant and therefore no correction path. It also passed
    that invented figure to the eligibility re-check as the subtotal, so a `minimum_spend` rule
    was compared against the discount rather than the sale.

    **The refusal is decided by reason code, never by words in the reason.** The first version
    tested `any(word in reason for word in ("redeemed", "revoked", "ended", "not started"))`,
    which made four English words the whole enforcement of every usage limit here: a draft
    promotion reads "is draft, not active" and matched none of them, so a code on a campaign
    nobody activated redeemed while `/catalog/promotions/validate` said it would not -- and a
    promotion keyed `extended.summer` contains "ended", so a benign rejection naming it refused
    a legitimate redemption. `Eligibility.blocks_redemption` asks the inverse question, so a
    code nobody thought about refuses.

    The basket conditions are still skipped, and that is deliberate and now explicit: a
    redemption does not have the basket, and re-evaluating a minimum spend against a subtotal
    this caller supplied would refuse nothing useful. `SKIPPABLE_AT_REDEMPTION` is the whole
    list of what may be skipped.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        found = _coupon_by_code(conn, code, for_update=True)
        if found is None:
            raise NotFound("coupon_not_found")
        coupon_id, promotion_id, status = found
        if status != "active":
            raise Conflict("this_coupon_has_been_revoked")
        promotion = _promotion(conn, promotion_id)
        usage = _usage(conn, promotion_id, subject_id)
        verdict = promotions.check_eligibility(
            promotion, subtotal_minor=subtotal_minor, currency=currency.upper(),
            channel=channel, customer_segment=_segment_of(conn, subject_id),
            product_type="", at=moment, usage=usage)
        blocking = verdict.blocks_redemption()
        if blocking is not None:
            raise Conflict(blocking.reason)
        discount_minor = promotions.discount_for(promotion, subtotal_minor)
        if discount_minor <= 0:
            raise Conflict("this_coupon_takes_nothing_off_this_sale")
        discount_minor = min(discount_minor, subtotal_minor)
        try:
            redemption_id, repeated = _record_redemption(
                conn, tenant_id, coupon_id=coupon_id, promotion_id=promotion_id,
                subject_id=subject_id, idempotency_key=idempotency_key.strip(),
                discount_minor=discount_minor, currency=currency.upper(),
                resolution_id=None, actor_id=actor_id, correlation_id=correlation_id,
                order_reference=order_reference)
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if not repeated:
            _append(conn, tenant_id, "coupon.redeemed", "coupon", coupon_id,
                    {"coupon_id": coupon_id, "promotion_id": promotion_id,
                     "redemption_id": redemption_id, "currency": currency.upper()},
                    correlation_id=correlation_id, actor_id=actor_id)
    return {"redemption_id": redemption_id, "coupon_id": coupon_id,
            "promotion_key": promotion.promotion_key,
            "discount_minor": discount_minor, "repeated": repeated}


# --------------------------------------------------------------------------------- bundles

def define_bundle(
    pool: Pool, tenant_id: str, *, product_id: str, items: list[dict[str, Any]],
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Declare what a sale of this product owes."""
    prepared = [
        bundles.Item(
            variant_id=str(item.get("variant_id", "")),
            quantity=int(item.get("quantity", 1)),
            fulfilment_kind=str(item.get("fulfilment_kind", "")))
        for item in items
    ]
    try:
        bundles.check_items(prepared)
    except bundles.BundleError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO plt01.cat_bundles (tenant_id, product_id, created_by,"
                " correlation_id) VALUES (%s, %s, %s, %s) RETURNING bundle_id",
                (tenant_id, product_id, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_product_is_already_a_bundle") from None
        except errors.ForeignKeyViolation:
            raise NotFound("product_not_found") from None
        assert row is not None
        bundle_id = str(row[0])
        for item in prepared:
            try:
                conn.execute(
                    "INSERT INTO plt01.cat_bundle_items (tenant_id, bundle_id, variant_id,"
                    " quantity, fulfilment_kind, created_by, correlation_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (tenant_id, bundle_id, item.variant_id, item.quantity,
                     item.fulfilment_kind, actor_id, correlation_id),
                )
            except errors.ForeignKeyViolation:
                raise NotFound("variant_not_found") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
        conn.execute(
            "UPDATE plt01.cat_bundles SET status = 'active' WHERE bundle_id = %s",
            (bundle_id,),
        )
    return {"bundle_id": bundle_id, "product_id": product_id, "items": len(prepared)}


def record_fulfilment(
    pool: Pool, tenant_id: str, *, bundle_id: str, variant_id: str, order_reference: str,
    quantity: int, outcome: str, idempotency_key: str, actor_id: str, correlation_id: str,
    subject_id: str | None = None, external_reference: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """FulfillBundle, as a record of what somebody says was delivered.

    **Nothing here delivers anything.** COM-01's entitlement grants and OPS-01's bookings are
    not built in this repository, so this is the ledger whatever does the work writes to -- with
    an actor on the row, because a `delivered` nobody signed is the fabricated-evidence shape
    this build has been bitten by five times.

    **A failure leaves the obligation standing and does not block the retry.** The first
    version carried `UNIQUE (tenant_id, order_reference, bundle_id, variant_id)` -- one row per
    item per order -- which `bundles.outstanding` and `check_fulfilment` both contradicted: they
    count only `delivered` rows and sum partial deliveries, neither of which that index allowed.
    So a transient provider failure recorded `failed`, and the retry was refused for ever: no
    UPDATE grant, no DELETE grant, and no second row permitted. The member had paid, the
    obligation stood, and no call in the module could satisfy it. Idempotency is keyed instead,
    as it is for a redemption, which is the half that index was actually providing.

    **And a mistaken delivery is reversed by a row, never an edit.** `reversed` subtracts, so
    the ledger stays insert-only -- MOD-015's credit note applied to an obligation. Without it
    a single `delivered` for the whole bundle was irreversible, which is why this permission is
    `financial` rather than routine: MOD-013's rule that irreversible state must not be
    declarable on a routine permission.
    """
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        item = conn.execute(
            "SELECT quantity, fulfilment_kind FROM plt01.cat_bundle_items"
            " WHERE bundle_id = %s AND variant_id = %s",
            (bundle_id, variant_id),
        ).fetchone()
        if item is None:
            raise NotFound("this_bundle_does_not_owe_this_variant")
        delivered = conn.execute(
            "SELECT coalesce(sum(CASE outcome WHEN 'delivered' THEN quantity"
            "                                 WHEN 'reversed' THEN -quantity"
            "                                 ELSE 0 END), 0)"
            " FROM plt01.cat_bundle_fulfilments"
            " WHERE bundle_id = %s AND variant_id = %s AND order_reference = %s",
            (bundle_id, variant_id, order_reference),
        ).fetchone()
        try:
            bundles.check_fulfilment(
                bundles.Item(variant_id, int(item[0]), str(item[1])),
                already_delivered=int(delivered[0]) if delivered else 0,
                quantity=quantity, outcome=outcome, detail=detail)
        except bundles.BundleError as e:
            raise Conflict(str(e)) from None
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cat_bundle_fulfilments
                    (tenant_id, bundle_id, variant_id, order_reference, subject_id, quantity,
                     outcome, idempotency_key, external_reference, detail, recorded_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING fulfilment_id
                """,
                (tenant_id, bundle_id, variant_id, order_reference, subject_id, quantity,
                 outcome, idempotency_key.strip(), external_reference, detail, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_fulfilment_was_already_recorded") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        _append(conn, tenant_id, "bundle.fulfilled", "bundle", bundle_id,
                # No `order_reference`: it is caller free text, and `evt_outbox.payload` is
                # the one store in this build that no erasure reaches. MOD-010's
                # `cfg_exposures.subject_id` and MOD-013's `notification.failed.reason` are
                # the same finding -- the restricted-field rule checks declared *names* and a
                # value carries anything.
                {"bundle_id": bundle_id, "variant_id": variant_id,
                 "fulfilment_id": str(row[0]), "outcome": outcome},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"fulfilment_id": str(row[0]), "bundle_id": bundle_id,
            "variant_id": variant_id, "outcome": outcome}


def bundle_status(
    pool: Pool, tenant_id: str, bundle_id: str, *, order_reference: str,
) -> dict[str, Any]:
    """What this sale of this bundle still owes."""
    with tenant_scope(pool, tenant_id) as conn:
        items = conn.execute(
            "SELECT variant_id, quantity, fulfilment_kind FROM plt01.cat_bundle_items"
            " WHERE bundle_id = %s ORDER BY variant_id",
            (bundle_id,),
        ).fetchall()
        if not items:
            raise NotFound("bundle_not_found")
        # Net of reversals, by the same expression `record_fulfilment` uses. Two readings of
        # the same ledger that disagreed would be worse than either.
        delivered = conn.execute(
            "SELECT variant_id,"
            " coalesce(sum(CASE outcome WHEN 'delivered' THEN quantity"
            "                           WHEN 'reversed' THEN -quantity"
            "                           ELSE 0 END), 0)"
            " FROM plt01.cat_bundle_fulfilments"
            " WHERE bundle_id = %s AND order_reference = %s"
            " GROUP BY variant_id",
            (bundle_id, order_reference),
        ).fetchall()
    counts = {str(r[0]): int(r[1]) for r in delivered}
    outstanding = bundles.outstanding(
        [bundles.Item(str(i[0]), int(i[1]), str(i[2])) for i in items], counts)
    return {"bundle_id": bundle_id, "order_reference": order_reference,
            "complete": all(o.remaining == 0 for o in outstanding),
            "items": [{"variant_id": o.variant_id, "fulfilment_kind": o.fulfilment_kind,
                       "owed": o.owed, "delivered": o.delivered,
                       "remaining": o.remaining} for o in outstanding]}


# --------------------------------------------------------------------------------- reads

def get_resolution(pool: Pool, tenant_id: str, resolution_id: str) -> dict[str, Any]:
    """One stored resolution with its whole explanation."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT variant_id, price_book_id, price_id, channel, customer_segment,"
            " quantity, resolved_at, list_amount_minor, discount_minor, final_amount_minor,"
            " currency, applied_promotions, rejected_promotions, explanation,"
            " policy_version FROM plt01.cat_price_resolutions"
            " WHERE resolution_id = %s",
            (resolution_id,),
        ).fetchone()
        if row is None:
            raise NotFound("resolution_not_found")
    return {"resolution_id": resolution_id, "variant_id": str(row[0]),
            "price_book_id": str(row[1]), "price_id": str(row[2]), "channel": row[3],
            "customer_segment": row[4], "quantity": int(row[5]),
            "resolved_at": row[6].isoformat(), "list_amount_minor": int(row[7]),
            "discount_minor": int(row[8]), "final_amount_minor": int(row[9]),
            "currency": row[10], "applied_promotions": list(row[11]),
            "rejected_promotions": list(row[12]), "explanation": list(row[13]),
            "policy_version": int(row[14])}


def list_price_books(pool: Pool, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT price_book_id, price_book_key, display_name, currency, channel,"
            " customer_segment, priority, status, effective_from, effective_to"
            " FROM plt01.cat_price_books ORDER BY price_book_key LIMIT %s",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [{"price_book_id": str(r[0]), "price_book_key": r[1], "display_name": r[2],
             "currency": r[3], "channel": r[4], "customer_segment": r[5],
             "priority": int(r[6]), "status": r[7],
             "effective_from": r[8].isoformat(),
             "effective_to": r[9].isoformat() if r[9] else None} for r in rows]


def list_promotions(pool: Pool, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT promotion_id, promotion_key, display_name, promotion_kind, percent_bp,"
            " amount_minor, currency, stacking_group, priority, approval_threshold_bp,"
            " status FROM plt01.cat_promotions ORDER BY promotion_key LIMIT %s",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [{"promotion_id": str(r[0]), "promotion_key": r[1], "display_name": r[2],
             "promotion_kind": r[3], "percent_bp": r[4],
             "amount_minor": int(r[5]) if r[5] is not None else None, "currency": r[6],
             "stacking_group": r[7], "priority": int(r[8]),
             "approval_threshold_bp": int(r[9]), "status": r[10]} for r in rows]


# ------------------------------------------------------------------------------ helpers

def _price_books(conn: Connection[Any]) -> list[pricing.PriceBook]:
    rows = conn.execute(
        "SELECT price_book_id, price_book_key, currency, effective_from, effective_to,"
        " brand_id, location_id, channel, customer_segment, priority, status"
        " FROM plt01.cat_price_books ORDER BY price_book_key"
    ).fetchall()
    return [pricing.PriceBook(
        price_book_id=str(r[0]), price_book_key=str(r[1]), currency=str(r[2]),
        effective_from=r[3], effective_to=r[4],
        brand_id=str(r[5]) if r[5] else None,
        location_id=str(r[6]) if r[6] else None,
        channel=str(r[7]), customer_segment=str(r[8]), priority=int(r[9]),
        status=str(r[10])) for r in rows]


def _prices_for(conn: Connection[Any], variant_id: str) -> list[pricing.Price]:
    rows = conn.execute(
        "SELECT price_id, price_book_id, variant_id, amount_minor, currency,"
        " effective_from, effective_to, superseded_by FROM plt01.cat_prices"
        " WHERE variant_id = %s ORDER BY price_id",
        (variant_id,),
    ).fetchall()
    return [pricing.Price(
        price_id=str(r[0]), price_book_id=str(r[1]), variant_id=str(r[2]),
        amount_minor=int(r[3]), currency=str(r[4]), effective_from=r[5],
        effective_to=r[6], superseded_by=str(r[7]) if r[7] else None) for r in rows]


def _promotion_row(conn: Connection[Any], row: Any) -> promotions.Promotion:
    rules = conn.execute(
        "SELECT rule_kind, amount_minor, quantity, text_value, date_from, date_to"
        " FROM plt01.cat_eligibility_rules WHERE promotion_id = %s"
        " ORDER BY rule_kind, rule_id",
        (str(row[0]),),
    ).fetchall()
    return promotions.Promotion(
        promotion_key=str(row[1]), kind=str(row[2]),
        percent_bp=int(row[3]) if row[3] is not None else None,
        amount_minor=int(row[4]) if row[4] is not None else None,
        currency=str(row[5]) if row[5] else None,
        stacking_group=str(row[6]), priority=int(row[7]),
        approval_threshold_bp=int(row[8]), status=str(row[9]),
        effective_from=row[10], effective_to=row[11],
        rules=tuple(promotions.Rule(
            kind=str(r[0]),
            amount_minor=int(r[1]) if r[1] is not None else None,
            quantity=int(r[2]) if r[2] is not None else None,
            text_value=str(r[3]) if r[3] else None,
            date_from=r[4], date_to=r[5]) for r in rules))


_PROMOTION_COLUMNS = (
    "promotion_id, promotion_key, promotion_kind, percent_bp, amount_minor, currency,"
    " stacking_group, priority, approval_threshold_bp, status, effective_from, effective_to"
)


def _promotion(conn: Connection[Any], promotion_id: str) -> promotions.Promotion:
    row = conn.execute(
        f"SELECT {_PROMOTION_COLUMNS} FROM plt01.cat_promotions WHERE promotion_id = %s",
        (promotion_id,),
    ).fetchone()
    if row is None:
        raise NotFound("promotion_not_found")
    return _promotion_row(conn, row)


def _applicable_promotions(
    conn: Connection[Any], at: datetime, coupon_code: str | None,
) -> tuple[list[tuple[str, promotions.Promotion]], tuple[str, str] | None]:
    """Every promotion that could apply, and the coupon that was presented.

    Returns `(candidates, coupon)` where `coupon` is `(coupon_id, promotion_id)` or None. The
    caller needs the coupon's identity, not only its promotion, because a resolution that
    applies a coupon writes the redemption that bounds it in the same transaction.

    **A coupon's promotion is only reachable with its code.** Loading every coupon promotion
    would apply a campaign to somebody who never presented the code, which is the discount
    nobody meant to give.

    **And a `manual` promotion is reachable by nothing**, which is the honest reading of a kind
    whose whole meaning is "somebody applies this by hand". The first version excluded only
    `coupon`, so a manual promotion was applied automatically to every sale -- the same defect
    a reviewer found for `staff_discount`, in the one kind where no targeting rule could fix it.
    The manual path in this module is `pricing.override`, which needs a recorded approval; a
    `manual` promotion is therefore storable and unreachable, and that is declared rather than
    quietly made automatic.

    **The coupon row is locked when a code is presented.** `_usage` counts the ledger and the
    insert follows, which under READ COMMITTED is a plain race: a reviewer ran six concurrent
    redemptions of a single-use code from a barrier and four were accepted. Locking the coupon
    serialises every redemption of *that* code and nothing else, which is the narrowest lock
    that makes the count it is compared against stable.
    """
    rows = conn.execute(
        f"SELECT {_PROMOTION_COLUMNS} FROM plt01.cat_promotions"
        " WHERE status = 'active' AND promotion_kind NOT IN ('coupon', 'manual')"
        "   AND effective_from <= %s AND (effective_to IS NULL OR effective_to > %s)"
        " ORDER BY promotion_key",
        (at, at),
    ).fetchall()
    found = [(str(r[0]), _promotion_row(conn, r)) for r in rows]
    presented: tuple[str, str] | None = None
    if coupon_code:
        coupon = _coupon_by_code(conn, coupon_code, for_update=True)
        if coupon is None:
            raise NotFound("coupon_not_found")
        if coupon[2] != "active":
            raise Conflict("this_coupon_has_been_revoked")
        row = conn.execute(
            f"SELECT {_PROMOTION_COLUMNS} FROM plt01.cat_promotions"
            " WHERE promotion_id = %s",
            (coupon[1],),
        ).fetchone()
        if row is None:
            raise NotFound("promotion_not_found")
        found.append((str(row[0]), _promotion_row(conn, row)))
        presented = (coupon[0], coupon[1])
    return found, presented


def _coupon_by_code(
    conn: Connection[Any], code: str, *, for_update: bool = False,
) -> tuple[str, str, str] | None:
    row = conn.execute(
        "SELECT coupon_id, promotion_id, status FROM plt01.cat_coupons WHERE code = %s"
        + (" FOR UPDATE" if for_update else ""),
        (code.strip().upper(),),
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]), str(row[2]))


def _usage(
    conn: Connection[Any], promotion_id: str, subject_id: str | None,
) -> promotions.Usage:
    """Redemption counts, from the ledger rather than from a counter column.

    `subject_known` is carried separately from `by_subject` because zero means two different
    things -- see `promotions.Usage`.
    """
    total = conn.execute(
        "SELECT count(*) FROM plt01.cat_coupon_redemptions WHERE promotion_id = %s",
        (promotion_id,),
    ).fetchone()
    by_subject = 0
    if subject_id is not None:
        row = conn.execute(
            "SELECT count(*) FROM plt01.cat_coupon_redemptions"
            " WHERE promotion_id = %s AND subject_id = %s",
            (promotion_id, subject_id),
        ).fetchone()
        by_subject = int(row[0]) if row else 0
    return promotions.Usage(total=int(total[0]) if total else 0, by_subject=by_subject,
                            subject_known=subject_id is not None)


def _segment_of(conn: Connection[Any], subject_id: str | None) -> str:
    """The customer segment this sale is in, **derived and never accepted**.

    COM-02-R02's dimensional matching decides which price book a sale prices from, so a caller
    able to state its own `customer_segment` can state the cheapest one: a review demonstrated
    a routine AAL-1 till session taking a 90% reduction by sending `"customer_segment":
    "staff"` beside an otherwise ordinary request, with the stored resolution citing the staff
    book as its authority. That is MOD-008's "derive a scope, never accept one" in this
    module's clothes, and the remedy is the same one -- ask the table that owns the answer.

    MOD-014 owns it. A segment is a tag on the person, so a sale for a named subject is in
    whatever segments that person's live tags say, and a sale for nobody is in `any`. The
    consequences, both deliberate:

    * **A segmented book is unreachable for an anonymous sale.** A walk-in has no person
      record, so a corporate rate cannot be applied to one. That is the correct direction: the
      alternative is letting the till say who it is selling to.
    * **One tag, chosen totally.** A person tagged both `staff` and `corporate` would otherwise
      make the book choice depend on which tag came back first. The lowest key wins, which is
      arbitrary but fixed, and `book_specificity` then scores it against one value.
    """
    if subject_id is None:
        return "any"
    row = conn.execute(
        "SELECT t.tag_key FROM plt01.ppl_person_tags pt"
        " JOIN plt01.ppl_tags t ON t.tag_id = pt.tag_id"
        " WHERE pt.person_id = %s AND pt.removed_at IS NULL AND t.retired_at IS NULL"
        " ORDER BY t.tag_key LIMIT 1",
        (subject_id,),
    ).fetchone()
    return str(row[0]) if row is not None else "any"


def _check_approval(
    conn: Connection[Any], approval_id: str, *, variant_id: str, list_amount_minor: int,
    final_amount_minor: int, currency: str, at: datetime,
) -> None:
    """Refuse an approval that does not cover **this** discount on **this** variant, now.

    An approval id that merely exists would be the authority bought with a body field -- the
    shape this repository has shipped three times. So the row has to name the same variant, the
    same list amount, the same currency, and an override at or below what is being charged: an
    approval for a deeper discount covers a shallower one, and one for a shallower discount
    does not cover a deeper one.

    **The currency is the third thing that makes an amount an amount.** The first version read
    the variant and the list figure and not the currency, so an approval reasoned, recorded and
    audited as "100.00 JOD down to 1.00 JOD" authorised "100.00 USD down to 1.00 USD" -- two
    minor-unit counts that are equal and mean different sums of money, which is the one
    comparison MOD-015's whole money discipline exists to forbid.

    **And an approval expires.** Without that, `_check_approval` passing was the only thing
    that ever happened to an approval: a one-off goodwill decision for one member became a
    standing authority to sell that variant at that price for ever, exercisable by the cheapest
    permission in the module. Single use is enforced one layer down, by a unique index on the
    resolution that cites it, because this table has no UPDATE grant and so cannot be marked.
    """
    row = conn.execute(
        "SELECT variant_id, list_amount_minor, override_amount_minor, currency, expires_at"
        " FROM plt01.cat_discount_approvals WHERE approval_id = %s",
        (approval_id,),
    ).fetchone()
    if row is None:
        raise NotFound("approval_not_found")
    if str(row[0]) != variant_id:
        raise Conflict("this_approval_is_for_another_variant")
    if int(row[1]) != list_amount_minor:
        raise Conflict("this_approval_was_measured_against_a_different_list_price")
    if str(row[3]) != currency:
        raise Conflict("this_approval_was_granted_in_another_currency")
    if row[4] is not None and row[4] <= at:
        raise Conflict("this_approval_has_expired")
    if final_amount_minor < int(row[2]):
        raise Conflict("this_approval_does_not_cover_a_discount_this_deep")


def today() -> date:
    """The date the eligibility rules compare a blackout window against."""
    return _now().date()
