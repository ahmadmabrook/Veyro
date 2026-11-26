import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession, useReaderSession } from "./sign-in";

/**
 * ADM-PAY-09 · CASH RECONCILIATION — "Closing Layla's shift".
 *
 * **The screen could not exist until this session**, because `open_cash_session` and
 * `close_cash_session` had no reader at all: a drawer could be opened and the only way to
 * learn what was in it was to close it and read the refusal. The sixth instance of this
 * build's "a writer with no reader" shape.
 */

const creds = fixture();
const AT = "/payments/cash";

test.describe("the cash board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("shows the expected figure before anything is counted", async ({ page }) => {
    // **The canvas's own decision, and the one worth asserting:** "The expected figure is
    // shown before the count is entered. Hiding it would be a fraud control; showing it is
    // an accuracy control, and accuracy is the more common problem." A screen that revealed
    // it after the count would be a different control with the same layout.
    const drawer = page.locator(".ds-cash-drawer").first();
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText("Should be in the drawer");
    await expect(drawer).toContainText("JOD 138.00");
    // And the count is still empty, so the figure is not a consequence of one.
    await expect(drawer.locator('input[name="counted"]')).toHaveValue("");
  });

  test("the breakdown adds up to the figure beneath it", async ({ page }) => {
    // What makes the number checkable by the person holding the notes rather than one they
    // have to trust: 50.00 in, 96.00 taken, 8.00 out, 138.00 expected.
    const drawer = page.locator(".ds-cash-drawer").first();
    for (const line of ["JOD 50.00", "JOD 96.00", "JOD -8.00", "JOD 138.00"]) {
      await expect(drawer).toContainText(line);
    }
    // The entry count sits on the line it counts, as the canvas has it.
    await expect(drawer).toContainText("2 entries");
  });

  test("the variance appears as the count is typed, with the reason it needs", async ({
    page,
  }) => {
    // **Before the submit, not after it.** The reason is a field somebody fills while they
    // are looking at the difference, not a refusal they discover by pressing a button.
    const drawer = page.locator(".ds-cash-drawer").first();
    await expect(drawer.locator(".ds-cash-variance")).toHaveCount(0);
    await drawer.locator('input[name="counted"]').fill("135.50");
    const variance = drawer.locator(".ds-cash-variance");
    await expect(variance).toBeVisible();
    await expect(variance).toContainText("Short by");
    await expect(variance).toContainText("JOD 2.50");
    await expect(variance.getByLabel("What happened")).toBeVisible();
  });

  test("a count over the expected reads as over, not as a negative shortfall", async ({
    page,
  }) => {
    const drawer = page.locator(".ds-cash-drawer").first();
    await drawer.locator('input[name="counted"]').fill("140.00");
    await expect(drawer.locator(".ds-cash-variance")).toContainText("Over by");
    await expect(drawer.locator(".ds-cash-variance")).toContainText("JOD 2.00");
  });

  test("a drawer that balances asks for nothing", async ({ page }) => {
    // `check_close` deliberately has no branch refusing a note on a session that balanced,
    // and equally none demanding one.
    const drawer = page.locator(".ds-cash-drawer").first();
    await drawer.locator('input[name="counted"]').fill("138.00");
    await expect(drawer.locator(".ds-cash-variance")).toHaveCount(0);
    await expect(drawer).toContainText("balances");
  });

  test("the count is read in the currency's own minor units", async ({ page }) => {
    // **JOD is stored in fils and shown with two decimals**, and conflating the two would
    // make 135.50 read as 13.55 and post a 121.95 shortfall. The variance shown here is the
    // proof the scaling is right: 138.00 − 135.50 is 2.50 and nothing else.
    const drawer = page.locator(".ds-cash-drawer").first();
    await drawer.locator('input[name="counted"]').fill("135.50");
    await expect(drawer.locator(".ds-cash-variance")).toContainText("JOD 2.50");
    await expect(drawer.locator(".ds-cash-variance")).not.toContainText("JOD 121.95");
  });

  test("names the two things the canvas draws that this build does not have", async ({
    page,
  }) => {
    // A co-sign and a tolerance. Both are refusals with reasons rather than omissions, and
    // the tolerance is the unusual direction: this build is *stricter* than the design.
    const gaps = page.locator("section").filter({ hasText: "What this screen does not do yet" });
    await expect(gaps).toContainText("A co-sign");
    await expect(gaps).toContainText("A tolerance");
    await expect(gaps).toContainText("stricter rather than looser");
  });

  test("a closed drawer shows what it was counted at and why it was out", async ({
    page,
  }) => {
    const closed = page.locator("section").filter({ hasText: "Closed today" });
    await expect(closed).toContainText("Shop");
    await expect(closed).toContainText("JOD 17.50");
    await expect(closed).toContainText("JOD -2.50");
    await expect(closed).toContainText("change twice");
  });

  test("no accessibility violations", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("closing a drawer", () => {
  /**
   * **This test provisions its own drawer, and it has to.** A cash session is closed once
   * and `close_cash_session` has no reopen — correctly, because a till somebody signed off
   * and then re-opened is a till nobody can account for. So a test that closed the
   * fixture's drawer would pass on the first run against a fresh fixture and fail on the
   * second with nothing open to count, which is this repository's own rule about a suite
   * that spends something the product keeps: provision your own.
   *
   * It opens one through the API rather than the UI because there is no form for opening a
   * drawer — the canvas draws the close, and a form nobody specified would be invented
   * product.
   */
  test("counts it, states what happened, and posts the difference", async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);

    const unique = Date.now().toString(36);
    // **The bearer token is the session cookie's value**, which `context.cookies()` can
    // read where page JavaScript cannot — the fleet spec's idiom, so no credential is
    // typed and none is in this file.
    const cookies = await page.context().cookies();
    const token = cookies.find((cookie) => cookie.name === "veyro_session")?.value;
    expect(token, "the browser session carries the bearer token").toBeTruthy();
    const origin = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";
    const headers = {
      "X-Veyro-Tenant": creds.tenantId,
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
    // **The account is the fixture's and the session is this test's.** Creating a ledger
    // account is a stepped-up financial write and this session is AAL 1 by design; opening
    // a drawer on one is routine, which is the whole reason this screen has a form at all.
    //
    // **It opens the way a desk does, which this test used to get wrong across runs.** The
    // first version always drew a float from the safe -- and after one run that drawer still
    // holds what the close counted, so the second run's open is a *handover* and the safe is
    // refused: FD-07's own finding, which this spec reached by being run twice rather than by
    // anybody reasoning about it. So the standing figure comes from `/ledger/drawers`, the
    // read FD-07 added, and the open matches what the drawer is actually in.
    const standing = await page.request.get(
      `${origin}/ledger/drawers?location_id=${creds.locationId}`, { headers });
    expect(standing.ok(), await standing.text()).toBe(true);
    const mine = (await standing.json()).drawers.find(
      (one: { cash_account_id: string }) =>
        one.cash_account_id === creds.suiteTillAccountId);
    const held: number = mine?.expected_minor ?? 0;
    const alreadyOpen: string | null = mine?.open_session === null || mine === undefined
      ? null : String(mine.drawer_label);

    // A drawer this suite left open means a previous run was interrupted between opening and
    // closing. That one is this suite's to finish, so the test carries on with its label
    // rather than failing on its own earlier mess -- and it is told apart from a refused
    // float, which the first version conflated into one 409.
    let label = alreadyOpen;
    if (label === null) {
      const opened = await page.request.post(`${origin}/ledger/cash-sessions`, {
        headers,
        data: {
          location_id: creds.locationId,
          cash_account_id: creds.suiteTillAccountId,
          drawer_label: `Shift ${unique}`, currency: "JOD",
          // Count what is there on a handover and draw a float on an empty drawer, which is
          // the distinction the server derives from this same figure.
          opening_float_minor: held === 0 ? 10_000 : held,
          ...(held === 0
            ? { float_source_account_id: creds.safeAccountId }
            : {}),
          legal_entity_id: creds.legalEntityId,
          idempotency_key: `e2e-${unique}`, correlation_id: crypto.randomUUID(),
        },
      });
      expect([200, 201], await opened.text()).toContain(opened.status());
      label = `Shift ${unique}`;
    }

    await page.goto(AT);
    const drawer = page.locator(".ds-cash-drawer").filter({ hasText: label }).first();
    await expect(drawer).toBeVisible();
    // **The count is derived from what the drawer holds, 2.50 short of it.** A literal 97.50
    // was right only while the drawer was always funded with exactly 100.00, which is the
    // assumption the handover broke.
    const expected = held === 0 ? 10_000 : held;
    const short = (expected - 250) / 1000;
    await drawer.locator('input[name="counted"]').fill(short.toFixed(2));
    await drawer.getByLabel("What happened").fill("a member was given change twice");
    await drawer.getByRole("button", { name: "Close the drawer" }).click();

    // It leaves the open list and joins the closed one, with its variance and its sentence.
    await expect(drawer).toHaveCount(0);
    const closed = page.locator("section").filter({ hasText: "Closed today" });
    await expect(closed).toContainText(label);
    await expect(closed).toContainText("JOD -2.50");
    await expect(closed).toContainText("change twice");
  });
});

test.describe("a reader who may not open a drawer", () => {
  test("is told which permission, not that the product is broken", async ({ page }) => {
    // "A refusal and a failure are different facts", and a dead gate reaches a page in the
    // same shape as a refusal — which is why this says which of the four it is.
    await useReaderSession(page);
    await page.goto(AT);
    // **The finding is that a refusal is distinguished from a failure, not that a permission
    // id is printed.** This pinned the literal `finance.cash.session`, which is a dotted
    // backend identifier on an operator's screen -- the one thing the directive bars outright
    // -- and the page says the same thing in words a reader can take to whoever grants it.
    // What has to stay true: the reader is told what is needed, told which of the four
    // states this is, and shown no drawer.
    const main = page.locator("main");
    await expect(main).toContainText("running a till");
    await expect(main).not.toContainText(/\b[a-z]+\.[a-z_]+\.[a-z_]+\b/);
    await expect(main).toContainText(/permission|sign-in|could not/i);
    await expect(page.locator(".ds-cash-drawer")).toHaveCount(0);
  });
});
