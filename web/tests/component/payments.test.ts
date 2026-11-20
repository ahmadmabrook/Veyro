import { describe, expect, it } from "vitest";

import { exceptions, moneyKind, type LedgerEntry, type PaymentsLedger } from "@/lib/payments";

/**
 * ADM-PAY-01's two decisions, tested where they are made.
 *
 * **A refund is a sign, not a kind**, which is the canvas's own rule: "A refund is never
 * shown as a payment of a different colour — it is a different sign on the same axis." The
 * `MoneyValue` kind is how that reaches a reader, and the browser suite can only see it on
 * the rows the fixture happens to have.
 *
 * **A clean period says nothing**, which the browser suite structurally cannot test: the
 * fixture seeds one of each kind precisely so the ledger's distinctions are visible, so the
 * suppression of a zero is only observable here.
 */

function entry(over: Partial<LedgerEntry>): LedgerEntry {
  return {
    kind: "payment", row_id: "r", at: "2026-01-01T00:00:00Z", payer_person_id: "p",
    method: "card", amount_minor: 5220, currency: "JOD", state: "received",
    needs_action: false, about_payment_id: null, ...over,
  };
}

function ledger(over: Partial<PaymentsLedger>): PaymentsLedger {
  return {
    entries: [], count: 0, since: "2026-01-01", until: "2026-01-31",
    needs_action: 0, failed: 0, refunded: 0, disputed: 0, truncated: false, ...over,
  };
}

describe("which money kind a ledger row is", () => {
  it("makes a refund and a dispute carry an explicit sign", () => {
    // `refunded` is the one `MoneyValue` kind that puts `−` in the text, which is what makes
    // it readable in monochrome and to a colour-blind reader.
    expect(moneyKind(entry({ kind: "refund" }))).toBe("refunded");
    expect(moneyKind(entry({ kind: "dispute" }))).toBe("refunded");
  });

  it("marks a failed charge as owed, because it is money that did not arrive", () => {
    // Not `neutral`: a failed attempt is the row somebody has to chase, and the design's
    // `owed` kind is "critical, always with a status word nearby" -- which the State column
    // supplies.
    expect(moneyKind(entry({ kind: "attempt", state: "failed" }))).toBe("owed");
  });

  it("leaves a received payment as a fact with no colour", () => {
    expect(moneyKind(entry({}))).toBe("neutral");
  });
});

describe("the header's exception sentence", () => {
  it("names only the kinds that happened", () => {
    expect(exceptions(ledger({ failed: 6, refunded: 3, disputed: 2 })).map((o) => o.count))
      .toEqual([6, 3, 2]);
    expect(exceptions(ledger({ failed: 0, refunded: 3, disputed: 0 }))
      .map((one) => one.key)).toEqual(["payments.refundedCount"]);
  });

  it("says nothing at all about a clean period", () => {
    // "0 failed, 0 refunded, 0 disputed" is three facts nobody needs stated, and they push
    // the figure that matters off the line. The absence is the signal, which is the same
    // rule as the member record's absent status band.
    expect(exceptions(ledger({}))).toEqual([]);
  });
});
