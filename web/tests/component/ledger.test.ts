import { describe, expect, it } from "vitest";

import {
  balanceVerdict,
  hasPostings,
  periodsNeedingAttention,
  type LedgerPeriod,
  type TrialBalance,
} from "@/lib/ledger";

/**
 * The three judgements MOD-018's board makes, tested where they are made.
 *
 * **"Needs somebody" is not "not open".** A `closed` period is the resting state of a filed
 * month and is not an exception; a `closing` one is work in progress somebody entered
 * deliberately, and a `reopened` one is a filed month that had to be unlocked -- the row a
 * reviewer asks about. Listing `closed` as an exception is how an alert channel gets muted,
 * which is the same judgement MOD-021's fleet board makes about `maintenance`.
 *
 * **An unbalanced trial balance is not a rounding question.** Every journal balances by a
 * deferred constraint trigger, so the two totals are equal by construction and a difference
 * means rows are missing. The verdict carries that distinction so a surface cannot render it
 * as "these columns differ by a bit".
 *
 * **A chart with no postings is an ordinary state**, not an empty one: `post_invoice` returns
 * `ledger_skipped_because` rather than refusing, so a tenant mid-setup still gets its invoice.
 */

function period(over: Partial<LedgerPeriod>): LedgerPeriod {
  return {
    period_id: "p1",
    legal_entity_id: "e1",
    period_key: "2026-11",
    starts_on: "2026-11-01",
    ends_on: "2026-11-30",
    status: "open",
    closed_at: null,
    closed_by: null,
    reopened_at: null,
    reopened_by: null,
    reopen_reason: null,
    admits_trade: true,
    ...over,
  };
}

function balance(over: Partial<TrialBalance>): TrialBalance {
  return {
    legal_entity_id: "e1",
    currency: "JOD",
    as_of: "2026-11-20",
    lines: [],
    debit_total_minor: 52200,
    credit_total_minor: 52200,
    balanced: true,
    difference_minor: 0,
    ...over,
  };
}

describe("periodsNeedingAttention", () => {
  it("names a closing period, because beginning a close stops the till", () => {
    const needs = periodsNeedingAttention([
      period({ period_id: "a", status: "closing", admits_trade: false }),
    ]);
    expect(needs.map((p) => p.period_id)).toEqual(["a"]);
  });

  it("names a reopened period, because a filed month was unlocked", () => {
    const needs = periodsNeedingAttention([
      period({ period_id: "b", status: "reopened", reopen_reason: "a credit note" }),
    ]);
    expect(needs.map((p) => p.period_id)).toEqual(["b"]);
  });

  it("names neither an open nor a closed period", () => {
    // A closed month is the resting state of a filed one. Calling it an exception is how
    // every row becomes an exception and nobody reads the list.
    expect(
      periodsNeedingAttention([
        period({ period_id: "c", status: "open" }),
        period({ period_id: "d", status: "closed", admits_trade: false }),
      ]),
    ).toEqual([]);
  });
});

describe("balanceVerdict", () => {
  it("reports a balanced ledger with no difference", () => {
    expect(balanceVerdict(balance({}))).toEqual({ kind: "balanced", differenceMinor: 0 });
  });

  it("calls an unbalanced ledger lost rows, not a difference", () => {
    // The wording matters: every journal balances by construction, so this is never two
    // columns disagreeing slightly.
    const verdict = balanceVerdict(
      balance({ balanced: false, difference_minor: -4500, credit_total_minor: 56700 }),
    );
    expect(verdict.kind).toBe("lost_rows");
    expect(verdict.differenceMinor).toBe(-4500);
  });
});

describe("hasPostings", () => {
  it("is false for a chart nobody has posted to", () => {
    expect(
      hasPostings(balance({ debit_total_minor: 0, credit_total_minor: 0 })),
    ).toBe(false);
  });

  it("is true as soon as either side has moved", () => {
    expect(hasPostings(balance({ debit_total_minor: 1, credit_total_minor: 0 }))).toBe(true);
    expect(hasPostings(balance({ debit_total_minor: 0, credit_total_minor: 1 }))).toBe(true);
  });
});
