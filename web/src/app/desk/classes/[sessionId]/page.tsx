
import { Banner } from "@/components/ds/banner";
import { NotYet } from "@/components/not-yet";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { PersonName } from "@/components/person-name";
import { withheldRemedy } from "@/lib/mask";
import { fill, formatInteger, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
import { ApiError, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import {
  checkinWindow, deskOrder, hasStarted, mayCheckIn, minutesUntil, nameOf, notHere,
  waitlistStateWord,
  presence, rowState, waiting, type NamedPerson, type Roster, type RosterBooking,
} from "@/lib/desk";
import { readNames, readRoster } from "@/lib/desk-reads";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { readSession } from "@/lib/scheduling";
import { inZone } from "@/lib/time";

import { CheckInButton } from "./check-in-button";

/**
 * FD-06 · CLASS CHECK-IN · RECEP · TOUCH.
 *
 * > "Spin · 19:00 · Dana · Studio 2 · 12 of 18 here · Waitlist · 3 … Four minutes to go, six
 * > not here. At 19:00 their places release to the waitlist automatically and the three
 * > waiting are notified — you do not have to remember. Rows are 48px because this is tapped
 * > while looking at a person, not at the screen. Hala's two prior no-shows are shown without
 * > judgement — it is context for the coach, not a flag on her."
 *
 * **The first Front Desk screen in this build, and the first working write form in this app
 * that is not behind a step-up.** `booking.attendance.write` is routine, so a receptionist at
 * an ordinary password sign-in can mark somebody present — which is exactly MOD-020's own gap
 * note ("a front desk cannot do it for them") closed without inventing a permission.
 *
 * **Touch density, on the wrapper.** The source puts Front Desk at Touch and says it is
 * "never user-selectable" there: 48px rows, 15px body, and a 44px minimum target. Setting it
 * on a wrapper is what this app's own density mechanism is for — and it found the second half
 * of a defect the row height already had, because the button floor was still scoped to
 * `:root` and so a screen that set its own density got a 36px button.
 *
 * **Three counts over the same rows, each from one place.** "12 of 18 here" is attendance
 * over the session's *places* rather than the roster's length, because a class with free
 * seats is twelve of eighteen; "six not here" is the bookings still open and unarrived; the
 * waitlist is a different list entirely. All three are in `@/lib/desk` so the screen cannot
 * compute one of them differently from another.
 *
 * **Names are composed, not joined.** The roster is MOD-020's and every row is a
 * `person_id`; paragraph 1300 bars the join and `GET /people/names` is the batch that keeps a
 * class of eighteen to one request. They arrive masked, so a routine front-desk session reads
 * the marker and the member number — which is the honest state for this reader and is why the
 * row's accessible name is built from what is *not* withheld.
 *
 * **And the canvas's own promise is the one thing this screen must not repeat.** "At 19:00
 * their places release to the waitlist automatically and the three waiting are notified — you
 * do not have to remember." Nothing in this build does either: settling a session is
 * deliberately not a worker job, because it decides whether somebody was absent, and MOD-013
 * sends no message. A screen that printed that sentence would be telling a receptionist to
 * forget something nobody is holding.
 */
export default async function ClassCheckInPage(
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;
  const { locale } = await presentation();
  // **The tenant's numerals rather than a constant** -- ADR-0015. Every count, date and time
  // on this page follows `localization.numerals`; money does not, and `MoneyValue` carries no
  // `numbering` prop at all so that exception is the component's rule rather than this page's
  // to remember. One read for the whole render: `conventions()` is React's per-request memo
  // and the layout starts it, so this costs no round trip of its own.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);
  const count = (value: number) => formatInteger(value, numbering);

  const [mayRoster, mayPeople, mayAttend, mayNames] = await gateAll([
    "booking.booking.read",
    "people.person.read",
    "booking.attendance.write",
    // For the withheld marker's remedy, not for any read. See `@/lib/mask`.
    "member.identity.read",
  ] as const);
  // **The remedy has to match the cause.** A legal name is MOD-014's `identity` class and
  // `member.identity.read` opens it; that permission is `financial`, so a step-up lifts the
  // mask for a session holding the grant at too low an assurance and does nothing for a role
  // that does not hold it. The row said "step up" to both until now. See `@/lib/mask`.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";

  if (!mayRoster.allowed) {
    return (
      <>
        <PageHeader title={text("desk.title")} />
        <Banner severity="info">{text(gateMessage(mayRoster))}</Banner>
      </>
    );
  }

  let roster: Roster | null = null;
  let failed = false;
  try {
    roster = await readRoster(sessionId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }
  // **Which class this is, which the roster cannot say.** The canvas leads "Spin · 19:00 ·
  // Dana · Studio 2", and every one of those is MOD-019's: the roster is MOD-020's and
  // carries a session id, an instant and a count. A desk that cannot see which class it is
  // looking at is a desk checking people into the wrong one. Composed through the scheduling
  // gate rather than joined, like every other pair of modules on this surface -- and a
  // refusal there costs the heading, not the roster.
  const detail = await readSession(sessionId).catch(() => null);
  if (failed || roster === null) {
    return (
      <>
        <PageHeader title={text("desk.title")} />
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </>
    );
  }

  // **One request for every name on the screen**, the roster and the waitlist together: a
  // waiting member is a person a desk may have to speak to, and two batches would be two
  // round trips for one page.
  //
  // **And a failure here is said, not swallowed.** Every row falls back to the withheld
  // marker when a name is missing, which is the right rendering for a masked one and the
  // wrong *explanation* for a read that did not happen: a desk told "withheld" goes looking
  // for a step-up that would change nothing. The first version caught the error and moved
  // on, and the screen then spent an afternoon claiming every member's name was masked
  // because the backend had been started before this route existed.
  let names = new Map<string, NamedPerson>();
  let namesFailed = false;
  if (mayPeople.allowed) {
    try {
      names = await readNames([
        ...roster.bookings.map((b) => b.person_id),
        ...roster.waitlist.map((e) => e.person_id),
      ]);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      namesFailed = true;
    }
  }

  const { here, places } = presence(roster);
  const absent = notHere(roster);
  const queue = waiting(roster);
  const now = new Date();
  const minutes = minutesUntil(roster.starts_at, now);
  const started = hasStarted(roster.starts_at, now);
  // **In the site's own zone**, which is the schedule board's hard-won rule: MOD-019 stores a
  // UTC instant and the local facts it came from because neither is derivable from the
  // other, and a surface that slices the ISO string renders the UTC wall time under a
  // heading promising the site's. Four layers of green assertions missed it there.
  const when = detail === null
    ? null : inZone(roster.starts_at, detail.timezone);
  const studio = detail?.resources.find((r) => r.resource_kind === "studio")
    ?? detail?.resources.find((r) => r.resource_kind === "room");
  // **The class's identity, each part dropped rather than guessed.** Built as a list so the
  // separator belongs to the join rather than to each part: with the counts moved out of this
  // line, whichever part is last must not carry a trailing one -- and a class with no
  // scheduling read at all has no line rather than an empty one.
  const identity: React.ReactNode[] = [
    ...(when === null ? [] : [
      <>
        <span className="data">{when.time}</span>
        {" "}
        <span className="muted">{when.zone}</span>
      </>,
    ]),
    ...(detail?.staff ? [detail.staff] : []),
    ...(studio ? [studio.display_name] : []),
  ];

  return (
    <div className="stack" data-density="touch">
      {/* **The canvas's own header line**: "Spin · 19:00 · Dana · Studio 2". The title is the
          class, because that is what a receptionist is looking at; each part after it is
          dropped rather than guessed when the scheduling read is refused or the session has
          no coach or studio assigned.
          **What is left here is the class's identity, not its figures.** "12 of 18 here" was
          the last thing on this line and it is the number a desk is standing there to read,
          so it is a figure below rather than 14px of caption beside a studio name. */}
      <PageHeader
        title={detail?.display_name ?? text("desk.title")}
        {...(identity.length === 0 ? {} : {
          figures: identity.map((part, index) => (
            <span key={index}>{index === 0 ? null : " · "}{part}</span>
          )),
        })}
      />

      {/* **Who is here, and who is still waiting.** The label under the first figure is the
          message the header line used to carry, so "12" is read as "12 of 18 here" and the
          denominator is not lost on its way out of that line. */}
      <MetricRow label={text("desk.roster")}>
        <MetricCell
          label={fill(locale, "desk.ofHere", { places: count(places) })}
          value={count(here)}
        />
        <MetricCell
          label={text("desk.waitlistHeading")}
          value={count(queue.length)}
        />
      </MetricRow>
      {detail === null ? (
        <p className="muted">{text("desk.classUnknown")}</p>
      ) : null}
      {namesFailed ? (
        <Banner severity="attention">{text("desk.namesUnread")}</Banner>
      ) : !mayPeople.allowed ? (
        <p className="muted">{text("desk.namesNotPermitted")}</p>
      ) : null}

      {/* **The sentence the canvas leads with, and it is derived rather than typed.** It
          exists only while the class is still to start: "started eleven minutes ago" is a
          different sentence and printing the first with a minus sign is what a receptionist
          reads at a glance. */}
      {absent.length > 0 && (minutes !== null || started) ? (
        <Banner
          severity="attention"
          title={minutes !== null
            ? fill(locale, "desk.minutesToGo", { minutes: count(minutes) })
            : text("desk.alreadyStarted")}
        >
          {fill(locale, "desk.notHereYet", { count: count(absent.length) })}
        </Banner>
      ) : null}

      <section className="page-section" aria-labelledby="desk-roster">
        <h2 id="desk-roster">{text("desk.roster")}</h2>
        {roster.bookings.length === 0 ? (
          <p className="muted">{text("desk.nobodyBooked")}</p>
        ) : (
          <ul className="ds-desk-rows">
            {deskOrder(roster.bookings).map((booking) => (
              <Row
                key={booking.booking_id}
                locale={locale} numbering={numbering} sessionId={sessionId}
                booking={booking} person={names.get(booking.person_id)}
                mayAttend={mayAttend.allowed} now={now}
                nameWithheld={nameWithheld}
              />
            ))}
          </ul>
        )}
      </section>

      {queue.length > 0 ? (
        <section className="page-section" aria-labelledby="desk-waitlist">
          <h2 id="desk-waitlist">{text("desk.waitlistHeading")}</h2>
          <ol className="ds-desk-rows">
            {queue.map((entry) => (
              <li key={entry.entry_id} className="ds-desk-row">
                <span className="ds-desk-row-name">
                  <span className="data">{count(entry.position)}</span>{" "}
                  <PersonName
                    locale={locale} person={names.get(entry.person_id)}
                    nameWithheld={nameWithheld}
                  />
                </span>
                {/* **One vocabulary, read through one function.** This built its key from
                    the stored value -- and `t` throws rather than falling back, while only
                    two of MOD-020's seven waitlist states had a key: an expired offer, which
                    keeps its place and can be offered again, would have taken this page down.
                    The session's own roster words the same states, so the map lives beside
                    the type they belong to and neither screen can word one state two ways. */}
                <span className="muted">
                  {waitlistStateWord(entry.state) === null
                    ? <span className="data" dir="ltr">{entry.state}</span>
                    : text(waitlistStateWord(entry.state) as MessageKey)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <NotYet locale={locale} items={["desk.gapRelease", "desk.gapNotify", "desk.gapScan"]} />
    </div>
  );
}

function Row({
  locale, numbering, sessionId, booking, person, mayAttend, now, nameWithheld,
}: {
  locale: Locale;
  nameWithheld: MessageKey;
  /**
   * The tenant's numeral system, for the counts and dates this renders.
   *
   * **Widened from the literal `"latn"` by ADR-0015**, which is what the setting reaching a
   * page means. Money is the exception and is not rendered through this: `MoneyValue` carries
   * no numbering at all, and a direct `formatMoney` here passes the literal.
   */
  numbering: Numbering;
  sessionId: string;
  booking: RosterBooking;
  person: NamedPerson | undefined;
  mayAttend: boolean;
  now: Date;
}) {
  const state = rowState(booking);
  const shown = nameOf(person);
  // What distinguishes this row when the name is withheld. `WithheldLink`'s reasoning, for a
  // control rather than a link: a button whose only name is "Check in" is one of fourteen a
  // screen-reader user cannot tell apart.
  const label = shown ?? person?.member_number ?? booking.person_id.slice(0, 8);

  return (
    <li className="ds-desk-row" data-state={state}>
      <span className="ds-desk-row-name">
        <PersonName locale={locale} person={person} nameWithheld={nameWithheld} />
        {/* **Context, not a flag** — the canvas's own words. It is shown for everybody who
            has one, including the member who is already here, because a coach reads it
            before the class rather than at the door. */}
        {booking.prior_no_shows > 0 ? (
          <span className="muted ds-desk-row-context">
            {fill(locale, "desk.priorNoShows", {
              count: formatInteger(booking.prior_no_shows, numbering),
            })}
          </span>
        ) : null}
      </span>
      <span className="ds-desk-row-state">
        {t(locale, `desk.state.${state}` as MessageKey)}
      </span>
      {/* **The button only where the module would take it**, and a sentence where it would
          not: a desk opening tomorrow's class is told when it opens rather than handed a
          control that answers 409. */}
      {mayAttend && booking.state === "booked" && booking.checked_in_at === null ? (
        mayCheckIn(booking, now) ? (
          <CheckInButton
            locale={locale} bookingId={booking.booking_id} sessionId={sessionId}
            label={label}
          />
        ) : (
          <span className="muted ds-desk-row-state">
            {t(locale, checkinWindow(booking, now) === "early"
              ? "desk.checkInNotOpenYet" : "desk.checkInClosed")}
          </span>
        )
      ) : null}
    </li>
  );
}
