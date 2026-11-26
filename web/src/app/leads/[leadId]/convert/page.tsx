import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell } from "@/components/ds/metric-cell";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { NotYet } from "@/components/not-yet";
import { ProseNote } from "@/components/prose";
import {
  fill, formatMoney, t, type Locale, type MessageKey,
} from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { BLOCKED_ACTIONS, carriesOver, chargeShape, fromTrial } from "@/lib/convert";
import { readNames } from "@/lib/desk-reads";
import type { ConversionQuote, SellablePlan } from "@/lib/leads";
import { listSellablePlans, readConversionQuote, readLead } from "@/lib/leads-reads";
import { planName } from "@/lib/members";
import { isWithheld } from "@/lib/people";
import { presentation } from "@/lib/preferences";
import { monthDayLabel } from "@/lib/time";

/**
 * ADM-CRM-06 · CONVERT — "Rana becomes a member / Club · monthly · JOD 55.00 / Pro-rata to
 * 31 Aug · JOD 21.29 / Then 55.00 from 1 Sep".
 *
 * **Its own route rather than a state of the lead profile.** ADM-CRM-05 shares a card title
 * with ADM-CRM-03 and so is a state of it; this canvas is a card of its own with its own id,
 * and the plan pick it needs is a selection the lead profile has nowhere to put.
 *
 * **Seven gates, because the card composes five modules and names a person.** The figures are
 * MOD-016's resolution and MOD-017's contract, the window is MOD-017's row, the attendance is
 * MOD-020's and the visits are MOD-022's; the picker is MOD-016's catalogue and the name is
 * MOD-014's. Each is the module that owns the fact, which is the Member 360's pattern.
 *
 * **No figure is computed here.** The part-period amount, the boundary and the day the
 * recurring charge starts come off the response, because they are `lifecycle.first_charge`
 * over the contract's own anchor -- and a browser deriving them would count days in its own
 * frame, which this app has three recorded defects from. `today` comes back too, so the screen
 * says which day the figures are for without consulting its own clock.
 *
 * **The plan pick is links, not a control**, so a chosen plan survives being sent to somebody
 * and works with no JavaScript -- the members list's, the schedule board's and the attendance
 * report's decision.
 *
 * **Neither of the canvas's buttons is drawn, and the reason is not the usual one.** Every
 * other absent form in this app is a stepped-up financial permission and is absent because "a
 * button that answered 403 is worse than its absence"; "Take 21.29" is the payment provider
 * and "Send link" is the messaging one, which are two of the seven things this build waits on
 * from outside. The third absence is a judgement rather than a blocker and is named with the
 * other two: the plan change that converts a trial is built and issues no invoice, so a button
 * that converted without charging would leave a member with access nobody has paid for.
 */
