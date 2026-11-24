/**
 * What ADM-CRM-03's five writes can say back.
 *
 * **No imports.** `actions.ts` reaches `@/lib/api` and therefore `next/headers`, and a client
 * component that imports a module touching `next/headers` fails the build — the account page
 * learned that by making the *login* page answer 500. Decisions here, I/O there, which is the
 * same split the backend makes between `domain` and `service`.
 */
export type LeadState = {
  message:
    | "lead.doneTouched" | "lead.doneStage" | "lead.doneAssigned" | "lead.doneReleased"
    | "lead.doneHandedOver" | "lead.doneNextAction" | "lead.doneNextCleared"
    | "lead.doneInterests"
    // ADM-CRM-07's three.
    | "lead.doneLost" | "lead.doneReopen" | "lost.withdrawn"
    | null;
  error:
    | "lead.writeRefused"
    | "lead.writeConflict"
    | "lead.writeInvalid"
    | "lead.writeNobody"
    | "error.network"
    | "error.tooMany"
    // **A reason is required and the server says which field.** `aria-required` announces it
    // without refusing the submit, so this is the sentence a reader acts on -- the branch
    // ADM-MEM-10's native `required` made unreachable.
    | "lost.needsAReason"
    | null;
  /** Which fields the reader left out, so the form names them rather than guessing. */
  missing: { summary?: true; action?: true; on?: true; interests?: true };
  /** What they typed, so a refusal does not also empty the form. */
  echo: { summary?: string; kind?: string; action?: string; on?: string };
};

export const IDLE: LeadState = { message: null, error: null, missing: {}, echo: {} };

/**
 * A calendar date the server will accept, checked before the request rather than after.
 *
 * The next action is a day somebody will do something on, which is what ADM-CRM-02's column
 * holds; a minute-precise one is precision nobody has.
 */
export function isDay(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}
