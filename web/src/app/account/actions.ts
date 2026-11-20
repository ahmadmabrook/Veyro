"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  ApiError, SESSION_COOKIE, TENANT_COOKIE, api, correlationId, currentSession,
} from "@/lib/api";

import { IDLE, type AccountState } from "./state";

/**
 * The first writes in this app, and all four are a member acting on their own account.
 *
 * **None of them is gated by a permission, and that is the server's design rather than an
 * omission here.** `owned(session, identity_id)` refuses anything that is not the caller's own
 * with a 404, so there is nothing to authorize when the only subject you can name is
 * yourself. MOD-007's review found the opposite shipped: password changes, recovery-code
 * issuing and session listing were open to anyone holding the tenant UUID, because a tenant
 * header is not an authentication.
 *
 * **`revalidatePath` after each one**, because every one of these changes what the page it was
 * submitted from should say. A revoked session that still appears in the list is a reader
 * told the action did not work.
 *
 * **A refusal is not elaborated.** MOD-007 answers the same 401 to a wrong credential, a used
 * recovery code, an expired challenge and a locked identity -- all costing one scrypt -- and a
 * form that explained which would be an oracle about an account. The page says the action was
 * refused and what would make it work.
 */

async function act(run: () => Promise<AccountState>): Promise<AccountState> {
  try {
    return await run();
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network" };
    }
    // A 403 here means the session is too weak for what was asked, which for this page is
    // only ever the recovery-code action. Saying so is the difference between a reader
    // stepping up and a reader concluding the product is broken.
    if (error instanceof ApiError && (error.status === 403 || error.status === 401)) {
      return { ...IDLE, error: "account.needsStepUp" };
    }
    return { ...IDLE, error: "account.refused" };
  }
}

export async function revokeSession(
  _previous: AccountState,
  form: FormData,
): Promise<AccountState> {
  const sessionId = String(form.get("session_id") ?? "");
  return act(async () => {
    await api(`/sessions/${encodeURIComponent(sessionId)}/revoke`, {
      method: "POST",
      body: { correlation_id: correlationId(), reason: "revoked_by_user" },
    });
    revalidatePath("/account");
    return { ...IDLE, message: "account.revoked" };
  });
}

/**
 * Revoke a device -- including, deliberately, the one this page is being read in.
 *
 * **Revoking your own device ends the session that pressed the button**, because
 * `revoke_device` revokes every session on the device in the same transaction. The first
 * version returned a success message into a page that no longer had a session to render it
 * on: nothing appeared, the reader was left looking at a stale screen, and the next
 * navigation threw them to the sign-in page with no explanation. The most consequential
 * control on the surface gave no feedback at all.
 *
 * So the action asks the server whether it still has a session -- derived, not a hidden field
 * saying "this one is mine" -- and if it does not, clears the cookies and sends the reader to
 * sign-in with the reason named. That is also the honest end state: the revoke is permanent,
 * `_authenticate_in_tx` refuses a revoked device rather than challenging it, and this browser
 * cannot sign in again.
 */
export async function revokeDevice(
  _previous: AccountState,
  form: FormData,
): Promise<AccountState> {
  const deviceId = String(form.get("device_id") ?? "");
  const outcome = await act(async () => {
    await api(`/devices/${encodeURIComponent(deviceId)}/revoke`, {
      method: "POST",
      body: { correlation_id: correlationId(), reason: "revoked_by_user" },
    });
    revalidatePath("/account");
    return {
      ...IDLE, message: "account.revoked" as const,
      signedOut: (await currentSession()) === null,
    };
  });
  // **Outside `act`.** `redirect` works by throwing, and the catch in `act` would turn it
  // into "that was refused" -- a navigation reported to the reader as a failure.
  if (outcome.signedOut) {
    const jar = await cookies();
    jar.delete(SESSION_COOKIE);
    jar.delete(TENANT_COOKIE);
    redirect("/login?signed_out=device");
  }
  return outcome;
}

export async function trustDevice(
  _previous: AccountState,
  form: FormData,
): Promise<AccountState> {
  const deviceId = String(form.get("device_id") ?? "");
  return act(async () => {
    await api(`/devices/${encodeURIComponent(deviceId)}/trust`, {
      method: "POST",
      body: { correlation_id: correlationId() },
    });
    revalidatePath("/account");
    return { ...IDLE, message: "account.trusted" };
  });
}

/**
 * Mint a fresh batch of recovery codes, which needs a stepped-up session.
 *
 * **This is the action the step-up flow had no screen for.** A step-up spends a recovery code
 * and TOTP and passkeys are unverifiable in this build, so a recovery code is the only second
 * factor there is -- and without a way to reissue, a member who stepped up five times was out
 * of them with no path back. The loop now closes: step up (spending one), then reissue.
 *
 * **Issuing replaces every code that came before it.** The old batch stops working the moment
 * this returns, which is what makes reissuing a remedy for a batch somebody else may have
 * seen rather than merely a top-up. The page says so before the button, not after.
 */
export async function issueRecoveryCodes(
  _previous: AccountState,
  form: FormData,
): Promise<AccountState> {
  const identityId = String(form.get("identity_id") ?? "");
  return act(async () => {
    const issued = await api<{ codes: string[] }>(
      `/identities/${encodeURIComponent(identityId)}/recovery-codes`,
      { method: "POST", body: { correlation_id: correlationId() } },
    );
    revalidatePath("/account");
    return { ...IDLE, message: "account.codesIssued", codes: issued.codes ?? [] };
  });
}
