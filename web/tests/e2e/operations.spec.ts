import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * The operations board, against the real event plane and a worker that really ran.
 *
 * **The fixture runs `python -m app.worker --once` as its last step**, so these assertions are
 * about rows a scheduled job actually wrote rather than about an empty screen with an
 * explanation on it. That is what makes the two halves of the board distinguishable here: the
 * relay drained the outbox, so pending events are zero and the page says why; and the
 * deliveries it created are still pending, because no name in this build has a handler behind
 * it and nothing about the worker changes that.
 *
 * **The assertions are about which kind of number is being shown.** A page that rendered a
 * backlog with an alarm beside it would cry wolf on every ordinary use of the product; one
 * that rendered it bare would let somebody conclude the relay is working. Saying which is the
 * feature, and a zero on this screen is now a sentence rather than an absence.
 */
/**
 * Drain the outbox, the way the fleet spec reports its own device healthy.
 *
 * **A test that asserts a freshness has to create it**, and "zero pending events" is one: the
 * fixture's `python -m app.worker --once` drains what the seeding wrote, and then the browser
 * suite itself writes more -- `access.spec` presents a credential, which records a decision,
 * which appends `access.denied` to the outbox. So this assertion passed immediately after
 * seeding and failed once the access suite had run before it, which is a green that depends
 * on spec order rather than on the product. The same family as this repository's three
 * budget-spending tests, and found the same way: by running the suite again.
 *
 * `POST /events/dispatch` is the relay the worker job calls, so this drains it with the same
 * code path rather than asserting around the problem.
 */
