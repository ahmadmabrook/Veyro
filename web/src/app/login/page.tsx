import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { t } from "@/i18n/locale";
import { currentSession } from "@/lib/api";
import { presentation } from "@/lib/preferences";

import { LoginForm } from "./login-form";

/**
 * Sign-in.
 *
 * A server component, so the locale comes from the cookie the layout already read rather than
 * being hard-coded to English in a client bundle -- which is what the first version did, and
 * it meant an Arabic reader got an Arabic document with an English form inside it.
 *
 * It also redirects a caller who already has a session: a sign-in page that re-authenticates
 * somebody already signed in is how a second session gets minted for no reason, and MOD-007
 * counts sessions.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  if (await currentSession()) redirect("/");

  // **Why this browser was signed out, when it was the reader's own doing.** Revoking the
  // device you are reading the account page in ends that session, and arriving at a sign-in
  // form with no explanation reads as the product having failed. The only value acted on is
  // the one this app sets; anything else renders nothing, because this is a query parameter
  // and a stranger can put whatever they like in a link.
  const signedOut = (await searchParams).signed_out === "device";

  return (
    <>
      {signedOut ? <Alert tone="info">{t(locale, "login.deviceRevoked")}</Alert> : null}
      <LoginForm locale={locale} />
    </>
  );
}
