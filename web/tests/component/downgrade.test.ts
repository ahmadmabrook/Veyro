import { describe, expect, it } from "vitest";

import {
  confirmsPlan, expiring, lossState, moveState, offerable, planLabel, refusalMessage,
  stillBooked, timingMessage, type ChangeQuote, type Holding, type Move, type PlanOption, type Right,
} from "@/lib/downgrade";

/**
 * ADM-MSH-06's loss panel, and the builders that refuse what the server cannot answer with.
 *
 * Three invariants hold, all three from `_plan_move` and `_revoke_plan_grants`:
 *
 * - `written_off_on_the_change` **is** the balance, because `entitlements.SIGNS` makes
 *   `reserve` negative so a held reservation has already left the ledger sum. The first
 *   version of the service subtracted the hold a second time, which left a revoked grant
 *   carrying a balance -- so a fixture where the two differ is a response the server cannot
 *   send, and a test built on one would be proving a branch nothing reaches.
 * - A right cannot be in two of `lost`, `kept` and `gained`: `same_right` partitions them.
 * - `the_leaving_plan_declares_rights` is false only where the leaving plan declares none, so
 *   a `lost` list beside that flag false is impossible.
 */

function right(over: Partial<Right> = {}): Right {
  return {
    policy_key: "pt.sessions",
    display_name: "PT sessions",
    entitlement_type: "class_credit",
    is_counted: true,
    quantity: 2,
    brand_id: null,
    location_id: null,
    ...over,
  };
}

function holding(over: Partial<Holding> = {}): Holding {
  const one: Holding = {
    grant_id: "grant-1",
    policy_key: "pt.sessions",
    display_name: "PT sessions",
    is_counted: true,
    remaining: 3,
    held: 1,
    written_off_on_the_change: 3,
    valid_to: "2026-09-01T23:59:59+00:00",
    ...over,
  };
  if (one.is_counted && one.written_off_on_the_change !== one.remaining) {
    throw new Error(
      "_revoke_plan_grants writes off the balance, and the balance is already net of what "
      + "is held -- so written_off_on_the_change equals remaining or the response is one no "
      + "server in this build can send");
  }
  return one;
}

function move(over: Partial<Move> = {}): Move {
  const one: Move = {
    lost: [],
    kept: [],
    gained: [],
    requantified: [],
    still_holding_from_the_plan_being_left: [],
    the_leaving_plan_declares_rights: true,
    the_joining_plan_declares_rights: true,
    ...over,
  };
  const keys = (rights: Right[]) => rights.map((r) => `${r.policy_key}:${r.location_id}`);
  const all = [...keys(one.lost), ...keys(one.kept), ...keys(one.gained)];
  if (new Set(all).size !== all.length) {
    throw new Error("same_right partitions the three lists; a right cannot be in two");
  }
  if (one.lost.length > 0 && !one.the_leaving_plan_declares_rights) {
    throw new Error("a lost right means the leaving plan declared one");
  }
  return one;
}

function quote(over: Partial<ChangeQuote> = {}): ChangeQuote {
  return {
    membership_id: "m-1",
    from_variant_id: "v-club-plus",
    to_variant_id: "v-club",
    kind: "downgrade",
    effective_on: "2026-09-01",
    takes_effect_immediately: false,
    from_amount_minor: 80_000,
    to_amount_minor: 55_000,
    due_minor: 0,
    credit_minor: 0,
    charge_minor: 0,
    currency: "JOD",
    billing_period: "monthly",
    may_change: true,
    refused_because: null,
    entitlements: move(),
    nothing_is_written_by_this_read: true,
    ...over,
  };
}

function plan(over: Partial<PlanOption> = {}): PlanOption {
  return {
    variant_id: "v-club",
    membership_terms_id: "t-club",
    product_name: "Club",
    product_key: "club",
    display_name: "Monthly",
    billing_period: "monthly",
    is_a_trial_product: false,
    ...over,
  };
}

describe("the builders refuse a response the server cannot send", () => {
  it("refuses a write-off that disagrees with the balance", () => {
    expect(() => holding({ remaining: 4, written_off_on_the_change: 3 }))
      .toThrow(/already net of what is held/);
  });

  it("refuses a right in two of the three lists", () => {
    const one = right();
    expect(() => move({ lost: [one], gained: [one] })).toThrow(/cannot be in two/);
  });

  it("refuses a lost right beside a plan that declares none", () => {
    expect(() => move({
      lost: [right()], the_leaving_plan_declares_rights: false,
    })).toThrow(/declared one/);
  });
});

