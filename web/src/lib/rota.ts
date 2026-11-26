import { api } from "@/lib/api";
import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-SCH-04 — "When Yousef can work, and what is already booked".
 *
 * **The rota is the background and the bookings are drawn on top**, which is the canvas's own
 * sentence and the whole structure of the screen. The server decides what a rota says and
 * whether each booking collides with it (`app/scheduling/availability.py`); what is decided
 * here is only what a grid cell shows, which is a rendering question and is the one place a
 * reader could be misled.
 *
 * **A cell that is both booked and inside an exception shows both.** The canvas is explicit:
 * "His 17:30 with Hala sits inside it, so the grid shows both and the booking is flagged
 * rather than silently honoured or silently dropped." So `bookedConflict` is its own state,
 * not a booking that quietly wins over the exception nor an exception that hides the booking.
 */

export type RotaWindow = {
  kind: "working" | "break" | "time_off";
  timezone: string;
  starts_at: string;
  ends_at: string;
  recurring: boolean;
  /**
   * The row, so a caller who may change a rota has something to withdraw.
   *
   * Not gated: an identifier discloses nothing the window beside it does not, and the write
   * it enables is gated at the route.
   */
  window_id: string | null;
  /** Only `time_off` carries one, and only a caller who could set a rota reads it. */
  reason: string | null;
  reason_masked: boolean;
};

export type RotaDay = {
  date: string;
  weekday: number;
  /** Whether this resource's rota is a statement about this day at all. */
  rota_binds: boolean;
  /** `null` where no rota binds — not zero. The server's docstring says why. */
  open_minutes: number | null;
  open_spans: { starts_at: string; ends_at: string }[];
  windows: RotaWindow[];
  booked_minutes: number;
};

export type RotaSession = {
  session_id: string;
  /**
   * A class or a personal-training session. ADR-0019 — and until `0036` this was one state
   * where the canvas draws two, which the gap note under this grid said out loud.
   */
  session_kind: "class" | "personal";
  /**
   * The template's display name, and **null for a personal session** — because ADR-0019 D3
   * stores no name on the row: a label holding "PT · Hala Barakat" would be a copy of a
   * member's name in a scheduling table. The grid words the kind from its own catalogue
   * instead, which is also what keeps it translated.
   */
  label: string | null;
  local_date: string;
  starts_at_local: string;
  ends_at_local: string;
  minutes: number;
  quantity: number;
  conflicts_with_availability: boolean;
  conflict_reason: string | null;
};

export type ResourceWeek = {
  resource_id: string;
  resource_code: string;
  resource_kind: string;
  display_name: string;
  quantity: number;
  status: string;
  location_id: string | null;
  location_name: string | null;
  /** The zone every time on this grid is in: the resource's own, never a session's. */
  timezone: string;
  weeks: number;
  window: { first_day: string; last_day: string };
  days: RotaDay[];
  sessions: RotaSession[];
  open_minutes: number | null;
  booked_minutes: number;
  conflicts: number;
  an_unconstrained_resource_has_no_open_hours: string;
  a_booking_is_never_dropped: string;
  times_are_the_resources_own_zone: string;
  a_time_off_reason_is_masked: string;
  a_personal_session_has_no_label: string;
};

export function readResourceWeek(
  resourceId: string,
  options: { from?: string } = {},
): Promise<ResourceWeek> {
  const query = new URLSearchParams({ resource_id: resourceId });
  if (options.from) query.set("from_date", options.from);
  return api<ResourceWeek>(`/scheduling/availability?${query.toString()}`);
}

/**
 * The six states the canvas's legend names. **All six, as of ADR-0019.**
 *
 * It was five, with a note saying a class and a personal session were one state "because
 * nothing records a session kind" — which `0036` made false, so the note went and the sixth
 * state arrived with it. The canvas draws `PT` and `CLS` as different marks, so a reader
 * scanning a coach's week can tell the hour somebody is teaching from the hour somebody is
 * training one person.
 */
export type CellState =
  | "closed" | "open" | "exception" | "booked" | "bookedPersonal" | "bookedConflict";

export const CELL_LABEL: Record<CellState, MessageKey> = {
  closed: "rota.cellClosed",
  open: "rota.cellOpen",
  exception: "rota.cellException",
  booked: "rota.cellBooked",
  bookedPersonal: "rota.cellPersonal",
  bookedConflict: "rota.cellConflict",
};

