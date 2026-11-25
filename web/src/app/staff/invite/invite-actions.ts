"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { EXPIRY_DAYS, missingFields, type InvitationMade } from "@/lib/invitations";

import { IDLE, type InviteState } from "./invite-state";

/**
 * Invite somebody. ADM-STF-03, ADR-0017.
 *
 * **One request, because the server makes it one act**: the invitation, its clubs and its
 * token commit together, so a partial outcome is not among the things this form reports.
 *
 * **The link comes back in the response and is rendered in place.** Only its digest is
 * stored, so this is the one moment the plaintext exists — and nothing sends it, which the
 * screen says rather than implying an email went out.
 */
export async function sendInvitation(
  _previous: InviteState,
  form: FormData,
): Promise<InviteState> {
  const email = String(form.get("email") ?? "").trim();
  const roleKey = String(form.get("role_key") ?? "");
  const tenantWide = String(form.get("tenant_wide") ?? "") === "on";
  const clubs = form.getAll("clubs").map(String).filter((one) => one.length > 0);
  const echo = { email, roleKey };

  const missing = missingFields(email, roleKey, clubs, tenantWide);
  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };

  try {
    const made = await api<InvitationMade>("/authz/invitations", {
      method: "POST",
      body: {
        email, role_key: roleKey,
        scopes: tenantWide
          ? [{ scope_type: "tenant" }]
          : clubs.map((location_id) => ({ scope_type: "location", location_id })),
        days: EXPIRY_DAYS,
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/staff/invite");
    return { ...IDLE, message: "sent", made, echo };
  } catch (error) {
    return { ...IDLE, echo, error: failure(error) };
  }
}

/** A fresh link, as a new invitation superseding the old. ADR-0017 D4. */
export async function resendInvitation(
  _previous: InviteState,
  form: FormData,
): Promise<InviteState> {
  const invitationId = String(form.get("invitation_id") ?? "");
  try {
    const made = await api<InvitationMade>(
      `/authz/invitations/${encodeURIComponent(invitationId)}/resend`,
      { method: "POST", body: { days: EXPIRY_DAYS, correlation_id: correlationId() } });
    revalidatePath("/staff/invite");
    return { ...IDLE, message: "resent", made };
  } catch (error) {
    return { ...IDLE, error: failure(error) };
  }
}

/**
 * Withdraw one nobody has accepted.
 *
 * **The reason is required**, because the row is the only record there is: `veyro_iam_app`
 * holds nothing outside `iam` and MOD-008 audits denials rather than allowed acts, so "who
 * stopped this and why" is answerable from that row or from nowhere.
 */
export async function withdrawInvitation(
  _previous: InviteState,
  form: FormData,
): Promise<InviteState> {
  const invitationId = String(form.get("invitation_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  if (reason.length === 0) return { ...IDLE, missing: { reason: true } };
  try {
    await api(`/authz/invitations/${encodeURIComponent(invitationId)}/revoke`, {
      method: "POST", body: { reason, correlation_id: correlationId() },
    });
    revalidatePath("/staff/invite");
    return { ...IDLE, message: "withdrawn" };
  } catch (error) {
    return { ...IDLE, error: failure(error) };
  }
}

/**
 * Which sentence a refusal gets.
 *
 * **Machine codes, not prose.** `ApiError.reason` is the backend's own machine-readable
 * reason and these three are stable strings backend tests pin; MOD-016's finding is about
 * matching *English words* in a sentence. A code that moved falls back to the generic
 * refusal, which is a safe degradation rather than a control that stops biting.
 */
function failure(error: unknown): InviteState["error"] {
  if (!(error instanceof ApiError)) return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) {
    return error.reason === "cannot_grant_what_you_do_not_hold"
      ? "invite.cannotGrant"
      : "invite.needsStepUp";
  }
  if (error.status === 409) {
    if (error.reason === "this_address_already_has_a_live_invitation") {
      return "invite.taken";
    }
    if (error.reason === "this_address_already_has_an_identity") {
      return "invite.hasIdentity";
    }
    return "invite.settled";
  }
  if (error.status === 422) return "invite.refused";
  return "error.network";
}
