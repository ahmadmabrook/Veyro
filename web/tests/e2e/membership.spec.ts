import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * MOD-017 on a member's page, against a tenant that really has a membership and an invoice.
 *
 * **The routes these blocks read did not exist until this surface needed them.** MOD-017
 * shipped with no listing route of any kind, so a membership, a grant, an account and an
 * invoice were each reachable only by somebody who already held the id. This spec is the
 * evidence that the reads work through the request path, not merely that the service returns
 * rows -- MOD-014's reviewers found four defects that a green service suite could not see
 * because no test had ever called a `/people` route successfully.
 *
 * **Two things are asserted that a label-shaped test would miss.** The price is checked as a
 * rendered figure, because an amount is an integer count of minor units and JOD has three of
 * them -- a client dividing by 100 would show 450.00 where the agreement says 45.000, and
 * "the price is on the page" would pass either way. And the gate is asserted from a session
 * that genuinely lacks the permission, because the owner holds all of them and can only ever
 * prove the allowed half.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

// **Read from the fixture file, not from `process.env`.** The ids are written by
// `fixture.mjs` into `.env.e2e.local` and nothing exports them into this process, so a
// spec reading the environment navigates to `/people/undefined` and is told there is no
// such person -- which looks exactly like a product defect and is a harness mistake.
const MEMBER = `/people/${fixture().personId}`;

test.describe("the membership blocks on a member's page", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(MEMBER);
  });

  test("shows the membership with its number, kind and status", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Membership agreement", level: 2 })).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "GOLD-00042" });
    await expect(row).toContainText("recurring");
    await expect(row).toContainText("monthly");
    await expect(row).toContainText("active");
  });

  test("renders the agreed price with the currency's own exponent", async ({ page }) => {
    // 45000 fils is 45.000 dinars. A hard-coded /100 would render 450.00 and every
    // assertion about the word "price" would still pass, which is the whole point.
    const row = page.getByRole("row").filter({ hasText: "GOLD-00042" });
    await expect(row).toContainText("45.000");
    await expect(row).not.toContainText("450.00");
  });

  test("warns that the two member numbers on this page are different numbers", async ({
    page,
  }) => {
    // MOD-014's profile carries one and MOD-017's agreement carries another, nothing relates
    // them, and both are read out at a front desk. A page showing both without saying so is
    // the quiet kind of wrong answer.
    await expect(page.getByText(/two human-facing numbers owned by two modules/)).toBeVisible();
    await expect(page.getByRole("row").filter({ hasText: "GOLD-00042" })).toBeVisible();
  });

  test("says the status is what is true now, not what was true then", async ({ page }) => {
    // The cached status and the replayed history are different questions, and a surface that
    // implied otherwise would be wrong about every future-dated cancellation.
    await expect(page.getByText(/Status is what is true now/)).toBeVisible();
  });

  test("shows what is left on the entitlement and what is held", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /What this membership entitles/, level: 2 }),
    ).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "Group classes" });
    await expect(row).toContainText("10");
    await expect(row).toContainText("active");
  });

  test("says the balance was read without sweeping lapsed holds", async ({ page }) => {
    // The swept figure writes a ledger row, so this read deliberately does not produce it --
    // and a page that showed the number without that sentence would be claiming a precision
    // the read does not have.
    await expect(page.getByText(/without sweeping lapsed holds/)).toBeVisible();
  });

  test("shows the invoice, what was paid and both of its statuses", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Billing", level: 2 })).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "INV-" });
    await expect(row).toContainText("52.200");
    await expect(row).toContainText("paid");
    await expect(page.getByText(/move independently/)).toBeVisible();
  });

  test("shows a due date that is not the issue date", async ({ page }) => {
    // A payment term of zero is a real value and not the one anybody means, and the fixture
    // set both dates the same at first -- which rendered a caption repeating the date above
    // it. Caught by looking at the page.
    const row = page.getByRole("row").filter({ hasText: "INV-" });
    const issued = await row.textContent();
    const dates = (issued ?? "").match(/\d{4}-\d{2}-\d{2}/g) ?? [];
    expect(dates.length).toBeGreaterThanOrEqual(2);
    expect(dates[0]).not.toBe(dates[1]);
  });

  test("lays the billing summary out as label and value, not side by side", async ({
    page,
  }) => {
    // `.facts` is a two-column grid whose items are the `dt` and `dd`; wrapping each pair in
    // a `<div>` is valid HTML and makes the div the grid item, which put both labels on one
    // row with their values beneath. Asserting the geometry is the only way to see it --
    // every assertion about the text passed either way.
    const accounts = page.getByRole("term").filter({ hasText: "Accounts" });
    const outstanding = page.getByRole("term").filter({ hasText: "Outstanding" });
    const a = await accounts.boundingBox();
    const o = await outstanding.boundingBox();
    expect(a).not.toBeNull();
    expect(o).not.toBeNull();
    // Different rows: the second label sits below the first, not beside it.
    expect(o!.y).toBeGreaterThan(a!.y + a!.height / 2);
  });

  test("reports nothing outstanding once the invoice is settled", async ({ page }) => {
    // `outstanding` is not `status !== "paid"`: a credited or written-off document is settled
    // too, and counting either would put money on the screen nobody is going to collect.
    const outstanding = page.getByRole("term").filter({ hasText: "Outstanding" });
    await expect(outstanding).toBeVisible();
    await expect(
      page.locator("dd").filter({ hasText: /0\.000/ }).first(),
    ).toBeVisible();
  });

  test("says the blocks are composed here rather than joined on the server", async ({
    page,
  }) => {
    // Paragraph 1300 bars the cross-domain read, so the Member 360 says it does not do it.
    // The page does, through each module's own gate, and says which is which.
    await expect(page.getByText(/paragraph 1300/).first()).toBeVisible();
  });

  test("has no accessibility violation in these blocks", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a front desk who holds none of MOD-017's permissions", () => {
  test("is told each block is refused rather than shown an empty one", async ({ page }) => {
    // **The distinction this whole surface rests on.** "This member has no invoices" and
    // "you may not see them" are different facts, and only the first is about the member.
    // The front-desk identity holds `people.person.read` and none of the three MOD-017
    // reads, which is exactly the subset that makes this provable -- the reader beside it
    // cannot, because without the person read the page's own gate answers first.
    await useDeskSession(page);
    await page.goto(MEMBER);
    // The page itself renders, because this identity may read a person. What it may not read
    // is any of MOD-017, so all three blocks say so and none of them renders empty.
    await expect(page.getByRole("heading", { name: "Member 360", level: 1 })).toBeVisible();
    for (const name of [/^Membership agreement$/, /What this membership entitles/, /^Billing$/]) {
      const heading = page.getByRole("heading", { name, level: 2 });
      await expect(heading).toBeVisible();
      await expect(
        heading.locator("xpath=following-sibling::*").getByText("Not permitted").first(),
      ).toBeVisible();
    }
    // And none of MOD-017's data leaks through the refusal.
    //
    // **`GOLD-00042`, not `M-00042`.** The first version of this assertion used the latter and
    // failed -- because that is MOD-014's member number, on the profile this reader *may*
    // read. Two human-facing numbers on one page owned by two modules, and the test tripped
    // over the confusion the caption beside them now warns about.
    await expect(page.getByText("GOLD-00042")).toHaveCount(0);
    await expect(page.getByText("45.000")).toHaveCount(0);
  });
});
