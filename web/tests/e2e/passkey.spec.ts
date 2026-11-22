import AxeBuilder from "@axe-core/playwright";
import { expect, test, type CDPSession, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn, useReaderSession } from "./sign-in";

/**
 * Enrolling a passkey and signing in with one, against a real authenticator.
 *
 * **This is the only place in the repository where a WebAuthn ceremony actually happens.**
 * `tests/component/passkey.test.ts` proves the options and the encoding and cannot do more --
 * `navigator.credentials` does not exist in jsdom, and faking it would be asserting a fake.
 * Chromium's own virtual authenticator, driven over CDP, produces a real credential and a
 * real signature, and the backend verifies it with `cryptography`. Nothing in this file is
 * mocked.
 *
 * **The authenticator lives in one browser context**, so enrolment and sign-in happen in the
 * same test: a credential created in one context does not exist in the next. The sign-out
 * between them is the product's own, and the cookie that comes back is what the assertions
 * are about.
 *
 * **It signs in for itself rather than adopting the shared cookie.** This spec signs out, and
 * `playwright/.auth/owner.json` is a file every other spec reads -- signing out of a context
 * that adopted it is harmless, but a spec that ends a session is exactly the shape that has
 * broken four other specs in this repository before, so it keeps to its own.
 */

const creds = fixture();

/**
 * A label nobody else has used, because **a credential enrolled here stays enrolled**.
 *
 * The virtual authenticator mints a fresh key pair every run, so every run adds a row --
 * there is no budget being spent and no state to restore, but a label is not a key. Asserting
 * on a fixed one resolved to five rows on the fifth local run, which is this repository's
 * accumulation shape with the harmless half of the usual consequence: the test breaks rather
 * than the product. CI re-provisions and never sees it; a local re-run does, immediately.
 */
const run = `${Date.now().toString(36)}`;

/**
 * A platform authenticator that verifies its user and keeps its credentials.
 *
 * `hasResidentKey` because the sign-in sends no credential list -- `allowCredentials` would
 * name a person's credential ids to anybody who typed their address -- so the authenticator
 * has to find the credential from the relying party id alone. `hasUserVerification` and
 * `isUserVerified` because the backend refuses an assertion whose `UV` flag is unset, there
 * being no factor name in this build for "a device was present and nobody was checked".
 *
 * **Backup eligibility is left at its default of false**, which is what makes the credential
 * device-bound and therefore `passkey_hardware` -- the factor that reaches AAL 3. A virtual
 * authenticator with `defaultBackupEligibility: true` would enrol the synced factor instead,
 * and the level-3 assertion below would read 2 for a reason that has nothing to do with this
 * app.
 */
async function virtualAuthenticator(
  page: Page,
  { backupEligible = false }: { backupEligible?: boolean } = {},
): Promise<CDPSession> {
  const client = await page.context().newCDPSession(page);
  await client.send("WebAuthn.enable");
  await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
      // **The flag the level follows, and the reason this is a parameter.** `BE` is set when
      // the credential is created and never changes, and the backend's `factor_for` reads it:
      // false is device-bound and reaches AAL 3, true is synced and reaches 2. Leaving it
      // false for every test would leave the other half of the module's defining distinction
      // rendered by nothing, which is this repository's "a surface branch no fixture can
      // reach" one layer out. `defaultBackupState` is deliberately not set: it is `BS`, which
      // nothing in this build reads, and setting it would suggest otherwise.
      defaultBackupEligibility: backupEligible,
    },
  });
  return client;
}

/** Enrol a passkey from the account page and return the label it was given. */
async function enrol(page: Page, label: string): Promise<void> {
  await page.goto("/account");
  const section = page.locator("section").filter({ hasText: "Passkeys" }).first();
  await expect(section).toBeVisible();
  await section.getByLabel("What to call it").fill(label);
  await section.getByRole("button", { name: "Add a passkey" }).click();
  // The ceremony is instant with a virtual authenticator, and the write is a server action,
  // so what is waited on is the row appearing rather than a spinner disappearing.
  await expect(page.getByText("That passkey is enrolled")).toBeVisible();
}

