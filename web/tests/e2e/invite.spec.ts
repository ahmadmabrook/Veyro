import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * ADM-STF-03 · INVITE, against the real routes. ADR-0017.
 *
 * **The form's own send is behind a step-up and this suite does not spend one.**
 * `authz.assignment.write` is financial in MOD-008's catalogue, so a password-only session is
 * refused -- which is the product working, and what the screen does about it is offer the
 * step-up rather than hide the form. So what is asserted here is that every field-level
 * refusal clears and the *remaining* hold is that one, which is ADM-MSH-09's own arrangement
 * and for the same reason: a recovery code is single-use and a suite that spent one per run
 * would be green exactly once.
 *
 * The pending list is seeded, because a list with one row of one kind demonstrates nothing:
 * the fixture writes a pending invitation and a withdrawn one. An **expired** one is
 * unwritable through any route -- `expires_at` is `now() + make_interval(days => N)` with a
 * one-day floor, so that the window's two ends come from one clock -- and all four words are
 * proved in `tests/component/invitations.test.tsx` instead.
 */
test.beforeEach(async ({ page }) => {
  await useOwnerSession(page);
  await page.goto("/staff/invite");
});

test.describe("the invite form", () => {
  test("draws the canvas's three fields and no name", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Invite someone");
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Role")).toBeVisible();
    await expect(page.getByRole("group", { name: "Where they work" })).toBeVisible();
    // **The pin that would have caught the column coming back.** The canvas collects an
    // address, a role and the clubs, and its pending list draws an address rather than a
    // person -- so a name field here is one this app invented, and a copy of somebody's name
    // in the plane whose own authentication log deliberately records none.
    await expect(page.locator('[name="display_name"]')).toHaveCount(0);
    await expect(page.getByRole("main").getByRole("textbox")).toHaveCount(1);
  });

  test("states the expiry before a role is chosen, and the reach after", async ({ page }) => {
    await expect(page.getByText("The link expires in 7 days.")).toBeVisible();
    await expect(page.getByText("Choose a role and what it grants is shown here."))
      .toBeVisible();
    await page.getByLabel("Role").selectOption({ label: "Tenant Administrator" });
    await expect(page.getByText("Choose a role and what it grants is shown here."))
      .toHaveCount(0);
    // The owner's role carries every permission, so the honest sentence is the count rather
    // than "no financial administration" -- which is the claim being checkable rather than
    // typed.
    await expect(page.getByText(/need(s)? a stronger sign-in/)).toBeVisible();
  });

  test("swaps the club picker for the tenant-wide warning", async ({ page }) => {
    await expect(page.getByRole("group", { name: "Clubs" })).toBeVisible();
    await page.locator(".ds-choice-chip").filter({ hasText: "Every club" }).click();
    await expect(page.getByRole("group", { name: "Clubs" })).toHaveCount(0);
    await expect(page.getByText(/A role held across the whole tenant is the widest grant/))
      .toBeVisible();
  });

  test("refuses an address that is not one, before anything is sent", async ({ page }) => {
    await page.getByLabel("Email").fill("kareem");
    await page.getByLabel("Role").selectOption({ label: "Tenant Administrator" });
    await page.locator(".ds-choice-chip").filter({ hasText: "Every club" }).click();
    await page.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByText("An invitation needs an address to go to.")).toBeVisible();
    // And no link is rendered, because nothing was written.
    await expect(page.getByText("The invitation is ready")).toHaveCount(0);
  });

  test("asks for a club rather than inviting somebody into none", async ({ page }) => {
    await page.getByLabel("Email").fill(`spec-${Date.now()}@nadi.test`);
    await page.getByLabel("Role").selectOption({ label: "Tenant Administrator" });
    await page.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByText(/A role held at no club grants nothing at all/)).toBeVisible();
  });

  test("the only hold left on a complete form is the step-up it offers", async ({ page }) => {
    await page.getByLabel("Email").fill(`spec-${Date.now()}@nadi.test`);
    await page.getByLabel("Role").selectOption({ label: "Tenant Administrator" });
    await page.locator(".ds-choice-chip").filter({ hasText: "Every club" }).click();
    await page.getByRole("button", { name: "Send invitation" }).click();

    await expect(page.getByText(/needs a stronger sign-in than this session has/))
      .toBeVisible();
    const raise = page.getByRole("link", { name: "Step up and invite" });
    await expect(raise).toBeVisible();
    await expect(raise).toHaveAttribute(
      "href", "/step-up?for=financial&action=authz.assignment.write&next=%2Fstaff%2Finvite");
    // Every field-level refusal has cleared: what is left is the one the reader cannot fix in
    // this form, which is the distinction this assertion exists for.
    await expect(page.getByText("An invitation needs an address to go to.")).toHaveCount(0);
    await expect(page.getByText(/A role held at no club grants nothing at all/))
      .toHaveCount(0);
    // And nothing was written: no link, because the refusal came before the row.
    await expect(page.getByText("The invitation is ready")).toHaveCount(0);
  });
});

