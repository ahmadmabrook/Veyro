import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * MOD-014's surfaces: the way in, and the composed record with its masks marked.
 *
 * **The masking assertions are the reason this suite exists.** MOD-008 has computed
 * `masked_fields` since it was written and nothing read it for five modules; MOD-014 applies
 * it, and a page that rendered a masked value as a blank would undo that silently -- an empty
 * cell is indistinguishable from "there was nothing here". Every assertion below is about the
 * difference between withheld and absent.
 *
 * The session here is the owner's, signed in with a password, which is assurance level 1. That
 * is deliberate: at level 1 the identity class is masked and the contact class is not, so one
 * fixture exercises both sides of the map.
 */
test.describe("the people index", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/people");
  });

  test("says there is no search instead of offering a scan", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "People", level: 1 })).toBeVisible();
    // PPL-01 puts the search index in ENG-01, which is not built. A `LIKE` scan presented as
    // search would be a read path with no permission pre-filter, which is worse than none.
    await expect(page.getByText(/There is no search/)).toBeVisible();
  });

  test("shows a duplicate pair with its score and the signals behind it", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "email_match" });
    await expect(row).toBeVisible();
    // **Never the score alone.** An operator asked to merge is being asked to destroy a
    // record, and `dedup.WEIGHTS` is the whole table: every signal is a named exact match.
    await expect(row).toContainText("legal_name_match");
    await expect(row).toContainText("50");
  });

  test("links to both sides of the pair rather than picking one", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "email_match" });
    await expect(row.getByRole("link")).toHaveCount(2);
  });
});

test.describe("the member record", () => {
  test.beforeEach(async ({ page }) => {
    const creds = fixture();
    await useOwnerSession(page);
    await page.goto(`/people/${creds.personId}`);
  });

  test("marks a masked identity field as withheld rather than leaving it blank", async ({
    page,
  }) => {
    await expect(page.getByRole("heading", { name: "Member 360", level: 1 })).toBeVisible();
    // The legal name is `identity` class, which needs `member.identity.read` -- a financial
    // action, so assurance level 2. This session has level 1, so the value is masked, and the
    // page has to say which of those two facts it is.
    const identity = page.locator("section").filter({ hasText: "Legal name" }).first();
    await expect(identity.getByText("Withheld").first()).toBeVisible();
    await expect(identity).not.toContainText("***");
  });

  test("shows the contact point in the clear, because that class is readable", async ({
    page,
  }) => {
    // **Both sides of one map.** `contact` opens on `member.profile.read`, which is routine,
    // so a level-1 session sees the address while the name beside it is withheld. A surface
    // that masked everything, or nothing, would pass a test that only looked at one.
    await expect(page.getByText("jane.member@veyro.test")).toBeVisible();
  });

  test("keeps a health note visible as a note and withholds only its body", async ({ page }) => {
    const notes = page.locator("section").filter({ hasText: "Notes" }).first();
    // The general note reads in full.
    await expect(notes).toContainText("Prefers the 7am class.");
    // The health one is counted, classified and withheld -- `member.health.read` is
    // `biometric_sensitive`, which is assurance level 3, which nothing in this build reaches.
    await expect(notes).toContainText("health");
    await expect(notes).not.toContainText("physiotherapist");
    // **And the reason, not merely the marker.** A note withheld "because this session is
    // too weak" and one withheld "because nobody can read it" are different facts with
    // different remedies, and the second has none -- so the marker has to carry which.
    const marker = notes.getByText("Withheld");
    await expect(marker).toHaveCount(1);
    await expect(marker).toHaveAttribute("title", /hardware authenticator/);
  });

  test("says a health field cannot be read by anybody, not that a step-up would help", async ({
    page,
  }) => {
    // **Scoped to the custom fields' own list, not to the panel.** The first version scoped
    // to the section and took the last marker in it, which is also satisfied by a marker
    // belonging to a different field -- so the mutation that pointed a health field at the
    // step-up message was not caught. The `dl` that contains "Injury history" is the
    // custom-field list and nothing else.
    const fields = page.locator("dl").filter({ hasText: "Injury history" });
    await expect(fields).toHaveCount(1);
    const marker = fields.getByText("Withheld");
    await expect(marker).toHaveCount(1);
    await expect(marker).toHaveAttribute("title", /hardware authenticator/);
    // And the remedy it does *not* offer is the step-up, because there is none to offer.
    await expect(marker).not.toHaveAttribute("title", /stronger sign-in/);
  });

  test("names the sections no module in this build can answer", async ({ page }) => {
    const sections = page.locator("section").filter({ hasText: "Where each part comes from" });
    // Seven of the twelve areas PPL-01-R02 lists belong to modules this repository does not
    // have. Rendering them as empty lists would read as "none".
    await expect(sections.getByRole("heading", { name: "Not in this build" })).toBeVisible();
    await expect(sections).toContainText("COM-01 is not built");
  });

  test("shows the projected timeline with what each entry was", async ({ page }) => {
    const timeline = page.locator("section").filter({ hasText: "Timeline" }).first();
    await expect(timeline).toContainText("Membership status changed from none to lead");
    await expect(timeline).toContainText("member.lifecycle.changed");
  });

  test("an unknown person is a 404 message, not a 500", async ({ page }) => {
    await page.goto("/people/11111111-1111-4111-8111-111111111111");
    await expect(page.locator("main").getByRole("status")).toContainText(/No such person/);
  });

  test("a malformed person id is a message, not a 500", async ({ page }) => {
    await page.goto("/people/not-a-uuid");
    await expect(page.locator("main").getByRole("status")).toBeVisible();
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: member 360, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may not read people", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no People entry in the navigation", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "People" })).toHaveCount(0);
  });

  test("is refused the record rather than shown an empty one", async ({ page }) => {
    const creds = fixture();
    await page.goto(`/people/${creds.personId}`);
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("jane.member@veyro.test")).toHaveCount(0);
  });
});
