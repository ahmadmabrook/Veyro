"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { t, type Locale, type MessageKey } from "@/i18n/locale";
import {
  creationOptions, enrolmentPayload, hasUsableKey, passkeyState, usable, type PasskeyFact,
} from "@/lib/passkey";
import { useCeremonyAvailable } from "@/lib/use-ceremony";
import { utcStamp } from "@/lib/time";

import { addPasskey, withdrawPasskey } from "./actions";
import { IDLE, type AccountState } from "./state";

/**
 * Enrolling and withdrawing a passkey -- the first ceremony in this app.
 *
 * **A client component because `navigator.credentials` exists nowhere else.** Everything
 * decided here is decided in `@/lib/passkey`, which imports nothing that reaches
 * `next/headers`: a client component that pulled in a module touching the request fails the
 * whole app's build, which this repository has paid for once when the account page's first
 * version made the *login* page answer 500.
 *
 * **The ceremony and the write are two steps and the second is a form submission.** The
 * browser produces a credential, this component puts its three fields into a form and submits
 * it, and the server action stores it. Doing the POST from here instead would mean the client
 * holding a bearer token, which it does not and must not: the session cookie is httpOnly
 * precisely so page JavaScript cannot read it.
 *
 * **What it says when it cannot help.** Three different refusals, because the remedies differ:
 * a browser with no WebAuthn at all gets a sentence and no button; one that can create a
 * credential but cannot hand over the public key in SPKI DER is told to use a current browser,
 * because enrolling would store something that could never sign in; and a cancelled or failed
 * ceremony says nothing was saved.
 */

