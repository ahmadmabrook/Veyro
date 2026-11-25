"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { previewCancellation } from "@/lib/cancel-class-reads";
import {
  CANCELLATION_REASONS, missingFields,
  type CancellationDone, type CancellationReason, type Remedy,
} from "@/lib/cancel-class";

import { IDLE, type CancelClassState } from "./cancel-state";

function reasonOf(form: FormData): CancellationReason | null {
  const value = String(form.get("cancellation_reason") ?? "");
  return (CANCELLATION_REASONS as readonly string[]).includes(value)
    ? (value as CancellationReason)
    : null;
}

function remedyOf(form: FormData): Remedy | "" {
  const value = String(form.get("remedy") ?? "");
  return value === "move" || value === "credit" ? value : "";
}

/**
 * Re-read the consequence for the remedy now chosen. ADM-SCH-07, ADR-0016.
 *
 * **Every figure on the sheet is about one remedy and one destination**, so changing either
 * has to re-ask: "6 places free · 12 would need to choose another" is a statement about
 * Friday's class, and a panel left behind from the previous choice is a figure a manager would
 * act on. The answer carries what it was about, so a reply about an edited choice is simply
 * not the answer to the one on screen -- the shape `@/lib/walk-in` needed a ref to catch and
 * which `detectionFor` replaced with a derivation.
 *
 * **It writes nothing**, which the route's own response asserts: the preview takes no hold,
 * cancels nothing and grants nothing, so a manager can read the consequence of both remedies
 * before committing either.
 */
export async function previewCancelClass(
  _previous: CancelClassState,
  form: FormData,
): Promise<CancelClassState> {
  const sessionId = String(form.get("session_id") ?? "");
  const cancellationReason = reasonOf(form);
  const remedy = remedyOf(form);
  const toSessionId = String(form.get("to_session_id") ?? "");
  const echo = { reason: cancellationReason ?? "", remedy, toSessionId };

  const missing = missingFields(remedy, toSessionId);
  if (Object.keys(missing).length > 0 || cancellationReason === null) {
    return {
      ...IDLE, echo,
      missing: cancellationReason === null ? { ...missing, reason: true } : missing,
    };
  }
  try {
    const preview = await previewCancellation(sessionId, {
      cancellation_reason: cancellationReason,
      reason: cancellationReason,
      remedy: remedy as Remedy,
      to_session_id: remedy === "move" ? toSessionId : null,
      correlation_id: correlationId(),
    });
    return {
      ...IDLE, echo, preview,
      previewFor: { remedy, toSessionId },
    };
  } catch (error) {
    return { ...IDLE, echo, error: failure(error) };
  }
}

/**
 * Cancel the class and give its members what was chosen.
 *
 * **One request, because the server makes it one act** (ADR-0016 D2). There is nothing for
 * this form to sequence: the cancellation, the released bookings, the lapsed queue and the
 * remedy commit together, so a partial outcome is not among the things it has to report.
 *
 * **The reason is required and goes into the message**, which the canvas states on the field
 * itself -- "WHY · GOES INTO THE MESSAGE" -- so the select has no default and an unanswered
 * one is refused here rather than sent as `other`, which is a different thing a member is
 * told.
 */
export async function cancelClass(
  _previous: CancelClassState,
  form: FormData,
): Promise<CancelClassState> {
  const sessionId = String(form.get("session_id") ?? "");
  const cancellationReason = reasonOf(form);
  const remedy = remedyOf(form);
  const toSessionId = String(form.get("to_session_id") ?? "");
  const echo = { reason: cancellationReason ?? "", remedy, toSessionId };

  const missing = missingFields(remedy, toSessionId);
  if (Object.keys(missing).length > 0 || cancellationReason === null) {
    return {
      ...IDLE, echo,
      missing: cancellationReason === null ? { ...missing, reason: true } : missing,
    };
  }

  try {
    const done = await api<CancellationDone>(
      `/scheduling/sessions/${encodeURIComponent(sessionId)}/cancel-with-remedy`,
      {
        method: "POST",
        body: {
          cancellation_reason: cancellationReason,
          // **The declared reason is the reason**, which is what the canvas draws: one field,
          // "WHY · GOES INTO THE MESSAGE". MOD-019 requires a non-blank prose reason on the
          // change record, and a client composing one would put *one locale's* sentence into
          // a column both locales read -- ADR-0015's own finding about prose on the wire,
          // from the writing side. The code is locale-free, greppable, and renders beside
          // `change_kind` on the session page, which is already a code.
          reason: cancellationReason,
          remedy,
          to_session_id: remedy === "move" ? toSessionId : null,
          correlation_id: correlationId(),
        },
      });
    revalidatePath(`/schedule/${sessionId}`);
    return {
      ...IDLE, message: "done", echo,
      recorded: {
        released: done.released,
        waitlistLapsed: done.waitlist_lapsed,
        toNotify: done.to_notify,
        moved: done.moved.length,
        credited: done.credited.length,
        mustChoose: done.must_choose,
      },
    };
  } catch (error) {
    return { ...IDLE, echo, error: failure(error) };
  }
}

/**
 * Which sentence a refusal gets.
 *
 * **Two of the credit's refusals are their own value**, because their next steps differ and a
 * reader can act on both: declare a class credit, or say which of the two to use. The rest
 * share one sentence, which is ADM-MSH-07's reasoning -- a declared value a reader cannot act
 * on is this build's most repeated finding and not worth adding to describe a distinction
 * nobody can use.
 */
function failure(error: unknown): CancelClassState["error"] {
  if (!(error instanceof ApiError)) return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) return "cancelClass.needsStepUp";
  if (error.status === 409) {
    // **A machine code, not prose.** MOD-016's finding is about a control decided by
    // matching *English words* in a sentence -- `ApiError.reason` is the backend's own
    // machine-readable reason and these two are stable strings a backend test pins. The
    // two-credits code carries the keys after it, so the comparison is a prefix; and a code
    // that moved falls back to the generic conflict sentence, which is a safe degradation
    // rather than a control that stops biting.
    if (error.reason.startsWith("this_tenant_has_declared_no_class_credit")) {
      return "cancelClass.noCredit";
    }
    if (error.reason.startsWith("this_tenant_has_more_than_one_class_credit")) {
      return "cancelClass.twoCredits";
    }
    return "cancelClass.conflict";
  }
  if (error.status === 422) return "cancelClass.refused";
  return "error.network";
}
