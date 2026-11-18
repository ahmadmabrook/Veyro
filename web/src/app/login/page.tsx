import { redirect } from "next/navigation";

import { LocaleSwitch } from "@/components/locale-switch";
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
export default async function LoginPage() {
  const { locale } = await presentation();
  if (await currentSession()) redirect("/");

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          padding: "var(--space-4) var(--space-4) 0",
        }}
      >
        <LocaleSwitch locale={locale} />
      </div>
      <LoginForm locale={locale} />
    </>
  );
}
