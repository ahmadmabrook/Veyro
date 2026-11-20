import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-PAY-01 · PAYMENTS LEDGER — "Money, and the one place friction is correct".
 *
 * **This screen did not exist and `/finance` was being counted as it.** That route is
 * MOD-018's general ledger -- the chart, the period lock and the trial balance -- which is a
 * different subject, and the compliance record carried the mismatch as a named deviation.
 *
 * The assertions are about the canvas's own rules rather than about labels, because this
 * suite has already paid for the difference: "the timezone is named on the page" passed while
 * every time on the schedule board was three hours wrong. So the tests here read **rendered
 * figures and signs**, and the fixture seeds one of each kind precisely so they can.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the payments ledger", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/payments");
  });

  test("heads the page with what the screen is for, not with its noun", async ({ page }) => {
    // Every canvas in this design heads a board with its argument or its finding and puts
    // the noun on the rail. "Payments" over a table of payments is the one sentence on the
    // screen that tells a reader nothing.
    await expect(
      page.getByRole("heading", { name: /friction is correct/, level: 1 }),
    ).toBeVisible();
  });

  test("puts a refund and a dispute on the same axis, with a negative sign", async ({
    page,
  }) => {
    // **The canvas's rule, verbatim**: "Refunds carry a negative sign and the parenthetical
    // original. A refund is never shown as a payment of a different colour — it is a
    // different sign on the same axis." A test asserting the row exists would pass against
    // a board that rendered it positive in red, which is the thing the rule forbids.
    const refund = page.getByRole("row").filter({ hasText: "refund" }).first();
    await expect(refund).toContainText("−");
    const dispute = page.getByRole("row").filter({ hasText: "chargeback" }).first();
    await expect(dispute).toContainText("−");
    // And the received payment on the same axis carries no sign at all.
    const received = page.getByRole("row").filter({ hasText: "received" }).first();
    await expect(received).not.toContainText("−");
  });

  test("names what a negative row is about", async ({ page }) => {
    // The canvas's "parenthetical original": a negative figure with no story is a figure
    // nobody can check.
    const refund = page.getByRole("row").filter({ hasText: "refund" }).first();
    await expect(refund).toContainText(/\(\w{8}\)/);
  });

  test("shows a failed charge as a row, not as an absence", async ({ page }) => {
    // A ledger of successes is a ledger that cannot be reconciled. `fin_payment_intents`
    // carries the attempts that never became payments, which is the canvas's "6 failed".
    const failed = page.getByRole("row").filter({ hasText: "failed" }).first();
    await expect(failed).toContainText("charge attempt");
    await expect(failed).toContainText("Retry or ask for a new card");
  });

  test("counts the exceptions in the header and nothing that is zero", async ({ page }) => {
    const header = page.locator(".ds-page-figures");
    await expect(header).toContainText("1 failed");
    await expect(header).toContainText("1 refunded");
    await expect(header).toContainText("1 disputed");
    // "0 failed, 0 refunded, 0 disputed" is three facts nobody needs stated, so a clean
    // period says nothing here. With all three seeded this asserts the formatting rather
    // than the suppression; the component test asserts the suppression.
    await expect(header).toContainText("collected");
  });

  test("filters to the rows that need somebody, and the filter is in the URL", async ({
    page,
  }) => {
    await page.getByRole("link", { name: /Needs action/ }).click();
    await expect(page).toHaveURL(/filter=needs_action/);
    // The settled payment is not one of them; the pending refund, the failed charge and the
    // open dispute are.
    await expect(page.getByRole("row").filter({ hasText: "payment received" }))
      .toHaveCount(0);
    await expect(page.getByRole("row").filter({ hasText: "charge attempt" }))
      .toHaveCount(1);
  });

  test("masks the member's name rather than leaving the cell blank", async ({ page }) => {
    // **The ledger read carries no name at all** -- `finance.payment.read` is tenant-wide
    // and a money permission that returned names would be a lateral read path around
    // `people.person.read`. The page composes one through MOD-014's own gate, which masks
    // it on a level-1 session: the cell says "Withheld", which is a different fact from a
    // payment with no payer.
    const row = page.getByRole("row").filter({ hasText: "received" }).first();
    await expect(row.getByText("Withheld")).toBeVisible();
  });

  test("names what it cannot do rather than drawing a control that would be refused", async ({
    page,
  }) => {
    // A refund is tier 3 *and* tier 4 in the design's own scale -- a typed amount and a
    // second person -- and `finance.refund.request` is a stepped-up financial permission
    // with no form in this build.
    const notYet = page.locator("section").filter({ hasText: "What this screen cannot do" });
    await expect(notYet).toContainText("a second person to approve");
    // And the permission name is set as data rather than printed with its backticks --
    // `Prose` renders a backticked run as `.data`, which is this app's mono treatment for
    // an identifier.
    await expect(notYet.locator(".data").filter({ hasText: "finance.refund.request" }))
      .toBeVisible();
    await expect(notYet).not.toContainText("`");
    // No button offers any of it.
    await expect(page.getByRole("button", { name: /refund/i })).toHaveCount(0);
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read payments", () => {
  test("is refused the ledger and gets no rail entry for it", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/payments");
    await expect(page.locator("main").getByRole("status")).toContainText(/Not permitted/);
    // The navigation is filtered by the gate, which is the design's own "not available, and
    // absent from their UI entirely".
    await expect(page.getByRole("navigation", { name: "Sections" })
      .getByRole("link", { name: "Payments" })).toHaveCount(0);
  });
});
