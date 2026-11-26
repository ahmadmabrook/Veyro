import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession, useReaderSession } from "./sign-in";

/**
 * ADM-SCH-04 · COACH AVAILABILITY · WEEK GRID.
 *
 * The fixture's coach has a weekly 06:00-22:00 rota, a daily evening class, and **one
 * evening off with that class inside it** -- which is the canvas's own case and the one thing
 * this screen exists to show. The spec navigates to the week containing that exception rather
 * than to "this week", because a seeded date and whatever week today falls in are two facts.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const creds = fixture();

/** The week containing the seeded exception. */
const AT = `/rota?resource=${creds.coachResourceId}&from=${creds.rotaExceptionDay}`;

test.describe("the availability grid", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("reads a rota at last, which nothing in this build could do", async ({ page }) => {
    // `set_availability` had a writer and no reader since MOD-019 was built: a rota could be
    // written and the only way to learn what it said was to publish a template against it
    // and read the refusal.
    await expect(page.locator("table.ds-week")).toBeVisible();
    await expect(page.locator(".ds-rota-mark")).not.toHaveCount(0);
  });

  test("names the resource's own timezone, because every time on it is that clock", async ({
    page,
  }) => {
    // The defect MOD-019 shipped: `Window.timezone` was declared, written from the resource's
    // own location and read by nothing, so a London coach rostered 09:00-17:00 was available
    // for an 09:00 class in Amman. A grid of somebody's week is where that is least
    // questioned.
    await expect(page.locator("main")).toContainText("Asia/Amman");
    await expect(page.locator("main")).toContainText("Dana Coach");
  });

  test("shows the booking inside the exception, and flags it", async ({ page }) => {
    // The canvas: "His 17:30 with Hala sits inside it, so the grid shows both and the booking
    // is flagged rather than silently honoured or silently dropped."
    const flagged = page.locator('.ds-rota-mark[data-state="bookedConflict"]');
    await expect(flagged).not.toHaveCount(0);
    // And the exception's other hours are drawn as the exception, not quietly open.
    await expect(page.locator('.ds-rota-mark[data-state="exception"]')).not.toHaveCount(0);
  });

  test("lists each refused booking beneath the grid, with the rota's own reason", async ({
    page,
  }) => {
    // A marked cell in a grid of ninety is a thing somebody has to find, so the conflicts are
    // a list as well as a colour.
    const section = page.locator("section").filter({ hasText: "Bookings the rota now" });
    await expect(section).toContainText("Evening yoga flow");
    await expect(section).toContainText("time off");
    await expect(section).toContainText("already been told a time");
  });

  test("the conflict links to the session it is about", async ({ page }) => {
    const section = page.locator("section").filter({ hasText: "Bookings the rota now" });
    await expect(section.getByRole("link", { name: "Evening yoga flow" })).toBeVisible();
  });

  test("states the week in one sentence, as two numbers and never a ratio", async ({ page }) => {
    // **The canvas puts the whole figure in the sub-line** -- "Week of 17 August · Khalda ·
    // 26 of 34 available hours booked" -- and draws no metric row at all. An earlier version
    // of this screen had four cells repeating open, booked and conflicts, which is the same
    // three numbers twice and a reader checking one against the other for a difference that
    // cannot exist.
    //
    // Two numbers rather than a percentage, because a session outside the rota is booked and
    // not open, so the ratio can exceed one -- which is the case this screen is for.
    await expect(page.locator("main")).toContainText("available hours booked");
    await expect(page.locator("main")).not.toContainText("OPEN HOURS");
    await expect(page.locator("main")).not.toContainText("BOOKED HOURS");
  });

  test("moves between weeks, which is most of what this screen is asked", async ({ page }) => {
    // **Found by TestSprite and not by anything here**, which is the argument for an
    // independent layer: the default week was the only week, so the fixture's own
    // exception -- agreed ahead of the day it covers, which is the realistic shape and the
    // canvas's own example -- was unreachable from the screen. Every in-repo spec navigates
    // straight to `?from=`, so none of them could notice.
    const week = page.getByRole("navigation", { name: "Which week" });
    await expect(week).toBeVisible();
    const first = page.locator("main").locator("p.muted").first();
    const before = await first.textContent();
    await week.getByRole("link", { name: "Next week" }).click();
    await expect(first).not.toHaveText(before ?? "");
    await week.getByRole("link", { name: "Previous week" }).click();
    await expect(first).toHaveText(before ?? "");
  });

  test("the marks the canvas prints are printed, so no fill stands alone", async ({ page }) => {
    // ADM-SCH-04 writes PT or CLS in a booked cell and OFF in an exception, and leaves the
    // two quiet states blank -- figure and ground, and the reason colour is not the only
    // channel here. **The two marks are two**, as of ADR-0019: this assertion read "Booked"
    // against a comment saying the build could not tell a class from a personal session,
    // which `0036` made false -- a stale assertion holding a closed gap on the page.
    const grid = page.locator("table.ds-week");
    await expect(grid.locator('.ds-rota-mark[data-state="booked"] .ds-rota-mark-text').first())
      .toHaveText("CLS");
    await expect(
      grid.locator('.ds-rota-mark[data-state="exception"] .ds-rota-mark-text').first())
      .toHaveText("Off");
    // And the quiet states print nothing, or the grid has no ground to read the figure against.
    expect(await grid.locator('.ds-rota-mark[data-state="open"] .ds-rota-mark-text').count())
      .toBe(0);
  });

  test("every cell says its own state, because six fills is six things", async ({
    page,
  }) => {
    // Colour never carries meaning alone, and the legend names all six.
    const legend = page.getByRole("list", { name: "What a cell means" });
    for (const label of ["Available, unbooked", "A class is booked",
                         "A personal session is booked",
                         "Booked, and the rota refuses it", "Exception", "Not working"]) {
      await expect(legend).toContainText(label);
    }
    const marks = page.locator(".ds-rota-mark .ds-visually-hidden");
    expect(await marks.count()).toBeGreaterThan(0);
  });

  test("names what the grid does not do, and no longer counts the form among it", async ({
    page,
  }) => {
    const gaps = page.locator("section").filter({ hasText: "What this screen does not do yet" });
    await expect(gaps).toContainText("The grid is hourly");
    // **"Class or personal training" has left this list too**, and asserting its absence is
    // what stops it coming back: it said nothing in this build distinguished the two, and
    // `0036` made that false -- the gap note that outlives its gap, which this screen's own
    // read was *returning to every caller* until ADR-0019 deleted it.
    await expect(gaps.getByRole("term").filter({ hasText: "Class or personal training" }))
      .toHaveCount(0);
    // **"Add an exception" has left this list**, which is what the note it used to carry
    // said would happen. These two tests previously asserted that the form did not exist
    // and that no button offered it; both were true and both were the gap, not the design.
    await expect(gaps.getByRole("term").filter({ hasText: "Add an exception" }))
      .toHaveCount(0);
  });

  test("offers the form the canvas draws, because the permission is routine", async ({
    page,
  }) => {
    // Every other write surface in this app is absent because "a button that answered 403
    // is worse than its absence" -- each is a stepped-up financial permission.
    // `scheduling.availability.write` is `configuration` with no financial class, and the
    // catalogue says why: "a rota is edited by the people who run the floor, and refusing
    // them a step-up every time somebody books a day off would make the rota wrong instead."
    await expect(page.getByRole("button", { name: "Add the exception" })).toBeVisible();
  });

  test("the whole screen reads in Arabic", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForFunction(() => document.documentElement.dir === "rtl");
    await page.goto(AT);
    const main = page.locator("main");
    await expect(main).toContainText("التوافر");
    await expect(main).toContainText("محجوز، والجدول يرفضه");
    await expect(main).toContainText("ما لا يفعله هذا المخطط");
    for (const english of [
      "Booked, and the rota refuses it", "What this screen does not do yet", "Not working",
    ]) {
      await expect(main).not.toContainText(english);
    }
  });

  test("no accessibility violations", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a time-off reason", () => {
  test("is withheld from a session that could not have written it", async ({ page }) => {
    // It is the one free-text column in a rota and the one place a health fact goes in
    // practice -- MOD-017's rule, and the same prose `sch_session_changes.reason` is masked
    // for one table over. The exception itself is never hidden.
    await useReaderSession(page);
    await page.goto(AT);
    await expect(page.locator("main")).not.toContainText("hospital appointment");
    await expect(page.locator("main")).toContainText("Reading it needs the permission");
    // The exception is still drawn: a grid that dropped it would be the rota lying about who
    // is working.
    await expect(page.locator('.ds-rota-mark[data-state="exception"]')).not.toHaveCount(0);
  });

  test("is readable by the session that may set a rota", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
    await expect(page.locator("main")).not.toContainText("Reading it needs the permission");
  });
});

