/**
 * What ADM-CC-06's five writes can say back.
 *
 * **No imports.** `actions.ts` reaches `@/lib/api` and therefore `next/headers`, and a client
 * component that imports a module touching `next/headers` fails the build — the account page
 * learned that by making the *login* page answer 500. Decisions here, I/O there, which is the
 * same split the backend makes between `domain` and `service`.
 */
export type SheetState = {
  message:
    | "case.doneAssigned" | "case.doneReleased" | "case.doneTakenOver"
    | "case.doneSnoozed" | "case.doneReturned" | "case.doneResolved"
    | null;
  error:
    | "case.writeRefused"
    | "case.writeConflict"
    | "case.writeInvalid"
    | "case.writeNobody"
    | "error.network"
    | "error.tooMany"
    | null;
  /** Which fields the reader left out, so the form names them rather than guessing. */
  missing: { until?: true; reason?: true };
  /** What they typed, so a refusal does not also empty the form. */
  echo: { until?: string; reason?: string };
};

export const IDLE: SheetState = { message: null, error: null, missing: {}, echo: {} };

/**
 * A calendar date the server will accept, checked before the request rather than after.
 *
 * The snooze takes an instant and the form offers a date, because "an exception cannot be
 * dismissed, only deferred with an account of why" is about a *day* somebody will look at it
 * again — a minute-precise return time is precision nobody has.
 */
export function isDay(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}
