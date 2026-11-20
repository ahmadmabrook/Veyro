import { describe, expect, it } from "vitest";

import {
  COMPOSED_SECTIONS,
  MASK,
  isWithheld,
  splitComposed,
  splitSections,
} from "@/lib/people";

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

describe("the sections this page answers itself", () => {
  /**
   * **MOD-014's `sections` block describes the projection, not the page.** It says
   * "MOD-017 owns this and nothing here reads it" about membership, entitlements and
   * finance, which is true of the projection and is what paragraph 1300 is for -- and the
   * Member 360 page composes all three by calling those modules' own routes through their
   * own gates.
   *
   * Rendering the block unfiltered therefore put "membership: nothing here reads it"
   * directly under a Membership tab full of memberships. Same class of defect as the stale
   * "not built in this repository" list this screen already paid for: a confident wrong
   * answer on the page somebody opens before talking to a member.
   */
  it("is exactly the set the page has tabs for", () => {
    // The tabs that compose another module. `overview`, `access` and `notes` read MOD-014's
    // own data or MOD-022's, neither of which is in the projection's unavailable list.
    expect([...COMPOSED_SECTIONS].sort()).toEqual(
      ["entitlements", "finance", "membership"]);
  });

  it("moves those out of the gaps and leaves every other one in", () => {
    const { unavailable } = splitSections({
      identity: "MOD-014",
      membership: "unavailable: MOD-017 owns this and nothing here reads it",
      entitlements: "unavailable: MOD-017 owns this and nothing here reads it",
      finance: "unavailable: MOD-018 owns this and nothing here reads it",
      bookings: "unavailable: MOD-019 owns this and nothing here reads it",
      nutrition: "unavailable: CCH-02 is not built in this repository",
    });
    const { composed, absent } = splitComposed(unavailable);
    expect(composed.map(([name]) => name).sort())
      .toEqual(["entitlements", "finance", "membership"]);
    // **A module that exists and a module that does not both stay**, because the page shows
    // neither: `bookings` is MOD-019's and built, and nothing here reads it either. The two
    // reasons differ and the server's own prose is what tells them apart.
    expect(absent.map(([name]) => name).sort()).toEqual(["bookings", "nutrition"]);
  });
});
