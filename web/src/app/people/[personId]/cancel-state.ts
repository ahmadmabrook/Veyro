/**
 * What ADM-MSH-07's one write can say back.
 *
 * Types only, so a client component can import it — the rule the cash board, the account
 * page and the freeze form all record: the decisions live apart from the I/O, because
 * `@/lib/api` reaches `next/headers` and a client component importing it fails the whole
 * app's build.
 */
export type CancelState = {
  /** Set once the write has landed; the sentence is built from `recorded`. */
  message: "done" | null;
  /**
   * A refusal the screen could see for itself, or one only the server could.
   *
   * **There is no separate "the fee moved" value, and the absence is on purpose.** The
   * disclosure check refuses when the figure sent is not the figure recomputed, which is the
   * control working rather than a failure -- but it arrives as the same machine reason as any
   * other conflict, and telling the two apart would mean matching the server's prose. That is
   * MOD-016's "a control decided by matching words in prose is a control anybody can edit
   * away". Both have the same next step, so they have the same sentence. A declared value
   * nothing can write is this build's most repeated finding and it is not worth adding one
   * here to describe a distinction the reader cannot act on.
   */
  error: "cancel.refused" | "cancel.conflict" | "cancel.needsStepUp"
    | "error.network" | "error.tooMany" | null;
  missing: { reason?: true };
  echo: { reason?: string };
  /** What was actually recorded, so the confirmation states it rather than restating the form. */
  recorded: { accessEndsOn: string; feeMinor: number; currency: string } | null;
};

export const IDLE: CancelState = {
  message: null, error: null, missing: {}, echo: {}, recorded: null,
};
