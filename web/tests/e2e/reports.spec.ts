import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-RPT-01 and ADM-RPT-02 — the reports index, and revenue.
 *
 * **Neither screen existed and the revenue read did not either.** MOD-017 could answer what
 * one member owed and `/finance/collections` could answer what a month collected; nothing put
 * collected, invoiced, outstanding and refunded beside each other, which is the arrangement
 * the canvas exists to argue for.
 *
 * The assertions are about rendered values rather than labels. "The timezone is named on the
 * page" passed while every time on the schedule board was three hours wrong, and the lesson
 * generalises: assert the figure, not the heading above it.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the reports index", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/reports");
  });

  test("lists the reports this session can open, with the roles the canvas prints", async ({
    page,
  }) => {
    const list = page.locator(".ds-report-list");
    await expect(list.getByRole("link", { name: "Revenue" })).toBeVisible();
    await expect(list.getByRole("link", { name: "Membership" })).toBeVisible();
    await expect(list.getByRole("link", { name: "Attendance" })).toBeVisible();
    // The canvas puts the roles at the row's end. They are descriptive -- the gate decided
    // whether the row exists -- so they are labelled rather than four bare letters.
    await expect(list.locator(".ds-report-roles").first()).toContainText("OWNER");
  });

  test("names what the design lists and this build cannot report, with the reason", async ({
    page,
  }) => {
    // **A module that does not exist is a different absence from a permission you lack.** If
    // these four were simply missing they would read as four more grants to go and ask for,
    // which is a false thing to teach somebody.
    const section = page.locator("section").filter({ hasText: "cannot report" });
    for (const name of ["Coaching", "Leads and conversion", "Tax and e-invoicing"]) {
      await expect(section.getByRole("term").filter({ hasText: name })).toBeVisible();
    }
    await expect(section).toContainText("Coach Workspace is not built");
    // **Attendance moved out of this list when it was built**, and the assertion has to
    // move with it or the page would be telling a reader that a report they can open does
    // not exist -- which is the Member 360's stale "not built in this repository" defect,
    // the same shape one screen over.
    await expect(section.getByRole("term").filter({ hasText: "Attendance" }))
      .toHaveCount(0);
  });

  test("offers no export, and says the gate in front of one is the feature", async ({
    page,
  }) => {
    await expect(page.getByRole("button", { name: /export/i })).toHaveCount(0);
    await expect(page.locator("section").filter({ hasText: "Exporting is not built" }))
      .toContainText("control removed rather than the feature added");
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("the revenue report", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/reports/revenue");
  });

  const cell = (page: import("@playwright/test").Page, label: string) =>
    page.locator(".ds-metric").filter({ hasText: label }).first();

  test("carries four figures, not one labelled revenue", async ({ page }) => {
    // The canvas's own argument for this screen: "A report showing one number labelled
    // 'revenue' is the reason operators cannot reconcile their own books."
    for (const label of ["COLLECTED", "INVOICED", "OUTSTANDING", "REFUNDED"]) {
      await expect(cell(page, label)).toBeVisible();
    }
    await expect(page.locator("main")).toContainText("separate facts");
  });

  test("outstanding carries no comparison, because it is a position", async ({ page }) => {
    // The other three are flows and have a same-point-last-month figure. Outstanding is what
    // this month's invoices owe *now*; a delta there would be a number nobody can reproduce.
    await expect(cell(page, "OUTSTANDING").locator(".ds-metric-delta")).toHaveCount(0);
    await expect(cell(page, "INVOICED").locator(".ds-metric-delta")).toHaveCount(1);
  });

  test("the fixture's part-paid invoice leaves an outstanding figure that is not zero", async ({
    page,
  }) => {
    // **A fixture that pays every invoice in full cannot show these are four facts.** The
    // seed part-pays one deliberately, so collected and outstanding disagree on this screen
    // -- which is the whole point of the four columns.
    const owed = await cell(page, "OUTSTANDING").locator(".ds-money").first().textContent();
    expect(owed).toBeTruthy();
    expect(owed).not.toMatch(/\b0\.00\b/);
  });

  test("breaks revenue down by the catalogue's own product types", async ({ page }) => {
    // Not a taxonomy invented by the report: an invoice line carries a variant, a variant
    // belongs to a product, and a product has one of COM-02-R01's eight types.
    const grid = page.locator("table").first();
    await expect(grid).toContainText("Memberships");
    // And a line with no variant is its own row rather than being dropped or guessed at.
    await expect(grid).toContainText("Raised by hand");
  });

  test("the sources add up to the total row, and the total is the net", async ({ page }) => {
    // **The identity a reader checks a breakdown against.** A source row is net and the
    // invoiced headline is gross, so a reader adding the column up finds it short by the tax
    // unless the figure it reconciles to is the one in the Total row. 46.50 under a headline
    // of 53.94 reads as a breakdown that lost a row, which is how this was found.
    const money = async (row: string) => {
      // **Select by column kind, not by position in the row.** Every cell in the footer
      // carries `ds-grid-total`, so a selector that unions the two classes puts the empty
      // change column last and reads the total as zero. The money columns are the entity
      // split and the net, in that order, on a body row and on the footer alike.
      const cells = page.locator("tr").filter({ hasText: row }).first()
        .locator("td.ds-col-money");
      const texts = await cells.allTextContents();
      const last = texts[texts.length - 1] ?? "";
      return Number(last.replace(/[^0-9.]/g, ""));
    };
    const memberships = await money("Memberships");
    const byHand = await money("Raised by hand");
    const total = await money("Total");
    expect(memberships + byHand).toBeCloseTo(total, 2);
    await expect(page.locator("main")).toContainText("net of tax");
  });

  test("the count under the grid states what it counts", async ({ page }) => {
    // §25: "the count always states what is selected". A bare numeral under a table is a
    // stray character to a reader who has not been told what it counts.
    const count = page.locator(".ds-grid-count").first();
    await expect(count).toContainText(/sources?/);
    await expect(count).not.toHaveText(/^\s*\d+\s*$/);
  });

  test("names the legal entity rather than printing its id", async ({ page }) => {
    const headers = await page.locator("th").allTextContents();
    expect(headers.some((h) => /Ltd|Veyro/i.test(h))).toBe(true);
    expect(headers.some((h) => /[0-9a-f]{8}-[0-9a-f]{4}-/.test(h))).toBe(false);
  });

  test("says the columns are legal entities and the design asked for clubs", async ({
    page,
  }) => {
    await expect(page.locator("main")).toContainText("breaks this down by club");
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read revenue", () => {
  test("is refused the report and told which permission it needs", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/reports/revenue");
    await expect(page.locator("main")).toContainText("finance.revenue.read");
    // And no figure leaks through the refusal.
    await expect(page.locator(".ds-metric")).toHaveCount(0);
  });

  test("does not see the revenue row on the index", async ({ page }) => {
    // The canvas: "A Club Manager opening this screen sees four reports, not six. The two
    // financial ones are absent — not listed and locked."
    await useDeskSession(page);
    await page.goto("/reports");
    await expect(page.locator(".ds-report-list").getByRole("link", { name: "Revenue" }))
      .toHaveCount(0);
    // The page still renders, and still says what this build cannot report at all.
    await expect(page.locator("main")).toContainText("cannot report");
  });
});
