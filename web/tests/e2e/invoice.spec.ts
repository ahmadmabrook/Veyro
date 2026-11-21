import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-PAY-03 · INVOICE DETAIL — "One invoice, and its life".
 *
 * **Both reads were built and nothing rendered either.** `GET /finance/invoices/{id}/history`
 * carries a docstring naming this canvas by id and saying what it is for; it was written,
 * tested and never opened, so every invoice in this product was a figure with no way in.
 *
 * The assertions are about rendered values rather than labels, which this suite has paid to
 * learn: "the timezone is named on the page" passed while every time on the schedule board
 * was three hours wrong.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

const INVOICE = `/finance/invoices/${fixture().invoiceId}`;

test.describe("one invoice", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(INVOICE);
  });

  test("heads with the document's own number and its state", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1 })).toContainText("INV-");
    // **A green badge on this screen and none in a list.** ADM-PAY-03's state note is "Paid
    // — status badge in success"; ADM-MEM-01's is "No green badges". Both are right, and
    // the difference is whether the document's own state is the subject.
    await expect(page.locator(".ds-record-band")).toHaveAttribute("data-tone", "success");
  });

  test("adds up: net plus tax is the total, and paid leaves nothing outstanding", async ({
    page,
  }) => {
    // The figures, not their labels. An invoice page whose arithmetic a reader cannot check
    // by eye is one they cannot reconcile their books against -- which is the whole reason
    // the design separates collected from invoiced two screens over.
    const value = async (label: string) =>
      (await page.getByRole("term").filter({ hasText: label }).first()
        .locator("xpath=following-sibling::dd[1]").textContent())?.trim();
    expect(await value("Net")).toBe("JOD 45.00");
    expect(await value("Tax")).toBe("JOD 7.20");
    expect(await value("Total")).toBe("JOD 52.20");
    expect(await value("Outstanding")).toBe("JOD 0.00");
  });

  test("shows the invoice's life in order, from the insert-only tables", async ({ page }) => {
    // **The timeline is composed from what happened, not from the status.** A timeline built
    // from the cached `payment_status` says what is true now and nothing about how it got
    // there -- and a dispute never appears in it at all, because that status stays `paid`
    // throughout a chargeback. So the assertion is that the dispute is on this list.
    const timeline = page.locator(".ds-timeline-items");
    await expect(timeline.getByText("Issued")).toBeVisible();
    await expect(timeline.getByText("Payment received")).toBeVisible();
    // **Two of them**, because ADM-PAY-10's deadline box has an urgent state and a calm
    // one and a single dispute renders only one. The assertion here is that a dispute
    // reaches this timeline at all, so it is the first rather than an exact count.
    await expect(timeline.getByText("Dispute").first()).toBeVisible();
    await expect(timeline.getByText("Refund")).toBeVisible();
    // And the refund is negative on the same axis as the payment above it.
    const refund = page.locator(".ds-timeline-item").filter({ hasText: "Refund" }).first();
    await expect(refund).toContainText("−");
  });

  test("renders a date-only row as a date rather than above a blank line", async ({
    page,
  }) => {
    // `issued_on` is a `date` column, so there is no time of day: the gutter showed an
    // empty clock with the day under it until somebody looked at the page.
    const issued = page.locator(".ds-timeline-item").filter({ hasText: "Issued" }).first();
    const clock = issued.locator(".ds-timeline-clock");
    await expect(clock).not.toHaveText("");
    await expect(issued.locator(".ds-timeline-day")).toHaveCount(0);
  });

  test("names the scheme's deadline, which is the one that cannot be extended", async ({
    page,
  }) => {
    // `role="alert"`, not `status`: `Banner` gives the critical severity an alert and
    // everything else a status, and never both. A deadline set by somebody else that cannot
    // be extended is the critical one.
    await expect(page.locator("main").getByRole("alert").first())
      .toContainText(/cannot be extended/);
  });

  test("says a rejected filing is a problem and nothing here resubmits it", async ({
    page,
  }) => {
    const filing = page.locator("section").filter({ hasText: "Tax filing" }).first();
    await expect(filing).toContainText("refused this filing");
    await expect(filing).toContainText("there is no connector");
    // The state itself, so a reader can act on the word rather than on the sentence.
    await expect(filing).toContainText("rejected");
  });

  test("offers no edit and no take-payment, and says why", async ({ page }) => {
    // The canvas's own immutability note, which is a property of the schema here: the five
    // ledger tables are insert-only for both runtime roles.
    const notYet = page.locator("section").filter({ hasText: "What this screen does not do" });
    await expect(notYet).toContainText("insert-only for both runtime roles");
    await expect(notYet.locator(".data").filter({ hasText: "finance.payment.take" }))
      .toBeVisible();
    await expect(page.getByRole("button", { name: /take payment/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /edit/i })).toHaveCount(0);
  });

  test("is reachable from the member's billing tab rather than by knowing an id", async ({
    page,
  }) => {
    await page.goto(`/people/${fixture().personId}?tab=billing`);
    const link = page.getByRole("link").filter({ hasText: "INV-" }).first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/finance\/invoices\//);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("INV-");
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read a billing account", () => {
  test("is refused the invoice rather than shown an empty one", async ({ page }) => {
    await useDeskSession(page);
    await page.goto(INVOICE);
    await expect(page.locator("main").getByRole("status")).toContainText(/Not permitted/);
    // And none of the document leaks through the refusal.
    await expect(page.locator("main")).not.toContainText("INV-");
    await expect(page.locator("main")).not.toContainText("52.20");
  });
});
