import { randomUUID } from "node:crypto";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn, useOwnerSession } from "./sign-in";

/**
 * MOD-007's account surface, and the first screens in this app that write.
 *
 * **One test here spends a product budget, so it spends its own.** Stepping up consumes a
 * recovery code and reissuing invalidates every earlier one; doing that as the owner would
 * pull the recovery code out from under every other spec that steps up, and the failure would
 * arrive in a different file reading "that was not accepted". The fixture provisions a fourth
 * identity for exactly this, which is the rule `CLAUDE.md` records after three instances of
 * it: consume a budget nobody else depends on, or provision your own.
 *
 * **The page closes a gap the web README recorded against itself**: a step-up spends a code,
 * TOTP and passkeys are unverifiable here, and there was no screen for reissuing -- so a
 * reader who stepped up five times was out of second factors with no path back.
 */

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const API = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";

test.describe("the account page as a password-only session", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
    await page.goto("/account");
  });

  test("says what this session can do, rather than its number", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Your account", level: 1 })).toBeVisible();
    await expect(page.getByText(/financial actions will ask for a second factor/))
      .toBeVisible();
    await expect(page.getByText(/A password session gets the long window/)).toBeVisible();
  });

  test("offers no reissue button, and says what would make one appear", async ({ page }) => {
    // The server takes the current password or a stepped-up session and nothing else, so a
    // button here would offer an action that is refused.
    await expect(page.getByRole("button", { name: "Issue a new batch" })).toHaveCount(0);
    await expect(page.getByText(/Minting codes needs a stepped-up session/)).toBeVisible();
  });

  test("shows no session token or digest anywhere", async ({ page }) => {
    // MOD-007 stores a session only as a SHA-256 digest, so there is nothing to render --
    // and this asserts the page did not find somewhere else to get one.
    // **Assert the real token is absent, not a shape that resembles one.** Two earlier
    // versions of this failed for the wrong cause: the word "bearer" is on this page
    // legitimately, because a caption explains that a refused bearer token writes nothing to
    // the log; and a 40-character base64url pattern matched
    // `unknown_device_unanswerable_no_second_factor`, which is an auth-log reason. The
    // session token is readable from the browser's own cookie jar -- `context.cookies()` sees
    // an httpOnly cookie where page JavaScript cannot -- so the precise assertion is
    // available and is the one worth making.
    const jar = await page.context().cookies();
    const token = jar.find((c) => c.name === "veyro_session")?.value ?? "";
    expect(token.length).toBeGreaterThan(20);
    const body = await page.locator("body").innerText();
    expect(body).not.toContain(token);
    // And no session digest, which is the only other form the secret takes anywhere.
    expect(body.match(/\b[0-9a-f]{64}\b/)).toBeNull();
  });

  test("bounds the sign-in log and says it did", async ({ page }) => {
    // The route defaults to a hundred, which is a fine API default and the wrong page.
    await expect(page.getByText(/The twenty most recent, not everything/)).toBeVisible();
  });

  test("says a refused token writes nothing to the log", async ({ page }) => {
    await expect(page.getByText(/A refused bearer token writes nothing here/)).toBeVisible();
  });

  test("has no accessibility violation", async ({ page }) => {
    const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(result.violations).toEqual([]);
  });
});

/**
 * The three writes that need no step-up, each against an identity it made itself.
 *
 * **Every one of these is destructive, so none of them may share a subject.** Trusting a
 * device cannot be asserted twice -- the button is gone the second time -- and revoking the
 * device this app signs in from locks that identity out of the product for good, because
 * `_authenticate_in_tx` refuses a revoked device rather than challenging it. A spec that
 * reused one subject would be green on a fresh fixture and red on the second run, which is
 * the failure `CLAUDE.md` records four times over and the reason the rule is "provision your
 * own" rather than "pick a spare".
 *
 * Registration is open in this build, so a test can make its own subject in one call. A
 * brand-new identity holds no second factor, so MOD-007 skips the risk challenge as
 * unanswerable -- which is what lets it sign in through the form without spending a code.
 */
async function ownSubject(
  request: APIRequestContext,
  tenantId: string,
): Promise<{ email: string; password: string; identityId: string }> {
  const email = `spec+${randomUUID()}@veyro.invalid`;
  const password = `spec-${randomUUID()}`;
  const made = await request.post(`${API}/identities`, {
    headers: { "X-Veyro-Tenant": tenantId },
    data: { display_name: "Spec Subject", correlation_id: randomUUID(), email, password },
  });
  expect(made.ok(), await made.text()).toBeTruthy();
  return { email, password, identityId: (await made.json()).identity_id };
}

