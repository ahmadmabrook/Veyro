import { expect, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";

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
export async function signIn(page: Page): Promise<void> {
  const creds = fixture();
  await page.goto("/login");
  await page.getByLabel("Tenant ID").fill(creds.tenantId);
  await page.getByLabel("Email or phone").fill(creds.email);
  await page.getByLabel("Password").fill(creds.password);
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
