import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll } from "@/lib/api";
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

  // One round trip rather than several: `/authz/checks` asks the same question about
  // every action at once, with the same scope resolution and the same assurance weighing.
  // The semantics are identical -- it is not a permission list, which would be MOD-014's
  // "a grant is not a session" finding.
  const [mayProducts, mayPrices, mayPromotions] = await gateAll([
    "catalog.product.read",
    "catalog.price.read",
    "catalog.promotion.read",
  ] as const);

  if (!mayProducts.allowed && !mayPrices.allowed && !mayPromotions.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {mayProducts.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Banner>
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
    <Shell
      locale={locale}
      figures={
        <>
          {fill(locale, "catalog.productsCounted", { count: products.length })}
          {" \u00b7 "}
          {fill(locale, "catalog.booksCounted", { count: books.length })}
          {" \u00b7 "}
          {fill(locale, "catalog.promotionsCounted", { count: promotions.length })}
        </>
      }
    >
      {failed ? <Banner severity="critical">{text("error.unexpected")}</Banner> : null}

      <section className="page-section">
        <h2 id="products-heading" style={{ margin: 0 }}>{text("catalog.products")}</h2>
        {!mayProducts.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : products.length === 0 ? (
          <Banner severity="info">{text("catalog.noProducts")}</Banner>
        ) : (
          <DataGrid
            caption={text("catalog.products")}
            labelledBy="products-heading"
            rows={products}
            rowKey={(product) => product.product_id}
            // A published product with no live price cannot be sold and nothing on the server
            // notices, so the board is where that shows -- but the price read is a different
            // gate, so the mark stays on the product page rather than guessed at here.
            rowSeverity={(product) => (product.status === "published" ? null : "attention")}
            columns={[
              {
                header: text("catalog.product"),
                kind: "text",
                priority: 1,
                render: (product) => (
                  <>
                    <Link href={`/catalog?product=${product.product_id}`}>
                      {product.display_name ?? product.product_key}
                    </Link>
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{product.product_key}</span>
                    </div>
                  </>
                ),
              },
              {
                header: text("catalog.status"),
                kind: "status",
                priority: 1,
                render: (product) => product.status,
              },
              {
                header: text("catalog.type"),
                kind: "text",
                priority: 2,
                render: (product) => product.product_type,
              },
              {
                header: text("catalog.rank"),
                kind: "text",
                priority: 3,
                render: (product) => (
                  <span className="data">
                    {formatInteger(product.merchandising_rank, "latn")}
                  </span>
                ),
              },
            ]}
          />
        )}
      </section>

      {detail === null ? null : (
        <section className="page-section">
          <h2 id="variants-heading" style={{ margin: 0 }}>
            {detail.display_name ?? detail.product_key}
          </h2>
          <Verdict
            locale={locale}
            verdict={sellable(detail, detail.variants, prices).kind}
            mayPrices={mayPrices.allowed}
          />
          {detail.variants.length === 0 ? (
            <Banner severity="info">{text("catalog.noVariants")}</Banner>
          ) : (
            <DataGrid
              caption={text("catalog.variants")}
              labelledBy="variants-heading"
              rows={detail.variants}
              rowKey={(variant) => variant.variant_id}
              columns={[
                {
                  header: text("catalog.variant"),
                  kind: "text",
                  priority: 1,
                  render: (variant) => (
                    <>
                      {variant.display_name}
                      <div className="muted" style={caption}>
                        <span className="data" dir="ltr">{variant.variant_key}</span>
                      </div>
                    </>
                  ),
                },
                {
                  header: text("catalog.written"),
                  kind: "money",
                  // Priority 1: a row in its window is not the resolved price, and a variant
                  // with no price at all is the thing somebody opened this page to find.
                  priority: 1,
                  // The price read is its own gate, so a reader who holds the product read
                  // and not the price read is told so rather than shown an empty cell.
                  restricted: () => !mayPrices.allowed,
                  render: (variant) => {
                    const rows = prices.filter((p) => p.variant_id === variant.variant_id);
                    return rows.length === 0 ? (
                      <span className="muted">{text("catalog.noPrice")}</span>
                    ) : (
                      rows.map((price) => (
                        <div key={price.price_id}>
                          <span className="data" dir="ltr">
                            {money(price.amount_minor, price.currency)}
                          </span>
                          <div className="muted" style={caption}>
                            <span className="data" dir="ltr">{price.price_book_key}</span>
                            {" · "}
                            {price.in_window && price.price_book_status === "active"
                              ? text("catalog.inWindow")
                              : text("catalog.notInForce")}
                          </div>
                        </div>
                      ))
                    );
                  },
                },
                {
                  header: text("catalog.grants"),
                  kind: "text",
                  priority: 2,
                  render: (variant) =>
                    variant.entitlement_quantity === null
                      ? variant.term_days === null
                        ? <span className="muted">—</span>
                        : `${formatInteger(variant.term_days, "latn")} ${text("catalog.days")}`
                      : `${formatInteger(variant.entitlement_quantity, "latn")} ${text("catalog.uses")}`,
                },
                {
                  header: text("catalog.status"),
                  kind: "status",
                  priority: 3,
                  render: (variant) => variant.status,
                },
              ]}
            />
          )}
          {mayPrices.allowed ? (
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("catalog.notThePrice")}
            </p>
          ) : null}
        </section>
      )}

      <section className="page-section">
        <h2 id="books-heading" style={{ margin: 0 }}>{text("catalog.books")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("catalog.booksLead")}
        </p>
        {!mayPrices.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : books.length === 0 ? (
          <Banner severity="info">{text("catalog.noBooks")}</Banner>
        ) : (
          <DataGrid
            caption={text("catalog.books")}
            labelledBy="books-heading"
            rows={books}
            rowKey={(book) => book.price_book_id}
            rowSeverity={(book) => (book.status === "active" ? null : "attention")}
            columns={[
              {
                header: text("catalog.book"),
                kind: "text",
                priority: 1,
                render: (book) => (
                  <>
                    {book.display_name}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">
                        {book.price_book_key} · {book.currency}
                      </span>
                    </div>
                  </>
                ),
              },
              {
                header: text("catalog.status"),
                kind: "status",
                priority: 1,
                render: (book) => book.status,
              },
              {
                header: text("catalog.dimensions"),
                kind: "text",
                priority: 2,
                render: (book) => `${book.channel} · ${book.customer_segment}`,
              },
              {
                header: text("catalog.priority"),
                kind: "text",
                // The priority comparison is what the board cannot do, so the number is here
                // and the page says it is not the resolved price.
                priority: 3,
                render: (book) => (
                  <span className="data">{formatInteger(book.priority, "latn")}</span>
                ),
              },
            ]}
          />
        )}
      </section>

      <section className="page-section">
        <h2 id="promotions-heading" style={{ margin: 0 }}>{text("catalog.promotions")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("catalog.promotionsLead")}
        </p>
        {!mayPromotions.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : promotions.length === 0 ? (
          <Banner severity="info">{text("catalog.noPromotions")}</Banner>
        ) : (
          <DataGrid
            caption={text("catalog.promotions")}
            labelledBy="promotions-heading"
            rows={promotions}
            rowKey={(promotion) => promotion.promotion_id}
            // Nothing retires a promotion when its window closes -- the resolver reads the
            // window -- so `status: active` on a campaign that ended in February is the
            // ordinary state of that table, and the row says which it is.
            rowSeverity={(promotion) => (promotionIsLive(promotion) ? null : "attention")}
            columns={[
              {
                header: text("catalog.promotion"),
                kind: "text",
                priority: 1,
                render: (promotion) => (
                  <>
                    {promotion.display_name}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{promotion.promotion_key}</span>
                      {" · "}
                      {promotion.promotion_kind}
                    </div>
                  </>
                ),
              },
              {
                header: text("catalog.status"),
                kind: "status",
                priority: 1,
                render: (promotion) => (
                  <>
                    {promotionIsLive(promotion)
                      ? text("catalog.discountingNow")
                      : text("catalog.notDiscounting")}
                    <div className="muted" style={caption}>{promotion.status}</div>
                  </>
                ),
              },
              {
                header: text("catalog.worth"),
                kind: "money",
                priority: 1,
                render: (promotion) => {
                  const worth = promotionValue(promotion);
                  return worth.kind === "percent" ? (
                    // **Not the basis points.** `1000` on screen for ten percent is the units
                    // mistake this build's money rules exist to prevent.
                    <span className="data" dir="ltr">{worth.percent}%</span>
                  ) : worth.kind === "amount" ? (
                    <span className="data" dir="ltr">{money(worth.minor, worth.currency)}</span>
                  ) : (
                    <span className="muted">—</span>
                  );
                },
              },
              {
                header: text("catalog.window"),
                kind: "date",
                priority: 2,
                render: (promotion) => (
                  <span className="data" dir="ltr">
                    {promotion.effective_from.slice(0, 10)}
                    {promotion.effective_to === null
                      ? " →"
                      : ` → ${promotion.effective_to.slice(0, 10)}`}
                  </span>
                ),
              },
            ]}
          />
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
    return <Banner severity="neutral">{t(locale, "catalog.sellable")}</Banner>;
  }
  if (verdict === "not_published") {
    return <Banner severity="info">{t(locale, "catalog.notPublished")}</Banner>;
  }
  return <Banner severity="attention">{t(locale, "catalog.noLivePrice")}</Banner>;
}

function Shell({
  locale,
  children,
  figures,
}: {
  locale: Locale;
  children: React.ReactNode;
  /**
   * The counts under the title.
   *
   * **The design's page header is a title and a line of figures, never a paragraph**, and
   * every drawn canvas does the same: "4,812 active · 312 expired · 68 frozen · all
   * locations". A board whose header carried only its own name made a reader scroll to find
   * out whether anything on it needed them.
   */
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader title={t(locale, "catalog.title")} {...(figures ? { figures } : {})} />
      {children}
      {/* **The lead paragraph moved to the foot.** The design's page header is a title and a
          line of figures -- every drawn canvas does the same -- so an explanation of what the
          screen is was pushing the data a manager opens the page for below the fold. What is
          kept is the half that is a product disclosure rather than a description, and it
          answers a question here instead of delaying one. */}
      <p className="ds-screen-note">{t(locale, "catalog.lead")}</p>
    </div>
  );
}



const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };
