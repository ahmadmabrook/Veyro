import { api } from "@/lib/api";

import type { Board, LeadDetail, LeadList, LeadFilter, SourceRow } from "@/lib/leads";

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
