import { describe, expect, it } from "vitest";

import { MASK } from "@/lib/mask";
import {
  checksFor, confirmable, metaParts, stateOf, type Lookup, type Match,
} from "@/lib/lookup";

/**
 * FD-02's four states and the identity checks a row can be confirmed by.
 *
 * **A builder that refuses a state the server cannot produce**, which ADM-MSH-07 paid for: its
 * `commitmentLine` reached a branch with a hand-written quote the lifecycle cannot emit, so the
 * branch passed its assertion and was dead in the product. Here the server's own invariant is
 * that `count` is the length of `people` -- the read derives one from the other -- so `found`
 * throws on a pair that disagrees, and one test proves it throws.
 */

function match(over: Partial<Match> = {}): Match {
  return {
    person_id: "p-1",
    legal_name: "Hala Barakat",
    preferred_name: null,
    lifecycle_state: "member",
    member_number: "M-1",
    joined_on: "2025-02-03",
    location_id: "loc-1",
    phone: "4180",
    ...over,
  };
}

function found(people: Match[], over: Partial<Lookup> = {}): Lookup {
  const one: Lookup = {
    query: "hala",
    count: people.length,
    more: false,
    people,
    masked_fields: [],
    a_prefix_of_the_name_and_nothing_else: "",
    a_number_is_matched_whole: "",
    the_phone_is_four_digits_and_never_the_number: "",
    the_plan_and_the_photo_are_not_this_module_s: "",
    ...over,
  };
  if (one.count !== one.people.length) {
    throw new Error(
      "lookup_people derives `count` from the rows it returns, so a pair that disagrees is "
      + "a response the server cannot produce");
  }
  return one;
}

describe("what state the lookup is in", () => {
  it("is resting before anything is typed", () => {
    // The field's ordinary state: somebody is about to scan into it.
    expect(stateOf("", null)).toEqual({ kind: "resting" });
    expect(stateOf("   ", null)).toEqual({ kind: "resting" });
  });

  it("is too short at one character, which is a refusal with a reason", () => {
    // **One letter is every member whose name starts with it**, in alphabetical order -- not
    // an ambiguous match a desk resolves, and returning the first ten would read as "these
    // are the matches".
    expect(stateOf("h", null)).toEqual({ kind: "tooShort", typed: "h" });
  });

  it("is none when nobody matches", () => {
    expect(stateOf("hala", found([]))).toEqual({ kind: "none", typed: "hala" });
    // A read that failed is the same state to a desk: nothing to act on.
    expect(stateOf("hala", null)).toEqual({ kind: "none", typed: "hala" });
  });

  it("is one when exactly one does", () => {
    expect(stateOf("hala", found([match()])))
      .toEqual({ kind: "one", typed: "hala" });
  });

  it("is several when two do, which is the state the screen exists for", () => {
    // "Ambiguous matches list side by side rather than guessing."
    expect(stateOf("hala", found([match(), match({ person_id: "p-2" })])))
      .toEqual({ kind: "several", typed: "hala", count: 2 });
  });

  it("refuses a count that disagrees with the rows", () => {
    expect(() => found([match()], { count: 2 })).toThrow(/derives `count`/);
  });
});

describe("what a desk can confirm a row by", () => {
  it("is the name and the digits, and never a photo in this build", () => {
    expect(checksFor(match())).toEqual({ name: true, digits: true, photo: false });
  });

  it("counts a withheld name as no check", () => {
    // **A marker is not a name.** MOD-027's board paid for rendering it as though somebody
    // were called that, and here it would be a desk confirming identity against `***`.
    expect(checksFor(match({ legal_name: MASK })).name).toBe(false);
  });

  it("counts a withheld number as no check", () => {
    expect(checksFor(match({ phone: MASK })).digits).toBe(false);
  });

  it("counts a record with no number as no check", () => {
    expect(checksFor(match({ phone: null })).digits).toBe(false);
  });

  it("says a row with neither cannot confirm anybody", () => {
    // **Worth saying, because the alternative is a receptionist letting somebody through on
    // a match they could not check.** The photo is gone, so these two are all there is.
    expect(confirmable(match({ legal_name: MASK, phone: MASK }))).toBe(false);
    expect(confirmable(match({ legal_name: MASK, phone: "4180" }))).toBe(true);
    expect(confirmable(match({ legal_name: "Hala Barakat", phone: null }))).toBe(true);
  });
});

describe("the meta line under a name", () => {
  it("is the club and the last four, in the canvas's own rendering", () => {
    // The canvas prints `Club · Sweifieh · ···4180`; the plan is three requests away per
    // match, so it is absent rather than guessed at.
    expect(metaParts(match(), { plan: null, club: "Sweifieh" }))
      .toEqual(["Sweifieh", "···4180"]);
  });

  it("draws the plan when a caller has one", () => {
    expect(metaParts(match(), { plan: "Club", club: "Sweifieh" }))
      .toEqual(["Club", "Sweifieh", "···4180"]);
  });

  it("leaves a part out rather than standing a dash in for it", () => {
    // **The Member 360's own rule.** A row printing `— · — · ···4180` reads as a record with
    // nothing in it rather than as a page that could not compose two facts.
    expect(metaParts(match({ location_id: null }), { plan: null, club: null }))
      .toEqual(["···4180"]);
    expect(metaParts(match({ phone: null }), { plan: null, club: "Sweifieh" }))
      .toEqual(["Sweifieh"]);
    expect(metaParts(match({ phone: null, location_id: null }),
                     { plan: null, club: null })).toEqual([]);
  });

  it("leaves a withheld number out rather than printing the marker as digits", () => {
    // `···***` would read as four digits somebody could ask for.
    expect(metaParts(match({ phone: MASK }), { plan: null, club: "Sweifieh" }))
      .toEqual(["Sweifieh"]);
  });
});
