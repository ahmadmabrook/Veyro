import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-MEM-05, the first screen in this app built from its design.
 *
 * The specification is pinned in `src/design/screens.generated.json`. What is asserted here
 * is the half this product can answer and the half it says it cannot — because the second is
 * the whole difference between a screen that is honest and one that renders an empty cell as
 * a fact about a member.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the members list", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/members");
  });

  test("is at Compact density, which the design states for this screen", async ({ page }) => {
    // "ADM-MEM-05 · MEMBERS LIST · CM, RECEP · COMPACT · 1440". Compact is 34px rows and the
    // body type one step down -- and the measurement is the assertion, because the first
    // version set `data-density` on a wrapper while the generated selector was `:root[...]`,
    // so the page read as compact and rendered at the default row height.
    const row = await page.evaluate(() => {
      const scope = document.querySelector("[data-density]");
      return scope
        ? getComputedStyle(scope).getPropertyValue("--density-row").trim()
        : null;
    });
    expect(row).toBe("34px");
  });

  test("states the match and the total as two numbers", async ({ page }) => {
    // "Showing 1-50 of 18 matching · 4,812 total". A filtered list that reported only its own
    // length would imply the records that did not match do not exist.
    await expect(page.getByText(/matching/)).toBeVisible();
    await expect(page.getByText(/in this tenant/)).toBeVisible();
  });

  test("filters by a lifecycle state and keeps the tenant's total", async ({ page }) => {
    // **The total only**, because the match is what the filter is supposed to move. Comparing
    // the whole footer compares both numbers and fails on the one that is working.
    const totalOf = async () =>
      (await page.getByText(/in this tenant/).innerText()).match(/·\s*([\d,٠-٩]+)/)?.[1];
    const before = await totalOf();
    expect(before).toBeTruthy();
    await page.getByRole("link", { name: "cancelled", exact: true }).click();
    await page.waitForURL(/state=cancelled/);
    expect(await totalOf()).toBe(before);
    await expect(page.getByText(/0 of 0 matching/)).toBeVisible();
  });

  test("an unknown state is ignored rather than rendering an empty list", async ({ page }) => {
    // A near miss in a URL somebody edited is not a filter. Rendering nothing would say the
    // tenant has no members, which is a different and wrong answer.
    await page.goto("/members?state=activ");
    await expect(page.getByRole("link", { name: "Every state" }))
      .toHaveAttribute("aria-current", "page");
  });

  test("marks a withheld name rather than printing the mask", async ({ page }) => {
    // The fixture's browser session is level 1, and `legal_name` is identity-classified -- so
    // MOD-014 returns `***`. A cell that rendered that raw would show three asterisks where
    // the member record shows a marked, explained withholding.
    const grid = page.locator(".ds-grid-table");
    await expect(grid).not.toContainText("***");
    await expect(grid.getByText("Withheld").first()).toBeVisible();
  });

  test("names what it does not do, with the product's own reason", async ({ page }) => {
    const gaps = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What this screen does not do yet" }) });
    await expect(gaps.getByText(/ENG-01/)).toBeVisible();
    await expect(gaps.getByText(/CLUB, BALANCE and LAST VISIT/)).toBeVisible();
    // And none of them is drawn as a control that does nothing.
    await expect(page.getByRole("button", { name: /Export/ })).toHaveCount(0);
    await expect(page.getByRole("searchbox")).toHaveCount(0);
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may read people and not memberships", () => {
  test("gets the table with the membership columns withheld, not an empty one", async ({
    page,
  }) => {
    // The design's own restricted state: "a receptionist sees the table without the balance
    // column and without Export". Here it is the membership columns, and "restricted" is a
    // word rather than a blank -- a blank cell in a plan column reads as "no plan".
    await useDeskSession(page);
    await page.goto("/members");
    const grid = page.locator(".ds-grid-table");
    await expect(grid).toBeVisible();
    // Scoped to what is visible: DataGrid renders every droppable column twice -- its own
    // cell and a secondary fragment in the primary cell -- with CSS showing one at any width.
    await expect(
      grid.getByText("restricted").filter({ visible: true }).first(),
    ).toBeVisible();
  });
});
