import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { Prose } from "@/components/prose";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage } from "@/lib/api";
import {
  erasesOf,
  holdIsLive,
  listIncidents,
  listLegalHolds,
  listPurposes,
  listRequests,
  listRetention,
  needingAction,
  readErasureReach,
  groupResidue,
  type DataSubjectRequest,
  type ErasureReach,
  type LegalHold,
  type ProcessingPurpose,
  type RetentionPolicy,
  type SecurityIncident,
} from "@/lib/privacy";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * MOD-009's board, and the one thing on it that is not about this tenant.
 *
 * **This build cannot fully erase a person, and that is a tested disclosure rather than a
 * silence.** Every `plt01` column naming a subject has neither UPDATE nor DELETE for any
 * runtime role -- the financial ledger, published configuration, recorded exposures, and
 * MOD-009's own evidence -- and three `iam` tables likewise: the audit chain, the
 * authentication log and approval decisions. Each is correct on its own terms; insert-only is
 * what makes a ledger reconstructible and an audit chain tamper-evident. Together they mean
 * erasure reaches the identity plane's mutable tables and MOD-014's contact data and stops.
 *
 * Until this page the disclosure had nowhere to live. `deletion_is_complete()` returns False
 * and `plan_dsar` surfaces it per request, so the honest answer to "what can you delete" was
 * reachable only after somebody had asked you to delete something, and the registry behind it
 * lived in Python and in a test. The block below is that registry, read from a route that
 * takes no tenant and reads nobody's rows.
 *
 * **A live legal hold is the control with the window.** It is durable with no expiry, so
 * `fulfil_dsar` re-reads holds at the moment it acts rather than trusting the legal check that
 * passed earlier -- litigation ordinarily starts *after* a request is queued, and an erasure
 * that ran under a correctly-served preservation order and reported `completed` is the defect
 * two independent reviewers found here. The board shows live holds first for the same reason.
 *
 * **Five permissions, five blocks**, each asked separately. A refused block says it was
 * refused rather than rendering empty.
 */
