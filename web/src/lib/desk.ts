/**
 * FD-06 · CLASS CHECK-IN — the front desk's view of a class about to start.
 *
 * **Decisions only, and no import that reaches `next/headers`.** The check-in control is a
 * client component, and this repository has paid for that lesson three times now.
 *
 * The canvas is specific about what the screen says and when: "Spin · 19:00 · Dana · Studio 2
 * · 12 of 18 here · Waitlist · 3", and under the roster, "Four minutes to go, six not here."
 * Those are three different counts over the same rows and getting any of them from a
 * different place is how two numbers on one screen start to disagree.
 */

import type { MessageKey } from "@/i18n/locale";

/** A booking as `GET /booking/sessions/{id}/roster` returns it. */
export type RosterBooking = {
  booking_id: string;
  person_id: string;
  state: string;
  source_kind: string;
  checked_in_at: string | null;
  booked_at: string;
  prior_no_shows: number;
  /** When the module will take a check-in for this booking: an hour before, until grace. */
  checkin_opens_at: string;
  checkin_closes_at: string;
};

export type RosterWaiting = {
  entry_id: string;
  person_id: string;
  state: string;
  position: number;
  offer_expires_at: string | null;
};

export type Roster = {
  session_id: string;
  status: string;
  starts_at: string;
  capacity: number;
  overbook_places: number;
  places: number;
  held: number;
  free: number;
  bookings: RosterBooking[];
  waitlist: RosterWaiting[];
};

/** A person as `GET /people/names` returns them, which may be withheld. */
export type NamedPerson = {
  person_id: string;
  legal_name: string | null;
  preferred_name: string | null;
  lifecycle_state: string | null;
  member_number: string | null;
};

/**
 * Who is here, out of how many.
 *
 * **"12 of 18 here" counts attendance, not bookings**, and the denominator is the session's
 * places rather than the roster's length: a class with six free seats is twelve of eighteen,
 * not twelve of twelve. Both come from the roster read, which takes the places from MOD-019's
 * session because this module owns no capacity — so the figure a coach reads and the figure
 * that refuses the nineteenth booking are the same number.
 */
export function presence(roster: Roster): { here: number; places: number } {
  return {
    here: roster.bookings.filter((b) => b.checked_in_at !== null).length,
    places: roster.places,
  };
}

/** Who is booked and has not arrived. The canvas's "six not here". */
export function notHere(roster: Roster): RosterBooking[] {
  return roster.bookings.filter(
    (b) => b.checked_in_at === null && b.state === "booked");
}

/** How many are waiting for a place, which is a different list from the roster. */
export function waiting(roster: Roster): RosterWaiting[] {
  return roster.waitlist.filter((e) => e.state === "waiting" || e.state === "offered");
}

/**
 * How long before a class the countdown is worth saying.
 *
 * **Ninety minutes, and the number is a judgement rather than a source.** The canvas's
 * sentence is a desk four minutes out -- "Four minutes to go, six not here" -- which is an
 * urgency, and an urgency about something tomorrow is not one. The first version printed
 * "2,266 minutes to go" for a class the next evening, found by opening the page: arithmetic
 * that is correct, a sentence that is absurd, and no assertion about text could see it.
 */
export const COUNTDOWN_WINDOW_MINUTES = 90;

/**
 * Minutes until the class starts, or `null` when the countdown does not apply.
 *
 * **Null in both directions**, because "four minutes to go", "started eleven minutes ago" and
 * "tomorrow at seven" are three different sentences: a screen that printed the first with a
 * minus sign, or with four digits, is the one a receptionist reads at a glance.
 */
export function minutesUntil(startsAt: string, now: Date): number | null {
  const start = Date.parse(startsAt);
  if (Number.isNaN(start)) return null;
  const minutes = Math.round((start - now.getTime()) / 60_000);
  if (minutes < 0 || minutes > COUNTDOWN_WINDOW_MINUTES) return null;
  return minutes;
}

/** Whether the class has already started, which the countdown deliberately cannot say. */
export function hasStarted(startsAt: string, now: Date): boolean {
  const start = Date.parse(startsAt);
  return !Number.isNaN(start) && start <= now.getTime();
}

/** What a row says about one member, in one word. */
export type RowState = "here" | "expected" | "absent" | "released" | "settled";

/**
 * **Derived from the booking, never declared by the caller**, which is MOD-020's own rule for
 * the state behind it: a no-show is three facts and nobody can mark one by hand.
 *
 * `released` is the gym's own cancellation — the module's worst shipped defect was that this
 * state existed and nothing wrote it, so every member of a cancelled class was recorded
 * absent with a fee and a strike. A roster that collapsed it into `absent` would put that
 * reading back on the screen.
 */
export function rowState(booking: RosterBooking): RowState {
  if (booking.checked_in_at !== null || booking.state === "attended") return "here";
  if (booking.state === "booked") return "expected";
  if (booking.state === "no_show") return "absent";
  if (booking.state === "released" || booking.state === "session_cancelled") {
    return "released";
  }
  return "settled";
}

