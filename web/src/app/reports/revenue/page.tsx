import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, failureMessage } from "@/lib/api";
import { listLegalEntities, type LegalEntity } from "@/lib/organization";
import { presentation } from "@/lib/preferences";
import {
  change,
  readRevenueReport,
  sourceName,
  type RevenueCurrency,
  type RevenueReport,
  type SourceRow,
} from "@/lib/reports";

/**
 * ADM-RPT-02 · REVENUE — "Revenue · month to date".
 *
 * **Four columns, because the canvas gives the reason in its own words**: "Collected and
 * invoiced are separate columns because they are separate facts. A report showing one number
 * labelled 'revenue' is the reason operators cannot reconcile their own books." Collected is
 * money received, invoiced is money billed, outstanding is what those invoices still owe and
 * refunded is what went back. A tenant that invoiced 41,592 and collected 41,280 is owed
 * 312, and only a report carrying both can say that.
 *
 * Three things this screen decides rather than copies:
 *
 * - **Outstanding carries no comparison, and says why.** The other three are flows and have
 *   a same-point-last-month figure; outstanding is a *position* -- what this month's invoices
 *   owe as of now. The comparable number is a balance as it stood a month ago, which is a
 *   different question. Rendering a delta there would be a figure nobody could reproduce.
 * - **BY SOURCE is the catalogue's own vocabulary.** The canvas's rows are Memberships,
 *   Personal training, Classes and Retail; an invoice line carries a variant, a variant
 *   belongs to a product and a product has one of COM-02-R01's eight types. So the split is a
 *   join. A line raised by hand has no variant and gets its own row rather than being dropped
 *   or guessed at -- which is what makes the sources add up to the invoiced total, the one
 *   property a reader checks a breakdown against.
 * - **The columns are legal entities, not clubs**, and the page says so. The money chain
 *   carries a billing account's legal entity; MOD-004's hierarchy puts brands and locations
 *   *under* one, so several clubs under a single entity are one column. Relabelling it
 *   "club" would be a confident wrong answer on a revenue report.
 *
 * **There is no Export button**, which is ADM-RPT-05 and the index's own note: the tier-4
 * gate in front of an export is the feature, and a button that produced a file without the
 * recorded reason would be the control removed rather than the feature added.
 */
export default async function RevenueReportPage() {
  const { locale } = await presentation();
  const numbering = "latn" as const;
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("finance.revenue.read");
  if (!may.allowed) {
    return (
      <>
        <PageHeader title={text("revenue.heading")} />
        <Banner severity="info">{text("revenue.refusedWhy")}</Banner>
      </>
    );
  }

  let report: RevenueReport | null = null;
  let failed: MessageKey | null = null;
  try {
    report = await readRevenueReport();
  } catch (error) {
    failed = failureMessage(error);
  }

  // **Naming the entity needs a different permission from reading the money**, exactly as on
  // `/finance` and the Command Center: `tenancy.organization.read` is MOD-004's. Looked up
  // where it can be, the id shown where it cannot.
  let entities: LegalEntity[] = [];
  if ((await gate("tenancy.organization.read")).allowed) {
    try {
      entities = await listLegalEntities();
    } catch {
      entities = [];
    }
  }

  if (report === null) {
    return (
      <>
        <PageHeader title={text("revenue.heading")} />
        <Banner severity="critical">{text(failed ?? "error.unexpected")}</Banner>
      </>
    );
  }

  const current = report;

  return (
    <>
      <PageHeader
        title={text("revenue.heading")}
        figures={
          <span className="data" dir="ltr">
            {fill(locale, "revenue.scope", { date: current.as_of })}
          </span>
        }
      />

      {current.comparable_previous_month.clamped ? (
        <Banner severity="info">{text("revenue.clamped")}</Banner>
      ) : null}

      {current.currencies.length === 0 ? (
        <Banner severity="info">{text("revenue.empty")}</Banner>
      ) : (
        current.currencies.map((block) => (
          <CurrencyBlock
            key={block.currency}
            block={block}
            report={current}
            locale={locale}
            numbering={numbering}
            entities={entities}
          />
        ))
      )}

      <ProseNote>{text("revenue.separateFacts")}</ProseNote>
      <ProseNote>{text("revenue.sourcesAreNet")}</ProseNote>
      <ProseNote>{text("revenue.positionNote")}</ProseNote>
      <ProseNote>{text("reports.unattributedWhy")}</ProseNote>
      <ProseNote>{text("reports.entityNotClub")}</ProseNote>
    </>
  );
}