export default async function PrivacyPage() {
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
  const [mayPurposes, mayRetention, mayDsar, mayIncidents] = await gateAll([
    "privacy.purpose.read",
    "privacy.retention.read",
    "privacy.dsar.read",
    "privacy.incident.read",
  ] as const);

  if (
    !mayPurposes.allowed && !mayRetention.allowed && !mayDsar.allowed &&
    !mayIncidents.allowed
  ) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {text(gateMessage(mayDsar))}
        </Banner>
      </Shell>
    );
  }

  let purposes: ProcessingPurpose[] = [];
  let policies: RetentionPolicy[] = [];
  let holds: LegalHold[] = [];
  let requests: DataSubjectRequest[] = [];
  let incidents: SecurityIncident[] = [];
  let reach: ErasureReach | null = null;
  let failed = false;
  try {
    [purposes, policies, holds, requests, incidents, reach] = await Promise.all([
      mayPurposes.allowed ? listPurposes() : Promise.resolve([]),
      mayRetention.allowed ? listRetention() : Promise.resolve([]),
      mayRetention.allowed ? listLegalHolds() : Promise.resolve([]),
      mayDsar.allowed ? listRequests() : Promise.resolve([]),
      mayIncidents.allowed ? listIncidents() : Promise.resolve([]),
      mayDsar.allowed ? readErasureReach() : Promise.resolve(null),
    ]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  const queue = needingAction(requests);
  const liveHolds = holds.filter(holdIsLive);

  return (
    <Shell
      locale={locale}
      figures={
        <>
          {fill(locale, "privacy.requestsCounted", { count: requests.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "privacy.queueCounted", { count: queue.length }, numbering)}
          {" \u00b7 "}
          {fill(locale, "privacy.holdsCounted", { count: liveHolds.length }, numbering)}
          {reach === null ? null : (
            <> {"\u00b7 "}{fill(locale, "privacy.residueCounted",
              { count: reach.residue_count }, numbering)}</>
          )}
        </>
      }
    >
      {failed ? <Banner severity="critical">{text("error.unexpected")}</Banner> : null}

      <section className="page-section">
        <h2 id="erasure-heading" style={{ margin: 0 }}>{text("privacy.erasure")}</h2>
        {!mayDsar.allowed ? (
          <Banner severity="info">{text(gateMessage(mayDsar))}</Banner>
        ) : reach === null ? (
          <Banner severity="critical">{text("error.unexpected")}</Banner>
        ) : (
          <>
            {reach.erasure_is_complete ? (
              <Banner severity="neutral">{text("privacy.erasureComplete")}</Banner>
            ) : (
              <Banner severity="attention">{text("privacy.erasureIncomplete")}</Banner>
            )}
            <p style={{ margin: 0 }}>{reach.why_incomplete}</p>
            <dl className="facts">
              <dt className="muted">{text("privacy.erases")}</dt>
              <dd style={{ margin: 0 }}>
                <span className="data">
                  {formatInteger(erasesOf(reach).length, "latn")}
                </span>{" "}
                {text("privacy.columns")}
              </dd>
              <dt className="muted">{text("privacy.residue")}</dt>
              <dd style={{ margin: 0 }}>
                <span className="data">
                  {formatInteger(reach.residue_count, numbering)}
                </span>{" "}
                {text("privacy.columns")}
              </dd>
            </dl>
            <h3 style={{ margin: 0 }}>{text("privacy.whatSurvives")}</h3>
            <p className="muted" style={{ margin: 0 }}>
              {text("privacy.groupedBecause")}
            </p>
            <DataGrid
              caption={text("privacy.whatSurvives")}
              labelledBy="erasure-heading"
              rows={groupResidue(reach)}
              rowKey={(group) => group.area}
              columns={[
                {
                  header: text("privacy.area"),
                  kind: "text",
                  priority: 1,
                  render: (group) => (
                    <>
                      <span className="data" dir="ltr">{group.area}</span>
                      <div className="muted" style={caption}>
                        <span className="data" dir="ltr">
                          {group.tables.slice(0, 3).join(", ")}
                        </span>
                        {group.tables.length > 3
                          ? ` +${formatInteger(group.tables.length - 3, numbering)}`
                          : ""}
                      </div>
                    </>
                  ),
                },
                {
                  header: text("privacy.columnsKept"),
                  kind: "text",
                  priority: 1,
                  render: (group) => (
                    <span className="data">{formatInteger(group.columns, numbering)}</span>
                  ),
                },
                {
                  header: text("privacy.why"),
                  kind: "text",
                  // The reason is the whole point of the block -- a count of surviving
                  // columns with no reason beside it is a number nobody can act on -- so it
                  // is priority 2 rather than 3 and drops only on a phone.
                  priority: 2,
                  render: (group) => <Prose>{group.example}</Prose>,
                },
              ]}
            />
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("privacy.notThisTenant")}
            </p>
          </>
        )}
      </section>

      <section className="page-section">
        <h2 id="requests-heading" style={{ margin: 0 }}>{text("privacy.requests")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("privacy.requestsLead")}
        </p>
        {!mayDsar.allowed ? (
          <Banner severity="info">{text(gateMessage(mayDsar))}</Banner>
        ) : queue.length === 0 ? (
          <Banner severity="info">{text("privacy.noRequests")}</Banner>
        ) : (
          <DataGrid
            caption={text("privacy.requests")}
            labelledBy="requests-heading"
            rows={queue}
            rowKey={(request) => request.request_id}
            // An overdue request is the regulator-facing deadline missed, which is the one
            // row on this board that is somebody's problem today.
            rowSeverity={(request) => (request.overdue ? "critical" : null)}
            columns={[
              {
                header: text("privacy.requestType"),
                kind: "text",
                priority: 1,
                render: (request) => (
                  <>
                    {request.request_type}
                    <div className="muted" style={caption}>
                      {text("privacy.received")}{" "}
                      <span className="data" dir="ltr">
                        {request.received_at.slice(0, 10)}
                      </span>
                    </div>
                  </>
                ),
              },
              {
                header: text("privacy.due"),
                kind: "date",
                priority: 1,
                render: (request) => (
                  <>
                    <span className="data" dir="ltr">{request.due_at.slice(0, 10)}</span>
                    {request.overdue ? (
                      <div style={{ ...caption, color: "var(--color-text-critical)" }}>
                        {text("privacy.overdue")}
                      </div>
                    ) : null}
                  </>
                ),
              },
              {
                header: text("privacy.status"),
                kind: "status",
                priority: 2,
                render: (request) => request.status,
              },
            ]}
          />
        )}
        {mayDsar.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("privacy.onlyDeletionExecutes")}
          </p>
        ) : null}
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("privacy.holds")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("privacy.holdsLead")}
        </p>
        {!mayRetention.allowed ? (
          <Banner severity="info">{text(gateMessage(mayRetention))}</Banner>
        ) : holds.length === 0 ? (
          <Banner severity="info">{text("privacy.noHolds")}</Banner>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {[...liveHolds, ...holds.filter((h) => !holdIsLive(h))].map((hold) => (
              <li key={hold.hold_id}>
                {holdIsLive(hold) ? (
                  <strong>{text("privacy.preserving")}</strong>
                ) : (
                  <span className="muted">{text("privacy.released")}</span>
                )}
                {" — "}
                {hold.reason}
                <div className="muted" style={caption}>
                  <span className="data" dir="ltr">{hold.reference}</span>
                  {" · "}
                  {hold.resource_type ?? text("privacy.everyResource")}
                  {" · "}
                  <span className="data" dir="ltr">{utcStamp(hold.placed_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="page-section">
        <h2 id="retention-heading" style={{ margin: 0 }}>{text("privacy.retention")}</h2>
        {!mayRetention.allowed ? (
          <Banner severity="info">{text(gateMessage(mayRetention))}</Banner>
        ) : policies.length === 0 ? (
          <Banner severity="info">{text("privacy.noRetention")}</Banner>
        ) : (
          <DataGrid
            caption={text("privacy.retention")}
            labelledBy="retention-heading"
            rows={policies}
            rowKey={(policy) => policy.policy_id}
            columns={[
              {
                header: text("privacy.resource"),
                kind: "text",
                priority: 1,
                render: (policy) => (
                  <span className="data" dir="ltr">{policy.resource_type}</span>
                ),
              },
              {
                header: text("privacy.keptFor"),
                kind: "text",
                priority: 1,
                render: (policy) => (
                  <>
                    <span className="data">
                      {formatInteger(policy.retention_days, numbering)}
                    </span>{" "}
                    {text("privacy.days")}
                  </>
                ),
              },
              {
                header: text("privacy.dataClass"),
                kind: "text",
                priority: 2,
                render: (policy) => policy.data_class,
              },
              {
                header: text("privacy.basis"),
                kind: "text",
                priority: 3,
                render: (policy) => policy.legal_basis,
              },
            ]}
          />
        )}
        {mayRetention.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("privacy.nothingSweeps")}
          </p>
        ) : null}
      </section>

      <section className="page-section">
        <h2 id="purposes-heading" style={{ margin: 0 }}>{text("privacy.purposes")}</h2>
        {!mayPurposes.allowed ? (
          <Banner severity="info">{text(gateMessage(mayPurposes))}</Banner>
        ) : purposes.length === 0 ? (
          <Banner severity="info">{text("privacy.noPurposes")}</Banner>
        ) : (
          <DataGrid
            caption={text("privacy.purposes")}
            labelledBy="purposes-heading"
            rows={purposes}
            rowKey={(purpose) => purpose.purpose_id}
            // A retired purpose is a fact about a record that is over, not a problem.
            rowSeverity={() => null}
            columns={[
              {
                header: text("privacy.purpose"),
                kind: "text",
                priority: 1,
                render: (purpose) => (
                  <>
                    {purpose.description}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{purpose.purpose_code}</span>
                      {purpose.retired_at === null ? "" : ` · ${text("privacy.retired")}`}
                    </div>
                  </>
                ),
              },
              {
                header: text("privacy.lawfulBasis"),
                kind: "text",
                priority: 1,
                render: (purpose) => purpose.lawful_basis,
              },
              {
                header: text("privacy.dataClasses"),
                kind: "text",
                priority: 2,
                render: (purpose) => purpose.data_classes.join(", "),
              },
            ]}
          />
        )}
      </section>

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("privacy.incidents")}</h2>
        {!mayIncidents.allowed ? (
          <Banner severity="info">{text(gateMessage(mayIncidents))}</Banner>
        ) : incidents.length === 0 ? (
          <Banner severity="info">{text("privacy.noIncidents")}</Banner>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {incidents.map((incident) => (
              <li key={incident.incident_id}>
                {incident.summary}
                <div className="muted" style={caption}>
                  {incident.severity}
                  {" · "}
                  {incident.category}
                  {" · "}
                  {text("privacy.personalData")} {incident.personal_data_involved}
                </div>
              </li>
            ))}
          </ul>
        )}
        {mayIncidents.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("privacy.noBreachClock")}
          </p>
        ) : null}
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
      <PageHeader title={t(locale, "privacy.title")} {...(figures ? { figures } : {})} />
      {children}
      {/* **The lead paragraph moved to the foot.** The design's page header is a title and a
          line of figures -- every drawn canvas does the same -- so an explanation of what the
          screen is was pushing the data a manager opens the page for below the fold. What is
          kept is the half that is a product disclosure rather than a description, and it
          answers a question here instead of delaying one. */}
      <p className="ds-screen-note">{t(locale, "privacy.lead")}</p>
    </div>
  );
}



const caption: React.CSSProperties = { fontSize: "var(--type-caption-size)" };
