import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * ADM-CRM-07 · MARK LOST — "Why did Omar Zaid not join?" over four reasons, "Which gym, if he
 * said…", a `Mark lost` button, and the footnote the whole design rests on: "Not deleted.
 * Reopenable, and re-contact after 90 days is a supported flow rather than a fresh record."
 *
 * **A side sheet in the design and a query parameter here**, which is ADM-MSH-07's judgement:
 * this app has no side sheet, and `?lost=1` keeps the lead's context on screen while giving
 * "Keep it open" somewhere to go.
 *
 * **The fixture's lost lead was toured first**, because the decision this screen makes visible
 * is that the stage does not move. A lead lost at `new` would render correctly and demonstrate
 * nothing.
 */
const { lostLeadId, coldLeadId } = fixture();

test.describe("a lead that said no", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${lostLeadId}`);
  });

  test("keeps its stage, and the screen says why that matters", async ({ page }) => {
    // **The whole of ADR-0010 D8 in one assertion.** A sixth stage value would have needed a
    // backwards edge the moment this lead is reopened, and ADR-0010 D3 rules that out because
    // it would make `Toured · 6` a count nobody can reconstruct.
    const lost = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(lost).toContainText("Marked lost on");
    await expect(lost).toContainText("Joined somewhere else");
    await expect(lost).toContainText("Still at Toured");
    await expect(lost).toContainText("the stage does not move");
  });

  test("draws the free-text detail a salesperson wrote", async ({ page }) => {
    await expect(page.locator("#main"))
      .toContainText("he joined the one on Mecca Street");
  });

  test("offers the reopen, and says the ninety days is not a lock", async ({ page }) => {
    // **Both sentences say reopening is allowed**, which is ADR-0010 D10: locking it would
    // make a lead marked lost by mistake uncorrectable for a quarter on a routine permission.
    const lost = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(lost.getByRole("button", { name: "Reopen" })).toBeVisible();
    await expect(lost).toContainText("allowed whenever you need it");
  });

  test("is off the board and out of the table", async ({ page }) => {
    // ADM-CRM-01 draws five columns and no sixth, so a person who said no is not in the
    // pipeline the board counts -- their refusal is on their own record.
    //
    // **Only the exclusion is asserted**, because the table has no lost chip yet: the read
    // takes `lost=true` and nothing on `/leads` sends it, which the compliance record names
    // as what this screen still owes. Navigating to a parameter the page does not read would
    // be a test asserting a route rather than a screen.
    await page.goto("/leads?view=table");
    await expect(page.locator("#main").getByRole("cell", { name: "Rami Odeh" }))
      .toHaveCount(0);
    const board = page.locator("#main");
    await page.goto("/leads");
    await expect(board.getByRole("link", { name: /Rami Odeh/ })).toHaveCount(0);
  });

  test("no accessibility violations, with the lost state on screen", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("marking a live lead lost", () => {
  test("asks the canvas's question over its four reasons", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}`);
    const open = page.locator("#main").getByRole("link", { name: "Mark lost" });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page).toHaveURL(new RegExp(`/leads/${coldLeadId}\\?lost=1`));

    const sheet = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(sheet).toContainText("not join?");
    for (const reason of ["Too expensive", "Joined somewhere else", "Location or hours",
                          "No longer responding"]) {
      await expect(sheet.getByText(reason, { exact: true })).toBeVisible();
    }
    await expect(sheet.getByLabel(/Which gym/)).toBeVisible();
    await expect(sheet.getByRole("link", { name: "Keep it open" })).toBeVisible();
  });

  test("states the footnote the canvas insists on", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}?lost=1`);
    const sheet = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(sheet).toContainText("Not deleted");
    await expect(sheet).toContainText("rather than a fresh record");
    await expect(sheet).toContainText("source effectiveness");
  });

  test("refuses with its own sentence when no reason is chosen", async ({ page }) => {
    // **`aria-required`, not the native attribute.** A native constraint refuses the submit
    // before any server sees it, so the message a reader acts on never renders -- which is
    // the branch ADM-MEM-10's `required` made unreachable.
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}?lost=1`);
    const sheet = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await sheet.getByRole("button", { name: "Mark lost" }).click();
    await expect(sheet).toContainText("Choose one of the four reasons");
  });
});

test.describe("an interest recorded by mistake", () => {
  test("can be taken back, which it could not before this slice", async ({ page }) => {
    // The fixture's lost lead holds `classes` and took `pt` back, so the profile lists one
    // and offers to withdraw it -- the remedy `crm_lead_interests` never had.
    await useOwnerSession(page);
    await page.goto(`/leads/${lostLeadId}`);
    const interests = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Interest" }),
    });
    await expect(interests.getByRole("button", { name: /Take back — Classes/ }))
      .toBeVisible();
    // And the one already withdrawn is not listed as held.
    await expect(interests.getByRole("button", { name: /Take back — PT/ }))
      .toHaveCount(0);
  });
});
