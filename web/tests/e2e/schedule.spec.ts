import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * MOD-019's calendar, against a schedule the fixture really published.
 *
 * **The fixture builds the whole chain** -- a service, an instructor with a rota, a studio, a
 * template with a recurrence rule, a publish, and a generation -- because a class is five rows
 * before it is a class and a board over a session row inserted by hand would prove none of it.
 * Seven daily occurrences come out of one rule, which is what the first assertion counts.
 *
 * **The assertion that matters most is the withheld reason.** MOD-019's review found a health
 * fact read out of a change reason by the routine schedule permission, so the server masks it
 * for anybody who cannot record one. A surface that dropped the entry would undo that
 * silently: an absent row says nothing changed, which is a different fact from "you may not
 * read why".
 */

const creds = fixture();
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the schedule board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/schedule");
  });

  test("is a week grid of seven day columns, not a list", async ({ page }) => {
    // **ADM-SCH-01 specifies a grid and this was a list**, which the compliance ledger
    // carried as a fidelity gap. "What is on at six o'clock on Thursday" is a scan down a
    // column in one and a search through forty rows in the other.
    await expect(page.getByRole("heading", { name: "Schedule", level: 1 })).toBeVisible();
    const headers = await page.locator(".ds-week thead th").allInnerTexts();
    // Seven days plus the time column, whose own header is for a screen reader.
    expect(headers).toHaveLength(8);
    const days = headers.slice(1).filter((text) => text.trim().length > 0);
    expect(days).toHaveLength(7);
  });

  test("renders every session in the site's timezone, not in UTC", async ({ page }) => {
    // **The defect this test exists for.** The rule says 18:00 local and the site is
    // Asia/Amman, so the stored instant is 15:00 UTC -- and the first version of this board
    // sliced the ISO string and rendered `15:00` under a heading promising the site's own
    // timezone. Every other assertion in this file passed while it did.
    //
    // In a grid the time is the *row header*, which makes the assertion stronger: a session
    // bucketed by its UTC hour would sit under a 15:00 row rather than merely print one.
    const times = await page.locator(".ds-week-time").allInnerTexts();
    expect(times.length).toBeGreaterThan(0);
    expect(times).toContain("18:00");
    expect(times).not.toContain("15:00");
  });

  test("a class cell carries its coach and its fill, which the design's ClassCell names",
    async ({ page }) => {
      const cell = page.locator(".ds-class-cell").filter({ hasText: "Evening yoga flow" })
        .first();
      // The live assignment, which needed the calendar read to return it: one request for
      // the week rather than one per cell.
      await expect(cell.locator(".ds-class-coach")).not.toBeEmpty();
      await expect(cell.locator(".ds-class-fill")).toContainText("/12");
    });

  test("severity is an edge-mark and never a cell fill", async ({ page }) => {
    // The canvas, in as many words: "severity on the cell edge-mark only, never the cell
    // fill". A grid of tinted blocks is a heat map, and a week with three marked classes
    // would read as a week three-quarters wrong.
    const spin = page.locator(".ds-class-cell").filter({ hasText: "Spin" }).first();
    const [edge, background] = await spin.evaluate((el) => [
      getComputedStyle(el).borderInlineStartWidth,
      getComputedStyle(el).backgroundColor,
    ]);
    expect(edge).toBe("3px");
    const plain = page.locator(".ds-class-cell").filter({ hasText: "Evening yoga flow" })
      .first();
    const ordinary = await plain.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(background, "a severe cell is not tinted").toBe(ordinary);
  });

  test("a class with no coach says so rather than leaving the cell blank", async ({ page }) => {
    // Null rather than an empty string, all the way from the read: a class with no coach is
    // a gap somebody has to fill, and a blank reads as a name nobody typed.
    const spin = page.locator(".ds-class-cell").filter({ hasText: "Spin" }).first();
    await expect(spin.locator(".ds-class-coach")).toHaveText("No coach");
  });

  test("anchors the week's problems under the grid rather than only marking them",
    async ({ page }) => {
      // `AttentionRow(condensed, footer-anchored)`. The problem is stated once under the
      // week rather than inferred from marks scattered across it.
      const problems = page.locator("section").filter({
        has: page.getByRole("heading", { name: "What needs you this week" }) });
      await expect(problems).toBeVisible();
      await expect(problems.locator(".ds-attention").first()).toContainText("Spin");
    });

  test("the grid is named once, not captioned twice", async ({ page }) => {
    // A caption that repeats the heading is the sentence said twice -- invisible to a
    // sighted reader and heard in full by a screen-reader user. This component shipped it:
    // a hidden caption *and* a hidden time-column header both carrying the page's title.
    await expect(page.locator(".ds-week")).toHaveAccessibleName("Schedule");
    expect(await page.getByText("Schedule", { exact: true }).count()).toBeLessThanOrEqual(2);
  });

  test("the day view is the same read over one column", async ({ page }) => {
    await page.getByRole("link", { name: "Day" }).click();
    await expect(page.locator(".ds-week thead th")).toHaveCount(2);
  });

  test("names the view and the write it does not have", async ({ page }) => {
    await expect(page.locator("main")).toContainText("The Coaches view");
    await expect(page.locator("main")).toContainText("Add a class");
  });

  test("names the site's own timezone, because every occurrence was converted in it", async ({
    page,
  }) => {
    // MOD-019 reads every rota window and converts every occurrence in the location's zone.
    // A board that rendered instants without saying which zone they are in would invite the
    // one mistake the module is built to avoid.
    await expect(page.getByText("Asia/Amman")).toBeVisible();
  });

  test("says what Taken and Free are, because neither is a stored counter", async ({ page }) => {
    // There is no `held_count` anywhere in MOD-019 and the absence is swept for. A reader who
    // took these for counters would expect them to be wrong after a crash, and would be
    // reasoning about a mechanism that does not exist.
    await expect(page.getByText(/not a counter anything stores/)).toBeVisible();
    await expect(page.getByText(/the module's own answer/)).toBeVisible();
  });

  test("opens a session and shows what it holds", async ({ page }) => {
    // **The last occurrence, not the first.** The fixture substitutes the instructor on the
    // first one, so it holds the stand-in -- which is the next test's subject. This one is
    // the ordinary case: the rule's own requirements, held by the resources it named.
    // In a grid the sessions are cells rather than rows, and the last column is the last
    // day of the week -- which is the occurrence no substitution touched.
    const cells = page.locator(".ds-class-cell").filter({ hasText: "Evening yoga flow" });
    await cells.last().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Evening yoga flow", level: 1 }))
      .toBeVisible();
    const holds = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What it holds" }) });
    await expect(holds).toContainText("Dana Coach");
    await expect(holds).toContainText("Studio A");
    // And no "used to hold" block at all, because nothing was substituted here.
    await expect(page.getByRole("heading", { name: "What it used to hold" }))
      .toHaveCount(0);
  });

  test("shows what a session used to hold, rather than replacing it", async ({ page }) => {
    // MOD-019 keeps a substituted instructor's hold rather than deleting it, because the
    // window a past conflict was decided against has to stay readable. Two lists rather than
    // one with a flag: a flag somebody forgets to filter puts a coach who was sent home back
    // on the roster.
    await page.goto(`/schedule/${creds.sessionId}`);
    const holds = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What it holds" }) });
    await expect(holds).toContainText("Sami Stand-in");
    const former = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What it used to hold" }) });
    await expect(former).toContainText("Dana Coach");
  });

  test("offers a step-up for a reason the owner's own session is too weak to read", async ({
    page,
  }) => {
    // **The owner holds every permission and still cannot read this**, which is the finding
    // MOD-014's review turned into a rule: `scheduling.session.change` is financial class, so
    // `held_permissions` filters it out of a password-only session. The withholding therefore
    // has a remedy here, and the page offers it -- which is a different answer from the one a
    // session that lacks the permission gets.
    await page.goto(`/schedule/${creds.sessionId}`);
    const changes = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What changed" }) });
    await expect(changes).toContainText("substitution");
    await expect(changes).toContainText("Reason withheld");
    const offer = page.getByRole("link", { name: "Sign in more strongly to read it" });
    await expect(offer).toBeVisible();
    await expect(offer).toHaveAttribute(
      "href",
      `/step-up?for=financial&next=${encodeURIComponent(`/schedule/${creds.sessionId}`)}`,
    );
  });

  test("says nothing has changed on a session nothing changed", async ({ page }) => {
    // The seventh occurrence, which no substitution touched. An empty list would read as
    // "there is no record", which is a different fact from "nothing happened".
    const cells = page.locator(".ds-class-cell").filter({ hasText: "Evening yoga flow" });
    await cells.last().getByRole("link").click();
    const changes = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What changed" }) });
    await expect(changes).toContainText("Nothing has changed about this session");
  });

  test("shows who is booked on tomorrow's class, and says whose seats they are", async ({
    page,
  }) => {
    // **The roster is MOD-020's and the seats are MOD-019's**, which is the module boundary
    // paragraph 4145 draws. There is no roster table and no cached total, so every count is a
    // sum over the holds -- and a surface that counted the rows it was handed would disagree
    // with the seat count the first time a hold existed without a booking behind it.
    await page.goto(`/schedule/${creds.bookedSessionId}`);
    const roster = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Who is booked" }) });
    await expect(roster).toContainText("front_desk");
    await expect(roster).toContainText("not yet");
    await expect(roster).toContainText(/belong to the schedule, not to the booking module/);
  });

  test("says nobody is waiting rather than showing an empty queue", async ({ page }) => {
    await page.goto(`/schedule/${creds.bookedSessionId}`);
    const roster = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Who is booked" }) });
    await expect(roster).toContainText("Nobody is waiting");
  });

  test("says nobody is booked on a class nobody booked", async ({ page }) => {
    // The substituted session, whose window closed before anybody could book it. An empty
    // table would read as "the roster could not be loaded", which is a different fact.
    await page.goto(`/schedule/${creds.sessionId}`);
    const roster = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Who is booked" }) });
    await expect(roster).toContainText("Nobody is booked on this session yet");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: schedule, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/schedule");
      }
      const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may read the schedule and may not change one", () => {
  // **This is the pair the mask needs.** The owner holds all 202 permissions, so signing in
  // as the owner proves only that an unmasked reason renders. This identity holds
  // `scheduling.schedule.read` and not `scheduling.session.change`, which is the case MOD-019
  // added the masking for.
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets the Schedule entry, because the navigation is filtered per item", async ({
    page,
  }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Schedule" })).toBeVisible();
    // And not the ones it does not hold, which is what makes the first assertion mean
    // something rather than "the navigation is all-or-nothing".
    await expect(nav.getByRole("link", { name: "Organization" })).toHaveCount(0);
  });

  test("is told to name the site in the link rather than shown an empty picker", async ({
    page,
  }) => {
    // Listing the sites is `tenancy.organization.read`, which this session does not hold --
    // and the board itself does not need it, because the calendar carries the site's name and
    // timezone. An empty picker would read as "this tenant has no sites".
    await page.goto("/schedule");
    await expect(page.getByText(/listing the sites is a different permission/)).toBeVisible();
    await expect(page.getByText("No session is published")).toHaveCount(0);
  });

  test("reads the board from a link that names the site", async ({ page }) => {
    await page.goto(`/schedule?site=${creds.locationId}`);
    // At least one, for the reason the owner's count test gives: the window is today onwards
    // and the fixture's seven occurrences start today, so the number drops as UTC days pass.
    const rows = page.getByRole("row").filter({ hasText: "Evening yoga flow" });
    expect(await rows.count()).toBeGreaterThan(0);
  });

  test("is refused the roster, because it belongs to another module", async ({ page }) => {
    // This identity holds the schedule read and not `booking.booking.read`. A refusal rather
    // than an empty class: "nobody is booked" and "you may not see who is" are different
    // facts, and the first one is the answer a coach would act on.
    await page.goto(`/schedule/${creds.bookedSessionId}`);
    const roster = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Who is booked" }) });
    await expect(roster).toContainText("Not permitted");
    await expect(roster).not.toContainText("Nobody is booked");
  });

  test("sees a change's reason withheld rather than absent", async ({ page }) => {
    // **Marked, never dropped.** An absent entry says nothing changed, which is a different
    // and wrong fact -- MOD-014's rule that a redacted record still exists, one module over.
    await page.goto(`/schedule/${creds.sessionId}`);
    const changes = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "What changed" }) });
    await expect(changes).toContainText("substitution");
    await expect(changes).toContainText("Reason withheld");
    await expect(changes).not.toContainText("the usual instructor is away");
    // And the marker says why, because a reader who cannot tell a withholding from an empty
    // field learns the wrong thing from both.
    await expect(page.getByText(/Reading one needs the permission to record one/))
      .toBeVisible();
    // **And no step-up is offered**, because this identity does not hold the permission at
    // any assurance -- sending it to find a second factor would be sending it nowhere.
    await expect(page.getByRole("link", { name: "Sign in more strongly to read it" }))
      .toHaveCount(0);
    await expect(page.getByText(/a stronger sign-in would not open it either/)).toBeVisible();
  });
});
