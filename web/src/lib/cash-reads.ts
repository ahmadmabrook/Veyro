import { api } from "@/lib/api";

import type { CashSessions } from "@/lib/cash";

/**
 * ADM-PAY-09's read, kept apart from its decisions.
 *
 * `@/lib/api` reaches `next/headers`, so anything importing it is server-only; the count
 * typed on this screen is parsed in a client component, and `@/lib/cash` is the module it
 * can import because this file is the one that cannot.
 */
export function readCashSessions(
  options: { status?: "open" | "closed"; locationId?: string; limit?: number } = {},
): Promise<CashSessions> {
  const query = new URLSearchParams();
  if (options.status) query.set("status", options.status);
  if (options.locationId) query.set("location_id", options.locationId);
  if (options.limit) query.set("limit", String(options.limit));
  const suffix = query.toString();
  return api<CashSessions>(`/ledger/cash-sessions${suffix ? `?${suffix}` : ""}`);
}
