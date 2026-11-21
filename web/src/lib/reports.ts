import { api } from "@/lib/api";
import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-RPT-01 … ADM-RPT-05 — the reports index and what sits behind each entry.
 *
 * **The index is gated, and the canvas says what that means**: "A Club Manager opening this
 * screen sees four reports, not six. The two financial ones are absent — not listed and
 * locked." So each entry names the permission its report needs and the page asks the gate
 * about all of them in one round trip; an entry the session cannot open is not rendered.
 *
 * **An absent module is a different absence from a refused permission, and conflating them
 * would be the worse of the two mistakes.** A reader who cannot see Revenue because they are
 * a club manager has learned something true about their own access. A reader who cannot see
 * Coaching because MOD-023 is unbuilt would learn the same thing and it would be false --
 * they would go asking for a permission that does not exist. So `UNBUILT` is a separate list
 * the page names out loud, rather than four more rows quietly missing from the six.
 */

export type ReportEntry = {
  /** The canvas id, so the screen and the design can be matched by somebody checking. */
  screen: "ADM-RPT-02" | "ADM-RPT-03" | "ADM-RPT-04";
  href: string;
  name: MessageKey;
  /** "Collected, invoiced, outstanding, by source and club" — the canvas's own line. */
  summary: MessageKey;
  /** The permission the report needs. The index asks the gate, never a role list. */
  permission: string;
  /** The roles the canvas prints at the row's end: "OWNER · ACCT". */
  roles: string;
};

/**
 * The reports this build can produce, in the canvas's own order.
 *
 * Revenue and Membership are first because the canvas puts them first, and that order is not
 * arbitrary: it is the order an owner opens them in.
 */
export const REPORTS: readonly ReportEntry[] = [
  {
    screen: "ADM-RPT-02",
    href: "/reports/revenue",
    name: "reports.revenueName",
    summary: "reports.revenueSummary",
    permission: "finance.revenue.read",
    roles: "OWNER · ACCT",
  },
  {
    screen: "ADM-RPT-03",
    href: "/reports/membership",
    name: "reports.membershipName",
    summary: "reports.membershipSummary",
    permission: "membership.record.read",
    roles: "OWNER · CM",
  },
] as const;

/**
 * The canvas's other four entries, and why each is not a row.
 *
 * Named on the screen rather than omitted, because a reports index is a claim about what can
 * be reported: six entries in the design and two here is a difference a reader has to be
 * told about, or they will take the short list for the whole answer.
 */
export const UNBUILT: readonly { name: MessageKey; why: MessageKey }[] = [
  { name: "reports.attendanceName", why: "reports.attendanceWhy" },
  { name: "reports.coachingName", why: "reports.coachingWhy" },
  { name: "reports.leadsName", why: "reports.leadsWhy" },
  { name: "reports.taxName", why: "reports.taxWhy" },
] as const;

export type SourceRow = {
  /** COM-02-R01's own vocabulary, or `unattributed` for a line with no variant. */
  product_type: string;
  net_minor: number;
  previous_minor: number;
  change_bp: number | null;
  by_legal_entity: { legal_entity_id: string; net_minor: number }[];
};

export type RevenueCurrency = {
  currency: string;
  collected_minor: number;
  collected_previous_minor: number;
  collected_change_bp: number | null;
  invoiced_minor: number;
  invoiced_previous_minor: number;
  invoiced_change_bp: number | null;
  /** A position, not a flow — so it carries no previous-month comparison. */
  outstanding_minor: number;
  refunded_minor: number;
  refunded_previous_minor: number;
  /**
   * What the sources add up to.
   *
   * `invoiced_minor` is gross and a source row is net, so this is the figure a reader
   * checking the breakdown reconciles against -- returned by the server rather than summed
   * here, because a second definition of a total is two answers the day either moves.
   */
  invoiced_net_minor: number;
  by_source: SourceRow[];
};

export type RevenueReport = {
  as_of: string;
  month_to_date: { first: string; last: string; days: number };
  comparable_previous_month: { first: string; last: string; days: number; clamped: boolean };
  currencies: RevenueCurrency[];
  outstanding_is_a_position: string;
  unattributed_source_is_a_row: string;
  sources_are_net: string;
  by_location_is_unavailable: string;
};

export function readRevenueReport(): Promise<RevenueReport> {
  return api<RevenueReport>("/reports/revenue");
}

/**
 * The message key for a product type, so a report row reads as a part of the business.
 *
 * **An unknown type falls through to its stored value rather than to "other".** The set is
 * MOD-016's and may grow; a row labelled "other" hides which one it is, and this is a
 * revenue table where the whole point is knowing what earned the money. The same judgement
 * the notifications board makes about a decision reason it does not recognise.
 */
export function sourceName(productType: string): MessageKey | null {
  const known: Record<string, MessageKey> = {
    membership: "reports.sourceMembership",
    service: "reports.sourceService",
    session_credit: "reports.sourceSessionCredit",
    class_credit: "reports.sourceClassCredit",
    retail_sku: "reports.sourceRetail",
    subscription_addon: "reports.sourceAddon",
    event: "reports.sourceEvent",
    gift_card: "reports.sourceGiftCard",
    unattributed: "reports.sourceUnattributed",
  };
  return known[productType] ?? null;
}

/**
 * A change in basis points as a signed percentage, and which way it leans.
 *
 * `null` where there is nothing to compare against — which is not zero, and rendering it as
 * "0.0%" would claim a month that matched its predecessor exactly.
 */
export function change(bp: number | null): { text: string; tone: "up" | "down" } | null {
  if (bp === null) return null;
  const pct = bp / 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return {
    text: `${sign}${Math.abs(pct).toFixed(1)}%`,
    tone: pct < 0 ? "down" : "up",
  };
}
