"use client";

import { useActionState } from "react";

import { Alert, Button } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import {
  assuranceMeans,
  currentDeviceId,
  mayIssueRecoveryCodes,
  needsAttention,
  sessionIsLive,
} from "@/lib/account";
import type { AuthEvent, DeviceFact, SessionFact } from "@/lib/account";

import { issueRecoveryCodes, revokeDevice, revokeSession, trustDevice } from "./actions";
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
export function AccountView({
  locale,
  identityId,
  aal,
  factors,
  expiresAt,
  nowIso,
  sessionId,
  sessions,
  devices,
  events,
}: {
  locale: Locale;
  identityId: string;
  aal: number;
  factors: string[];
  expiresAt: string;
  nowIso: string;
  sessionId: string;
  sessions: SessionFact[];
  devices: DeviceFact[];
  events: AuthEvent[];
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
      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("account.thisSession")}</h2>
        <dl className="facts">
          <dt className="muted">{text("account.assurance")}</dt>
          <dd style={{ margin: 0 }}>
            {assurance === "stepped_up"
              ? text("account.steppedUp")
              : assurance === "unreachable"
                ? text("account.unreachableLevel")
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
              {assurance === "stepped_up"
                ? text("account.shortWindow")
                : text("account.longWindow")}
            </div>
          </dd>
        </dl>
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("account.recoveryCodes")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.recoveryLead")}
        </p>
        {!mayIssueRecoveryCodes(aal) ? (
          <Alert tone="info">{text("account.codesNeedStepUp")}</Alert>
        ) : (
          <form action={issueCodes}>
            <input type="hidden" name="identity_id" value={identityId} />
            <Button type="submit" variant="primary">
              {text("account.issueCodes")}
            </Button>
          </form>
        )}
        <Result locale={locale} state={codeState} />
        {codeState.codes.length === 0 ? null : (
          <>
            <Alert tone="warning">{text("account.codesShownOnce")}</Alert>
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

      <section className="panel stack">
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
          <Alert tone="info">{text("account.noOtherSessions")}</Alert>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {others.map((other) => (
              <li key={other.session_id}>
                {text("account.level")}{" "}
                <span className="data">{formatInteger(other.aal, "latn")}</span>
                {" · "}
                <span className="data" dir="ltr">
                  {other.last_seen_at === null
                    ? other.issued_at.slice(0, 10)
                    : other.last_seen_at.slice(0, 16).replace("T", " ")}
                </span>
                <form action={revokeOne} style={{ display: "inline" }}>
                  <input type="hidden" name="session_id" value={other.session_id} />
                  <Button type="submit" style={{ marginInlineStart: "var(--space-3)" }}>
                    {text("account.revoke")}
                  </Button>
                </form>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("account.devices")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.devicesLead")}
        </p>
        <Result locale={locale} state={deviceState} />
        <Result locale={locale} state={trustState} />
        {devices.length === 0 ? (
          <Alert tone="info">{text("account.noDevices")}</Alert>
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
                      <Button type="submit" style={{ marginInlineEnd: "var(--space-2)" }}>
                        {text("account.revoke")}
                      </Button>
                    </form>
                    {device.trusted ? null : (
                      <form action={trustOne} style={{ display: "inline" }}>
                        <input type="hidden" name="device_id" value={device.device_id} />
                        <Button type="submit">{text("account.trust")}</Button>
                      </form>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("account.events")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("account.eventsLead")}
        </p>
        {events.length === 0 ? (
          <Alert tone="info">{text("account.noEvents")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("account.events")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("account.what")}</th>
                <th scope="col" style={head}>{text("account.outcome")}</th>
                <th scope="col" style={head}>{text("account.when")}</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => (
                <tr key={`${event.occurred_at}-${index}`}>
                  <td style={cell}>
                    {event.kind}
                    {event.factor === null ? null : (
                      <div className="muted" style={caption}>{event.factor}</div>
                    )}
                  </td>
                  <td style={cell}>
                    {event.outcome}
                    {event.reason === null ? null : (
                      <div className="muted" style={caption}>{event.reason}</div>
                    )}
                  </td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {event.occurred_at.slice(0, 16).replace("T", " ")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
    return <Alert tone="error">{t(locale, state.error)}</Alert>;
  }
  if (state.message !== null) {
    return <Alert tone="success">{t(locale, state.message)}</Alert>;
  }
  return null;
}

const head: React.CSSProperties = {
  textAlign: "start",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-default)",
  background: "var(--color-surface-sunken)",
  fontSize: "var(--type-label-size)",
  fontWeight: "var(--type-label-weight)",
};

const cell: React.CSSProperties = {
  textAlign: "start",
  verticalAlign: "top",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};

const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };
