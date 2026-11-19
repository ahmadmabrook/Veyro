"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Alert, Button, Field } from "@/components/controls";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { signIn } from "./actions";
import { SIGN_IN_IDLE, type SignInState } from "./state";

/**
 * The sign-in form.
 *
 * `action={formAction}` rather than `onSubmit`: see the long note in `actions.ts` for why that
 * is the security-relevant choice. The consequence here is that **every piece of state this
 * component holds is a progressive enhancement, never a control.** The empty-field messages
 * come back from the server in `state.missing`, so they are correct with JavaScript off; the
 * busy state comes from `useFormStatus`, so with JavaScript off there simply is no busy state
 * and the browser's own navigation spinner does the job.
 *
 * Four states, all rendered rather than implied: idle, submitting (the button is disabled and
 * `aria-busy`), field-empty (a per-field message associated by `aria-describedby`), and refused
 * (one `role="alert"`, announced without stealing focus).
 */
export function LoginForm({ locale }: { locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  const [state, formAction] = useActionState<SignInState, FormData>(signIn, SIGN_IN_IDLE);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        padding: "var(--space-10) var(--space-4)",
      }}
    >
      <form action={formAction} noValidate className="panel stack" style={{ width: "100%", maxWidth: "420px" }}>
        <h1>{text("login.title")}</h1>

        {state.error ? (
          <Alert tone={state.challenge ? "info" : "error"}>{text(state.error)}</Alert>
        ) : null}

        <Field
          id="tenant"
          name="tenant_id"
          label={text("login.tenant")}
          hint={text("login.tenantHint")}
          defaultValue={state.tenantId}
          autoComplete="off"
          inputMode="text"
          // Not `required`: the browser's own validation bubble is unstyled, untranslated and
          // replaces the associated message this form renders. `noValidate` is the other half,
          // and the server checks the same thing regardless.
          {...(state.missing.tenant ? { error: text("login.required") } : {})}
        />

        <Field
          id="identifier"
          name="identifier"
          label={text("login.identifier")}
          defaultValue={state.identifier}
          autoComplete="username"
          {...(state.missing.identifier ? { error: text("login.required") } : {})}
        />

        {/* **The password field goes away once a challenge is in flight**, and the challenge
            rides in a hidden field. MOD-007 has already taken the password; asking for it
            again after a security prompt is the habit a phishing page relies on, and
            re-sending it would mean a second scrypt for nothing. */}
        {state.challenge ? (
          <>
            <input type="hidden" name="challenge" value={state.challenge} />
            <Field
              id="recovery"
              name="recovery_code"
              label={text("login.recovery")}
              hint={text("login.recoveryHint")}
              autoComplete="one-time-code"
              inputMode="text"
              {...(state.missing.recovery ? { error: text("login.required") } : {})}
            />
          </>
        ) : (
          <Field
            id="password"
            name="password"
            type="password"
            label={text("login.password")}
            // No `defaultValue`: a refused attempt clears the password and only the password.
            autoComplete="current-password"
            {...(state.missing.password ? { error: text("login.required") } : {})}
          />
        )}

        <SubmitButton
          idle={state.challenge ? text("login.continue") : text("login.submit")}
          busy={text("login.working")}
        />
      </form>
    </div>
  );
}

/**
 * Its own component because `useFormStatus` reports the status of the form *above* it in the
 * tree -- called inside `LoginForm` it would always read `pending: false`, which is a busy
 * state that silently never appears.
 */
function SubmitButton({ idle, busy }: { idle: string; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" busy={pending} busyLabel={busy}>
      {idle}
    </Button>
  );
}
