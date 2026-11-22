/**
 * ADM-MSH-07 · CANCEL — "Cancel Tareq Odeh's membership".
 *
 * **Decisions only, and no imports that reach `next/headers`.** The form is a client
 * component, and the cash board and the account page both paid for this: a client component
 * importing `@/lib/api` fails the whole app's build with an error naming a chain of
 * `[Client Component Browser]` imports and never mentioning `next/headers`.
 *
 * The canvas is three facts above a required reason and two buttons:
 *
 *   > His 12-month commitment runs to March. Cancelling now triggers a two-month fee of
 *   > JOD 80.00, and his access ends on 7 September after the notice period.
 *   >
 *   > **Before you cancel** — He stopped visiting 12 days ago and has not given a reason. A
 *   > freeze costs him nothing and keeps the commitment intact. [Offer a freeze instead]
 *
 * Every figure comes from `GET /memberships/{id}/cancellation-preview`, which computes them
 * with the expressions `cancel_membership` compares the acknowledged figure against. Nothing
 * here does money arithmetic: a screen that added the parts itself would be a second
 * definition of the figure a member is held to.
 */

/** `GET /memberships/{id}/cancellation-preview`. */
export type CancellationQuote = {
  membership_id: string;
  status: string;
  version: number;
  may_cancel: boolean;
  refused_because: string | null;
  effective_on: string;
  ends_immediately: boolean;
  disclosed_fee_minor: number;
  disclosed_fee_currency: string;
  /**
   * The total, in parts.
   *
   * **Two figures that answer different questions**, which is why the server returns both:
   * `period_minor` is what the current billing period costs for the part of it the member
   * will have used, and `early_termination_minor` is the contract's buy-out. A member
   * disputing one should not have to take the other on trust.
   */
  fee_parts: { period_minor: number; early_termination_minor: number } | null;
  amount_minor: number;
  explanation: string[];
  cancellation_mode: string;
  notice_days: number;
  commitment: {
    minimum_term_months: number;
    ends_on: string | null;
    leaving_early: boolean;
    /** `null` is "this contract has no buy-out", which is not the same as a buy-out of 0. */
    early_termination_months: number | null;
    may_leave_early: boolean;
  };
  freeze_is_an_alternative: boolean;
  the_fee_is_what_it_costs_not_what_is_owed: string;
  the_figures_are_the_writes_own: string;
};

/**
 * How long without a visit counts as having stopped coming.
 *
 * **A judgement, stated here because nothing in the sources or the design declares one.**
 * The canvas's member "stopped visiting 12 days ago"; ten days is three or four missed
 * sessions for somebody training twice a week, which is the point at which a freeze is worth
 * offering rather than an interruption nobody wanted. It is the same kind of number as
 * MOD-014's threshold of eighteen for a minor and FD-06's ninety-minute countdown: a product
 * decision written where it is used, so it can be argued with.
 */
export const DORMANT_AFTER_DAYS = 10;

/**
 * Why a freeze is being offered instead, or `null` when it is not.
 *
 * **The canvas's interruption has two separate arguments and they are not always both
 * true.** "A freeze costs him nothing" is about the member having stopped coming — freezing
 * is the answer to a lull, not to somebody moving abroad. "And keeps the commitment intact"
 * is only meaningful while there *is* a commitment to keep: said to a member on a rolling
 * monthly contract it describes a benefit that does not exist.
 *
 * So each combination is its own answer with its own sentence, rather than one panel whose
 * text is true of the canvas's member and false of the next one. The contract allowing a
 * freeze at all is the precondition for every branch, because `check_freeze` refuses one
 * whatever the session holds — offering it there would send somebody to a form that cannot
 * accept them.
 *
 * **An unknown last visit is not dormancy.** `days_since` is null when MOD-022 has recorded
 * no entry for this person, and that happens at a club with no readers as readily as with a
 * member who never came. MOD-014's rule, in the same direction: an unknown birth date is not
 * a minor, because treating absent data as a fact is how a screen makes a confident wrong
 * claim about somebody.
 */
