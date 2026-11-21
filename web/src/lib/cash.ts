import { CURRENCY_DISPLAY_DIGITS, CURRENCY_MINOR_UNITS } from "@/i18n/conventions.mjs";

/**
 * ADM-PAY-09 — "Closing Layla's shift".
 *
 * **The expected figure is on this page before the count is entered, and that is the
 * canvas's own decision rather than an oversight:** *"The expected figure is shown before
 * the count is entered. Hiding it would be a fraud control; showing it is an accuracy
 * control, and accuracy is the more common problem."* So the read returns it for an open
 * drawer, derived from that account's own postings with no number any caller sent.
 *
 * **`open_cash_session` and `close_cash_session` had no reader**, which is why this screen
 * could not be drawn: a drawer could be opened and the only way to learn what was in it was
 * to close it and read the refusal. The sixth instance of this build's "a writer with no
 * reader" shape. `GET /ledger/cash-sessions` closes it.
 */

export type CashSession = {
  session_id: string;
  location_id: string;
  cash_account_id: string;
  drawer_label: string;
  currency: string;
  opening_float_minor: number;
  status: string;
  opened_at: string;
  opened_by: string;
  /** Derived now for an open drawer; what it was measured against for a closed one. */
  expected_minor: number | null;
  counted_minor: number | null;
  variance_minor: number | null;
  variance_reason: string | null;
  closed_at: string | null;
  closed_by: string | null;
  variance_journal_id: string | null;
  /** What came in after the float, what went out, and how many entries put money in. */
  taken_minor: number;
  paid_out_minor: number;
  entries_in: number;
};

export type CashSessions = {
  count: number;
  sessions: CashSession[];
  expected_is_derived_from_postings: string;
  the_figures_span_the_drawer_not_the_shift: string;
  an_entry_is_a_journal_not_a_sale: string;
};


/** What a currency's two exponents are. Both come from the conventions module. */
export type Money = { displayDigits: number; storageDigits: number };

/**
 * A currency's two exponents, or `null` for one this build does not carry.
 *
 * Both tables are closed and fail closed, which is why this returns `null` rather than
 * guessing two: a till in a currency the conventions module has never heard of is a till
 * whose count this screen must refuse to parse at all.
 */
export function moneyOf(currency: string): Money | null {
  const storageDigits = (CURRENCY_MINOR_UNITS as Record<string, number>)[currency];
  const displayDigits = (CURRENCY_DISPLAY_DIGITS as Record<string, number>)[currency];
  if (storageDigits === undefined || displayDigits === undefined) return null;
  return { displayDigits, storageDigits };
}

/**
 * A till count as the server's minor units, or `null` where it is not a number this build
 * will accept.
 *
 * **Two exponents, and conflating them is a defect this repository has already shipped
 * once.** A JOD amount is *stored* as a count of fils — three decimals — and *shown* with
 * two, because "Veyro is a retail product and shows two everywhere, including exports, so a
 * reconciliation never has to guess which convention a column used". Every figure on this
 * screen is therefore rendered with two decimals, which is what the person at the till
 * reads and what they type back; the parse has to scale that to three. Using the display
 * digits as the storage exponent would turn a 135.50 count into 13550 fils — 13.55 — and
 * post the difference to suspense as a 121.95 shortfall.
 *
 * **Parsed by splitting the string, never by multiplying a float.** `Math.round(135.50 *
 * 100)` is right and `Math.round(1.005 * 100)` is not, and a till produces exactly those
 * inputs all day. `app/billing/money.py` is the arithmetic this agrees with.
 */
export function parseAmount(
  typed: string, { displayDigits, storageDigits }: Money,
): number | null {
  const text = typed.trim();
  if (!/^\d{1,12}(\.\d{1,6})?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  if (fraction.length > displayDigits) return null;
  const shown = Number(whole) * 10 ** displayDigits
    + Number(fraction.padEnd(displayDigits, "0") || "0");
  return shown * 10 ** (storageDigits - displayDigits);
}


/** What a drawer is out by, and which way. `null` until something has been counted. */
export function variance(expected: number | null, counted: number | null): number | null {
  if (expected === null || counted === null) return null;
  return counted - expected;
}
