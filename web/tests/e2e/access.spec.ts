import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { assuranceLevel, signIn } from "./sign-in";

/**
 * The MOD-022 surfaces, against the real access plane.
 *
 * Every assertion here is about a control the module exists to enforce, rendered where an
 * operator can see it. The two that matter most are paragraph 1944's -- a denial never
 * reveals sensitive financial or health information publicly -- and paragraph 4180's, that an
 * occupancy figure is advisory and never a muster source.
 *
 * The fixture seeds a zone whose policy requires an entitlement and a member who has none, so
 * the one decision in the log is a **restricted** refusal. That is deliberate: the public
 * half of an unrestricted refusal is its own text, and only a restricted one shows whether
 * the split is real.
 */

const creds = fixture();
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the door board", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("lists the seeded zone with its risk class and its readers", async ({ page }) => {
    await page.goto("/access");
    const row = page.getByRole("row").filter({ hasText: "Main floor" });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Standard");
    // Entry and exit counted separately: a zone with no exit reader cannot measure
    // occupancy, and one with no entry reader decides nothing at all.
    await expect(row).toContainText("1 Entry");
    await expect(row).toContainText("0 Exit");
  });

  test("says in words when a zone has no live policy", async ({ page }) => {
    // **Two zones, one with terms and one without**, because a test that only had the first
    // passed with the warning branch removed -- the else branch renders "Version N" either
    // way. The fixture seeds a plant room nobody has published a policy for.
    await page.goto("/access");
    await expect(
      page.getByRole("row").filter({ hasText: "Main floor" }),
    ).toContainText("Version");
    const unregulated = page.getByRole("row").filter({ hasText: "Plant room" });
    await expect(unregulated).toContainText("decides nothing");
    await expect(unregulated).not.toContainText("Version");
  });

  test("the board is reachable from the landing page only when the gate allows it", async ({
    page,
  }) => {
    await expect(page.getByRole("link", { name: "Doors" })).toBeVisible();
    await page.getByRole("link", { name: "Doors" }).click();
    await page.waitForURL("/access");
    await expect(page.getByRole("heading", { name: "Doors" })).toBeVisible();
  });
});

test.describe("a zone", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
    await page.goto(`/access/${creds.zoneId}`);
  });

  test("renders the terms a decision is made against", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Main floor" })).toBeVisible();
    await expect(page.getByText("Needs an entitlement")).toBeVisible();
    await expect(page.getByText("One entry every")).toBeVisible();
    await expect(page.getByText("60 seconds")).toBeVisible();
  });

  test("carries paragraph 4180's disclaimer next to the number", async ({ page }) => {
    // **Not summarised, not a tooltip, not a footnote.** A figure without this is the one
    // somebody counts heads against during an evacuation.
    const occupancy = page.getByRole("status").filter({ hasText: "muster" });
    await expect(occupancy).toBeVisible();
    await expect(occupancy).toContainText("never the sole life-safety muster source");
    await expect(page.getByText("Advisory only")).toBeVisible();
  });

  test("names what the zone cannot do rather than implying it can", async ({ page }) => {
    // `access_gaps` is the service's own list. A surface that dropped it would present a
    // zone as fully capable while its signature verification does not exist.
    await expect(page.getByRole("heading", { name: "What this zone cannot do" })).toBeVisible();
    await expect(page.getByText(/no signature is verified/)).toBeVisible();
  });

  test("shows the discreet line the member saw, marked as withheld", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "see_front_desk" });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Refused");
    // **The third cell, not the row.** Paragraph 1944: the member standing in the lobby is
    // told one thing, and the log has to say so rather than implying they were given the
    // real reason. Asserting on the row passed even with the mark removed, because the
    // fourth cell carries its own "Withheld" when the caller lacks the reason permission --
    // which is a different fact about a different column.
    const shownToMember = row.getByRole("cell").nth(2);
    await expect(shownToMember).toContainText("please see the front desk");
    await expect(shownToMember).toContainText("Withheld");
  });

  test("the full reason follows the session's assurance, not the role", async ({ page }) => {
    // **`access.decision.read_reason` is financial class**, which needs assurance level 2 --
    // and `held_permissions` filters the permission set by the session's level before the
    // service is asked. So the fixture's owner, who holds every permission there is, sees the
    // private half only on a sign-in that reached level 2.
    //
    // That is MOD-014's review finding made visible: "a grant is not a session". A test that
    // asserted the full reason unconditionally would have passed on a challenged sign-in and
    // failed on a password-only one, which is a coin flip rather than a check -- and asserting
    // it is always withheld would be worse, because it would keep passing if the filter were
    // removed.
    await page.goto("/");
    const aal = await assuranceLevel(page);
    await page.goto(`/access/${creds.zoneId}`);
    const row = page.getByRole("row").filter({ hasText: "see_front_desk" });
    if (aal >= 2) {
      await expect(row).toContainText("this member holds nothing that admits them here");
    } else {
      await expect(row).toContainText("Withheld");
      await expect(row).not.toContainText("holds nothing that admits");
    }
  });

  test("an unknown zone is a 404, not a 500", async ({ page }) => {
    const response = await page.goto("/access/11111111-2222-4333-8444-555555555555");
    expect(response?.status()).toBe(404);
  });

  test("a malformed zone id is a 404, not a 500", async ({ page }) => {
    // The backend answers 422 for a malformed id; the surface turns that into "no such page"
    // rather than an error, because a reader who mistyped a URL has not broken anything.
    const response = await page.goto("/access/not-a-uuid");
    expect(response?.status()).toBe(404);
  });

  test("mirrors in Arabic and keeps identifiers left-to-right", async ({ page }) => {
    // The language control is in the layout, so it is on this page too -- which is the point
    // of it being there rather than on the two pages that happened to need it first.
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL(`/access/${creds.zoneId}`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByText("ما لا تستطيع هذه المنطقة فعله")).toBeVisible();
    // The clock range is a Latin run inside RTL text; without `dir` the bidi algorithm moves
    // the dash and the colon and the window reads as a different one.
    const window = page.getByText("00:00–23:59");
    await expect(window).toHaveAttribute("dir", "ltr");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: zone, ${theme}`, async ({ page }) => {
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
});
