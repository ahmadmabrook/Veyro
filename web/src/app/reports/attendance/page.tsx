import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { Prose, ProseNote } from "@/components/prose";
import { fill, formatInteger, t, type MessageKey } from "@/i18n/locale";
import {
  currentSession,
  failureMessage,
  gate,
  gateMessage,
  gateVerdict,
} from "@/lib/api";
import { listLocations, type Location } from "@/lib/organization";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import {
  barHeightPercent,
  dayRange,
  DAY_RANGES,
  DEFAULT_RANGE,
  hourLabel,
  readAttendanceReport,
  sharePercent,
  type AttendanceReport,
} from "@/lib/reports";

/**
 * ADM-RPT-04 · ATTENDANCE — "VISITS BY HOUR · KHALDA · WEEKDAYS".
 *
 * **The canvas's own note is the requirement rather than a styling remark**: "The conclusion
 * is written in words beneath the chart. A manager should not have to interpret a heat strip
 * to find the actionable hour." So the busiest window and the quietest attended hour are
 * derived on the server, in `app/access/attendance.py`, where they are unit-tested — and this
 * page renders a sentence rather than asking a reader to count bars.
 *
 * **The one claim on the canvas this build will not make is its percentage of capacity.** It
 * writes "18:00–20:00 runs at 94% of floor capacity", and a capacity figure does exist:
 * `acc_policies.capacity`, the number a presentation is refused against. It is not this
 * chart's denominator, for two independent reasons either of which would be enough. Entries
 * in an hour are arrivals, not people inside at a moment — a hundred arrivals is a floor
 * holding a hundred if everybody stays an hour and fifty if everybody stays half of one. And
 * occupancy derived from access events is advisory unless a zone reads both directions, which
 * is paragraph 4180 and `occupancy.confidence` behind it, so the honest version of the
 * comparison is unavailable at exactly the single-turnstile clubs most tenants have.
 *
 * Nothing is lost from the canvas's reading, because every figure it draws is already
 * relative: the bars are heights against the busiest hour and the three tones are tiers of
 * the same ratio. The conclusion is written against the peak, and the page says so where a
 * reader might otherwise take a percentage for a capacity. The canvas's second sentence —
 * "two more classes at 07:00 would move perhaps 30 people" — is a recommendation with a
 * headcount in it, and nothing here models what a new class would draw; the hour is named,
 * which is the half the data supports.
 *
 * **"WEEKDAYS" is the reader's choice, because nothing in this build knows which days those
 * are.** A working week is Sunday to Thursday in the market this product is built for and
 * Monday to Friday in the one its design language comes from, and no table or configuration
 * key declares either. So the chips name *which days* rather than what they mean to a
 * business, which is `DAY_RANGES`' own argument, and the server refuses to default the set at
 * all — MOD-009's DSAR deadline and MOD-015's tax rate are the precedent.
 *
 * **Listing the sites is a different permission from reading the report**, which is the
 * schedule board's rule and matters for the same reason: the read returns the club's own name
 * and timezone, so a session holding only `access.zone.read` can open this page from a link.
 * The site list is what the *picker* needs, and a reader without it is told so rather than
 * shown an empty one — which would read as a tenant with no clubs.
 *
 * **Class fill and capacity planning are named, not drawn.** The registry line for this
 * screen is "Peak hours, class fill, capacity planning" and the canvas draws the first of the
 * three. A second chart this design does not have would be as much a deviation as a missing
 * one, so the two absences are stated, with the place average fill already exists.
 */
