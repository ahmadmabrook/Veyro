import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession, useReaderSession } from "./sign-in";

/**
 * ADM-RPT-04 · ATTENDANCE — "VISITS BY HOUR · KHALDA · WEEKDAYS".
 *
 * **The assertions are about rendered values, not labels.** "The timezone is named on the
 * page" passed while every time on the schedule board was three hours wrong, and this screen
 * is the one where that lesson bites hardest: its whole output is an hour.
 *
 * The fixture's club is `Asia/Amman`, UTC+3 all year, and the seed writes UTC instants at
 * local 07:00, 10:30, 17:00, 18:00 and 19:00 over the last few days. So the chart has a
 * shape, which is what makes a busiest window and a quietest hour assertable at all.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const cell = (page: Page, label: string) =>
  page.locator(".ds-metric").filter({ hasText: label }).first();

/** What a bar says to a screen reader: "19:00: 10". */
async function bars(page: Page): Promise<Map<string, number>> {
  const texts = await page.locator(".ds-hourbar .ds-visually-hidden").allTextContents();
  return new Map(texts.map((text) => {
    const [hour, count] = text.split(":").length === 3
      ? [text.slice(0, 5), text.slice(6)]
      : [text, "0"];
    return [hour.trim(), Number((count ?? "").trim())];
  }));
}

