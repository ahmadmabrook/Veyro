import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * MOD-008's surface: the roles, what this session may do, and the log refusals land in.
 *
 * **The audit assertions are about honesty rather than about rendering.** A hash chain that
 * reports "verified" with no caveat is the more misleading of its two answers: it detects
 * editing and not truncation by somebody who also moves the head, because every value the
 * verifier compares lives in the database that actor already controls. MOD-008 found that by
 * tamper-testing. A surface that printed a green tick alone would undo the disclosure.
 */
test.describe("the permissions surface", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/permissions");
  });

  test("lists the roles with what each one actually holds", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Permissions", level: 1 })).toBeVisible();
    // The bootstrap role holds every permission in the catalogue; the fixture's publisher
    // holds three. Both are rendered, and the count comes from the list rather than a claim.
    const roles = page.locator("section").filter({ hasText: "Roles" }).first();
    // **The matrix, not the role key.** ADM-STF-04 draws roles across the top and
    // capabilities down the side, which is what makes "nine roles and what each may
    // actually do" answerable; this page printed each role's 205 permission names instead,
    // 4,300 pixels of identifier with no way to compare two roles at all.
    await expect(roles.getByRole("columnheader", { name: "Tenant Administrator" }))
      .toBeVisible();
    await expect(roles.getByRole("columnheader", { name: "Front desk" })).toBeVisible();
    // And a mark that differs between two roles, which is the comparison the screen is for:
    // the front desk holds some of `people` and none of `finance`.
    const peopleRow = roles.getByRole("row").filter({ hasText: "people" }).first();
    await expect(peopleRow).toContainText("can do some of it");
    const financeRow = roles.getByRole("row").filter({ hasText: "finance" }).first();
    await expect(financeRow).toContainText("not available");
    await expect(roles).toContainText("Publisher");
  });

  test("can be expanded to every capability, one row each", async ({ page }) => {
    // **The module summary is the default and not the whole screen.** ◑ says the role can do
    // some of what a module covers and only the full list says which, so the link that gets
    // there is part of the answer rather than a convenience -- and it is a link, so the view
    // is in the URL and a reader can send somebody the one they are looking at.
    await page.goto("/permissions?rows=all");
    const roles = page.locator("section").filter({ hasText: "Roles" }).first();
    const row = roles.getByRole("row").filter({ hasText: "access.policy.publish" }).first();
    await expect(row).toBeVisible();
    // **The publisher holds this one and still cannot use it on an ordinary sign-in**,
    // because publishing a zone policy is `financial` class. That is the state the design's
    // middle mark sits in here, and it is the one a reader is most likely to get wrong:
    // holding the permission is not enough, which no list of permission names can say.
    await expect(row).toContainText("held, but needs a stronger sign-in");
    // The front desk holds none of it, which is the mark beside it in the same row.
    await expect(row).toContainText("not available");
  });

  test("says what this session may do, at the scope the server derived", async ({ page }) => {
    const mine = page.locator("section").filter({ hasText: "What this session may do" }).first();
    await expect(mine).toContainText("tenant");
    // **Counts by module, not every name.** The full list was 205 identifiers under their
    // module; which permissions this session holds in particular is what the gate table
    // below answers, action by action, and it answers it correctly where a list cannot --
    // a permission held on a sign-in too weak for it is in the list and refused by the gate.
    await expect(mine).toContainText("authz");
    await expect(mine).toContainText("authz");
    // **A permission listed is not a permission usable.** The assurance check is on the
    // action, not on the grant, and the page says so rather than implying the list is enough.
    await expect(mine).toContainText(/stronger sign-in/);
  });

  test("shows the chain's verdict and never without its caveat", async ({ page }) => {
    const audit = page.locator("section").filter({ hasText: "Audit log" }).first();
    await expect(audit).toContainText("The chain verifies");
    // The caveat is part of the green answer, not a footnote under the red one.
    await expect(audit).toContainText("detects editing, not truncation");
    await expect(audit).toContainText("head digest published somewhere the database cannot reach");
  });

  test("describes the log by what is in it, not by what would be tidy", async ({ page }) => {
    const audit = page.locator("section").filter({ hasText: "Audit log" }).first();
    // MOD-008 records the acts that hand out access as well as every refusal -- the fixture's
    // own log carries `role.assigned`. The first version of this page claimed allowed actions
    // are never recorded, which the data contradicts.
    await expect(audit).toContainText("role.assigned");
    await expect(audit).toContainText(/acts that hand out access/);
  });

  test("keeps a permission name left-to-right inside an Arabic document", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL("/permissions");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    // A permission name is an identifier: ASCII, never translated, and reordered by the bidi
    // algorithm without `dir` -- which turns `authz.role.read` into a different string.
    await expect(page.getByText("role.assigned").first()).toHaveAttribute("dir", "ltr");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: permissions, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/permissions");
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may not read roles", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no Permissions entry in the navigation", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Permissions" })).toHaveCount(0);
  });

  test("is refused each block rather than shown an empty one", async ({ page }) => {
    await page.goto("/permissions");
    // **Two permissions, two refusals.** An empty audit table would read as "nothing has been
    // refused", which is a different fact from "you may not see what has been".
    const refusals = page.locator("main").getByRole("status");
    await expect(refusals.filter({ hasText: "Not permitted" })).toHaveCount(3);
    await expect(page.getByText("role.assigned")).toHaveCount(0);
  });
});
