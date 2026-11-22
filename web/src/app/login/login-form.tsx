"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { Banner } from "@/components/ds/banner";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { signIn } from "./actions";
import { PasskeySignIn } from "./passkey-button";
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
/** The form's own id, so the passkey button can read the two fields it needs at press time. */
const FORM_ID = "sign-in";

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
      <form
        id={FORM_ID}
        action={formAction}
        noValidate
        className="page-section"
        style={{ width: "100%", maxWidth: "420px" }}
      >
        {/* **The brand lockup, which ADM-AUTH-01 puts above the heading.** A sign-in page is
            the one screen with no chrome around it, so the mark is what says which product
            this is -- and without it the form reads as any form on any host, which is the
            page where that matters most. 24px tile at radius 5 on the warm.900 ground,
            with the name at 15/1.2, tracking -.012em: the canvas's own measurements. */}
        <div className="ds-login-brand">
          <span className="ds-login-mark" aria-hidden="true">{text("app.mark")}</span>
          <span className="ds-login-name">{text("app.name")}</span>
        </div>
        <h1>{text("login.title")}</h1>

        {state.error ? (
          <Banner severity={state.challenge ? "info" : "critical"}>{text(state.error)}</Banner>
        ) : null}

        <Field
          id="tenant"
          name="tenant_id"
          label={text("login.tenant")}
          description={text("login.tenantHint")}
          defaultValue={state.tenantId}
          autoComplete="off"
          // Not `required`: the browser's own validation bubble is unstyled, untranslated and
          // replaces the associated message this form renders. `noValidate` is the other half,
          // and the server checks the same thing regardless.
          {...(state.missing.tenant ? { message: { kind: "error" as const, text: text("login.required") } } : {})}
        />

        <Field
          id="identifier"
          name="identifier"
          label={text("login.identifier")}
          defaultValue={state.identifier}
          autoComplete="username"
          {...(state.missing.identifier ? { message: { kind: "error" as const, text: text("login.required") } } : {})}
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
              description={text("login.recoveryHint")}
              autoComplete="one-time-code"
              {...(state.missing.recovery ? { message: { kind: "error" as const, text: text("login.required") } } : {})}
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
            {...(state.missing.password ? { message: { kind: "error" as const, text: text("login.required") } } : {})}
          />
        )}

        <SubmitButton
          idle={state.challenge ? text("login.continue") : text("login.submit")}
          busy={text("login.working")}
        />

        {/* **The canvas's note box, and both sentences in it are true of this build.**
            ADM-AUTH-01 ends with a note rather than a link, and the first half is the one
            MOD-007's review paid for: a locked identity used to answer 423 in under two
            milliseconds while everything else answered 401 in fifty, which identified every
            registered address in five requests. Every refusal now costs one scrypt and
            returns the same 401.

            The second half is where the design and this build differ, and the honest place
            to say so: the canvas resolves the tenant from the email domain and there is no
            such resolution here -- `/auth/login` takes a tenant header, and inventing a
            domain-to-tenant map would be inventing product. So the field above is real and
            the reason it exists is stated, rather than a lookup that does not happen being
            implied by its absence.

            **And there is no "Forgotten your password?".** MOD-007 has a recovery path and
            no form for it in this build; a link to a page that does not exist is worse than
            the gap it hides, which is ADM-MEM-05's rule. */}
        {/* **Beside the password, not instead of it**, and only while no challenge is in
            flight: a challenge is the second act of a password sign-in, and offering a
            different credential in the middle of one would abandon a ceremony the server is
            already holding a nonce for. It is the only second factor on this surface that
            spends nothing -- a step-up burns a recovery code and there are ten -- and the
            only one that reaches level 3. */}
        {state.challenge ? null : <PasskeySignIn locale={locale} formId={FORM_ID} />}

        <p className="ds-login-note">{text("login.sameMessage")}</p>
        <p className="ds-login-note">{text("login.tenantIsNotResolved")}</p>
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
    <Button
      type="submit"
      variant="primary"
      // The label stays while loading -- the contract says a spinner never replaces it -- so
      // the busy wording is the label rather than a separate one that swaps in.
      label={pending ? busy : idle}
      state={pending ? "loading" : "default"}
      fullWidth
    />
  );
}
