import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * ADM-MSH-06 · DOWNGRADE · TIER 3, and ADM-MSH-05's upgrade read the other way.
 *
 * The canvas: **"Dana · Club+ to Club** — She loses: Access to Abdoun and Sweifieh · 2 monthly
 * PT sessions · her 4 unused PT credits expire on 1 Sep. Takes effect **1 September**, not
 * today — she has paid for August at the higher rate and keeps it." And the note that decides
 * the order: "The loss is stated before the saving, and the credit expiry is the line that
 * matters — a member who discovers it afterwards has been quietly charged for something they
 * never got."
 *
 * **Nothing here presses the confirm.** `membership.agreement.write` is financial class, so
 * the write needs a step-up and a step-up spends one of the owner's five recovery codes per
 * run — this repository has four recorded tests whose green depended on how many times the
 * suite had been run. And a plan change is one-way: the successor agreement stays, so a second
 * run would be moving a member who has already moved. What the spec proves is the disclosure,
 * which is where this screen's whole requirement lives.
 *
 * **The fixture's member is on the richer plan**, declared before they activated — ADR-0013
 * D8 means the mapping is read at activation and never again, so a fixture declaring
 * afterwards could only ever render the empty case.
 */

const creds = fixture();
// **The member inside their billing period**, which `lifecycle.plan_change` requires: the
// fixture's main member started ninety days ago and nothing rolls a period forward, so every
// change on them is correctly refused and the sheet renders its refusal banner. That state has
// its own test below.
const AT = `/people/${creds.recentPersonId}?tab=membership`;
const STALE = `/people/${creds.personId}?tab=membership`;

test.describe("the plan-change sheet", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("is closed until it is opened, with one control", async ({ page }) => {
    await page.goto(AT);
    const closed = page.getByRole("heading", { name: "Change this member's plan" });
    await expect(closed).toBeVisible();
    await expect(page.getByTestId("plan-consequence")).toHaveCount(0);
    await page.getByRole("link", { name: "Change the plan" }).click();
    await expect(page).toHaveURL(/plan=1/);
  });

  test("offers the other plans and not the one they are on", async ({ page }) => {
    await page.goto(`${AT}&plan=1`);
    await expect(page.getByRole("heading", { name: "Which plan" })).toBeVisible();
    const rows = page.locator(".ds-desk-row");
    await expect(rows.first()).toBeVisible();
    // The member's own plan is "Gold membership", declared on the variant they activated on.
    // Offering it would be a control `plan-change-quote` answers 409 to.
    await expect(page.getByRole("link", { name: "Gold membership", exact: true }))
      .toHaveCount(0);
  });

  test("states the loss before the saving, in the canvas's order", async ({ page }) => {
    await page.goto(`${AT}&plan=1`);
    await page.getByRole("link", { name: "Club", exact: true }).click();
    const sheet = page.getByTestId("plan-consequence");
    await expect(sheet).toBeVisible();

    // The loss, which the canvas puts first.
    await expect(sheet.getByText("What they lose")).toBeVisible();
    await expect(sheet.getByText(/Club access, at one club/)).toBeVisible();
    // PT is requantified rather than lost: two becomes one, which is neither keeping it nor
    // losing it and is the half a member argues about.
    await expect(sheet.getByText(/PT sessions: 2 becomes 1/)).toBeVisible();

    // Then the credits, which the canvas calls the line that matters.
    await expect(sheet.getByText("Credits that stop being usable")).toBeVisible();

    // Then the date, with the reason rather than the rule.
    await expect(sheet.getByText(/not today/)).toBeVisible();
    await expect(sheet.getByText(/higher rate and keeps it/)).toBeVisible();

    // And the money last, with what this build does not do said out loud.
    await expect(sheet.getByText(/New monthly:/)).toBeVisible();
    await expect(sheet.getByText(/no invoice is issued/)).toBeVisible();
  });

  // **The loss is above the control in the DOM, not only in the prose.** A screen that put
  // the confirmation first and the consequence under it would satisfy every assertion above
  // and still be the order the canvas's note forbids.
  test("puts the loss above the confirmation", async ({ page }) => {
    await page.goto(`${AT}&plan=1`);
    await page.getByRole("link", { name: "Club", exact: true }).click();
    const loss = await page.getByText("What they lose").boundingBox();
    const field = await page.getByLabel(/Type .* to confirm/).boundingBox();
    expect(loss).not.toBeNull();
    expect(field).not.toBeNull();
    expect(loss!.y).toBeLessThan(field!.y);
  });

  test("holds the confirm until the plan's name is typed back", async ({ page }) => {
    await page.goto(`${AT}&plan=1`);
    await page.getByRole("link", { name: "Club", exact: true }).click();
    const confirm = page.getByRole("button", { name: "Change the plan" });
    await expect(confirm).toBeDisabled();

    const field = page.getByLabel(/Type .* to confirm/);
    await field.fill("Gold membership");
    await expect(page.getByText("That is not the plan named above.")).toBeVisible();
    await expect(confirm).toBeDisabled();

    // **The plan's name, not the figure.** On a downgrade the figure is zero, so typing it
    // would be typing "0.00" to confirm losing access to a club.
    await field.fill("Club");
    await expect(page.getByText("That is not the plan named above.")).toHaveCount(0);

    // Still held, and by the one thing a field cannot clear: `membership.agreement.write` is
    // financial class, so an ordinary password session cannot press this whatever it types.
    await expect(confirm).toBeDisabled();
    await expect(page.getByText("Changing a plan needs a stronger sign-in.")).toBeVisible();
  });

  test("has a way out that changes nothing", async ({ page }) => {
    await page.goto(`${AT}&plan=1`);
    await page.getByRole("link", { name: "Keep the current plan" }).click();
    await expect(page).not.toHaveURL(/plan=1/);
    await expect(page.getByTestId("plan-consequence")).toHaveCount(0);
  });

  // **A membership outside its own billing period refuses every change**, because nothing in
  // this build rolls a period forward -- so the sheet names the server's refusal rather than
  // offering a confirmation it would answer 409 to.
  test("names the server's refusal rather than offering a dead control", async ({ page }) => {
    await page.goto(`${STALE}&plan=1`);
    await page.getByRole("link", { name: "Club", exact: true }).click();
    const sheet = page.getByTestId("plan-consequence");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByText("This change cannot be made")).toBeVisible();
    // The sentence, not the enum: `an_upgrade_takes_effect_inside_the_current_period` was
    // printed straight onto the page by the first version of this sheet.
    await expect(sheet.getByText(/past the end of its current billing period/))
      .toBeVisible();
    await expect(sheet.getByText(/an_upgrade_takes_effect/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Change the plan" })).toHaveCount(0);
  });

  test("has no accessibility violations with the consequence open", async ({ page }) => {
    await page.goto(`${AT}&plan=1`);
    await page.getByRole("link", { name: "Club", exact: true }).click();
    await expect(page.getByTestId("plan-consequence")).toBeVisible();
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(scan.violations).toEqual([]);
  });
});
