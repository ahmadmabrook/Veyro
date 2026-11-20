import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * The row whose *category chip* is this, not whose text mentions the word.
 *
 * `filter({ hasText: "MONEY" })` matched two rows: the compliance row's evidence says "the
 * money is collected". A locator that matches on body prose is coupled to copy it is not
 * testing -- the same trap as the positional cell locator this suite already records.
 */
function row(page: import("@playwright/test").Page, category: string) {
  return page.locator(".ds-attention")
    .filter({ has: page.locator(".ds-attention-category", { hasText: new RegExp(`^${category}$`, "i") }) });
}

/**
 * ADM-CC-01 … ADM-CC-05, the Command Center, in a real browser against a real backend.
 *
 * **What was at `/` before this was a session-and-permissions diagnostic**, and it passed its
 * own tests. That is the point of this file: every assertion here is about a *rendered value*
 * rather than a label, because this repository has already paid for the weaker kind. The
 * schedule board shipped `15:00` for an 18:00 class with 140 green assertions behind it, and
 * every one of them asserted that the timezone was *named* on the page.
 *
 * The fixture seeds all four queue classes deliberately — a payment in recovery, a rejected
 * filing, a membership expiring inside the week and three classes with no coach — because an
 * empty queue is a legitimate state (canvas 4) in which every assertion about a row passes
 * vacuously.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the Command Center", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/");
  });

  test("is the Command Center and not a session diagnostic", async ({ page }) => {
    // The two facts the old page led with. Neither belongs on the product's front door: the
    // identity and its assurance are on `/account`, the gate table is on `/permissions`.
    const body = await page.locator("main").innerText();
    expect(body).not.toContain("Signed in as");
    expect(body).not.toContain("Assurance level");
    // And the heading counts the queue rather than naming the app.
    await expect(page.getByRole("heading", { level: 1 }))
      .toContainText(/things? need you this morning/);
  });

  test("is at Compact density, which the design states for this screen", async ({ page }) => {
    // "CANVAS 1 · OWNER · ALL LOCATIONS · NORMAL OPERATIONAL DAY · 1440×900", and the
    // foundation audit: "Command Center runs Compact, Member 360 runs Default".
    const row = await page.evaluate(() => {
      const scope = document.querySelector("[data-density]");
      return scope ? getComputedStyle(scope).getPropertyValue("--density-row").trim() : null;
    });
    expect(row).toBe("34px");
  });

  test("renders four metric cells, and the fourth has no figure", async ({ page }) => {
    const metrics = page.locator(".ds-metric");
    // Four, or five when a tenant bills in two currencies: the collected cell is per
    // currency, which is the money rule rather than a layout choice.
    expect(await metrics.count()).toBeGreaterThanOrEqual(4);
    const leads = metrics.filter({ hasText: "LEAD CONVERSION" });
    await expect(leads).toHaveAttribute("data-freshness", "unavailable");
    // Not a zero and not an em-dash: both read as a measurement.
    await expect(leads).toContainText("ADM-CRM");
    await expect(leads.locator(".ds-metric-value")).toHaveCount(0);
  });

  test("the collected figure has a comparison that is not a fabricated zero", async ({
    page,
  }) => {
    // `change_bp` is null with no baseline, and `0%` would read as "unchanged" — a confident
    // wrong answer about a month nobody can compare against.
    const collected = page.locator(".ds-metric").filter({ hasText: "COLLECTED" }).first();
    await expect(collected.locator(".ds-metric-value")).toContainText("JOD");
    await expect(collected.locator(".ds-metric-comparison")).toContainText(/compare against/);
  });

  test("the queue carries all four classes the fixture seeded, in the design's order", async ({
    page,
  }) => {
    const rows = page.locator(".ds-attention");
    await expect(rows).toHaveCount(4);
    const categories = await page.locator(".ds-attention-category").allInnerTexts();
    expect(categories.map((c) => c.trim().toUpperCase())).toEqual([
      "MONEY", "COMPLIANCE", "RETENTION", "STAFFING",
    ]);
  });

  test("a headline states a fact, with its count agreeing in English", async ({ page }) => {
    // §38: "The headline is never a metric name — '6 payments failed' not 'Payment failure
    // rate'." And the plural agrees: the page rendered "1 payments are in recovery" before
    // the catalogue grew CLDR forms, which is a defect no label assertion could see.
    await expect(row(page, "money").locator(".ds-attention-headline"))
      .toHaveText("1 payment is in recovery");
  });

  test("severity is an edge-mark and a category and the wording, never the bar alone", async ({
    page,
  }) => {
    // §38's contract, and the contrast matrix: a signal carried only by a coloured edge is a
    // colour-only signal. The row's category and its own words carry it too, which is what
    // this asserts alongside the measured border.
    const money = row(page, "money");
    await expect(money).toHaveAttribute("data-severity", "critical");
    const edge = await money.evaluate((el) => getComputedStyle(el).borderInlineStartWidth);
    expect(edge).toBe("3px");
    await expect(money.locator(".ds-attention-category")).toHaveText(/MONEY/i);
  });

  test("the money figure sits at the logical end and names what it means", async ({ page }) => {
    const money = row(page, "money");
    await expect(money.locator(".ds-attention-money")).toContainText("at risk");
    await expect(money.locator(".ds-attention-money")).toContainText("JOD");
  });

  test("the interpretation panel is withheld and says why", async ({ page }) => {
    const panel = page.locator(".ds-ai");
    await expect(panel).toHaveAttribute("data-withheld", "true");
    await expect(panel).toContainText(/not a confirmed figure/i);
    await expect(panel).toContainText("No module in this build produces one");
  });

  test("the AI panel's border is the system indigo, not the tenant accent", async ({ page }) => {
    // G7 and DS-CL-02: "A tenant brand on an AI panel would make inference look like a
    // first-party assertion; Veyro is accountable for what its AI says, so Veyro owns the
    // colour it says it in." The audit found this exact defect and closed it by locking the
    // hue; asserting the computed colour is what stops it coming back.
    const [border, accent] = await page.locator(".ds-ai").evaluate((el) => [
      getComputedStyle(el).borderTopColor,
      getComputedStyle(el).getPropertyValue("--color-action-default").trim(),
    ]);
    expect(border).toBe("rgb(74, 61, 122)"); // ai.600 — #4a3d7a
    expect(border).not.toBe(accent);
  });

  test("only the last week bucket can be partial, and never more than one", async ({ page }) => {
    // "The last bar is a partial week and is marked, not extrapolated."
    //
    // **At most one, not exactly one**, and the difference is a day of the week. The week
    // starts Saturday, so on a Friday today *is* the bucket's last day and nothing is
    // outstanding -- the chart is correct and has no partial bar. The first version of this
    // test asserted exactly one and was true six days in seven, which is the green that
    // depends on when it ran rather than on the behaviour: the same shape as the fixture
    // whose freshness expired ten minutes after it was seeded. The invariant is that a
    // partial bucket can only ever be the last one.
    const bars = page.locator(".ds-bar");
    expect(await bars.count()).toBe(12);
    const partial = await bars.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-partial") === "true"));
    expect(partial.filter(Boolean).length).toBeLessThanOrEqual(1);
    expect(partial.slice(0, -1).every((p) => p === false)).toBe(true);
  });

  test("the chart axis reads as a day and a month, not an ISO date", async ({ page }) => {
    // An ISO date wrapped onto two lines in the narrowest column on the page, which is how
    // this was found — by looking at the rendered chart.
    const first = await page.locator(".ds-bar").first().locator("span").first().innerText();
    expect(first).toMatch(/^\d{1,2} \w{3,9}$/);
  });

  test("the pace is named as a projection wherever it appears", async ({ page }) => {
    // A figure a manager could quote as collections is the one thing this must not produce.
    await expect(page.locator("main")).toContainText("straight-line projection");
    await expect(page.locator("main")).toContainText("must not be rendered as a total");
  });

  test("says the breakdown is by legal entity and that the design asked for clubs", async ({
    page,
  }) => {
    await expect(page.locator("main")).toContainText("legal entity");
    await expect(page.locator("main")).toContainText(/breaks this down by club/);
  });

  test("names its own gaps rather than drawing empty panels", async ({ page }) => {
    const gaps = page.locator("main").getByText("What this screen does not do yet");
    await expect(gaps).toBeVisible();
    await expect(page.locator("main")).toContainText("scope switcher");
  });

  test("has no axe violations", async ({ page }) => {
    const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(results.violations).toEqual([]);
  });

  test("does not scroll sideways at phone width", async ({ page }) => {
    // Seven of thirteen surfaces did, and a reader on a phone could not see that columns
    // existed. The metric row is the one deliberate exception and it is its own scroll
    // container, not the page's.
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
  });

  test("the queue never collapses, at any width", async ({ page }) => {
    // bp.md: "The attention queue never collapses — it is the reason the page exists."
    for (const width of [1600, 1400, 1000, 760, 375]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator(".ds-attention")).toHaveCount(4);
      const hidden = await page.locator(".ds-attention").evaluateAll((els) =>
        els.filter((el) => getComputedStyle(el).display === "none").length);
      expect(hidden, `rows hidden at ${width}px`).toBe(0);
    }
  });
});

test.describe("the Command Center for a session that cannot see everything", () => {
  test("does not claim nothing needs you when a panel was refused", async ({ page }) => {
    // **The defect this exists for.** The desk session holds the schedule read and not the
    // money ones, so three of the four feeds are refused — and the first version told it
    // "Nothing needs you right now", which is a statement about the club made out of the
    // page's own permissions.
    await useDeskSession(page);
    await page.goto("/");
    const heading = await page.getByRole("heading", { level: 1 }).innerText();
    expect(heading).not.toBe("Nothing needs you right now");
    // And the body says what the heading is a statement about.
    await expect(page.locator("main")).toContainText("not a statement about the whole club");
  });
});