export default async function AttendanceReportPage({
  searchParams,
}: {
  searchParams: Promise<{ site?: string; range?: string; zone?: string; weeks?: string }>;
}) {
  const { locale } = await presentation();
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const count = (value: number) => (
    <span className="data" dir="ltr">{formatInteger(value, numbering)}</span>
  );

  if (!(await currentSession())) redirect("/login");

  const may = await gate("access.zone.read");
  if (!may.allowed) {
    // **A plain refusal names the permission; the other three verdicts do not, because they
    // are not about what this reader holds.** Both sibling reports say "This report needs
    // <permission>", which is the actionable sentence -- and `gateMessage` alone cannot say
    // it, because its whole job is to keep a transport failure, an unreachable assurance
    // level and a step-up apart from a denial. So the denial gets the report's own sentence
    // and the other three keep theirs. Found by a browser test asserting the permission was
    // named and getting the generic line instead.
    const verdict = gateVerdict(may);
    return (
      <>
        <PageHeader title={text("attendanceReport.heading")} />
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {text(verdict === "denied"
            ? "attendanceReport.refusedWhy"
            : gateMessage(may))}
        </Banner>
      </>
    );
  }

  const maySites = await gate("tenancy.organization.read");
  const sites: Location[] | null = maySites.allowed
    ? await listLocations().catch(() => null)
    : null;

  const params = await searchParams;
  const range = dayRange(params.range);
  const chosen = isUuid(params.site) ? params.site : sites?.[0]?.location_id;
  if (chosen === undefined) {
    return (
      <>
        <PageHeader title={text("attendanceReport.heading")} />
        <Banner severity="info">
          {sites === null
            ? text("attendanceReport.pickSiteInLink")
            : sites.length === 0
              ? text("attendanceReport.noLocation")
              : text("error.unexpected")}
        </Banner>
      </>
    );
  }

  const zone = isUuid(params.zone) ? params.zone : null;
  let report: AttendanceReport | null = null;
  let failed: MessageKey | null = null;
  try {
    report = await readAttendanceReport(chosen, range.days, { zoneId: zone });
  } catch (error) {
    failed = failureMessage(error);
  }
  if (report === null) {
    return (
      <>
        <PageHeader title={text("attendanceReport.heading")} />
        <Banner severity="critical">{text(failed ?? "error.unexpected")}</Banner>
      </>
    );
  }

  const here = (next: { range?: string; zone?: string | null; site?: string }) => {
    const query = new URLSearchParams({ site: next.site ?? chosen });
    const nextRange = next.range ?? range.key;
    if (nextRange !== DEFAULT_RANGE.key) query.set("range", nextRange);
    const nextZone = next.zone === undefined ? zone : next.zone;
    if (nextZone) query.set("zone", nextZone);
    return `/reports/attendance?${query.toString()}`;
  };

  const busiest = report.busiest;
  const quietest = report.quietest;
  // **The whole club or one of its readers.** A multi-zone club counts presentations rather
  // than people, so the narrowing is the figure a manager actually wants for a front door.
  // Offered only where there is more than one zone: a single chip is a control that does
  // nothing beside a sentence saying the same thing.
  const zoneChips = report.zones.length > 1;

  return (
    <>
      <PageHeader
        title={text("attendanceReport.heading")}
        figures={
          <span className="data" dir="ltr">
            {report.window.first_day} – {report.window.last_day}
          </span>
        }
      />

      {/* The canvas's own eyebrow: the club, the days and the zone the hours are in. The
          timezone is on the line because every hour on this page is that club's wall clock
          and no other screen in this app may assume a reader knows which. */}
      <p className="muted" style={{ margin: 0 }}>
        {report.location_name}
        {" · "}
        {text(range.label)}
        {" · "}
        {text("attendanceReport.timezone")}{" "}
        <span className="data" dir="ltr">{report.timezone}</span>
      </p>

      {sites !== null && sites.length > 1 ? (
        <nav
          aria-label={text("attendanceReport.site")}
          style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}
        >
          {sites.map((one) => (
            <Link
              key={one.location_id}
              href={here({ site: one.location_id, zone: null })}
              aria-current={one.location_id === chosen ? "page" : undefined}
            >
              {one.location_name}
            </Link>
          ))}
        </nav>
      ) : null}

      {/* Links rather than controls, so a view survives being sent to somebody and works
          with no JavaScript -- the members list's and the schedule board's decision. */}
      <nav className="ds-filter-bar" aria-label={text("attendanceReport.daysLabel")}>
        {DAY_RANGES.map((one) => (
          <Link
            key={one.key}
            className="ds-filter-chip"
            href={here({ range: one.key })}
            aria-current={one.key === range.key ? "page" : undefined}
          >
            {text(one.label)}
          </Link>
        ))}
      </nav>

      {zoneChips ? (
        <nav className="ds-filter-bar" aria-label={text("attendanceReport.zoneLabel")}>
          <Link
            className="ds-filter-chip"
            href={here({ zone: null })}
            aria-current={zone === null ? "page" : undefined}
          >
            {text("attendanceReport.wholeClub")}
          </Link>
          {report.zones.map((one) => (
            <Link
              key={one.zone_id}
              className="ds-filter-chip"
              href={here({ zone: one.zone_id })}
              aria-current={zone === one.zone_id ? "page" : undefined}
            >
              {/* A retired reader keeps its recorded entries, so it is marked rather
                  than dropped -- the per-zone figures then still add up to the total.
                  MOD-018's trial balance makes the same choice for a retired account. */}
              {one.retired
                ? fill(locale, "attendanceReport.retiredZone", { name: one.display_name })
                : one.display_name}
            </Link>
          ))}
        </nav>
      ) : null}

      <MetricRow label={text("attendanceReport.title")} columns={4}>
        <MetricCell label={text("attendanceReport.visits")} value={count(report.entries)} />
        <MetricCell
          label={text("attendanceReport.busiest")}
          {...(busiest === null
            ? { freshness: "unavailable" as const,
                unavailableBecause: text("attendanceReport.nobodyCame") }
            : {
                value: (
                  <span className="data" dir="ltr">
                    {hourLabel(busiest.from_hour)}–{hourLabel(busiest.to_hour)}
                  </span>
                ),
                comparison: fill(locale, "attendanceReport.inTheBusiestHour",
                                 { count: busiest.entries }, numbering),
              })}
        />
        <MetricCell
          label={text("attendanceReport.quietest")}
          {...(quietest === null
            ? { freshness: "unavailable" as const,
                unavailableBecause: text("attendanceReport.nobodyCame") }
            : {
                value: (
                  <span className="data" dir="ltr">{hourLabel(quietest.hour)}</span>
                ),
                comparison: fill(locale, "attendanceReport.ofThePeak",
                                 { percent: sharePercent(quietest.share_of_peak_bp) ?? 0 }),
              })}
        />
        {/* What the bars are summed over. A chart of twenty weekdays and a chart of one are
            read differently, and nothing else on the page says which this is. */}
        <MetricCell
          label={text("attendanceReport.daysCounted")}
          value={count(report.window.days_counted)}
          comparison={fill(locale, "attendanceReport.overWeeks", { count: report.weeks }, numbering)}
        />
      </MetricRow>

      <section className="page-section" aria-labelledby="visits-by-hour">
        <h2 id="visits-by-hour">{text("attendanceReport.chartTitle")}</h2>
        {/* **Twenty-four bars, including the empty ones.** This read does not consult the
            club's opening hours, so trimming the axis to the hours that saw somebody would
            be the surface inventing them -- and a 03:00 entry is exactly the bar a manager
            wants to see.

            **"Nothing in this build records when a club is open" is what this comment said,
            and it had been false for a module.** `plt01.tsk_business_hours` holds a
            location's weekly pattern and its dated overrides, and `/tasks/business-hours`
            sets, withdraws and reads it -- MOD-026 built that calendar *because* nothing
            recorded a club's hours, citing this report's own refusal. The hours are gated on
            `tasks.calendar.read`, which an access reader does not hold, so marking the closed
            bars is a composed second read rather than a missing fact; whether a club's
            opening hours are a *tasks* fact at all is ADM-SET-02's question. Each bar carries its hour and count as text, because a bar
            is a colour-and-length signal and §15's rule is that nothing carries meaning
            alone; the three tones are tiers of the share of the busiest hour, never of a
            capacity. */}
        <ol className="ds-hourbars" aria-labelledby="visits-by-hour">
          {report.by_hour.map((bucket) => (
            <li key={bucket.hour} className="ds-hourbar">
              <span
                className="ds-hourbar-fill"
                data-tier={bucket.tier}
                style={{ blockSize: `${barHeightPercent(bucket.entries, report.peak_entries)}%` }}
                aria-hidden="true"
              />
              <span className="ds-visually-hidden">
                {hourLabel(bucket.hour)}: {formatInteger(bucket.entries, numbering)}
              </span>
            </li>
          ))}
        </ol>
        <p className="ds-hourbars-axis">
          <span className="data" dir="ltr">{hourLabel(0)}</span>
          <span className="data" dir="ltr">{hourLabel(23)}</span>
        </p>

        {/* The canvas's conclusion box, in words. Its own note is why this is here rather
            than left to the reader: "A manager should not have to interpret a heat strip to
            find the actionable hour." */}
        {/* **A panel, not an alert.** The canvas draws a tinted box on `warm.50` with
            its first sentence in bold and no edge mark. `Banner` carries a semantic edge and
            `role="status"`, which is a live region -- so a screen reader would announce a
            static conclusion as though it had just changed. The bold sentence comes from
            `**` in the message and `Prose`, which is what that component exists for, so the
            emphasis is the translator's rather than the layout's. */}
        <div className="ds-conclusion">
          {busiest === null || quietest === null ? (
            <Prose>{text("attendanceReport.nobodyCameAtAll")}</Prose>
          ) : (
            <>
              <Prose>
                {fill(locale, "attendanceReport.conclusion", {
                  from: hourLabel(busiest.from_hour),
                  to: hourLabel(busiest.to_hour),
                  peak: busiest.entries,
                  quiet: hourLabel(quietest.hour),
                  percent: sharePercent(quietest.share_of_peak_bp) ?? 0,
                })}
              </Prose>
              {busiest.other_peak_hours.length > 0 ? (
                <>
                  {" "}
                  <Prose>
                    {fill(locale, "attendanceReport.anotherPeak", {
                      hours: busiest.other_peak_hours.map(hourLabel).join(", "),
                      count: busiest.other_peak_hours.length,
                    }, numbering)}
                  </Prose>
                </>
              ) : null}
            </>
          )}
        </div>

        {/* The refusal, where a reader might otherwise take a share for a capacity. */}
        <ProseNote>{text("attendanceReport.notCapacity")}</ProseNote>
        <ProseNote>{text("attendanceReport.noOpeningHours")}</ProseNote>
        {report.zones.length > 1 && zone === null ? (
          <ProseNote>{text("attendanceReport.presentations")}</ProseNote>
        ) : null}
        <ProseNote>{text("attendanceReport.weekendNotDeclared")}</ProseNote>
      </section>

      <section className="page-section" aria-labelledby="attendance-gaps">
        <h2 id="attendance-gaps">{text("attendanceReport.gapsTitle")}</h2>
        {/* `.facts` is a two-column grid whose items are the `dt` and the `dd`
            themselves, so each pair is wrapped in `display: contents` -- a plain `div`
            makes the div the grid item and puts both labels on one row with their values
            beneath, which is a defect no assertion about text can see. */}
        <dl className="facts">
          {([
            ["attendanceReport.gapClassFillLabel", "attendanceReport.gapClassFill"],
            ["attendanceReport.gapCapacityLabel", "attendanceReport.gapCapacity"],
            ["attendanceReport.gapExportLabel", "attendanceReport.gapExport"],
          ] as [MessageKey, MessageKey][]).map(([label, why]) => (
            <div key={label} style={{ display: "contents" }}>
              <dt className="muted">{text(label)}</dt>
              <dd style={{ margin: 0 }}>{text(why)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}

/** The same shape check the other boards use before a value reaches a route. */
function isUuid(value: string | undefined): value is string {
  return value !== undefined
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
