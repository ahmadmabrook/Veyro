import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * ADM-CRM-07 · MARK LOST — "Why did Omar Zaid not join?" over four reasons, "Which gym, if he
 * said…", a `Mark lost` button, and the footnote the whole design rests on: "Not deleted.
 * Reopenable, and re-contact after 90 days is a supported flow rather than a fresh record."
 *
 * **A side sheet in the design and a query parameter here**, which is ADM-MSH-07's judgement:
 * this app has no side sheet, and `?lost=1` keeps the lead's context on screen while giving
 * "Keep it open" somewhere to go.
 *
 * **The fixture's lost lead was toured first**, because the decision this screen makes visible
 * is that the stage does not move. A lead lost at `new` would render correctly and demonstrate
 * nothing.
 */
const { lostLeadId, coldLeadId } = fixture();

test.describe("a lead that said no", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${lostLeadId}`);
  });

  test("keeps its stage, and the screen says why that matters", async ({ page }) => {
    // **The whole of ADR-0010 D8 in one assertion.** A sixth stage value would have needed a
    // backwards edge the moment this lead is reopened, and ADR-0010 D3 rules that out because
    // it would make `Toured · 6` a count nobody can reconstruct.
    const lost = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(lost).toContainText("Marked lost on");
    await expect(lost).toContainText("Joined somewhere else");
    // **The stage metric is the assertion now, and the sentence explaining it has gone.**
    // D8 is that a lost lead keeps the stage it reached, and the thing that says so is the
    // stage itself: this lead is lost and STAGE still reads Toured. The sentence that used to
    // sit in this panel ("Still at Toured, because the stage does not move") restated what
    // the reader could already see two inches above, so a test pinning it was asserting the
    // prose rather than the behaviour. Read where the reader reads it, with the absence of
    // the old wording asserted because that is the direction a revert comes from.
    const stage = page.locator("#main").locator(".ds-metric").filter({ hasText: "stage" });
    await expect(stage).toContainText("Toured");
    await expect(page.locator("#main")).not.toContainText("the stage does not move");
  });

  test("draws the free-text detail a salesperson wrote", async ({ page }) => {
    await expect(page.locator("#main"))
      .toContainText("he joined the one on Mecca Street");
  });

  test("offers the reopen, and says the ninety days is not a lock", async ({ page }) => {
    // **Both sentences say reopening is allowed**, which is ADR-0010 D10: locking it would
    // make a lead marked lost by mistake uncorrectable for a quarter on a routine permission.
    const lost = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(lost.getByRole("button", { name: "Reopen" })).toBeVisible();
    await expect(lost).toContainText("allowed whenever you need it");
  });

  test("is off the board and out of the table", async ({ page }) => {
    // ADM-CRM-01 draws five columns and no sixth, so a person who said no is not in the
    // pipeline the board counts -- their refusal is on their own record.
    //
    // **Identified by its own link, not by a name.** Every name on these screens is withheld
    // at an ordinary sign-in -- `legal_name` is an identity-class field -- so an assertion on
    // "Rami Odeh" is vacuous in *both* directions: it is absent from the live list and from
    // the lost one alike. The row's `href` is what is rendered and unambiguous.
    await page.goto("/leads?view=table");
    const main = page.locator("#main");
    const row = `a[href="/leads/${lostLeadId}"]`;
    await expect(main.locator(row)).toHaveCount(0);
    await page.goto("/leads");
    await expect(main.locator(row)).toHaveCount(0);
  });

  test("and is in the table's own Lost list, which is the only way to a list of them",
    async ({ page }) => {
      // **The chip this slice owed.** `GET /crm/leads` took `lost=true` from the day the
      // slice landed and nothing on `/leads` sent it, so a salesperson reviewing why people
      // did not join had no list at all -- the "writer with no reader" shape at the surface,
      // which this app has recorded twice and a tester found both times.
      await page.goto("/leads?view=table");
      const main = page.locator("#main");
      const chip = main.getByRole("link", { name: "Lost", exact: true });
      await expect(chip).toBeVisible();
      await chip.click();
      await expect(page).toHaveURL(/filter=lost/);
      await expect(main.locator(`a[href="/leads/${lostLeadId}"]`)).toBeVisible();
    });

  test("and the board offers no Lost chip, because it has no column for one",
    async ({ page }) => {
      // ADM-CRM-01 draws five stages and ADM-CRM-07 is a side sheet, so a chip here would ask
      // for a list the board cannot draw -- and one that changed the view under the reader
      // would be worse than one that is not there.
      await page.goto("/leads");
      await expect(page.locator("#main").getByRole("link", { name: "Lost" }))
        .toHaveCount(0);
    });

  test("no accessibility violations, with the lost state on screen", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("marking a live lead lost", () => {
  test("asks the canvas's question over its four reasons", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}`);
    const open = page.locator("#main").getByRole("link", { name: "Mark lost" });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page).toHaveURL(new RegExp(`/leads/${coldLeadId}\\?lost=1`));

    const sheet = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(sheet).toContainText("not join?");
    for (const reason of ["Too expensive", "Joined somewhere else", "Location or hours",
                          "No longer responding"]) {
      await expect(sheet.getByText(reason, { exact: true })).toBeVisible();
    }
    await expect(sheet.getByLabel(/Which gym/)).toBeVisible();
    await expect(sheet.getByRole("link", { name: "Keep it open" })).toBeVisible();
  });

  test("states the footnote the canvas insists on", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}?lost=1`);
    const sheet = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await expect(sheet).toContainText("Not deleted");
    await expect(sheet).toContainText("rather than a fresh record");
    await expect(sheet).toContainText("source effectiveness");
  });

  test("refuses with its own sentence when no reason is chosen", async ({ page }) => {
    // **`aria-required`, not the native attribute.** A native constraint refuses the submit
    // before any server sees it, so the message a reader acts on never renders -- which is
    // the branch ADM-MEM-10's `required` made unreachable.
    await useOwnerSession(page);
    await page.goto(`/leads/${coldLeadId}?lost=1`);
    const sheet = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Mark lost" }),
    });
    await sheet.getByRole("button", { name: "Mark lost" }).click();
    await expect(sheet).toContainText("Choose one of the four reasons");
  });
});

test.describe("an interest recorded by mistake", () => {
  test("can be taken back, which it could not before this slice", async ({ page }) => {
    // The fixture's lost lead holds `classes` and took `pt` back, so the profile lists one
    // and offers to withdraw it -- the remedy `crm_lead_interests` never had.
    await useOwnerSession(page);
    await page.goto(`/leads/${lostLeadId}`);
    const interests = page.locator("#main").locator("section.page-section").filter({
      has: page.getByRole("heading", { name: "Interest" }),
    });
    await expect(interests.getByRole("button", { name: /Take back — Classes/ }))
      .toBeVisible();
    // And the one already withdrawn is not listed as held.
    await expect(interests.getByRole("button", { name: /Take back — PT/ }))
      .toHaveCount(0);
  });
});
