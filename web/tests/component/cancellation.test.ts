import { describe, expect, it } from "vitest";

import {
  DORMANT_AFTER_DAYS,
  affordanceFor,
  commitmentLine,
  feeLines,
  freezeOffer,
  type CancellationQuote,
} from "@/lib/cancellation";

/**
 * ADM-MSH-07's decisions. Every figure is the server's; what is here is which of several
 * sentences the sheet says, and each one is a branch with a test because the canvas's own
 * wording is true of its member and false of three others.
 */

const quote = (over: Partial<CancellationQuote> = {}): CancellationQuote => ({
  membership_id: "m-1",
  status: "active",
  version: 3,
  may_cancel: true,
  refused_because: null,
  effective_on: "2026-09-07",
  ends_immediately: false,
  disclosed_fee_minor: 12_000,
  disclosed_fee_currency: "JOD",
  fee_parts: { period_minor: 4000, early_termination_minor: 8000 },
  amount_minor: 4000,
  explanation: ["decided_on: 2026-08-08"],
  cancellation_mode: "end_of_notice",
  notice_days: 30,
  commitment: {
    minimum_term_months: 12,
    ends_on: "2027-03-01",
    leaving_early: true,
    early_termination_months: 2,
    may_leave_early: true,
  },
  freeze_is_an_alternative: true,
  the_fee_is_what_it_costs_not_what_is_owed: "x",
  the_figures_are_the_writes_own: "x",
  ...over,
});

describe("which commitment sentence the sheet says", () => {
  it("names the term and that it is being left early, which is the canvas's own case", () => {
    expect(commitmentLine(quote())).toBe("leaving_early");
  });

  it("says nothing about a commitment where there is none", () => {
    // A member on a rolling monthly contract. Rendering "a 0-month commitment runs to null"
    // is the confident wrong answer a screen makes when it draws one sentence for everybody.
    expect(commitmentLine(quote({
      commitment: {
        minimum_term_months: 0, ends_on: null, leaving_early: false,
        early_termination_months: null, may_leave_early: false,
      },
    }))).toBe("none");
    // And a term length with no end date is the same absence, from the other side: the
    // agreement carries `minimum_term_ends_on` and a contract's month count is not a date.
    expect(commitmentLine(quote({
      commitment: {
        minimum_term_months: 12, ends_on: null, leaving_early: false,
        early_termination_months: null, may_leave_early: false,
      },
    }))).toBe("none");
  });

  it("says the term has been served where access ends on or after it", () => {
    expect(commitmentLine(quote({
      commitment: {
        minimum_term_months: 12, ends_on: "2026-01-01", leaving_early: false,
        early_termination_months: 2, may_leave_early: true,
      },
    }))).toBe("served");
  });

  it("says the term holds where the contract sells no way out of it", () => {
    // **The state every contract in this build was in until the buy-out existed**, and the
    // sentence is different in kind: access ends at the term rather than after notice, so a
    // screen saying "this leaves it early" would be describing something that cannot happen.
    expect(commitmentLine(quote({
      commitment: {
        minimum_term_months: 12, ends_on: "2027-03-01", leaving_early: true,
        early_termination_months: null, may_leave_early: false,
      },
    }))).toBe("held_to_term");
  });
});

describe("the fee, line by line", () => {
  it("shows both parts where both are charged", () => {
    expect(feeLines(quote()).map((line) => line.key))
      .toEqual(["cancel.feePeriod", "cancel.feeBuyOut"]);
  });

  it("leaves out a part that is not charged", () => {
    // A line reading "leaving the commitment early · 0.00" states a price for something that
    // is not on offer, which is worse than saying nothing: a zero in a money column is a
    // figure, and this one would be a figure about a charge that does not exist.
    expect(feeLines(quote({
      fee_parts: { period_minor: 4000, early_termination_minor: 0 },
    })).map((line) => line.key)).toEqual(["cancel.feePeriod"]);
    expect(feeLines(quote({
      fee_parts: { period_minor: 0, early_termination_minor: 8000 },
    })).map((line) => line.key)).toEqual(["cancel.feeBuyOut"]);
    expect(feeLines(quote({
      fee_parts: { period_minor: 0, early_termination_minor: 0 },
    }))).toEqual([]);
  });

  it("has no lines where the server sent no breakdown", () => {
    // A repeat answers from the recorded row, which carries the total and not its parts --
    // so the breakdown is absent rather than reconstructed against terms that may have been
    // superseded since.
    expect(feeLines(quote({ fee_parts: null }))).toEqual([]);
  });

  it("never adds the parts up", () => {
    // **The total is the server's**, because it is the figure the form echoes back for the
    // disclosure check. A sum computed here would be a second arithmetic that agrees until
    // the day it does not, which is the defect this whole screen was built out of.
    const odd = quote({
      disclosed_fee_minor: 999,
      fee_parts: { period_minor: 1, early_termination_minor: 1 },
    });
    expect(feeLines(odd).reduce((total, line) => total + line.minor, 0)).toBe(2);
    expect(odd.disclosed_fee_minor).toBe(999);
  });
});

