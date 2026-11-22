"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, type CheckInState } from "./state";

/**
 * Mark somebody present. FD-06's only write.
 *
 * **Routine, and that is the unusual part.** `booking.attendance.write` is `data_access` with
 * no financial class, so a front desk can do this at an ordinary password sign-in — which is
 * why this screen has a working button where every `tenancy.*`, `catalog.*` and `finance.*`
 * form in this app is a step-up or an absence. MOD-020's own gap note said a front desk
 * could not check anybody in; this is the half of that which needed no new permission.
 *
 * **`front_desk`, chosen by the screen rather than taken from the body.** `CHECKIN_SOURCES`
 * has four values and one of them is `device`: a form that let its caller say the turnstile
 * had read the card would be writing a claim about hardware nobody touched, which is
 * MOD-012's `validated` shape and MOD-021's whole argument about fabricated evidence. The
 * source is what this screen *is*.
 */
export async function checkIn(
  _previous: CheckInState, form: FormData,
): Promise<CheckInState> {
  const bookingId = String(form.get("booking_id") ?? "");
  const sessionId = String(form.get("session_id") ?? "");
  try {
    await api(`/booking/bookings/${encodeURIComponent(bookingId)}/check-in`, {
      method: "POST",
      body: { source: "front_desk", correlation_id: correlationId() },
    });
    revalidatePath(`/desk/classes/${sessionId}`);
    return { ...IDLE, checkedIn: bookingId };
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network" };
    }
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany" };
    }
    if (error instanceof ApiError && error.status === 403) {
      return { ...IDLE, error: "desk.checkInNotPermitted" };
    }
    // **A 409 here is the window, and it is the one refusal worth its own sentence.**
    // `check_in` refuses outside the policy's check-in window and refuses a booking that is
    // no longer open — a settled no-show, a cancellation. A desk told only "that was
    // refused" would try again; told which, they know whether to fetch a manager.
    if (error instanceof ApiError && error.status === 409) {
      return { ...IDLE, error: "desk.checkInTooLate" };
    }
    return { ...IDLE, error: "desk.checkInRefused" };
  }
}
