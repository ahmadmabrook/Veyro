import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession } from "./sign-in";

/**
 * Language, direction, theme and accessibility -- on every combination, because the defects
 * found here were all in one combination and invisible in the others.
 *
 * The dark theme shipped with seven semantic tokens unmapped: fields rendered near-white on a
 * near-black page, the primary button stayed ink.600 against it, and the focus ring -- which
 * guardrail G4 makes system-owned precisely so "a tenant cannot ship an unnavigable product" --
 * was dark navy on near-black. Light mode was perfect throughout.
 */

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
    await useOwnerSession(page);
    // **The text run's box, not the heading element's.** The element is a block that spans
    // the content column in both directions, so its own `x` *decreases* in Arabic -- the rail
    // moves to the right and the column starts at the gutter. The old assertion passed only
    // because the old landing page put its heading in a flex row, where it was sized to its
    // content and genuinely moved; measuring the element was reading a layout accident as the
    // mirroring. A Range over the text node measures what a reader actually sees move.
    const runBox = () => page.getByRole("heading", { level: 1 }).evaluate((el) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      const { x, width } = range.getBoundingClientRect();
      return { x, width };
    });
    const before = await runBox();

    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const after = await runBox();

    expect(before.width, "the English heading must be measurable").toBeGreaterThan(0);
    expect(after.width, "the Arabic heading must be measurable").toBeGreaterThan(0);
    // The heading starts at the inline-start edge, so mirroring moves it from the left of the
    // viewport to the right. Nothing in the source names `left` or `right`; this is what
    // `text-align: start` and the logical properties buy.
    expect(after.x).toBeGreaterThan(before.x);
  });

  test("the dark theme remaps the field, the accent and the focus ring", async ({ page }) => {
    await useOwnerSession(page);
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
      // **The ring is on the control, not the input.** §23's shell holds a prefix, the
      // control and a suffix in one bounded box -- a currency prefix, a phone country code --
      // so a ring drawn on the `<input>` alone would exclude them and read as a ring around
      // part of the field. `:focus-within` puts it on the box the reader sees.
      const ring = await field.evaluate((element) => {
        const box = element.closest(".ds-field-control") ?? element;
        const style = getComputedStyle(box);
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
        await useOwnerSession(page);
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

test.describe("the typeface", () => {
  test("IBM Plex is actually loaded, not merely declared", async ({ page }) => {
    // **The defect this exists for.** `globals.css` named `"IBM Plex Sans"` from the first
    // commit and nothing ever loaded it, so every screen in this product rendered in the
    // system face while the stylesheet said otherwise -- and no assertion could see it,
    // because `getComputedStyle` reports the *declared* family whether or not the browser
    // found a face for it. The only thing that catches it is asking the font loader.
    await useOwnerSession(page);
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const loaded = await page.evaluate(() =>
      [...document.fonts].map((face) => ({ family: face.family, status: face.status })));
    const families = new Set(
      loaded.filter((f) => f.status === "loaded").map((f) => f.family));
    // The three faces the design's own preamble asks for.
    expect([...families].some((f) => /Plex Sans/i.test(f)), `loaded: ${[...families]}`)
      .toBe(true);
    expect([...families].some((f) => /Plex Mono/i.test(f)), `loaded: ${[...families]}`)
      .toBe(true);
  });

  test("the body renders in the loaded face rather than falling back", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
    // `next/font` self-hosts under a generated name, so the assertion is that the first
    // family in the stack is the variable this app sets rather than a system fallback.
    expect(family).not.toMatch(/^system-ui/);
    const usable = await page.evaluate(() =>
      document.fonts.check(`${getComputedStyle(document.body).fontSize} ${
        getComputedStyle(document.body).fontFamily}`));
    expect(usable, "the computed body font must resolve to a face the browser has").toBe(true);
  });

  test("a money figure and an id are set in the mono face", async ({ page }) => {
    // `type.data` is "Mono tabular. Money, counts, sets, reps, macros, IDs. The reason
    // columns align." A money figure in the proportional face is a column that does not.
    await useOwnerSession(page);
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const family = await page.locator(".ds-metric-value").first()
      .evaluate((el) => getComputedStyle(el).fontFamily);
    expect(family).toMatch(/Plex_Mono|Plex Mono|mono/i);
  });
});
