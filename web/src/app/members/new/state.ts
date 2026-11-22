import type { MatchResult } from "@/lib/walk-in";

/**
 * What ADM-MEM-10's two server calls can say back.
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

/**
 * What the detection call answers.
 *
 * **`unknown` is its own answer and not a `clear`.** A check the server could not be asked is
 * not a check that passed, and conflating the two turns a network blip into a silent
 * duplicate — "a control consulted once is a control with a window", in a surface. The form
 * holds the button for this exactly as it does for a match.
 */
export type DetectionAnswer =
  | { outcome: "match"; result: MatchResult }
  | { outcome: "clear" }
  | { outcome: "unknown" };
