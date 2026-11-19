import { api } from "@/lib/api";

/**
 * MOD-020's reads, typed.
 *
 * **The module owns no capacity and the roster shows it.** `places`, `held` and `free` on this
 * response come from MOD-019's session, not from a count of the rows beside them: there is no
 * roster table and no cached total, because paragraph 4145 puts capacity on the schedule's
 * side of the line. A surface that counted the bookings it was handed would disagree with the
 * seat count the first time a hold existed without a booking behind it.
 *
 * **A waitlist position is derived from the order, not stored.** It is the row's place in a
 * queue ordered by when somebody joined, so it moves when the person ahead is promoted or
 * leaves -- which is what a member is actually asking when they ask where they are.
 */

export type RosterBooking = {
  booking_id: string;
  person_id: string;
  state: string;
  source_kind: string;
  checked_in_at: string | null;
  booked_at: string;
};

export type WaitlistEntry = {
  entry_id: string;
  person_id: string;
  state: string;
  /** Derived from the member's plan, never sent by a caller: it decides the queue order. */
  tier: number;
  joined_at: string;
  /** The position in the queue as it stands, not a stored rank. */
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
  waitlist: WaitlistEntry[];
};

export function readRoster(sessionId: string): Promise<Roster> {
  return api<Roster>(`/booking/sessions/${sessionId}/roster`);
}

/**
 * Whether the roster's own rows account for every held place.
 *
 * **They need not, and a surface that assumed they did would be wrong in the direction that
 * matters.** A place can be held by a waitlist offer nobody has answered, and MOD-019's hold
 * is the authority rather than the booking -- so `held` can exceed the bookings shown. Saying
 * so is better than rendering two numbers that look like they should agree.
 */
export function heldBeyondRoster(roster: Roster): number {
  const accounted = roster.bookings.length
    + roster.waitlist.filter((entry) => entry.state === "offered").length;
  return Math.max(0, roster.held - accounted);
}
