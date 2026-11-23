/**
 * What ADM-CRM-04's create can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`,
 * and a client component that imports a module touching it fails the build — the account
 * page's first version made the *login* page answer 500 that way, and the cash board's parse
 * did it again.
 */
export type NewLeadState = {
  /** The lead that was opened, so the page can offer to open it. */
  createdLeadId: string | null;
  /**
   * Whether that lead already existed.
   *
   * **The canvas's own sentence, reported rather than smoothed over**: "if this number
   * already existed, that record would open instead of a second one being created". The
   * server returns `existing` because `crm_leads_one_per_person` is the control, and a form
   * that said "the lead is open" for a record somebody else opened last week would be telling
   * a desk they did something they did not do.
   */
  openedExisting: boolean;
  /**
   * The person that was created when the lead was not.
   *
   * **Two commands, so there is a window, and the form says what is in it rather than
   * reporting a flat failure.** A person with no lead is a real state: `POST /people` and
   * `POST /crm/leads` are separate writes and nothing makes them atomic from a browser. A
   * reader told only "that was refused" would type the name again and be stopped by their own
   * duplicate check, which is the worst of the three possible answers.
   */
  orphanedPersonId: string | null;
  error:
    | "newLead.refused"
    | "newLead.needsStepUp"
    | "newLead.personOnly"
    | "error.network"
    | "error.tooMany"
    | null;
  missing: { name?: true; phone?: true };
  echo: { name?: string; phone?: string; source?: string; interests?: string[] };
};

export const IDLE: NewLeadState = {
  createdLeadId: null, openedExisting: false, orphanedPersonId: null, error: null,
  missing: {}, echo: {},
};