describe("whether a freeze is offered instead", () => {
  const dormant = DORMANT_AFTER_DAYS;

  it("makes the canvas's own argument where both halves of it hold", () => {
    expect(freezeOffer(quote(), 12)).toBe("dormant_and_committed");
  });

  it("drops the dormancy half for somebody who is still coming", () => {
    expect(freezeOffer(quote(), 1)).toBe("committed");
    expect(freezeOffer(quote(), dormant - 1)).toBe("committed");
    expect(freezeOffer(quote(), dormant)).toBe("dormant_and_committed");
  });

  it("drops the commitment half where there is no commitment to keep", () => {
    // "A freeze keeps the commitment intact" describes a benefit that does not exist for a
    // member on a rolling contract, so the sentence that says it is not the one shown.
    const rolling = quote({
      commitment: {
        minimum_term_months: 0, ends_on: null, leaving_early: false,
        early_termination_months: null, may_leave_early: false,
      },
    });
    expect(freezeOffer(rolling, 30)).toBe("dormant");
    expect(freezeOffer(rolling, 1)).toBeNull();
  });

  it("offers nothing where the contract allows no freezing", () => {
    // The precondition for every branch: `check_freeze` refuses one whatever the session
    // holds, so offering it would point at a form that cannot accept them.
    const noFreeze = quote({ freeze_is_an_alternative: false });
    expect(freezeOffer(noFreeze, 30)).toBeNull();
    expect(freezeOffer(noFreeze, 1)).toBeNull();
  });

  it("treats an unknown last visit as not dormant", () => {
    // **MOD-014's rule, in the same direction: absent data is not a fact about somebody.**
    // `days_since` is null at a club with no readers as readily as for a member who never
    // came, and a screen that read the first as the second would tell a receptionist
    // somebody had stopped attending on the strength of there being no turnstile.
    expect(freezeOffer(quote(), null)).toBe("committed");
    expect(freezeOffer(quote({
      commitment: {
        minimum_term_months: 0, ends_on: null, leaving_early: false,
        early_termination_months: null, may_leave_early: false,
      },
    }), null)).toBeNull();
  });
});

describe("what this reader is offered", () => {
  const gate = (allowed: boolean, verdict = "allowed") => ({ allowed, verdict });

  it("gives the form to a session that may act", () => {
    expect(affordanceFor(quote(), gate(true))).toBe("form");
  });

  it("offers a step-up to one that could after a stronger sign-in", () => {
    expect(affordanceFor(quote(), gate(false, "needs_step_up"))).toBe("step_up");
  });

  it("says so where the membership cannot be cancelled by anybody", () => {
    // **Before the gate, and that order is the point.** `check_transition` refuses this
    // whatever the session holds, so a step-up would send somebody to find a second factor
    // that changes nothing. It holds even for a session that may act.
    const done = quote({ may_cancel: false, refused_because: "no such transition" });
    expect(affordanceFor(done, gate(true))).toBe("cannot");
    expect(affordanceFor(done, gate(false, "needs_step_up"))).toBe("cannot");
    expect(affordanceFor(done, gate(false, "denied"))).toBe("cannot");
  });

  it("says refused where no step-up would help", () => {
    expect(affordanceFor(quote(), gate(false, "denied"))).toBe("refused");
    expect(affordanceFor(quote(), gate(false, "gate_failed"))).toBe("refused");
  });
});
