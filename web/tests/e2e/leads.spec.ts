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

const { coldLeadId, ownedLeadId, touredLeadId } = fixture();

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
    // **At least the four seeded ones, counted rather than fixed.** None is a member, so
    // every lead in the tenant is open -- and the add-lead spec opens one more, which is the
    // point of that spec: a literal here would be an assertion about how many *other* specs
    // have run, which is the consumable-state trap this repository has paid for four times.
    // What the figure must do is come from `GET /crm/board` rather than from the page's rows,
    // so the shape is what is asserted and the floor is what the fixture guarantees.
    const figures = page.locator("#main .ds-page-figures");
    await expect(figures).toHaveText(/\d+ open leads · \d+ going cold/);
    const open = Number((await figures.textContent() ?? "").match(/(\d+) open leads/)?.[1]);
    expect(open).toBeGreaterThanOrEqual(4);
  });

  test("the On trial column is drawn and no longer explains itself", async ({ page }) => {
    // **This asserted "nothing marks a product as a trial"**, which was the *consequence* of
    // a gap rather than the finding: the finding was that a column with nothing in it is
    // drawn with its reason rather than hidden, because hiding it makes the board read as
    // four stages. ADR-0010 D7 settled the marker and the server derives the column from
    // MOD-017, so there is no reason left to carry -- and a test insisting on one is the gap
    // note outliving its gap.
    await page.goto("/leads");
    const column = page.locator("#main").getByRole("region", { name: /^On trial,/ });
    await expect(column).toBeVisible();
    await expect(column.getByText(/marks a product as a trial/)).toHaveCount(0);
    // **And the column is populated**, which is the end-to-end evidence that the derivation
    // reaches the board: the fixture seeds one trialist and the count is the server's answer
    // over every lead rather than the page's over the cards it loaded.
    await expect(column).toContainText("1");
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
      // **The shape of the age, not a literal.** This asserted "just now", which
      // `sinceLabel` returns only under an hour -- so the test passed for sixty minutes
      // after each seeding and failed afterwards, which CI never sees because CI provisions
      // immediately before the suite. This repository records that trap three times; it is
      // the same one, in a test asserting a freshness nothing creates.
      await expect(card).toContainText(/just now|\d+[hd]$/);
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
    // **The four seeded leads each have a row, and the count is a floor rather than a
    // literal.** The add-lead spec creates one in this tenant, so an exact count would be an
    // assertion about which other specs have run -- and the property worth holding is that
    // every seeded lead is drawn as its own link, which is what the table is for.
    const rows = grid.getByRole("row").filter({ has: page.getByRole("link") });
    expect(await rows.count()).toBeGreaterThanOrEqual(4);
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
    // Reworded when the trial became expressible: the conversion rate is still uncounted and
    // the reason is now the window rather than the marker.
    await expect(gaps.getByText(/nothing counts a conversion/)).toBeVisible();
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

  test("the profile carries the lead's own facts and its timeline", async ({ page }) => {
    // ADM-CRM-03. The name is withheld at this assurance, so what is asserted is everything
    // this module owns: the source, the interests, the stage, the touchpoint and the four
    // metrics the slice can answer.
    await page.goto(`/leads/${coldLeadId}`);
    const main = page.locator("#main");
    await expect(main.getByText("from Sweifieh open day")).toBeVisible();
    await expect(main.getByText(/interested in Classes/)).toBeVisible();
    await expect(main.getByText("unassigned")).toBeVisible();
    await expect(main.getByRole("heading", { name: /Touchpoints/ })).toBeVisible();
  });

  test("a lead with no touchpoint says the clock runs from its creation", async ({ page }) => {
    // **The empty timeline is a sentence rather than a blank**, because an absent list reads
    // as a lead nobody has spoken to *and* as a screen that failed to load -- and the first
    // is the fact the cold rule is computed from.
    await page.goto(`/leads/${coldLeadId}`);
    await expect(page.locator("#main").getByText(/clock the pipeline reads runs from/))
      .toBeVisible();
  });

  test("a touchpoint is rendered with its kind and its prose", async ({ page }) => {
    await page.goto(`/leads/${touredLeadId}`);
    const main = page.locator("#main");
    await expect(main.getByText("Toured").first()).toBeVisible();
    await expect(main.getByText("walked the floor with Yasmin")).toBeVisible();
  });

  test("the five write forms are offered, because every permission here is routine",
    async ({ page }) => {
      // Elsewhere in this app a write form is absent because its permission is a stepped-up
      // financial one; none of MOD-027's is, which is what makes this the second module with
      // a full set of working forms.
      await page.goto(`/leads/${coldLeadId}`);
      const main = page.locator("#main");
      for (const label of ["Record it", "Move to Contacted", "Claim this lead", "Set it",
        "Add"]) {
        await expect(main.getByRole("button", { name: label, exact: true })).toBeVisible();
      }
    });

  test("a toured lead is offered no stage move, because the pipeline has no edge",
    async ({ page }) => {
      // "A button the module will refuse is worse than no button": `toured` is the last sales
      // stage and the two columns after it are what a membership answers.
      await page.goto(`/leads/${touredLeadId}`);
      const main = page.locator("#main");
      await expect(main.getByText(/last sales stage/)).toBeVisible();
      await expect(main.getByRole("button", { name: /^Move to/ })).toHaveCount(0);
    });

  test("an owned lead is offered the release and not the claim", async ({ page }) => {
    // One control, because the server refuses a no-op: assigning the owner a lead already has
    // is a 409, since a write that changed nothing would read as a handover somebody made.
    await page.goto(`/leads/${ownedLeadId}`);
    const main = page.locator("#main");
    await expect(main.getByRole("button", { name: "Release it" })).toBeVisible();
    await expect(main.getByRole("button", { name: "Claim this lead" })).toHaveCount(0);
  });

  test("the next action is shown and offers to be cleared where there is one",
    async ({ page }) => {
      await page.goto(`/leads/${ownedLeadId}`);
      const main = page.locator("#main");
      await expect(main.getByText("call back about the 17:00 tour").first()).toBeVisible();
      await expect(main.getByRole("button", { name: "Clear it" })).toBeVisible();
    });

  test("an interest already recorded is not offered again, and can be taken back",
    async ({ page }) => {
      // The cold lead was seeded interested in classes and PT, so only the third is offered.
      //
      // **This asserted "cannot be taken back yet" and slice 3 closed that gap.** The note
      // was MOD-027's own recorded one -- `crm_lead_interests` had no UPDATE grant, so a tick
      // was permanent on a routine permission -- and the withdrawal is the remedy ADR-0010
      // D11 owed. The note went with the gap in the same change, which is this repository's
      // rule about a gap list being a claim about the product, and what is asserted instead
      // is the control that replaced it plus the absence of the claim that is no longer true.
      await page.goto(`/leads/${coldLeadId}`);
      const main = page.locator("#main");
      await expect(main.getByRole("checkbox", { name: "Gym only" })).toBeVisible();
      await expect(main.getByRole("checkbox", { name: "Classes" })).toHaveCount(0);
      await expect(main.getByRole("button", { name: /Take back — Classes/ })).toBeVisible();
      await expect(main).not.toContainText("cannot be taken back yet");
    });

  test("what the trial card still cannot answer is named on the profile", async ({ page }) => {
    // **This asserted "nothing in this build marks one"**, which ADR-0010 D7 made false --
    // the clock, the visits and the engagement reading are drawn now while a trial runs, and
    // `trial.spec.ts` is where that is proved. What is left is the canvas's "all spin": the
    // class count is a count, and naming a class the read did not identify would be the
    // confident wrong answer MOD-014's own 360 was bitten by.
    await page.goto(`/leads/${coldLeadId}`);
    await expect(page.locator("#main").getByText(/counts classes by what they were/))
      .toBeVisible();
  });

  test("a lead id nobody holds says so rather than failing", async ({ page }) => {
    await page.goto("/leads/00000000-0000-4000-8000-000000000000");
    await expect(page.locator("#main").getByText(/no lead with that id/)).toBeVisible();
  });

  test("no accessibility violations on the profile", async ({ page }) => {
    await page.goto(`/leads/${ownedLeadId}`);
    const scan = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(scan.violations).toEqual([]);
  });

  test("the rail reaches the board", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("navigation").getByRole("link", { name: "Leads" }))
      .toHaveAttribute("href", "/leads");
  });
});
