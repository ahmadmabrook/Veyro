import { expect, test, type Page } from "@playwright/test";

import { assuranceLevel, useOwnerSession } from "./sign-in";

/**
 * What the interface renders is what the gate answered.
 *
 * MOD-008 returns four distinguishable facts and the page must render them as four different
 * things. The one that is easy to get wrong is `reachable: false`: the gate sets
 * `step_up_required` *and* `reachable: false` for an AAL-3 action, so reading them in the wrong
 * order offers a step-up to a level this build cannot reach, and sends somebody looking for a
 * hardware key MOD-007 cannot verify.
 *
 * These assertions are against the **live** evaluator with the fixture's `tenant_admin` role, so
 * they would change if the catalogue's action classes changed -- which is the intent. A test
 * that stubbed the gate would keep passing while the product stopped agreeing with it.
 */

/** The gate cell for one action, read out of the permissions table. */
function verdictFor(page: Page, action: string) {
  return page.getByRole("row").filter({ hasText: action }).getByRole("cell").nth(1);
}

test.describe("gate-driven rendering", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("an allowed action reads as allowed", async ({ page }) => {
    await expect(verdictFor(page, "people.person.read")).toHaveText("Allowed");
    await expect(verdictFor(page, "finance.ledger.read")).toHaveText("Allowed");
  });

  test("a financial action is gated on the session's assurance, not on the role", async ({
    page,
  }) => {
    // **The assertion is read from the session, not assumed.** The fixture holds
    // `tenant_admin`, which holds everything -- so this cell is not about the permission at
    // all. `catalog.action_class` marks an unlock `financial`, which needs assurance level 2;
    // a password-only sign-in is level 1 and a sign-in that answered MOD-007's device
    // challenge with a recovery code is level 2. Both happen in a normal run, depending on
    // whether this browser has been seen before, so a test that hard-coded either answer
    // would be a coin flip. What must hold is the *relationship*, which is MOD-014's rule
    // that a grant is not a session.
    const aal = await assuranceLevel(page);
    await expect(verdictFor(page, "devices.command.unlock")).toHaveText(
      aal >= 2 ? "Allowed" : "Needs a stronger sign-in",
    );
    // And the control that does not move: `support.session.start` is privileged, which maps
    // to level 3, which needs a hardware factor MOD-007 cannot verify at any assurance.
    await expect(verdictFor(page, "support.session.start")).toHaveText(
      "Not available in this build",
    );
  });

  test("an AAL-3 action says it is unavailable rather than offering an impossible step-up", async ({
    page,
  }) => {
    await expect(verdictFor(page, "support.session.start")).toHaveText(
      "Not available in this build",
    );
  });

  test("the permissions table has an accessible name and is not captioned twice", async ({
    page,
  }) => {
    const table = page.getByRole("table");
    await expect(table).toHaveAccessibleName("What this session may do");
    // The heading said it and the caption repeated it, so a screen-reader user heard the
    // sentence twice. `aria-labelledby` gives the table a name without the duplication.
    await expect(page.getByText("What this session may do")).toHaveCount(1);
  });

  test("a permission name renders left-to-right even inside an Arabic document", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const action = page.getByText("people.person.read");
    await expect(action).toBeVisible();
    // Without an explicit direction the bidi algorithm reorders a dotted identifier inside RTL
    // text, which is how `people.person.read` arrives on screen as something else.
    await expect(action).toHaveAttribute("dir", "ltr");
  });
});
