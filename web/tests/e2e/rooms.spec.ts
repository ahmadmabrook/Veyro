import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-SCH-06 · ROOMS & RESOURCES, against the real routes. ADR-0018.
 *
 * **The fixture carries one of each kind, because a list with one kind demonstrates nothing.**
 * The spin room states a capacity of twenty-four and contains twenty bikes; the studio beside
 * it deliberately states neither, which is the other half of the distinction the screen exists
 * to draw — "not stated" is unbounded rather than "holds nobody", and a reader has to be able
 * to tell them apart.
 */
test.beforeEach(async ({ page }) => {
  await useOwnerSession(page);
  await page.goto("/schedule/resources");
});

test.describe("the rooms and resources card", () => {
  test("draws the canvas's three columns and nothing else", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1 }))
      .toContainText("Rooms and resources");
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    for (const header of ["NAME", "CAPACITY", "EQUIPMENT"]) {
      await expect(table.getByRole("columnheader", { name: header, exact: true }))
        .toBeVisible();
    }
    // No action, because the canvas draws none: a capacity and a containment are stated when
    // a resource is registered, and neither column carries an UPDATE grant.
    await expect(page.getByRole("main").getByRole("button")).toHaveCount(0);
  });

  test("states what the spin room holds, and what is in it", async ({ page }) => {
    const row = page.getByRole("table").getByRole("row").filter({ hasText: "Spin room" });
    await expect(row).toContainText("24 people");
    // **The quantity and the code**, because a count of rows is not a count of bikes: twenty
    // bikes are one row with a quantity of twenty, deliberately.
    await expect(row).toContainText("20 × BIKES-SPIN");
  });

  test("tells an unstated capacity from a room that holds nobody", async ({ page }) => {
    const row = page.getByRole("table").getByRole("row").filter({ hasText: "Studio" });
    await expect(row).toContainText("not stated");
    await expect(row).not.toContainText("0 people");
    await expect(row).toContainText("nothing recorded in it");
  });

  test("counts the spaces and how many are described", async ({ page }) => {
    // The header region, not one element of it: the space count leads as a figure now and
    // the described count stays in the line beneath, which is the same two facts.
    const head = (await page.locator(".ds-page-head, .ds-metric-row").allInnerTexts()).join(" ");
    expect(head).toMatch(/space/i);
    expect(head).toContain("with a stated capacity");
  });

  test("lists only spaces, because only a place holds people", async ({ page }) => {
    // The fixture's coach, service and bikes are resources too; a table that listed them
    // would be a table of three columns two of which are blank for most rows.
    const table = page.getByRole("table");
    await expect(table).not.toContainText("Dana Coach");
    await expect(table).not.toContainText("Spin bikes");
  });

  test("says the capacity is a ceiling rather than a default", async ({ page }) => {
    const note = page.locator("section").filter({
      hasText: "Capacity here is the ceiling every class inherits",
    });
    await expect(note).toContainText("not a default for one");
    await expect(note).toContainText("does not bind");
  });

  test("names the two routes that do not exist", async ({ page }) => {
    const notYet = page.locator("section").filter({
      hasText: "What this screen does not do yet",
    });
    await expect(notYet).toContainText("Change a capacity or move equipment");
    await expect(notYet).toContainText("stricter");
  });

  test("is the schedule's fourth view and links back to the others", async ({ page }) => {
    const bar = page.getByRole("navigation", { name: "View" });
    await expect(bar.getByRole("link", { name: "Week" })).toHaveAttribute(
      "href", "/schedule");
    await expect(bar.getByRole("link", { name: "Coaches" })).toHaveAttribute(
      "href", "/rota");
    await expect(bar.getByRole("link", { name: "Rooms" }))
      .toHaveAttribute("aria-current", "page");
  });
});

test.describe("the way in", () => {
  test("is on the schedule board, which is the list the canvas points at", async ({
    page,
  }) => {
    // "Double-booking is impossible because ADM-SCH-03 reads this list" -- so the list a
    // scheduler is told the constraint lives in has to be reachable from the schedule. A
    // route nothing links to is a route nobody finds, which ADM-MEM-05's missing Add member
    // and `/rota`'s stale gap note each cost this app once.
    await page.goto("/schedule");
    const rooms = page.getByRole("navigation", { name: "View" })
      .getByRole("link", { name: "Rooms" });
    await expect(rooms).toBeVisible();
    await rooms.click();
    await expect(page.getByRole("heading", { level: 1 }))
      .toContainText("Rooms and resources");
  });
});

test.describe("who may open it", () => {
  test("a reader without the schedule read is told so rather than shown an empty table",
    async ({ page }) => {
      await useDeskSession(page);
      await page.goto("/schedule/resources");
      await expect(page.getByRole("table")).toHaveCount(0);
      await expect(page.getByRole("main")).toContainText(/not permitted|permission/i);
    });
});

test.describe("the screen reads in both languages", () => {
  test("the whole screen reads in Arabic", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("القاعات");
    await expect(page.getByRole("main")).not.toContainText("Rooms and resources");
  });

  test("no accessibility violations", async ({ page }) => {
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
  });
});
