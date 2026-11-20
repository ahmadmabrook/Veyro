import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
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
  if (!(await gate("access.zone.read")).allowed) {
    return (
      <Shell locale={locale} title={text("access.title")}>
        <Banner severity="info">{text("gate.denied")}</Banner>
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
      <Shell locale={locale} title={text("access.title")}>
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

  return (
    <Shell locale={locale} title={zone.display_name}>
      <section className="page-section">
        <h2>{text("access.policy")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("access.risk")}: {text(`access.risk.${zone.risk_class}` as MessageKey)} ·{" "}
          {text("access.offlineCeiling")}{" "}
          <span className="data">
            {formatInteger(Math.round(zone.snapshot_ceiling_seconds / 3600), "latn")}
          </span>{" "}
          {text("access.hours")}
        </p>
        {zone.policy === null ? (
          <Banner severity="critical">{text("access.noPolicy")}</Banner>
        ) : (
          <Terms policy={zone.policy} locale={locale} />
        )}
      </section>

      {occupancy ? <OccupancyPanel occupancy={occupancy} locale={locale} /> : null}

      <section className="page-section">
        <h2>{text("access.points")}</h2>
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
        {zone.access_gaps.length > 0 ? (
          <>
            <h3>{text("access.gaps")}</h3>
            <ul className="muted" style={{ paddingInlineStart: "var(--space-5)" }}>
              {zone.access_gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      {decisions ? <DecisionLog page={decisions} locale={locale} /> : null}
    </Shell>
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

function OccupancyPanel({ occupancy, locale }: { occupancy: Occupancy; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="page-section">
      <h2>{text("access.occupancy")}</h2>
      <p className="data" style={{ margin: 0, fontSize: "var(--type-display-size)" }}>
        {formatInteger(occupancy.inside, "latn")}
      </p>
      <p className="muted" style={{ margin: 0 }}>
        {text(`access.confidence.${occupancy.confidence}` as MessageKey)}
      </p>
      {/* **The disclaimer is the server's own words, rendered in full.** Paragraph 4180 makes
          this number advisory unless both directions are reliably measured, and never the
          sole life-safety muster source. Shortening it here would be the interface deciding
          the caveat was not worth the space. */}
      <Banner severity="info">{occupancy.detail}</Banner>
    </section>
  );
}

function DecisionLog({ page, locale }: { page: DecisionPage; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="page-section" aria-labelledby="decisions-heading">
      <h2 id="decisions-heading">{text("access.decisions")}</h2>
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

function Shell({
  locale,
  title,
  children,
}: {
  locale: Locale;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="stack">
      <nav aria-label={t(locale, "nav.back")}>
        <Link href="/access">{t(locale, "access.title")}</Link>
      </nav>
      <h1 style={{ margin: 0 }}>{title}</h1>
      {children}
    </div>
  );
}


