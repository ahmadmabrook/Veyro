import { describe, expect, it } from "vitest";

import {
  isOutstanding,
  money,
  outstandingMinor,
  remaining,
  type EntitlementGrant,
  type InvoiceRow,
} from "@/lib/membership";

/**
 * The three decisions MOD-017's surface makes about numbers, tested where they are made.
 *
 * **An amount is an integer count of minor units and the exponent is per currency.** Every
 * figure in Veyro is a `bigint` of minor units because `app/billing/money.py` says so, and a
 * client that divided by 100 would render 4500 JOD-fils as 45.00 JOD when it is 4.500 --
 * a factor of ten, in the currency this product's first tenant invoices in. `Intl` holds the
 * real exponent, which is why it does the division rather than this code.
 *
 * **"What is left" is three facts.** An uncounted grant has no balance at all, a counted one
 * has a balance, and part of that balance may be held by a booking nobody has attended.
 *
 * **"Outstanding" is not `status !== "paid"`.** `credited` and `written_off` are settled by
 * different means, and a collections figure that counted them would be money nobody is going
 * to collect.
 */

function grant(over: Partial<EntitlementGrant>): EntitlementGrant {
  return {
    grant_id: "g1",
    person_id: "p1",
    membership_id: null,
    is_counted: true,
    granted_quantity: 10,
    valid_from: "2026-01-01T00:00:00+00:00",
    valid_to: null,
    status: "active",
    source_kind: "membership",
    brand_id: null,
    location_id: null,
    usable_from_minute: null,
    usable_to_minute: null,
    policy_key: "classes",
    display_name: "Classes",
    entitlement_type: "class_credit",
    balance: 7,
    held: 2,
    ...over,
  };
}

function invoice(over: Partial<InvoiceRow>): InvoiceRow {
  return {
    invoice_id: "i1",
    billing_account_id: "b1",
    payer_person_id: "p1",
    document_number: "INV-1",
    document_kind: "invoice",
    net_minor: 4500,
    tax_minor: 720,
    gross_minor: 5220,
    currency: "JOD",
    issued_on: "2026-01-01",
    due_on: "2026-01-15",
    payment_status: "unpaid",
    fiscal_status: "pending",
    credits_invoice_id: null,
    paid_minor: 0,
    ...over,
  };
}

describe("money", () => {
  it("uses the currency's own exponent, which is three for JOD", () => {
    // The whole point: 4500 fils is 4.500 dinars, not 45.00. A hard-coded /100 is the defect
    // this test exists to catch, and it would be invisible in USD.
    expect(money(4500, "JOD")).toContain("4.50");
    expect(money(4500, "USD")).toContain("45.00");
  });

  it("falls back to the integer and the code for a currency the table does not know", () => {
    // `formatMoney` knows JOD and USD and raises for anything else, which is right for a
    // receipt and wrong for a page: a tenant trading in a third currency would get a 500 on
    // a member's record. "4500 JPY" is honest and unmistakable; "¥45.00" would not be.
    const shown = money(4500, "JPY");
    expect(shown).toContain("4500");
    expect(shown).toContain("JPY");
    const malformed = money(1234, "not-a-code");
    expect(malformed).toContain("1234");
    expect(malformed).toContain("not-a-code");
  });

  it("is the same renderer the receipt uses, not a second one", () => {
    // The point of delegating: `formatMoney` is parity-tested against the backend's own
    // formatter, so a screen and a receipt cannot drift. This asserts the shape that
    // function produces -- the code before the amount -- which `Intl` does not.
    expect(money(45000, "JOD")).toBe("JOD 45.00");
    expect(money(-45500, "JOD")).toBe("JOD -45.50");
  });

  it("formats zero rather than rendering it as empty", () => {
    expect(money(0, "JOD")).toContain("0.00");
  });
});

describe("remaining", () => {
  it("reports an uncounted grant as not counted, with no number", () => {
    const left = remaining(grant({ is_counted: false, balance: null, held: null }));
    expect(left.kind).toBe("unlimited");
    expect(left.balance).toBeNull();
    expect(left.held).toBeNull();
  });

  it("keeps the balance and the held quantity apart", () => {
    // "You have seven left" and "two of them are held for a class you have not attended" are
    // different answers to the same question, and MOD-017 returns both for that reason.
    const left = remaining(grant({ balance: 7, held: 2 }));
    expect(left).toEqual({ kind: "counted", balance: 7, held: 2 });
  });
});

describe("isOutstanding", () => {
  it("counts an unpaid or partly paid invoice", () => {
    expect(isOutstanding(invoice({ payment_status: "unpaid" }))).toBe(true);
    expect(isOutstanding(invoice({ payment_status: "part_paid" }))).toBe(true);
    expect(isOutstanding(invoice({ payment_status: "overdue" }))).toBe(true);
  });

  it("treats credited and written off as settled, because they are", () => {
    expect(isOutstanding(invoice({ payment_status: "paid" }))).toBe(false);
    expect(isOutstanding(invoice({ payment_status: "credited" }))).toBe(false);
    expect(isOutstanding(invoice({ payment_status: "written_off" }))).toBe(false);
  });

  it("never counts a credit note, whatever its payment status", () => {
    // A credit note is stored positive and is a reduction. Adding one to an outstanding
    // figure would move the total the wrong way by twice its value.
    expect(
      isOutstanding(invoice({ document_kind: "credit_note", payment_status: "unpaid" })),
    ).toBe(false);
  });
});

describe("outstandingMinor", () => {
  it("sums what is still owed on each outstanding document", () => {
    const total = outstandingMinor([
      invoice({ invoice_id: "a", gross_minor: 5220, paid_minor: 0 }),
      invoice({ invoice_id: "b", gross_minor: 5220, paid_minor: 2000,
                payment_status: "part_paid" }),
      invoice({ invoice_id: "c", gross_minor: 5220, paid_minor: 5220,
                payment_status: "paid" }),
    ]);
    expect(total).toBe(5220 + 3220);
  });

  it("is zero rather than negative when a credit note sits beside a paid invoice", () => {
    const total = outstandingMinor([
      invoice({ invoice_id: "a", payment_status: "paid", paid_minor: 5220 }),
      invoice({ invoice_id: "b", document_kind: "credit_note", gross_minor: 5220,
                paid_minor: 0 }),
    ]);
    expect(total).toBe(0);
  });

  it("is zero for an empty list, which is a figure rather than an absence", () => {
    expect(outstandingMinor([])).toBe(0);
  });
});
