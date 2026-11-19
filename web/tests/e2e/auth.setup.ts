import { test as setup } from "@playwright/test";

import { fixture } from "./fixture-env";
import { OWNER_STATE, READER_STATE, signIn } from "./sign-in";

/**
 * Sign in once per run and save the cookie, rather than once per test.
 *
 * **This is a rate-limit fix, not a speed one.** MOD-011's limiter allows 30 logins per minute
 * per subject -- a real product control, bounding the volume MOD-007's lockout cannot see --
 * and a suite with a `beforeEach` that signs in crosses it as soon as it has more than thirty
 * tests. It did: at 45 tests the run passed, at 53 the owner's thirty-first login inside the
 * window was refused and the sign-in helper timed out waiting for a page it was never going to
 * get. **The suite had a cap on how many tests it could contain**, which is the kind of
 * failure that reads as flakiness and gets retried rather than fixed.
 *
 * Two states, because the gated-navigation assertions need a session that cannot read
 * everything: the owner holds all 202 permissions and the reader holds `access.zone.read` and
 * not `tenancy.organization.read`.
 */
setup("sign in as the owner", async ({ page }) => {
  await signIn(page);
  await page.context().storageState({ path: OWNER_STATE });
});

setup("sign in as a reader who may not read the hierarchy", async ({ page }) => {
  const creds = fixture();
  await signIn(page, { email: creds.readerEmail, password: creds.readerPassword });
  await page.context().storageState({ path: READER_STATE });
});