export function PasskeySection({
  locale, identityId, displayName, identifier, passkeys,
}: {
  locale: Locale;
  identityId: string;
  displayName: string;
  identifier: string;
  passkeys: PasskeyFact[];
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [state, action, pending] = useActionState<AccountState, FormData>(addPasskey, IDLE);
  // **The withdrawal's result lives here rather than in the row, because the row removes
  // itself.** Each row rendered its own form with its own `useActionState`, and withdrawing
  // made `usable(passkey)` false -- which unmounts the button *and* the state holding the
  // message it had just produced, so the most consequential control in this section said
  // nothing when it worked. That is verbatim MOD-007's recorded shape: `revokeDevice`
  // "returned a success message into a page that no longer had a session to render it on".
  // Found by a browser test asserting the sentence; nothing else could see it, because the
  // row visibly changes state either way.
  //
  // One state for every row is right rather than merely convenient: only one withdrawal
  // happens at a time, and a result that belongs to the section is where a reader who
  // pressed and looked away will find it.
  const [withdrawn, withdrawAction, withdrawing] =
    useActionState<AccountState, FormData>(withdrawPasskey, IDLE);
  const [ceremony, setCeremony] = useState<"idle" | "running" | "failed" | "unsupported">(
    "idle");
  const canCeremony = useCeremonyAvailable();

  async function enrol(form: HTMLFormElement) {
    setCeremony("running");
    try {
      const credential = await navigator.credentials.create({
        publicKey: creationOptions({
          rpName: text("app.name"), identityId, displayName, identifier,
        }),
      }) as PublicKeyCredential | null;
      if (credential === null) {
        setCeremony("failed");
        return;
      }
      const payload = enrolmentPayload(credential);
      if ("unsupported" in payload) {
        setCeremony("unsupported");
        return;
      }
      // Into the form the action reads, so the write goes through the server where the session
      // cookie is.
      for (const [name, value] of Object.entries(payload)) {
        const field = form.elements.namedItem(name) as HTMLInputElement | null;
        if (field) field.value = String(value);
      }
      setCeremony("idle");
      form.requestSubmit();
    } catch {
      // A cancelled prompt, a timeout and a refused ceremony all land here, and the browser
      // deliberately does not say which -- so neither does this.
      setCeremony("failed");
    }
  }

  // **One definition of "is there a way in that spends nothing".** The recovery-codes block
  // asks the same question one section up, and two copies of it are two answers the day
  // either moves -- the rule this repository applies to a balance and to a retry curve.
  const hasWayIn = hasUsableKey(passkeys);
  return (
    <section className="page-section ds-passkeys" aria-labelledby="passkey-heading">
      <h2 id="passkey-heading">{text("passkey.heading")}</h2>
      <p className="muted">{text("passkey.lead")}</p>

      {hasWayIn ? null : (
        <Banner severity="attention">{text("passkey.none")}</Banner>
      )}

      {passkeys.length > 0 ? (
        <ul className="ds-passkey-list">
          {passkeys.map((passkey) => (
            <li key={passkey.passkey_id} className="ds-passkey" data-state={
              passkeyState(passkey)}>
              <div className="ds-passkey-what">
                <span className="ds-passkey-label">
                  {passkey.label ?? text("passkey.heading")}
                </span>
                {" "}
                {/* **Not a `StatusBadge`, and the reason is the design rather than
                    convenience.** Its vocabulary is closed over four domains -- membership,
                    payment, booking and access -- and a credential is none of them, so there
                    is no word in it for "withdrawn". The nearest, `Cancelled`, is a
                    membership state, and putting a membership word on a passkey is how two
                    screens come to spell one thing two ways. Adding to the vocabulary would
                    mean editing the design source to suit the implementation, which is the
                    one thing this project forbids outright -- so the state is marked text
                    with its own three words, and the gap is recorded instead. */}
                <span className="ds-passkey-state">
                  {text(`passkey.state.${passkeyState(passkey)}` as MessageKey)}
                </span>
              </div>
              <dl className="facts">
                <dt>{text("passkey.created")}</dt>
                <dd className="data" dir="ltr">{utcStamp(passkey.created_at)}</dd>
                <dt>{text("passkey.lastUsed")}</dt>
                <dd className={passkey.last_used_at ? "data" : "muted"} dir={
                  passkey.last_used_at ? "ltr" : undefined}>
                  {passkey.last_used_at
                    ? utcStamp(passkey.last_used_at)
                    : text("passkey.neverUsed")}
                </dd>
                <dt>{text(passkey.backed_up ? "passkey.backedUp" : "passkey.deviceBound")}</dt>
                <dd className="muted">{text("passkey.whyBound")}</dd>
              </dl>
              {usable(passkey) ? (
                <form action={withdrawAction} className="ds-passkey-withdraw">
                  <input type="hidden" name="passkey_id" value={passkey.passkey_id} />
                  <Button
                    type="submit" variant="ghost" size="md" label={text("passkey.withdraw")}
                    state={withdrawing ? "loading" : "default"}
                  />
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {!canCeremony ? (
        <p className="muted">{text("passkey.browserCannot")}</p>
      ) : (
        <form
          action={action}
          className="ds-passkey-form"
          onSubmit={(event) => {
            // The ceremony runs first and submits the form itself once it has a credential.
            const form = event.currentTarget;
            const field = form.elements.namedItem(
              "webauthn_credential_id") as HTMLInputElement | null;
            if (!field?.value) {
              event.preventDefault();
              void enrol(form);
            }
          }}
        >
          <input type="hidden" name="webauthn_credential_id" defaultValue="" />
          <input type="hidden" name="public_key" defaultValue="" />
          <input type="hidden" name="backed_up" defaultValue="false" />
          <Field
            id="passkey-label" name="label" type="text" rarer="optional"
            optionalLabel={text("field.optional")}
            label={text("passkey.label")}
            description={text("passkey.labelHint")}
            autoComplete="off"
          />
          <Button
            type="submit" variant="secondary" size="lg"
            label={ceremony === "running" ? text("passkey.adding") : text("passkey.add")}
            state={ceremony === "running" || pending ? "loading" : "default"}
          />
        </form>
      )}

      {ceremony === "failed" ? (
        <Banner severity="critical">{text("passkey.ceremonyFailed")}</Banner>
      ) : ceremony === "unsupported" ? (
        <Banner severity="critical">{text("passkey.unsupported")}</Banner>
      ) : null}
      {state.message !== null ? (
        <Banner severity="info">{text(state.message)}</Banner>
      ) : null}
      {state.error !== null ? (
        <Banner severity="critical">{text(state.error)}</Banner>
      ) : null}
      {withdrawn.message !== null ? (
        <Banner severity="info">{text(withdrawn.message)}</Banner>
      ) : null}
      {withdrawn.error !== null ? (
        <Banner severity="critical">{text(withdrawn.error)}</Banner>
      ) : null}
      <p className="ds-screen-note">{text("passkey.notYetVerified")}</p>
    </section>
  );
}
