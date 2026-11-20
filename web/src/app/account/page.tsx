import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { t, type Locale, type MessageKey } from "@/i18n/locale";
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
  return (
    <Shell locale={locale}>
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

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "account.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "account.lead")}
      </p>
      {children}
    </div>
  );
}
