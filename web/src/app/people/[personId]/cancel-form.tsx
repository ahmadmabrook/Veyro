"use client";

import { useActionState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";

import { cancelMembership } from "./cancel-actions";
import { IDLE, type CancelState } from "./cancel-state";

/**
 * ADM-MSH-07's reason and its two buttons.
 *
 * **The consequence panel is not in here, and that is the difference from the freeze.** A
 * freeze's cost changes as the dates are typed, so its panel lives inside the form and fills
 * in; a cancellation's cost is fixed before anybody types anything — it is the contract's
 * arithmetic over today — so it is rendered by the server beside this, from the quote. A
 * figure recomputed in the client would be the second definition this screen exists to
 * avoid.
 *
 * **The fee and the version travel as hidden fields**, which is what makes the disclosure
 * provable: the command compares the figure sent against the one it recomputes and refuses a
 * mismatch, so the number on screen and the number applied are the same number or the write
 * does not happen. A form that sent no fee would be allowed — the module permits a
 * staff-initiated cancellation that discloses nothing — and would quietly turn this screen
 * into one of those.
 *
 * **"Keep it" is a link, not a button.** The canvas draws these as side sheets over Member
 * 360 and this app has no side sheets, so the sheet is a query parameter on the membership
 * tab: leaving is going back to the tab without it. Rendering it as a `<button>` that did
 * nothing, or as a second submit, is how a destructive form gets confirmed by somebody
 * reaching for the way out.
 */
export function CancelForm({
  locale, personId, membershipId, feeMinor, currency, version, feeText, backHref,
}: {
  locale: Locale;
  personId: string;
  membershipId: string;
  feeMinor: number;
  currency: string;
  version: number;
  /** The fee as the panel above rendered it, so the button names the same figure. */
  feeText: string;
  backHref: string;
}) {
  const [state, action, pending] =
    useActionState<CancelState, FormData>(cancelMembership, IDLE);
  const text = (key: MessageKey) => t(locale, key);

  if (state.message !== null && state.recorded !== null) {
    // **The confirmation states what was recorded, not what was typed.** The command returns
    // the effective date and the fee it actually applied; echoing the form back would be the
    // shape MOD-017's own repeat path was fixed for -- a caller told its figure was accepted
    // when the recorded one was something else.
    return (
      <Banner severity="info">
        {fill(locale, "cancel.doneOn", { date: state.recorded.accessEndsOn })}
      </Banner>
    );
  }

  return (
    <form action={action} className="ds-freeze-form">
      <input type="hidden" name="membership_id" value={membershipId} />
      <input type="hidden" name="person_id" value={personId} />
      <input type="hidden" name="fee_minor" value={String(feeMinor)} />
      <input type="hidden" name="currency" value={currency} />
      <input type="hidden" name="version" value={String(version)} />

      <Field
        id={`cancel-reason-${membershipId}`} name="reason" type="text" required
        rarer="optional"
        label={text("cancel.reason")}
        description={text("cancel.reasonWhy")}
        placeholder={text("cancel.reasonHint")}
        defaultValue={state.echo.reason ?? ""}
        message={state.missing.reason
          ? { kind: "error", text: text("cancel.reasonNeeded") } : null}
      />

      {/* **One primary, and it names the figure.** The design system's rule is one primary
          per view, and on a destructive screen the primary is the destructive act -- the
          canvas draws "Cancel membership" as the filled button with "Keep it" beside it.
          Putting the fee in the label is the canvas's own money-before-commit discipline
          applied to the control rather than only to the panel. */}
      <div className="ds-cancel-actions">
        <Button
          type="submit" variant="primary" size="lg"
          label={fill(locale, "cancel.submit", { fee: feeText })}
          state={pending ? "loading" : "default"}
        />
        <Button variant="secondary" size="lg" href={backHref} label={text("cancel.keep")} />
      </div>

      {state.error !== null ? (
        <Banner severity="critical">{t(locale, state.error)}</Banner>
      ) : null}
    </form>
  );
}