/**
 * A recovery code for a subject that has none, **after** its device has been confirmed.
 *
 * The order is the control, not a convenience: MOD-007 challenges a login from a device it
 * has not seen and skips the challenge as unanswerable when the identity holds no second
 * factor, confirming the device on the strength of that login. Issue codes first and the
 * browser sign-in is challenged instead -- and this test would be answering a challenge
 * rather than exercising the page.
 */
async function firstRecoveryCode(
  request: APIRequestContext,
  tenantId: string,
  who: { email: string; password: string; identityId: string },
): Promise<string> {
  const signedIn = await request.post(`${API}/auth/login`, {
    headers: { "X-Veyro-Tenant": tenantId },
    data: { identifier: who.email, password: who.password, correlation_id: randomUUID() },
  });
  expect(signedIn.ok(), await signedIn.text()).toBeTruthy();
  const issued = await request.post(
    `${API}/identities/${who.identityId}/recovery-codes`,
    {
      headers: {
        "X-Veyro-Tenant": tenantId,
        authorization: `Bearer ${(await signedIn.json()).token}`,
      },
      data: { correlation_id: randomUUID(), current_password: who.password },
    },
  );
  expect(issued.ok(), await issued.text()).toBeTruthy();
  return (await issued.json()).codes[0];
}

/** A second live session for that identity, so there is one on the page to revoke. */
async function secondSession(
  request: APIRequestContext,
  tenantId: string,
  who: { email: string; password: string },
): Promise<void> {
  const signedIn = await request.post(`${API}/auth/login`, {
    headers: { "X-Veyro-Tenant": tenantId },
    data: { identifier: who.email, password: who.password, correlation_id: randomUUID() },
  });
  expect(signedIn.ok(), await signedIn.text()).toBeTruthy();
  expect((await signedIn.json()).authenticated, await signedIn.text()).toBeTruthy();
}

test.describe("the writes that need no step-up", () => {
  test("revokes another live session", async ({ page, request }) => {
    const { tenantId } = fixture();
    const who = await ownSubject(request, tenantId);
    await secondSession(request, tenantId, who);
    await signIn(page, who);
    await page.goto("/account");

    // Scoped to the section, because "Revoke" is also the device button -- and Playwright's
    // text filters are substring matches over a whole row, which is the trap this suite has
    // now walked into five times.
    const section = page.locator("section")
      .filter({ has: page.getByRole("heading", { name: "Other sessions" }) });
    const buttons = section.getByRole("button", { name: "Revoke" });
    // Exactly one, because this identity was made by this test: the API login above and the
    // browser login it is reading in.
    await expect(buttons).toHaveCount(1);

    await buttons.click();
    await expect(section.getByText("Revoked.")).toBeVisible();
    // The list is re-read from the server rather than spliced in the client, so the count is
    // the server's answer and not an optimistic one.
    await expect(section.getByRole("button", { name: "Revoke" })).toHaveCount(0);
    await expect(section.getByText("No other session is open.")).toBeVisible();
  });

  test("marks the browser it is reading from, and says what revoking it costs", async ({
    page, request,
  }) => {
    const { tenantId } = fixture();
    await signIn(page, await ownSubject(request, tenantId));
    await page.goto("/account");

    const section = page.locator("section")
      .filter({ has: page.getByRole("heading", { name: "Devices" }) });
    await expect(section.getByText("this browser")).toBeVisible();
    await expect(section.getByText(/no sign-in from it will be accepted again/)).toBeVisible();
    // And the section's own lead says the permanence, which the first version got wrong: it
    // said the next sign-in would be challenged again, and the server refuses it outright.
    await expect(section.getByText(/refused outright rather than challenged again/))
      .toBeVisible();
  });

  test("trusts a device, which stops it being challenged", async ({ page, request }) => {
    const { tenantId } = fixture();
    await signIn(page, await ownSubject(request, tenantId));
    await page.goto("/account");

    const section = page.locator("section")
      .filter({ has: page.getByRole("heading", { name: "Devices" }) });
    const trust = section.getByRole("button", { name: "Trust" });
    await expect(trust).toBeVisible();
    await trust.click();

    await expect(section.getByText(/will not be challenged/)).toBeVisible();
    // Trusted now, so there is nothing left to trust.
    await expect(section.getByRole("button", { name: "Trust" })).toHaveCount(0);
    await expect(section.getByText(/confirmed · trusted/)).toBeVisible();
  });
});

