import { api } from "@/lib/api";
import type { MessageKey } from "@/i18n/locale";

/**
 * ADM-PAY-07 · WALLET & CREDITS — what a member holds, and where each part came from.
 *
 * The canvas's own rule, printed under the panel: *"Always labelled credit, never a negative
 * balance. Each entry names its origin — a cancelled class, an overpayment, a goodwill
 * gesture — because unexplained credit is indistinguishable from an error."*
 */

export type WalletLine = {
  at: string;
  /** `cash | promotional | referral | refund_credit` — never collapsed into one figure. */
  value_kind: string;
  /** Signed: a credit is positive and a spend is negative, on one axis. */
  amount_minor: number;
  balance_after: number;
  expires_on: string | null;
  /** True once `expires_on` has passed. Returned marked rather than dropped. */
  lapsed: boolean;
  /** The tenant's own prose: what this movement was. */
  reason: string;
};

export type WalletStatement = {
  wallet_id: string;
  person_id: string;
  currency: string;
  as_of: string;
  /** Per value kind, because the kinds are not interchangeable. */
  balances: Record<string, number>;
  spendable_minor: number;
  /** What the member could actually ask for back: the cash they paid in. */
  refundable_minor: number;
  lines: WalletLine[];
};

export type WalletStatements = {
  person_id: string;
  as_of: string;
  /** Empty where this member holds nothing, which is a true answer rather than a 404. */
  wallets: WalletStatement[];
};

/**
 * Every wallet this member holds.
 *
 * **Not the single-currency read beside it.** `GET /ledger/wallets/{id}` takes a currency,
 * which a till settling a sale has and a member's record does not: a wallet is one row per
 * (person, currency), and a screen that guessed at one -- the tenant's first billing
 * account, say -- would show one and silently omit the rest.
 */
export function readWallets(personId: string): Promise<WalletStatements> {
  return api<WalletStatements>(
    `/ledger/wallets/${encodeURIComponent(personId)}/statements`,
  );
}

/**
 * The message key naming a value kind.
 *
 * **Four balances, not one**, which is paragraph 1686 and MOD-018 calls it a Critical
 * Control: a member holding 50.00 they paid in and 10.00 the tenant gave away holds two
 * different things, and only the first is money the tenant owes. A screen that summed them
 * would erase the distinction that decides whether a refund is possible.
 */
export function kindName(valueKind: string): MessageKey | null {
  const known: Record<string, MessageKey> = {
    cash: "wallet.kindCash",
    promotional: "wallet.kindPromotional",
    referral: "wallet.kindReferral",
    refund_credit: "wallet.kindRefundCredit",
  };
  return known[valueKind] ?? null;
}

/**
 * The neutral word for a value kind, for a sentence about a movement.
 *
 * **A balance label and a movement label are not the same words.** `wallet.kindPromotional`
 * is "Given away", which is right over a balance -- it says where that value came from -- and
 * wrong under a spend, where it reads as though the gym gave away a protein bar. A debit's
 * kind says which pocket the money came *out of*, and `plan_debit` chooses that pocket in the
 * member's interest: promotional first, because it expires and is worth nothing lapsed, cash
 * last because cash is the only kind they can ask for back. Worth saying on the row, in words
 * that mean it. Found by reading the rendered statement.
 */
export function kindWord(valueKind: string): MessageKey | null {
  const known: Record<string, MessageKey> = {
    cash: "wallet.wordCash",
    promotional: "wallet.wordPromotional",
    referral: "wallet.wordReferral",
    refund_credit: "wallet.wordRefundCredit",
  };
  return known[valueKind] ?? null;
}

/**
 * The soonest-expiring value the member still holds, and when it goes.
 *
 * ADM-PAY-07 puts this beside the balance — `JOD 12.50 · 8.00 EXPIRES 30 SEP` — because it
 * is the only thing on the panel a member can act on by a date. `null` where nothing expires,
 * which is a different answer from zero: a wallet of pure cash never lapses.
 *
 * **Lapsed entries are excluded.** They are shown in the list, marked, because "where did my
 * 10.00 go" is the question a member asks — but counting them here would promise value that
 * is already gone.
 */
export function nextExpiry(statement: WalletStatement): { amountMinor: number; on: string } | null {
  const live = statement.lines
    .filter((line) => line.amount_minor > 0 && line.expires_on !== null && !line.lapsed)
    .sort((a, b) => (a.expires_on ?? "").localeCompare(b.expires_on ?? ""));
  const soonest = live[0];
  if (soonest === undefined || soonest.expires_on === null) return null;
  // Everything expiring on that same date, not just the first row: two promotional credits
  // granted a week apart can lapse together, and naming one of them understates what the
  // member is about to lose.
  const amountMinor = live
    .filter((line) => line.expires_on === soonest.expires_on)
    .reduce((sum, line) => sum + line.amount_minor, 0);
  return { amountMinor, on: soonest.expires_on };
}
