import { describe, expect, it } from "vitest";

import {
  affordanceFor, freezeDays, refusalFor, startIsAllowed, wouldRemain,
  type FreezeAllowance,
} from "@/lib/freeze";

/**
 * ADM-MSH-03's arithmetic. What a freeze costs and whether it is allowed are the server's;
 * what is here is the conversion between the two dates the canvas draws and the length the
 * module takes, plus the order a refusal is reported in.
 */

const allowance = (over: Partial<FreezeAllowance> = {}): FreezeAllowance => ({
  membership_id: "m-1",
  status: "active",
  counting_an_open_freeze: false,
  contract_year: { from: "2026-03-01", to: "2027-02-28" },
  allowance_days: 30,
  days_used: 0,
  days_remaining: 30,
  may_start_between: { from: "2026-10-22", to: "2026-11-22" },
  allows_freezing: true,
  an_open_freeze_counts_to_the_year_end: "x",
  the_figure_is_the_writes_own: "x",
  ...over,
});

describe("the length of a freeze", () => {
  it("counts both ends, because the canvas draws FROM and UNTIL", () => {
    // `freeze_membership` stores `planned_ends_on = starts_on + days - 1`, so a freeze from
    // the first to the first is one day. Treating the pair as exclusive spends somebody's
    // allowance a day at a time, in the direction nobody checks.
    expect(freezeDays("2026-11-01", "2026-11-01")).toBe(1);
    expect(freezeDays("2026-11-01", "2026-11-02")).toBe(2);
    expect(freezeDays("2026-09-01", "2026-09-30")).toBe(30);
  });

  it("crosses a month, a year and a clock change without losing a day", () => {
    // UTC on a date-only string: a difference taken in the host's zone is a day out on the
    // two nights a year it shifts.
    expect(freezeDays("2026-12-28", "2027-01-03")).toBe(7);
    expect(freezeDays("2026-03-26", "2026-04-01")).toBe(7);
    expect(freezeDays("2026-10-29", "2026-11-04")).toBe(7);
  });

  it("refuses a backwards span and anything that is not a date", () => {
    expect(freezeDays("2026-11-02", "2026-11-01")).toBeNull();
    for (const bad of ["", "2026-13-01", "01-11-2026", "2026-11", "tomorrow"]) {
      expect(freezeDays(bad, "2026-11-30"), bad).toBeNull();
      expect(freezeDays("2026-11-01", bad), bad).toBeNull();
    }
  });
});

describe("the window a freeze may start in", () => {
  it("includes both of its ends", () => {
    // The module takes a start within the month before today -- a month back because one
    // agreed at the desk on Friday is recorded on Monday -- and an exclusive end would drop
    // the day most freezes are actually recorded on.
    const window = { from: "2026-10-22", to: "2026-11-22" };
    expect(startIsAllowed("2026-10-22", window)).toBe(true);
    expect(startIsAllowed("2026-11-22", window)).toBe(true);
    expect(startIsAllowed("2026-11-05", window)).toBe(true);
  });

  it("excludes the future, which is the module's own refusal", () => {
    // Nothing in this build applies a booked freeze when its day arrives, and a booked
    // freeze that never takes effect is worse than one that cannot be booked.
    const window = { from: "2026-10-22", to: "2026-11-22" };
    expect(startIsAllowed("2026-11-23", window)).toBe(false);
    expect(startIsAllowed("2026-10-21", window)).toBe(false);
  });
});

describe("what a freeze would leave", () => {
  it("is the remainder after this one", () => {
    expect(wouldRemain(allowance(), "2026-11-01", "2026-11-07")).toBe(23);
    expect(wouldRemain(allowance({ days_remaining: 7 }), "2026-11-01", "2026-11-07"))
      .toBe(0);
  });

  it("goes negative rather than clamping, because that is the refusal", () => {
    // A panel that showed 0 for both "exactly spent" and "over by eight" would hide the one
    // state the reader has to act on.
    expect(wouldRemain(allowance({ days_remaining: 5 }), "2026-11-01", "2026-11-07"))
      .toBe(-2);
  });
});

describe("why a freeze is refused", () => {
  it("names the contract before anything else", () => {
    // `check_freeze` refuses a contract that allows no freezing outright, so a form that
    // reported bad dates over it would send somebody to fix the wrong thing.
    expect(refusalFor(allowance({ allows_freezing: false, days_remaining: 0 }),
                      "not-a-date", "also-not"))
      .toBe("freeze.noAllowance");
  });

  it("names the start window before the allowance", () => {
    // Otherwise it tells somebody to shorten a freeze whose date the server was going to
    // refuse anyway -- the order is the server's, so the reasons are too.
    expect(refusalFor(allowance({ days_remaining: 1 }), "2026-11-25", "2026-12-25"))
      .toBe("freeze.startOutsideWindow");
  });

  it("names a length over a year before the allowance, as check_freeze does", () => {
    expect(refusalFor(allowance({ days_remaining: 400 }), "2026-11-01", "2028-11-01"))
      .toBe("freeze.tooLong");
  });

  it("names the allowance last", () => {
    expect(refusalFor(allowance({ days_remaining: 3 }), "2026-11-01", "2026-11-07"))
      .toBe("freeze.overAllowance");
  });

  it("is null for a freeze the module would take", () => {
    expect(refusalFor(allowance(), "2026-11-01", "2026-11-07")).toBeNull();
    // Exactly the remainder is allowed; `check_freeze` refuses only what exceeds it.
    expect(refusalFor(allowance({ days_remaining: 7 }), "2026-11-01", "2026-11-07"))
      .toBeNull();
  });
});


describe("what the reader is offered", () => {
  /**
   * **This block exists because a mutation passed a green suite.** The fixture's contract
   * allows thirty freeze days, so the "this contract allows no freezing" branch never
   * rendered and deleting it changed nothing any test could see -- the "branch no fixture
   * can reach" shape this repository records for four modules. A decision is testable where
   * a rendered branch is not.
   */
  const gate = (allowed: boolean, verdict = "denied") => ({ allowed, verdict });

  it("offers the form to a session that may act", () => {
    expect(affordanceFor({ allows_freezing: true }, gate(true))).toBe("form");
  });

  it("offers a step-up to one that could after a stronger sign-in", () => {
    expect(affordanceFor({ allows_freezing: true }, gate(false, "needs_step_up")))
      .toBe("step_up");
  });

  it("offers neither where the contract forbids freezing at all", () => {
    // **Before the gate, and that order is the point.** `check_freeze` refuses this whatever
    // the session holds, so a step-up would send somebody to find a second factor that
    // changes nothing -- the member record's own rule about a health field, applied to a
    // write. It holds even for a session that may act.
    expect(affordanceFor({ allows_freezing: false }, gate(true))).toBe("no_allowance");
    expect(affordanceFor({ allows_freezing: false }, gate(false, "needs_step_up")))
      .toBe("no_allowance");
    expect(affordanceFor({ allows_freezing: false }, gate(false, "denied")))
      .toBe("no_allowance");
  });

  it("says refused where no step-up would help", () => {
    expect(affordanceFor({ allows_freezing: true }, gate(false, "denied"))).toBe("refused");
    expect(affordanceFor({ allows_freezing: true }, gate(false, "gate_failed")))
      .toBe("refused");
  });
});
