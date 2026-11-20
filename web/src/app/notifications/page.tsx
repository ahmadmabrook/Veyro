import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { money } from "@/lib/membership";
import {
  listChannels,
  listDigests,
  listNotifications,
  listSuppressions,
  listTemplates,
  reasonKey,
  releasable,
  suppressionIsLive,
  usableChannels,
  waitingOn,
  type ChannelPolicy,
  type Digest,
  type NotificationRow,
  type NotificationTemplate,
  type Suppression,
} from "@/lib/notifications";
import { presentation } from "@/lib/preferences";

/**
 * MOD-013's board: what this tenant can say, what it decided to say, and to whom it may not.
 *
 * **Nothing sends, and that is the first thing on the page.** There is no provider, no SMTP
 * and no outbound HTTP in this build: `dispatch_notification` claims a delivery for whatever
 * does the sending and `record_outcome` is written by it. So every notification here sits at
 * `requested` or `deferred` for ever, and a board rendering that as a queue making progress
 * would be the fabricated-evidence shape this codebase has been bitten by six times. The
 * count of waiting messages is not a backlog to clear; it is the absence of a dispatcher.
 *
 * **No message text and no address appear anywhere on this page.** The list route carries no
 * rendered body on purpose -- one that did would be a read path to everything a tenant has
 * ever said to anybody, under one permission -- and the tables carry a SHA-256 of
 * `channel:address` rather than the address. The board asks for neither.
 *
 * **A suppression's reason decides whether it can ever be lifted**, which is why the page
 * says which kind each row is rather than offering a release control that would be refused. A
 * bounce or a complaint is the channel's judgement about deliverability, and a tenant that
 * could clear those would be choosing to keep sending to an address that rejected them.
 */