/**
 * The short mark a cell prints, or `null` where the canvas leaves it blank.
 *
 * ADM-SCH-04 writes `PT` or `CLS` in a booked cell and `OFF` in an exception, and prints
 * nothing in the two quiet states. That is the same statement as "working hours are the
 * background, bookings are drawn on top": a reader scans for marks rather than for the
 * absence of them, and a grid that printed something in all ninety cells would have no
 * figure and ground at all.
 *
 * **It is also what keeps colour from being the only channel.** The full state stays in each
 * cell's accessible name, because "Booked" does not say that the rota now refuses it -- the
 * one distinction this screen exists for.
 *
 * **The two marks the canvas draws are two here**, as of ADR-0019: `CLS` for a class and `PT`
 * for a personal session. This comment used to say they were one "because nothing in this
 * build distinguishes" them, which was true until `0036` and is the shape of gap note that
 * outlives its gap -- the one this repository keeps finding.
 *
 * **A refused booking keeps the mark of whatever it is**, because the cell's border is what
 * says the rota refuses it: a reader needs both facts, and overwriting the kind would lose
 * the one they can act on. That is why `bookedConflict` has no entry here and `cellMark`
 * derives it -- a static map cannot, since the refusal is one state and the kind is not.
 * **This map claimed otherwise for a commit**, listing the class mark against the conflict
 * while `cellState`'s own comment says the refusal outranks the kind, so a refused personal
 * session was marked `CLS`: two comments in one module disagreeing about one rule, and the
 * code agreeing with the wrong one.
 */
export const CELL_MARK: Record<Exclude<CellState, "bookedConflict">, MessageKey | null> = {
  closed: null,
  open: null,
  exception: "rota.markOff",
  booked: "rota.markClass",
  bookedPersonal: "rota.markPersonal",
};

/**
 * The mark a cell prints, with the conflict's taken from what is actually booked in it.
 *
 * Reachable: a personal session is created only where the coach's rota covers the hour, so a
 * refused one is a rota somebody withdrew afterwards -- which `/rota` has a form for.
 */
export function cellMark(
  state: CellState, day: RotaDay, hour: number, sessions: RotaSession[],
): MessageKey | null {
  if (state !== "bookedConflict") return CELL_MARK[state];
  return sessionsIn(day, hour, sessions).every((one) => one.session_kind === "personal")
    ? "rota.markPersonal"
    : "rota.markClass";
}

/** `"09:30"` as minutes from midnight, so two wall-clock times can be compared. */
export function minutesOf(clock: string): number {
  const [hours, minutes] = clock.split(":");
  return Number(hours) * 60 + Number(minutes ?? 0);
}

/** `9` as `"09:00"`, padded and 24-hour — the axis is a clock, not prose. */
export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

/**
 * The hours the grid draws, derived from the data rather than from opening hours.
 *
 * **This grid does not read the club's opening hours** — they *are* recorded, per location, in
 * MOD-026's business calendar; this comment used to say nothing in the build held them, which
 * was false for a module — so the span is the union of everything this resource's own week
 * touches: its rota rows and the sessions it holds. A rota *is* the opening-hours statement for
 * a resource, which is why deriving it here is honest and deriving a club's from it would not
 * be. Reading the club's hours to bound the grid instead is work, and it would be the wrong
 * bound anyway: a coach's week is theirs, and a club open at seven says nothing about whether
 * this person is.
 *
 * `null` where there is nothing to draw at all, so the page shows an empty state rather than
 * twenty-four rows of "not working" for a room nobody wrote a rota for.
 */
export function hourSpan(week: ResourceWeek): { first: number; last: number } | null {
  const edges: number[] = [];
  for (const day of week.days) {
    for (const w of day.windows) {
      edges.push(minutesOf(w.starts_at), minutesOf(w.ends_at));
    }
  }
  for (const one of week.sessions) {
    edges.push(minutesOf(one.starts_at_local), minutesOf(one.ends_at_local));
  }
  if (edges.length === 0) return null;
  const first = Math.floor(Math.min(...edges) / 60);
  // The end is exclusive, so a window ending at 17:00 needs no 17:00 row and one ending at
  // 17:30 does. `ceil` of the end minus one hour is that row's index.
  const last = Math.max(first, Math.ceil(Math.max(...edges) / 60) - 1);
  return { first, last };
}

const overlaps = (aStart: number, aEnd: number, bStart: number, bEnd: number) =>
  aStart < bEnd && bStart < aEnd;

/**
 * What one cell of the grid is, for one day and one hour.
 *
 * The order is the design's: a booking is drawn on top of the rota, and a booking that sits
 * inside a break or a day off is **flagged rather than hidden**. So the two booked states are
 * checked first and the conflict wins over the plain one — a cell that is both is the single
 * thing this screen exists to show.
 */
/** The sessions that fall in one cell -- one definition, because `cellMark` asks too. */
export function sessionsIn(
  day: RotaDay, hour: number, sessions: RotaSession[],
): RotaSession[] {
  const from = hour * 60;
  const to = from + 60;
  return sessions.filter(
    (one) => one.local_date === day.date
      && overlaps(from, to, minutesOf(one.starts_at_local), minutesOf(one.ends_at_local)));
}

export function cellState(
  day: RotaDay,
  hour: number,
  sessions: RotaSession[],
): CellState {
  const from = hour * 60;
  const to = from + 60;
  const here = sessionsIn(day, hour, sessions);
  if (here.length > 0) {
    // **A refusal outranks the kind**, because the kind is what a reader *is* and the refusal
    // is what somebody has to resolve: an hour the rota now says no to is the one thing this
    // screen exists to surface. Where nothing is refused, a personal session is drawn as one
    // -- the canvas's own `PT` against `CLS`.
    if (here.some((one) => one.conflicts_with_availability)) return "bookedConflict";
    return here.every((one) => one.session_kind === "personal")
      ? "bookedPersonal"
      : "booked";
  }
  const removed = day.windows.some(
    (w) => (w.kind === "break" || w.kind === "time_off")
      && overlaps(from, to, minutesOf(w.starts_at), minutesOf(w.ends_at)));
  if (removed) return "exception";
  const open = day.open_spans.some(
    (span) => overlaps(from, to, minutesOf(span.starts_at), minutesOf(span.ends_at)));
  return open ? "open" : "closed";
}

/**
 * Hours as the header's own sentence needs them: "26 of 34 available hours booked".
 *
 * **Two numbers, never a percentage.** A session outside the rota is booked and not open, so
 * the ratio can exceed one — which is the case the screen is for. And `open` is `null` where
 * no rota binds, where the sentence has to change rather than divide by nothing.
 *
 * **A whole number, because this app has no decimal formatter and that is deliberate.**
 * `formatInteger` throws `ConventionError("integer required")` for a fraction, and the first
 * version of this returned tenths — so the page answered 500 from inside `fill`, on every
 * request, in the one place the figure is rendered. The numeral discipline is not an obstacle
 * here: it is the reason there is exactly one number-rendering path in a repository with a
 * cross-runtime parity test for it, and adding a second to show "1.5" would be the defect
 * that test exists to prevent.
 *
 * The rounding is stated on the screen rather than hidden, because across a week it is
 * immaterial and below an hour it is not: a half-hour booking reads as no hours beside a grid
 * cell that is visibly booked, and the exact minutes are on the route.
 */
export function hours(minutes: number): number {
  return Math.round(minutes / 60);
}

/** Whether any day in the window has a rota that binds, so the grid is worth drawing. */
export function anyRota(week: ResourceWeek): boolean {
  return week.days.some((day) => day.rota_binds);
}

/** A schedulable resource, as the picker needs it. */
export type SchedulableResource = {
  resource_id: string;
  resource_code: string;
  resource_kind: string;
  display_name: string;
  quantity: number;
  location_id: string | null;
  person_id: string | null;
  status: string;
};

/**
 * The resources a rota could be read for.
 *
 * **Narrowed to a kind by the caller, because the canvas is a coach's week.** A room, a court
 * and a bike have no rota in any meaningful sense -- the server returns `null` open minutes
 * for them and says why -- so offering every resource in the picker would be offering a
 * screen that is empty for most of them.
 */
export function listSchedulableResources(
  options: { kind?: string; locationId?: string } = {},
): Promise<{ count: number; resources: SchedulableResource[] }> {
  const query = new URLSearchParams();
  if (options.kind) query.set("kind", options.kind);
  if (options.locationId) query.set("location_id", options.locationId);
  const suffix = query.toString();
  return api<{ count: number; resources: SchedulableResource[] }>(
    `/scheduling/resources${suffix ? `?${suffix}` : ""}`);
}
