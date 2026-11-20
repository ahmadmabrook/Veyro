import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * MOD-016's board, against a tenant with a published product, a live price and two promotions.
 *
 * **The fixture seeds one promotion that is live and one that ended while still reading as
 * active**, because that pair is the whole point of showing the window beside the status.
 * Nothing retires a promotion when its window closes -- the resolver reads the window -- so
 * `status: "active"` on a campaign that finished in February is the ordinary state of that
 * table. With only a live one seeded, the distinction is a comment rather than a behaviour.
 *
 * **No figure on this page is "the price".** `resolve_price` is the sale: it redeems the
 * coupon it applies, so the route that answers authoritatively cannot be called to find out.
 * The board shows stored rows and says which of the three conditions it has checked.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the catalog board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/catalog");
  });

  test("lists the published product with its type and status", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Catalog and pricing", level: 1 }),
    ).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "Gold membership" });
    await expect(row).toContainText("membership");
    await expect(row).toContainText("published");
  });

  test("shows a promotion that is active and no longer discounting", async ({ page }) => {
    // **The distinction the block exists for.** Both rows say `active`; only one of them is
    // doing anything, and the window is what tells them apart.
    const live = page.getByRole("row").filter({ hasText: "January sale" });
    await expect(live).toContainText("Discounting now");
    const past = page.getByRole("row").filter({ hasText: "New year offer" });
    await expect(past).toContainText("Not discounting");
    await expect(past).toContainText("active");
    await expect(past).toContainText("2026-02-01");
  });

  test("renders a promotion's worth as a percentage, not as basis points", async ({
    page,
  }) => {
    // 1000 bp is ten percent. `1000%` would be the units mistake, and an assertion about the
    // word "worth" would pass either way.
    const live = page.getByRole("row").filter({ hasText: "January sale" });
    await expect(live).toContainText("10%");
    await expect(live).not.toContainText("1000");
  });

  test("says nothing retires a promotion when its window closes", async ({ page }) => {
    await expect(page.getByText(/Nothing retires a promotion/)).toBeVisible();
  });

  test("shows the price book's dimensions and its priority", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "Standard" });
    await expect(row).toContainText("any");
    await expect(row).toContainText("active");
  });
});

test.describe("a product opened on the catalog board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/catalog?product=${fixture().productId}`);
  });

  test("shows the variant, what it grants and the price written for it", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "Monthly" });
    await expect(row).toContainText("30 days");
    // The agreed figure with the currency's own exponent: 45000 fils is 45.000 dinars.
    await expect(row).toContainText("JOD 45.000");
    await expect(row).toContainText("in its window, in an active book");
  });

  test("says the product can be sold, because it has a live price", async ({ page }) => {
    await expect(page.getByText(/has a live price and can be sold/)).toBeVisible();
  });

  test("says a row in its window is not the resolved price", async ({ page }) => {
    // Three things decide what a sale costs and a stored row answers one. A board that let
    // the figure read as a promise would be making a claim only the sale can make.
    await expect(page.getByText(/is not the resolved price/)).toBeVisible();
    await expect(page.getByText(/wins on priority/)).toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read the catalog", () => {
  test("gets no Catalog entry in the navigation", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Catalog" })).toHaveCount(0);
  });

  test("is refused the board rather than shown an empty catalog", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/catalog");
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("JOD 45.000")).toHaveCount(0);
  });
});
