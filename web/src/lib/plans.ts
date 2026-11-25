import { moneyOf, parseAmount } from "@/lib/cash";

/**
 * ADM-MSH-09 — "Plans & pricing · OWNER ONLY", and the one disclosure the screen is for.
 *
 * The canvas is a table and a sheet. The table is `PLAN | PRICE | ACTIVE | CHANGED |
 * ENTITLEMENTS`; the sheet is a price rise with its blast radius stated before it is saved:
 *
 * > Raising Club from 55.00 to 58.00 — 2,140 members are on this plan. 890 are inside a
 * > fixed-term commitment and keep 55.00 until it ends. The other 1,250 move at their next
 * > renewal, the earliest on 22 August. Effective date required · type "58.00" to confirm
 *
 * And its note: "The affected count is computed before the change is saved, not reported
 * after. A price rise is the most consequential action in Admin and the only one where the
 * blast radius is stated in members rather than currency."
 *
 * **The count is the server's** — `GET /catalog/variants/{id}/price-impact` — because it walks
 * the supersession chain and nothing a client could compose would get the split right. What is
 * decided here is which of five states the sheet is in, and whether the typed confirmation the
 * canvas requires has been given.
 */

/** One plan as the composition of three reads leaves it. */
export type Plan = {
  product_id: string;
  variant_id: string;
  /** The **variant's** name — a term length, not the plan's. */
  display_name: string;
  /** The product's, in the locale asked for, or `null` where it is not translated. */
  product_name: string | null;
  product_key: string;
  billing_period: string;
  is_a_trial_product: boolean;
  /** The live price row, where one is in its window. */
  price: PriceRow | null;
  /** How many members a rise would reach, where this session could read it. */
  impact: Impact | null;
};

export type PriceRow = {
  price_id: string;
  price_book_id: string;
  price_book_key: string;
  /** `draft`, `active` or `retired`, which is the second of the three conditions. */
  price_book_status: string;
  /** `resolve_price` prefers the higher one among the books that match a sale. */
  price_book_priority: number;
  variant_id: string;
  amount_minor: number;
  currency: string;
  effective_from: string;
  in_window: boolean;
};

export type Impact = {
  variant_id: string;
  as_of: string;
  on_this_plan: number;
  inside_a_commitment: number;
  move_at_renewal: number;
  earliest_move_on: string | null;
  earliest_commitment_ends_on: string | null;
};

/**
 * What a plan is called, which needed a server change to be answerable at all.
 *
 * **A variant's name is not a plan's**, which this screen found by rendering six rows that all
 * read "Monthly": a variant is a term length and a product is the thing a member buys. The
 * read carries both now, so a plan is its product and the variant qualifies it.
 *
 * **An untranslated product shows its key rather than another locale's name**, which is
 * `list_products`' own rule the plan read copied: a name in a language nobody asked for is
 * worse than none. The key is always there, which is what makes the absence usable.
 */
export function planName(plan: Plan): { name: string; qualifier: string; isKey: boolean } {
  const named = plan.product_name !== null && plan.product_name.trim() !== "";
  return {
    name: named ? (plan.product_name as string) : plan.product_key,
    qualifier: plan.display_name,
    isKey: !named,
  };
}

/**
 * Which price each variant reads as, when a variant is priced in more than one book.
 *
 * **Not the first row the server happened to return**, which is what the first version took.
 * `list_prices` orders by book key, so the alphabet would choose which figure a plan reads as
 * — MOD-018's `chart_for` finding, where an unordered lookup made the planner the author of
 * which account an invoice credited. A variant priced in two books is a legitimate chart
 * (`REV` beside `REV-RETAIL` is MOD-016's own example), so the order has to be stated.
 *
 * **It is `choose_book`'s own comparison, borrowed rather than invented**, and that function's
 * docstring says why the last key is there: "most specific, then highest priority, then the
 * key -- which is unique, so there is never a tie the planner gets to break. A resolver whose
 * answer depended on row order would fail the requirement in the way nobody notices until two
 * tills disagree." So the order here ends on the book key too, and is total for the same
 * reason. The first version ended on `effective_from`, which ties for two books priced from
 * the same date — the ordinary result of adding a seasonal book beside a standing one — and
 * then the answer came back to iteration order, which is the defect this ordering exists to
 * remove.
 *
 * **One of `choose_book`'s three keys is missing and that is the gap the screen names.**
 * Specificity is scored against a *sale* — its channel, its customer segment — and a plans
 * table has no sale, so this read answers for a sale that matches every book. A book scoped
 * to one channel can therefore win here and lose at the till.
 */
export function livePrices(prices: PriceRow[]): Map<string, PriceRow> {
  const live = new Map<string, PriceRow>();
  for (const price of prices) {
    if (!price.in_window) continue;
    const held = live.get(price.variant_id);
    if (held === undefined || beats(price, held)) live.set(price.variant_id, price);
  }
  return live;
}

function beats(one: PriceRow, held: PriceRow): boolean {
  const active = (price: PriceRow) => (price.price_book_status === LIVE_BOOK ? 1 : 0);
  if (active(one) !== active(held)) return active(one) > active(held);
  if (one.price_book_priority !== held.price_book_priority) {
    return one.price_book_priority > held.price_book_priority;
  }
  // The book key, which is unique per tenant, so the order is total. Two prices in the *same*
  // book are ordered by their start instead -- `list_prices` already returns them newest-first
  // within a book, and the later one is the row in force.
  if (one.price_book_key !== held.price_book_key) {
    return one.price_book_key < held.price_book_key;
  }
  return one.effective_from > held.effective_from;
}

/**
 * Whether this plan can be re-priced at all, and what is missing when it cannot.
 *
 * **A plan with no live price is not a plan whose price can be raised**, and the reason is a
 * real one rather than a guard: a new version supersedes the one in force, so without one in
 * force there is nothing to supersede and what the screen would be doing is setting a first
 * price — a different act, on a plan the till cannot currently sell.
 */
export type Repriceable =
  | { kind: "ready"; price: PriceRow }
  | { kind: "noPrice" }
  | { kind: "deadBook"; price: PriceRow; status: string };

/** The one book status a sale resolves against. */
export const LIVE_BOOK = "active";

export function repriceable(plan: Plan): Repriceable {
  if (plan.price === null || !plan.price.in_window) return { kind: "noPrice" };
  // **The second condition, which the read answers and the write does not.** `list_prices`
  // returns `price_book_status` and `create_price` never looks at it, so a new version written
  // into a draft or retired book is accepted by the server and resolved by no sale -- a price
  // change that reports success and changes nothing a member is charged. The screen refuses
  // rather than writing it, and names the book, because activating it is a different act.
  if (plan.price.price_book_status !== LIVE_BOOK) {
    return { kind: "deadBook", price: plan.price, status: plan.price.price_book_status };
  }
  return { kind: "ready", price: plan.price };
}

/**
 * What the typed confirmation has to be, and whether it has been given.
 *
 * **Compared as an amount, not as a string.** The canvas says `type "58.00" to confirm`, and
 * the point of a tier-3 typed confirmation is to make somebody read the figure — not to make
 * them reproduce its trailing zero. "58.0" and "58.00" are the same amount in the same
 * currency, and refusing the first would be a control about typography rather than about the
 * number, which teaches people to copy and paste.
 *
 * **Still the new figure rather than a word.** Typing the amount is what makes the reader look
 * at it; a "yes" would not.
 */
export function confirms(
  typed: string, { amountMinor, currency }: { amountMinor: number; currency: string },
): boolean {
  const money = moneyOf(currency);
  if (money === null) return false;
  const parsed = parseAmount(typed, money);
  return parsed !== null && parsed === amountMinor;
}

/** Which state the sheet is in, so each refusal has its own sentence. */
export type RiseState =
  | { kind: "resting" }
  | { kind: "notAnAmount" }
  | { kind: "unchanged" }
  | { kind: "needsDate" }
  | { kind: "dateInThePast" }
  | { kind: "needsConfirmation"; amountMinor: number }
  | { kind: "ready"; amountMinor: number; effectiveFrom: string };

export function riseState(
  { typedAmount, effectiveFrom, typedConfirmation, current, today }: {
    typedAmount: string;
    effectiveFrom: string;
    typedConfirmation: string;
    current: PriceRow;
    today: string;
  },
): RiseState {
  if (typedAmount.trim() === "") return { kind: "resting" };
  const money = moneyOf(current.currency);
  const amountMinor = money === null ? null : parseAmount(typedAmount, money);
  if (amountMinor === null) return { kind: "notAnAmount" };
  // **A new version that charges the same is a version nobody can act on**, and it would still
  // supersede the row in force — so a reader who mistyped and got the old figure back would
  // have moved the price's history for nothing.
  if (amountMinor === current.amount_minor) return { kind: "unchanged" };
  if (effectiveFrom === "") return { kind: "needsDate" };
  // **Not in the past**, which is MOD-016's own stated gap: a stored resolution is immutable
  // so a receipt stands, but a *re-derivation* of a historical order reads the price rows and
  // would come back with a figure nobody charged.
  if (effectiveFrom < today) return { kind: "dateInThePast" };
  if (!confirms(typedConfirmation, { amountMinor, currency: current.currency })) {
    return { kind: "needsConfirmation", amountMinor };
  }
  return { kind: "ready", amountMinor, effectiveFrom };
}

/**
 * Whether this is a rise or a cut, which the canvas does not draw and a reader needs.
 *
 * The canvas's example is a rise, and its note calls one "the most consequential action in
 * Admin". A cut reaches the same members and the same commitment split applies — a member
 * inside a term keeps the *old, higher* figure until it ends, which is the surprising
 * direction and the one somebody would otherwise have to work out from two numbers.
 */
export function direction(amountMinor: number, current: PriceRow): "rise" | "cut" {
  return amountMinor > current.amount_minor ? "rise" : "cut";
}
