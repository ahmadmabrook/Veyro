import { Button } from "@/components/ds/button";
import { MoneyValue } from "@/components/ds/money-value";
import { AttentionQueue, AttentionRow } from "@/components/ds/attention-row";
import { Banner } from "@/components/ds/banner";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { MESSAGES, fill, formatInteger, formatMoney, t, type MessageKey, type Numbering } from "@/i18n/locale";
import { ApiError, currentSession, gate, gateAll } from "@/lib/api";
import { listLegalEntities, type LegalEntity } from "@/lib/organization";
import {
  heading as headingFor,
  orderQueue,
  queueCounts,
  type AttentionItem,
} from "@/lib/command-centre";
import {
  readCollections,
  readDunningCases,
  readMembershipSummary,
  readRejectedFilings,
  readUnstaffed,
  readVisits,
  type Collections,
  type DunningCases,
  type MembershipSummary,
  type RejectedFilings,
  type Unstaffed,
  type Visits,
} from "@/lib/command-centre-reads";
import { numerals } from "@/lib/display";
import type { Board } from "@/lib/leads";
import { readBoard } from "@/lib/leads-reads";
import { presentation } from "@/lib/preferences";
import { redirect } from "next/navigation";

/**
 * ADM-CC-01 … ADM-CC-05 · COMMAND CENTER · Owner, RM · COMPACT · 1440×900.
 *
 * **What was here before was a session-and-permissions diagnostic.** It printed the caller's
 * identity uuid, their assurance level and a six-row table of gate answers — a developer's
 * view of the authorization layer, at the product's front door, where the design puts the
 * screen a club owner opens at 08:40. That is the mismatch the owner directive of 2026-11-20
 * names by example, and it happened because this app was composed from what each backend
 * module's routes could answer rather than from the screens the design folder specifies.
 *
 * The diagnostic is not deleted — it moved. The gate table is on `/permissions`, beside the
 * roles and the audit chain it is about; the session's own identity and assurance are on
 * `/account`, beside the devices and sessions. Neither was a product screen and neither is
 * one now.
 *
 * ## The design, and what this build can answer of it
 *
 * Five canvases: the owner's normal day, the same morning for a club manager at branch scope,
 * a critical exception, the quiet day, and degraded data. The structure is a metric row of
 * four, an attention queue, an interpretation panel and two charts, and the queue is the
 * point — "The attention queue never collapses — it is the reason the page exists."
 *
 * | The design | Here |
 * | --- | --- |
 * | Collected month to date, vs the same point last month, with a pace | `GET /finance/collections` |
 * | Active members, net this month, joined and left | `GET /memberships/summary` |
 * | Visits today, against the usual for this weekday | `GET /access/visits` |
 * | Lead conversion over 30 days | **no CRM module** — `unavailable`, with the reason |
 * | MONEY · payments in recovery | `GET /finance/dunning-cases` |
 * | COMPLIANCE · invoices the tax authority rejected | `GET /finance/invoices?fiscal_status=rejected` |
 * | RETENTION · memberships expiring, with renewal value | the membership summary |
 * | STAFFING · classes with no coach, and the places held | `GET /scheduling/unstaffed` |
 * | LEADS · uncontacted leads | **no CRM module** — named, not drawn |
 * | The interpretation panel | **withheld**, with the true reason |
 * | Collections by week, the partial week marked | the collections read |
 * | Collections by location | **by legal entity** — the money chain carries no location |
 *
 * ## Four decisions worth knowing
 *
 * **Six reads, each behind its own permission, and a refusal is a panel rather than a page.**
 * That is canvas 2: a club manager gets "not a reduced Command Center — a differently
 * prioritised one", and the design states the boundary as a product fact — "What Ziad does
 * not see: group revenue, cross-location comparison, the JoFotara queue, and the
 * payment-recovery workflow itself." So `finance.revenue.read` is a grant a club manager does
 * not hold, and a reader without it sees every other panel.
 *
 * **A read that failed, a read that is late and a module that does not exist are three
 * states, not one.** `DS-CL-01`'s `freshness` is `live | stale | unavailable` for exactly
 * this reason, and the fourth metric is the case the design could not have anticipated: there
 * is no lead in this product, so the cell carries prose where a figure would go.
 *
 * **The metrics never carry severity.** Canvas 3, during an outage: "48 people in the
 * building is a fact, not a problem, and colouring it red during an unrelated outage teaches
 * staff to distrust the colour."
 *
 * **Every primary action the design puts on a queue row is absent, and the rows say so.**
 * "Send 6 payment links", "Fix the 3 invoices", "Offer to Dana or Yousef" — each is a
 * stepped-up financial write with no form in this app. ADM-MEM-05's rule: a control that does
 * nothing is worse than one that is not there. Each row links to the record instead.
 */

