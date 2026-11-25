import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-MSH-06 — "Downgrade · Tier 3", and the half of its canvas this build could not draw.
 *
 * The canvas, verbatim:
 *
 * > **Dana · Club+ to Club** — She loses: Access to Abdoun and Sweifieh · 2 monthly PT
 * > sessions · her 4 unused PT credits expire on 1 Sep. Takes effect **1 September**, not
 * > today — she has paid for August at the higher rate and keeps it. New monthly: **JOD
 * > 55.00**. *[Use the credits first] [Downgrade from 1 Sep]*
 * >
 * > The loss is stated before the saving, and the credit expiry is the line that matters — a
 * > member who discovers it afterwards has been quietly charged for something they never got.
 *
 * **Three facts, and the build had one of them until ADR-0013.** What a plan grants had no
 * table at all: `mem_entitlement_policies` had a consumer and no producer, so activating a
 * membership granted nothing and `change_membership_plan` said in its own response that it
 * could not know what the plan being left gave.
 *
 * **The disclosure comes before any write**, which is why the preview is keyed on a *variant*
 * rather than on a successor agreement: drawing one up is a financial write, and a tier-3
 * screen that wrote a contract in order to tell somebody what it would cost has the order
 * backwards.
 */

/** One plan this member could move to, as the picker sees it. */
export type PlanOption = {
  variant_id: string;
  membership_terms_id: string;
  product_name: string | null;
  product_key: string;
  display_name: string;
  billing_period: string;
  is_a_trial_product: boolean;
};

export type Right = {
  policy_key: string;
  display_name: string;
  entitlement_type: string;
  is_counted: boolean;
  quantity: number | null;
  brand_id: string | null;
  location_id: string | null;
};

export type Holding = {
  grant_id: string;
  policy_key: string;
  display_name: string;
  is_counted: boolean;
  remaining: number | null;
  held: number | null;
  written_off_on_the_change: number | null;
  valid_to: string | null;
};

export type Move = {
  lost: Right[];
  kept: Right[];
  gained: Right[];
  requantified: (Right & { from_quantity: number | null; to_quantity: number | null })[];
  still_holding_from_the_plan_being_left: Holding[];
  the_leaving_plan_declares_rights: boolean;
  the_joining_plan_declares_rights: boolean;
};

export type ChangeQuote = {
  membership_id: string;
  from_variant_id: string;
  to_variant_id: string;
  /** `null` where the move is refused, because there is no change to have a kind. */
  kind: "upgrade" | "downgrade" | null;
  effective_on: string | null;
  takes_effect_immediately: boolean;
  from_amount_minor: number;
  to_amount_minor: number;
  due_minor: number | null;
  /** The two halves kept apart, which is MOD-018's reason: a total that has lost its
   * components cannot be reconciled against anything. */
  credit_minor: number | null;
  charge_minor: number | null;
  currency: string;
  billing_period: string;
  may_change: boolean;
  refused_because: string | null;
  entitlements: Move;
  nothing_is_written_by_this_read: boolean;
};

/**
 * Which plans this member could be moved to.
 *
 * **The plan they are on is not an option**, because `change_membership_plan` refuses an
 * agreement on the same plan outright ("this membership is already on that agreement") — so
 * offering it would be a control the server answers 409 to, which is FD-06's rule.
 *
 * **A trial is not an option either.** `sellable_plans` excludes them by default and
 * ADR-0010 D7 is why: a product declaring `trial_days` is what somebody converts *from*, so
 * moving a member onto one would be a downgrade into a seven-day clock.
 */
export function offerable(plans: PlanOption[], currentVariantId: string): PlanOption[] {
  return plans.filter(
    (one) => one.variant_id !== currentVariantId && !one.is_a_trial_product);
}

/** What a plan is called here: the product, qualified by the variant. */
export function planLabel(plan: PlanOption): { name: string; qualifier: string } {
  const named = plan.product_name !== null && plan.product_name.trim() !== "";
  return {
    name: named ? (plan.product_name as string) : plan.product_key,
    qualifier: plan.display_name,
  };
}

/**
 * Whether the loss panel can say anything, and which of two silences it is.
 *
 * **An empty loss is two different facts** and only the server's two flags tell them apart: a
 * tenant that has declared no plan entitlements at all, and two plans that genuinely grant the
 * same rights. Rendering both as "nothing changes" is exactly the quiet charge the canvas's
 * own note is about, so the screen says which.
 */
export type LossState =
  | { kind: "nothingDeclared" }
  | { kind: "sameRights" }
  | { kind: "loses" };

