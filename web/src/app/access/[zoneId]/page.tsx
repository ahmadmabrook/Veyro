import { notFound, redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { RecordHeader } from "@/components/ds/record-header";
import { fill, formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate, gateMessage } from "@/lib/api";
import {
  DISCREET,
  isRestricted,
  readDecisions,
  readOccupancy,
  readZone,
  type DecisionPage,
  type Occupancy,
  type ZoneDetail,
  type ZonePolicy,
} from "@/lib/access";
import { presentation } from "@/lib/preferences";

/**
 * One zone: its terms, its readers, how many are inside, and what it has decided.
 *
 * **Three things on this page are the module's controls made visible**, and each is rendered
 * rather than summarised away:
 *
 *   * An exit-facing reader is labelled "records only; never decides". Paragraph 4177 puts
 *     egress outside the Veyro application path, and an operator looking at a list of readers
 *     should be able to see which ones are not gates.
 *   * The occupancy carries paragraph 4180's disclaimer verbatim, next to the number. A
 *     figure without it is the one somebody counts heads against during an evacuation.
 *   * A decision shows **what the member was shown** and, separately, the full reason -- and
 *     when the caller does not hold `access.decision.read_reason`, the full reason is marked
 *     withheld rather than filled in with the public text. The server returns null there; a
 *     surface that rendered the discreet line in that slot would make "the member was told
 *     the whole truth" indistinguishable from "we are not showing you".
 */
export default async function ZonePage({
  params,
}: {
  params: Promise<{ zoneId: string }>;
}) {
  const { zoneId } = await params;
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");
  // **The answer, not just its `allowed`.** A refusal has four meanings and only the whole
  // answer tells them apart; discarding it here reported a failed request as "Not permitted".
  const may = await gate("access.zone.read");
  if (!may.allowed) {
    return (
      <Shell title={text("access.title")}>
        <Banner severity="info">{text(gateMessage(may))}</Banner>
      </Shell>
    );
  }

  let zone: ZoneDetail;
  try {
    zone = await readZone(zoneId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    if (error instanceof ApiError && error.status === 422) notFound();
    return (
      <Shell title={text("access.title")}>
        <Banner severity="critical">{text("error.unexpected")}</Banner>
      </Shell>
    );
  }

  // The occupancy and the decision log are separate permissions from the zone read, and a
  // refusal on either must not take the page with it: a front desk that may see the doors and
  // not the log still needs the doors.
  const occupancy = await readOccupancy(zoneId).catch(() => null);
  const decisions = (await gate("access.decision.read")).allowed
    ? await readDecisions(zoneId).catch(() => null)
    : null;
  // **A TypeScript type is a claim about a JSON response, not a check on it.** Against a
  // server that predates `counts` the field is `undefined`, and reading `.granted` off it
  // threw -- which took the whole page down with a 500 rather than losing one cell. The
  // counts are recomputed from the rows when the server does not send them, which is both a
  // fallback and the assertion that the two agree.
  const counts = decisions === null ? null : (decisions.counts ?? {
    granted: decisions.decisions.filter((one) => one.bucket === "granted").length,
    policy: decisions.decisions.filter((one) => one.bucket === "policy").length,
    fault: decisions.decisions.filter((one) => one.bucket === "fault").length,
  });

  const entries = zone.points.filter((point) => point.decides_entry).length;

  return (
    <div className="ds-inspector-pane">
      <RecordHeader
        name={zone.display_name}
        {...(zone.policy === null
          ? { band: { text: text("access.noPolicyBand"), tone: "critical" as const } }
          : {})}
        subline={
          <>
            {text(`access.risk.${zone.risk_class}` as MessageKey)}
            {" · "}
            {fill(locale, "access.pointsCounted",
              { count: zone.points.length, entries })}
            {" · "}
            {text("access.offlineCeiling")}{" "}
            <span className="data" dir="ltr">
              {formatInteger(Math.round(zone.snapshot_ceiling_seconds / 3600), "latn")}
            </span>{" "}
            {text("access.hours")}
          </>
        }
      />
      <div className="ds-record-body">
      {/* ADM-ACC-02's counts, which the canvas argues for rather than merely draws: "Policy
          and fault are separate filters for a reason. Twenty-seven expired memberships is
          the system working. Four reader failures is a maintenance job. Mixing them in one
          count hides the second inside the first." The classification is MOD-022's own, by
          reason code, so two screens cannot disagree about which a refusal was. */}
      <MetricRow label={text("access.metrics")} columns={4}>
        <MetricCell
          label={text("access.insideNow")}
          {...(occupancy === null
            ? { freshness: "unavailable" as const,
                unavailableBecause: text("metric.notPermitted") }
            : {
              value: (
                <span className="data" dir="ltr">
                  {formatInteger(occupancy.inside, "latn")}
                </span>
              ),
              // Paragraph 4180: advisory unless both directions are reliably measured, and
              // never a muster source. The word is in the cell rather than under it.
              comparison: text(
                `access.confidence.${occupancy.confidence}` as MessageKey),
            })}
        />
        <MetricCell
          label={text("access.grantedMetric")}
          {...(decisions === null || counts === null
            ? { freshness: "unavailable" as const,
                unavailableBecause: text("metric.notPermitted") }
            : {
              value: (
                <span className="data" dir="ltr">
                  {formatInteger(counts.granted, "latn")}
                </span>
              ),
              comparison: fill(locale, "access.ofDecisions",
                { count: decisions.decisions.length }),
            })}
        />
        <MetricCell
          label={text("access.policyMetric")}
          {...(decisions === null || counts === null
            ? { freshness: "unavailable" as const,
                unavailableBecause: text("metric.notPermitted") }
            : {
              value: (
                <span className="data" dir="ltr">
                  {formatInteger(counts.policy, "latn")}
                </span>
              ),
              comparison: text("access.policyMeans"),
            })}
        />
        <MetricCell
          label={text("access.faultMetric")}
          {...(decisions === null || counts === null
            ? { freshness: "unavailable" as const,
                unavailableBecause: text("metric.notPermitted") }
            : {
              value: (
                <span className="data" dir="ltr">
                  {formatInteger(counts.fault, "latn")}
                </span>
              ),
              comparison: text("access.faultMeans"),
            })}
        />
      </MetricRow>

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("access.policy")}</h2>
        </div>
        <div className="ds-panel-body">
          {zone.policy === null ? (
            <Banner severity="critical">{text("access.noPolicy")}</Banner>
          ) : (
            <Terms policy={zone.policy} locale={locale} />
          )}
        </div>
      </section>

      {occupancy ? <OccupancyPanel occupancy={occupancy} locale={locale} /> : null}

      <section className="ds-panel">
        <div className="ds-panel-head">
          <h2 className="ds-panel-title">{text("access.points")}</h2>
        </div>
        <div className="ds-panel-body">
        <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
          {zone.points.map((point) => (
            <li key={point.point_id}>
              {point.display_name}{" "}
              <span className="muted">
                — {text(`access.direction.${point.direction}` as MessageKey)}
              </span>
              {point.decides_entry ? null : (
                <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                  {text("access.decidesNothing")}
                </div>
              )}
            </li>
          ))}
        </ul>
        </div>
      </section>

      {zone.access_gaps.length > 0 ? (
        <section className="ds-panel">
          <div className="ds-panel-head">
            <h2 className="ds-panel-title">{text("access.gaps")}</h2>
          </div>
          <div className="ds-panel-body">
            <ul className="muted" style={{ margin: 0,
              paddingInlineStart: "var(--space-5)" }}>
              {zone.access_gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {decisions ? <DecisionLog page={decisions} locale={locale} /> : null}
      </div>
    </div>
  );
}

function Terms({ policy, locale }: { policy: ZonePolicy; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  const hhmm = (minute: number) =>
    `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
  const rows: [string, React.ReactNode][] = [
    [
      text("access.terms.opens"),
      policy.opens_minute === null || policy.closes_minute === null ? (
        text("access.terms.none")
      ) : (
        // Isolated: a clock range is a Latin run inside what may be an RTL paragraph, and
        // without `dir` the bidi algorithm moves the dash and the colon.
        <span className="data" dir="ltr">
          {hhmm(policy.opens_minute)}–{hhmm(policy.closes_minute)}
        </span>
      ),
    ],
    [text("access.terms.entitlement"), policy.requires_entitlement ? "✓" : "—"],
    [
      text("access.terms.balance"),
      policy.max_balance_minor === null ? (
        text("access.terms.none")
      ) : (
        <span className="data">{formatInteger(policy.max_balance_minor, "latn")}</span>
      ),
    ],
    [
      text("access.terms.age"),
      policy.min_age_years === null ? (
        text("access.terms.none")
      ) : (
        <>
          <span className="data">{formatInteger(policy.min_age_years, "latn")}</span>{" "}
          {text("access.terms.years")}
        </>
      ),
    ],
    [
      text("access.terms.passback"),
      policy.anti_passback_seconds === 0 ? (
        text("access.terms.none")
      ) : (
        <>
          <span className="data">{formatInteger(policy.anti_passback_seconds, "latn")}</span>{" "}
          {text("access.terms.seconds")}
        </>
      ),
    ],
    [
      text("access.terms.capacity"),
      policy.capacity === null ? (
        text("access.terms.none")
      ) : (
        <span className="data">{formatInteger(policy.capacity, "latn")}</span>
      ),
    ],
  ];
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--space-2)", margin: 0 }}>
      {rows.map(([label, value]) => (
        <div key={label} style={{ display: "contents" }}>
          <dt className="muted">{label}</dt>
          <dd style={{ margin: 0 }}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The occupancy disclaimer.
 *
 * **The figure moved into the metric row and the caveat did not follow it**, which would
 * have been the defect: paragraph 4180 makes this number advisory unless both directions are
 * reliably measured, and never the sole life-safety muster source. A cell carrying `0` with
 * the word "advisory" under it is not the same sentence. So the number is a metric and the
 * server's own words stay beside it in full -- shortening them here would be the interface
 * deciding the caveat was not worth the space.
 */
function OccupancyPanel({ occupancy, locale }: { occupancy: Occupancy; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("access.occupancyCaveat")}</h2>
      </div>
      <div className="ds-panel-body">
        <Banner severity="info">{occupancy.detail}</Banner>
      </div>
    </section>
  );
}

function DecisionLog({ page, locale }: { page: DecisionPage; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="ds-panel" aria-labelledby="decisions-heading">
      <div className="ds-panel-head">
        <h2 id="decisions-heading" className="ds-panel-title">{text("access.decisions")}</h2>
      </div>
      {page.decisions.length === 0 ? (
        <Banner severity="info">{text("access.noDecisions")}</Banner>
      ) : (
        <DataGrid
          caption={text("access.decisions")}
          labelledBy="decisions-heading"
          rows={page.decisions}
          rowKey={(decision) => decision.decision_id}
          // A refusal at a door is what somebody reads this log for.
          rowSeverity={(decision) => (decision.granted ? null : "attention")}
          columns={[
            {
              header: text("access.policy"),
              kind: "status",
              priority: 1,
              render: (decision) => (
                <>
                  {decision.granted ? text("access.granted") : text("access.refused")}
                  <div
                    className="muted data"
                    dir="ltr"
                    style={{ fontSize: "var(--type-caption-size)" }}
                  >
                    {decision.code}
                  </div>
                </>
              ),
            },
            {
              header: text("access.shownToMember"),
              kind: "text",
              priority: 1,
              render: (decision) => (
                <>
                  {decision.public_reason}
                  {decision.public_reason === DISCREET || isRestricted(decision.code) ? (
                    <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                      {/* Marked, because a reader of this log should be able to tell at a
                          glance that the member was not told why -- which is the whole trade
                          paragraph 1944 makes. */}
                      {text("access.reasonWithheld")}
                    </div>
                  ) : null}
                </>
              ),
            },
            {
              header: text("access.fullReason"),
              kind: "text",
              priority: 2,
              render: (decision) =>
                decision.private_reason === null ? (
                  <span className="muted">{text("access.reasonWithheld")}</span>
                ) : (
                  decision.private_reason
                ),
            },
            {
              header: text("access.when"),
              kind: "date",
              priority: 2,
              // A timestamp is a Latin run; isolated for the same reason as the clock range.
              render: (decision) => (
                <span className="data" dir="ltr">
                  {decision.decided_at.slice(0, 19).replace("T", " ")}
                </span>
              ),
            },
          ]}
        />
      )}
    </section>
  );
}

/**
 * The shell for a page with no zone to name.
 *
 * **No breadcrumb.** `Doors` is on the rail; a link above the title repeating a rail entry
 * is the chrome saying the same thing twice, which is what every other screen in this app
 * stopped doing.
 */
function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="ds-inspector-pane">
      <PageHeader title={title} />
      <div className="ds-record-body">{children}</div>
    </div>
  );
}


