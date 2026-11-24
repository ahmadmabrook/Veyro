"use server";

import { ApiError, api, correlationId } from "@/lib/api";
import { codeFor } from "@/lib/new-class";

import { IDLE, type ClassCreated, type NewClassState } from "./state";

/**
 * ADM-SCH-03 · CREATE A CLASS — "Create · 2 classes a week".
 *
 * **Three writes, in this order, and the order is MOD-019's rather than this form's.**
 * Drafting a template, publishing it and generating its sessions are three acts with three
 * permissions, because "a draft affects nobody and a publication is what members plan their
 * week around" -- so the button does all three and the state says how far it got. A draft
 * nobody published is a real state and a recoverable one; a published template with no
 * sessions is the same.
 *
 * **Generating over a clash costs the override permission and a written reason**, which is
 * paragraph 1842's Critical Control: "resource conflicts cannot be overridden without
 * permission and reason". The canvas's "Keep Omar anyway" is the button that leads to the
 * reason, so the reason is collected rather than derived -- a sentence this action wrote
 * would be the first non-human prose in a column an operator is accountable for.
 *
 * **The code and the name are derived.** The canvas draws neither, this build has no template
 * numbering scheme, and asking a manager to invent one would be asking them to do the
 * product's job -- FD-05's membership handle and MOD-026's case number, for the third time.
 * The display name is the class format's own, which is what the calendar shows.
 */
export async function createClass(
  _previous: NewClassState, form: FormData,
): Promise<NewClassState> {
  const locationId = String(form.get("location_id") ?? "").trim();
  const serviceId = String(form.get("service_id") ?? "").trim();
  const roomId = String(form.get("room_id") ?? "").trim();
  const staffId = String(form.get("staff_id") ?? "").trim();
  const displayName = String(form.get("display_name") ?? "").trim();
  const localTime = String(form.get("local_time") ?? "").trim();
  const startsOn = String(form.get("starts_on") ?? "").trim();
  const until = String(form.get("until") ?? "").trim();
  const weekdays = form.getAll("weekday").map((d) => Number(d));
  const capacity = Number(form.get("capacity") ?? 0);
  const duration = Number(form.get("duration_minutes") ?? 60);
  const waitlist = Number(form.get("waitlist_capacity") ?? 0);
  const equipment = Number(form.get("equipment") ?? 0);
  const overrideReason = String(form.get("override_reason") ?? "").trim();

  const rule = {
    frequency: "weekly", local_time: localTime, duration_minutes: duration,
    starts_on: startsOn, until, weekdays,
  };
  const requirements: { kind: string; quantity: number; resource_id?: string }[] = [
    { kind: "service", quantity: 1, resource_id: serviceId },
    { kind: "room", quantity: 1, resource_id: roomId },
    { kind: "staff", quantity: 1, resource_id: staffId },
  ];
  // **The equipment requirement is the capacity**, which is the canvas's own arithmetic read
  // the other way: "Studio 2 holds 20 bikes. Capacity cannot exceed the room" is a statement
  // that a class of twenty takes twenty bikes. Written only where the reader said the class
  // needs equipment at all, because a yoga class takes a room and nothing else.
  if (equipment > 0) requirements.push({ kind: "equipment", quantity: capacity });

  let template: ClassCreated;
  try {
    const drafted = await api<{ template_id: string }>("/scheduling/templates", {
      method: "POST",
      body: {
        template_code: codeFor(crypto.randomUUID()),
        display_name: displayName,
        service_resource_id: serviceId,
        location_id: locationId,
        rule, policy: {
          capacity, setup_minutes: 0, cleanup_minutes: 0,
          waitlist_capacity: waitlist,
        },
        requirements, restrictions: [],
        correlation_id: correlationId(),
      },
    });
    template = {
      templateId: String(drafted.template_id), reached: "drafted", sessions: 0,
      overridden: false,
    };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error) };
  }

  try {
    await api(`/scheduling/templates/${template.templateId}/publish`, {
      method: "POST", body: { correlation_id: correlationId() },
    });
    template = { ...template, reached: "published" };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), stoppedAt: template };
  }

  try {
    const generated = await api<{ created: number }>(
      `/scheduling/templates/${template.templateId}/sessions`, {
        method: "POST",
        body: {
          ...(overrideReason.length > 0 ? { override_reason: overrideReason } : {}),
          correlation_id: correlationId(),
        },
      });
    return {
      ...IDLE,
      created: {
        ...template, reached: "generated", sessions: Number(generated.created),
        overridden: overrideReason.length > 0,
      },
    };
  } catch (error) {
    // **A 409 here is the clash refusing, which is the one failure with its own remedy.**
    // `generate_sessions` refuses an occurrence it cannot place unless a reason was sent, so
    // a reader who created the class without one is told to say why rather than told it was
    // refused -- the template is published and waiting, which `stoppedAt` carries.
    if (error instanceof ApiError && error.status === 409) {
      return { ...IDLE, error: "newClass.needsOverride", stoppedAt: template };
    }
    return { ...IDLE, error: reasonFor(error), stoppedAt: template };
  }
}

function reasonFor(error: unknown): NewClassState["error"] {
  if (!(error instanceof ApiError)) return "newClass.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  // 403 is the step-up rather than a refusal to act, and the two have different next steps.
  if (error.status === 403) return "newClass.needsStepUp";
  return "newClass.refused";
}
