import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession, useReaderSession } from "./sign-in";

/**
 * FD-06 · CLASS CHECK-IN, the first Front Desk screen in this build.
 *
 * **And the first working write form in this app that is not behind a step-up.**
 * `booking.attendance.write` is routine, so a receptionist at an ordinary password sign-in
 * marks somebody present — which closes the half of MOD-020's own gap note ("a front desk
 * cannot do it for them") that needed no new permission.
 *
 * **Two of this screen's states are unreachable from a fixture and are tested elsewhere.**
 * A settled no-show and a gym-released booking both need `settle_session_bookings`, which
 * has no route by design — it decides whether somebody was absent, so it takes no
 * caller-supplied instant. `tests/component/desk.test.ts` constructs both; three backend
 * tests prove the prior-no-show count itself. A browser cannot get there, and saying so is
 * better than a spec that pretends.
 */

const creds = fixture();

/**
 * **Two sessions, because one cannot carry both halves.** Tomorrow's class has a coach, a
 * studio and a timezone to render and a check-in window that is correctly shut; the one
 * starting in half an hour has an open window and, deliberately, no coach -- an instructor's
 * rota is 06:00-22:00 and a fixture that ran at five in the morning would be refused.
 */
const AT = `/desk/classes/${creds.bookedSessionId}`;
const SOON = `/desk/classes/${creds.deskSessionId}`;

test.describe("the class a desk is checking people into", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("says which class it is, in the site's own timezone", async ({ page }) => {
    // **The schedule board's hard-won rule.** MOD-019 stores a UTC instant and the local
    // facts it came from because neither is derivable from the other; the board once
    // rendered 15:00 for an 18:00 class under a heading naming the right zone, and every
    // test passed because they asserted the *name* of the timezone rather than the time.
    // So this asserts the rendered value.
    const head = page.locator(".ds-page-head");
    await expect(head).toContainText("18:00");
    await expect(head).toContainText("Asia/Amman");
    await expect(head).toContainText("Studio A");
  });

  test("counts who is here against the session's places", async ({ page }) => {
    // A class with free seats is "0 of 12 here", not "0 of 1": the denominator is MOD-019's
    // capacity and the roster has no cached total.
    await expect(page.locator(".ds-page-head")).toContainText("of 12 here");
  });

  test("identifies a member whose name is withheld, rather than showing only a marker",
    async ({ page }) => {
      // A row a desk cannot tell from the next one is a row they cannot act on — the
      // finding an independent tester made twice against the members and staff lists.
      const row = page.locator(".ds-desk-row").first();
      await expect(row).toContainText("Withheld");
      await expect(row).toContainText("M-00042");
      await expect(row).toContainText("Expected");
    });

  test("offers no check-in for a class whose window has not opened", async ({ page }) => {
    // **The defect a browser test found.** `may_check_in` opens the window an hour before
    // the session, so a desk opening tomorrow's class is correctly refused -- and the first
    // version offered the button anyway and surfaced the 409 as prose under the row. A
    // button that answered 403 is worse than its absence; a sentence saying when it opens
    // is what belongs there.
    const row = page.locator(".ds-desk-row").first();
    await expect(row.getByRole("button", { name: "Check in" })).toHaveCount(0);
    await expect(row).toContainText("Check-in opens an hour before");
  });

  test("names the three things it does not do, including the canvas's own promise",
    async ({ page }) => {
      // The canvas says "At 19:00 their places release to the waitlist automatically and
      // the three waiting are notified — you do not have to remember." Nothing in this
      // build does either, and a screen that repeated it would be telling a receptionist to
      // forget something nobody is holding.
      const gaps = page.locator(".ds-desk-gaps");
      await expect(gaps.getByRole("term")
        .filter({ hasText: "Releasing a place when the class starts" })).toBeVisible();
      await expect(gaps).toContainText("you do not have to remember");
      await expect(gaps.getByRole("term")
        .filter({ hasText: "Telling the people waiting" })).toBeVisible();
      await expect(gaps.getByRole("term")
        .filter({ hasText: "Reading a card" })).toBeVisible();
    });

  test("no accessibility violations", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });

});

