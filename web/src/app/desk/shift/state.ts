/**
 * What FD-07's open can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`
 * and a client component that imports a module touching it fails the build -- the account
 * page's first version made the *login* page answer 500 that way.
 *
 * **There is no close state here.** ADM-PAY-09 already writes the close and FD-07's registry
 * line is the same act, so that form and its state are shared rather than written twice; what
 * this screen adds is the open, which the admin board has no notion of.
 */
export type ShiftError =
  | "deskShift.refused"
  | "deskShift.needsStepUp"
  | "deskShift.needsReason"
  | "deskShift.needsAccounts"
  | "deskShift.drawsNothing"
  | "deskShift.alreadyOpen"
  | "deskShift.invalid"
  | "error.network"
  | "error.tooMany";

export type Opened = {
  sessionId: string;
  wasHandover: boolean;
  /** What the ledger said was in the drawer, against the count that was made. */
  expectedMinor: number | null;
  varianceMinor: number | null;
  /** Set only where the difference opened a question somebody has to answer. */
  caseId: string | null;
  repeated: boolean;
};

export type ShiftState = {
  opened: Opened | null;
  error: ShiftError | null;
  /** Which field the reader left out or mistyped, so the form names it. */
  missing: { counted?: true; reason?: true };
  /** What they typed, so a refusal does not empty the figure they are holding. */
  echo: { counted?: string; reason?: string };
};

export const IDLE: ShiftState = {
  opened: null, error: null, missing: {}, echo: {},
};
