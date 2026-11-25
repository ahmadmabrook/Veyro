"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, type DunningError, type DunningState } from "./state";

/** The bands, from the one place that states them: `collections.Policy`, through the read. */
const RETRY = { min: 1, max: 20 };
const GRACE = { min: 8, max: 180 };

/**
 * ADM-PAY-06 -- set the retry budget and the access grace. COM-03-R04.
 *
 * **The bands are checked here as well as in the form and again on the server.** A client
 * decides whether to enable a button and a server action is the thing that writes, so a submit
 * that arrived from a form rendered before JavaScript ran is bounded rather than trusted --
 * and the route's own body bounds both figures a third time, because a service is not safe
 * because its only caller happens to be.
 *
 * **Three permissions on the route, and the dunning half is financial class**, because the
 * figures decide when a member's access is recommended to be restricted. So an ordinary
 * password session cannot press this and the page offers the step-up first: ADM-MSH-03's
 * precedent, where the honest cost is one recovery code per twelve-hour window rather than one
 * per act.
 */
export async function writeDunningPolicy(
  _previous: DunningState, form: FormData,
): Promise<DunningState> {
  const retry = String(form.get("retry_attempts") ?? "").trim();
  const grace = String(form.get("access_grace_days") ?? "").trim();
  const echo = { retry, grace };

  const retryAttempts = whole(retry);
  const accessGraceDays = whole(grace);
  if (retryAttempts === null || accessGraceDays === null) {
    return { ...IDLE, error: "dunning.notAWholeNumber", echo };
  }
  if (retryAttempts < RETRY.min || retryAttempts > RETRY.max
      || accessGraceDays < GRACE.min || accessGraceDays > GRACE.max) {
    return { ...IDLE, error: "dunning.outOfBand", echo };
  }

  try {
    await api("/finance/dunning-policy", {
      method: "POST",
      body: {
        retry_attempts: retryAttempts,
        access_grace_days: accessGraceDays,
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/payments/dunning");
    return { ...IDLE, saved: { retryAttempts, accessGraceDays } };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), echo };
  }
}

/**
 * A whole number or nothing.
 *
 * `Number("")` is 0 and `Number("2.5")` is 2.5, so neither is a budget: a blank field and a
 * fraction are both "not a whole number", which is the one sentence a reader can act on.
 */
function whole(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function reasonFor(error: unknown): DunningError {
  if (!(error instanceof ApiError)) return "dunning.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) return "dunning.needsStepUp";
  return "dunning.refused";
}
