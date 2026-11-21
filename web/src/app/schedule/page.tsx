import Link from "next/link";
import { redirect } from "next/navigation";

import { AttentionQueue, AttentionRow } from "@/components/ds/attention-row";
import { Banner } from "@/components/ds/banner";
import { ClassCell, WeekGrid } from "@/components/ds/week-grid";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate, gateMessage } from "@/lib/api";
import { listLocations, type Location } from "@/lib/organization";
import { presentation } from "@/lib/preferences";
import {
  needsAttention,
  readCalendar,
  weekDays,
  weekRows,
  weekSummary,
  type ScheduledSession,
} from "@/lib/scheduling";
import { inZone } from "@/lib/time";

/**
 * ADM-SCH-01 · CLASS SCHEDULE · WEEK GRID · CM · COMPACT.
 *
 * **This was a list and the design specifies a grid**, which the compliance ledger recorded
 * as a fidelity gap from the day the design folder was read properly. The canvas is
 * "CANVAS 1 · SCHEDULING · KHALDA · WEEK OF 18 AUGUST", seven day columns with a row per
 * local start time, and it names its own components:
 *
 * > AdminShell · WeekGrid(7×4, horizontal scroll below bp.lg) · ClassCell ×13 (1 unstaffed,
 * > 1 full, 1 low-fill) · AttentionRow(condensed, footer-anchored) · Compact density ·
 * > **severity on the cell edge-mark only, never the cell fill**
 *
 * A list and a grid answer different questions. "What is on at six o'clock on Thursday" is a
 * scan down a column in one and a search through forty rows in the other, and the design's
 * own heading -- "The week, with one problem in it" -- is a sentence only a grid can earn.
 *
 * What is built and what is named:
 *
 * - **The header's three figures**: how many classes, how many without a coach, and the
 *   average fill. All three are exact, because the calendar read is bounded by its date
 *   window rather than by a row limit.
 * - **The coach in every cell**, which needed the calendar read to return the live staff
 *   assignment. `superseded_at IS NULL` is what "has a coach" means.
 * - **Week and Day**, which are the same read over different spans. **Coaches is named as
 *   missing**: that view is a grid of rota rows rather than of sessions, and nothing here
 *   reads a resource's availability.
 * - **"Add a class" is named as missing.** Publishing a schedule is a stepped-up permission
 *   with no form in this app, which is the same gap the hierarchy has.
 *
 * Everything the list got right is kept, and all of it was hard-won: the zone is the site's
 * own and every instant is converted in it (a class at 18:00 in Amman read as 15:00 under a
 * heading promising the site's timezone, and 140 green assertions did not notice); `free` is
 * the module's own answer rather than `places - held`; and `dst_adjusted` is the one flag
 * worth marking, because a class moved by a clock change is one whose members were told a
 * time that is not when it happens.
 */