export default async function ConvertPage({
  params,
  searchParams,
}: {
  params: Promise<{ leadId: string }>;
  searchParams: Promise<{ variant?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const { leadId } = await params;
  const { variant } = await searchParams;

  if (!(await currentSession())) redirect("/login");

  const [mayLead, mayPrice, mayMembership, mayBookings, mayVisits, mayProducts, mayPeople] =
    await gateAll([
      "crm.lead.read", "catalog.price.read", "membership.record.read",
      "booking.booking.read", "access.decision.read", "catalog.product.read",
      "people.person.read",
    ] as const);

  // The quote needs five of the seven; without any one of them the server refuses the whole
  // card rather than returning part of it, so the screen says so rather than drawing a figure
  // it cannot complete.
  const mayQuote = mayLead.allowed && mayPrice.allowed && mayMembership.allowed
    && mayBookings.allowed && mayVisits.allowed;

  if (!mayLead.allowed || !mayQuote) {
    const refused = mayLead.allowed ? mayPrice : mayLead;
    const verdict = gateVerdict(refused);
    return (
      <div className="stack">
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {verdict === "denied" ? text("convert.refused") : text(gateMessage(refused))}
        </Banner>
        <Link href={`/leads/${leadId}`}>{text("convert.backToLead")}</Link>
      </div>
    );
  }

  let plans: SellablePlan[] = [];
  let quote: ConversionQuote | null = null;
  let missing = false;
  let failed = false;
  let name: string | null = null;
  try {
    const lead = await readLead(leadId);
    plans = mayProducts.allowed
      ? (await listSellablePlans().catch(() => ({ plans: [] }))).plans
      : [];
    if (variant) quote = await readConversionQuote(leadId, variant);
    if (mayPeople.allowed) {
      const found = await readNames([lead.person_id]).catch(() => new Map());
      const legal = found.get(lead.person_id)?.legal_name ?? null;
      // A masked value is a marker rather than a name -- the board paid for discovering that
      // `***` renders as though somebody were called it.
      name = legal !== null && !isWithheld(legal) ? legal : null;
    }
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) missing = true;
    else failed = true;
  }

  if (missing) {
    return (
      <div className="stack">
        <Banner severity="info">{text("lead.notFound")}</Banner>
        <Link href={`/leads/${leadId}`}>{text("convert.backToLead")}</Link>
      </div>
    );
  }

  const money = (amountMinor: number) =>
    formatMoney(amountMinor, quote?.currency ?? "JOD", "latn", locale);

  return (
    <div className="stack">
      <PageHeader title={text("convert.title")} />
      {/* **The sub-line is this screen's own, not `PageHeader`'s.** That component's rule is
          that the design's header is a title and a line of figures, derived from every data
          canvas; this canvas draws "Rana becomes a member" under the title, which is the
          subject rather than a description of the screen -- ADM-CRM-04's judgement for the
          same shape. */}
      <ProseNote>
        {name === null
          ? text("convert.becomesUnnamed")
          : fill(locale as Locale, "convert.becomes", { name })}
      </ProseNote>

      {failed ? <Banner severity="critical">{text("error.unexpected")}</Banner> : null}

      <section className="page-section">
        <h2>{text("convert.pickPlan")}</h2>
        {plans.length === 0 ? (
          <Banner severity="info">{text("convert.noPlans")}</Banner>
        ) : (
          <nav className="ds-filter-bar" aria-label={text("convert.pickPlan")}>
            {plans.map((plan) => (
              <Link
                key={plan.variant_id}
                className="ds-filter-chip"
                href={`/leads/${leadId}/convert?variant=${plan.variant_id}`}
                aria-current={plan.variant_id === variant ? "page" : undefined}
              >
                {plan.display_name}
              </Link>
            ))}
          </nav>
        )}
      </section>

      {quote === null ? null : (
        <>
          <section className="page-section">
            {/* The canvas's first line, with the stored billing period rendered as a word --
                `planName` is the one map, because a vocabulary the backend stores is never a
                label and this app has four recorded defects from rendering one raw. */}
            {/* **Three data values joined by the canvas's own separator, not a message.**
                The first version of this was a catalogue key reading `{plan} · {period} ·
                {amount}` -- identical in both languages, because a template of only
                placeholders has nothing to translate -- and the parity check that refuses an
                Arabic string equal to its English caught it. It was never a sentence: a plan
                name, a period word and an amount are three values, and this app already joins
                a lead's interests the same way. */}
            <h2>
              {[
                quote.plan.display_name,
                (() => {
                  const key = planName(quote.plan.billing_period);
                  return key === null ? quote.plan.billing_period : text(key);
                })(),
                money(quote.recurring_minor),
              ].join(" · ")}
            </h2>
            <section className="metrics" aria-label={text("convert.title")}>
              <MetricCell
                label={text("convert.dueToday")}
                value={
                  <MoneyValue
                    kind="aggregate"
                    amountMinor={quote.first_charge_minor}
                    currency={quote.currency}
                  />
                }
                comparison={
                  chargeShape(quote) === "prorated"
                    ? fill(locale as Locale, "convert.proRata", {
                        date: monthDayLabel(quote.first_period_ends_on, locale),
                        amount: money(quote.first_charge_minor),
                      })
                    : fill(locale as Locale, "convert.fullPeriod", {
                        date: monthDayLabel(quote.first_period_ends_on, locale),
                        amount: money(quote.first_charge_minor),
                      })
                }
              />
              <MetricCell
                label={text("convert.recurring")}
                value={
                  <MoneyValue
                    kind="aggregate"
                    amountMinor={quote.recurring_minor}
                    currency={quote.currency}
                  />
                }
                comparison={fill(locale as Locale, "convert.thenFrom", {
                  amount: money(quote.recurring_minor),
                  date: monthDayLabel(quote.recurring_starts_on, locale),
                })}
              />
            </section>
            {/* **The list and the discount, which the response carried and this screen
                dropped.** A heading reading `JOD 49.50` over a plan a tenant prices at
                `JOD 55.00` is a figure a member cannot reconcile, and the browser run that
                found it was looking at a fixture with four automatic promotions running --
                which is the ordinary state of a gym's catalogue rather than an edge case.
                MOD-016's own receipt is list, discount and final for the same reason. */}
            {quote.discount_minor > 0 ? (
              <ProseNote>
                {fill(locale as Locale, "convert.listWas", {
                  list: money(quote.list_amount_minor),
                  discount: money(quote.discount_minor),
                })}
              </ProseNote>
            ) : null}
            {/* Removed: a note explaining why this contract does not prorate. The
                prorated and full-period cases already read differently in the metric
                cell above ("{amount} for the first period, which runs to {date}"), so
                what went is the mechanism rather than the distinction. */}
            <ProseNote>
              {fill(locale as Locale, "convert.figuresFor", {
                date: monthDayLabel(quote.today, locale),
              })}
            </ProseNote>
          </section>

          {/* **The whole section is conditional, not just its contents.** Both children are
              conditional -- a lead with no classes, visits or touchpoints that is not
              converting from a trial renders neither -- so the section drew a heading with
              nothing under it, which reads as a block that failed to load. */}
          {carriesOver(quote).length > 0 || fromTrial(quote) ? (
          <section className="page-section">
            <h2>{text("convert.carriesTitle")}</h2>
            {/* Nothing with a count of zero is claimed: "her four class attendances carry
                over" is true of Rana and false of a lead who has never booked anything, and a
                line reading "0 class attendances" is the confident wrong answer MOD-014's own
                Member 360 was bitten by. */}
            {carriesOver(quote).length > 0 ? (
              <ul>
                {carriesOver(quote).map((item) => (
                  <li key={item.key}>
                    {fill(locale as Locale, item.key, { count: item.count })}
                  </li>
                ))}
              </ul>
            ) : null}
            {fromTrial(quote) && quote.trial !== null ? (
              <ProseNote>
                {fill(locale as Locale, "convert.fromTrial", {
                  days: quote.trial.trial_days,
                  date: monthDayLabel(quote.trial.ends_on, locale),
                })}
              </ProseNote>
            ) : null}
          </section>
          ) : null}
        </>
      )}

      {/* **The three acts this screen does not do, named and not explained.** The list used
          to carry a paragraph per act saying which provider each waits on and that the owner
          reserves real expenditure -- true, and governance rather than anything a receptionist
          can act on. What they need is that the charge does not happen here. */}
      <NotYet
        locale={locale}
        items={[...BLOCKED_ACTIONS.map((one) => one.key), "convert.actionConvert"]}
      />

      <Link href={`/leads/${leadId}`}>{text("convert.backToLead")}</Link>
    </div>
  );
}
