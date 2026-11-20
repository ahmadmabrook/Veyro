import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  listPriceBooks,
  listPrices,
  listProducts,
  listPromotions,
  promotionIsLive,
  promotionValue,
  readProduct,
  sellable,
  type CatalogPrice,
  type CatalogProduct,
  type PriceBook,
  type ProductDetail,
  type Promotion,
} from "@/lib/catalog";
import { money } from "@/lib/membership";
import { presentation } from "@/lib/preferences";

/**
 * MOD-016's board: what is for sale, what it costs, and what is discounting it.
 *
 * **No figure on this page is "the price", and that is the hard part of the module.**
 * `resolve_price` is the sale -- it redeems the coupon it applies -- so the one route that
 * answers authoritatively cannot be called to find out. Three things decide what a sale
 * costs: the price row's own window, whether its book is active, and whether that book wins
 * the priority comparison against every other book matching the sale's seven dimensions. A
 * stored row answers the first. The page says so rather than letting a number read as a
 * promise.
 *
 * **Three permissions, three blocks.** A merchandiser may see the products and not the
 * margins, so `catalog.product.read`, `catalog.price.read` and `catalog.promotion.read` are
 * asked separately and a refused block says it was refused rather than rendering empty.
 *
 * **A published product with no live price is the state worth finding.** `publish_product`
 * refuses one at publication and nothing re-checks afterwards, so a price superseded later --
 * or a book nobody activated -- leaves a published product that cannot be sold. The board
 * computes that from what it already has.
 */
