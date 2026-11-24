/**
 * ADM-SCH-03 · CREATE A CLASS — "New recurring class".
 *
 * **Decisions only, and no import that reaches `next/headers`.** The form is a client
 * component, and this repository has paid for that lesson three times -- the account page's
 * first version made the *login* page answer 500, the cash board's parse did it again, and the
 * tell is a build error naming a chain of `[Client Component Browser]` imports.
 *
 * The canvas is seven controls and one live answer:
 *
 * > TYPE · Spin ▾   COACH · Omar Salti ▾
 * > *Omar already has PT at 19:00 Thursdays. With Ahmad Nabulsi, booked until 12 October.*
 * > *Dana and Yousef are both qualified and free at that hour.*  [Use Dana] [Keep Omar anyway]
 * > ROOM · Studio 2 ▾   CAPACITY · 20   TIME · 19:00
 * > *Studio 2 holds 20 bikes. Capacity cannot exceed the room.*
 * > REPEATS · S M T W **Th** F S   WAITLIST · Up to 5 · auto-promote · notify immediately
 * > **Create · 2 classes a week**
 * > Conflicts surface as the coach field changes, not on save -- a save-time error means
 * > re-deciding everything else too. It warns, it does not block: a manager may know Omar's
 * > PT is moving.
 */

/**
 * The week, Sunday first, which is the canvas's own order: `S M T W Th F S`.
 *
 * **Storage is Monday-first and reading is not.** `Window.weekday` is 0-Monday because that is
 * Python's convention, and `/rota` already records that this says nothing about how a week is
 * *read* -- the rota rows are keyed by number either way and only the order of the seven
 * columns moved. This is the same seven in the same order as that grid, so the two screens
 * cannot disagree about which column is Sunday.
 */
export const WEEK: readonly { weekday: number; key: WeekdayKey }[] = [
  { weekday: 6, key: "week.sun" },
  { weekday: 0, key: "week.mon" },
  { weekday: 1, key: "week.tue" },
  { weekday: 2, key: "week.wed" },
  { weekday: 3, key: "week.thu" },
  { weekday: 4, key: "week.fri" },
  { weekday: 5, key: "week.sat" },
];

export type WeekdayKey =
  | "week.sun" | "week.mon" | "week.tue" | "week.wed" | "week.thu" | "week.fri"
  | "week.sat";

/** One conflict, as `POST /scheduling/conflict-check` reports it. */
export type ScheduleConflict = {
  local_date: string;
  starts_at: string;
  kind: string;
  resource_id: string | null;
  resource_name: string | null;
  detail: string;
  with_session_id: string | null;
};

export type ConflictCheck = {
  clear: boolean;
  conflicts: ScheduleConflict[];
  alternatives: { resource_id: string; display_name: string | null }[];
  spare: Record<string, number>;
  occurrences: number;
  per_week: number | null;
  examined: number;
  examined_of: number;
  examined_from: string | null;
  examined_to: string | null;
  timezone: string;
};

/**
 * What to call a conflict, by its stored kind.
 *
 * **A vocabulary the backend stores is never a label**, which this app has five recorded
 * defects from -- a lifecycle state, three plan words, a wallet kind and a credential kind,
 * each rendered as its enum in the middle of an Arabic line. `MESSAGE_KEYS` is structurally
 * blind to all of them, because a string that never became a key is in neither catalogue.
 *
 * **An unknown kind falls through to `null` rather than to a word**, and the caller then shows
 * the server's `detail`: the set is `conflicts.py`'s and may grow, and hiding a clash somebody
 * has to act on would be worse than showing one in its raw form.
 */
export function conflictWord(kind: string): ConflictKey | null {
  switch (kind) {
    case "double_booked": return "newClass.clashBooked";
    case "over_capacity": return "newClass.clashCapacity";
    case "elsewhere": return "newClass.clashElsewhere";
    case "unavailable": return "newClass.clashRota";
    default: return null;
  }
}

export type ConflictKey =
  | "newClass.clashBooked" | "newClass.clashCapacity" | "newClass.clashElsewhere"
  | "newClass.clashRota";

/**
 * **There is no capacity ceiling here, and the canvas's sentence is why it is a gap.**
 *
 * "Studio 2 holds 20 bikes. Capacity cannot exceed the room." Enforcing it needs one fact
 * this build does not record: that a class *format* takes one unit of equipment per attendee.
 * `sch_resources.quantity` says how many bikes exist and `sch_template_requirements.quantity`
 * says how many a session takes, and nothing relates either to the capacity -- a yoga class
 * takes a room and no mats at all, so a ceiling applied to every class would be wrong more
 * often than right.
 *
 * The dry run returns the spare quantity of each anonymous requirement and this screen writes
 * none, so the figure has no reader here. Showing it as advice while not enforcing it would be
 * the shape this repository names a defect: a field explaining why the product did not do what
 * it was asked. It is in the screen's gap list instead, with what it needs.
 */

