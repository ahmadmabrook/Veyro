import { expect, test } from "@playwright/test";

import { signIn, useOwnerSession } from "./sign-in";
import { stepUp } from "./step-up-helper";

/**
 * FD-05 · WALK-IN TRIAL — "Two fields. Sales will get the rest later."
 *
 * **The second stepped-up write form in this app, and the first on the Front Desk.** Every
 * other absent form here is a financial-class permission and the inventory said so for each:
 * "a button that answered 403 is worse than its absence". What makes this one buildable is
 * the step-up this app already has -- the form offers it with `next` back to the desk, the
 * way ADM-MSH-03's freeze block does. So the assertion that matters is not that a form exists
 * but that **a reader can get to it**, which is why the second describe actually steps up.
 *
 * **A seeded number is the duplicate and a per-run one is the start.** The fixture's member
 * holds `+962 79 000 0042`, so the interruption is reachable without writing anything; the
 * press that does write uses a number nobody holds, because a spec that reused one would be
 * refused by its own duplicate check from the second run onwards -- the budget trap this
 * repository has paid for four times, in the shape where the state rather than the budget is
 * what the run consumes.
 */

const KNOWN = "+962 79 000 0042";
/**
 * One number held by two people, which no fixture had.
 *
 * **It is here because its absence hid a live 500 on two shipped screens.** All three screens
 * that check a phone draw an "also held by N other records" line, and it passed a *formatted*
 * count to a plural message -- which `fill` refuses, so the page answered "This page couldn't
 * load" the first time a family shared a number. The branch had never rendered, because the
 * two seeded numbers belong to one person each: a surface branch no fixture can reach, in the
 * quietest form this repository has met it. `fill` now takes the number and formats it itself,
 * the per-plural-form sweep names any site that pre-formats one, and this is the fixture that
 * makes the line real.
 */
const FAMILY_LINE = "+962 79 000 0044";
const AT = "/desk/trial";

test.describe("the walk-in form at an ordinary sign-in", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("names the trial's own length in the heading, from the published plan", async ({
    page,
  }) => {
    // The canvas's title is "Start a 7-day trial" -- a figure, so it comes from the plan's
    // `trial_days` rather than from a string. The fixture publishes one seven-day trial.
    await expect(page.getByRole("heading", { level: 1 }))
      .toHaveText("Start a 7-day trial");
    await expect(page.locator("main")).toContainText("Two fields");
  });

  test("is two fields and nothing else, which is the whole design", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await expect(form.getByLabel("Name")).toBeVisible();
    await expect(form.getByLabel("Phone")).toBeVisible();
    // No source, no interest, no plan: one published trial means the command derives it, so
    // the picker is the state the canvas does not draw.
    await expect(form.getByLabel("Which trial")).toHaveCount(0);
    // **Counted by role rather than by element**, because the first version asserted two
    // `input, select` nodes and the form has six: the acknowledgement travels as a hidden
    // input, React's form action adds its own, and the shell renders more. Those are not
    // fields a reader fills, and an assertion coupled to a component's internals fails the
    // day the shell changes for a reason that has nothing to do with this screen.
    await expect(form.getByRole("textbox")).toHaveCount(2);
    await expect(form.getByRole("combobox")).toHaveCount(0);
  });

  test("offers the step-up rather than a button that would answer 403", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await expect(form).toContainText("needs a stronger sign-in");
    await expect(form.getByRole("link", { name: "Raise this session to start a trial" }))
      .toBeVisible();
    await expect(form.getByRole("button", { name: "Start the trial now" }))
      .toBeDisabled();
  });

  test("runs the duplicate check as the number is typed, with the three escapes", async ({
    page,
  }) => {
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Name").fill("Maya Rifai");
    await form.getByLabel("Phone").fill(KNOWN);
    const panel = form.locator(".ds-walk-in-duplicate");
    await expect(panel).toContainText("This number already has a record");
    await expect(panel.getByRole("link", { name: "Open that record" })).toBeVisible();
    await expect(panel.getByRole("button", { name: "Different person" })).toBeVisible();
    // "Start the trial for them" is the one that needs the write permission, so at this
    // sign-in it is absent rather than offered and refused.
    await expect(panel.getByRole("button", { name: "Start the trial for them" }))
      .toHaveCount(0);
  });

  test("counts the other records on a number a family shares", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Name").fill("Maya Rifai");
    await form.getByLabel("Phone").fill(FAMILY_LINE);
    const panel = form.locator(".ds-walk-in-duplicate");
    await expect(panel).toContainText("This number already has a record");
    // Two people hold it, so one *other* record beyond the one named -- and this is the line
    // whose own 500 this fixture exists to have caught.
    await expect(panel).toContainText("Held by 1 other record");
  });

  test("says what it does and what it cannot do", async ({ page }) => {
    const main = page.locator("main");
    await expect(main).toContainText("starts the trial with the clock running");
    await expect(main).toContainText("Issuing a credential");
    await expect(main).toContainText("app invitation by text");
    await expect(main.getByRole("term")
      .filter({ hasText: "A membership number the club chose" })).toBeVisible();
  });
});

test.describe("the press, once the reader has stepped up", () => {
  /**
   * **Each test signs in for itself**, because a step-up revokes the session it came from:
   * MOD-007 opens a new one rather than elevating in place, so the shared cookie in
   * `playwright/.auth/owner.json` would be signed out for every spec that ran afterwards.
   * That is how four of `step-up.spec.ts`'s tests failed the hour ADM-MSH-03's spec existed.
   */
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto(AT);
    await page.getByRole("link", { name: "Raise this session to start a trial" }).click();
    await stepUp(page);
  });

  test("starts a trial and reports day one of it", async ({ page }) => {
    await expect(page).toHaveURL(new RegExp("/desk/trial"));
    const form = page.locator("form.ds-walk-in-form");
    const unique = `+962 79 1${Date.now().toString().slice(-6)}`;
    await form.getByLabel("Name").fill("Maya Rifai");
    await form.getByLabel("Phone").fill(unique);
    // The clear verdict is the state the canvas's sibling draws, and it is what releases the
    // button: a check that has not answered holds it.
    await expect(form.locator(".ds-walk-in-duplicate"))
      .toContainText("No existing record");
    await form.getByRole("button", { name: "Start the trial now" }).click();

    const done = page.locator(".ds-banner");
    await expect(done).toContainText("The trial is running");
    // Day one is a fact about the write rather than a figure anybody computed, and seven is
    // the fixture plan's own length.
    await expect(done).toContainText("Day 1 of 7");
    await expect(done).toContainText("Membership handle TRIAL-");
    // The two of the canvas's three promises this build does not keep, on the screen.
    await expect(done).toContainText("No credential was issued");
    // "Yasmin picks it up on her pipeline within the minute" is an unowned lead on the
    // board, and this is the link to it.
    await expect(done.getByRole("link", { name: "Open the lead" })).toBeVisible();
  });

  test("offers to start the trial on a record the check already found", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Name").fill("Maya Rifai");
    await form.getByLabel("Phone").fill(KNOWN);
    const panel = form.locator(".ds-walk-in-duplicate");
    await expect(panel).toContainText("This number already has a record");
    // ADM-MEM-10 can only link to that record; this screen can act on it, because the
    // command takes a `person_id`. Asserted as an offer rather than pressed: the fixture's
    // member would be put on a trial, and a spec that did that once would find them already
    // on one on every run afterwards.
    await expect(panel.getByRole("button", { name: "Start the trial for them" }))
      .toBeEnabled();
  });
});
