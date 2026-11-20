import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn, useOwnerSession, useReaderSession } from "./sign-in";

/**
 * Raising a session's assurance, in a real browser against the real MOD-007.
 *
 * **This spec signs in for itself rather than adopting the shared owner cookie, and that is
 * load-bearing.** A successful step-up *revokes* the session it came from -- MOD-007 sets
 * `revoke_reason = 'stepped_up'` and opens a new one, because a level-2 window is twelve hours
 * rather than a fortnight. A test that adopted the saved owner state and stepped up would
 * destroy that session for every test after it in the run.
 *
 * It also mints its own recovery codes. The fixture writes one spare, and a code is spent the
 * moment it works -- so a spec that used the spare would pass on the first run against a fresh
 * fixture and fail on every one after it, which is the exact trap `auth.setup.ts` was written
 * to close one layer up. Minting is what an operator does, it needs only the password this
 * session already proved, and it makes the spec re-runnable.
 */
async function freshRecoveryCode(page: Page): Promise<string> {
  const creds = fixture();
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name === "veyro_session")?.value;
  expect(token, "signed in, so there is a session cookie to use as a bearer token").toBeTruthy();

  const api = process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";
  const response = await page.request.post(
    `${api}/identities/${creds.identityId}/recovery-codes`,
    {
      headers: {
        "X-Veyro-Tenant": creds.tenantId,
        Authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      data: { correlation_id: crypto.randomUUID(), current_password: creds.password },
    },
  );
  expect(response.status(), await response.text()).toBe(201);
  const body = (await response.json()) as { codes: string[] };
  return body.codes[0]!;
}

/**
 * The tests that only *look* at the step-up surface share the run's one owner session: they
 * never complete a step-up, so they never revoke anything, and MOD-011's limiter allows 30
 * logins a minute per subject -- a budget this suite has already run into once.
 */
