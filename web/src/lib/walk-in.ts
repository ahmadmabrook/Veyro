/**
 * ADM-MEM-10 · ADD MEMBER MANUALLY — "New member · walk-in".
 *
 * **Decisions only, and no import that reaches `next/headers`.** The form is a client
 * component, and this repository has paid for that lesson twice: the account page's first
 * version put its decisions beside its fetchers and made the *login* page answer 500, and
 * the cash board's parse did it again. The tell is a build error naming a chain of
 * `[Client Component Browser]` imports and never mentioning `next/headers`.
 *
 * **Nothing here normalizes a phone number, and that is the point.** `normalize_contact` on
 * the server is MOD-007's normalizer, imported rather than reimplemented, and it is what the
 * write stores and what the duplicate check compares — one spelling rule in the build,
 * because two drift and the day they disagree a duplicate is invisible to one of them.
 * MOD-011's review found exactly that: a limiter lowercased where `normalize_phone` strips
 * separators, so eight spellings of one number each got a full budget. So this module decides
 * only *whether a value is worth asking about*, by counting digits, which is a question about
 * length and not a rule about spelling.
 */

/**
 * How many digits a value needs before the duplicate check runs.
 *
 * **Not a validation and not a rule about phone numbers.** It is the point at which asking
 * the server is worth a request: every keystroke before it would match either nothing or
 * everybody, and `api.request` is a real per-identity budget this repository has already
 * spent by accident — the browser suite tripped MOD-011's limiter at three hundred page views
 * and six tests came back saying the product had broken.
 *
 * Seven is the shortest national subscriber number in use anywhere, so it never withholds a
 * check from a number somebody could actually have typed in full.
 */
export const DETECTION_MIN_DIGITS = 7;

/** How long to wait after the last keystroke. A person types faster than this. */
export const DETECTION_DEBOUNCE_MS = 400;

export function digitsIn(typed: string): number {
  return (typed.match(/\d/g) ?? []).length;
}

/** Whether this value is long enough that asking the server tells us something. */
export function worthChecking(typed: string): boolean {
  return digitsIn(typed) >= DETECTION_MIN_DIGITS;
}

/** One holder of a contact value, as `GET /people/contact-match` returns it. */
export type ContactMatch = {
  person_id: string;
  legal_name: string | null;
  preferred_name: string | null;
  known_since: string;
  lifecycle_state: string | null;
  member_number: string | null;
  joined_on: string | null;
  is_primary: boolean;
};

export type MatchResult = {
  matches: ContactMatch[];
  count: number;
  more: boolean;
};

/**
 * What the form is showing about the phone that was typed.
 *
 * **The checked value is part of the state, and the dismissal is keyed to it.** "Different
 * person" is an answer about *this* number; a dismissal that survived an edit would be a
 * dismissal of a different number, and the next thing the desk types would go in unchecked
 * with the banner still hidden. So a change to the value puts the state back to `idle` and
 * the acknowledgement with it.
 */
export type DetectionState =
  | { kind: "idle" }
  | { kind: "tooShort" }
  | { kind: "checking"; value: string }
  | { kind: "clear"; value: string }
  | { kind: "found"; value: string; result: MatchResult }
  | { kind: "failed"; value: string };

/** Whether the detection on screen is about the value currently in the field. */
export function isAbout(state: DetectionState, value: string): boolean {
  return "value" in state && state.value === value;
}

/** What the server said about one value. The only part of this screen that is asynchronous. */
export type DetectionAnswerFor =
  | { value: string; outcome: "clear" }
  | { value: string; outcome: "unknown" }
  | { value: string; outcome: "match"; result: MatchResult };

/**
 * The detection state, derived from what is in the field and the newest answer.
 *
 * **Derived rather than stored, which is what makes the stale-answer race impossible rather
 * than guarded.** The first version held the whole state and wrote to it from three places --
 * the field being emptied, the value being too short, and the reply landing -- so a reply for
 * a number the desk had already edited had to be caught by comparing against a ref. That
 * guard was correct and it was a guard: miss it and a clear number reads as duplicated, or
 * worse, a duplicated one reads as clear. Here the answer carries the value it was about and
 * is simply not the answer to any other, so there is nothing to catch.
 *
 * **Found by the linter**, which refused `setState` inside the effect for two of those three
 * writes -- and it was right for a better reason than the one it gives: a value that can be
 * computed from a prop is not state, and storing it is what created the race in the first
 * place.
 */
