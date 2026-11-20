import { describe, expect, it } from "vitest";

import {
  promotionIsLive,
  promotionValue,
  sellable,
  type CatalogPrice,
  type CatalogProduct,
  type ProductVariant,
  type Promotion,
} from "@/lib/catalog";

/**
 * The three judgements MOD-016's board makes, tested where they are made.
 *
 * **A status is not a window.** Nothing retires a promotion when its window closes -- the
 * resolver reads the window -- so `status: "active"` on a campaign that ended in February is
 * the ordinary state of that table, and a board showing the status alone says a campaign is
 * running when it is not.
 *
 * **A percentage is in basis points.** Rendering `percent_bp` would put `1000` on screen for
 * ten percent, which is the units mistake this build's money rules exist to prevent, one field
 * over.
 *
 * **A published product can stop being sellable without anything changing its status.**
 * `publish_product` refuses one with no live price and nothing re-checks afterwards, so a
 * price superseded later leaves a published product the till cannot sell.
 */

function promotion(over: Partial<Promotion>): Promotion {
  return {
    promotion_id: "pr1",
    promotion_key: "january",
    display_name: "January sale",
    promotion_kind: "automatic",
    percent_bp: 1000,
    amount_minor: null,
    currency: null,
    stacking_group: "default",
    priority: 0,
    approval_threshold_bp: 0,
    status: "active",
    effective_from: "2026-01-01T00:00:00+00:00",
    effective_to: null,
    in_window: true,
    ...over,
  };
}

function price(over: Partial<CatalogPrice>): CatalogPrice {
  return {
    price_id: "pz1",
    price_book_id: "b1",
    variant_id: "v1",
    amount_minor: 45000,
    currency: "JOD",
    effective_from: "2026-01-01T00:00:00+00:00",
    effective_to: null,
    superseded_by: null,
    superseded_at: null,
    price_book_key: "standard",
    price_book_status: "active",
    price_book_priority: 0,
    channel: "any",
    customer_segment: "any",
    variant_key: "monthly",
    product_id: "p1",
    in_window: true,
    ...over,
  };
}

const PRODUCT: CatalogProduct = {
  product_id: "p1",
  product_key: "gold",
  product_type: "membership",
  status: "published",
  merchandising_rank: 1000,
  display_name: "Gold membership",
  description: null,
  text_locale: "en",
};

const VARIANT: ProductVariant = {
  variant_id: "v1",
  variant_key: "monthly",
  display_name: "Monthly",
  entitlement_quantity: null,
  term_days: 30,
  sku: null,
  status: "active",
  merchandising_rank: 1000,
};

describe("promotionValue", () => {
  it("converts basis points to a percentage", () => {
    // 1000 bp is ten percent. Rendering the stored number would be off by a hundred.
    const worth = promotionValue(promotion({ percent_bp: 1000 }));
    expect(worth).toEqual({ kind: "percent", percent: 10 });
  });

  it("keeps a fixed amount in minor units, with its currency", () => {
    const worth = promotionValue(
      promotion({ percent_bp: null, amount_minor: 5000, currency: "JOD" }),
    );
    expect(worth).toEqual({ kind: "amount", minor: 5000, currency: "JOD" });
  });

  it("reports neither rather than guessing when both are absent", () => {
    // A constraint forbids this row, so reaching it means the data disagrees with the schema
    // -- and a surface that rendered 0% would be inventing a discount.
    expect(promotionValue(promotion({ percent_bp: null, amount_minor: null })).kind)
      .toBe("neither");
  });
});

describe("promotionIsLive", () => {
  it("needs both the status and the window", () => {
    expect(promotionIsLive(promotion({}))).toBe(true);
    // Active and over: the ordinary state of this table, and the one the board exists for.
    expect(promotionIsLive(promotion({ in_window: false }))).toBe(false);
    // In window and never activated.
    expect(promotionIsLive(promotion({ status: "draft" }))).toBe(false);
  });
});

describe("sellable", () => {
  it("says a published product with a live price can be sold", () => {
    expect(sellable(PRODUCT, [VARIANT], [price({})]).kind).toBe("sellable");
  });

  it("catches a published product whose only price was superseded", () => {
    // The state nothing in the backend re-checks: publication required a live price and a
    // later supersession took it away.
    expect(
      sellable(PRODUCT, [VARIANT], [price({ in_window: false, superseded_by: "pz2" })]).kind,
    ).toBe("no_live_price");
  });

  it("catches a price whose book was never activated", () => {
    expect(
      sellable(PRODUCT, [VARIANT], [price({ price_book_status: "draft" })]).kind,
    ).toBe("no_live_price");
  });

  it("does not count a price on a retired variant", () => {
    expect(
      sellable(PRODUCT, [{ ...VARIANT, status: "retired" }], [price({})]).kind,
    ).toBe("no_live_price");
  });

  it("says an unpublished product is unpublished rather than unpriced", () => {
    // Two different next actions: publish it, or write a price. Reporting the wrong one
    // sends somebody to the wrong form.
    expect(sellable({ ...PRODUCT, status: "draft" }, [VARIANT], [price({})]).kind)
      .toBe("not_published");
  });
});
