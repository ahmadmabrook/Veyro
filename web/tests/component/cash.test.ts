import { describe, expect, it } from "vitest";

import { moneyOf, parseAmount, variance } from "@/lib/cash";

/**
 * ADM-PAY-09's till count, which is the one number on these surfaces a person types in
 * money and the server stores as an integer. Everything else about the screen is a read.
 */

describe("a currency's two exponents", () => {
  it("are different for JOD, which is the whole hazard", () => {
    // Stored as fils — three decimals — and shown with two, because "Veyro is a retail
    // product and shows two everywhere, including exports, so a reconciliation never has to
    // guess which convention a column used".
    expect(moneyOf("JOD")).toEqual({ displayDigits: 2, storageDigits: 3 });
    expect(moneyOf("USD")).toEqual({ displayDigits: 2, storageDigits: 2 });
  });

  it("fail closed for a currency the conventions module does not carry", () => {
    // A till whose count this screen cannot parse is a till it must refuse, not guess at.
    expect(moneyOf("XYZ")).toBeNull();
    expect(moneyOf("")).toBeNull();
  });
});

describe("a till count typed by a person", () => {
  const jod = { displayDigits: 2, storageDigits: 3 };
  const usd = { displayDigits: 2, storageDigits: 2 };

  it("scales what is shown to what is stored", () => {
    // **135.50 JOD is 135500 fils, not 13550.** Using the display digits as the storage
    // exponent would read the count as 13.55 and post the difference to suspense as a
    // 121.95 shortfall — on the screen whose entire job is the difference between two
    // numbers.
    expect(parseAmount("135.50", jod)).toBe(135_500);
    expect(parseAmount("135.5", jod)).toBe(135_500);
    expect(parseAmount("135", jod)).toBe(135_000);
    expect(parseAmount("0", jod)).toBe(0);
    expect(parseAmount("0.05", jod)).toBe(50);
  });

  it("is the same number of minor units as the figure beside it", () => {
    // The expected figure comes from the server in storage units and the count is typed in
    // display units; the variance is their difference, so a parse that returned display
    // units would make every drawer read as out by two orders of magnitude.
    const expected = 138_000; // JOD 138.00, from the server
    expect(variance(expected, parseAmount("138.00", jod))).toBe(0);
    expect(variance(expected, parseAmount("135.50", jod))).toBe(-2_500);
    expect(variance(expected, parseAmount("140.00", jod))).toBe(2_000);
  });

  it("never goes through a float", () => {
    // `Math.round(1.005 * 100)` is 100, not 101, and a till produces exactly these inputs
    // all day. The string is split and the fraction padded instead.
    expect(parseAmount("1.005", usd)).toBeNull(); // more decimals than USD shows
    expect(parseAmount("1.01", usd)).toBe(101);
    expect(parseAmount("8.07", usd)).toBe(807);
    expect(parseAmount("70.07", usd)).toBe(7_007);
  });

  it("refuses anything that is not a plain positive amount", () => {
    for (const bad of ["", "   ", "-5.00", "5,00", "1e3", "abc", "5.", ".5", "1.2.3",
                       "135.555"]) {
      expect(parseAmount(bad, jod), bad).toBeNull();
    }
  });

  it("refuses more decimals than the currency is shown with", () => {
    // Not more than it is *stored* with: a person reading a two-decimal screen who types
    // three has mistyped, and silently accepting it would store a figure the screen can
    // never show back to them.
    expect(parseAmount("135.500", jod)).toBeNull();
    expect(parseAmount("135.50", jod)).toBe(135_500);
  });
});

describe("the variance", () => {
  it("is null until something has been counted", () => {
    // An uncounted drawer is not a balanced drawer, and a screen that drew 0.00 there would
    // be stating the one thing nobody yet knows.
    expect(variance(138_000, null)).toBeNull();
    expect(variance(null, 138_000)).toBeNull();
  });

  it("is signed, because short and over are different problems", () => {
    expect(variance(138_000, 135_500)).toBeLessThan(0);
    expect(variance(138_000, 140_000)).toBeGreaterThan(0);
    expect(variance(138_000, 138_000)).toBe(0);
  });
});
