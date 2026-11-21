import type { FreezeRefusal } from "@/lib/freeze";

/**
 * What ADM-MSH-03's one write can say back.
 *
 * Types only, so a client component can import it: `@/lib/freeze` imports nothing and this
 * imports only its type. The rule the cash board and the account page both record — the
 * decisions live apart from the I/O, because `@/lib/api` reaches `next/headers` and a client
 * component importing it fails the whole app's build.
 */
export type FreezeState = {
  message: "freeze.done" | null;
  /**
   * A refusal this screen could see for itself, or one only the server could.
   *
   * The first kind is named by `refusalFor` and is already on screen before anybody
   * submits; this carries the second — the server refused for a reason the form could not
   * have known, which is a different sentence and a different next step.
   */
  error: FreezeRefusal | "freeze.refused" | "freeze.conflict" | "freeze.needsStepUp"
    | "error.network" | "error.tooMany" | null;
  missing: { from?: true; until?: true; reason?: true };
  echo: { from?: string; until?: string; reason?: string };
};

export const IDLE: FreezeState = { message: null, error: null, missing: {}, echo: {} };
