import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

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
    // channel here. This build cannot tell a class from a personal-training session, so the
    // two tones the canvas draws are one mark.
    const grid = page.locator("table.ds-week");
    await expect(grid.locator('.ds-rota-mark[data-state="booked"] .ds-rota-mark-text').first())
      .toHaveText("Booked");
    await expect(
      grid.locator('.ds-rota-mark[data-state="exception"] .ds-rota-mark-text').first())
      .toHaveText("Off");
    // And the quiet states print nothing, or the grid has no ground to read the figure against.
    expect(await grid.locator('.ds-rota-mark[data-state="open"] .ds-rota-mark-text').count())
      .toBe(0);
  });

  test("every cell says its own state, because five fills is five things", async ({
    page,
  }) => {
    // Colour never carries meaning alone, and the legend names all five.
    const legend = page.getByRole("list", { name: "What a cell means" });
    for (const label of ["Available, unbooked", "Booked", "Booked, and the rota refuses it",
                         "Exception", "Not working"]) {
      await expect(legend).toContainText(label);
    }
    const marks = page.locator(".ds-rota-mark .ds-visually-hidden");
    expect(await marks.count()).toBeGreaterThan(0);
  });

  test("names what the grid does not do, including the form that is not blocked", async ({
    page,
  }) => {
    const gaps = page.locator("section").filter({ hasText: "What this grid does not do" });
    await expect(gaps.getByRole("term").filter({ hasText: "Add an exception" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "Class or personal training" }))
      .toBeVisible();
    await expect(gaps.getByRole("term").filter({ hasText: "The grid is hourly" }))
      .toBeVisible();
    // `scheduling.availability.write` is routine rather than stepped-up, so this is the next
    // piece of work rather than a button that would answer 403.
    await expect(gaps).toContainText("routine");
    await expect(gaps).toContainText("not a refusal");
  });

  test("offers no exception form yet, and no button that would fail", async ({ page }) => {
    await expect(page.getByRole("button", { name: /exception/i })).toHaveCount(0);
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
      "Booked, and the rota refuses it", "What this grid does not do", "Not working",
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
