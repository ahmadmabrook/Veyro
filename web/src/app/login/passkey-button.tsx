"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { t, type Locale, type MessageKey } from "@/i18n/locale";
import { assertionPayload, requestOptions } from "@/lib/passkey";
import { useCeremonyAvailable } from "@/lib/use-ceremony";

import { beginPasskeySignIn, finishPasskeySignIn } from "./actions";

/**
 * Sign in with a passkey, beside the password form rather than instead of it.
 *
 * **It reads the two fields the form already has rather than owning its own.** The tenant id
 * and the identifier are typed into the form above, so this takes a reference to that form
 * and reads them at press time -- a second pair of inputs would be two places to type one
 * thing, and a value passed as a prop would be the value at render rather than the value now.
 *
 * **The cookie is written by a server action, which is the whole reason the ceremony's result
 * goes back across that boundary.** The session cookie is httpOnly precisely so page
 * JavaScript cannot read or write it; a client that held a bearer token would be the thing
 * that property exists to prevent. So this runs `navigator.credentials.get`, hands the four
 * base64url fields to `finishPasskeySignIn`, and navigates on success.
 *
 * **The action revalidates and this pushes.** The session cookie is written by the action,
 * and a push into a router cache populated before it ran would render the signed-out page
 * with a live session in the jar -- so `finishPasskeySignIn` calls `revalidatePath` and the
 * push then fetches the layout again, carrying the new cookie. A full page load would also
 * work and is what the first version did; the pair is the idiom Next asks for, and the
 * linter says so.
 *
 * **Absent where the browser cannot.** A control that cannot work is worse than its absence,
 * which is this app's standing rule about a button that answers 403 -- and here the reader
 * would have no way to tell a missing passkey from a browser that cannot ask for one.
 */
export function PasskeySignIn({
  locale,
  formId,
}: {
  locale: Locale;
  /** The sign-in form, read for the tenant and the identifier at press time. */
  formId: string;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [running, setRunning] = useState(false);
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const router = useRouter();
  const canCeremony = useCeremonyAvailable();
  if (!canCeremony) return null;

  async function run() {
    setProblem(null);
    const form = document.getElementById(formId) as HTMLFormElement | null;
    const tenantId = fieldValue(form, "tenant_id");
    const identifier = fieldValue(form, "identifier");
    if (!tenantId || !identifier) {
      // **Which field, because two are needed and only one is obvious.** A passkey is
      // discoverable from the relying party, so a reader could reasonably expect to press
      // this with nothing typed -- the tenant header is what this build needs beside it, and
      // the form's own note already says why that field exists at all.
      setProblem("passkey.needIdentifier");
      return;
    }
    setRunning(true);
    try {
      const issued = await beginPasskeySignIn(tenantId, identifier);
      if (issued === null) {
        setProblem("passkey.signInFailed");
        return;
      }
      const credential = (await navigator.credentials.get({
        publicKey: requestOptions({ challenge: issued.challenge }),
      })) as PublicKeyCredential | null;
      if (credential === null) {
        setProblem("passkey.ceremonyFailed");
        return;
      }
      const refused = await finishPasskeySignIn(tenantId, {
        identifier,
        challenge: issued.challenge,
        ...assertionPayload(credential),
      });
      if (refused !== null) {
        setProblem(refused);
        return;
      }
      router.push("/");
    } catch {
      // A cancelled prompt, a timeout and a refused ceremony all land here, and the browser
      // deliberately does not say which -- so neither does this.
      setProblem("passkey.ceremonyFailed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="ds-passkey-signin">
      <Button
        type="button"
        variant="secondary"
        size="lg"
        fullWidth
        label={running ? text("passkey.signingIn") : text("passkey.signIn")}
        state={running ? "loading" : "default"}
        onClick={() => void run()}
      />
      {problem !== null ? <Banner severity="critical">{text(problem)}</Banner> : null}
    </div>
  );
}

function fieldValue(form: HTMLFormElement | null, name: string): string {
  if (form === null) return "";
  const field = form.elements.namedItem(name);
  return field instanceof HTMLInputElement ? field.value.trim() : "";
}
