"use server";

/**
 * The app-wide server actions: sign out, and the two presentation preferences.
 *
 * All three are **server actions rather than route handlers or client state**, for the reason
 * the login form is one: a form whose `action` is a server action POSTs and works whether or
 * not the client bundle ever ran, and nothing it carries is ever in a URL.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { SESSION_COOKIE, TENANT_COOKIE } from "@/lib/api";
import {
  LOCALE_COOKIE,
  PREFERENCE_MAX_AGE,
  THEME_COOKIE,
  parseLocaleStrict,
  parseThemeStrict,
} from "@/lib/preferences";

/**
 * Drop the session cookies and go back to sign-in.
 *
 * **This does not revoke the session server-side**, and that is a real gap rather than an
 * oversight: MOD-007 has `/identities/{id}/sessions` for listing and revoking, but no
 * "revoke the one I am holding" route, and inventing a revocation here by calling a route
 * that revokes *all* of them would sign the member out of their phone because they closed a
 * browser tab. Clearing the cookie makes the token unreachable from this browser; the token
 * itself stays valid until it expires. Named in web/README.md.
 */
export async function signOut(): Promise<never> {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  jar.delete(TENANT_COOKIE);
  redirect("/login");
}

/**
 * Set the interface language.
 *
 * The value is narrowed against the closed set before it is stored, because this cookie is
 * echoed into `lang` and `dir` on `<html>` on the next render. A cookie that could hold any
 * string would be an attribute-injection sink one `document.cookie` away.
 */
export async function setLocale(formData: FormData): Promise<void> {
  const locale = parseLocaleStrict(formData.get("locale"));
  if (locale) {
    const jar = await cookies();
    jar.set(LOCALE_COOKIE, locale, {
      sameSite: "lax",
      path: "/",
      maxAge: PREFERENCE_MAX_AGE,
    });
  }
  // No redirect: the action re-renders the current route, which is what a preference change
  // should do. A redirect would lose the page the reader was on.
}

export async function setTheme(formData: FormData): Promise<void> {
  const theme = parseThemeStrict(formData.get("theme"));
  if (theme) {
    const jar = await cookies();
    jar.set(THEME_COOKIE, theme, {
      sameSite: "lax",
      path: "/",
      maxAge: PREFERENCE_MAX_AGE,
    });
  }
}
