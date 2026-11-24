import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * FD-02 · MEMBER LOOKUP — "Two members match. Check the photo before you let them through."
 *
 * **The photo does not exist**, so the sentence names what a desk can actually check: the last
 * four digits the canvas's own footnote calls the second check. ADR-0012 is why the lookup is
 * this module's work at all.
 *
 * **Nothing here writes**, so the suite can run as many times as it likes: a lookup is a read,
 * and the one control the canvas draws that would change anything -- "Let in" -- is named as
 * absent because it needs a door and a written reason this screen has neither of.
 */

const creds = fixture();
const AT = "/desk/lookup";

test.describe("the member lookup", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("rests until something is typed, rather than listing everybody", async ({ page }) => {
    await expect(page.getByText("Type the start of a name, or scan a card.")).toBeVisible();
    await expect(page.getByTestId("match")).toHaveCount(0);
  });

  test("refuses one character with the reason", async ({ page }) => {
    // One letter is every member whose name starts with it, in alphabetical order.
    await page.goto(`${AT}?q=h`);
    await expect(page.getByText("Two characters at least.")).toBeVisible();
    await expect(page.getByText(/alphabetical order/)).toBeVisible();
    await expect(page.getByTestId("match")).toHaveCount(0);
  });

  test("finds two people who share the start of a name, side by side", async ({ page }) => {
    // **The canvas's own case**, and what it refuses to do is pick one.
    await page.goto(`${AT}?q=${creds.lookupPrefix}`);
    const rows = page.getByTestId("match");
    await expect(rows).toHaveCount(2);
    await expect(page.getByTestId("match-count")).toContainText("2 members match");
    // And the check it tells a desk to make, which is not the photo.
    await expect(page.getByTestId("match-count"))
      .toContainText("last four digits");
  });

  test("puts the last four of the number beside each name", async ({ page }) => {
    await page.goto(`${AT}?q=${creds.lookupPrefix}`);
    const rows = page.getByTestId("match");
    await expect(rows.first()).toContainText("···");
    // **The whole number never reaches the page.** Four digits answer the question.
    const shown = await rows.first().innerText();
    expect(shown).not.toMatch(/\d{7}/);
  });

  test("links each match to the record, which is what a lookup is for", async ({ page }) => {
    await page.goto(`${AT}?q=${creds.lookupPrefix}`);
    const link = page.getByTestId("match").first().getByRole("link").first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/people\//);
  });

  test("offers the trial when nobody matches, and names the guest entry it cannot do",
    async ({ page }) => {
      // "No-match offers guest entry or lead capture." One of the two is built.
      await page.goto(`${AT}?q=zzzznobody`);
      const none = page.getByTestId("no-match");
      await expect(none).toContainText("Nobody matches");
      const escape = none.getByRole("link", { name: "Start a trial instead" });
      await expect(escape).toBeVisible();
      // **Where it goes, not just what it says.** A link with the right words and the wrong
      // destination is a dead end dressed as an escape, and asserting the name alone could
      // not tell the two apart -- which the mutation sweep said by coming back uncaught.
      await expect(escape).toHaveAttribute("href", "/desk/trial");
      await expect(none).toContainText(/payment at the door/);
    });

  test("still offers the trial beside the matches, which the canvas draws as Neither",
    async ({ page }) => {
      await page.goto(`${AT}?q=${creds.lookupPrefix}`);
      await expect(page.getByTestId("no-match")).toContainText("Neither of them?");
    });

  test("names the photo, the plan and the admission as absent", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /does not do/ })).toBeVisible();
    await expect(page.getByText("No photo")).toBeVisible();
    await expect(page.getByText(/blank circle would read as a photo missing/)).toBeVisible();
    await expect(page.getByText("No plan")).toBeVisible();
    await expect(page.getByText("A number is matched whole")).toBeVisible();
  });

  test("has no accessibility violations", async ({ page }) => {
    await page.goto(`${AT}?q=${creds.lookupPrefix}`);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations).toEqual([]);
  });
});
