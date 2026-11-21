import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * MOD-009's board, and the block on it that is not about this tenant.
 *
 * **This build cannot fully erase a person**, and until this page the disclosure had nowhere
 * to live: `deletion_is_complete()` returns False and `plan_dsar` surfaced it per request, so
 * the honest answer to "what can you delete" was reachable only after somebody had asked you
 * to delete something. The registry behind it was in Python and in a test.
 *
 * **The fixture seeds two pairs that exist to make a distinction visible**: a live legal hold
 * beside a released one, because a hold's whole meaning is whether it is still preserving;
 * and a request due in the future beside one already overdue, because the deadline is the one
 * number on that screen with a regulator attached. With one of each kind the board would
 * render and prove nothing.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the privacy board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/privacy");
  });

  test("says this build cannot fully erase a person", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Privacy and retention", level: 1 }),
    ).toBeVisible();
    await expect(page.getByText(/cannot fully erase a person/)).toBeVisible();
    await expect(page.getByText(/crypto-shred/)).toBeVisible();
  });

  test("shows far more columns surviving than erased", async ({ page }) => {
    // The proportion rather than the exact numbers: both move as modules add columns, and a
    // test pinned to today's figures would fail for a reason that is not a regression. What
    // must not change silently is which way round they are.
    const erased = page.locator("dt").filter({ hasText: "Erased or anonymised" });
    const survives = page.locator("dt").filter({ hasText: "Survives an erasure" });
    await expect(erased).toBeVisible();
    await expect(survives).toBeVisible();
    const numbers = (await page.locator("dd .data").allTextContents())
      .map((n) => Number(n.replace(/[^0-9]/g, "")));
    expect(numbers.length).toBeGreaterThanOrEqual(2);
    const erasedCount = numbers[0] ?? 0;
    const survivesCount = numbers[1] ?? 0;
    expect(erasedCount).toBeGreaterThan(0);
    expect(survivesCount).toBeGreaterThan(erasedCount * 5);
  });

  test("groups the residue by area rather than listing every column", async ({ page }) => {
    // 375 rows of column names is a wall, not a disclosure. The grouping is the fix and the
    // row count is the only assertion that can see it.
    await expect(page.getByText(/is a wall rather than a disclosure/)).toBeVisible();
    const areas = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What erasure reaches" }) })
      .getByRole("row");
    const count = await areas.count();
    expect(count).toBeGreaterThan(5);
    expect(count).toBeLessThan(60);
    // The ledger keeps the most and is what a disclosure is about, so it is first.
    await expect(areas.nth(1)).toContainText("plt01.led_");
  });

  test("renders the registry's emphasis as emphasis, not as asterisks", async ({ page }) => {
    // The reasons were written where `**` is emphasis and a backtick is a column name, in a
    // Python module a developer reads. Printed literally they are punctuation nobody wrote
    // for a reader, in the one block whose job is to be read by somebody who is not one.
    const section = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What erasure reaches" }) });
    await expect(section).not.toContainText("**");
    // **Scoped to what is visible**, because DataGrid renders every droppable column twice:
    // once in its own cell and once as a secondary fragment inside the primary cell, with
    // CSS showing exactly one at any width. That is what makes the collapse a stylesheet
    // rule rather than a measurement -- a measurement is wrong on the first paint -- and it
    // means a plain locator matches two nodes while the reader and the accessibility tree
    // see one.
    await expect(
      section.locator("strong").filter({ hasText: "who pays." }).filter({ visible: true }),
    ).toBeVisible();
  });

  test("says the block reads no tenant data at all", async ({ page }) => {
    await expect(page.getByText(/reads no tenant data/)).toBeVisible();
  });

  test("puts the overdue request first and marks it", async ({ page }) => {
    const requests = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Data subject requests" }) });
    const first = requests.getByRole("row").nth(1);
    await expect(first).toContainText("deletion");
    await expect(first).toContainText("Overdue");
    // And the one that is not overdue is there too, after it.
    await expect(requests.getByRole("row").nth(2)).toContainText("access");
  });

  test("says only a deletion has an executor", async ({ page }) => {
    await expect(page.getByText(/Only a deletion has an executor/)).toBeVisible();
  });

  test("tells a live legal hold from a released one", async ({ page }) => {
    const holds = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Legal holds" }) });
    await expect(holds.getByText("Preserving")).toBeVisible();
    await expect(holds.getByText("Released")).toBeVisible();
    await expect(holds).toContainText("CASE-2026-114");
  });

  test("says nothing deletes on the retention schedule", async ({ page }) => {
    // The decision function exists and no job calls it. The absence changes the product, so
    // the board states it rather than listing policies that read as though they run.
    await expect(page.getByText(/Nothing deletes on this schedule/)).toBeVisible();
    const retention = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Retention policies" }) });
    await expect(retention).toContainText("access_decision");
    await expect(retention).toContainText("365");
  });

  test("says no clock runs from an incident", async ({ page }) => {
    await expect(page.getByText(/Nothing computes a notification deadline/)).toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read privacy", () => {
  test("gets no Privacy entry in the navigation", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Privacy" })).toHaveCount(0);
  });

  test("is refused the board rather than shown an empty register", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/privacy");
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("CASE-2026-114")).toHaveCount(0);
  });
});