test.describe("the schedule board's third view", () => {
  test("links to the rota, which its own gap note said did not exist", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/schedule");
    // `schedule.views` reads "View", not "Views" -- selecting by the accessible name means
    // reading the name rather than guessing it.
    const views = page.getByRole("navigation", { name: "View" });
    await expect(views.getByRole("link", { name: "Coaches" })).toBeVisible();
    await views.getByRole("link", { name: "Coaches" }).click();
    await expect(page.locator("h1")).toContainText("Availability");
  });
});

test.describe("adding and withdrawing an exception", () => {
  /**
   * **The first write in this app that is not a member acting on their own account**, and it
   * needed a migration before it could exist: `sch_availability_windows` carried
   * `GRANT SELECT, INSERT` and nothing else, so a day off entered on the wrong date was
   * permanent. `scheduling.availability.write` is routine and AAL 1 by design, and a routine
   * permission whose every act is uncorrectable is MOD-013's rule from the other side.
   *
   * **The test puts the rota back where it found it**, which is this repository's own rule
   * about a suite that spends something the product keeps: a rota has no delete, so a test
   * that only added would leave one more absence on every run and the second run would
   * assert against a different week. It writes on a date no other spec looks at, proves the
   * grid moved, withdraws it, and proves the grid moved back. The only residue is a
   * withdrawn row, which no read returns.
   */
  const far = "2027-03-17";

  /**
   * **Clear the far week before each test, because a rota has no delete.**
   * The suite's own rule is that a test which spends something the product keeps provisions
   * its own — and the first version only withdrew what it had added, which is fine until the
   * test fails *between* the add and the withdraw. It did, once, for an unrelated reason, and
   * the next run found two exceptions where it expected one and failed for a reason that had
   * nothing to do with the product. Cleaning up front is idempotent whatever the last run
   * left; the only residue is withdrawn rows, which no read returns.
   */
  async function clearFarWeek(page: Page): Promise<void> {
    await page.goto(`/rota?resource=${creds.coachResourceId}&from=${far}`);
    for (;;) {
      const rows = page.locator(".ds-rota-exceptions li");
      if (await rows.count() === 0) return;
      const first = rows.first();
      await first.getByLabel("Why take it back").fill("clearing the test week");
      await first.getByRole("button", { name: /^Withdraw/ }).click();
      await expect(rows).toHaveCount(0, { timeout: 15_000 });
    }
  }

  test("writes a day off, shows it on the grid, and takes it back", async ({ page }) => {
    await useOwnerSession(page);
    await clearFarWeek(page);

    const form = page.locator("form.ds-rota-form");
    await expect(form).toBeVisible();
    await form.getByLabel("Day").fill(far);
    await form.getByLabel("From", { exact: true }).fill("13:00");
    await form.getByLabel("To", { exact: true }).fill("17:00");
    await form.getByLabel("Why", { exact: true }).fill("a dentist appointment");
    await form.getByRole("button", { name: "Add the exception" }).click();

    // The grid says so, which is the point: a write that the read does not reflect is a
    // reader told the product worked when it did not.
    const listed = page.locator(".ds-rota-exceptions li")
      .filter({ hasText: "13:00" });
    await expect(listed).toHaveCount(1);
    await expect(listed).toContainText("a dentist appointment");
    const marks = page.locator('.ds-week td .ds-rota-mark[data-state="exception"]');
    expect(await marks.count()).toBeGreaterThan(0);

    // And take it back, which is the half that had to be built first.
    await listed.getByLabel("Why take it back").fill("entered on the wrong day");
    await listed.getByRole("button", { name: /^Withdraw/ }).click();
    await expect(page.locator(".ds-rota-exceptions li").filter({ hasText: "13:00" }))
      .toHaveCount(0);
    await expect(page.locator('.ds-week td .ds-rota-mark[data-state="exception"]'))
      .toHaveCount(0);
  });

  test("names the field it needs rather than refusing the whole form", async ({ page }) => {
    // An empty field and a malformed one are different mistakes, and a form that reported
    // both as "that was refused" makes the reader try the same thing again.
    //
    // **The browser refuses this one first, and that is not the control being tested.**
    // Every field is `required`, so native validation stops the submit and the server never
    // hears about it -- which is right for a reader and proves nothing about the server. The
    // control that matters is the one a client which is not a browser reaches, so the test
    // turns native validation off and submits, exactly as `curl` would.
    await useOwnerSession(page);
    await clearFarWeek(page);
    const form = page.locator("form.ds-rota-form");
    await form.evaluate((el) => { (el as HTMLFormElement).noValidate = true; });
    await form.getByLabel("Day").fill(far);
    await form.getByLabel("From", { exact: true }).fill("13:00");
    await form.getByLabel("To", { exact: true }).fill("17:00");
    await form.getByRole("button", { name: "Add the exception" }).click();
    await expect(form).toContainText("This is needed");
    // And nothing was written.
    await expect(page.locator(".ds-rota-exceptions li").filter({ hasText: "13:00" }))
      .toHaveCount(0);
  });

  test("a reader who may not change a rota is given no form at all", async ({ page }) => {
    // "A button that answered 403 is worse than its absence" -- which is why every other
    // write surface in this app is missing, and the reason this one is gated on the write
    // rather than on the read that renders the page.
    await useReaderSession(page);
    await page.goto(`/rota?resource=${creds.coachResourceId}&from=${far}`);
    await expect(page.locator("form.ds-rota-form")).toHaveCount(0);
    await expect(page.locator("form.ds-rota-withdraw")).toHaveCount(0);
  });
});

