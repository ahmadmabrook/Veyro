/**
 * What ADM-TSK-01's bulk completion can say back.
 *
 * **No imports.** `actions.ts` reaches `@/lib/api` and therefore `next/headers`, and a client
 * component that imports a module touching `next/headers` fails the build — the account page
 * learned that by making the *login* page answer 500. Decisions here, I/O there, which is the
 * same split the backend makes between `domain` and `service`.
 */
export type BulkState = {
  /** How many were settled, so the result is a figure rather than a word. */
  done: number;
  /** How many were asked for, so a partial result can say which it was. */
  asked: number;
  error:
    | "tasks.bulkNone"
    | "tasks.bulkFailed"
    | "error.network"
    | "error.tooMany"
    | null;
  /** The ones that refused, with the reason each gave. Named, never summarised. */
  refused: { task_id: string; reason: string }[];
  /** Whether a reason was supplied, so a refusal does not also empty the field. */
  echo: { reason?: string };
  missing: { reason?: true };
};

export const IDLE: BulkState = {
  done: 0, asked: 0, error: null, refused: [], echo: {}, missing: {},
};
