import { api } from "@/lib/api";

/**
 * ADM-PAY-01's ledger: money in, money out and money contested, on one axis.
 *
 * > Refunds carry a negative sign and the parenthetical original. **A refund is never shown
 * > as a payment of a different colour — it is a different sign on the same axis.**
 *
 * **This screen did not exist.** `/finance` is MOD-018's general ledger -- the chart, the
 * periods and the trial balance -- which is a different subject from the payments ledger the
 * design specifies, and the compliance record has carried that as a named deviation since the
 * audit. The route behind it is new too: MOD-017 could answer "what does this member owe" and
 * had no read that put a tenant's payments, failed attempts, refunds and disputes in one
 * list, which is the one thing a reconciler opens every morning.
 */

export type LedgerKind = "payment" | "attempt" | "refund" | "dispute";

export type LedgerEntry = {
  kind: LedgerKind;
  row_id: string;
  at: string;
  /**
   * The payer, as an id.
   *
   * **No name comes out of this read**, deliberately: `finance.payment.read` is tenant-wide,
   * and a money permission that returned names would be a lateral read path around
   * `people.person.read` -- MOD-010's `events.event.read` finding, which this repository has
   * paid for once. The screen composes a name per row through MOD-014's own gate instead.
   */
  payer_person_id: string | null;
  method: string;
  /** Signed. A refund and a dispute are negative on the same axis as a payment. */
  amount_minor: number;
  currency: string;
  state: string;
  needs_action: boolean;
  /** What a refund or a dispute is about: the canvas's "parenthetical original". */
  about_payment_id: string | null;
};

export type PaymentsLedger = {
  entries: LedgerEntry[];
  count: number;
  since: string;
  until: string;
  needs_action: number;
  failed: number;
  refunded: number;
  disputed: number;
  truncated: boolean;
};

export function readPayments(params: {
  needsAction?: boolean;
  limit?: number;
} = {}): Promise<PaymentsLedger> {
  const query = new URLSearchParams();
  if (params.needsAction) query.set("needs_action", "true");
  query.set("limit", String(params.limit ?? 100));
  return api(`/finance/payments?${query.toString()}`);
}

/**
 * Which `MoneyValue` kind a row's amount is.
 *
 * The design's seven kinds are not decoration: a refund carries an explicit sign so it reads
 * in monochrome, and a failed attempt is money that did *not* arrive, which is `owed` rather
 * than `neutral` -- it is the row somebody has to chase.
 */
export function moneyKind(entry: LedgerEntry): "neutral" | "owed" | "refunded" {
  if (entry.kind === "refund" || entry.kind === "dispute") return "refunded";
  if (entry.kind === "attempt") return "owed";
  return "neutral";
}

/**
 * The header's own sentence: "6 failed, 3 refunded, 2 disputed".
 *
 * Returns only the non-zero parts, because "0 failed, 0 refunded, 0 disputed" is three facts
 * nobody needs stated and it pushes the one that matters off the line. A clean period says
 * nothing here, which is the same rule as the member record's absent status band: the absence
 * is the signal.
 */
export function exceptions(ledger: PaymentsLedger): {
  key: "payments.failedCount" | "payments.refundedCount" | "payments.disputedCount";
  count: number;
}[] {
  return ([
    { key: "payments.failedCount" as const, count: ledger.failed },
    { key: "payments.refundedCount" as const, count: ledger.refunded },
    { key: "payments.disputedCount" as const, count: ledger.disputed },
  ]).filter((one) => one.count > 0);
}
