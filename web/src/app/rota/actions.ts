"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, isClock, isDay, type RotaState } from "./state";

/**
 * ADM-SCH-04's two writes, and the first in this app that are not a member acting on their
 * own account.
 *
 * **Both are the same permission, and it is routine.** `scheduling.availability.write` is
 * `configuration` with no financial class — AAL 1 — and the catalogue argues for that
 * deliberately: "a rota is edited by the people who run the floor, and refusing them a
 * step-up every time somebody books a day off would make the rota wrong instead." That is
 * why this is the one form in this app that is not blocked, where every `tenancy.*`,
 * `catalog.*` and `finance.*` write is a stepped-up financial permission and "a button that
 * answered 403 is worse than its absence".
 *
 * **And it is why the withdrawal had to be built before the form.** The table carried
 * `GRANT SELECT, INSERT` and nothing else, so a day off entered on the wrong date was
 * permanent — a routine permission whose every act is uncorrectable, which is MOD-013's "an
 * irreversible act must not be declarable on a routine permission" from the other side.
 * `0017` adds the withdrawal; this adds the button for both halves.
 *
 * **A refusal names which one it is.** A 409 is a state the reader can see and act on (the
 * window was already withdrawn by somebody else), a 422 is what they typed, and a 403 is the
 * permission — three different next steps, and "something went wrong" is none of them.
 */
async function act(run: () => Promise<RotaState>): Promise<RotaState> {
  try {
    return await run();
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network" };
    }
    // Temporary and the reader's to act on, which "something went wrong" is not.
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany" };
    }
    if (error instanceof ApiError && error.status === 409) {
      return { ...IDLE, error: "rota.writeConflict" };
    }
    if (error instanceof ApiError && (error.status === 400 || error.status === 422)) {
      return { ...IDLE, error: "rota.writeInvalid" };
    }
    return { ...IDLE, error: "rota.writeRefused" };
  }
}

/**
 * Write a dated absence, which is what the canvas's button means by an exception.
 *
 * **Dated and `time_off`, not a weekly pattern.** "Add an exception" is one day — the
 * canvas's own case is "he asked for Thursday afternoon off three weeks ago" — and a weekly
 * `working` row is the rota itself rather than an exception to it. Writing a rota pattern is
 * a different screen and the page says so.
 *
 * The reason is required by the schema (`window_kind <> 'time_off' OR reason ~
 * '[^[:space:]]'`) and it is the one free-text column in a rota, which is why the grid masks
 * it for anybody who could not have written it.
 */
export async function addException(
  _previous: RotaState,
  form: FormData,
): Promise<RotaState> {
  const resourceId = String(form.get("resource_id") ?? "");
  const onDate = String(form.get("on_date") ?? "").trim();
  const startsAt = String(form.get("starts_at") ?? "").trim();
  const endsAt = String(form.get("ends_at") ?? "").trim();
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { on_date: onDate, starts_at: startsAt, ends_at: endsAt, reason };

  // **Named, not guessed.** An empty field and a malformed one are different mistakes and a
  // form that reported both as "that was refused" makes the reader try the same thing again.
  const missing: RotaState["missing"] = {};
  if (!isDay(onDate)) missing.on_date = true;
  if (!isClock(startsAt)) missing.starts_at = true;
  if (!isClock(endsAt)) missing.ends_at = true;
  if (reason.length === 0) missing.reason = true;
  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };
  // The server refuses this too — "a window over midnight is two windows, because the day it
  // belongs to is otherwise unanswerable" — and saying so here costs one comparison.
  if (endsAt <= startsAt) {
    return { ...IDLE, missing: { ends_at: true }, echo };
  }

  return act(async () => {
    await api("/scheduling/availability", {
      method: "POST",
      body: {
        resource_id: resourceId, window_kind: "time_off",
        starts_at: startsAt, ends_at: endsAt, on_date: onDate, reason,
        correlation_id: correlationId(),
      },
    });
    revalidatePath("/rota");
    return { ...IDLE, message: "rota.added" };
  });
}

/**
 * Take one back.
 *
 * **A withdrawal, not a delete**, and the reason is required for the same purpose it is on
 * the window itself: "was this coach marked off on the fourteenth, and who said so" gets
 * asked precisely when somebody was turned away, and a deleted row answers nothing.
 */
export async function withdrawException(
  _previous: RotaState,
  form: FormData,
): Promise<RotaState> {
  const windowId = String(form.get("window_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  if (reason.length === 0) {
    return { ...IDLE, missing: { reason: true }, echo: { reason } };
  }
  return act(async () => {
    await api(`/scheduling/availability/${encodeURIComponent(windowId)}/withdraw`, {
      method: "POST",
      body: { reason, correlation_id: correlationId() },
    });
    revalidatePath("/rota");
    return { ...IDLE, message: "rota.withdrawn" };
  });
}