test.describe("the step-up surface", () => {
  test.beforeEach(async ({ page }) => {
    await useOwnerSession(page);
  });

  test("is offered where the refusal is, on the member record", async ({ page }) => {
    const creds = fixture();
    await page.goto(`/people/${creds.personId}`);
    // The identity fields are withheld at assurance level 1 and the page says a stronger
    // sign-in would reveal them. Saying that and offering no way to do it is the dead end.
    const link = page.getByRole("link", { name: "Raise this session to read them" });
    await expect(link).toBeVisible();
    await link.click();
    await page.waitForURL(/\/step-up\?/);
    await expect(page.getByRole("heading", { name: "Confirm it is you" })).toBeVisible();
  });

  test("asks for a recovery code, because a password session cannot use a password", async ({
    page,
  }) => {
    await page.goto("/step-up?for=financial&next=/");
    // `policy.assurance_for` reads distinct *kinds*: two passwords are one factor, so a
    // password session is raised by something else. This build can verify a recovery code and
    // not a passkey, which the page says rather than leaving to be discovered.
    await expect(page.getByLabel("Recovery code")).toBeVisible();
    await expect(page.getByLabel("Password")).toHaveCount(0);
    await expect(page.getByText(/cannot be verified here/)).toBeVisible();
  });



  test("a wrong code is refused without saying which thing was wrong", async ({ page }) => {
    // **As the reader, not the owner, and the reason is a budget rather than a permission.**
    // MOD-007 keeps a separate recovery lockout -- five failures and the identity's recovery
    // path is shut -- and nothing resets it between runs. Spending one of the owner's slots
    // per run means the suite breaks on the fifth run against one fixture, which is the same
    // "green depends on how many times it has been run" shape the single-use recovery code
    // had. The reader never completes a step-up, so its budget is nobody else's, and a locked
    // identity answers the *same* refusal as a wrong code -- MOD-007 made every refusal here
    // identical on purpose -- so the assertion stays true even once this one is spent.
    await useReaderSession(page);
    await page.goto("/step-up?for=financial&next=/");
    await page.getByLabel("Recovery code").fill("not-one-of-the-ten");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.locator("main").getByRole("alert")).toContainText("was not accepted");
    // **And the reader is still signed in.** The old session is revoked only on success; a
    // refusal that cleared the cookie would lock somebody out for mistyping.
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/need(s)? you/);
  });

  test("an empty field is named rather than submitted", async ({ page }) => {
    await page.goto("/step-up?for=financial&next=/");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByText("Enter it to continue.")).toBeVisible();
  });

  test("a level nobody can reach is said, not offered", async ({ page }) => {
    await page.goto("/step-up?for=biometric_sensitive&next=/");
    // AAL 3 needs a hardware authenticator MOD-007 cannot verify, so there is no field.
    await expect(page.locator("main").getByRole("status")).toContainText(
      /hardware security key/,
    );
    await expect(page.getByLabel("Recovery code")).toHaveCount(0);
  });


  test("no accessibility violations on the step-up form", async ({ page }) => {
    await page.goto("/step-up?for=financial&next=/");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

/**
 * And the three that actually complete one, each in a session of its own.
 *
 * **A successful step-up revokes the session it came from** -- MOD-007 sets
 * `revoke_reason = 'stepped_up'` and opens a new one, because a level-2 window is twelve hours
 * rather than a fortnight. A test that spent the shared owner cookie would sign out every test
 * after it in the run.
 */
test.describe("completing a step-up", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("raises the session, keeps the reader signed in, and unmasks the name", async ({
    page,
  }) => {
    const creds = fixture();
    const code = await freshRecoveryCode(page);

    await page.goto(`/step-up?for=financial&next=${encodeURIComponent(`/people/${creds.personId}`)}`);
    await page.getByLabel("Recovery code").fill(code);
    await page.getByRole("button", { name: "Confirm" }).click();

    // **Back where they came from, still signed in.** MOD-007 revoked the old session, so a
    // step-up that did not replace the cookie would land on the sign-in page instead -- a
    // sign-out dressed as a success, on the one path where the reader has just proved who
    // they are.
    await page.waitForURL(`/people/${creds.personId}`);
    await expect(page.getByRole("heading", { name: "Member 360" })).toBeVisible();

    // And the fields that were withheld are readable, which is the whole point.
    //
    // **Scoped to the `dl` that holds the name, not to the panel.** The panel also holds the
    // health custom field, which stays withheld for everybody at every level -- so a panel-wide
    // "no markers" assertion asserts something false, and the first version of this test failed
    // for exactly that reason. The health marker staying put is asserted below, because it is
    // the half that must not change.
    const identity = page.locator("dl").filter({ hasText: "Legal name" });
    await expect(identity).toContainText("Jane Member");
    await expect(identity.getByText("Withheld")).toHaveCount(0);
    // Level 2 does not open the health class, and nothing in this build does.
    const health = page.locator("dl").filter({ hasText: "Injury history" });
    await expect(health.getByText("Withheld")).toHaveCount(1);
    // The offer is gone, because there is nothing left to raise.
    await expect(
      page.getByRole("link", { name: "Raise this session to read them" }),
    ).toHaveCount(0);
  });

  test("the session really is level 2 afterwards, not merely rendered as one", async ({
    page,
  }) => {
    const code = await freshRecoveryCode(page);
    await page.goto("/step-up?for=financial&next=/");
    await page.getByLabel("Recovery code").fill(code);
    await page.getByRole("button", { name: "Confirm" }).click();
    await page.waitForURL("/");
    // The landing page reads the level from `/auth/session`, so this is the server's answer.
    // The assurance is on `/account` now, beside the devices and sessions it is about --
    // and it is rendered as what the level *means* rather than as a digit.
    await page.goto("/account");
    await expect(page.getByText(/Stepped up/)).toBeVisible();
  });

  test("sends the reader back to this app and never to another host", async ({ page }) => {
    const code = await freshRecoveryCode(page);
    // A `next` is attacker-controllable by construction: it arrives in a link.
    await page.goto("/step-up?for=financial&next=//evil.test/pwned");
    await page.getByLabel("Recovery code").fill(code);
    await page.getByRole("button", { name: "Confirm" }).click();
    await page.waitForURL("/");
    expect(new URL(page.url()).host).toBe(new URL(page.url()).host);
    expect(page.url()).not.toContain("evil.test");
  });
});
