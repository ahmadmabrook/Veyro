import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { WeekGrid } from "@/components/ds/week-grid";
import { ProseNote } from "@/components/prose";

import { ExceptionForm, WithdrawForm } from "./exception-form";
import { fill, t, type MessageKey } from "@/i18n/locale";
import {
  currentSession,
  failureMessage,
  gate,
  gateMessage,
  gateVerdict,
} from "@/lib/api";
import { listLocations, type Location } from "@/lib/organization";
import { presentation } from "@/lib/preferences";
import { shiftWeek, weekDays } from "@/lib/scheduling";
import { inZone, monthDayLabel } from "@/lib/time";
import {
  anyRota,
  CELL_LABEL,
  cellMark,
  cellState,
  hourLabel,
  hourSpan,
  hours,
  listSchedulableResources,
  readResourceWeek,
  type CellState,
  type ResourceWeek,
  type SchedulableResource,
} from "@/lib/rota";

/**
 * ADM-SCH-04 · COACH AVAILABILITY · WEEK GRID — "When Yousef can work, and what is already
 * booked".
 *
 * **This is the schedule board's missing third view.** That board's own note says so: "`Coaches`
 * is in the gaps below: it is a grid of rota rows rather than of sessions, and nothing here
 * reads a resource's availability." Both halves are closed here — `GET /scheduling/availability`
 * is new, because `set_availability` had a writer and no reader since MOD-019 was built, which
 * is the fifth instance of this build's "a writer with no reader" shape.
 *
 * **The rota is the background and the bookings are drawn on top**, which is the canvas's own
 * structure and its own argument: "Reducing availability never deletes a booking — it surfaces
 * the conflict for a person to resolve, because the member on the other end has already been
 * told a time." So a session that the rota now refuses is **drawn and flagged**, never dropped
 * and never silently honoured, and the cells that are both booked and inside an exception have
 * a state of their own. A section beneath the grid lists each one, because a marked cell in a
 * grid of ninety is a thing somebody has to find.
 *
 * **Every time on this page is the resource's own zone, never a session's.** That is the defect
 * MOD-019 shipped and a reviewer found — `Window.timezone` was declared, written from the
 * resource's own location and read by nothing, so a London coach rostered 09:00–17:00 was
 * available for an 09:00 class in Amman. A grid of somebody's week is where that error would
 * be least questioned, so the zone is named on the page and the server converts.
 *
 * **Open hours are no figure where no rota binds, not zero.** A room, a court and a bike have
 * no rota in any meaningful sense and on the day a gym opens nobody has one, so the page says
 * "unconstrained" rather than drawing seven columns of "not working" — which would read as a
 * studio that can never be booked.
 *
 * Three things the design draws that this build does not, each named on the screen: a class and
 * a personal-training session are one state because nothing records a session kind; the grid is
 * hourly while the figures are exact minutes; and "Add an exception" is a form that is not
 * built — and, unusually, **not blocked**: `scheduling.availability.write` is the one
 * scheduling permission that is routine rather than stepped-up, and the catalogue says why.
 */
