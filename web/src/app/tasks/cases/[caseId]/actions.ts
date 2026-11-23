"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, isDay, type SheetState } from "./state";

/**
 * ADM-CC-06's five writes — assign, release, take over, snooze and return to the queue — plus
 * the resolution.
 *
 * **Every one of them is routine, which is why this screen has forms at all.** Every MOD-026
 * permission is `data_access` or `configuration` with no financial class, and the catalogue
 * argues for it: "Raising, assigning and settling a task is the ordinary work of a shift."
 * Elsewhere in this app a write form is absent because its permission is a stepped-up
 * financial one and "a button that answered 403 is worse than its absence"; none of these is.
 *
 * **Which assignment act it was is derived, not declared.** One route takes one field and the
 * server decides from what the column held — so a caller cannot report a release and perform
 * a handover. `to_self` is the flag for "me", because a browser has no person id for its own
 * reader: a session carries an `identity_id` and the link to a person is MOD-014's.
 *
 * **A refusal names which refusal it is.** A 409 is a state somebody else changed, a 422 is
 * what the reader typed or an identity with no person record, a 403 is the permission and a
 * 429 is a wait — four different next steps, and "something went wrong" is none of them.
 */
async function act(
  run: () => Promise<SheetState>,
  echo: SheetState["echo"] = {},
): Promise<SheetState> {
  try {
    return await run();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.reason === "unreachable") return { ...IDLE, error: "error.network", echo };
    if (error.status === 429) return { ...IDLE, error: "error.tooMany", echo };
    if (error.status === 409) return { ...IDLE, error: "case.writeConflict", echo };
    // **The one 422 worth its own sentence.** `no_person_record_for_this_identity` is not a
    // malformed request: it is a reader who holds the permission and is nobody in this
    // organization, and the remedy is a link MOD-014 makes rather than anything they typed.
    if (error.reason === "no_person_record_for_this_identity") {
      return { ...IDLE, error: "case.writeNobody", echo };
    }
    if (error.status === 400 || error.status === 422) {
      return { ...IDLE, error: "case.writeInvalid", echo };
    }
    return { ...IDLE, error: "case.writeRefused", echo };
  }
}

/** "Assign to me", "Take over" and "Release" — one route, three acts, derived. */
export async function assign(
  _previous: SheetState,
  form: FormData,
): Promise<SheetState> {
  const caseId = String(form.get("case_id") ?? "");
  const release = String(form.get("release") ?? "") === "true";
  return act(async () => {
    const answer = await api<{ act: string }>(
      `/tasks/cases/${encodeURIComponent(caseId)}/assign`,
      {
        method: "POST",
        body: release
          ? { assignee_person_id: null, correlation_id: correlationId() }
          : { to_self: true, correlation_id: correlationId() },
      });
    revalidatePath(`/tasks/cases/${caseId}`);
    // **The message is the act the server derived**, not the button that was pressed: taking
    // over and assigning are the same request and differ only by what the column held.
    return {
      ...IDLE,
      message: answer.act === "released" ? "case.doneReleased"
        : answer.act === "handed_over" ? "case.doneTakenOver"
        : "case.doneAssigned",
    };
  });
}

/**
 * Defer it, with a reason and a return date.
 *
 * Both are required by the body *and* by the schema, because "an exception cannot be
 * dismissed, only deferred with an account of why" — and a control stated in one layer only
 * is a control the other layer can be wrong about.
 */
export async function snooze(
  _previous: SheetState,
  form: FormData,
): Promise<SheetState> {
  const caseId = String(form.get("case_id") ?? "");
  const until = String(form.get("until") ?? "").trim();
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { until, reason };

  const missing: SheetState["missing"] = {};
  if (!isDay(until)) missing.until = true;
  if (reason.length === 0) missing.reason = true;
  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };

  return act(async () => {
    await api(`/tasks/cases/${encodeURIComponent(caseId)}/snooze`, {
      method: "POST",
      body: {
        // Start of that day in UTC: the form offers a date because a minute-precise return
        // time is precision nobody has, and the bound the schema applies is to the span.
        snoozed_until: `${until}T00:00:00Z`,
        reason,
        correlation_id: correlationId(),
      },
    });
    revalidatePath(`/tasks/cases/${caseId}`);
    return { ...IDLE, message: "case.doneSnoozed" };
  }, echo);
}

/**
 * Bring it back early — the remedy the routine deferral needs.
 *
 * A routine permission whose every act is uncorrectable is MOD-013's "an irreversible act
 * must not be declarable on a routine permission" from the other side: a return date typed as
 * next year would otherwise hide an exception for eleven months with nothing able to undo it.
 */
export async function returnToQueue(
  _previous: SheetState,
  form: FormData,
): Promise<SheetState> {
  const caseId = String(form.get("case_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { reason };
  if (reason.length === 0) return { ...IDLE, missing: { reason: true }, echo };
  return act(async () => {
    await api(`/tasks/cases/${encodeURIComponent(caseId)}/return`, {
      method: "POST",
      body: { reason, correlation_id: correlationId() },
    });
    revalidatePath(`/tasks/cases/${caseId}`);
    return { ...IDLE, message: "case.doneReturned" };
  }, echo);
}

/**
 * Resolve it.
 *
 * **Forward only, and this build offers no undo.** The canvas puts a 30-second undo on this
 * and `tsk_cases` is one-way by trigger, so there is nothing to undo with — which is also
 * what makes ADM-CC-07 a record rather than a state. The screen says so above the button
 * rather than after it.
 */
export async function resolve(
  _previous: SheetState,
  form: FormData,
): Promise<SheetState> {
  const caseId = String(form.get("case_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  const echo = { reason };
  if (reason.length === 0) return { ...IDLE, missing: { reason: true }, echo };
  return act(async () => {
    await api(`/tasks/cases/${encodeURIComponent(caseId)}/settle`, {
      method: "POST",
      body: { target: "resolved", resolution_reason: reason,
              correlation_id: correlationId() },
    });
    revalidatePath(`/tasks/cases/${caseId}`);
    revalidatePath("/tasks/resolved");
    return { ...IDLE, message: "case.doneResolved" };
  }, echo);
}