type Panel<T> = { data: T; allowed: true } | { allowed: false; reachable: boolean }
  | { allowed: true; data: null };

export default async function CommandCentre() {
  const { locale } = await presentation();
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  // Six gates, asked together. The design's loading section describes four independent
  // requests each with its own skeleton; this renders on the server, so the equivalent is
  // that one refusal or one failure costs one panel rather than the page.
  const [
    mayRevenue, mayMembership, mayVisits, mayDunning, mayInvoices, maySchedule, mayLeads,
  ] = await gateAll([
      "finance.revenue.read",
      "membership.record.read",
      "access.zone.read",
      "finance.dunning.read",
      "finance.account.read",
      "scheduling.schedule.read",
      "crm.lead.read",
    ] as const);

  const [collections, membership, visits, dunning, filings, unstaffed, leads] =
    await Promise.all([
      read(mayRevenue.allowed, () => readCollections()),
      read(mayMembership.allowed, () => readMembershipSummary()),
      read(mayVisits.allowed, () => readVisits()),
      read(mayDunning.allowed, () => readDunningCases()),
      read(mayInvoices.allowed, () => readRejectedFilings()),
      read(maySchedule.allowed, () => readUnstaffed()),
      read(mayLeads.allowed, () => readBoard()),
    ]);

  // **A UUID is not a label.** The collections block breaks down by legal entity, and the
  // first version printed the entity's id -- so the one figure on this page that names a part
  // of the business named it with 36 hex characters. `tenancy.organization.read` is MOD-004's
  // and `finance.revenue.read` is MOD-015's, so a reader may hold the figure without the
  // name: looked up when it can be, the id shown when it cannot. Exactly the arrangement
  // `/finance` already makes for its trial balance, which is why this is the same four lines
  // rather than a second way of doing it.
  let entities: LegalEntity[] = [];
  if ((await gate("tenancy.organization.read")).allowed) {
    try {
      entities = await listLegalEntities();
    } catch {
      entities = [];
    }
  }

  const money = (amountMinor: number, currency: string) =>
    // **`latn`, not the tenant's.** ADM-SET-07's rule: money keeps Latin digits with its
    // code whatever the numeral setting is, "because that is the form on your invoices and
    // JoFotara submissions" and a member disputing a charge has to see the same string in
    // both places. The counts on this page follow the setting; this does not.
    formatMoney(amountMinor, currency, "latn", locale);

  const items = orderQueue([
    ...moneyItems(dunning, locale, numbering),
    ...complianceItems(filings, locale, numbering),
    ...retentionItems(membership, locale, numbering),
    ...staffingItems(unstaffed, locale, numbering),
  ]);
  const counts = queueCounts(items);
  // **Every panel that feeds the queue, and whether it answered.** "Nothing needs you" is a
  // statement about the club, and a page that said it while four of its six reads were
  // refused would be making a claim out of its own permissions.
  const feeds: [MessageKey, boolean, Panel<unknown>][] = [
    ["cc.catMoney", mayDunning.allowed, dunning],
    ["cc.catCompliance", mayInvoices.allowed, filings],
    ["cc.catRetention", mayMembership.allowed, membership],
    ["cc.catStaffing", maySchedule.allowed, unstaffed],
  ];
  const complete = feeds.every(([, allowed, panel]) => allowed && panel.allowed && panel.data !== null);
  const head = headingFor(items, complete);

  return (
    // Compact density, which the design states for this screen and the foundation audit
    // confirms: "Command Center runs Compact, Member 360 runs Default, and both use the same
    // components with no anatomy changes."
    <div className="stack" data-density="compact">
      {/* The canvas's header row: `display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap`
          with the title and its sub-line on the left and the period toggle at the end. */}
      <PageHeader
        title={<>
          {/* **`head.key`, not a hard-coded clear heading.** The first version branched on
              the count here and threw away the key `heading()` had just chosen -- so a
              session that could see three of the four feeds read "Nothing needs you right
              now" above a paragraph saying the opposite. The decision belongs in one place
              and this renders it. */}
          {head.count === 0
            ? text(head.key)
            : fill(locale, head.key, { count: head.count }, numbering)}
        </>}
        figures={<>
        {/* The design's sub-line: "Wednesday 19 August · all locations · data through 08:38".
            The scope is stated because there is no switcher to change it, and the gap says so
            rather than letting "all locations" read as a choice somebody made. */}
        {/* **The period reads here, not as a control that cannot be pressed.** It was a
            bordered, rounded, button-shaped `<span>` at the end of the header row -- the
            shape of every pressable thing in this system, for the one period this build can
            answer. A reader reaches for it, nothing happens, and they have learned that this
            product's controls are unreliable. It is a scope statement and it sits with the
            other two, which is where a reader is already looking for "what am I looking
            at". The other two periods stay named in the gaps. */}
          {text("cc.periodMonth")}
          {" · "}
          {text("cc.scope")}
          {collections.allowed && collections.data
            ? <> {" · "} {text("cc.asOf")}{" "}
                <span className="data" dir="ltr">{collections.data.as_of}</span></>
            : null}
        </>}
      />
      {head.count === 0 ? (
        // Canvas 4: "No illustration, no 'all caught up!' -- it reports the day and offers
        // the next useful thing. A manager who sees this should feel informed, not
        // congratulated." So this is a sentence, not a celebration -- and when the page
        // could not read everything, it says what it is a statement about instead.
        <p style={{ margin: 0 }}>
          {text(complete ? "cc.headingClearBody" : "cc.headingPartialBody")}
        </p>
      ) : null}

      {/* **No visible heading over the metrics.** The canvas puts the row straight under the
          sub-line: the four labels are the heading, and a "Today's figures" above them would
          be the sentence said twice. The group keeps its accessible name, which is what a
          screen reader needs and a sighted reader already has. */}
      <section aria-label={text("cc.metrics")}>
        <MetricRow label={text("cc.metrics")}>
          <CollectedMetric panel={collections} locale={locale} money={money} />
          <MembersMetric panel={membership} locale={locale} numbering={numbering} />
          <VisitsMetric panel={visits} locale={locale} numbering={numbering} />
          {/* **The fourth was a permanent "unavailable" telling every owner that Veyro
              does not track leads, and it had been false since the CRM shipped.** A `/leads`
              entry sits in the rail, the board returns a count per stage, and this screen
              said there was nothing to report -- a gap note outliving its gap, on the most
              read screen in the product, which is this repository's own most recorded
              defect. It is the 30-day *conversion rate* that is still underivable: the board
              carries no time window. Open leads and leads going cold are real, they are what
              an owner acts on in the morning, and they are what this cell says now. */}
          <LeadsMetric panel={leads} locale={locale} numbering={numbering} />
        </MetricRow>
      </section>

      {/* **No heading over an empty queue.** Canvas 4 has no "Needs you now" block at all --
          the quiet day is a heading, a sentence and the figures. A section heading with
          nothing under it reads as a panel that failed to load, which is the one thing the
          empty state must not look like. The refusals below are rendered either way, because
          a category somebody cannot see is a fact about the page rather than about the day. */}
      {items.length === 0 && complete ? null : (
      <section className="ds-page-section" aria-labelledby="cc-queue">
        {items.length === 0 ? null : (
          <AttentionQueue
            heading="cc-queue"
            title={<h2 id="cc-queue" className="ds-section-title">{text("cc.queue")}</h2>}
            counts={fill(locale, "cc.queueCounts", {
              open: counts.open,
              critical: counts.critical,
              assigned: counts.assigned,
            }, numbering)}
          >
            {items.map((item) => (
              <AttentionRow
                key={item.key}
                id={item.key}
                severity={item.severity}
                category={t(locale, categoryLabel(item.category))}
                kind={item.category}
                when={item.when}
                {...(item.money
                  ? { money: { amount: item.money.amount, meaning: t(locale, item.money.meaning) } }
                  : {})}
                headline={item.title}
                evidence={item.body}
                {...(item.density ? { density: item.density } : {})}
                {...(item.owner ? { owner: item.owner } : {})}
                // **Real buttons, primary first.** The canvas draws a filled primary, an
                // outlined secondary and a ghost -- `Button(primary, secondary, ghost)` is in
                // its own component list. A row of identical outline chips reads as three
                // equal options, which is the opposite of what a resolution action is.
                actions={item.actions.map((action, index) => (
                  action.href === undefined ? null : (
                    <Button
                      key={action.href}
                      href={action.href}
                      variant={index === 0 ? "primary" : "secondary"}
                      size="sm"
                      label={t(locale, action.label)}
                    />
                  )
                ))}
              />
            ))}
          </AttentionQueue>
        )}
        {/* A refused panel is named. "Nobody is in recovery" and "you may not see who is" are
            different facts and only the first is one a manager would act on. */}
        <RefusedPanels locale={locale} panels={feeds} />
      </section>
      )}

      {collections.allowed && collections.data ? (
        <Charts data={collections.data} locale={locale} money={money} entities={entities} />
      ) : null}

    </div>
  );
}

