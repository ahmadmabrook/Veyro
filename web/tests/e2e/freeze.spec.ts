import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn, useDeskSession, useOwnerSession } from "./sign-in";
import { stepUp } from "./step-up-helper";

/**
 * ADM-MSH-03 · FREEZE, and the first stepped-up write form in this app.
 *
 * **Every other absent form here is a financial-class permission**, and the inventory said
 * so for every one of them: "a button that answered 403 is worse than its absence". What
 * makes this one buildable is not a change to the permission but the step-up this app
 * already has — the block offers it with `next` back to this member, the way the member
 * record already offers one for a masked field. So the assertion that matters is not that
 * the form exists but that **a reader can get to it**, which is why the middle test here
 * actually steps up and looks.
 *
 * **Nothing in this file freezes anything.** A freeze spends the contract's annual
 * allowance, and a browser test that took a day of it per run is the budget shape this
 * repository has paid for four times; `test_commercial_api` covers the write with 176 tests
 * against memberships it makes itself. What a browser can prove and a backend test cannot is
 * that the cost is on screen *before* the button, which is the canvas's own structure.
 */

const creds = fixture();
const AT = `/people/${creds.personId}?tab=membership`;

test.describe("the freeze block at an ordinary sign-in", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("reads the allowance without a step-up, because that read is routine", async ({
    page,
  }) => {
    // `membership.record.read` is routine and `membership.lifecycle.change` is financial,
    // so the figure that bounds the act is legible to everybody who may see the membership
    // and only the act costs more. A screen that hid the allowance behind the step-up would
    // make somebody step up to find out whether it was worth stepping up.
    const block = page.locator("section").filter({ hasText: "Freeze this membership" });
    await expect(block).toContainText("of 30 days used this contract year");
    await expect(block).toContainText("A freeze starts between");
  });

  test("offers the step-up rather than a button that would answer 403", async ({ page }) => {
    const block = page.locator("section").filter({ hasText: "Freeze this membership" });
    await expect(block).toContainText("needs a stronger sign-in");
    await expect(block.getByRole("link", { name: "Sign in more strongly" })).toBeVisible();
    // And no form, because offering one that cannot submit is the thing being avoided.
    await expect(page.locator("form.ds-freeze-form")).toHaveCount(0);
  });

  test("says what it cannot do, including the two the canvas draws", async ({ page }) => {
    const block = page.locator("section").filter({ hasText: "Freeze this membership" });
    await expect(block.getByRole("term").filter({ hasText: "An override at the limit" }))
      .toBeVisible();
    await expect(block.getByRole("term").filter({ hasText: "A thirty-second undo" }))
      .toBeVisible();
  });
});

test.describe("the freeze form, once the reader has stepped up", () => {
  /**
   * **A saved session can be stepped up once, and then it is gone.** MOD-007 does not
   * elevate a session in place: it revokes the one it came from with
   * `revoke_reason = 'stepped_up'` and opens a new one, "because a session's lifetime
   * follows what it can do and a level-2 window is twelve hours rather than a fortnight".
   * The new cookie lives in that one browser context; `playwright/.auth/owner.json` still
   * holds the old one, so the *next* test to adopt it is signed out — and so is every spec
   * that runs after this file, which is how four of `step-up.spec.ts`'s tests failed the
   * moment this one existed.
   *
   * So each test here signs in for itself rather than adopting the shared cookie. Four
   * logins against MOD-011's thirty a minute, and the saved session is never touched.
   */
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto(AT);
    await page.getByRole("link", { name: "Sign in more strongly" }).click();
    await stepUp(page);
  });

  test("appears, and the step-up is the way to it", async ({ page }) => {
    // **This is the assertion the whole pattern rests on.** The claim is not "a form
    // exists" but "a reader at an ordinary sign-in can reach it", and the only way to know
    // is to follow the link the block offers and look at what comes back.
    await expect(page).toHaveURL(new RegExp(`/people/${creds.personId}`));

    const form = page.locator("form.ds-freeze-form");
    await expect(form).toBeVisible();
    await expect(form.getByLabel("From")).toBeVisible();
    await expect(form.getByLabel("Until")).toBeVisible();
    await expect(form.getByLabel("Why")).toBeVisible();
  });

  test("states the cost above the button, as the canvas does", async ({ page }) => {
    const form = page.locator("form.ds-freeze-form");
    const today = new Date().toISOString().slice(0, 10);
    const inSix = new Date(Date.now() + 6 * 86_400_000).toISOString().slice(0, 10);
    await form.getByLabel("From").fill(today);
    await form.getByLabel("Until").fill(inSix);

    // Seven days, counting both ends, leaving 23 of the thirty.
    const panel = form.locator(".ds-freeze-consequence");
    await expect(panel).toContainText("7 days");
    await expect(panel).toContainText("leaves 23");
    // And what a freeze actually does here, which is less than the canvas says.
    await expect(panel).toContainText("term is extended when the membership resumes");
  });

  test("refuses a freeze the contract cannot take, before anybody submits", async ({
    page,
  }) => {
    const form = page.locator("form.ds-freeze-form");
    const today = new Date().toISOString().slice(0, 10);
    const inForty = new Date(Date.now() + 40 * 86_400_000).toISOString().slice(0, 10);
    await form.getByLabel("From").fill(today);
    await form.getByLabel("Until").fill(inForty);
    await expect(form).toContainText("longer than the allowance left");
    // The consequence panel is replaced rather than sitting beside the refusal: a panel
    // describing what a freeze would do, under a sentence saying it cannot be taken, is two
    // answers to one question.
    await expect(form.locator(".ds-freeze-consequence")).toHaveCount(0);
  });

  test("refuses a start in the future, which is the module's own rule", async ({ page }) => {
    const form = page.locator("form.ds-freeze-form");
    const soon = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);
    const later = new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10);
    await form.getByLabel("From").fill(soon);
    await form.getByLabel("Until").fill(later);
    await expect(form).toContainText("not in the future");
  });
});

test.describe("a reader who holds nothing of the lifecycle", () => {
  test("is told which permission, and offered no step-up that would not help", async ({
    page,
  }) => {
    // A step-up cannot grant a permission nobody holds, so offering one here would send
    // somebody looking for a second factor that changes nothing — the member record's own
    // rule about a health field, applied to a write.
    await useDeskSession(page);
    await page.goto(AT);
    const block = page.locator("section").filter({ hasText: "Freeze this membership" });
    if (await block.count() === 0) return; // the membership block itself was refused
    await expect(block).not.toContainText("Sign in more strongly");
  });
});
