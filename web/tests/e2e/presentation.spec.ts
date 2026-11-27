import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { join } from "node:path";

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
    // **Read from the design source, never copied.** This pinned five hexes from the
    // retired palette -- `#7ea6e8` for the action and the focus ring, `#1a1917` for the
    // canvas -- so it failed for the design having been replaced rather than for the theme
    // having failed to apply, which is what it is for. The property is that dark *remaps*
    // every one of these rather than inheriting it, and the values come from the file that
    // decides them.
    for (const [name, value] of Object.entries(tokens)) {
      expect(value, `${name} has no dark value`).toMatch(/^#[0-9a-f]{3,8}$/i);
    }
    // Dark remaps rather than inheriting: every one differs from its light value.
    // **Read the root in each theme, not a nested probe.** The tokens are declared on
    // `:root[data-theme]`, so a `<div data-theme="light">` inside a dark document inherits
    // the dark values and the comparison reports every token as unchanged.
    await page.getByRole("button", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    const light = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const read = (n: string) => root.getPropertyValue(n).trim();
      return {
        canvas: read("--color-surface-canvas"), input: read("--color-surface-input"),
        action: read("--color-action-primary"), focus: read("--color-border-focus"),
        error: read("--color-border-error"),
      };
    });
    for (const key of ["canvas", "input", "action", "focus", "error"] as const) {
      expect(tokens[key], `${key} is the same in both themes`).not.toBe(light[key]);
    }
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
        // The ground the ring is drawn against, walked up until something paints.
        let ground = "rgba(0, 0, 0, 0)";
        for (let node: Element | null = box; node; node = node.parentElement) {
          const bg = getComputedStyle(node).backgroundColor;
          if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) { ground = bg; break; }
        }
        return {
          color: style.outlineColor, style: style.outlineStyle,
          width: style.outlineWidth, ground,
        };
      });
      // Guardrail G4: the focus ring is system-owned so "a tenant cannot ship an unnavigable
      // product". A ring that resolves to the light accent on a dark field is one a keyboard
      // user cannot see, which is the same failure with the rule still formally satisfied.
      expect(ring.style, `${theme} focus ring style`).not.toBe("none");
      expect(parseFloat(ring.width), `${theme} focus ring width`).toBeGreaterThanOrEqual(2);
      // **Measured against the field, not compared to a hex.** This pinned the retired
      // palette's blue in both themes, so it failed for the palette having been replaced
      // rather than for a keyboard user being unable to see the ring -- which is what the
      // comment above says the test is for. WCAG 2.1 asks 3:1 of a focus indicator against
      // what it sits on, and that number holds whatever colour the brand turns out to be.
      const luminance = (colour: string) => {
        const [r, g, b] = colour.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number)
          .map((channel) => {
            const v = channel / 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          });
        return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
      };
      const [brighter, darker] = [luminance(ring.color), luminance(ring.ground)]
        .sort((a, b) => b - a);
      const contrast = (brighter! + 0.05) / (darker! + 0.05);
      expect(contrast, `${theme} focus ring against ${ring.ground}`)
        .toBeGreaterThanOrEqual(3);
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
  test("the declared faces are actually loaded, not merely named", async ({ page }) => {
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
    // **The faces are read from `layout.tsx` rather than named here.** This pinned "IBM
    // Plex Sans" and "IBM Plex Mono", which the redesign replaced -- so it failed for the
    // typeface having changed rather than for a face not loading, which is what it is for.
    // The three the app imports are what has to be loaded, whichever three those are.
    const layout = readFileSync(join(process.cwd(), "src/app/layout.tsx"), "utf8");
    const imported = [...layout.matchAll(/import \{([^}]+)\} from "next\/font\/google"/g)]
      .flatMap((m) => m[1]!.split(",").map((n) => n.trim()))
      .filter(Boolean);
    expect(imported.length, "layout.tsx imports no font").toBeGreaterThan(0);
    // **A face loads when a glyph needs it, so an English page loads the Latin ones.** The
    // Arabic face is imported and never requested here, and asserting every import loads on
    // every page would be asserting a browser does not lazy-load. What has to hold is that
    // the faces this page *uses* are real: more than one imported face is loaded, and the
    // ones the body and a figure resolve to are among them.
    const loadedHere = imported.filter(
      (face) => [...families].some((f) => f.toLowerCase().includes(face.toLowerCase())),
    );
    expect(
      loadedHere.length,
      `no imported face loaded on an English page; loaded: ${[...families]}`,
    ).toBeGreaterThanOrEqual(2);
  });

  test("the body renders in the loaded face rather than falling back", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const family = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
    // `next/font` self-hosts under a generated name, so the assertion is that the first
    // family in the stack is the variable this app sets rather than a system fallback.
    expect(family).not.toMatch(/^system-ui/);
    // **The first family only, not the whole stack.** `document.fonts.check` over the
    // declared list also asks whether the browser has `system-ui` and `sans-serif`, which
    // is a question about the machine rather than about this app -- and a bare Linux CI
    // runner answered no, so this failed in CI and passed on every developer's laptop. What
    // the test is for is that the face the body *uses* is loaded rather than merely named,
    // and that is the first family: the self-hosted Plex `next/font` generated.
    const usable = await page.evaluate(() => {
      const first = getComputedStyle(document.body).fontFamily.split(",")[0]!.trim();
      return {
        first,
        loaded: document.fonts.check(
          `${getComputedStyle(document.body).fontSize} ${first}`),
      };
    });
    // The self-hosted name is generated, so the assertion is that the first family is a
    // real face this app ships rather than a system fallback -- not which face it is.
    expect(usable.first, "the body's first family is the app's own variable")
      .not.toMatch(/^(system-ui|sans-serif|serif|-apple-system)$/);
    expect(usable.loaded, `the body's own face must be loaded: ${usable.first}`).toBe(true);
  });

  test("a figure is set in the figure face and aligns as a column", async ({ page }) => {
    // **There is no mono face any more, and that is the design rather than a regression.**
    // This asserted `/Plex_Mono|mono/i` on a money figure, from a scale whose `type.data`
    // read "Mono tabular" -- and the replacement sets every quantity in Archivo, which is
    // the signature move: the numeral on the back of a shirt. `system-check.mjs` refuses a
    // monospace family outright, so a test demanding one is asking for the thing the design
    // system now bans.
    //
    // What the mono was *for* survives and is what this asserts: a column of figures has to
    // align, which is `tabular-nums` rather than a particular face.
    await useOwnerSession(page);
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    const figure = await page.locator(".ds-metric-value").first().evaluate((el) => {
      const style = getComputedStyle(el);
      return { family: style.fontFamily, numeric: style.fontVariantNumeric };
    });
    expect(figure.family, "a figure falls back to a system face").not.toMatch(/^system-ui/);
    expect(figure.family, "a figure is not set in a monospace face").not.toMatch(/mono/i);
    expect(figure.numeric, "a column of figures must align").toMatch(/tabular-nums/);
  });
});