describe("which plans this member can be moved to", () => {
  // `change_membership_plan` refuses an agreement on the same plan outright, so offering it
  // would be a control the server answers 409 to -- FD-06's rule.
  it("excludes the plan they are on", () => {
    const plans = [plan({ variant_id: "v-club" }), plan({ variant_id: "v-club-plus" })];
    expect(offerable(plans, "v-club").map((one) => one.variant_id)).toEqual(["v-club-plus"]);
  });

  // ADR-0010 D7: a product declaring `trial_days` is what somebody converts *from*, so
  // moving a member onto one would be a downgrade into a seven-day clock.
  it("excludes a trial", () => {
    const plans = [plan({ variant_id: "v-trial", is_a_trial_product: true })];
    expect(offerable(plans, "v-club")).toEqual([]);
  });

  it("names the product, qualified by the variant", () => {
    expect(planLabel(plan())).toEqual({ name: "Club", qualifier: "Monthly" });
  });

  it("falls back to the key where the product is not translated", () => {
    expect(planLabel(plan({ product_name: null })).name).toBe("club");
  });
});

describe("which of two silences an empty loss panel is", () => {
  // **The distinction the canvas's own note is about.** Rendering both as "nothing changes"
  // is exactly the quiet charge: "a member who discovers it afterwards has been quietly
  // charged for something they never got".
  it("says nothing is declared where neither plan declares a right", () => {
    expect(lossState(move({
      the_leaving_plan_declares_rights: false,
      the_joining_plan_declares_rights: false,
    })).kind).toBe("nothingDeclared");
  });

  it("says the rights are the same where both declare and nothing moves", () => {
    expect(lossState(move({ kept: [right()] })).kind).toBe("sameRights");
  });

  it("says there is a loss for each of the three kinds of move", () => {
    expect(lossState(move({ lost: [right()] })).kind).toBe("loses");
    expect(lossState(move({ gained: [right({ policy_key: "spa" })] })).kind).toBe("loses");
    expect(lossState(move({
      requantified: [{ ...right(), from_quantity: 2, to_quantity: 1 }],
    })).kind).toBe("loses");
  });
});

describe("the credits that stop being drawable", () => {
  // The canvas's third line and the one it calls the line that matters.
  it("lists a counted holding with something to write off", () => {
    const one = holding({ remaining: 3, written_off_on_the_change: 3, held: 1 });
    expect(expiring(move({ still_holding_from_the_plan_being_left: [one] })))
      .toHaveLength(1);
  });

  it("leaves out a holding with nothing left", () => {
    const one = holding({ remaining: 0, written_off_on_the_change: 0, held: 0 });
    expect(expiring(move({ still_holding_from_the_plan_being_left: [one] })))
      .toEqual([]);
  });

  it("leaves out an uncounted right, which has no quantity to expire", () => {
    const one = holding({
      is_counted: false, remaining: null, held: null,
      written_off_on_the_change: null, policy_key: "clubs.all",
    });
    expect(expiring(move({ still_holding_from_the_plan_being_left: [one] })))
      .toEqual([]);
  });

  // **A booking is protected and is its own sentence.** A member told they lose four when one
  // is a class they are in has been given the wrong number in the direction the note is about.
  it("names the booked ones separately", () => {
    const booked = holding({ held: 1 });
    const free = holding({ grant_id: "g-2", policy_key: "spa", held: 0,
                           remaining: 2, written_off_on_the_change: 2 });
    const both = move({ still_holding_from_the_plan_being_left: [booked, free] });
    expect(stillBooked(both).map((one) => one.grant_id)).toEqual(["grant-1"]);
    expect(expiring(both)).toHaveLength(2);
  });
});

