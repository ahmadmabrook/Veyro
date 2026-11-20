import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  credentialIsCurrent,
  listConnections,
  listCredentials,
  listCursors,
  listInstalls,
  listRuns,
  missingObligations,
  obligationsApply,
  needsSomebody,
  obligationsMet,
  reportedNotObserved,
  type Connection,
  type ConnectorRun,
  type CredentialRef,
  type Install,
  type SyncCursor,
} from "@/lib/integrations";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * MOD-012's board: what is installed, what it may reach, and what it has done.
 *
 * **Nothing syncs, and the page says so where the figures are.** There is no provider, no
 * outbound HTTP and no adapter code: `start_run`, `finish_run` and `fail_run` are written by
 * whatever does the work and nothing does, so `records_read` and `records_written` are
 * numbers a caller supplied. A board rendering them as data that moved would be the
 * fabricated-evidence shape this codebase has been bitten by six times -- and it is the shape
 * MOD-012's own review found, where any holder of a routine permission could settle a running
 * run as "synced four million records" with the only name on it belonging to the party that
 * did *not* make the claim.
 *
 * **A credential is a reference to a vault this build does not have**, which is the same
 * sentence the fleet board says about device certificates, deliberately in the same words:
 * MOD-007's TOTP seeds, MOD-009's crypto-shred, MOD-012's webhook signatures and MOD-021's
 * device keys are all waiting on one vault, and four screens saying it four ways would read as
 * four different gaps.
 *
 * **A `live_critical` install needs three things in writing before it may carry traffic**, and
 * they are checked at activation with nothing re-checking afterwards. MOD-012's review found
 * three blank strings erasing all three from a live install with the same permission that
 * wrote them -- `coalesce` replaces NULL, not the empty string -- so this board recomputes the
 * check on every read, which is the cheapest place a surface can close that window.
 */
