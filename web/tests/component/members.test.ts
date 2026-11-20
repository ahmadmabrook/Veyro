import { describe, expect, it } from "vitest";

import {
  LIFECYCLE_STATES,
  UNANSWERABLE,
  isLifecycleState,
  membershipsByPerson,
  stateCounts,
  type MembershipRow,
} from "@/lib/members";

import { specFor, specTextFor } from "@/design/screen-specs";

/**
 * ADM-MEM-05's decisions, and the screen's claim about its own gaps.
 *
 * **One assertion here reads the design source.** The screen says it implements ADM-MEM-05,
 * and the extraction is pinned by digest — so the test can check that the specification it
 * claims to follow is actually present rather than taking the comment's word for it.
 */

describe("the members list is built from a design that exists", () => {
  it("finds ADM-MEM-05 in the extracted source", () => {
    const spec = specFor("ADM-MEM-05");
    // The eyebrow states the density and the width the screen was drawn at, which is why the
    // page sets `data-density="compact"` rather than inheriting the Admin default.
    expect(spec.sections.map((s) => s.title).join(" ")).toContain("COMPACT");
    // And the scale rule the footer's two numbers exist for.
    expect(specTextFor("ADM-MEM-05")).toContain("There is no state where 4,812 rows render");
  });

  it("names every column the design specifies that this build cannot answer", () => {
    // CLUB, BALANCE and LAST VISIT. Named in one place, so a page cannot quietly render an
    // empty cell as a fact about a member.
    expect(UNANSWERABLE.columns).toContain("CLUB");
    expect(UNANSWERABLE.columns).toContain("BALANCE");
    expect(UNANSWERABLE.columns).toContain("LAST VISIT");
  });

  it("says why there is no search rather than offering a box that scans", () => {
    expect(UNANSWERABLE.search).toContain("ENG-01");
    expect(UNANSWERABLE.search).toContain("pre-filter");
  });
});

describe("the lifecycle filter", () => {
  it("admits exactly the states the module owns", () => {
    expect([...LIFECYCLE_STATES]).toEqual([
      "lead", "prospect", "active", "paused", "cancelled", "former",
    ]);
  });

  it("refuses a near miss rather than treating it as no filter", () => {
    // `state=activ` and "nobody is active" are different answers, and a list that renders
    // both as an empty table is a list nobody can trust.
    expect(isLifecycleState("active")).toBe(true);
    expect(isLifecycleState("activ")).toBe(false);
    expect(isLifecycleState(undefined)).toBe(false);
  });
});

describe("composing the membership column", () => {
  const membership = (person: string, kind: string, end: string | null): MembershipRow => ({
    membership_id: `m-${person}-${kind}`,
    person_id: person,
    status: "active",
    membership_kind: kind,
    billing_period: "monthly",
    current_period_end: end,
    ends_on: null,
  });

  it("indexes one membership per person, keeping the first the list returned", () => {
    // The list route orders newest first, and the column is "what are they on now".
    const index = membershipsByPerson([
      membership("p1", "recurring", "2026-12-01"),
      membership("p1", "fixed_term", "2025-01-01"),
      membership("p2", "recurring", null),
    ]);
    expect(index.get("p1")?.membership_kind).toBe("recurring");
    expect(index.get("p2")?.current_period_end).toBeNull();
    expect(index.size).toBe(2);
  });

  it("has no entry for a person whose membership is outside the page's read", () => {
    // Which is why the cell says so rather than rendering "no membership": the two are
    // different facts and only one of them is about the member.
    const index = membershipsByPerson([membership("p1", "recurring", null)]);
    expect(index.has("p2")).toBe(false);
  });
});

describe("the subtitle's counts", () => {

  it("orders the tenant's states largest first", () => {
    expect(stateCounts({ active: 2, lead: 1 })).toEqual([
      { state: "active", count: 2 },
      { state: "lead", count: 1 },
    ]);
  });

  it("breaks a tie by name, so the sub-line does not reshuffle between loads", () => {
    expect(stateCounts({ paused: 1, former: 1 }).map((s) => s.state))
      .toEqual(["former", "paused"]);
  });

  it("keeps `none` as its own figure, because the parts have to sum to the total", () => {
    // A person with no member profile is a real row on this list -- a lead who has not been
    // given one -- and a sub-line whose figures did not add up would send a reader looking
    // for the ones it left out.
    expect(stateCounts({ active: 3, none: 1 })).toEqual([
      { state: "active", count: 3 },
      { state: "none", count: 1 },
    ]);
  });

  it("is empty for a tenant with nobody in it, rather than inventing a zero per state", () => {
    expect(stateCounts({})).toEqual([]);
  });
});
