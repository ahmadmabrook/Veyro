import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import type { AuthEvent, DeviceFact, SessionFact } from "@/lib/account";
import { listAuthEvents, listDevices, listSessions } from "@/lib/account-reads";
import { ApiError, currentSession } from "@/lib/api";
import { presentation } from "@/lib/preferences";

/**
 * MOD-007's own surface: this session, its devices, the other sessions, and the log.
 *
 * **There is no permission on this page**, which is the server's design rather than an
 * omission. Every route it reads is scoped by `owned(session, identity_id)` and refuses
 * anything that is not the caller's own with a 404 -- so there is nothing to authorize when
 * the only readable subject is yourself. MOD-007's review found the opposite shipped, where a
 * tenant UUID was enough to list somebody's sessions or issue their recovery codes, and the
 * rule it left behind is that a tenant header is not an authentication.
 *
 * **It closes a gap the web README recorded against itself.** A step-up spends a recovery
 * code, TOTP and passkeys are unverifiable here, and there was no screen for reissuing a
 * batch -- so a reader who stepped up five times was out of second factors with no path back.
 * The loop closes now: step up with a code, then mint a new batch, which needs exactly the
 * assurance the step-up just produced.
 */
export default async function AccountPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  const identityId = String(session.identity_id);
  let sessions: SessionFact[] = [];
  let devices: DeviceFact[] = [];
  let events: AuthEvent[] = [];
  try {
    [sessions, devices, events] = await Promise.all([
      listSessions(identityId),
      listDevices(identityId),
      listAuthEvents(),
    ]);
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Banner>
      </Shell>
    );
  }

  const { AccountView } = await import("./account-view");
  const live = sessions.filter((one) => one.revoked_at === null);
  return (
    <Shell
      locale={locale}
      figures={
        <>
          {fill(locale, "account.sessionsCounted", { count: live.length })}
          {" \u00b7 "}
          {fill(locale, "account.devicesCounted",
            { count: devices.filter((one) => one.revoked_at === null).length })}
          {" \u00b7 "}
          {fill(locale, "account.assuranceLevel",
            { level: String(Number(session.aal ?? 1)) })}
        </>
      }
    >
      <AccountView
        locale={locale}
        identityId={identityId}
        aal={Number(session.aal ?? 1)}
        factors={(session.factors as string[] | undefined) ?? []}
        expiresAt={String(session.expires_at ?? "")}
        nowIso={new Date().toISOString()}
        sessionId={String(session.session_id ?? "")}
        sessions={sessions}
        devices={devices}
        events={events}
      />
    </Shell>
  );
}

/**
 * **The lead moved to the foot, which is the rule every other screen in this app follows.**
 * The design's page header is a title and a line of figures, never a paragraph: an
 * explanation of what the screen is pushes the facts a reader came for below the fold, and
 * they only need it once. What is kept is the half that is a disclosure -- these routes
 * refuse any subject that is not the caller's own, which is why none of them asks for a
 * permission and why the rail entry is unconditional.
 */
function Shell({
  locale,
  children,
  figures,
}: {
  locale: Locale;
  children: React.ReactNode;
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader
        title={t(locale, "account.title")}
        {...(figures ? { figures } : {})}
      />
      {children}
      <p className="ds-screen-note">{t(locale, "account.lead")}</p>
    </div>
  );
}
