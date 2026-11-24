import { describe, expect, it } from "vitest";

import { MESSAGES, type MessageKey } from "@/i18n/locale";
import { BLOCKED_ACTIONS, carriesOver, chargeShape, fromTrial } from "@/lib/convert";
import type { ConversionQuote } from "@/lib/leads";

/**
 * ADM-CRM-06's decisions.
 *
 * **The builder refuses a quote the server cannot emit.** ADM-MSH-07 paid for the alternative:
 * a hand-written unit fixture encoded `leaving_early: true` beside `may_leave_early: false`,
 * which the lifecycle's own arithmetic forbids, and a dead branch sat behind a green assertion
 * for a commit. Every implication the server guarantees is a throw here, and one test proves
 * the throws fire.
 */

function raw(over: Partial<ConversionQuote> = {}): ConversionQuote {
  return {
    lead_id: "l1",
    person_id: "p1",
    stage: "toured",
    today: "2026-08-20",
    plan: {
      variant_id: "v1",
      display_name: "Club",
      product_key: "club.membership",
      billing_period: "monthly",
      billing_anchor: "calendar",
    },
    currency: "JOD",
    price_book_id: "b1",
    price_id: "pr1",
    recurring_minor: 5500,
    list_amount_minor: 5500,
    discount_minor: 0,
    first_charge_minor: 2129,
    first_period_ends_on: "2026-08-31",
    recurring_starts_on: "2026-09-01",
    prorated: true,
    explanation: ["calendar monthly unit: 2026-08-01..2026-08-31"],
    converting_from_a_trial: true,
    trial: {
      membership_id: "m1",
      starts_on: "2026-08-15",
      ends_on: "2026-08-21",
      trial_days: 7,
    },
    carries_over: {
      classes: 4,
      visits: 4,
      touchpoints: 3,
      the_record_does_not_change: "one ppl_persons row",
      no_credential_count_here: "MOD-022's own read",
    },
    nothing_is_charged_here: "the payment provider",
    ...over,
  };
}

/** `raw`, checked against what the server's own arithmetic guarantees. */
function quote(over: Partial<ConversionQuote> = {}): ConversionQuote {
  const q = raw(over);
  if (q.prorated && q.first_charge_minor === q.recurring_minor) {
    throw new Error(
      "a prorated first charge is not the whole recurring amount: `first_charge` returns the "
      + "full amount and reports prorated: false when the period is whole");
  }
  if (!q.prorated && q.first_charge_minor !== q.recurring_minor) {
    throw new Error("an unprorated first charge is exactly the recurring amount");
  }
  if (q.converting_from_a_trial !== (q.trial !== null)) {
    throw new Error("`trial` is present exactly when `converting_from_a_trial` is true");
  }
  if (q.recurring_starts_on <= q.first_period_ends_on) {
    throw new Error("the recurring charge starts the day after the boundary");
  }
  return q;
}

describe("the builder refuses states the server cannot produce", () => {
  it("throws on each of the four", () => {
    expect(() => quote({ prorated: true, first_charge_minor: 5500 })).toThrow();
    expect(() => quote({ prorated: false })).toThrow();
    expect(() => quote({ converting_from_a_trial: false })).toThrow();
    expect(() => quote({ recurring_starts_on: "2026-08-31" })).toThrow();
  });
});

describe("the charge shape", () => {
  it("is the canvas's pro-rata case for a calendar anchor mid-month", () => {
    expect(chargeShape(quote())).toBe("prorated");
  });

  it("is a full period where the contract does not prorate", () => {
    // **The server says which, rather than a client comparing two amounts.** Two equal
    // figures are also what a member who joined on the first sees, and those are different
    // facts: one is the rule and one is a coincidence.
    expect(chargeShape(quote({
      prorated: false, first_charge_minor: 5500,
      plan: { ...raw().plan, billing_anchor: "agreement_start" },
    }))).toBe("full_period");
  });
});

describe("the carry-over", () => {
  it("is the canvas's own three, with their counts", () => {
    expect(carriesOver(quote())).toEqual([
      { key: "convert.carriesClasses", count: 4 },
      { key: "convert.carriesVisits", count: 4 },
      { key: "convert.carriesNotes", count: 3 },
    ]);
  });

  it("claims nothing with a count of zero", () => {
    // "Her four class attendances carry over" is true of Rana and false of a lead who has
    // never booked anything; a line reading "0 class attendances" is the confident wrong
    // answer MOD-014's own Member 360 was bitten by.
    const none = quote({
      carries_over: { ...raw().carries_over, classes: 0, visits: 0, touchpoints: 0 },
    });
    expect(carriesOver(none)).toEqual([]);
  });

  it("keeps the ones that exist when others do not", () => {
    const some = quote({
      carries_over: { ...raw().carries_over, classes: 0, visits: 2, touchpoints: 0 },
    });
    expect(some.carries_over.visits).toBe(2);
    expect(carriesOver(some).map((one) => one.key)).toEqual(["convert.carriesVisits"]);
  });

  it("does not claim a credential, which has no count on the wire", () => {
    // What this person can present at a door is MOD-022's own read behind its own permission,
    // so claiming "her credential carries over" would be the same wrong answer in the other
    // direction.
    for (const item of carriesOver(quote())) {
      expect(item.key).not.toContain("redential");
    }
  });
});

describe("whether this is the canvas's own case", () => {
  it("is a trialist becoming a member", () => {
    expect(fromTrial(quote())).toBe(true);
  });

  it("and a lead who never had a trial converts just as well", () => {
    expect(fromTrial(quote({ converting_from_a_trial: false, trial: null }))).toBe(false);
  });
});

describe("the blocked actions", () => {
  it("are the canvas's two buttons, each with its own reason", () => {
    expect(BLOCKED_ACTIONS.map((one) => one.key)).toEqual([
      "convert.actionTake", "convert.actionLink",
    ]);
  });

  it("name a provider rather than a permission", () => {
    // **Every other absent form in this app is a stepped-up financial permission**, and these
    // two are not: one needs a payment provider and the other a messaging one. A reader told
    // "you need a stronger sign-in" would go and get one for nothing.
    const take = MESSAGES.en["convert.actionTakeWhy"] as string;
    const link = MESSAGES.en["convert.actionLinkWhy"] as string;
    expect(take).toContain("payment provider");
    expect(link.toLowerCase()).toMatch(/email|sms|provider/);
    for (const why of [take, link]) {
      expect(why).not.toContain("stronger sign-in");
    }
  });

  it("and every key they name exists in both languages", () => {
    // `MESSAGE_KEYS` compares key sets, and a string that never became a key is invisible to
    // it -- so a module that maps to keys asserts its own.
    const keys: MessageKey[] = [
      ...BLOCKED_ACTIONS.flatMap((one) => [one.key, one.why]),
      "convert.carriesClasses", "convert.carriesVisits", "convert.carriesNotes",
      "convert.actionConvert", "convert.actionConvertWhy",
    ];
    for (const key of keys) {
      expect(MESSAGES.en[key], `en ${key}`).toBeDefined();
      expect(MESSAGES.ar[key], `ar ${key}`).toBeDefined();
    }
  });
});
