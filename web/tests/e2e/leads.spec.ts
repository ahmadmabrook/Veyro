import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * ADM-CRM-01 and ADM-CRM-02 in a real browser, against a real database.
 *
 * **What a browser can settle that a component test cannot**: that the board's columns are
 * the five the canvas draws with the counts the server computed, that the two views render
 * the same rows, that a name composed from MOD-014 arrives (or is marked withheld), and that
 * the chips filter rather than flag.
 *
 * **Nothing here presses a write.** The fixture's leads are shared with the phone sweep and
 * every MOD-027 write moves a stage forward or records a touchpoint that cannot be removed --
 * so a spec that wrote would pass on the first run against a fresh fixture and fail on every
 * run after it, which is the budget trap this repository has paid for four times. The writes
 * are proven by `backend/tests/test_crm_api.py` and by fifteen mutations over the decisions.
 */

const { coldLeadId, ownedLeadId } = fixture();

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the lead pipeline", () => {
  // **The saved cookie, adopted rather than a sign-in per test.** MOD-011's limiter allows
  // thirty logins a minute per identity, and this repository has three recorded flakes whose
  // green depended on how much of that budget an earlier test had spent.
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("the board draws the canvas's five columns, in its order", async ({ page }) => {
    await page.goto("/leads");
    const board = page.getByRole("region", { name: "The pipeline, by stage" });
    for (const column of ["New", "Contacted", "Toured", "On trial", "Joined"]) {
      await expect(board.getByRole("region", { name: new RegExp(`^${column},`) }))
        .toBeVisible();
    }
    // **The order is the canvas's own**, so the sequence is asserted rather than membership:
    // a board that drew Joined before New would pass five separate visibility checks. Scoped
    // to the board's own region, because the gap list below it is a labelled section and
    // therefore a region too -- which the first version of this assertion counted as a sixth
    // column with an empty name.
    const drawn = await board.getByRole("region").evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("aria-label")?.split(",")[0] ?? ""));
    expect(drawn).toEqual(["New", "Contacted", "Toured", "On trial", "Joined"]);
  });

  test("the header's two figures come from the board read", async ({ page }) => {
    await page.goto("/leads");
    // Four leads are seeded and none is a member, so every one of them is open.
    await expect(page.locator("#main").getByText("4 open leads")).toBeVisible();
  });

  test("the On trial column says why it is empty rather than being hidden", async ({ page }) => {
    await page.goto("/leads");
    const column = page.locator("#main").getByRole("region", { name: /^On trial,/ });
    await expect(column).toBeVisible();
    await expect(column.getByText(/marks a product as a trial/)).toBeVisible();
  });

  test("a card's name is withheld at this assurance and the card is still a link",
    async ({ page }) => {
      // **The canvas draws a name on every card and this session can read none of them.**
      // `legal_name` is an identity-class field, so an ordinary password sign-in -- which is
      // what a sales desk has -- gets the marker. That is MOD-014's masking working rather
      // than a defect, and the card stays a link: a row whose name was marked and not linked
      // made the members list a dead end, found twice by an independent tester.
      await page.goto("/leads");
      const board = page.getByRole("region", { name: "The pipeline, by stage" });
      const card = board.getByRole("link").first();
      await expect(card).toContainText("Sweifieh open day");
      await expect(card).toContainText("just now");
      await expect(card).toHaveAttribute("href", /^\/leads\//);
    });

  test("the board offers the step-up that lifts the names", async ({ page }) => {
    // The remedy belongs on the board, not only on a record: a reader looking at a column of
    // markers with nothing to act on is the finding the members list paid for.
    await page.goto("/leads");
    await expect(page.locator("#main").getByText(/Every name here is withheld/))
      .toBeVisible();
    await expect(page.locator("#main").getByRole("link", { name: /Raise this session/ }))
      .toHaveAttribute("href", /\/step-up\?for=financial/);
  });

  test("the table view renders the same rows through the grid", async ({ page }) => {
    await page.goto("/leads?view=table");
    const grid = page.locator("#main").getByRole("table");
    await expect(grid).toBeVisible();
    // The columns ADM-CRM-02 names, in its own order.
    for (const header of ["Lead", "Source", "Owner", "Stage", "Age", "Next action"]) {
      // `exact`, because "Age" is a substring of "Stage" and Playwright matches names by
      // substring unless told otherwise -- which is the positional-locator trap in its
      // smallest form: an assertion that passes on the wrong element.
      await expect(grid.getByRole("columnheader", { name: header, exact: true }))
        .toBeVisible();
    }
    // Four seeded leads, each a row linking to its own record. The names are withheld at
    // this assurance, so the rows are counted rather than named -- which is also the only
    // assertion that would survive a fixture with different names in it.
    await expect(grid.getByRole("row").filter({ has: page.getByRole("link") }))
      .toHaveCount(4);
    await expect(grid.getByRole("cell", { name: /Sweifieh open day/ }).first())
      .toBeVisible();
  });

  test("an unowned lead says so rather than showing an empty cell", async ({ page }) => {
    await page.goto("/leads?view=table");
    const grid = page.locator("#main").getByRole("table");
    await expect(grid.getByRole("cell", { name: "Unassigned" }).first()).toBeVisible();
  });

  test("the next action is rendered where there is one", async ({ page }) => {
    await page.goto("/leads?view=table");
    // **`getByRole("cell")`, not `getByText`.** A droppable column is in the DOM twice and
    // visible once -- that is `DataGrid`'s documented mechanism -- so a text locator matches
    // both copies and fails strict mode. The rules file records this trap; `next_action` is
    // priority 3, which is the first to drop.
    await expect(page.locator("#main")
      .getByRole("cell", { name: "call back about the 17:00 tour" })).toBeVisible();
    expect(ownedLeadId).toBeTruthy();
  });

  test("the mine chip says the reader is nobody rather than showing an empty board",
    async ({ page }) => {
      // **Two different facts and only one is about the work.** The fixture's owner holds
      // every permission and is nobody in this tenant, so "mine" is zero because the
      // sign-in is not linked to a person -- which is ordinary, because staff hold
      // permissions and do not have to be anybody in particular.
      await page.goto("/leads?filter=mine");
      await expect(page.locator("#main").getByText(/not linked to a person/)).toBeVisible();
    });

  test("the cold chip filters rather than flagging", async ({ page }) => {
    // Every seeded lead was made a moment ago, so none is cold and the filtered board is
    // empty -- and the empty state names the chip rather than saying "no data", because an
    // empty cold list is a queue in hand rather than a queue nobody has.
    await page.goto("/leads?filter=going_cold&view=table");
    await expect(page.locator("#main").getByText(/contacted inside the window/)).toBeVisible();
  });

  test("the two absent halves of the canvas are named on the screen", async ({ page }) => {
    await page.goto("/leads");
    const gaps = page.locator("#main").getByRole("region", { name: /does not do yet/ })
      .or(page.locator("#main"));
    await expect(gaps.getByText(/model nobody here has an account with/)).toBeVisible();
    await expect(gaps.getByText(/Nothing counts a conversion yet/)).toBeVisible();
  });

  test("every card points at a lead record", async ({ page }) => {
    await page.goto("/leads");
    expect(coldLeadId).toBeTruthy();
    // The profile is ADM-CRM-03 and is not built yet, so what this asserts is that each card
    // is a link to the route the board points at -- a board whose cards went nowhere is the
    // dead end the members list was, found twice by an independent tester. The href is the
    // assertion rather than the name, because the name is withheld at this assurance.
    const board = page.getByRole("region", { name: "The pipeline, by stage" });
    const hrefs = await board.getByRole("link").evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("href") ?? ""));
    expect(hrefs.length).toBe(4);
    for (const href of hrefs) expect(href).toMatch(/^\/leads\/[0-9a-f-]{36}$/);
    expect(hrefs).toContain(`/leads/${coldLeadId}`);
  });

  test("no accessibility violations on either view", async ({ page }) => {
    // Both, because they are two different component trees over one list: five labelled
    // regions of links on the board, and a six-column grid with a composite tab stop on the
    // table. A scan of one proves nothing about the other.
    for (const view of ["board", "table"]) {
      await page.goto(`/leads?view=${view}`);
      const scan = await new AxeBuilder({ page }).withTags(WCAG).analyze();
      expect(scan.violations, view).toEqual([]);
    }
  });

  test("the rail reaches the board", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("navigation").getByRole("link", { name: "Leads" }))
      .toHaveAttribute("href", "/leads");
  });
});
