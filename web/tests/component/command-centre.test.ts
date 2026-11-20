import { describe, expect, it } from "vitest";

import { MESSAGES, MESSAGE_KEYS, fill, isPlural, t } from "@/i18n/locale";
import { specFor, specTextFor } from "@/design/screen-specs";
import {
  AI_PANEL,
  CATEGORIES,
  UNANSWERABLE,
  heading,
  orderQueue,
  queueCounts,
  withRoutes,
  type AttentionItem,
} from "@/lib/command-centre";

/**
 * ADM-CC-01's decisions, and the screen's claim about its own gaps.
 *
 * **Two of these read the design source.** The page says it implements ADM-CC-01 and the
 * extraction is pinned by digest, so a test can check that the specification it cites is
 * actually there and says what the page claims — rather than taking a comment's word for it.
 */

const item = (over: Partial<AttentionItem> & { key: string }): AttentionItem => ({
  category: "money",
  severity: "attention",
  when: "today",
  title: "something",
  body: "because",
  actions: [],
  ...over,
});

describe("the Command Center is built from a design that exists", () => {
  it("finds ADM-CC-01 in the extracted source, drawn at 1440", () => {
    const spec = specFor("ADM-CC-01");
    expect(spec.name).toContain("Command Center");
    expect(spec.sections.map((s) => s.title).join(" ")).toContain("1440");
    // The eyebrow's own file: the Command Center is drawn at high fidelity, in the document
    // the first extraction could not see.
    expect(spec.sections[0]!.file).toContain("HF Command Center");
  });

  it("quotes the rule that the queue is the reason the page exists", () => {
    // bp.md's behaviour, which is why nothing collapses the queue at any width.
    expect(specTextFor("ADM-CC-03")).toBeTruthy();
    const all = ["ADM-CC-01", "ADM-CC-02", "ADM-CC-03", "ADM-CC-04", "ADM-CC-05"]
      .map(specTextFor).join("\n");
    expect(all).toContain("The attention queue never collapses");
  });

  it("carries canvas 5's two behaviours: a stale figure, and a withheld panel", () => {
    // The `freshness` variant and the AI panel's withheld state are both filed in the
    // design rather than invented here, and this is what says so.
    //
    // **The change-log entry itself is a section of its own**, because `DS-CL-01` matches
    // the extraction's section-title shape -- an id, a middot, a title -- so it is not part
    // of ADM-CC-05's text. The assertion is therefore against what canvas 5 states, which
    // is what the screen implements.
    const canvas = specTextFor("ADM-CC-05");
    expect(canvas).toContain("WITHHELD");
    expect(canvas).toContain("de-emphasise");
    expect(canvas).toContain("as of");
  });

  it("states the boundary that makes group revenue a separate grant", () => {
    // ADM-CC-02 as a product fact, which is why `finance.revenue.read` exists at all.
    expect(specTextFor("ADM-CC-02")).toContain("does not see");
  });
});

describe("the attention queue", () => {
  it("orders critical first, then by the design's own category sequence", () => {
    const ordered = orderQueue([
      item({ key: "d", category: "staffing" }),
      item({ key: "c", category: "retention" }),
      item({ key: "a", category: "money", severity: "critical" }),
      item({ key: "b", category: "compliance" }),
    ]);
    expect(ordered.map((i) => i.key)).toEqual(["a", "b", "c", "d"]);
  });

  it("is a declared sequence, not a sort by recency", () => {
    // A queue that reshuffled every few minutes would be un-learnable, and canvas 2 runs a
    // different order for a different role — which only makes sense if the order is a
    // statement rather than a timestamp comparison.
    expect([...CATEGORIES]).toEqual([
      "money", "compliance", "retention", "staffing", "leads",
    ]);
  });

  it("counts open, critical and assigned separately", () => {
    const counts = queueCounts([
      item({ key: "a", severity: "critical" }),
      item({ key: "b", owner: "Nadia" }),
      item({ key: "c" }),
    ]);
    expect(counts).toEqual({ open: 3, critical: 1, assigned: 1 });
  });

  it("drops an action with nowhere to go rather than rendering a dead control", () => {
    // ADM-MEM-05's rule: a control that does nothing is worse than one that is absent.
    const kept = withRoutes([
      { label: "cc.openIt", href: "/finance" },
      { label: "cc.openIt" },
    ]);
    expect(kept).toHaveLength(1);
  });
});