/**
 * What the form is asking about, as one string.
 *
 * **Derived rather than stored, which is what makes the stale-answer race impossible rather
 * than guarded.** `@/lib/walk-in` records the same lesson from the duplicate check: the first
 * version held the whole state and wrote to it from three places, so a reply about a proposal
 * the reader had already changed had to be caught by comparing against a ref. Here the answer
 * carries the key it was about and is simply not the answer to any other -- and the linter
 * refuses a synchronous `setState` in an effect, which is the same rule stated as a rule.
 *
 * Every field the check's answer depends on is in it, and nothing else is: the display name
 * and the template code change no clash.
 */
export function proposalKey(proposal: {
  locationId: string; serviceId: string; roomId: string; staffId: string;
  localTime: string; duration: number; capacity: number; waitlist: number;
  weekdays: readonly number[];
}): string {
  return [
    proposal.locationId, proposal.serviceId, proposal.roomId, proposal.staffId,
    proposal.localTime, proposal.duration, proposal.capacity, proposal.waitlist,
    [...proposal.weekdays].sort((a, b) => a - b).join("."),
  ].join("|");
}

/** An answer, with the proposal it was about. */
export type CheckedProposal = { key: string; result: ConflictCheck | null };

/**
 * What is known about the proposal on screen: the answer, or that none has arrived.
 *
 * `unchecked` and `clear` are different facts and the screen says so -- a check that could not
 * run has not told anybody the hour is free, which is `@/lib/contact-check`'s own rule for the
 * duplicate read one surface over.
 */
export type CheckState =
  | { kind: "incomplete" }
  | { kind: "asking" }
  | { kind: "checked"; result: ConflictCheck }
  | { kind: "unchecked" };

export function checkState(
  ready: boolean, key: string, answer: CheckedProposal | null,
): CheckState {
  if (!ready) return { kind: "incomplete" };
  if (answer === null || answer.key !== key) return { kind: "asking" };
  return answer.result === null
    ? { kind: "unchecked" } : { kind: "checked", result: answer.result };
}

/**
 * Whether the create may go ahead.
 *
 * **It warns, it does not block** -- the canvas's own sentence, and the reason this is a
 * function rather than a comment: "a manager may know Omar's PT is moving". So a clash never
 * holds the button. What a clash *does* change is the permission the create costs: generating
 * over one needs `scheduling.conflict.override` and a written reason, which is paragraph
 * 1842's Critical Control, so the reason is the thing that is required rather than the
 * absence of a clash.
 */
export function mayCreate(
  fields: { serviceId: string; roomId: string; staffId: string; weekdays: number[] },
  check: ConflictCheck | null,
  overrideReason: string,
): boolean {
  if (!fields.serviceId || !fields.roomId || !fields.staffId) return false;
  if (fields.weekdays.length === 0) return false;
  if (check !== null && !check.clear && overrideReason.trim().length === 0) return false;
  return true;
}

/** Why the create is held, or `null` when it is not. */
export type CreateHold = "fields" | "weekdays" | "reason";

export function holdReason(
  fields: { serviceId: string; roomId: string; staffId: string; weekdays: number[] },
  check: ConflictCheck | null,
  overrideReason: string,
): CreateHold | null {
  if (!fields.serviceId || !fields.roomId || !fields.staffId) return "fields";
  if (fields.weekdays.length === 0) return "weekdays";
  if (check !== null && !check.clear && overrideReason.trim().length === 0) return "reason";
  return null;
}

/**
 * The code a template gets, derived rather than typed.
 *
 * **The canvas draws no code field and this build has no scheme**, which is FD-05's membership
 * handle one module over and MOD-026's case number before it: minting one here would be
 * inventing the tenant's numbering, and asking a manager for it would be asking them to do the
 * product's job. `sch_templates.resource_code`'s shape is `^[A-Z0-9][A-Z0-9._-]{1,47}$`, so a
 * hex handle fits and reads as what it is.
 */
export function codeFor(seed: string): string {
  return `CLS-${seed.replace(/[^0-9a-f]/gi, "").slice(0, 12).toUpperCase()}`;
}

/**
 * How many classes a week the button states: "Create · 2 classes a week".
 *
 * Derived here rather than read back, because the figure has to move as the chips are tapped
 * and the check is debounced -- a button that lagged the chips by 400ms would be a count
 * nobody could trust. The server answers the same question for the rule it was sent, and the
 * two agree by construction: a weekly rule's occurrences per week *are* its weekdays.
 */
export function perWeek(weekdays: readonly number[]): number {
  return weekdays.length;
}
