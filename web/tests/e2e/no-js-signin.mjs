#!/usr/bin/env node
/**
 * Sign in with JavaScript entirely absent, by replaying the server-rendered form.
 *
 * This is the regression test for the defect the browser found: a client-side form whose only
 * protection was `event.preventDefault()` did a native GET when the React tree had not attached,
 * and put `?tenant_id=&identifier=&password=` in the address bar. The form is a server action
 * now, so the un-hydrated path is a POST that genuinely works -- and this script is what says so
 * rather than asserting it.
 *
 * It parses the HTML the server sends, posts exactly the fields that HTML declares, and checks
 * three things: the response sets a session cookie, no credential appears in any URL anywhere in
 * the exchange (including every redirect `Location`), and the form it replayed really was a POST.
 *
 *   node tests/e2e/no-js-signin.mjs
 *
 * Needs a running web app and backend, and `web/.env.e2e.local` from `fixture.mjs`.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const web = process.env.VEYRO_WEB_ORIGIN ?? "http://127.0.0.1:3000";

function loadFixture() {
  const path = fileURLToPath(new URL("../../.env.e2e.local", import.meta.url));
  const env = Object.fromEntries(
    readFileSync(path, "utf8")
      .split("\n")
      .filter((line) => line && !line.startsWith("#"))
      .map((line) => {
        const at = line.indexOf("=");
        return [line.slice(0, at), line.slice(at + 1)];
      }),
  );
  for (const key of ["VEYRO_E2E_TENANT_ID", "VEYRO_E2E_EMAIL", "VEYRO_E2E_PASSWORD"]) {
    if (!env[key]) throw new Error(`${key} missing from web/.env.e2e.local -- run fixture.mjs`);
  }
  return env;
}

/** Minimal HTML entity decoding, enough for the attribute values Next emits. */
function decode(text) {
  return text
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

/** The sign-in form's method, action and hidden fields, exactly as served. */
function parseSignInForm(html) {
  const start = html.indexOf("<form noValidate");
  if (start < 0) throw new Error("no sign-in form in the served HTML");
  const open = html.slice(start, html.indexOf(">", start) + 1);
  const block = html.slice(start, html.indexOf("</form>", start));
  const method = (/method="([^"]*)"/i.exec(open)?.[1] ?? "GET").toUpperCase();
  const action = /\saction="([^"]*)"/i.exec(open)?.[1] ?? "";
  const hidden = [...block.matchAll(/<input[^>]*type="hidden"[^>]*>/g)].map((match) => {
    const tag = match[0];
    return {
      name: decode(/name="([^"]*)"/.exec(tag)?.[1] ?? ""),
      value: decode(/value="([^"]*)"/.exec(tag)?.[1] ?? ""),
    };
  });
  return { method, action, hidden };
}

const failures = [];
function check(label, condition, detail = "") {
  if (condition) {
    console.log(`  ok    ${label}`);
  } else {
    console.log(`  FAIL  ${label}${detail ? ` -- ${detail}` : ""}`);
    failures.push(label);
  }
}

const fixture = loadFixture();
const secrets = [fixture.VEYRO_E2E_PASSWORD, fixture.VEYRO_E2E_EMAIL];

console.log("no-JS sign-in against", web);

const page = await fetch(`${web}/login`);
const html = await page.text();
const form = parseSignInForm(html);

check("the served form is a POST", form.method === "POST", `got ${form.method}`);
check(
  "the served form declares at least one action field",
  form.hidden.some((field) => field.name.startsWith("$ACTION")),
  JSON.stringify(form.hidden.map((f) => f.name)),
);

const body = new FormData();
for (const field of form.hidden) body.append(field.name, field.value);
body.append("tenant_id", fixture.VEYRO_E2E_TENANT_ID);
body.append("identifier", fixture.VEYRO_E2E_EMAIL);
body.append("password", fixture.VEYRO_E2E_PASSWORD);

// `redirect: "manual"` so the action's own redirect is visible rather than followed: the
// `Location` header is one of the places a credential must not appear.
// No `Next-Action` header, deliberately: that header is how the *client runtime* invokes an
// action. A browser with JavaScript off sends none, and the `$ACTION_ID_...` hidden field in
// the body is what Next reads instead -- so sending the header here would test the path that
// already works rather than the one this script exists for.
const posted = await fetch(`${web}${form.action || "/login"}`, {
  method: "POST",
  body,
  redirect: "manual",
});

const setCookie = posted.headers.getSetCookie?.() ?? [];
const location = posted.headers.get("location") ?? "";
const responseText = await posted.text();
if (process.env.VEYRO_E2E_DEBUG) {
  // Cookie *values* are redacted even behind the debug flag. A session token printed to a
  // terminal is a session token in scrollback and in whatever CI collects, and a debug switch
  // that leaks one is a worse defect than whatever it was switched on to diagnose.
  const names = setCookie.map((cookie) => `${cookie.split("=")[0]} [redacted]`);
  console.log("  debug status", posted.status, "location", location, "cookies", names.join(", "));
}

check(
  "the sign-in POST was accepted",
  posted.status < 500,
  `status ${posted.status} ${responseText.slice(0, 200)}`,
);
check(
  "a session cookie was set",
  setCookie.some((cookie) => cookie.startsWith("veyro_session=")),
  setCookie.map((c) => c.split("=")[0]).join(",") || "none",
);
check(
  "the session cookie is httpOnly",
  setCookie
    .filter((cookie) => cookie.startsWith("veyro_session="))
    .every((cookie) => /httponly/i.test(cookie)),
);
check(
  "no credential appears in the redirect target",
  secrets.every((secret) => !location.includes(secret)),
  location,
);
check(
  "no credential appears in the response body",
  secrets.every((secret) => !responseText.includes(secret)),
);

// And the thing the original defect actually was: a GET whose query string carried the fields.
check(
  "the form cannot submit credentials as a query string",
  form.method === "POST",
);

console.log(failures.length === 0 ? "\nPASS" : `\nFAIL (${failures.length})`);
process.exit(failures.length === 0 ? 0 : 1);