/**
 * Read a panel, or say which of the three reasons there is no data.
 *
 * A refusal, a failure and an absent module are different facts. The first two are
 * distinguished here; the third is a `freshness` of `unavailable` on the cell itself.
 */
async function read<T>(allowed: boolean, fetch: () => Promise<T>): Promise<Panel<T>> {
  if (!allowed) return { allowed: false, reachable: true };
  try {
    return { allowed: true, data: await fetch() };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { allowed: true, data: null };
  }
}

function CollectedMetric({
  panel,
  locale,
  money,
}: {
  panel: Panel<Collections>;
  locale: "en" | "ar";
  money: (minor: number, currency: string) => string;
}) {
  const label = t(locale, "cc.metricCollected");
  if (!panel.allowed) {
    return (
      <MetricCell label={label} freshness="unavailable"
        unavailableBecause={t(locale, "cc.refusedPanel")} />
    );
  }
  if (panel.data === null) {
    return (
      <MetricCell label={label} freshness="unavailable"
        unavailableBecause={t(locale, "cc.failedPanel")} />
    );
  }
  // **One cell per currency, which is the money rule rather than a layout choice.** A tenant
  // may bill in several and `money.py`'s first convention is that an amount is a count of
  // minor units in one currency; one total across two is the comparison MOD-016's discount
  // approval made and a reviewer found. A single-currency tenant gets the design's one cell.
  const blocks = panel.data.collected;
  if (blocks.length === 0) {
    return <MetricCell label={label} value="—" />;
  }
  return (
    <>
      {blocks.map((block) => (
        <MetricCell
          key={block.currency}
          label={blocks.length === 1 ? label : `${label} · ${block.currency}`}
          // `MoneyValue(aggregate)`: the fils de-emphasised, never truncated.
          value={
            <MoneyValue
              kind="aggregate"
              amountMinor={block.collected_minor}
              currency={block.currency}
            />
          }
          {...(block.change_bp === null
            ? {}
            : {
                delta: {
                  text: `${block.change_bp > 0 ? "\u2191" : "\u2193"} ${
                    formatInteger(Math.abs(block.change_bp) / 100, "latn")}%`,
                  // Down is the warning tone and up is the success one. The *value* above
                  // carries neither: "the metrics do not turn red -- they are still facts".
                  tone: block.change_bp > 0 ? ("up" as const) : ("down" as const),
                },
              })}
          comparison={
            /* **The pace leads where there is nothing to compare against.** `null` is not
               zero -- a tenant with nothing last month cannot say whether this month is down,
               and 0% would read as "unchanged" -- but announcing that absence *first* put a
               seven-word apology directly under the largest figure on the screen and pushed
               the one number a manager can act on to the end of the line. With a baseline the
               comparison leads, because the delta arrow above it is its subject. */
            block.change_bp === null ? (
              <>
                {t(locale, "cc.pace")}{" "}
                <span className="data">{money(block.pace_minor, block.currency)}</span>
                {" · "}
                {t(locale, "cc.noBaseline")}
              </>
            ) : (
              <>
                {t(locale, "cc.vsLastMonth")}
                {" · "}
                {t(locale, "cc.pace")}{" "}
                <span className="data">{money(block.pace_minor, block.currency)}</span>
              </>
            )
          }
        />
      ))}
    </>
  );
}

