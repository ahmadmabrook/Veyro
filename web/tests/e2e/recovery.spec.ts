import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession } from "./sign-in";

/**
 * ADM-PAY-05 · RECOVERY · OPENED FROM THE COMMAND CENTER.
 *
 * The canvas's argument is its closing note — "the six are one decision, not six … the batch
 * action is the default because the recommended treatment is identical for all six" — and
 * **that is a claim, not a caption.** It is true only once something has established that the
 * treatments agree, which is the read this screen exists on top of.
 *
 * So the assertions here are about **what the rows say** rather than about which headings
 * are present. This suite has already paid for the difference once: "the timezone is named
 * on the page" passed while every time on the schedule board was three hours wrong.
 *
 * The fixture seeds **both halves of the distinction** — a debt with no membership behind it
 * and one whose invoice cites the member's own membership, each failing on an expired card.
 * With one of them the banner renders one branch and the other passes vacuously, which is
 * the surface-branch vacuity this repository has now shipped four times.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the recovery workspace", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/payments/recovery");
  });

  test("the Command Center's money item opens this, not the trial balance", async ({
    page,
  }) => {
    // `veyro-screen.js` wires ADM-CC-01's MONEY attention item to ADM-PAY-05 by id and
    // labels the button "Open the recovery workspace". It pointed at `/finance`, which is
    // MOD-018's chart and period lock: an accountant closes a month there and nobody
    // chases a failed card.
    await page.goto("/");
    const open = page.getByRole("link", { name: /Open the recovery workspace/ });
    await expect(open).toBeVisible();
    await open.click();
    await expect(page).toHaveURL(/\/payments\/recovery$/);
  });

  test("the header's two clauses are derived, and agree with the rows", async ({ page }) => {
    // "All retries exhausted · no access blocked" is the canvas's own second line. Both are
    // read off the set on the server — a caller able to pass either in could head a
    // workspace with a sentence its own rows contradict. Every seeded case failed on an
    // expired card, which `may_retry` never retries, so the clause is the true one.
    const header = page.locator(".ds-page-figures");
    await expect(header).toContainText("all retries exhausted");
    await expect(header).toContainText("no access blocked");
    await expect(header).toContainText("failed payments");
    // And the figure beside them is money, with its currency, not a bare number.
    await expect(header).toContainText("JOD");
  });

  test("says these are NOT one decision, because they are not", async ({ page }) => {
    // The fixture's two cases want different things, so the batch argument does not hold
    // and the page says which rows differ instead of implying one button would do.
    const banner = page.getByText(/These are not one decision/);
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("1 want the member asked");
    await expect(banner).toContainText("1 want somebody to look first");
  });

  test("sorts the two cases, and says why each wants what it wants", async ({ page }) => {
    // **The sort is the screen.** A row saying only "failed" would be the dunning listing;
    // what makes this a workspace is that the same failure code on two debts comes back as
    // two different treatments, each with the reason underneath.
    const ask = page.getByRole("row").filter({ hasText: "Ask the member" });
    await expect(ask).toHaveCount(1);
    await expect(ask).toContainText("Nothing to retry until they act");

    const review = page.getByRole("row").filter({ hasText: "Review first" });
    await expect(review).toHaveCount(1);
    // The membership is the one the *invoice* cites, never the payer's latest — this payer
    // has a live membership and this debt is personal training, which cites none.
    await expect(review).toContainText("This debt cites no membership");
  });

  test("the failure is a word, and the card detail the canvas draws is absent", async ({
    page,
  }) => {
    // `card_expired` rendered raw is a stored value where a word belongs, which in Arabic is
    // Latin letters mid-sentence. And "Visa ···4417" does not exist anywhere in this build:
    // paragraph 1597 keeps card data out of Veyro, so the instrument's kind is all there is.
    const row = page.getByRole("row").filter({ hasText: "Ask the member" });
    await expect(row).toContainText("Card expired");
    await expect(row).not.toContainText("card_expired");
    // **The instrument is its own cell, asserted exactly.** `toContainText("Card")` on the
    // row would pass on "Card expired" alone, which is the assertion passing for a reason
    // that has nothing to do with the column under test.
    await expect(row.getByRole("cell", { name: "Card", exact: true })).toBeVisible();
    await expect(page.locator("main")).not.toContainText("4417");
    await expect(page.locator("main")).not.toContainText("Visa");
  });

  test("offers the step-up that would name the members", async ({ page }) => {
    // Every row is withheld on a level-1 session, and this screen's whole left column is
    // who to contact — so a workspace of "Withheld" with no remedy is unusable. The members
    // list learned this from an independent tester who clicked the marker looking for a way
    // through; here it matters more.
    await expect(page.getByText("Withheld").first()).toBeVisible();
    const raise = page.getByRole("link", { name: /Raise this session/ });
    await expect(raise).toBeVisible();
    await expect(raise).toHaveAttribute(
      "href", /action=member\.identity\.read.*payments%2Frecovery/,
    );
  });

  test("previews the real template, with its placeholders unfilled", async ({ page }) => {
    // **Unrendered on purpose.** `templates.render` requires a value for every variable the
    // template declares, and this build has no payment link to supply — so a filled example
    // would be a message that does not exist. The placeholders are exactly what say which
    // values a sender does not have.
    const preview = page.locator("section").filter({ hasText: "The message they receive" });
    await expect(preview).toContainText("{{ link }}");
    await expect(preview).toContainText("didn't go through");
    // The template the *stage* chose, not one the reader picked.
    await expect(preview.locator(".data").filter({ hasText: "payment_failed" }).first())
      .toBeVisible();
    // And the category, which is the control the note below rests on.
    await expect(preview.locator(".data").filter({ hasText: "transactional" }).first())
      .toBeVisible();
    await expect(preview).toContainText("Values a sender supplies");
  });

  test("states the consent rule as one paragraph, not eight", async ({ page }) => {
    // **`Prose` is a run of inline spans and a `.page-section` is a column flex container**,
    // so used bare every emphasised and backticked run became its own flex item on its own
    // line — eight blocks where one paragraph belonged. Found by looking at the page;
    // `ProseNote` is the block form.
    const note = page.locator("p.ds-note").filter({
      hasText: /Sent in the member\u2019s chosen language/,
    });
    await expect(note).toContainText("what makes this a service message");
    await expect(note).toContainText("ntf_preferences");
    await expect(note).toContainText("still receives this");

    // **The geometric assertion, because the text one passes either way.** In the broken
    // rendering every span was its own row, so no two shared a vertical position; in a
    // paragraph the runs flow and several sit on one line. A height threshold would be the
    // weaker check — it moves whenever the sentence does.
    const tops = await note.locator("span, strong").evaluateAll(
      (nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().top)),
    );
    expect(tops.length).toBeGreaterThan(4);
    expect(new Set(tops).size).toBeLessThan(tops.length);

    // The delimiters are rendered, never printed.
    await expect(note).not.toContainText("**");
    await expect(note).not.toContainText("`");
  });

  test("draws no send button and no row checkboxes", async ({ page }) => {
    // Nothing in this build sends, and a selection control for an action that does not
    // exist is worse than its absence.
    await expect(page.getByRole("button", { name: /send/i })).toHaveCount(0);
    await expect(page.getByRole("checkbox")).toHaveCount(0);
    const notYet = page.locator("section").filter({ hasText: "What this screen does not do yet" });
    await expect(notYet).toContainText("Nothing in this build sends");
    // The sentence that explained *why* this gap exists has gone with the section that
    // held it: the names above are what a reader needs, and the reasoning is in
    // `contracts/ui/design-compliance.md`.
  });

  test("the stored vocabularies read in Arabic, not in English", async ({ page }) => {
    // **Four of these shipped in one pass elsewhere in this app** — a lifecycle state, two
    // plan words, a credential kind — each a column's value rendered where a word belongs,
    // which in Arabic is Latin letters in the middle of the line. `MESSAGE_KEYS` is
    // structurally blind to every one of them, because it compares the two catalogues
    // against each other and cannot see a string that never became a key. The only thing
    // that finds it is reading the Arabic page.
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForFunction(() => document.documentElement.dir === "rtl");
    await page.goto("/payments/recovery");
    const main = page.locator("main");
    // The treatment, its reason, the failure code and the instrument.
    await expect(main).toContainText("راجعها أولاً");
    await expect(main).toContainText("خاطب العضو");
    await expect(main).toContainText("انتهت صلاحية البطاقة");
    // The instrument's own cell, exactly: "انتهت صلاحية البطاقة" contains "بطاقة", so a
    // substring assertion on the row would pass without the method column being translated
    // at all.
    await expect(
      page.getByRole("cell", { name: "بطاقة", exact: true }).first(),
    ).toBeVisible();
    for (const english of [
      "Review first", "Ask the member", "Card expired",
      "This debt cites no membership",
    ]) {
      await expect(main).not.toContainText(english);
    }
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});
