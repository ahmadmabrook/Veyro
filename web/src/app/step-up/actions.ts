"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, SESSION_COOKIE, api, correlationId } from "@/lib/api";
import { safeNext } from "@/lib/navigation";

import type { SecondFactor, StepUpState } from "./state";

/**
 * Raise this session's assurance, and replace the cookie, because the old session is gone.
 *
 * **MOD-007 revokes the session it steps up from and issues a fresh token.** `_step_up_in_tx`
 * sets `revoke_reason = 'stepped_up'` on the old row and opens a new one, which is right -- a
 * session's lifetime follows what it can do, and a level-2 window is twelve hours rather than a
 * fortnight. The consequence for this app is absolute: **a step-up that does not write the new
 * token into the cookie signs the reader out**, and it does so on the one path where they have
 * just proved who they are. The browser suite asserts the landing page afterwards for that
 * reason.
 *
 * **The challenge is fetched here rather than carried in the form.** A nonce is one-use and
 * bound to the session and the required level; a page that rendered one into a hidden field
 * would hand the reader a token that goes stale while they look for their recovery codes, and
 * the failure would read as "that code was not accepted". Asking `/auth/require` immediately
 * before posting is what the fixture does and what the protocol is for.
 *
 * **The refusal is not elaborated**, for MOD-007's own reason: a wrong code, a used code, an
 * expired challenge and an identity that has been locked all answer the same thing. Saying
 * which would turn this form into an oracle about somebody else's account.
 */
export async function stepUp(
  _previous: StepUpState,
  form: FormData,
): Promise<StepUpState> {
  const credential = String(form.get("credential") ?? "").trim();
  const factor: SecondFactor =
    form.get("factor") === "password" ? "password" : "recovery_code";
  const actionClass = ACTION_CLASSES.has(String(form.get("action_class")))
    ? String(form.get("action_class"))
    : "financial";
  // Validated here as well as on the page: a form field is as attacker-controllable as a query
  // string, and this is the value the redirect at the end follows.
  const next = safeNext(String(form.get("next") ?? ""));

  if (credential.length === 0) return { error: null, missing: true };

  let token: string | undefined;
  let state: StepUpState | null = null;
  try {
    const asked = await api<{
      step_up_required: boolean;
      reachable: boolean;
      challenge?: string;
    }>(`/auth/require/${actionClass}`);

    if (!asked.step_up_required) {
      // Somebody stepped up in another tab, or the gate was always satisfied. Nothing to do,
      // and spending a recovery code to discover that would be the wrong answer.
      token = undefined;
      state = null;
    } else if (!asked.reachable || !asked.challenge) {
      // Level 3 needs a hardware authenticator MOD-007 cannot verify. The page says so before
      // rendering a field; this is the race where somebody posts anyway.
      state = { error: "stepUp.unreachable", missing: false };
    } else {
      const stepped = await api<{ token?: string }>("/auth/step-up", {
        method: "POST",
        body: {
          challenge: asked.challenge,
          correlation_id: correlationId(),
          [factor]: credential,
        },
      });
      if (!stepped.token) state = { error: "stepUp.failed", missing: false };
      else token = stepped.token;
    }
  } catch (error) {
    if (error instanceof ApiError) {
      state =
        error.status === 429
          ? { error: "stepUp.tooMany", missing: false }
          : error.status === 503
            ? { error: "error.network", missing: false }
            : error.status === 401 || error.status === 403
              ? { error: "stepUp.failed", missing: false }
              : { error: "error.unexpected", missing: false };
    } else {
      throw error;
    }
  }

  if (state) return state;

  if (token) {
    const jar = await cookies();
    const secure = process.env.NODE_ENV === "production";
    // **The old token is revoked.** Not replacing it here is a sign-out dressed as a success.
    jar.set(SESSION_COOKIE, token, {
      httpOnly: true,
      sameSite: "strict",
      secure,
      path: "/",
    });
  }

  // Outside the try, because `redirect` signals by throwing and catching it here would turn a
  // successful step-up into `error.unexpected`.
  redirect(next);
}

/**
 * The four classes MOD-008 declares. A caller-supplied class reaches a path segment, so it is
 * matched against the set rather than passed through -- not because the backend would accept an
 * unknown one, but because a 422 from a URL the reader never typed is a worse answer than the
 * default.
 */
const ACTION_CLASSES = new Set([
  "routine",
  "financial",
  "privileged",
  "biometric_sensitive",
]);
