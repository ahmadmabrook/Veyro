import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession, useReaderSession } from "./sign-in";

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
    // **The record's heading is the member's own name**, which ADM-MEM-01 draws and this
    // page now renders: the old `<h1>Member 360</h1>` was the screen's label where the
    // canvas puts the person. Masked here, because this session is level 1.
    await expect(page.getByRole("heading", { name: "Name withheld", level: 1 })).toBeVisible();
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

  test("tells a reader who holds no contact read that no sign-in will open it", async ({
    page,
  }) => {
    // **The other side of that map, and the branch the owner cannot reach.** The test above
    // proves a routine session *sees* the address, which means the withheld-contact case had
    // no fixture at all -- and the marker it rendered said "identity fields need a stronger
    // sign-in. Step up and the value is readable." for a phone number, which is false in
    // every case rather than in some: `member.profile.read` is `data_access` with no
    // financial class, so a stronger sign-in can never lift a contact mask. The front desk
    // holds `people.person.read` and nothing else, so this is the reader it is about.
    await useDeskSession(page);
    await page.goto(`/people/${fixture().personId}`);
    const marker = page.locator("#main").getByText("Withheld").first();
    await expect(marker).toBeVisible();
    await expect(
      page.locator("#main").locator('[title*="contact field"]').first(),
    ).toBeVisible();
    await expect(page.locator("#main").getByText("jane.member@veyro.test"))
      .toHaveCount(0);
    // **And never the remedy that does not exist for it** -- asserted as the *offer* rather
    // than as the words, which is what the first version got wrong: `[title*="stronger
    // sign-in"]` matched the contact sentence itself, because that sentence says the remedy
    // is "a permission rather than a stronger sign-in". A substring that appears in more
    // than the thing it means is the positional-locator trap in prose.
    await expect(
      page.locator("#main").locator('[title*="Step up and the value is readable"]'),
    ).toHaveCount(0);
    await expect(
      page.locator("#main").getByRole("link", { name: /stronger sign-in|Raise/i }),
    ).toHaveCount(0);
  });

  test("keeps a health note visible as a note and withholds only its body", async ({ page }) => {
    // ADM-MEM-01 puts notes behind their own tab rather than in the Overview stack.
    await page.goto(`/people/${fixture().personId}?tab=notes`);
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

  test("says a health field needs a level this screen cannot reach, not a step-up", async ({
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
    const sections = page.locator("section").filter({ hasText: "Not answered here" });
    // Seven of the twelve areas PPL-01-R02 lists are not answered here. Rendering them as
    // empty lists would read as "none".
    await expect(sections.getByRole("heading", { name: "Not answered here" })).toBeVisible();
    await expect(sections).toContainText("CCH-02 is not built in this repository");
  });

  test("does not call a module that exists one that was never built", async ({ page }) => {
    // **This test used to assert the defect.** It checked for "COM-01 is not built", which
    // was true when it was written and false by the time somebody looked at the page: the
    // modules behind membership, bookings, attendance and finance have all been built since,
    // and the one screen a staff member opens before talking to a member was telling them the
    // product does not have bookings.
    const sections = page.locator("section").filter({ hasText: "Not answered here" });
    // **MOD-017 and MOD-018 are no longer in this list, and that is the point.** The page
    // composes membership, entitlements and finance on their own tabs now, so naming them
    // as gaps would say the product does not have what the tab beside it shows -- the same
    // stale-list defect this test was written for, in the other direction. They are named
    // in the panel's own footer as answered elsewhere, which is asserted below.
    for (const built of ["MOD-019", "MOD-020"]) {
      await expect(sections).toContainText(built);
    }
    await expect(sections).toContainText("this page asks those modules directly");
    await expect(sections).toContainText("nothing here reads it");
    await expect(sections).not.toContainText("COM-01 is not built");
    await expect(sections).not.toContainText("OPS-01 is not built");
    // And the line that tells the two reasons apart, without which they read as one.
    await expect(sections).toContainText(/Two reasons, and the difference matters/);
  });

  test("shows the projected timeline with what each entry was", async ({ page }) => {
    const timeline = page.locator("section").filter({ hasText: "Timeline" }).first();
    await expect(timeline).toContainText("Membership status changed from none to lead");
    await expect(timeline).toContainText("member.lifecycle.changed");
  });

  test("the attendance tab draws the gap as well as the visits", async ({ page }) => {
    // **ADM-MEM-07, and the read was built a session before the tab was.** This page's own
    // notes listed attendance among five tabs that "need a module or a read this build does
    // not have" while `GET /access/attendance` was already feeding the LAST VISIT cell -- a
    // claim about what a product cannot do goes stale the moment somebody builds it.
    await page.goto(`/people/${fixture().personId}?tab=attendance`);
    const panel = page.locator("section").filter({ hasText: "Attendance" }).first();

    // The three figures the canvas leads with. Lifetime is what makes the other two mean
    // something: a gap of a fortnight reads differently against two hundred visits than six.
    for (const label of ["SINCE LAST", "WEEKLY AVG", "LIFETIME"]) {
      await expect(panel.locator(".ds-metric").filter({ hasText: label })).toHaveCount(1);
    }

    // **Twelve bars, including the empty ones.** The canvas's own reading is "three weeks at
    // zero", which means nothing unless the zeros are drawn -- and a series that omitted
    // them, which is what a GROUP BY returns if nobody fills the gaps, shows a member who
    // trained steadily.
    const bars = panel.locator(".ds-weekbar");
    await expect(bars).toHaveCount(12);
    const zero = await bars.filter({ hasText: ": 0" }).count();
    expect(zero, "the fixture seeds a gap, so some week is empty").toBeGreaterThan(0);

    // A zero week is a mark on the baseline, not an absence: a bar nobody can see and no bar
    // at all are the same thing to a reader.
    const height = await bars.filter({ hasText: ": 0" }).first()
      .locator(".ds-weekbar-fill").evaluate((el) => el.getBoundingClientRect().height);
    expect(height).toBeGreaterThan(0);
  });

  test("a visit names the club and how they got in, in words", async ({ page }) => {
    await page.goto(`/people/${fixture().personId}?tab=attendance`);
    const recent = page.locator("dl").filter({ hasText: "Downtown" }).first();
    await expect(recent).toBeVisible();
    // **The word, not the column's value.** The canvas reads "card"; this rendered
    // `nfc_card`, which is Latin letters in the middle of an Arabic line and the third
    // stored-value-as-label in one pass.
    await expect(recent).toContainText("Card");
    await expect(recent).not.toContainText("nfc_card");
    // And never the credential itself: the stored value is a one-way digest.
    await expect(page.locator("main")).not.toContainText("CARD-");
  });

  test("a credential says how often it has been used and when last", async ({ page }) => {
    // ADM-ACC-03's second line: "Card ...8841 · Issued 4 Mar 2024 · 214 uses". Both halves
    // are what make the row actionable -- `state` reads `active` for a card used this
    // morning and for one nobody has presented in two years.
    await page.goto(`/people/${fixture().personId}?tab=access`);
    const panel = page.locator("section").filter({ hasText: "Access" }).first();
    await expect(panel).toContainText("Issued");
    await expect(panel).toContainText(/\d+ uses/);
    await expect(panel).toContainText("last used");
  });

  test("says there is no last-four and never was, rather than losing it quietly", async ({
    page,
  }) => {
    // The canvas draws "Card ··· 8841" and this build stores a one-way digest, so a reader
    // looking for the number would otherwise assume the screen dropped it. The stronger
    // position said out loud, not a gap apologised for.
    await page.goto(`/people/${fixture().personId}?tab=access`);
    await expect(page.locator("main")).toContainText("no last-four here and never was");
    // And nothing resembling a card number reaches the page.
    await expect(page.locator("main")).not.toContainText("CARD-");
  });

  test("offers no reading of the chart, and says why", async ({ page }) => {
    await page.goto(`/people/${fixture().personId}?tab=attendance`);
    await expect(page.locator("main")).toContainText("confident answer with nothing behind it");
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
