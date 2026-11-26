import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import type { AuthEvent, DeviceFact, SessionFact } from "@/lib/account";
import { listAuthEvents, listDevices, listSessions } from "@/lib/account-reads";
import type { PasskeyFact } from "@/lib/passkey";
import { listPasskeys, readOwnIdentity, type OwnIdentity } from "@/lib/passkey-reads";
import { currentSession, failureMessage } from "@/lib/api";
import { numerals } from "@/lib/display";
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
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  const identityId = String(session.identity_id);
  let sessions: SessionFact[] = [];
  let devices: DeviceFact[] = [];
  let events: AuthEvent[] = [];
  let passkeys: PasskeyFact[] = [];
  let me: OwnIdentity | null = null;
  try {
    [sessions, devices, events, passkeys, me] = await Promise.all([
      listSessions(identityId),
      listDevices(identityId),
      listAuthEvents(),
      listPasskeys(identityId),
      readOwnIdentity(identityId),
    ]);
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">
          {text(failureMessage(error))}
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
          {fill(locale, "account.sessionsCounted", { count: live.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "account.assuranceLevel",
            { level: String(Number(session.aal ?? 1)) })}
        </>
      }
    >
      {/* **How many devices are remembered, at the size of a figure.** It was a 14px count
          beside two others, and it is the one of the three a reader acts on: a device is
          remembered so a sign-in from it is not challenged, and revoking one is permanent.
          The live-session count stays in the line above, because the only noun keys this
          catalogue has for a session mean *other* sessions -- which excludes the one being
          read -- and a figure labelled by the wrong set is worse than a small one. */}
      <MetricRow label={text("account.devices")}>
        <MetricCell
          label={text("account.devices")}
          value={formatInteger(
            devices.filter((one) => one.revoked_at === null).length, numbering)}
        />
      </MetricRow>

      <AccountView
        locale={locale}
        numbering={numbering}
        identityId={identityId}
        aal={Number(session.aal ?? 1)}
        factors={(session.factors as string[] | undefined) ?? []}
        expiresAt={String(session.expires_at ?? "")}
        nowIso={new Date().toISOString()}
        sessionId={String(session.session_id ?? "")}
        sessions={sessions}
        devices={devices}
        events={events}
        passkeys={passkeys}
        displayName={me.display_name}
        identifier={me.email ?? me.phone ?? me.display_name}
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