export type FreezeOffer = "dormant_and_committed" | "committed" | "dormant" | null;

export function freezeOffer(
  quote: Pick<CancellationQuote, "freeze_is_an_alternative" | "commitment">,
  daysSinceLastVisit: number | null,
): FreezeOffer {
  if (!quote.freeze_is_an_alternative) return null;
  const dormant =
    daysSinceLastVisit !== null && daysSinceLastVisit >= DORMANT_AFTER_DAYS;
  const committed = quote.commitment.leaving_early;
  if (dormant && committed) return "dormant_and_committed";
  if (committed) return "committed";
  if (dormant) return "dormant";
  return null;
}

/**
 * The fee, line by line, with the zeroes left out.
 *
 * **A line reading "buy-out: 0.00" on a rolling contract is noise that looks like a
 * charge**, and one reading "0.00" where the contract has no buy-out at all is worse — it
 * states a price for something that is not on offer. So a part is a line only when it is
 * actually being charged, and a contract with one component shows one line.
 *
 * The total is never computed here. It is `disclosed_fee_minor`, which is the figure the form
 * sends back for the server to compare against what it recomputes; adding the parts in the
 * client would be a second arithmetic that agrees with the server until the day it does not.
 */
export type FeeLine = { key: "cancel.feePeriod" | "cancel.feeBuyOut"; minor: number };

export function feeLines(quote: CancellationQuote): FeeLine[] {
  if (quote.fee_parts === null) return [];
  const lines: FeeLine[] = [];
  if (quote.fee_parts.period_minor !== 0) {
    lines.push({ key: "cancel.feePeriod", minor: quote.fee_parts.period_minor });
  }
  if (quote.fee_parts.early_termination_minor !== 0) {
    lines.push({
      key: "cancel.feeBuyOut", minor: quote.fee_parts.early_termination_minor,
    });
  }
  return lines;
}

/**
 * What the commitment line says, which is four different sentences.
 *
 * ADM-MSH-07's own line is "his 12-month commitment runs to March", and it is only one of
 * the cases this screen has to draw. A member on a rolling contract has no commitment line
 * at all; one whose term has already run out has a commitment that is no longer binding; and
 * one inside a term their contract will not let them buy out of cannot leave early, which is
 * the state the lifecycle enforced for every contract in this build until the buy-out
 * existed. Rendering the canvas's sentence in all four would tell three members something
 * untrue.
 */
export type CommitmentLine = "none" | "served" | "leaving_early" | "held_to_term";

export function commitmentLine(quote: CancellationQuote): CommitmentLine {
  if (quote.commitment.ends_on === null || quote.commitment.minimum_term_months === 0) {
    return "none";
  }
  if (!quote.commitment.leaving_early) return "served";
  return quote.commitment.may_leave_early ? "leaving_early" : "held_to_term";
}

/**
 * What this reader is offered, which is four answers rather than two.
 *
 * The same shape as the freeze's, and for the same reason: the quote reads on
 * `membership.record.read`, which is routine, and the act needs
 * `membership.lifecycle.change`, which is financial. A page that collapsed "a step-up would
 * open this" into "you may not" sends somebody to ask for a grant they already hold.
 *
 * **`cannot` comes first, because it is the server's answer whatever the session holds.**
 * `may_cancel` is `check_transition` asked the way the command asks it — a membership already
 * cancelled, or never activated, cannot be cancelled by anybody — so offering a step-up
 * there would be sending somebody to find a second factor that changes nothing. That is the
 * freeze's `no_allowance` rule, which the browser sweep found had no fixture to render it.
 */
export type CancelAffordance = "form" | "step_up" | "cannot" | "refused";

export function affordanceFor(
  quote: Pick<CancellationQuote, "may_cancel">,
  gate: { allowed: boolean; verdict: "needs_step_up" | "denied" | string },
): CancelAffordance {
  if (!quote.may_cancel) return "cannot";
  if (gate.allowed) return "form";
  if (gate.verdict === "needs_step_up") return "step_up";
  return "refused";
}
