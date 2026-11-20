import { api } from "@/lib/api";

/**
 * MOD-016's reads, typed: what is for sale, what it costs and what is discounting it.
 *
 * **The hard part of this module is that there is no price lookup.** `resolve_price` is the
 * sale -- it redeems the coupon it applies -- so the one route that answers "what would this
 * cost" authoritatively cannot be called to find out. What a board can show is what was
 * *written*: the rows in each price book, their windows, and which book would win on
 * priority. Three things decide a sale's price and a stored row answers one of them, so every
 * read here says so rather than letting a figure read as "the price".
 *
 * **Three permissions, three blocks.** `catalog.product.read`, `catalog.price.read` and
 * `catalog.promotion.read` are separate and a reader may hold any subset -- a merchandiser
 * sees the products and not the margins. The product read deliberately carries no figure,
 * because a read that returned both would make "see the catalog" buy "see what every sale
 * costs", which is MOD-013's `GET /notifications/channels` finding one module over.
 */

export type CatalogProduct = {
  product_id: string;
  product_key: string;
  product_type: string;
  status: string;
  merchandising_rank: number;
  display_name: string | null;
  description: string | null;
  text_locale: string | null;
};

export type ProductVariant = {
  variant_id: string;
  variant_key: string;
  display_name: string;
  entitlement_quantity: number | null;
  term_days: number | null;
  sku: string | null;
  status: string;
  merchandising_rank: number;
};

export type ProductDetail = CatalogProduct & {
  tax_category_id: string | null;
  version: number;
  variants: ProductVariant[];
};

export type PriceBook = {
  price_book_id: string;
  price_book_key: string;
  display_name: string;
  currency: string;
  channel: string;
  customer_segment: string;
  priority: number;
  status: string;
  effective_from: string;
  effective_to: string | null;
};

export type CatalogPrice = {
  price_id: string;
  price_book_id: string;
  variant_id: string;
  amount_minor: number;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  superseded_by: string | null;
  superseded_at: string | null;
  price_book_key: string;
  price_book_status: string;
  price_book_priority: number;
  channel: string;
  customer_segment: string;
  variant_key: string;
  product_id: string;
  /** This row's own window only. The book must also be active and win on priority. */
  in_window: boolean;
};

export type Promotion = {
  promotion_id: string;
  promotion_key: string;
  display_name: string;
  promotion_kind: string;
  percent_bp: number | null;
  amount_minor: number | null;
  currency: string | null;
  stacking_group: string;
  priority: number;
  approval_threshold_bp: number;
  status: string;
  effective_from: string;
  effective_to: string | null;
  /** Derived by the server: nothing retires a promotion, the resolver reads the window. */
  in_window: boolean;
};

export function listProducts(): Promise<CatalogProduct[]> {
  return api("/catalog/products");
}

export function readProduct(productId: string): Promise<ProductDetail> {
  return api(`/catalog/products/${encodeURIComponent(productId)}`);
}

export function listPriceBooks(): Promise<PriceBook[]> {
  return api("/catalog/price-books");
}

export function listPrices(variantIds: string[]): Promise<CatalogPrice[]> {
  // One request per variant rather than one unfiltered page: a tenant's whole price list can
  // be long and a board only ever shows the product somebody opened.
  return Promise.all(
    variantIds.map((id) =>
      api<{ prices: CatalogPrice[] }>(
        `/catalog/prices?variant_id=${encodeURIComponent(id)}`,
      ).then((page) => page.prices),
    ),
  ).then((pages) => pages.flat());
}

export function listPromotions(): Promise<Promotion[]> {
  return api("/catalog/promotions");
}

/**
 * What a promotion is worth, as the kind of figure it actually is.
 *
 * A promotion is either a percentage in basis points or an amount in minor units, never both
 * and never neither -- a constraint, not a convention. Rendering `percent_bp` as a number
 * would put `1000` on screen for ten percent, which is the units mistake MOD-015's money rules
 * exist to prevent, one field over.
 */
export function promotionValue(
  promotion: Promotion,
): { kind: "percent"; percent: number } | { kind: "amount"; minor: number; currency: string }
  | { kind: "neither" } {
  if (promotion.percent_bp !== null) {
    return { kind: "percent", percent: promotion.percent_bp / 100 };
  }
  if (promotion.amount_minor !== null && promotion.currency !== null) {
    return { kind: "amount", minor: promotion.amount_minor, currency: promotion.currency };
  }
  return { kind: "neither" };
}

/**
 * Whether a promotion is actually discounting anything right now.
 *
 * Two facts and not one: a promotion has a status somebody set and a window the resolver
 * reads, and nothing retires it when the window closes. `status: "active"` on a campaign that
 * ended in March is the ordinary state of this table, so a board showing the status alone says
 * a campaign is running when it is not.
 */
export function promotionIsLive(promotion: Promotion): boolean {
  return promotion.status === "active" && promotion.in_window;
}

/**
 * Whether a published product could actually be sold.
 *
 * `publish_product` refuses a product with no live price, counted over active books and live
 * windows -- so a published product whose only price has been superseded or whose book was
 * never activated is a till that stops working. The check is at publication and nothing
 * re-checks it afterwards, which is exactly the gap a board can close by looking.
 */
export function sellable(
  product: CatalogProduct,
  variants: ProductVariant[],
  prices: CatalogPrice[],
): { kind: "sellable" | "no_live_price" | "not_published" } {
  if (product.status !== "published") return { kind: "not_published" };
  const live = prices.some(
    (p) =>
      p.in_window &&
      p.price_book_status === "active" &&
      variants.some((v) => v.variant_id === p.variant_id && v.status === "active"),
  );
  return { kind: live ? "sellable" : "no_live_price" };
}
