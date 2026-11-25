import { api, correlationId } from "@/lib/api";

import type { ChangeQuote, PlanOption } from "@/lib/downgrade";

/**
 * ADM-MSH-06's two reads, kept apart from its decisions.
 *
 * `@/lib/api` reaches `next/headers`, so anything importing it is server-only — and the typed
 * confirmation this screen requires is parsed in a client component. `@/lib/downgrade` is the
 * module that component can import because this file is the one that cannot. The account page
 * and the cash screen both record what happens otherwise: a build error naming a chain of
 * `[Client Component Browser]` imports that never mentions `next/headers`.
 */

/** How many plans the picker offers. A gym sells a handful. */
export const PLAN_CHOICES = 24;

export async function readPlans(locale: string): Promise<PlanOption[]> {
  // `trials=exclude` is the default and is what makes this a *move* list: a product declaring
  // `trial_days` is what somebody converts from, so offering one would be a downgrade into a
  // seven-day clock.
  const body = await api<{ plans: PlanOption[] }>(
    `/memberships/plans?locale=${encodeURIComponent(locale)}&limit=${PLAN_CHOICES}`);
  return body.plans;
}

/**
 * What moving this member to that plan would cost and change.
 *
 * **Keyed on the variant, not on a successor agreement**, which is the whole reason the route
 * exists: drawing an agreement up is a financial write, and a tier-3 screen that wrote a
 * contract in order to tell somebody what it would cost has the order backwards. The canvas's
 * own instruction is that "the loss is stated before the saving".
 */
export function readPlanChangeQuote(
  membershipId: string, variantId: string,
): Promise<ChangeQuote> {
  // **The correlation id is required by the route and is not added for us.** `api` sets one
  // on a body it builds and on the gate's own query, and nothing else -- so a read whose
  // route takes `correlation_id: str` answers 422 without it. The sheet rendered its picker,
  // the quote came back null through the `catch`, and the consequence block simply did not
  // appear: a refusal that reaches a screen as an absence.
  return api<ChangeQuote>(
    `/memberships/${encodeURIComponent(membershipId)}/plan-change-quote`
    + `?to_variant_id=${encodeURIComponent(variantId)}`
    + `&correlation_id=${correlationId()}`);
}