/**
 * Whether this row can be checked in **now**.
 *
 * **The window as well as the state, because the module checks both.** `may_check_in`
 * refuses outside the check-in window -- it opens an hour before the session and closes
 * after that booking's own snapshotted grace -- and the first version of this screen
 * considered only the state, so a desk opening a class the next evening was offered a
 * button that answered 409. That is this build's own "a button that answered 403 is worse
 * than its absence", and it was found by a browser test rather than by reading: the refusal
 * came back as prose under a row nobody should have been able to act on.
 *
 * The window comes from the roster read, which computes it with the same function the write
 * uses — a screen and a refusal that disagree is worse than either.
 */
export function mayCheckIn(booking: RosterBooking, now: Date): boolean {
  if (booking.state !== "booked" || booking.checked_in_at !== null) return false;
  return checkinWindow(booking, now) === "open";
}

/** Where `now` sits against this booking's check-in window. */
export type WindowState = "early" | "open" | "closed";

export function checkinWindow(booking: RosterBooking, now: Date): WindowState {
  const opens = Date.parse(booking.checkin_opens_at);
  const closes = Date.parse(booking.checkin_closes_at);
  // **An unreadable window is `closed`, not `open`.** Failing toward offering a control the
  // module will refuse is the direction this whole function exists to avoid.
  if (Number.isNaN(opens) || Number.isNaN(closes)) return "closed";
  if (now.getTime() < opens) return "early";
  return now.getTime() < closes ? "open" : "closed";
}

/**
 * The roster in the order a desk reads it: who is still expected first.
 *
 * **Not booking order, which is what the read returns.** A receptionist four minutes from the
 * start is looking for the people who have not arrived; the ones already in the room are the
 * rows they want out of the way. Within each group the booking order stands, because that is
 * the only order the module has an opinion about.
 */
const GROUP: Record<RowState, number> = {
  expected: 0, here: 1, absent: 2, released: 3, settled: 4,
};

export function deskOrder(bookings: RosterBooking[]): RosterBooking[] {
  return [...bookings].sort((a, b) => {
    const byGroup = GROUP[rowState(a)] - GROUP[rowState(b)];
    return byGroup !== 0 ? byGroup : a.booked_at.localeCompare(b.booked_at);
  });
}

/** The name to show, or `null` when it is withheld or this person is not in the batch. */
export function nameOf(person: NamedPerson | undefined): string | null {
  if (person === undefined) return null;
  const shown = person.preferred_name ?? person.legal_name;
  return shown === null || shown === "***" ? null : shown;
}

/**
 * A booking's state, its origin and a waitlist entry's state, worded.
 *
 * **All three were rendered raw** -- `booked`, `front_desk`, `waiting` -- on the roster a
 * coach opens before a class. A stored enumeration where a word belongs is this
 * repository's most-repeated surface finding, and the Arabic page had it worst: Latin
 * letters and an underscore in the middle of an Arabic line, in neither catalogue, so
 * invisible to the parity sweep.
 *
 * **Two of the words carry a distinction the module calls load-bearing.** `cancelled` is
 * the member's own act and `released` is the gym calling the class off -- the module's own
 * comment says conflating them "is how somebody gets a strike for a class the gym called
 * off" -- so the two sentences say whose decision it was rather than both reading
 * "cancelled". The waitlist's `lapsed` is the same fact from the queue's side.
 *
 * **An unmapped value falls through to its stored form.** Each set is MOD-020's and may
 * grow; hiding a state somebody needs to see is worse than showing an ugly one.
 */
export function bookingStateWord(state: string): MessageKey | null {
  return (BOOKING_STATE as Record<string, MessageKey>)[state] ?? null;
}

export function bookingSourceWord(source: string): MessageKey | null {
  return (BOOKING_SOURCE as Record<string, MessageKey>)[source] ?? null;
}

export function waitlistStateWord(state: string): MessageKey | null {
  return (WAITLIST_STATE as Record<string, MessageKey>)[state] ?? null;
}

const BOOKING_STATE = {
  booked: "booking.state.booked",
  attended: "booking.state.attended",
  no_show: "booking.state.no_show",
  cancelled: "booking.state.cancelled",
  released: "booking.state.released",
} as const satisfies Record<string, MessageKey>;

const BOOKING_SOURCE = {
  member: "booking.source.member",
  waitlist: "booking.source.waitlist",
  front_desk: "booking.source.front_desk",
  migration: "booking.source.migration",
} as const satisfies Record<string, MessageKey>;

const WAITLIST_STATE = {
  waiting: "waitlist.state.waiting",
  offered: "waitlist.state.offered",
  confirmed: "waitlist.state.confirmed",
  declined: "waitlist.state.declined",
  expired: "waitlist.state.expired",
  withdrawn: "waitlist.state.withdrawn",
  lapsed: "waitlist.state.lapsed",
} as const satisfies Record<string, MessageKey>;