function MembersMetric({
  panel,
  locale,
  numbering,
}: {
  panel: Panel<MembershipSummary>;
  locale: "en" | "ar";
  numbering: "latn" | "arab";
}) {
  const label = t(locale, "cc.metricMembers");
  if (!panel.allowed || panel.data === null) {
    return (
      <MetricCell label={label} freshness="unavailable"
        unavailableBecause={t(locale, panel.allowed ? "cc.failedPanel" : "cc.refusedPanel")} />
    );
  }
  const month = panel.data.this_month;
  return (
    <MetricCell
      label={label}
      value={formatInteger(panel.data.active, numbering)}
      comparison={
        <>
          {month.net >= 0 ? "+" : "−"}
          <span className="data">{formatInteger(Math.abs(month.net), numbering)}</span>
          {" · "}
          {fill(locale, "cc.joinedLeft", { joined: month.joined, left: month.left }, numbering)}
        </>
      }
    />
  );
}

/**
 * Open leads, with the ones going cold beneath.
 *
 * **It replaced a cell that had been permanently "unavailable" and permanently wrong.** The
 * sentence read "Veyro is not tracking leads yet, so there is no conversion rate to show",
 * and it had been false since the CRM landed: the rail carries a Leads entry, the board
 * returns a count per stage and a count going cold. What is genuinely still underivable is
 * the *30-day conversion rate* the cell was labelled for, because the board carries no time
 * window -- so the cell reports what the module answers rather than what the label wanted.
 *
 * **Going cold is the comparison line, not a second cell**, because the two are one thought:
 * how many are open, and how many of them are slipping. NN/g's limit of two large elements
 * per screen is what stops a figure row becoming the tile wall it replaced.
 */
