"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { Banner } from "@/components/ds/banner";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { stepUp } from "./actions";
import { STEP_UP_IDLE, type SecondFactor, type StepUpState } from "./state";

/**
 * The step-up form: one field, and everything else is said rather than implied.
 *
 * `action={formAction}` rather than `onSubmit`, for the reason written at the top of
 * `login/actions.ts`: a credential typed into this field must never be able to reach a query
 * string, and a client-side `preventDefault` is a control with a window on every page load.
 * With JavaScript off the browser posts the form and the step-up works.
 *
 * **Which factor is asked for comes from the server.** A session opened with a password cannot
 * raise itself with another password -- `policy.assurance_for` reads the distinct *kinds*, so
 * two of one kind is one factor -- and a session opened with a recovery code is the mirror
 * case. The page reads `/auth/session` and passes the answer in; this component never guesses.
 */
export function StepUpForm({
  locale,
  factor,
  actionClass,
  next,
}: {
  locale: Locale;
  factor: SecondFactor;
  actionClass: string;
  next: string;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [state, formAction] = useActionState<StepUpState, FormData>(stepUp, STEP_UP_IDLE);
  const isRecovery = factor === "recovery_code";

  return (
    <form
      action={formAction}
      noValidate
      className="panel stack"
      style={{ width: "100%", maxWidth: "420px" }}
    >
      <h1>{text("stepUp.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {text("stepUp.lead")}
      </p>
      <p className="muted" style={{ margin: 0 }}>
        {text(isRecovery ? "stepUp.whyRecovery" : "stepUp.whyPassword")}
      </p>

      {state.error ? <Banner severity="critical">{text(state.error)}</Banner> : null}

      <Field
        id="credential"
        name="credential"
        type={isRecovery ? "text" : "password"}
        label={text(isRecovery ? "stepUp.recovery" : "stepUp.password")}
        {...(isRecovery ? { description: text("stepUp.recoveryHint") } : {})}
        autoComplete={isRecovery ? "one-time-code" : "current-password"}
        {...(state.missing
          ? { message: { kind: "error" as const, text: text("stepUp.required") } }
          : {})}
      />

      {/* The server re-derives all three. They are here so the form works without JavaScript
          and so a refusal re-renders the same question rather than a different one. */}
      <input type="hidden" name="factor" value={factor} />
      <input type="hidden" name="action_class" value={actionClass} />
      <input type="hidden" name="next" value={next} />

      <SubmitButton locale={locale} />
    </form>
  );
}

/**
 * Its own component because `useFormStatus` reads the form it is *inside*: called in the
 * component that renders the `<form>`, it reports the parent form's state, which is always
 * idle here.
 */
function SubmitButton({ locale }: { locale: Locale }) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant="primary"
      label={t(locale, pending ? "stepUp.working" : "stepUp.submit")}
      state={pending ? "loading" : "default"}
    />
  );
}
