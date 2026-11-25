import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * ADM-SET-07, against a tenant that really has published both keys.
 *
 * **The assertions are about rendered values, not about labels.** The schedule board's own
 * lesson: 140 tests asserted that the timezone's *name* was on the page while every time on it
 * was three hours wrong. Here the four claims the canvas makes are all in one string, so the
 * sentence itself is what gets read off the page -- the Levantine month name, Arabic-Indic
 * digits on the date, Latin digits on the money, and the two not re-ordering each other.
 *
 * **The fixture publishes `arab`**, so this is the canvas's own preview rather than a
 * Latin-digit version of it. The defaulted state -- a tenant that has declared nothing -- is
 * the one state this fixture cannot also be, and is covered where it is decided.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the localization screen", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/localization");
  });

  test("renders the canvas's own preview sentence", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Localization", level: 1 })).toBeVisible();
    // The whole claim in one string. `٢١ آب` is the Levantine month under Arabic-Indic
    // digits; `JOD 55.00` is Latin beside it, which is the rule the panel above states.
    const preview = page.locator(".ds-preview-line");
    await expect(preview).toContainText("٢١ آب");
    await expect(preview).toContainText("JOD 55.00");
    // The money is not shaped: `٥٥` would mean the rule had been applied to it.
    await expect(preview).not.toContainText("٥٥");
    await expect(preview).toHaveAttribute("dir", "rtl");
  });

  test("marks which numeral system is in force, in words as well as in fill", async ({
    page,
  }) => {
    // **Colour is never the only signal.** The filled chip is the sighted reading; the word
    // is what a screen reader gets, and it is on the one chip that carries it.
    const numerals = page.locator(".ds-state-group").filter({ hasText: "Numerals" });
    await expect(numerals.getByText("٠١٢٣")).toBeVisible();
    await expect(numerals.locator('[data-on="true"]')).toHaveCount(1);
    await expect(numerals.locator('[data-on="true"]')).toContainText("in use");
    // The figures line names the system in words, because the chips are only samples.
    await expect(page.locator(".ds-page-figures")).toContainText("Arabic-Indic digits");
  });

  test("shapes its own count by the setting, in an English sentence", async ({ page }) => {
    // **This reads oddly and is the rule.** `٢ languages offered` is what "one rule per
    // tenant, never mixed and never decided per component" means for an English reader on an
    // `arab` tenant -- `conventions.mjs` says numbering is never derived from locale, and the
    // rule runs both ways. It is also the only figure on the screen that demonstrates the
    // setting reaching anything, which is why it is asserted rather than left to look like a
    // defect somebody will helpfully fix.
    await expect(page.locator(".ds-page-figures")).toContainText("٢");
    await expect(page.locator(".ds-page-figures")).toContainText("languages offered");
  });

  test("offers no control, because the canvas draws none", async ({ page }) => {
    // ADM-SET-06 beside it draws an action; this one draws no save, no button and no field.
    // A chip a reader can press would be a control this screen cannot honour.
    await expect(page.locator("main").getByRole("button")).toHaveCount(0);
    await expect(page.locator("main").getByRole("checkbox")).toHaveCount(0);
    await expect(page.locator("main").getByRole("radio")).toHaveCount(0);
  });

  test("says nothing about defaults, because this tenant chose both", async ({ page }) => {
    // The sharp direction: the sentence is about a tenant that has declared nothing, and
    // rendering it here would be telling an owner they had not set what they had just set.
    await expect(page.getByText(/Nobody has set this/)).toHaveCount(0);
  });

  test("names what it cannot do, with the reason for each", async ({ page }) => {
    const notYet = page.getByRole("heading", { name: "What this screen cannot do" });
    await expect(notYet).toBeVisible();
    // The three absences, each a different kind: a design decision, work, and a dependency.
    await expect(page.getByText(/Publishing a configuration value is a financial-class/))
      .toBeVisible();
    await expect(page.getByText(/Seventeen call sites still pass Latin digits/)).toBeVisible();
    await expect(page.getByText(/Python’s standard library carries no CLDR month names/))
      .toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("the localization screen, in Arabic", () => {
  test("renders its own sentences in Arabic and keeps the money Latin", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/localization");
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.getByRole("heading", { name: "التوطين", level: 1 })).toBeVisible();
    // **The one place a mixed script is correct**: the money rule names a figure that must
    // stay Latin, in an Arabic sentence, which is what the canvas draws.
    await expect(page.getByText(/JOD 41,280\.00/)).toBeVisible();
    // The rule itself, in Arabic rather than in the server's English.
    await expect(page.getByText(/أرقام عربية-هندية للأعداد والتواريخ/)).toBeVisible();
  });
});

test.describe("a reader who does not hold the permission", () => {
  test("is told it is a refusal rather than shown a silent fallback", async ({ page }) => {
    // ADR-0015 D2's fallback is for a page *rendering figures*, where a gate answer must not
    // put a notice on the screen. This is the screen whose subject is the setting, so a
    // refusal is a refusal -- and the rail does not offer it either.
    await useReaderSession(page);
    await page.goto("/localization");
    await expect(page.getByRole("heading", { name: "Localization", level: 1 })).toBeVisible();
    await expect(page.locator(".ds-preview-line")).toHaveCount(0);
    await expect(page.getByText("Not permitted")).toBeVisible();
    await expect(page.getByRole("navigation").getByRole("link", { name: "Localization" }))
      .toHaveCount(0);
  });
});
