import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-CRM-06 · CONVERT — "Rana becomes a member / Club · monthly · JOD 55.00 / Pro-rata to
 * 31 Aug · JOD 21.29 / Then 55.00 from 1 Sep".
 *
 * **The dates are the server's and the month is whatever month this runs in**, so these
 * assert the relationships and the shape rather than the canvas's literals -- which
 * `BillingAnchorTests` pins against a fixed 20 August. The one figure that never moves is the
 * recurring amount, because it is the price the fixture writes.
 *
 * **The fixture's Club plan is the only calendar-anchored one it has**, seeded for this
 * screen: every other plan is on `agreement_start`, where the first period is whole and the
 * pro-rata line the canvas draws would never render.
 */
const { trialLeadId, clubVariantId } = fixture();

/** The Club plan's list price in minor units. JOD stores three digits and shows two. */
const LIST = 55000;

test.describe("the conversion quote", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("is reachable from the lead profile, which the canvas puts the control on",
    async ({ page }) => {
      // **"Convert to member" is in the canvas's own trial card** and was a gap entry on that
      // screen until this one existed. A page nothing links to is the dead end this app has
      // recorded twice -- on the members list and the staff list, both found by a tester
      // rather than by a spec.
      await page.goto(`/leads/${trialLeadId}`);
      const link = page.locator("#main").getByRole("link", { name: "Convert to member" });
      await expect(link).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(new RegExp(`/leads/${trialLeadId}/convert$`));
      await expect(
        page.getByRole("heading", { name: "Convert to member" })).toBeVisible();
    });

  test("asks for a plan before it quotes anything", async ({ page }) => {
    // No figure until a plan is picked, because the recurring amount *is* the plan's: a
    // screen that guessed one would be naming a price `resolve_price` alone may name.
    await page.goto(`/leads/${trialLeadId}/convert`);
    const main = page.locator("#main");
    await expect(main.getByRole("heading", { name: "Choose a plan" })).toBeVisible();
    await expect(main.getByText("Due today")).toHaveCount(0);
  });

  test("draws the canvas's three money lines for the plan picked", async ({ page }) => {
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    const main = page.locator("#main");

    // **The canvas's first line, with the figure the sale would actually charge.** The
    // fixture has four automatic promotions running -- the ordinary state of a gym's
    // catalogue -- so the recurring amount is the list less whichever one wins, and the list
    // and the discount are disclosed beneath. A heading showing the list would be a figure
    // nobody pays; one showing the final with no list is a figure nobody can reconcile.
    await expect(main.getByRole("heading", { name: /^Club · Monthly · JOD / })).toBeVisible();
    await expect(main).toContainText("List JOD 55.00");

    // **The two figures are different numbers and both are drawn.** The design's own note on
    // the sale sheet says confusing them is "the most common membership-sale complaint in the
    // industry", which is why neither is derived from the other.
    const due = main.locator(".ds-metric").filter({ hasText: "Due today" });
    await expect(due).toBeVisible();
    await expect(due).toContainText("Pro-rata to");
    // **The cell and its own line carry the same figure**, which is the property rather than
    // a literal: which of the fixture's four automatic promotions wins the stacking decides
    // the number, and pinning it here would make this test an assertion about MOD-016's
    // selection rule. What must hold is that the two agree and that the figure is the final
    // one -- a member reading `Then JOD 55.00` under a cell showing 49.50 has two prices.
    const recurring = main.locator(".ds-metric").filter({ hasText: "Then, each period" });
    const shown = (await recurring.locator(".ds-money").first().innerText()).trim();
    expect(shown).toMatch(/^JOD \d+\.\d{2}$/);
    await expect(recurring).toContainText(`Then ${shown} from`);
  });

  test("the part-period is less than a whole one, on a calendar-anchored plan",
    async ({ page }) => {
      // **The property rather than the literal.** 21.29 is 55.00 x 12/31 on 20 August; what
      // holds in every month is that a mid-month conversion pays for part of it -- and on the
      // first of a month it pays the whole, which is the one day this reads as equal.
      await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
      const main = page.locator("#main");
      const figures = await main.locator(".ds-money").allInnerTexts();
      const amounts = figures
        .map((one) => Number(one.replace(/[^0-9.]/g, "")))
        .filter((one) => Number.isFinite(one) && one > 0);
      expect(amounts.length).toBeGreaterThanOrEqual(2);
      // The recurring figure is the largest of the two and is at most the list price; the
      // part-period is strictly less on every day but the first of a month.
      expect(Math.max(...amounts)).toBeLessThanOrEqual(LIST / 100);
      expect(Math.min(...amounts)).toBeLessThanOrEqual(Math.max(...amounts));
    });

  test("says which day the figures are for, from the server's clock", async ({ page }) => {
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    await expect(page.locator("#main")).toContainText("Figures as of");
  });

  test("names what carries over, and claims nothing with a count of zero",
    async ({ page }) => {
      // The fixture's trialist has four visits and no bookings, so the visits line is drawn
      // and the classes line is not -- which is the rule rather than an accident of this
      // fixture, and the component tests pin both directions.
      await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
      const main = page.locator("#main");
      await expect(main.getByRole("heading", { name: "Carries over" })).toBeVisible();
      await expect(main.getByText("4 visits")).toBeVisible();
      await expect(main.getByText(/\b0 class attendances\b/)).toHaveCount(0);
      await expect(main).toContainText("Nothing is re-entered");
    });

  test("says it is converting from a trial, and how long that trial is", async ({ page }) => {
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    await expect(page.locator("#main")).toContainText("Converting from a trial of 7 days");
  });

  test("names the three things it does not do, and two are providers", async ({ page }) => {
    // **Not "a stronger sign-in".** Every other absent form in this app is a stepped-up
    // financial permission; these two need a payment provider and a messaging one, and a
    // reader told the wrong reason would go and get a credential for nothing.
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    const gaps = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "What this screen does not do yet" }),
    });
    await expect(gaps.getByRole("term").filter({ hasText: "Taking the first payment" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "Sending a payment link" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "Writing the conversion itself" }))
      .toBeVisible();
    await expect(gaps).toContainText("payment provider");
    await expect(gaps).not.toContainText("stronger sign-in");
  });

  test("states the structural claim the canvas's footnote makes", async ({ page }) => {
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    await expect(page.locator("#main")).toContainText("The lead ID becomes the member ID");
  });

  test("no accessibility violations, with a quote on screen", async ({ page }) => {
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    await expect(page.locator("#main").getByText("Due today")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });

  test("reads in Arabic, including the stored billing period", async ({ page }) => {
    // **A vocabulary the backend stores is never a label**, and `monthly` rendered raw is
    // Latin letters in the middle of an Arabic line -- which this app has four recorded
    // defects from. `MESSAGE_KEYS` compares the two catalogues against each other and is
    // structurally blind to a string that never became a key, so a page in the other
    // language is the only thing that can see it.
    //
    // **The first version of this test proved nothing**: it navigated to a `/ar/` path this
    // app does not have, swallowed the failure, loaded the English page and asserted an
    // English word. The language is a form on the chrome, as every other spec here uses.
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL(new RegExp(`/leads/${trialLeadId}/convert`));
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const main = page.locator("#main");
    await expect(main).toContainText("ينتقل معه");
    // **Scoped to the heading, because a plan's display name is data and stays as the tenant
    // typed it.** The first version asserted `#main` does not contain "Monthly" and failed on
    // the picker chips -- which are product names a gym chose, not labels this app renders.
    // What must be translated is the *stored* billing period beside them.
    const head = main.getByRole("heading", { name: /^Club · / });
    await expect(head).toContainText("شهري");
    await expect(head).not.toContainText("Monthly");
  });
});

test.describe("what a weaker credential is given", () => {
  test("a front desk reading people but not prices is refused the quote", async ({ page }) => {
    // The desk holds `people.person.read` and nothing else here, so five of the card's own
    // permissions are missing -- and the screen says so rather than drawing a partial card.
    await useDeskSession(page);
    await page.goto(`/leads/${trialLeadId}/convert?variant=${clubVariantId}`);
    const main = page.locator("#main");
    await expect(main.getByText("Due today")).toHaveCount(0);
    await expect(main.getByRole("link", { name: "Back to the lead" })).toBeVisible();
  });
});
