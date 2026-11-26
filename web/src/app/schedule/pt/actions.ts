"use server";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, type BookPtState } from "./state";

/**
 * ADM-SCH-05 · SCHEDULE PT — "Book · use 1 credit".
 *
 * **One write, and the server does the rest.** The session, the coach's hold, the member's
 * place and the credit commit in one transaction (ADR-0019 D5) — a session with no credit
 * drawn is a free PT session and a credit drawn with no session is a member charged for
 * nothing — so this action posts once and has no partial outcome to report.
 *
 * **No grant id is sent**, and that is the control rather than an omission: `reserve_
 * entitlement` reserves against the *grant's* own owner, so a form carrying both a member and
 * a grant would let a desk train one person on another's credit. The command picks it from
 * the member, soonest-expiring first, and the quote names the same one.
 *
 * **The refusal is told apart by its code**, because the canvas's two states have two
 * remedies: "sell a package first" and "pick another hour" are not the same sentence, and a
 * screen that merged them would send somebody to the wrong one.
 */
export async function bookPersonalSession(
  _previous: BookPtState, form: FormData,
): Promise<BookPtState> {
  const coachResourceId = String(form.get("coach_resource_id") ?? "").trim();
  const personId = String(form.get("person_id") ?? "").trim();
  const locationId = String(form.get("location_id") ?? "").trim();
  const startsAt = String(form.get("starts_at") ?? "").trim();
  const minutes = Number(form.get("minutes") ?? 0);
  // **The browser's key, so a double press is one booking.** Generated per submit rather than
  // per render: a key fixed at render time would make a *second deliberate* booking of another
  // hour read as a repeat of the first.
  const idempotencyKey = String(form.get("idempotency_key") ?? "").trim();

  try {
    const booked = await api<{
      session_id: string; coach_name: string; starts_at: string; ends_at: string;
      minutes: number; timezone: string; credits_remaining: number | null;
      repeated: boolean;
    }>("/scheduling/personal-sessions", {
      method: "POST",
      body: {
        coach_resource_id: coachResourceId, person_id: personId,
        location_id: locationId, starts_at: startsAt, minutes,
        idempotency_key: idempotencyKey, correlation_id: correlationId(),
      },
    });
    return {
      ...IDLE,
      booked: {
        sessionId: booked.session_id, coachName: booked.coach_name,
        startsAt: booked.starts_at, endsAt: booked.ends_at,
        minutes: booked.minutes, timezone: booked.timezone,
        creditsRemaining: booked.credits_remaining, repeated: booked.repeated,
      },
    };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 403) return { ...IDLE, error: "pt.needsPermission" };
      if (error.status === 429) return { ...IDLE, error: "error.tooMany" };
      // **The server's code, not a guess from the status.** Both of these are 409 and they
      // are the canvas's two different states: the remedy for one is a package and for the
      // other another hour.
      if (error.reason === "this_member_has_no_personal_training_credit") {
        return { ...IDLE, error: "pt.refusedNoCredit" };
      }
      if (error.reason.startsWith("the_coach_is_not_free")) {
        return { ...IDLE, error: "pt.refusedBusy" };
      }
      return { ...IDLE, error: "pt.refused" };
    }
    return { ...IDLE, error: "error.network" };
  }
}
