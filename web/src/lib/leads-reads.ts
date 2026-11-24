import { api } from "@/lib/api";

import type {
  Board, LeadDetail, LeadList, LeadFilter, SourceRow, TrialCard,
} from "@/lib/leads";

/**
 * The reads ADM-CRM-01 to 04 make.
 *
 * **`mine` is a flag rather than a person id.** The browser has no person id for the reader
 * -- a session carries an `identity_id` and the link to a person is MOD-014's -- so a
 * client-side "mine" filter is not expressible at all, and sending one up would let a reader
 * ask the question as somebody else. The server derives it, as MOD-026's task list does.
 *
 * **The board's counts are the tenant's, the table's rows are the page's.** The board read
 * counts over every lead; the table is a bounded page. A chip figure taken from the page
 * would be the members-list finding -- summing the rows was honest and still the wrong number
 * in the place a manager reads the business.
 */

export function listLeads(params: {
  filter?: LeadFilter;
  stage?: string;
  limit?: number;
}): Promise<LeadList> {
  const query = new URLSearchParams();
  if (params.filter === "going_cold") query.set("going_cold", "true");
  if (params.filter === "mine") query.set("mine", "true");
  if (params.stage) query.set("stage", params.stage);
  query.set("limit", String(params.limit ?? 50));
  return api(`/crm/leads?${query.toString()}`);
}

export function readBoard(params: { mine?: boolean } = {}): Promise<Board> {
  const query = new URLSearchParams();
  if (params.mine) query.set("mine", "true");
  const suffix = query.toString();
  return api(suffix ? `/crm/board?${suffix}` : "/crm/board");
}

export function readLead(leadId: string): Promise<LeadDetail> {
  return api(`/crm/leads/${leadId}`);
}

/** ADM-CRM-04's dropdown. Retired sources are left out, which is what makes it a dropdown. */
export function listSources(): Promise<{ sources: SourceRow[] }> {
  return api("/crm/sources?limit=50");
}

/**
 * ADM-CRM-05's card, or why there is not one.
 *
 * **Three permissions**, because the card carries three modules' facts: the window is
 * MOD-017's, the visits are MOD-022's entry events and the classes are MOD-020's settled
 * bookings. A reader holding only the lead read gets 403 for the whole card rather than three
 * of its four cells, which is what the canvas draws.
 *
 * **Every figure is the server's.** `day_of`, `days_left` and the band are all arithmetic over
 * today, and a browser comparing dates against its own clock counts in the wrong frame --
 * which this app has three recorded defects from.
 */
export function readLeadTrial(leadId: string): Promise<TrialCard> {
  return api(`/crm/leads/${leadId}/trial`);
}
