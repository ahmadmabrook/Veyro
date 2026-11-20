import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { listLocations, type Location } from "@/lib/organization";
import { presentation } from "@/lib/preferences";
import { needsAttention, readCalendar } from "@/lib/scheduling";
import { inZone } from "@/lib/time";

/**
 * The week's schedule at one site: MOD-019's calendar, rendered as the board it is for.
 *
 * **A site has to be chosen before there is anything to show**, and the site is where the
 * timezone lives. MOD-019 reads every rota window and converts every occurrence in the
 * location's own zone, so a board that rendered instants without saying which zone they are
 * in would be inviting the one mistake the module is built to avoid. The zone is on the page.
 *
 * **Three numbers per session, because capacity alone is not what a booking is counted
 * against.** `places` is the capacity plus whatever overbooking was declared, `held` is a sum
 * over the hold rows rather than a counter anybody stores, and `free` is the module's own
 * answer -- a surface that subtracted for itself would render a negative number for a session
 * whose overbooking was reduced after the holds were taken.
 *
 * **`dst_adjusted` is the one flag worth marking.** A full class is ordinary and a cancelled
 * one is a decision somebody made; an occurrence stepped forward because its local time did
 * not exist that day is a session whose members were told a time that is not when it happens.
 * Nothing else on this board is an alert, deliberately.
 */
export default async function SchedulePage({
  searchParams,
}: {
  searchParams: Promise<{ site?: string; from?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
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
  const to = addDays(from, 6);
  const calendar = await readCalendar(chosen, from, to).catch(toNull);
  if (calendar === null) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  return (
    <Shell locale={locale}>
      <dl className="facts">
        <dt className="muted">{text("schedule.site")}</dt>
        <dd style={{ margin: 0 }}>{calendar.location_name}</dd>
        <dt className="muted">{text("schedule.timezone")}</dt>
        <dd style={{ margin: 0 }}>
          <span className="data" dir="ltr">
            {calendar.timezone}
          </span>
        </dd>
      </dl>

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

      {calendar.sessions.length === 0 ? (
        <Banner severity="info">{text("schedule.empty")}</Banner>
      ) : (
        <>
          <table
            tabIndex={0}
            aria-labelledby="schedule-heading"
            style={{ width: "100%", borderCollapse: "collapse" }}
          >
            <thead>
              <tr>
                <th scope="col" style={headCell}>{text("schedule.when")}</th>
                <th scope="col" style={headCell}>{text("schedule.session")}</th>
                <th scope="col" style={headCell}>{text("schedule.held")}</th>
                <th scope="col" style={headCell}>{text("schedule.places")}</th>
                <th scope="col" style={headCell}>{text("schedule.free")}</th>
                <th scope="col" style={headCell}>{text("schedule.status")}</th>
              </tr>
            </thead>
            <tbody>
              {calendar.sessions.map((session) => (
                <tr key={session.session_id}>
                  <td style={cell}>
                    {/* **In the site's zone, which is what the heading promises.** Slicing the
                        ISO string renders the UTC wall time: a class at 18:00 in Amman read as
                        15:00, under a page that says it is showing the site's own timezone. */}
                    <span className="data" dir="ltr">
                      {inZone(session.starts_at, calendar.timezone).date}
                    </span>{" "}
                    <span className="data" dir="ltr">
                      {inZone(session.starts_at, calendar.timezone).time}
                    </span>
                  </td>
                  <td style={cell}>
                    <Link href={`/schedule/${session.session_id}`}>{session.display_name}</Link>
                    {needsAttention(session) ? (
                      <div className="muted" style={{ fontSize: "var(--type-label-size)" }}>
                        {text("schedule.dstMoved")}
                      </div>
                    ) : null}
                  </td>
                  <td style={cell}>
                    <span className="data">{formatInteger(session.held, "latn")}</span>
                  </td>
                  <td style={cell}>
                    <span className="data">{formatInteger(session.places, "latn")}</span>
                  </td>
                  <td style={cell}>
                    {session.free === 0 ? (
                      <span className="muted">{text("schedule.full")}</span>
                    ) : (
                      <span className="data">{formatInteger(session.free, "latn")}</span>
                    )}
                  </td>
                  <td style={cell}>{session.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* **What "Taken" and "Free" are.** Without this a reader takes them for stored
              counters, and the one thing MOD-019 refuses to keep is a `held_count`. */}
          <p className="muted" style={{ margin: 0 }}>
            {text("schedule.heldExplained")}
          </p>
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

const headCell: React.CSSProperties = {
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

