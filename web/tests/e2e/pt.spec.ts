import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * **The browser's own zone is the hour the reader typed**, which `instantFrom` argues is the
 * honest reading of a desk booking an hour it is standing in -- so a spec that types `18:30`
 * is typing it in whatever zone the runner is in. Locally that is the club's and the class
 * clash is real; on CI it is UTC, so `18:30` is 21:30 at the club, the evening class is three
 * hours earlier and the refusal that comes back is the rota's rather than the coach's. The
 * test asserted "Already booked" and CI read "The rota does not cover this hour" -- both
 * correct, for two different hours. Pinning the zone to the club's makes the typed hour mean
 * one thing, and is also the ordinary case: a receptionist is in the building.
 */
test.use({ timezoneId: "Asia/Amman" });

/**
 * ADM-SCH-05 · SCHEDULE PT, against the real routes. ADR-0019.
 *
 * **Two members, because the canvas's figure and its button need different fixtures.** The
 * first holds two counted credits from their plan's own mapping, which is the figure the
 * consequence panel states — and pressing the button would spend one, so a suite that booked
 * on them would be green on a fresh fixture and red on the third run. The second holds an
 * *uncounted* entitlement, which is a real product state (a plan that includes unlimited
 * personal training) and is what makes the booking pressable for ever.
 *
 * **Each booking still takes a distinct hour**, because the coach's time is the one thing a
 * booking consumes whatever the credit says: a second run at the same instant is correctly
 * refused, and that refusal is itself one of the tests.
 */
// **From the file rather than from `process.env`.** `fixture.mjs` writes `.env.e2e.local` at
// mode 600 and nothing exports it -- so a spec reading the process environment gets empty
// strings, which rendered this screen's "which member is this for?" state and failed eight
// assertions about a page that was working.
//
// **The member with a *live* credit is the recent one, and that is the product being right
// rather than a fixture quirk.** The main member's membership started ninety days ago, and
// `grant_entitlement` dates a counted right to the billing period it was granted in -- so
// their two PT credits expired at the end of that first period, because nothing in this build
// rolls a period forward. `drawable_credits_on` therefore refuses them, correctly, and the
// panel says "sell a package first" for a member who paid for two sessions in August. The
// recent member started ten days ago, so their window is always a few days out whenever the
// fixture ran.
const { recentPersonId: PERSON, ptPersonId: PT_PERSON, coachResourceId: COACH,
        staffNoLoginPersonId: NO_CREDIT } = fixture();

/** A free weekday morning, far enough out that the coach's 18:00 class is not in the way. */
function slot(daysOut: number, hour: number): { day: string; clock: string } {
  const at = new Date(Date.now() + daysOut * 86_400_000);
  return {
    day: at.toISOString().slice(0, 10),
    clock: `${String(hour).padStart(2, "0")}:00`,
  };
}

/**
 * An hour no previous run has booked.
 *
 * **A booking consumes the coach's time whatever the credit says**, so the one test that
 * presses the button needs a slot of its own — and the first version keyed it on the clock's
 * minute, which collided with the run before it and failed on the second pass. That is this
 * repository's most-repeated harness finding, and running the suite twice in a row is the
 * only thing that finds it.
 *
 * 1,920 slots (twenty days × eight hours × twelve five-minute marks), cycled by the
 * millisecond clock: two runs seconds apart land on different ones, and the whole cycle is
 * longer than a fixture lives. Every one is inside the coach's 06:00–22:00 rota and clear of
 * the 18:00 class the fixture seeds daily.
 */
function freeSlot(): { day: string; clock: string } {
  const n = Math.floor(Date.now() / 1000) % 1920;
  const at = new Date(Date.now() + (7 + (n % 20)) * 86_400_000);
  const hour = 8 + (Math.floor(n / 20) % 8);
  const minute = (Math.floor(n / 160) % 12) * 5;
  return {
    day: at.toISOString().slice(0, 10),
    clock: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
  };
}

async function open(page: import("@playwright/test").Page, person: string) {
  await page.goto(`/schedule/pt?person=${person}`);
}

