import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn } from "./sign-in";

/**
 * ADR-0014 — a club manager can use the product.
 *
 * **Until this, a brand- or location-scoped role was refused every gated read.**
 * `authz.check` asked at the tenant-wide scope and `permissions_of` lets a broad assignment
 * cover a narrow one and never the reverse, so a location-scoped grant contributed nothing.
 * Four modules record the same gap in almost the same words, and the practical consequence was
 * that every tenant in this build had exactly one kind of user: one who holds everything
 * everywhere.
 *
 * **This spec signs in as its own identity rather than adopting the saved owner session**, for
 * the reason the passkey spec does: the owner is tenant-wide, which is precisely the case this
 * is not about. It spends a few logins against MOD-011's thirty-a-minute budget and nothing
 * shared.
 */

const creds = fixture();

test.describe("a location-scoped session", () => {
  test("can read the staff list at all, and is told it is bounded", async ({ page }) => {
    await signIn(page, { email: creds.clubEmail, password: creds.clubPassword });
    await page.goto("/staff");

    // **The read happens**, which is the whole finding: before ADR-0014 this was the gate's
    // "not permitted" page.
    await expect(page.getByRole("heading",
      { name: "The team, and who can still open the product" })).toBeVisible();
    await expect(page.getByText(/not permitted/i)).toHaveCount(0);

    // And the screen says the list is their club rather than the tenant -- a bounded list
    // read as the whole team is a team that is not there.
    await expect(page.getByText(/This list is your club only/)).toBeVisible();

    // **And the withheld names offer a remedy this reader has, which needed a second fix.**
    // Every name here is masked -- correctly: a legal name is MOD-014's `identity` class and
    // this role holds `people.person.read`, which opens no class at all. What was wrong was
    // the sentence. The banner said "this session has not presented a second factor" and
    // linked to the step-up, whoever was reading, so the first caller ADR-0014 let onto this
    // page was sent to spend a recovery code on a remedy that lifts nothing: a step-up raises
    // assurance and this reader's problem is a permission they do not hold at any assurance.
    //
    // That is MOD-008's `reachable` finding in a sentence instead of a field, and it is the
    // split the schedule board already makes for a masked change reason. The gate decides it.
    //
    // **Found by asserting what the reader sees** rather than that the page rendered -- and
    // the first diagnosis was wrong: I read it as the mask resolving at the tenant-wide
    // default scope, fixed that, and the markers stayed, because the cause was the missing
    // permission all along. Reproduce before diagnosing, which here meant reading the role.
    // **Both halves**, because the first fix was only the banner and the rows outnumber it
    // five to one: the per-row marker takes a reason key and twelve screens pass the step-up
    // one, which `WithheldLink`'s own docstring anticipated and nobody supplied a third case
    // for. One element matching the step-up sentence would be the banner; five were the rows.
    await expect(page.getByText(/need a stronger sign-in/)).toHaveCount(0);
    await expect(page.getByText(/does not include reading/)).toBeVisible();
    await expect(page.getByText(/would not change it/)).toBeVisible();
    // Never the offer, because following it is what would cost the recovery code.
    await expect(page.getByRole("link", { name: /stronger sign-in|step up/i }))
      .toHaveCount(0);
    // And the rows still say they are withheld rather than reading as blank -- MOD-014's own
    // rule, which is the half a reader would lose if the marker were simply dropped.
    await expect(page.getByText(/withheld from this session/).first()).toBeVisible();
  });

  // **The other half, and the one that keeps the change fail-closed** (ADR-0014 D4). A route
  // that has not been taught to filter would return the whole tenant to this session, so
  // `permit` refuses it -- which is exactly the behaviour every untaught route had before.
  test("is still refused a route that has not opted in", async ({ page }) => {
    await signIn(page, { email: creds.clubEmail, password: creds.clubPassword });
    await page.goto("/members");
    await expect(page.getByText(/not permitted/i)).toBeVisible();
  });

  // **ADM-CC-02's own sentence**: "the rail is generated from his role rather than greyed".
  // A rail of one entry is what that means in a build where one route has opted in -- and the
  // entries whose pages would refuse this caller are absent rather than shown and dead, which
  // is the navigation's own standing rule.
  test("gets a rail generated from their role rather than a greyed one", async ({ page }) => {
    await signIn(page, { email: creds.clubEmail, password: creds.clubPassword });
    await page.goto("/");
    const rail = page.getByRole("navigation", { name: "Sections" });
    await expect(rail.getByRole("link", { name: "Staff" })).toBeVisible();
    // Members needs the same permission and has not opted in, so its page would refuse: the
    // entry is absent rather than a link to a 403.
    await expect(rail.getByRole("link", { name: "Members" })).toHaveCount(0);
  });

  // The tenant-wide reader is unchanged, which is ADR-0014 D3 and is load-bearing: every
  // route, test and fixture here assumes one.
  test("the owner sees no boundary notice at all", async ({ page }) => {
    await signIn(page);
    await page.goto("/staff");
    await expect(page.getByRole("heading",
      { name: "The team, and who can still open the product" })).toBeVisible();
    await expect(page.getByText(/This list is your club only/)).toHaveCount(0);
  });
});