test.describe("a passkey, from enrolment to sign-in", () => {
  test("is enrolled, signs in, and reaches the level nothing else can", async ({ page }) => {
    await virtualAuthenticator(page);
    await signIn(page);

    // --- enrolment, on a password-only session -------------------------------------------
    //
    // **Routine and self-scoped, which is why there is a form at all.** Every other write in
    // this app is a stepped-up financial permission; `owned(session, identity_id)` refuses
    // any subject but the caller's own with a 404, so there is nothing to authorize.
    const label = `E2E laptop ${run}`;
    await enrol(page, label);
    const section = page.locator("section").filter({ hasText: "Passkeys" }).first();
    const row = section.locator(".ds-passkey").filter({ hasText: label });
    await expect(row).toHaveCount(1);
    await expect(row).toHaveAttribute("data-state", "unused");
    // And the "no passkey" warning is gone, because the account now has a way in that spends
    // nothing -- which is the sentence the section exists for. The recovery block one section
    // up asks the *same* function, so it must have changed with it: two copies of "is there a
    // way in that spends nothing" are two answers the day either moves.
    await expect(section.getByText("No passkey is enrolled")).toHaveCount(0);
    await expect(page.getByText("You also have a passkey")).toBeVisible();
    await expect(page.getByText("You have no passkey")).toHaveCount(0);

    // --- sign out, so the sign-in below is a real one ------------------------------------
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL(/\/login/);

    // --- sign in with the passkey --------------------------------------------------------
    await page.getByLabel("Tenant ID").fill(creds.tenantId);
    await page.getByLabel("Email or phone").fill(creds.email);
    await page.getByRole("button", { name: "Use a passkey" }).click();
    // **The push has to land on a page that knows about the new cookie.** The action writes
    // it and calls `revalidatePath`, and a router cache populated before that would render
    // the signed-out page with a live session in the jar -- which is the defect this
    // navigation is arranged to avoid and the reason the assertion is on the landing page's
    // own heading.
    await page.waitForURL("/");
    await expect(page.getByRole("heading", { level: 1 }))
      .toContainText(/need(s)? you|Nothing needs you/);

    // --- the level, which is the whole point --------------------------------------------
    //
    // For five modules `/auth/require/privileged` answered `reachable: false`, because a
    // privileged action needs a hardware authenticator and nothing checked a signature.
    await page.goto("/account");
    // **Scoped to the assurance block, not the page.** An unscoped `getByText` on a phrase is
    // a test coupled to that phrase being unique in the whole document, and it stopped being
    // so the moment the recovery block grew a sentence about the same level -- a strict-mode
    // violation reported as a failure of the level, which it was not. The duplication was
    // worth removing on its own account; the assertion is scoped so the next one does not
    // read as a product defect.
    const facts = page.locator(".facts").first();
    await expect(facts).toContainText("A passkey on a hardware authenticator");
    await expect(facts).toContainText("the highest assurance this product has");
    // **Fifteen minutes, not a fortnight.** `SESSION_LIFETIME` gives level 3 the shortest
    // window of the three, and this caption read the password one for it until a passkey
    // session existed to notice.
    await expect(page.getByText("the shortest window")).toBeVisible();
    // The factor the authenticator's own signed flag decided, which no request field can ask
    // for: backup-*eligible* is false, so this is the device-bound one.
    await expect(facts).toContainText("passkey_hardware");
  });

  test("is withdrawn by its owner, and then signs nobody in", async ({ page }) => {
    // **The remedy that had to exist before the button that creates one.** Until
    // `revoke_passkey`, the only writer of `revoked_at` was the clone check -- so a lost
    // authenticator left a credential that could open a level-3 session for ever.
    await virtualAuthenticator(page);
    await signIn(page);
    const label = `E2E withdrawn ${run}`;
    await enrol(page, label);

    const section = page.locator("section").filter({ hasText: "Passkeys" }).first();
    const row = section.locator(".ds-passkey").filter({ hasText: label });
    await expect(row).toHaveCount(1);
    await row.getByRole("button", { name: "Withdraw" }).click();
    await expect(page.getByText("can no longer sign anybody in")).toBeVisible();

    // **The row stays and recedes**, for the reason a redacted field is marked rather than
    // dropped: an absent row and a withdrawn one are different facts, and "was this
    // credential ever enrolled" is asked precisely when somebody lost a device.
    await expect(row).toHaveAttribute("data-state", "withdrawn");
    // And it offers no second withdrawal, which would admit nothing and read as a control.
    await expect(row.getByRole("button", { name: "Withdraw" })).toHaveCount(0);

    // The session the owner is sitting in is untouched -- deliberately unlike the clone path,
    // which revokes every session for the identity.
    await page.goto("/account");
    await expect(page.getByText("A password only")).toBeVisible();
  });

  test("a credential that can be synced says so, and reaches one level lower", async ({
    page,
  }) => {
    // **The other half of the distinction the module is built on**, and until this test
    // existed it was rendered by nothing: every other test here uses a device-bound
    // authenticator, so "Can be synced to a keychain" and the level that follows from it were
    // a branch no fixture could reach. `BE` is signed by the authenticator and no request
    // field can ask for it, which is what makes the level trustworthy.
    await virtualAuthenticator(page, { backupEligible: true });
    await signIn(page);
    const label = `E2E synced ${run}`;
    await enrol(page, label);

    const section = page.locator("section").filter({ hasText: "Passkeys" }).first();
    const row = section.locator(".ds-passkey").filter({ hasText: label });
    // **"Can be synced", not "is synced"**: eligibility is a capability the authenticator
    // decides at creation, and the flag is written once at enrolment, so the present tense
    // would go stale the moment a keychain finished -- or never become true if it did not.
    await expect(row).toContainText("Can be synced to a keychain");
    await expect(row).not.toContainText("Stays on this device");

    // And the level: signing in with it reaches 2 rather than 3, which is the whole point of
    // keeping the two factors apart. `passkey_synced` is a strong factor and not a
    // hardware-bound one, so a privileged action still needs a device-bound credential.
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL(/\/login/);
    await page.getByLabel("Tenant ID").fill(creds.tenantId);
    await page.getByLabel("Email or phone").fill(creds.email);
    await page.getByRole("button", { name: "Use a passkey" }).click();
    await page.waitForURL("/");

    await page.goto("/account");
    await expect(page.locator(".facts").first()).toContainText("passkey_synced");
    // Not the hardware sentence, and not the shortest window either -- a level-2 session gets
    // the twelve-hour one, which is what `policy.session_expiry` gives a stepped-up session.
    await expect(page.getByText("A passkey on a hardware authenticator")).toHaveCount(0);
  });

  test("says which field it needs before it asks the authenticator", async ({ page }) => {
    // Two fields are needed and only one is obvious: a passkey is discoverable from the
    // relying party, so a reader could reasonably press this with nothing typed. The tenant
    // header is what this build needs beside it.
    await virtualAuthenticator(page);
    await page.goto("/login");
    await page.getByRole("button", { name: "Use a passkey" }).click();
    await expect(page.getByText("Type your email or phone first")).toBeVisible();
    // Nothing navigated and no ceremony ran.
    await expect(page).toHaveURL(/\/login/);
  });

  test("refuses an identifier with no passkey without saying so", async ({ page }) => {
    // **The anti-enumeration property, from the surface.** The challenge route answers the
    // same shape for every identifier -- a row is stored only where there is an identity to
    // store it against -- so the ceremony runs and the assertion is refused at the second
    // call. What a reader sees is one refusal, which is the same one a wrong password gets.
    await virtualAuthenticator(page);
    await page.goto("/login");
    await page.getByLabel("Tenant ID").fill(creds.tenantId);
    await page.getByLabel("Email or phone").fill(`nobody-${Date.now()}@acme.test`);
    await page.getByRole("button", { name: "Use a passkey" }).click();
    await expect(page.getByText(/did not sign you in|not complete that/)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("a browser that cannot do a ceremony", () => {
  test("is offered nothing rather than a control that cannot work", async ({ page }) => {
    // **Absent, not disabled**, which is this app's standing rule about a button that answers
    // 403: here the reader would have no way to tell a missing passkey from a browser that
    // cannot ask for one. `PublicKeyCredential` is deleted before any script runs, because
    // `navigator.credentials` exists in browsers with no WebAuthn at all -- it carries the
    // password manager API too, so checking only that reports a browser as capable and then
    // throws at the ceremony.
    await page.addInitScript(() => {
      Reflect.deleteProperty(window, "PublicKeyCredential");
    });
    await page.goto("/login");
    await expect(page.getByLabel("Tenant ID")).toBeVisible();
    await expect(page.getByRole("button", { name: "Use a passkey" })).toHaveCount(0);

    await signIn(page);
    await page.goto("/account");
    const section = page.locator("section").filter({ hasText: "Passkeys" }).first();
    await expect(section).toContainText("no passkey support");
    await expect(section.getByRole("button", { name: "Add a passkey" })).toHaveCount(0);
  });
});

test.describe("the passkey section", () => {
  test.beforeEach(async ({ page }) => {
    await virtualAuthenticator(page);
    await signIn(page);
    await page.goto("/account");
  });

  test("says what a passkey is for, and what this build does not check", async ({ page }) => {
    const section = page.locator("section").filter({ hasText: "Passkeys" }).first();
    // The one second factor here that is not a recovery code, and the only one that reaches
    // the level a privileged action needs.
    await expect(section).toContainText("the only second factor here that is not a recovery");
    await expect(section).toContainText("the highest assurance level");
    // **Attestation is a different claim from the signature**, and the section says which one
    // is checked rather than implying both.
    await expect(section).toContainText("which model of authenticator");
    await expect(section).toContainText("does check is the signature");
  });

  test("reads in Arabic", async ({ page }) => {
    await page.getByRole("button", { name: "العربية" }).click();
    await page.waitForURL("/account");
    const section = page.locator("section").filter({ hasText: "مفاتيح المرور" }).first();
    await expect(section).toBeVisible();
    await expect(section).toContainText("أضف مفتاح مرور");
    // Not the English word, which is the finding `StatusBadge` paid for one screen over.
    await expect(section).not.toContainText("Add a passkey");
  });

  test("no accessibility violations", async ({ page }) => {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});

test.describe("the recovery codes, for an account with no passkey", () => {
  test("say they are the only way back, which the lead used to get wrong", async ({ page }) => {
    // **The sentence the recovery block got wrong for five modules**, on the page that now
    // enrols a passkey: its lead said a recovery code is "the only second factor this build
    // can verify". What a reader needs is not which factors exist but whether *they* have
    // one -- a member with a passkey cannot be locked out by spending ten codes and a member
    // without one can, which is the dead end MOD-007 recorded against itself.
    //
    // **It has to be an identity nobody enrols a passkey for.** A credential stays enrolled,
    // and the owner gets one in the first test in this file, so asserting the negative half
    // as the owner would pass only until that test had run once -- this repository's "a green
    // that depends on how many times the suite has been run", which it has paid for four
    // times. The reader session is never given a passkey by anything here.
    await useReaderSession(page);
    await page.goto("/account");
    await expect(page.getByText("You have no passkey")).toBeVisible();
    await expect(page.getByText(/only second factor on your account/)).toBeVisible();
    // And not the claim that a recovery code is the only factor the build can verify at all.
    await expect(page.getByText(/only second factor this build can verify/)).toHaveCount(0);
  });
});
