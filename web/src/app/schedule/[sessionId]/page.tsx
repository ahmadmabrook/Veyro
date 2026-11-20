import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
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
      <Shell locale={locale}>
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
      <Shell locale={locale}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  return (
    <Shell locale={locale} name={session.display_name}>
      <dl className="facts">
        <dt className="muted">{text("schedule.when")}</dt>
        {/* **The site's zone, not UTC.** The instant and the local facts are stored separately
            because neither is derivable from the other, and a surface that slices the ISO
            string throws away the half the reader needs. */}
        <dd style={{ margin: 0 }}>
          <span className="data" dir="ltr">
            {inZone(session.starts_at, session.timezone).date}
          </span>{" "}
          <span className="data" dir="ltr">
            {inZone(session.starts_at, session.timezone).time}
          </span>
          {" — "}
          <span className="data" dir="ltr">
            {inZone(session.ends_at, session.timezone).time}
          </span>
        </dd>
        <dt className="muted">{text("schedule.timezone")}</dt>
        <dd style={{ margin: 0 }}>
          <span className="data" dir="ltr">
            {session.timezone}
          </span>
        </dd>
        <dt className="muted">{text("schedule.status")}</dt>
        <dd style={{ margin: 0 }}>{session.status}</dd>
        <dt className="muted">{text("schedule.held")}</dt>
        <dd style={{ margin: 0 }}>
          <span className="data">{formatInteger(session.held, "latn")}</span>
          {" / "}
          <span className="data">{formatInteger(session.places, "latn")}</span>
        </dd>
        <dt className="muted">{text("schedule.free")}</dt>
        <dd style={{ margin: 0 }}>
          {session.free === 0 ? (
            <span className="muted">{text("schedule.full")}</span>
          ) : (
            <span className="data">{formatInteger(session.free, "latn")}</span>
          )}
        </dd>
      </dl>

      {session.dst_adjusted ? <Banner severity="info">{text("schedule.dstExplained")}</Banner> : null}
      {session.cancellation_reason !== null ? (
        <Banner severity="info">
          {text("schedule.cancelled")}: {session.cancellation_reason}
        </Banner>
      ) : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("schedule.resources")}</h2>
        <Resources list={session.resources} timezone={session.timezone} />
      </section>

      {session.former_resources.length > 0 ? (
        <section className="panel stack">
          <h2 style={{ margin: 0 }}>{text("schedule.formerResources")}</h2>
          <Resources list={session.former_resources} timezone={session.timezone} />
        </section>
      ) : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("schedule.changes")}</h2>
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
                      href={`/step-up?for=financial&next=${encodeURIComponent(
                        `/schedule/${session.session_id}`,
                      )}`}
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
      </section>

      <section className="panel stack">
        <h2 id="roster-heading" style={{ margin: 0 }}>
          {text("roster.title")}
        </h2>
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
              <table
                tabIndex={0}
                aria-labelledby="roster-heading"
                style={{ width: "100%", borderCollapse: "collapse" }}
              >
                <thead>
                  <tr>
                    <th scope="col" style={headCell}>{text("roster.member")}</th>
                    <th scope="col" style={headCell}>{text("roster.state")}</th>
                    <th scope="col" style={headCell}>{text("roster.source")}</th>
                    <th scope="col" style={headCell}>{text("roster.checkedIn")}</th>
                  </tr>
                </thead>
                <tbody>
                  {roster.bookings.map((entry) => (
                    <tr key={entry.booking_id}>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {entry.person_id.slice(0, 8)}
                        </span>
                      </td>
                      <td style={cell}>{entry.state}</td>
                      <td style={cell}>{entry.source_kind}</td>
                      <td style={cell}>
                        {/* **A check-in is recorded, not performed.** Nothing in this build
                            reads a turnstile, so this is a claim a named actor made at a
                            time -- and "not yet" is a different fact from a blank cell. */}
                        {entry.checked_in_at === null ? (
                          <span className="muted">{text("roster.notCheckedIn")}</span>
                        ) : (
                          <span className="data" dir="ltr">
                            {inZone(entry.checked_in_at, session.timezone).time}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
      </section>

      {session.conflict_overrides.length > 0 ? (
        <section className="panel stack">
          <h2 style={{ margin: 0 }}>{text("schedule.overrides")}</h2>
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
        </section>
      ) : null}
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

function Shell({
  locale,
  name,
  children,
}: {
  locale: Locale;
  name?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "860px" }}>
      <Link href="/schedule">{t(locale, "schedule.title")}</Link>
      <h1 style={{ margin: 0 }}>{name ?? t(locale, "schedule.session")}</h1>
      {children}
    </div>
  );
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
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

