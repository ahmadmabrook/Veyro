import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { useOwnerSession } from "./sign-in";

/**
 * ADM-MSH-09 · PLANS & PRICING · OWNER ONLY.
 *
 * The canvas is a table and a sheet whose whole argument is one disclosure: "2,140 members are
 * on this plan. 890 are inside a fixed-term commitment and keep 55.00 until it ends. The other
 * 1,250 move at their next renewal, the earliest on 22 August" — with the note that it "is
 * computed *before* the change is saved, not reported after. A price rise is the most
 * consequential action in Admin and the only one where the blast radius is stated in members
 * rather than currency."
 *
 * **Nothing here presses the save**, and that is a bound on this layer rather than a gap in the
 * screen. `catalog.price.write` is financial class, so the write needs a step-up, and a step-up
 * spends one of the owner's five recovery codes per run — this repository has four recorded
 * tests whose green depended on how many times the suite had been run, every one of them a
 * budget somebody else needed. What the spec proves instead is every refusal, which is where
 * the control actually lives: the button is disabled until a figure, a date and the typed
 * confirmation are all given, and `writePrice` re-checks the confirmation on the server.
 *
 * **The two plans that cannot be re-priced are seeded**, because neither branch could be
 * reached otherwise — a published product with no in-window price, and one whose price in force
 * sits in a book nobody activated. The second is the branch that matters most: `create_price`
 * never reads the book's status, so the screen refuses a write the server would accept.
 */

// The display names are fixture constants rather than generated keys, so the spec names them
// directly. Their product keys carry a timestamp; their names do not.
const UNSELLABLE = "Off-peak (unpriced)";
const DEAD_BOOK = "Corporate (draft book)";
const AT = "/plans";
// The suite's own four tags. `region` -- "all page content is contained by landmarks" -- is
// axe's *best-practice* set rather than WCAG, and it fires 127 times on the app shell, which
// sits above the landmarks deliberately. Narrowing to the convention rather than to hide
// something: every scan in this suite uses these four.
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("the plans table", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  test("lists the plans with a figure in the currency's display precision", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Plans and pricing", exact: true }))
      .toBeVisible();
    // JOD is stored in fils and shown with two decimals, so the Club plan's 55,000 minor units
    // read as 55.00 — the one conflation `@/lib/cash` exists to prevent.
    const club = page.getByRole("row").filter({ has: page.getByRole("link", { name: "Club" }) });
    await expect(club.getByRole("cell", { name: /55\.00/ })).toBeVisible();
  });

  // `effective_from` is a timestamptz and the canvas's column is a date. The frame is UTC and
  // the header says so once, because a price book is tenant-wide and carries no club zone to
  // convert into -- the same reason the member timeline is UTC.
  test("renders the price date as a date, labelled on the column", async ({ page }) => {
    await expect(page.getByRole("columnheader", { name: "Price set (UTC)" })).toBeVisible();
    const club = page.getByRole("row").filter({ has: page.getByRole("link", { name: "Club" }) });
    await expect(club.getByRole("cell", { name: /^\d{4}-\d{2}-\d{2}$/ })).toBeVisible();
  });

  test("says the member count is per plan rather than a total", async ({ page }) => {
    // The ACTIVE column is `price_change_impact`'s `on_this_plan`, one request per row.
    const gold = page.getByRole("row")
      .filter({ has: page.getByRole("link", { name: "Gold membership" }) });
    await expect(gold).toBeVisible();
  });

  // **A published plan the till cannot sell is the row an owner needs to notice**, and MOD-016
  // records it as reachable with nothing changing a status.
  test("marks a plan with no price in force rather than showing a blank", async ({ page }) => {
    const row = page.getByRole("row")
      .filter({ has: page.getByRole("link", { name: UNSELLABLE }) });
    await expect(row.getByText("No price in force")).toBeVisible();
  });

  // The figure is real — it was written — so it stays, with the marker saying what is untrue
  // of it. Dropping the number would hide the thing to act on.
  test("keeps the figure on a dead book and says the book is not active", async ({ page }) => {
    const row = page.getByRole("row")
      .filter({ has: page.getByRole("link", { name: DEAD_BOOK }) });
    await expect(row.getByText("Its price book is not active")).toBeVisible();
    await expect(row.getByRole("cell", { name: /30\.00/ })).toBeVisible();
  });

  test("names what it does not do, including which of the three conditions", async ({ page }) => {
    await expect(page.getByText("Which book wins is not answered here")).toBeVisible();
    await expect(page.getByText("No entitlements column")).toBeVisible();
  });

  test("has no accessibility violations", async ({ page }) => {
    const scan = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(scan.violations).toEqual([]);
  });
});

