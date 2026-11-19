import { readFileSync } from "node:fs";

import { expect, type BrowserContext, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";

/**
 * Where the signed-in cookies are kept between the setup project and the specs.
 *
 * Gitignored: the file holds a live bearer session for a synthetic tenant, and
 * `playwright/.auth` is excluded by `web/.gitignore` for the same reason `.env.e2e.local` is.
 */
export const OWNER_STATE = "playwright/.auth/owner.json";
export const READER_STATE = "playwright/.auth/reader.json";

/**
 * Sign in through the real form.
 *
 * **No challenge is expected, and one appearing is a failure rather than something to
 * answer.** MOD-007 challenges a login from a device it has not seen, and the fixture
 * confirms this app's device itself precisely so that no test spends a recovery code: a code
 * is single-use, so a helper that answered the challenge passed on the first run against a
 * fresh fixture and failed on every run after it -- which is what it did, timing out at the
 * recovery field in every signing-in test of the second run. Failing loudly here is what
 * catches the regression that would make every sign-in challenged again.
 */
export async function signIn(
  page: Page,
  who?: { email: string; password: string },
): Promise<void> {
  const creds = fixture();
  await page.goto("/login");
  await page.getByLabel("Tenant ID").fill(creds.tenantId);
  await page.getByLabel("Email or phone").fill(who?.email ?? creds.email);
  await page.getByLabel("Password").fill(who?.password ?? creds.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  const recovery = page.getByLabel("Recovery code");
  if (await recovery.isVisible().catch(() => false)) {
    throw new Error(
      "the sign-in was challenged: the fixture should have confirmed this app's device, so "
      + "either the device label changed or the fixture was not re-run after the database "
      + "was rebuilt. Answering it here would spend the one spare recovery code.",
    );
  }
  await page.waitForURL("/");
  await expect(page.getByRole("heading", { name: "Veyro Admin" })).toBeVisible();
}

/** The assurance level the landing page reports for the session now signed in. */
export async function assuranceLevel(page: Page): Promise<number> {
  const text = await page.getByText(/Assurance level/).innerText();
  const digits = /(\d+)/.exec(text);
  expect(digits, `no assurance level in ${JSON.stringify(text)}`).toBeTruthy();
  return Number(digits![1]);
}


/**
 * Adopt a session the setup project already signed in, instead of signing in again.
 *
 * **Thirty logins a minute is the budget and the suite had more tests than that.** MOD-011's
 * limiter counts per subject, so a `beforeEach` that signs in puts a hard cap on how many
 * tests the suite may contain -- and crossing it reads as a flake: the form answers "too many
 * attempts", the helper waits for a page it will never get, and the failure names a timeout
 * rather than a limit. The cookie is written once per run by `auth.setup.ts` and adopted here.
 *
 * This is also the honest division of labour: `signIn` exercises the sign-in *form*, which is
 * what `auth.spec.ts` and the no-JavaScript replay are for. Every other spec is about a page
 * behind the session, and re-proving the login on the way to each one proves nothing new.
 */
async function adopt(page: Page, path: string): Promise<void> {
  const state = JSON.parse(readFileSync(path, "utf8")) as {
    cookies: Parameters<BrowserContext["addCookies"]>[0];
  };
  await page.context().addCookies(state.cookies);
  // **Ends where `signIn` ends, on the landing page.** Adopting a cookie leaves the tab on
  // `about:blank`, and the first version of this helper stopped there -- so every test that
  // had been written against `signIn`'s postcondition was suddenly asserting against a blank
  // page. Seven of them failed and the messages were about missing headings rather than
  // about the session, which is the wrong place to look.
  await page.goto("/");
}

/** The owner: every permission in the catalogue. */
export function useOwnerSession(page: Page): Promise<void> {
  return adopt(page, OWNER_STATE);
}

/** The reader: `access.zone.read` and not `tenancy.organization.read`. */
export function useReaderSession(page: Page): Promise<void> {
  return adopt(page, READER_STATE);
}
