import { describe, expect, it } from "vitest";

import { MASK, isWithheld, splitSections } from "@/lib/people";

/**
 * The two distinctions MOD-014's surface rests on, tested where they are decided.
 *
 * **`"***"` is a value, not an absence.** MOD-014 replaces a field the caller may not read
 * with that marker at every depth, and its own rule is that a redacted record still exists.
 * A surface that compared against `null`, or that trimmed falsy values away, would render
 * withheld and empty identically -- which is the one reading that is always wrong.
 *
 * **A section whose source begins `unavailable:` has no module behind it.** Seven of the
 * twelve areas PPL-01-R02 lists belong to modules this repository does not have, and the
 * server says so in prose rather than returning an empty list, because `[]` reads as "none".
 */
describe("a withheld value", () => {
  it("is the mask, and nothing else is", () => {
    expect(isWithheld(MASK)).toBe(true);
    expect(isWithheld("***")).toBe(true);
    // The three shapes a surface would confuse it with if it tested for falsiness.
    expect(isWithheld(null)).toBe(false);
    expect(isWithheld("")).toBe(false);
    expect(isWithheld(undefined)).toBe(false);
    // And a real value that merely contains asterisks is not withheld.
    expect(isWithheld("4*** **** **** 1234")).toBe(false);
  });
});

describe("splitting the sections", () => {
  // **Two shapes of "unavailable", because there are two reasons now.** Four of these
  // sections used to say "not built in this repository" about modules that have since been
  // built, which made the Member 360 tell a staff member that bookings and finance do not
  // exist in a build that has both. The split does not care which reason it is -- that is the
  // point of testing it with one of each.
  const sections = {
    identity: "ppl_persons, ppl_contact_points (this module)",
    timeline: "ppl_timeline_entries, projected from MOD-010's outbox",
    membership: "unavailable: MOD-017 (COM-01) owns this and nothing here reads it",
    nutrition: "unavailable: CCH-02 is not built in this repository",
  };

  it("keeps both halves and strips the marker from the reason", () => {
    const { available, unavailable } = splitSections(sections);
    expect(available.map(([name]) => name)).toEqual(["identity", "timeline"]);
    expect(unavailable.map(([name]) => name)).toEqual(["membership", "nutrition"]);
    // The reason is rendered as prose, so the machine-readable prefix goes.
    expect(unavailable[0]![1]).toBe("MOD-017 (COM-01) owns this and nothing here reads it");
    expect(unavailable[1]![1]).toBe("CCH-02 is not built in this repository");
  });

  it("loses nothing: every section lands in exactly one half", () => {
    const { available, unavailable } = splitSections(sections);
    expect(available.length + unavailable.length).toBe(Object.keys(sections).length);
    const names = [...available, ...unavailable].map(([name]) => name).sort();
    expect(names).toEqual(Object.keys(sections).sort());
  });
});
