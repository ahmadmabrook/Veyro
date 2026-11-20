import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * MOD-013's board, against a tenant with two templates, two channels and a suppression.
 *
 * **The fixture seeds a transactional template beside a marketing one, and an enabled channel
 * beside a disabled one with a fallback.** Each pair is a distinction the board exists to
 * render: the category decides whether a member can mute a message at all, and a disabled
 * channel with a fallback is the arrangement MOD-013's review found a defect in -- the
 * fallback was resolved *after* the preference, the suppression and the address digest had
 * been read for the channel the message was no longer going to.
 *
 * **Nothing sends, and the page leads with it.** Every notification sits at `requested`, so a
 * board rendering that as a queue making progress would be claiming an outbound path there is
 * none of.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the messages board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/notifications");
  });

  test("leads with the fact that nothing sends", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Messages", level: 1 })).toBeVisible();
    await expect(page.getByText(/Nothing sends in this build/)).toBeVisible();
    await expect(page.getByText(/absence of a dispatcher, not a backlog/)).toBeVisible();
  });

  test("shows the authored message waiting, and says what it waits on", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "payment.failed" }).first();
    await expect(row).toContainText("requested");
    await expect(row).toContainText("no dispatcher exists here");
  });

  test("renders the decision reason as a sentence, not as the stored enum", async ({
    page,
  }) => {
    // "A rule id is not a reason", which the configuration board learned about flags.
    const section = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Messages authored" }) });
    await expect(section).toContainText("nothing in the member's preferences stops it");
    await expect(section).not.toContainText("no_preference_stops_it");
  });

  test("translates the decision reason, rather than leaving it in English", async ({
    page,
  }) => {
    // **Found by opening the board in Arabic.** The first version held English sentences in
    // a map, so the most explanatory field on the page stayed English on the Arabic one --
    // which no assertion about structure could see. Every other string on these surfaces
    // goes through the catalogue.
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForFunction(() => document.documentElement.dir === "rtl");
    await page.goto("/notifications");
    const section = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "الرسائل المُنشأة" }) });
    await expect(section).toContainText("لا شيء في تفضيلات العضو يمنعها");
    await expect(section).not.toContainText("nothing in the member");
  });

  test("carries no message text and never asks for it", async ({ page }) => {
    // The list route has no body on purpose; one that did would be a read path to everything
    // this tenant has ever said to anybody, under one permission.
    await expect(page.getByText(/The rendered text is not on this list/)).toBeVisible();
    await expect(page.getByText("Hello Jane")).toHaveCount(0);
  });

  test("says which suppressions can be lifted and which cannot", async ({ page }) => {
    const section = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Suppressed addresses" }) });
    await expect(section.getByText("Blocking")).toBeVisible();
    await expect(section).toContainText("unsubscribed");
    await expect(section).toContainText("can be lifted");
  });

  test("shows no address anywhere, only a digest", async ({ page }) => {
    // The tables hold a SHA-256 of `channel:address`, so a bounce is remembered and a
    // recipient matched without a second copy of everyone's email.
    await expect(page.getByText("left@veyro.test")).toHaveCount(0);
    await expect(page.getByText("jane.member@veyro.test")).toHaveCount(0);
  });

  test("tells an enabled channel from a disabled one with a fallback", async ({ page }) => {
    // **Scoped to the section, because `email` appears in four tables on this page.** An
    // unscoped row filter matched the notification row first -- `email · en · v1` -- which is
    // the fourth time in this suite that a substring filter has named the wrong row. Scoping
    // to the block under test is the form that survives another table being added.
    const channels = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Channels" }) });
    const email = channels.getByRole("row").filter({ hasText: "email" }).first();
    await expect(email).toContainText("Yes");
    const sms = channels.getByRole("row").filter({ hasText: "sms" });
    await expect(sms).toContainText("No");
    await expect(sms).toContainText("email");
    // A per-message cost with the currency's own exponent: 45 fils is 0.045 dinars.
    await expect(sms).toContainText("JOD 0.05");
  });

  test("says which templates a member may mute and which they may not", async ({ page }) => {
    const templates = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Templates" }) });
    const marketing = templates.getByRole("row").filter({ hasText: "class.offer" });
    await expect(marketing).toContainText("a member may mute this");
    const transactional = templates
      .getByRole("row")
      .filter({ hasText: "payment.failed" });
    await expect(transactional).toContainText("a member cannot mute this");
    await expect(page.getByText(/no request field overrides it/)).toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read messages", () => {
  test("gets no Messages entry in the navigation", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Messages" })).toHaveCount(0);
  });

  test("is refused the board rather than shown an empty outbox", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/notifications");
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("payment.failed")).toHaveCount(0);
  });
});
