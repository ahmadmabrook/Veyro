import { api } from "@/lib/api";

import type { AccessDecision } from "@/lib/denial";

/** The I/O half of FD-03, apart from the decisions for the reason every screen here does. */

export function readDecisions(personId: string): Promise<{ decisions: AccessDecision[] }> {
  return api<{ decisions: AccessDecision[] }>(
    `/access/decisions?person_id=${encodeURIComponent(personId)}&limit=50`);
}

export type PersonAttendance = {
  person_id: string;
  last_entry_on: string | null;
  last_location: string | null;
  days_since: number | null;
  entries_in_window: number;
  weeks: number;
  entries_per_week: number | null;
};

/**
 * **Behind `access.decision.read`, which this screen already holds.** An entry record is
 * strictly less disclosing than the decision rows that permission returns -- no code, no
 * reason, no policy -- so the pattern comes free with the refusal rather than costing a
 * second gate.
 */
export function readAttendance(personId: string): Promise<PersonAttendance> {
  return api<PersonAttendance>(
    `/access/attendance?person_id=${encodeURIComponent(personId)}`);
}
