import { expect, test, type Page } from "@playwright/test";

import { fixture } from "./fixture-env";
import { signIn } from "./sign-in";

/**
 * Sign-in, against the real backend.
 *
 * Every assertion here corresponds to a decision in `src/app/login/actions.ts` or to a defect
 * found by driving the page in a browser. The one that matters most is `does not put anything
 * in the URL`: the first version of this form was a client component whose only protection was
 * `event.preventDefault()`, and a dev-server origin block stopped hydration, so the browser did
 * a native GET and put the password in the address bar.
 */

const creds = fixture();

/**
 * An address no identity has, for the tests whose point is a refusal.
 *
 * **A suite that locks its own account fails for a reason that has nothing to do with the
 * product.** MOD-007 locks an identity after a few failed passwords, and the two tests below
 * send a wrong one deliberately -- so across a few runs, or one interrupted run, the identity
 * every other test signs in with was locked, and four tests failed with "those details were
 * not accepted" on a password that was correct.
 *
 * Substituting an unknown address is sound precisely because of the property these tests
 * assert: MOD-007's review made every refusal identical, costing one scrypt and answering the
 * same 401, so that a locked account, a wrong password and an address nobody has registered
 * are indistinguishable. If that ever stopped being true, these tests would start failing --
 * which is the right outcome.
 */
const unknown = `nobody+${Date.now()}@veyro.invalid`;

/**
 * The form's own alert, not any element with `role="alert"`.
 *
 * Next renders `#__next-route-announcer__` with `role="alert"` on every page so route changes
 * are announced, so an unscoped `getByRole("alert")` matches two elements and the assertion
 * fails for a reason that has nothing to do with the product.
 */
function formAlert(page: Page) {
  return page.locator("form").getByRole("alert");
}

test.describe("sign-in", () => {
  test("the form is a POST, so credentials can never reach a query string", async ({ page }) => {
    await page.goto("/login");
    const form = page.locator("form").filter({ has: page.getByLabel("Password") });
    // A server action compiles to method="POST" with the action id in a hidden field, so this
    // holds whether or not the client bundle ran. The original defect was precisely the absence
    // of this: an un-hydrated form defaults to GET.
    await expect(form).toHaveAttribute("method", /post/i);
  });

  test("an empty submission names every missing field and navigates nowhere", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("This field is required.")).toHaveCount(3);
    for (const label of ["Tenant ID", "Email or phone", "Password"]) {
      const field = page.getByLabel(label);
      await expect(field).toHaveAttribute("aria-invalid", "true");
      // The message is associated, not merely adjacent: an error a screen reader never reaches
      // is an error only sighted users have.
      //
      // **One slot, not one per kind.** §23 gives the field shell a single message slot with
      // the priority error > warning > success > description, so the id is `-message` and the
      // error is what it holds -- which the old component could not express, because it
      // rendered a hint *and* an error and described the field by both.
      const describedBy = await field.getAttribute("aria-describedby");
      expect(describedBy ?? "").toContain("-message");
      const message = page.locator(`#${describedBy}`);
      await expect(message).toHaveText("This field is required.");
    }
    expect(new URL(page.url()).search).toBe("");
  });

  test("a wrong password is refused without saying why, and the URL stays clean", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByLabel("Tenant ID").fill(creds.tenantId);
    await page.getByLabel("Email or phone").fill(unknown);
    await page.getByLabel("Password").fill("deliberately-wrong");
    await page.getByRole("button", { name: "Sign in" }).click();

    const alert = formAlert(page);
    await expect(alert).toHaveText("Those details were not accepted.");
    // MOD-007's review found a locked identity answering differently from a wrong password,
    // which identified every registered address in five requests. The interface must not
    // reintroduce the distinction in words.
    await expect(alert).not.toContainText(/locked|no such|unknown|not found/i);
    expect(new URL(page.url()).search).toBe("");
  });

  test("a refusal keeps the tenant and identifier and clears only the password", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByLabel("Tenant ID").fill(creds.tenantId);
    await page.getByLabel("Email or phone").fill(unknown);
    await page.getByLabel("Password").fill("deliberately-wrong");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(formAlert(page)).toBeVisible();

    await expect(page.getByLabel("Tenant ID")).toHaveValue(creds.tenantId);
    await expect(page.getByLabel("Email or phone")).toHaveValue(unknown);
    await expect(page.getByLabel("Password")).toHaveValue("");
  });

  test("a malformed tenant id is a field error, not a rejected credential", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Tenant ID").fill("not-a-uuid");
    await page.getByLabel("Email or phone").fill(creds.email);
    await page.getByLabel("Password").fill(creds.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByLabel("Tenant ID")).toHaveAttribute("aria-invalid", "true");
    // No alert: nothing was looked up, so nothing was refused.
    await expect(formAlert(page)).toHaveCount(0);
  });

  test("a correct sign-in lands on the admin page and sets an httpOnly session", async ({
    page,
    context,
  }) => {
    await signIn(page);

    await expect(page.getByRole("heading", { name: "Veyro Admin" })).toBeVisible();
    await expect(page.getByText(creds.identityId)).toBeVisible();

    const cookies = await context.cookies();
    const session = cookies.find((cookie) => cookie.name === "veyro_session");
    expect(session, "a session cookie must be set").toBeTruthy();
    // The browser must never be able to read the bearer token: MOD-007 stores a session only as
    // a SHA-256 digest so a stolen database cannot replay one, and handing the token to client
    // JavaScript would undo that by handing it to any XSS instead.
    expect(session!.httpOnly).toBe(true);
    expect(session!.sameSite).toBe("Strict");

    const reachableFromScript = await page.evaluate(() => document.cookie);
    expect(reachableFromScript).not.toContain("veyro_session");
  });

  test("the sign-in page sends an already-signed-in caller to the admin page", async ({ page }) => {
    await signIn(page);
    await page.goto("/login");
    await page.waitForURL("/");
    await expect(page.getByRole("heading", { name: "Veyro Admin" })).toBeVisible();
  });

  test("signing out clears the session and the admin page becomes unreachable", async ({
    page,
    context,
  }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("/login");

    expect((await context.cookies()).find((c) => c.name === "veyro_session")).toBeFalsy();

    await page.goto("/");
    await page.waitForURL("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("no page ever puts a credential in a URL", async ({ page }) => {
    // Watches every navigation and every request for the whole sign-in journey, which is the
    // general form of the defect rather than the one page it was found on.
    const urls: string[] = [];
    page.on("request", (request) => urls.push(request.url()));
    page.on("framenavigated", (frame) => urls.push(frame.url()));

    await signIn(page);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("/login");

    const leaked = urls.filter(
      (url) => url.includes(creds.password) || url.includes(encodeURIComponent(creds.password)),
    );
    expect(leaked, `credential appeared in ${leaked[0] ?? ""}`).toHaveLength(0);
  });
});
