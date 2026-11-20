import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { RecordHeader } from "@/components/ds/record-header";
import { fill, formatInteger, t, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { presentation } from "@/lib/preferences";
import { heldBeyondRoster, readRoster } from "@/lib/booking";
import { readSession, type SessionResource } from "@/lib/scheduling";
import { inZone } from "@/lib/time";

/**
 * One session: what it holds, what it used to hold, and what changed about it.
 *
 * **The withheld reason is the point of this page.** MOD-019's review found a health fact read
 * out of a change reason by the routine schedule permission -- "she is having chemotherapy on
 * Tuesdays" -- so the server masks it for anybody who does not hold
 * `scheduling.session.change`. A surface that dropped the entry, or rendered an empty cell,
 * would undo that silently: an absent row says nothing changed, which is a different and
 * wrong fact. So the entry is rendered, the withholding is marked, and the marker says why.
 * That is MOD-014's rule -- a redacted record still exists -- applied one module over.
 *
 * **Former resources are a list of their own rather than a flag.** MOD-019 keeps a substituted
 * instructor's hold rather than deleting it, because the window a past conflict was decided
 * against has to stay readable; a single list with a flag puts a coach who was sent home back
 * on the roster the first time somebody forgets to filter.
 */
export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("scheduling.schedule.read");
  if (!may.allowed) {
    return (
      <Shell title={text("schedule.session")}>
        <Banner severity="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Banner>
      </Shell>
    );
  }

  // **Why the reason is withheld, which the response alone cannot say.** `reason_masked` is
  // one boolean over two different situations: a session too weak for a financial action, and
  // an identity that does not hold the permission at all. The first has a remedy and the
  // second does not, and offering a step-up for the second sends somebody looking for a
  // second factor that would change nothing. So the gate is asked, and it answers which --
  // the same pattern the Member 360 uses for an identity-class field.
  const { sessionId } = await params;
  // **The roster is MOD-020's and needs its own permission**, which is the module boundary
  // paragraph 4145 draws: the schedule owns the occurrence and its capacity, booking owns the
  // member's reservation. A reader may hold one and not the other, so the block is gated on
  // its own and a refusal says so rather than rendering an empty class.
  const [mayChange, mayRoster] = await Promise.all([
    gate("scheduling.session.change"),
    gate("booking.booking.read"),
  ]);
  const session = await readSession(sessionId).catch(toNull);
  const roster = mayRoster.allowed ? await readRoster(sessionId).catch(toNull) : null;
  if (session === null) {
    return (
      <Shell title={text("schedule.session")}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  // ADM-SCH-02's band: `NO COACH`, which is the one thing about a class that has to be
  // visible before anything else on the page. MOD-019 holds an instructor as a `staff`
  // resource, so "no coach" is the absence of one -- and a substituted instructor whose hold
  // was superseded is not one either, which is why this reads the live list.
  const hasCoach = session.resources.some((held) => held.resource_kind === "staff");
  const local = inZone(session.starts_at, session.timezone);
  const ends = inZone(session.ends_at, session.timezone);

  return (
    <Shell>
      <RecordHeader
        name={session.display_name}
        {...(hasCoach || session.status === "cancelled"
          ? {}
          : { band: { text: text("schedule.noCoach"), tone: "critical" as const } })}
        subline={
          <>
            <span className="data" dir="ltr">{local.date} {local.time}–{ends.time}</span>
            {" · "}
            <span className="data" dir="ltr">{session.timezone}</span>
            {" · "}
            {session.status}
            {session.resources.length === 0 ? null : (
              <> {"· "}{session.resources.map((held) => held.display_name).join(" · ")}</>
            )}
          </>
        }
      />
      <div className="ds-record-body">
      {/* ADM-SCH-02's four cells: BOOKED · FREE · WAITLIST · USUAL FILL. **The seats belong
          to MOD-019 and the waitlist to MOD-020**, which paragraph 4145 separates on purpose
          -- so a reader holding one permission and not the other gets one of the two as a
          refusal rather than a zero. */}
      <MetricRow label={text("schedule.metrics")}>
        <MetricCell
          label={text("schedule.booked")}
          value={<span className="data" dir="ltr">{formatInteger(session.held, "latn")}</span>}
          comparison={fill(locale, "schedule.ofPlaces", { places: session.places })}
        />
        <MetricCell
          label={text("schedule.freeMetric")}
          value={<span className="data" dir="ltr">{formatInteger(session.free, "latn")}</span>}
          {...(session.free === 0 ? { comparison: text("schedule.full") } : {})}
        />
        <MetricCell
          label={text("schedule.waitlistMetric")}
          {...(!mayRoster.allowed || roster === null
            ? {
              freshness: "unavailable" as const,
              unavailableBecause: text(
                mayRoster.allowed ? "metric.readFailed" : "metric.notPermitted"),
            }
            : {
              value: (
                <span className="data" dir="ltr">
                  {formatInteger(roster.waitlist.length, "latn")}
                </span>
              ),
            })}
        />
        <MetricCell
          label={text("schedule.usualFill")}
          // **`typeof`, not `=== null`.** A TypeScript type is a claim about a JSON
          // response, not a check on it: against a backend that predates this field the
          // value is `undefined`, which is not `null`, and `undefined / 100` is `NaN` --
          // which `formatInteger` refuses, so the whole page answered 500. Found by looking
          // at it, against a server that had not been restarted.
          {...(typeof session.usual_fill_bp !== "number"
            ? {
              // **No baseline is not zero.** A class running for the first time has no
              // usual fill, and 0% would read as one nobody ever books.
              freshness: "unavailable" as const,
              unavailableBecause: text("schedule.noBaseline"),
            }
            : {
              value: (
                <span className="data" dir="ltr">
                  {formatInteger(Math.round(session.usual_fill_bp / 100), "latn")}%
                </span>
              ),
              comparison: fill(locale, "schedule.overOccurrences",
                { count: session.usual_fill_over }),
            })}
        />
      </MetricRow>

      {/* **The header and the metric row say all of this**, and the `dl` that used to sit
          here repeated every figure a second time: the date, the zone and the status are the
          sub-line, and taken-of-places is the BOOKED cell. The canvas has no such list --
          ADM-SCH-02 goes straight from the four cells to the roster. */}

      {session.dst_adjusted ? <Banner severity="info">{text("schedule.dstExplained")}</Banner> : null}
      {session.cancellation_reason !== null ? (
        <Banner severity="info">
          {text("schedule.cancelled")}: {session.cancellation_reason}
        </Banner>
      ) : null}

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("schedule.resources")}</h2>
        </div>
        <div className="ds-panel-body">
          <Resources list={session.resources} timezone={session.timezone} />
        </div>
      </section>

      {session.former_resources.length > 0 ? (
        <section className="ds-panel">
          <div className="ds-panel-head">
            <h2 className="ds-panel-title">{text("schedule.formerResources")}</h2>
          </div>
          <div className="ds-panel-body">
            <Resources list={session.former_resources} timezone={session.timezone} />
          </div>
        </section>
      ) : null}

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("schedule.changes")}</h2>
        </div>
        <div className="ds-panel-body">
        {session.changes.length === 0 ? (
          <Banner severity="info">{text("schedule.noChanges")}</Banner>
        ) : (
          <>
            <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
              {session.changes.map((change) => (
                <li key={`${change.change_kind}-${change.recorded_at}`}>
                  {change.change_kind}
                  {" · "}
                  <span className="data" dir="ltr">
                    {inZone(change.recorded_at, session.timezone).date}{" "}
                    {inZone(change.recorded_at, session.timezone).time}
                  </span>
                  {" · "}
                  {/* **Marked, never dropped.** An absent reason reads as "nothing was
                      written", which is the one answer that is always wrong here. */}
                  {change.reason_masked ? (
                    <span
                      style={{
                        border: "1px dashed var(--color-border-default)",
                        padding: "0 var(--space-2)",
                        borderRadius: "var(--radius-sm)",
                      }}
                    >
                      {text("schedule.reasonWithheld")}
                    </span>
                  ) : (
                    (change.reason ?? "")
                  )}
                </li>
              ))}
            </ul>
            {session.changes.some((change) => change.reason_masked) ? (
              <>
                <p className="muted" style={{ margin: 0 }}>
                  {text("schedule.reasonWhy")}
                </p>
                {mayChange.step_up_required ? (
                  <p style={{ margin: 0 }}>
                    <Link
                      href={`/step-up?for=financial&action=scheduling.session.change`
                        + `&next=${encodeURIComponent(
                          `/schedule/${session.session_id}`)}`}
                    >
                      {text("schedule.raiseSession")}
                    </Link>
                  </p>
                ) : (
                  <p className="muted" style={{ margin: 0 }}>
                    {text("schedule.reasonUnreachable")}
                  </p>
                )}
              </>
            ) : null}
          </>
        )}
        </div>
      </section>

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 id="roster-heading" className="ds-panel-title">{text("roster.title")}</h2>
        </div>
        <div className="ds-panel-body">
        {!mayRoster.allowed ? (
          <Banner severity="info">
            {mayRoster.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Banner>
        ) : roster === null ? (
          <Banner severity="critical">{text("error.unexpected")}</Banner>
        ) : (
          <>
            {roster.bookings.length === 0 ? (
              <Banner severity="info">{text("roster.empty")}</Banner>
            ) : (
              <DataGrid
                caption={text("roster.title")}
                labelledBy="roster-heading"
                rows={roster.bookings}
                rowKey={(entry) => entry.booking_id}
                columns={[
                  {
                    header: text("roster.member"),
                    kind: "person",
                    priority: 1,
                    render: (entry) => (
                      <span className="data" dir="ltr">{entry.person_id.slice(0, 8)}</span>
                    ),
                  },
                  {
                    header: text("roster.checkedIn"),
                    kind: "status",
                    // Priority 1: whether somebody is in the room is what a coach opens a
                    // roster to find out.
                    priority: 1,
                    // **A check-in is recorded, not performed.** Nothing in this build reads
                    // a turnstile, so this is a claim a named actor made at a time -- and
                    // "not yet" is a different fact from a blank cell.
                    render: (entry) =>
                      entry.checked_in_at === null ? (
                        <span className="muted">{text("roster.notCheckedIn")}</span>
                      ) : (
                        <span className="data" dir="ltr">
                          {inZone(entry.checked_in_at, session.timezone).time}
                        </span>
                      ),
                  },
                  {
                    header: text("roster.state"),
                    kind: "status",
                    priority: 2,
                    render: (entry) => entry.state,
                  },
                  {
                    header: text("roster.source"),
                    kind: "text",
                    priority: 3,
                    render: (entry) => entry.source_kind,
                  },
                ]}
              />
            )}
            <h3 style={{ margin: 0, fontSize: "var(--type-label-size)" }}>
              {text("roster.waitlist")}
            </h3>
            {roster.waitlist.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>
                {text("roster.noWaitlist")}
              </p>
            ) : (
              <ol style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
                {roster.waitlist.map((entry) => (
                  <li key={entry.entry_id}>
                    <span className="data" dir="ltr">
                      {entry.person_id.slice(0, 8)}
                    </span>
                    {" · "}
                    {entry.state}
                  </li>
                ))}
              </ol>
            )}
            {/* **A held place need not be on this list.** An unanswered waitlist offer holds
                one, and MOD-019's hold is the authority rather than the booking -- so two
                numbers that look like they should agree sometimes do not, and saying so beats
                rendering them bare. */}
            {heldBeyondRoster(roster) > 0 ? (
              <Banner severity="info">{text("roster.heldBeyond")}</Banner>
            ) : null}
            <p className="muted" style={{ margin: 0 }}>
              {text("roster.capacityIsElsewhere")}
            </p>
          </>
        )}
        </div>
      </section>

      {session.conflict_overrides.length > 0 ? (
        <section className="ds-panel">
          <div className="ds-panel-head">
            <h2 className="ds-panel-title">{text("schedule.overrides")}</h2>
          </div>
          <div className="ds-panel-body">
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {session.conflict_overrides.map((override) => (
              <li key={override.overridden_at}>
                <span className="data">
                  {formatInteger(override.conflict_count, "latn")}
                </span>
                {" · "}
                {override.conflict_summary}
                {" · "}
                {override.reason}
              </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
      </div>
    </Shell>
  );
}

function Resources({
  list,
  timezone,
}: {
  list: (SessionResource & { superseded_at?: string })[];
  timezone: string;
}) {
  return (
    <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
      {list.map((resource) => (
        <li key={`${resource.resource_id}-${resource.superseded_at ?? "live"}`}>
          {resource.display_name}
          {" · "}
          <span className="data" dir="ltr">
            {resource.resource_kind}
          </span>
          {resource.quantity > 1 ? (
            <>
              {" × "}
              <span className="data">{formatInteger(resource.quantity, "latn")}</span>
            </>
          ) : null}
          {resource.superseded_at !== undefined ? (
            <>
              {" · "}
              <span className="data" dir="ltr">
                {inZone(resource.superseded_at, timezone).date}{" "}
                {inZone(resource.superseded_at, timezone).time}
              </span>
            </>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * The record shell.
 *
 * **No breadcrumb.** The rail is the navigation and `Schedule` is on it; a link above the
 * title repeating a rail entry is the chrome saying the same thing twice, which is the
 * pattern this surface removed from every other screen.
 *
 * A failure before the session is read has no name to put in a `RecordHeader`, so those
 * paths fall back to `PageHeader` -- a header with a status band and an empty name would be
 * worse than one that says what the page is.
 */
function Shell({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="ds-inspector-pane">
      {title === undefined ? null : <PageHeader title={title} />}
      {children}
    </div>
  );
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
}