test.describe("the schedule board's own gap list", () => {
  test("no longer says this build cannot read a rota", async ({ page }) => {
    // **The note outlived the gap by one change, and an independent tester believed it.**
    // Told to add a rota exception, TestSprite read "nothing in this build reads a
    // resource's availability" on the board, concluded the capability was absent and never
    // opened the view the chip beside it links to. That is the Member 360's "not built in
    // this repository" defect one screen over: a confident wrong answer where a missing one
    // would have been honest, and the kind of staleness only a reader notices.
    await useOwnerSession(page);
    await page.goto(`/schedule?site=${creds.locationId}`);
    await expect(page.locator("main")).not.toContainText("reads a resource's availability");
    await expect(page.getByRole("link", { name: "Coaches", exact: true })).toBeVisible();
  });
});

test.describe("a resource nobody wrote a rota for", () => {
  test("is unconstrained rather than never available", async ({ page }) => {
    // Seven columns of "not working" would read as a studio nothing can be booked into,
    // which is the opposite of true.
    //
    // **The resource has to be one with no rota, and the stand-in is not.** A substitution is
    // refused unless the replacement's rota covers the class, so the fixture gives the stand-in
    // a 06:00-22:00 week -- and this test, pointed at it, asserted against a page showing 112
    // open hours across a full grid. It failed for the right reason and the claim it was
    // written to prove had never been rendered at all.
    await useOwnerSession(page);
    await page.goto(`/rota?resource=${creds.noRotaResourceId}`);
    await expect(page.locator("main")).toContainText("no rota");
    await expect(page.locator("main")).toContainText("unconstrained");
    await expect(page.locator("table.ds-week")).toHaveCount(0);
  });
});

test.describe("a session that may not read the schedule", () => {
  test("is refused and told which permission it needs", async ({ page }) => {
    await useDeskSession(page);
    await page.goto(AT);
    await expect(page.locator("main")).toContainText("scheduling.schedule.read");
    await expect(page.locator(".ds-rota-mark")).toHaveCount(0);
  });
});
