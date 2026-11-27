import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useDeskSession, useOwnerSession } from "./sign-in";

/**
 * MOD-012's board, against a tenant with two installs, a validated connection and a run.
 *
 * **The fixture seeds a `critical` install beside an `important` one**, and gives the
 * critical one two of its three written obligations. That pair is what makes the obligations
 * column say anything: with only the important one it never fires, and with a complete
 * critical one it never differs from "satisfied". The board shipped with the check keyed on
 * `live_critical` -- a value the column never holds -- so every row said the obligations did
 * not apply, and only looking at a `critical` row saying that found it.
 *
 * **Nothing syncs.** The run's record counts are what a caller reported, and the page says so
 * next to them rather than letting a number read as data that moved.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the integrations board", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/integrations");
  });

  test("leads with the fact that nothing syncs", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
    await expect(page.getByText(/Nothing syncs in this build/)).toBeVisible();
  });

  test("names the critical install missing a written obligation", async ({ page }) => {
    // **The defect this assertion exists for.** The check was keyed on `live_critical`, which
    // `int_installs.criticality` never holds, so every install reported "not required at this
    // criticality" -- including a `critical` one carrying traffic without its exit plan.
    const installs = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Installed" }) });
    // **`alert`, not `status`.** An error-tone Alert is `role="alert"`; only the other three
    // tones are `status`. An install carrying traffic without its written obligations is an
    // error, which is the point of the tone and the reason this assertion has to name it.
    await expect(installs.getByRole("alert")).toContainText(
      "Carrying traffic without the written obligations",
    );
    // **An exact cell, because `hasText` is a case-insensitive substring over the whole
    // row** -- and "critical" is inside the header's own "Criticality". Fifth time in this
    // suite, and the first where the wrong row was a table header.
    const critical = installs
      .getByRole("row")
      .filter({ has: page.getByText("critical", { exact: true }) });
    // **`exit_plan` is this app's own field name**, and the row words the obligation
    // instead -- the stored-vocabulary-as-a-label defect, in a money-adjacent column.
    await expect(critical).toContainText("An exit plan");
    await expect(critical).not.toContainText("exit_plan");
  });

  test("says the obligations do not bind an install below that criticality", async ({
    page,
  }) => {
    // The other half of the pair: a column that only ever says one thing says nothing.
    const installs = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Installed" }) });
    const important = installs
      .getByRole("row")
      .filter({ has: page.getByText("important", { exact: true }) });
    await expect(important).toContainText("not required at this criticality");
  });

  test("says a validation was recorded, not performed", async ({ page }) => {
    // There is no provider to call, so the state is a claim by a named party at a time --
    // the same shape as MOD-014's contact verification and MOD-021's commissioning.
    const connections = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Connections" }) });
    await expect(connections).toContainText("validated");
    await expect(connections).toContainText("recorded by a named party, not performed here");
    await expect(connections).toContainText("members.read");
  });

  test("shows a credential as a reference and says the vault does not exist", async ({
    page,
  }) => {
    const credentials = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Credential references" }) });
    await expect(credentials).toContainText("vault://");
    await expect(credentials).toContainText("Current");
    // The same sentence the fleet board says about device certificates, deliberately: four
    // screens saying it four ways would read as four gaps.
    await expect(page.getByText(/one gap, not four/)).toBeVisible();
  });

  test("says a run's counts were reported rather than observed", async ({ page }) => {
    const runs = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Connector runs" }) });
    const row = runs.getByRole("row").filter({ hasText: "members" }).first();
    await expect(row).toContainText("120");
    await expect(row).toContainText("reported by the caller, not observed here");
  });

  test("says the conflict policy is decided and never applied", async ({ page }) => {
    await expect(page.getByText(/decided and never applied/)).toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

test.describe("a session that may not read integrations", () => {
  test("gets no Integrations entry in the navigation", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Sections" });
    await expect(nav.getByRole("link", { name: "Integrations" })).toHaveCount(0);
  });

  test("is refused the board rather than shown an empty install list", async ({ page }) => {
    await useDeskSession(page);
    await page.goto("/integrations");
    await expect(page.locator("main").getByRole("status")).toContainText(/not permitted/i);
    await expect(page.getByText("vault://")).toHaveCount(0);
  });
});
