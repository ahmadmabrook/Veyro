import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * MOD-018's board, against a tenant whose ledger really has postings in it.
 *
 * **The fixture seeds the chart before the invoice, and that ordering is the test.** MOD-018's
 * bridge runs inside MOD-017's transaction, so an invoice issued with no chart is posted
 * nowhere -- `post_invoice` returns `ledger_skipped_because` rather than refusing, precisely so
 * a tenant mid-setup does not find its till has stopped working. With the chart first, an
 * invoice and a payment produce a trial balance that an accountant can check by hand:
 * `provider_clearing` debited by what the card paid, revenue and tax credited by what the
 * invoice said, and receivable back to zero.
 *
 * **Two periods, not one.** The invoice is dated ninety days ago and the payment today, so the
 * lock table has two rows -- which is what makes "a month that is not listed has never been
 * opened" a statement about this tenant rather than a sentence on an empty page.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the finance board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/finance");
  });

  test("lists the periods that exist and says each takes a posting", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Finance", level: 1 })).toBeVisible();
    const lock = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "The period lock" }) });
    const rows = lock.getByRole("row");
    // Two months: the back-dated invoice opened one and the payment opened another.
    expect(await rows.count()).toBeGreaterThanOrEqual(3); // header plus two periods
    await expect(lock).toContainText("open");
    await expect(lock).toContainText("Yes");
  });

  test("names the period somebody is in the middle of closing", async ({ page }) => {
    // **The state that stops the till, rendered as the thing it is.** `closing` admits the
    // close's own entries and no trade at all, so an accountant who began a close has
    // deliberately stopped that entity's postings -- and nothing in the product said so
    // before this board. Without a fixture that reaches the state, the banner, the "No" cell
    // and the caption are three features nothing proves.
    const lock = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "The period lock" }) });
    await expect(lock.getByRole("status")).toContainText("Needs somebody");
    const closing = lock.getByRole("row").filter({ hasText: "closing" });
    await expect(closing).toContainText("No");
    await expect(closing).toContainText("Takes the close's own entries and no trade");
    // And the current month is still open, so the board shows both states rather than one.
    //
    // **An exact cell, not a word boundary.** `/\bopen\b/` matched nothing: the row's text
    // is `2026-11…2026-11-30openYes`, and `\b` needs a word character beside a non-word one,
    // so there is no boundary between `0` and `o`. Matching the status cell exactly is the
    // form that names a row.
    //
    // **Every open row, not "the" open row.** A tenant has as many period rows as it has
    // posted months, and the fixture now back-dates an overdue invoice into an earlier one --
    // so naming a single open period made this assertion depend on how much the fixture
    // happened to seed. What holds whatever it seeds is the invariant: an open period takes
    // a posting, and that is what `admits_trade` is derived on the server for.
    const open = lock.getByRole("row").filter({ has: page.getByText("open", { exact: true }) });
    expect(await open.count()).toBeGreaterThan(0);
    for (const row of await open.all()) await expect(row).toContainText("Yes");
  });

  test("says a month that is not listed has never been opened", async ({ page }) => {
    // **The distinction the whole block rests on.** The lock is enforced per period row, so
    // an absent month is not an open one -- and a board that listed twelve months would be
    // inventing eleven rows the database does not have.
    await expect(page.getByText(/has never been opened, which is not the same/)).toBeVisible();
  });

  test("names the legal entity the trial balance belongs to", async ({ page }) => {
    // The block's own sentence says a balance is per legal entity, and the first version
    // rendered only the currency -- the defect the sentence warns about, on the page that
    // warns about it.
    const balance = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Trial balance" }) });
    await expect(balance).toContainText("Veyro Sites Ltd");
    await expect(balance).toContainText("JOD");
  });

  test("shows the ledger balancing, with totals that match", async ({ page }) => {
    const balance = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Trial balance" }) });
    await expect(balance).toContainText("The ledger balances");
    // The figures an accountant can check by hand: the card paid the gross, which sits in
    // provider_clearing; revenue and tax carry what the invoice said.
    // **The two totals agree, which is what "balances" means** -- rather than one figure
    // that moves every time the fixture seeds another document. The chart carries an unpaid
    // invoice as well now, so a hard-coded total was asserting the fixture rather than the
    // ledger.
    const totals = balance.getByRole("row").filter({ hasText: "Total" });
    const cells = (await totals.locator("td, th").allInnerTexts())
      .map((text) => text.trim())
      .filter((text) => /JOD/.test(text));
    expect(cells.length, "a trial balance has a debit total and a credit total").toBe(2);
    expect(cells[0]).toBe(cells[1]);
    // **An exact cell, not a substring.** Playwright's `hasText` is a case-insensitive
    // substring, so `"REV"` matches CONTRA (whose kind is `contra_revenue`) and REV-OLD as
    // well -- and `.first()` then asserted against whichever the chart's ordering put first.
    // Matching the account code cell exactly is the only form that names one row.
    // **Revenue exceeds clearing, and that gap is the assertion.** Revenue is earned when a
    // document is issued; `provider_clearing` moves only when one is paid. The fixture
    // issues more than it collects -- an overdue invoice in recovery and a part-paid one --
    // so the two cells disagree, which is exactly the confusion MOD-017 keeps apart:
    // "membership state, billing state and access state are related but never conflated".
    //
    // **Stated as a relationship rather than three amounts**, which is this test's own
    // lesson applied one block further down: the totals above were un-pinned for being "one
    // figure that moves every time the fixture seeds another document", and these three were
    // left pinned and duly broke the next time it did. The exact postings are proved against
    // a real database in `backend/tests/test_ledger_api.py`.
    const figure = async (code: string) => {
      const row = balance.getByRole("row").filter({ has: page.getByText(code, { exact: true }) });
      const cells = (await row.locator("td").allInnerTexts())
        .map((text) => text.trim())
        .filter((text) => /JOD/.test(text))
        .map((text) => Number(text.replace(/[^0-9.]/g, "")));
      return cells;
    };
    // An exact cell, not a substring: Playwright's `hasText` is a case-insensitive substring,
    // so "REV" matches CONTRA (kind `contra_revenue`) and REV-OLD as well.
    // A trial balance row is a debit cell and a credit cell; a row missing one has not
    // rendered, which is a failure rather than a value to compare against.
    const rowCells = async (code: string) => {
      const found = await figure(code);
      expect(found.length, `${code} has a debit and a credit cell`).toBe(2);
      return { debit: found[0] as number, credit: found[1] as number };
    };
    const clearing = await rowCells("CLEARING");
    const revenue = await rowCells("REV");
    const tax = await rowCells("TAX");

    expect(clearing.debit, "a card payment lands in clearing").toBeGreaterThan(0);
    // Nothing has relieved it: there is no settlement import in this build, so the payout
    // line that would move it to the bank has never been written.
    expect(clearing.credit, "no settlement has moved it to the bank").toBe(0);
    expect(revenue.credit, "revenue is earned at issue, so it outruns what was collected")
      .toBeGreaterThan(clearing.debit);
    expect(tax.credit, "tax is credited on every issued document").toBeGreaterThan(0);
  });

  test("marks a retired account rather than letting it read as live", async ({ page }) => {
    // A retired account is still on the trial balance -- it has to be, because a retired
    // account with a balance is exactly the row somebody needs to notice -- so the page has
    // to say which it is. The first version dropped the status and showed it as ordinary.
    const row = page.getByRole("row").filter({ hasText: "REV-OLD" });
    await expect(row).toContainText("retired");
  });

  test("says the two totals are equal by construction", async ({ page }) => {
    // Not a reassurance: it is why a difference means missing rows rather than rounding.
    await expect(page.getByText(/equal by construction/)).toBeVisible();
  });

  test("says nothing is waiting rather than showing an empty case list", async ({ page }) => {
    const cases = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Unanswered questions" }) });
    await expect(cases).toContainText("Nothing is waiting on anybody");
  });

  test("says revenue recognition is driven by nobody in this build", async ({ page }) => {
    // The gap changes the product -- revenue sits unrecognised until a person acts -- so the
    // board states it rather than rendering an empty list that reads as "all caught up".
    await expect(page.getByText(/until a person acts/)).toBeVisible();
  });

  test("has no journal on it and offers no way to list one", async ({ page }) => {
    // `finance.ledger.read` returns an invoice's figures and the payer out of a journal read,
    // which is safe only while journal ids cannot be enumerated. The page says so, and this
    // asserts the page has no link that would start enumerating them.
    await expect(page.getByText(/no way to list one/)).toBeVisible();
    await expect(page.locator('a[href*="/ledger/journals"]')).toHaveCount(0);
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read the ledger", () => {
  test("gets no Finance entry in the navigation", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Finance" })).toHaveCount(0);
  });

  test("is refused the board rather than shown an empty ledger", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/finance");
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    // And no figure reaches the refusal.
    await expect(page.getByText("JOD 52.20")).toHaveCount(0);
  });
});
