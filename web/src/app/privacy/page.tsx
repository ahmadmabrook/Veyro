import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { Prose } from "@/components/prose";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
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
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayPurposes, mayRetention, mayDsar, mayIncidents] = await Promise.all([
    gate("privacy.purpose.read"),
    gate("privacy.retention.read"),
    gate("privacy.dsar.read"),
    gate("privacy.incident.read"),
  ]);

  if (
    !mayPurposes.allowed && !mayRetention.allowed && !mayDsar.allowed &&
    !mayIncidents.allowed
  ) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {mayDsar.reachable ? text("gate.denied") : text("gate.unreachable")}
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
    <Shell locale={locale}>
      {failed ? <Banner severity="critical">{text("error.unexpected")}</Banner> : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("privacy.erasure")}</h2>
        {!mayDsar.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
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
                  {formatInteger(reach.residue_count, "latn")}
                </span>{" "}
                {text("privacy.columns")}
              </dd>
            </dl>
            <h3 style={{ margin: 0 }}>{text("privacy.whatSurvives")}</h3>
            <p className="muted" style={{ margin: 0 }}>
              {text("privacy.groupedBecause")}
            </p>
            <table
              tabIndex={0}
              style={{ width: "100%", borderCollapse: "collapse" }}
              aria-label={text("privacy.whatSurvives")}
            >
              <thead>
                <tr>
                  <th scope="col" style={head}>{text("privacy.area")}</th>
                  <th scope="col" style={head}>{text("privacy.columnsKept")}</th>
                  <th scope="col" style={head}>{text("privacy.why")}</th>
                </tr>
              </thead>
              <tbody>
                {groupResidue(reach).map((group) => (
                  <tr key={group.area}>
                    <td style={cell}>
                      <span className="data" dir="ltr">{group.area}</span>
                      <div className="muted" style={caption}>
                        <span className="data" dir="ltr">
                          {group.tables.slice(0, 3).join(", ")}
                        </span>
                        {group.tables.length > 3
                          ? ` +${formatInteger(group.tables.length - 3, "latn")}`
                          : ""}
                      </div>
                    </td>
                    <td style={cell}>
                      <span className="data">
                        {formatInteger(group.columns, "latn")}
                      </span>
                    </td>
                    <td style={cell}>
                      <Prose>{group.example}</Prose>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("privacy.notThisTenant")}
            </p>
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("privacy.requests")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("privacy.requestsLead")}
        </p>
        {!mayDsar.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : queue.length === 0 ? (
          <Banner severity="info">{text("privacy.noRequests")}</Banner>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("privacy.requests")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("privacy.requestType")}</th>
                <th scope="col" style={head}>{text("privacy.status")}</th>
                <th scope="col" style={head}>{text("privacy.due")}</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((request) => (
                <tr key={request.request_id}>
                  <td style={cell}>
                    {request.request_type}
                    <div className="muted" style={caption}>
                      {text("privacy.received")}{" "}
                      <span className="data" dir="ltr">
                        {request.received_at.slice(0, 10)}
                      </span>
                    </div>
                  </td>
                  <td style={cell}>{request.status}</td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {request.due_at.slice(0, 10)}
                    </span>
                    {request.overdue ? (
                      <div style={{ ...caption, color: "var(--color-text-critical)" }}>
                        {text("privacy.overdue")}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {mayDsar.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("privacy.onlyDeletionExecutes")}
          </p>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("privacy.holds")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("privacy.holdsLead")}
        </p>
        {!mayRetention.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
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

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("privacy.retention")}</h2>
        {!mayRetention.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : policies.length === 0 ? (
          <Banner severity="info">{text("privacy.noRetention")}</Banner>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("privacy.retention")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("privacy.resource")}</th>
                <th scope="col" style={head}>{text("privacy.dataClass")}</th>
                <th scope="col" style={head}>{text("privacy.keptFor")}</th>
                <th scope="col" style={head}>{text("privacy.basis")}</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((policy) => (
                <tr key={policy.policy_id}>
                  <td style={cell}>
                    <span className="data" dir="ltr">{policy.resource_type}</span>
                  </td>
                  <td style={cell}>{policy.data_class}</td>
                  <td style={cell}>
                    <span className="data">
                      {formatInteger(policy.retention_days, "latn")}
                    </span>{" "}
                    {text("privacy.days")}
                  </td>
                  <td style={cell}>{policy.legal_basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {mayRetention.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("privacy.nothingSweeps")}
          </p>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("privacy.purposes")}</h2>
        {!mayPurposes.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : purposes.length === 0 ? (
          <Banner severity="info">{text("privacy.noPurposes")}</Banner>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("privacy.purposes")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("privacy.purpose")}</th>
                <th scope="col" style={head}>{text("privacy.lawfulBasis")}</th>
                <th scope="col" style={head}>{text("privacy.dataClasses")}</th>
              </tr>
            </thead>
            <tbody>
              {purposes.map((purpose) => (
                <tr key={purpose.purpose_id}>
                  <td style={cell}>
                    {purpose.description}
                    <div className="muted" style={caption}>
                      <span className="data" dir="ltr">{purpose.purpose_code}</span>
                      {purpose.retired_at === null
                        ? ""
                        : ` · ${text("privacy.retired")}`}
                    </div>
                  </td>
                  <td style={cell}>{purpose.lawful_basis}</td>
                  <td style={cell}>{purpose.data_classes.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("privacy.incidents")}</h2>
        {!mayIncidents.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
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

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "privacy.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "privacy.lead")}
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
