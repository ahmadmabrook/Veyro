/**
 * What ADM-MSH-09's one write can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`
 * and a client component that imports a module touching it fails the build — the account
 * page's first version made the *login* page answer 500 that way.
 */
export type PriceError =
  | "plans.refused"
  | "plans.needsStepUp"
  | "plans.notAnAmount"
  | "plans.datePast"
  | "error.network"
  | "error.tooMany";

export type Priced = {
  priceId: string;
  amountMinor: number;
  currency: string;
  effectiveFrom: string;
  /** What the figure was before, so the banner can state the change rather than the result. */
  wasMinor: number;
};

export type PriceState = {
  priced: Priced | null;
  error: PriceError | null;
  /** What they typed, so a refusal does not empty a figure somebody is holding. */
  echo: { amount?: string; from?: string; confirm?: string };
};

export const IDLE: PriceState = { priced: null, error: null, echo: {} };
