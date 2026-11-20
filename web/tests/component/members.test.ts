import { describe, expect, it } from "vitest";

import {
  LIFECYCLE_STATES,
  UNANSWERABLE,
  isLifecycleState,
  membershipsByPerson,
  stateCounts,
  stateName,
  type MembershipRow,
} from "@/lib/members";
import { MESSAGES, t } from "@/i18n/locale";

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
    // **Through the catalogue, because these are message keys now.** They were English
    // sentences in a library, rendered straight to the page -- which put six English
    // paragraphs under Arabic headings in the Arabic build, where the catalogue parity check
    // could not see them. The Command Center's own `UNANSWERABLE` was already keys.
    expect(t("en", UNANSWERABLE.columns)).toContain("CLUB");
    expect(t("en", UNANSWERABLE.columns)).toContain("BALANCE");
    expect(t("en", UNANSWERABLE.columns)).toContain("LAST VISIT");
    for (const key of Object.values(UNANSWERABLE)) {
      expect(MESSAGES.en[key], `${key} is missing from the English catalogue`).toBeTruthy();
      expect(MESSAGES.ar[key], `${key} is missing from the Arabic catalogue`).toBeTruthy();
    }
  });

  it("says why there is no search rather than offering a box that scans", () => {
    expect(t("en", UNANSWERABLE.search)).toContain("ENG-01");
    expect(t("en", UNANSWERABLE.search)).toContain("pre-filter");
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

describe("stateName", () => {
  it("names every lifecycle state in both catalogues", () => {
    // **A stored value is not a label.** These were rendered raw, so an Arabic reader saw
    // `lead` in Latin letters on the filter chips and in every row of the table. The
    // catalogue parity check cannot see that: it compares the two catalogues against each
    // other and is blind to a string that never became a key. This is that check run from
    // the side the catalogue cannot see -- the rule MOD-013's board already paid for.
    for (const state of LIFECYCLE_STATES) {
      const key = stateName(state);
      expect(key, `${state} has no message key`).not.toBeNull();
      expect(MESSAGES.en[key!], `${state} is missing from the English catalogue`).toBeTruthy();
      expect(MESSAGES.ar[key!], `${state} is missing from the Arabic catalogue`).toBeTruthy();
    }
  });

  it("returns null for a state added later, so the screen shows it rather than hiding it", () => {
    // The set is MOD-014's and may grow. On the screen that *filters* by this value,
    // rendering an unknown one as "other" hides which one it is.
    expect(stateName("reactivated")).toBeNull();
  });
});
