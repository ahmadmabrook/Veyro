import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * MOD-005's board, against a tenant that really has two keys and two flags.
 *
 * **Every assertion here is about telling two answers apart.** One configuration key is
 * published and one is not, so "nobody set it" can be distinguished from a tenant that chose
 * the same value; one flag is on its default and one has its kill switch engaged, which
 * outranks every targeting rule. A board that rendered the value and the variant alone would
 * be showing the two numbers most likely to be read as something they are not.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the configuration board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/configuration");
  });

  test("shows a published value with the scope it was set at", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Configuration", level: 1 })).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "booking.window_hours" });
    await expect(row).toContainText("72");
    // The scope is what makes the value meaningful: this one was published at the tenant.
    await expect(row).toContainText("tenant");
  });

  test("says nobody set the key nobody set, rather than showing its default bare", async ({
    page,
  }) => {
    // **A default is not a setting.** An unset key reads back as its own default, which is
    // indistinguishable from a tenant that published the same value unless the scope is shown.
    const row = page.getByRole("row").filter({ hasText: "checkin.grace_minutes" });
    await expect(row).toContainText("15");
    await expect(row).toContainText("nobody set it");
    await expect(page.getByText(/is a different fact from a tenant that published/))
      .toBeVisible();
  });

  test("says why a flag is off, not just that it is", async ({ page }) => {
    // Four reasons, four next actions. `off` on its own is the answer an operator cannot use.
    const row = page.getByRole("row").filter({ hasText: "booking.new_flow" });
    await expect(row).toContainText("off");
    await expect(row).toContainText("no rule matched, so the default");
  });

  test("marks a kill switch, because it outranks every rule", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "kiosk.offline_mode" });
    await expect(row).toContainText("a kill switch is engaged");
    await expect(page.getByText(/deliberate stop, not a rollout/)).toBeVisible();
  });

  test("names the subject the flags were evaluated for", async ({ page }) => {
    // A flag is evaluated per subject because that is what a rollout bucket is computed from,
    // so a board with no subject on it would be answering a question nobody asked.
    await expect(page.getByText(/what these flags say for/)).toBeVisible();
  });

  test("says there is no route that lists flags without evaluating them", async ({ page }) => {
    // Which is why a flag missing from this board is not a flag that is absent.
    await expect(page.getByText(/no route that lists flags without evaluating them/))
      .toBeVisible();
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: configuration, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/configuration");
      }
      const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may not read the configuration", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no Configuration entry in the navigation", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Configuration" })).toHaveCount(0);
  });

  test("is refused both blocks rather than shown an unconfigured tenant", async ({ page }) => {
    await page.goto("/configuration");
    const refusals = page.locator("main").getByRole("status").filter({ hasText: "Not permitted" });
    await expect(refusals).toHaveCount(2);
    // An empty registry would say this tenant has configured nothing, which is a different
    // fact -- and the flag block is its own permission, so a reader may hold one and not both.
    await expect(page.getByText("No configuration key is declared")).toHaveCount(0);
  });
});