export default async function IntegrationsPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayInstalls, mayConnections, mayCredentials, maySync] = await Promise.all([
    gate("integrations.install.read"),
    gate("integrations.connection.read"),
    gate("integrations.credential.read"),
    gate("integrations.sync.read"),
  ]);

  if (
    !mayInstalls.allowed && !mayConnections.allowed && !mayCredentials.allowed &&
    !maySync.allowed
  ) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">
          {mayInstalls.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Banner>
      </Shell>
    );
  }

  let installs: Install[] = [];
  let connections: Connection[] = [];
  let credentials: CredentialRef[] = [];
  let cursors: SyncCursor[] = [];
  let runs: ConnectorRun[] = [];
  let failed = false;
  try {
    [installs, connections, credentials, cursors, runs] = await Promise.all([
      mayInstalls.allowed ? listInstalls() : Promise.resolve([]),
      mayConnections.allowed ? listConnections() : Promise.resolve([]),
      mayCredentials.allowed ? listCredentials() : Promise.resolve([]),
      maySync.allowed ? listCursors() : Promise.resolve([]),
      maySync.allowed ? listRuns() : Promise.resolve([]),
    ]);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    failed = true;
  }

  const unmet = installs.filter((i) => !obligationsMet(i));
  const dead = runs.filter(needsSomebody);

  return (
    <Shell locale={locale}>
      {failed ? <Banner severity="critical">{text("error.unexpected")}</Banner> : null}

      {maySync.allowed ? (
        <Banner severity="attention">{text("integrations.nothingSyncs")}</Banner>
      ) : null}

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("integrations.installs")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("integrations.installsLead")}
        </p>
        {!mayInstalls.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : installs.length === 0 ? (
          <Banner severity="info">{text("integrations.noInstalls")}</Banner>
        ) : (
          <>
            {unmet.length > 0 ? (
              <Banner severity="critical">
                {text("integrations.obligationsMissing")}{" "}
                {unmet.map((i) => i.definition_key).join(", ")}
              </Banner>
            ) : null}
            <table
              tabIndex={0}
              style={{ width: "100%", borderCollapse: "collapse" }}
              aria-label={text("integrations.installs")}
            >
              <thead>
                <tr>
                  <th scope="col" style={head}>{text("integrations.integration")}</th>
                  <th scope="col" style={head}>{text("integrations.criticality")}</th>
                  <th scope="col" style={head}>{text("integrations.state")}</th>
                  <th scope="col" style={head}>{text("integrations.inWriting")}</th>
                </tr>
              </thead>
              <tbody>
                {installs.map((install) => {
                  const missing = missingObligations(install);
                  return (
                    <tr key={install.install_id}>
                      <td style={cell}>
                        <span className="data" dir="ltr">{install.definition_key}</span>
                        <div className="muted" style={caption}>
                          {"v"}
                          <span className="data">
                            {formatInteger(install.definition_version, "latn")}
                          </span>
                          {" · "}
                          {text("integrations.snapshotted")}
                        </div>
                      </td>
                      <td style={cell}>{install.criticality}</td>
                      <td style={cell}>{install.state}</td>
                      <td style={cell}>
                        {!obligationsApply(install) ? (
                          <span className="muted">{text("integrations.notRequired")}</span>
                        ) : missing.length === 0 ? (
                          text("integrations.allThree")
                        ) : (
                          <span className="data" dir="ltr">
                            {text("integrations.missing")} {missing.join(", ")}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
              {text("integrations.obligationsNote")}
            </p>
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("integrations.connections")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("integrations.connectionsLead")}
        </p>
        {!mayConnections.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : connections.length === 0 ? (
          <Banner severity="info">{text("integrations.noConnections")}</Banner>
        ) : (
          <table
            tabIndex={0}
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={text("integrations.connections")}
          >
            <thead>
              <tr>
                <th scope="col" style={head}>{text("integrations.account")}</th>
                <th scope="col" style={head}>{text("integrations.state")}</th>
                <th scope="col" style={head}>{text("integrations.mayReach")}</th>
                <th scope="col" style={head}>{text("integrations.validated")}</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((connection) => (
                <tr key={connection.connection_id}>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {connection.external_account_ref}
                    </span>
                    {connection.region === null ? null : (
                      <div className="muted" style={caption}>{connection.region}</div>
                    )}
                  </td>
                  <td style={cell}>{connection.state}</td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {connection.granted_scopes.join(", ")}
                    </span>
                  </td>
                  <td style={cell}>
                    {connection.validated_at === null ? (
                      <span className="muted">{text("integrations.notValidated")}</span>
                    ) : (
                      <>
                        <span className="data" dir="ltr">
                          {connection.validated_at.slice(0, 10)}
                        </span>
                        <div className="muted" style={caption}>
                          {text("integrations.validatedMeans")}
                        </div>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {mayConnections.allowed ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("integrations.scopesNote")}
          </p>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("integrations.credentials")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("integrations.credentialsLead")}
        </p>
        {!mayCredentials.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : credentials.length === 0 ? (
          <Banner severity="info">{text("integrations.noCredentials")}</Banner>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {credentials.map((credential) => (
              <li key={credential.credential_ref_id}>
                {credentialIsCurrent(credential) ? (
                  <strong>{text("integrations.current")}</strong>
                ) : (
                  <span className="muted">{text("integrations.superseded")}</span>
                )}
                {" — "}
                <span className="data" dir="ltr">{credential.vault_ref}</span>
                <div className="muted" style={caption}>
                  <span className="data" dir="ltr">
                    {credential.scopes.join(", ") || "—"}
                  </span>
                  {credential.expires_at === null ? null : (
                    <>
                      {" · "}
                      {text("integrations.expires")}{" "}
                      <span className="data" dir="ltr">
                        {credential.expires_at.slice(0, 10)}
                      </span>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {mayCredentials.allowed ? (
          <Banner severity="info">{text("integrations.noVault")}</Banner>
        ) : null}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("integrations.runs")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("integrations.runsLead")}
        </p>
        {!maySync.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : runs.length === 0 ? (
          <Banner severity="info">{text("integrations.noRuns")}</Banner>
        ) : (
          <>
            {dead.length > 0 ? (
              <Banner severity="attention">
                {text("integrations.deadRuns")}{" "}
                <span className="data">{formatInteger(dead.length, "latn")}</span>
              </Banner>
            ) : null}
            <table
              tabIndex={0}
              style={{ width: "100%", borderCollapse: "collapse" }}
              aria-label={text("integrations.runs")}
            >
              <thead>
                <tr>
                  <th scope="col" style={head}>{text("integrations.resource")}</th>
                  <th scope="col" style={head}>{text("integrations.state")}</th>
                  <th scope="col" style={head}>{text("integrations.attempts")}</th>
                  <th scope="col" style={head}>{text("integrations.reported")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id}>
                    <td style={cell}>
                      <span className="data" dir="ltr">{run.resource}</span>
                      <div className="muted" style={caption}>
                        <span className="data" dir="ltr">{utcStamp(run.started_at)}</span>
                      </div>
                    </td>
                    <td style={cell}>
                      {run.status}
                      {needsSomebody(run) ? (
                        <div className="muted" style={caption}>
                          {text("integrations.needsRelease")}
                        </div>
                      ) : null}
                    </td>
                    <td style={cell}>
                      <span className="data">
                        {formatInteger(run.attempts, "latn")}
                      </span>
                      {" / "}
                      <span className="data">
                        {formatInteger(run.max_attempts, "latn")}
                      </span>
                    </td>
                    <td style={cell}>
                      <span className="data">
                        {formatInteger(run.records_read, "latn")}
                      </span>{" "}
                      {text("integrations.read")}
                      {" · "}
                      <span className="data">
                        {formatInteger(run.records_written, "latn")}
                      </span>{" "}
                      {text("integrations.written")}
                      {reportedNotObserved(run) ? (
                        <div className="muted" style={caption}>
                          {text("integrations.reportedNotObserved")}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("integrations.cursors")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("integrations.cursorsLead")}
        </p>
        {!maySync.allowed ? (
          <Banner severity="info">{text("gate.denied")}</Banner>
        ) : cursors.length === 0 ? (
          <Banner severity="info">{text("integrations.noCursors")}</Banner>
        ) : (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {cursors.map((cursor) => (
              <li key={cursor.cursor_id}>
                <span className="data" dir="ltr">{cursor.resource}</span>
                {" · "}
                {cursor.conflict_policy}
                <div className="muted" style={caption}>
                  {text("integrations.observedAt")}{" "}
                  <span className="data" dir="ltr">{utcStamp(cursor.observed_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
        {maySync.allowed && cursors.length > 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
            {text("integrations.conflictNote")}
          </p>
        ) : null}
      </section>
    </Shell>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "integrations.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "integrations.lead")}
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
