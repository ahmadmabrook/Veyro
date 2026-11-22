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
    // A refusal by the rate limiter is temporary and is the reader's to act on, which
    // "something went wrong" is not: the form says to wait rather than that it broke.
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany" };
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


/**
 * Store a credential the browser has just created.
 *
 * **The ceremony happens in the client and only its result crosses this boundary**, because
 * `navigator.credentials` exists nowhere else. What arrives is the credential id, the SPKI
 * public key and the backup flag, all base64url; the server loads the key and refuses one it
 * cannot verify, which is what keeps "a passkey is enrolled" and "a passkey can be used" the
 * same statement.
 *
 * **No challenge is sent, and `iam.challenges` has a `passkey_registration` kind nothing
 * writes.** A registration challenge is checked by verifying the attestation, which this build
 * deliberately does not do -- so issuing one and consuming it here would be a ceremony-shaped
 * control that checks nothing. What makes this safe is that it is authenticated and
 * self-scoped; what makes the credential trustworthy afterwards is that every assertion is
 * verified.
 */
export async function addPasskey(
  _previous: AccountState,
  form: FormData,
): Promise<AccountState> {
  const credentialId = String(form.get("webauthn_credential_id") ?? "");
  const publicKey = String(form.get("public_key") ?? "");
  const backedUp = String(form.get("backed_up") ?? "") === "true";
  const label = String(form.get("label") ?? "").trim();
  if (!credentialId || !publicKey) return { ...IDLE, error: "passkey.ceremonyFailed" };
  const session = await currentSession();
  if (!session) redirect("/login?reason=expired");
  return act(async () => {
    await api(`/identities/${encodeURIComponent(String(session.identity_id))}/passkeys`, {
      method: "POST",
      body: {
        webauthn_credential_id: credentialId,
        public_key: publicKey,
        backed_up: backedUp,
        label: label || null,
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/account");
    return { ...IDLE, message: "passkey.added" };
  });
}

/**
 * Withdraw a passkey.
 *
 * **The remedy that had to exist before the button that creates one.** Enrolling is routine
 * and self-scoped, and until `revoke_passkey` existed the only writer of `revoked_at` was the
 * clone check -- so a lost authenticator left a credential that could open a level-3 session
 * for ever. MOD-013's rule, from the side this repository has already paid for once in
 * MOD-019's insert-only rota: a write form needs its remedy before it needs its button.
 *
 * It does **not** end the session the reader is in, deliberately and unlike the clone path:
 * a clone means the credential exists in two places, a lost phone means it should open
 * nothing new, and signing somebody out while they are telling the product about it is a
 * worse answer than the problem.
 */
export async function withdrawPasskey(
  _previous: AccountState,
  form: FormData,
): Promise<AccountState> {
  const passkeyId = String(form.get("passkey_id") ?? "");
  return act(async () => {
    await api(`/passkeys/${encodeURIComponent(passkeyId)}/revoke`, {
      method: "POST",
      body: { correlation_id: correlationId() },
    });
    revalidatePath("/account");
    return { ...IDLE, message: "passkey.withdrawn" };
  });
}