test.describe("a class that is about to start", () => {
  /**
   * **The fixture seeds ten members on this class and the suite spends one a run.**
   * Checking somebody in is one-way -- there is no un-check-in, correctly -- so a block that
   * leaned on a single booking is green on a fresh fixture and red on the second run, which
   * is the budget-consuming shape this repository records three times and which only shows
   * up by running the suite twice. The test cannot provision its own: `people.person.write`
   * is financial class, so a browser session at AAL 1 is refused, which is the same boundary
   * that makes ADM-MEM-10's form offer a step-up.
   *
   * So every assertion here is about *a* row the module would still accept rather than a
   * named member, and the count is relative to what was on screen a moment earlier.
   */
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(SOON);
  });

  /** The first row the module would still take a check-in for. */
  const expected = (page: Page) =>
    page.locator(".ds-desk-row").filter({ has: page.locator(".ds-desk-checkin") }).first();

  test("marks somebody present, at an ordinary sign-in", async ({ page }) => {
    // **The assertion the whole screen rests on.** Not that a button exists but that a
    // password-only session can use it: every other write form in this app is a step-up or
    // an absence, and the reason this one is not is `booking.attendance.write`'s own class.
    //
    // **It books its own member**, because checking somebody in is one-way. A test that
    // used the fixture's booking was green on a fresh fixture and red on the second run --
    // the budget-consuming shape this repository records three times, and the only way to
    // see it is to run the suite twice. The API call goes through the browser's own session
    // cookie, which is the fleet spec's pattern: `context.cookies()` can read an httpOnly
    // cookie where page JavaScript cannot, so the state the test asserts is state it made.
    const before = await presentCount(page);
    const row = expected(page);
    await expect(row).toContainText("Expected");
    const who = (await row.innerText()).match(/M-[A-Z0-9]+/)?.[0];
    expect(who, "a row is identified by its member number when the name is withheld")
      .toBeTruthy();
    await row.getByRole("button", { name: "Check in" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator(".ds-desk-row").filter({ hasText: who! }))
      .toContainText("Here");
    expect(await presentCount(page)).toBe(before + 1);
  });

  test("meets the touch target floor the density makes mandatory", async ({ page }) => {
    // **44px on Touch is "the minimum target, not a style"**, and the rule that enforces it
    // was scoped to `:root` -- so a screen setting its own density got the type, the row
    // height and a 36px button under the finger it is designed for. Measured rather than
    // asserted about a class name, because the pixels are the property.
    //
    // **What delivers it here is `size="lg"`, not the density rule**, and the mutation sweep
    // is what established that: breaking the density selector left this measurement green,
    // because `BUTTON_HEIGHT` makes `lg` 44px on its own. Both are worth having -- the rule
    // is the floor for every other control on a touch screen, proved structurally in
    // `tests/unit/shell-tokens.test.mjs` -- and this assertion is about what a finger
    // actually gets on this screen.
    const button = expected(page).locator(".ds-desk-checkin button");
    const box = await button.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    const row = await page.locator(".ds-desk-row").first().boundingBox();
    expect(row!.height).toBeGreaterThanOrEqual(48);
  });

  test("puts the people who have not arrived first", async ({ page }) => {
    // Not booking order, which is what the read returns: four minutes out a receptionist is
    // looking for who is missing, and the ones in the room are the rows they want out of
    // the way.
    const states = await page.locator(".ds-desk-row").evaluateAll(
      (rows) => rows.map((row) => (row as HTMLElement).dataset.state));
    expect(states.length).toBeGreaterThan(1);
    expect([...states].sort((a, b) =>
      (a === "expected" ? 0 : 1) - (b === "expected" ? 0 : 1))).toEqual(states);
  });

  test("counts the minutes, or says it has begun, because both are urgency", async ({
    page,
  }) => {
    // The canvas's lead sentence, and it is only true close to the start: the first version
    // printed "2,266 minutes to go" for a class the next evening. **Two members are booked
    // on this class** so that the test above checking one of them in leaves somebody still
    // expected -- the block's own booking, so this never depends on what ran before it.
    //
    // **Both branches, because the fixture's class is thirty minutes out when it is seeded
    // and the clock does not stop.** A test asserting only the countdown is green for half
    // an hour after provisioning and red afterwards -- the shape this repository records for
    // a device's freshness, a recovery code and a login budget, and the worst version of it,
    // because CI provisions immediately before the suite and never sees the other side. The
    // freshness cannot be *made* here: moving a session is a stepped-up scheduling write and
    // a browser session is AAL 1. So the screen's own answer decides which sentence to
    // expect, the way `assuranceLevel` does one spec over, and both are asserted -- a class
    // in progress with six people missing is urgency too, which is why the banner has that
    // branch at all.
    const banner = page.locator(".ds-banner");
    await expect(banner).toContainText(/minutes to go|has started/);
    await expect(banner).toContainText("not here yet");
  });

  test("says nothing of the sort about a class tomorrow", async ({ page }) => {
    await page.goto(AT);
    await expect(page.getByText("minutes to go")).toHaveCount(0);
  });
});

test.describe("getting to it", () => {
  test("is linked from the session the schedule board shows", async ({ page }) => {
    // A route nothing links to is a route nobody finds — ADM-MEM-05 specified a button and
    // rendered none for as long as its screen existed.
    await useOwnerSession(page);
    await page.goto(`/schedule/${creds.bookedSessionId}`);
    const link = page.getByRole("link", { name: "Check people in" });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(new RegExp(`/desk/classes/${creds.bookedSessionId}`));
  });
});

test.describe("what a weaker credential is given", () => {
  test("a session without the roster read is refused the screen", async ({ page }) => {
    await useReaderSession(page);
    await page.goto(AT);
    await expect(page.locator(".ds-desk-row")).toHaveCount(0);
  });

  test("a front desk reading people but not bookings is refused too", async ({ page }) => {
    // The desk identity holds `people.person.read` and nothing of MOD-020, which is the
    // pair that proves the roster gate rather than the names one.
    await useDeskSession(page);
    await page.goto(AT);
    await expect(page.locator(".ds-desk-row")).toHaveCount(0);
  });
});

