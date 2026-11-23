"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, isDay, type LeadState } from "./state";

/**
 * ADM-CRM-03's five writes: a touchpoint, a stage move, the ownership, the next action and
 * the interests.
 *
 * **Every MOD-027 permission is routine, which is why this screen has forms at all.** They
 * are `data_access` or `configuration` with no financial class, and the catalogue argues for
 * it: raising, claiming and writing up a lead is the ordinary work of a sales shift, and a
 * step-up on every logged phone call would make the pipeline wrong instead. Elsewhere in this
 * app a write form is absent because its permission is a stepped-up financial one and "a
 * button that answered 403 is worse than its absence"; none of these is.
 *
 * **Which ownership act it was is derived, not declared**, exactly as MOD-026's is: one route
 * takes one intent and the server decides from what the column held, so a caller cannot
 * report a release and perform a handover.
 *
 * **A refusal names which refusal it is.** A 409 is a state somebody else changed or a move
 * the pipeline does not admit, a 422 is what the reader typed or an identity with no person
 * record, a 403 is the permission and a 429 is a wait — four different next steps, and
 * "something went wrong" is none of them.
 */
async function act(
  run: () => Promise<LeadState>,
  echo: LeadState["echo"] = {},
): Promise<LeadState> {
  try {
    return await run();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.reason === "unreachable") return { ...IDLE, error: "error.network", echo };
    if (error.status === 429) return { ...IDLE, error: "error.tooMany", echo };
    // **The one 422 worth its own sentence.** `no_person_record_for_this_identity` is not a
    // malformed request: it is a reader who holds the permission and is nobody in this
    // organization, and the remedy is a link MOD-014 makes rather than anything they typed.
    if (error.reason === "no_person_record_for_this_identity") {
      return { ...IDLE, error: "lead.writeNobody", echo };
    }
    if (error.status === 409) return { ...IDLE, error: "lead.writeConflict", echo };
    if (error.status === 400 || error.status === 422) {
      return { ...IDLE, error: "lead.writeInvalid", echo };
    }
    return { ...IDLE, error: "lead.writeRefused", echo };
  }
}

/** ADM-CRM-03's TOUCHPOINTS list, written to. The kind decides which stage it reaches. */
export async function recordTouchpoint(
  _previous: LeadState,
  form: FormData,
): Promise<LeadState> {
  const leadId = String(form.get("lead_id") ?? "");
  const kind = String(form.get("kind") ?? "");
  const summary = String(form.get("summary") ?? "").trim();
  const echo = { kind, summary };
  if (summary === "") return { ...IDLE, missing: { summary: true }, echo };
  return act(async () => {
    await api(`/crm/leads/${encodeURIComponent(leadId)}/touchpoints`, {
      method: "POST",
      body: { kind, summary, correlation_id: correlationId() },
    });
    revalidatePath(`/leads/${leadId}`);
    return { ...IDLE, message: "lead.doneTouched" };
  }, echo);
}

/** The explicit stage move, for what a conversation does not cover. Forward only. */
export async function moveStage(
  _previous: LeadState,
  form: FormData,
): Promise<LeadState> {
  const leadId = String(form.get("lead_id") ?? "");
  const toStage = String(form.get("to_stage") ?? "");
  return act(async () => {
    await api(`/crm/leads/${encodeURIComponent(leadId)}/stage`, {
      method: "POST",
      body: { to_stage: toStage, correlation_id: correlationId() },
    });
    revalidatePath(`/leads/${leadId}`);
    return { ...IDLE, message: "lead.doneStage" };
  });
}

/** Claim, hand over or release — one route, three acts, and the server names which. */
export async function assignLead(
  _previous: LeadState,
  form: FormData,
): Promise<LeadState> {
  const leadId = String(form.get("lead_id") ?? "");
  const release = String(form.get("release") ?? "") === "true";
  return act(async () => {
    const answer = await api<{ act: string }>(
      `/crm/leads/${encodeURIComponent(leadId)}/assign`,
      {
        method: "POST",
        body: release
          ? { release: true, correlation_id: correlationId() }
          : { to_self: true, correlation_id: correlationId() },
      });
    revalidatePath(`/leads/${leadId}`);
    // **The message is the act the server derived**, not the button that was pressed: taking
    // over and claiming are the same request and differ only by what the column held.
    return {
      ...IDLE,
      message: answer.act === "released" ? "lead.doneReleased"
        : answer.act === "handed_over" ? "lead.doneHandedOver"
        : "lead.doneAssigned",
    };
  });
}

/** ADM-CRM-02's NEXT ACTION column, set or cleared. Both halves or neither. */
export async function setNextAction(
  _previous: LeadState,
  form: FormData,
): Promise<LeadState> {
  const leadId = String(form.get("lead_id") ?? "");
  const clear = String(form.get("clear") ?? "") === "true";
  const action = String(form.get("next_action") ?? "").trim();
  const on = String(form.get("next_action_on") ?? "").trim();
  const echo = { action, on };
  if (!clear) {
    // **Both halves, checked here rather than after the request**: a date with no action is a
    // reminder about nothing and an action with no date is a note, which the constraint also
    // refuses -- and naming the missing field is what a 422 cannot do, because this app's
    // validation handler deliberately returns no field name.
    const missing: LeadState["missing"] = {};
    if (action === "") missing.action = true;
    if (!isDay(on)) missing.on = true;
    if (missing.action || missing.on) return { ...IDLE, missing, echo };
  }
  return act(async () => {
    await api(`/crm/leads/${encodeURIComponent(leadId)}/next-action`, {
      method: "POST",
      body: clear
        ? { correlation_id: correlationId() }
        : { next_action: action, next_action_on: on, correlation_id: correlationId() },
    });
    revalidatePath(`/leads/${leadId}`);
    return { ...IDLE, message: clear ? "lead.doneNextCleared" : "lead.doneNextAction" };
  }, echo);
}

/**
 * What a lead is interested in, added to.
 *
 * **The set only grows**, which is MOD-027's own recorded gap rather than this form's
 * restraint: there is no UPDATE and no DELETE grant on the table, so withdrawing one is the
 * slice that adds `lost`. The form says so rather than offering a tick that cannot be
 * untaken.
 */
export async function recordInterests(
  _previous: LeadState,
  form: FormData,
): Promise<LeadState> {
  const leadId = String(form.get("lead_id") ?? "");
  const interests = form.getAll("interest").map(String);
  if (interests.length === 0) return { ...IDLE, missing: { interests: true } };
  return act(async () => {
    await api(`/crm/leads/${encodeURIComponent(leadId)}/interests`, {
      method: "POST",
      body: { interests, correlation_id: correlationId() },
    });
    revalidatePath(`/leads/${leadId}`);
    return { ...IDLE, message: "lead.doneInterests" };
  });
}
