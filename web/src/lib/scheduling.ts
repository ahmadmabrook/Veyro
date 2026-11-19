import { api } from "@/lib/api";

/**
 * MOD-019's reads, typed.
 *
 * **Three of these fields are the module's own difficulty and a surface has to carry all
 * three.** `places` is the capacity plus the declared overbooking, `held` is a sum over the
 * hold rows rather than a counter anybody stores, and `free` is what is left -- so a board
 * that showed capacity alone would be telling an operator a number the booking path does not
 * use. `dst_adjusted` says the occurrence was moved because its local time did not exist that
 * day, which is a fact about this session that no amount of looking at the rule would reveal.
 *
 * **A change's reason arrives masked unless the caller could have written one.** MOD-019's own
 * review found a health fact read out of that column by the routine schedule permission, so
 * `reason` is null and `reason_masked` is true for everybody who does not hold
 * `scheduling.session.change`. That is the same shape as MOD-014's masked fields and it is
 * rendered the same way: a marked withholding, never an empty cell.
 */

export type ScheduledSession = {
  session_id: string;
  template_id: string;
  display_name: string;
  starts_at: string;
  ends_at: string;
  local_date: string;
  capacity: number;
  /** Capacity plus declared overbooking: the ceiling a hold is counted against. */
  places: number;
  /** A sum over the hold rows. Nothing stores it, which is the point. */
  held: number;
  free: number;
  status: string;
  /** The occurrence was stepped because its local time did not exist that day. */
  dst_adjusted: boolean;
};

export type Calendar = {
  location_id: string;
  location_name: string;
  timezone: string;
  from_date: string;
  to_date: string;
  count: number;
  sessions: ScheduledSession[];
};

export type SessionResource = {
  resource_id: string;
  resource_kind: string;
  quantity: number;
  resource_code: string;
  display_name: string;
};

export type SessionChange = {
  change_kind: string;
  replacement_id: string | null;
  replaced_id: string | null;
  /** Null when withheld. `reason_masked` is what says which. */
  reason: string | null;
  reason_masked: boolean;
  recorded_at: string;
};

export type SessionDetail = ScheduledSession & {
  location_id: string;
  timezone: string;
  overbook_places: number;
  cancellation_reason: string | null;
  rule_id: string;
  resources: SessionResource[];
  former_resources: (SessionResource & { superseded_at: string })[];
  changes: SessionChange[];
  conflict_overrides: {
    conflict_count: number;
    conflict_summary: string;
    reason: string;
    overridden_at: string;
  }[];
};

/** The calendar is bounded to 62 days by the module; this asks for a week by default. */
export function readCalendar(
  locationId: string,
  fromDate: string,
  toDate: string,
): Promise<Calendar> {
  const query = new URLSearchParams({
    location_id: locationId,
    from_date: fromDate,
    to_date: toDate,
  });
  return api<Calendar>(`/scheduling/calendar?${query.toString()}`);
}

export function readSession(sessionId: string): Promise<SessionDetail> {
  return api<SessionDetail>(`/scheduling/sessions/${sessionId}`);
}

/**
 * How full a session is, as three numbers a surface can render without arithmetic of its own.
 *
 * **`free` is the module's answer, not a subtraction done here.** `held` can exceed `places`
 * when overbooking was declared and then reduced, and MOD-019 clamps at zero -- a surface that
 * recomputed `places - held` would render a negative number in exactly that case.
 */
export function occupancy(session: ScheduledSession): {
  held: number;
  places: number;
  free: number;
  full: boolean;
} {
  return {
    held: session.held,
    places: session.places,
    free: session.free,
    full: session.free === 0,
  };
}

/** Whether this session is one an operator should look at rather than merely read. */
export function needsAttention(session: ScheduledSession): boolean {
  // A cancelled session is a decision somebody made, not a fault. A session that is full is
  // ordinary. What is worth a second look is one that was moved by a clock change, because
  // the members booked into it were told a time that no longer exists.
  return session.dst_adjusted && session.status !== "cancelled";
}
