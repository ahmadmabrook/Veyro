import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * FD-07 · SHIFT OPEN AND CLOSE — "a discrepancy found at open belongs to the previous shift".
 *
 * **The open is the half this build had no notion of.** ADM-PAY-09 already closes a drawer,
 * and its form is imported here rather than written twice; what is new is the open, the
 * handover, and the note that travels between the two ends -- and a handover driven through
 * the route that existed used to post the float a second time, which is the defect migration
 * `0031` closes.
 *
 * **Nothing here opens a shift.** An open is one-way in the sense that matters for a suite:
 * the drawer the fixture hands over is the one the screen is about, and a spec that opened a
 * session on it would pass once and leave every later run looking at a close instead -- which
 * is this repository's own rule about a test that consumes state it cannot create, paid for
 * four times. The write itself is proven by the HTTP tests and the mutation sweep; what the
 * browser proves is what a receptionist is shown.
 */

const creds = fixture();
const AT = `/desk/shift?location_id=${creds.locationId}`;

test.describe("the shift screen", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("names the drawer and what the ledger says is in it", async ({ page }) => {
    // Derived from that account's own postings and shown before anything is counted, which
    // is the canvas's decision at the other end of the shift and holds at this one.
    const card = page.locator(".ds-cash-drawer").first();
    await expect(card).toBeVisible();
    await expect(card.getByRole("heading").first())
      .toContainText("the ledger says");
  });

  test("says who handed the drawer over, with the figure and the time", async ({ page }) => {
    // **The canvas's own line.** The Shop till closed with 17.50 counted and nothing banked,
    // so the drawer still holds it -- which is precisely "Kareem left JOD 50.00 at 16:04", a
    // till waiting for the next person to count what is there.
    //
    // **17,500 fils is JOD 17.50, and the first version of this test asserted 175.00.** JOD
    // is stored in fils and shown with two decimals, which is the one conflation
    // `@/lib/cash` exists to prevent -- so a test reading a seeded minor-unit figure as a
    // displayed one is the same defect from the other side.
    await page.goto(`${AT}&drawer=${creds.shopTillAccountId}`);
    const handover = page.getByTestId("handover");
    await expect(handover).toBeVisible();
    await expect(handover).toContainText("left");
    await expect(handover).toContainText("17.50");
  });

  test("renders the handover note the previous shift wrote", async ({ page }) => {
    // "The handover note is part of the shift, not a message that leaves with the person who
    // wrote it." The note is the point of this screen and nothing in the build wrote one
    // before `0031`.
    await page.goto(`${AT}&drawer=${creds.shopTillAccountId}`);
    const handover = page.getByTestId("handover");
    await expect(handover).toContainText("Sweifieh reader still down");
    await expect(page.getByTestId("handover-note-heading")).toBeVisible();
  });

  test("puts a name on the handover rather than an identity", async ({ page }) => {
    // **Three modules on one line**: the figure is MOD-018's, the time is the previous
    // session's close and the name is MOD-014's through `ppl_identity_links`. A till's
    // `closed_by` is a MOD-007 identity, so a screen that rendered it would read "handed over
    // from 7f3a1c2e" -- and the owner session is linked to no person, which is the ordinary
    // staff case and has its own sentence rather than a blank.
    await page.goto(`${AT}&drawer=${creds.shopTillAccountId}`);
    const handover = page.getByTestId("handover");
    const shown = await handover.innerText();
    expect(shown).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}/);
  });

  test("offers the count for a drawer being handed over", async ({ page }) => {
    await page.goto(`${AT}&drawer=${creds.shopTillAccountId}`);
    // "Count what is in the drawer", not "count the float": the money is already there and
    // nothing is drawn from the safe, which is the distinction the whole slice is about.
    await expect(page.getByLabel(/Count what is in the drawer/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Open the shift" })).toBeVisible();
  });

  test("says the difference belongs to the previous shift as the count goes out",
    async ({ page }) => {
      await page.goto(`${AT}&drawer=${creds.shopTillAccountId}`);
      // The drawer holds 17.50, so a count of 15.00 is 2.50 short.
      await page.getByLabel(/Count what is in the drawer/).fill("15.00");
      // **The canvas's sentence, and it is about attribution rather than blame.** It appears
      // before anything is pressed, which is what makes the reason a field somebody fills
      // rather than a refusal they discover.
      await expect(page.getByText(/belongs to the previous shift/)).toBeVisible();
      await expect(page.getByText("Short by")).toBeVisible();
      await expect(page.getByText("2.50")).toBeVisible();
      await expect(page.getByLabel("Why it differs")).toBeVisible();

      // **And over, which the short case cannot see.** A one-directional assertion about a
      // difference is this repository's own weakening trap pointed at a surface: a panel
      // keyed on `gap < 0` would pass every short case and render nothing for an over one.
      await page.getByLabel(/Count what is in the drawer/).fill("20.00");
      await expect(page.getByText("Over by")).toBeVisible();
      await expect(page.getByText("2.50")).toBeVisible();
    });

  test("offers the close for a drawer with a shift open, with the note field",
    async ({ page }) => {
      // The close is ADM-PAY-09's own form -- one definition of an act that posts to
      // suspense -- with FD-07's note added, which the admin board deliberately does not ask
      // for: the note is what one shift passes to the next.
      await page.goto(`${AT}&drawer=${creds.tillAccountId}`);
      await expect(page.getByRole("button", { name: "Close the drawer" })).toBeVisible();
      await expect(page.getByLabel(/What to pass to the next shift/)).toBeVisible();
    });

  test("names what it does not do rather than implying it does", async ({ page }) => {
    // The shift report the registry line promises, the threshold the canvas gates the note
    // on, the abandoned till the schema admits and nothing writes, and the club this desk
    // cannot know it is standing at.
    const gaps = page.getByRole("heading", { name: /does not do/ });
    await expect(gaps).toBeVisible();
    await expect(page.getByText("No shift report")).toBeVisible();
    await expect(page.getByText("Every difference needs a sentence")).toBeVisible();
  });

  test("has no accessibility violations", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations).toEqual([]);
  });
});
