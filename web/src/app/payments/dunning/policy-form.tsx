"use client";

import { useActionState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { writeDunningPolicy } from "./actions";
import { IDLE, type DunningState } from "./state";

/**
 * ADM-PAY-06's two rules, in the canvas's own sentence form.
 *
 * **`Field`'s `prefix` and `suffix` are what make it a sentence**, and the division is the
 * component's own contract: both are decorative and excluded from the accessible name, so the
 * `label` carries the whole meaning a screen reader hears ("Times to retry a failed card")
 * while the two halves draw the sentence a sighted reader reads ("Retry the card [2] times,
 * one day apart."). A sentence assembled out of spans with the control in the middle would be
 * a field with no accessible name at all.
 *
 * **One refusal per thing a reader can get wrong**, because a disabled button with no reason
 * is the control nobody can act on: not a whole number, outside its band, and the step-up this
 * permission needs. The bands are re-checked in the action and again by the route's own body.
 */
export function PolicyForm({
  locale, retryAttempts, accessGraceDays, canWrite, stepUpHref,
}: {
  locale: Locale;
  retryAttempts: number;
  accessGraceDays: number;
  canWrite: boolean;
  /** Where to send a session that could step up, or `null` when nothing would help. */
  stepUpHref: string | null;
}) {
  const [state, action, pending] = useActionState<DunningState, FormData>(
    writeDunningPolicy, IDLE);
  // **The value a reader types back stays ASCII, and the setting does not reach it.** Every
  // *rendered* figure in this app follows `localization.numerals` -- and a form field is not a
  // rendered figure: on an `arab` tenant `formatInteger` would put `\u0662` in the box and the
  // action's own `/^\d+$/` would refuse the tenant's own digits. `String()` rather than the
  // formatter, which is the one place in this app that is correct.
  const retry = state.echo.retry ?? String(retryAttempts);
  const grace = state.echo.grace ?? String(accessGraceDays);

  const text = (key: MessageKey) => t(locale, key);

  return (
    <form action={action} className="stack">
      {state.error !== null ? (
        <Banner severity={state.error === "error.network" ? "critical" : "info"}
          actions={state.error === "dunning.needsStepUp" && stepUpHref !== null
            ? <Button size="sm" href={stepUpHref} label={text("gate.stepUp")} />
            : undefined}>
          {text(state.error)}
        </Banner>
      ) : state.saved !== null ? (
        <Banner severity="info">{text("dunning.saved")}</Banner>
      ) : null}

      {/* **Whole numbers typed, not stepped.** The canvas writes a figure into a sentence, and
          a spinner beside a word is a control that reads as part of the prose. `inputMode`
          numeric keeps a phone's keypad without making the field a `number` input, whose
          browser-chrome arrows this app's field shell does not style. */}
      <Field
        id="dunning-retry"
        name="retry_attempts"
        type="number"
        label={text("dunning.retryLabel")}
        prefix={text("dunning.retryPrefix")}
        suffix={text("dunning.retrySuffix")}
        defaultValue={retry}
        describedBy="dunning-grace-note"
      />

      <Field
        id="dunning-grace"
        name="access_grace_days"
        type="number"
        label={text("dunning.graceLabel")}
        prefix={text("dunning.gracePrefix")}
        suffix={text("dunning.graceSuffix")}
        defaultValue={grace}
        describedBy="dunning-grace-note"
      />

      <p className="ds-note" id="dunning-grace-note">
        {text("dunning.outOfBand")}
      </p>

      {/* **Never a locked control with no route.** A reader who may not write gets the
          sentence and the step-up where one would help; a reader the gate refuses outright
          gets neither, because a button that answered 403 is worse than its absence. */}
      {canWrite ? (
        <Button variant="primary" type="submit" label={text("dunning.save")}
          state={pending ? "loading" : "default"} />
      ) : (
        <Banner severity="info"
          actions={stepUpHref === null
            ? undefined
            : <Button size="sm" href={stepUpHref} label={text("gate.stepUp")} />}>
          {text("dunning.needsStepUp")}
        </Banner>
      )}
    </form>
  );
}