describe("which sentence the effective date gets", () => {
  // The canvas states the *reason* rather than the rule -- "not today, she has paid for
  // August at the higher rate and keeps it" -- and that reason is only true of a downgrade.
  it("explains a future downgrade by what the member keeps", () => {
    expect(timingMessage(quote()).key).toBe("downgrade.effectiveAtRenewal");
  });

  it("does not borrow that reason for a future upgrade", () => {
    expect(timingMessage(quote({ kind: "upgrade" })).key)
      .toBe("downgrade.effectiveLater");
  });

  it("says today where the change is immediate", () => {
    expect(timingMessage(quote({ kind: "upgrade", takes_effect_immediately: true })).key)
      .toBe("downgrade.effectiveToday");
  });

  // **The values travel with the key, because `fill` is strict in both directions**: a value
  // passed for a placeholder the message does not have is an error, not an ignored extra.
  // "Takes effect today." carries no `{on}`, and the first version of the component passed
  // one unconditionally -- a 500 on the member's record rather than a missing word.
  it("carries the date only for the two messages that have a placeholder for it", () => {
    expect(timingMessage(quote()).values).toEqual({ on: "2026-09-01" });
    expect(timingMessage(quote({ kind: "upgrade" })).values).toEqual({ on: "2026-09-01" });
    expect(timingMessage(quote({ takes_effect_immediately: true })).values).toEqual({});
  });
});

describe("the typed confirmation", () => {
  // **The plan's name, not the figure.** On a downgrade the figure is zero, so typing it
  // would be typing "0.00" to confirm losing access to two clubs. The canvas's own button
  // names the plan change.
  it("accepts the plan's name, however it is spaced or cased", () => {
    expect(confirmsPlan("Club", "Club")).toBe(true);
    expect(confirmsPlan("  club  ", "Club")).toBe(true);
    expect(confirmsPlan("CLUB  PLUS", "Club Plus")).toBe(true);
  });

  it("refuses a different plan, a word and nothing", () => {
    expect(confirmsPlan("Club Plus", "Club")).toBe(false);
    expect(confirmsPlan("yes", "Club")).toBe(false);
    expect(confirmsPlan("   ", "Club")).toBe(false);
    expect(confirmsPlan("", "")).toBe(false);
  });
});

describe("the server's refusal, in words", () => {
  // **A vocabulary the backend stores is never a label** -- this build's fifth instance, and
  // the first version of this sheet printed the enum onto the page.
  it("has a sentence for each refusal the server can send", () => {
    expect(refusalMessage("an_upgrade_takes_effect_inside_the_current_period"))
      .toBe("downgrade.outsidePeriod");
    expect(refusalMessage("this_membership_is_already_on_that_plan"))
      .toBe("downgrade.alreadyOnIt");
  });

  // An unknown value falls through rather than being replaced by a generic "refused": the
  // set is the server's and may grow, and hiding a reason somebody needs is worse than an
  // ugly one.
  it("falls through for a refusal it does not know", () => {
    expect(refusalMessage("some_future_refusal")).toBeNull();
  });
});

describe("which of five states the sheet is in", () => {
  const plans = [plan()];

  it("has nothing to offer where there is no other plan", () => {
    expect(moveState({ plans: [], quote: null, typed: "", planName: "" }).kind)
      .toBe("noPlans");
  });

  it("asks for a plan before anything else", () => {
    expect(moveState({ plans, quote: null, typed: "", planName: "" }).kind)
      .toBe("pickAPlan");
  });

  // The server's own refusal, named rather than turned into a disabled button with no reason.
  it("carries the server's refusal", () => {
    const state = moveState({
      plans, quote: quote({ may_change: false, refused_because: "same_price_is_a_transfer" }),
      typed: "Club", planName: "Club",
    });
    expect(state.kind).toBe("refused");
    if (state.kind !== "refused") throw new Error("unreachable");
    expect(state.because).toBe("same_price_is_a_transfer");
  });

  it("waits for the typed plan name", () => {
    expect(moveState({ plans, quote: quote(), typed: "", planName: "Club" }).kind)
      .toBe("needsConfirmation");
  });

  it("is ready with a plan, a quote and the name typed back", () => {
    expect(moveState({ plans, quote: quote(), typed: "Club", planName: "Club" }).kind)
      .toBe("ready");
  });

  // The refusal is named before the confirmation, so a reader is told why it cannot happen
  // rather than asked to type a name into a form that will refuse.
  it("names the refusal before asking for the confirmation", () => {
    expect(moveState({
      plans, quote: quote({ may_change: false, refused_because: "x" }),
      typed: "", planName: "Club",
    }).kind).toBe("refused");
  });
});