function LeadsMetric({
  panel,
  locale,
  numbering,
}: {
  panel: Panel<Board>;
  locale: "en" | "ar";
  numbering: "latn" | "arab";
}) {
  const label = t(locale, "cc.metricLeads");
  if (!panel.allowed || panel.data === null) {
    return (
      <MetricCell label={label} freshness="unavailable"
        unavailableBecause={t(locale, panel.allowed ? "cc.failedPanel" : "cc.refusedPanel")} />
    );
  }
  return (
    <MetricCell
      label={label}
      value={formatInteger(panel.data.open_leads, numbering)}
      comparison={fill(locale, "leads.goingCold", { count: panel.data.going_cold }, numbering)}
    />
  );
}

function VisitsMetric({
  panel,
  locale,
  numbering,
}: {
  panel: Panel<Visits>;
  locale: "en" | "ar";
  numbering: "latn" | "arab";
}) {
  const label = t(locale, "cc.metricVisits");
  if (!panel.allowed || panel.data === null) {
    return (
      <MetricCell label={label} freshness="unavailable"
        unavailableBecause={t(locale, panel.allowed ? "cc.failedPanel" : "cc.refusedPanel")} />
    );
  }
  // The baseline is the sum of each location's own, and it is absent rather than zero where
  // no earlier same-weekday carried entries.
  const seen = panel.data.locations.filter((l) => l.usual_for_this_weekday !== null);
  const usual = seen.reduce((n, l) => n + (l.usual_for_this_weekday ?? 0), 0);
  return (
    <MetricCell
      label={label}
      value={formatInteger(panel.data.entries, numbering)}
      comparison={
        seen.length === 0
          ? fill(locale, "cc.noUsual", { weekday: weekdayName(locale, panel.data.weekday) })
          : (
            <>
              <span className="data">{formatInteger(usual, numbering)}</span>{" "}
              {fill(locale, "cc.usualFor", { weekday: weekdayName(locale, panel.data.weekday) })}
            </>
          )
      }
    />
  );
}