test.describe("the attendance report", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/reports/attendance?site=${fixture().locationId}`);
  });

  test("draws a bar for every hour of the day, including the empty ones", async ({ page }) => {
    // Nothing in this build records when a club is open, so trimming the axis to the hours
    // that saw somebody would be the surface inventing opening hours -- and a 03:00 entry is
    // exactly the bar a manager wants to see.
    await expect(page.locator(".ds-hourbar")).toHaveCount(24);
    await expect(page.locator(".ds-hourbars-axis")).toContainText("00:00");
    await expect(page.locator(".ds-hourbars-axis")).toContainText("23:00");
  });

  test("buckets each entry in the club's own hour and not the host's", async ({ page }) => {
    // **The defect this repository has shipped twice, on the screen whose subject is hours.**
    // Amman is UTC+3, so the seed's 16:00Z entries are 19:00 local. A chart bucketed on the
    // instant puts them at 16:00 under a heading naming Amman -- which is verbatim the
    // schedule board's own defect, found by opening the page.
    const seen = await bars(page);
    expect(seen.get("19:00")).toBe(10);
    expect(seen.get("18:00")).toBe(9);
    expect(seen.get("17:00")).toBe(6);
    expect(seen.get("07:00")).toBe(3);
    expect(seen.get("16:00")).toBe(0);
    expect(seen.get("15:00")).toBe(0);
    expect(seen.get("04:00")).toBe(0);
  });

  test("names the club's timezone on the page, because every hour on it is that clock", async ({
    page,
  }) => {
    await expect(page.locator("main")).toContainText("Asia/Amman");
    await expect(page.locator("main")).toContainText("Downtown");
  });

  test("writes the conclusion in words, which is the canvas's own requirement", async ({
    page,
  }) => {
    // "The conclusion is written in words beneath the chart. A manager should not have to
    // interpret a heat strip to find the actionable hour."
    const main = page.locator("main");
    await expect(main).toContainText("18:00–20:00 is the busiest window");
    await expect(main).toContainText("07:00 is the quietest hour that sees anybody");
    // 3 of 10 is 30% of the peak, which is the figure that makes the hour actionable.
    await expect(main).toContainText("30% of the peak");
  });

  test("the busiest window spans the two peak-tier hours, as the canvas draws it", async ({
    page,
  }) => {
    // 19:00 at ten and 18:00 at nine are both at or above 85% of the peak, so the span is
    // two hours and ends at the hour the last bar ends.
    await expect(cell(page, "BUSIEST WINDOW")).toContainText("18:00–20:00");
    await expect(cell(page, "BUSIEST WINDOW")).toContainText("10 in the busiest hour");
  });

  test("the quietest hour is the quietest one that saw anybody", async ({ page }) => {
    // Not 03:00, which is where "the quietest hour over all 24" lands in every club in the
    // world and is useless advice.
    await expect(cell(page, "QUIETEST HOUR")).toContainText("07:00");
    await expect(cell(page, "QUIETEST HOUR")).toContainText("30%");
  });

  test("paints three tiers and the peak hour is in the top one", async ({ page }) => {
    const tier = (hour: number) =>
      page.locator(".ds-hourbar").nth(hour).locator(".ds-hourbar-fill");
    await expect(tier(19)).toHaveAttribute("data-tier", "peak");
    await expect(tier(18)).toHaveAttribute("data-tier", "peak");
    await expect(tier(17)).toHaveAttribute("data-tier", "busy");
    await expect(tier(7)).toHaveAttribute("data-tier", "quiet");
    await expect(tier(3)).toHaveAttribute("data-tier", "quiet");
  });

  test("refuses the canvas's percentage of capacity, and says which claim it refuses", async ({
    page,
  }) => {
    // The canvas writes "18:00–20:00 runs at 94% of floor capacity". A capacity figure
    // exists -- it is what a presentation is refused against -- and it is not this chart's
    // denominator: entries in an hour are arrivals, not people inside at a moment.
    const main = page.locator("main");
    await expect(main).toContainText("never of a zone's capacity");
    await expect(main).toContainText("arrivals rather than people inside at a moment");
    await expect(main).toContainText("94% of floor capacity");
  });

  test("says this report does not consult the opening hours, which is why all 24 are drawn",
    async ({ page }) => {
      // **This test used to pin the sentence in place, and the sentence was false.** It
      // asserted "Nothing in this build records when a club is open" -- which stopped being
      // true when MOD-026's third slice added `plt01.tsk_business_hours`, a location's weekly
      // pattern and its dated overrides with a writer, a withdrawal and a read route. MOD-026
      // built that calendar *because* nothing recorded a club's hours and cited this report's
      // refusal as its evidence, so closing the gap left the note behind -- and this assertion
      // held it on the screen, in both locales, for a module.
      //
      // The claim that is still true is narrower: the report does not *consult* them. So that
      // is what this asserts, plus the absence of the old sentence -- which is the direction
      // that matters, because a gap note outliving its gap is what happened here and an
      // assertion on the new wording alone would not notice a revert.
      const main = page.locator("main");
      await expect(main).toContainText("does not consult the club's opening hours");
      await expect(main).not.toContainText("Nothing in this build records");
      // And it says where they are, so a reader is not left thinking the product cannot know.
      await expect(main).toContainText("recorded per club in this build");
    });

  test("says the day set is the reader's choice and no chip claims a working week", async ({
    page,
  }) => {
    const chips = page.getByRole("navigation", { name: "Which days" });
    await expect(chips.getByRole("link", { name: "All days" })).toBeVisible();
    await expect(chips.getByRole("link", { name: "Sun–Thu" })).toBeVisible();
    await expect(chips.getByRole("link", { name: "Mon–Fri" })).toBeVisible();
    // **Neither chip claims to be the working week, and that is still right** -- the day set
    // is the reader's choice and labelling one "weekdays" would assert a fact about their
    // business. What changed is the reason: this assertion used to pin "No table or
    // configuration key in this build says which days are a working week", which stopped
    // being true when MOD-026's business calendar started recording each club's open days.
    // The behaviour stands; the sentence is narrower now, and the absence of the old one is
    // asserted because that is the direction a revert comes from.
    await expect(chips.getByRole("link", { name: /weekday/i })).toHaveCount(0);
    const main = page.locator("main");
    await expect(main).toContainText("does not read which days your clubs are open");
    await expect(main).not.toContainText("No table or configuration key in this build");
  });

  test("narrowing the days changes what is counted", async ({ page }) => {
    // The exact figure depends on which weekdays the seeded days fall on, which moves with
    // the calendar -- so the assertion is that the narrow view is a subset, which is true
    // whatever day the suite runs on. A chart about five days of seven cannot be larger.
    const all = Number((await cell(page, "VISITS").textContent())?.replace(/\D/g, ""));
    await page.goto(`/reports/attendance?site=${fixture().locationId}&range=sun-thu`);
    const narrow = Number((await cell(page, "VISITS").textContent())?.replace(/\D/g, ""));
    expect(narrow).toBeLessThanOrEqual(all);
    await expect(page.getByRole("navigation", { name: "Which days" })
      .getByRole("link", { name: "Sun–Thu" })).toHaveAttribute("aria-current", "page");
  });

  test("offers the readers of a multi-zone club, and says the total counts presentations", async ({
    page,
  }) => {
    // The fixture has two zones: Main floor with a turnstile and Plant room with none. A
    // member who passes two readers is two entries, so the whole-club total is
    // presentations rather than people -- said on the page rather than left to be found.
    const zones = page.getByRole("navigation", { name: "Which reader" });
    await expect(zones.getByRole("link", { name: "Whole club" })).toBeVisible();
    await expect(zones.getByRole("link", { name: "Main floor" })).toBeVisible();
    // A live zone that counted nothing is listed: absent would read as a zone that is not
    // there.
    await expect(zones.getByRole("link", { name: "Plant room" })).toBeVisible();
    await expect(page.locator("main")).toContainText("is two entries");
  });

  test("narrowing to the reader with no entries empties the chart and says so", async ({
    page,
  }) => {
    await page.getByRole("navigation", { name: "Which reader" })
      .getByRole("link", { name: "Plant room" }).click();
    // **A club that was shut is not a club that was quiet** -- MOD-011's rule in a report.
    // No hour is marked quietest and no share is rendered.
    await expect(page.locator("main")).toContainText("No entry was recorded");
    await expect(page.locator("main")).toContainText("not a club that was quiet");
    await expect(page.locator("main")).not.toContainText("is the busiest window");
    // **The two cells carry their reason rather than going blank**, which is what
    // `MetricCell` does when `freshness` is left off and the reason is passed alone: it
    // takes the value branch with no value. An empty cell beside a label is the one
    // reading that is always wrong -- "never blank, never zero".
    for (const label of ["BUSIEST WINDOW", "QUIETEST HOUR"]) {
      const metric = page.locator(".ds-metric").filter({ hasText: label }).first();
      await expect(metric).toContainText("Nobody came in during this window");
      await expect(metric.locator(".ds-metric-value")).toHaveCount(0);
    }
  });

  test("says what the bars are summed over", async ({ page }) => {
    // A chart of twenty days and a chart of one are read differently and nothing else on
    // the page says which this is.
    await expect(cell(page, "DAYS COUNTED")).toContainText("28");
    await expect(cell(page, "DAYS COUNTED")).toContainText("over 4 weeks");
  });

  test("names class fill and capacity planning rather than drawing them", async ({ page }) => {
    // The design's line for this report is "peak hours, class fill, capacity planning" and
    // the canvas draws the first. A second chart this design does not have would be as much
    // a deviation as a missing one, so the two are stated.
    const gaps = page.locator("section").filter({ hasText: "What this report does not do" });
    await expect(gaps.getByRole("term").filter({ hasText: "Class fill" })).toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "Capacity headroom" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "Export" })).toBeVisible();
    await expect(gaps).toContainText("tier-four gate");
  });

  test("offers no export, because nothing here exports anything", async ({ page }) => {
    await expect(page.getByRole("button", { name: /export/i })).toHaveCount(0);
  });

  test("the whole screen reads in Arabic", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForFunction(() => document.documentElement.dir === "rtl");
    await page.goto(`/reports/attendance?site=${fixture().locationId}`);
    const main = page.locator("main");
    // The conclusion is the most explanatory field on the page, which is exactly the one
    // MOD-013's board shipped in English on an Arabic screen: a string that never became a
    // message key is invisible to the parity check.
    await expect(main).toContainText("أكثر الفترات ازدحاماً");
    await expect(main).toContainText("أهدأ ساعة");
    await expect(main).toContainText("كل الأيام");
    // And the refusal, which is prose rather than a label.
    await expect(main).toContainText("سعة المنطقة");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    // And the English prose is gone, which is the half a key-count check cannot see.
    for (const english of [
      "is the busiest window", "All days", "What this report does not do",
    ]) {
      await expect(main).not.toContainText(english);
    }
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may read the report and not list the clubs", () => {
  test("is told to open it from a link rather than shown an empty picker", async ({ page }) => {
    // The schedule board's rule: the read carries the club's own name and timezone, so a
    // session holding only `access.zone.read` can open this page from a link. An empty
    // picker would read as a tenant with no clubs.
    await useReaderSession(page);
    await page.goto("/reports/attendance");
    await expect(page.locator("main")).toContainText("open it from a link that names one");
    await expect(page.locator(".ds-hourbar")).toHaveCount(0);
  });

  test("gets the whole report from a link that names a club", async ({ page }) => {
    await useReaderSession(page);
    await page.goto(`/reports/attendance?site=${fixture().locationId}`);
    await expect(page.locator(".ds-hourbar")).toHaveCount(24);
    await expect(page.locator("main")).toContainText("18:00–20:00 is the busiest window");
    // No site picker, because listing the clubs is a different permission.
    await expect(page.getByRole("link", { name: "Downtown" })).toHaveCount(0);
  });
});

test.describe("a session that may not read the access plane", () => {
  test("is refused the report and told which permission it needs", async ({ page }) => {
    await useDeskSession(page);
    await page.goto(`/reports/attendance?site=${fixture().locationId}`);
    await expect(page.locator("main")).toContainText("access.zone.read");
    // And no figure leaks through the refusal.
    await expect(page.locator(".ds-hourbar")).toHaveCount(0);
    await expect(page.locator(".ds-metric")).toHaveCount(0);
  });

  test("does not see the attendance row on the index", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/reports");
    await expect(page.locator(".ds-report-list")
      .getByRole("link", { name: "Attendance" })).toHaveCount(0);
  });
});
