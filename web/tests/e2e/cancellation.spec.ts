import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { useOwnerSession } from "./sign-in";

/**
 * ADM-MSH-07 · CANCEL — the sheet's **content**, which nothing had ever read off the page.
 *
 * The phone sweep already carries this route, so the sheet's geometry was covered; its
 * figures were not, and the fixture had no contract with a term, so the canvas's own case --
 * "his 12-month commitment runs to March. Cancelling now triggers a two-month fee of
 * JOD 80.00" -- had never been drawn at all.
 *
 * **Seeding it is what found a defect, and that is the argument for this file.**
 * `commitmentLine` says one of four sentences and the fixture produced exactly one of them,
 * so three had never rendered. Of those three, `held_to_term` turned out to be *unreachable*:
 * it was keyed on `leaving_early`, which is "access ends before the term does", and where a
 * contract forbids an early exit the lifecycle pushes the effective date **to** the term end
 * -- so the flag goes false exactly when the member is most firmly held, and such a member
 * was told their commitment "has been served" nine months early while being denied the freeze
 * offer whose whole subject is keeping a commitment intact.
 *
 * A hand-written component fixture had "proved" that branch with a quote the server cannot
 * emit. Only a real membership, priced by the real lifecycle, could say otherwise — which is
 * this repository's own rule about vacuous evidence, met from a direction it had not been met
 * from before.
 *
 * **Nothing here cancels anything.** A cancellation is one-way and there is no un-cancel, so
 * a browser test that spent one per run would be the budget shape this repository has paid
 * for five times. `test_commercial_api` drives the write against memberships it makes itself.
 * What a browser proves and a backend test cannot is that the member is told the right thing
 * before the button.
 */

const creds = fixture();
const sheet = (personId: string) => `/people/${personId}?tab=membership&cancel=1`;

/** Scoped by its heading, never by `hasText`: a job name or a row label elsewhere on the
 *  page puts a section's own word into a sibling, which this suite has been bitten by. */
const block = (page: import("@playwright/test").Page) =>
  page.locator("section").filter({
    has: page.getByRole("heading", { name: "Cancel this membership" }),
  });

test.describe("what the sheet tells a member about their commitment", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("names the term and the buy-out for the canvas's own member", async ({ page }) => {
    await page.goto(sheet(creds.buyOutPersonId));
    const sheetBlock = block(page);

    // The canvas's first sentence, with the term length read off the page rather than the
    // timezone being named — the schedule board's hard-won distinction.
    await expect(sheetBlock).toContainText("A 12-month commitment runs to");
    await expect(sheetBlock).toContainText("and this leaves it early");

    // **JOD 80.00 is the canvas's figure**, and it is two months of a JOD 40.00 membership
    // computed by `cancellation_fee` rather than by anything here. It is also the only
    // figure on this sheet that does not move: `early_termination_minor` is months times the
    // agreement amount, full stop.
    await expect(sheetBlock).toContainText("Leaving the commitment early");
    await expect(sheetBlock).toContainText("JOD 80.00");

    // **The headline is deliberately not asserted as a figure.** It is the buy-out plus the
    // part of the current period already used, and monthly periods tiling from a start
    // ninety days back put the period boundary near the notice date on some calendar days
    // and not others — so the total is JOD 120.00 most of the year and a few fils under it
    // the rest. A test asserting it would be green depending on the day it ran, which is the
    // class of flake this repository has paid for four times. The period *line* is what is
    // stable, and that it is present beside the buy-out is the thing worth proving: the
    // breakdown block is gated on there being more than one part, so until a committed
    // member existed it had never rendered at all.
    await expect(sheetBlock).toContainText("The period already used");
    await expect(sheetBlock).toContainText("Cancelling now costs");

    // The notice sentence, which is the canvas's third fact.
    await expect(sheetBlock).toContainText("after the 30 days' notice");

    // And the interruption, whose committed half is true because the term is running.
    await expect(sheetBlock).toContainText("Before you cancel");
    await expect(sheetBlock).toContainText("leaves the commitment standing");
  });

  test("tells a member held to their term that it holds, not that it was served", async ({
    page,
  }) => {
    // **The regression, named for what it said rather than for the fix.** This member is
    // nine months inside a twelve-month commitment on a contract that sells no way out, and
    // the sheet told them it "has been served".
    await page.goto(sheet(creds.heldToTermPersonId));
    const sheetBlock = block(page);

    await expect(sheetBlock).toContainText("does not allow leaving it early");
    await expect(sheetBlock).toContainText("access ends then rather than after notice");
    await expect(sheetBlock).not.toContainText("has been served");

    // A freeze is the alternative that keeps this commitment intact, and this is the member
    // it was withheld from — the offer is keyed on whether a commitment is running, not on
    // whether access ends before it.
    await expect(sheetBlock).toContainText("Before you cancel");
    await expect(sheetBlock).toContainText("leaves the commitment standing");

    // One part, so no breakdown: a line reading "leaving the commitment early · 0.00" states
    // a price for something that is not on offer.
    await expect(sheetBlock).not.toContainText("Leaving the commitment early");
  });

  test("says the term has been served where it actually has", async ({ page }) => {
    // The one member for whom that sentence is true, so the assertion above is a distinction
    // rather than a blanket ban on the string.
    await page.goto(sheet(creds.servedTermPersonId));
    const sheetBlock = block(page);

    await expect(sheetBlock).toContainText("has been served");
    await expect(sheetBlock).not.toContainText("does not allow leaving it early");
    // No commitment left to keep, and this member came in yesterday, so neither half of the
    // freeze argument holds and the interruption is absent rather than hedged.
    await expect(sheetBlock).not.toContainText("Before you cancel");
  });

  test("says nothing about a commitment where the contract has none", async ({ page }) => {
    // The rolling member — the only one of the four this fixture used to carry, which is how
    // three sentences went unrendered for as long as they did.
    await page.goto(sheet(creds.personId));
    const sheetBlock = block(page);

    await expect(sheetBlock).not.toContainText("commitment runs to");
    await expect(sheetBlock).not.toContainText("has been served");
    await expect(sheetBlock).not.toContainText("does not allow leaving it early");
    // Still priced and still dated, because a rolling membership is the ordinary case.
    // **"Access ends", not "Access ends on":** this contract gives no notice, so the
    // effective date is today and the sheet says "Access ends today." instead. The two are
    // different messages and the prefix is what both say -- asserting the dated one here
    // was a bug in this spec, caught by rendering the page rather than by reasoning about
    // which of the pair a contract with no notice period takes.
    await expect(sheetBlock).toContainText("Cancelling now costs");
    await expect(sheetBlock).toContainText("Access ends");
  });
});