export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<{ product?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const chosen = await searchParams;

  if (!(await currentSession())) redirect("/login");

  const [mayProducts, mayPrices, mayPromotions] = await Promise.all([
    gate("catalog.product.read"),
    gate("catalog.price.read"),
    gate("catalog.promotion.read"),
  ]);

  if (!mayProducts.allowed && !mayPrices.allowed && !mayPromotions.allowed) {
    return (
      <Shell locale={locale}>
        <Alert tone="info">
          {mayProducts.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Alert>
      </Shell>
    );
  }

  let products: CatalogProduct[] = [];
  let books: PriceBook[] = [];
  let promotions: Promotion[] = [];
  let failed = false;
  try {
    [products, books, promotions] = await Promise.all([
      mayProducts.allowed ? listProducts() : Promise.resolve([]),
      mayPrices.allowed ? listPriceBooks() : Promise.resolve([]),
      mayPromotions.allowed ? listPromotions() : Promise.resolve([]),
    ]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  let detail: ProductDetail | null = null;
  let prices: CatalogPrice[] = [];
  if (chosen.product && mayProducts.allowed) {
    try {
      detail = await readProduct(chosen.product);
      if (mayPrices.allowed) {
        prices = await listPrices(detail.variants.map((v) => v.variant_id));
      }
    } catch {
      // A link naming a product that is gone is not a broken page. The block says so and the
      // rest of the board still renders, because somebody came here for the catalogue.
      detail = null;
    }
  }

  return (
    <Shell locale={locale}>
      {failed ? <Alert tone="error">{text("error.unexpected")}</Alert> : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("catalog.products")}</h2>
        {!mayProducts.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : products.length === 0 ? (
          <Alert tone="info">{text("catalog.noProducts")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("catalog.products")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("catalog.product")}</th>
                <th scope="col" style={head}>{text("catalog.type")}</th>
                <th scope="col" style={head}>{text("catalog.status")}</th>
                <th scope="col" style={head}>{text("catalog.rank")}</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.product_id}>
                  <td style={cell}>
                    <Link href={`/catalog?product=${product.product_id}`}>
                      {product.display_name ?? product.product_key}
                    </Link>
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{product.product_key}</span>
                    </div>
                  </td>
                  <td style={cell}>{product.product_type}</td>
                  <td style={cell}>{product.status}</td>
                  <td style={cell}>
                    <span className="data">
                      {formatInteger(product.merchandising_rank, "latn")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {detail === null ? null : (
        <section className="panel stack">
          <h2 style={{ margin: 0 }}>
            {detail.display_name ?? detail.product_key}
          </h2>
          <Verdict
            locale={locale}
            verdict={sellable(detail, detail.variants, prices).kind}
            mayPrices={mayPrices.allowed}
          />
          {detail.variants.length === 0 ? (
            <Alert tone="info">{text("catalog.noVariants")}</Alert>
          ) : (
            <table
              tabIndex={0}
              style={{ width: "100%", borderCollapse: "collapse" }}
              aria-label={text("catalog.variants")}
            >
              <thead>
                <tr>
                  <th scope="col" style={head}>{text("catalog.variant")}</th>
                  <th scope="col" style={head}>{text("catalog.grants")}</th>
                  <th scope="col" style={head}>{text("catalog.status")}</th>
                  <th scope="col" style={head}>{text("catalog.written")}</th>
                </tr>
              </thead>
              <tbody>
                {detail.variants.map((variant) => {
                  const rows = prices.filter((p) => p.variant_id === variant.variant_id);
                  return (
                    <tr key={variant.variant_id}>
                      <td style={cell}>
                        {variant.display_name}
                        <div className="muted" style={caption}>
                          <span className="data" dir="ltr">{variant.variant_key}</span>
                        </div>
                      </td>
                      <td style={cell}>
                        {variant.entitlement_quantity === null
                          ? variant.term_days === null
                            ? <span className="muted">—</span>
                            : `${formatInteger(variant.term_days, "latn")} ${text("catalog.days")}`
                          : `${formatInteger(variant.entitlement_quantity, "latn")} ${text("catalog.uses")}`}
                      </td>
                      <td style={cell}>{variant.status}</td>
                      <td style={cell}>
                        {!mayPrices.allowed ? (
                          <span className="muted">{text("gate.denied")}</span>
                        ) : rows.length === 0 ? (
                          <span className="muted">{text("catalog.noPrice")}</span>
                        ) : (
                          rows.map((price) => (
                            <div key={price.price_id}>
                              <span className="data" dir="ltr">
                                {money(price.amount_minor, price.currency)}
                              </span>
                              <div className="muted" style={caption}>
                                <span className="data" dir="ltr">
                                  {price.price_book_key}
                                </span>
                                {" · "}
                                {price.in_window && price.price_book_status === "active"
                                  ? text("catalog.inWindow")
                                  : text("catalog.notInForce")}
                              </div>
                            </div>
                          ))
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {mayPrices.allowed ? (
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("catalog.notThePrice")}
            </p>
          ) : null}
        </section>
      )}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("catalog.books")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("catalog.booksLead")}
        </p>
        {!mayPrices.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : books.length === 0 ? (
          <Alert tone="info">{text("catalog.noBooks")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("catalog.books")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("catalog.book")}</th>
                <th scope="col" style={head}>{text("catalog.dimensions")}</th>
                <th scope="col" style={head}>{text("catalog.priority")}</th>
                <th scope="col" style={head}>{text("catalog.status")}</th>
              </tr>
            </thead>
            <tbody>
              {books.map((book) => (
                <tr key={book.price_book_id}>
                  <td style={cell}>
                    {book.display_name}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">
                        {book.price_book_key} · {book.currency}
                      </span>
                    </div>
                  </td>
                  <td style={cell}>
                    {book.channel}
                    {" · "}
                    {book.customer_segment}
                  </td>
                  <td style={cell}>
                    <span className="data">
                      {formatInteger(book.priority, "latn")}
                    </span>
                  </td>
                  <td style={cell}>{book.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("catalog.promotions")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("catalog.promotionsLead")}
        </p>
        {!mayPromotions.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : promotions.length === 0 ? (
          <Alert tone="info">{text("catalog.noPromotions")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("catalog.promotions")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("catalog.promotion")}</th>
                <th scope="col" style={head}>{text("catalog.worth")}</th>
                <th scope="col" style={head}>{text("catalog.status")}</th>
                <th scope="col" style={head}>{text("catalog.window")}</th>
              </tr>
            </thead>
            <tbody>
              {promotions.map((promotion) => {
                const worth = promotionValue(promotion);
                return (
                  <tr key={promotion.promotion_id}>
                    <td style={cell}>
                      {promotion.display_name}
                      <div className="muted" style={caption}>
                        <span className="data" dir="ltr">{promotion.promotion_key}</span>
                        {" · "}
                        {promotion.promotion_kind}
                      </div>
                    </td>
                    <td style={cell}>
                      {worth.kind === "percent" ? (
                        // **Not the basis points.** `1000` on screen for ten percent is the
                        // units mistake this build's money rules exist to prevent.
                        <span className="data" dir="ltr">{worth.percent}%</span>
                      ) : worth.kind === "amount" ? (
                        <span className="data" dir="ltr">
                          {money(worth.minor, worth.currency)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td style={cell}>
                      {promotionIsLive(promotion)
                        ? text("catalog.discountingNow")
                        : text("catalog.notDiscounting")}
                      <div className="muted" style={caption}>{promotion.status}</div>
                    </td>
                    <td style={cell}>
                      <span className="data" dir="ltr">
                        {promotion.effective_from.slice(0, 10)}
                        {promotion.effective_to === null
                          ? " →"
                          : ` → ${promotion.effective_to.slice(0, 10)}`}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {mayPromotions.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("catalog.nothingRetires")}
          </p>
        ) : null}
      </section>
    </Shell>
  );
}

/** Whether a published product could actually be sold, as a sentence. */
function Verdict({
  locale,
  verdict,
  mayPrices,
}: {
  locale: Locale;
  verdict: "sellable" | "no_live_price" | "not_published";
  mayPrices: boolean;
}) {
  // Without the price read there is nothing to base the verdict on, and asserting one would
  // be a claim built from half the facts.
  if (!mayPrices) return null;
  if (verdict === "sellable") {
    return <Alert tone="success">{t(locale, "catalog.sellable")}</Alert>;
  }
  if (verdict === "not_published") {
    return <Alert tone="info">{t(locale, "catalog.notPublished")}</Alert>;
  }
  return <Alert tone="warning">{t(locale, "catalog.noLivePrice")}</Alert>;
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "catalog.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "catalog.lead")}
      </p>
      {children}
    </div>
  );
}

const head: React.CSSProperties = {
  textAlign: "start",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-default)",
  background: "var(--color-surface-sunken)",
  fontSize: "var(--type-label-size)",
  fontWeight: "var(--type-label-weight)",
};

const cell: React.CSSProperties = {
  textAlign: "start",
  verticalAlign: "top",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};

const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };
