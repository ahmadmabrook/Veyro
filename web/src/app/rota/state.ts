/**
 * What ADM-SCH-04's two writes can say back.
 *
 * **No imports.** `actions.ts` reaches `@/lib/api` and therefore `next/headers`, and a client
 * component that imports a module touching `next/headers` fails the build — the account page
 * learned that by making the *login* page answer 500. Decisions here, I/O there, which is the
 * same split the backend makes between `domain` and `service`.
 */
export type RotaState = {
  /** A message key, so a result is translated like everything else on these surfaces. */
  message: "rota.added" | "rota.withdrawn" | null;
  error:
    | "rota.writeRefused"
    | "rota.writeConflict"
    | "rota.writeInvalid"
    | "error.network"
    | "error.tooMany"
    | null;
  /** Which fields the reader left out, so the form can name them rather than guess. */
  missing: { on_date?: true; starts_at?: true; ends_at?: true; reason?: true };
  /** What they typed, so a refusal does not also empty the form. */
  echo: { on_date?: string; starts_at?: string; ends_at?: string; reason?: string };
};

export const IDLE: RotaState = { message: null, error: null, missing: {}, echo: {} };

/**
 * A wall-clock time the server will accept, checked before the request rather than after.
 *
 * The route parses `HH:MM` with `time.fromisoformat` and answers `a_window_time_is_hh_mm`;
 * saying so here costs nothing and keeps a typo from reading as "the product is broken".
 */
export function isClock(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
}

/** A calendar date, in the one format every date on these surfaces uses. */
export function isDay(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}
