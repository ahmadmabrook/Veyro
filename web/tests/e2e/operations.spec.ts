import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * The operations board, against the real event plane.
 *
 * **The assertions are about which kind of number is being shown.** `evt_outbox` fills
 * whenever any module writes a business row -- the fixture alone leaves a dozen behind -- and
 * nothing in this build drains it: no consumer has a handler, no worker loops on the relay,
 * and the table has no DELETE grant. A page that rendered the backlog with an alarm beside it
 * would cry wolf on every ordinary use of the product; one that rendered it bare would let
 * somebody conclude the relay is working. Saying which is the feature.
 */
test.describe("the operations board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/operations");
  });

  test("counts the outbox the fixture's own writes filled", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Operations", level: 1 })).toBeVisible();
    const outbox = page.locator("section").filter({ hasText: "Event outbox" }).first();
    await expect(outbox).toContainText("Events waiting to be dispatched");
    // Provisioning a tenant writes events, so this is never zero on a seeded fixture -- which
    // is what makes the explanation beside it load-bearing rather than decorative.
    await expect(outbox.locator(".data").first()).not.toHaveText("0");
  });

  test("says a backlog nothing consumes is the missing worker, not a failure", async ({
    page,
  }) => {
    const outbox = page.locator("section").filter({ hasText: "Event outbox" }).first();
    await expect(outbox).toContainText(/Nothing drains this/);
    await expect(outbox).toContainText(/missing worker rather than a failing one/);
  });

  test("keeps a dead letter apart from a backlog, because that one is a fault", async ({
    page,
  }) => {
    // **Scoped by the heading, not by the text.** The outbox section carries "Dead letters"
    // as one of its row labels, so a `hasText` filter matches it first -- which is the "two
    // things answer the same locator" trap this suite has now hit three times.
    const letters = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Dead letters" }) });
    await expect(letters).toContainText(/used its whole retry budget/);
    await expect(letters).toContainText("Nothing is quarantined");
  });

  test("says no consumer has a handler rather than showing an empty routing table", async ({
    page,
  }) => {
    const routing = page.locator("section").filter({ hasText: "Routing" }).first();
    await expect(routing).toContainText(/no name in this build has a handler behind it/);
  });

  test("says an objective nobody runs raises no alert", async ({ page }) => {
    const objectives = page.locator("section").filter({ hasText: "Objectives" }).first();
    // An empty list here is honest rather than reassuring, and the page has to be the one
    // that says which.
    await expect(objectives).toContainText(/raises no alert/);
    await expect(objectives).toContainText(/honest rather than reassuring/);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: operations, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/operations");
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may not read the event plane", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no Operations entry in the navigation", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Operations" })).toHaveCount(0);
  });

  test("is refused each block rather than shown four empty ones", async ({ page }) => {
    await page.goto("/operations");
    // **Four permissions, four refusals.** An empty dead-letter table somebody may not see
    // reads as "nothing is quarantined", which is a different fact.
    const refusals = page.locator("main").getByRole("status").filter({ hasText: "Not permitted" });
    await expect(refusals).toHaveCount(4);
    await expect(page.getByText("Nothing is quarantined")).toHaveCount(0);
  });
});
