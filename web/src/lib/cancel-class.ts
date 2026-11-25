/**
 * ADM-SCH-07's reads and the decisions over them. ADR-0016.
 *
 * **This module imports nothing**, which is the fifth time this build has paid for the rule:
 * the sheet is a client component, so anything it imports has to be free of `next/headers` --
 * and a module that is pure in its *exports* and reaches `@/lib/api` at the top is impure to a
 * bundler. `tsc` and the linter both passed; the dev server answered 500 on every page in the
 * app, including sign-in, which is how the account page and the cash board found it. The read
 * lives in `cancel-class-reads.ts`.
 *
 * **The server returns the facts and this chooses the sentence**, which is D10: the members are
 * written to in their own language and the backend has no message catalogue, so what crosses
 * the wire are counts, dates and a reason code. The preview a manager reads is rendered here
 * from the same catalogue every other screen uses, and the sheet says it is one preview of a
 * message each member gets in their own language.
 */
/** The six reasons MOD-019 admits. A declared set, because what a member is owed depends on it. */
export const CANCELLATION_REASONS = [
  "instructor_unavailable", "resource_unavailable", "insufficient_bookings",
  "facility_closed", "weather", "other",
] as const;

export type CancellationReason = (typeof CANCELLATION_REASONS)[number];

export type Remedy = "move" | "credit";

export type NotMoved = {
  person_id: string;
  reason: "no_place" | "already_booked" | "ineligible";
  ineligible_because: string | null;
};

export type CancellationPreview = {
  session_id: string;
  remedy: Remedy;
  starts_at: string;
  timezone: string;
  booked: number;
  waiting: number;
  to_notify: number;
  destination: {
    session_id: string;
    starts_at: string;
    timezone: string;
    places_free: number;
  } | null;
  credit: {
    policy_key: string;
    display_name: string;
    days: number;
    expires_at: string;
    each: number | null;
  } | null;
  moving: string[];
  moved_count: number;
  must_choose: NotMoved[];
  must_choose_count: number;
  wrote_nothing: boolean;
};

export type CancellationDone = {
  session_id: string;
  status: string;
  remedy: Remedy;
  released: number;
  waitlist_lapsed: number;
  to_notify: number;
  moved: { person_id: string; booking_id: string }[];
  credited: { person_id: string; grant_id: string }[];
  must_choose: NotMoved[];
  notified: boolean;
  repeated: boolean;
};

/**
 * How much notice the members get, in whole days, **in the club's own frame**.
 *
 * The canvas's urgency is "This is tomorrow", which is a statement about calendar days at the
 * club rather than about hours: a class at 06:00 tomorrow and one at 23:00 tomorrow are both
 * tomorrow to the member reading the message. Both dates therefore come from the same zone --
 * this build has three recorded defects from a date computed in one frame and compared against
 * another, and the sharpest of them answered "-1 days since" a member's last visit.
 */
export function noticeDays(sessionLocalDate: string, todayLocalDate: string): number {
  const at = Date.parse(`${sessionLocalDate}T00:00:00Z`);
  const today = Date.parse(`${todayLocalDate}T00:00:00Z`);
  if (Number.isNaN(at) || Number.isNaN(today)) return 0;
  return Math.round((at - today) / 86_400_000);
}

/**
 * Which urgency sentence a reader gets.
 *
 * **A class in the past is its own case rather than a negative count.** MOD-019 admits
 * cancelling a session whose time has gone -- the status is what it turns on, not the clock --
 * and "starts in -2 days" is not a sentence. It is also the case where the notification is
 * moot, which the sheet says rather than implying there is still time.
 */
export function noticeKey(
  days: number,
): "cancelClass.noticePast" | "cancelClass.noticeToday"
  | "cancelClass.noticeTomorrow" | "cancelClass.noticeDays" {
  if (days < 0) return "cancelClass.noticePast";
  if (days === 0) return "cancelClass.noticeToday";
  if (days === 1) return "cancelClass.noticeTomorrow";
  return "cancelClass.noticeDays";
}

/**
 * Whether the sheet can be committed, and what is missing when it cannot.
 *
 * **The remedy is the canvas's own "REQUIRED"**, and a move with no destination is not a
 * remedy at all -- `Remedy` refuses it at the service boundary, so a form that sent one would
 * be asking the server to say what the screen already knows. The submit stays reachable and
 * the message slot names the field, which is this app's Input contract: a disabled button is
 * a reader left with no sentence.
 */
export function missingFields(
  remedy: Remedy | "", toSessionId: string,
): { remedy?: true; destination?: true } {
  if (remedy === "") return { remedy: true };
  if (remedy === "move" && toSessionId === "") return { destination: true };
  return {};
}

/**
 * A destination worth offering: another class at this club that could take somebody.
 *
 * **Not restricted to the same template.** A manager moving a cancelled Spin onto Friday's
 * Spin is the canvas's case and the commonest one, and restricting the list to one template
 * would hide a legitimate move onto another slot of the same format run from a different
 * template. Each option names its own coach and free places, so the choice is the manager's
 * on facts rather than on a filter nobody can see.
 *
 * **A cancelled or finished class is not offered**, because the command refuses it -- a
 * control the screen can see for itself is one it should not make a reader discover.
 *
 * **A *full* class is offered**, deliberately: the preview then says nobody fits and names
 * everybody who would have to choose another, which is information a manager acts on. Taking
 * `free` here and filtering on it would be a parameter with no reader, which this build calls
 * a finding -- so it is not taken.
 */
export function offerable(
  session: { session_id: string; status: string },
  cancelling: string,
): boolean {
  return session.session_id !== cancelling && session.status === "scheduled";
}
