"use client";

import { useActionState } from "react";

import { Button } from "@/components/ds/button";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { checkIn } from "./actions";
import { IDLE, type CheckInState } from "./state";

/**
 * One row's check-in. FD-06's only control, and the only working write form in this app that
 * is not behind a step-up.
 *
 * **A form per row rather than one form with a row id**, because each row reports its own
 * outcome: a desk marking four people present in a row needs to see which one was refused,
 * and a single shared state would show the last answer against every button.
 *
 * **`size="lg"`, which is the design system's 44px.** Touch density makes it the minimum
 * target rather than a style, and the canvas says why this screen in particular: "Rows are
 * 48px because this is tapped while looking at a person, not at the screen."
 */
export function CheckInButton({
  locale, bookingId, sessionId, label,
}: {
  locale: Locale;
  bookingId: string;
  sessionId: string;
  /** What the control is for, built from what is not withheld. */
  label: string;
}) {
  const [state, action, pending] = useActionState<CheckInState, FormData>(checkIn, IDLE);
  return (
    <form action={action} className="ds-desk-checkin">
      <input type="hidden" name="booking_id" value={bookingId} />
      <input type="hidden" name="session_id" value={sessionId} />
      <Button
        type="submit" variant="primary" size="lg"
        label={t(locale, "desk.checkIn")}
        state={pending ? "loading" : state.checkedIn === bookingId ? "disabled" : "default"}
      />
      {/* The accessible name carries who this is, because fourteen buttons all reading
          "Check in" are fourteen controls a screen-reader user cannot tell apart. */}
      <span className="sr-only">{label}</span>
      {state.error !== null ? (
        <p className="ds-desk-row-error">{t(locale, state.error as MessageKey)}</p>
      ) : null}
    </form>
  );
}
