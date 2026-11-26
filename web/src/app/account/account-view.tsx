"use client";

import { useActionState } from "react";

import { Button } from "@/components/ds/button";
import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import {
  fill, formatInteger, t, type Locale, type MessageKey, type Numbering,
} from "@/i18n/locale";
import {
  assuranceMeans,
  currentDeviceId,
  mayIssueRecoveryCodes,
  needsAttention,
  sessionIsLive,
} from "@/lib/account";
import { hasUsableKey, type PasskeyFact } from "@/lib/passkey";
import type { AuthEvent, DeviceFact, SessionFact } from "@/lib/account";

import { signOut } from "@/app/actions";
import { issueRecoveryCodes, revokeDevice, revokeSession, trustDevice } from "./actions";
import { PasskeySection } from "./passkey-section";
import { IDLE, type AccountState } from "./state";

/**
 * The account surface: this session, the devices it came from, the other sessions open on
 * this account, and what the authentication log says.
 *
 * **It is a client component because it is the first page in this app with four forms whose
 * results have to be shown in place.** Everything else here renders on the server and stays
 * there; `useActionState` is what lets a revoke say "revoked" without a navigation, and lets
 * a fresh batch of recovery codes be rendered **once** without ever reaching a URL, a cookie
 * or storage.
 *
 * **The codes are the reason this is not a redirect.** MOD-007 stores only a hash, so a batch
 * exists in one HTTP response and nowhere else. A redirect would lose them, and carrying them
 * in a query string or a cookie to survive one would be putting permanent credentials
 * somewhere a browser keeps things.
 */
/**
 * The word for an authentication event, in the reader's language.
 *
 * **This is the member's own security log**, and it rendered the stored kind -- `step_up`,
 * `recovery_code`, `codes_issued` -- to the person whose account it is. A vocabulary the
 * backend stores is never a label. The kinds are dotted (`step_up.succeeded`), so the leading
 * segment is what carries the meaning and the outcome has its own column; an unmapped kind
 * falls through to its stored form rather than to a blank, because the log is evidence and a
 * row nobody can read is worse than an ugly one.
 */
function authEventWord(kind: string, locale: "en" | "ar"): string {
  const known: Record<string, MessageKey> = {
    authenticated: "authEvent.signIn",
    authentication_failed: "authEvent.signInFailed",
    step_up: "authEvent.stepUp",
    recovery_code: "authEvent.recoveryCode",
    recovery_codes_issued: "authEvent.codesIssued",
    codes_issued: "authEvent.codesIssued",
    password_changed: "authEvent.passwordChanged",
    device_confirmed: "authEvent.deviceConfirmed",
    device_revoked: "authEvent.deviceRevoked",
    session_revoked: "authEvent.sessionRevoked",
    passkey_enrolled: "authEvent.passkeyEnrolled",
    passkey_revoked: "authEvent.passkeyRevoked",
  };
  const head = kind.split(".")[0] ?? kind;
  const key = known[kind] ?? known[head];
  return key === undefined ? kind : t(locale, key);
}

