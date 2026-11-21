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
  label: string;
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
  a_session_kind_is_not_recorded: string;
};

export function readResourceWeek(
  resourceId: string,
  options: { from?: string } = {},
): Promise<ResourceWeek> {
  const query = new URLSearchParams({ resource_id: resourceId });
  if (options.from) query.set("from_date", options.from);
  return api<ResourceWeek>(`/scheduling/availability?${query.toString()}`);
}

/** The five states the canvas's legend names, less the one this build cannot tell apart. */
export type CellState = "closed" | "open" | "exception" | "booked" | "bookedConflict";

export const CELL_LABEL: Record<CellState, MessageKey> = {
  closed: "rota.cellClosed",
  open: "rota.cellOpen",
  exception: "rota.cellException",
  booked: "rota.cellBooked",
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
 * The two tones the canvas draws are one here: nothing in this build distinguishes a class
 * from a personal-training session, and `rota.gapKind` says so rather than colouring a guess.
 */
export const CELL_MARK: Record<CellState, MessageKey | null> = {
  closed: null,
  open: null,
  exception: "rota.markOff",
  booked: "rota.markBooked",
  bookedConflict: "rota.markBooked",
};

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
 * **Nothing in this build records when a club is open** — the attendance report refuses a
 * capacity comparison for a neighbouring reason — so the span is the union of everything this
 * resource's own week touches: its rota rows and the sessions it holds. A rota *is* the
 * opening-hours statement for a resource, which is why deriving it here is honest and
 * deriving a club's from it would not be.
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
export function cellState(
  day: RotaDay,
  hour: number,
  sessions: RotaSession[],
): CellState {
  const from = hour * 60;
  const to = from + 60;
  const here = sessions.filter(
    (one) => one.local_date === day.date
      && overlaps(from, to, minutesOf(one.starts_at_local), minutesOf(one.ends_at_local)));
  if (here.length > 0) {
    return here.some((one) => one.conflicts_with_availability)
      ? "bookedConflict"
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
