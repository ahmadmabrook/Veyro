"use server";

import { ApiError, api, correlationId } from "@/lib/api";
import { worthChecking } from "@/lib/walk-in";
import type { TrialSteps } from "@/lib/walk-in-trial";

import { IDLE, type WalkInTrialState } from "./state";

type Started = {
  lead_id: string;
  membership_number?: string;
  trial_days?: number | null;
  ends_on?: string | null;
  steps: TrialSteps;
};

/**
 * FD-05 · WALK-IN TRIAL — "Start her trial now".
 *
 * **One write, which is the difference from ADM-CRM-04 and the reason this form has no
 * window to report.** That screen makes two HTTP writes and says so, because a person with no
 * lead is a real outcome nothing makes atomic from a browser. Here the four facts -- a person,
 * a lead, a signed agreement and the activation -- are one request, so the only partial state
 * is the one the *server* reports in `steps`, and a retry converges because every step keys on
 * the person (ADR-0010 D12).
 *
 * **The duplicate is refused by the server, not decided here.** MOD-014's
 * `AUTO_MERGE_THRESHOLD` is `None` because two siblings at one address with one family line is
 * the ordinary case, so `different_person` is the field that says a human looked at the match
 * -- the same acknowledgement ADM-MEM-10 and ADM-CRM-04 collect, sent on rather than kept as a
 * client-side decision, because this command is the one that refuses.
 *
 * **Three of the five permissions are financial class, so a 403 here is a step-up rather than
 * a denial**, and the two have different next steps: a reader told "that was refused" goes and
 * asks for a grant they already hold. The page offers the step-up on arrival, which is
 * ADM-MSH-03's pattern and what makes a form of this kind buildable at all.
 */
export async function startWalkInTrial(
  _previous: WalkInTrialState, form: FormData,
): Promise<WalkInTrialState> {
  const name = String(form.get("name") ?? "").trim();
  const phone = String(form.get("phone") ?? "").trim();
  const variant = String(form.get("variant_id") ?? "").trim();
  const acknowledged = String(form.get("different_person") ?? "") === "1";
  const chosen = String(form.get("use_person") ?? "").trim();
  const echo = { name, phone };

  const subject = chosen.length > 0
    ? { person_id: chosen }
    : { legal_name: name, phone };
  if (chosen.length === 0) {
    const missing: WalkInTrialState["missing"] = {};
    if (name.length === 0) missing.name = true;
    if (!worthChecking(phone)) missing.phone = true;
    if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };
  }

  try {
    const started = await api<Started>("/crm/walk-in-trial", {
      method: "POST",
      body: {
        ...subject,
        // **The canvas's own sentence as the timeline entry.** The command requires one and
        // the summary comes from the client because a sentence the service wrote would be the
        // first non-human prose in a column every other row of which a salesperson typed --
        // ADR-0010 D12. It is English here for the same reason every other stored prose in
        // this build is in whatever language it was written in: the column is a record of
        // what somebody said, not a label to be translated later.
        summary: "Walked in and started a trial at the front desk.",
        ...(acknowledged ? { different_person: true } : {}),
        ...(variant.length > 0 ? { variant_id: variant } : {}),
        correlation_id: correlationId(),
      },
    });
    return {
      ...IDLE,
      started: {
        leadId: String(started.lead_id),
        membershipNumber: String(started.membership_number ?? ""),
        trialDays: started.trial_days ?? null,
        endsOn: started.ends_on ?? null,
        steps: started.steps,
      },
    };
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), echo };
  }
}

function reasonFor(error: unknown): WalkInTrialState["error"] {
  if (!(error instanceof ApiError)) return "deskTrial.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  if (error.status === 403) return "deskTrial.needsStepUp";
  // **The three refusals a desk can act on, told apart by their codes.** A flat "that was
  // refused" would send a receptionist to retype the name for a duplicate they can confirm,
  // or to look for a field when the gym publishes two trials.
  if (error.reason === "this_number_already_has_a_record") return "deskTrial.duplicate";
  if (error.reason === "this_tenant_publishes_no_trial_plan") return "deskTrial.noPlan";
  if (error.reason === "name_the_trial_plan") return "deskTrial.pickPlan";
  return "deskTrial.refused";
}
