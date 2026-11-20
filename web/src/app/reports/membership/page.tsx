import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { formatInteger, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, failureMessage } from "@/lib/api";
import { readMembershipSummary, type MembershipSummary } from "@/lib/command-centre-reads";
import { presentation } from "@/lib/preferences";

/**
 * ADM-RPT-03 · MEMBERSHIP — joins, leaves, and the net movement this month.
 *
 * **The three figures the canvas leads with are here and the chart under them is not.**
 * ADM-RPT-03 draws `+61 / −23 / +38` over a bar chart titled WHY THE 23 LEFT, with five
 * named reasons: no reason given, moving away, too expensive, not using it, went elsewhere.
 * Its own note says where those come from -- "Reasons come from ADM-MSH-07's required field.
 * Nine of 23 gave no reason — shown honestly rather than folded into 'other'."
 *
 * **There is no such field.** `mem_lifecycle_changes.reason` is free prose: a sentence
 * somebody typed about why this membership ended. Charting five named reasons from it would
 * mean classifying what a person wrote, and this is a retention report -- the screen an owner
 * uses to decide what to change about the business. A bar labelled "Too expensive · 4" that
 * was produced by keyword-matching prose is a confident wrong answer in the place it costs
 * most, and MOD-016 already shipped a control decided by matching words in prose and had a
 * reviewer defeat it with a promotion key containing the word "ended".
 *
 * **The prose is not shown either, and that is the second reason.** MOD-017's own rule, from
 * its review: "A health fact is a health fact whatever column it is in." A freeze's reason is
 * masked for exactly this -- a reviewer read a staged diagnosis out of one -- and a
 * cancellation reason is the same column one lifecycle event over. `membership.record.read`
 * is routine and tenant-wide, which a front desk holds. So the gap is named rather than
 * filled, which is what the rest of this build does with a figure it cannot produce.
 *
 * **Net is returned, not computed here.** Joined minus left is arithmetic a page could do,
 * and a second definition of a figure is two answers the day either moves -- which is this
 * repository's own argument for `entitlements.balance_of` over a `sum()` in SQL.
 */
export default async function MembershipReportPage() {
  const { locale } = await presentation();
  const numbering = "latn" as const;
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("membership.record.read");
  if (!may.allowed) {
    return (
      <>
        <PageHeader title={text("membershipReport.heading")} />
        <Banner severity="info">{text("membershipReport.refusedWhy")}</Banner>
      </>
    );
  }

  let summary: MembershipSummary | null = null;
  let failed: MessageKey | null = null;
  try {
    summary = await readMembershipSummary();
  } catch (error) {
    failed = failureMessage(error);
  }

  if (summary === null) {
    return (
      <>
        <PageHeader title={text("membershipReport.heading")} />
        <Banner severity="critical">{text(failed ?? "error.unexpected")}</Banner>
      </>
    );
  }

  const month = summary.this_month;
  const count = (value: number) => (
    <span className="data" dir="ltr">{formatInteger(value, numbering)}</span>
  );
  // A signed figure, because the net is the one number on this screen whose direction is the
  // whole point. `−` is the minus sign, not a hyphen: the canvas sets it in mono beside the
  // other two and a hyphen is visibly shorter there.
  const net = month.net > 0 ? `+${month.net}` : month.net < 0
    ? `−${Math.abs(month.net)}` : "0";

  return (
    <>
      <PageHeader
        title={text("membershipReport.heading")}
        figures={<span className="data" dir="ltr">{summary.as_of}</span>}
      />

      <MetricRow label={text("membershipReport.title")} columns={4}>
        <MetricCell label={text("membershipReport.joined")} value={count(month.joined)} />
        <MetricCell label={text("membershipReport.left")} value={count(month.left)} />
        <MetricCell
          label={text("membershipReport.net")}
          value={<span className="data" dir="ltr">{net}</span>}
          {...(month.net === 0 ? {} : {
            delta: { text: net, tone: month.net < 0 ? "down" as const : "up" as const },
          })}
        />
        <MetricCell label={text("membershipReport.active")} value={count(summary.active)} />
      </MetricRow>

      <section className="page-section" aria-labelledby="churn-reasons">
        <h2 id="churn-reasons">{text("membershipReport.whyTitle")}</h2>
        <Banner severity="info">{text("membershipReport.whyUnavailable")}</Banner>
        <ProseNote>{text("membershipReport.whyAlsoSensitive")}</ProseNote>
      </section>

      <section className="page-section" aria-labelledby="cohort">
        <h2 id="cohort">{text("membershipReport.cohortTitle")}</h2>
        <ProseNote>{text("membershipReport.cohortWhy")}</ProseNote>
      </section>
    </>
  );
}