export function AccountView({
  locale,
  numbering,
  identityId,
  aal,
  factors,
  expiresAt,
  nowIso,
  sessionId,
  sessions,
  devices,
  events,
  passkeys,
  displayName,
  identifier,
}: {
  locale: Locale;
  /** The tenant's numeral system, so a count here matches every other figure. */
  numbering: Numbering;
  identityId: string;
  aal: number;
  factors: string[];
  expiresAt: string;
  nowIso: string;
  sessionId: string;
  sessions: SessionFact[];
  devices: DeviceFact[];
  events: AuthEvent[];
  passkeys: PasskeyFact[];
  /** For the ceremony: an authenticator shows these when somebody picks a credential later. */
  displayName: string;
  identifier: string;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [codeState, issueCodes] = useActionState(issueRecoveryCodes, IDLE);
  const [sessionState, revokeOne] = useActionState(revokeSession, IDLE);
  const [deviceState, revokeOneDevice] = useActionState(revokeDevice, IDLE);
  const [trustState, trustOne] = useActionState(trustDevice, IDLE);

  // The server already filtered to live sessions and bounded the page; this is the belt
  // that keeps a stale row out if the clock moved between the read and the render.
  const live = sessions.filter((s) => sessionIsLive(s, nowIso));
  const others = live.filter((s) => s.session_id !== sessionId);
  const assurance = assuranceMeans(aal);
  // The one device whose revoke button is irreversible from this browser's point of view.
  const thisDevice = currentDeviceId(sessions, sessionId);

  return (
    <>
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("account.thisSession")}</h2>
        <dl className="facts">
          <dt className="muted">{text("account.assurance")}</dt>
          <dd style={{ margin: 0 }}>
            {assurance === "stepped_up"
              ? text("account.steppedUp")
              : assurance === "hardware"
                ? text("account.hardwareLevel")
                : text("account.passwordOnly")}
            <div className="muted" style={caption}>
              {text("account.provedWith")}{" "}
              <span className="data" dir="ltr">{factors.join(", ")}</span>
            </div>
          </dd>
          <dt className="muted">{text("account.expires")}</dt>
          <dd style={{ margin: 0 }}>
            <span className="data" dir="ltr">{expiresAt.slice(0, 16).replace("T", " ")}</span>
            {" UTC"}
            <div className="muted" style={caption}>
              {/* **Three windows, not two.** `SESSION_LIFETIME` gives level 3 fifteen
                  minutes -- the shortest of the three, because the strongest credential
                  opens the narrowest window -- and this branch read the password one for it,
                  so a passkey session was told it had a fortnight. */}
              {assurance === "stepped_up"
                ? text("account.shortWindow")
                : assurance === "hardware"
                  ? text("account.shortestWindow")
                  : text("account.longWindow")}
            </div>
          </dd>
        </dl>
        {/* **Sign out lives here, which is where §21 puts it.** The global chrome is a scope
            switcher, a command palette, tasks, alerts and *account*, and ending a session is
            account chrome rather than a page of its own. It sat on the overview while that
            page was a session diagnostic; when the Command Center replaced it the control
            went with it, and for a few minutes this app had no way to sign out at all.
            Found by trying to use it. */}
        <form action={signOut}>
          <Button type="submit" variant="secondary" label={text("nav.signOut")} />
        </form>
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("account.recoveryCodes")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.recoveryLead")}
        </p>
        {/* **Whether these codes are the only way back, which is now a question with two
            answers.** The lead used to say a recovery code is the only second factor this
            build can verify -- true for five modules and false since WebAuthn verification
            landed, on the same page that now enrols a passkey. What matters to the reader is
            not which factors exist but whether *they* have one: a member with a passkey
            cannot be locked out by spending ten codes, and a member without one can, which
            is the dead end MOD-007 recorded against itself. `hasUsableKey` is the question,
            asked in one place so this sentence and the section's own banner cannot
            disagree. */}
        <p className="muted" style={{ margin: 0 }}>
          {text(hasUsableKey(passkeys)
            ? "account.recoveryAndPasskey"
            : "account.recoveryIsTheOnlyWayBack")}
        </p>
        {!mayIssueRecoveryCodes(aal) ? (
          <Banner severity="info">{text("account.codesNeedStepUp")}</Banner>
        ) : (
          <form action={issueCodes}>
            <input type="hidden" name="identity_id" value={identityId} />
            <Button type="submit" variant="primary" label={text("account.issueCodes")} />
          </form>
        )}
        <Result locale={locale} state={codeState} />
        {codeState.codes.length === 0 ? null : (
          <>
            <Banner severity="attention">{text("account.codesShownOnce")}</Banner>
            <ul
              className="data"
              dir="ltr"
              style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}
            >
              {codeState.codes.map((code) => (
                <li key={code}>{code}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      {/* **Above the sessions, because it is the way back.** A step-up spends a recovery
          code and reissuing needs a stepped-up session, so a member who spends all ten has
          no way in from this surface -- which is the dead end MOD-007 recorded against itself.
          A passkey is the way back that spends nothing, so it is offered before the list of
          places you are signed in. */}
      <PasskeySection
        locale={locale}
        identityId={identityId}
        displayName={displayName}
        identifier={identifier}
        passkeys={passkeys}
      />

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("account.otherSessions")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.otherSessionsLead")}
        </p>
        <Result locale={locale} state={sessionState} />
        <dl className="facts">
          <dt className="muted">{text("account.openElsewhere")}</dt>
          <dd style={{ margin: 0 }}>
            <span className="data">{formatInteger(others.length, "latn")}</span>
            {others.length >= 20 ? ` ${text("account.atLeast")}` : ""}
          </dd>
        </dl>
        {others.length === 0 ? (
          <Banner severity="info">{text("account.noOtherSessions")}</Banner>
        ) : (
          // **A grid, because a bulleted list of nineteen "level 2 · 17:11" rows is not a
          // thing anybody can act on.** Revoking a session is a destructive act and the
          // reader has to be able to tell which one they are ending: the device it came
          // from is what distinguishes them, and the list carried it all along while the
          // rendering dropped it. Found by looking at the page.
          <ul className="ds-session-list">
            {others.map((other) => (
              <li key={other.session_id} className="ds-session">
                <span className="ds-session-where">
                  {other.device_id === null
                    ? text("account.noDevice")
                    : (devices.find((one) => one.device_id === other.device_id)?.label
                      ?? text("account.unknownDevice"))}
                  <span className="ds-session-when data" dir="ltr">
                    {other.last_seen_at === null
                      ? `${text("account.issued")} ${other.issued_at.slice(0, 10)}`
                      : `${text("account.lastSeen")} `
                        + other.last_seen_at.slice(0, 16).replace("T", " ")}
                  </span>
                </span>
                <span className="ds-session-level">
                  {text("account.level")}{" "}
                  <span className="data">{formatInteger(other.aal, "latn")}</span>
                </span>
                <form action={revokeOne}>
                  <input type="hidden" name="session_id" value={other.session_id} />
                  <Button type="submit" label={text("account.revoke")} />
                </form>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("account.devices")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.devicesLead")}
        </p>
        <Result locale={locale} state={deviceState} />
        <Result locale={locale} state={trustState} />
        {devices.length === 0 ? (
          <Banner severity="info">{text("account.noDevices")}</Banner>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {devices.map((device) => (
              <li key={device.device_id}>
                <span className="data" dir="ltr">{device.label}</span>
                {device.device_id === thisDevice ? (
                  <span className="muted"> · {text("account.thisBrowser")}</span>
                ) : null}
                {device.revoked_at !== null ? (
                  <span className="muted"> · {text("account.deviceRevoked")}</span>
                ) : null}
                <div className="muted" style={caption}>
                  {device.confirmed
                    ? text("account.confirmed")
                    : text("account.unconfirmed")}
                  {device.trusted ? ` · ${text("account.trustedDevice")}` : ""}
                  {" · "}
                  <span className="data" dir="ltr">
                    {device.last_seen_at.slice(0, 10)}
                  </span>
                </div>
                {needsAttention(device) ? (
                  <div className="muted" style={caption}>
                    {text("account.unconfirmedMeans")}
                  </div>
                ) : null}
                {device.device_id === thisDevice && device.revoked_at === null ? (
                  <div className="muted" style={caption}>
                    {text("account.revokingThisSignsYouOut")}
                  </div>
                ) : null}
                {device.revoked_at !== null ? null : (
                  <>
                    <form action={revokeOneDevice} style={{ display: "inline" }}>
                      <input type="hidden" name="device_id" value={device.device_id} />
                      <Button
                        type="submit"
                        // **Destructive**, and the source says it is never adjacent to a
                        // primary: there is no primary in this row, and Trust beside it is
                        // the secondary default.
                        variant="destructive"
                        label={text("account.revoke")}
                        style={{ marginInlineEnd: "var(--space-2)" }}
                      />
                    </form>
                    {device.trusted ? null : (
                      <form action={trustOne} style={{ display: "inline" }}>
                        <input type="hidden" name="device_id" value={device.device_id} />
                        <Button type="submit" label={text("account.trust")} />
                      </form>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="page-section">
        <h2 id="events-heading" style={{ margin: 0 }}>{text("account.events")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.eventsLead")}
        </p>
        {events.length === 0 ? (
          <Banner severity="info">{text("account.noEvents")}</Banner>
        ) : (
          <DataGrid
            caption={text("account.events")}
            countLabel={fill(locale, "grid.count.signIns", { count: events.length }, numbering)}
            labelledBy="events-heading"
            rows={events}
            rowKey={(event) => `${event.occurred_at}-${event.kind}-${event.outcome}`}
            // A refused sign-in is the row somebody checking their account after a
            // suspicious email is looking for.
            rowSeverity={(event) => (event.outcome === "failed" ? "attention" : null)}
            columns={[
              {
                header: text("account.what"),
                kind: "text",
                priority: 1,
                render: (event) => (
                  <>
                    {authEventWord(event.kind, locale)}
                    {event.factor === null ? null : (
                      <div className="muted" style={caption}>{event.factor}</div>
                    )}
                  </>
                ),
              },
              {
                header: text("account.outcome"),
                kind: "status",
                priority: 1,
                render: (event) => (
                  <>
                    {event.outcome}
                    {event.reason === null ? null : (
                      <div className="muted" style={caption}>{event.reason}</div>
                    )}
                  </>
                ),
              },
              {
                header: text("account.when"),
                kind: "date",
                priority: 2,
                render: (event) => (
                  <span className="data" dir="ltr">
                    {event.occurred_at.slice(0, 16).replace("T", " ")}
                  </span>
                ),
              },
            ]}
          />
        )}
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          {text("account.recentOnly")}
        </p>
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          {text("account.refusedTokenNote")}
        </p>
      </section>
    </>
  );
}

function Result({ locale, state }: { locale: Locale; state: AccountState }) {
  if (state.error !== null) {
    return <Banner severity="critical">{t(locale, state.error)}</Banner>;
  }
  if (state.message !== null) {
    return <Banner severity="neutral">{t(locale, state.message)}</Banner>;
  }
  return null;
}



const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };
