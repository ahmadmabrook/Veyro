import type { MessageKey } from "@/i18n/locale";
import type { ConversionQuote } from "@/lib/leads";

/**
 * ADM-CRM-06's decisions — "Rana becomes a member".
 *
 * The canvas is four lines and two buttons:
 *
 *     Club · monthly · JOD 55.00
 *     Pro-rata to 31 Aug · JOD 21.29
 *     Then 55.00 from 1 Sep
 *     Her four class attendances, her credential and Yasmin's notes all carry over.
 *     Nothing is re-entered.
 *
 * **No figure is computed here.** The part-period amount, the boundary and the day the
 * recurring charge starts all come off the response, because they are `lifecycle.first_charge`
 * over the contract's own anchor and a browser deriving them would count days in its own
 * frame. What this module decides is which sentences those figures belong in.
 */

/** Which of the two shapes a first charge takes. */
export type ChargeShape = "prorated" | "full_period";

/**
 * **A contract that does not prorate must not be given a pro-rata line.** Under the
 * `agreement_start` anchor the first period runs a whole month from the day the member joins,
 * so the figure equals the recurring one -- and printing "Pro-rata to 19 Sep · JOD 55.00"
 * beside "Then 55.00 from 20 Sep" would read as a coincidence rather than as the rule. The
 * server says which, in `prorated`, rather than leaving a client to compare two amounts: two
 * equal figures are also what a member who joined on the first sees, and those are different
 * facts.
 */
export function chargeShape(quote: ConversionQuote): ChargeShape {
  return quote.prorated ? "prorated" : "full_period";
}

/** One thing a conversion carries over, with the count that proves it already exists. */
export type CarriedOver = { key: MessageKey; count: number };

/**
 * The carry-over items that actually exist.
 *
 * **Nothing with a count of zero is claimed.** "Her four class attendances ... carry over" is
 * true of Rana and false of a lead who has never booked anything, and a line reading "0 class
 * attendances carry over" is the confident wrong answer MOD-014's own Member 360 was bitten
 * by. The structural sentence is shown either way, because *that* is true of everybody: there
 * is one person row, so a conversion moves nothing.
 *
 * **The credential is not in this list and is in the sentence instead.** What somebody can
 * present at a door is MOD-022's own read behind its own permission, so the quote carries no
 * count -- and claiming "her credential carries over" for a member who has none would be the
 * same wrong answer in the other direction.
 */
export function carriesOver(quote: ConversionQuote): CarriedOver[] {
  const items: CarriedOver[] = [
    { key: "convert.carriesClasses", count: quote.carries_over.classes },
    { key: "convert.carriesVisits", count: quote.carries_over.visits },
    { key: "convert.carriesNotes", count: quote.carries_over.touchpoints },
  ];
  return items.filter((item) => item.count > 0);
}

/**
 * Whether this conversion is the canvas's own case: a trialist becoming a member.
 *
 * A lead can become a member without ever having had a trial -- three of the five board
 * columns are people who never did -- so the absence is a state to render rather than a
 * refusal, and the screen says which of the two it is drawing.
 */
export function fromTrial(quote: ConversionQuote): boolean {
  return quote.converting_from_a_trial && quote.trial !== null;
}

/**
 * The canvas's two controls, and why neither is a button here.
 *
 * **"Take 21.29" is the payment provider and "Send link" is the messaging one**, which are
 * two of the seven external blockers this build names. Every other absent form in this app is
 * a stepped-up financial permission and is absent because "a button that answered 403 is
 * worse than its absence"; these two are absent because nothing in the repository can take
 * money or send a message, which is a different reason and is worth saying separately.
 *
 * **The conversion itself is not offered either, and that is a product judgement rather than
 * a blocker.** `change_membership_plan` exists and would write the superseding agreement --
 * it is what ADM-MSH-05 is built on -- but it issues no invoice, so a button that converted
 * without charging would leave a member with access that nobody has paid for. Converting and
 * charging are one act at this door, and half of it is worse than neither.
 */
export const BLOCKED_ACTIONS: readonly { key: MessageKey; why: MessageKey }[] = [
  { key: "convert.actionTake", why: "convert.actionTakeWhy" },
  { key: "convert.actionLink", why: "convert.actionLinkWhy" },
] as const;