test.describe("the price sheet", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto(AT);
  });

  async function openSheet(page: import("@playwright/test").Page, plan: string) {
    await page.getByRole("link", { name: plan, exact: true }).click();
    await expect(page.getByTestId("price-sheet")).toBeVisible();
  }

  test("opens as a parameter on the table, with a way out", async ({ page }) => {
    await openSheet(page, "Club");
    await expect(page).toHaveURL(/\/plans\?variant=/);
    await expect(page.getByTestId("price-sheet")
      .getByRole("heading", { name: /Changing the price of Club/ })).toBeVisible();
    // A permanently-open destructive form has no way out, which is why it is a parameter and
    // not a modal this app does not have.
    await page.getByTestId("price-sheet").getByRole("link", { name: "Close" }).click();
    await expect(page.getByTestId("price-sheet")).toHaveCount(0);
  });

  test("refuses to re-price a dead book, naming the book and its status", async ({ page }) => {
    await openSheet(page, DEAD_BOOK);
    const sheet = page.getByTestId("price-sheet");
    await expect(sheet.getByText("The price in force is in a book nobody activated"))
      .toBeVisible();
    // The sentence names the book, because activating it is a different act from re-pricing.
    await expect(sheet.getByText(/is draft, and a sale only resolves/)).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Save the new price" })).toHaveCount(0);
  });

  test("refuses to re-price a plan with nothing to supersede", async ({ page }) => {
    await openSheet(page, UNSELLABLE);
    await expect(page.getByTestId("price-sheet")
      .getByText("This plan has no price in force")).toBeVisible();
  });

  test("holds the save until a figure, a date and the typed figure", async ({ page }) => {
    await openSheet(page, "Club");
    const sheet = page.getByTestId("price-sheet");
    const save = sheet.getByRole("button", { name: "Save the new price" });
    await expect(save).toBeDisabled();

    // The blast radius appears as the figure is typed, which is the canvas's own requirement.
    await expect(sheet.getByTestId("blast-radius")).toHaveCount(0);
    await sheet.getByLabel("New price").fill("58.00");
    await expect(sheet.getByTestId("blast-radius")).toBeVisible();
    await expect(sheet.getByTestId("blast-radius")).toContainText("Raising Club from");
    await expect(save).toBeDisabled();

    // A date next, and not one in the past.
    await sheet.getByLabel("Effective from").fill("2020-01-01");
    await expect(sheet.getByText("Not a date in the past.")).toBeVisible();
    await expect(save).toBeDisabled();
    await sheet.getByLabel("Effective from").fill("2099-01-01");

    // And the canvas's tier-3 control: `type "58.00" to confirm`.
    const confirm = sheet.getByLabel(/Type .* to confirm/);
    await expect(confirm).toBeVisible();
    await confirm.fill("55.00");
    await expect(sheet.getByText("That is not the figure above.")).toBeVisible();
    await expect(save).toBeDisabled();
    await confirm.fill("58.00");

    // **Still held, and by the one thing a field cannot clear.** Every refusal above is gone
    // -- no message is on any field -- and `catalog.price.write` is financial class, so an
    // ordinary password session cannot press this whatever it types. The page says which it
    // is and offers the step-up, which is ADM-MSH-03's precedent: the honest cost is one
    // recovery code per twelve-hour window rather than one per act.
    await expect(sheet.getByText("That is not the figure above.")).toHaveCount(0);
    await expect(sheet.getByText("Not a date in the past.")).toHaveCount(0);
    await expect(save).toBeDisabled();
    await expect(sheet.getByText("Writing a price needs a stronger sign-in.")).toBeVisible();
    await expect(sheet.getByRole("link", { name: /sign in|Raise|stronger/i })).toBeVisible();
  });

  test("refuses the price it already is, and the same amount written shorter", async ({ page }) => {
    await openSheet(page, "Club");
    const sheet = page.getByTestId("price-sheet");
    await sheet.getByLabel("New price").fill("55.00");
    await expect(sheet.getByText(/That is the price it is already/)).toBeVisible();
    // An amount, not a string: 55 is the same figure as 55.00.
    await sheet.getByLabel("New price").fill("55");
    await expect(sheet.getByText(/That is the price it is already/)).toBeVisible();
    await expect(sheet.getByTestId("blast-radius")).toHaveCount(0);
  });

  test("names a figure it cannot parse", async ({ page }) => {
    await openSheet(page, "Club");
    const sheet = page.getByTestId("price-sheet");
    await sheet.getByLabel("New price").fill("fifty-eight");
    await expect(sheet.getByText("That is not an amount in this currency.")).toBeVisible();
  });

  test("has no accessibility violations with the sheet open", async ({ page }) => {
    await openSheet(page, "Club");
    const scan = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(scan.violations).toEqual([]);
  });
});
