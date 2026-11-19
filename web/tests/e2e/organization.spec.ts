import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * MOD-004's hierarchy, and the navigation that leads to it.
 *
 * **The gated-navigation assertions use a second identity on purpose.** The fixture's owner
 * holds every permission in the catalogue, so signing in as the owner can only ever prove the
 * allowed half of a gate -- and a navigation that ignored the gate entirely would pass every
 * one of those assertions. The reader identity holds `access.zone.read` and not
 * `tenancy.organization.read`, which is the shape that distinguishes "filtered per item" from
 * "rendered unconditionally".
 */
test.describe("the organization surface", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/organization");
  });

  test("renders the tenant's own hierarchy, parent to child", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Organization", level: 1 })).toBeVisible();
    // The fixture's own names. A page that resolved a brand's organization by position
    // rather than by id would still show all three, so the nesting is what is asserted.
    const organization = page.getByRole("region").or(page.locator("section")).filter({
      hasText: "Veyro Sites Ltd",
    }).first();
    await expect(organization).toContainText("City");
    await expect(organization).toContainText("Downtown");
    await expect(organization).toContainText("Asia/Amman");
  });

  test("mirrors in Arabic and keeps the identifiers left-to-right", async ({ page }) => {
    // **Asserted in Arabic, because in English every element inherits `dir="ltr"` from the
    // document and the assertion is vacuous** -- the first version matched `<html>` itself.
    // An IANA zone and an ISO country code are identifiers rather than prose: ASCII, not
    // translated, and without `dir` the bidi algorithm moves the slash and reads the zone as
    // a different one.
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL("/organization");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByText("المؤسسة").first()).toBeVisible();
    await expect(page.getByText("Asia/Amman")).toHaveAttribute("dir", "ltr");
    await expect(page.getByText("JO", { exact: true })).toHaveAttribute("dir", "ltr");
  });

  test("says there is no legal entity rather than leaving a blank", async ({ page }) => {
    // **The emptiness is the fact.** COM-03-R07 numbers an invoice per legal entity, so a
    // tenant without one cannot be billed at all -- and a page that showed an empty list
    // would read as "nothing to see here".
    await expect(page.getByText(/No legal entity yet/)).toBeVisible();
    await expect(page.getByText(/numbered per entity/)).toBeVisible();
  });

  test("is reachable from the navigation, which marks where you are", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link", { name: "Organization" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // The other sections are links and are not marked.
    await expect(nav.getByRole("link", { name: "Doors" })).not.toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: organization, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/organization");
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may not read the hierarchy", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no navigation entry for it, and the doors entry it may use", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    // **Absent, not disabled.** A disabled control is a promise that something could be
    // unlocked; this session's role simply does not carry the permission.
    await expect(nav.getByRole("link", { name: "Organization" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "Doors" })).toBeVisible();
  });

  test("is refused the page itself rather than shown an empty tree", async ({ page }) => {
    await page.goto("/organization");
    // A page that caught the 403 and rendered "no organizations" would tell an operator
    // their company does not exist, which is a worse answer than "you may not see this".
    // Scoped to `main`: Next's own route announcer is a live region too, and an unscoped
    // role query matches it -- which is the same trap the sign-in suite records.
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("Veyro Sites Ltd")).toHaveCount(0);
  });
});
