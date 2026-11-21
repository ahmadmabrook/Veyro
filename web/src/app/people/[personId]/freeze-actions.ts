"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { freezeDays, isDay } from "@/lib/freeze";

import { IDLE, type FreezeState } from "./freeze-state";

/**
 * Freeze a membership. ADM-MSH-03, and COM-01-R04's annual allowance.
 *
 * **The second write in this app behind a stepped-up permission, and the first that is not
 * routine.** `membership.lifecycle.change` is financial class, so a password-only session
 * cannot reach it — which is why every form of this kind was absent until now and the
 * inventory said so. What makes it buildable is not a change to the permission but the
 * step-up this app already has: the page offers it with `next` back to the member, the way
 * the member record already offers one for a masked field. A step-up opens a twelve-hour
 * window, so this is one recovery code a shift rather than one an act.
 *
 * **The server is the authority on every figure.** This sends a start and a length; it never
 * sends a day count it computed against an allowance, and it never sends the allowance. The
 * module checks the contract, the start window and the allowance itself, under the
 * membership's own lock — "counting and then inserting without the lock is the race MOD-016
 * shipped for coupons; here it would let a member exceed a thirty-day allowance by sending
 * two requests at once."
 */
export async function freezeMembership(
  _previous: FreezeState,
  form: FormData,
): Promise<FreezeState> {
  const membershipId = String(form.get("membership_id") ?? "");
  const personId = String(form.get("person_id") ?? "");
  const from = String(form.get("from") ?? "").trim();
  const until = String(form.get("until") ?? "").trim();
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { from, until, reason };

  const missing: FreezeState["missing"] = {};
  if (!isDay(from)) missing.from = true;
  if (!isDay(until)) missing.until = true;
  if (reason.length === 0) missing.reason = true;
  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };

  const days = freezeDays(from, until);
  // The dates parse and the span does not, which is the one case the field-level check
  // above cannot name: UNTIL before FROM.
  if (days === null) return { ...IDLE, missing: { until: true }, echo };

  try {
    await api(`/memberships/${encodeURIComponent(membershipId)}/freeze`, {
      method: "POST",
      body: {
        // **`freeze`, not `medical_hold`.** The kind that escapes the allowance requires a
        // written piece of evidence and is a different conversation; offering it on this
        // form would make the allowance optional by choosing a radio button.
        freeze_kind: "freeze",
        starts_on: from,
        days,
        reason,
        idempotency_key: `freeze-${membershipId}-${from}-${days}`,
        correlation_id: correlationId(),
      },
    });
    revalidatePath(`/people/${personId}`);
    return { ...IDLE, message: "freeze.done" };
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network", echo };
    }
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany", echo };
    }
    // **403 is the step-up, not a refusal to act.** A reader who sees "that was refused"
    // goes and asks somebody for a grant they already hold; this one needs a stronger
    // sign-in and the page says so with the link.
    if (error instanceof ApiError && error.status === 403) {
      return { ...IDLE, error: "freeze.needsStepUp", echo };
    }
    // A 409 is the allowance or the membership's own state, both of which the panel above
    // the form shows — so it means something changed under the reader, not that they were
    // wrong. Saying "reload and look again" is the actionable sentence.
    if (error instanceof ApiError && error.status === 409) {
      return { ...IDLE, error: "freeze.conflict", echo };
    }
    return { ...IDLE, error: "freeze.refused", echo };
  }
}
