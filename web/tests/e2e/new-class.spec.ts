import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn, useOwnerSession } from "./sign-in";
import { stepUp } from "./step-up-helper";

/**
 * ADM-SCH-03 · CREATE A CLASS, and MOD-019's first write form.
 *
 * **The live check is the screen**, which the canvas says twice: "conflicts surface as the
 * coach field changes, not on save", and "it warns, it does not block: a manager may know
 * Omar's PT is moving". So the assertions that matter are that a clash appears without a
 * submit and that it does *not* stop one -- the opposite of every other hold in this app.
 *
 * **Nothing here creates a class.** The fixture's template holds the one studio and the one
 * coach at that hour, which is what makes the clash reachable at all, and a spec that
 * published a second class would change what every schedule assertion in the suite sees --
 * the fixture-coupling trap this repository records for two specs sharing one tenant. The
 * three writes are covered by `test_scheduling_api`, which builds its own gym.
 */

const creds = fixture();
const AT = `/schedule/new?location=${creds.locationId}`;

test.describe("the create form at an ordinary sign-in", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("is the canvas's seven controls", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1 }))
      .toHaveText("New recurring class");
    const form = page.locator("form.ds-walk-in-form");
    for (const label of ["Type", "Coach", "Room", "Capacity", "Time", "Minutes",
                         "Waitlist"]) {
      await expect(form.getByLabel(label)).toBeVisible();
    }
    // The week, Sunday first, which is the canvas's own order and the rota grid's.
    const chips = form.getByRole("group", { name: "Repeats" });
    await expect(chips.getByRole("checkbox")).toHaveCount(7);
  });

  test("states the dates it derived, because the canvas asks for none", async ({ page }) => {
    // `recurrence.Rule` requires an end and "repeats weekly" has none, so the range is
    // derived -- and printed, rather than hidden behind a button.
    await expect(page.locator("form.ds-walk-in-form"))
      .toContainText("The rule runs");
  });

  test("offers the step-up rather than a button that would answer 403", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await expect(form).toContainText("needs a stronger sign-in");
    await expect(form.getByRole("link", { name: "Raise this session to create a class" }))
      .toBeVisible();
  });

  test("says what it cannot do, including the capacity the canvas caps", async ({ page }) => {
    const main = page.locator("#main");
    await expect(main.getByRole("term")
      .filter({ hasText: "Capping the capacity at what the room holds" })).toBeVisible();
    await expect(main.getByRole("term")
      .filter({ hasText: "Whether a coach can teach this class" })).toBeVisible();
    await expect(main.getByRole("term")
      .filter({ hasText: "Editing a class that already has bookings" })).toBeVisible();
  });

  test("is reachable from the calendar, which is the only route to it", async ({ page }) => {
    await page.goto(`/schedule?site=${creds.locationId}`);
    const open = page.getByRole("link", { name: "Create a class" });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page).toHaveURL(new RegExp("/schedule/new"));
  });
});

test.describe("the live check, once the reader has stepped up", () => {
  /**
   * Each test signs in for itself, because a step-up revokes the session it came from: the
   * shared cookie would be signed out for every spec that ran afterwards.
   */
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto(AT);
    await page.getByRole("link", { name: "Raise this session to create a class" }).click();
    await stepUp(page);
  });

  test("reports the clash as the fields change, with no submit", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    // **The fixture's template is *daily* at 18:00**, holding the one studio and the one
    // coach every day -- so any weekday collides and the chip's index does not matter. A
    // weekly fixture would make this spec depend on which day the suite ran, which is the
    // day-of-week flake `test_scheduling_api` already records.
    await form.getByLabel("Time").fill("18:00");
    // **The chip, not the checkbox.** `ChoiceChips` hides the control and draws the chip
    // on its label, so `.check()` waits for an element that is never visible -- which
    // FD-05's spec paid for once. The click a reader makes is on the face.
    const chips = form.getByRole("group", { name: "Repeats" });
    await chips.locator(".ds-choice-chip").nth(1).click();
    const panel = form.locator(".ds-walk-in-duplicate");
    await expect(panel).toContainText("This hour is not free");
    // A clash's kind is a word from the catalogue and never its stored form.
    await expect(panel).not.toContainText("double_booked");
  });

  test("warns and does not block: the reason is what is required", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Time").fill("18:00");
    const chips = form.getByRole("group", { name: "Repeats" });
    await chips.locator(".ds-choice-chip").nth(1).click();
    await expect(form.locator(".ds-walk-in-duplicate")).toContainText("not free");
    // **The button is held by the missing reason, not by the clash.** Paragraph 1842 is
    // permission *and* reason, so the field is what the hold is about -- and the sentence
    // says so rather than saying the hour is busy.
    await expect(form).toContainText("Say why the clash is acceptable");
    await form.getByLabel("Keep them anyway — why").fill("his PT is moving");
    await expect(form).not.toContainText("Say why the clash is acceptable");
  });

  test("says the hour is free, and over how many classes it looked", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    // An hour nothing holds: the fixture's classes are at 18:00 and 19:00, so 06:00 is free.
    await form.getByLabel("Time").fill("06:00");
    const chips = form.getByRole("group", { name: "Repeats" });
    await chips.locator(".ds-choice-chip").nth(1).click();
    const panel = form.locator(".ds-walk-in-duplicate");
    await expect(panel).toContainText("The hour is free");
    await expect(panel).toContainText(/Checked the next \d+ class/);
  });

  test("counts the classes a week on its own button", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    const chips = form.getByRole("group", { name: "Repeats" });
    await expect(form.getByRole("button", { name: "Create" })).toBeVisible();
    await chips.locator(".ds-choice-chip").nth(1).click();
    await expect(form.getByRole("button", { name: "Create · 1 class a week" }))
      .toBeVisible();
    await chips.locator(".ds-choice-chip").nth(3).click();
    await expect(form.getByRole("button", { name: "Create · 2 classes a week" }))
      .toBeVisible();
  });
});
