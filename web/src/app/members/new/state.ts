/**
 * What ADM-MEM-10's create can say back.
 *
 * **One call now, not two.** The duplicate check and its answer moved to
 * `@/lib/contact-check`, because ADM-CRM-04 asks the same question before creating a lead and
 * a lead *is* a person -- so this holds the create's own state and nothing else.
 *
 * Types only, so the client component can import it: `@/lib/walk-in` imports nothing and this
 * imports only its type. The split the account page, the cash board and the freeze form all
 * record — decisions apart from I/O, because `@/lib/api` reaches `next/headers`.
 */
export type WalkInState = {
  /** The record that was created, so the page can offer to open it. */
  createdPersonId: string | null;
  error:
    | "walkIn.refused"
    | "walkIn.needsStepUp"
    | "error.network"
    | "error.tooMany"
    | null;
  missing: { name?: true; phone?: true };
  echo: { name?: string; phone?: string; email?: string; birthDate?: string };
};

export const IDLE: WalkInState = {
  createdPersonId: null, error: null, missing: {}, echo: {},
};
