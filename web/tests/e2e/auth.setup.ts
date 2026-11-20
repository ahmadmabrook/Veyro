import { test as setup } from "@playwright/test";

import { fixture } from "./fixture-env";
import { DESK_STATE, OWNER_STATE, READER_STATE, signIn } from "./sign-in";

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
 * Three states, because the negative proofs need permission subsets that contradict each
 * other. The owner holds all 202. The reader holds `access.zone.read` and **not**
 * `people.person.read`, which is what makes the navigation filter and the record refusal
 * provable. The front desk holds `people.person.read` and **nothing** of MOD-017, which is the
 * only subset that can prove the membership blocks' own gates -- with no person read the
 * page's gate answers first and the spec proves the wrong refusal.
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

setup("sign in as a front desk who may read a person and none of their money", async ({
  page,
}) => {
  const creds = fixture();
  await signIn(page, { email: creds.deskEmail, password: creds.deskPassword });
  await page.context().storageState({ path: DESK_STATE });
});
