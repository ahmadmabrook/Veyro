import { api } from "@/lib/api";

/**
 * ADM-CC-01's four reads, each asking the module that owns the answer.
 *
 * **Four requests, not one composed endpoint.** Paragraph 1300 bars a cross-domain join and
 * MOD-014's own projection says in its `sections` block that it does not read MOD-017; a
 * surface has no such restriction and every reason to compose, which is the call ADM-MEM-05
 * already made and the Member 360 before it. Each read is behind its own permission, so a
 * reader who holds three of the four gets three panels and a refusal in the fourth rather
 * than an empty page — which is the design's own canvas 2, where a club manager is shown a
 * differently prioritised Command Center rather than a reduced one.
 *
 * **The design names four independent requests and this is them.** Its loading section:
 * "Shell and rail render immediately from cached role and scope. Then, in parallel and each
 * with its own skeleton at true final height: metrics, attention queue, charts, AI panel."
 */

export type CollectedBlock = {
  currency: string;
  collected_minor: number;
  previous_minor: number;
  change_bp: number | null;
  pace_minor: number;
  by_week: { first: string; last: string; partial: boolean; collected_minor: number }[];
  by_legal_entity: { legal_entity_id: string; collected_minor: number }[];
};

export type Collections = {
  as_of: string;
  month_to_date: { first: string; last: string; days: number };
  comparable_previous_month: { first: string; last: string; days: number; clamped: boolean };
  collected: CollectedBlock[];
  pace_is_a_projection: string;
  by_location_is_unavailable: string;
};

export type MembershipSummary = {
  as_of: string;
  active: number;
  by_status: Record<string, number>;
  this_month: { first: string; last: string; joined: number; left: number; net: number };
  expiring: {
    within_days: number;
    until: string;
    count: number;
    renewal_value: { currency: string; amount_minor: number }[];
    memberships: {
      membership_id: string;
      person_id: string;
      membership_number: string;
      status: string;
      expires_on: string;
      amount_minor: number;
      currency: string;
    }[];
  };
};

export type Visits = {
  /** The day the locations share. A caller's `on` when it named one. */
  date: string;
  weekday: string;
  /**
   * True where the tenant's clubs are on two dates at once.
   *
   * A club's day is local to its own zone, so a tenant spanning zones genuinely has two
   * todays for a few hours. The headline date is one of them and this says so, rather than
   * letting one club's date stand for all of them.
   */
  local_days_differ: boolean;
  entries: number;
  locations: {
    location_id: string;
    location_name: string;
    timezone: string;
    /** The day *this* club's figure is about, resolved in its own zone. */
    date: string;
    weekday: string;
    entries: number;
    usual_for_this_weekday: number | null;
    weekdays_compared: number;
  }[];
};

export type DunningCases = {
  cases: {
    case_id: string;
    invoice_id: string;
    stage: number;
    attempts: number;
    next_action_on: string | null;
    document_number: string;
    outstanding_minor: number;
    currency: string;
    access_recommendation: string;
    owner_ref: string | null;
  }[];
  count: number;
  at_risk: { currency: string; amount_minor: number }[];
};

export type Unstaffed = {
  from_date: string;
  to_date: string;
  count: number;
  members_affected: number;
  sessions: {
    session_id: string;
    display_name: string;
    local_starts_at: string;
    timezone: string;
    location_name: string;
    held: number;
    places: number;
  }[];
};

export type RejectedFilings = {
  invoices: {
    invoice_id: string;
    document_number: string;
    gross_minor: number;
    currency: string;
    fiscal_status: string;
    issued_on: string;
  }[];
  count: number;
};

export function readCollections(weeks = 12): Promise<Collections> {
  return api(`/finance/collections?weeks=${weeks}`);
}

export function readMembershipSummary(withinDays = 7): Promise<MembershipSummary> {
  return api(`/memberships/summary?expiring_within_days=${withinDays}`);
}

export function readVisits(): Promise<Visits> {
  return api("/access/visits");
}

export function readDunningCases(): Promise<DunningCases> {
  return api("/finance/dunning-cases?status=open&limit=50");
}

export function readUnstaffed(days = 7): Promise<Unstaffed> {
  return api(`/scheduling/unstaffed?days=${days}`);
}

/**
 * Invoices the tax authority rejected — the COMPLIANCE item.
 *
 * **Filtered on the server.** `fiscal_status` is a filter on `GET /finance/invoices` rather
 * than a predicate applied here, because the list is bounded at 200 rows: a count derived
 * from a bounded page would report the first page as the tenant, which is the same defect as
 * summing a page to get a month.
 *
 * The design calls this item "JoFotara rejected 3 invoices". **There is no JoFotara adapter
 * in this build** — ADM-SET-03 is that screen and it is unbuilt — so what this reads is the
 * generic fiscal status, and the page names the authority generically for the same reason.
 */
export function readRejectedFilings(): Promise<RejectedFilings> {
  return api("/finance/invoices?fiscal_status=rejected&limit=50");
}
