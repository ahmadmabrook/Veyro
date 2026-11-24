import { isWithheld } from "@/lib/mask";

/**
 * FD-02 — "Member lookup", and the identity check this build can actually offer.
 *
 * The canvas is a field, a sentence and the matches: `SCAN OR TYPE  hala|`, "Two members
 * match. Check the photo before you let them through", two rows at 44px with a plan, a club
 * and the last four digits of a number, and a `Let in` on each. Its footnote argues the photo
 * size: "A receptionist confirming identity at a busy desk needs a face they can actually
 * recognise. Partial phone digits are the second check, because two members can share a name
 * but not a number."
 *
 * **The second check is the only one this build has**, because the photo needs an object store
 * — the third external blocker. So the sentence cannot say "check the photo", and a 44px grey
 * circle would read as a photo missing from the *record* rather than from the product. What is
 * drawn is the check that exists and a named absence for the one that does not.
 */

/** A match as `GET /people/lookup` returns it, masked by MOD-014's own gate. */
export type Match = {
  person_id: string;
  legal_name: string | null;
  preferred_name: string | null;
  lifecycle_state: string | null;
  member_number: string | null;
  joined_on: string | null;
  location_id: string | null;
  /** The last four of the primary number, or the marker, or null where none is recorded. */
  phone: string | null;
};

export type Lookup = {
  query: string;
  count: number;
  more: boolean;
  people: Match[];
  masked_fields: string[];
  a_prefix_of_the_name_and_nothing_else: string;
  a_number_is_matched_whole: string;
  the_phone_is_four_digits_and_never_the_number: string;
  the_plan_and_the_photo_are_not_this_module_s: string;
};

/**
 * What the lookup is in, which is four states and not two.
 *
 * The canvas draws the ambiguous one, which is the whole reason the screen exists — "ambiguous
 * matches list side by side rather than guessing". `asked` and `tooShort` are different facts
 * and a desk acts on them differently: nothing typed is the resting state of a field somebody
 * is about to scan into, and one character is a refusal with a reason.
 */
export type LookupState =
  | { kind: "resting" }
  | { kind: "tooShort"; typed: string }
  | { kind: "none"; typed: string }
  | { kind: "one"; typed: string }
  | { kind: "several"; typed: string; count: number };

export const MIN_QUERY = 2;

export function stateOf(typed: string, found: Lookup | null): LookupState {
  const folded = typed.trim();
  if (folded === "") return { kind: "resting" };
  if (folded.length < MIN_QUERY) return { kind: "tooShort", typed: folded };
  if (found === null || found.count === 0) return { kind: "none", typed: folded };
  if (found.count === 1) return { kind: "one", typed: folded };
  return { kind: "several", typed: folded, count: found.count };
}

/**
 * Which identity checks a row can actually be confirmed by.
 *
 * **Both are absences the screen has to name rather than imply.** A photo is the object store;
 * a withheld name is a session that may not read `identity` class, and a withheld number a
 * session that may not read `contact`. A row with neither readable is a row a desk cannot
 * confirm anybody by — which is worth saying, because the alternative is a receptionist
 * letting somebody through on a match they could not check.
 */
export type Checks = {
  /** A name they can read, rather than the withheld marker. */
  name: boolean;
  /** Four digits they can ask the person for. */
  digits: boolean;
  /** Always false in this build, and named rather than drawn. */
  photo: false;
};

export function checksFor(match: Match): Checks {
  return {
    name: match.legal_name !== null && !isWithheld(match.legal_name),
    digits: match.phone !== null && !isWithheld(match.phone),
    photo: false,
  };
}

/** Whether anything on this row could confirm the person in front of the desk. */
export function confirmable(match: Match): boolean {
  const checks = checksFor(match);
  return checks.name || checks.digits;
}

/**
 * The meta line under a name: the plan, the club and the last four.
 *
 * **Each part is absent rather than guessed**, which is the Member 360's own rule: the canvas
 * prints `Club · Sweifieh · ···4180`, and a row that printed `— · — · ···4180` with dashes
 * standing in for facts would read as a record with nothing in it. The plan is MOD-017's and
 * the club is the hierarchy's, so both are composed and either can be missing.
 */
export function metaParts(
  match: Match,
  { plan, club }: { plan: string | null; club: string | null },
): string[] {
  const parts: string[] = [];
  if (plan !== null) parts.push(plan);
  if (club !== null) parts.push(club);
  if (match.phone !== null && !isWithheld(match.phone)) {
    // The canvas's own rendering, and the leading marks are what make four digits read as the
    // end of a number rather than as a number.
    parts.push(`···${match.phone}`);
  }
  return parts;
}
