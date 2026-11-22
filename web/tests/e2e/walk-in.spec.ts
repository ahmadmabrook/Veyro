import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { signIn, useDeskSession, useOwnerSession, useReaderSession } from "./sign-in";
import { stepUp } from "./step-up-helper";

/**
 * ADM-MEM-10 · ADD MEMBER MANUALLY — "New member · walk-in".
 *
 * **The number the fixture seeds on its member.** The detection assertions are about the
 * *answer*, not the digits, so the value is here once rather than inline in six places.
 */
const KNOWN = "+962 79 000 0042";

/** A second seeded number, on a different record. */
const OTHER = "+962 79 000 0043";

/** A number no run has used, so the clear path is clear and stays clear. */
const fresh = () => `+962 79 1${String(Date.now()).slice(-6)}`;

test.describe("the walk-in form at an ordinary sign-in", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/members/new");
  });

  test("is reachable from the members list, which specified the button and had none",
    async ({ page }) => {
      // **ADM-MEM-05's header draws "Add member"** and this app rendered nothing there — and
      // it was not in that screen's gap list either, so a specified control was missing with
      // no record anywhere that it was missing. This is the only way to reach the screen.
      await page.goto("/members");
      const add = page.getByRole("link", { name: "Add member" });
      await expect(add).toBeVisible();
      await add.click();
      await expect(page).toHaveURL(/\/members\/new$/);
      await expect(page.getByRole("heading", { name: "New member · walk-in" })).toBeVisible();
    });

  test("finds the record a number already belongs to, before anything is saved",
    async ({ page }) => {
      const form = page.locator("form.ds-walk-in-form");
      await form.getByLabel("Phone").fill(KNOWN);

      // **The read that did not exist.** `find_duplicates` scores pairs that already exist,
      // so the moment a duplicate is cheap to prevent had nothing to ask until now.
      const banner = page.locator(".ds-walk-in-detection");
      await expect(banner).toContainText("This number already has a record");
      await expect(banner).toContainText("create a second record for the same person");
      await expect(banner.getByRole("link", { name: "Open that record" })).toBeVisible();
      await expect(banner.getByRole("button", { name: "Different person" })).toBeVisible();
    });

  test("holds the create and says which of the two reasons it is", async ({ page }) => {
    // **At this assurance the button is disabled whatever the duplicate says**, because
    // `people.person.write` is financial class — so what is observable here is the sentence,
    // and the order of the two is the decision: a reader who cannot create a record at all
    // learns that before they spend effort resolving an interruption.
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Name").fill("Hala Barakat");
    await form.getByLabel("Phone").fill(KNOWN);
    await expect(page.locator(".ds-walk-in-detection"))
      .toContainText("This number already has a record");
    await expect(form.getByRole("button", { name: "Create the record" })).toBeDisabled();
    await expect(form).toContainText("needs a stronger sign-in");
  });

  test("acknowledges one number and not the next one", async ({ page }) => {
    // **The acknowledgement is the value, not a flag.** "Different person" answers *this*
    // number; a dismissal that carried over would hide the interruption for whatever is
    // typed next — which is why it takes two seeded numbers to show, and why one would only
    // ever prove that the dismissal sticks.
    const form = page.locator("form.ds-walk-in-form");
    const detection = page.locator(".ds-walk-in-detection");

    await form.getByLabel("Phone").fill(KNOWN);
    await expect(detection).toContainText("This number already has a record");
    await page.getByRole("button", { name: "Different person" }).click();
    await expect(detection).not.toContainText("This number already has a record");
    // And the field's own mark goes with it, because they are one state.
    await expect(page.locator('.ds-field-control[data-message="warning"]')).toHaveCount(0);

    await form.getByLabel("Phone").fill(OTHER);
    await expect(detection).toContainText("This number already has a record");
    await expect(page.locator('.ds-field-control[data-message="warning"]')).toHaveCount(1);
  });

  test("does not interrupt a number nobody holds", async ({ page }) => {
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Name").fill("Walk-in Clear");
    await form.getByLabel("Phone").fill(fresh());
    await expect(page.locator(".ds-walk-in-detection"))
      .not.toContainText("This number already has a record");
    // And the field is not marked, which is the other half of the interruption.
    await expect(page.locator('.ds-field-control[data-message="warning"]')).toHaveCount(0);
  });

  test("offers the step-up rather than a button that would answer 403", async ({ page }) => {
    // `people.person.write` is financial class, so the owner's own password-only session
    // cannot reach it — the freeze form's finding, and the reason the screen says so instead
    // of letting the submit fail.
    await expect(page.locator("form.ds-walk-in-form"))
      .toContainText("needs a stronger sign-in");
  });

  test("names the three parts of the design it does not do, and why", async ({ page }) => {
    const gaps = page.locator(".ds-walk-in-gaps");
    await expect(gaps.getByRole("term").filter({ hasText: "Selling the membership" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "An emergency contact" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "The waiver" })).toBeVisible();
  });

  test("states the mechanism the canvas's own footnote states", async ({ page }) => {
    await expect(page.locator(".ds-walk-in-note"))
      .toContainText("before anything is saved");
    await expect(page.locator(".ds-walk-in-note"))
      .toContainText("prevention is never perfect");
  });

  test("no accessibility violations, with the interruption on screen", async ({ page }) => {
    // **With the panel rendered**, because that is where this screen's own colour is: the
    // canvas draws the title in the attention hue and an axe run against the empty form
    // would never evaluate the one pairing this screen introduces.
    await page.locator("form.ds-walk-in-form").getByLabel("Phone").fill(KNOWN);
    await expect(page.locator(".ds-walk-in-detection"))
      .toContainText("This number already has a record");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("creating the record, once the reader has stepped up", () => {
  /**
   * **Signing in for itself rather than adopting the shared cookie.** A step-up revokes the
   * session it came from — `revoke_reason = 'stepped_up'` — and the new cookie lives in this
   * browser context only, so a spec that stepped up the saved session would sign out every
   * spec that runs after it. That is how four of `step-up.spec.ts`'s tests failed the moment
   * `freeze.spec.ts` existed.
   */
  test("creates a person with a contact point, and offers to open it", async ({ page }) => {
    await signIn(page);
    await page.goto("/members/new");
    await page.getByRole("link", { name: "Raise this session to create records" })
      .click();
    await stepUp(page);

    const form = page.locator("form.ds-walk-in-form");
    await expect(form.getByLabel("Name")).toBeVisible();
    await form.getByLabel("Name").fill("Walk-in Created");
    await form.getByLabel("Phone").fill(fresh());

    const create = form.getByRole("button", { name: "Create the record" });
    await expect(create).toBeEnabled();

    // **The interruption holds a session that CAN act**, which is the only place the
    // enabling half is observable: at AAL 1 the button is disabled whatever the duplicate
    // says, so a spec that asserted it there would prove the permission and not the hold.
    await form.getByLabel("Phone").fill(KNOWN);
    await expect(page.locator(".ds-walk-in-detection"))
      .toContainText("This number already has a record");
    await expect(create).toBeDisabled();
    await page.getByRole("button", { name: "Different person" }).click();
    await expect(create).toBeEnabled();

    // Back to a number nobody holds, so the record this test creates is its own.
    const mine = fresh();
    await form.getByLabel("Phone").fill(mine);
    await expect(create).toBeEnabled();
    await create.click();

    // **"Nothing has been sold", said out loud**, because the design puts a sale sheet after
    // this block and this screen is only the identity half. A reader who thought a membership
    // had been sold would not go and sell one.
    await expect(page.getByText("The record was created")).toBeVisible();
    await expect(page.getByText("Nothing has been sold")).toBeVisible();
    const open = page.getByRole("link", { name: "Open the record" });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page).toHaveURL(/\/people\/[0-9a-f-]{36}/);
  });
});

test.describe("what each weaker credential is given", () => {
  test("a session without the read is refused the screen, not given a form with no check",
    async ({ page }) => {
      // Without the read there is no duplicate check, and a form that created records with no
      // check is the opposite of what this screen is for — so the page refuses rather than
      // degrading into one. This identity holds `access.zone.read` and not
      // `people.person.read`, which is the pair that makes the refusal provable.
      await useReaderSession(page);
      await page.goto("/members/new");
      await expect(page.locator("form.ds-walk-in-form")).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "Add a member" })).toBeVisible();
    });

  test("a front desk gets the check and no step-up that would not help", async ({ page }) => {
    // **The desk holds `people.person.read` and nothing else**, so the duplicate check works
    // and the write is `denied` rather than `needs_step_up`. A step-up cannot grant a
    // permission nobody holds, so offering one would send somebody looking for a second
    // factor that changes nothing — the member record's own rule about a health field,
    // applied to a write.
    await useDeskSession(page);
    await page.goto("/members/new");
    const form = page.locator("form.ds-walk-in-form");
    await form.getByLabel("Phone").fill(KNOWN);
    await expect(page.locator(".ds-walk-in-detection"))
      .toContainText("This number already has a record");
    await expect(form.getByRole("button", { name: "Create the record" })).toBeDisabled();
  });

  test("and the members list offers it no Add member button at all", async ({ page }) => {
    // A button that answered 403 is worse than its absence, and `gateVerdict` is what tells
    // "a stronger sign-in would open this" from "you may not".
    await useDeskSession(page);
    await page.goto("/members");
    await expect(page.getByRole("link", { name: "Add member" })).toHaveCount(0);
  });
});
