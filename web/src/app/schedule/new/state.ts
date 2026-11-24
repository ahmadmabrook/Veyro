/**
 * What ADM-SCH-03's create can say back.
 *
 * **Types only, so the client component can import it.** `@/lib/api` reaches `next/headers`.
 *
 * **Three writes, so there are three windows, and the state names which one it is in.**
 * Drafting, publishing and generating are three acts with three permissions -- MOD-019's own
 * division, because "a draft affects nobody and a publication is what members plan their week
 * around" -- and nothing makes three HTTP writes atomic from a browser. A reader told only
 * "that was refused" after the draft landed would fill the form in again and be refused for a
 * duplicate code; told which step stopped, they can carry on from it.
 */
export type ClassCreated = {
  templateId: string;
  /** How far it got: a draft nobody published is a real and recoverable state. */
  reached: "drafted" | "published" | "generated";
  sessions: number;
  overridden: boolean;
};

export type NewClassState = {
  created: ClassCreated | null;
  error:
    | "newClass.refused"
    | "newClass.needsStepUp"
    | "newClass.needsOverride"
    | "error.network"
    | "error.tooMany"
    | null;
  /** The template the failed attempt left behind, so the reader can carry on from it. */
  stoppedAt: ClassCreated | null;
};

export const IDLE: NewClassState = { created: null, error: null, stoppedAt: null };
