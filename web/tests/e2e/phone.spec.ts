import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * No surface scrolls sideways on a phone.
 *
 * **Seven of thirteen pages did, and no test in four layers noticed**, because every
 * assertion in this suite is about text and structure and all of them pass at any width. A
 * page that scrolls sideways hides its own right-hand edge: on the schedule board "Free" and
 * "Status" were simply off the screen, and nothing in the product said so.
 *
 * The fix is two CSS rules -- a table scrolls inside itself, and a label/value grid collapses
 * and is allowed to shrink -- but the rules are not the evidence. This is: every surface, at
 * the narrowest width the design system claims to support, asserted to have no horizontal
 * scroll at all.
 */

const creds = fixture();
const PHONE = { width: 375, height: 812 };

const surfaces: [string, string][] = [
  ["the overview", "/"],
  ["the schedule board", "/schedule"],
  ["a session", `/schedule/${creds.bookedSessionId}`],
  ["the configuration board", "/configuration"],
  ["the operations board", "/operations"],
  ["the fleet board", "/fleet"],
  ["a device", `/fleet/${creds.deviceId}`],
  ["the organization", "/organization"],
  ["the door board", "/access"],
  ["a zone", `/access/${creds.zoneId}`],
  ["the permissions page", "/permissions"],
  ["the people list", "/people"],
  ["a member", `/people/${creds.personId}`],
  // Twelve bars in a flex row: the one chart here whose width is a count rather than a
  // layout, so it is the one most likely to push a phone sideways.
  ["a member's attendance", `/people/${creds.personId}?tab=attendance`],
  // MOD-018's board is the widest table in the app -- four money columns over a chart of
  // thirteen accounts -- so it is the one most likely to push the page sideways.
  ["the payments ledger", "/payments"],
  // Five columns, two of which stack a word over a sentence — and the message preview below
  // is the one block in the app holding a template body with `{{ }}` runs that cannot break.
  ["the recovery workspace", "/payments/recovery"],
  // A card per dispute, each with a four-line evidence list whose rows pair a mark
  // with prose — the layout most likely to put a mark on its own line at phone width.
  ["the dispute board", "/payments/disputes"],
  ["an invoice", `/finance/invoices/${creds.invoiceId}`],
  ["the finance board", "/finance"],
  ["the catalog board", "/catalog"],
  ["a product", `/catalog?product=${creds.productId}`],
  ["the reports index", "/reports"],
  // **The revenue report's grid grows a column per legal entity**, so it is the one table
  // here whose width depends on the tenant rather than on the design. The entity columns are
  // priority 3 and drop first, which is what this asserts in practice.
  ["the revenue report", "/reports/revenue"],
  ["the membership report", "/reports/membership"],
  // The widest table in the app: twenty areas against a column of prose.
  ["the privacy board", "/privacy"],
  ["the messages board", "/notifications"],
  ["the integrations board", "/integrations"],
  ["the members list", "/members"],
  // Four columns where two of them stack a derived sentence over a timestamp, which is the
  // shape most likely to force a minimum width on a cell.
  ["the staff list", "/staff"],
  ["a staff record", `/staff/${creds.staffWorkingPersonId}`],
  ["your account", "/account"],
];

test.describe("at phone width", () => {
  test.use({ viewport: PHONE });

  /**
   * **A droppable value is in the DOM twice and visible once**, which is the claim
   * `DataGrid`'s own docstring makes and which was false at the one width the mechanism
   * exists for. `.ds-col-p2 { display: none }` is specificity (0,1,0) and
   * `.ds-grid-table td { display: block }` is (0,1,1) and comes after it, so below 600px
   * every priority-2 and priority-3 cell rendered beside the secondary fragment of the same
   * value — 21 duplicated values on the members list, 21 on the payments ledger, on every
   * grid in the app.
   *
   * Four layers of tests could not see it: an assertion about text matches either copy, and
   * the sweep below measures horizontal scroll, which a duplicate does not cause. Found by
   * taking a screenshot and reading it, which is how this surface's defects keep being found.
   */
  for (const [label, path] of [
    ["the members list", "/members"],
    ["the payments ledger", "/payments"],
    ["the staff list", "/staff"],
  ] as const) {
    test(`${label} shows each dropped value once, not twice`, async ({ page }) => {
      await useOwnerSession(page);
      await page.goto(path);
      await expect(page.locator(".ds-grid-table").first()).toBeVisible();
      const counts = await page.evaluate(() => {
        const cells = [...document.querySelectorAll(
          ".ds-grid-table td.ds-col-p2, .ds-grid-table td.ds-col-p3")];
        return {
          dropped: cells.length,
          stillVisible: cells.filter((c) => getComputedStyle(c).display !== "none").length,
        };
      });
      expect(counts.dropped, `${path} has no droppable columns to prove this with`)
        .toBeGreaterThan(0);
      expect(counts.stillVisible,
        `${path} renders ${counts.stillVisible} dropped cells beside their own secondary line`)
        .toBe(0);
    });
  }

  for (const [name, path] of surfaces) {
    test(`${name} does not scroll sideways`, async ({ page }) => {
      await useOwnerSession(page);
      await page.goto(path);
      const overflow = await page.evaluate(() => ({
        by:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
      }));
      expect(overflow.by, `${path} overflows by ${overflow.by}px`).toBeLessThanOrEqual(0);
    });
  }

  test("a table that scrolls inside itself is still reachable from a keyboard", async ({
    page,
  }) => {
    // The rule that makes a table scroll is also the rule that creates a scrollable region,
    // and axe requires one to be focusable. Running the check at this width is the point:
    // every other axe run in this suite is at desktop width, where no table scrolls at all.
    await useOwnerSession(page);
    await page.goto("/operations");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