function CurrencyBlock({
  block,
  report,
  locale,
  numbering,
  entities,
}: {
  block: RevenueCurrency;
  report: RevenueReport;
  locale: Locale;
  numbering: "latn";
  entities: LegalEntity[];
}) {
  const text = (key: MessageKey) => t(locale, key);
  const previous = fill(locale, "revenue.vsPrevious", {
    first: report.comparable_previous_month.first,
    last: report.comparable_previous_month.last,
  });
  const collected = change(block.collected_change_bp);
  const invoiced = change(block.invoiced_change_bp);
  const amount = (minor: number) => (
    <MoneyValue kind="aggregate" amountMinor={minor} currency={block.currency}
      numbering={numbering} />
  );

  // The entity columns, in a stable order, so a row's cells line up with the heading. A
  // source that earned nothing at an entity still gets a zero rather than a gap: an absent
  // cell in a money table reads as a figure somebody failed to fetch.
  const entityIds = [
    ...new Set(
      block.by_source.flatMap((row) => row.by_legal_entity.map((e) => e.legal_entity_id)),
    ),
  ].sort();
  const entityName = (id: string) =>
    entities.find((e) => e.legal_entity_id === id)?.registered_name ?? id;
  const at = (row: SourceRow, id: string) =>
    row.by_legal_entity.find((e) => e.legal_entity_id === id)?.net_minor ?? 0;

  return (
    <section className="page-section" aria-labelledby={`revenue-${block.currency}`}>
      <h2 id={`revenue-${block.currency}`} className="ds-visually-hidden">
        {block.currency}
      </h2>

      <MetricRow label={text("revenue.title")}>
        <MetricCell
          label={text("revenue.collected")}
          value={amount(block.collected_minor)}
          comparison={collected ? previous : text("revenue.noComparison")}
          {...(collected ? { delta: collected } : {})}
        />
        <MetricCell
          label={text("revenue.invoiced")}
          value={amount(block.invoiced_minor)}
          comparison={invoiced ? previous : text("revenue.noComparison")}
          {...(invoiced ? { delta: invoiced } : {})}
        />
        {/* **No delta here, deliberately.** Outstanding is a position, not a flow, so there
            is no same-point-last-month figure that means the same thing. */}
        <MetricCell
          label={text("revenue.outstanding")}
          value={
            <MoneyValue kind="owed" amountMinor={block.outstanding_minor}
              currency={block.currency} numbering={numbering} />
          }
        />
        <MetricCell
          label={text("revenue.refunded")}
          value={amount(block.refunded_minor)}
        />
      </MetricRow>

      <h3 id={`revenue-sources-${block.currency}`}>{text("revenue.bySource")}</h3>
      {block.by_source.length === 0 ? (
        <Banner severity="info">{text("revenue.empty")}</Banner>
      ) : (
        <DataGrid<SourceRow>
          caption={text("revenue.bySource")}
          labelledBy={`revenue-sources-${block.currency}`}
          density="compact"
          countLabel={fill(locale, "revenue.sourceCount", { count: block.by_source.length })}
          rows={block.by_source}
          rowKey={(row) => row.product_type}
          columns={[
            {
              header: text("revenue.sourceCol"),
              kind: "text",
              priority: 1,
              render: (row) => {
                const named = sourceName(row.product_type);
                return named ? text(named) : (
                  <span className="data" dir="ltr">{row.product_type}</span>
                );
              },
              total: () => text("revenue.totalRow"),
            },
            // One column per legal entity, dropped first when the grid narrows: the net and
            // the change are the two a reader cannot do without, and a per-entity split is
            // the detail you open a wider screen for.
            ...entityIds.map((id) => ({
              header: entityName(id),
              kind: "money" as const,
              priority: 3 as const,
              render: (row: SourceRow) => (
                <MoneyValue kind="aggregate" amountMinor={at(row, id)}
                  currency={block.currency} numbering={numbering} />
              ),
              total: () => (
                <MoneyValue kind="aggregate"
                  amountMinor={block.by_source.reduce((sum, row) => sum + at(row, id), 0)}
                  currency={block.currency} numbering={numbering} />
              ),
            })),
            {
              header: text("revenue.amountCol"),
              kind: "money",
              priority: 1,
              render: (row) => amount(row.net_minor),
              // **The server's figure, not a sum of the column.** `invoiced_net_minor` is
              // what the sources reconcile to; adding the rows up here would be a second
              // definition of the same total, able to disagree with it the day either moves.
              total: () => amount(block.invoiced_net_minor),
            },
            {
              header: text("revenue.changeCol"),
              kind: "text",
              priority: 2,
              render: (row) => {
                const delta = change(row.change_bp);
                // **Not a zero.** No comparable figure last month is a different fact from a
                // month that matched exactly, and "0.0%" would claim the second.
                return delta ? (
                  <span className="ds-metric-delta data" data-tone={delta.tone} dir="ltr">
                    {delta.text}
                  </span>
                ) : (
                  <span className="muted">{text("revenue.noComparison")}</span>
                );
              },
            },
          ]}
        />
      )}
    </section>
  );
}
