import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { NotYet } from "@/components/not-yet";
import { fill, formatInteger, formatMoney, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { planName, repriceable, type Plan } from "@/lib/plans";
import { planName as storedWord } from "@/lib/members";
import { readPlanTable } from "@/lib/plans-reads";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { utcDate } from "@/lib/time";

import { PriceForm } from "./price-form";

/**
 * ADM-MSH-09 · PLANS & PRICING · OWNER ONLY.
 *
 * "Settings-shaped, not a sheet. Plan catalogue with entitlements, price, and a change-history
 * trail. Raising a price requires an effective date and states how many members are affected
 * before saving." Tier 3 · typed.
 *
 * **The count is the screen.** Its canvas draws a table and then one disclosure — "2,140
 * members are on this plan. 890 are inside a fixed-term commitment and keep 55.00 until it
 * ends. The other 1,250 move at their next renewal, the earliest on 22 August" — with the note
 * that it "is computed *before* the change is saved, not reported after. A price rise is the
 * most consequential action in Admin and the only one where the blast radius is stated in
 * members rather than currency." That read did not exist until this slice;
 * `membership_summary` groups by status and nothing counted members per plan.
 *
 * **Three reads and a request per plan, which this screen can pay for and FD-02 could not.**
 * It is owner-only and settings-shaped: nobody is standing at a desk waiting, so N requests
 * for N plans is the honest shape rather than a batch route invented for a table of six. The
 * page says so rather than leaving a reader to wonder why it is slower than the members list.
 *
 * **The sheet is a query parameter, not a modal**, as ADM-MSH-07's cancellation is: this app
 * has no side sheet, and a permanently-open destructive form has no way out.
 */
/**
 * The billing period in the reader's language.
 *
 * `one_off` and `fixed_term` reached this row raw -- the same vocabulary-as-label defect the
 * members list had, on the screen where a tenant picks which plan to re-price. An unmapped
 * value falls through to its stored form rather than to a blank.
 */
function periodWord(stored: string, locale: "en" | "ar"): string {
  const key = storedWord(stored);
  return key === null ? stored : t(locale, key);
}

export default async function PlansPage({
  searchParams,
}: {
  searchParams: Promise<{ variant?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const chosen = (await searchParams).variant ?? "";

  if (!(await currentSession())) redirect("/login");

  // **Three, because the plan picker charges two of them.** `GET /memberships/plans` asks for
  // `catalog.product.read` *and* `membership.record.read` -- a plan is a published product with
  // active terms, so both planes answer -- and the price column is `catalog.price.read`. A page
  // that checked two of the three would render for a session the plan read then refuses, which
  // is a 403 arriving as a thrown page rather than as a sentence.
  const [productRead, plansGate, priceRead] = await gateAll([
    "catalog.product.read",
    "membership.record.read",
    "catalog.price.read",
  ] as const);

  if (!productRead.allowed || !plansGate.allowed || !priceRead.allowed) {
    const refused = !productRead.allowed ? productRead
      : !plansGate.allowed ? plansGate : priceRead;
    return (
      <>
        <PageHeader title={text("plans.heading")} />
        <Banner severity="attention" title={text(gateMessage(refused))}>
          {text("plans.needsReads")}
          {gateVerdict(refused) === "needs_step_up" ? (
            <>
              {" "}
              <Link href={
                "/step-up?for=financial&action=membership.record.read&next=/plans"
              }>
                {text("member.raiseSession")}
              </Link>
            </>
          ) : null}
        </Banner>
      </>
    );
  }

  // **The count needs the membership read, which the gate above already has** -- so the table
  // asks for it. A session that could read plans and prices but not memberships would get the
  // table with an empty ACTIVE column, which is the state the row's own cell names.
  const rows = await readPlanTable({ withImpact: true, locale });
  const write = await gate("catalog.price.write");
  const plan = rows.find((one) => one.variant_id === chosen);
  // Today in UTC, which is what the service compares `effective_from` against. A browser's
  // own date would disagree with it for a few hours a night, which this build has three
  // recorded defects from.
  const today = new Date().toISOString().slice(0, 10);
  const amount = (minor: number, currency: string) =>
    // `latn`, not the tenant's: ADM-SET-07's money exception. See the comment above.
    formatMoney(minor, currency, "latn", locale);

  return (
    <>
      <PageHeader title={text("plans.heading")} />
      {/* **The catalogue's size, at the size of a figure.** It was the whole of the figures
          line -- one 14px sentence -- on the screen where a tenant picks which plan to
          re-price. With nothing to sell the banner below says so, so a `0` here would be the
          same sentence twice. */}
      {rows.length === 0 ? null : (
        <MetricRow label={text("plans.heading")}>
          <MetricCell
            label={text("plans.tableCaption")}
            value={formatInteger(rows.length, numbering)}
          />
        </MetricRow>
      )}

      {rows.length === 0 ? (
        <Banner severity="attention" title={text("plans.noPlans")}>
          {text("plans.noPlansWhat")}
        </Banner>
      ) : (
        <section className="page-section">
          <h2 id="plans-heading" style={{ margin: 0 }}>
            {text("plans.tableCaption")}
          </h2>
          <DataGrid
            caption={text("plans.tableCaption")}
            labelledBy="plans-heading"
            rows={rows}
            rowKey={(row) => row.variant_id}
            countLabel={fill(locale, "plans.rowCount", { count: rows.length }, numbering)}
            columns={[
              {
                header: text("plans.colPlan"),
                kind: "text",
                priority: 1,
                render: (row) => {
                  // **The product, qualified by the variant.** The first version rendered
                  // `display_name` alone, which is the *variant's* -- six of eight rows read
                  // "Monthly" on a screen whose job is choosing which plan to re-price. The
                  // read carries both now.
                  const named = planName(row);
                  return (
                    <>
                      <Link href={`/plans?variant=${row.variant_id}`}>{named.name}</Link>
                      <div className="muted ds-desk-row-context">
                        {[named.qualifier, periodWord(row.billing_period, locale),
                          ...(row.is_a_trial_product ? [text("plans.isTrial")] : []),
                          ...(named.isKey ? [text("plans.untranslated")] : [])]
                          .join(" \u00b7 ")}
                      </div>
                    </>
                  );
                },
              },
              {
                header: text("plans.colPrice"),
                kind: "money",
                priority: 1,
                render: (row) => (
                  <PriceCell plan={row} amount={amount} locale={locale} />
                ),
              },
              {
                header: text("plans.colActive"),
                kind: "text",
                priority: 1,
                // **`restricted` rather than a zero.** A session that cannot read memberships
                // gets the grid's own "restricted" marker, because a count of nobody and a
                // count this caller may not see are different facts and only one of them is
                // a reason to leave a plan's price alone.
                restricted: (row) => row.impact === null,
                render: (row) => (
                  <span className="data" dir="ltr">
                    {formatInteger(row.impact?.on_this_plan ?? 0, numbering)}
                  </span>
                ),
              },
              {
                header: text("plans.colChanged"),
                kind: "date",
                priority: 2,
                render: (row) => (
                  <span className="data" dir="ltr">
                    {row.price === null
                      ? text("plans.never")
                      : utcDate(row.price.effective_from)}
                  </span>
                ),
              },
            ]}
          />
        </section>
      )}

      {plan !== undefined ? <PriceSheet
        plan={plan} write={write} today={today} locale={locale} /> : null}

      <NotYet
        locale={locale}
        items={["plans.gapEntitlements", "plans.gapHistory", "plans.gapOneRequestEach", "plans.gapPriority"]}
      />
    </>
  );
}

/**
 * The price cell, which says which of three things it is.
 *
 * **A published product with no live price is the row an owner needs to notice.** MOD-016
 * records it as reachable with nothing changing a status: `publish_product` refuses one with no
 * live price and nothing re-checks afterwards, so a superseded price or a book nobody activated
 * leaves a published plan the till cannot sell.
 */
function PriceCell({
  plan, amount, locale,
}: {
  plan: Plan;
  amount: (minor: number, currency: string) => string;
  locale: Parameters<typeof t>[0];
}) {
  const text = (key: MessageKey) => t(locale, key);
  const state = repriceable(plan);
  if (state.kind === "noPrice") {
    return <span className="ds-desk-row-state">{text("plans.noLivePrice")}</span>;
  }
  // **A figure beside a marker, for the dead book.** The amount is what was written and is
  // real; what is not true of it is that a sale resolves to it, so dropping the number would
  // hide the thing an owner has to act on and printing it alone would be the claim the
  // `in_window_is_not_the_resolved_price` field exists to refuse.
  return (
    <>
      <span className="data" dir="ltr">
        {amount(state.price.amount_minor, state.price.currency)}
      </span>
      {state.kind === "deadBook" ? (
        <div className="ds-desk-row-state">{text("plans.bookNotLive")}</div>
      ) : null}
    </>
  );
}

/** The chosen plan's price change, or the reason there cannot be one. */
function PriceSheet({
  plan, write, today, locale,
}: {
  plan: Plan;
  write: Awaited<ReturnType<typeof gate>>;
  today: string;
  locale: Parameters<typeof t>[0];
}) {
  const text = (key: MessageKey) => t(locale, key);
  const state = repriceable(plan);

  return (
    <section className="ds-cash-drawer" data-testid="price-sheet">
      <h2>{fill(locale, "plans.changing", { plan: planName(plan).name })}</h2>
      {state.kind === "noPrice" ? (
        <Banner severity="attention" title={text("plans.cannotReprice")}>
          {text("plans.cannotRepriceWhat")}
        </Banner>
      ) : state.kind === "deadBook" ? (
        <Banner severity="attention" title={text("plans.cannotRepriceDeadBook")}>
          {fill(locale, "plans.cannotRepriceDeadBookWhat", {
            book: state.price.price_book_key, status: state.status,
          })}
        </Banner>
      ) : (
        <PriceForm
          locale={locale} numbering="latn" current={state.price}
          plan={{ variant_id: plan.variant_id, name: planName(plan).name }}
          impact={plan.impact} today={today}
          canWrite={write.allowed}
          stepUpHref={gateVerdict(write) === "needs_step_up"
            ? `/step-up?for=financial&action=catalog.price.write&next=/plans?variant=${plan.variant_id}`
            : null}
        />
      )}
      <p className="muted" style={{ margin: 0 }}>
        <Link href="/plans">{text("plans.closeSheet")}</Link>
      </p>
    </section>
  );
}