async function drainOutbox(page: import("@playwright/test").Page) {
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name === "veyro_session")?.value;
  expect(token, "the browser session carries the bearer token").toBeTruthy();
  const response = await page.request.post(
    `${process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000"}/events/dispatch`,
    {
      headers: {
        "X-Veyro-Tenant": fixture().tenantId,
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      data: { correlation_id: crypto.randomUUID() },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
}

test.describe("the operations board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/operations");
  });

  test("shows the outbox drained by the relay and the deliveries nothing handles", async ({
    page,
  }) => {
    await expect(page.getByRole("heading", { name: "Operations", level: 1 })).toBeVisible();
    await drainOutbox(page);
    await page.reload();
    const outbox = page.locator("section").filter({ hasText: "Event outbox" }).first();
    // **Zero pending events is the assertion, and it used to be the opposite one.** Before the
    // worker existed this suite asserted the number was *not* zero, because nothing drained
    // it. The fixture's tick dispatched every event the seeding wrote, so a non-zero here now
    // means the relay did not run.
    const pending = outbox.locator("dd").first();
    await expect(pending).toHaveText(/^0/);
    // The deliveries the relay created are still waiting, and always will be.
    const deliveries = outbox.locator("dd").nth(1);
    await expect(deliveries).not.toHaveText("0");
  });

  test("says the relay is running, which is the half a worker changed", async ({ page }) => {
    const outbox = page.locator("section").filter({ hasText: "Event outbox" }).first();
    await expect(outbox).toContainText(/The relay is running/);
    await expect(outbox).toContainText(/within about fifteen seconds/);
  });

  test("still says a delivery nobody handles is expected, which a worker did not change", async ({
    page,
  }) => {
    const outbox = page.locator("section").filter({ hasText: "Event outbox" }).first();
    await expect(outbox).toContainText(/no name in this build has a handler behind it/);
  });

  test("shows every scheduled job and what it did for this tenant", async ({ page }) => {
    const jobs = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Scheduled jobs" }) });
    // Eight jobs, and the registry is what decides that -- a job added without a declared
    // name cannot record a metric at all, so a ninth row here means a ninth job was wired.
    // **The count is a tripwire on purpose**, which is why it is a literal rather than a
    // property: wiring a job should bring somebody to this file. The seventh is MOD-011's
    // objective evaluation, which is also what made the next test's locator fail; the eighth
    // is MOD-013's digest close.
    await expect(jobs.locator("tbody tr")).toHaveCount(8);
    await expect(jobs).toContainText("events.relay");
    await expect(jobs).toContainText("access.replay_sweep");
    // The fixture ran the worker once, so no job may read as never run.
    await expect(jobs.getByText("none recorded")).toHaveCount(0);
    // And nothing failed: a failure here is a real one, since the tick is the real binary.
    await expect(jobs.getByText(/A job failed in this window/)).toHaveCount(0);
  });

  test("says a burst of runs after a restart is expected rather than a fault", async ({
    page,
  }) => {
    const jobs = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Scheduled jobs" }) });
    // **Not "recorded by the worker itself".** That phrase is in the block's lead paragraph
    // as well as in the gaps list, so asserting it proved the lead and left the gaps list
    // removable in silence -- the "two things answer the same locator" trap, found by the
    // mutation sweep rather than by reading. This phrase is only in the gaps.
    await expect(jobs).toContainText(/the worker process's memory/);
    await expect(jobs).toContainText(/a burst here after a deployment is expected/);
  });

  test("keeps a dead letter apart from a backlog, because that one is a fault", async ({
    page,
  }) => {
    // **Scoped by the heading, not by the text.** The outbox section carries "Dead letters"
    // as one of its row labels, so a `hasText` filter matches it first -- which is the "two
    // things answer the same locator" trap this suite has now hit three times.
    const letters = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Dead letters" }) });
    await expect(letters).toContainText(/used its whole retry budget/);
    await expect(letters).toContainText("Nothing is quarantined");
  });

  test("keeps the no-handler disclosure above the routing table, not inside its empty case", async ({
    page,
  }) => {
    // It used to live in the "nothing is subscribed" message, so the day a subscription
    // existed -- which the fixture now creates -- the page stopped saying the one thing a
    // reader looking at routing most needs to know.
    const routing = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Routing" }) });
    await expect(routing).toContainText("No name in this build has a handler behind it");
    await expect(routing).toContainText("member_projection");
  });

  test("says an empty objective list means nobody set a threshold", async ({ page }) => {
    // **Scoped by the heading, not by the text**, for the fourth time in this file -- and
    // this one was predicted by the comment two tests up. `hasText: "Objectives"` matched the
    // *Scheduled jobs* section the hour `observability.evaluate_objectives` was wired, so a
    // test about the objectives block began asserting against the jobs block and failed on a
    // sentence that was rendered correctly a few hundred pixels below. A section filter on a
    // word is coupled to that word appearing in one section, and a job name is exactly the
    // sort of thing that puts it in another.
    const objectives = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Objectives" }) });
    // **This asserted "an objective nobody runs raises no alert"**, which was true for as
    // long as nothing evaluated one on a schedule and became false the hour the worker
    // started -- a gap note outliving its gap, in the sentence a reader of an empty list
    // sees. What still needs saying is which of the two an empty list is, and the answer
    // moved: it used to be "nothing is watching" and is now "nobody set a threshold".
    await expect(objectives).toContainText(/every five minutes/);
    await expect(objectives).toContainText(/nobody has set a threshold/);
    await expect(objectives).not.toContainText(/raises no alert/);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: operations, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/operations");
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a session that may not read the event plane", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no Operations entry in the navigation", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Operations" })).toHaveCount(0);
  });

  test("is refused each block rather than shown four empty ones", async ({ page }) => {
    await page.goto("/operations");
    // **Five permissions, five refusals.** An empty dead-letter table somebody may not see
    // reads as "nothing is quarantined", which is a different fact -- and a scheduled-jobs
    // block they may not see must not read as a worker that is not running, which is why
    // `relayVerdict` keeps `no_evidence` apart from `stopped`.
    const refusals = page.locator("main").getByRole("status").filter({ hasText: "Not permitted" });
    await expect(refusals).toHaveCount(5);
    await expect(page.getByText("Nothing is quarantined")).toHaveCount(0);
    await expect(page.getByText(/is a worker that is not running/)).toHaveCount(0);
  });
});
