"use server";

import { api } from "@/lib/api";
import type { PersonalSessionQuote } from "@/lib/personal-session";

/**
 * ADM-SCH-05's consequence panel, as the form asks it.
 *
 * **A server action rather than a route handler**, which is this app's pattern for a check a
 * client makes as fields change: `checkClass` for ADM-SCH-03's clash and `checkPhone` for the
 * three screens that look for a duplicate number. The session cookie is httpOnly, so page
 * JavaScript cannot carry a bearer token and a `fetch` from the browser would have nothing to
 * authenticate with.
 *
 * **`unknown` is not `ready`.** A quote the server could not be asked has not said the coach
 * is free nor that there is a credit to spend, and a form that treated silence as a clear
 * would offer a booking the command refuses. The caller renders the difference; nothing here
 * smooths it over -- `checkClass` records the same rule in the same words.
 */
export type QuoteAnswer =
  | { outcome: "quoted"; quote: PersonalSessionQuote }
  | { outcome: "unknown" };

export async function quotePersonalSession(ask: {
  coachResourceId: string;
  personId: string;
  locationId: string;
  startsAt: string;
  minutes: number;
}): Promise<QuoteAnswer> {
  if (!ask.coachResourceId || !ask.startsAt) return { outcome: "unknown" };
  const query = new URLSearchParams({
    coach_resource_id: ask.coachResourceId,
    person_id: ask.personId,
    location_id: ask.locationId,
    // **Encoded, which is why this is `URLSearchParams` and not a template string.** An
    // `isoformat()` offset is `+00:00`, and an unencoded `+` in a query string decodes to a
    // space -- so a hand-built URL answers 422. Every HTTP test for this route did.
    starts_at: ask.startsAt,
    minutes: String(ask.minutes),
  });
  try {
    return {
      outcome: "quoted",
      quote: await api<PersonalSessionQuote>(
        `/scheduling/personal-session-quote?${query}`),
    };
  } catch {
    // One answer rather than several: which failure it was is not actionable here, and the
    // *booking* reports its own refusal with the code that distinguishes the two states.
    return { outcome: "unknown" };
  }
}
