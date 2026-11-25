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
  // **A week grid whose width is seven columns plus an hour label**, and the only other
  // place in this product where a sideways scroll is sanctioned. The cells are 26px marks
  // rather than text, so a reader at phone width is reading a scrollable region.
  ["the availability grid",
   `/rota?resource=${creds.coachResourceId}&from=${creds.rotaExceptionDay}`],
  ["the configuration board", "/configuration"],
  ["the localization screen", "/localization"],
  ["the dunning rules", "/payments/dunning"],
  ["the operations board", "/operations"],
  ["the fleet board", "/fleet"],
  ["a device", `/fleet/${creds.deviceId}`],
  ["the organization", "/organization"],
  ["the door board", "/access"],
  ["a zone", `/access/${creds.zoneId}`],
  ["the permissions page", "/permissions"],
  ["the people list", "/people"],
  // ADM-MEM-10's form. A fixed `max-inline-size` on a form is the shape that looks
  // safe at 1440 and clips at 375, and the interruption panel under the phone field
  // carries two controls on one row.
  ["the walk-in form", "/members/new"],
  // FD-06 is the one screen in this app at Touch density: 48px rows and a 44px button on
  // every row, which is the shape most likely to push a narrow screen sideways.
  ["the class check-in", `/desk/classes/${creds.deskSessionId}`],
  // FD-03 is at Touch density too, and its one `dl.facts` is the grid whose items are the
  // `dt` and `dd` themselves -- wrapping a pair in a div puts both labels on one row, which
  // the ledger paid for once.
  ["the denial screen", `/desk/denials/${creds.personId}`],
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
  // **ADM-MSH-07's sheet, which is behind a parameter and so invisible to a sweep of
  //    routes.** It holds the one layout in this screen that can push a page sideways: a
  //    row of two buttons where one label carries a money figure, beside a two-column
  //    `.facts` grid of fee parts. Neither is wide on a desktop and both are the shape
  //    this sweep exists for -- and a surface reachable only with a query string is
  //    exactly the kind that gets left out of a list of paths.
  // **The committed member, not the rolling one, because only they draw the grid.** The
  // comment above has claimed the `.facts` grid of fee parts since this entry was added and
  // it was not being measured: the breakdown is gated on there being more than one fee part,
  // and the rolling member has one. This member renders everything that one does plus the
  // two-row grid and the "Before you cancel" interruption, so it is a strict superset for a
  // geometry sweep -- and the grid is the component this repository already records a
  // row-wrapping defect in.
  ["a membership cancellation",
   `/people/${creds.buyOutPersonId}?tab=membership&cancel=1`],
  // ADM-MSH-06's sheet is a picker and a consequence block, both reached by a query string --
  // the kind of route a list of paths leaves out, as the cancellation sheet was until
  // somebody added it by hand.
  ["the plan-change sheet",
   `/people/${creds.personId}?tab=membership&plan=1`],
  // ADM-SCH-07's sheet: a select, a chip group, a consequence banner and a message body, all
  // above the roster that stays rendered -- and reached by a query string, which is the kind
  // of route a list of paths leaves out.
  ["the class-cancellation sheet",
   `/schedule/${creds.bookedSessionId}?cancel=1`],
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
  // A two-column money breakdown above a form, which is the label/value grid this sweep was
  // written for -- and the one screen here whose figures a reader checks against notes in
  // their hand, so a column that scrolled out of sight would be the worst place for it.
  ["the cash board", "/payments/cash"],
  ["an invoice", `/finance/invoices/${creds.invoiceId}`],
  ["the finance board", "/finance"],
  ["the catalog board", "/catalog"],
  // ADM-MSH-09's table is four columns with a figure and a count, and its sheet is a form
  // reached by a query string -- which is exactly the kind of route a list of paths leaves
  // out, as ADM-MSH-07's cancellation sheet was until somebody added it by hand.
  ["the plans table", "/plans"],
  ["the price sheet", `/plans?variant=${creds.clubVariantId}`],
  ["a product", `/catalog?product=${creds.productId}`],
  ["the reports index", "/reports"],
  // **MOD-026's three.** The task list is a six-column grid whose primary cell stacks a title
  // over a meta line, which is the shape that duplicated every droppable value on three other
  // grids below 600px; the sheet is four `MetricCell`s over a `Timeline` and five forms, which
  // is the densest stack of components on any screen here; and the resolved board is a grid
  // whose outcome column holds a tenant's own prose.
  // **MOD-027's two.** The board is five columns in a CSS grid, which is the one layout here
  // whose width is a column count rather than a table's -- a `repeat(5, minmax(0, 1fr))` with
  // a card in each is what `/permissions` overflowed by 125px for, so it is swept. And the
  // table is a six-column grid whose primary cell stacks a name over a meta line, which is
  // the shape that duplicated every droppable value on three other grids below 600px.
  ["the add-lead form", "/leads/new"],
  // **FD-05, which is the same two-field shell with a detection panel over it** -- and the
  // first `/desk` route in this sweep that is reachable without an id, so it carries FD-08's
  // device strip above a form rather than above a roster.
  ["the walk-in trial form", "/desk/trial"],
  // **ADM-SCH-03, which is seven fields and a live panel** -- the densest form on this
  // surface, and the one whose weekday chips are a seven-across group at 375px.
  [
    "the create-a-class form",
    `/schedule/new?location=${creds.locationId}`,
  ],
  // **FD-02, which is a field, a sentence and two touch rows** -- the rows are FD-06's own
  // family, and a match's meta line is the one place on this surface where a name, a club and
  // a bidi-isolated digit group share a line at 375px.
  ["the member lookup", "/desk/lookup?q=hala"],
  // **FD-07, which is a picker, a handover panel and a count on one narrow column.** The
  // close half of it is ADM-PAY-09's own form, already swept at `/payments/cash`; what is new
  // here is the drawer chip bar, which is a link row whose width is a count of tills.
  [
    "the shift screen",
    `/desk/shift?location_id=${creds.locationId}`,
  ],
  ["the lead board", "/leads"],
  ["the lead table", "/leads?view=table"],
  // The profile is a record header over four metric cells, a timeline and five forms,
  // which is the densest stack of components on any CRM screen.
  ["a lead profile", `/leads/${creds.ownedLeadId}`],
  // The trial state draws an extra section and a four-cell metric row, which is a different
  // layout from the sales one above and is the one with a 5,687-pixel zero-width box in its
  // history.
  ["a lead on a trial", `/leads/${creds.trialLeadId}`],
  // **Two states of ADM-CRM-07**, both reachable only with a query string or a seeded row --
  // the kind of surface a route list leaves out, which ADM-MSH-07's sheet had to be added by
  // hand for. The sheet is a radio group and a field; the lost state is a banner, three notes
  // and a button.
  ["the mark-lost sheet", `/leads/${creds.coldLeadId}?lost=1`],
  ["a lead that said no", `/leads/${creds.lostLeadId}`],
  // **The conversion quote, which is reachable only with a query string** -- so it is exactly
  // the kind of surface a route list leaves out, which ADM-MSH-07's cancellation sheet had to
  // be added by hand for. Two metric cells beside a definition list, at the width where
  // `.facts` collapses.
  ["a conversion quote",
    `/leads/${creds.trialLeadId}/convert?variant=${creds.clubVariantId}`],
  ["the task list", "/tasks"],
  ["an attention item", `/tasks/cases/${creds.moneyCaseId}`],
  ["resolved today", "/tasks/resolved"],
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
  // A form of three fields over a grid of four, which is the pair most likely to force a
  // width: the chips wrap and the table drops, and only one of those is measurable here.
  ["inviting someone", "/staff/invite"],
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

  test("the week grid really scrolls inside itself, rather than being contained empty",
    async ({ page }) => {
      // **The sideways-scroll assertion above cannot see this state, and it is the state that
      // shipped on `/permissions`.** A wrapper with `contain: layout` around a table pinned to
      // `inline-size: 100%` reports zero document overflow and has nothing to scroll: the
      // columns are clipped and unreachable, and every assertion about text still passes
      // because the cells are in the DOM. So the property is asserted from both sides -- the
      // page does not scroll, and the region does.
      //
      // The region is `tabIndex={0}` with a labelled `role="region"`, which is what makes a
      // scrollable area reachable without a mouse; axe requires that and the test above runs
      // it. Here the subject is the scrolling itself.
      await useOwnerSession(page);
      await page.goto(
        `/rota?resource=${creds.coachResourceId}&from=${creds.rotaExceptionDay}`);
      const region = page.locator(".ds-week-scroll");
      await expect(region).toBeVisible();
      const measured = await region.evaluate((el) => ({
        scrolls: el.scrollWidth - el.clientWidth,
        clientWidth: el.clientWidth,
        tableWidth: Math.round(
          (el.querySelector(".ds-week") as HTMLElement).getBoundingClientRect().width),
        focusable: (el as HTMLElement).tabIndex,
      }));
      // **The subject is the table *box*, not the scroller's scroll width**, and the
      // difference is the whole finding. Pinning the table to `inline-size: 100%` leaves its
      // cells overflowing the box they sit in, so the wrapper still reports a scrollable
      // width -- 117px of it -- while every column is squeezed and the design's 64rem is
      // gone. Asserting "the region scrolls" passes in that state, which is how the mutation
      // that removes `min-inline-size` first came back uncaught. The table has to be allowed
      // to *grow*, which is what `.ds-matrix-scroll`'s own comment says one screen over.
      expect(measured.tableWidth,
        "the week grid is pinned to its container, so its columns are squeezed")
        .toBeGreaterThan(measured.clientWidth);
      expect(measured.scrolls, "the region does not scroll, so the columns are unreachable")
        .toBeGreaterThan(0);
      expect(measured.focusable, "a scrollable region needs a keyboard").toBe(0);
    });
});
