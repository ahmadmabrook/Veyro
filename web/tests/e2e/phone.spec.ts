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
  // **The four hand-rolled tables left in this app are on these two tabs**, in
  // `membership-panels.tsx`, and they are the only thing the generic phone rule
  // `table { display: block }` still applies to -- every other table in the app is a
  // `DataGrid` with its own rule and its own scroll wrapper. Neither tab was swept, so
  // breaking that rule changed nothing on any surface in this list and the mutation that
  // names it came back uncaught: the rule was live and the page that depends on it was
  // missing. Found by running the sweep and measuring, not by reading the CSS.
  ["a member's membership", `/people/${creds.personId}?tab=membership`],
  ["a member's billing", `/people/${creds.personId}?tab=billing`],
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
  // **Twenty-four bars in a flex row**, which is twice the widest chart in the app and the
  // one whose width is purely a count. Below it four metric cells and two rows of chips.
  ["the attendance report", `/reports/attendance?site=${creds.locationId}`],
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

  /**
   * **The collapse itself, asserted directly, because the document-level sweep below cannot
   * see it any more.**
   *
   * `table { display: block }` at phone width is what makes `overflow-x` apply to a table at
   * all -- the rule's own comment calls it "the table scrolls inside itself rather than
   * widening the page". Breaking it used to make seven surfaces overflow the document. It no
   * longer makes any of them overflow, because every table here is now either a `DataGrid`
   * whose columns drop by priority until it fits or a hand-rolled one at `width: 100%`: the
   * protection is still correct and is redundant on every page that exists. So the mutation
   * naming it came back **uncaught** -- a rule nothing could prove, which is this
   * repository's own "a mutation that changes nothing is not evidence" from the other side.
   *
   * The property is directly measurable, so it is measured: a grid's table collapses to a
   * block and its cells with it, and the capability matrix is the exception the design makes
   * for itself and keeps table layout. Established by `getComputedStyle`, not by reading the
   * stylesheet.
   */
  for (const [label, path, selector, allowed] of [
    ["a grid table", "/members", ".ds-grid-table", ["block"]],
    // **`none` is expected and is the other half of the collapse**: a droppable cell is in
    // the DOM twice and visible once, so the set here is block-or-hidden. What must never
    // appear is `table-cell`, which is a cell still in table layout -- the collapse not
    // having happened.
    ["its cells", "/members", ".ds-grid-table td", ["block", "none"]],
    // "A column dropped from a matrix is a comparison a reader gets wrong", so this one
    // scrolls inside its wrapper instead -- and `display: block` on it is what used to let
    // its sticky header escape to the document root.
    ["the capability matrix", "/permissions", ".ds-matrix", ["table"]],
    // **The four hand-rolled tables, which are the only thing the *generic* phone rule still
    // reaches.** A grid gets `display: block` from the 599px collapse rule and the matrix is
    // exempt, so `table { display: block }` is provable on nothing else -- and these tabs
    // were not swept at phone width at all. They are `membership-panels.tsx`'s, on a member's
    // billing tab, and the rule is what makes `overflow-x` apply to them.
    ["a hand-rolled table", `/people/${creds.personId}?tab=billing`,
     "table:not(.ds-grid-table):not(.ds-matrix):not(.ds-week)", ["block"]],
  ] as const) {
    test(`${label} collapses as the design states at phone width`, async ({ page }) => {
      await useOwnerSession(page);
      await page.goto(path);
      await expect(page.locator(selector).first()).toBeVisible();
      const displays = await page.evaluate((css) => [...new Set(
        [...document.querySelectorAll(css)].map((el) => getComputedStyle(el).display))],
        selector);
      expect(displays.length, `${selector} on ${path} rendered nothing`).toBeGreaterThan(0);
      for (const display of displays) {
        expect(allowed, `${selector} on ${path} computed ${display}`).toContain(display);
      }
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