export function detectionFor(
  value: string, answer: DetectionAnswerFor | null,
): DetectionState {
  if (value === "") return { kind: "idle" };
  if (!worthChecking(value)) return { kind: "tooShort" };
  if (answer === null || answer.value !== value) return { kind: "checking", value };
  if (answer.outcome === "match") return { kind: "found", value, result: answer.result };
  if (answer.outcome === "unknown") return { kind: "failed", value };
  return { kind: "clear", value };
}

/**
 * The interruption to show, or `null` when there is none.
 *
 * **One definition, because there were two.** The component computed "a match about this
 * value that nobody has acknowledged" inline for the banner while `mayCreate` computed the
 * same thing for the button, and the mutation sweep found it immediately: breaking the
 * acknowledgement comparison in one left the other intact, so the suite stayed green with a
 * dismissal that outlived its number. That is this repository's "one module, two definitions
 * of the same balance", in a screen.
 */
export function interruption(
  state: DetectionState, acknowledgedValue: string | null, value: string,
): MatchResult | null {
  if (state.kind !== "found") return null;
  if (!isAbout(state, value)) return null;
  if (acknowledgedValue === value) return null;
  return state.result;
}

/**
 * Whether the form may be submitted.
 *
 * **A duplicate does not block the write, it interrupts it.** The canvas is explicit: "Open
 * that record" and "Different person" — two records for one person is sometimes right, a
 * shared family line being the ordinary case, and paragraph 10200 requires a human to decide
 * rather than a threshold. So the rule is an acknowledgement, not a refusal: somebody has to
 * have said "different person" about *this* number.
 *
 * **And a check that failed is not a check that passed.** If the server could not be asked,
 * the honest state is "we do not know", which is the same obligation as a match: say so and
 * let somebody decide. Treating an unreachable check as clear would make a network blip into
 * a silent duplicate, which is this build's own "a control consulted once is a control with a
 * window" in a surface.
 */
export function mayCreate(
  state: DetectionState, acknowledgedValue: string | null, value: string,
): boolean {
  if (state.kind === "checking") return false;
  if (state.kind === "found") return interruption(state, acknowledgedValue, value) === null;
  // A check that could not run is held the same way, and released the same way: there is
  // nothing else a person can do about a server that did not answer.
  if (state.kind === "failed") {
    return isAbout(state, value) && acknowledgedValue === value;
  }
  return true;
}

/** Why the create button is held, or `null` when it is not. */
export type WalkInHold = "checking" | "duplicate" | "unknown";

export function holdReason(
  state: DetectionState, acknowledgedValue: string | null, value: string,
): WalkInHold | null {
  if (mayCreate(state, acknowledgedValue, value)) return null;
  if (state.kind === "checking") return "checking";
  if (state.kind === "failed") return "unknown";
  return "duplicate";
}

/**
 * The fields a walk-in cannot be created without.
 *
 * `POST /people` requires a legal name and nothing else, and a record with no way to reach
 * the person is one nobody can use — which is the reason `PersonBody` takes the contact
 * points in the same command rather than leaving a window where the duplicate detector sees
 * somebody with no signals at all. The canvas draws both fields, so both are required here;
 * the email and the birth date it also names are not, because a walk-in who gives neither is
 * the ordinary case and refusing them would send them away.
 */
export function missingFields(fields: { name: string; phone: string }): {
  name?: true; phone?: true;
} {
  const missing: { name?: true; phone?: true } = {};
  if (fields.name.trim().length === 0) missing.name = true;
  if (!worthChecking(fields.phone)) missing.phone = true;
  return missing;
}

/**
 * The recognition line beside a matched record — "· Club · Sweifieh · joined Feb 2025".
 *
 * **Two of the canvas's four parts are not this module's to answer**, and the read says so
 * rather than leaving a surface to render an empty cell as a fact: the plan is MOD-017's and
 * a home club is a concept no module in this build has. What is left is the member number,
 * the standing, and when the record was known — which is what a desk actually recognises a
 * person by when the name is the thing they are unsure about.
 */
export function recognitionParts(match: ContactMatch): string[] {
  const parts: string[] = [];
  if (match.member_number !== null) parts.push(match.member_number);
  return parts;
}

/** The date a record is recognised by: when they joined, else when we first knew them. */
export function knownFrom(match: ContactMatch): string {
  return match.joined_on ?? match.known_since;
}
