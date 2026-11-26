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
 * **The fixture publishes `latn`, declared on purpose**, which is the sharper of the two
 * states: the same value as the fallback and a different fact, so the screen's "nobody has set
 * this" branch is absent here. It is not `arab` because the hour a figure anywhere else in the
 * product followed the setting -- which is now every quantity on every screen -- an `arab`
 * tenant would turn several hundred assertions into Arabic-Indic digits no maintainer could
 * read. So the Arabic-Indic half is proven where it is decided: the canvas's exact sentence,
 * character for character, in `tests/component/localization.test.ts`, and the browser mutation
 * `localization-the-setting-reaches-a-page`, which flips the reader and is caught by the pages
 * that then change.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the localization screen", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/localization");
  });

  test("renders the preview in the tenant's own conventions", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Localization", level: 1 })).toBeVisible();
    // **`آب`, the Levantine month, under this tenant's Latin digits.** The month name comes
    // from the region and the digits from the setting, which is exactly what makes them two
    // decisions: `21 آب` is the pair that proves the tag did not decide the numbering.
    const preview = page.locator(".ds-preview-line");
    await expect(preview).toContainText("21 آب");
    await expect(preview).not.toContainText("أغسطس");
    await expect(preview).toContainText("JOD 55.00");
    await expect(preview).toHaveAttribute("dir", "rtl");
  });

  test("marks which numeral system is in force, in words as well as in fill", async ({
    page,
  }) => {
    // **Colour is never the only signal.** The filled chip is the sighted reading; the word
    // is what a screen reader gets, and it is on the one chip that carries it.
    const numerals = page.locator(".ds-state-group").filter({ hasText: "Numerals" });
    // Both samples are drawn; one is filled. The unoffered one is what makes the group read
    // as a choice of two rather than as a list of one.
    await expect(numerals.getByText("٠١٢٣")).toBeVisible();
    await expect(numerals.locator('[data-on="true"]')).toHaveCount(1);
    await expect(numerals.locator('[data-on="true"]')).toContainText("0123");
    await expect(numerals.locator('[data-on="true"]')).toContainText("in use");
    // The figures line names the system in words, because the chips are only samples.
    await expect(page.locator(".ds-page-figures")).toContainText("Latin digits");
  });

  test("shapes its own count by the setting", async ({ page }) => {
    // **The figure follows the chip that is filled**, which on this tenant means Latin digits
    // and no visible difference -- so what is asserted here is that the count is rendered at
    // all and that it is not Arabic-Indic while the setting says Latin. The direction that
    // moves is the mutation's: flipping the reader to `arab` changes this and every other
    // count in the product, which is the property "never mixed" is about.
    await expect(page.locator(".ds-page-figures")).toContainText("2 languages offered");
    await expect(page.locator(".ds-page-figures")).not.toContainText("٢");
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
    const notYet = page.getByRole("heading", { name: "What this screen does not do yet" });
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