test.describe("the pending list", () => {
  test("draws the address and nothing else in the who column", async ({ page }) => {
    const creds = fixture();
    const row = page.getByRole("table").getByRole("row")
      .filter({ hasText: creds.invitedEmail });
    await expect(row).toBeVisible();
    await expect(row).toContainText("waiting");
    // The clubs the invitation names, which is the row's own answer rather than the
    // invitee's club: an invitation has no profile to sit at.
    await expect(row).toContainText("Downtown");
  });

  test("counts what is waiting, and a withdrawn one has left the list", async ({ page }) => {
    const creds = fixture();
    // **The figures line, not the heading**: the design's header is a title and a line of
    // figures, and `PageHeader` renders them as siblings rather than inside the `h1`.
    await expect(page.locator(".ds-page-figures"))
      .toContainText("1 invitation is waiting to be accepted.");
    // **And the withdrawn one is not on screen at all**, which is what found the dead guard
    // in `PendingActions`: `listInvitations` asks for what is waiting, so a settled
    // invitation is not in this list and the em-dash branch written for one could not
    // render. The canvas draws PENDING and nothing else, so there is no settled list to put
    // it in -- the route carries `include_settled` for a reader this design does not draw.
    await expect(page.getByRole("table")).not.toContainText(creds.withdrawnEmail);
    await expect(page.getByRole("table")).not.toContainText("withdrawn");
  });

  test("offers both controls on the waiting one, because neither is refused", async ({
    page,
  }) => {
    const creds = fixture();
    const waiting = page.getByRole("table").getByRole("row")
      .filter({ hasText: creds.invitedEmail });
    await expect(waiting.getByRole("button", { name: "Resend" })).toBeVisible();
    await expect(waiting.getByRole("button", { name: "Withdraw" })).toBeVisible();
  });

  test("never carries a token back, only the digest is stored", async ({ page }) => {
    // The listing route returns no token at all, which is what makes "shown once" true.
    const table = await page.getByRole("table").innerText();
    expect(table).not.toMatch(/[A-Za-z0-9_-]{30,}/);
  });
});

test.describe("who may open it", () => {
  test("a reader without the grant is told so rather than shown a dead form", async ({
    page,
  }) => {
    await useDeskSession(page);
    await page.goto("/staff/invite");
    await expect(page.getByLabel("Email")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Send invitation" })).toHaveCount(0);
    // The gate denied outright, so the remedy is a permission and not a stronger sign-in --
    // offering a step-up here would send somebody to spend a recovery code for nothing.
    await expect(page.getByRole("link", { name: "Step up and invite" })).toHaveCount(0);
    await expect(page.getByRole("main")).toContainText(/not permitted|permission/i);
  });
});

test.describe("the screen reads in both languages", () => {
  test("the whole screen reads in Arabic", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("ادعُ شخصًا");
    await expect(page.getByRole("main")).not.toContainText("Invite someone");
  });

  test("no accessibility violations", async ({ page }) => {
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
  });
});
