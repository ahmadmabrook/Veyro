import { expect, test } from "@playwright/test";

import { fixture } from "./fixture-env";

/**
 * Sign in with JavaScript entirely absent, by replaying the server-rendered form.
 *
 * This is the regression test for the defect a browser found by accident: the sign-in form was
 * a client component whose whole protection was `event.preventDefault()`, the dev server
 * blocked a cross-origin dev resource so the React tree never attached, and the form did what
 * an un-handled form does -- a native GET with `?tenant_id=&identifier=&password=`.
 *
 * **It uses `request`, not `page`.** Playwright's request context is an HTTP client with no
 * browser and no JavaScript at all, so this exercises exactly the path a reader with a broken
 * bundle takes: parse the HTML the server sent, post the fields that HTML declares, and check
 * what comes back. Three things have to hold -- the form it replayed really was a POST, a
 * session cookie was set, and no credential appears in any URL anywhere in the exchange,
 * including the redirect target.
 *
 * It was a standalone `node` script first, which worked locally against a dev server somebody
 * had already started and failed in CI with ECONNREFUSED: Playwright shuts its `webServer`
 * down when the run ends, so by the time a separate script ran there was nothing listening.
 * Folding it into the suite is also the answer to the drift this repository keeps naming --
 * two implementations of one check disagree eventually, and the day they do nobody can say
 * which is the policy.
 */

const creds = fixture();

/** Minimal HTML entity decoding, enough for the attribute values Next emits. */
function decode(text: string): string {
  return text
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

type ServedForm = {
  method: string;
  action: string;
  hidden: { name: string; value: string }[];
};

/** The sign-in form's method, action and hidden fields, exactly as served. */
function parseSignInForm(html: string): ServedForm {
  const start = html.indexOf("<form noValidate");
  expect(start, "the served HTML must contain the sign-in form").toBeGreaterThan(-1);
  const open = html.slice(start, html.indexOf(">", start) + 1);
  const block = html.slice(start, html.indexOf("</form>", start));
  const hidden = [...block.matchAll(/<input[^>]*type="hidden"[^>]*>/g)].map((match) => ({
    name: decode(/name="([^"]*)"/.exec(match[0])?.[1] ?? ""),
    value: decode(/value="([^"]*)"/.exec(match[0])?.[1] ?? ""),
  }));
  return {
    method: (/method="([^"]*)"/i.exec(open)?.[1] ?? "GET").toUpperCase(),
    action: /\saction="([^"]*)"/i.exec(open)?.[1] ?? "",
    hidden,
  };
}

test.describe("sign-in with no client runtime", () => {
  test("the served form is a POST carrying its own action field", async ({ request }) => {
    const form = parseSignInForm(await (await request.get("/login")).text());
    expect(form.method, "an un-hydrated GET form puts credentials in the URL").toBe("POST");
    expect(
      form.hidden.some((field) => field.name.startsWith("$ACTION")),
      `hidden fields were ${form.hidden.map((f) => f.name).join(", ") || "none"}`,
    ).toBe(true);
  });

  test("replaying it signs in, sets an httpOnly session, and leaks nothing to a URL", async ({
    playwright,
    baseURL,
  }) => {
    // A context of its own with redirects off, so the action's own redirect is visible rather
    // than followed: the `Location` header is one of the places a credential must not appear.
    const api = await playwright.request.newContext({ baseURL: baseURL! });
    const form = parseSignInForm(await (await api.get("/login")).text());

    const multipart: Record<string, string> = {};
    for (const field of form.hidden) multipart[field.name] = field.value;
    multipart.tenant_id = creds.tenantId;
    multipart.identifier = creds.email;
    multipart.password = creds.password;

    // **No `Next-Action` header, deliberately.** That header is how the *client runtime*
    // invokes an action; a browser with JavaScript off sends none, and the `$ACTION_ID_...`
    // field in the body is what Next reads instead. Sending it would test the path that
    // already works rather than the one this file exists for.
    const posted = await api.post(form.action || "/login", {
      multipart,
      maxRedirects: 0,
    });

    expect(posted.status(), await posted.text()).toBeLessThan(500);

    const headers = posted.headersArray();
    const setCookie = headers
      .filter((header) => header.name.toLowerCase() === "set-cookie")
      .map((header) => header.value);
    const session = setCookie.find((cookie) => cookie.startsWith("veyro_session="));
    expect(session, "the no-JavaScript path must actually sign in").toBeTruthy();
    expect(session!).toMatch(/HttpOnly/i);
    expect(session!).toMatch(/SameSite=strict/i);

    const location = posted.headers()["location"] ?? "";
    const body = await posted.text();
    for (const secret of [creds.password, creds.email]) {
      expect(location, "a credential reached the redirect target").not.toContain(secret);
      expect(body, "a credential was echoed into the response").not.toContain(secret);
    }

    await api.dispose();
  });
});
