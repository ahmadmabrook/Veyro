import { describe, expect, it } from "vitest";

import { MESSAGES } from "@/i18n/locale";
import { LOST_REASONS, reasonWord, recontactSentence } from "@/lib/lost";

/**
 * ADM-CRM-07's decisions.
 *
 * **Nothing here decides whether a lead is lost or re-contactable**: all three come off the
 * read, because the ninety days is arithmetic over the server's clock. What is decided here is
 * which words the four reasons are drawn as and which sentence a lost lead's state gets.
 */

describe("the four reasons", () => {
  it("are the canvas's own, in its order", () => {
    expect(LOST_REASONS.map((one) => one.value)).toEqual([
      "too_expensive", "joined_elsewhere", "location_or_hours", "no_longer_responding",
    ]);
  });

  it("each have a word in both languages", () => {
    // **A vocabulary the backend stores is never a label**, and `MESSAGE_KEYS` is
    // structurally blind to a string that never became a key -- so a module that maps to
    // keys asserts its own, which is this app's rule after four recorded defects.
    for (const one of LOST_REASONS) {
      expect(MESSAGES.en[one.label], `en ${one.label}`).toBeDefined();
      expect(MESSAGES.ar[one.label], `ar ${one.label}`).toBeDefined();
    }
  });

  it("and there is no catch-all, which is the canvas's call", () => {
    // Four and no "Other": `no_longer_responding` absorbs a lead who simply stopped, and the
    // free-text detail is where a salesperson writes what they learned. A fifth is a product
    // decision, so inventing one here would be inventing product.
    const values = LOST_REASONS.map((one) => one.value);
    expect(values).not.toContain("other");
    expect(values).toHaveLength(4);
  });
});

describe("the word a stored reason is drawn as", () => {
  it("is found for each of the four", () => {
    for (const one of LOST_REASONS) {
      expect(reasonWord(one.value)).toBe(one.label);
    }
  });

  it("and a fifth the server grows falls through rather than reading as other", () => {
    // The set is closed on the server and a fifth is a migration away; showing an ugly value
    // is better than hiding a reason somebody needs to see, which is the members list's rule.
    expect(reasonWord("changed_their_mind")).toBeNull();
  });
});

describe("the re-contact sentence", () => {
  it("differs by whether ninety days have passed", () => {
    expect(recontactSentence(true)).toBe("lost.reopenable");
    expect(recontactSentence(false)).toBe("lost.notYetReopenable");
  });

  it("but both say reopening is allowed, which is the whole point", () => {
    // ADR-0010 D10: the ninety days is advisory, never a lock -- locking it would make a lead
    // marked lost by mistake uncorrectable for a quarter on a routine permission. So neither
    // sentence may read as a refusal.
    for (const allowed of [true, false]) {
      const text = MESSAGES.en[recontactSentence(allowed)] as string;
      expect(text).not.toMatch(/cannot|not allowed|refused/i);
    }
    expect(MESSAGES.en["lost.notYetReopenable"] as string)
      .toContain("allowed whenever you need it");
  });
});

describe("the footnote the canvas insists on", () => {
  it("says the record is not deleted and the stage is kept", () => {
    const note = MESSAGES.en["lost.note"] as string;
    expect(note).toContain("Not deleted");
    expect(note).toContain("stage it reached stays");
    expect(note).toContain("rather than a fresh record");
  });

});