/** How many the header says are here, read from the figure rather than from the rows. */
async function presentCount(page: Page): Promise<number> {
  const text = await page.locator(".ds-page-head").innerText();
  const found = text.match(/(\d+) of \d+ here/);
  expect(found, `no "N of M here" in ${text}`).not.toBeNull();
  return Number(found![1]);
}

test.describe("the device strip above the desk", () => {
  /**
   * FD-08 · DEVICE STRIP · ALWAYS VISIBLE.
   *
   * > "The card reader is down and the strip says **what to do instead**, not just that it
   * > failed. Every degraded state on this strip names its fallback. Hardware failing
   * > silently is how a receptionist ends up apologising for something they could not see."
   *
   * The fixture carries one scanner in service that has never reported, which is the row
   * this whole component exists for -- and until FD-08 needed it, nothing in the fixture
   * produced a device a surface had to say anything about.
   */
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    // **A test that asserts a freshness has to create it.** `Working` means the device
    // reported within ten minutes, and the fixture's own report is what made that true --
    // so an assertion about a working row expires ten minutes after seeding and then reads
    // "Not responding", which looks exactly like a product regression. The fleet spec
    // learned this first and the strip inherits it: the device is reported healthy here, so
    // the freshness asserted is the freshness this test made.
    await reportHealthy(page);
    await page.goto(SOON);
  });

  test("sits above the screen rather than being a screen", async ({ page }) => {
    // A layout, so every `/desk` route carries it. "It sits above both Front Desk and POS at
    // all times" -- there is no POS here, which is a gap rather than a decision.
    const strip = page.locator(".ds-strip");
    await expect(strip).toBeVisible();
    const stripBox = await strip.boundingBox();
    const headBox = await page.locator(".ds-page-head").boundingBox();
    expect(stripBox!.y).toBeLessThan(headBox!.y);
  });

  test("names what to do instead, which is the requirement", async ({ page }) => {
    const row = page.locator('.ds-strip-row[data-state="degraded"]').first();
    await expect(row).toContainText("Studio A scanner");
    await expect(row).toContainText("Not responding");
    // **Not "type the name instead"**, which the canvas writes and this product cannot
    // honour: there is no member search here, so that advice fails at the keyboard.
    await expect(row).toContainText("Find the member on the class they booked");
  });

  test("puts what is broken above what is fine", async ({ page }) => {
    const states = await page.locator(".ds-strip-row").evaluateAll(
      (rows) => rows.map((row) => (row as HTMLElement).dataset.state));
    expect(states.length).toBeGreaterThan(1);
    expect(states[0]).toMatch(/down|degraded/);
    expect(states[states.length - 1]).toBe("working");
  });

  test("does not say all is well while a reader is out of service", async ({ page }) => {
    // **The defect this replaced.** Two out-of-service readers raise no attention, and the
    // strip said "everything this desk needs is responding" directly above both of them.
    await expect(page.locator(".ds-strip")).not.toContainText("Everything this desk needs");
  });

  test("marks the strip itself when something needs doing", async ({ page }) => {
    // An edge mark rather than a fill, and `aria-live` so it is announced -- a strip of
    // green rows is chrome and should not be read out on every navigation.
    await expect(page.locator(".ds-strip")).toHaveAttribute("data-attention", "yes");
    await expect(page.locator(".ds-strip")).toHaveAttribute("aria-live", "polite");
  });

  test("says which hardware it cannot see at all", async ({ page }) => {
    // The canvas draws a receipt printer and a card terminal; neither is a kind of device
    // MOD-021 registers, so a reader who took this strip for the whole desk would be wrong.
    await expect(page.locator(".ds-strip")).toContainText("receipt printer");
  });

  test("is refused rather than silent for a session that may not read devices",
    async ({ page }) => {
      // A strip that rendered nothing would be hardware failing silently with the silence
      // built into the product.
      await useDeskSession(page);
      await page.goto(SOON);
      await expect(page.locator(".ds-strip")).toContainText("may not read the hardware");
      await expect(page.locator(".ds-strip-row")).toHaveCount(0);
    });
});

/**
 * Report the fixture's turnstile as healthy, now, so the strip has a working row.
 *
 * The bearer token is the session cookie's value: `context.cookies()` can read an httpOnly
 * cookie where page JavaScript cannot, so no credential is typed and none is in this file.
 */
async function reportHealthy(page: Page) {
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name === "veyro_session")?.value;
  expect(token, "the browser session carries the bearer token").toBeTruthy();
  const response = await page.request.post(
    `${process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000"}/fleet/${creds.deviceId}/health`,
    {
      headers: {
        "X-Veyro-Tenant": creds.tenantId,
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      data: {
        latency_ms: 42, error_count: 0, storage_free_bytes: 8 * 1024 * 1024 * 1024,
        agent_version: "1.0.0", peripherals: {},
        correlation_id: crypto.randomUUID(),
      },
    },
  );
  expect(response.status(), await response.text()).toBe(201);
}
