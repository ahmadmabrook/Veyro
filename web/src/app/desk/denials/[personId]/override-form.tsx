"use client";

import { useActionState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { t, type Locale, type MessageKey } from "@/i18n/locale";
import { OVERRIDE_REASONS } from "@/lib/denial";

import { overrideDenial } from "./actions";
import { IDLE, type OverrideState } from "./state";

/**
 * FD-03's "Let in, flag it", with the three reasons the canvas names.
 *
 * > "Letting him in records your name, the reason, and appears in the access log. **Choose a
 * > reason:** renewing today · manager approved · resolving a dispute."
 *
 * **Radio buttons rather than a select**, because three options a receptionist picks between
 * under pressure are three things to see at once, and the design writes them as a list. The
 * `lg` size carries the Touch density's 44px target.
 */
export function OverrideForm({
  locale, personId, pointId, decisionId,
}: {
  locale: Locale;
  personId: string;
  pointId: string;
  /** The refusal this press answers, which is what the write is keyed on. */
  decisionId: string;
}) {
  const [state, action, pending] =
    useActionState<OverrideState, FormData>(overrideDenial, IDLE);
  const text = (key: MessageKey) => t(locale, key);

  if (state.done) {
    return <Banner severity="info">{text("denial.overrideDone")}</Banner>;
  }

  return (
    <form action={action} className="ds-override-form">
      <input type="hidden" name="person_id" value={personId} />
      <input type="hidden" name="point_id" value={pointId} />
      <input type="hidden" name="decision_id" value={decisionId} />
      <fieldset className="ds-override-reasons">
        <legend>{text("denial.overrideReason")}</legend>
        {OVERRIDE_REASONS.map((reason, n) => (
          <label key={reason} className="ds-override-reason">
            <input type="radio" name="reason" value={reason} defaultChecked={n === 0} />
            {text(`denial.reason.${reason}` as MessageKey)}
          </label>
        ))}
      </fieldset>
      <Button
        type="submit" variant="secondary" size="lg"
        label={text("denial.overrideSubmit")}
        state={pending ? "loading" : "default"}
      />
      {state.error !== null ? (
        <Banner severity="critical">{text(state.error)}</Banner>
      ) : null}
    </form>
  );
}