test.describe("the booking screen", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await open(page, PERSON);
  });

  test("draws the canvas's title, two fields and the button", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1 }))
      .toContainText("personal session");
    await expect(page.getByRole("combobox", { name: "Coach" })).toBeVisible();
    await expect(page.getByLabel("Day")).toBeVisible();
    await expect(page.getByLabel("When")).toBeVisible();
    await expect(page.getByLabel("Length in minutes")).toHaveValue("55");
    await expect(page.getByRole("button", { name: /Book/ })).toBeVisible();
  });

  test("says nothing about the cost until an hour is picked", async ({ page }) => {
    // A consequence panel over an unchosen hour would be a figure about nothing.
    await expect(page.getByRole("main")).toContainText("Pick a day and an hour");
    await expect(page.getByRole("button", { name: /Book/ })).toBeDisabled();
  });

  test("states the credit, what is left and when it expires", async ({ page }) => {
    const { day, clock } = slot(4, 9);
    await page.getByLabel("Day").fill(day);
    await page.getByLabel("When").fill(clock);
    const main = page.getByRole("main");
    // The canvas: "Uses 1 of her 3 remaining credits. Two left after this, expiring 30
    // November." Two here, because that is what the plan grants.
    await expect(main).toContainText("Uses 1 of the member’s 2 remaining credits");
    await expect(main).toContainText("One left after this");
    await expect(main).toContainText("Expiring");
    // **And the template is not what rendered**, which the three assertions above cannot
    // say. Both of those messages shipped as ICU brace-pipe strings -- `{one=...|other=...}`
    // -- which this catalogue treats as plain text, so the page printed every form at once
    // and each `toContainText` passed on a substring of the *template*. A substring
    // assertion cannot tell a rendered plural from its own unrendered form; this can.
    await expect(main).not.toContainText("|other=");
    await expect(main).not.toContainText("{");
    await expect(page.getByRole("button", { name: /use 1 credit/ })).toBeEnabled();
  });

  test("forgets an answer once the choice is no longer complete", async ({ page }) => {
    // **The answer carries the proposal it was about.** A quote is an answer about one coach
    // at one hour, so a panel left over from a previous choice is a figure a desk would act
    // on -- and the cheapest way to see that is to make the choice incomplete again: with
    // the key compared, `live` goes back to null and the "pick a day" note returns; without
    // it the stale panel stays. ADM-SCH-07's own derivation, proved rather than commented.
    const { day, clock } = slot(4, 9);
    await page.getByLabel("Day").fill(day);
    await page.getByLabel("When").fill(clock);
    await expect(page.getByRole("main")).toContainText("remaining credits");
    await page.getByLabel("Day").fill("");
    await expect(page.getByRole("main")).toContainText("Pick a day and an hour");
    await expect(page.getByRole("main")).not.toContainText("remaining credits");
  });

  test("names the hour this screen cannot do, rather than drawing a dead control",
    async ({ page }) => {
      const notYet = page.locator("section").filter({
        has: page.getByRole("heading", { name: "What this screen cannot do" }),
      });
      await expect(notYet).toContainText("Point of Sale");
      await expect(notYet).toContainText("weekly");
      await expect(notYet).toContainText("Nothing is sent");
    });

  test("is reached from the member's own credits", async ({ page }) => {
    // **The way in matters as much as the screen**: a route nothing links to is a route
    // nobody finds, which ADM-MEM-05's missing Add member and `/rota`'s stale gap note each
    // cost this app once. The link is on the entitlements table, because that is where the
    // credits are and the screen's whole subject is spending one.
    await page.goto(`/people/${PERSON}?tab=membership`);
    const link = page.getByRole("link", { name: /Book a personal session/ });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("personal session");
  });
});

