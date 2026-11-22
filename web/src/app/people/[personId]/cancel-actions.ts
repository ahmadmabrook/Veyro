"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";

import { IDLE, type CancelState } from "./cancel-state";

/**
 * Cancel a membership. ADM-MSH-07, and COM-01-R02's notice with COM-01-R06's disclosure.
 *
 * **The fee the reader was shown is sent back, and that is the whole control.**
 * `cancel_membership` recomputes the fee and refuses when the two differ: "without that, the
 * preview and the command are two independent calculations and the member can be shown one
 * figure and charged another -- which is the defect a disclosure requirement exists to
 * prevent." So this form is only as honest as the figure it echoes, which is why it sends
 * the one the panel rendered rather than one computed here.
 *
 * **And the version with it.** `expected_version` is the membership's own optimistic
 * concurrency token, which the quote returns for exactly this: two staff cancelling one
 * membership is the ordinary front-desk case, and last-write-wins on a lifecycle change
 * discards whichever finished first with no trace.
 *
 * **The idempotency key is derived from what the command takes, not from the membership
 * alone.** Four modules have now shipped a key compared on fewer fields than the command
 * reads, and the worst of them handed one member's booking to another; here a key that
 * ignored the fee would let a retry carrying a different acknowledged figure be answered
 * from the first call's row -- which is "a retry must be answered from what was recorded"
 * and is precisely what the service's own repeat path guards. The date is in it because a
 * cancellation decided today and one decided tomorrow are different acts.
 */
export async function cancelMembership(
  _previous: CancelState,
  form: FormData,
): Promise<CancelState> {
  const membershipId = String(form.get("membership_id") ?? "");
  const personId = String(form.get("person_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  const feeMinor = Number(form.get("fee_minor") ?? Number.NaN);
  const currency = String(form.get("currency") ?? "");
  const version = Number(form.get("version") ?? Number.NaN);
  const echo = { reason };

  if (reason.length === 0) return { ...IDLE, missing: { reason: true }, echo };
  // The fee and the version come from the panel rather than from the reader, so a value
  // that is not a number means the page rendered something it should not have. Refusing
  // here rather than sending it is the fail-closed direction: an unparseable fee would
  // reach the disclosure check as "no figure disclosed", which the module allows for a
  // staff-initiated cancellation and would quietly turn this screen into one.
  if (!Number.isInteger(feeMinor) || !Number.isInteger(version)) {
    return { ...IDLE, error: "cancel.conflict", echo };
  }

  try {
    const done = await api<{
      effective_on: string; fee_due_minor: number;
    }>(`/memberships/${encodeURIComponent(membershipId)}/cancel`, {
      method: "POST",
      body: {
        reason,
        acknowledged_fee_minor: feeMinor,
        expected_version: version,
        idempotency_key:
          `cancel-${membershipId}-${new Date().toISOString().slice(0, 10)}-${feeMinor}`,
        correlation_id: correlationId(),
      },
    });
    revalidatePath(`/people/${personId}`);
    return {
      ...IDLE,
      message: "done",
      recorded: {
        accessEndsOn: done.effective_on, feeMinor: done.fee_due_minor, currency,
      },
    };
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network", echo };
    }
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany", echo };
    }
    // **403 is the step-up, not a refusal to act** -- the freeze form's rule, and the reader
    // here has already read the whole consequence panel on the routine permission.
    if (error instanceof ApiError && error.status === 403) {
      return { ...IDLE, error: "cancel.needsStepUp", echo };
    }
    if (error instanceof ApiError && error.status === 409) {
      // **One sentence for both 409s, and deliberately not two.** A conflict here is either
      // the fee having moved under the reader -- a panel left open across midnight
      // re-prices, because the fee is computed from today -- or the membership having
      // changed under them. Telling those apart would mean reading the server's prose, and
      // MOD-016 shipped exactly that: four English words were the whole enforcement of a
      // usage limit, and a benign message containing one of them refused a legitimate
      // redemption. The machine reason is the same for both, and so is the next step: the
      // panel above is stale, so reload and look again. A distinction that does not change
      // what the reader does is not worth a control that can be edited away.
      return { ...IDLE, error: "cancel.conflict", echo };
    }
    return { ...IDLE, error: "cancel.refused", echo };
  }
}