describe("the heading", () => {
  it("counts the queue", () => {
    expect(heading([item({ key: "a" }), item({ key: "b" })])).toEqual({
      key: "cc.heading", count: 2,
    });
  });

  it("says nothing needs you only when it could see everything", () => {
    // **The defect this exists for**: a reader holding three of the four grants was shown
    // "Nothing needs you right now" over six payments in recovery. "Nothing needs you" is a
    // statement about the club; a page that cannot see a category cannot make it.
    expect(heading([], true).key).toBe("cc.headingClear");
    expect(heading([], false).key).toBe("cc.headingPartial");
  });

  it("counts the queue whether or not every panel answered", () => {
    // An incomplete read does not change a count that is already non-zero: four items are
    // four items, and the heading is about them.
    expect(heading([item({ key: "a" })], false)).toEqual({ key: "cc.heading", count: 1 });
  });
});

describe("the interpretation panel", () => {
  it("is withheld, and the reason is the true one", () => {
    expect(AI_PANEL.state).toBe("withheld");
    // Not the design's stale-data reason, which would be a plausible sentence that is false
    // here: nothing in this build produces an interpretation at all.
    expect(t("en", AI_PANEL.reason)).toContain("No module in this build produces one");
  });

  it("carries the eyebrow every interpretation in this product has to carry", () => {
    expect(t("en", AI_PANEL.eyebrow).toLowerCase()).toContain("not a confirmed figure");
  });
});

describe("what the screen says it cannot do", () => {
  it("names the CRM as the reason the fourth metric has no figure", () => {
    expect(t("en", UNANSWERABLE.leadConversion)).toContain("ADM-CRM");
  });

  it("names every gap in both languages", () => {
    // **The parity check is structurally blind to prose held in a library**, which is how
    // eight English decision reasons reached an otherwise-correct Arabic board in MOD-013.
    // Every gap here is a message key, and this asserts both catalogues carry it.
    for (const key of Object.values(UNANSWERABLE)) {
      expect(MESSAGE_KEYS, `${key} is not a message key`).toContain(key);
      expect(t("en", key).length).toBeGreaterThan(20);
      expect(t("ar", key).length).toBeGreaterThan(20);
    }
  });
});

describe("counted messages carry plural forms", () => {
  it("renders the English singular and plural", () => {
    // "1 payments are in recovery" is what the page said before this existed, and it was
    // found by reading the rendered screen rather than by any assertion.
    expect(fill("en", "cc.moneyTitle", { count: 1 })).toBe("1 payment is in recovery");
    expect(fill("en", "cc.moneyTitle", { count: 6 })).toBe("6 payments are in recovery");
  });

  it("renders Arabic's dual, which no `n === 1` check could", () => {
    expect(fill("ar", "cc.heading", { count: 1 })).toContain("أمر واحد");
    expect(fill("ar", "cc.heading", { count: 2 })).toContain("أمران");
    expect(fill("ar", "cc.heading", { count: 4 })).toContain("أمور");
  });

  it("gives every plural key all six Arabic forms", () => {
    // Arabic needs `zero`, `one`, `two`, `few`, `many` and `other`, and a missing one falls
    // back to `other` — which renders a plural where the language wants a dual. A fallback
    // that works is exactly the kind of gap that ships.
    const plurals = MESSAGE_KEYS.filter(isPlural);
    expect(plurals.length).toBeGreaterThan(0);
    for (const key of plurals) {
      const ar = MESSAGES.ar[key] as unknown as Record<string, string>;
      for (const form of ["zero", "one", "two", "few", "many", "other"]) {
        expect(Object.keys(ar), `${key} has no ar.${form}`).toContain(form);
      }
      const en = MESSAGES.en[key] as unknown as Record<string, string>;
      expect(Object.keys(en).sort()).toEqual(["one", "other"]);
    }
  });

  it("refuses a plural key through `t`, which cannot pick a form", () => {
    expect(() => t("en", "cc.heading")).toThrow(/plural/);
  });

  it("refuses a plural message with no count", () => {
    expect(() => fill("en", "cc.moneyTitle", {})).toThrow(/numeric count/);
  });
});
