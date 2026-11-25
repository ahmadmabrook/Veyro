/**
 * ADM-STF-03's reads, apart from the decisions they feed.
 *
 * Separate because the invite form is a client component and `@/lib/api` reaches
 * `next/headers` — the split the account page, the cash board and ADM-SCH-07's sheet all
 * record, the last of which took every page in the app to a 500.
 */
import { api, correlationId } from "@/lib/api";
import type { InvitationList } from "@/lib/invitations";

export function listInvitations(includeSettled = false): Promise<InvitationList> {
  const query = new URLSearchParams({
    correlation_id: correlationId(),
    include_settled: includeSettled ? "true" : "false",
  });
  return api<InvitationList>(`/authz/invitations?${query.toString()}`);
}
