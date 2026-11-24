"use server";

import { api } from "@/lib/api";
import type { ConflictCheck } from "@/lib/new-class";

/**
 * ADM-SCH-03's live check, as the form asks it.
 *
 * **Asked as the fields change, not on save**, which is the canvas's own instruction: "a
 * save-time error means re-deciding everything else too". So it is a server action the client
 * calls on a debounce, the way `checkPhone` is for the three screens that look for a duplicate
 * number -- and like that one, every failure is one answer rather than several, because which
 * failure it was is not actionable on this screen.
 *
 * **`unknown` is not `clear`.** A check the server could not be asked has not told anybody the
 * hour is free, and a form that treated silence as a clear would be showing a green field over
 * a studio that is booked. The caller renders the difference; nothing here smooths it over.
 */
export type CheckAnswer =
  | { outcome: "checked"; result: ConflictCheck }
  | { outcome: "refused" }
  | { outcome: "unknown" };

export async function checkClass(proposal: {
  locationId: string;
  localTime: string;
  durationMinutes: number;
  weekdays: number[];
  startsOn: string;
  until: string;
  capacity: number;
  setupMinutes: number;
  cleanupMinutes: number;
  waitlistCapacity: number;
  requirements: { kind: string; quantity: number; resource_id?: string }[];
}): Promise<CheckAnswer> {
  if (proposal.weekdays.length === 0 || proposal.requirements.length === 0) {
    return { outcome: "unknown" };
  }
  try {
    const result = await api<ConflictCheck>("/scheduling/conflict-check", {
      method: "POST",
      body: {
        location_id: proposal.locationId,
        rule: {
          frequency: "weekly",
          local_time: proposal.localTime,
          duration_minutes: proposal.durationMinutes,
          starts_on: proposal.startsOn,
          until: proposal.until,
          weekdays: proposal.weekdays,
        },
        policy: {
          capacity: proposal.capacity,
          setup_minutes: proposal.setupMinutes,
          cleanup_minutes: proposal.cleanupMinutes,
          waitlist_capacity: proposal.waitlistCapacity,
        },
        requirements: proposal.requirements,
      },
    });
    return { outcome: "checked", result };
  } catch {
    // **A refusal and a failure are told apart by the caller and not here**, because the
    // remedy is the same on this screen: the answer is absent either way and the form says
    // the hour has not been checked. A 422 means the rule itself is unusable, which the
    // fields will show as soon as one more of them is filled in.
    return { outcome: "unknown" };
  }
}
