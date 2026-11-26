/**
 * ADM-SCH-05 — "Book Yousef with Hala". ADR-0019.
 *
 * **This module imports nothing, and that is not tidiness.** `@/lib/api` reaches
 * `next/headers`, and a *pure name* in a module that touches it is still impure to a bundler:
 * the client form imports three functions from here, so an `api` import at the top of this
 * file made `next/headers` part of a client bundle and the whole app answered a build error —
 * which `tsc` and the linter were both green on, for the fifth time in this build. The read
 * lives in `@/lib/pt-check.ts`, which is a server action and is the only caller of the route.
 *
 * **Nothing here is arithmetic.** The credit that would be spent, what is left after it, when
 * it expires and whether the coach is free are all the server's — `personal_session_quote`,
 * which picks the same grant the command draws on, soonest-expiring first. A screen that
 * computed any of them would be a second definition of a figure somebody is about to act on,
 * and a quote naming a credit the draw would not take is the worst of the four.
 *
 * What is decided here is only which sentence a reader is given, and that is the one place a
 * reader could be misled: the canvas's zero-credit state and its busy-coach state are two
 * different refusals with two different remedies, and a screen that merged them would tell
 * somebody the coach was busy when the member simply has nothing to spend.
 */

export type PersonalSessionClash = {
  kind: string;
  resource_id: string | null;
  detail: string;
  with_session_id: string | null;
};

export type PersonalSessionQuote = {
  coach_resource_id: string;
  coach_name: string;
  person_id: string;
  location_id: string;
  timezone: string;
  starts_at: string;
  ends_at: string;
  minutes: number;
  clashes: PersonalSessionClash[];
  coach_is_free: boolean;
  /** The grant the command would draw on. `null` where there is nothing to draw. */
  grant_id: string | null;
  /** `null` for an uncounted grant as well as for none at all — the two are told apart by
   *  `grant_id`, which is why both fields are returned rather than one. */
  credits_remaining: number | null;
  credits_remaining_after: number | null;
  credits_expire_at: string | null;
  credit_name: string | null;
  drawable_grants: number;
  may_book: boolean;
  needs_a_package: boolean;
  balance_is_unswept: boolean;
  soonest_expiring_is_spent_first: string;
};

/**
 * **One of the canvas's two refusals, and never both at once.**
 *
 * "At zero credits the button becomes *Sell a package first*" and a busy coach is a different
 * sentence with a different remedy — pick another hour. A screen that rendered one message for
 * both would tell somebody to buy a package because the coach is teaching, or send them
 * looking for another slot when what they need is a package.
 *
 * `ready` is the state the canvas draws: both answered, and the button says what it costs.
 */
export type BookingState = "ready" | "needsPackage" | "coachBusy" | "bothInTheWay";

export function bookingState(quote: PersonalSessionQuote): BookingState {
  if (quote.needs_a_package && !quote.coach_is_free) return "bothInTheWay";
  if (quote.needs_a_package) return "needsPackage";
  if (!quote.coach_is_free) return "coachBusy";
  return "ready";
}

/**
 * The local wall clock an instant falls on at the club, as `HH:MM`.
 *
 * **The club's zone, not the reader's.** The schedule board's own hard-won rule: a session
 * stores a UTC instant and the zone it was converted with precisely because neither is
 * derivable from the other, and a board that sliced the ISO string showed 15:00 under a
 * heading promising Asia/Amman. Four layers of tests did not notice.
 */
export function atClub(instant: string, timezone: string, locale: string): string {
  return new Date(instant).toLocaleTimeString(locale === "ar" ? "ar-JO" : "en-GB", {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    timeZone: timezone, numberingSystem: "latn",
  });
}

/** The instant a `date` and a `HH:MM` name, as the UTC string the routes take. */
export function instantFrom(day: string, clock: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !/^\d{2}:\d{2}$/.test(clock)) return null;
  // **Built as a local instant and sent as UTC.** `datetime-local` has no offset, so the
  // browser's own zone is what the reader typed in -- which is the honest reading of a desk
  // booking an hour they are standing in. The club's zone is what the *server* converts into
  // for the local date it stores, which is why that conversion is not attempted here.
  const at = new Date(`${day}T${clock}`);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}
