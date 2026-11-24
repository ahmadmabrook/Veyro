/**
 * What ADM-PAY-09's one write can say back.
 *
 * **No imports**, for the reason `account/state.ts` records: `actions.ts` reaches
 * `@/lib/api` and therefore `next/headers`, and a client component that imports a module
 * touching `next/headers` fails the build — which is how the *login* page once started
 * answering 500. Decisions here, I/O there.
 */
export type CashState = {
  message: "cash.closed" | null;
  error:
    | "cash.refused"
    | "cash.conflict"
    | "cash.invalid"
    | "cash.needsSuspense"
    | "error.network"
    | "error.tooMany"
    | null;
  /** Which field the reader left out or mistyped, so the form names it. */
  missing: { counted?: true; reason?: true };
  /** What they typed, so a refusal does not also empty the drawer count. */
  echo: { counted?: string; reason?: string; note?: string };
};

export const IDLE: CashState = { message: null, error: null, missing: {}, echo: {} };
