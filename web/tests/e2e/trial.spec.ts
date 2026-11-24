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
const { trialLeadId, coldLeadId } = fixture();

test.describe("the trial state of a lead profile", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${trialLeadId}`);
  });

  test("the band is the day of the trial, not the cold mark", async ({ page }) => {
    // **A running trial outranks the cold mark**, because a trialist is not somebody nobody
    // has rung -- the clock that matters is the one running out. `RecordHeader` draws one.
    const main = page.locator("#main");
    await expect(main.getByText("Day 6 of 7")).toBeVisible();
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
    await expect(metrics).toContainText("4");
    await expect(metrics).toContainText("High");
    await expect(metrics).toContainText("2");
  });

  test("the urgency line is the canvas's own sentence", async ({ page }) => {
    // "Her trial ends tomorrow" -- the server decides which of three it is, because
    // `ends_tomorrow` is a date comparison in the tenant's own frame.
    await expect(page.locator("#main").getByRole("heading", { name: /ends tomorrow/ }))
      .toBeVisible();
  });

  test("and the sentence under it is about use rather than a prediction", async ({ page }) => {
    const main = page.locator("#main");
    await expect(main.getByText(/used the trial more than most/)).toBeVisible();
    await expect(main.getByText(/not a prediction about whether they will join/))
      .toBeVisible();
  });

  test("the conversion is named rather than drawn, with both halves of why",
    async ({ page }) => {
      // The canvas's button is "Convert to member" and takes a payment. Converting is a
      // stepped-up financial plan change and the payment is the provider, so the screen says
      // what it would take -- a button that answered 403 is worse than its absence.
      const main = page.locator("#main");
      // `getByText`, not `getByRole("term")`: a `<dt>` has the role and Playwright computes
      // no accessible name for it, so the role locator finds nothing.
      await expect(main.getByText("Convert to member")).toBeVisible();
      await expect(main.getByText(/plan change onto the membership/)).toBeVisible();
      await expect(main.getByText(/A card is real money/)).toBeVisible();
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
