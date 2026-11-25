import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * ADM-SCH-07 · CANCEL A CLASS, in a browser against a real backend.
 *
 * **Nothing is cancelled here.** `scheduling.session.change` is financial class, so the commit
 * is refused for an AAL-1 session and the button's own refusal is what this asserts -- which
 * is better evidence than not pressing it: the step-up offer is a control, and a test that
 * skipped the press would prove the sheet renders and nothing about what it does. The
 * cancellation is one-way (a cancelled session does not come back, by design), so a spec that
 * did commit would be green once and red ever after.
 *
 * **The reads behind it are routine**, which is why the consequence and the message render at
 * all: the preview takes no hold, writes nothing, and says so on its own response.
 */
const creds = fixture();

/**
 * The consequence banners, which are the sheet's own and not the message panel's.
 *
 * **Precise rather than the whole form**, because the form contains the message panel: an
 * assertion scoped to the form would be satisfied by either, which makes it a weaker claim
 * than it reads as. The consequence is a banner; the message is a paragraph in a panel.
 */
function consequence(page: import("@playwright/test").Page) {
  return page.locator("form .ds-banner");
}

/**
 * The canvas's "They will receive", scoped by its own heading.
 *
 * `.last()` because the panel is nested inside the sheet, so both sections *have* that
 * heading and a bare filter is a strict-mode violation -- the innermost is the one the
 * message is in.
 */
function messagePanel(page: import("@playwright/test").Page) {
  return page.locator("section").filter({
    has: page.getByRole("heading", { name: "They will receive" }),
  }).last();
}

test.describe("the cancellation sheet", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/schedule/${creds.bookedSessionId}?cancel=1`);
  });

  test("leads with the class, its counts and how much notice the members get", async ({
    page,
  }) => {
    const sheet = page.locator("section", {
      has: page.getByRole("heading", { level: 2, name: /Cancel / }),
    }).first();
    await expect(sheet).toBeVisible();
    // The canvas's own sub-line: "18 booked, 3 on the waitlist. This is tomorrow."
    await expect(sheet).toContainText(/booked/);
    await expect(sheet).toContainText(/waitlist/);
    // **One of the three notice sentences, not a named one**: the fixture's class is the
    // second occurrence of a rule starting today, so it is tomorrow at the club -- and a run
    // that crosses local midnight between seeding and this spec would make it today. Both are
    // correct; a negative count is the thing that must never render.
    await expect(sheet).toContainText(/This is (today|tomorrow|in \d+ days?)\./);
    await expect(sheet).not.toContainText("in -");
  });

  test("offers every one of MOD-019's six declared reasons and no default", async ({
    page,
  }) => {
    const why = page.getByLabel(/^Why/);
    await expect(why).toHaveValue("");
    // A vocabulary the backend stores is never a label: each code has a word.
    await expect(why.locator("option")).toHaveCount(7);
    await expect(why.locator("option", { hasText: "No coach available" }))
      .toHaveCount(1);
  });

  test("says nothing about the consequence until a remedy is chosen", async ({ page }) => {
    const sheet = page.locator("section").filter({ hasText: /Cancel / }).first();
    await expect(sheet).toContainText(/Choose what the members get/);
    await expect(sheet).not.toContainText(/places are free/);
  });

  test("a credit states the window the canvas names, from the server", async ({ page }) => {
    await page.getByLabel(/^Why/).selectOption("instructor_unavailable");
    await page.locator(".ds-choice-chip", { hasText: "Give each a class credit" }).click();
    // **Scoped, because the sheet says it twice on purpose**: the consequence a manager reads
    // and the message a member receives both name the window, and an unscoped locator is a
    // test coupled to a phrase being unique in the document -- which this repository records
    // as a trap and which this spec hit on its first run.
    const message = messagePanel(page);
    await expect(message).toBeVisible();
    await expect(consequence(page)).toContainText(/usable on any class within 30 days/i);
    await expect(message).toContainText(/We have credited you a class/);
    await expect(message).toContainText(/Sent in each member's language/);
  });

  test("a move states the places and who would have to choose another", async ({ page }) => {
    await page.getByLabel(/^Why/).selectOption("instructor_unavailable");
    await page.locator(".ds-choice-chip", { hasText: "Move them to another class" }).click();
    // **By id, because `getByLabel` matches a substring**: the chip's own label is "Move them
    // to another class", so the name of the select is a prefix of it -- the same trap this
    // repository records for a column header that is a substring of a sibling's.
    const where = page.locator("#destination");
    await expect(where).toBeVisible();
    // **Counted, not asserted visible**: an `option` inside a closed `select` is hidden to a
    // browser, so `toBeVisible` on one fails for a list that is plainly there.
    await expect(where.locator("option")).not.toHaveCount(1);
    await where.selectOption({ index: 1 });
    // The figure is the destination's own free count, from MOD-019's hold sum -- nothing on
    // this page subtracts anything.
    await expect(consequence(page)).toContainText(/places are free\./);
    await expect(messagePanel(page)).toContainText(/We have held you a place on/);
  });

  test("the consequence follows the choice rather than the previous one", async ({ page }) => {
    await page.getByLabel(/^Why/).selectOption("weather");
    await page.locator(".ds-choice-chip", { hasText: "Give each a class credit" }).click();
    await expect(consequence(page)).toContainText(/usable on any class within 30 days/i);
    await page.locator(".ds-choice-chip", { hasText: "Move them to another class" }).click();
    // **A figure about a remedy the reader has just changed away from is the one they would
    // act on**, so the credit's sentence is gone rather than sitting beside a move. Asserted
    // on the sheet rather than on the banner: between the two choices the consequence is a
    // "reading…" line with no banner at all, and `not.toContainText` on a locator that
    // resolves to nothing fails rather than passing.
    await expect(page.locator("form").filter({ has: page.locator("#cancellation_reason") }))
      .not.toContainText(/usable on any class/i);
  });

  test("the commit offers the step-up this session needs, and cancels nothing", async ({
    page,
  }) => {
    await page.getByLabel(/^Why/).selectOption("instructor_unavailable");
    await page.locator(".ds-choice-chip", { hasText: "Give each a class credit" }).click();
    await expect(consequence(page)).toContainText(/class credit/i);
    await expect(page.getByRole("button", { name: /^Cancel and notify/ })).toBeVisible();
    await page.getByRole("button", { name: /^Cancel and notify/ }).click();
    await expect(page.getByText(/needs a stronger sign-in/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Step up and cancel" })).toBeVisible();
    // **The class is still scheduled**, which is what makes this spec re-runnable: a
    // cancelled session does not come back.
    await page.goto(`/schedule/${creds.bookedSessionId}`);
    await expect(page.locator(".ds-record-head")).not.toContainText("cancelled");
  });

  test("names finding a coach instead rather than offering a dead control", async ({
    page,
  }) => {
    // "Never a locked control with no route": ADM-SCH-03's clash check is about a class being
    // created, and substituting an instructor on a published one has no form.
    await expect(page.getByText(/Finding a coach instead is not a form/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Find a coach/ })).toHaveCount(0);
  });

  test("the roster stays on the page, because the sheet is over a record", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Who is booked" })).toBeVisible();
  });

  test("the way in is on the class itself", async ({ page }) => {
    // A route nothing links to is a route nobody finds -- ADM-MEM-05's own finding.
    await page.goto(`/schedule/${creds.bookedSessionId}`);
    const open = page.getByRole("link", { name: "Cancel this class" });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page.getByRole("heading", { level: 2, name: /Cancel / })).toBeVisible();
  });
});
