import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { MoneyValue } from "@/components/ds/money-value";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { gate } from "@/lib/api";
import { readAttendance, readCredentials, recordBand } from "@/lib/member-record";
import {
  listGrants,
  listInvoices,
  listMemberships,
  isOutstanding,
  outstandingMinor,
  remaining,
  type InvoiceRow,
  type MembershipRow,
} from "@/lib/membership";

/**
 * ADM-MEM-01's metric row: `OUTSTANDING · MEMBERSHIP · LAST VISIT · PT CREDITS · ACCESS`.
 *
 * Five cells from four modules, each behind its own gate, and the one thing that makes this
 * component worth having rather than inlining: **it also decides the header's band**, because
 * the band is a statement about the same five facts and computing it twice from two reads is
 * how the Front Desk's obligations cell and its banner came to disagree.
 *
 * Every cell that cannot be read says so with `freshness="unavailable"` rather than rendering
 * a zero or an em-dash: `MoneyValue`'s own rule is "never blank, never zero", and a `0` in
 * `OUTSTANDING` for a reader who may not see invoices is a financial misstatement about a
 * member.
 */

export type MemberFacts = {
  band: ReturnType<typeof recordBand>;
  outstandingMinor: number | null;
  currency: string | null;
  membership: MembershipRow | null;
  row: React.ReactNode;
};

export async function memberFacts(
  personId: string, locale: Locale,
): Promise<MemberFacts> {
  const text = (key: MessageKey) => t(locale, key);
  const [finance, records, entitlements, visits, credentials] = await Promise.all([
    gate("finance.account.read"),
    gate("membership.record.read"),
    gate("membership.entitlement.read"),
    gate("access.decision.read"),
    gate("access.credential.read"),
  ]);

  // Each read is attempted only where its gate allowed, and a failure is the cell's own
  // "unavailable" rather than the page's error: one module being down must not take the
  // member's record with it.
  const [invoices, memberships, grants, attendance, held] = await Promise.all([
    finance.allowed ? listInvoices(personId).catch(() => null) : null,
    records.allowed ? listMemberships(personId).catch(() => null) : null,
    entitlements.allowed ? listGrants(personId).catch(() => null) : null,
    visits.allowed ? readAttendance(personId).catch(() => null) : null,
    credentials.allowed ? readCredentials(personId).catch(() => null) : null,
  ]);

  const rows: InvoiceRow[] = invoices?.invoices ?? [];
  const owed = invoices === null ? null : outstandingMinor(rows);
  // `isOutstanding` rather than a gross-minus-paid comparison: a credited or written-off
  // invoice is settled, and counting either would put a figure in front of somebody that
  // nobody is going to collect. The library owns that distinction and says why.
  const unpaidRows = rows.filter(isOutstanding);
  const owedCurrency = unpaidRows[0]?.currency ?? rows[0]?.currency ?? null;
  const unpaid = unpaidRows.length;

  // The membership the band and the MEMBERSHIP cell are about: the live one if there is one,
  // else the most recently started, so a lapsed member's cell says when it lapsed rather
  // than nothing at all.
  const all = memberships?.memberships ?? [];
  const live = all.find((row) => row.status === "active")
    ?? all.find((row) => row.status === "frozen" || row.status === "paused")
    ?? all[0] ?? null;

  const counted = (grants?.grants ?? []).filter((grant) => grant.is_counted);
  const credits = counted.reduce(
    (sum, grant) => sum + (remaining(grant).balance ?? 0), 0);
  const creditsOf = counted.reduce(
    (sum, grant) => sum + (grant.granted_quantity ?? 0), 0);

  const band = recordBand({
    outstandingMinor: owed ?? 0,
    membershipStatus: live?.status ?? null,
  });

  return {
    band,
    outstandingMinor: owed,
    currency: owedCurrency,
    membership: live,
    row: (
      <MetricRow label={text("member.metrics")} columns={5}>
        <MetricCell
          label={text("member.outstanding")}
          {...(owed === null || owedCurrency === null
            ? {
              freshness: "unavailable" as const,
              unavailableBecause: text(
                finance.allowed ? "metric.readFailed" : "metric.notPermitted"),
            }
            : {
              value: (
                <MoneyValue
                  kind={owed > 0 ? "owed" : "aggregate"}
                  amountMinor={owed}
                  currency={owedCurrency}
                />
              ),
              comparison: fill(locale, "member.unpaidCount", { count: unpaid }),
            })}
        />
        <MetricCell
          label={text("member.membershipMetric")}
          {...(live === null
            ? {
              freshness: "unavailable" as const,
              unavailableBecause: text(
                records.allowed ? "member.noMembership" : "metric.notPermitted"),
            }
            : {
              value: (
                <span className="data" dir="ltr">
                  {live.current_period_end ?? live.ends_on ?? live.starts_on}
                </span>
              ),
              comparison: live.status,
            })}
        />
        <MetricCell
          label={text("member.lastVisit")}
          {...(attendance === null || attendance.days_since === null
            ? {
              freshness: "unavailable" as const,
              unavailableBecause: text(
                !visits.allowed
                  ? "metric.notPermitted"
                  : attendance === null ? "metric.readFailed" : "member.neverVisited"),
            }
            : {
              // Zero is "today", which English's two CLDR categories cannot express: a
              // `zero` form in an English message is one nothing can ever select, so the
              // case gets its own key rather than a plural form that is dead on arrival.
              value: attendance.days_since === 0
                ? text("member.today")
                : fill(locale, "member.daysAgo", { count: attendance.days_since }),
              // "was 3× a week" — past tense, because the rate is measured over the weeks
              // before the last visit rather than before today. The service says why.
              comparison: attendance.entries_per_week === null
                ? undefined
                : fill(locale, "member.wasPerWeek", {
                  rate: attendance.entries_per_week.toFixed(1),
                }),
            })}
        />
        <MetricCell
          label={text("member.credits")}
          {...(grants === null
            ? {
              freshness: "unavailable" as const,
              unavailableBecause: text(
                entitlements.allowed ? "metric.readFailed" : "metric.notPermitted"),
            }
            : counted.length === 0
              ? {
                freshness: "unavailable" as const,
                unavailableBecause: text("member.noCountedGrant"),
              }
              : {
                value: (
                  <span className="data" dir="ltr">
                    {credits} / {creditsOf}
                  </span>
                ),
                comparison: fill(locale, "member.grantCount",
                  { count: counted.length }),
              })}
        />
        <MetricCell
          label={text("member.accessMetric")}
          {...(held === null
            ? {
              freshness: "unavailable" as const,
              unavailableBecause: text(
                credentials.allowed ? "metric.readFailed" : "metric.notPermitted"),
            }
            : {
              value: fill(locale, "member.liveCredentials", { count: held.live }),
              // **Holding a credential is not an admission**, and the cell says so rather
              // than reading as "Granted": whether this person gets in is decided per
              // presentation against the zone's policy, their membership and their
              // entitlement, and nothing on a record page can evaluate that without
              // recording a decision.
              comparison: text("member.notAnAdmission"),
            })}
        />
      </MetricRow>
    ),
  };
}
