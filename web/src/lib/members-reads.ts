import { api } from "@/lib/api";

import type { MembersPage, MembershipRow } from "@/lib/members";

/**
 * The two reads ADM-MEM-05 needs, and the reason there are two.
 *
 * MOD-014 owns the person and their lifecycle state; MOD-017 owns the membership. Paragraph
 * 1300 bars a cross-domain join, so this surface asks each module its own question and the
 * page composes — one extra request for the whole table rather than one per row.
 */

export function listMembers(params: {
  lifecycleState?: string;
  limit?: number;
}): Promise<MembersPage> {
  const query = new URLSearchParams();
  if (params.lifecycleState) query.set("lifecycle_state", params.lifecycleState);
  query.set("limit", String(params.limit ?? 50));
  return api(`/people?${query.toString()}`);
}

/**
 * The tenant's memberships, for the PLAN and RENEWS columns.
 *
 * Bounded to the same page size the member list uses: this is a lookup table for the rows on
 * screen, not an inventory, and a person on the page whose membership falls outside the bound
 * renders as "not on this page's membership read" rather than as "no membership" — which is
 * the distinction the column would otherwise get wrong.
 */
export function listMemberships(limit = 200): Promise<{ memberships: MembershipRow[] }> {
  return api(`/memberships?limit=${limit}`);
}
