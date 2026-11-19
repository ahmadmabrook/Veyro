import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn } from "./sign-in";

/**
 * Language, direction, theme and accessibility -- on every combination, because the defects
 * found here were all in one combination and invisible in the others.
 *
 * The dark theme shipped with seven semantic tokens unmapped: fields rendered near-white on a
 * near-black page, the primary button stayed ink.600 against it, and the focus ring -- which
 * guardrail G4 makes system-owned precisely so "a tenant cannot ship an unnavigable product" --
 * was dark navy on near-black. Light mode was perfect throughout.
 */

const creds = fixture();

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("presentation", () => {
  test("Arabic sets lang and dir on the document, and English sets them back", async ({
    page,
  }) => {
    await page.goto("/login");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");

    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "تسجيل الدخول" })).toBeVisible();

    await page.getByRole("button", { name: "English" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  });

  test("the language in force is announced rather than merely highlighted", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "English" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    await expect(page.getByRole("button", { name: "العربية" })).not.toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  test("the layout mirrors in Arabic without a direction-specific rule", async ({ page }) => {
    await signIn(page);
    const before = await page.getByRole("heading", { name: "Veyro Admin" }).boundingBox();

    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const after = await page.getByRole("heading", { name: "إدارة فيرو" }).boundingBox();

    expect(before, "the English heading must be measurable").toBeTruthy();
    expect(after, "the Arabic heading must be measurable").toBeTruthy();
    // The heading starts at the inline-start edge, so mirroring moves it from the left of the
    // viewport to the right. Nothing in the source names `left` or `right`; this is what
    // `text-align: start` and the logical properties buy.
    expect(after!.x).toBeGreaterThan(before!.x);
  });

  test("the dark theme remaps the field, the accent and the focus ring", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    const tokens = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      return {
        canvas: root.getPropertyValue("--color-surface-canvas").trim(),
        input: root.getPropertyValue("--color-surface-input").trim(),
        action: root.getPropertyValue("--color-action-primary").trim(),
        focus: root.getPropertyValue("--color-border-focus").trim(),
        error: root.getPropertyValue("--color-border-error").trim(),
      };
    });
    // The source's own dark rule: "Accent lightens, text on it darkens: ink.600 becomes
    // #7ea6e8". A dark theme still showing #1b4079 is a theme that did not apply.
    expect(tokens.action).toBe("#7ea6e8");
    expect(tokens.focus).toBe("#7ea6e8");
    expect(tokens.input).toBe("#141311");
    expect(tokens.error).toBe("#e0836a");
    expect(tokens.canvas).toBe("#1a1917");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`the focus ring is visible on a field in the ${theme} theme`, async ({ page }) => {
      // No sign-in: the theme is a cookie the layout reads, and `/login` is the page with a
      // field on it. An earlier version signed in, switched theme, then navigated back to
      // `/login` -- which redirects a signed-in caller -- and timed out chasing itself.
      await page.goto("/login");
      await page.evaluate((value) => {
        document.cookie = `veyro_theme=${value}; path=/`;
      }, theme);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

      const field = page.getByLabel("Email or phone");
      await field.focus();
      const ring = await field.evaluate((element) => {
        const style = getComputedStyle(element);
        return { color: style.outlineColor, style: style.outlineStyle, width: style.outlineWidth };
      });
      // Guardrail G4: the focus ring is system-owned so "a tenant cannot ship an unnavigable
      // product". A ring that resolves to the light accent on a dark field is one a keyboard
      // user cannot see, which is the same failure with the rule still formally satisfied.
      expect(ring.style, `${theme} focus ring style`).not.toBe("none");
      expect(parseFloat(ring.width), `${theme} focus ring width`).toBeGreaterThanOrEqual(2);
      expect(ring.color, `${theme} focus ring colour`).toBe(
        theme === "dark" ? "rgb(126, 166, 232)" : "rgb(27, 64, 121)",
      );
    });
  }

  test("the first tab stop is the skip link", async ({ page }) => {
    await page.goto("/login");
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.textContent ?? "");
    expect(focused).toContain("Skip to content");
  });

  for (const theme of ["light", "dark"] as const) {
    for (const locale of ["en", "ar"] as const) {
      test(`no accessibility violations: sign-in, ${locale}, ${theme}`, async ({ page }) => {
        await page.goto("/login");
        if (locale === "ar") await page.getByRole("button", { name: "العربية" }).click();
        await page.evaluate((value) => {
          document.cookie = `veyro_theme=${value}; path=/`;
        }, theme);
        await page.reload();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

        // Submit once so the error state is on screen as well: a contrast failure on a
        // validation message is one nobody sees until somebody makes a mistake.
        await page.getByRole("button", { name: /Sign in|تسجيل الدخول/ }).click();
        await expect(page.locator("[aria-invalid='true']").first()).toBeVisible();

        const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
        expect(
          results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
          JSON.stringify(results.violations, null, 1).slice(0, 2000),
        ).toEqual([]);
      });

      test(`no accessibility violations: admin, ${locale}, ${theme}`, async ({ page }) => {
        await signIn(page);
        if (locale === "ar") await page.getByRole("button", { name: "العربية" }).click();
        await page.evaluate((value) => {
          document.cookie = `veyro_theme=${value}; path=/`;
        }, theme);
        await page.reload();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

        const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
        expect(
          results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
          JSON.stringify(results.violations, null, 1).slice(0, 2000),
        ).toEqual([]);
      });
    }
  }

  test("the sign-in form is usable at phone width with no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/login");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "the page must not scroll sideways on a phone").toBeLessThanOrEqual(0);

    // Touch density's minimum target is 44px, and the sign-in button is the one control a
    // member has to hit before anything else works.
    const button = await page.getByRole("button", { name: "Sign in" }).boundingBox();
    expect(button!.height).toBeGreaterThanOrEqual(44);
  });
});
