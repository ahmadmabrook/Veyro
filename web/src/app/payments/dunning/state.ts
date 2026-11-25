/**
 * What ADM-PAY-06's one write can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`
 * and a client component that imports a module touching it fails the build -- the account
 * page's first version made the *login* page answer 500 that way, and `@/lib/people` made it
 * happen again through a pure predicate that happened to live beside an impure import.
 */
export type DunningError =
  | "dunning.refused"
  | "dunning.needsStepUp"
  | "dunning.notAWholeNumber"
  | "dunning.outOfBand"
  | "error.network"
  | "error.tooMany";

export type DunningState = {
  /** The figures as saved, so the banner states what is now in force rather than "done". */
  saved: { retryAttempts: number; accessGraceDays: number } | null;
  error: DunningError | null;
  /** What they typed, so a refusal does not empty a figure somebody is holding. */
  echo: { retry?: string; grace?: string };
};

export const IDLE: DunningState = { saved: null, error: null, echo: {} };