test.describe("reissuing recovery codes", () => {
  test("needs a step-up, and then shows the batch once", async ({ page, request }) => {
    // **Its own subject, because this test spends two budgets.** The step-up consumes a
    // single-use code and the reissue invalidates every earlier one, so a shared subject
    // makes this green on a fresh fixture and red on the second run -- which is how the
    // first version of this spec failed, on exactly that second run.
    const { tenantId } = fixture();
    const who = await ownSubject(request, tenantId);
    await signIn(page, who);
    const code = await firstRecoveryCode(request, tenantId, who);

    await page.goto("/step-up?next=%2Faccount");
    await page.getByLabel("Recovery code").fill(code);
    await page.getByRole("button", { name: "Confirm" }).click();
    await page.waitForURL("/account");

    await expect(page.getByText(/financial actions are available/)).toBeVisible();
    const issue = page.getByRole("button", { name: "Issue a new batch" });
    await expect(issue).toBeVisible();
    await issue.click();

    // **The batch is rendered once and nowhere else.** MOD-007 keeps only a hash, so these
    // exist in one HTTP response; the page says so rather than implying they can be fetched
    // again.
    await expect(page.getByText(/Written down now or not at all/)).toBeVisible();
    await expect(page.getByText(/every earlier code has stopped working/)).toBeVisible();
    const codes = page.locator("li").filter({ hasText: /^[A-Za-z0-9-]{8,}$/ });
    expect(await codes.count()).toBeGreaterThan(0);

    // And nothing put them in the URL.
    expect(page.url()).not.toMatch(/[A-Za-z0-9-]{16,}/);
  });
});

/**
 * Revoking the device you are using, against a subject this test made itself.
 *
 * Three facts worth proving together: the device goes, the session on it goes with it, and
 * the next sign-in is **refused rather than challenged** -- in the same words a wrong
 * password gets, which is MOD-007's uniform-refusal design and the reason the page has to
 * say what revoking costs *before* the button is pressed. A member who did this without
 * being told would be locked out with no way to tell why.
 *
 * Nothing in 2,089 backend tests covered that refusal until this page needed it:
 * `revoke_device`'s own docstring records the regression it closed -- "the first version
 * revoked the sessions, left the fingerprint usable" -- and the control was guarded by
 * nothing. `RevokedDeviceReadmissionTests` is the server-side half.
 */
test.describe("revoking the device you are using", () => {
  test("signs you out here, and this browser cannot sign in again", async ({
    page, request,
  }) => {
    const { tenantId } = fixture();
    const who = await ownSubject(request, tenantId);
    await signIn(page, who);
    await page.goto("/account");

    const section = page.locator("section")
      .filter({ has: page.getByRole("heading", { name: "Devices" }) });
    await section.getByRole("button", { name: "Revoke" }).first().click();

    // **The reader is taken to sign-in and told why**, which is the whole finding here: the
    // first version returned a success message into a page that no longer had a session to
    // render it on, so nothing appeared at all and the next navigation threw them out with
    // no explanation. Waiting for the navigation is also what makes this test deterministic
    // -- clicking and leaving passed three runs alone and failed inside the full suite.
    await page.waitForURL(/\/login/);
    await expect(page.getByText(/You revoked this device, so you were signed out here/))
      .toBeVisible();

    // And the session really is gone, not merely unreachable from the cookie.
    await page.goto("/account");
    await expect(page).toHaveURL(/\/login/);

    // And the way back is closed. The refusal is the ordinary one: a revoked device and a
    // wrong password are the same 401, so nothing here tells an attacker which it was.
    await page.goto("/login");
    await page.getByLabel("Tenant ID").fill(tenantId);
    await page.getByLabel("Email or phone").fill(who.email);
    await page.getByLabel("Password").fill(who.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Those details were not accepted.")).toBeVisible();
    // Not a challenge, which is the distinction the page's copy now makes.
    await expect(page.getByLabel("Recovery code")).toHaveCount(0);
  });
});
