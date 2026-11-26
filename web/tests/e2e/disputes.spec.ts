import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession } from "./sign-in";

/**
 * ADM-PAY-10 · DISPUTE · ACCOUNTANT ONLY.
 *
 * > The check-in record is the strongest evidence a gym has and Veyro assembles it
 * > automatically. Accepting the loss is a real option and is recorded as a decision, not a
 * > lapse.
 *
 * **"Veyro assembles it automatically" is a claim**, and these assert it is true: each
 * evidence line is a real read through its own gate rather than a tick drawn beside a
 * sentence. The fixture seeds two disputes on purpose — one with ten days left and one with
 * four — because the deadline box has two states and the canvas draws only the urgent one.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the dispute board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/payments/disputes");
  });

  test("is readable without a step-up, which is why it exists", async ({ page }) => {
    // **MOD-018's rule, applied.** "A read behind a step-up is a read nobody does until the
    // month-end panic" — and a chargeback is worse than a wrong balance because the window
    // expires. The fixture's browser session is level 1, so reaching the board at all is
    // the assertion: behind `finance.dispute.manage` this page would be a refusal.
    await expect(
      page.getByRole("heading", { name: /what the gym can prove/, level: 1 }),
    ).toBeVisible();
    // **The board itself, not merely the heading.** A refusal renders the heading too, so
    // what proves the read went through is a dispute on the page. And the assertion is
    // not "no mention of a stronger sign-in": the *name* is masked on a level-1 session
    // and its marker says exactly that, which is a different sentence from the page being
    // refused — the first version of this test could not tell them apart.
    await expect(page.locator(".ds-evidence").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Disputed/ }).first()).toBeVisible();
  });

  test("leads with what is still at stake, not with every dispute ever recorded", async ({
    page,
  }) => {
    const header = page.locator(".ds-page-figures");
    await expect(header).toContainText("disputes");
    await expect(header).toContainText("still undecided");
    await expect(header).toContainText("JOD");
  });

  test("puts the deadline and what missing it costs together", async ({ page }) => {
    // The canvas's red box is two sentences and the second is the one it is for: a date
    // with no consequence beside it is a date somebody files.
    const urgent = page.getByText(/Missing the deadline forfeits the amount/).first();
    await expect(urgent).toBeVisible();
    await expect(urgent).toContainText("Evidence due");
    await expect(urgent).toContainText("days");
  });

  test("tells an urgent deadline from one that can wait", async ({ page }) => {
    // Two disputes, four days and ten. `critical` is the canvas's error-ink box and `info`
    // is the one it does not draw — and with a single dispute seeded only one of them
    // would ever render, which is the vacuity this suite keeps finding.
    const banners = page.getByRole("status").or(page.getByRole("alert"));
    const tones = await banners.evaluateAll(
      (nodes) => nodes.map((n) => n.className),
    );
    expect(tones.join(" ")).toMatch(/critical/);
    expect(tones.join(" ")).toMatch(/info/);
  });

  test("assembles the three pieces of evidence it claims to", async ({ page }) => {
    // **The screen's whole claim.** Each is a real read: the check-ins from MOD-022's
    // window, the agreement's signature from MOD-017, the document from the dispute read.
    const list = page.locator(".ds-evidence").first();
    await expect(list.getByText(/Check-ins in the billed period/)).toBeVisible();
    await expect(list.getByText(/Signed membership contract/)).toBeVisible();
    await expect(list.getByText(/Invoice and its fiscal acknowledgement/)).toBeVisible();
    // The fixture walks the member through the door fourteen times, all inside the
    // billed period, so this is a count rather than a tick.
    const checkins = list.locator("li").filter({ hasText: "Check-ins" });
    await expect(checkins).toHaveAttribute("data-state", "have");
    await expect(checkins.locator(".data")).toContainText(/\d+/);
  });

  test("leaves the written statement to the operator, as the canvas does", async ({
    page,
  }) => {
    const statement = page.locator(".ds-evidence").first()
      .locator("li").filter({ hasText: "Written statement" });
    await expect(statement).toHaveAttribute("data-state", "missing");
    await expect(statement).toContainText("Yours to write");
  });

  test("the mark is never the only signal", async ({ page }) => {
    // §15: nothing carries meaning by colour or by a glyph alone. There are three states
    // here rather than the canvas's two, and "you may not see whether this is held" is a
    // different fact from "we do not have it" — so each row says which in text.
    const row = page.locator(".ds-evidence li").first();
    await expect(row.locator(".ds-visually-hidden")).toHaveText(/held|not held|may not/);
  });

  test("draws no submit and no accept button", async ({ page }) => {
    // Both are stepped-up financial writes with no form here, and "accept the loss" is the
    // one action nobody can undo.
    await expect(page.getByRole("button", { name: /submit/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /accept/i })).toHaveCount(0);
    const notYet = page.locator("section").filter({ hasText: "What this screen does not do yet" });
    await expect(notYet).toContainText("Nothing in this build sends anything to a scheme");
    // The sentence that explained *why* this gap exists has gone with the section that
    // held it: the names above are what a reader needs, and the reasoning is in
    // `contracts/ui/design-compliance.md`.
  });

  test("the payments ledger sends a chargeback here", async ({ page }) => {
    await page.goto("/payments");
    const row = page.getByRole("row").filter({ hasText: "chargeback" }).first();
    const link = row.getByRole("link", { name: /Respond before the deadline/ });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/payments\/disputes$/);
  });

  test("the whole screen reads in Arabic", async ({ page }) => {
    // The status, the kind, the scheme's reason and the three evidence states are all
    // vocabularies the backend stores, and a stored value rendered as a label is Latin
    // letters in the middle of the line. `MESSAGE_KEYS` is blind to every one of them.
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForFunction(() => document.documentElement.dir === "rtl");
    await page.goto("/payments/disputes");
    const main = page.locator("main");
    await expect(main).toContainText("متنازع عليها");
    await expect(main).toContainText("يزعمون أن الخدمة لم تُقدَّم");
    await expect(main).toContainText("مرّات الدخول في الفترة المفوترة");
    for (const english of [
      "Disputed", "claiming the service was not received",
      "Check-ins in the billed period", "Written statement",
    ]) {
      await expect(main).not.toContainText(english);
    }
  });

  test("offers the step-up that would name the members", async ({ page }) => {
    // The canvas names the member in its opening sentence, and a dispute you cannot
    // attach to a person is one nobody can act on. The members list learned this from an
    // independent tester who clicked the marker looking for a way through.
    await expect(page.getByText("Withheld").first()).toBeVisible();
    const raise = page.getByRole("link", { name: /Raise this session/ });
    await expect(raise).toBeVisible();
    await expect(raise).toHaveAttribute(
      "href", /action=member\.identity\.read.*payments%2Fdisputes/);
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});
