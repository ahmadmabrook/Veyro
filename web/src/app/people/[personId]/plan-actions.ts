"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, correlationId } from "@/lib/api";
import { confirmsPlan } from "@/lib/downgrade";

import { IDLE, type PlanMoveError, type PlanMoveState } from "./plan-state";

/**
 * ADM-MSH-06 and ADM-MSH-05 — move a member to another plan. COM-01-R04.
 *
 * **Two writes, because the command needs an agreement and there is no way round it.**
 * `change_membership_plan` signs the successor itself — "the command is the signer, and that
 * is what makes it one act" — but the successor has to *exist*, and drawing one up is its own
 * route. So this action draws up the agreement at the quoted figure and then changes the plan,
 * and the state says which step it reached: a reader told only "that was refused" after the
 * agreement landed would try again and be refused for a fork.
 *
 * **The confirmation is re-checked here.** The client decides whether to enable a button and a
 * server action is the thing that writes, so a submit that arrived without the typed plan name
 * is refused rather than trusted — ADM-MSH-09's rule, and the reason a control only the
 * browser enforces is not one.
 *
 * **The figure is the quote's, not the form's.** MOD-017's review found an agreement citing a
 * receipt for 45.00 and recording 4.50; the rule out of it is that a cited authority is the
 * authority or it is decoration beside the figure. So the amount comes back from
 * `plan-change-quote` in this request rather than riding on a hidden input a client could
 * edit.
 */
export async function movePlan(
  _previous: PlanMoveState, form: FormData,
): Promise<PlanMoveState> {
  const membershipId = String(form.get("membership_id") ?? "");
  const personId = String(form.get("person_id") ?? "");
  const termsId = String(form.get("membership_terms_id") ?? "");
  const variantId = String(form.get("to_variant_id") ?? "");
  const planName = String(form.get("plan_name") ?? "");
  const confirm = String(form.get("confirm") ?? "").trim();
  const echo = { confirm };

  if (!confirmsPlan(confirm, planName)) {
    return { ...IDLE, error: "downgrade.confirmMismatch", echo };
  }

  try {
    // **Quoted again, in this request.** The figure the member was shown may be minutes old
    // and a price version could have superseded in between -- and the agreement has to carry
    // what is true now, because `create_agreement` takes its figures from the resolution it
    // cites and a stale one is the mismatch that review found.
    const quote = await api<{
      to_amount_minor: number; currency: string; effective_on: string | null;
      may_change: boolean;
    }>(`/memberships/${encodeURIComponent(membershipId)}/plan-change-quote`
      + `?to_variant_id=${encodeURIComponent(variantId)}`);
    if (!quote.may_change || quote.effective_on === null) {
      return { ...IDLE, error: "downgrade.refused", echo };
    }

    const agreement = await api<{ agreement_id: string }>("/memberships/agreements", {
      method: "POST",
      body: {
        person_id: personId,
        membership_terms_id: termsId,
        variant_id: variantId,
        amount_minor: quote.to_amount_minor,
        currency: quote.currency,
        // **The successor starts the day the change takes effect**, which
        // `change_membership_plan` refuses the pair of when they disagree: the minimum term
        // is computed from `starts_on`, so a downgrade agreement starting today while the
        // change lands at the next renewal would hold the member to a term that began
        // before their plan did.
        starts_on: quote.effective_on,
        correlation_id: correlationId(),
      },
    });

    const done = await api<{ change_id: string; kind: string; effective_on: string }>(
      `/memberships/${encodeURIComponent(membershipId)}/plan-change`, {
        method: "POST",
        body: {
          to_agreement_id: agreement.agreement_id,
          reason: `moved to ${planName}`,
          signature_kind: "click_through",
          signature_evidence_ref:
            `veyro://plan-change/${membershipId}/${agreement.agreement_id}`,
          idempotency_key: `plan-${membershipId}-${agreement.agreement_id}`,
          correlation_id: correlationId(),
        },
      });
    revalidatePath(`/people/${personId}`);
    return {
      ...IDLE,
      moved: {
        changeId: String(done.change_id), kind: String(done.kind),
        effectiveOn: String(done.effective_on), planName,
      },
    };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), echo };
  }
}

function reasonFor(error: unknown): PlanMoveError {
  if (!(error instanceof ApiError)) return "downgrade.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) return "downgrade.needsWrite";
  return "downgrade.refused";
}
