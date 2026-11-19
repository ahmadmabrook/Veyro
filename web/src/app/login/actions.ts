"use server";

/**
 * Sign-in, as a server action.
 *
 * **It is a server action and not a `fetch` from an `onSubmit` handler, and that is a security
 * decision rather than a stylistic one.** The first version of this page was a client form
 * calling `/api/auth/login`, and the whole of its protection rested on `event.preventDefault()`
 * having run. Driving it in a real browser produced this, immediately and by accident:
 *
 *     http://127.0.0.1:3000/login?tenant_id=&identifier=&password=
 *
 * The dev server had blocked a cross-origin dev resource, the React tree never attached, and
 * the form did what an un-handled form does -- a native GET, with every field in the query
 * string. The page looked identical. Nothing errored. **A password in a URL is in the address
 * bar, in browser history, in the server's access log and in every proxy between the two**,
 * and the Privacy rule this repository works under names it in as many words: never place
 * sensitive data in query strings.
 *
 * The cause that day was a dev-origin block, now fixed in `next.config.mjs`. The *shape* is
 * the one `CLAUDE.md` records for the backend over and over: a control that only works once
 * something else has happened is a control with a window. A client-side `preventDefault` is
 * exactly that, and the window is every millisecond before hydration on every page load, plus
 * every browser where the bundle fails to run at all.
 *
 * A server action closes it structurally. Without JavaScript the browser POSTs to the server
 * and the sign-in genuinely works; with JavaScript React intercepts and there is no navigation.
 * In both cases the credentials are in a request body and there is no arrangement of failures
 * that puts them anywhere else.
 */


import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, SESSION_COOKIE, TENANT_COOKIE, api, correlationId } from "@/lib/api";

// The state shape lives in `state.ts`: a `"use server"` module may export async functions and
// nothing else, so a constant declared here reaches the client as `undefined`. The file says
// what that cost.
import { browserFingerprint } from "@/lib/device";

import type { SignInState } from "./state";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function signIn(
  _previous: SignInState,
  form: FormData,
): Promise<SignInState> {
  const tenantId = String(form.get("tenant_id") ?? "").trim();
  const identifier = String(form.get("identifier") ?? "").trim();
  const password = String(form.get("password") ?? "");

  // A challenge in flight: the second act of the same sign-in, so the same action handles it
  // rather than a second route. The password is not re-sent -- MOD-007 already took it, and
  // a form that asked for it again would be training people to retype a password after a
  // security prompt, which is the shape a phishing page copies.
  const challenge = String(form.get("challenge") ?? "").trim();
  const recoveryCode = String(form.get("recovery_code") ?? "").trim();

  const missing = {
    tenant: tenantId.length === 0,
    identifier: identifier.length === 0,
    password: challenge ? false : password.length === 0,
    recovery: challenge ? recoveryCode.length === 0 : false,
  };
  // **The password is never echoed back**, so a refused attempt clears it and only it. The
  // other two are returned because retyping a tenant UUID to fix a typo in a password is the
  // kind of friction that makes people paste credentials into the wrong field.
  const echo = { tenantId, identifier, challenge: challenge || null };

  if (missing.tenant || missing.identifier || missing.password || missing.recovery) {
    return { error: null, missing, ...echo };
  }
  // The backend shape-checks `X-Veyro-Tenant` and answers 422 for a malformed one. Catching it
  // here turns a generic refusal into a field error, which is the honest distinction: a
  // malformed tenant id is a typo, not a rejected credential. It discloses nothing, because
  // the shape of a UUID is not a secret and no lookup has happened.
  if (!UUID.test(tenantId)) {
    return { error: null, missing: { ...missing, tenant: true }, ...echo };
  }

  let token: string | undefined;
  let state: SignInState | null = null;
  try {
    // One response type for both acts, so narrowing is not needed to read the nonce: a
    // union of two object shapes makes `result.challenge` `{}` on the branch that does not
    // declare it, which is a type error standing in for a real question -- which of the two
    // calls can return a challenge. Both can: `/auth/challenge` re-challenges a wrong code.
    type LoginAnswer = { token?: string; challenge?: string; aal?: number };
    const result: LoginAnswer = challenge
      ? await api<LoginAnswer>("/auth/challenge", {
          method: "POST",
          authenticated: false,
          tenantId,
          body: {
            identifier,
            challenge,
            recovery_code: recoveryCode,
            correlation_id: correlationId(),
          },
        })
      : await api<LoginAnswer>("/auth/login", {
          method: "POST",
          authenticated: false,
          tenantId,
          body: {
            identifier,
            password,
            correlation_id: correlationId(),
            // **One fingerprint per browser, not per attempt.** A fresh value on every
            // submission makes every sign-in look like a new device, so MOD-007 challenges
            // every one -- which trains people to spend a recovery code to get in and burns
            // the budget that exists for a real lockout. It is derived from the tenant and
            // the identifier so it is stable without this app storing anything about the
            // reader, and it is honest about what it is: a label, not a measurement.
            device_fingerprint: browserFingerprint(tenantId, identifier),
            device_label: "Veyro web",
          },
        });
    // A challenged login is not a failure and not a session: MOD-007 wants a second factor
    // before it trusts a device it has not seen. The form asks for one and posts it back.
    if (!result.token) {
      state = {
        error: "login.challenge",
        missing,
        ...echo,
        challenge: result.challenge ?? challenge ?? null,
      };
    } else {
      token = result.token;
    }
  } catch (error) {
    if (error instanceof ApiError) {
      // **The refusal is not elaborated.** MOD-007's review found a locked identity answering
      // 423 in two milliseconds while everything else answered 401 in fifty, which identified
      // every registered address in five requests; every refusal there now costs one scrypt
      // and returns the same 401. Passing the backend's distinctions through to a reader here
      // would hand back exactly what that fix removed.
      state =
        error.status === 429
          ? { error: "login.tooMany", missing, ...echo }
          : error.status === 503
            ? { error: "error.network", missing, ...echo }
            : error.status === 401 || error.status === 403
              ? { error: "login.failed", missing, ...echo }
              : { error: "error.unexpected", missing, ...echo };
    } else {
      throw error;
    }
  }

  if (state) return state;
  if (!token) return { error: "error.unexpected", missing, ...echo };

  const jar = await cookies();
  // `secure` outside development, because a session cookie on plain HTTP is a session cookie
  // on the wire. `sameSite: "strict"` because nothing in this product is a legitimate
  // cross-site POST -- and with a server action that is now literally true of sign-in too.
  const secure = process.env.NODE_ENV === "production";
  jar.set(SESSION_COOKIE, token, { httpOnly: true, sameSite: "strict", secure, path: "/" });
  // The tenant is not a secret and the API wants it on every call, so it rides alongside --
  // still httpOnly, because no client code needs to read it either.
  jar.set(TENANT_COOKIE, tenantId, { httpOnly: true, sameSite: "strict", secure, path: "/" });

  // Outside the try: `redirect` signals by throwing, and catching it here would turn a
  // successful sign-in into `error.unexpected`.
  redirect("/");
}
