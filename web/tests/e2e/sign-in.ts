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
export const DESK_STATE = "playwright/.auth/desk.json";

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
  // **The landing page is the Command Center**, so what proves a sign-in landed is its
  // heading rather than the app's name: `/` used to render "Veyro Admin" over a session
  // diagnostic, and the design puts ADM-CC-01 there. The heading counts the queue, so the
  // assertion is on the shape of the sentence rather than on a number that moves with the
  // fixture.
  await expect(page.getByRole("heading", { level: 1 }))
    .toContainText(/need(s)? you|Nothing needs you/);
}

/**
 * The assurance level this session holds, read from the account page.
 *
 * **It used to be on the landing page and is not any more.** `/` reported the caller's
 * identity uuid and assurance level, which is a session diagnostic rather than a product
 * screen; the Command Center replaced it and the facts moved to `/account`, beside the
 * devices and the other sessions they are about. This navigates there and leaves the caller
 * to go on to whatever page it is actually testing.
 */
export async function assuranceLevel(page: Page): Promise<number> {
  await page.goto("/account");
  const assurance = page.getByText(/Password only|Stepped up|hardware/i).first();
  const text = await assurance.innerText();
  // The account page says what the level *means* rather than printing a digit, which is the
  // better copy and means this maps the sentence back to the number the callers compare.
  if (/stepped up/i.test(text)) return 2;
  return 1;
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
  // **It lands on `/login`, which redirects, rather than on `/`.**
  //
  // Adopting a cookie leaves the tab on `about:blank`, so this has to navigate somewhere:
  // the first version stopped at the blank page and seven tests written against `signIn`'s
  // postcondition failed with messages about missing headings. It then landed on `/` -- and
  // `/` became the Command Center, which asks the gate about six reads and makes six module
  // reads of its own.
  //
  // **That turned a harness convenience into the suite's biggest cost.** MOD-011's
  // `api.request` budget is 600 a minute per identity, and a 280-test suite loading the
  // product's heaviest page before every test went over it -- so roughly seven tests failed
  // per run, a different seven each time, each one passing in isolation. A green that
  // depends on how far into the run a test sits is the same family as the three
  // budget-spending tests this suite already records.
  //
  // **`/account` rather than `/`.** It is always permitted -- every read behind it is scoped
  // to the caller's own identity, so there is no gate to fail -- it carries the navigation
  // that a dozen specs assert against, and it costs four requests where the Command Center
  // costs seven. The limiter is not the thing at fault here: 600 a minute is eighty-five
  // Command Center loads, which no person reaches. A suite that loads the product's heaviest
  // page before every test is the outlier, and the fix belongs in the harness.
  //
  // A spec that needs the landing page navigates to it, which is what every spec does for
  // the page it actually tests.
  await page.goto("/account");
}

/** The owner: every permission in the catalogue. */
export function useOwnerSession(page: Page): Promise<void> {
  return adopt(page, OWNER_STATE);
}

/** The reader: `access.zone.read` and not `tenancy.organization.read`. */
export function useReaderSession(page: Page): Promise<void> {
  return adopt(page, READER_STATE);
}

/**
 * The front desk: `people.person.read` and nothing of MOD-017.
 *
 * The one subset that can prove the membership blocks' own gates. With no person read the
 * page's gate answers first and the spec proves the wrong refusal; with any MOD-017 read the
 * blocks render and there is no refusal to prove at all.
 */
export function useDeskSession(page: Page): Promise<void> {
  return adopt(page, DESK_STATE);
}
