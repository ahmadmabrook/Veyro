import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { join } from "node:path";

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

  test("names the lifecycle state in the reader's own language", async ({ page }) => {
    // **A stored value is not a label.** The filter chips and the state column printed
    // `lead` and `active` raw, so an Arabic reader got Latin letters in the middle of an
    // Arabic page. The catalogue parity check is structurally blind to it -- it compares the
    // two catalogues against each other and never sees a string that was not a key -- so
    // this was found by switching the language and looking.
    await expect(page.locator("main")).toContainText("Lead");
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL(/members/);
    await expect(page.locator("main")).toContainText("\u0639\u0645\u064a\u0644 \u0645\u062d\u062a\u0645\u0644");
    await expect(page.locator("main")).not.toContainText(/\blead\b/);
  });

  test("offers the step-up on the list, not only inside a record", async ({ page }) => {
    // **Every name here is withheld at AAL 1**, because identity fields need a financial
    // permission the session does not carry -- and the remedy lived only on the member
    // record, so a reader of this list saw "Name withheld" against every row with nothing
    // on the page to act on. Found by an independent tester, who clicked the marker looking
    // for a way through.
    const withheld = page.locator("main").getByText("Withheld").first();
    await expect(withheld).toBeVisible();
    const offer = page.getByRole("link", { name: /stronger sign-in|Raise/i }).first();
    await expect(offer).toBeVisible();
    await expect(offer).toHaveAttribute("href", /\/step-up\?/);
    // And it comes back here, rather than dropping the reader on the record of nobody.
    await expect(offer).toHaveAttribute("href", /next=%2Fmembers/);
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
    const ds = JSON.parse(readFileSync(
      join(process.cwd(), "src/design/ds.json"), "utf8",
    )) as { DENSITY: string[][] };
    const compact = ds.DENSITY.find((mode) => mode[0] === "Compact");
    expect(row).toBe(`${String(compact?.[1]).split("/")[0]?.trim()}px`);
  });

  test("states the match and the total as two numbers", async ({ page }) => {
    // "Showing 1-50 of 18 matching · 4,812 total". A filtered list that reported only its own
    // length would imply the records that did not match do not exist.
    // **The two numbers are the figure and the grid's own count now.** The footer sentence
    // "Showing 1-50 of 18 matching · 4,812 total" has gone: the tenant total leads the
    // screen as the figure and the grid states how many rows it is showing, which is the
    // same two numbers in the two places a reader looks for each.
    await expect(page.locator(".ds-metric-row")).toContainText(/\d/);
    await expect(page.locator("#main")).toContainText(/\d+ (member|people|row)/i);
  });

  test("filters by a lifecycle state and keeps the tenant's total", async ({ page }) => {
    // **The total only**, because the match is what the filter is supposed to move. Comparing
    // the whole footer compares both numbers and fails on the one that is working.
    // **The tenant total is the figure now, not a clause of a footer.** It read
    // "Showing 1-50 of 18 matching · 4,812 total"; the total leads the screen as the one
    // figure the page is about, which is where this reads it.
    const totalOf = async () =>
      (await page.locator(".ds-metric-value").first().innerText()).replace(/\D/g, "");
    const before = await totalOf();
    expect(before).toBeTruthy();
    // **The chip reads the label, not the stored value.** It used to print `cancelled` raw,
    // which put a Latin word on an Arabic page; the URL still carries the stored value.
    await page.getByRole("link", { name: "Cancelled", exact: true }).click();
    await page.waitForURL(/state=cancelled/);
    expect(await totalOf()).toBe(before);
    // An empty filter result: the tenant total is unchanged above and the grid says it is
    // showing none, which is the same two facts the footer used to carry in one sentence.
    await expect(page.locator("#main")).toContainText(/0 member|no member/i);
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
    // **A module id and a column list, both from the retired bodies.** `ENG-01` names a
    // module to somebody reading the members list, and the columns the design draws that
    // this build cannot fill are named in the section rather than spelled in a sentence.
    await expect(gaps).not.toContainText(/ENG-\d+|MOD-\d+/);
    await expect(gaps).toContainText(/Search|Club|Balance|Last visit/i);
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
