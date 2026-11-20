import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession, useReaderSession } from "./sign-in";

const creds = fixture();

/**
 * Report this device as healthy, now.
 *
 * **A test that asserts a freshness has to create it.** `Online` means the device reported
 * within ten minutes, and the fixture's own health report is what made that true -- so this
 * assertion used to expire ten minutes after seeding and then read `Late`, which looks exactly
 * like a product regression. CI provisions immediately before the suite and never saw it; a
 * local run an hour later saw it every time. The sibling of this suite's rule about budgets.
 *
 * The bearer token is the session cookie's value, which is what the sign-in action stores --
 * `context.cookies()` can read an httpOnly cookie where page JavaScript cannot, so no
 * credential is typed and none is in this file.
 */
async function reportHealthy(page: import("@playwright/test").Page) {
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

/**
 * MOD-021's surfaces, against the real fleet.
 *
 * **The fixture seeds three shapes on purpose**, because one healthy turnstile cannot show
 * what this board is for: a door that works, a door that cannot be put into service because
 * paragraph 4175's commissioning is incomplete, and a device that is not a door at all. Every
 * assertion below is about telling those three apart.
 */
test.describe("the fleet board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/fleet");
  });

  test("lists every device with its state and whether it is reachable", async ({ page }) => {
    // The freshness this test is about, created by this test. See `reportHealthy`.
    await reportHealthy(page);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Devices", level: 1 })).toBeVisible();
    const board = page.locator("table");
    await expect(board.getByRole("row").filter({ hasText: "North turnstile" })).toContainText(
      "Online",
    );
    await expect(board.getByRole("row").filter({ hasText: "South turnstile" })).toContainText(
      "provisioned",
    );
    await expect(
      board.getByRole("row").filter({ hasText: "Reception scanner" }),
    ).toContainText("Never reported");
  });

  test("says reachability is worked out rather than stored", async ({ page }) => {
    // Nothing asks a device for its state and nothing records one, so a board that read as
    // live would claim a freshness the product does not have. **The worker's offline sweep
    // runs on a schedule now and changes nothing here**, which the lead says in as many
    // words -- the earlier wording was "nothing polls on a schedule", and leaving it would
    // have been a page making a claim the build had outgrown.
    await expect(page.getByText(/nothing stores it and nothing asks a device for it/))
      .toBeVisible();
    await expect(page.getByText(/what was true when the page was loaded/)).toBeVisible();
    await expect(page.getByText(/changes nothing on this board/)).toBeVisible();
  });

  test("labels the count and the clock, so neither reads as the other", async ({ page }) => {
    // **A bare number after a timestamp reads as part of it.** The footer said
    // "As of 2026-11-20 00:02 · 3", and the 3 is a device count with nothing saying so.
    const board = page.locator("section").filter({ hasText: "As of" });
    await expect(board).toContainText("devices");
    // And every instant on this board is UTC, which matters now that the schedule board
    // converts into a site's own zone -- a reader with one local-time screen reads the next
    // one as local too.
    await expect(board).toContainText("UTC");
  });

  test("does not call an unfinished or unreachable-but-idle device an incident", async ({
    page,
  }) => {
    // `blocks_operation` is `active` *and* `offline` together. The scanner has never reported
    // and the south turnstile is half-installed; neither is somebody's problem right now, and
    // listing them as problems is how an alert channel gets muted.
    const attention = page.locator("section").filter({ hasText: "Needs somebody" }).first();
    await expect(attention).toContainText("No device in service is unreachable");
    await expect(attention.getByRole("link")).toHaveCount(0);
    await expect(attention).toContainText(/deliberately in maintenance/);
  });

  test("keeps a serial number left-to-right inside an Arabic document", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL("/fleet");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const serial = page.locator('[dir="ltr"]').filter({ hasText: /^SN-/ }).first();
    await expect(serial).toBeVisible();
  });

  for (const theme of ["light", "dark"] as const) {
    test(`no accessibility violations: fleet, ${theme}`, async ({ page }) => {
      if (theme === "dark") {
        await page.getByRole("button", { name: "Dark" }).click();
        await page.waitForURL("/fleet");
      }
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

test.describe("a device", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("names every commissioning test that is still outstanding", async ({ page }) => {
    const creds = fixture();
    await page.goto(`/fleet/${creds.pendingDeviceId}`);
    const block = page.locator("section").filter({ hasText: "Commissioning" }).first();
    // **All seven, with which are done.** A list of only the missing ones cannot be told from
    // a list of everything when nothing is missing, and the question is "what is left before
    // this door can open".
    await expect(block.getByText("Outstanding")).toHaveCount(3);
    await expect(block.getByText("Recorded")).toHaveCount(4);
    await expect(block).toContainText("emergency_unlock");
    await expect(block).toContainText("power_loss");
    // It is a block, not a warning: activation and every unlock are refused.
    await expect(block).toContainText(/block rather than a warning/);
  });

  test("shows a fully commissioned door with nothing outstanding", async ({ page }) => {
    const creds = fixture();
    await page.goto(`/fleet/${creds.deviceId}`);
    const block = page.locator("section").filter({ hasText: "Commissioning" }).first();
    await expect(block.getByText("Outstanding")).toHaveCount(0);
    await expect(block.getByText("Recorded")).toHaveCount(7);
  });

  test("says a credential here is not a key anything checks", async ({ page }) => {
    const creds = fixture();
    await page.goto(`/fleet/${creds.deviceId}`);
    // There is no vault in this build, so no signature is verified: the device's identity is
    // what somebody recorded -- and MOD-022 opens doors on it.
    await expect(page.getByText(/No signature is verified anywhere here/)).toBeVisible();
    await expect(page.getByText(/opens doors on that identity/)).toBeVisible();
  });

  test("says a device that moves no barrier is not an access point", async ({ page }) => {
    await page.goto("/fleet");
    await page.getByRole("link", { name: "Reception scanner" }).click();
    await page.waitForURL(/\/fleet\/[0-9a-f-]{36}$/);
    await expect(page.getByText("It moves no barrier")).toBeVisible();
    // And it has no commissioning block at all, because the fire code is about barriers.
    await expect(page.getByRole("heading", { name: "Commissioning" })).toHaveCount(0);
  });

  test("an unknown or malformed device id is a message, not a 500", async ({ page }) => {
    await page.goto("/fleet/11111111-1111-4111-8111-111111111111");
    await expect(page.locator("main").getByRole("status")).toContainText(/No such device/);
    await page.goto("/fleet/not-a-uuid");
    await expect(page.locator("main").getByRole("status")).toContainText(/No such device/);
  });
});

test.describe("a session that may not read devices", () => {
  test.beforeEach(async ({ page }) => {
    await useReaderSession(page);
  });

  test("gets no Devices entry in the navigation", async ({ page }) => {
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Devices" })).toHaveCount(0);
  });

  test("is refused the board rather than shown an empty one", async ({ page }) => {
    await page.goto("/fleet");
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("North turnstile")).toHaveCount(0);
  });
});
