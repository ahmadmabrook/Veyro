import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * ADM-PAY-06, against a tenant that has declared nothing.
 *
 * **The fixture publishes no dunning policy**, which is the state the canvas does not draw and
 * the one most tenants are in: the figures are the journey this build already ran, and the
 * screen says so rather than presenting a default as a decision. The arithmetic is pinned in
 * `test_commercial_domain.py` and the registry half in `test_commercial_api.py`; what is here
 * is what a reader sees.
 *
 * **Nothing presses the save.** `finance.dunning.manage` is financial class, so the owner's
 * AAL-1 session is correctly refused and the screen offers the step-up -- which is the state
 * worth asserting, because a spec that stepped up would spend a recovery code per run.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the dunning rules", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/payments/dunning");
  });

  test("renders the two rules as sentences with the figures in them", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Dunning rules", level: 1 })).toBeVisible();
    // **The sentence is the canvas's and the label is what a screen reader hears.** `Field`'s
    // prefix and suffix are decorative by contract, so the accessible name has to carry the
    // meaning on its own -- which is why the control is found by its label rather than by the
    // words around it.
    const retry = page.getByLabel("Times to retry a failed card");
    await expect(retry).toHaveValue("4");
    await expect(page.getByText("Retry the card")).toBeVisible();
    await expect(page.getByText("times, one day apart.")).toBeVisible();
    const grace = page.getByLabel("Days of access past the due date");
    await expect(grace).toHaveValue("14");
    await expect(page.getByText("days past the due date.")).toBeVisible();
  });

  test("says the figures are defaults rather than a decision", async ({ page }) => {
    // The fixture declares neither key, so this is the sentence that must be here -- and its
    // absence would present the journey this build already ran as something somebody chose.
    await expect(page.getByText(/Nobody has set these/)).toBeVisible();
  });

  test("renders the journey the figures produce, with the restricting step marked", async ({
    page,
  }) => {
    // **Rendered from the server rather than described**, so what a reader checks is what the
    // module will do. Five steps, and the fourth is the one the access grace moves.
    const journey = page.locator("section").filter({
      has: page.getByRole("heading", { name: "The journey these rules produce" }),
    });
    await expect(journey.getByRole("row")).toHaveCount(6);
    const restricting = journey.getByRole("row").filter({ hasText: "payment_final_notice" });
    await expect(restricting).toContainText("day 14");
    await expect(restricting).toContainText("restrict");
    // The suspension step keeps its seven days behind, which is what "the tail moves with it"
    // means when the grace is left at its default.
    await expect(journey.getByRole("row").filter({ hasText: "account_suspension_notice" }))
      .toContainText("day 21");
  });

  test("offers the step-up rather than a button the gate would refuse", async ({ page }) => {
    // `finance.dunning.manage` is financial class because the figures decide when a member's
    // access is recommended to be restricted. A button that answered 403 is worse than its
    // absence; a step-up offered first is the precedent ADM-MSH-03 set.
    await expect(page.getByText(/financial-class permission/)).toBeVisible();
    const offer = page.getByRole("link", { name: "Needs a stronger sign-in" });
    await expect(offer).toBeVisible();
    await expect(offer).toHaveAttribute(
      "href", /action=finance\.dunning\.manage/);
    await expect(page.getByRole("button", { name: "Save these rules" })).toHaveCount(0);
  });

  test("renders the floor and says which half of it is structural", async ({ page }) => {
    // **The NEVER block is not a setting**, which the canvas says outright. Two of its four
    // rules are properties of this build -- an access recommendation is recorded and never
    // applied, and there is no stored card to charge -- and a floor a reader cannot tell from
    // an intention is a floor they have to take on trust.
    const floor = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Never, whatever the rules say" }),
    });
    await expect(floor.getByRole("listitem")).toHaveCount(4);
    await expect(floor.getByRole("listitem")
      .filter({ hasText: "Never block access without a person deciding" }))
      .toContainText("enforced by this build");
    await expect(floor.getByRole("listitem")
      .filter({ hasText: "Never message outside" }))
      .toContainText("an intention");
    await expect(page.getByText(/Not configurable per tenant/)).toBeVisible();
  });

  test("names the three settings it cannot honour, with what each waits on", async ({
    page,
  }) => {
    await expect(page.getByRole("heading", { name: "What these rules cannot set yet" }))
      .toBeVisible();
    await expect(page.getByText(/Nothing retries a card on a schedule in this build/))
      .toBeVisible();
    await expect(page.getByText(/there is no approval queue for a drafted message/))
      .toBeVisible();
    await expect(page.getByText(/nothing in collections writes one/)).toBeVisible();
  });

  test("keeps the account's own payment terms apart from the policy", async ({ page }) => {
    // Two figures in days and two different subjects: a reader seeing both would assume they
    // were one, which is the conflation this sentence exists to prevent.
    await expect(page.getByText(/payment terms are a separate figure/)).toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("the dunning rules, reached from the workspace they sort", () => {
  test("is linked from the recovery workspace", async ({ page }) => {
    // A screen with no route to it is unreachable, and this is the screen whose figures decide
    // whether a row wants a retry or a link.
    await useOwnerSession(page);
    await page.goto("/payments/recovery");
    const link = page.getByRole("link", { name: "The rules this is sorted by" });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByRole("heading", { name: "Dunning rules", level: 1 })).toBeVisible();
  });
});

test.describe("a reader who may not see the recovery journeys", () => {
  test("is refused the policy rather than shown the defaults", async ({ page }) => {
    // The figures are not sensitive, but `finance.dunning.read` is what this screen is: a
    // reader refused the journeys has no business reading the rules they run on, and a page
    // that fell back silently would present this build's own constants as the tenant's.
    await useReaderSession(page);
    await page.goto("/payments/dunning");
    await expect(page.getByRole("heading", { name: "Dunning rules", level: 1 })).toBeVisible();
    await expect(page.getByLabel("Times to retry a failed card")).toHaveCount(0);
    await expect(page.getByText("Not permitted")).toBeVisible();
  });
});
