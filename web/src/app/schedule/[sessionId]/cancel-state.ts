/**
 * What ADM-SCH-07's sheet can say back.
 *
 * Types only, so the client component can import it -- the rule the cash board, the account
 * page and three other forms all record: the decisions live apart from the I/O, because
 * `@/lib/api` reaches `next/headers` and a client component importing it fails the whole
 * app's build. This app has three recorded instances, the last through a *mixed* module whose
 * exports were pure and whose top-level import was not.
 */
import type { CancellationPreview, NotMoved, Remedy } from "@/lib/cancel-class";

export type CancelClassState = {
  /** Set once the class has been cancelled; the sentence is built from `recorded`. */
  message: "done" | null;
  /**
   * A refusal the sheet could see for itself, or one only the server could.
   *
   * `cancelClass.noCredit` and `cancelClass.twoCredits` are their own values because the
   * remedy is unavailable until a tenant declares a class credit, and the next step differs:
   * one is "declare one", the other is "there are two, say which". Every other conflict --
   * the class already cancelled by somebody else, a destination that is not scheduled -- has
   * the same next step and so has one sentence, which is ADM-MSH-07's own reasoning about not
   * declaring a value a reader cannot act on.
   */
  error: "cancelClass.refused" | "cancelClass.conflict" | "cancelClass.noCredit"
    | "cancelClass.twoCredits" | "cancelClass.needsStepUp"
    | "error.network" | "error.tooMany" | null;
  missing: { remedy?: true; destination?: true; reason?: true };
  echo: { reason?: string; remedy?: Remedy | ""; toSessionId?: string };
  /**
   * The server's own figures for the chosen remedy, or null before one is chosen.
   *
   * **Re-read whenever the remedy or the destination changes**, because every figure on the
   * sheet depends on both: "6 places free · 12 would need to choose another" is about one
   * destination, and the credit's window is about the policy the tenant declared. A stale
   * panel beside a changed choice is the race `@/lib/walk-in` records -- an answer carrying
   * the value it was about is the shape that cannot land wrong.
   */
  preview: CancellationPreview | null;
  /** What the preview was asked about, so a reply about an edited choice is simply not it. */
  previewFor: { remedy: Remedy | ""; toSessionId: string } | null;
  /** What was actually cancelled, so the confirmation states it rather than the form. */
  recorded: {
    released: number;
    waitlistLapsed: number;
    toNotify: number;
    moved: number;
    credited: number;
    mustChoose: NotMoved[];
  } | null;
};

export const IDLE: CancelClassState = {
  message: null, error: null, missing: {}, echo: {},
  preview: null, previewFor: null, recorded: null,
};
