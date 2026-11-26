import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-CRM-05 · TRIAL RUNNING — a *state* of ADM-CRM-03 rather than a screen of its own,
 * which the canvas says by labelling one card with both ids.
 *
 * The fixture's trialist is on day 6 of a 7-day trial with four visits, which is the canvas's
 * own worked example: `DAY 6 OF 7 · Her trial ends tomorrow · 4 VISITS · 4 CLASSES ·
 * 2 DAYS LEFT · High ENGAGEMENT`. **Four of those six are asserted here and two are named
 * rather than drawn**: the classes count is zero because nothing in the fixture books this
 * person into a class, and "all spin" is a fact no read in this build produces.
 */
const { trialLeadId, coldLeadId, trialStart } = fixture();

/**
 * The day the trial is on **now**, derived from the seeded start rather than assumed.
 *
 * **The fixture and the assertions are two processes with two clocks.** Provisioning puts
 * the trialist on day 6 of 7; CI provisions and then runs a ten-minute suite, so a run that
 * begins at 23:58Z asserts at 00:02Z against a page correctly saying day 7 -- and three
 * tests here went red on `main` for exactly that, on a commit whose code was right. The
 * canvas's own figures (`DAY 6 OF 7 · 2 DAYS LEFT · ends tomorrow`) are asserted in
 * `tests/component/trial.test.ts`, where the card is built by hand and no clock can move.
 * What this file proves is that the page renders the day the seeded start implies, which is
 * a second route to the same number rather than a weaker assertion.
 */
const OF_DAYS = 7;
const midnightUtc = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
function trialDay(): { dayOf: number; daysLeft: number; urgency: RegExp } {
  const start = midnightUtc(trialStart);
  const today = midnightUtc(new Date().toISOString().slice(0, 10));
  const dayOf = Math.floor((today - start) / 86_400_000) + 1;
  const daysLeft = OF_DAYS - dayOf + 1;
  // `urgencyKey`'s own three branches, which the page picks between on the server's figures.
  const urgency = daysLeft === 2 ? /ends tomorrow/
    : daysLeft <= 1 ? /ends today/ : /day \d+ of/i;
  return { dayOf, daysLeft, urgency };
}

test.describe("the trial state of a lead profile", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${trialLeadId}`);
  });

  test("the band is the day of the trial, not the cold mark", async ({ page }) => {
    // **A running trial outranks the cold mark**, because a trialist is not somebody nobody
    // has rung -- the clock that matters is the one running out. `RecordHeader` draws one.
    const main = page.locator("#main");
    const { dayOf } = trialDay();
    await expect(main.getByText(`Day ${dayOf} of ${OF_DAYS}`)).toBeVisible();
    await expect(main.getByText("No contact")).toHaveCount(0);
  });

  test("the metric row is the trial's four cells, not the sales four", async ({ page }) => {
    const metrics = page.locator("#main section.metrics");
    await expect(metrics).toContainText("Visits");
    await expect(metrics).toContainText("Classes");
    await expect(metrics).toContainText("Days left");
    await expect(metrics).toContainText("Engagement");
    // And not the sales row, which a trial has already answered.
    await expect(metrics).not.toContainText("Touchpoints");
  });

  test("four visits in six days reads as high use", async ({ page }) => {
    // **The figure and the word.** Four visits on day six is 0.67 a day, which is the
    // canvas's `High` -- and the word comes from the catalogue rather than the stored band,
    // which this app has five recorded defects from.
    const metrics = page.locator("#main section.metrics");
    const { daysLeft } = trialDay();
    await expect(metrics).toContainText("4");
    await expect(metrics).toContainText("High");
    await expect(metrics).toContainText(String(daysLeft));
  });

  test("the urgency line is the canvas's own sentence", async ({ page }) => {
    // "Her trial ends tomorrow" -- the server decides which of three it is, because
    // `ends_tomorrow` is a date comparison in the tenant's own frame.
    await expect(page.locator("#main").getByRole("heading", { name: trialDay().urgency }))
      .toBeVisible();
  });

  test("and the sentence under it is about use rather than a prediction", async ({ page }) => {
    const main = page.locator("#main");
    await expect(main.getByText(/used the trial more than most/)).toBeVisible();
    // **The refusal to predict is carried by the label, not by a sentence disclaiming one.**
    // MOD-020 refuses a no-show score outright and the same reasoning holds here, so the cell
    // is labelled by what it measures. The prototype's own name for it was CONVERSION
    // LIKELIHOOD; asserting that word is absent is the property, where the removed clause was
    // one wording of it.
    await expect(main).toContainText("engagement");
    await expect(main.getByText(/likelihood/i)).toHaveCount(0);
  });

  test("the conversion is a link now, and the gap sentences are gone with the gap",
    async ({ page }) => {
      // **This asserted the gap and ADM-CRM-06 closed it.** It required
      // "plan change onto the membership" and "A card is real money" to be *visible* on this
      // card -- the two sentences explaining why the canvas's `Convert to member` button was
      // not here -- and the conversion screen exists, so the control is a link and both
      // sentences went with the gap. A gap list is a claim about the product, which is why
      // closing one means deleting its note in the same change.
      //
      // **What is asserted instead is the property that still holds, plus the absence of the
      // claim that does not** -- the direction that cannot go stale the next time a gap
      // closes behind it, which this repository has now paid for three times.
      const main = page.locator("#main");
      const link = main.getByRole("link", { name: "Convert to member" });
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute("href", /\/convert$/);
      await expect(main).not.toContainText("plan change onto the membership");
      await expect(main).not.toContainText("A card is real money");
      // And the payment is still not taken; the conversion screen says so where the figure
      // is, which is where a reader is deciding.
      await expect(main.getByRole("button", { name: "Convert to member" }))
        .toHaveCount(0);
    });

  test("a visit and a class are told apart on the screen", async ({ page }) => {
    await expect(page.locator("#main")
      .getByText(/a visit is a door they came through/i)).toBeVisible();
  });

  test("no accessibility violations with the trial card on screen", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("a lead who is not on a trial", () => {
  test("gets the sales metric row and no trial card at all", async ({ page }) => {
    // **Three of the five board columns are people without a trial**, so the ordinary state
    // says nothing: a note explaining the absence would be on every lead in the tenant.
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}`);
    const main = page.locator("#main");
    await expect(main.locator("section.metrics")).toContainText("Touchpoints");
    // **Scoped to the metric row**, because the gap list at the foot names the engagement
    // reading the design draws -- and a document-wide `getByText` found that sentence, which
    // is how the stale "nothing marks a trial product" note on this very screen surfaced.
    await expect(main.locator("section.metrics")).not.toContainText("Engagement");
    await expect(main.getByText(/ends tomorrow/)).toHaveCount(0);
  });
});

test.describe("what a weaker credential is given", () => {
  test("a front desk is told which reads the card wants", async ({ page }) => {
    // The desk holds `people.person.read` and nothing else, so it has neither the lead read
    // nor the two the card composes -- and the page's own refusal comes first. What this
    // asserts is that the screen never renders a trial card it could not read.
    await useDeskSession(page);
    await page.goto(`/leads/${trialLeadId}`);
    await expect(page.locator("#main").getByText("Day 6 of 7")).toHaveCount(0);
    await expect(page.locator("#main").locator("section.metrics")).toHaveCount(0);
  });
});