export function lossState(move: Move): LossState {
  const moves = move.lost.length + move.gained.length + move.requantified.length;
  if (moves > 0) return { kind: "loses" };
  if (!move.the_leaving_plan_declares_rights && !move.the_joining_plan_declares_rights) {
    return { kind: "nothingDeclared" };
  }
  return { kind: "sameRights" };
}

/**
 * The credits that stop being drawable, and the ones a booking protects.
 *
 * **"Her 4 unused PT credits expire on 1 Sep" is the canvas's own third line and the one it
 * calls the line that matters.** `written_off_on_the_change` is the balance, which is already
 * net of what is held — `reserve` is a negative ledger movement — so a member with four
 * credits who has booked one loses three and keeps the booking. Telling them they lose four
 * would be the wrong number in the direction the note is about.
 */
export function expiring(move: Move): Holding[] {
  return move.still_holding_from_the_plan_being_left.filter(
    (one) => one.is_counted && (one.written_off_on_the_change ?? 0) > 0);
}

export function stillBooked(move: Move): Holding[] {
  return move.still_holding_from_the_plan_being_left.filter(
    (one) => one.is_counted && (one.held ?? 0) > 0);
}

/**
 * Which sentence the effective date gets.
 *
 * The canvas states the reason rather than the rule: "Takes effect 1 September, **not today**
 * — she has paid for August at the higher rate and keeps it." That reason is only true of a
 * downgrade; an upgrade takes effect today and charges the difference, so the same date field
 * needs two different sentences.
 */
export function timingMessage(
  quote: ChangeQuote,
): { key: MessageKey; values: Record<string, string> } {
  // **The key *and* its values**, because `fill` is strict in both directions: a value passed
  // for a placeholder the message does not have is an error, not an ignored extra. "Takes
  // effect today." carries no `{on}` and the other two do, so a function returning the key
  // alone pushes the placeholder contract onto every call site -- and the first one got it
  // wrong, which is a 500 on the member's record rather than a missing word.
  if (quote.takes_effect_immediately) {
    return { key: "downgrade.effectiveToday", values: {} };
  }
  const values = { on: quote.effective_on ?? "" };
  return quote.kind === "downgrade"
    ? { key: "downgrade.effectiveAtRenewal", values }
    : { key: "downgrade.effectiveLater", values };
}

/**
 * What the server's refusal says, in words.
 *
 * **A vocabulary the backend stores is never a label** — this build's fifth instance, and the
 * first version of this sheet printed `an_upgrade_takes_effect_inside_the_current_period`
 * straight onto the page. An unknown value falls through to its stored form rather than to a
 * generic "refused", because the set is the server's and may grow: showing an ugly reason is
 * better than hiding one somebody needs.
 */
const REFUSALS: Record<string, MessageKey> = {
  an_upgrade_takes_effect_inside_the_current_period: "downgrade.outsidePeriod",
  a_plan_change_at_the_same_price_is_a_transfer_which_has_no_writer:
    "downgrade.samePrice",
  this_membership_is_already_on_that_plan: "downgrade.alreadyOnIt",
  this_membership_has_no_billing_period_to_prorate: "downgrade.noPeriod",
};

export function refusalMessage(because: string): MessageKey | null {
  return REFUSALS[because] ?? null;
}

/** Which of five states the sheet is in, so each refusal has its own sentence. */
export type MoveState =
  | { kind: "pickAPlan" }
  | { kind: "noPlans" }
  | { kind: "refused"; because: string }
  | { kind: "needsConfirmation" }
  | { kind: "ready" };

/**
 * **The typed confirmation is the plan's name, not the figure.** ADM-MSH-09's is an amount
 * because the act *is* the amount; this act is a move between two plans and the money is a
 * consequence of it — and on a downgrade the figure is zero, so typing it would be typing
 * "0.00" to confirm losing access to two clubs. The canvas's own button is "Downgrade from 1
 * Sep", which names the plan change rather than a sum.
 */
export function confirmsPlan(typed: string, planName: string): boolean {
  const fold = (value: string) => value.trim().replace(/\s+/g, " ").toLowerCase();
  return fold(typed) !== "" && fold(typed) === fold(planName);
}

export function moveState(
  { plans, quote, typed, planName }: {
    plans: PlanOption[];
    quote: ChangeQuote | null;
    typed: string;
    planName: string;
  },
): MoveState {
  if (plans.length === 0) return { kind: "noPlans" };
  if (quote === null) return { kind: "pickAPlan" };
  if (!quote.may_change) {
    return { kind: "refused", because: quote.refused_because ?? "refused" };
  }
  if (!confirmsPlan(typed, planName)) return { kind: "needsConfirmation" };
  return { kind: "ready" };
}