export default async function SchedulePage({
  searchParams,
}: {
  searchParams: Promise<{ site?: string; from?: string; span?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(may))}
        </Banner>
      </Shell>
    );
  }

  // **Listing the sites is a different permission from reading the schedule**, and the board
  // does not need it: `readCalendar` returns the site's own name and timezone, so a session
  // that holds only `scheduling.schedule.read` can open a board from a link. The site list is
  // what the *picker* needs, and a reader without it is told that rather than shown an empty
  // one -- which would read as "this tenant has no sites".
  const maySites = await gate("tenancy.organization.read");
  const sites = maySites.allowed ? await listLocations().catch(toNull) : null;

  const params = await searchParams;
  const chosen = isUuid(params.site) ? params.site : sites?.[0]?.location_id;
  if (chosen === undefined) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {sites === null
            ? text("schedule.pickSiteInLink")
            : sites.length === 0
              ? text("schedule.noLocation")
              : text("error.unexpected")}
        </Banner>
      </Shell>
    );
  }
  // A week, because the module bounds the range to 62 days and a week is what an operator
  // reads at once. `from` is a date rather than an instant: the calendar is addressed by the
  // site's own local dates, which is what `local_date` on each session is.
  const from = isDate(params.from) ? params.from : today();
  // Week or day: the same read over a different span, which is the half of the design's view
  // toggle this build can answer. A day is one column rather than a different grid.
  const span = params.span === "day" ? "day" : "week";
  const to = addDays(from, span === "day" ? 0 : 6);
  const calendar = await readCalendar(chosen, from, to).catch(toNull);
  if (calendar === null) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  const summary = weekSummary(calendar.sessions);
  const localDate = (session: ScheduledSession) =>
    inZone(session.starts_at, calendar.timezone).date;
  const localTime = (session: ScheduledSession) =>
    inZone(session.starts_at, calendar.timezone).time;
  // **Today in the site's zone, not in the host's.** The column marked "today" is the one a
  // reader at that club is standing in, and a board in Amman read from a UTC server is three
  // hours out for three hours a night.
  const todayAtSite = inZone(new Date().toISOString(), calendar.timezone).date;
  const days = weekDays(from, locale, todayAtSite).slice(0, span === "day" ? 1 : 7);
  const rows = weekRows(calendar.sessions, days, localTime);
  // The sessions a reader has to act on, which the design anchors under the grid as a
  // condensed row rather than scattering marks across the week.
  const problems = calendar.sessions.filter(
    (session) => session.staff === null || needsAttention(session));

  return (
    <Shell locale={locale}>
      {/* The design's own sub-line: the site, the span and the average fill. */}
      <p className="muted" style={{ margin: 0 }}>
        {calendar.location_name}
        {" · "}
        <span className="data" dir="ltr">{from}</span>
        {" – "}
        <span className="data" dir="ltr">{to}</span>
        {summary.averageFillPercent === null
          ? null
          : <>
              {" · "}
              {fill(locale, "schedule.averageFill",
                { percent: summary.averageFillPercent })}
            </>}
        {" · "}
        {t(locale, "schedule.timezone")}{" "}
        <span className="data" dir="ltr">{calendar.timezone}</span>
      </p>

      {sites !== null && sites.length > 1 ? (
        <nav
          aria-label={text("schedule.site")}
          style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}
        >
          {sites.map((one) => (
            <SiteLink key={one.location_id} site={one} currentId={chosen} from={from} />
          ))}
        </nav>
      ) : null}

      {/* Week · Day · Coaches. Links rather than controls, so the view survives being sent
          to somebody and works with no JavaScript -- the same decision the members list's
          filters make.

          **`Coaches` was in the gaps below until there was a rota to read.** It is a grid of
          rota rows rather than of sessions, and the note here said "nothing here reads a
          resource's availability" -- which was true of the whole build: `set_availability`
          had a writer and no reader. `/rota` is ADM-SCH-04 and the read behind it is new. */}
      <nav aria-label={text("schedule.views")} className="ds-filter-bar">
        <Link
          href={`/schedule?site=${chosen}&from=${from}`}
          aria-current={span === "week" ? "page" : undefined}
          className="ds-filter-chip"
        >
          {text("schedule.week")}
        </Link>
        <Link
          href={`/schedule?site=${chosen}&from=${from}&span=day`}
          aria-current={span === "day" ? "page" : undefined}
          className="ds-filter-chip"
        >
          {text("schedule.day")}
        </Link>
        <Link href={`/rota?site=${chosen}`} className="ds-filter-chip">
          {text("schedule.coaches")}
        </Link>
      </nav>

      {calendar.sessions.length === 0 ? (
        <Banner severity="info">{text("schedule.empty")}</Banner>
      ) : (
        <>
          <WeekGrid
            labelledBy="schedule-heading"
            timeHeader={text("schedule.time")}
            days={days}
            rows={rows.map((row) => ({
              time: row.time,
              cells: row.cells.map((slot) =>
                slot === null ? null : (
                  <div key={slot[0]!.session_id} className="stack-tight">
                    {slot.map((session) => (
                      <ClassCell
                        key={session.session_id}
                        name={session.display_name}
                        href={`/schedule/${session.session_id}`}
                        // Never blank: a class with no coach is a gap somebody has to fill.
                        coach={session.staff ?? text("schedule.noCoach")}
                        fill={`${formatInteger(session.held, "latn")}/${
                          formatInteger(session.places, "latn")}`}
                        // **An edge-mark, never a fill.** A class with no coach is the
                        // design's own severe cell; a full class is ordinary and a
                        // cancelled one is a decision somebody made.
                        severity={
                          session.staff === null
                            ? "critical"
                            : needsAttention(session)
                              ? "attention"
                              : null
                        }
                        {...(needsAttention(session)
                          ? { note: text("schedule.dstMoved") }
                          : {})}
                      />
                    ))}
                  </div>
                )),
            }))}
          />

          {/* **Footer-anchored**, which the canvas states: the problem is stated once under
              the week rather than inferred from marks scattered across it. */}
          {problems.length > 0 ? (
            <section className="ds-page-section" aria-labelledby="schedule-problems">
              <AttentionQueue
                heading="schedule-problems"
                title={
                  <h2 id="schedule-problems" className="ds-section-title">
                    {text("schedule.problems")}
                  </h2>
                }
                counts={fill(locale, "schedule.problemCount", { count: problems.length })}
              >
                {problems.map((session) => (
                  <AttentionRow
                    key={session.session_id}
                    id={`sch-${session.session_id}`}
                    severity={session.staff === null ? "critical" : "attention"}
                    category={text(
                      session.staff === null ? "cc.catStaffing" : "schedule.clockChange")}
                    when={`${localDate(session)} ${localTime(session)}`}
                    headline={session.display_name}
                    // **Two bodies.** "0 places are held, so somebody is expecting a
                    // class" is a sentence that contradicts itself, and the empty case is
                    // the one worth saying something useful about -- the same correction
                    // the Command Center's staffing row needed.
                    evidence={
                      session.staff === null
                        ? session.held > 0
                          ? fill(locale, "schedule.noCoachBody", { held: session.held })
                          : text("schedule.noCoachBodyEmpty")
                        : text("schedule.dstBody")
                    }
                    actions={
                      <Link
                        href={`/schedule/${session.session_id}`}
                        className="ds-filter-chip"
                      >
                        {text("cc.openIt")}
                      </Link>
                    }
                  />
                ))}
              </AttentionQueue>
            </section>
          ) : null}

          {/* **What "Taken" and "Free" are.** Without this a reader takes them for stored
              counters, and the one thing MOD-019 refuses to keep is a `held_count`. */}
          <p className="muted" style={{ margin: 0 }}>
            {text("schedule.heldExplained")}
          </p>

          <section className="page-section">
            <h2>{text("cc.gaps")}</h2>
            <dl className="facts">
              <dt className="muted">{text("schedule.coachesView")}</dt>
              <dd style={{ margin: 0 }}>{text("schedule.coachesViewWhy")}</dd>
              <dt className="muted">{text("schedule.addClass")}</dt>
              <dd style={{ margin: 0 }}>{text("schedule.addClassWhy")}</dd>
            </dl>
          </section>
        </>
      )}
    </Shell>
  );
}