test.describe("the two refusals the canvas draws", () => {
  test("a member with nothing to spend is told to sell a package", async ({ page }) => {
    await useOwnerSession(page);
    // **A staff member, who holds no personal-training credit.** The zero state needs a
    // person with no `service_credit` grant, and the fixture's staff are exactly that --
    // seeded for ADM-STF-01 and reused here rather than one more member nobody else reads.
    const nobody = NO_CREDIT;
    await open(page, nobody);
    const { day, clock } = slot(5, 10);
    await page.getByLabel("Day").fill(day);
    await page.getByLabel("When").fill(clock);
    const main = page.getByRole("main");
    await expect(main).toContainText("No personal-training credit");
    await expect(main).toContainText("Sell a package first");
    // **And the coach is not blamed.** The two refusals have different remedies, so a screen
    // that merged them would send a desk looking for another hour.
    await expect(main).not.toContainText("The coach is not free");
    await expect(page.getByRole("button", { name: /Book/ })).toBeDisabled();
  });

  test("a busy coach is a different sentence from a missing credit", async ({ page }) => {
    await useOwnerSession(page);
    await open(page, PT_PERSON);
    // The coach teaches at 18:00 every day in this fixture, which is the clash without
    // anything having to be booked first.
    const { day } = slot(3, 18);
    await page.getByLabel("Day").fill(day);
    await page.getByLabel("When").fill("18:30");
    const main = page.getByRole("main");
    await expect(main).toContainText("The coach is not free then");
    await expect(main).toContainText("Already booked");
    await expect(main).not.toContainText("No personal-training credit");
    // **And no resource id reaches the reader.** The banner rendered the server's own
    // `detail` -- "staff 86807d78-... is already held by Evening yoga flow" -- which is a
    // generator diagnostic, in English, with a uuid in it. The kind is worded from the
    // catalogue now; this is what says the diagnostic has not come back.
    await expect(main).not.toContainText(/[0-9a-f]{8}-[0-9a-f]{4}-/);
    await expect(page.getByRole("button", { name: /Book/ })).toBeDisabled();
  });
});

test.describe("the booking", () => {
  test("books the hour and says what is left", async ({ page }) => {
    await useOwnerSession(page);
    await open(page, PT_PERSON);
    const { day, clock } = freeSlot();
    await page.getByLabel("Day").fill(day);
    await page.getByLabel("When").fill(clock);
    // An uncounted entitlement: "nothing is deducted", which is why this is pressable on
    // every run.
    await expect(page.getByRole("main")).toContainText("not counted");
    const book = page.getByRole("button", { name: /^Book$/ });
    await expect(book).toBeEnabled();
    await book.click();
    // **"Booked", not "already booked".** The slot is unique per run and the idempotency key
    // is generated per submit, so a repeat here would mean something the module does not do.
    await expect(page.getByRole("main")).toContainText("Booked");
    await expect(page.getByRole("main")).toContainText("Dana Coach");
  });

  test("the booked hour is on the coach's week, marked as personal", async ({ page }) => {
    // **The whole reason a PT session is a `sch_sessions` row**: an inner join on
    // `template_id` would have dropped it from this grid, from the calendar and from the
    // conflict reader. The canvas draws `PT` against `CLS`, which this build could not tell
    // apart until `0036`.
    await useOwnerSession(page);
    await page.goto(`/rota?resource=${COACH}`);
    const legend = page.locator(".ds-rota-legend");
    await expect(legend).toContainText("A personal session is booked");
    await expect(legend).toContainText("A class is booked");
  });
});

test.describe("who may open it", () => {
  test("a reader without the schedule read is told so rather than shown a form",
    async ({ page }) => {
      await useDeskSession(page);
      await open(page, PERSON);
      await expect(page.getByRole("combobox", { name: "Coach" })).toHaveCount(0);
      await expect(page.getByRole("main")).toContainText(/not permitted|permission/i);
    });
});

test.describe("the screen reads in both languages", () => {
  test("the whole screen reads in Arabic", async ({ page }) => {
    await useOwnerSession(page);
    await open(page, PERSON);
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("جلسة شخصية");
    await expect(page.getByRole("main")).not.toContainText("Book a personal session");
  });

  test("no accessibility violations", async ({ page }) => {
    await useOwnerSession(page);
    await open(page, PERSON);
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
  });
});
