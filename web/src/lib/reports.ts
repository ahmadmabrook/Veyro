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
  {
    screen: "ADM-RPT-04",
    href: "/reports/attendance",
    name: "reports.attendanceName",
    summary: "reports.attendanceSummary",
    // **The access plane's own read, not a reports permission.** An hourly histogram is the
    // same events `/access/visits` already counts at a different grain, and a second
    // permission for it would be a role that may see the day's total and not the hours it
    // is made of -- which is the revenue report's argument for reusing
    // `finance.revenue.read` rather than minting one.
    permission: "access.zone.read",
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

/* ------------------------------------------------- ADM-RPT-04 · ATTENDANCE */

export type AttendanceHour = {
  hour: number;
  entries: number;
  /** `null` where nobody came in at all, which is not the same as 0% — see the server. */
  share_of_peak_bp: number | null;
  tier: "quiet" | "busy" | "peak";
};

export type AttendanceReport = {
  location_id: string;
  location_name: string;
  /** The zone every hour on this chart is an hour of. */
  timezone: string;
  zone_id: string | null;
  weekdays: number[];
  weeks: number;
  window: {
    first_day: string;
    last_day: string;
    /** Days of the chosen set inside the window — what the bars are summed over. */
    days_counted: number;
    clamped: boolean;
  };
  entries: number;
  peak_entries: number;
  by_hour: AttendanceHour[];
  busiest: {
    from_hour: number;
    /** The hour the span *ends*, so 18:00 and 19:00 read as "18:00–20:00". */
    to_hour: number;
    busiest_hour: number;
    entries: number;
    other_peak_hours: number[];
  } | null;
  quietest: { hour: number; entries: number; share_of_peak_bp: number | null } | null;
  zones: {
    zone_id: string;
    display_name: string;
    entries: number;
    /** Its events stay, so it is listed and marked rather than dropped. */
    retired: boolean;
  }[];
  shares_are_of_the_peak_hour: string;
  opening_hours_are_not_recorded: string;
  entries_are_presentations: string;
  a_weekend_is_not_declared_anywhere: string;
  complete_days_only: string;
  zone_counts_are_not_narrowed: string;
  a_retired_zone_keeps_its_entries: string;
};

export function readAttendanceReport(
  locationId: string,
  weekdays: readonly number[],
  options: { zoneId?: string | null; weeks?: number } = {},
): Promise<AttendanceReport> {
  const query = new URLSearchParams();
  query.set("location_id", locationId);
  for (const day of weekdays) query.append("weekday", String(day));
  if (options.zoneId) query.set("zone_id", options.zoneId);
  if (options.weeks) query.set("weeks", String(options.weeks));
  return api<AttendanceReport>(`/reports/attendance?${query.toString()}`);
}

/**
 * The day ranges this screen offers, and why none of them is called "weekdays".
 *
 * **The canvas scopes its chart to "WEEKDAYS" and nothing in this build knows which days
 * those are.** A working week is Sunday to Thursday in the market this product is built for
 * and Monday to Friday in the one its design language comes from, and no table, constant or
 * MOD-005 configuration key declares either. So a chip labelled "Weekdays" would be the
 * surface picking a market convention and then presenting it as the product's own — which is
 * the one thing the delegation does not cover.
 *
 * Each chip therefore names *which days*, which is a fact, rather than what they mean to a
 * business, which is not. The note beside them says the choice is the reader's and why. A
 * reader who wants a single day asks for it in the URL: the route takes any set.
 */
export type DayRange = {
  key: string;
  label: MessageKey;
  /** 0 is Monday, which is MOD-019's rota convention rather than a second one. */
  days: readonly number[];
};

/** Every day, which is what the chart shows when nobody has narrowed it. */
export const DEFAULT_RANGE: DayRange = {
  key: "all",
  label: "attendanceReport.allDays",
  days: [0, 1, 2, 3, 4, 5, 6],
};

export const DAY_RANGES: readonly DayRange[] = [
  DEFAULT_RANGE,
  { key: "sun-thu", label: "attendanceReport.sunThu", days: [6, 0, 1, 2, 3] },
  { key: "mon-fri", label: "attendanceReport.monFri", days: [0, 1, 2, 3, 4] },
];

/** The range a `range=` parameter names, falling back to every day. */
export function dayRange(key: string | undefined): DayRange {
  return DAY_RANGES.find((range) => range.key === key) ?? DEFAULT_RANGE;
}

/**
 * An hour as a wall-clock label: 6 is "06:00".
 *
 * Padded and 24-hour because the axis is a clock rather than prose, and `Intl` would give a
 * locale's own 12-hour form for one of the two locales this app ships — which puts "6 AM"
 * under a heading whose other end reads "22:00".
 */
export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

/** A share of the busiest hour as a whole percentage, or `null` where there is no peak. */
export function sharePercent(bp: number | null): number | null {
  return bp === null ? null : Math.round(bp / 100);
}

/**
 * The bar's height as a percentage of the tallest, with a floor so a quiet hour is a mark.
 *
 * **An hour nobody came in is drawn at the baseline rather than omitted**, which is the
 * weekbar chart's own rule: an absent bar and a bar nobody can see are the same to a reader,
 * and "nothing happens before seven" is a reading this chart exists for.
 */
export function barHeightPercent(entries: number, peak: number): number {
  if (peak <= 0) return 0;
  return Math.max(2, Math.round((entries / peak) * 100));
}
