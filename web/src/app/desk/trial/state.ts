/**
 * What FD-05's start can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`
 * and a client component that imports a module touching it fails the build -- the account
 * page's first version made the *login* page answer 500 that way.
 */
import type { TrialSteps } from "@/lib/walk-in-trial";

export type TrialStarted = {
  leadId: string;
  membershipNumber: string;
  trialDays: number | null;
  endsOn: string | null;
  steps: TrialSteps;
};

export type WalkInTrialState = {
  /** The trial that is now running, or `null` when nothing was written. */
  started: TrialStarted | null;
  error:
    | "deskTrial.refused"
    | "deskTrial.needsStepUp"
    | "deskTrial.duplicate"
    | "deskTrial.noPlan"
    | "deskTrial.pickPlan"
    | "error.network"
    | "error.tooMany"
    | null;
  missing: { name?: true; phone?: true };
  echo: { name?: string; phone?: string };
};

export const IDLE: WalkInTrialState = {
  started: null, error: null, missing: {}, echo: {},
};