/** The two charts. "By legal entity", because the money chain carries no location. */
function Charts({
  data,
  locale,
  money,
  entities,
}: {
  data: Collections;
  locale: "en" | "ar";
  money: (minor: number, currency: string) => string;
  /** Empty where the reader may not list them, which is a refusal rather than an absence. */
  entities: LegalEntity[];
}) {
  const block = data.collected[0];
  if (block === undefined) return null;
  const peak = Math.max(1, ...block.by_week.map((w) => w.collected_minor));
  return (
    <section className="page-section" aria-labelledby="cc-charts">
      <h2 id="cc-charts">{t(locale, "cc.charts")}</h2>
      <h3 style={{ margin: 0, fontSize: "var(--type-label-size)" }}>
        {t(locale, "cc.chartWeeks")}
      </h3>
      <ul className="ds-bars">
        {block.by_week.map((week) => (
          <li
            key={week.first}
            className="ds-bar"
            data-partial={week.partial ? "true" : "false"}
          >
            {/* "2 Jun", not "2026-06-02". The design's axis runs "2 Jun … 19 Aug", and an
                ISO date in an 11ch column wraps onto two lines -- which is how this was
                found, by looking at the rendered chart rather than at the markup. */}
            <span className="muted data" dir="ltr">{axisLabel(week.first, locale)}</span>
            <span className="ds-bar-track">
              {/* The width is the only inline value on the page that is not a token: a bar's
                  length *is* the datum. The partial bucket is hatched rather than scaled up --
                  "marked, not extrapolated". */}
              <span
                className="ds-bar-fill"
                style={{ inlineSize: `${(week.collected_minor / peak) * 100}%` }}
              />
            </span>
            <span className="ds-bar-amount data">
              {money(week.collected_minor, block.currency)}
              {week.partial ? (
                <span className="muted"> {t(locale, "cc.chartPartial")}</span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      <h3 style={{ margin: 0, fontSize: "var(--type-label-size)" }}>
        {t(locale, "cc.chartEntity")}
      </h3>
      <dl className="facts">
        {block.by_legal_entity.map((entity) => (
          <div key={entity.legal_entity_id} style={{ display: "contents" }}>
            <dt className="muted">
              {entities.find((e) => e.legal_entity_id === entity.legal_entity_id)
                ?.registered_name ?? (
                <span className="data" dir="ltr">{entity.legal_entity_id}</span>
              )}
            </dt>
            <dd className="data" style={{ margin: 0 }}>
              {money(entity.collected_minor, block.currency)}
            </dd>
          </div>
        ))}
      </dl>
      {/* **The server's own two sentences are not rendered here, and that is deliberate.**
          `by_location_is_unavailable` and `pace_is_a_projection` are prose fields on the
          collections response, and both are written for an engineer: they name `MOD-004`,
          `by_legal_entity` and `pace_minor`. An operator screen is not where this product
          explains its own module boundaries, and the directive protects the backend contract,
          so the fields keep being returned and this surface stops printing them.

          What an operator actually needs from the first is one line in their own language,
          which is below. The second is already carried where it belongs -- the collected
          figure's own comparison line says "pace", beside the number it is a pace for. The
          consequence, recorded rather than left to be discovered: those two response fields
          now have no reader in this app. */}
      <p className="ds-section-note">{t(locale, "cc.chartEntityNote")}</p>
    </section>
  );
}

/**
 * The weekday, in the reader's language.
 *
 * **The visits read returns an English weekday name**, and an Arabic page rendered it
 * verbatim: "لا يوجد يوم Thursday سابق للمقارنة", Latin letters mid-sentence in a product
 * whose bilingual parity is a stated commitment. That is this repository's own recurring
 * finding -- a vocabulary the backend stores is never a label -- and the message-catalogue
 * parity check cannot see it, because the English name never became a key.
 *
 * Mapped rather than reformatted from a date: `conventions.mjs` is compared character for
 * character against the backend's own copy, so a weekday formatter added there would need a
 * Python twin, and the response carries a name rather than an instant anyway. An unknown
 * value falls through to what the server said instead of to a blank, because a weekday nobody
 * mapped is still more use to a reader than nothing.
 */
function weekdayName(locale: "en" | "ar", weekday: string): string {
  const key = `weekday.${weekday.trim().toLowerCase()}`;
  const message = MESSAGES[locale][key as MessageKey];
  // The catalogue holds plural forms as objects as well as plain strings, so the type is a
  // union: a weekday is never a plural, and anything that is not a string is not one of
  // these keys. Falling through to the server's own word is the honest default.
  return typeof message === "string" ? message : weekday;
}

function RefusedPanels({
  locale,
  panels,
}: {
  locale: "en" | "ar";
  panels: [MessageKey, boolean, Panel<unknown>][];
}) {
  const refused = panels.filter(([, allowed]) => !allowed);
  const failed = panels.filter(
    ([, allowed, panel]) => allowed && panel.allowed && panel.data === null);
  if (refused.length === 0 && failed.length === 0) return null;
  return (
    <>
      {refused.length > 0 ? (
        <Banner severity="info">
          {refused.map(([label]) => t(locale, label)).join(" · ")}
          {" — "}
          {t(locale, "cc.refusedPanel")}
        </Banner>
      ) : null}
      {failed.length > 0 ? (
        <Banner severity="critical">
          {failed.map(([label]) => t(locale, label)).join(" · ")}
          {" — "}
          {t(locale, "cc.failedPanel")}
        </Banner>
      ) : null}
    </>
  );
}

function categoryLabel(category: string): MessageKey {
  switch (category) {
    case "money":
      return "cc.catMoney";
    case "compliance":
      return "cc.catCompliance";
    case "retention":
      return "cc.catRetention";
    case "staffing":
      return "cc.catStaffing";
    default:
      return "cc.catLeads";
  }
}

// ---------------------------------------------------------------- the four queue classes
//
// Each is one item summarising one module's answer, not one item per row of it. The design's
// queue is nine items on a busy morning; a row per failed payment would be a list, and
// "9 open · 2 critical" would stop meaning anything.

function moneyItems(
  panel: Panel<DunningCases>,
  locale: "en" | "ar",
  numbering: Numbering,
): AttentionItem[] {
  if (!panel.allowed || panel.data === null || panel.data.count === 0) return [];
  const at = panel.data.at_risk[0];
  return [{
    key: "cc-money",
    category: "money",
    // Critical: money the tenant is owed and is actively chasing.
    severity: "critical",
    when: t(locale, "cc.scope"),
    ...(at
      ? {
          money: {
            // `owed` — critical, and always with a status word nearby, which is what
            // "at risk" is. §39: never a bare number.
            amount: (
              <MoneyValue
                kind="owed"
                amountMinor={at.amount_minor}
                currency={at.currency}
              />
            ),
            meaning: "cc.atRisk" as const,
          },
        }
      : {}),
    title: fill(locale, "cc.moneyTitle", { count: panel.data.count }, numbering),
    body: t(locale, "cc.moneyBody"),
    // **"Open the recovery workspace"**, which is what the canvas's own button says and
    // where ADM-PAY-05 is reached from -- `veyro-screen.js` wires this item to that screen
    // by id. It pointed at `/finance`, MOD-018's trial balance, which is a different
    // subject: an accountant closes a month there and nobody chases a failed card.
    actions: [{ label: "cc.openRecovery", href: "/payments/recovery" }],
  }];
}

function complianceItems(
  panel: Panel<RejectedFilings>,
  locale: "en" | "ar",
  numbering: Numbering,
): AttentionItem[] {
  if (!panel.allowed || panel.data === null || panel.data.count === 0) return [];
  return [{
    key: "cc-compliance",
    category: "compliance",
    severity: "critical",
    when: t(locale, "cc.scope"),
    title: fill(locale, "cc.complianceTitle", { count: panel.data.count }, numbering),
    body: t(locale, "cc.complianceBody"),
    actions: [{ label: "cc.openIt", href: "/finance" }],
  }];
}

function retentionItems(
  panel: Panel<MembershipSummary>,
  locale: "en" | "ar",
  numbering: Numbering,
): AttentionItem[] {
  if (!panel.allowed || panel.data === null) return [];
  const expiring = panel.data.expiring;
  if (expiring.count === 0) return [];
  const value = expiring.renewal_value[0];
  return [{
    key: "cc-retention",
    category: "retention",
    severity: "attention",
    when: t(locale, "cc.scope"),
    ...(value
      ? {
          money: {
            // `neutral` — a renewal value is a fact rather than money anybody is owed.
            amount: (
              <MoneyValue
                kind="neutral"
                amountMinor={value.amount_minor}
                currency={value.currency}
              />
            ),
            meaning: "cc.renewalValue" as const,
          },
        }
      : {}),
    title: fill(locale, "cc.retentionTitle",
      { count: expiring.count, days: expiring.within_days }, numbering),
    body: t(locale, "cc.retentionBody"),
    actions: [{ label: "cc.openIt", href: "/members" }],
  }];
}

function staffingItems(
  panel: Panel<Unstaffed>, locale: "en" | "ar", numbering: Numbering,
): AttentionItem[] {
  if (!panel.allowed || panel.data === null || panel.data.count === 0) return [];
  return [{
    key: "cc-staffing",
    category: "staffing",
    // **The canvas draws staffing in `info`, with eighteen members booked.** The first
    // version here escalated to `critical` once anybody was affected, which reads as a
    // sensible rule and disagrees with the one screen the design draws: MONEY and COMPLIANCE
    // are error, RETENTION is warning, and STAFFING and LEADS are info even when a full
    // class is waiting. The severity is about what the item *is*, not how many it touches --
    // a class with no coach is a thing to assign, and colouring it like a failed payment is
    // what teaches somebody to stop reading the colour.
    severity: "info",
    density: "condensed",
    when: `${panel.data.from_date} → ${panel.data.to_date}`,
    title: fill(locale, "cc.staffingTitle", { count: panel.data.count }, numbering),
    // Two bodies: "0 places are held across them" is a sentence with nothing in it, and the
    // empty case is the one worth saying something useful about.
    body: panel.data.members_affected > 0
      // `fill` defaults its numbering to `latn`, so omitting it renders Latin digits on an
      // `arab` tenant -- the one plural message on this surface that was doing so.
      ? fill(locale, "cc.staffingBody", { members: panel.data.members_affected }, numbering)
      : t(locale, "cc.staffingBodyEmpty"),
    actions: [{ label: "cc.openIt", href: "/schedule" }],
  }];
}

/**
 * A bucket's label on the weekly axis: the day and the short month.
 *
 * The year is dropped because every bucket on a twelve-week axis shares it, and a label that
 * repeats what every other label says is noise in the narrowest column on the page.
 */
function axisLabel(isoDate: string, locale: "en" | "ar"): string {
  const at = new Date(`${isoDate}T00:00:00Z`);
  return new Intl.DateTimeFormat(locale === "ar" ? "ar" : "en-GB", {
    timeZone: "UTC", day: "numeric", month: "short",
  }).format(at);
}