function SiteLink({
  site,
  currentId,
  from,
}: {
  site: Location;
  currentId: string;
  from: string;
}) {
  const here = site.location_id === currentId;
  return (
    <Link
      href={`/schedule?site=${site.location_id}&from=${from}`}
      aria-current={here ? "page" : undefined}
      style={here ? { fontWeight: "var(--type-label-weight)" } : undefined}
    >
      {site.location_name}
    </Link>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 id="schedule-heading" style={{ margin: 0 }}>
        {t(locale, "schedule.title")}
      </h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "schedule.lead")}
      </p>
      {children}
    </div>
  );
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
}

/** Today in UTC, which is what the calendar's date bounds are compared against. */
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function addDays(date: string, days: number): string {
  const at = new Date(`${date}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
}

/**
 * A date out of a query string, checked for shape rather than trusted.
 *
 * It reaches the API as a bound on a range the module limits to 62 days, so a malformed one
 * is a 422 from the backend rather than anything worse -- but a page that passed it through
 * would answer 500 where it could answer with this week.
 */
function isDate(value: string | undefined): value is string {
  return value !== undefined && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

/**
 * A site id out of a query string, checked for shape.
 *
 * The backend answers 422 for a malformed one -- `require_uuid` is in that route -- so this is
 * not the control. It is what keeps a mistyped link rendering the board's own refusal instead
 * of an unexpected-error panel.
 */
function isUuid(value: string | undefined): value is string {
  return value !== undefined && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value);
}



