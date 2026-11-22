"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { isOverrideReason, overrideKey } from "@/lib/denial";

import { IDLE, type OverrideState } from "./state";

/**
 * FD-03's "Let in, flag it". Paragraph 1938's staff override, as its own decision.
 *
 * **Financial class, so this needs a stepped-up session** -- the freeze form's pattern, and
 * right: this is the one path that admits somebody the policy refused.
 *
 * **The reason is one of three and the screen says so.** `override` takes free text and
 * requires only that it is not blank; the canvas offers "renewing today · manager approved ·
 * resolving a dispute", and a written reason that is one of three is a reason somebody can
 * count later. The narrowing is checked here rather than trusted from the form, because a
 * select is a suggestion to anything that is not a browser.
 */
export async function overrideDenial(
  _previous: OverrideState, form: FormData,
): Promise<OverrideState> {
  const personId = String(form.get("person_id") ?? "");
  const pointId = String(form.get("point_id") ?? "");
  const decisionId = String(form.get("decision_id") ?? "");
  const reason = String(form.get("reason") ?? "");
  if (!isOverrideReason(reason)) return { ...IDLE, error: "denial.overrideRefused" };

  try {
    await api("/access/decisions/override", {
      method: "POST",
      body: {
        point_id: pointId,
        person_id: personId,
        reason,
        // The key is the refusal being answered. `overrideKey` says why, and is a
        // function so it can be tested: this one was wrong until a browser test's second
        // run was worked out on paper.
        idempotency_key: overrideKey(decisionId),
        correlation_id: correlationId(),
      },
    });
    revalidatePath(`/desk/denials/${personId}`);
    return { done: true, error: null };
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network" };
    }
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany" };
    }
    if (error instanceof ApiError && error.status === 403) {
      return { ...IDLE, error: "denial.overrideNeedsStepUp" };
    }
    return { ...IDLE, error: "denial.overrideRefused" };
  }
}