export default async function NotificationsPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayTemplates, mayPolicies, mayNotifications, maySuppressions] = await Promise.all([
    gate("notifications.template.read"),
    gate("notifications.policy.read"),
    gate("notifications.notification.read"),
    gate("notifications.suppression.read"),
  ]);

  if (
    !mayTemplates.allowed && !mayPolicies.allowed && !mayNotifications.allowed &&
    !maySuppressions.allowed
  ) {
    return (
      <Shell locale={locale}>
        <Alert tone="info">
          {mayNotifications.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Alert>
      </Shell>
    );
  }

  let templates: NotificationTemplate[] = [];
  let channels: ChannelPolicy[] = [];
  let rows: NotificationRow[] = [];
  let suppressions: Suppression[] = [];
  let digests: Digest[] = [];
  let failed = false;
  try {
    [templates, channels, rows, suppressions, digests] = await Promise.all([
      mayTemplates.allowed ? listTemplates() : Promise.resolve([]),
      mayPolicies.allowed ? listChannels() : Promise.resolve([]),
      mayNotifications.allowed ? listNotifications() : Promise.resolve([]),
      maySuppressions.allowed ? listSuppressions() : Promise.resolve([]),
      mayNotifications.allowed ? listDigests() : Promise.resolve([]),
    ]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  const waiting = rows.filter((r) => waitingOn(r) === "no_dispatcher");
  const liveSuppressions = suppressions.filter(suppressionIsLive);

  return (
    <Shell locale={locale}>
      {failed ? <Alert tone="error">{text("error.unexpected")}</Alert> : null}

      {mayNotifications.allowed ? (
        <Alert tone="warning">{text("notify.nothingSends")}</Alert>
      ) : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("notify.authored")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.authoredLead")}
        </p>
        {!mayNotifications.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : rows.length === 0 ? (
          <Alert tone="info">{text("notify.noneAuthored")}</Alert>
        ) : (
          <>
            <dl className="facts">
              <dt className="muted">{text("notify.waitingCount")}</dt>
              <dd style={{ margin: 0 }}>
                <span className="data">{formatInteger(waiting.length, "latn")}</span>{" "}
                {text("notify.of")}{" "}
                <span className="data">{formatInteger(rows.length, "latn")}</span>
              </dd>
            </dl>
            <table
              tabIndex={0}
              style={{ width: "100%", borderCollapse: "collapse" }}
              aria-label={text("notify.authored")}
            >
              <thead>
                <tr>
                  <th scope="col" style={head}>{text("notify.message")}</th>
                  <th scope="col" style={head}>{text("notify.category")}</th>
                  <th scope="col" style={head}>{text("notify.status")}</th>
                  <th scope="col" style={head}>{text("notify.decidedBecause")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.notification_id}>
                    <td style={cell}>
                      <span className="data" dir="ltr">{row.template_key}</span>
                      <div className="muted" style={caption}>
                        {row.channel}
                        {" · "}
                        {row.locale}
                        {" · v"}
                        <span className="data">
                          {formatInteger(row.template_version, "latn")}
                        </span>
                      </div>
                    </td>
                    <td style={cell}>{row.category}</td>
                    <td style={cell}>
                      {row.status}
                      {waitingOn(row) === "no_dispatcher" ? (
                        <div className="muted" style={caption}>
                          {text("notify.noDispatcher")}
                        </div>
                      ) : null}
                    </td>
                    <td style={cell}>
                      {row.decision_reason === null ? (
                        <span className="muted">{text("notify.noReason")}</span>
                      ) : reasonKey(row.decision_reason) !== null ? (
                        text(reasonKey(row.decision_reason)!)
                      ) : (
                        // A reason this build does not know a sentence for. Raw and true
                        // beats a friendly lie about a decision somebody needs to see.
                        <span className="data" dir="ltr">{row.decision_reason}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("notify.noBodyHere")}
            </p>
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("notify.suppressions")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.suppressionsLead")}
        </p>
        {!maySuppressions.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : suppressions.length === 0 ? (
          <Alert tone="info">{text("notify.noSuppressions")}</Alert>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {[...liveSuppressions, ...suppressions.filter((s) => !suppressionIsLive(s))].map(
              (suppression) => (
                <li key={suppression.suppression_id}>
                  {suppressionIsLive(suppression) ? (
                    <strong>{text("notify.blocking")}</strong>
                  ) : (
                    <span className="muted">{text("notify.lifted")}</span>
                  )}
                  {" — "}
                  {suppression.reason}
                  {" · "}
                  {suppression.channel}
                  <div className="muted" style={caption}>
                    {releasable(suppression)
                      ? text("notify.canBeLifted")
                      : text("notify.cannotBeLifted")}
                    {" · "}
                    {/* The digest, truncated: it identifies the row and is not an address. */}
                    <span className="data" dir="ltr">
                      {suppression.address_digest.slice(0, 12)}…
                    </span>
                  </div>
                </li>
              ),
            )}
          </ul>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("notify.channels")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.channelsLead")}
        </p>
        {!mayPolicies.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : channels.length === 0 ? (
          <Alert tone="info">{text("notify.noChannels")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("notify.channels")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("notify.channel")}</th>
                <th scope="col" style={head}>{text("notify.enabled")}</th>
                <th scope="col" style={head}>{text("notify.fallback")}</th>
                <th scope="col" style={head}>{text("notify.cost")}</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((policy) => (
                <tr key={policy.policy_id}>
                  <td style={cell}>{policy.channel}</td>
                  <td style={cell}>
                    {policy.enabled ? text("notify.yes") : text("notify.no")}
                  </td>
                  <td style={cell}>
                    {policy.fallback_channel ?? (
                      <span className="muted">{text("notify.noFallback")}</span>
                    )}
                  </td>
                  <td style={cell}>
                    {policy.cost_per_message_minor === null || policy.currency === null ? (
                      <span className="muted">—</span>
                    ) : (
                      <span className="data" dir="ltr">
                        {money(policy.cost_per_message_minor, policy.currency)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {mayPolicies.allowed && usableChannels(channels).length === 0 &&
          channels.length > 0 ? (
          <Alert tone="warning">{text("notify.everyChannelDisabled")}</Alert>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("notify.templates")}</h2>
        {!mayTemplates.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : templates.length === 0 ? (
          <Alert tone="info">{text("notify.noTemplates")}</Alert>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("notify.templates")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("notify.template")}</th>
                <th scope="col" style={head}>{text("notify.category")}</th>
                <th scope="col" style={head}>{text("notify.status")}</th>
                <th scope="col" style={head}>{text("notify.variables")}</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((template) => (
                <tr key={template.template_id}>
                  <td style={cell}>
                    <span className="data" dir="ltr">{template.template_key}</span>
                    <div className="muted" style={caption}>
                      {template.channel}
                      {" · "}
                      {template.locale}
                      {" · v"}
                      <span className="data">
                        {formatInteger(template.version, "latn")}
                      </span>
                    </div>
                  </td>
                  <td style={cell}>
                    {template.category}
                    {template.category === "marketing" ||
                    template.category === "coaching" ? (
                      <div className="muted" style={caption}>
                        {text("notify.canBeMuted")}
                      </div>
                    ) : (
                      <div className="muted" style={caption}>
                        {text("notify.cannotBeMuted")}
                      </div>
                    )}
                  </td>
                  <td style={cell}>{template.status}</td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {template.variables.join(", ") || "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {mayTemplates.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("notify.categoryDecides")}
          </p>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("notify.digests")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.digestsLead")}
        </p>
        {!mayNotifications.allowed ? (
          <Alert tone="info">{text("gate.denied")}</Alert>
        ) : digests.length === 0 ? (
          <Alert tone="info">{text("notify.noDigests")}</Alert>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {digests.map((digest) => (
              <li key={digest.digest_id}>
                {digest.category}
                {" · "}
                {digest.channel}
                {" · "}
                <span className="data">
                  {formatInteger(digest.notification_count, "latn")}
                </span>{" "}
                {text("notify.held")}
                {" · "}
                {digest.state}
              </li>
            ))}
          </ul>
        )}
      </section>
    </Shell>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "notify.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "notify.lead")}
      </p>
      {children}
    </div>
  );
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
