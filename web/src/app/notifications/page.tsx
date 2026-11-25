import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage } from "@/lib/api";
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
import { numerals } from "@/lib/display";
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
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  // One round trip rather than several: `/authz/checks` asks the same question about
  // every action at once, with the same scope resolution and the same assurance weighing.
  // The semantics are identical -- it is not a permission list, which would be MOD-014's
  // "a grant is not a session" finding.
  const [mayTemplates, mayPolicies, mayNotifications, maySuppressions] = await gateAll([
    "notifications.template.read",
    "notifications.policy.read",
    "notifications.notification.read",
    "notifications.suppression.read",
  ] as const);

  if (
    !mayTemplates.allowed && !mayPolicies.allowed && !mayNotifications.allowed &&
    !maySuppressions.allowed
  ) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(mayNotifications))}
        </Banner>
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
    <Shell
      locale={locale}
      figures={
        <>
          {fill(locale, "notify.authoredCounted", { count: rows.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "notify.waitingCounted", { count: waiting.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "notify.suppressedCounted", { count: liveSuppressions.length }, numbering)}
        </>
      }
    >
      {failed ? <Banner severity="critical">{text("error.unexpected")}</Banner> : null}

      {mayNotifications.allowed ? (
        <Banner severity="attention">{text("notify.nothingSends")}</Banner>
      ) : null}

      <section className="page-section">
        <h2 id="authored-heading" style={{ margin: 0 }}>{text("notify.authored")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.authoredLead")}
        </p>
        {!mayNotifications.allowed ? (
          <Banner severity="info">{text(gateMessage(mayNotifications))}</Banner>
        ) : rows.length === 0 ? (
          <Banner severity="info">{text("notify.noneAuthored")}</Banner>
        ) : (
          <>
            <dl className="facts">
              <dt className="muted">{text("notify.waitingCount")}</dt>
              <dd style={{ margin: 0 }}>
                <span className="data">{formatInteger(waiting.length, numbering)}</span>{" "}
                {text("notify.of")}{" "}
                <span className="data">{formatInteger(rows.length, numbering)}</span>
              </dd>
            </dl>
            <DataGrid
              caption={text("notify.authored")}
              labelledBy="authored-heading"
              rows={rows}
              rowKey={(row) => row.notification_id}
              // A message nothing will ever send is the standing fact of this board, not a
              // fault of its own, so no row is marked for it. A suppressed one is a decision.
              rowSeverity={(row) => (row.status === "suppressed" ? "attention" : null)}
              columns={[
                {
                  header: text("notify.message"),
                  kind: "text",
                  priority: 1,
                  render: (row) => (
                    <>
                      <span className="data" dir="ltr">{row.template_key}</span>
                      <div className="muted" style={caption}>
                        {row.channel}
                        {" · "}
                        {row.locale}
                        {" · v"}
                        <span className="data">
                          {/* A template version is cited, not counted: Latin. ADR-0015. */}
                          {formatInteger(row.template_version, "latn")}
                        </span>
                      </div>
                    </>
                  ),
                },
                {
                  header: text("notify.status"),
                  kind: "status",
                  priority: 1,
                  render: (row) => (
                    <>
                      {row.status}
                      {waitingOn(row) === "no_dispatcher" ? (
                        <div className="muted" style={caption}>
                          {text("notify.noDispatcher")}
                        </div>
                      ) : null}
                    </>
                  ),
                },
                {
                  header: text("notify.decidedBecause"),
                  kind: "text",
                  // Priority 1: the reason is the most explanatory field on the board, and a
                  // status without it is a decision nobody can act on.
                  priority: 1,
                  render: (row) =>
                    row.decision_reason === null ? (
                      <span className="muted">{text("notify.noReason")}</span>
                    ) : reasonKey(row.decision_reason) !== null ? (
                      text(reasonKey(row.decision_reason)!)
                    ) : (
                      // A reason this build does not know a sentence for. Raw and true beats
                      // a friendly lie about a decision somebody needs to see.
                      <span className="data" dir="ltr">{row.decision_reason}</span>
                    ),
                },
                {
                  header: text("notify.category"),
                  kind: "text",
                  priority: 3,
                  render: (row) => row.category,
                },
              ]}
            />
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("notify.noBodyHere")}
            </p>
          </>
        )}
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("notify.suppressions")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.suppressionsLead")}
        </p>
        {!maySuppressions.allowed ? (
          <Banner severity="info">{text(gateMessage(maySuppressions))}</Banner>
        ) : suppressions.length === 0 ? (
          <Banner severity="info">{text("notify.noSuppressions")}</Banner>
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

      <section className="page-section">
        <h2 id="channels-heading" style={{ margin: 0 }}>{text("notify.channels")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.channelsLead")}
        </p>
        {!mayPolicies.allowed ? (
          <Banner severity="info">{text(gateMessage(mayPolicies))}</Banner>
        ) : channels.length === 0 ? (
          <Banner severity="info">{text("notify.noChannels")}</Banner>
        ) : (
          <DataGrid
            caption={text("notify.channels")}
            labelledBy="channels-heading"
            rows={channels}
            rowKey={(policy) => policy.policy_id}
            rowSeverity={(policy) => (policy.enabled ? null : "attention")}
            columns={[
              {
                header: text("notify.channel"),
                kind: "text",
                priority: 1,
                render: (policy) => policy.channel,
              },
              {
                header: text("notify.enabled"),
                kind: "status",
                priority: 1,
                render: (policy) => (policy.enabled ? text("notify.yes") : text("notify.no")),
              },
              {
                header: text("notify.fallback"),
                kind: "text",
                priority: 2,
                render: (policy) =>
                  policy.fallback_channel ?? (
                    <span className="muted">{text("notify.noFallback")}</span>
                  ),
              },
              {
                header: text("notify.cost"),
                kind: "money",
                priority: 3,
                render: (policy) =>
                  policy.cost_per_message_minor === null || policy.currency === null ? (
                    <span className="muted">—</span>
                  ) : (
                    <span className="data" dir="ltr">
                      {money(policy.cost_per_message_minor, policy.currency)}
                    </span>
                  ),
              },
            ]}
          />
        )}
        {mayPolicies.allowed && usableChannels(channels).length === 0 &&
          channels.length > 0 ? (
          <Banner severity="attention">{text("notify.everyChannelDisabled")}</Banner>
        ) : null}
      </section>

      <section className="page-section">
        <h2 id="templates-heading" style={{ margin: 0 }}>{text("notify.templates")}</h2>
        {!mayTemplates.allowed ? (
          <Banner severity="info">{text(gateMessage(mayTemplates))}</Banner>
        ) : templates.length === 0 ? (
          <Banner severity="info">{text("notify.noTemplates")}</Banner>
        ) : (
          <DataGrid
            caption={text("notify.templates")}
            labelledBy="templates-heading"
            rows={templates}
            rowKey={(template) => template.template_id}
            columns={[
              {
                header: text("notify.template"),
                kind: "text",
                priority: 1,
                render: (template) => (
                  <>
                    <span className="data" dir="ltr">{template.template_key}</span>
                    <div className="muted" style={caption}>
                      {template.channel}
                      {" · "}
                      {template.locale}
                      {" · v"}
                      <span className="data">{formatInteger(template.version, "latn")}</span>
                    </div>
                  </>
                ),
              },
              {
                header: text("notify.category"),
                kind: "text",
                // Priority 1: the category decides whether a recipient's opt-out can stop
                // the message at all, which is the control §2463 is about.
                priority: 1,
                render: (template) => (
                  <>
                    {template.category}
                    <div className="muted" style={caption}>
                      {template.category === "marketing" || template.category === "coaching"
                        ? text("notify.canBeMuted")
                        : text("notify.cannotBeMuted")}
                    </div>
                  </>
                ),
              },
              {
                header: text("notify.status"),
                kind: "status",
                priority: 2,
                render: (template) => template.status,
              },
              {
                header: text("notify.variables"),
                kind: "text",
                priority: 3,
                render: (template) => (
                  <span className="data" dir="ltr">
                    {template.variables.join(", ") || "—"}
                  </span>
                ),
              },
            ]}
          />
        )}
        {mayTemplates.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("notify.categoryDecides")}
          </p>
        ) : null}
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("notify.digests")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("notify.digestsLead")}
        </p>
        {!mayNotifications.allowed ? (
          <Banner severity="info">{text(gateMessage(mayNotifications))}</Banner>
        ) : digests.length === 0 ? (
          <Banner severity="info">{text("notify.noDigests")}</Banner>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {digests.map((digest) => (
              <li key={digest.digest_id}>
                {digest.category}
                {" · "}
                {digest.channel}
                {" · "}
                <span className="data">
                  {formatInteger(digest.notification_count, numbering)}
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

function Shell({
  locale,
  children,
  figures,
}: {
  locale: Locale;
  children: React.ReactNode;
  /**
   * The counts under the title.
   *
   * **The design's page header is a title and a line of figures, never a paragraph**, and
   * every drawn canvas does the same: "4,812 active · 312 expired · 68 frozen · all
   * locations". A board whose header carried only its own name made a reader scroll to find
   * out whether anything on it needed them.
   */
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader title={t(locale, "notify.title")} {...(figures ? { figures } : {})} />
      {children}

      {/* **What ADM-COM-02 and ADM-COM-04 draw and this build has no read for.** Named here
          rather than left to be noticed, which is the members list's precedent: an absent
          block reads as a fact about the product rather than about the screen. */}
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{t(locale, "notify.notYet")}</h2>
        <dl className="facts">
          <dt className="muted">{t(locale, "notify.noMatrixTitle")}</dt>
          <dd style={{ margin: 0 }}>{t(locale, "notify.noMatrixWhy")}</dd>
          <dt className="muted">{t(locale, "notify.noPairTitle")}</dt>
          <dd style={{ margin: 0 }}>{t(locale, "notify.noPairWhy")}</dd>
        </dl>
      </section>
      {/* **The lead paragraph moved to the foot.** The design's page header is a title and a
          line of figures -- every drawn canvas does the same -- so an explanation of what the
          screen is was pushing the data a manager opens the page for below the fold. What is
          kept is the half that is a product disclosure rather than a description, and it
          answers a question here instead of delaying one. */}
      <p className="ds-screen-note">{t(locale, "notify.lead")}</p>
    </div>
  );
}



const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };
