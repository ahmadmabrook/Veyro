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
  /**
   * The live coach, or null where no live staff assignment exists.
   *
   * Null rather than an empty string, because a class with no coach is a gap somebody has to
   * fill and a blank reads as a name nobody typed. A substitution supersedes the outgoing
   * assignment and leaves the row, so this is the *live* one -- counting rows would show a
   * class whose coach went home ill as staffed.
   */
  staff: string | null;
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
  /** Null where no earlier occurrence of this rule exists — a baseline, not a zero. */
  usual_fill_bp: number | null;
  usual_fill_over: number;
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

// ------------------------------------------------------------ ADM-SCH-01's week grid
//
// The canvas is a 7-column grid of days with a row per local start time, and these are the
// decisions behind it: which days the week holds, which rows exist, where each session goes,
// and the three figures in the header. They are here rather than in the page so they can be
// tested without a browser -- the week-boundary cases especially, which are the ones a
// rendered screenshot would not make obvious.

/** A day in the grid, keyed by the site's own local date. */
export type WeekDay = { date: string; label: string; today: boolean };

/**
 * The seven local dates from `from`, inclusive.
 *
 * **Date arithmetic in UTC on a date-only string, deliberately.** `local_date` is already the
 * site's own calendar date -- MOD-019 computed it in the session's zone -- so the only job
 * here is to walk seven days from it. Constructing a `Date` from a bare `YYYY-MM-DD` parses
 * as UTC midnight, and adding days in UTC never crosses a clock change; doing the same in the
 * host's local zone gives six days or eight on the two nights a year it shifts.
 */
export function weekDays(from: string, locale: "en" | "ar", todayLocal: string): WeekDay[] {
  const start = Date.parse(`${from}T00:00:00Z`);
  return Array.from({ length: 7 }, (_, offset) => {
    const at = new Date(start + offset * 86_400_000);
    const date = at.toISOString().slice(0, 10);
    return {
      date,
      label: new Intl.DateTimeFormat(locale === "ar" ? "ar" : "en-GB", {
        timeZone: "UTC", weekday: "short", day: "numeric",
      }).format(at),
      today: date === todayLocal,
    };
  });
}


/**
 * A local date moved by whole weeks, for the previous/next links on a week grid.
 *
 * Same UTC-parse reasoning as `weekDays` and `monthDayLabel`: a bare `YYYY-MM-DD` is UTC
 * midnight and adding days in UTC never crosses a clock change, where the host's own zone
 * gives six days or eight on the two nights a year it shifts.
 */
export function shiftWeek(date: string, weeks: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + weeks * 7 * 86_400_000)
    .toISOString().slice(0, 10);
}

/**
 * The grid: one row per distinct local start time, each with one slot per day.
 *
 * **Bucketed by the local clock, not the instant.** MOD-019 stores a UTC instant *and* the
 * local facts it came from because neither is derivable from the other, and a grid that
 * bucketed by the UTC hour would put a Monday 00:30 class in Sunday's column and under the
 * wrong row. `local_date` is the column and the local wall time is the row.
 *
 * A session outside the seven days is dropped rather than forced into an edge column, which
 * is what a `from` that does not match the data would otherwise produce.
 */
export function weekRows(
  sessions: ScheduledSession[],
  days: WeekDay[],
  localTime: (session: ScheduledSession) => string,
): { time: string; cells: (ScheduledSession[] | null)[] }[] {
  const column = new Map(days.map((day, index) => [day.date, index]));
  const byTime = new Map<string, (ScheduledSession[] | null)[]>();
  for (const session of sessions) {
    const index = column.get(session.local_date);
    if (index === undefined) continue;
    const time = localTime(session);
    let row = byTime.get(time);
    if (row === undefined) {
      row = days.map(() => null);
      byTime.set(time, row);
    }
    // A slot can hold more than one class: two studios run at six o'clock, and a grid that
    // kept the last one would silently drop the other. `publishing.assess` shipped exactly
    // that defect -- a dict keyed on the start instant -- and which class vanished depended
    // on row order.
    row[index] = [...(row[index] ?? []), session];
  }
  return [...byTime.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, cells]) => ({ time, cells }));
}

/**
 * The three figures in ADM-SCH-01's header: "54 classes · 1 without a coach" and
 * "78% average fill".
 *
 * **The average is over the week on screen**, which is exact: the calendar read is bounded by
 * its date window rather than by a row limit, so every session in the week is here. That is
 * the difference between this and summing a paginated list, which reports the first page as
 * the whole.
 *
 * **A session with no places is excluded from the average rather than counted as zero.** A
 * cancelled class is not a class nobody came to.
 */
export function weekSummary(sessions: ScheduledSession[]): {
  classes: number;
  unstaffed: number;
  averageFillPercent: number | null;
} {
  const live = sessions.filter((session) => session.status !== "cancelled");
  const withPlaces = live.filter((session) => session.places > 0);
  const held = withPlaces.reduce((total, session) => total + session.held, 0);
  const places = withPlaces.reduce((total, session) => total + session.places, 0);
  return {
    classes: live.length,
    unstaffed: live.filter((session) => session.staff === null).length,
    // Null rather than zero where there is nothing to average: "0% fill" is a claim about a
    // week, and an empty week has not made one.
    averageFillPercent: places === 0 ? null : Math.round((held / places) * 100),
  };
}


/**
 * A site id out of a query string, checked for shape.
 *
 * The backend answers 422 for a malformed one -- `require_uuid` is in that route -- so this is
 * not the control. It is what keeps a mistyped link rendering the board's own refusal instead
 * of an unexpected-error panel.
 */
export function isUuid(value: string | undefined): value is string {
  return value !== undefined && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value);
}