export default async function RotaPage({
  searchParams,
}: {
  searchParams: Promise<{ resource?: string; site?: string; from?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    const verdict = gateVerdict(may);
    return (
      <>
        <PageHeader title={text("rota.heading")} />
        <Banner severity={verdict === "gate_failed" ? "critical" : "info"}>
          {text(verdict === "denied" ? "rota.refusedWhy" : gateMessage(may))}
        </Banner>
      </>
    );
  }

  // Listing the clubs is a different permission from reading a rota, which is the schedule
  // board's rule: the rota read carries the resource's own name and zone, so a session holding
  // only the schedule read can open this page from a link.
  const maySites = await gate("tenancy.organization.read");
  const sites: Location[] | null = maySites.allowed
    ? await listLocations().catch(() => null)
    : null;

  const params = await searchParams;
  const site = isUuid(params.site) ? params.site : sites?.[0]?.location_id;
  // **Staff only in the picker.** The server answers for any resource and says `null` open
  // hours for one with no rota; offering every bike in the building would be offering a screen
  // that is empty for most of them.
  const staff = await listSchedulableResources({
    kind: "staff",
    ...(site ? { locationId: site } : {}),
  }).catch(() => null);

  const chosen = isUuid(params.resource)
    ? params.resource
    : staff?.resources[0]?.resource_id;
  if (chosen === undefined) {
    return (
      <>
        <PageHeader title={text("rota.heading")} />
        <Banner severity="info">
          {staff === null
            ? text("rota.pickResourceInLink")
            : text("rota.noResources")}
        </Banner>
      </>
    );
  }

  let week: ResourceWeek | null = null;
  let failed: MessageKey | null = null;
  try {
    week = await readResourceWeek(chosen, isDate(params.from) ? { from: params.from } : {});
  } catch (error) {
    failed = failureMessage(error);
  }
  if (week === null) {
    return (
      <>
        <PageHeader title={text("rota.heading")} />
        <Banner severity="critical">{text(failed ?? "error.unexpected")}</Banner>
      </>
    );
  }

  const span = hourSpan(week);
  // **Today in the resource's own zone**, which is the column `WeekGrid` marks. A board in
  // Amman read from a UTC server is three hours out for three hours a night, which is the
  // schedule board's own note one screen over.
  const todayAtSite = inZone(new Date().toISOString(), week.timezone).date;
  const first = week.window.first_day;
  // **Whether this reader may change a rota**, which decides three things on this page: the
  // form, the withdraw controls and whether a time-off reason is prose or a mark. The server
  // makes the same call for the third of those -- `may_read_reasons` is
  // `"scheduling.availability.write" in held_permissions(session)` -- so asking the gate here
  // and trusting the response's own masking there is one decision read twice rather than two
  // that can disagree.
  const mayWrite = (await gate("scheduling.availability.write")).allowed;
  // **This week's dated absences, which is what the canvas's button adds and the only thing
  // this screen withdraws.** A weekly working pattern is the rota itself rather than an
  // exception to it, and writing one is a different screen; `rota.exceptionsScope` says so
  // rather than leaving a reader to wonder why their Tuesdays are not listed.
  const exceptions = week.days.flatMap((day) =>
    day.windows
      .filter((w) => !w.recurring && w.kind === "time_off" && w.window_id !== null)
      .map((w) => ({
        window_id: w.window_id as string,
        date: day.date,
        starts_at: w.starts_at,
        ends_at: w.ends_at,
        reason: w.reason,
      })));
  // "This week" is current when today falls inside the window, which is what the reader
  // means -- not when `from` happens to equal today's date.
  const thisWeek = todayAtSite >= first && todayAtSite <= week.window.last_day;
  const binds = anyRota(week);
  const clashing = week.sessions.filter((one) => one.conflicts_with_availability);
  const here = (next: { resource?: string; from?: string }) => {
    const query = new URLSearchParams({ resource: next.resource ?? chosen });
    if (site) query.set("site", site);
    const from = next.from ?? (isDate(params.from) ? params.from : undefined);
    if (from) query.set("from", from);
    return `/rota?${query.toString()}`;
  };

  return (
    <>
      <PageHeader
        title={text("rota.heading")}
        figures={
          <span className="data" dir="ltr">
            {week.window.first_day} – {week.window.last_day}
          </span>
        }
      />
      {/* **A lead, not a heading.** The canvas sets this sentence at 19px because its card
          excerpt has no page title above it; here the `PageHeader` is the h1, so making this
          an `h2` would put a heading level in front of the section headings -- the sibling of
          the two-`h1` defect the staff record shipped. The reports index does the same. */}
      <ProseNote>{text("rota.title")}</ProseNote>

      {/* The canvas's own sub-line: who, which week, which club, and the hours figure. */}
      <p className="muted" style={{ margin: 0 }}>
        {week.display_name}
        {" · "}
        {fill(locale, "rota.weekOf", { first: monthDayLabel(week.window.first_day, locale) })}
        {week.location_name === null ? null : <>{" · "}{week.location_name}</>}
        {" · "}
        {week.open_minutes === null
          ? fill(locale, "rota.hoursBookedNoRota",
                 { booked: hours(week.booked_minutes) })
          : fill(locale, "rota.hoursBooked", {
              booked: hours(week.booked_minutes),
              open: hours(week.open_minutes),
            })}
        {" · "}
        {text("rota.timezone")}{" "}
        <span className="data" dir="ltr">{week.timezone}</span>
      </p>

      {staff !== null && staff.resources.length > 1 ? (
        <nav className="ds-filter-bar" aria-label={text("rota.whichResource")}>
          {staff.resources.map((one: SchedulableResource) => (
            <Link
              key={one.resource_id}
              className="ds-filter-chip"
              href={here({ resource: one.resource_id })}
              aria-current={one.resource_id === chosen ? "page" : undefined}
            >
              {one.display_name}
            </Link>
          ))}
        </nav>
      ) : null}

      {/* **A week grid needs a way to leave the week it opened on, and this one had none.**
          Found by TestSprite, which is the point of an independent layer: the whole screen
          answers "when can this coach work", and the question is almost always about a week
          that is not this one -- an exception agreed three weeks ago for a date next month
          is the canvas's own example. Without these links the default week was the only
          week, so the fixture's own exception was unreachable from the screen and the agent
          correctly reported it could not see the behaviour. `here({ from })` existed and
          nothing called it. */}
      <nav className="ds-filter-bar" aria-label={text("rota.whichWeek")}>
        <Link className="ds-filter-chip" href={here({ from: shiftWeek(first, -1) })} rel="prev">
          {text("rota.previousWeek")}
        </Link>
        <Link
          className="ds-filter-chip"
          href={here({ from: todayAtSite })}
          aria-current={thisWeek ? "page" : undefined}
        >
          {text("rota.thisWeek")}
        </Link>
        <Link className="ds-filter-chip" href={here({ from: shiftWeek(first, 1) })} rel="next">
          {text("rota.nextWeek")}
        </Link>
      </nav>

      {/* **No metric row, because the canvas has none and the sub-line above already
          carries the figure.** ADM-SCH-04 states the week in one sentence -- "Week of 17
          August · Khalda · 26 of 34 available hours booked" -- and puts the conflicts in the
          callout below the grid. Four cells repeating open, booked and conflicts put the same
          three numbers on the screen twice, which is a reader checking one against the other
          for a difference that cannot exist. */}
      <section className="page-section" aria-labelledby="rota-grid">
        <h2 id="rota-grid">{text("rota.gridTitle")}</h2>

        {!binds ? (
          // **"Unconstrained" is not "never available".** Seven columns of "not working"
          // would read as a studio nothing can be booked into, which is the opposite of true.
          <>
            <Banner severity="info">{text("rota.noRotaTitle")}</Banner>
            <ProseNote>{text("rota.noRotaBody")}</ProseNote>
          </>
        ) : span === null ? (
          <Banner severity="info">{text("rota.nothingToDraw")}</Banner>
        ) : (
          <>
            {/* **`WeekGrid` is the design system's own answer for this shape**, and it is
                ADM-SCH-01's component: seven day columns against a row per local time, with
                the sideways scroll the design sanctions in exactly two places because "a
                Tuesday is not a lower-priority Monday". Hand-rolling a second one was caught
                by the usage sweep, which is what that sweep is for.

                **Its "severity is an edge-mark and never a fill" rule holds here rather than
                conflicting with this canvas.** That rule is about a *class* cell: a week
                where three classes are tinted reads as a week three-quarters wrong. These
                cells are not severities -- they are states of availability, and the fill is
                the information the legend names. The one severity on this grid is a booking
                the rota refuses, and the canvas marks that with a border, which is the
                edge-mark the rule asks for. */}
            <WeekGrid
              labelledBy="rota-grid"
              timeHeader={text("rota.gridTitle")}
              days={weekDays(week.window.first_day, locale, todayAtSite)}
              rows={Array.from(
                { length: span.last - span.first + 1 },
                (_, index) => span.first + index,
              ).map((hour) => ({
                time: hourLabel(hour),
                cells: week.days.map((day) => {
                  const state: CellState = cellState(day, hour, week.sessions);
                  const mark = cellMark(state, day, hour, week.sessions);
                  return (
                    // **The mark is visible, because the canvas prints one and colour must
                    // not be the only channel.** ADM-SCH-04 writes PT or CLS in a booked cell
                    // and OFF in an exception, and leaves the quiet states blank -- which is
                    // the same sentence as "working hours are the background": a reader scans
                    // for the marks, not for the absence of them. This build cannot tell a
                    // class from a personal-training session, so the two the canvas draws are
                    // one here and the gaps below say so. The full state stays in the
                    // accessible name, because "Booked" alone does not say refused.
                    <span key={day.date} className="ds-rota-mark" data-state={state}>
                      <span className="ds-visually-hidden">{text(CELL_LABEL[state])}</span>
                      {mark ? (
                        <span className="ds-rota-mark-text" aria-hidden="true">
                          {text(mark)}
                        </span>
                      ) : null}
                    </span>
                  );
                }),
              }))}
            />

            <ul className="ds-rota-legend" aria-label={text("rota.legend")}>
              {(["open", "booked", "bookedPersonal", "bookedConflict", "exception",
                "closed"] as const).map(
                (state) => (
                  <li key={state}>
                    <span className="ds-rota-mark" data-state={state} aria-hidden="true" />
                    {text(CELL_LABEL[state])}
                  </li>
                ))}
            </ul>
          </>
        )}
      </section>

      <section className="page-section" aria-labelledby="rota-conflicts">
        <h2 id="rota-conflicts">{text("rota.conflictsTitle")}</h2>
        {clashing.length === 0 ? (
          <Banner severity="info">{text("rota.noConflicts")}</Banner>
        ) : (
          <>
            <Banner severity="attention">{text("rota.conflictLead")}</Banner>
            <dl className="facts">
              {clashing.map((one) => (
                <div key={one.session_id} style={{ display: "contents" }}>
                  <dt>
                    <Link href={`/schedule/${one.session_id}`}>
                      {/* **The kind where there is no name**, which is ADR-0019 D3:
                          a personal session stores none, so the catalogue words it
                          rather than the row carrying a copy of a member's name. */}
                      {one.label ?? text("rota.personalSession")}
                    </Link>
                    {" "}
                    <span className="muted data" dir="ltr">
                      {one.local_date} {one.starts_at_local}–{one.ends_at_local}
                    </span>
                  </dt>
                  <dd style={{ margin: 0 }}>{one.conflict_reason}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </section>

      {week.days.some((day) => day.windows.some((w) => w.reason_masked)) ? (
        <ProseNote>{text("rota.reasonMaskedWhy")}</ProseNote>
      ) : null}

      {/* **The first write form in this app that is not a member acting on their own
          account**, and it took a migration to earn: `sch_availability_windows` carried
          `GRANT SELECT, INSERT` and nothing else, so a day off entered on the wrong date was
          permanent. `scheduling.availability.write` is routine and AAL 1 by design, and a
          routine permission whose every act is uncorrectable is MOD-013's rule from the
          other side -- so `0017` adds the withdrawal and this adds the button for both.

          Gated on the write, not on the read: a form that answered 403 is worse than its
          absence, which is why every other write surface in this app is missing. */}
      {mayWrite ? (
        <section className="page-section" aria-labelledby="rota-exceptions">
          <h2 id="rota-exceptions">{text("rota.formTitle")}</h2>
          <ProseNote>{text("rota.formWhat")}</ProseNote>
          <ExceptionForm
            locale={locale}
            resourceId={chosen}
            defaultDate={first}
          />

          <h3>{text("rota.exceptionsTitle")}</h3>
          <ProseNote>{text("rota.exceptionsScope")}</ProseNote>
          {exceptions.length === 0 ? (
            <p className="muted">{text("rota.noExceptions")}</p>
          ) : (
            <ul className="ds-rota-exceptions">
              {exceptions.map((one) => (
                <li key={one.window_id}>
                  <span className="data" dir="ltr">
                    {one.date} {one.starts_at}&ndash;{one.ends_at}
                  </span>
                  {one.reason === null ? null : <span>{one.reason}</span>}
                  <WithdrawForm
                    locale={locale}
                    windowId={one.window_id}
                    label={`${one.date} ${one.starts_at}\u2013${one.ends_at}`}
                  />
                </li>
              ))}
            </ul>
          )}
          <ProseNote>{text("rota.withdrawWhat")}</ProseNote>
        </section>
      ) : null}

      <section className="page-section" aria-labelledby="rota-gaps">
        <h2 id="rota-gaps">{text("rota.gapsTitle")}</h2>
        <dl className="facts">
          {([
            // **"Add an exception" has left this list**, which is what the note it used to
            // carry said would happen: it was the one form here that was never blocked, and
            // the only thing missing was the remedy a routine, uncorrectable write needs.
            ["rota.gapKindLabel", "rota.gapKind"],
            ["rota.gapHourLabel", "rota.gapHour"],
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

function isUuid(value: string | undefined): value is string {
  return value !== undefined
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function isDate(value: string | undefined): value is string {
  return value !== undefined && /^\d{4}-\d{2}-\d{2}$/.test(value);
}
